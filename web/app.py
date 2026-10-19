"""Solaris web interface.

Started by `python chatbot.py`. All heavy work lives in core.py; this module is
HTTP plumbing: pages, JSON endpoints, the setup wizard and the settings menu.
"""

import io
import os
import platform
import secrets
import shutil
import tempfile
import time
import uuid

from flask import Flask, jsonify, redirect, render_template, request, send_file
from flask import session as flask_session

import config
import config_io
import core
import env_io
import main_db
import model_state
import web.access as access
import web.jobs as jobs

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openrouter": "OpenRouter",
    "openrouter-assist": "OpenRouter (Assistant)",
    "nvidia": "NVIDIA NIM",
    "groq": "Groq",
    "ollama-cloud": "Ollama Cloud",
}

WEB_KEYS = {
    "tavily": {"env": "TAVILY_API_KEY", "label": "Tavily", "url": "https://app.tavily.com/home"},
    "firecrawl": {"env": "FIRECRAWL_API_KEY", "label": "Firecrawl", "url": "https://www.firecrawl.dev/app/api-keys"},
}

CONFIG_TOP_KEYS = {"gemini", "openrouter", "local", "or_assist", "web", "vision_model", "specialist"}

# Session uploads (attachments) land here and stay until the OS clears the temp dir.
UPLOAD_DIR = [tempfile.mkdtemp(prefix="solaris_uploads_")]

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # attachments / audio uploads


def _secret_key():
    path = os.path.join(BASE_DIR, ".flask_secret")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app.secret_key = _secret_key()

# Workspace API (memory, study trails, session workspace, answer controls).
from web.api_workspace import bp as workspace_bp  # noqa: E402

app.register_blueprint(workspace_bp)

# ---------------------------------------------------------------- helpers


def needs_setup():
    """True until a usable config.json and at least one provider key exist."""
    if not os.path.exists(config_io.CONFIG_PATH):
        return True
    try:
        cfg = config_io.load_config()
    except Exception:
        return True
    if any(key not in cfg for key in ("gemini", "openrouter", "local", "specialist")):
        return True
    return not any(os.getenv(p["api_key_env"]) for p in config.PROVIDERS.values())


def status_payload():
    try:
        cfg = config_io.load_config()
    except Exception:
        cfg = {}

    profile = None
    if core.session.user_id is not None and access.allows(core.session.user_id):
        profile = {
            "user_id": core.session.user_id,
            "name": core.session.name,
            "preference": core.session.preference,
            "about_user": core.session.about_user,
            "visibility": (main_db.get_access(core.session.user_id) or {}).get("visibility"),
            "state": (main_db.get_access(core.session.user_id) or {}).get("state"),
        }

    return {
        "profile": profile,
        "providers": [
            {
                "name": name,
                "label": PROVIDER_LABELS.get(name, name),
                "env": provider["api_key_env"],
                "has_key": bool(os.getenv(provider["api_key_env"])),
            }
            for name, provider in config.PROVIDERS.items()
        ],
        "web_keys": {key: bool(os.getenv(value["env"])) for key, value in WEB_KEYS.items()},
        "models": {
            "gemini": cfg.get("gemini"),
            "openrouter": cfg.get("openrouter", []),
            "local": cfg.get("local"),
            "or_assist": cfg.get("or_assist"),
            "vision": cfg.get("vision_model", {}),
            "specialist": cfg.get("specialist", {}),
            "depths": cfg.get("web", {}).get("depths", {}),
        },
        "disabled_models": sorted(model_state.unavailable_models),
        "tts_engine": core.session.tts_engine,
        "version": "1.3.0-web",
    }


def _select_profile(user_id):
    """Select a profile for this session — only when access allows it."""
    if not access.allows(user_id):
        return False
    if core.session.load_profile(user_id):
        flask_session["user_id"] = user_id
        main_db.touch_last_active(user_id)
        return True
    return False


def _auto_select():
    """Open the first profile this session may access; never bypasses a lock."""
    for profile in core.profiles():
        if access.allows(profile["user_id"]) and _select_profile(profile["user_id"]):
            return True
    return False


