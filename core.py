"""Shared Solaris conversation core.

Holds the session state and the full message pipeline (chat, commands,
specialists, study, web, vision, attachments, voice) so every front end —
currently the web interface — drives the same logic instead of reimplementing it.
"""

import asyncio
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from markdown_it import MarkdownIt

from _log import system_log, current_time
import attachment
import config
import config_io
import embeddings
import env_io
import helper_ai
import history_db
import main_db
import memory_db
import model_state
import skills
import specialist_ai
import study_ai
import study_db
import vec_db
import vision_ai
import web_search
import workspace_db

# Raw HTML from model output is escaped (<script> in a reply stays text).
_md = MarkdownIt("gfm-like", {"linkify": False}).disable("html_block").disable("html_inline")

# Same startup contract as the terminal: tables exist and the schema is migrated
# before any request touches the database.
main_db.create_table()
history_db.create_table()
memory_db.create_table()
vec_db.create_table()
study_db.create_table()
workspace_db.create_table()
embeddings.warm()
system_log("SYSTEM", "INFO", "Application database tables initialized.")


def render_markdown(text):
    return _md.render(text or "")


# --------------------------------------------------------------------------
# Provider clients
# --------------------------------------------------------------------------

_client_cache = {}
_client_lock = threading.Lock()

# provider names accepted in config.json for a given PROVIDERS entry
_CLIENT_ALIASES = {"google": "gemini"}


def refresh_clients():
    """(Re)build every client whose API key is available. Keys change at runtime."""
    with _client_lock:
        _client_cache.clear()
        for name, provider in config.PROVIDERS.items():
            if not os.getenv(provider["api_key_env"]):
                continue
            try:
                _client_cache[name] = config.init_client(name)
            except Exception as e:
                system_log("AI", "WARNING", f"Could not initialise {name}: {e}")
    system_log("SYSTEM", "INFO", "Ready providers: " + (", ".join(sorted(_client_cache)) or "none"))
    return dict(_client_cache)


def clients():
    with _client_lock:
        ready = dict(_client_cache)
    return ready if ready else refresh_clients()


def client_for(provider):
    """Client for a config provider name, or None when its key is missing."""
    name = _CLIENT_ALIASES.get(provider, provider)
    return clients().get(name)


def reload_dependent_modules():
    """Pick up config.json changes in modules that cache it at import time."""
    import importlib
    importlib.reload(web_search)
    importlib.reload(helper_ai)
    # specialist_ai / study_ai hold references to helper_ai and read config.json per call
    importlib.reload(specialist_ai)
    importlib.reload(study_ai)


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

class Session:
    """State of the single local chat session."""

    def __init__(self):
        self.user_id = None
        self.name = None
        self.preference = None
        self.about_user = None
        self.tts_engine = "off"           # off | edge | kitten
        self.last_input = "text"          # how the last message was entered
        self.conv_history = []
        self.session_history = []
        self.imp_conv_history = []
        self.memories = []
        self.used_memories = []
        self.last_route = None
        self.session_start_time = current_time()
        self.better_state = None
        self.lock = threading.Lock()

    # -- profile handling ---------------------------------------------------

    def load_profile(self, user_id):
        data = main_db.get_data(user_id)
        if not data:
            return False
        self.preference, self.name, self.about_user = data[0], data[1], data[2]
        self.memories = history_db.access_history(user_id)
        self.user_id = user_id
        self.session_start_time = current_time()
        self.conv_history.clear()
        self.session_history.clear()
        self.imp_conv_history.clear()
        self.better_state = None
        system_log("PROFILE", "INFO", f"Active profile set to user_id={user_id}.")
        return True

    def end_session(self):
        """Summarise and store the session, exactly like the terminal goodbye path."""
        processed = helper_ai.summarise_session(self.session_history)
        if self.user_id is not None:
            history_db.store_history(self.session_start_time, self.user_id, processed)
        attachment.clear_attachment_context()
        skills.clear_active()
        self.session_history.clear()
        self.conv_history.clear()
        self.imp_conv_history.clear()
        self.better_state = None
        system_log("SYSTEM", "INFO", f"Session closed for user_id={self.user_id}.")
        return "Goodbye! Have a great day ahead!"


session = Session()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _scrub(text):
    """Strip anything that looks like a credential from a message we may show."""
    cleaned = str(text)
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned


