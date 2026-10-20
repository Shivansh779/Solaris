import sys
import platform
import random
import textwrap
import shutil
import getpass
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
import ollama
import time
from textwrap import dedent
import json
import subprocess
from spinner import Spinner, RecordingTimer
import config
import model_state

SPINNER_TEXTS = [
    "Thinking...",
    "Reasoning...",
    "Recalling memories...",
    "Building response...",
    "Connecting ideas...",
    "Analyzing context...",
    "Writing reply...",
    "Consulting the specialist...",
    "Fetching expert insight...",
    "Summoning domain knowledge...",
    "Analyzing with precision...",
    "Crafting specialist response...",
    "Searching the web...",
    "Synthesizing sources...",
]

def get_spinner(message_list=None):
    """Return a Spinner with a random message from the given list or default SPINNER_TEXTS."""
    messages = message_list if message_list is not None else SPINNER_TEXTS
    return Spinner(random.choice(messages))

import main_db
import history_db
import specialist_ai
import web_search
import study_ai
import tui_utils
import attachment
import vision_ai

# The shared core (pulse, answer controls, strategist flow) and the modules
# behind the new shelf features. Importing them is safe: no network call and
# no client is built until a request is actually made.
import core
import memory_db
import skills
import study_db
import workspace_db

from _log import system_log, current_time

# Create the tables for the Database
main_db.create_table()
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

profiles = main_db.check_existing()


def profile_state_tag(user_id):
    """Short label so the terminal shows why a profile is closed."""
    access = main_db.get_access(user_id)
    if access is None:
        return ""
    if access["state"] == main_db.STATE_INACTIVE:
        return " [inactive — needs its activation code]"
    if access["visibility"] == main_db.VISIBILITY_PRIVATE:
        return " [private — needs its password]"
    return ""


def profile_gate(user_id):
    """The same rule the web interface enforces, applied to the TUI as well:
    inactive profiles need their activation code first, private ones need their
    password. Never open a profile the access model would deny."""
    access = main_db.get_access(user_id)
    if access is None:
        print("Profile not found!")
        return False
    if access["state"] == main_db.STATE_INACTIVE:
        print("That profile is inactive. Reactivate it with its activation code in the web interface first.")
        return False
    if access["visibility"] != main_db.VISIBILITY_PRIVATE:
        return True

    locked_for = main_db.lockout_remaining(user_id)
    if locked_for:
        print(f"Too many incorrect attempts. Try again in {locked_for}s.")
        return False
    for _ in range(3):
        try:
            password = getpass.getpass("Profile password: ")
        except Exception:
            password = input("Profile password: ")
        if main_db.verify_profile_password(user_id, password):
            main_db.reset_failed_attempts(user_id)
            return True
        main_db.register_failed_attempt(user_id)
        print("That password is not correct.")
    print("Too many attempts.")
    return False


for user in profiles:
    print(f"{user[0]}: {user[1]}{profile_state_tag(user[0])}")

print("""
Commands:
N          - New Profile
<ID>       - Select Profile
/exit      - Exit
""")

choice = input("Profile -> ").strip().lower()

current_user_id = None

if choice == "/exit":
    system_log("SYSTEM", "INFO", "Application exited from profile selection.")
    print("Goodbye! Have a Great Day!")
    sys.exit()

elif choice in ['n', 'no', 'nope', 'nah', 'nahh', 'negative']:
    name = input("Enter your name: ")
    preference = input("Enter a description of how you want the AI to behave: ")
    about_user = input("Tell Solaris about yourself (prefer to keep it in 50 words): ")
    processed_pref = helper_ai.summarise_pref(preference)
    processed_about = helper_ai.summarise_about(about_user)
    current_user_id = main_db.new_user(name, processed_pref, processed_about)
    system_log("PROFILE", "INFO", f"Created new profile with user_id={current_user_id}.")
    preference = processed_pref
    about_user = processed_about

else:
    try:
        selected_id = int(choice)
        profile_ids = [p[0] for p in profiles]
        if selected_id not in profile_ids:
            system_log("PROFILE", "ERROR", f"Invalid profile ID selected: {selected_id}")
            print("Invalid Profile ID!")
            sys.exit()
        if not profile_gate(selected_id):
            system_log("PROFILE", "WARNING", f"Access denied for profile {selected_id} in the terminal.")
            sys.exit()
        data = main_db.get_data(selected_id)
        preference = data[0]
        name = data[1]
        about_user = data[2]
        current_user_id = selected_id
        system_log("PROFILE", "INFO", f"Profile selected with user_id={current_user_id}.")
    except ValueError:
        system_log("SYSTEM", "WARNING", "Invalid profile menu option selected.")
        print("Invalid Option Selected!")
        sys.exit()


def sync_core_session():
    """Point the shared core at the profile this terminal has selected.

    core.* works on core.session, so the terminal's own profile choice has to
    be copied over before any shared module is called.
    """
    core.session.user_id = current_user_id
    core.session.name = name
    core.session.preference = preference
    core.session.about_user = about_user


