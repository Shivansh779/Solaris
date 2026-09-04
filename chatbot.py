import platform
import random
import textwrap
import shutil
from dotenv import load_dotenv
import os
import sounddevice as sd
import soundfile as sf
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
import asyncio
import edge_tts
from kittentts import KittenTTS
from playsound3 import playsound
from datetime import datetime
import ollama
import time
import sys
from textwrap import dedent
import json
import subprocess
from spinner import Spinner, RecordingTimer
import config

import main_db
import history_db
import specialist_ai
import study_ai
import tui_utils

# Logging Function Definition
def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

# Current Time Function
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Create the tables for the Database
main_db.create_table()
history_db.enable_foreign_key()
history_db.create_table()
system_log("SYSTEM", "INFO", "Application database tables initialized.")

import helper_ai

session_start_time = current_time()

conv_history = []
session_history = []
memories = []

fs = 16000 # sample rate, (fps of audio)
seconds=5

with open("config.json", "r") as f:
    models = json.load(f)

# Gemini Set-Up
client_gem = config.init_gemini()

MODEL = models["gemini"].lower()

# Ollama Local
LOCAL_MODEl = models["local"].split("/")[1].lower()

# OpenRouter Set-up
client_or = config.init_openrouter()

MODELS = [model.lower() for model in models["openrouter"]]

# Ollama Cloud
client_ollama = config.init_ollama_cloud()

# groq
client_groq = config.init_groq()

# NVIDIA NIM
client_nvidia = config.init_nvidia()

# TODO: Dictionary mapping for client

# EdgeTTS
async def main(response):
    text = response if isinstance(response, str) else response.text
    communicate = edge_tts.Communicate(text, "en-IN-NeerjaNeural")
    await communicate.save("output.wav")

# KittenTTS
kitten_model = None

if platform.system() == "Windows":
    subprocess.run(["cls"], shell=True)
else:
    if platform.system() == "Linux" or platform.system() == "Darwin":
        subprocess.run(["clear"])
    else:
        print("\n" * 100)

voice_text = input("Voice (Enter V)\nText (Enter T) \nInput -> ").strip().lower()
print("You have chosen: " + ("Voice" if voice_text == 'v' else "Text") + " for yourself.")

if voice_text == 'v':
    whisper_model = WhisperModel("small")
    system_log("SYSTEM", "INFO", "Voice input mode selected.")
else:
    system_log("SYSTEM", "INFO", "Text input mode selected.")

ai_voice_text = input("\nVoice (Enter V)\nText (Enter T) \nOutput -> ").strip().lower()
print("You have chosen: " + ("Voice" if ai_voice_text == 'v' else "Text") + " for the AI.\n")
system_log("SYSTEM", "INFO", "AI output mode selected.")
pref = None
if ai_voice_text == 'v':
    print("Options for Text-to-Speech Model" + "─"*36 + "\n1. EdgeTTS (Requires Internet, Indian Accent)\n2. KittenTTS (Offline, British Accent)")
    pref = int(input("Enter which Text-to-Speech Model you want to use: "))

    if pref > 2 or pref < 1:
        print("Invalid choice. Restart Program!")
        sys.exit(0)

print("""╭──────────────────────────────╮
│       Solaris Profiles       │
╰──────────────────────────────╯

Profiles
""")

for user in main_db.check_existing():
    if user[2] == 1 and user[3] == 0:
        print(f"{user[0]}: {user[1]} (Private & Inactive)")
    elif user[2] == 1:
        print(f"{user[0]}: {user[1]} (Private)")
    elif user[3] == 0:
        print(f"{user[0]}: {user[1]} (Inactive)")
    else:
        print(f"{user[0]}: {user[1]}")

existing = input("""
Commands

N               New Profile
<ID>.update     Update
<ID>.rename     Rename
<ID>.activate   Activate
<ID>.deactivate Deactivate
/exit           Exit

Profile -> """
).strip().lower()

existing = existing.split(".")