def _ensure_selection():
    """Keep the in-memory selection in step with the access rules."""
    current = core.session.user_id
    if current is not None:
        if access.allows(current):
            return True
        core.session.user_id = None
    return _auto_select()


def _check_password(password):
    """Verify the API password with a small lockout after repeated failures."""
    if not main_db.api_password_set():
        return False, "No API password has been set yet. Create one in Settings → API Keys."
    now = time.time()
    if now < _lockout["until"]:
        return False, f"Too many attempts. Try again in {int(_lockout['until'] - now) + 1}s."
    if main_db.verify_api_password(password or ""):
        _lockout["count"] = 0
        return True, ""
    _lockout["count"] += 1
    if _lockout["count"] >= 5:
        _lockout["count"] = 0
        _lockout["until"] = now + 60
        return False, "Too many attempts. Locked for 60 seconds."
    return False, "Incorrect password."


_lockout = {"count": 0, "until": 0.0}


def _save_config_partial(partial):
    if not isinstance(partial, dict) or not partial:
        raise ValueError("No configuration received.")
    unknown = set(partial) - CONFIG_TOP_KEYS
    if unknown:
        raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")
    config_io.update_config(partial)
    core.reload_dependent_modules()
    return config_io.load_config()


# ---------------------------------------------------------------- pages


@app.route("/")
def home():
    if needs_setup():
        return redirect("/setup")
    _ensure_selection()
    return render_template("landing.html", status=status_payload())


@app.route("/chat")
def chat_page():
    if needs_setup():
        return redirect("/setup")
    if not _ensure_selection():
        return redirect("/")
    return render_template(
        "chat.html",
        status=status_payload(),
        controls=core.answer_controls(),
    )


@app.route("/memory")
def memory_page():
    if needs_setup():
        return redirect("/setup")
    if not _ensure_selection():
        return redirect("/")
    return render_template("memory.html", status=status_payload())


@app.route("/study")
def study_page():
    if needs_setup():
        return redirect("/setup")
    if not _ensure_selection():
        return redirect("/")
    import study_db

    return render_template(
        "study.html",
        status=status_payload(),
        meta={
            "stages": [{"key": key, "label": study_db.STAGE_LABELS[key]} for key in study_db.STAGES],
            "mastery": list(study_db.MASTERY),
        },
    )


@app.route("/setup")
def setup_page():
    return render_template("setup.html", status=status_payload())


@app.route("/settings")
def settings_page():
    if needs_setup():
        return redirect("/setup")
    return render_template("settings.html", status=status_payload())


@app.route("/api/status")
def api_status():
    return jsonify(status_payload())


# ---------------------------------------------------------------- profiles
#
# Access model (enforced here, never in the browser):
#   active + public   → selectable
#   active + private  → unlock with the profile password for this session
#   inactive (+ any)  → reactivate with that profile's activation code first
# Locked profiles only ever expose their card (id, name, visibility, state).


def _profile_card(user_id):
    for profile in core.profiles():
        if profile["user_id"] == user_id:
            return profile
    return None


def _profiles_payload():
    return {
        "profiles": core.profiles(),
        "current": core.session.user_id if core.session.user_id is not None else None,
        "current_access": (
            main_db.get_access(core.session.user_id) if core.session.user_id is not None else None
        ),
    }


@app.get("/api/profiles")
def api_profiles():
    return jsonify(_profiles_payload())


@app.post("/api/profiles")
def api_create_profile():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    preference = (data.get("preference") or "").strip()
    about_user = (data.get("about") or "").strip()
    if not name or not preference:
        return jsonify({"ok": False, "error": "Name and behaviour preference are required."}), 400
    if len(name) > 120:
        return jsonify({"ok": False, "error": "That name is too long."}), 400

    try:
        created = core.create_profile(name, preference, about_user)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not create profile: {e}"}), 500

    _select_profile(created["user_id"])
    return jsonify({
        "ok": True,
        "user_id": created["user_id"],
        "activation_code": created["activation_code"],
        **_profiles_payload(),
        "status": status_payload(),
    })