sync_core_session()

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
    sync_core_session()
    system_log("PROFILE", "INFO", f"Changed active profile to user_id={user_id}.")

def ask_ai(prompt, spinner, models=None, route=None):
    if models is None:
        models = MODELS
    spinner.start()
    try:
        system_log("AI", "INFO", "Sending request to Gemini model.")
        answer = ask_gemini(prompt)
        core._route_step(route, "gemini", MODEL)
    except Exception as e:
        core._route_step(route, "gemini", MODEL, ok=False, reason=str(e))
        system_log("AI", "WARNING", f"Gemini request failed, falling back to OpenRouter: {e}")
        spinner.update_message("Reasoning... ⚠️ Cloud models unavailable.")
        answer = ask_openrouter(prompt, spinner, models, route)
    finally:
        spinner.stop()

    return answer

def ask_gemini(prompt, model=MODEL):
    if not model_state.can_attempt(model):
        system_log("AI", "INFO", f"Skipping unavailable Gemini model: {model}.")
        raise RuntimeError(f"Gemini model unavailable for this session: {model}")
    try:
        system_log("AI", "INFO", f"Using Gemini model: {model}.")
        response = client_gem.models.generate_content(
            model=model,
            contents=prompt
        )
        return response.text
    except Exception as e:
        state = model_state.classify_error(e)
        if state == model_state.RATE_LIMIT or state == model_state.MODEL_UNAVAILABLE:
            model_state.mark_unavailable(model)
            system_log("AI", "WARNING", f"Gemini model disabled for this session: {model}. Error: {e}")
        elif state == model_state.SERVICE_UNAVAILABLE:
            model_state.mark_temporarily_unavailable(model)
            system_log("AI", "WARNING", f"Gemini model cooling down {model_state.COOLDOWN_SECONDS}s: {model}. Error: {e}")
        raise

def ask_openrouter(prompt, spinner, models, route=None):
    for model in models:
        if not model_state.can_attempt(model):
            system_log("AI", "INFO", f"Skipping unavailable OpenRouter model: {model}.")
            continue
        try:
            system_log("AI", "INFO", f"Using OpenRouter model: {model}.")
            response = client_or.chat.completions.create(
                model=model,
                messages=[
                    {"role" : "user", "content" : prompt}
                ]
            )
            core._route_step(route, "openrouter", model)
            return response.choices[0].message.content
        except Exception as e:
            core._route_step(route, "openrouter", model, ok=False, reason=str(e))
            state = model_state.classify_error(e)
            if state == model_state.RATE_LIMIT or state == model_state.MODEL_UNAVAILABLE:
                model_state.mark_unavailable(model)
                system_log("AI", "WARNING", f"OpenRouter model disabled for this session: {model}. Error: {e}")
            elif state == model_state.SERVICE_UNAVAILABLE:
                model_state.mark_temporarily_unavailable(model)
                system_log("AI", "WARNING", f"OpenRouter model cooling down {model_state.COOLDOWN_SECONDS}s: {model}. Error: {e}")
            else:
                system_log("AI", "WARNING", f"OpenRouter model failed: {model}. Error: {e}")
            spinner.update_message(f"Cloud model unavailable: {model} ⚠️")
            time.sleep(0.7)

    spinner.update_message("Switching to Local AI...")
    if route is not None:
        route["fallbacks"].append("All cloud models unavailable; continued with the local model.")
    response = ask_ollama(prompt, LOCAL_MODEl, route)
    return response

def ask_ollama(prompt, model, route=None):
    system_log("AI", "INFO", f"Using Ollama model: {model}")
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
    except Exception as e:
        core._route_step(route, "ollama", model, ok=False, reason=str(e))
        raise
    core._route_step(route, "ollama", model)
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
    tui_utils.display_inline("  .CLEAR                 - Clears the terminal. Context is preserved.")
    tui_utils.display_inline("  .ATTACH                - Attach a file (md, pdf, jpg, png) as context.")
    tui_utils.display_inline("  .DETACH                - Remove a file attachment (see attached list).")
    tui_utils.display_inline("  .VISION[:question]     - Analyze attached images with a vision model.")
    tui_utils.display_inline("  .WEB[:quick|:deep] <question>  - Search the web for real-time info.")
    tui_utils.display_inline("")
    tui_utils.display_inline("\n[bold]Shelf Commands:[/]")
    tui_utils.display_inline("")
    tui_utils.display_inline("  .SKILLS                - List the skills, switch one on or off.")
    tui_utils.display_inline("  .MEMORY                - Show the active Constellation Memory, add one.")
    tui_utils.display_inline("  .TRAILS                - Show the study trails, create one, add a concept.")
    tui_utils.display_inline("  .TASK                  - Set the session task, save a checkpoint.")
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
    tui_utils.display_inline("Every answer is followed by a privacy pulse and the list of")
    tui_utils.display_inline("refinements you can ask for (shorter, deeper, plan, ...).")
    tui_utils.display_inline("\nNote: Profile management (update, rename, activate, deactivate)")
    tui_utils.display_inline("      is available only at application startup.")
    tui_utils.display_inline("─" * shutil.get_terminal_size().columns + "\n")

