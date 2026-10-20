# Solaris – AI Chatbot Agent Instructions

## Quick Start
```bash
python chatbot.py            # starts the web interface on 127.0.0.1 (first free port from 7900), opens the browser
python chatbot.py --terminal # legacy terminal (TUI) interface
```

## Environment
- Python 3.14 (`.venv`, managed with `uv`; `pyproject.toml` pins `requires-python = ">=3.14"`)
- `.env` required with API keys — writable from the web UI (gated by the API password)
- `config.json` controls model selection and fallback chains — writable from the web UI
- `settings.json` controls response style/personality — writable from the web UI
- `database.db` (SQLite) holds profiles, chat history and all profile workspace data
- All of the above are **user data**: never rewrite them to make a test pass

## Key Commands
| Task | Command |
|------|---------|
| Run assistant (web) | `python chatbot.py` |
| Run assistant (terminal) | `python chatbot.py --terminal` |
| Custom web port | `python chatbot.py --port 7900` |
| Run tests | `pytest Test/` |
| Offline web smoke test | `python Test/web_smoke.py` |
| Install deps | `pip install -r requirements.txt` (or `uv add <pkg>`) |

## Architecture Notes
- **Entry point**: `chatbot.py` — launcher (port walk 7900–7909, browser open, `--terminal` fallback)
- **Core**: `core.py` — session state + the whole message pipeline every front end shares
- **Web**: `web/app.py` (pages + JSON API), `web/api_workspace.py` (workspace blueprint),
  `web/access.py` (profile authorization), `web/jobs.py` (background installs / whichllm)
- **Legacy terminal**: `terminal.py` — the original TUI, kept working, not the default
- **Config I/O**: `config_io.py` (JSON + `_backups/`), `env_io.py` (`.env`, keeps `os.environ` in sync)
- **Databases**: `main_db.py` (profiles + credential hashes + migrations), `history_db.py`
  (conversations, web_log), `memory_db.py` (Constellation Memory), `study_db.py` (Study Trails),
  `workspace_db.py` (session task + checkpoint)
- **Models**: chat fallback Gemini → OpenRouter → Ollama (local); summarisation OpenRouter → Ollama
- **Attachments**: in-memory only (`attachment.py`); web uploads land in `_uploads/` first
- **Voice/TTS**: `/api/voice` (faster-whisper, lazy), `/api/tts` (EdgeTTS mp3 / KittenTTS wav)

## Three separate credentials (never reuse one for another)
1. **App-wide API password** — 6 chars, PBKDF2-SHA256 in `user_data.api_password_hash` (lowest
   `user_id`). Gates API-key add/change/remove only. In-memory 5-attempt / 60 s lockout.
2. **Profile activation code** — 8 chars shown once as `ABCD-EFGH`, stored only as
   `activation_code_hash`. Required to reactivate an inactive profile.
3. **Profile password** — required to unlock a *private* profile; `profile_password_hash`, PBKDF2.

Profile access model, enforced server-side in `web/access.py` + `web/app.py`:

| State | Visibility | Behaviour |
|-------|-----------|-----------|
| active | public | selectable |
| active | private | needs the profile password (unlock lasts for that Flask session) |
| inactive | public | needs the activation code first |
| inactive | private | activation code, then password |

- `visibility` (`public`/`private`) and `state` (`active`/`inactive`) are canonical;
  `is_private`/`is_active` stay as legacy mirrors for `helper_ai.current_profile_info`.
- The legacy terminal enforces the same rule (`terminal.profile_gate`) — it never opens a profile
  the web interface would deny.
- Locked profiles expose only id, name, visibility, state, has-password, lockout seconds.
  Never preference/about/memory/history content, never a hash.
- Per-profile lockout: `MAX_FAILED_ATTEMPTS` (5) → `LOCKOUT_SECONDS` (60), stored on the row.
- `main_db._migrate_legacy_secrets` hashes any plain-text legacy `password`/`activation_code`
  values on first run, then nulls the plain text.

## Product features (see `web/static/` + `web/api_workspace.py`)
- **Living Workspace** — collapsible shelf on `/chat` (task, files, skills, context, checkpoint, study, routing);
  open/closed state in `localStorage`. A checkpoint is only written on an explicit save.
- **Files shelf** — every attachment is a box in the shelf. Only selected boxes (lime ring, `--lens-select`)
  are assembled into the prompt; unselected files keep their extracted stats but never reach a model.
  Selection lives in memory next to the attachment itself.
- **Skills shelf** — Markdown skills in `Skills/` (project) and `~/.solaris/skills/` (user, overrides project
  by name), shown as a collapsed dropdown that opens into a grid. Toggling a card injects its body into the
  prompt (`skills.get_context()`); Run sends its `default-prompt` as a visible message. Only active skills
  reach the model, and their prompt text never lives in JS.
- **Answer controls dial** — prompts live in `core.ANSWER_CONTROLS` (never in JS); every refinement
  goes through `core.follow_up` → normal `ask_ai` pipeline and appends to history.
