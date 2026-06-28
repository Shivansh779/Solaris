import os
from openai import OpenAI
from dotenv import load_dotenv
import ollama
from datetime import datetime

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
        chatbot.system_log("AI", "INFO", "Long-term session summarization completed with OpenRouter.")
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
