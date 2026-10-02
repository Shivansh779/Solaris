"""Tests for session-level model availability state.

FakeTime lets the 30 second 503 cooldown be tested without real sleeping.
"""

import importlib

import httpx
import openai
import pytest
from google.genai import errors as genai_errors

import model_state


class FakeTime:
    """Minimal stand-in for the time module with a movable clock."""

    def __init__(self, now=1000.0):
        self.now = now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Give every test empty state and a controllable clock."""
    clock = FakeTime()
    monkeypatch.setattr(model_state, "time", clock)
    model_state.unavailable_models.clear()
    model_state.temporary_unavailable.clear()
    return clock


def openai_error(cls, status):
    request = httpx.Request("POST", "https://example.test")
    return cls("failed", response=httpx.Response(status, request=request), body=None)


# --- default eligibility ---------------------------------------------------

def test_unmarked_model_is_eligible():
    assert model_state.can_attempt("some/model") is True


# --- 429 / 404 / model-not-found: permanent for the session ----------------

def test_429_disables_model_for_session():
    assert model_state.classify_error(openai_error(openai.RateLimitError, 429)) == model_state.RATE_LIMIT

    model_state.mark_unavailable("model-a")
    model_state.mark_temporarily_unavailable("model-b")

    assert model_state.can_attempt("model-a") is False


def test_404_disables_model_for_session():
    assert model_state.classify_error(openai_error(openai.NotFoundError, 404)) == model_state.MODEL_UNAVAILABLE

    model_state.mark_unavailable("model-a")

    assert model_state.can_attempt("model-a") is False


def test_model_not_found_text_disables_model_for_session():
    error = Exception("No endpoints found that can handle model-a")

    assert model_state.classify_error(error) == model_state.MODEL_UNAVAILABLE

    model_state.mark_unavailable("model-a")

    assert model_state.can_attempt("model-a") is False


def test_disabled_model_stays_disabled_past_a_cooldown(clean_state):
    model_state.mark_unavailable("model-a")
    clean_state.advance(model_state.COOLDOWN_SECONDS * 10)

    assert model_state.can_attempt("model-a") is False


# --- 503: 30 second cooldown ----------------------------------------------

def test_503_starts_cooldown_without_disabling_model():
    assert model_state.classify_error(openai_error(openai.APIStatusError, 503)) == model_state.SERVICE_UNAVAILABLE

    model_state.mark_temporarily_unavailable("model-a")

    assert model_state.can_attempt("model-a") is False
    assert "model-a" not in model_state.unavailable_models


def test_cooldown_blocks_until_thirty_seconds_elapse(clean_state):
    model_state.mark_temporarily_unavailable("model-a")

    clean_state.advance(model_state.COOLDOWN_SECONDS - 0.1)

    assert model_state.can_attempt("model-a") is False
    assert "model-a" in model_state.temporary_unavailable


def test_cooldown_expires_and_clears_its_entry(clean_state):
    model_state.mark_temporarily_unavailable("model-a")

    clean_state.advance(model_state.COOLDOWN_SECONDS)

    assert model_state.can_attempt("model-a") is True
    assert "model-a" not in model_state.temporary_unavailable


def test_each_model_cooldown_is_independent(clean_state):
    model_state.mark_temporarily_unavailable("model-a")
    clean_state.advance(20)
    model_state.mark_temporarily_unavailable("model-b")

    clean_state.advance(15)  # model-a at 35s, model-b at 15s

    assert model_state.can_attempt("model-a") is True
    assert model_state.can_attempt("model-b") is False
    assert "model-a" not in model_state.temporary_unavailable
    assert "model-b" in model_state.temporary_unavailable


# --- unrecognised errors keep existing behaviour ---------------------------

def test_unrelated_errors_are_unclassified():
    assert model_state.classify_error(Exception("connection reset by peer")) is None
    assert model_state.classify_error(openai_error(openai.APIStatusError, 500)) is None


def test_unrelated_error_leaves_model_eligible():
    model_state.classify_error(Exception("connection reset by peer"))

    assert model_state.can_attempt("model-a") is True
    assert model_state.unavailable_models == set()
    assert model_state.temporary_unavailable == {}


# --- provider specific shapes ---------------------------------------------

def test_gemini_errors_are_classified():
    quota = genai_errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED: quota"}})
    down = genai_errors.ServerError(503, {"error": {"message": "Service Unavailable"}})

    assert model_state.classify_error(quota) == model_state.RATE_LIMIT
    assert model_state.classify_error(down) == model_state.SERVICE_UNAVAILABLE


def test_503_status_wins_over_conflicting_message_text():
    error = Exception("Error code: 503 - model not found")

    assert model_state.classify_error(error) == model_state.SERVICE_UNAVAILABLE


def test_status_code_is_read_from_either_attribute():
    class CodeOnly(Exception):
        code = 503

    assert model_state.classify_error(CodeOnly("down")) == model_state.SERVICE_UNAVAILABLE


# --- ordering and session lifetime ----------------------------------------

def test_disabled_models_are_dropped_without_reordering():
    chain = ["model-a", "model-b", "model-c"]
    model_state.mark_unavailable("model-b")

    assert [m for m in chain if model_state.can_attempt(m)] == ["model-a", "model-c"]


def test_state_resets_on_restart():
    model_state.mark_unavailable("model-a")
    model_state.mark_temporarily_unavailable("model-b")

    reloaded = importlib.reload(model_state)

    assert reloaded.unavailable_models == set()
    assert reloaded.temporary_unavailable == {}