if not existing[0]:
    print("Please enter a valid option.")
    sys.exit()

current_user_id = None

# Exitting the Application
if "/exit" in existing:
    system_log("SYSTEM", "INFO", "Application exited from profile selection.")
    print("Goodbye! Have a Great Day!")
    sys.exit()

# New Profile
elif existing[0] in ['n', 'no', 'nope', 'nah', 'nahh', 'negative']:
    name = input("Enter your name: ")
    preference = input("Enter a description of how you want the AI to behave: ")
    about_user = input("Tell Solaris about yourself (prefer to keep it in 50 words): ")
    privacy_setting = input("Do you want it to be a Private Profile? (Y/N) ")
    if privacy_setting == "Y"  or privacy_setting == "y":
        is_private = 1
        print("Your Profile is Private.")
    else:
        is_private = 0
        print("Your Profile is Public")
    processed_pref = helper_ai.summarise_pref(preference)
    processed_about = helper_ai.summarise_about(about_user)
    current_user_id = main_db.new_user(name, processed_pref, is_private, processed_about)
    system_log("PROFILE", "INFO", f"Created new profile with user_id={current_user_id}.")
    preference = processed_pref
    about_user = processed_about
    if is_private == 1:
        print(f"Your Profile Password: {main_db.fetch_password(current_user_id)}\nKindly Save your Password to access your profile in future!")

# Private Profiles
elif (len(existing) < 2 and main_db.fetch_privacy_setting(existing[0]) == 1
      and main_db.fetch_status(existing[0]) == 1):
    system_log("PROFILE", "INFO", f"Private profile login requested for user_id={existing[0]}.")
    password = main_db.fetch_password(existing[0])
    attempts = 3
    while attempts > 0:
        user_password = input("Enter your password: ")
        if user_password == password:
            print("Acces Granted!")
            system_log("PROFILE", "INFO", f"Private profile access granted for user_id={existing[0]}.")
            data = main_db.get_data(existing[0])
            preference = data[0]
            name = data[1]
            about_user = data[2]
            current_user_id = int(existing[0])
            break
        else:
            attempts -= 1
            system_log("PROFILE", "WARNING", f"Invalid private profile password attempt for user_id={existing[0]}.")
            print("Invalid password Try Again!")
    else:
        system_log("PROFILE", "ERROR", f"Private profile access failed after maximum attempts for user_id={existing[0]}.")
        print("Too many attempts failed!\nRestarting Application...")
        sys.exit()

elif (len(existing) > 1 and existing[1] == "update" and main_db.fetch_privacy_setting(existing[0]) == 1
      and main_db.fetch_status(existing[0]) == 1):
    system_log("PROFILE", "INFO", f"Private profile update requested for user_id={existing[0]}.")
    password = main_db.fetch_password(existing[0])
    attempts = 3
    while attempts > 0:
        user_password = input("Enter your password: ")
        if user_password == password:
            print("Acces Granted!")
            system_log("PROFILE", "INFO", f"Private profile update access granted for user_id={existing[0]}.")
            print("Updating Private Profile!")
            preference = input("Enter the new description of how you want the AI to behave: ")
            processed_pref = helper_ai.summarise_pref(preference)
            main_db.update_user_pref(int(existing[0]), processed_pref)
            system_log("PROFILE", "INFO", f"Private profile preferences updated for user_id={existing[0]}.")
            preference = processed_pref
            current_user_id = int(existing[0])
            data = main_db.get_data(existing[0])
            preference = data[0]
            name = data[1]
            about_user = data[2]
            current_user_id = int(existing[0])
            break
        else:
            attempts -= 1
            system_log("PROFILE", "WARNING", f"Invalid password attempt during private profile update for user_id={existing[0]}.")
            print(f"Invalid password!\n\nAttempts Remaining: {attempts}")
    else:
        system_log("PROFILE", "ERROR", f"Private profile update failed after maximum attempts for user_id={existing[0]}.")
        print("Too many attempts failed!\nRestarting Application...")
        sys.exit()