@app.post("/api/profiles/select")
def api_select_profile():
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400

    card = _profile_card(user_id)
    if card is None:
        return jsonify({"ok": False, "error": "Profile not found."}), 404

    ok, body, status = access.require(user_id)
    if not ok:
        return jsonify(body), status
    if not _select_profile(user_id):
        return jsonify({"ok": False, "error": "Profile not found."}), 404
    return jsonify({"ok": True, "status": status_payload()})


@app.post("/api/profiles/activate")
def api_activate_profile():
    """Reactivate an inactive profile with its activation code."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400
    code = (data.get("code") or "").strip()

    if main_db.get_access(user_id) is None:
        return jsonify({"ok": False, "error": "Profile not found."}), 404

    locked_for = main_db.lockout_remaining(user_id)
    if locked_for:
        return jsonify({
            "ok": False,
            "error": f"Too many incorrect attempts. Try again in {locked_for}s.",
        }), 429

    if not code:
        return jsonify({"ok": False, "error": "Enter the activation code."}), 400

    if not main_db.verify_activation_code(user_id, code):
        main_db.register_failed_attempt(user_id)
        return jsonify({"ok": False, "error": "That activation code is not correct."}), 403

    main_db.reset_failed_attempts(user_id)
    main_db.set_state(user_id, main_db.STATE_ACTIVE)
    return jsonify({"ok": True, "profiles": core.profiles(), "needs_password": main_db.has_profile_password(user_id)})


@app.post("/api/profiles/unlock")
def api_unlock_profile():
    """Unlock a private profile for this browser session."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400
    password = data.get("password") or ""

    profile_access = main_db.get_access(user_id)
    if profile_access is None:
        return jsonify({"ok": False, "error": "Profile not found."}), 404
    if profile_access["state"] == main_db.STATE_INACTIVE:
        return jsonify({
            "ok": False,
            "error": "This profile is inactive. Reactivate it with its activation code first.",
            "needs": "activation",
        }), 403

    locked_for = main_db.lockout_remaining(user_id)
    if locked_for:
        return jsonify({
            "ok": False,
            "error": f"Too many incorrect attempts. Try again in {locked_for}s.",
        }), 429

    if profile_access["visibility"] == main_db.VISIBILITY_PUBLIC and not profile_access["has_profile_password"]:
        return jsonify({
            "ok": False,
            "error": "This profile is public — it opens without a password.",
        }), 400

    if not profile_access["has_profile_password"]:
        return jsonify({
            "ok": False,
            "error": "This profile is private but has no password set. Set one to make it accessible.",
            "needs": "password_setup",
        }), 409

    if not main_db.verify_profile_password(user_id, password):
        main_db.register_failed_attempt(user_id)
        return jsonify({"ok": False, "error": "That password is not correct."}), 403

    main_db.reset_failed_attempts(user_id)
    access.mark_unlocked(user_id)
    return jsonify({"ok": True, "unlocked": sorted(access.unlocked_ids())})


@app.post("/api/profiles/lock")
def api_lock_profile():
    """Forget the unlock for this browser session."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400
    access.mark_locked(user_id)
    if core.session.user_id == user_id:
        core.session.user_id = None
    return jsonify({"ok": True, "locked": True})


@app.post("/api/profiles/deactivate")
def api_deactivate_profile():
    """Deactivate a profile (it then needs its activation code to reopen)."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400

    ok, body, status = access.require(user_id)
    if not ok:
        return jsonify(body), status
    if (data.get("confirm") or "").strip().upper() != "DEACTIVATE":
        return jsonify({"ok": False, "error": "Type DEACTIVATE to confirm."}), 400

    main_db.set_state(user_id, main_db.STATE_INACTIVE)
    access.mark_locked(user_id)
    if core.session.user_id == user_id:
        core.session.user_id = None
    return jsonify({
        "ok": True,
        "profiles": core.profiles(),
        "note": "Keep the activation code safe — without it this profile cannot be reopened.",
    })


