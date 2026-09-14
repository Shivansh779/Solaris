"""Tests for specialist_ai plumbing.

All network calls are replaced with fake client objects that reply from
memory, so nothing reaches an API. Facts verified: provider/model selection,
task-name plumbing, fallback behavior, and delegation to helper_ai prompt
builders.
"""

import json

import pytest

import specialist_ai

with open("config.json") as f:
    CONFIG = json.load(f)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeChat:
    def __init__(self, owner):
        self.completions = FakeCompletions(owner)


class FakeCompletions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, model, messages):
        self.owner.calls.append(("chat", model, messages))
        if self.owner.error:
            raise self.owner.error
        msg = type("M", (), {"content": self.owner.text})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


class FakeModels:
    def __init__(self, owner):
        self.owner = owner

    def generate_content(self, model, contents):
        self.owner.calls.append(("google", model, contents))
        if self.owner.error:
            raise self.owner.error
        return FakeResponse(self.owner.text)


class FakeClient:
    def __init__(self, text="ok", error=None):
        self.text = text
        self.error = error
        self.calls = []
        self.chat = FakeChat(self)
        self.models = FakeModels(self)


class TestCallModel:
    def test_google_provider_success(self):
        client = FakeClient(text="gemini reply")
        result = specialist_ai._call_model(client, "google", "model-1", "prompt-1")
        assert result == "gemini reply"
        assert client.calls == [("google", "model-1", "prompt-1")]

    def test_openai_style_provider_success(self):
        client = FakeClient(text="chat reply")
        result = specialist_ai._call_model(client, "ollama-cloud", "model-1", "prompt-1")
        assert result == "chat reply"
        assert client.calls[0] == ("chat", "model-1", [{"role": "user", "content": "prompt-1"}])

    def test_provider_error_propagates(self):
        client = FakeClient(error=RuntimeError("down"))
        with pytest.raises(RuntimeError):
            specialist_ai._call_model(client, "ollama-cloud", "m", "p")


class TestTryFallback:
    def test_primary_success(self):
        primary = FakeClient(text="primary ok")
        result = specialist_ai._try_fallback(
            lambda: "built prompt", primary, "ollama-cloud", "p-model",
            FakeClient(), "ollama-cloud", "s-model", "coding",
        )
        assert result == "primary ok"
        assert primary.calls[0][1] == "p-model"

    def test_falls_back_to_secondary(self):
        secondary = FakeClient(text="secondary ok")
        result = specialist_ai._try_fallback(
            lambda: "built prompt", FakeClient(error=RuntimeError("down")),
            "ollama-cloud", "p-model", secondary, "ollama-cloud", "s-model", "writing",
        )
        assert result == "secondary ok"
        assert secondary.calls[0][1] == "s-model"

    def test_both_fail_mentions_task_name(self):
        result = specialist_ai._try_fallback(
            lambda: "built prompt",
            FakeClient(error=ValueError("a")), "ollama-cloud", "p-model",
            FakeClient(error=ValueError("b")), "ollama-cloud", "s-model", "strategist",
        )
        assert result == "Both primary and secondary models failed to generate a response for strategist."


class TestDelegation:
    """coder/writer/questionaire must read config.json and pass the builder
    output (prompt text) to the client, along with the configured model."""

    def test_coder_prompt_and_models(self):
        spec = CONFIG["specialist"]["coding"]
        client = FakeClient(text="code")
        result = specialist_ai.coder("sum a list", client, FakeClient(), attachment_context="f.py")
        assert result == "code"
        assert client.calls[0][1] == spec["primary"]["name"]
        content = client.calls[0][2][0]["content"]
        assert "Solaris' coding specialist" in content
        assert "sum a list" in content
        assert "f.py" in content

    def test_coder_falls_back_to_secondary(self):
        spec = CONFIG["specialist"]["coding"]
        secondary = FakeClient(text="fallback code")
        result = specialist_ai.coder("fix bug", FakeClient(error=RuntimeError("down")), secondary)
        assert result == "fallback code"
        assert secondary.calls[0][1] == spec["secondary"]["name"]

    def test_writer_prompt_and_models(self):
        spec = CONFIG["specialist"]["writing"]
        client = FakeClient(text="draft")
        specialist_ai.writer("make it shorter", client, FakeClient())
        assert client.calls[0][1] == spec["primary"]["name"]
        content = client.calls[0][2][0]["content"]
        assert "Solaris' writing specialist" in content
        assert "make it shorter" in content

    def test_questionaire_prompt_and_models(self):
        spec = CONFIG["specialist"]["reasoning"]
        client = FakeClient(text="q")
        specialist_ai.questionaire("build a chatbot", client, FakeClient())
        assert client.calls[0][1] == spec["primary"]["name"]
        content = client.calls[0][2][0]["content"]
        assert "planning-question stage of Solaris' Strategist mode" in content
        assert "build a chatbot" in content

    def test_strategist_includes_previous_draft(self):
        client = FakeClient(text="design")
        specialist_ai.strategist(
            "make a notes app", client, FakeClient(),
            ai_questions="q1", answers="a1", previous_draft="old draft",
        )
        content = client.calls[0][2][0]["content"]
        assert "Solaris' Strategist" in content
        assert "Previous Draft:" in content
        assert "old draft" in content

    def test_strategist_force_secondary_uses_secondary(self):
        spec = CONFIG["specialist"]["reasoning"]
        secondary = FakeClient(text="revised")
        result = specialist_ai.strategist(
            "goal", FakeClient(), secondary,
            ai_questions="q", answers="a", force_secondary=True,
        )
        assert result == "revised"
        assert secondary.calls[0][1] == spec["secondary"]["name"]

    def test_strategist_force_secondary_falls_back_to_primary(self):
        spec = CONFIG["specialist"]["reasoning"]
        primary = FakeClient(text="primary revised")
        result = specialist_ai.strategist(
            "goal", primary, FakeClient(error=RuntimeError("down")),
            ai_questions="q", answers="a", force_secondary=True,
        )
        assert result == "primary revised"
        assert primary.calls[0][1] == spec["primary"]["name"]

    def test_strategist_force_secondary_both_fail(self):
        result = specialist_ai.strategist(
            "goal", FakeClient(error=ValueError("a")), FakeClient(error=ValueError("b")),
            ai_questions="q", answers="a", force_secondary=True,
        )
        assert result == "Both models failed to generate a revised draft."

    def test_strategist_default_path_uses_primary(self):
        spec = CONFIG["specialist"]["reasoning"]
        primary = FakeClient(text="design v1")
        result = specialist_ai.strategist("goal", primary, FakeClient(), ai_questions="q", answers="a")
        assert result == "design v1"
        assert primary.calls[0][1] == spec["primary"]["name"]