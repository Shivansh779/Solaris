from google import genai
from openai import OpenAI
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

import helper_ai
import history_db
import main_db

# Current Time Function
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Logging Function Definition
def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

# Create the tables for the Database
main_db.create_table()
history_db.enable_foreign_key()
history_db.create_table()
system_log("SYSTEM", "INFO", "Application database tables initialized.")

conv_history = []
session_history = []
memories = []

fs = 16000 # sample rate, (fps of audio)
seconds=5

load_dotenv()
system_log("SYSTEM", "INFO", "Environment configuration loaded.")

# Gemini Set-Up
gemini_api_key = os.getenv("GEMINI_API_KEY")
client_gem = genai.Client(api_key=gemini_api_key)

MODEL = "gemini-2.5-flash"

MODELS = ['openai/gpt-oss-120b:free', 'meta-llama/llama-3.3-70b-instruct:free',
          'nvidia/nemotron-3-ultra-550b-a55b:free']

#OpenRouter Set-up
openrouter_api_key = os.getenv("OR_API_KEY")
client_or = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=openrouter_api_key,
)

# EdgeTTS
async def main(response):
    text = response if isinstance(response, str) else response.text
    communicate = edge_tts.Communicate(text, "en-IN-NeerjaNeural")
    await communicate.save("output.wav")

# KittenTTS
kitten_model = None

voice_text = input("Choose input mode: Voice or Text (Press V for Voice, T for Text): ").strip().lower()
print("You have chosen: " + ("Voice" if voice_text == 'v' else "Text") + " for yourself.")

if voice_text == 'v':
    whisper_model = WhisperModel("small")
    system_log("SYSTEM", "INFO", "Voice input mode selected.")
else:
    system_log("SYSTEM", "INFO", "Text input mode selected.")

ai_voice_text = input("Choose output mode: Voice or Text (Press V for Voice, T for Text): ").strip().lower()
print("You have chosen: " + ("Voice" if ai_voice_text == 'v' else "Text") + " for the AI.")
system_log("SYSTEM", "INFO", "AI output mode selected.")
print("Options for Text-to-Speech Model:\n1. EdgeTTS (Requires Internet, Indian Accent)\n2. KittenTTS (Offline, British Accent)")
pref = int(input("Enter which Text-to-Speech Model you want to use: "))
if pref > 2 or pref < 1:
    print("Invalid choice. Restart Program!")
    sys.exit(0)

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
Enter Number of Profile to use it, or 
Create New Profile (Type N), or
Update Preferences of a Profile (Type ID.update), or
Deactivate Profile (Type ID.deactivate), or
Activate Profile (Type ID.activate), or,
Exit (type .exit)
Enter your Choice:  """
).strip().lower()

existing = existing.split(".")

current_user_id = None

if existing[0] in ['n', 'no', 'nope', 'nah', 'nahh', 'negative']:
    name = input("Enter your name: ")
    preference = input("Enter a description of how you want the AI to behave: ")
    privacy_setting = input("Do you want it to be a Private Profile? (Y/N) ")
    if privacy_setting == "Y"  or privacy_setting == "y":
        is_private = 1
        print("Your Profile is Private.")
        print(f"Your Profile Password: {main_db.password}\nKindly Save your Password to access your"
              f"profile in future!")
    else:
        is_private = 0
        print("Your Profile is Public")
    processed_pref = helper_ai.summarise_pref(preference)
    current_user_id = main_db.new_user(name, processed_pref, is_private)
    system_log("PROFILE", "INFO", f"Created new profile with user_id={current_user_id}.")
    preference = processed_pref

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
            data = main_db.get_preference(existing[0])
            preference = data[0]
            name = data[1]
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
            data = main_db.get_preference(existing[0])
            preference = data[0]
            name = data[1]
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
    preference = input("Enter the new description of how you want the AI to behave: ")
    processed_pref = helper_ai.summarise_pref(preference)
    main_db.update_user_pref(int(existing[0]), processed_pref)
    system_log("PROFILE", "INFO", f"Public profile preferences updated for user_id={existing[0]}.")
    preference = processed_pref
    current_user_id = int(existing[0])
    data = main_db.get_preference(current_user_id)
    name = data[1]
    preference = data[0]
elif len(existing) < 2 and main_db.fetch_status(existing[0]) == 1:
    try:
        existing = int(existing[0])
        data = main_db.get_preference(existing)
        preference = data[0]
        name = data[1]
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
    message = """"==========================
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

# Exitting the Application
elif len(existing) < 2 and existing[0] == "exit":
    system_log("SYSTEM", "INFO", "Application exited from profile selection.")
    print("Goodbye! Have a Great Day!")
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
            kitten_tts(response)
    elif pref == 2:
        kitten_tts(response)
        system_log("SYSTEM", "INFO", "KittenTTS selected.")

def kitten_tts(kitten_model, response):
    if kitten_model is None:
        kitten_model = "KittenML/kitten-tts-mini-0.8"
    audio = kitten_model.generate(
    text=response,
    voice="Jasper",
    clean_text=True
)
    sf.write("output.wav", audio, 24000)

def change_user_id(user_id):
    global current_user_id, memories, name, preference
    data = main_db.get_preference(user_id)
    memories = history_db.access_history(user_id)
    name = data[1]
    preference = data[0]
    current_user_id = user_id
    system_log("PROFILE", "INFO", f"Changed active profile to user_id={user_id}.")