@app.post("/api/profiles/activation-code/regenerate")
def api_regenerate_activation_code():
    """Issue a fresh activation code; the old one stops working immediately."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400

    ok, body, status = access.require(user_id)
    if not ok:
        return jsonify(body), status

    profile_access = main_db.get_access(user_id)
    if profile_access and profile_access["visibility"] == main_db.VISIBILITY_PRIVATE:
        # A private profile already proved itself when it was unlocked; still ask
        # for the password again so a walk-up cannot rotate the code.
        locked_for = main_db.lockout_remaining(user_id)
        if locked_for:
            return jsonify({"ok": False, "error": f"Too many incorrect attempts. Try again in {locked_for}s."}), 429
        if not main_db.verify_profile_password(user_id, data.get("password") or ""):
            main_db.register_failed_attempt(user_id)
            return jsonify({"ok": False, "error": "Enter this profile's password to rotate its code."}), 403
        main_db.reset_failed_attempts(user_id)

    code = main_db.issue_activation_code(user_id)
    return jsonify({
        "ok": True,
        "activation_code": code,
        "warning": "Store this now — it is shown once and replaces the previous code.",
    })


@app.post("/api/profiles/visibility")
def api_set_visibility():
    """Make a profile public/private. Private profiles need a password."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400
    visibility = (data.get("visibility") or "").strip().lower()

    ok, body, status = access.require(user_id)
    if not ok:
        return jsonify(body), status
    if visibility not in (main_db.VISIBILITY_PUBLIC, main_db.VISIBILITY_PRIVATE):
        return jsonify({"ok": False, "error": "Visibility must be 'public' or 'private'."}), 400

    if visibility == main_db.VISIBILITY_PRIVATE:
        password = (data.get("password") or "").strip()
        if password:
            try:
                main_db.set_profile_password(user_id, password)
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 400
        elif not main_db.has_profile_password(user_id):
            return jsonify({"ok": False, "error": "Set a password to make this profile private."}), 400

    try:
        main_db.set_visibility(user_id, visibility)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if visibility == main_db.VISIBILITY_PRIVATE:
        access.mark_unlocked(user_id)
    else:
        access.mark_locked(user_id)
    return jsonify({"ok": True, "profiles": core.profiles()})


@app.post("/api/profiles/password/set")
def api_set_profile_password():
    """Set or rotate the private password for a profile."""
    data = request.get_json(force=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid profile."}), 400

    ok, body, status = access.require(user_id)
    if not ok:
        return jsonify(body), status

    locked_for = main_db.lockout_remaining(user_id)
    if locked_for:
        return jsonify({"ok": False, "error": f"Too many incorrect attempts. Try again in {locked_for}s."}), 429

    if main_db.has_profile_password(user_id):
        # Changing an existing secret requires the current one.
        if not main_db.verify_profile_password(user_id, data.get("current") or ""):
            main_db.register_failed_attempt(user_id)
            return jsonify({"ok": False, "error": "Enter the current profile password first."}), 403
    main_db.reset_failed_attempts(user_id)

    try:
        main_db.set_profile_password(user_id, data.get("password") or "")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


# ---------------------------------------------------------------- chat


@app.post("/api/chat")
def api_chat():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    data = request.get_json(force=True) or {}
    payload = core.send(data.get("message", ""), input_mode=data.get("input", "text"))
    return jsonify(payload)


@app.post("/api/session/end")
def api_session_end():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    return jsonify({"message": core.session.end_session()})


@app.post("/api/voice")
def api_voice():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    upload = request.files.get("audio")
    if upload is None:
        return jsonify({"ok": False, "error": "No audio received."}), 400

    suffix = os.path.splitext(upload.filename or "")[1] or ".webm"
    handle, path = tempfile.mkstemp(prefix="solaris_voice_", suffix=suffix)
    os.close(handle)
    try:
        upload.save(path)
        text = core.transcribe(path)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Transcription failed: {e}"}), 500
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return jsonify({"ok": True, "text": text})


@app.post("/api/tts/engine")
def api_tts_engine():
    data = request.get_json(force=True) or {}
    engine = data.get("engine", "off")
    if engine not in ("off", "edge", "kitten"):
        return jsonify({"ok": False, "error": "Unknown engine."}), 400
    core.session.tts_engine = engine
    return jsonify({"ok": True, "engine": engine})


@app.post("/api/tts")
def api_tts():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    engine = data.get("engine") or core.session.tts_engine
    if not text:
        return jsonify({"ok": False, "error": "Nothing to speak."}), 400
    try:
        audio, mimetype = core.synthesize(text[:4000], engine)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Speech generation failed: {e}"}), 500
    return send_file(io.BytesIO(audio), mimetype=mimetype)


# ---------------------------------------------------------------- attachments


@app.post("/api/attach")
def api_attach():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"type": "error", "message": "No file received."}), 400

    # Uploads live for the whole session: .VISION reads image bytes from the path later.
    safe_name = os.path.basename(upload.filename or "upload")
    path = os.path.join(UPLOAD_DIR[0], f"{uuid.uuid4().hex[:8]}_{safe_name}")
    upload.save(path)
    payload = core.add_attachment(path)
    return jsonify(payload)