# Public Profiles
elif len(existing) > 1 and existing[1] == "update" and main_db.fetch_status(existing[0]) == 1:
    system_log("PROFILE", "INFO", f"Public profile update requested for user_id={existing[0]}.")
    choice = int(input("\n\n1. Update Preferences\n2. Update the Description About Yourself\nEnter Choice: "))
    if choice == 1:
        current_pref = main_db.get_data(existing[0])[0]
        print("Current Preference\n" + str(current_pref))
        preference = input("Enter the new description of how you want the AI to behave: ")
        processed_pref = helper_ai.summarise_pref(preference)
        main_db.update_user_pref(int(existing[0]), processed_pref)
        system_log("PROFILE", "INFO", f"Public profile preferences updated for user_id={existing[0]}.")
    elif choice == 2:
        current_about = main_db.get_data(existing[0])[2]
        print("Current About Yourself:\n" + str(current_about))
        about_user = input("Tell Solaris About ourself in 50 words: ")
        processed_about = helper_ai.summarise_pref(about_user)
        main_db.update_about_user(processed_about, existing[0])
        system_log("PROFILE", "INFO", f"Public profile about user_id={existing[0]} has been updated.")

    current_user_id = int(existing[0])
    data = main_db.get_data(current_user_id)
    name = data[1]
    preference = data[0]
    about_user = data[2]

elif len(existing) < 2 and main_db.fetch_status(existing[0]) == 1:
    try:
        existing = int(existing[0])
        data = main_db.get_data(existing)
        preference = data[0]
        name = data[1]
        about_user = data[2]
        current_user_id = existing
        system_log("PROFILE", "INFO", f"Profile selected with user_id={current_user_id}.")
    except Exception as e:
        system_log("PROFILE", "ERROR", f"Invalid profile selection failed: {e}")
        print("Invalid profile ID")
        sys.exit()

# Profile Deactivation
elif len(existing) > 1 and existing[1] == "deactivate" and main_db.fetch_status(existing[0]) == 1:
    user_id = int(existing[0])
    system_log("PROFILE", "INFO", f"Profile deactivation requested for user_id={user_id}.")
    message = """==========================
Deactivate Profile
==========================
This profile will become inactive.
• It will no longer be usable until activated.
• Your memories and preferences will be preserved.
• An unique Activation Code will be generated, every time the profile is deactivated.
• The previous Activation Code (if any) will become invalid.

Note:
If you plan to continue using this profile regularly,
consider making it Private instead. A private profile
uses a short PIN, while an inactive profile requires a
new Activation Code every time it is deactivated.

Do you wish to deactiate the profile? (Y/N) """
    confirmation = input(message)
    if confirmation == "Y" or confirmation == "y":
        print("Deactivating Profile...")
        activation_code = main_db.deactivate_user(user_id)
        system_log("PROFILE", "INFO", f"Profile deactivated for user_id={user_id}.")
        print("Profile Deactivated!")
        print(f"Your Activation Code: {activation_code}\nKindly Save it to later activate your profile.")
        print("Kindly restart the application!")
        sys.exit()
    else:
        system_log("PROFILE", "INFO", f"Profile deactivation cancelled for user_id={user_id}.")
        print("Your Profile has not been activated! Kindly Restart the application!")

# Profile Activation
elif len(existing) > 1 and existing[1] == "activate" and main_db.fetch_status(existing[0]) == 0:
    user_id = int(existing[0])
    system_log("PROFILE", "INFO", f"Profile activation requested for user_id={user_id}.")
    print("This profile is inactive.\n\nEnter the activation code to continue.")
    stored_code = main_db.fetch_activation_code(existing[0])
    attempts = 3
    while attempts > 0:
        code = input("Enter (in XXXXX-XXXXX format): ")
        if code == stored_code:
            print("Activating Profile...")
            main_db.activate_user(user_id)
            system_log("PROFILE", "INFO", f"Profile activated for user_id={user_id}.")
            print("Profile Activated!")
            print("Kindly restart the application!")
            sys.exit()
        else:
            attempts -= 1
            system_log("PROFILE", "WARNING", f"Invalid activation code attempt for user_id={user_id}.")
            print(f"Invalid Activation Code!\n\nAttempts Remaining: {attempts}")
    else:
        system_log("PROFILE", "ERROR", f"Profile activation failed after maximum attempts for user_id={user_id}.")
        print("Too Many Attempts! Restart Application to try again!")
        sys.exit()
    sys.exit()

