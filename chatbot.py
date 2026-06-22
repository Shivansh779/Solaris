from google import genai
from openai import OpenAI
from dotenv import load_dotenv
import os
import sounddevice as sd
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
import asyncio
import edge_tts
from playsound3 import playsound
from datetime import datetime
import ollama

history = []

fs = 16000 # sample rate, (fps of audio)
seconds=5

load_dotenv()

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

async def main(response):
    text = response if isinstance(response, str) else response.text
    communicate = edge_tts.Communicate(text, "en-IN-NeerjaNeural")
    await communicate.save("output.wav")

voice_text = input("Choose input mode: Voice or Text (Press V for Voice, T for Text): ").strip().lower()
print("You have chosen: " + ("Voice" if voice_text == 'v' else "Text") + " for yourself.")

if voice_text == 'v':
    model = WhisperModel("base")

ai_voice_text = input("Choose output mode: Voice or Text (Press V for Voice, T for Text): ").strip().lower()
print("You have chosen: " + ("Voice" if ai_voice_text == 'v' else "Text") + " for the AI.")

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ask_ai(prompt, models=None):
    if models is None:
        models = MODELS
    try:
        answer = ask_gemini(prompt)
    except Exception as e:
        print("An Error occurred with Gemini, Switching to backup models!")
        with open("chat_logs.txt", "a") as f:
            f.write(f"ERROR WITH GEMINI: {current_time()}\n{e}\n")
        answer = ask_openrouter(prompt, models=models)

    return answer

def ask_gemini(prompt, model=MODEL):
    response = client_gem.models.generate_content(
        model=model,
        contents=prompt
    )
    return response.text

def ask_openrouter(prompt, models):
    for model in models:
        try:
            response = client_or.chat.completions.create(
                model=model,
                messages=[
                    {"role" : "user", "content" : prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"{model} failed: {e}")
            with open("chat_logs.txt", "a") as f:
                f.write(f"\nERROR WITH AN OPENROUTER MODEL: {current_time()}\n{e}\n")

    print("All OpenRouter Models Failed, switching to Ollama")
    return ask_ollama(prompt)

def ask_ollama(prompt):
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

with open("chat_logs.txt", "a") as f:
    f.write(f"SESSION STARTED: {current_time()}\n")
    f.write("="*50 + "\n")

while True:
    if voice_text == 'v':
        print("Recording...")
        recording = sd.rec(int(seconds*fs), samplerate=fs, channels=1)

        sd.wait()

        print("Transcribing...")
        write("input.wav", fs, recording)

        segments, info = model.transcribe("input.wav")

        transcribed_text = ""

        transcribed_text = "".join(segment.text for segment in segments).strip()
    elif voice_text == 't':
        transcribed_text = input("You: ")

    # Send to the AI
    print("\nYou: " + transcribed_text)
    question = transcribed_text.strip()

    # Add to current chat history
    history.append(f"User: {question}")

    # Add to chat_log
    with open("chat_logs.txt", "a") as f:
        f.write(f"User: {question}\n")

    prompt = f"""
    You are a voice assistant.

    Follow these rules:
    1. Always respond in a friendly and helpful manner.
    2. Keep your responses concise and to the point.
    3. Give responses up to maximum 3 sentences.
    4. Try not to use * symbol.

    Conversation So Far:
    {chr(10).join(history[-10:])}

    User's question: {question}
    """

    if not question:
        print("No speech detected.")
        continue

    _ = question.lower().strip('?!.')
    temp_question = _.split()
    exit_commands = ['exit', 'quit', 'close', 'bye', 'goodbye']

    if  any(item in temp_question for item in exit_commands):
        response = "Goodbye! Have a great day ahead!"
        if ai_voice_text == 'v':
            asyncio.run(main(response))
            playsound("output.wav")
            print("AI: " + response)
        else:
            print("AI: " + response)
        with open(f"chat_logs.txt", "a") as f:
            f.write(f"AI: {response}\n")
            f.write(f"END OF SESSION: {current_time()}\n")
            f.write("="*50 + "\n")
        break

    print("\nAI is thinking...\n")

    try:
        response = ask_ai(prompt)

        if ai_voice_text == 'v':
            asyncio.run(main(response))
            playsound("output.wav")
            print("AI: " + response)
        else:
            print("AI: " + response)

        # Append AI Response to History
        history.append(f"AI: {response}")

        # Add to Chat_Log
        with open("chat_logs.txt", "a") as f:
            f.write(f"AI: {response}\n")

    except Exception as e:
        if '503' in str(e):
            print("Server unavailable at the moment!")
        elif '429' in str(e):
            print("Rate Limit Reached!")
        else:
            print(f"An error occurred: {e}")

        with open("chat_logs.txt", "a") as f:
            f.write(f"ERROR: {e}\n")