_SECRET_PATTERNS = (
    re.compile(r"\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|_KEY)\b\s*[=:]\s*\S+"),
    re.compile(r"\b(?:sk|pk|rk|gsk|xai|hf)-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
)


def _short(error, limit=120):
    text = _scrub(error).replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


# --------------------------------------------------------------------------
# Routing trace + privacy pulse
# --------------------------------------------------------------------------

# Providers that run on this machine. Everything else in config.PROVIDERS is a
# remote API, so it counts as cloud.
LOCAL_PROVIDERS = {"ollama"}

CLOUD = "cloud"
LOCAL = "local"
HYBRID = "hybrid"
UNKNOWN = "unknown"


def new_route():
    """Fresh routing record for one answer."""
    return {"steps": [], "provider": None, "model": None, "fallbacks": []}


def _route_step(route, provider, model, ok=True, reason=""):
    if route is None:
        return
    route["steps"].append({"provider": provider, "model": model, "ok": ok, "reason": reason[:160]})
    if ok:
        route["provider"] = provider
        route["model"] = model


def _classify(route):
    """Local / cloud / hybrid from the providers that actually saw the request.

    A failed cloud attempt still means the request left the machine, so that is
    'hybrid' — never 'local'.
    """
    steps = (route or {}).get("steps") or []
    if not steps:
        return UNKNOWN
    touched_local = any(step["provider"] in LOCAL_PROVIDERS for step in steps)
    touched_cloud = any(step["provider"] not in LOCAL_PROVIDERS for step in steps)
    if touched_local and touched_cloud:
        return HYBRID
    if touched_local:
        return LOCAL
    return CLOUD


def build_pulse(route, **extra):
    """Small factual provenance record attached to every answer."""
    route = route or {}
    classification = _classify(route)
    pulse = {
        "classification": classification,
        "provider": route.get("provider"),
        "model": route.get("model"),
        "steps": route.get("steps", []),
        "fallbacks": route.get("fallbacks", []),
        "web_search": bool(extra.get("web_search")),
        "attachments": bool(extra.get("attachments")),
        "files_selected": int(extra.get("files_selected") or 0),
        "files_total": int(extra.get("files_total") or 0),
        "skills": list(extra.get("skills") or []),
        "memories": int(extra.get("memories") or 0),
        "memory_items": extra.get("memory_items") or [],
        "study_trail": extra.get("study_trail"),
        "latency_ms": extra.get("latency_ms"),
        "reason": extra.get("reason"),
    }
    return pulse


def _context_counts(include_files=True):
    """Exactly what the shelf is contributing to the next prompt."""
    items = list(attachment.get_all_attachments().values())
    selected = [item for item in items if item.get("selected", True)] if include_files else []
    return {
        "attachments": bool(selected),
        "files_selected": len(selected),
        "files_total": len(items),
        "skills": [skill["name"] for skill in skills.discover() if skill["active"]],
    }


# --------------------------------------------------------------------------
# Context manifest ("why this answer")
# --------------------------------------------------------------------------
#
# One row per source that went into the prompt: a memory node, an active skill,
# a selected file or the profile preferences. The row id ("memory:12",
# "skill:project:x.md", "file:0", "profile") is what a re-ask excludes.

def _file_sources(exclude_ids=None):
    """Selected attachments with the text length each one contributes."""
    excluded = set(exclude_ids or ())
    sources = []
    for index, (_path, item) in enumerate(attachment.get_all_attachments().items()):
        if not item.get("selected", True):
            continue
        if f"file:{index}" in excluded or str(index) in excluded:
            continue
        sources.append({
            "index": index,
            "name": item["file_name"],
            "type": item["file_type"],
            "size": len(item.get("content") or ""),
        })
    return sources


def _profile_source(exclude_ids=None):
    """The profile preferences/about that are always injected into the prompt."""
    if "profile" in set(exclude_ids or ()):
        return None
    preference = session.preference or ""
    about = session.about_user or ""
    if not (preference or about):
        return None
    return {
        "label": "Profile",
        "size": len(preference) + len(about),
        "detail": "preferences and about you",
    }


def _context_manifest(memory_items=None, skill_sources=None, file_sources=None, profile=None,
                      history=0, session_facts=0):
    """The manifest of one answer: one row per source that reached the model."""
    entries = []
    for node in memory_items or []:
        entries.append({
            "id": f"memory:{node['id']}",
            "kind": "memory",
            "label": node["title"],
            "size": int(node.get("size") or 0),
            "detail": memory_db.CATEGORY_LABELS.get(node["category"], node["category"]),
        })
    for skill in skill_sources or []:
        entries.append({
            "id": f"skill:{skill['id']}",
            "kind": "skill",
            "label": skill["name"],
            "size": int(skill.get("size") or 0),
            "detail": skill.get("scope", ""),
        })
    for item in file_sources or []:
        entries.append({
            "id": f"file:{item['index']}",
            "kind": "file",
            "label": item["name"],
            "size": int(item.get("size") or 0),
            "detail": item.get("type", ""),
        })
    if profile:
        entries.append({
            "id": "profile",
            "kind": "profile",
            "label": profile["label"],
            "size": int(profile.get("size") or 0),
            "detail": profile.get("detail", ""),
        })
    if history:
        entries.append({
            "id": "history",
            "kind": "history",
            "label": "Past sessions",
            "size": int(history),
            "detail": "summaries of earlier chats",
        })
    if session_facts:
        entries.append({
            "id": "session",
            "kind": "session",
            "label": "This session so far",
            "size": int(session_facts),
            "detail": "summarised earlier turns",
        })
    return entries


def _reply(text, title="Solaris", notes=None, sources=None, pulse=None, context=None):
    return {
        "type": "reply",
        "title": title,
        "raw": text,
        "html": render_markdown(text),
        "notes": notes or [],
        "sources": sources or [],
        "speak": session.tts_engine != "off",
        "pulse": pulse,
        "context": context or [],
    }


def _error(message):
    return {"type": "error", "message": message}


def _local_model_name():
    """Ollama model name derived from the config.json 'local' entry."""
    raw = str(config_io.load_config().get("local", "")).strip()
    return raw.split("/")[-1].lower() if "/" in raw else raw.lower()


def _gemini_model():
    return str(config_io.load_config().get("gemini", "")).lower()


def _openrouter_models():
    models = config_io.load_config().get("openrouter", [])
    return [str(m).lower() for m in models]


# --------------------------------------------------------------------------
# Chat pipeline (ported from the terminal loop)
# --------------------------------------------------------------------------

def ask_gemini(prompt, model, notes, route=None):
    if not model:
        raise RuntimeError("No Gemini model configured.")
    if not model_state.can_attempt(model):
        raise RuntimeError(f"Gemini model unavailable for this session: {model}")
    client = client_for("gemini")
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    try:
        system_log("AI", "INFO", f"Using Gemini model: {model}.")
        notes.append(f"Primary model: Gemini ({model}).")
        response = client.models.generate_content(model=model, contents=prompt)
        _route_step(route, "gemini", model)
        return response.text
    except Exception as e:
        _route_step(route, "gemini", model, ok=False, reason=_short(e))
        _note_model_state(model, e)
        raise


def ask_openrouter(prompt, notes, route=None):
    client = client_for("openrouter")
    if client is None:
        notes.append("OR_API_KEY is not set — skipping OpenRouter.")
        if route is not None:
            route["fallbacks"].append("OpenRouter skipped: no OR_API_KEY.")
        return ask_ollama(prompt, notes, route)

    for model in _openrouter_models():
        if not model_state.can_attempt(model):
            system_log("AI", "INFO", f"Skipping unavailable OpenRouter model: {model}.")
            continue
        try:
            system_log("AI", "INFO", f"Using OpenRouter model: {model}.")
            notes.append(f"Fallback to OpenRouter ({model}).")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            _route_step(route, "openrouter", model)
            return response.choices[0].message.content
        except Exception as e:
            _route_step(route, "openrouter", model, ok=False, reason=_short(e))
            _note_model_state(model, e)
            notes.append(f"OpenRouter model failed: {model} ({_short(e)}).")

    notes.append("All cloud models unavailable — switching to the local model.")
    if route is not None:
        route["fallbacks"].append("All cloud models unavailable; continued with the local model.")
    return ask_ollama(prompt, notes, route)


def ask_ollama(prompt, notes, route=None):
    import ollama

    model = _local_model_name()
    if not model:
        raise RuntimeError("No local model configured.")
    system_log("AI", "INFO", f"Using Ollama model: {model}")
    notes.append(f"Local model: {model}.")
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        _route_step(route, "ollama", model, ok=False, reason=_short(e))
        raise
    _route_step(route, "ollama", model)
    return response["message"]["content"]


def ask_ai(prompt, notes, route=None):
    """Gemini → OpenRouter → Ollama, mirroring the terminal fallback chain."""
    try:
        return ask_gemini(prompt, _gemini_model(), notes, route)
    except Exception as e:
        system_log("AI", "WARNING", f"Gemini unavailable, falling back to OpenRouter: {e}")
        notes.append(f"Gemini unavailable ({_short(e)}) — falling back to OpenRouter.")
        if route is not None:
            route["fallbacks"].append(f"Gemini unavailable ({_short(e)}).")
        return ask_openrouter(prompt, notes, route)


def _note_model_state(model, error):
    state = model_state.classify_error(error)
    if state in (model_state.RATE_LIMIT, model_state.MODEL_UNAVAILABLE):
        model_state.mark_unavailable(model)
        system_log("AI", "WARNING", f"Model disabled for this session: {model}. Error: {error}")
    elif state == model_state.SERVICE_UNAVAILABLE:
        model_state.mark_temporarily_unavailable(model)
        system_log("AI", "WARNING", f"Model cooling down: {model}. Error: {error}")


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

HELP_TEXT = """# Solaris Commands

**General**
- `.CHANGE` — switch profile (or use the profile menu in the header)
- `.BETTER` — ask a specialist (Writer / Programmer / Strategist)
- `.VOICE` — text-to-speech settings (header toggle)
- `.ABOUT` — profile and program information
- `.CLEAR` — clear this chat view (context is preserved)
- `.ATTACH` — use the attach (paperclip) button
- `.DETACH` — list, include or remove attachments
- `.VISION:question` — analyse attached images
- `.WEB:quick|:standard|:deep question` — live web search
- `goodbye` / `bye` / `exit` — end the session (summary is saved)

**Study**
- `.DETAIL topic` — explain like a teacher
- `.SIMPLE topic` — explain in simple language
- `.QUIZ topic` — 10-question quiz with answers
- `.TIMELINE topic` — chronological events
- `.COMPARE topic` — side-by-side comparison
- `.STEPS topic` — step-by-step guide

Tip: the mic button dictates, the paperclip attaches files, and voice replies can be switched on in the header.
"""


def parse_web_depth(question):
    q = question.strip()
    if q.startswith(":"):
        rest = q[1:].strip()
        if rest:
            first = rest.split()[0].lower()
            remaining = " ".join(rest.split()[1:]).strip()
            if first in ("quick", "deep"):
                return first, remaining
    return "standard", q


def profiles():
    """Safe profile cards for the UI: id, name, visibility, state. No content."""
    return main_db.safe_profiles()


def create_profile(name, preference, about_user):
    """Summarise and store a new profile (same pipeline as the terminal).

    Returns the new profile id plus its one-time activation code, which is
    shown to the user exactly once — only its hash is stored.
    """
    processed_pref = helper_ai.summarise_pref(preference)
    processed_about = helper_ai.summarise_about(about_user)
    user_id = main_db.new_user(name, processed_pref, processed_about)
    system_log("PROFILE", "INFO", f"Created new profile with user_id={user_id}.")
    code = main_db.issue_activation_code(user_id)
    return {"user_id": user_id, "activation_code": code}


def about_text():
    input_mode = "v" if session.last_input == "voice" else "t"
    if session.tts_engine == "off":
        output_mode, pref = "t", None
    else:
        output_mode = "v"
        pref = 1 if session.tts_engine == "edge" else 2
    return helper_ai.about(session.user_id, input_mode, output_mode, pref)


def _route_from_providers(providers, model=None):
    """Routing record for flows (study / specialists / vision) that pick their own model.

    The exact model that answered is not reported back by those modules, so the
    record carries the candidate providers and leaves the model unset.
    """
    route = new_route()
    for provider in [p for p in providers if p]:
        _route_step(route, provider, model)
    route["provider"] = None
    route["model"] = model
    return route


def _classify_providers(providers):
    """Same local/cloud/hybrid reading as _classify, for provider name lists."""
    names = [p for p in providers if p]
    if not names:
        return UNKNOWN
    touched_local = any(name in LOCAL_PROVIDERS for name in names)
    touched_cloud = any(name not in LOCAL_PROVIDERS for name in names)
    if touched_local and touched_cloud:
        return HYBRID
    return LOCAL if touched_local else CLOUD


def handle_web(question):
    question = (question or "").strip()
    if not question:
        return _error("Usage: .WEB <question> or .WEB:quick <question>")

    depth, query = parse_web_depth(question)
    if not query:
        return _error("Usage: .WEB <question> or .WEB:quick <question>")
    system_log("COMMAND", "INFO", f"Web search requested: {query[:50]}... (depth={depth}).")

    if not env_io.is_set("TAVILY_API_KEY") and not env_io.is_set("FIRECRAWL_API_KEY"):
        return {"type": "need_keys", "services": ["tavily", "firecrawl"], "retry": f".WEB {question}"}

    depths = config_io.load_config().get("web", {}).get("depths")
    try:
        sources = web_search.search_web(query, depth, depths)
    except Exception as e:
        system_log("WEB", "ERROR", f"Web search failed: {e}")
        sources = None
    if not sources:
        return _error("Web search unavailable. Check your Tavily / Firecrawl keys in Settings → API Keys.")

    provider = sources[0].get("source", "unknown")
    history_db.store_web_log(session.user_id, query, provider, depth, ", ".join(s["url"] for s in sources))

    notes = []
    route = new_route()
    started = time.time()
    try:
        response = ask_ai(helper_ai.build_web_prompt(query, sources), notes, route)
    except Exception as e:
        system_log("SYSTEM", "ERROR", f"Web search response failed: {e}")
        return _error("An error occurred while processing the web search results.")

    session.conv_history += [
        {"role": "user", "content": f".WEB {query}"},
        {"role": "assistant", "content": response},
    ]
    session.session_history += [
        {"role": "user", "content": f".WEB {query}"},
        {"role": "assistant", "content": response},
    ]
    return _reply(
        response,
        title="Web Search",
        notes=notes,
        sources=[{"title": s["title"], "url": s["url"], "source": s.get("source", "")} for s in sources],
        pulse=build_pulse(
            route,
            web_search=True,
            attachments=bool(attachment.get_combined_attachment_context()),
            latency_ms=int((time.time() - started) * 1000),
        ),
    )


def handle_vision(question):
    cfg = config_io.load_config()
    vision_cfg = cfg.get("vision_model", {})
    primary = vision_cfg.get("primary", {})
    if not primary.get("model") or not primary.get("provider"):
        return _error("No vision model configured. Set one in Settings → Models.")

    images = attachment.get_attachments_for_vision()
    if not images:
        return _error("No images selected. Attach an image and include it in the Files shelf first.")
    if not question.strip():
        return _error("Provide a question, for example: .VISION what is in this picture?")

    secondary = vision_cfg.get("secondary", {})
    p_client = client_for(primary.get("provider"))
    s_client = client_for(secondary.get("provider")) if secondary.get("provider") else None
    if p_client is None and s_client is None:
        return _error("Vision model providers are unavailable. Check your API keys.")

    try:
        response = vision_ai.vision(question, p_client, s_client, images)
    except Exception as e:
        system_log("COMMAND", "ERROR", f".VISION failed: {e}")
        return _error("Vision analysis failed. Check the system logs for details.")

    count = len(images)
    route = _route_from_providers([
        primary.get("provider"),
        secondary.get("provider") if vision_cfg.get("secondary") else None,
    ])
    return _reply(
        response,
        title=f"Vision Analysis ({count} image{'s' if count != 1 else ''})",
        pulse=build_pulse(route, attachments=True, files_selected=count, files_total=count),
    )


STUDY_MODES = {
    ".DETAIL": ("detail", "Detailed Explanation"),
    ".SIMPLE": ("simple", "Simple Explanation"),
    ".QUIZ": ("quiz", "Quiz"),
    ".TIMELINE": ("timeline", "Timeline"),
    ".COMPARE": ("compare", "Comparison"),
    ".STEPS": ("steps", "Steps"),
}


def count_quiz_for_topic(user_id, topic):
    """Count a finished quiz for the trail with the same topic. None when there is none."""
    topic = (topic or "").strip().lower()
    if not topic or user_id is None:
        return None
    try:
        for trail in study_db.list_trails(user_id):
            if trail["title"].strip().lower() == topic:
                study_db.register_quiz(user_id, trail["id"])
                system_log("STUDY", "INFO", f"Quiz counted for trail {trail['id']}.")
                return trail
    except Exception as e:  # counting must never break the reply
        system_log("STUDY", "WARNING", f"Could not record the quiz: {e}")
    return None


def handle_study(topic, mode, title):
    cfg = config_io.load_config()
    study_cfg = cfg.get("specialist", {}).get("study", {})
    p_provider = study_cfg.get("primary", {}).get("provider")
    s_provider = study_cfg.get("secondary", {}).get("provider")
    p_client = client_for(p_provider) if p_provider else None
    s_client = client_for(s_provider) if s_provider else None
    if p_client is None and s_client is None:
        return _error("Study models are unavailable. Check your config and API keys.")
    try:
        response = study_ai.study(topic, p_client, s_client, mode)
    except Exception as e:
        system_log("COMMAND", "ERROR", f"Study command '{mode}' failed: {e}")
        return _error("Both models failed to generate a response.")

    # A completed quiz counts against a trail with the same topic, when one exists.
    if mode == "quiz" and session.user_id is not None:
        count_quiz_for_topic(session.user_id, topic)

    route = _route_from_providers([p_provider, s_provider])
    return _reply(
        response,
        title=f"{title}: {topic}",
        pulse=build_pulse(
            route,
            study_trail=topic,
            attachments=bool(attachment.get_combined_attachment_context()),
        ),
    )


SPECIALISTS = {
    "writer": ("writing", "✍️ The Writer"),
    "coder": ("coding", "💻 The Programmer"),
    "strategist": ("reasoning", "🧠 The Strategist"),
}


def _specialist_clients(role_key):
    cfg = config_io.load_config()
    spec = cfg.get("specialist", {}).get(role_key, {})
    primary = spec.get("primary", {})
    secondary = spec.get("secondary", {})
    p_client = client_for(primary.get("provider")) if primary.get("provider") else None
    s_client = client_for(secondary.get("provider")) if secondary.get("provider") else None
    return p_client, s_client


def _specialist_provider_names(role_key):
    cfg = config_io.load_config()
    spec = cfg.get("specialist", {}).get(role_key, {})
    return [
        (spec.get("primary", {}) or {}).get("provider"),
        (spec.get("secondary", {}) or {}).get("provider"),
    ]


def better(specialist, question, use_attachments=True):
    if specialist not in SPECIALISTS:
        return _error("Unknown specialist.")
    question = (question or "").strip()
    if not question:
        return _error("Describe what you want the specialist to work on.")

    role_key, title = SPECIALISTS[specialist]
    p_client, s_client = _specialist_clients(role_key)
    if p_client is None and s_client is None:
        return _error(f"The {title} models are unavailable. Check your config and API keys.")

    context = attachment.get_combined_attachment_context() if use_attachments else ""
    skill_context = skills.get_context()
    route = _route_from_providers(_specialist_provider_names(role_key))
    pulse = build_pulse(route, **_context_counts(include_files=use_attachments))

    if specialist == "writer":
        response = specialist_ai.writer(question, p_client, s_client, context, skill_context)
        return _reply(response, title=title, pulse=pulse)
    if specialist == "coder":
        response = specialist_ai.coder(question, p_client, s_client, context, skill_context)
        return _reply(response, title=title, pulse=pulse)

    # Strategist: questions → answers → draft → approve / revise
    questions = specialist_ai.questionaire(question, p_client, s_client, context, skill_context)
    session.better_state = {"goal": question, "questions": questions, "draft": None,
                            "context": context, "skill_context": skill_context}
    return {
        "type": "better_questions",
        "title": title,
        "raw": questions,
        "html": render_markdown(questions),
        "questions": helper_ai.split_questions(questions),
        "pulse": pulse,
    }


def better_answers(answers):
    state = session.better_state
    if not state:
        return _error("No strategist session is active. Start with .BETTER.")
    p_client, s_client = _specialist_clients("reasoning")
    if p_client is None and s_client is None:
        return _error("The Strategist models are unavailable. Check your config and API keys.")
    draft = specialist_ai.strategist(
        state["goal"], p_client, s_client, state["questions"], answers or "N/A",
        attachment_context=state["context"], skill_context=state.get("skill_context", ""),
    )
    state["draft"] = draft
    return {"type": "better_draft", "title": "Design Draft", "raw": draft, "html": render_markdown(draft)}


def better_decision(approve):
    state = session.better_state
    if not state or not state.get("draft"):
        return _error("No strategist draft to decide on.")
    if approve:
        draft = state["draft"]
        session.better_state = None
        return _reply(draft, title="🧠 The Strategist")
    p_client, s_client = _specialist_clients("reasoning")
    if p_client is None and s_client is None:
        return _error("The Strategist models are unavailable. Check your config and API keys.")
    draft = specialist_ai.strategist(
        state["goal"], p_client, s_client, state["questions"], "N/A",
        previous_draft=state["draft"], force_secondary=True, attachment_context=state["context"],
        skill_context=state.get("skill_context", ""),
    )
    state["draft"] = draft
    return {"type": "better_draft", "title": "Alternative Design Draft", "raw": draft, "html": render_markdown(draft)}


# --------------------------------------------------------------------------
# Attachments
# --------------------------------------------------------------------------

def add_attachment(path):
    result = attachment.ingest_file(path)
    if not result["success"]:
        system_log("COMMAND", "ERROR", f"Attach failed for {path}: {result['message']}")
        return {"type": "error", "message": result["message"]}
    system_log("COMMAND", "INFO", f"Attached {result['file_type']} file: {result['file_path']}")
    return {
        "type": "attached",
        "message": result["message"],
        "recommendation": result.get("recommendation"),
        "attachments": attachments_payload(),
    }


def attachments_payload():
    items = []
    for index, (path, item) in enumerate(attachment.get_all_attachments().items()):
        summary = attachment.format_attachment_summary({
            "file_name": item["file_name"],
            "file_type": item["file_type"],
            "file_path": item["file_path"],
            "attached_at": item.get("attached_at", ""),
            "metadata": item["metadata"],
        })
        items.append({
            "index": index,
            "name": item["file_name"],
            "type": item["file_type"],
            "summary": summary,
            "detail": attachment.format_attachment_detail(item),
            "selected": item.get("selected", True),
        })
    return items


def set_attachment_selected(index, selected):
    updated = attachment.set_selected(index, bool(selected))
    if updated is None:
        return _error("Invalid attachment number.")
    state = "included in" if updated.get("selected", True) else "excluded from"
    system_log("COMMAND", "INFO", f"Attachment {updated['file_name']} is {state} prompts.")
    return {"type": "attachments", "attachments": attachments_payload()}


def remove_attachment(index):
    removed = attachment.remove_attachment(index)
    if removed is None:
        return _error("Invalid attachment number.")
    system_log("COMMAND", "INFO", f"Removed attachment: {removed['file_name']}")
    return {"type": "detached", "message": f"Removed attachment: {removed['file_name']}", "attachments": attachments_payload()}


# --------------------------------------------------------------------------
# Attachment -> study trail
# --------------------------------------------------------------------------

STUDY_PLAN_PROMPT = """You are a tutor. Turn the study material below into a study trail \
that someone can work through later.

FILE: {file_name}

=== MATERIAL ===
{material}
=== END MATERIAL ===

Answer in exactly this format and nothing else:
TITLE: <short human title for the topic, no quotes, no trailing punctuation>
DESCRIPTION: <one line on what the trail covers>
CONCEPT: <concept name> | <one line note>
CONCEPT: <concept name> | <one line note>

Give 3 to 8 CONCEPT lines, each note one line long."""


def trail_from_attachment(index):
    """Turn an attached file into a study trail: title, concepts and a note.

    The model writes the plan. A plan that cannot be read still leaves a
    usable trail built from the file name, and a failure after the trail was
    created removes it again — no half-built trail survives.
    """
    items = list(attachment.get_all_attachments().items())
    if not isinstance(index, int) or index < 0 or index >= len(items):
        raise ValueError("Pick an attached file first.")
    path, item = items[index]
    name = item.get("file_name") or os.path.basename(path)
    user_id = session.user_id
    if user_id is None:
        raise ValueError("Select a profile first.")

    plan = _study_plan(name, item.get("content") or "") or {}
    title = (plan.get("title") or "").strip().rstrip(".") or _title_from_file(name)
    description = (plan.get("description") or "").strip() or f"Study trail from {name}."
    concepts = plan.get("concepts") or [{"name": title, "note": f"Read {name}."}]

    trail_id = study_db.create_trail(user_id, title, description)
    try:
        for concept in concepts:
            study_db.add_concept(
                user_id, trail_id, concept["name"], mastery="new", note=concept.get("note", ""),
            )
        study_db.add_note(user_id, trail_id, title, f"{description}\n\nSource: {name}")
    except Exception as e:
        study_db.delete_trail(user_id, trail_id)
        system_log("STUDY", "ERROR", f"Study trail from {name} failed: {e}")
        raise
    return study_db.get_trail(user_id, trail_id)


def _title_from_file(name):
    """A human title for a file: 'photosynthesis-notes.md' -> 'photosynthesis notes'."""
    stem = re.sub(r"[_-]+", " ", os.path.splitext(name)[0]).strip()
    return stem or name


def _study_plan(file_name, text):
    """Ask the model for a study plan; None when it cannot answer or be read."""
    material = (text or "").strip()[:20000]  # shortcut: only the first 20k characters reach the model
    prompt = STUDY_PLAN_PROMPT.format(file_name=file_name, material=material or "(no text could be extracted)")
    notes = []
    try:
        raw = ask_ai(prompt, notes)
    except Exception as e:
        system_log("STUDY", "WARNING", f"No study plan for {file_name}: {e}")
        return None
    return _parse_study_plan(raw)


def _parse_study_plan(raw):
    """Read the TITLE / DESCRIPTION / CONCEPT lines out of a model answer."""
    plan = {"title": "", "description": "", "concepts": []}
    for line in (raw or "").splitlines():
        label, _, value = line.partition(":")
        label = label.strip().strip("-*# ").upper()
        value = value.strip().strip('"').strip("*").strip()
        if label == "TITLE":
            plan["title"] = value
        elif label == "DESCRIPTION":
            plan["description"] = value
        elif label == "CONCEPT":
            name, _, note = value.partition("|")
            name = name.strip().strip('"').strip()
            if name:
                plan["concepts"].append({"name": name, "note": note.strip().strip('"').strip()})
    if not plan["title"] and not plan["concepts"]:
        return None
    plan["concepts"] = plan["concepts"][:8]
    return plan


# --------------------------------------------------------------------------
# Voice
# --------------------------------------------------------------------------

_whisper = None
_whisper_lock = threading.Lock()
_kitten = None


def transcribe(path):
    """Transcribe an audio file with faster-whisper (model loads on first use)."""
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel
            system_log("VOICE", "INFO", "Loading faster-whisper 'small' model.")
            _whisper = WhisperModel("small")
    segments, _info = _whisper.transcribe(path)
    return "".join(segment.text for segment in segments).strip()


def synthesize(text, engine):
    """Return (audio_bytes, mimetype) for the requested TTS engine."""
    if engine == "kitten":
        global _kitten
        import soundfile as sf
        if _kitten is None:
            from kittentts import KittenTTS
            system_log("VOICE", "INFO", "Loading KittenTTS model.")
            _kitten = KittenTTS("KittenML/kitten-tts-mini-0.8")
        audio = _kitten.generate(text=text, voice="Jasper", speed=1.2)
        buffer = io.BytesIO()
        sf.write(buffer, audio, 24000, format="WAV")
        return buffer.getvalue(), "audio/wav"

    import edge_tts
    system_log("VOICE", "INFO", "Generating speech with EdgeTTS.")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = tmp.name
    try:
        asyncio.run(edge_tts.Communicate(text, "en-IN-NeerjaNeural").save(path))
        with open(path, "rb") as f:
            return f.read(), "audio/mpeg"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Main entry point used by the web routes
# --------------------------------------------------------------------------

EXIT_WORDS = {"exit", "quit", "close", "bye", "goodbye"}


def send(message, input_mode="text", exclude_ids=None, record=True, previous_answer=None):
    """Run one message (chat or command) through the full pipeline.

    exclude_ids drops manifest sources from the prompt (a re-ask with one
    source removed). record=False keeps the whole turn out of the conversation
    history, so a re-ask never repeats the user's message. previous_answer is
    the answer being re-asked: it must not be in the prompt, because it was
    written with the very source the re-ask removes.
    """
    text = (message or "").strip()
    if not text:
        return _error("Empty message.")
    if session.user_id is None:
        return _error("No profile selected. Pick one on the home page.")

    excluded = set(exclude_ids or ())
    session.last_input = input_mode
    upper = text.upper()

    if upper.startswith(".WEB"):
        return handle_web(text[4:].strip() if len(text) > 4 else "")

    if upper.startswith(".VISION"):
        return handle_vision(text[7:].strip() if len(text) > 7 else "")

    if upper == ".HELP":
        return _reply(HELP_TEXT, title="Help")
    if upper.startswith(".BETTER"):
        prefill = text[7:].strip()
        return {"type": "better_open", "prefill": prefill}
    if upper == ".CHANGE":
        return {"type": "profile_picker", "profiles": profiles(), "current": session.user_id}
    if upper == ".VOICE":
        return {"type": "info", "message": "Voice replies are switched in the header (Off / EdgeTTS / KittenTTS).", "engine": session.tts_engine}
    if upper == ".ABOUT":
        return _reply(about_text(), title="About Solaris")
    if upper == ".CLEAR":
        return {"type": "clear"}
    if upper in (".ATTACH", ".DETACH"):
        if upper == ".ATTACH":
            return {"type": "info", "message": "Use the paperclip button to attach a file (md, pdf, jpg, png)."}
        return {"type": "attachments", "attachments": attachments_payload()}

    for command, (mode, title) in STUDY_MODES.items():
        if upper.startswith(command):
            topic = text[len(command):].strip()
            if not topic:
                return _error(f"Please provide a topic. Example: {command.lower()} photosynthesis")
            return handle_study(topic, mode, title)

    if text.lower().strip(" ?!.") in EXIT_WORDS:
        farewell = session.end_session()
        return {"type": "session_end", "message": farewell}

    # ---- normal chat ------------------------------------------------------
    route = new_route()
    started = time.time()
    with session.lock:
        if len(session.conv_history) > 24:
            session.imp_conv_history.append(helper_ai.current_chat_summariser(session.conv_history))
            session.conv_history = session.conv_history[-7:]
            system_log("AI", "INFO", f"Current session summarised. Memories: {len(session.imp_conv_history)}")

        if record:
            session.conv_history.append({"role": "user", "content": text})
            session.session_history.append({"role": "user", "content": text})

        history = session.conv_history[-25:]
        if not record:
            # A re-ask must not see the answer it replaces: it was written with
            # the very source we are removing. Match the answer itself, not
            # "the last one" — an older answer can be re-asked too.
            target = (previous_answer or "").strip()
            if target:
                for index in range(len(history) - 1, -1, -1):
                    if history[index]["role"] == "assistant" and history[index]["content"].strip() == target:
                        history = history[:index] + history[index + 1:]
                        break
            elif history and history[-1]["role"] == "assistant":
                history = history[:-1]
        conversation_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in history
        )
        # The past-sessions block is ranked by relevance to this question; the
        # newest summaries are used when the vector index is cold or unavailable.
        session.memories = history_db.access_history_similar(session.user_id, text)
        summary_text = "" if "history" in excluded else "\n\n".join(
            f"[{timestamp}]\n{summary}" for summary, timestamp in session.memories
        )
        session_facts = [] if "session" in excluded else session.imp_conv_history
        workspace_memory, used_memories = memory_db.build_context(
            session.user_id, text, exclude_ids=excluded,
        )
        memory_text = "\n\n".join(part for part in (
            summary_text,
            f"Workspace memories:\n{workspace_memory}" if workspace_memory else "",
        ) if part)
        attachment_context = attachment.get_combined_attachment_context(exclude_ids=excluded)
        file_sources = _file_sources(excluded)
        bundle = skills.context_bundle(exclude_ids=excluded)
        skill_context = bundle["text"]
        skill_sources = bundle["skills"]

        prompt = helper_ai.build_prompt(
            session.name,
            "" if "profile" in excluded else session.preference,
            session_facts, conversation_text,
            memory_text, text,
            "" if "profile" in excluded else session.about_user,
            attachment_context, skill_context,
        )

    notes = []
    try:
        response = ask_ai(prompt, notes, route)
    except Exception as e:
        system_log("SYSTEM", "ERROR", f"Chat failed: {e}")
        message = str(e)
        if "503" in message:
            return _error("Server unavailable at the moment (503).")
        if "429" in message:
            return _error("Rate limit reached (429) and the local model failed too.")
        return _error(f"An error occurred: {_short(e, 300)}")

    with session.lock:
        if record:
            session.conv_history.append({"role": "assistant", "content": response})
            session.session_history.append({"role": "assistant", "content": response})

    session.used_memories = used_memories
    pulse = build_pulse(
        route,
        **_context_counts(),
        memories=len(used_memories),
        memory_items=used_memories,
        latency_ms=int((time.time() - started) * 1000),
    )
    session.last_route = pulse
    _offer_memory_suggestions(session.user_id, text)

    manifest = _context_manifest(
        used_memories, skill_sources, file_sources, _profile_source(excluded),
        history=len(summary_text),
        session_facts=sum(len(str(item)) for item in session_facts),
    )
    return _reply(response, notes=notes, pulse=pulse, context=manifest)