@app.get("/api/attachments")
def api_attachments():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    return jsonify({"attachments": core.attachments_payload()})


@app.post("/api/attachments/remove")
def api_remove_attachment():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    data = request.get_json(force=True) or {}
    try:
        index = int(data.get("index"))
    except (TypeError, ValueError):
        return jsonify({"type": "error", "message": "Invalid attachment number."}), 400
    return jsonify(core.remove_attachment(index))


# ---------------------------------------------------------------- specialists


@app.post("/api/better")
def api_better():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    data = request.get_json(force=True) or {}
    return jsonify(core.better(
        (data.get("specialist") or "").strip(),
        data.get("question", ""),
        bool(data.get("use_attachments", True)),
    ))


@app.post("/api/better/answers")
def api_better_answers():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    data = request.get_json(force=True) or {}
    return jsonify(core.better_answers(data.get("answers", "")))


@app.post("/api/better/decision")
def api_better_decision():
    ok, body, status = access.require_selected()
    if not ok:
        return jsonify(body), status
    data = request.get_json(force=True) or {}
    return jsonify(core.better_decision(bool(data.get("approve"))))


# ---------------------------------------------------------------- settings


@app.get("/api/settings")
def api_settings():
    keys = [
        {
            "env": provider["api_key_env"],
            "label": PROVIDER_LABELS.get(name, name),
            "set": bool(os.getenv(provider["api_key_env"])),
            "group": "provider",
        }
        for name, provider in config.PROVIDERS.items()
    ]
    keys += [
        {
            "env": value["env"],
            "label": value["label"],
            "set": bool(os.getenv(value["env"])),
            "group": "web",
            "url": value["url"],
        }
        for value in WEB_KEYS.values()
    ]
    return jsonify({
        "config": config_io.load_config(),
        "settings": config_io.load_settings(),
        "keys": keys,
        "password_set": main_db.api_password_set(),
        "providers": list(config.PROVIDERS.keys()),
    })


@app.post("/api/settings/models")
def api_settings_models():
    data = request.get_json(force=True) or {}
    try:
        cfg = _save_config_partial(data.get("config") or {})
        if data.get("settings"):
            config_io.save_settings(data["settings"])
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "config": cfg, "status": status_payload()})


@app.post("/api/settings/keys")
def api_settings_keys():
    data = request.get_json(force=True) or {}
    ok, problem = _check_password(data.get("password", ""))
    if not ok:
        return jsonify({"ok": False, "error": problem}), 403

    values = data.get("values") or {}
    allowed = {p["api_key_env"] for p in config.PROVIDERS.values()} | {v["env"] for v in WEB_KEYS.values()}
    cleaned = {key: (value or "").strip() for key, value in values.items() if key in allowed}
    if not cleaned:
        return jsonify({"ok": False, "error": "Nothing to update."}), 400

    env_io.set_env(cleaned)
    core.refresh_clients()
    core.reload_dependent_modules()
    removed = [key for key, value in cleaned.items() if not value]
    updated = [key for key, value in cleaned.items() if value]
    return jsonify({
        "ok": True,
        "updated": updated,
        "removed": removed,
        "status": status_payload(),
    })


@app.post("/api/settings/password")
def api_settings_password():
    """Create a new API password (requires the current one once it exists)."""
    data = request.get_json(force=True) or {}
    if main_db.api_password_set():
        ok, problem = _check_password(data.get("current", ""))
        if not ok:
            return jsonify({"ok": False, "error": problem}), 403
    password = main_db.generate_api_password()
    if not main_db.set_api_password(password):
        return jsonify({"ok": False, "error": "Create a profile first — the password is stored on the profile row."}), 400
    return jsonify({"ok": True, "password": password})