def show_about():
    print(helper_ai.about(current_user_id, voice_text, ai_voice_text, pref))

def change_profile():
    global conv_history, session_history, imp_conv_history
    temp_list = []
    for user in main_db.check_existing():
        print(f"{user[0]}: {user[1]}{profile_state_tag(user[0])}")
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
    if not profile_gate(changed_profile):
        system_log("PROFILE", "WARNING", f"Access denied for profile {changed_profile} in the terminal.")
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

def attach():
    """Handle .ATTACH command - ingest a file into temporary attachment context."""
    file_path = tui_utils.prompt_box("File Path", "Enter absolute file path:").strip()
    if not file_path:
        tui_utils.error("No file path provided. Nothing was attached.")
        system_log("COMMAND", "WARNING", "Attach command invoked with empty path.")
        return

    result = attachment.ingest_file(file_path)

    if result["success"]:
        summary = attachment.format_attachment_summary({
            'file_name': os.path.basename(result['file_path']),
            'file_type': result['file_type'],
            'file_path': result['file_path'],
            'attached_at': result.get('attached_at', ''),
            'metadata': result['metadata']
        })
        tui_utils.display(summary, title="File Attached")
        tui_utils.ok(result['message'])
        if result.get("recommendation"):
            tui_utils.info(result['recommendation'])
        system_log("COMMAND", "INFO", f"Attached {result['file_type']} file: {result['file_path']}")
    else:
        tui_utils.error(f"Failed to attach file: {result['message']}")
        system_log("COMMAND", "ERROR", f"Attach failed for {file_path}: {result['message']}")

def detach():
    """Handle .DETACH command - remove a file from temporary attachment context."""
    if not attachment.has_attachments():
        tui_utils.warn("No files attached currently. Use .ATTACH to add one.")
        system_log("COMMAND", "INFO", "Detach command invoked with no attachments.")
        return

    all_attachments = attachment.get_all_attachments()
    rows = []
    for idx, (abs_path, att) in enumerate(all_attachments.items(), start=1):
        rows.append((str(idx), abs_path))

    tui_utils.display_table(["#", "File Path"], rows, title="Attached Files")

    pick_str = tui_utils.prompt_box("Serial Number", "Enter the serial number to detach:").strip()
    if not pick_str:
        tui_utils.error("No serial number provided. Nothing was removed.")
        system_log("COMMAND", "WARNING", "Detach command invoked with empty serial number.")
        return

    try:
        pick = int(pick_str)
    except ValueError:
        tui_utils.error("Invalid serial number. Please enter a number.")
        system_log("COMMAND", "WARNING", f"Detach command invoked with non-numeric input: {pick_str}")
        return

    if pick < 1 or pick > len(all_attachments):
        tui_utils.error(f"Invalid serial number. Choose between 1 and {len(all_attachments)}.")
        system_log("COMMAND", "WARNING", f"Detach command invoked with out-of-range serial number: {pick}")
        return

    dict_index = pick - 1
    removed = attachment.remove_attachment(dict_index)
    if removed is None:
        tui_utils.error("Failed to remove attachment (internal error).")
        system_log("COMMAND", "ERROR", f"remove_attachment returned None for valid index {dict_index}")
        return

    import json
    tui_utils.ok(f"Removed attachment: {removed['file_name']}")
    system_log("COMMAND", "INFO", f"Removed attachment: {removed['file_name']}. Metadata: {json.dumps(removed['metadata'])}")


# ---------------------------------------------------------------------------
# Shared core: privacy pulse, answer controls and the shelf features
# ---------------------------------------------------------------------------

def choose_option(label, options, default=1):
    """Numbered choice from a list of (value, label) pairs."""
    tui_utils.display_table(
        ["#", label],
        [(str(index), text) for index, (value, text) in enumerate(options, 1)],
        title=label,
    )
    pick = tui_utils.prompt_box(label, f"Enter a number between 1 and {len(options)}:").strip()
    if pick.isdigit() and 1 <= int(pick) <= len(options):
        return options[int(pick) - 1][0]
    tui_utils.warn(f"No valid choice — keeping '{options[default - 1][0]}'.")
    return options[default - 1][0]


