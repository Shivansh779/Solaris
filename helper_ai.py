import os
import sqlite3
from openai import OpenAI
from dotenv import load_dotenv
import ollama
from datetime import datetime
import platform
from textwrap import dedent

def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

load_dotenv()

# Primary Summariser
model = "nvidia/nemotron-3-super-120b-a12b:free"

client_or = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OR_ASSIST_API_KEY"),
)

# If Network is down, or Rate Limits; Ollama
ollama_model = "qwen3:4b"

def build_prompt(name, preference, imp_conv_history, conversation_text, memory_text, question):
    prompt = f"""
    You are a voice assistant.

    Follow these rules:
    1. Always respond in a friendly and helpful manner.
    2. Keep your responses concise and to the point.
    3. Give responses up to maximum 3 sentences.
    4. Try not to use * symbol.
    5. Respond according to the preference given by the User.
    6. Don't Greet the user at every response.
    
    User Name: {name}
    Preference: {preference}
    
    Important Facts from Current Session:
    {imp_conv_history}

    Conversation So Far:
    {conversation_text}
    
    Past Sessions:
    {memory_text}

    User's question: {question}
"""
    return prompt


# Preference summariser
def summarise_pref(user_preference):
    system_log("AI", "INFO", "Starting preference summarization.")

    prompt = f"""
You are a preference extraction system.

Convert the user's message into short AI behavior instructions.

Rules:
- Each instruction must be concise.
- Use imperative style.
- Keep only stable preferences.
- Ignore temporary requests.
- Output only the instructions.
- One instruction per line.
- Do not explain your reasoning.
- Do not add headings or bullet points.

User message:
{user_preference}
"""
    try:
        response = client_or.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        text = response.choices[0].message.content
        system_log("AI", "INFO", "Preference summarization completed with OpenRouter.")
        return text
    except Exception as e:
        system_log("AI", "WARNING", f"Preference summarization failed on OpenRouter; falling back to Ollama: {e}")
        response = ollama.chat(
            model=ollama_model,
            messages=[
                {"role":"user", "content":prompt}
            ]
        )
        text = response['message']['content']
        if "...done thinking" in text:
            text = text.replace("...done thinking", "")
        system_log("AI", "INFO", "Preference summarization completed with Ollama.")
        return text