def _offer_memory_suggestions(user_id, message):
    """Queue extracted memories as *suggestions* — never as silent active memory."""
    try:
        created = memory_db.extract_suggestions(user_id, message)
    except Exception as e:  # extraction must never break a reply
        system_log("MEMORY", "WARNING", f"Memory extraction skipped: {e}")
        return []
    if created:
        system_log("MEMORY", "INFO", f"{len(created)} memory suggestion(s) queued for user_id={user_id}.")
    return created


# --------------------------------------------------------------------------
# Answer controls (the refinement dial under every answer)
# --------------------------------------------------------------------------

# Every follow-up prompt lives here so they stay auditable — no prompt text in JS.
ANSWER_CONTROLS = {
    "shorter": {
        "label": "Shorter",
        "hint": "Tighten the answer",
        "instruction": (
            "Rewrite the previous answer so it is substantially shorter. Keep every fact, "
            "number and code detail that matters, cut repetition and padding. "
            "Return only the rewritten answer."
        ),
    },
    "deeper": {
        "label": "Go deeper",
        "hint": "Add substance and detail",
        "instruction": (
            "Expand the previous answer with more depth: mechanisms, trade-offs, edge cases and "
            "concrete specifics. Do not pad with filler. Return only the expanded answer."
        ),
    },
    "challenge": {
        "label": "Challenge this",
        "hint": "Argue the other side",
        "instruction": (
            "Challenge the previous answer. Name its weakest assumptions, where it could be wrong, "
            "and what evidence would change the conclusion. Be direct and specific. "
            "Return only the critique."
        ),
    },
    "plan": {
        "label": "Make a plan",
        "hint": "Turn it into steps",
        "instruction": (
            "Turn the previous answer into an actionable plan: ordered steps, what each step needs, "
            "and the first concrete action to take today. Return only the plan."
        ),
    },
    "notes": {
        "label": "Turn into notes",
        "hint": "Compact notes to keep",
        "instruction": (
            "Turn the previous answer into compact study notes: short headings, bullet points, "
            "definitions kept verbatim where they matter. Return only the notes."
        ),
    },
    "beginner": {
        "label": "Explain for a beginner",
        "hint": "Plain-language version",
        "instruction": (
            "Explain the previous answer as if to a curious beginner: plain language, one analogy, "
            "no unexplained jargon. Return only the explanation."
        ),
    },
    "examples": {
        "label": "Add examples",
        "hint": "Concrete examples",
        "instruction": (
            "Keep the previous answer and add concrete, worked examples that make it tangible. "
            "Return the answer with the examples included."
        ),
    },
    "regenerate": {
        "label": "Regenerate",
        "hint": "Answer the original question again",
        "instruction": (
            "Answer the original question again from scratch. Do not reuse the previous wording: "
            "aim for a clearer, better structured answer with the same technical accuracy. "
            "Return only the new answer."
        ),
    },
}