def offer_refinements(question, answer):
    """Offer the shared answer controls and run the one that is picked."""
    controls = core.answer_controls()
    if not controls:
        return
    tui_utils.display_controls(controls)
    pick = tui_utils.prompt_box(
        "Refine", "Number to refine this answer, or press Enter to continue:"
    ).strip()
    if not pick:
        return
    if not pick.isdigit() or not 1 <= int(pick) <= len(controls):
        tui_utils.warn(f"Pick a number between 1 and {len(controls)}.")
        return

    control = controls[int(pick) - 1]
    sync_core_session()
    with get_spinner():
        result = core.follow_up(control["key"], question, answer)
    if result.get("type") == "error":
        tui_utils.error(result.get("message", "The refinement failed."))
        return
    tui_utils.display_markdown(result.get("raw", ""), title=result.get("title", control["label"]))
    tui_utils.display_pulse(result.get("pulse"))
    # Keep the terminal's own conversation in step with the refinement.
    label = control["label"]
    for history in (conv_history, session_history):
        history.append({"role": "user", "content": f"({label}) {question}".strip()})
        history.append({"role": "assistant", "content": result.get("raw", "")})


def handle_skills():
    """List the Markdown skills and let the user switch one on or off."""
    items = skills.payload()["skills"]
    if not items:
        tui_utils.warn("No skills found. Add a Markdown file to Skills/ or ~/.solaris/skills/.")
        return

    rows = [
        (str(index), item["name"], item["scope"], "active" if item["active"] else "off", item["short"])
        for index, item in enumerate(items, 1)
    ]
    tui_utils.display_table(["#", "Skill", "Scope", "State", "Description"], rows, title="Skills")

    pick = tui_utils.prompt_box(
        "Skill", "Number to switch on/off, 'c' for the active prompt context, Enter to exit:"
    ).strip().lower()
    if not pick:
        return
    if pick == "c":
        context = skills.get_context()
        if context:
            tui_utils.display(context, title="Active Skills In The Prompt")
        else:
            tui_utils.info("No skill is active, so the prompt carries no skill instructions.")
        return
    if not pick.isdigit() or not 1 <= int(pick) <= len(items):
        tui_utils.warn(f"Pick a number between 1 and {len(items)}.")
        return

    item = items[int(pick) - 1]
    now_active = not item["active"]
    if not skills.set_active(item["id"], now_active):
        tui_utils.error("That skill is unknown.")
        return
    tui_utils.ok(f"{item['name']} is now {'active' if now_active else 'off'}.")


def handle_memory():
    """Show the profile's active memories (Constellation Memory) and add one."""
    nodes = memory_db.list_memories(current_user_id, status="active")
    rows = [
        (
            str(index),
            memory_db.CATEGORY_LABELS.get(node["category"], node["category"]),
            node["title"],
            node["detail"] or "-",
        )
        for index, node in enumerate(nodes, 1)
    ]
    tui_utils.display_table(["#", "Category", "Memory", "Detail"], rows, title="Constellation Memory")

    action = tui_utils.prompt_box("Memory", "'a' to add a memory, Enter to exit:").strip().lower()
    if action != "a":
        return

    title = tui_utils.prompt_box("Memory Title", "What should Solaris remember?").strip()
    if not title:
        tui_utils.warn("A memory needs a title. Nothing was stored.")
        return
    detail = tui_utils.prompt_box("Detail", "Anything else worth keeping (optional):").strip()
    category = choose_option(
        "Category",
        [(key, memory_db.CATEGORY_LABELS[key]) for key in memory_db.CATEGORIES],
        default=memory_db.CATEGORIES.index("custom") + 1,
    )
    memory_db.add_memory(current_user_id, category, title, detail, source="user", status="active")
    tui_utils.ok("Memory stored. It is now part of the prompt context.")


def handle_trails():
    """List the study trails, create one, or add a concept to one."""
    trails = study_db.list_trails(current_user_id)
    rows = [
        (
            str(trail["id"]),
            trail["title"],
            study_db.STAGE_LABELS.get(trail["stage"], trail["stage"]),
            str(trail["quizzes_completed"]),
            ", ".join(spot["name"] for spot in trail["weak_spots"]) or "-",
        )
        for trail in trails
    ]
    tui_utils.display_table(["#", "Trail", "Stage", "Quizzes", "Revisit"], rows, title="Study Trails")

    action = tui_utils.prompt_box(
        "Trail", "'n' for a new trail, a trail number to add a concept, Enter to exit:"
    ).strip().lower()
    if not action:
        return
    if action == "n":
        title = tui_utils.prompt_box("Trail Title", "What are you learning?").strip()
        if not title:
            tui_utils.warn("A study trail needs a topic. Nothing was created.")
            return
        description = tui_utils.prompt_box("Description", "What is this trail about? (optional)").strip()
        trail_id = study_db.create_trail(current_user_id, title, description)
        tui_utils.ok(f"Study trail {trail_id} created: {title}")
        return
    if not action.isdigit():
        tui_utils.warn("Enter 'n' or the number of a trail.")
        return

    trail_id = int(action)
    if not any(trail["id"] == trail_id for trail in trails):
        tui_utils.error(f"No study trail with the number {trail_id}.")
        return

    name = tui_utils.prompt_box("Concept", "Which concept goes into this trail?").strip()
    if not name:
        tui_utils.warn("A concept needs a name. Nothing was added.")
        return
    mastery = choose_option("Mastery", [(key, key) for key in study_db.MASTERY], default=1)
    study_db.add_concept(current_user_id, trail_id, name, mastery)
    tui_utils.ok(f"Concept '{name}' added to trail {trail_id} ({mastery}).")