# Memory Extraction System
def summarise_session (conv_history):
    system_log("AI", "INFO", "Starting long-term session summarization.")
    prompt = f"""
You are a long-term memory extraction system.
Extract only information that would help an AI assistant provide better future responses.
Keep:
- User goals
- Ongoing projects
- Interests
- Skills being learned
- Personal preferences
- Important plans
Discard:
- Greetings
- Casual conversation
- Temporary requests
- One-off questions
- AI responses
Output:
- Short bullet points
- One memory per line
- No explanations

Conversation:
{conv_history}
"""
    try:
        response = client_or.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        text = response.choices[0].message.content
        system_log("AI", "INFO", "Long-term session summarization completed with OpenRouter.")
        return text
    except Exception as e:
        system_log("AI", "WARNING", f"Long-term session summarization failed on OpenRouter; falling back to Ollama: {e}")
        response = ollama.chat(
            model=ollama_model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        text = response['message']['content']
        if "...done thinking" in text:
            text = text.replace("...done thinking", "")
        system_log("AI", "INFO", "Long-term session summarization completed with Ollama.")
        return text


def current_chat_summariser (conv_history):
    system_log("AI", "INFO", "Starting current chat summarization.")
    prompt = f"""
You are an AI whose only task is to create Important Current Session Memory.
Given the conversation, extract only the important facts, decisions, preferences, ongoing tasks, and conclusions that should be remembered for the rest of the current session.
Rules:
* Write concise bullet points.
* Do NOT narrate the conversation.
* Do NOT mention “the user said” or “the assistant replied”.
* Ignore greetings, filler, jokes, and small talk.
* Keep only information that will help another AI continue the conversation with proper context.
* Preserve technical decisions, plans, unresolved questions, and important user preferences.
Output only the bullet points. No headings, explanations, or extra text.

Conversation:
{conv_history}
"""
    try:
        response = client_or.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        text = response.choices[0].message.content
        system_log("AI", "INFO", "Current chat summarization completed with OpenRouter.")
        return text
    except Exception as e:
        system_log("AI", "WARNING", f"Current chat summarization failed on OpenRouter; falling back to Ollama: {e}")
        response = ollama.chat(
            model=ollama_model,
            messages=[
                {"role":"user", "content":prompt}
            ]
        )
        text = response['message']['content']
        if "...done thinking" in text:
            text = text.replace("...done thinking", "")
        system_log("AI", "INFO", "Current chat summarization completed with Ollama.")
        return text

def count_sessions (user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(Session_id) FROM history WHERE user_id = ?;
    """, (user_id,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data[0]

def current_profile_info (user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, is_active, is_private FROM user_data WHERE user_id = ?;
    """, (user_id,))
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data[0], data[1], data[2]

def profiles_data ():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COUNT(user_id) FROM user_data;
    """)
    data1 = cursor.fetchone()
    cursor.execute("""
        SELECT COUNT(user_id) FROM user_data WHERE is_active = 1;
    """)
    data2 = cursor.fetchone()
    cursor.execute("""
        SELECT COUNT(user_id) FROM user_data WHERE is_private = 1;
    """)
    data3 = cursor.fetchone()
    cursor.close()
    conn.close()
    return data1[0], data2[0], data3[0]

def about(user_id, input, output, voice_model):
    if platform.system() == "Darwin":
        system = "macOS"
    elif platform.system() == "Windows":
        system = "Windows"
    else:
        system = "Linux"

    if input == "v":
        input_mode = "Voice"
        input_model = "Faster-Whisper"
    else:
        input_mode = "Text"
        input_model = "N/A"


    if output == "v":
        output_mode = "Voice"
        if voice_model == 1:
            model = "EdgeTTS"
        else:
            model = "KittenTTS"
    else:
        output_mode = "Text"
        model = "N/A"

    profiles, active, private = profiles_data()

    username, status, privacy = current_profile_info(user_id)


    message = dedent(f"""
        ====================================================
                            About - Solaris
        ====================================================      
            Version        : 1.0.1
            Developer      : Shivansh Singh
            Platform       : {system} {platform.release()}
            Languages      : Python {platform.python_version()}, SQLite3 ({sqlite3.sqlite_version}) 
            Architecture   : {platform.machine()}
        
        ----------------------------------------------------
        
        Current Profile    : {username}
        Profile ID         : {user_id}
        Privacy            : {"Private" if privacy == 1 else "Public"}
        Status             : {"Active" if active == 1 else "Inactive"}
        
       Total Sessions      : {count_sessions(user_id)}
       
       -----------------------------------------------------
       
       Primary AI          : Gemini 2.5 Flash
       Fallback Models
       - GPT-OSS-120B
       - Llama 3.3 70B
       - Nemotron 550B
       
       Offline Model       : Qwen3:4B
       
       -----------------------------------------------------
       
       Input Mode          : {input_mode}
       Speech Model        : {input_model}
       
       Output Mode         : {output_mode}
       TTS Model           : {model}
       Available Output Models:
       - EdgeTTS
       - KittenTTS
       
       -----------------------------------------------------
       
       Database            : SQLite3
       
       Profiles            : {profiles}
       Active Profiles     : {active}
       Private Profiles    : {private}
       
       -----------------------------------------------------
       Features

        ✓ Multi-user Profiles
        ✓ Long-term Memory
        ✓ Voice Input
        ✓ Voice Output
        ✓ AI Fallback
        ✓ Session Summaries
        ✓ Preference Learning
       
       -----------------------------------------------------
       Useful Commands
        .HELP
        .CHANGE
        .VOICE
        .RENAME
        .CLEAR
        .ABOUT  
       =====================================================
       Built with curiosity and lots of debugging.
       =====================================================
        """)
    return message
