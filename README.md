# <u>Solaris – Personal AI Chatbot</u>


![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini-4285F4)
![OpenRouter](https://img.shields.io/badge/Fallback-OpenRouter-orange)
![Ollama](https://img.shields.io/badge/Offline-Ollama-black)
![Voice](https://img.shields.io/badge/Voice-Supported-success)
![Memory](https://img.shields.io/badge/Memory-Persistent-blueviolet)
![Status](https://img.shields.io/badge/Status-Active%20Development-blue)


A local, profile-aware AI chatbot with persistent memory, multiple LLM fallbacks, voice support, and SQLite-backed long-term context.

Solaris is designed to maintain personalized conversations across sessions by combining conversation history, summarized memories, and user preferences. It supports multiple user profiles, private accounts, and graceful fallback between different AI providers.

---

## <u> Features ✨ </u>

* 💬 Text and voice input
* 🔊 Text and voice output
* 👤 Multiple user profiles
* 🔒 Password-protected private profiles
* 🧠 Long-term memory using SQLite
* 📝 Automatic session summarization
* ⚙️ User preference learning
* 🔄 Multi-provider AI fallback
* 💾 Local-first architecture

---

## <u> Project Structure 🧱 </u>

|File	|Purpose|
|---|---|
|chatbot.py	|Main assistant with chat, profiles, memory and voice support
|helper_ai.py	|Preference extraction and session summarization
|main_db.py	|Profile management and user database
|history_db.py	|Long-term conversation history storage
|merged_assistant.py	|Extended assistant with desktop automation support
|requirements.txt	|Project dependencies

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

---

### <u> Profiles 👤 </u>

At startup, Solaris allows you to:

* Create new profiles
* Open existing profiles
* Update profile preferences
* Activate or deactivate profiles
* Secure private profiles with a numeric password

---

### <u> Chat Modes 🎙️ </u>

Choose your preferred interaction style:

**Input**

* Text
* Voice

**Output**

* Text
* Speech

You can also switch between supported text-to-speech backends during runtime.

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

## <u>Requirements 📌</u>

* Python 3.11+
* SQLite
* Microphone (for voice input)
* Audio output device (for speech)
* Ollama (optional, for offline fallback)
* Gemini API Key (optional)
* OpenRouter API Key (optional)

---

## <u>Installation 🛠️</u>

Install the required dependencies:

```bash
pip install -r requirements.txt
```
---

Environment Variables

Create a .env file in the project root.

```bash
GEMINI_API_KEY="your_gemini_api_key"
OR_API_KEY="your_openrouter_api_key"
OR_ASSIST_API_KEY="your_openrouter_helper_api_key"
```

<u>API Usage 🔐</u>

|Variable |	Purpose |
|---|---|
|GEMINI_API_KEY	|Primary Gemini chat requests
|OR_API_KEY	| OpenRouter fallback chat
|OR_ASSIST_API_KEY	| Preference and memory summarization

---

## <u>Running the Assistant ▶️</u>

Start the standard assistant:

python chatbot.py

The assistant will:

1. Initialize the database
2. Select input mode
3. Select output mode
4. Open or create a user profile
5. Begin the conversation

---

## <u>Built-In Commands ⌨️</u>

| Command | Description|
| --- | --- |
|.HELP	| Display available commands
|.CHANGE	|Switch to another public profile
|.VOICE	|Change the speech backend
|exit, quit, bye, goodbye, close	|Save the session summary and exit

---

## <u>Runtime Files 💾</u>

The following files are generated while Solaris is running:

| File	| Purpose |
|---| --- |
|database.db	|SQLite database
|System_Logs.txt	|Application logs
|input.wav |	Recorded voice input
|output.wav	| Generated speech output

---

## <u>Database Design 🗂️</u>

The assistant separates user information from conversational memory.

### <u>user_data</u>

**Managed by main_db.py**

Stores:

* User profiles
* Passwords
* Privacy settings
* Activation state

### <u>history</u>

**Managed by history_db.py**

Stores:

* Session summaries
* Long-term memory
* Associated user_id

Separating these tables keeps profile management independent from conversational memory while maintaining their relationship through the user ID.

---
## <u>Notes 📝</u>

* Voice input records a short audio sample before transcription.
* Private profiles are protected using a numeric password.
* Deactivated profiles require an activation code before reuse.
* If cloud providers become unavailable, Solaris automatically falls back to Ollama (when configured).

---

## <u>Future Improvements 🚀</u>

* Additional local model support
* Richer long-term memory retrieval
* Smarter preference learning
* Plugin and tool integration
* Expanded desktop automation capabilities


## <u> P.S. </u>

Solaris serves as the core AI engine behind another project called Stellar.

Stellar currently integrates Solaris v1 as its conversational backend. From Solaris v2.0 onward, both projects are developed and maintained independently. Future updates to Solaris may not be reflected in Stellar unless they are explicitly integrated.