def register_quiz(user_id, topic):
    """Count a finished quiz for the trail with the same topic."""
    try:
        for trail in study_db.list_trails(user_id):
            if trail["title"].strip().lower() == (topic or "").strip().lower():
                study_db.register_quiz(user_id, trail["id"])
                system_log("STUDY", "INFO", f"Quiz counted for trail {trail['id']}.")
                tui_utils.ok(f"Quiz counted for the trail '{trail['title']}'.")
                return
    except Exception as e:  # counting must never break the reply
        system_log("STUDY", "WARNING", f"Could not record the quiz: {e}")


def handle_task():
    """Show the workspace task and checkpoint, and let the user change them."""
    task = workspace_db.get_task(current_user_id)
    checkpoint = workspace_db.get_checkpoint(current_user_id)
    tui_utils.display_table(
        ["Field", "Value"],
        [
            ("Task", task["task"] or "-"),
            ("Updated", task["updated_at"] or "-"),
            ("Goal", checkpoint["goal"] or "-"),
            ("Decisions", checkpoint["decisions"] or "-"),
            ("Open questions", checkpoint["questions"] or "-"),
            ("Next step", checkpoint["next_step"] or "-"),
        ],
        title="Workspace",
        expand=False,
    )

    action = tui_utils.prompt_box(
        "Workspace", "'t' to set the task, 'c' to save a checkpoint, Enter to exit:"
    ).strip().lower()
    if action == "t":
        value = tui_utils.prompt_box("Task", "What are you working on?").strip()
        workspace_db.set_task(current_user_id, value)
        tui_utils.ok("Task saved for this profile.")
        return
    if action == "c":
        goal = tui_utils.prompt_box("Goal", "What is the goal of this session?").strip()
        decisions = tui_utils.prompt_box("Decisions", "What was decided? (optional)").strip()
        questions = tui_utils.prompt_box("Open Questions", "What is still open? (optional)").strip()
        next_step = tui_utils.prompt_box("Next Step", "What happens next? (optional)").strip()
        workspace_db.save_checkpoint(current_user_id, goal, decisions, questions, next_step)
        tui_utils.ok("Checkpoint saved for this profile.")

def select_vision_attachments():
    """Select image attachments for .VISION. Returns list of image dicts or empty list."""
    images = attachment.get_attachments_for_vision()
    if not images:
        return []

    while True:
        yn = tui_utils.prompt_box("Use Images", "Use attached images for .VISION? (Y/N)").strip().lower()
        if yn in ("y", "yes"):
            return images
        elif yn in ("n", "no"):
            return []
        else:
            tui_utils.warn("Please enter Y or N.")


def handle_vision(question=""):
    """Handle .VISION command - analyze attached images with a vision model."""
    with open("config.json", "r") as f:
        config_data = json.load(f)

    vm = config_data.get("vision_model", {})
    primary = vm.get("primary", {})
    if not primary.get("model") or not primary.get("provider"):
        tui_utils.display("Warning: no vision model configured. Set vision_model.primary in config.json.", title="Vision")
        system_log("COMMAND", "WARNING", ".VISION invoked but no vision model configured.")
        return

    if not attachment.has_attachments():
        tui_utils.warn("No files attached. Use .ATTACH to add an image first.")
        return

    images = select_vision_attachments()
    if not images:
        tui_utils.warn("No images selected.")
        return

    if not question:
        question = tui_utils.prompt_box("Question", "What would you like to know about the image?").strip()
        if not question:
            tui_utils.error("No question provided, so nothing was analysed.")
            return

    clients = {
        "openrouter": client_or,
        "ollama-cloud": client_ollama,
        "google": client_gem,
        "nvidia": client_nvidia,
        "groq": client_groq,
    }

    p_provider = primary.get("provider", "")
    s_provider = vm.get("secondary", {}).get("provider", "")
    p_client = clients.get(p_provider)
    s_client = clients.get(s_provider)

    if not p_client and not s_client:
        tui_utils.display("Error: vision model providers are unavailable. Check your config.", title="Error")
        system_log("COMMAND", "ERROR", ".VISION: no available vision model clients.")
        return

    started = time.time()
    try:
        with get_spinner():
            response = vision_ai.vision(question, p_client, s_client, images)
    except Exception as e:
        system_log("COMMAND", "ERROR", f".VISION failed: {e}")
        tui_utils.display("Error: vision analysis failed. Check logs for details.", title="Error")
        return

    img_count = len(images)
    img_word = "image" if img_count == 1 else "images"
    tui_utils.display_markdown(response, title=f"Vision Analysis ({img_count} {img_word})")
    route = core._route_from_providers([p_provider, s_provider])
    tui_utils.display_pulse(core.build_pulse(
        route,
        **core._context_counts(),
        files_selected=img_count,
        files_total=img_count,
        latency_ms=int((time.time() - started) * 1000),
    ))
    system_log("COMMAND", "INFO", f".VISION analyzed {img_count} {img_word} with question: {question[:80]}")


