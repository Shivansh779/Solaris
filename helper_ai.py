import sqlite3
from dotenv import load_dotenv
import ollama
from datetime import datetime
import platform
from textwrap import dedent
import json

import config

def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

load_dotenv()

with open("config.json", "r") as f:
    models = json.load(f)

with open("settings.json", "r") as file:
    settings = json.load(file)

# Primary Summariser
model = models["or_assist"]

client_or = config.init_assist_or()

# If Network is down, or Rate Limits; Ollama
ollama_model = models['local']

# Prompt Builder
def build_prompt(name, preference, imp_conv_history, conversation_text, memory_text, question, about_user):
    prompt = f"""
    You are a personal assistant.

    Follow these rules:
    1. Always respond in a friendly and helpful manner.
    2. Keep your responses concise and to the point.
    3. Give responses up to maximum {settings["response"]["maximum_length"]} sentences.
    4. Try not to use * symbol.
    5. Respond according to the preference given by the User.
    6. Don't Greet the user at every response.
    7. Emoji Density: {settings['response']['emoji_density']}
    
    User Name: {name}
    Preference: {preference}

    Be {settings['personality']['warmth'].title()} and {settings['personality']['humor'].title()}
    
    Important Facts from Current Session:
    {imp_conv_history}

    Conversation So Far:
    {conversation_text}
    
    Past Sessions:
    {memory_text}
    
    About the User:
    {about_user}

    User's question: {question}
"""
    return prompt

# Coder Prompt Builder
def build_coding_prompt(prompt):
    return f"""You are Solaris' coding specialist. Help with writing code snippets, reviewing code, debugging errors, and improving existing code.

## Instructions
- Understand the user's intent before changing code.
- Prefer simple, practical solutions.
- Don't rewrite working code without a reason.
- When debugging, identify the cause before giving the fix.
- Explain important changes briefly.
- Don't invent API, library, or language behaviour.
- If multiple approaches exist, recommend the most suitable one and briefly mention meaningful trade-offs.
- Ask for missing context when it is necessary to give an accurate answer.

## Output
Adapt the format to the task. Generally:
- **Problem / Observation**
- **Solution / Improved Code**
- **Why / Explanation**

For simple requests, keep the response concise and provide the code directly.

User's request: {prompt}
"""

# Writing Prompt Builder
def build_writing_prompt(prompt):
    return f"""
You are Solaris' writing specialist. Help with drafting, rewriting, editing, summarizing, and improving written content.

## Instructions
- Understand the purpose, audience, and intended tone before writing.
- Preserve the user's meaning and intent unless asked to change it.
- Improve clarity, structure, grammar, and flow without unnecessarily changing the writing.
- Match the requested tone and level of formality.
- Don't add unsupported facts or ideas.
- When editing, clearly preserve what already works and change only what needs improvement.
- Ask for missing context when it is necessary.

## Output
Adapt the format to the task. Generally:
- **Draft / Revised Version**
- **Notes / Explanation** when useful

For simple requests, provide the finished writing directly.

User's request: {prompt}
"""

# Strategist Prompt Builder
def build_strategist_prompt(prompt, answers, ai_questions, previous_draft=None):
    comparison = ""
    if previous_draft:
        comparison = f"""

A previous strategist draft exists. Critically evaluate it and produce a revised design that improves, challenges, or replaces its decisions where appropriate. Do not simply repeat the same approach without adding value.

Previous Draft:
{previous_draft}
"""
    return f"""
    You are Solaris' Strategist. Turn the user's defined goal and collected answers into a clear, detailed, and practical PRD or Design Draft.

## Instructions

- Understand the goal and all provided answers before designing.
- Base decisions on the information provided; clearly identify assumptions where information is missing.
- Turn requirements into a coherent design rather than merely restating them.
- Explain important design decisions and meaningful trade-offs.
- Prefer simple, practical, and appropriately scoped solutions.
- Consider components, workflows, dependencies, edge cases, and implementation considerations where relevant.
- Keep the design internally consistent.
- Do not introduce unnecessary complexity.
- When given another strategist's draft, critically evaluate it and improve, challenge, or replace its decisions where appropriate. Avoid repeating the same approach without adding value.

## Output
Adapt the structure to the task. Generally include:

### Goal
...

### Requirements
...

### Proposed Design
...

### Components / Structure
...

### Workflow
...

### Implementation Plan
...

### Decisions & Trade-offs
...

### Open Questions / Assumptions
...

The result should be detailed enough to act as a blueprint for implementation while remaining practical and readable.

User's Question: {prompt}

Questions asked to user for details: {ai_questions}

Answer's Provided by the user to questions provided: {answers}
{comparison}
"""

