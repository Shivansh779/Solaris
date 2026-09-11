"""Tests for study_ai prompt templates and the study() fallback logic.

study() never touches the network here: fake client objects reply locally.
"""

import pytest

import study_ai


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


def make_config(provider):
    return {
        "specialist": {
            "study": {
                "primary": {"name": "primary-model", "provider": provider},
                "secondary": {"name": "secondary-model", "provider": provider},
            }
        }
    }


class TestBuildPrompt:
    @pytest.mark.parametrize("mode", list(study_ai.PROMPT_TEMPLATES))
    def test_builds_template(self, mode):
        prompt = study_ai.build_prompt("photosynthesis", mode)
        assert prompt is not None
        assert "photosynthesis" in prompt
        assert "{topic}" not in prompt

    def test_detail_keywords(self):
        prompt = study_ai.build_prompt("gravity", "detail")
        assert "expert teacher" in prompt
        assert "college-lecture" in prompt
        assert "## Output Format" in prompt

    def test_simple_keywords(self):
        prompt = study_ai.build_prompt("gravity", "simple")
        assert "plain, everyday language" in prompt
        assert "imagine that..." in prompt

    def test_quiz_keywords(self):
        prompt = study_ai.build_prompt("gravity", "quiz")
        assert "exactly 10" in prompt
        assert "A, B, C, D" in prompt
        assert "Answer: A" in prompt

    def test_timeline_keywords(self):
        prompt = study_ai.build_prompt("World War II", "timeline")
        assert "chronological order" in prompt
        assert "### Era/Period Name (Year)" in prompt

    def test_compare_keywords(self):
        prompt = study_ai.build_prompt("python vs java", "compare")
        assert "side-by-side comparison" in prompt
        assert "| Dimension | Subject1 | Subject2 |" in prompt

    def test_steps_keywords(self):
        prompt = study_ai.build_prompt("make a cake", "steps")
        assert "7-10 steps" in prompt
        assert "Step 1: Action" in prompt

    def test_unknown_mode_falls_back_to_detail(self):
        prompt = study_ai.build_prompt("gravity", "does-not-exist")
        assert "expert teacher" in prompt
        assert "gravity" in prompt


class TestStudy:
    def _patch_config(self, monkeypatch, provider):
        monkeypatch.setattr(study_ai.json, "load", lambda f: make_config(provider))

    def test_google_provider_primary_success(self, monkeypatch):
        self._patch_config(monkeypatch, "google")
        client = FakeClient(text="full explanation")
        result = study_ai.study("gravity", client, FakeClient(), "detail")
        assert result == "full explanation"
        assert client.calls[0][0] == "google"
        assert client.calls[0][1] == "primary-model"
        assert "gravity" in client.calls[0][2]

    def test_openai_style_primary_success(self, monkeypatch):
        self._patch_config(monkeypatch, "ollama-cloud")
        client = FakeClient(text="explained")
        result = study_ai.study("gravity", client, FakeClient(), "simple")
        assert result == "explained"
        assert client.calls[0][0] == "chat"
        assert client.calls[0][1] == "primary-model"

    def test_falls_back_to_secondary(self, monkeypatch):
        self._patch_config(monkeypatch, "ollama-cloud")
        primary = FakeClient(error=RuntimeError("down"))
        secondary = FakeClient(text="secondary answer")
        result = study_ai.study("gravity", primary, secondary, "detail")
        assert result == "secondary answer"
        assert secondary.calls[0][1] == "secondary-model"

    def test_both_fail(self, monkeypatch):
        self._patch_config(monkeypatch, "google")
        result = study_ai.study(
            "gravity", FakeClient(error=ValueError("a")), FakeClient(error=ValueError("b")), "detail",
        )
        assert result == "Both models failed to generate a response for this study request."