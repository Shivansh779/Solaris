# <u>Solaris – Personal AI Chatbot</u>


![Python](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini-4285F4)
![OpenRouter](https://img.shields.io/badge/Fallback-OpenRouter-orange)
![Ollama](https://img.shields.io/badge/Offline-Ollama-black)
![Voice](https://img.shields.io/badge/Voice-Supported-success)
![Memory](https://img.shields.io/badge/Memory-Persistent-blueviolet)
![Status](https://img.shields.io/badge/Status-Active%20Development-blue)


A local, profile-aware AI chatbot with persistent memory, multiple LLM fallbacks, voice support, file attachments, web search, study tools, and SQLite-backed long-term context.

Solaris is designed to maintain personalized conversations across sessions by combining conversation history, summarized memories, and user preferences. It supports multiple user profiles, private accounts, and graceful fallback between different AI providers.

Solaris now runs as a **self-hosted web interface**: `uv run python chatbot.py` starts a local server (`127.0.0.1`), opens your browser, and gives you chat, settings and a guided setup wizard — no more editing `.env` or `config.json` by hand.

---

## <u> Features ✨ </u>

* 🌐 Self-hosted web interface (starts with the program, local only)
* 🧭 Setup wizard: dependency check, best-local-model pick via `whichllm`, API keys, models, profile
* 🔑 API-key vault: keys editable from the UI, protected by a generated 6-character password
* 💬 Text and voice input
* 🔊 Text and voice output (EdgeTTS or KittenTTS, switchable in the header)
* 👤 Multiple user profiles
* 🔒 Password-protected private profiles
* 🧠 Long-term memory using SQLite
* 📝 Automatic session summarization
* ⚙️ User preference learning
* 🔄 Multi-provider AI fallback
* 📎 File attachments (md, pdf, jpg, png) as session context
* 🗂️ Living Workspace shelf — collapsible task/files/skills/context panel on `/chat`
* 🧩 Skills — reusable Markdown playbooks in `Skills/` (project) and `~/.solaris/skills/` (user), toggled into prompt context or run as a visible prompt
* 🌌 Constellation Memory — a `/memory` page of remembered facts (active / suggested / archived)
* 🛤️ Study Trails — a `/study` page with trails, concepts, notes and quiz progress
* 🎛️ Answer controls — refine any reply (shorter, deeper, simpler, …) without retyping the question
* 🛡️ Privacy pulse — every reply shows whether it came from local, cloud or hybrid models
* 👁️ `.VISION` image analysis with vision-capable models
* 🔎 `.WEB` real-time web search with multiple depths
* 📚 Study commands (detail, simple, quiz, timeline, compare, steps)
* 🎯 `.BETTER` specialist answers (Writer, Programmer, Strategist)
* 💾 Local-first architecture

---

## <u> Project Structure 🧱 </u>

The Important files of this project and their use cases are as follows:

|File	|Purpose|
|---|---|
|chatbot.py	|Launcher — starts the web interface (or `--terminal` for the classic TUI)
|core.py	|Shared conversation core: session state, chat pipeline, commands, specialists, voice helpers
|config.py	|Provider registry and API client initializers (Gemini, OpenRouter, NVIDIA, Groq, Ollama Cloud)
|config_io.py	|Reads/writes `config.json` and `settings.json` with `_backups/` snapshots
|env_io.py	|Reads/updates `.env` from the UI and keeps `os.environ` in sync
|model_state.py	|Session model availability (429/404 disable, 503 cooldown)
|web/app.py	|Flask app: pages (landing, chat, memory, study, settings, wizard) and the JSON API
|web/access.py	|Profile unlock state and server-side authorization
|web/api_workspace.py	|Memory, study trails, workspace shelf and answer-control routes
|web/jobs.py	|Background job runner for installs and `whichllm` runs
|terminal.py	|Original terminal (TUI) interface, still runnable with `--terminal`
|helper_ai.py	|Preference/about extraction, session summarization, prompt building
|specialist_ai.py	|Specialist flows for `.BETTER` (Writer, Programmer, Strategist)
|study_ai.py	|Study command prompt builders for `.DETAIL`, `.QUIZ`, `.TIMELINE`, etc.
|web_search.py	|Web search providers for the `.WEB` command (Tavily, Firecrawl)
|vision_ai.py	|Image analysis for the `.VISION` command (NVIDIA NIM models)
|attachment.py	|File attachment system — ingestion, temporary context, vision helpers
|skills.py	|Markdown skills: discovery, YAML frontmatter, activation, prompt context
|main_db.py	|Profiles, credential hashing, access state, migrations
|history_db.py	|Long-term conversation history and `web_log`
|memory_db.py	|Constellation Memory nodes
|study_db.py	|Study trails, concepts and saved notes
|workspace_db.py	|Session task and checkpoint
|tui_utils.py	|Terminal UI helpers (markdown rendering, tables, prompts)
|spinner.py	|Loading spinners and recording timer
|requirements.txt	|Pinned dependency export (source of truth is `pyproject.toml` / `uv.lock`)

---
## <u> Architecture </u>
![UX Flow](assets/UX_Flow.png)

![Program Flow](assets/Program_flow.png)

![LLM_fallback](assets/LLM_fallback.png)

![Memory and Preference](assets/memory.png)

---


## <u> How Solaris Works </u>

The assistant maintains three layers of context:

1. Current Conversation – Active chat history.
2. Session Memory – Important facts summarized during the current session.
3. Long-Term Memory – Persistent summaries stored in SQLite and retrieved in future conversations.

User preferences are automatically summarized into concise behavioral instructions, allowing Solaris to remain consistent across multiple sessions.

On top of this sits **temporary file context** — files you attach (paperclip on the web, `.ATTACH` in the terminal) are held in memory for the session only. They inform specialist, vision, and chat responses but are **never** written to permanent memory.

---

### <u> Profiles 👤 </u>

At startup, the home page lists every profile and what it needs:

* Create new profiles — name, behaviour preference and "about you", summarized into the profile
* Open existing profiles — public ones open directly
* Update profile preferences from the profile settings
* Activate or deactivate profiles — a deactivated profile needs its 8-character activation code
  (shown once when it was created) before it can be opened again
* Secure private profiles with a password (at least 4 characters) — the unlock lasts for the
  current browser session

---

### <u> Chat Modes 🎙️ </u>

Choose your preferred interaction style:

**Input**

* Text
* Voice — the mic button records up to 5 seconds (click it again to stop early), then transcribes

**Output**

* Text
* Speech — Off / EdgeTTS / KittenTTS, switched from the header selector

`python chatbot.py` is the only command needed; typing `.VOICE` just points you at the header selector.

---

### <u>Model Fallback Pipeline 🔁</u>

Solaris automatically switches providers if one becomes unavailable.

Primary Chat Pipeline

1. Gemini
2. OpenRouter
3. Ollama

Memory & Preference Summarization

1. OpenRouter
2. Ollama

This ensures the assistant continues functioning even if cloud providers fail.

---

## <u> Built-In Commands ⌨️ </u>

### General Commands

| Command | Description|
| --- | --- |
|`.HELP`	| Display available commands
|`.CHANGE`	|Switch profiles (or use the profile menu in the header)
|`.BETTER`	|Ask a specialist (Writer / Programmer / Strategist)
|`.VOICE`	|Points at the header's text-to-speech selector (Off / EdgeTTS / KittenTTS)
|`.ABOUT` |Profile and program information
|`.CLEAR` | Clears the chat view. Conversation, memory, and context remain unchanged.
|`.ATTACH` | Use the paperclip button to attach a file (web); absolute path in the terminal
|`.DETACH` | List attachments and include or remove them
|`.VISION[:question]` | Analyze attached images with a vision-capable model
|`.WEB[:quick\|:standard\|:deep] <question>` | Search the web for real-time information (primary: Tavily, fallback: Firecrawl)
|exit, quit, bye, goodbye, close	|Save the session summary and end the session

### Study Commands

| Command | Description|
| --- | --- |
|`.DETAIL <topic>` | Explain a concept in depth, like a teacher
|`.SIMPLE <topic>` | Explain a concept in simple language
|`.QUIZ <topic>` | Generate a 10-question quiz with answers
|`.TIMELINE <topic>` | Show events in chronological order
|`.COMPARE <topic>` | Compare subjects side by side
|`.STEPS <topic>` | Break down a process into steps with explanations

---

### <u> File Attachments 📎 </u>

Attach files so Solaris can work with their actual content. In the web interface use the paperclip
button (or drop files onto the chat); in the terminal, `.ATTACH` takes an absolute path:

```
.ATTACH /path/to/notes.md
.ATTACH /path/to/report.pdf
.ATTACH /path/to/screenshot.png
```

| Type | Behaviour |
|---|---|
| `.md` | Full text read as context |
| `.pdf` | Text extracted page by page (no OCR for scanned pages) |
| `.jpg` `.jpeg` `.png` | Validated as an image, ready for `.VISION` |

* Attachments are **temporary** — held only for the session and cleared on exit.
* They are **never** written to the database or long-term memory.
* Every attachment becomes a box in the **Files** shelf; only selected boxes (lime ring) are
  assembled into the prompt, so you can keep a file's stats yet leave it out of the answer.
* `.DETACH` lists the attachments so you can include or remove one.

After attaching, Solaris gives a subtle suggestion for the best next step:
* Markdown → use `.BETTER` for context-aware specialist answers
* Image → use `.VISION <question>` to analyze it

---

### <u> Skills 🧩 </u>

Solaris has a **Living Workspace** shelf on the chat page that holds your task, attached files, skills, context, checkpoint and study info. The **Skills** section there is a collapsible dropdown that opens into a grid of cards.

* Skills are plain Markdown files with YAML frontmatter, looked up in two places: `Skills/` in the project (shipped defaults) and `~/.solaris/skills/` (personal), with the user scope winning on a name clash.
* Each card has a **Toggle** (always-on prompt context) and a **Run** (sends the skill's `default-prompt` as a visible message).
* Active skills are injected into every reply, `.BETTER` specialists, and follow-ups; their text never leaves the server.
* See the shipped examples: `code-review`, `deep-summary`, `study-tutor`.

---

### <u> `.BETTER` — Specialist Answers 🎯 </u>

Get a higher-quality answer by routing your request through a dedicated specialist:

1. **Writer** — polished, convincing prose
2. **Programmer** — code-first technical solutions
3. **Strategist** — a step-by-step reasoning flow that interviews you with targeted questions before drafting a full strategy. The questions appear as a form (one field each — leave a field blank for N/A), and the draft ends with an inline **Approve** / **Ask the Secondary Model** row.

`.BETTER` is now **context-aware**:

* The specialist dialog has an **Include attached files** checkbox, and only the files selected in the
  Files shelf are taken into account.
* Selected files shape the Strategist's questions to suit your expertise and material, rather than generic questions.
* With no files attached, everything works exactly as before.

---

### <u> `.VISION` — Image Analysis 👁️ </u>

Analyze attached images with a vision-capable model:

```
.ATTACH /path/to/screenshot.png
.VISION what is wrong with this error message?
```

* Uses a dedicated vision model (NVIDIA NIM): **Kimi-K3** primary, **Llama-3.2-90B-Vision** fallback
* Single image → analyzed directly; multiple images → pick which to use
* Falls back gracefully if the primary model fails
* Models are configurable in `config.json` under `vision_model`

---

### <u> `.WEB` — Web Search 🔎 </u>

Search the web for real-time information when chat memory is not enough:

| Syntax | Depth | Behaviour |
| --- | --- | --- |
| `.WEB:quick <question>` | 3 results | Fast, surface-level search |
| `.WEB <question>` | 5 results | Default (standard) depth |
| `.WEB:deep <question>` | 8 results | Thorough, source-heavy search |

* Primary provider is **Tavily**, fallback is **Firecrawl**.
* Results are synthesized into a single answer with source links.
* Each search is logged to the `web_log` table (query, provider, depth, sources) — raw page content is not persisted.

---

### <u> Constellation Memory & Study Trails 🌌 </u>

Two pages hold what Solaris learns over time:

* **`/memory` (Constellation Memory)** — remembered facts grouped by category. Statements extracted from chat land as **suggestions**; only what you approve becomes active and reaches the prompt.
* **`/study` (Study Trails)** — a trail per topic with concepts (new / practicing / confident / revisit) and saved notes. A successful `.QUIZ` on a trail's topic advances that trail.

Neither page uses points, streaks or badges.

---

### <u> Refining Answers 🎛️ </u>

Every reply has refinement controls underneath it (shorter, deeper, simpler, …). A refinement runs
the same chat pipeline as a normal message — with the same context — and appends both the request and
the new answer to the conversation history.

---

## <u>Requirements 📌</u>

* Python 3.14+
* SQLite
* Microphone (for voice input)
* Audio output device (for speech)
* Ollama (optional, for offline fallback)
* Gemini API Key (optional)
* OpenRouter API Key (optional)
* NVIDIA NIM / Groq API access (optional, for vision and chat providers)
* Tavily + Firecrawl API keys (optional, for `.WEB`)

---

## <u>Installation 🛠️</u>

The project is managed with [`uv`](https://docs.astral.sh/uv/) and targets Python 3.14. From the repo root:

```bash
uv sync
```

Or with plain pip:

```bash
pip install -r requirements.txt
```

`requirements.txt` is a pinned export of `pyproject.toml`; `uv.lock` is the source of truth for versions.

The setup wizard can also do this for you on first run (it lists anything missing and installs it).

---

Environment Variables

The recommended path is the **setup wizard** — it asks for each key once and writes `.env` for you. If you prefer doing it by hand, create a `.env` file in the project root:

```bash
GEMINI_API_KEY="your_gemini_api_key"
OR_API_KEY="your_openrouter_api_key"
OR_ASSIST_API_KEY="your_openrouter_helper_api_key"
NVIDIA_API_KEY="your_nvidia_api_key"
GROQ_API_KEY="your_groq_api_key"
OLLAMA_CLOUD_API_KEY="your_ollama_cloud_api_key"
TAVILY_API_KEY="your_tavily_api_key"
FIRECRAWL_API_KEY="your_firecrawl_api_key"
```

<u>API Usage 🔐</u>

|Variable |	Purpose |
|---|---|
|GEMINI_API_KEY	|Primary Gemini chat requests
|OR_API_KEY	| OpenRouter fallback chat
|OR_ASSIST_API_KEY	| Preference and memory summarization
|NVIDIA_API_KEY	| NVIDIA NIM vision and chat providers
|GROQ_API_KEY	| Groq chat provider
|OLLAMA_CLOUD_API_KEY	| Ollama cloud chat provider
|TAVILY_API_KEY	| Primary web search provider for the `.WEB` command
|FIRECRAWL_API_KEY	| Fallback web search provider for the `.WEB` command

Web keys are optional at setup: choose "No" in the wizard and `.WEB` will ask for them (with your API password) the first time you use it.

---

## <u>Running the Assistant ▶️</u>

Start the web interface (default):

```bash
uv run python chatbot.py
# or, with the project venv:
.venv/bin/python chatbot.py
```

(`python` may not be on PATH — use `uv run` or `.venv/bin/python`.)

Solaris then:

1. Picks a free local port (7900 by default — override with `--port`) and binds `127.0.0.1` only
2. Opens your browser at the interface
3. Sends you to the **setup wizard** if `config.json` or your keys are incomplete
4. Otherwise drops you on the home/status page → Chat

The classic terminal interface is still available:

```bash
uv run python chatbot.py --terminal
```

---

## <u>Setup Wizard 🧭</u>

1. **Environment** — checks packages, installs anything missing
2. **Local AI** — installs and runs [whichllm](https://github.com/Andyyyy64/whichllm), shows the top models that fit your hardware, and saves your pick as the offline model (run `ollama run <name>` to pull it)
3. **Web search** — optional Tavily / Firecrawl keys → `.env`
4. **Providers** — tick the providers you use (Gemini, OpenRouter, OpenRouter Assist, NVIDIA, Groq, Ollama Cloud) and paste their keys → `.env`
5. **Models** — chat model, fallback chain, specialists (primary/secondary per role), vision models → `config.json`
6. **Profile** — name, behaviour preference, about you
7. **Password** — a 6-character API password is generated and shown once

---

## <u>Settings & API Password 🔐</u>

Everything previously edited by hand lives in **Settings**:

* **Models** — chat primary, fallback chain, local model, specialists, vision, web depths, response style
* **API Keys** — add, replace or remove any provider or web key (writes `.env`)
* **Password** — rotate the 6-character API password

The password is stored as a PBKDF2-SHA256 hash in the `user_data.api_password_hash` column. It is required for every API-key change, including web keys added from chat — the chat window pops the same dialog when `.WEB` has no keys yet, then retries automatically after saving.

---

## <u>Runtime Files 💾</u>

The following files are generated while Solaris is running:

| File	| Purpose |
|---| --- |
|database.db	|SQLite database
|System_Logs.txt	|Application logs
|_backups/	|Timestamped copies of config.json / settings.json taken before each save
|.flask_secret	|Local session-signing key for the web interface (generated once)
|input.wav |	Recorded voice input (terminal mode)
|output.wav	| Generated speech output (terminal mode)

---

## <u>Database Design 🗂️</u>

The assistant separates user information from conversational memory.

### <u>user_data</u>

**Managed by main_db.py**

Stores:

* User profiles
* Passwords (private profiles)
* Privacy settings
* Activation state
* `api_password_hash` — PBKDF2-SHA256 hash of the 6-character API-key password (app-wide, kept on the lowest `user_id` row)

### <u>history</u>

**Managed by history_db.py**

Stores:

* Session summaries
* Long-term memory
* Associated user_id

Separating these tables keeps profile management independent from conversational memory while maintaining their relationship through the user ID.

### <u>web_log</u>

**Managed by history_db.py**

Stores:

* Web search metadata for the `.WEB` command
* Query, provider used (tavily / firecrawl), depth, and source URLs
* Associated user_id and timestamp

Raw retrieved web content is intentionally <b>not</b> persisted to keep the database small.

### <u>profile_memory</u>

**Managed by memory_db.py**

* Constellation Memory nodes: title, body, category and status (`active` / `suggested` / `archived`)
* `suggested` nodes are extracted statements waiting for your approval; only `active` nodes reach the prompt

### <u>study_trail / study_concept / study_note</u>

**Managed by study_db.py**

* Study trails, their concepts (mastery: new / practicing / confident / revisit) and saved notes
* A successful `.QUIZ` on the same topic advances the matching trail

### <u>workspace_task / workspace_checkpoint</u>

**Managed by workspace_db.py**

* The current task for the session
* The checkpoint (goal, decisions, open questions, next step) — written only when you save it

---

## <u>Notes 📝</u>

* Voice input records a short audio sample before transcription (5s in the terminal, 5s via the browser mic button, stop-able early).
* Private profiles are protected with a password (at least 4 characters); the API-key password (6 characters, hashed) is a separate, app-wide credential stored in `user_data.api_password_hash`.
* Deactivated profiles require an activation code before reuse.
* If cloud providers become unavailable, Solaris automatically falls back to Ollama (when configured). Every reply carries a **privacy pulse** naming the provider/model that actually answered (local, cloud, hybrid or unknown), with notes explaining any fallback.
* Attachments never persist beyond the session — use `.BETTER`, `.VISION`, or normal chat to work with them while they last.
* The web interface binds to `127.0.0.1` only; it is not reachable from other machines.

---

## <u>Future Improvements 🚀</u>

* Additional local model support
* Richer long-term memory retrieval
* Smarter preference learning
* Plugin and tool integration
* Streaming token output in the web chat
* Expanded desktop automation capabilities


## <u> P.S. </u>

Solaris serves as the core AI engine behind another project called Stellar.

Stellar currently integrates Solaris v1.0.0 as its conversational backend. From Solaris v1.0.1 onward, both projects are developed and maintained independently. Future updates to Solaris may not be reflected in Stellar unless they are explicitly integrated.

---

© 2026 Shivansh Singh
Solaris is licensed under the MIT License.
See the LICENSE file for details.