def parse_web_depth(question):
    q = question.strip()
    if q.startswith(":"):
        rest = q[1:].strip()
        if rest:
            first_word = rest.split()[0].lower()
            remaining = " ".join(rest.split()[1:]).strip()
            if first_word == "quick":
                return "quick", remaining
            elif first_word == "deep":
                return "deep", remaining
    return "standard", q

def handle_web(question=""):
    question = question.strip()
    if not question:
        tui_utils.error("Please provide a question. Usage: .WEB <question> or .WEB:quick <question>")
        system_log("COMMAND", "WARNING", "Web search requested with no question.")
        return

    depth, query = parse_web_depth(question)
    if not query:
        tui_utils.error("Please provide a question. Usage: .WEB <question> or .WEB:quick <question>")
        system_log("COMMAND", "WARNING", "Web search requested with no question.")
        return
    system_log("COMMAND", "INFO", f"Web search requested: {query[:50]}... (depth={depth}).")

    with Spinner("Searching the web..."):
        sources = web_search.search_web(query, depth)

    if not sources:
        tui_utils.error("Web search unavailable. Check the Tavily / Firecrawl keys in your .env file.")
        system_log("WEB", "ERROR", f"Web search unavailable for query: {query[:50]}...")
        return

    provider = sources[0].get("source", "unknown")
    urls = ", ".join(s["url"] for s in sources)
    history_db.store_web_log(current_user_id, query, provider, depth, urls)

    web_prompt = helper_ai.build_web_prompt(query, sources)

    route = core.new_route()
    started = time.time()
    try:
        spinner = get_spinner()
        response = ask_ai(web_prompt, spinner=spinner, route=route)

        if ai_voice_text == 'v':
            ai_voice_manager(pref, response)
            playsound("output.wav")
        tui_utils.display_markdown(response, title="Web Search")

        tui_utils.display_sources(sources)

        tui_utils.display_pulse(core.build_pulse(
            route,
            **core._context_counts(),
            web_search=True,
            latency_ms=int((time.time() - started) * 1000),
        ))
        offer_refinements(query, response)

        session_history.append({
            "role": "user",
            "content": f".WEB {query}"
        })
        session_history.append({
            "role": "assistant",
            "content": response
        })
        system_log("AI", "INFO", f"Web search response generated for query: {query[:50]}...")

    except Exception as e:
        system_log("SYSTEM", "ERROR", f"Unexpected error in web search response generation: {e}")
        tui_utils.error("An error occurred while processing the web search results.")




def select_better_attachments() -> str:
    """Prompt user to select which attached files .BETTER should use.
    Returns combined context string for all files, or empty string if none/no attachments."""
    if not attachment.has_attachments():
        return ""

    while True:
        yn = tui_utils.prompt_box("Use Attached Files", "Use attached files for .BETTER? (Y/N)").strip().lower()
        if yn in ("y", "yes"):
            return attachment.get_combined_attachment_context()
        elif yn in ("n", "no"):
            return ""
        else:
            tui_utils.warn("Please enter Y or N.")


def flow_route(primary, secondary):
    """Route record for the flows that pick their own model (study, specialists, vision).

    Those modules do not report back which client answered, so the route names
    the candidates only — the pulse must never claim a model that did not answer.
    """
    return core._route_from_providers([primary.get("provider"), secondary.get("provider")])