# Questionaire Prompt
def questions (prompt):
    return f"""
You are the planning-question stage of Solaris' Strategist mode. Your job is to understand the user's goal deeply enough for another model to create a strong PRD or Design Draft.

## Instructions
- Read the user's goal carefully before asking anything.
- For the next response ask the most important questions needed to understand the goal, requirements, constraints, preferences, and intended outcome.
- Ask a maximum of 10 questions.
- Make questions specific and non-redundant.
- Prioritize questions whose answers could materially change the eventual design.
- Do not ask questions that can reasonably be inferred from the user's goal.
- Do not design the solution, write the PRD, or prematurely recommend an implementation.
- Ask all questions in one response so the user can answer them together.
- If the goal is already sufficiently clear, ask fewer questions rather than forcing 10.
- Choose the best answer for questions with N/A as answers by the User.

## Output

### Questions
1. ...
2. ...
3. ...

Keep the questions concise and easy to answer.

User's Request: {prompt}
"""

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
- Any command starting with "." in capital letters.
Output:
- Short bullet points
- One memory per line
- No explanations

You may return a blank session or N/A if necessary.

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

    fallback_models = [_ for _ in models['openrouter']]
    str_fallback_models = ''
    for fallback_model in fallback_models[:-1]:
        str_fallback_models = str_fallback_models +str(fallback_model) + "\n"


    message = dedent(f"""
==========================================================================
                    About - Solaris
==========================================================================
    Version        : 1.0.1
    Developer      : Shivansh Singh
    Platform       : {system} {platform.release()}
    Languages      : Python {platform.python_version()}, SQLite3 ({sqlite3.sqlite_version}) 
    Architecture   : {platform.machine()}

--------------------------------------------------------------------------

Current Profile    : {username}
Profile ID         : {user_id}
Privacy            : {"Private" if privacy == 1 else "Public"}
Status             : {"Active" if active == 1 else "Inactive"}

Total Sessions      : {count_sessions(user_id)}

--------------------------------------------------------------------------

Primary AI          : Gemini 2.5 Flash
Fallback Models ↴
{str_fallback_models.title()}

Offline Model       : {ollama_model}

--------------------------------------------------------------------------

Input Mode          : {input_mode}
Speech Model        : {input_model}

Output Mode         : {output_mode}
TTS Model           : {model}
Available Output Models:
- EdgeTTS
- KittenTTS

--------------------------------------------------------------------------

Database            : SQLite3

Profiles            : {profiles}
Active Profiles     : {active}
Private Profiles    : {private}

--------------------------------------------------------------------------
Features

✓ Multi-user Profiles
✓ Long-term Memory
✓ Voice Input
✓ Voice Output
✓ AI Fallback
✓ Session Summaries
✓ Preference Learning

--------------------------------------------------------------------------
Useful Commands
.HELP
.CHANGE
.VOICE
.RENAME
.CLEAR
.ABOUT  
==========================================================================
Built with curiosity and lots of debugging.
==========================================================================
        """)
    return message

def summarise_about(about_user):
    system_log("AI", "INFO", "Starting summarization of details of the User.")
    prompt = f"""
You are a Summariser of Details of the User.
Extract only information that would help an AI assistant provide better future responses.
Keep:
- Information About User
- Important Factual, constant information (dates and etc.)
Discard:
- Non-Permanent Information
Output:
- Short bullet points
- No explanations
- Try to segregate into four categories, Name, Occupation (Student if they mention class),
    DOB, and Interests (if they provide the last two)
    
Conversation:
{about_user}
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
        system_log("AI", "INFO", "User detail summarization completed with OpenRouter.")
        return text
    except Exception as e:
        system_log("AI", "WARNING",
                   f"Long-term session summarization failed on OpenRouter; falling back to Ollama: {e}")
        response = ollama.chat(
            model=ollama_model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        text = response['message']['content']
        if "...done thinking" in text:
            text = text.replace("...done thinking", "")
        system_log("AI", "INFO", "User detail summarization completed with Ollama.")
        return text
