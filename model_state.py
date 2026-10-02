"""Session-level availability state for the models Solaris can call.

Models that return 429 (rate limit) or 404 / model-not-found are removed from
the automatic fallback chain for the rest of the session. Models that return
503 are skipped for COOLDOWN_SECONDS and become eligible again afterwards.

State is in-memory only: it resets when Solaris exits and is never persisted.
"""

import re
import time

COOLDOWN_SECONDS = 30

# Failure kinds returned by classify_error.
RATE_LIMIT = "rate_limit"
MODEL_UNAVAILABLE = "model_unavailable"
SERVICE_UNAVAILABLE = "service_unavailable"

# 429 / model-not-found: never retried automatically in this session.
unavailable_models = set()

# 503: model -> time.time() of the most recent 503. Presence means cooling down.
temporary_unavailable = {}

# Some providers report a bad model name as a generic 400 with the reason in the
# message body, so text is checked for anything the status code does not explain.
RATE_LIMIT_HINTS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "resource_exhausted",
    "resource exhausted",
)

NOT_FOUND_HINTS = (
    "not found",
    "does not exist",
    "no endpoints found",
    "model_not_found",
    "unknown model",
    "invalid model",
)


def _status_code(error):
    """Best-effort HTTP status for a provider exception, or None if there is none."""
    for attr in ("status_code", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    match = re.search(r"\b(429|503|404)\b", str(error))
    return int(match.group(1)) if match else None


def classify_error(error):
    """Return the failure kind of a provider exception, or None if unrecognised.

    An explicit 429/404/503 always wins over the message body, so a 503 that
    happens to mention a missing model is still treated as temporary.
    """
    code = _status_code(error)
    if code == 429:
        return RATE_LIMIT
    if code == 404:
        return MODEL_UNAVAILABLE
    if code == 503:
        return SERVICE_UNAVAILABLE

    text = str(error).lower()
    if any(hint in text for hint in RATE_LIMIT_HINTS):
        return RATE_LIMIT
    if any(hint in text for hint in NOT_FOUND_HINTS):
        return MODEL_UNAVAILABLE
    return None


def can_attempt(model):
    """False if the model is disabled for the session or inside its 503 cooldown.

    A cooldown that has expired is cleared here, making the model eligible again.
    """
    if model in unavailable_models:
        return False
    if model in temporary_unavailable:
        if time.time() - temporary_unavailable[model] < COOLDOWN_SECONDS:
            return False
        del temporary_unavailable[model]
    return True


def mark_unavailable(model):
    """Disable the model for the rest of the session (429 / model-not-found)."""
    unavailable_models.add(model)
    temporary_unavailable.pop(model, None)


def mark_temporarily_unavailable(model):
    """Start a 30 second cooldown for the model (503)."""
    temporary_unavailable[model] = time.time()
