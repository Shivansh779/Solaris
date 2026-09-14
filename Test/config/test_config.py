"""Tests for config module: PROVIDERS table, init_client, aliases, config.json structure.

No network: OpenAI/genai clients are constructed with api_key=None (or a fake key)
but never used to make a request.
"""

import json
from pathlib import Path

import pytest
from google import genai
from openai import OpenAI

import config

ROOT = Path(__file__).resolve().parents[2]

OPENAI_PROVIDERS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openrouter-assist": "https://openrouter.ai/api/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama-cloud": "https://ollama.com/v1",
}


@pytest.mark.parametrize("provider", sorted(config.PROVIDERS))
def test_provider_entry_has_required_fields(provider):
    entry = config.PROVIDERS[provider]
    assert isinstance(entry["api_key_env"], str) and entry["api_key_env"]
    assert entry["api_key_env"].endswith("API_KEY")
    assert "base_url" in entry
    assert entry["client_class"] in (genai.Client, OpenAI)


@pytest.mark.parametrize(
    "provider,expected_base", sorted(OPENAI_PROVIDERS.items())
)
def test_init_client_openai_provider_sets_base_url(monkeypatch, provider, expected_base):
    monkeypatch.setenv(config.PROVIDERS[provider]["api_key_env"], "sk-fake-test-key")
    client = config.init_client(provider)
    assert isinstance(client, OpenAI)
    assert str(client.base_url).rstrip("/") == expected_base.rstrip("/")
    assert client.api_key == "sk-fake-test-key"


def test_init_client_gemini_has_no_base_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fake-test-key")
    client = config.init_client("gemini")
    assert isinstance(client, genai.Client)
    assert getattr(client, "base_url", None) is None


def test_init_client_requires_env_key(monkeypatch):
    """Missing key -> friendly RuntimeError naming provider and env var."""
    monkeypatch.delenv("OR_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for provider, var in (("openrouter", "OR_API_KEY"), ("gemini", "GEMINI_API_KEY")):
        with pytest.raises(RuntimeError, match=var):
            config.init_client(provider)


def test_init_client_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        config.init_client("does-not-exist")
    with pytest.raises(ValueError):
        config.init_client("")


@pytest.mark.parametrize(
    "alias,provider,expected_base",
    [
        ("init_gemini", "gemini", None),
        ("init_openrouter", "openrouter", "https://openrouter.ai/api/v1"),
        ("init_assist_or", "openrouter-assist", "https://openrouter.ai/api/v1"),
        ("init_nvidia", "nvidia", "https://integrate.api.nvidia.com/v1"),
        ("init_groq", "groq", "https://api.groq.com/openai/v1"),
        ("init_ollama_cloud", "ollama-cloud", "https://ollama.com/v1"),
    ],
)
def test_backward_compat_aliases(monkeypatch, alias, provider, expected_base):
    monkeypatch.setenv(config.PROVIDERS[provider]["api_key_env"], "sk-fake-test-key")
    client = getattr(config, alias)()
    if expected_base is None:
        assert isinstance(client, genai.Client)
        assert getattr(client, "base_url", None) is None
    else:
        assert isinstance(client, OpenAI)
        assert str(client.base_url).rstrip("/") == expected_base.rstrip("/")


@pytest.fixture(scope="module")
def models():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


def test_config_top_level_keys_present(models):
    for key in ("gemini", "openrouter", "local", "or_assist", "web",
                "vision_model", "specialist"):
        assert key in models, f"missing top-level key: {key}"


def test_gemini_model_is_nonempty_str(models):
    assert isinstance(models["gemini"], str) and models["gemini"].strip()


def test_openrouter_models_is_list_of_str(models):
    assert isinstance(models["openrouter"], list)
    assert len(models["openrouter"]) > 0
    assert all(isinstance(m, str) and m.strip() for m in models["openrouter"])


def test_local_model_is_nonempty_str(models):
    assert isinstance(models["local"], str) and "/" in models["local"]


def test_or_assist_is_nonempty_str(models):
    assert isinstance(models["or_assist"], str) and models["or_assist"].strip()


def test_web_depths(models):
    depths = models["web"]["depths"]
    for key in ("quick", "standard", "deep"):
        assert key in depths and isinstance(depths[key], int)


def test_vision_model_primary_secondary(models):
    for slot in ("primary", "secondary"):
        entry = models["vision_model"][slot]
        assert entry["model"]
        assert isinstance(entry["provider"], str) and entry["provider"]


@pytest.mark.parametrize("area", ["coding", "writing", "reasoning", "study"])
def test_specialist_area_primary_secondary(models, area):
    spec = models["specialist"][area]
    for slot in ("primary", "secondary"):
        entry = spec[slot]
        assert entry["name"], f"{area}.{slot}.name missing"
        assert isinstance(entry["provider"], str) and entry["provider"]


def _collect_provider_refs(node):
    if isinstance(node, dict):
        if "provider" in node:
            yield node["provider"]
        for value in node.values():
            yield from _collect_provider_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _collect_provider_refs(value)


def test_every_config_provider_maps_to_provider_table(models):
    referenced = set(_collect_provider_refs(models))
    assert referenced, "no provider fields found in config.json"
    for provider in referenced:
        entry = config.PROVIDERS.get(provider)
        assert entry is not None, f"provider referenced in config.json not in PROVIDERS: {provider}"
        assert entry["api_key_env"] and entry["base_url"] is not None