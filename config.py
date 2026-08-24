from google import genai
from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()

def init_gemini ():
    api_key = os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)

def init_openrouter ():
    api_key = os.getenv("OR_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

def init_assist_or ():
    api_key = os.getenv("OR_ASSIST_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

def init_nvidia ():
    api_key = os.getenv("NVIDIA_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://integrate.api.nvidia.com/v1"
    )

def init_groq ():
    api_key = os.getenv("GROQ_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )

def init_ollama_cloud ():
    api_key = os.getenv("OLLAMA_CLOUD_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://ollama.com/v1"
    )
