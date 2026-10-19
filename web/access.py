"""Profile authorization for the web interface.

One rule, enforced server-side everywhere: a profile may only be read or
written when it is active and — if it is private — unlocked in this browser
session. Client-side state is never trusted.

Three separate credentials exist in Solaris and none of them substitute for
another:
    * the app-wide API password  (provider keys / API configuration)
    * a profile activation code  (reactivating an inactive profile)
    * a profile password         (private profiles)
"""

from flask import jsonify
from flask import session as flask_session

import main_db

UNLOCK_KEY = "unlocked_profiles"


# ---------------------------------------------------------------- session unlock


def unlocked_ids():
    values = flask_session.get(UNLOCK_KEY) or []
    return {int(value) for value in values if str(value).isdigit()}


def mark_unlocked(user_id):
    """Remember the private-profile unlock for this browser session only."""
    ids = unlocked_ids()
    ids.add(int(user_id))
    flask_session[UNLOCK_KEY] = sorted(ids)
    flask_session.modified = True


def mark_locked(user_id):
    ids = unlocked_ids()
    ids.discard(int(user_id))
    flask_session[UNLOCK_KEY] = sorted(ids)
    flask_session.modified = True


def clear_unlocks():
    flask_session[UNLOCK_KEY] = []
    flask_session.modified = True


# ---------------------------------------------------------------- access checks


def denial_reason(user_id):
    """Why this profile cannot be opened right now, or None when it can."""
    access = main_db.get_access(user_id)
    if access is None:
        return "unknown"
    if access["state"] == main_db.STATE_INACTIVE:
        return "inactive"
    if access["visibility"] == main_db.VISIBILITY_PRIVATE and int(user_id) not in unlocked_ids():
        return "locked"
    return None


def allows(user_id):
    return denial_reason(user_id) is None


def require(user_id):
    """(ok, payload, status) for a route that needs profile access."""
    reason = denial_reason(user_id)
    if reason is None:
        return True, None, 200
    if reason == "unknown":
        return False, {"ok": False, "error": "Profile not found."}, 404
    if reason == "inactive":
        return False, {
            "ok": False,
            "error": "This profile is inactive. Reactivate it with its activation code to open it.",
            "needs": "activation",
        }, 403
    return False, {
        "ok": False,
        "error": "This profile is private. Enter its password to unlock it.",
        "needs": "password",
    }, 403


def require_selected():
    """(ok, payload, status) for routes that act on the selected profile."""
    import core

    if core.session.user_id is None:
        return False, {"ok": False, "error": "No profile selected."}, 400
    return require(core.session.user_id)


def protected_json(user_id, payload):
    """Guard helper: returns (jsonify(payload), None) when allowed, else (None, response)."""
    ok, body, status = require(user_id)
    if not ok:
        return None, (jsonify(body), status)
    return jsonify(payload), None
