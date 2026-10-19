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
import env_io
import helper_ai
import history_db
import main_db
import memory_db
import model_state
import specialist_ai
import study_ai
import study_db
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
study_db.create_table()
workspace_db.create_table()
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
        "memories": int(extra.get("memories") or 0),
        "memory_items": extra.get("memory_items") or [],
        "study_trail": extra.get("study_trail"),
        "latency_ms": extra.get("latency_ms"),
        "reason": extra.get("reason"),
    }
    return pulse


def _reply(text, title="Solaris", notes=None, sources=None, pulse=None):
    return {
        "type": "reply",
        "title": title,
        "raw": text,
        "html": render_markdown(text),
        "notes": notes or [],
        "sources": sources or [],
        "speak": session.tts_engine != "off",
        "pulse": pulse,
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
- `.DETACH` — list and remove attachments
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
        return _error("No images attached. Use the paperclip button to attach an image first.")
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
        pulse=build_pulse(route, attachments=True),
    )


STUDY_MODES = {
    ".DETAIL": ("detail", "Detailed Explanation"),
    ".SIMPLE": ("simple", "Simple Explanation"),
    ".QUIZ": ("quiz", "Quiz"),
    ".TIMELINE": ("timeline", "Timeline"),
    ".COMPARE": ("compare", "Comparison"),
    ".STEPS": ("steps", "Steps"),
}


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
        try:
            for trail in study_db.list_trails(session.user_id):
                if trail["title"].strip().lower() == (topic or "").strip().lower():
                    study_db.register_quiz(session.user_id, trail["id"])
                    system_log("STUDY", "INFO", f"Quiz counted for trail {trail['id']}.")
        except Exception as e:  # counting must never break the reply
            system_log("STUDY", "WARNING", f"Could not record the quiz: {e}")

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
    route = _route_from_providers(_specialist_provider_names(role_key))
    pulse = build_pulse(route, attachments=bool(context))

    if specialist == "writer":
        response = specialist_ai.writer(question, p_client, s_client, context)
        return _reply(response, title=title, pulse=pulse)
    if specialist == "coder":
        response = specialist_ai.coder(question, p_client, s_client, context)
        return _reply(response, title=title, pulse=pulse)

    # Strategist: questions → answers → draft → approve / revise
    questions = specialist_ai.questionaire(question, p_client, s_client, context)
    session.better_state = {"goal": question, "questions": questions, "draft": None, "context": context}
    return {
        "type": "better_questions",
        "title": title,
        "raw": questions,
        "html": render_markdown(questions),
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
        attachment_context=state["context"],
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
        })
    return items


def remove_attachment(index):
    removed = attachment.remove_attachment(index)
    if removed is None:
        return _error("Invalid attachment number.")
    system_log("COMMAND", "INFO", f"Removed attachment: {removed['file_name']}")
    return {"type": "detached", "message": f"Removed attachment: {removed['file_name']}", "attachments": attachments_payload()}


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


def send(message, input_mode="text"):
    """Run one message (chat or command) through the full pipeline."""
    text = (message or "").strip()
    if not text:
        return _error("Empty message.")
    if session.user_id is None:
        return _error("No profile selected. Pick one on the home page.")

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

        session.conv_history.append({"role": "user", "content": text})
        session.session_history.append({"role": "user", "content": text})

        conversation_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in session.conv_history[-25:]
        )
        session.memories = history_db.access_history(session.user_id)
        summary_text = "\n\n".join(f"[{timestamp}]\n{summary}" for summary, timestamp in session.memories)
        workspace_memory, used_memories = memory_db.build_context(session.user_id, text)
        memory_text = summary_text
        if workspace_memory:
            memory_text = f"{summary_text}\n\nWorkspace memories:\n{workspace_memory}".strip()
        attachment_context = attachment.get_combined_attachment_context()

        prompt = helper_ai.build_prompt(
            session.name, session.preference, session.imp_conv_history, conversation_text,
            memory_text, text, session.about_user, attachment_context,
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
        session.conv_history.append({"role": "assistant", "content": response})
        session.session_history.append({"role": "assistant", "content": response})

    session.used_memories = used_memories
    pulse = build_pulse(
        route,
        attachments=bool(attachment_context),
        memories=len(used_memories),
        memory_items=used_memories,
        latency_ms=int((time.time() - started) * 1000),
    )
    session.last_route = pulse
    _offer_memory_suggestions(session.user_id, text)

    return _reply(response, notes=notes, pulse=pulse)


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

    prompt = (
        f"{control['instruction']}\n\n"
        f"{memory_note}"
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

    attachment_context = attachment.get_combined_attachment_context()
    pulse = build_pulse(
        route,
        attachments=bool(attachment_context),
        memories=len(memory_items),
        memory_items=memory_items,
        latency_ms=int((time.time() - started) * 1000),
    )
    session.last_route = pulse
    return _reply(response, title=control["label"], notes=notes, pulse=pulse)


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