# ---------------------------------------------------------------- wizard


def _wizard_status():
    try:
        cfg = config_io.load_config()
    except Exception:
        cfg = {}
    whichllm = core.whichllm_command()
    return {
        "needs_setup": needs_setup(),
        "python": platform.python_version(),
        "missing_imports": core.missing_imports(),
        "whichllm_command": " ".join(whichllm) if whichllm else None,
        "uv": bool(shutil.which("uv")),
        "provider_keys": {name: bool(os.getenv(p["api_key_env"])) for name, p in config.PROVIDERS.items()},
        "provider_labels": PROVIDER_LABELS,
        "web_keys": {key: bool(os.getenv(value["env"])) for key, value in WEB_KEYS.items()},
        "config": cfg,
        "profiles": core.profiles(),
        "password_set": main_db.api_password_set(),
    }


@app.get("/api/wizard/status")
def api_wizard_status():
    return jsonify(_wizard_status())


@app.post("/api/wizard/install-requirements")
def api_wizard_install_requirements():
    return jsonify({"job": jobs.start(core.install_requirements)})


@app.post("/api/wizard/whichllm/install")
def api_wizard_install_whichllm():
    return jsonify({"job": jobs.start(core.install_whichllm)})


@app.post("/api/wizard/whichllm/run")
def api_wizard_run_whichllm():
    data = request.get_json(silent=True) or {}
    return jsonify({"job": jobs.start(core.run_whichllm, int(data.get("top", 10)))})


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Unknown job."}), 404
    return jsonify(job)


@app.post("/api/wizard/local")
def api_wizard_local():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Model name is required."}), 400
    config_io.update_config({"local": name})
    core.reload_dependent_modules()
    return jsonify({"ok": True, "local": name})


@app.post("/api/wizard/web-keys")
def api_wizard_web_keys():
    data = request.get_json(force=True) or {}
    values = {}
    for service, value in WEB_KEYS.items():
        provided = (data.get(service) or "").strip()
        if provided:
            values[value["env"]] = provided
    if values:
        env_io.set_env(values)
        core.refresh_clients()
    return jsonify({"ok": True, "saved": sorted(values.keys())})


@app.post("/api/wizard/provider-keys")
def api_wizard_provider_keys():
    data = request.get_json(force=True) or {}
    provided = data.get("keys") or {}
    values = {}
    for name, value in provided.items():
        provider = config.PROVIDERS.get(name)
        if provider and (value or "").strip():
            values[provider["api_key_env"]] = value.strip()
    if values:
        env_io.set_env(values)
        core.refresh_clients()
        core.reload_dependent_modules()
    return jsonify({"ok": True, "saved": sorted(values.keys())})


@app.post("/api/wizard/config")
def api_wizard_config():
    data = request.get_json(force=True) or {}
    try:
        cfg = _save_config_partial(data.get("config") or {})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "config": cfg})


@app.post("/api/wizard/profile")
def api_wizard_profile():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    preference = (data.get("preference") or "").strip()
    about_user = (data.get("about") or "").strip()
    if not name or not preference:
        return jsonify({"ok": False, "error": "Name and behaviour preference are required."}), 400
    try:
        created = core.create_profile(name, preference, about_user)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not create profile: {e}"}), 500
    _select_profile(created["user_id"])
    return jsonify({
        "ok": True,
        "user_id": created["user_id"],
        "activation_code": created["activation_code"],
        "profiles": core.profiles(),
    })


@app.post("/api/wizard/finish")
def api_wizard_finish():
    """Issue the 6 character API password (created once, at the end of setup)."""
    if main_db.api_password_set():
        return jsonify({"ok": True, "password": None, "already_set": True})
    password = main_db.generate_api_password()
    if not main_db.set_api_password(password):
        return jsonify({
            "ok": False,
            "error": "Create a profile first — the password is stored on the profile row.",
        }), 400
    return jsonify({"ok": True, "password": password})


def run(host="127.0.0.1", port=7860):
    """Start the development server (single user, local only)."""
    app.run(host=host, port=port, threaded=True, use_reloader=False)