def ask_ai(prompt, models=None):
    if models is None:
        models = MODELS
    try:
        system_log("AI", "INFO", "Sending request to Gemini model.")
        answer = ask_gemini(prompt)
    except Exception as e:
        system_log("AI", "WARNING", f"Gemini request failed, falling back to OpenRouter: {e}")
        print("Please wait a few seconds...")
        answer = ask_openrouter(prompt, models=models)

    return answer

def ask_gemini(prompt, model=MODEL):
    system_log("AI", "INFO", f"Using Gemini model: {model}.")
    response = client_gem.models.generate_content(
        model=model,
        contents=prompt
    )
    return response.text

def ask_openrouter(prompt, models):
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
            print(f"Please wait a few more seconds...")

    system_log("AI", "WARNING", "All OpenRouter models failed; switching to Ollama.")
    print("All AI Models Failed, switching to Ollama")
    return ask_ollama(prompt)

def ask_ollama(prompt):
    system_log("AI", "INFO", "Using Ollama model: qwen3:4b.")
    response = ollama.chat(
        model="qwen3:4b",
        messages=[
            {"role" : "user", "content" : prompt}
        ]
    )
    text = response['message']['content']
    if "...done thinking." in text:
        text = text.split("...done thinking.")[-1].strip()
    return text

system_log("SYSTEM", "INFO", "Chat session started.")

print("Type .HELP to see list of commands!")
imp_conv_history = []
while True:
    if len(conv_history) > 24:
        imp_conv_history.append(helper_ai.current_chat_summariser(conv_history))
        conv_history = conv_history[-7:]
        system_log("AI", "INFO", f"Current Session Summarised.\nImportant Memories stored: {len(imp_conv_history)}")

    if voice_text == 'v':
        print("Recording...")
        recording = sd.rec(int(seconds*fs), samplerate=fs, channels=1)

        sd.wait()

        print("Transcribing...")
        write("input.wav", fs, recording)

        segments, info = whisper_model.transcribe("input.wav")

        transcribed_text = ""

        transcribed_text = "".join(segment.text for segment in segments).strip()
    elif voice_text == 't':
        transcribed_text = input("You: ")

    # Send to the AI
    print("\nYou: " + transcribed_text)
    question = transcribed_text.strip()

    if ".HELP" in question:
        print(".CHANGE - to Chaange Profiles\nprofile_number.update - To Update Preferences")
        print("exit/goodbye/bye - To Exit")
        print(".VOICE - To Change the Text-To-Speech model")
        continue

    elif ".CHANGE" in question:
        temp_list = []
        for user in main_db.check_existing():
            print(f"{user[0]}: {user[1]}")
            temp_list.append(user[0])
        print("Select the profile to switch to!")
        changed_profile = int(input("Switch to profile: "))
        if changed_profile not in temp_list:
            system_log("PROFILE", "WARNING", f"Invalid profile switch target selected: {changed_profile}.")
            print("Invalid Profile ID!\n\n\n")
            continue
        elif main_db.fetch_privacy_setting(changed_profile) == 1:
            system_log("PROFILE", "WARNING", f"Blocked mid-session switch to private profile user_id={changed_profile}.")
            print("Profile Number Entered is a Private Profile; Restart Application to Switch to\nthe Profile.")
            continue
        change_user_id(changed_profile)
        print("Changing Profile...")
        time.sleep(1.0)
        print("Profile Changed!")
        print("=" * 50 + "\n")
        continue

    elif ".VOICE" in question:
        print("1. EdgeTTS (Requires Internet, Indian Accent)\n2.KittenTTS (Offline, British Accent)")
        pref = int(input("Enter Your Preferred Text-To-Speech Model: "))
        if pref > 2 or pref < 1:
            print("Invalid Choice!")
        else:
            if pref == 1:
                system_log("VOICE", "INFO", "Text-To-Speech Model changed. Model: EdgeTTs")
            else:
                system_log("VOICE", "INFO", "Text-To-Speech Model changed. Model: KittenTTS")
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

    prompt = helper_ai.build_prompt(name, preference, imp_conv_history, conversation_text, memory_text, question)

    if not question:
        print("No speech detected.")
        continue

    _ = question.lower().strip('?!.')
    temp_question = _.split()
    exit_commands = ['exit', 'quit', 'close', 'bye', 'goodbye']

    if  any(item in temp_question for item in exit_commands):
        now = current_time()
        response = "Goodbye! Have a great day ahead!"
        system_log("SYSTEM", "INFO", f"Shutdown requested by user_id={current_user_id}.")
        if ai_voice_text == 'v':
            ai_voice_manager(pref, response)
            playsound("output.wav")
            print("AI: " + response)
        else:
            print("AI: " + response)
        processed_session_hist = helper_ai.summarise_session(session_history)
        history_db.store_history(now, current_user_id, processed_session_hist)
        system_log("DATABASE", "INFO", f"Stored session history for user_id={current_user_id}.")
        break

    print("\nAI is thinking...\n")

    try:
        response = ask_ai(prompt)

        if ai_voice_text == 'v':
            ai_voice_manager(pref, response)
            playsound("output.wav")
            print("AI: " + response)
        else:
            print("AI: " + response)

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

