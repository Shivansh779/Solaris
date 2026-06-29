# Personal Voice AI Assistant

A **desktop voice assistant** with long-term memory, multi-user profiles (including private password-protected ones), and smart fallback between multiple AI models.

Built by a Class 9 student during summer vacation as a Hobby Project.

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)

---

## ✨ Features

### Core Capabilities
- **Voice & Text Support** — Speak to it or type (you can mix both)
- **Natural Indian English Voice** — Uses Edge-TTS (NeerjaNeural)
- **Long-term Memory** — Remembers your projects, goals, and preferences across days and weeks
- **Smart Session Summarization** — Automatically saves important memories after each chat

### User Management (Netflix Style)
- Multiple user profiles
- **Public Profiles**
- **Private Profiles** with numeric password protection
- Mid-session profile switching using `.CHANGE`
- Update preferences anytime using `ID.update`

### Reliability
- Primary: Gemini
- Backup: OpenRouter (multiple strong models)
- Final Fallback: Local Ollama (works offline)
- Graceful error handling

### Commands
- `.CHANGE` — Switch to another profile mid-conversation
- `.HELP` — Show available commands
- `bye` / `exit` / `goodbye` — End session and save memory

---

## 🛠️ Tech Stack

- **Language**: Python
- **AI Models**: Gemini, OpenRouter, Ollama
- **Speech**: Faster-Whisper (STT), Edge-TTS (TTS)
- **Database**: SQLite3 (with proper relational design)
- **Others**: Sounddevice, playsound3, dotenv

---

## 📁 Project Structure
Chatbot

- **chatbot.py**: Main chatbot file
- **helper_ai.py**: AI summarization (Preferences and Memories)
- **main_db.py**: User Profile + Privacy Logic and Preference Extraction
- **history.db**: Long-Term Memory 
- **database.db**: SQLite-based Database (auto-created)
- **.env**: API Keys (Created By the User)
- **input.wav and output.wav**: Temporary Audio Files (auto-created)
- **requirements.txt**: Required packages/dependencies to Install to run the program
- **System_Logs.txt**: Used by developer while Debugging; Not Essential for the User (auto-created)

---

## 🚀 Installation & Setup

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd chatbot

2. Install dependencies:
   ```bash
   pip install -r requirements.txt

3. Set up API keys in .env file:

   Kindly write the following in your .env file; (ignore the comments)
   ```bash
   GEMINI_API_KEY="your_api_key"
   OR_API_KEY="your_openrouter_api_key"
   OR_ASSIST_API_KEY="your_secondary_openrouter_api_key" # Used by the Helper AI
   
4. Install Ollama + qwen3:4b (optional but recommended for offline fallback)
5. Run the assistant:
   ```bash
   python3 chatbot.py
   
   OR
   
   python chatbot.py
   
---

## 📝 How to Use
1. Initiate ollama by running:
      ```bash
   ollama run qwen3:4b
2. Run the program
3. Choose Voice/Text mode
4. Select or create a profile
5. Start chatting!
6. Type .CHANGE anytime to switch profiles
7. Say "bye" to end the session

---
## 🎯 What Makes This Special
This isn't just another ChatGPT wrapper.
I designed and built:

- A full user system with public + private profiles
- Hybrid short-term + long-term memory architecture
- AI-powered preference summarization
- Resilient multi-AI fallback system
- Clean modular architecture

All while learning SQL, system design, and proper code organization.

---
## Future Improvements (TODO)
- GUI interface (Tkinter / CustomTkinter)
- Vector embeddings for smarter memory retrieval
- Voice wake word ("Hey Assistant")
- Better error recovery
- Export chat history

### Made with curiosity and lots of debugging! 🥀🚀