def answer_controls():
    """Control metadata for the UI (labels only — prompts stay server-side)."""
    return [
        {"key": key, "label": value["label"], "hint": value["hint"]}
        for key, value in ANSWER_CONTROLS.items()
    ]


def follow_up(action, question, answer):
    """Run one refinement of a previous answer through the normal pipeline."""
    control = ANSWER_CONTROLS.get(action)
    if control is None:
        return _error("Unknown refinement.")
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not answer:
        return _error("Nothing to refine — send a message first.")
    if session.user_id is None:
        return _error("No profile selected. Pick one on the home page.")

    route = new_route()
    started = time.time()

    # Refinements see the same compact memory block as a normal reply, so the
    # pulse stays honest about what the model was given.
    memory_items = []
    memory_note = ""
    try:
        context_text, memory_items = memory_db.build_context(session.user_id, question or answer)
        if context_text:
            memory_note = f"Workspace memories:\n{context_text}\n\n"
    except Exception as e:  # memory must never break a refinement
        system_log("MEMORY", "WARNING", f"Memory context skipped for refinement: {e}")

    # Refinements see the same skill and file context as the original reply,
    # so the pulse stays honest about what the model was given.
    bundle = skills.context_bundle()
    skill_context = bundle["text"]
    skill_sources = bundle["skills"]
    attachment_context = attachment.get_combined_attachment_context()
    file_sources = _file_sources()
    context_note = "\n\n".join(part for part in (skill_context, attachment_context) if part)
    if context_note:
        context_note += "\n\n"

    prompt = (
        f"{control['instruction']}\n\n"
        f"{memory_note}"
        f"{context_note}"
        f"Original question:\n{question or '(not recorded)'}\n\n"
        f"Previous answer:\n{answer}\n"
    )
    notes = []
    try:
        response = ask_ai(prompt, notes, route)
    except Exception as e:
        system_log("SYSTEM", "ERROR", f"Refinement '{action}' failed: {e}")
        return _error(f"The refinement could not be generated: {_short(e, 200)}")

    with session.lock:
        session.conv_history.append({"role": "user", "content": f"({control['label']}) {question}".strip()})
        session.conv_history.append({"role": "assistant", "content": response})
        session.session_history.append({"role": "user", "content": f"({control['label']}) {question}".strip()})
        session.session_history.append({"role": "assistant", "content": response})

    pulse = build_pulse(
        route,
        **_context_counts(),
        memories=len(memory_items),
        memory_items=memory_items,
        latency_ms=int((time.time() - started) * 1000),
    )
    session.last_route = pulse
    manifest = _context_manifest(memory_items, skill_sources, file_sources)
    return _reply(response, title=control["label"], notes=notes, pulse=pulse, context=manifest)


