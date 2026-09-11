"""Tests for helper_ai prompt builders.

Only pure string-building functions are tested, plus the summariser prompt
templates (network call stubbed out via _call_with_fallback monkeypatch).
"""

import pytest

import helper_ai

SETTINGS = helper_ai.settings


class TestBuildPrompt:
    def test_contains_role_and_sections(self):
        prompt = helper_ai.build_prompt(
            name="Shivansh",
            preference="use short answers",
            imp_conv_history="Working on Solaris",
            conversation_text="hello",
            memory_text="past memory",
            question="what is git",
            about_user="class 9 student",
        )
        assert "You are a personal assistant." in prompt
        assert "User Name: Shivansh" in prompt
        assert "Preference: use short answers" in prompt
        assert "Important Facts from Current Session:" in prompt
        assert "Conversation So Far:" in prompt
        assert "Past Sessions:" in prompt
        assert "About the User:" in prompt
        assert "User's question: what is git" in prompt

    def test_interpolates_settings(self):
        prompt = helper_ai.build_prompt(
            name="n", preference="p", imp_conv_history="", conversation_text="",
            memory_text="", question="q", about_user="",
        )
        assert f"up to maximum {SETTINGS['response']['maximum_length']} sentences." in prompt
        assert f"Emoji Density: {SETTINGS['response']['emoji_density']}" in prompt
        assert f"Be {SETTINGS['personality']['warmth'].title()} and {SETTINGS['personality']['humor'].title()}" in prompt

    def test_attachment_absent_when_not_given(self):
        prompt = helper_ai.build_prompt(
            name="n", preference="p", imp_conv_history="", conversation_text="",
            memory_text="", question="q", about_user="",
        )
        assert "Attached Files Context:" not in prompt

    def test_attachment_present_when_given(self):
        prompt = helper_ai.build_prompt(
            name="n", preference="p", imp_conv_history="", conversation_text="",
            memory_text="", question="q", about_user="", attachment_context="notes.md contents",
        )
        assert "Attached Files Context:" in prompt
        assert "notes.md contents" in prompt


class TestBuildWebPrompt:
    def test_numbered_sources(self):
        sources = [
            {"title": "Git Basics", "url": "https://a.example", "content": "git tracks changes"},
            {"title": "Branches", "url": "https://b.example", "content": "branches diverge"},
        ]
        prompt = helper_ai.build_web_prompt("what is git", sources)
        assert "You are a personal assistant with access to current web search results." in prompt
        assert "[1] Git Basics" in prompt
        assert "URL: https://a.example" in prompt
        assert "[2] Branches" in prompt
        assert "git tracks changes" in prompt
        assert "User's question: what is git" in prompt

    def test_empty_sources(self):
        prompt = helper_ai.build_web_prompt("hi", [])
        assert "[1] " not in prompt
        assert "User's question: hi" in prompt


class TestBuildCodingPrompt:
    def test_role_and_request(self):
        prompt = helper_ai.build_coding_prompt("debug this")
        assert "Solaris' coding specialist" in prompt
        assert "User's request: debug this" in prompt
        assert "Attached Files Context:" not in prompt

    def test_attachment_context(self):
        prompt = helper_ai.build_coding_prompt("review it", attachment_context="code.py")
        assert "Attached Files Context:" in prompt
        assert "code.py" in prompt


class TestBuildWritingPrompt:
    def test_role_and_request(self):
        prompt = helper_ai.build_writing_prompt("edit this")
        assert "Solaris' writing specialist" in prompt
        assert "User's request: edit this" in prompt

    def test_attachment_context(self):
        prompt = helper_ai.build_writing_prompt("edit this", attachment_context="essay.md")
        assert "Attached Files Context:" in prompt
        assert "essay.md" in prompt


class TestBuildStrategistPrompt:
    def test_without_previous_draft(self):
        prompt = helper_ai.build_strategist_prompt("build an app", "a1;a2", "q1;q2")
        assert "Solaris' Strategist" in prompt
        assert "User's Question: build an app" in prompt
        assert "Questions asked to user for details: q1;q2" in prompt
        assert "Answer's Provided by the user to questions provided: a1;a2" in prompt
        assert "Previous Draft:" not in prompt

    def test_with_previous_draft(self):
        prompt = helper_ai.build_strategist_prompt(
            "build an app", "a1", "q1", previous_draft="old design here",
        )
        assert "Previous Draft:" in prompt
        assert "old design here" in prompt
        assert "critically evaluate it" in prompt

    def test_attachment_context(self):
        prompt = helper_ai.build_strategist_prompt("goal", "a", "q", attachment_context="prefs.txt")
        assert "Attached Files Context:" in prompt
        assert "prefs.txt" in prompt


class TestQuestions:
    def test_planning_stage_prompt(self):
        prompt = helper_ai.questions("build a prd")
        assert "planning-question stage of Solaris' Strategist mode" in prompt
        assert "maximum of 10 questions" in prompt
        assert "### Questions" in prompt
        assert "User's Request: build a prd" in prompt

    def test_attachment_context(self):
        prompt = helper_ai.questions("build a prd", attachment_context="interview.txt")
        assert "Attached Files Context:" in prompt
        assert "interview.txt" in prompt


@pytest.fixture
def captured_fallback(monkeypatch):
    captured = {}

    def fake(prompt, operation_name):
        captured["prompt"] = prompt
        captured["op"] = operation_name
        return "summarised"

    monkeypatch.setattr(helper_ai, "_call_with_fallback", fake)
    return captured


class TestSummariserPromptBuilders:
    def test_summarise_pref(self, captured_fallback):
        result = helper_ai.summarise_pref("always be brief with me")
        assert result == "summarised"
        assert "preference extraction system" in captured_fallback["prompt"]
        assert "always be brief with me" in captured_fallback["prompt"]
        assert captured_fallback["op"] == "Preference summarization"

    def test_summarise_session(self, captured_fallback):
        helper_ai.summarise_session("user said hello")
        assert "long-term memory extraction system" in captured_fallback["prompt"]
        assert "user said hello" in captured_fallback["prompt"]

    def test_current_chat_summariser(self, captured_fallback):
        helper_ai.current_chat_summariser("convo")
        assert "Important Current Session Memory" in captured_fallback["prompt"]
        assert "convo" in captured_fallback["prompt"]

    def test_summarise_about(self, captured_fallback):
        helper_ai.summarise_about("I am a Class 9 student")
        assert "Summariser of Details of the User" in captured_fallback["prompt"]
        assert "I am a Class 9 student" in captured_fallback["prompt"]