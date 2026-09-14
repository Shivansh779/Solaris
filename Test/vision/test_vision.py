import base64
import json
import os
from types import SimpleNamespace

import pytest
from google.genai import types as genai_types

from vision_ai import (
    _build_google_parts,
    _build_openai_parts,
    _build_vision_prompt,
    _call,
    vision,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JPG = os.path.join(ROOT, "test_attach.jpg")
JPG_BYTES = open(JPG, "rb").read()

with open(os.path.join(ROOT, "config.json")) as f:
    VISION_CFG = json.load(f)["vision_model"]

PRIMARY_MODEL = VISION_CFG["primary"]["model"]
PRIMARY_PROVIDER = VISION_CFG["primary"]["provider"]
SECONDARY_MODEL = VISION_CFG["secondary"]["model"]


def _resp(text):
    return SimpleNamespace(
        text=text,
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


class FakeCompletions:
    def __init__(self, mode, answer):
        self.mode = mode
        self.answer = answer
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.mode == "raise":
            raise RuntimeError("nvidia boom")
        return _resp(self.answer)


class FakeChat:
    def __init__(self, mode, answer):
        self.completions = FakeCompletions(mode, answer)


class FakeModels:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return _resp(self.answer)


class FakeClient:
    def __init__(self, mode="ok", answer="primary answer"):
        self.chat = FakeChat(mode, answer)
        self.models = FakeModels(answer)


@pytest.fixture(autouse=True)
def _no_logging(monkeypatch):
    monkeypatch.setattr("vision_ai.system_log", lambda *a, **k: None)


def _images(n=1):
    return [{"path": JPG, "mime_type": "image/jpeg", "metadata": {}} for _ in range(n)]


class TestPrompt:
    def test_singular_image(self):
        prompt = _build_vision_prompt("What color is the car?", 1)
        assert "Analyze the attached image carefully" in prompt
        assert "Analyze the attached images" not in prompt
        assert "What color is the car?" in prompt

    def test_plural_images(self):
        prompt = _build_vision_prompt("Compare them.", 3)
        assert "Analyze the attached images carefully" in prompt
        assert "Compare them." in prompt

    def test_includes_no_hallucination_rule(self):
        assert "Do not guess or hallucinate" in _build_vision_prompt("x", 1)


class TestOpenAIParts:
    def test_payload_shape(self):
        parts = _build_openai_parts([{"path": JPG, "mime_type": "image/jpeg", "metadata": {}}])
        assert parts[0]["type"] == "image_url"
        url = parts[0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        raw = url.split(",", 1)[1]
        assert base64.b64decode(raw) == JPG_BYTES


class TestGoogleParts:
    def test_part_from_bytes(self):
        parts = _build_google_parts([{"path": JPG, "mime_type": "image/jpeg", "metadata": {}}])
        assert isinstance(parts[0], genai_types.Part)
        inline = parts[0].inline_data
        assert inline.mime_type == "image/jpeg"
        assert bytes(inline.data) == JPG_BYTES


class TestCall:
    def test_openai_path(self):
        client = FakeClient()
        result = _call(client, "nvidia", "some-model", "q?", _images())
        assert result == "primary answer"
        kwargs = client.chat.completions.calls[0]
        assert kwargs["model"] == "some-model"
        content = kwargs["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "q?"}
        assert content[1]["type"] == "image_url"

    def test_google_path(self):
        client = FakeClient(answer="google answer")
        result = _call(client, "google", "gemini-test", "q?", _images())
        assert result == "google answer"
        kwargs = client.models.calls[0]
        assert kwargs["model"] == "gemini-test"
        assert kwargs["contents"][0] == "q?"
        assert isinstance(kwargs["contents"][1], genai_types.Part)


class TestVisionFlow:
    def test_primary_payload_matches_config(self):
        client = FakeClient()
        result = vision("What is this?", client, FakeClient(), _images())
        assert result == "primary answer"
        kwargs = client.chat.completions.calls[0]
        assert kwargs["model"] == PRIMARY_MODEL
        assert PRIMARY_PROVIDER == "nvidia", "assumes config uses the OpenAI-compatible path"
        content = kwargs["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert "What is this?" in content[0]["text"]
        image_url = content[1]["image_url"]["url"]
        assert image_url.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(image_url.split(",", 1)[1]) == JPG_BYTES

    def test_falls_back_to_secondary_on_primary_failure(self):
        primary = FakeClient(mode="raise")
        secondary = FakeClient(answer="fallback answer")
        result = vision("Q", primary, secondary, _images())
        assert result == "fallback answer"
        sec_kwargs = secondary.chat.completions.calls[0]
        assert sec_kwargs["model"] == SECONDARY_MODEL

    def test_llama_secondary_truncates_to_one_image(self):
        primary = FakeClient(mode="raise")
        secondary = FakeClient(answer="fallback answer")
        result = vision("Q", primary, secondary, _images(n=3))
        assert result == "fallback answer"
        sec_kwargs = secondary.chat.completions.calls[0]
        content = sec_kwargs["messages"][0]["content"]
        assert len(content) == 2, "text part + exactly one image part"
        assert content[1]["type"] == "image_url"

    def test_both_models_fail(self):
        client = FakeClient(mode="raise")
        result = vision("Q", client, FakeClient(mode="raise"), _images())
        assert result == "Both vision models failed to analyze the image."

    def test_no_primary_configured(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.json").write_text(json.dumps({"web": {}}))
        result = vision("Q", FakeClient(), FakeClient(), _images())
        assert result == "No primary vision model configured. Add vision_model.primary to config.json."