- **Privacy pulse** — `core.build_pulse`/`_classify`: local / cloud / hybrid / unknown, built from the
  providers that actually saw the request. A failed cloud attempt is never reported as "local".
  Reasons and notes are scrubbed by `core._scrub` (no keys/tokens in payloads).
- **Constellation Memory** — `memory_db.py`; statuses active / suggested / archived, grouped by
  category. Extracted statements land as *suggestions* only; `build_context` sends at most
  `CONTEXT_LIMIT` relevant nodes and reports which ones were used.
- **Study Trails** — `study_db.py`; trails + concepts (new/practicing/confident/revisit) + saved notes.
  A successful `.QUIZ` counts against a trail with the same topic. No points, streaks or badges.
- **Solaris Lens** — `web/static/app.css`; aurora tokens (`--lens-*`) used only for routing, privacy,
  memory, study progress and system activity. `prefers-reduced-motion` respected, `:focus-visible` set.

## Testing
- `pytest Test/` — file fixtures `test_attach.pdf`, `test_attach.jpg` live in the repo root
- `Test/web_smoke.py` — offline end-to-end check of the web app (stubs SDKs, temp config/.env/db)
- `Test/workspace/test_skills.py` and `Test/workspace/test_attachment_selection.py` — skills discovery/activation and file selection coverage
- `Test/workspace/` — profile access, memory, study, workspace, answer controls, privacy pulse
  (offline: `Test/_stubs.py` installs fake `openai`/`google.genai`/`ollama`/`PIL`/`pypdf`)
- `Test/` is untracked (gitignored) — a local-only suite; keep it passing anyway

## Common Gotchas
- `config.json` is cached at import in `helper_ai`/`web_search`/`study_ai`/`specialist_ai` — after a
  write call `core.reload_dependent_modules()`
- `.gitignore` ignores `*.md`; project skills are re-included with `!Skills/` + `!Skills/**`
- Tables are created on import of the DB modules; migrations must be idempotent and safe for a
  pre-existing `database.db` (see `main_db._ensure_profile_access_columns`)
- `core.session` is single-user and in-memory; the private-profile unlock lives in the Flask session
  cookie, so a second browser needs its own unlock
- Importing `config.py` pulls in `openai` and `google.genai` — stub them in tests, never call real
  providers
- `terminal.py` `.ATTACH` rejects relative paths; the web UI uploads server-side so has no such limit
- Voice: terminal records 5 s at 16 kHz; the web sends webm/opus decoded through `av`
- `helper_ai` starts even when `OR_ASSIST_API_KEY` is missing (client `None` → Ollama)

## File Ownership
| Module | Responsibility |
|--------|----------------|
| `chatbot.py` | Launcher: port pick, browser open, `--terminal` fallback |
| `terminal.py` | Original terminal loop, commands, voice, dispatch |
| `core.py` | Session state, chat pipeline, commands, providers, pulse, answer controls |
| `web/app.py` | Flask pages + JSON API (profiles, chat, wizard, settings, keys, password) |
| `web/access.py` | Session unlock state + server-side profile authorization |
| `web/api_workspace.py` | Memory, study trails, workspace shelf, answer-control routes |
| `web/jobs.py` | In-memory background job runner |
| `main_db.py` | Profiles, credential hashing, access state, migrations |
| `memory_db.py` | Constellation Memory nodes (active/suggested/archived) |
| `study_db.py` | Study trails, concepts, saved notes |
| `skills.py` | Markdown skills: discovery, activation, prompt context |
| `workspace_db.py` | Session task + checkpoint |
| `history_db.py` | Conversations and web_log |
| `config_io.py` / `env_io.py` | Config and `.env` reads/writes with `_backups/` |
| `helper_ai.py` | Preference/about summarisation, prompt building, profile info |
| `specialist_ai.py` / `study_ai.py` | `.BETTER` flows / study command prompts |
| `web_search.py` / `vision_ai.py` | `.WEB` (Tavily → Firecrawl) / `.VISION` |
| `attachment.py` | File ingestion, validation, temporary context |
| `model_state.py` | Session model availability (429/404 disable, 503 cooldown) |
| `web/templates/`, `web/static/` | Landing, chat (+shelf), memory, study, settings, wizard UI |

## UI Conventions
- Flask + Jinja + vanilla JS, no build step, no framework, no external assets
- `web/static/app.js` holds shared helpers (`api`, `toast`, `escapeHtml`, `openModal`, profile access)
- Page scripts: `landing.js`, `chat.js`, `memory.js`, `study.js`, `settings.js`, `setup.js`;
  `workspace.js` owns the shelf, privacy pulse and refinement dial on the chat page
- Content from the server is inserted with `textContent` or the project's `escapeHtml` — never raw
  HTML from model output
- Keep `app.css` tokens (`--lens-*`) for meaningful states only; no decorative gradients or emoji UI

## Ponytail Mode
This repo uses `@dietrichgebert/ponytail` plugin (full intensity). Prefer stdlib/native solutions, delete over add, shortest working diff.
