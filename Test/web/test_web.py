import json
import os

import pytest
import requests

import web_search

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

with open(os.path.join(ROOT, "config.json")) as f:
    WEB_CFG = json.load(f)["web"]


class FakeResponse:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise requests.HTTPError("upstream error")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_logging(monkeypatch):
    monkeypatch.setattr("web_search.system_log", lambda *a, **k: None)


@pytest.fixture
def _keys(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "t-key")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f-key")
    yield


class TestConfigLoad:
    def test_depths_match_config_json(self):
        assert web_search.DEPTHS == WEB_CFG["depths"]
        assert web_search.DEPTHS == {"quick": 3, "standard": 5, "deep": 8}


class TestDepthKey:
    def test_int_aliases(self):
        assert web_search._depth_key(1) == "quick"
        assert web_search._depth_key(2) == "standard"
        assert web_search._depth_key(3) == "deep"

    def test_string_passthrough(self):
        assert web_search._depth_key("quick") == "quick"
        assert web_search._depth_key("deep") == "deep"

    def test_unknown_falls_back_to_standard(self):
        assert web_search._depth_key("bogus") == "standard"
        assert web_search._depth_key(None) == "standard"


class TestTavily:
    def test_formats_results(self, monkeypatch, _keys):
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse({"results": [
                {"title": "T", "url": "http://x", "content": "alpha"},
                {"title": "", "url": "", "content": None},
            ]})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        results = web_search._tavily("hello world", 5)
        assert results == [
            {"title": "T", "url": "http://x", "content": "alpha", "source": "tavily"},
            {"title": "", "url": "", "content": "", "source": "tavily"},
        ]
        assert captured["url"] == "https://api.tavily.com/search"
        assert captured["kwargs"]["json"] == {
            "api_key": "t-key",
            "query": "hello world",
            "max_results": 5,
        }
        assert captured["kwargs"]["timeout"] == 30

    def test_truncates_content_to_max(self, monkeypatch, _keys):
        def fake_post(url, **kwargs):
            return FakeResponse({"results": [{"title": "T", "url": "u", "content": "x" * 2000}]})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        results = web_search._tavily("q", 3)
        assert len(results[0]["content"]) == web_search.MAX_CONTENT_CHARS

    def test_missing_key_returns_none_without_network(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

        def fail_post(url, **kwargs):
            raise AssertionError("network should not be hit")

        monkeypatch.setattr("web_search.requests.post", fail_post)
        assert web_search._tavily("q", 3) is None

    def test_empty_results(self, monkeypatch, _keys):
        monkeypatch.setattr(
            "web_search.requests.post",
            lambda url, **kwargs: FakeResponse({"results": []}),
        )
        assert web_search._tavily("q", 3) == []


class TestFirecrawl:
    def test_formats_results(self, monkeypatch, _keys):
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse({"data": [
                {"title": "F", "url": "http://f", "description": "fred"},
            ]})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        results = web_search._firecrawl("cats", 5)
        assert results == [
            {"title": "F", "url": "http://f", "content": "fred", "source": "firecrawl"}
        ]
        assert captured["url"] == "https://api.firecrawl.dev/v1/search"
        assert captured["kwargs"]["headers"] == {
            "Authorization": "Bearer f-key",
            "Content-Type": "application/json",
        }
        assert captured["kwargs"]["json"] == {"query": "cats", "limit": 5}
        assert captured["kwargs"]["timeout"] == 30

    def test_missing_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

        def fail_post(url, **kwargs):
            raise AssertionError("network should not be hit")

        monkeypatch.setattr("web_search.requests.post", fail_post)
        assert web_search._firecrawl("q", 3) is None


class TestSearchWeb:
    def test_uses_tavily_first_and_stops(self, monkeypatch, _keys):
        urls = []

        def fake_post(url, **kwargs):
            urls.append(url)
            return FakeResponse({"results": [{"title": "A", "url": "http://a", "content": "a"}]})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        results = web_search.search_web("python")
        assert results[0]["source"] == "tavily"
        assert urls == ["https://api.tavily.com/search"], "Firecrawl should not be reached"

    def test_falls_back_to_firecrawl_when_tavily_fails(self, monkeypatch, _keys):
        def fake_post(url, **kwargs):
            if "tavily" in url:
                raise requests.ConnectionError("tavily down")
            return FakeResponse({"data": [{"title": "F", "url": "http://f", "description": "fd"}]})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        results = web_search.search_web("python")
        assert results[0]["source"] == "firecrawl"
        assert results[0]["url"] == "http://f"

    def test_http_error_triggers_fallback(self, monkeypatch, _keys):
        def fake_post(url, **kwargs):
            if "tavily" in url:
                return FakeResponse({}, ok=False)
            return FakeResponse({"data": [{"title": "F", "url": "http://f", "description": "fd"}]})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        results = web_search.search_web("q")
        assert results[0]["source"] == "firecrawl"

    def test_empty_results_everywhere_returns_none(self, monkeypatch, _keys):
        monkeypatch.setattr(
            "web_search.requests.post",
            lambda url, **kwargs: (
                FakeResponse({"results": []})
                if "tavily" in url
                else FakeResponse({"data": []})
            ),
        )
        assert web_search.search_web("q") is None

    def test_all_providers_error_returns_none(self, monkeypatch, _keys):
        def boom(url, **kwargs):
            raise requests.ConnectionError("everything is on fire")

        monkeypatch.setattr("web_search.requests.post", boom)
        assert web_search.search_web("q") is None

    def test_no_api_keys_returns_none(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

        def fail_post(url, **kwargs):
            raise AssertionError("network should not be hit")

        monkeypatch.setattr("web_search.requests.post", fail_post)
        assert web_search.search_web("q") is None

    def test_deep_depth_passes_max_results_8(self, monkeypatch, _keys):
        captured = {}

        def fake_post(url, **kwargs):
            if "tavily" in url:
                captured["json"] = kwargs["json"]
                return FakeResponse({"results": [{"title": "a", "url": "u", "content": "c"}]})
            return FakeResponse({"data": []})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        web_search.search_web("q", depth="deep")
        assert captured["json"]["max_results"] == 8

    def test_int_depth_2_maps_to_standard_5(self, monkeypatch, _keys):
        captured = {}

        def fake_post(url, **kwargs):
            if "tavily" in url:
                captured["json"] = kwargs["json"]
                return FakeResponse({"results": [{"title": "a", "url": "u", "content": "c"}]})
            return FakeResponse({"data": []})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        web_search.search_web("q", depth=2)
        assert captured["json"]["max_results"] == 5

    def test_unknown_depth_defaults_to_standard(self, monkeypatch, _keys):
        captured = {}

        def fake_post(url, **kwargs):
            if "tavily" in url:
                captured["json"] = kwargs["json"]
                return FakeResponse({"results": [{"title": "a", "url": "u", "content": "c"}]})
            return FakeResponse({"data": []})

        monkeypatch.setattr("web_search.requests.post", fake_post)
        web_search.search_web("q", depth="nonsense")
        assert captured["json"]["max_results"] == 5