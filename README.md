# Unified AI Assistant

Unified AI Assistant is a personal desktop assistant designed to combine natural conversation, persistent memory, profile-based personalization, and local system control in one workflow.

The purpose of the program is practical: let one assistant handle dialogue, remember user preferences across sessions, and execute desktop actions without forcing the user to switch between separate tools.

## What It Does

This project supports four main areas:

1. Conversational assistance
   - Answers questions using a multi-provider AI fallback chain.
   - Keeps responses concise and adapted to the active user profile.

2. Voice and text interaction
   - Accepts either typed input or microphone input.
   - Can respond through text or speech.

3. Profile-aware memory
   - Supports multiple user profiles.
   - Allows private profiles with password protection.
   - Stores profile preferences and long-term session summaries in SQLite.

4. Desktop command handling
   - Executes common local actions such as volume, brightness, Wi-Fi, Bluetooth, browser, screen, and gesture commands.
   - Routes explicit desktop requests directly to the matching module instead of sending them to the language model.

## Primary Entry Point

The main runtime is:

- `merged_assistant.py`

This is the integrated assistant that combines chat, memory, profiles, and desktop automation.

## Core Capabilities

### Assistant Behavior

- Gemini as the first chat provider
- OpenRouter as the fallback provider
- Ollama as the local offline fallback
- Preference summarization for each profile
- Session summarization for long-term memory

### Interaction Modes

- Text input
- Voice input using Faster-Whisper
- Text output
- Voice output using Edge-TTS

### Profile Management

- Create new profiles
- Load existing profiles
- Update preferences
- Deactivate and reactivate profiles
- Protect private profiles with a numeric password

### Desktop Automation

Supported command areas include:

- Volume control
- Brightness control
- Wi-Fi control
- Bluetooth control
- Browser opening and search
- Screen text actions
- Keyboard input helpers
- Gesture control
- Instagram messaging via the browser automation module

## Repository Layout

- `merged_assistant.py` - integrated assistant and command router
- `helper_ai.py` - preference and memory summarization
- `main_db.py` - profile storage, privacy, activation, and preference management
- `history_db.py` - long-term memory storage
- `database.db` - SQLite database created at runtime
- `System_Logs.txt` - runtime log file
- `drive-download-20260630T102541Z-3-001/` - desktop automation modules
- `requirements.txt` - Python dependencies
- `chatbot.py`, `index.py`, `test.py` - earlier or auxiliary scripts kept in the repository

The desktop automation bundle contains modules for:

- `volume_control.py`
- `brightness_control.py`
- `wifi_bluetooth.py`
- `browser_automation.py`
- `screen_vision.py`
- `gesture_control.py`

## Requirements

- Python 3.11 or later is recommended
- SQLite support
- Microphone access for voice input
- Speaker or audio output for voice responses
- Optional: Ollama for local fallback execution
- Optional: Gemini API key
- Optional: OpenRouter API keys

## Installation

```bash
git clone <your-repository-url>
cd AI
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root with the required API keys:

```bash
GEMINI_API_KEY="your_gemini_api_key"
OR_API_KEY="your_openrouter_api_key"
OR_ASSIST_API_KEY="your_openrouter_helper_api_key"
```

Notes:

- `GEMINI_API_KEY` is used for primary chat responses.
- `OR_API_KEY` is used for OpenRouter chat fallback.
- `OR_ASSIST_API_KEY` is used by the helper AI that summarizes preferences and session memory.
- If the remote providers are unavailable, the assistant can fall back to Ollama.

## Running The Assistant

```bash
python merged_assistant.py
```

During startup, the assistant will:

1. Initialize the database tables
2. Ask for input mode
3. Ask for output mode
4. Present available profiles
5. Start the session

## Common Commands

### Session and Profile Commands

- `.HELP` - show built-in commands
- `.CHANGE` - switch public profiles during a session
- `bye`, `exit`, `goodbye`, `quit`, `close` - end the session and save memory

### Desktop Commands

- `set volume 50`
- `volume up 10`
- `brightness down 15`
- `turn on wifi`
- `turn off bluetooth`
- `open gmail`
- `open youtube lo-fi music`
- `open example.com`
- `close chrome`
- `click Submit`
- `find text Settings`
- `press enter`
- `type hello world`
- `start gesture control`
- `stop gesture control`
- `gesture status`

### Browser and Search Examples

- `open youtube in chrome`
- `open gmail in safari`
- `google python decorators`
- `search google for best prompt patterns`

## Data And Persistence

The assistant persists:

- Profile definitions
- Privacy and activation state
- Profile preferences
- Session summaries for long-term memory
- Runtime logs

Generated artifacts such as `input.wav`, `output.wav`, and `System_Logs.txt` are runtime files and can be regenerated.

## Design Notes

This project is built around a simple rule:

- If the request is a direct desktop action, handle it locally.
- If the request is conversational, route it through the AI providers.
- If the conversation matters for future use, summarize and store it.

That keeps the assistant responsive while still preserving context across sessions.

## Platform Notes

- Voice features require working audio hardware.
- Some desktop control features are platform dependent.
- Browser automation and gesture control may require extra OS permissions.
- Ollama must be installed and running locally if you want offline fallback behavior.

## Status

This repository is a functional personal assistant project with an emphasis on:

- personal productivity
- profile-based memory
- local desktop control
- model fallback resilience