# --------------------------------------------------------------------------
# Setup wizard support
# --------------------------------------------------------------------------


def whichllm_command():
    """Best available way to run whichllm on this machine."""
    if shutil.which("whichllm"):
        return ["whichllm"]
    if shutil.which("uvx"):
        return ["uvx", "whichllm@latest"]
    return None


def install_whichllm(log):
    """Install whichllm, preferring `uv tool install`, falling back to pip."""
    if shutil.which("uv"):
        log("$ uv tool install whichllm")
        _run_streaming(["uv", "tool", "install", "whichllm"], log)
    else:
        log(f"$ {sys.executable} -m pip install whichllm")
        _run_streaming([sys.executable, "-m", "pip", "install", "whichllm"], log)
    log("whichllm installed.")
    return shutil.which("whichllm")


def run_whichllm(top=10, log=None):
    """Run whichllm in JSON mode and return the parsed hardware + model rows."""
    log = log or (lambda line: None)
    command = whichllm_command()
    if command is None:
        log("Neither uv, uvx nor whichllm found — installing with pip first.")
        install_whichllm(log)
        command = whichllm_command()
    if command is None:
        raise RuntimeError("whichllm is not available. Install it with 'pip install whichllm'.")

    command = command + ["--top", str(top), "--json"]
    log("$ " + " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "whichllm failed").strip()[:400])

    start = result.stdout.find("{")
    if start == -1 or not result.stdout[start:].strip():
        raise RuntimeError("whichllm returned no output.")
    import json
    data = json.loads(result.stdout[start:])
    models = [m for m in data.get("models", []) if m.get("can_run", True)]
    return {"hardware": data.get("hardware", {}), "models": models}


def install_requirements(log):
    """Install the project requirements (used by the wizard's environment step)."""
    log(f"$ {sys.executable} -m pip install -r requirements.txt")
    _run_streaming([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], log)
    log("Dependencies installed.")
    return True


def _run_streaming(command, log):
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    for line in process.stdout:
        log(line.rstrip())
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(command)}")