# Rename a Profile
elif len(existing) > 1 and existing[1] == "rename":
    new_name = input("Enter new name: ")
    system_log("PROFILE", "INFO", f"Profile rename requested for user_id={existing[0]}. New Name: {new_name}.")
    main_db.rename_user(existing[0], new_name)
    print("Profile Rename! Restart Application to see changes.")
    sys.exit()

else:
    system_log("SYSTEM", "WARNING", "Invalid profile menu option selected.")
    print("Invalid Option Selected!")
    print("Retry!")
    sys.exit()

# Important Function Definitions
def ai_voice_manager(pref, response):
    if pref == 1:
        try:
            asyncio.run(main(response))
            system_log("SYSTEM", "INFO", "EdgeTTS selected.")
        except Exception as e:
            system_log("SYSTEM", "ERROR", f"Error in EdgeTTS. {e}\nSwitched to KittenTTS!")
            kitten_tts(response=response)
    elif pref == 2:
        kitten_tts(response=response)
        system_log("SYSTEM", "INFO", "KittenTTS selected.")

def kitten_tts(response, kitten_model=None):
    if kitten_model is None:
        kitten_model = KittenTTS("KittenML/kitten-tts-mini-0.8")
    audio = kitten_model.generate(
    text=response,
    voice="Jasper",
    speed=1.2,
)
    sf.write("output.wav", audio, 24000)

def change_user_id(user_id):
    global current_user_id, memories, name, preference
    data = main_db.get_data(user_id)
    memories = history_db.access_history(user_id)
    name = data[1]
    preference = data[0]
    current_user_id = user_id
    system_log("PROFILE", "INFO", f"Changed active profile to user_id={user_id}.")

def ask_ai(prompt, spinner, models=None):
    if models is None:
        models = MODELS
    spinner.start()
    try:
        system_log("AI", "INFO", "Sending request to Gemini model.")
        answer = ask_gemini(prompt)
    except Exception as e:
        system_log("AI", "WARNING", f"Gemini request failed, falling back to OpenRouter: {e}")
        spinner.update_message("Reasoning... ⚠️ Cloud models unavailable.")
        answer = ask_openrouter(prompt, spinner, models)
    finally:
        spinner.stop()

    return answer

def ask_gemini(prompt, model=MODEL):
    system_log("AI", "INFO", f"Using Gemini model: {model}.")
    response = client_gem.models.generate_content(
        model=model,
        contents=prompt
    )
    return response.text