def better(question="", clien=None, answers=""):
    # Select attachments at the start (before specialist choice)
    attachment_context = select_better_attachments()

    tui_utils.display_table(
        ["#", "Specialist", "Expertise"],
        [
            ("1", "✍️  The Writer", "Writing, essays, creative content"),
            ("2", "💻 The Programmer", "Coding, debugging, software design"),
            ("3", "🧠 The Strategist", "Reasoning, planning, problem solving"),
        ],
        title="Who do you want to answer?",
    )
    pick = tui_utils.prompt_box("Your Option").strip()
    if not pick.isdigit() or not 1 <= int(pick) <= 3:
        tui_utils.error("Invalid option. Choose 1, 2 or 3.")
        return "Invalid Option Selected! Try Again!"
    choice = int(pick)

    if choice in (1, 2) and not question:
        question = tui_utils.prompt_box("Your Request", "Describe your request clearly:").strip()
        if not question:
            tui_utils.error("No request provided. Nothing was sent.")
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
            primary = config['specialist']['writing']['primary']
            secondary = config['specialist']['writing']['secondary']
            if primary['provider'] in clients and secondary['provider'] in clients:
                started = time.time()
                with get_spinner():
                    response = specialist_ai.writer(question, clients[primary['provider']], clients[secondary['provider']], attachment_context, skills.get_context())
                tui_utils.display_markdown(response, title="✍️ The Writer")
                tui_utils.display_pulse(core.build_pulse(
                    flow_route(primary, secondary),
                    **core._context_counts(),
                    latency_ms=int((time.time() - started) * 1000),
                ))
                offer_refinements(question, response)
                return response
            tui_utils.error("The Writer models are unavailable. Check your config.")
            return "Writer models unavailable. Check config."
        case 2:
            primary = config['specialist']['coding']['primary']
            secondary = config['specialist']['coding']['secondary']
            if primary['provider'] in clients and secondary['provider'] in clients:
                started = time.time()
                with get_spinner():
                    response = specialist_ai.coder(question, clients[primary['provider']], clients[secondary['provider']], attachment_context, skills.get_context())
                tui_utils.display_markdown(response, title="💻 The Programmer")
                tui_utils.display_pulse(core.build_pulse(
                    flow_route(primary, secondary),
                    **core._context_counts(),
                    latency_ms=int((time.time() - started) * 1000),
                ))
                offer_refinements(question, response)
                return response
            tui_utils.error("The Programmer models are unavailable. Check your config.")
            return "Programmer models unavailable. Check config."
        case 3:
            primary = config['specialist']['reasoning']['primary']
            secondary = config['specialist']['reasoning']['secondary']
            if primary['provider'] not in clients or secondary['provider'] not in clients:
                tui_utils.error("Strategist models unavailable. Check config.")
                return "Strategist models unavailable. Check config."
            return strategist_flow(question, use_attachments=bool(attachment_context))
        case _:
            tui_utils.error("Invalid option. Choose 1, 2 or 3.")
            return "Invalid Option Selected! Try Again!"


def collect_answers(questions):
    """Ask the strategist's questions one by one and format the answers."""
    if not questions:
        return tui_utils.prompt_box("Your Answers", "Answer the questions above (N/A is fine):").strip() or "N/A"
    answers = []
    for index, question in enumerate(questions, 1):
        answers.append(tui_utils.prompt_box(f"Question {index}", question).strip() or "N/A")
    return "\n".join(f"{index}. {answer}" for index, answer in enumerate(answers, 1))