def missing_imports():
    """Import check for the wizard's environment step."""
    checks = {
        "flask": "flask",
        "faster_whisper": "faster-whisper",
        "sounddevice": "sounddevice",
        "pypdf": "pypdf",
        "PIL": "pillow",
        "requests": "requests",
        "ollama": "ollama",
        "edge_tts": "edge-tts",
        "markdown_it": "markdown-it-py",
    }
    missing = []
    for module, package in checks.items():
        try:
            __import__(module)
        except Exception:
            missing.append(package)
    return missing


# --------------------------------------------------------------------------
# Skill drafts (turn the current thread into a reusable skill)
# --------------------------------------------------------------------------

# The prompt text lives here, never in the browser.
SKILL_DRAFT_PROMPT = (
    "Turn this conversation into a reusable skill: a short set of instructions "
    "that makes a later answer better in the same situation.\n\n"
    "Answer in exactly this format and nothing else:\n"
    "TITLE: <short name, max six words>\n"
    "DESCRIPTION: <one line, max 100 characters>\n"
    "DEFAULT PROMPT: <the message that starts the skill, one line>\n"
    "BODY:\n<the instructions to follow, markdown, max 200 words>\n\n"
    "Conversation:\n"
)


def _parse_skill_draft(text):
    """Read the labelled draft format the model was asked for."""
    fields = {}
    body = []
    in_body = False
    for line in str(text or "").splitlines():
        if in_body:
            body.append(line)
            continue
        if line.strip().startswith("```"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().strip("*# ").lower()
        if key == "body":
            in_body = True
            if value.strip():
                body.append(value.strip())
            continue
        if key in ("title", "description", "default prompt", "default_prompt"):
            fields[key] = value.strip()
    title = fields.get("title", "").strip()
    instructions = "\n".join(body).strip()
    if not title or not instructions:
        return None
    return {
        "title": title,
        "description": fields.get("description", "").strip(),
        "default_prompt": fields.get("default prompt", fields.get("default_prompt", "")).strip(),
        "body": instructions,
    }


def _fallback_skill_draft(history):
    """A draft built from the thread itself, for when the model cannot help."""
    users = [str(item.get("content") or "").strip() for item in history
             if item.get("role") == "user"]
    answers = [str(item.get("content") or "").strip() for item in history
               if item.get("role") == "assistant"]
    title = (users[0].splitlines() or [""])[0].strip()[:60] if users else ""
    title = title.replace("/", " ").replace("\\", " ").replace("..", " ").strip() or "Saved conversation"
    body = (
        f"User request:\n{users[-1] if users else ''}\n\n"
        f"Answer that worked:\n{answers[-1] if answers else ''}\n\n"
        "Follow the approach above when a similar request comes up again."
    ).strip()
    return {
        "title": title,
        "description": f"Reusable instructions captured from this conversation: {title}",
        "default_prompt": f"Apply the {title} skill.",
        "body": body,
    }


def draft_skill_from_thread():
    """Draft a skill from the recent conversation. Never raises.

    When the model is unavailable or its answer cannot be parsed, the draft is
    built from the thread itself so the editor always has something to edit.
    """
    history = [item for item in list(session.conv_history)[-12:] if isinstance(item, dict)]
    fallback = _fallback_skill_draft(history)
    if not history:
        return fallback
    conversation = "\n".join(
        f"{str(item.get('role') or 'user').title()}: {str(item.get('content') or '')}"
        for item in history
    )
    notes = []
    try:
        response = ask_ai(SKILL_DRAFT_PROMPT + conversation, notes)
    except Exception as e:
        system_log("SYSTEM", "WARNING", f"Skill draft failed: {e}")
        return fallback
    return _parse_skill_draft(response) or fallback