def ask_openrouter(prompt, spinner, models):
    for model in models:
        try:
            system_log("AI", "INFO", f"Using OpenRouter model: {model}.")
            response = client_or.chat.completions.create(
                model=model,
                messages=[
                    {"role" : "user", "content" : prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            system_log("AI", "WARNING", f"OpenRouter model failed: {model}. Error: {e}")
            spinner.update_message(f"Cloud model unavailable: {model} ⚠️")
            time.sleep(0.7)

    spinner.update_message("Switching to Local AI...")
    response = ask_ollama(prompt, LOCAL_MODEl)
    return response

def ask_ollama(prompt, model):
    system_log("AI", "INFO", f"Using Ollama model: {model}")
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    text = response['message']['content']
    return text


# Response Commands
def show_help():
    tui_utils.display_inline("\n[bold bright_cyan]Available Commands[/]\n")
    tui_utils.display_inline("─" * shutil.get_terminal_size().columns + "\n")
    tui_utils.display_inline("\n[bold]General Commands:[/]")
    tui_utils.display_inline("")
    tui_utils.display_inline("  .CHANGE                - To Change Profiles")
    tui_utils.display_inline("  .BETTER                - Get a better answer for a request.")
    tui_utils.display_inline("  .VOICE                 - To Change the Text-To-Speech model")
    tui_utils.display_inline("  .ABOUT                 - See about the Profile and the AI Chatbot.")
    tui_utils.display_inline("  .UPDATE_PRIVACY        - To Update Privacy Settings")
    tui_utils.display_inline("  .CLEAR                 - Clears the terminal. Context is preserved.")
    tui_utils.display_inline("  .WEB <question>        - Search the web for real-time information.")
    tui_utils.display_inline("")
    tui_utils.display_inline("\n[bold]Study Commands:[/]")
    tui_utils.display_inline("")
    tui_utils.display_inline("  .DETAIL <topic>        - Explain a concept like a teacher.")
    tui_utils.display_inline("  .SIMPLE <topic>        - Explain a concept in simple language.")
    tui_utils.display_inline("  .QUIZ <topic>          - Generate a 10-question quiz with answers.")
    tui_utils.display_inline("  .TIMELINE <topic>      - Show events in chronological order.")
    tui_utils.display_inline("  .COMPARE <topic>       - Compare subjects side by side.")
    tui_utils.display_inline("  .STEPS <topic>         - Show a series of steps with explanations.")
    tui_utils.display_inline("")
    tui_utils.display_inline("  exit/goodbye/bye       - To Exit")
    tui_utils.display_inline("\nNote: Profile management (update, rename, activate, deactivate)")
    tui_utils.display_inline("      is available only at application startup.")
    tui_utils.display_inline("─" * shutil.get_terminal_size().columns + "\n")

def show_about():
    print(helper_ai.about(current_user_id, voice_text, ai_voice_text, pref))

def change_profile():
    global conv_history, session_history, imp_conv_history
    temp_list = []
    for user in main_db.check_existing():
        print(f"{user[0]}: {user[1]}")
        temp_list.append(user[0])
    print("Select the profile to switch to!")
    try:
        changed_profile = int(input("Switch to profile: "))
    except ValueError:
        system_log("PROFILE", "WARNING", "Invalid profile switch input (non-numeric).")
        print("Invalid Profile ID!")
        return
    if changed_profile not in temp_list:
        system_log("PROFILE", "WARNING", f"Invalid profile switch target selected: {changed_profile}.")
        print("Invalid Profile ID!")
        return
    elif main_db.fetch_privacy_setting(changed_profile) == 1:
        system_log("PROFILE", "WARNING", f"Blocked mid-session switch to private profile user_id={changed_profile}.")
        print("Profile Number Entered is a Private Profile; Restart Application to Switch to\nthe Profile.")
        return
    change_user_id(changed_profile)
    conv_history.clear()
    session_history.clear()
    imp_conv_history.clear()
    print("Changing Profile...")
    time.sleep(1.0)
    print("Profile Changed!")
    print("=" * 50 + "\n")

def change_voice():
    global pref
    print("1. EdgeTTS (Requires Internet, Indian Accent)\n2.KittenTTS (Offline, British Accent)")
    try:
        pref = int(input("Enter Your Preferred Text-To-Speech Model: "))
    except ValueError:
        print("Invalid Choice!")
        return
    if pref > 2 or pref < 1:
        print("Invalid Choice!")
    else:
        if pref == 1:
            system_log("VOICE", "INFO", "Text-To-Speech Model changed. Model: EdgeTTs")
        else:
            system_log("VOICE", "INFO", "Text-To-Speech Model changed. Model: KittenTTS")

def update_privacy():
    print(f"Current Privacy Setting: {"Public" if main_db.fetch_privacy_setting(current_user_id) == 0 else "Private"}")
    preference = input(f"Switch Privacy Setting to {"Public" if main_db.fetch_privacy_setting(current_user_id) == 1 else "Private"}? "
          f"(Y/N) ")
    if preference in ["Y", "y"]:
        if main_db.fetch_privacy_setting(current_user_id) == 1:
            attempts = 3
            while attempts > 0:
                password = input("Enter Password to change Privacy Settings: ")
                if password == main_db.fetch_password(current_user_id):
                    main_db.update_privacy(current_user_id,  0)
                    break
                else:
                    attempts -= 1
                    print(f"Invalid Password. Remaining Attempts: {attempts}")
        else:
            main_db.update_privacy(current_user_id, 1)
            print("Privacy Settings Changed!")
            print(f"Your Password is {main_db.fetch_password(current_user_id)}")
    
    elif preference in ['N', 'n']:
        print("Private Settings Remain Unchanged")
    else:
        print("Invalid Choice")

def clear():
    print("Clearing terminal window...")
    time.sleep(1)
    if platform.system() == "Windows":
        subprocess.run("cls", shell=True)
    else:
        if os.getenv("TERM"):
            subprocess.run(["clear"])
        else:
            print("\n" * 100)
    print(dedent("""
        ────────────────────────────────────────────────────
                            Solaris
        ────────────────────────────────────────────────────
        
        Screen cleared.
        Conversation context is still active.
        
        Type .HELP for commands.
        ╰───────────────────────────────────────────────────
        """))

def handle_web(question=""):
    print("Upcoming~")
    if question:
        system_log("COMMAND", "INFO", f"Web search requested: {question[:50]}...")

def specialist_spinner():
    return Spinner(random.choice([
        "Consulting the specialist...",
        "Fetching expert insight...",
        "Summoning domain knowledge...",
        "Analyzing with precision...",
        "Crafting specialist response..."
    ]))

def better(question="", clien=None, answers=""):
    tui_utils.display_table(
        ["#", "Specialist", "Expertise"],
        [
            ("1", "✍️  The Writer", "Writing, essays, creative content"),
            ("2", "💻 The Programmer", "Coding, debugging, software design"),
            ("3", "🧠 The Strategist", "Reasoning, planning, problem solving"),
        ],
        title="Who do you want to answer?",
    )
    choice = int(tui_utils.prompt_box("Your Option"))

    if choice in (1, 2) and not question:
        question = tui_utils.prompt_box("Your Request", "Describe your request clearly:").strip()
        if not question:
            return "No request provided. Try Again!"

    clients = {
        "openrouter" : client_or,
        "ollama-cloud" : client_ollama,
        "google" : client_gem,
        "nvidia" : client_nvidia,
        "groq" : client_groq
    }

    with open("config.json", "r") as f:
        config = json.load(f)

    match choice:
        case 1:
            p_client = config['specialist']['writing']['primary']['provider']
            s_client = config['specialist']['writing']['secondary']['provider']
            if p_client in clients and s_client in clients:
                with specialist_spinner():
                    response = specialist_ai.writer(question, clients[p_client], clients[s_client])
                tui_utils.display_markdown(response, title="✍️ The Writer")
                return response
        case 2:
            p_client = config['specialist']['coding']['primary']['provider']
            s_client = config['specialist']['coding']['secondary']['provider']
            if p_client in clients and s_client in clients:
                with specialist_spinner():
                    response = specialist_ai.coder(question, clients[p_client], clients[s_client])
                tui_utils.display_markdown(response, title="💻 The Programmer")
                return response
        case 3:
            p_client = config['specialist']['reasoning']['primary']['provider']
            s_client = config['specialist']['reasoning']['secondary']['provider']
            if p_client not in clients or s_client not in clients:
                return "Strategist models unavailable. Check config."
            return strategist_flow(question, clients[p_client], clients[s_client])
        case _:
            return "Invalid Option Selected! Try Again!"

def strategist_flow(goal, p_client, s_client):
    goal = goal.strip()
    if not goal:
        goal = input("Define your goal (structured, one response): ").strip()

    if not goal:
        return "No goal provided. Try again."

    system_log("AI", "INFO", f"Strategist flow started for goal: {goal[:60]}...")

    print("\nSolaris is drafting its questions...")
    with specialist_spinner():
        ai_questions = specialist_ai.questionaire(goal, p_client, s_client)
    tui_utils.display_markdown(ai_questions, title="🤖 Solaris Questions")

    answers = tui_utils.prompt_box("Your Answers", "Respond to each question clearly:").strip()
    if not answers:
        answers = "N/A"

    system_log("AI", "INFO", "Primary strategist drafting PRD.")
    with specialist_spinner():
        draft = specialist_ai.strategist(goal, p_client, s_client, ai_questions, answers)
    previous_draft = None

    while True:
        tui_utils.display_markdown(draft, title="Design Draft")
        accept = input("\nDo you approve this design draft? (Y/N): ").strip().lower()
        if accept in ("y", "yes"):
            system_log("AI", "INFO", "Strategist draft approved by user.")
            return draft
        elif accept in ("n", "no"):
            system_log("AI", "INFO", "Strategist draft rejected; requesting an alternative from the secondary model.")
            print("\nSolaris is asking the secondary strategist for an alternative approach...")
            previous_draft = draft
            with specialist_spinner():
                draft = specialist_ai.strategist(goal, p_client, s_client, ai_questions, answers,
                                                 previous_draft=previous_draft, force_secondary=True)
        else:
            print("Invalid input. Please enter Y or N.")
            

system_log("SYSTEM", "INFO", "Chat session started.")

print("Type .HELP to see list of commands!")
imp_conv_history = []
while True:
    if len(conv_history) > 24:
        imp_conv_history.append(helper_ai.current_chat_summariser(conv_history))
        conv_history = conv_history[-7:]
        system_log("AI", "INFO", f"Current Session Summarised.\nImportant Memories stored: {len(imp_conv_history)}")

    if voice_text == 'v':

        with RecordingTimer(seconds):
            recording = sd.rec(int(seconds*fs), samplerate=fs, channels=1)
            sd.wait()

        write("input.wav", fs, recording)
        with Spinner("Transcribing speech..."):
            segments, info = whisper_model.transcribe("input.wav")
        transcribed_text = ""
        transcribed_text = "".join(segment.text for segment in segments).strip()
    elif voice_text == 't':
        transcribed_text = tui_utils.prompt_box(f"👤 {name}")

    # Send to the AI
    question = transcribed_text.strip()

    commands = {
        ".HELP" : show_help,
        ".BETTER" : better,
        ".CHANGE" : change_profile,
        ".VOICE" : change_voice,
        ".ABOUT" : show_about,
        ".UPDATE_PRIVACY" : update_privacy,
        ".CLEAR" : clear,
    }

    # Handle .WEB command with optional question
    if question.upper().startswith(".WEB"):
        try:
            web_question = question[4:].strip() if len(question) > 4 else ""
            handle_web(web_question)
        except Exception as e:
            system_log("COMMAND", "ERROR", f"Command '{question}' failed: {e}")
        continue

    if question.upper() in commands:
        try:
            response = commands[f'{question.upper()}']()
        except Exception as e:
            system_log("COMMAND", "ERROR", f"Command '{question}' failed: {e}")
            continue
        continue

    study_commands = {
        ".DETAIL": "detail",
        ".SIMPLE": "simple",
        ".QUIZ": "quiz",
        ".TIMELINE": "timeline",
        ".COMPARE": "compare",
        ".STEPS": "steps",
    }

    study_mode = None
    for cmd, mode in study_commands.items():
        if question.upper().startswith(cmd):
            study_mode = mode
            break

    if study_mode:
        topic = question[len(f".{study_mode.upper()}"):].strip()
        if not topic:
            tui_utils.display_inline("[yellow]Please provide a topic. Example: .QUIZ photosynthesis[/]")
            continue

        clients = {
            "openrouter": client_or,
            "ollama-cloud": client_ollama,
            "google": client_gem,
            "nvidia": client_nvidia,
            "groq": client_groq,
        }

        config_data = json.load(open("config.json"))
        p_provider = config_data["specialist"]["study"]["primary"]["provider"]
        s_provider = config_data["specialist"]["study"]["secondary"]["provider"]

        p_client = clients.get(p_provider)
        s_client = clients.get(s_provider)

        if not p_client or not s_client:
            tui_utils.display("Study models are unavailable. Check your config.", title="Error")
            continue

        try:
            with specialist_spinner():
                response = study_ai.study(topic, p_client, s_client, study_mode)
        except Exception as e:
            system_log("COMMAND", "ERROR", f"Study command '{study_mode}' failed: {e}")
            tui_utils.display("Both models failed to generate a response.", title="Error")
            continue

        if study_mode == "quiz":
            tui_utils.display_markdown(response, title=f"Quiz: {topic}")
        elif study_mode == "compare":
            tui_utils.display_markdown(response, title=f"Comparison: {topic}")
        elif study_mode == "timeline":
            tui_utils.display_markdown(response, title=f"Timeline: {topic}")
        elif study_mode == "detail":
            tui_utils.display_markdown(response, title=f"Detailed Explanation: {topic}")
        elif study_mode == "simple":
            tui_utils.display_markdown(response, title=f"Simple Explanation: {topic}")
        elif study_mode == "steps":
            tui_utils.display_markdown(response, title=f"Steps: {topic}")
        continue

    # Add to current chat conv_history and session_history
    conv_history.append({
        "role": "user",
        "content": question
    })
    session_history.append({
        "role" : "user",
        "content": question
    })

    # For Prompt Injection
    conversation_text = "\n".join(
        f"{msg['role'].title()}: {msg['content']}"
        for msg in conv_history[-25:]
    )

    memories = history_db.access_history(current_user_id)
    system_log("DATABASE", "INFO", f"Retrieved conversation history for user_id={current_user_id}.")
    memory_text = "\n\n".join(
        f"[{timestamp}]\n{summary}"
        for summary, timestamp in memories
    )

    prompt = helper_ai.build_prompt(name, preference, imp_conv_history, conversation_text, memory_text, question, about_user)

    if not question:
        print("No speech detected.")
        continue

    _ = question.lower().strip(' ?!.')
    temp_question = _.split()
    exit_commands = ['exit', 'quit', 'close', 'bye', 'goodbye']

    if _ in exit_commands:
        response = "Goodbye! Have a great day ahead!"
        system_log("SYSTEM", "INFO", f"Shutdown requested by user_id={current_user_id}.")
        if ai_voice_text == 'v':
            ai_voice_manager(pref, response)
            playsound("output.wav")
        tui_utils.display(response, title="Goodbye")
        processed_session_hist = helper_ai.summarise_session(session_history)
        history_db.store_history(session_start_time, current_user_id, processed_session_hist)
        system_log("DATABASE", "INFO", f"Stored session history for user_id={current_user_id}.")
        break

    try:
        text = [
            "Thinking...",
            "Reasoning...",
            "Recalling memories...",
            "Building response...",
            "Connecting ideas...",
            "Analyzing context...",
            "Writing reply..."
        ]
        spinner = Spinner(random.choice(text))
        response = ask_ai(prompt, spinner=spinner)

        if ai_voice_text == 'v':
            ai_voice_manager(pref, response)
            playsound("output.wav")
        tui_utils.display_markdown(response)
        # Append AI Response to History and session_history
        conv_history.append({
            "role": "assistant",
            "content": response
        })
        session_history.append({
            "role": "assistant",
            "content": response
        })

    except Exception as e:
        system_log("SYSTEM", "ERROR", f"Unexpected chat loop error: {e}")
        if '503' in str(e):
            print("Server unavailable at the moment!")
        elif '429' in str(e):
            print("Rate Limit Reached!")
        else:
            print(f"An error occurred: {e}")