def strategist_flow(goal="", use_attachments=True):
    """Questions → numbered answers → draft → Approve or Ask the Secondary Model."""
    goal = (goal or "").strip()
    if not goal:
        goal = tui_utils.prompt_box("Your Goal", "Define your goal (structured, one response):").strip()

    if not goal:
        tui_utils.error("No goal provided. Nothing was sent.")
        return "No goal provided. Try again."

    system_log("AI", "INFO", f"Strategist flow started for goal: {goal[:60]}...")

    sync_core_session()
    with get_spinner():
        questions_result = core.better("strategist", goal, use_attachments=use_attachments)
    if questions_result.get("type") == "error":
        tui_utils.error(questions_result.get("message", "The Strategist is unavailable."))
        return questions_result.get("message", "")

    tui_utils.display_markdown(questions_result.get("raw", ""), title="🤖 Solaris Questions")
    tui_utils.display_pulse(questions_result.get("pulse"))

    questions = questions_result.get("questions") or helper_ai.split_questions(questions_result.get("raw", ""))
    answers = collect_answers(questions)

    system_log("AI", "INFO", "Primary strategist drafting PRD.")
    with get_spinner():
        draft_result = core.better_answers(answers)
    if draft_result.get("type") == "error":
        tui_utils.error(draft_result.get("message", "The draft could not be written."))
        return draft_result.get("message", "")
    tui_utils.display_markdown(draft_result.get("raw", ""), title="Design Draft")

    while True:
        action = tui_utils.prompt_box(
            "Design Draft", "Approve (a) or Ask the Secondary Model (s)?"
        ).strip().lower()
        if action in ("a", "approve", "y", "yes"):
            with get_spinner():
                approved = core.better_decision(True)
            if approved.get("type") == "error":
                tui_utils.error(approved.get("message", "The draft could not be approved."))
                return approved.get("message", "")
            system_log("AI", "INFO", "Strategist draft approved by user.")
            tui_utils.display_markdown(approved.get("raw", ""), title="🧠 The Strategist")
            return approved.get("raw", "")
        if action in ("s", "secondary", "n", "no"):
            system_log("AI", "INFO", "Strategist draft rejected; requesting an alternative from the secondary model.")
            tui_utils.info("Asking the secondary strategist for an alternative approach...")
            with get_spinner():
                alternative = core.better_decision(False)
            if alternative.get("type") == "error":
                tui_utils.error(alternative.get("message", "The alternative draft failed."))
                return alternative.get("message", "")
            tui_utils.display_markdown(alternative.get("raw", ""), title="Alternative Design Draft")
            continue
        tui_utils.warn("Enter 'a' to approve or 's' for the secondary model.")

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
        ".CLEAR" : clear,
        ".ATTACH" : attach,
        ".DETACH" : detach,
        ".SKILLS" : handle_skills,
        ".MEMORY" : handle_memory,
        ".TRAILS" : handle_trails,
        ".TASK" : handle_task,
    }

    # Handle .WEB command with optional question
    if question.upper().startswith(".WEB"):
        try:
            web_question = question[4:].strip() if len(question) > 4 else ""
            handle_web(web_question)
        except Exception as e:
            system_log("COMMAND", "ERROR", f"Command '{question}' failed: {e}")
        continue

    # Handle .VISION command
    if question.upper().startswith(".VISION"):
        try:
            vis_question = question[7:].strip() if len(question) > 7 else ""
            handle_vision(vis_question)
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
            tui_utils.warn("Please provide a topic. Example: .QUIZ photosynthesis")
            continue

        clients = {
            "openrouter": client_or,
            "ollama-cloud": client_ollama,
            "google": client_gem,
            "nvidia": client_nvidia,
            "groq": client_groq,
        }

        config_data = json.load(open("config.json"))
        primary = config_data["specialist"]["study"]["primary"]
        secondary = config_data["specialist"]["study"]["secondary"]
        p_provider = primary["provider"]
        s_provider = secondary["provider"]

        p_client = clients.get(p_provider)
        s_client = clients.get(s_provider)

        if not p_client or not s_client:
            tui_utils.display("Error: study models are unavailable. Check your config.", title="Error")
            continue

        started = time.time()
        try:
            with get_spinner():
                response = study_ai.study(topic, p_client, s_client, study_mode)
        except Exception as e:
            system_log("COMMAND", "ERROR", f"Study command '{study_mode}' failed: {e}")
            tui_utils.display("Error: both models failed to generate a response.", title="Error")
            continue

        titles = {
            "quiz": f"Quiz: {topic}",
            "compare": f"Comparison: {topic}",
            "timeline": f"Timeline: {topic}",
            "detail": f"Detailed Explanation: {topic}",
            "simple": f"Simple Explanation: {topic}",
            "steps": f"Steps: {topic}",
        }
        tui_utils.display_markdown(response, title=titles[study_mode])

        # A finished quiz counts for a trail with the same topic.
        if study_mode == "quiz":
            register_quiz(current_user_id, topic)

        tui_utils.display_pulse(core.build_pulse(
            flow_route(primary, secondary),
            **core._context_counts(),
            study_trail=topic,
            latency_ms=int((time.time() - started) * 1000),
        ))
        offer_refinements(topic, response)
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

    # Constellation Memory: only the active nodes that match this question.
    try:
        workspace_memory, used_memories = memory_db.build_context(current_user_id, question)
    except Exception as e:
        workspace_memory, used_memories = "", []
        system_log("MEMORY", "WARNING", f"Memory context skipped: {e}")
    if workspace_memory:
        memory_text = f"{memory_text}\n\nWorkspace memories:\n{workspace_memory}".strip()

    # Get temporary attachment context if any
    attachment_context = attachment.get_combined_attachment_context()

    # Active skills add their instructions to every prompt.
    skill_context = skills.get_context()

    prompt = helper_ai.build_prompt(name, preference, imp_conv_history, conversation_text, memory_text, question, about_user, attachment_context, skill_context)

    if not question:
        tui_utils.warn("No speech detected.")
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
        # Clear temporary attachment context and the session's active skills
        attachment.clear_attachment_context()
        skills.clear_active()
        processed_session_hist = helper_ai.summarise_session(session_history)
        history_db.store_history(session_start_time, current_user_id, processed_session_hist)
        system_log("DATABASE", "INFO", f"Stored session history for user_id={current_user_id}.")
        break

    try:
        spinner = get_spinner()
        route = core.new_route()
        started = time.time()
        response = ask_ai(prompt, spinner=spinner, route=route)

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

        tui_utils.display_pulse(core.build_pulse(
            route,
            **core._context_counts(),
            memories=len(used_memories),
            memory_items=used_memories,
            latency_ms=int((time.time() - started) * 1000),
        ))
        offer_refinements(question, response)

    except Exception as e:
        system_log("SYSTEM", "ERROR", f"Unexpected chat loop error: {e}")
        if '503' in str(e):
            tui_utils.error("Server unavailable at the moment (503). Nothing was sent — try again.")
        elif '429' in str(e):
            tui_utils.error("Rate limit reached (429). Nothing was sent — try again in a moment.")
        else:
            tui_utils.error(f"An error occurred: {e}")
