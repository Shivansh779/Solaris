from dotenv import load_dotenv
import os

load_dotenv()

PROVIDERS = {
    "gemini": {"api_key_env": "GEMINI_API_KEY", "base_url": None, "client_kind": "gemini"},
    "openrouter": {"api_key_env": "OR_API_KEY", "base_url": "https://openrouter.ai/api/v1", "client_kind": "openai"},
    "openrouter-assist": {"api_key_env": "OR_ASSIST_API_KEY", "base_url": "https://openrouter.ai/api/v1", "client_kind": "openai"},
    "nvidia": {"api_key_env": "NVIDIA_API_KEY", "base_url": "https://integrate.api.nvidia.com/v1", "client_kind": "openai"},
    "groq": {"api_key_env": "GROQ_API_KEY", "base_url": "https://api.groq.com/openai/v1", "client_kind": "openai"},
    "ollama-cloud": {"api_key_env": "OLLAMA_CLOUD_API_KEY", "base_url": "https://ollama.com/v1", "client_kind": "openai"},
}

def client_class(provider: str):
    """The SDK class a provider's client is built from.

    The import is lazy on purpose: config.py is imported at startup, and the
    provider SDKs are heavy to load.
    """
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise ValueError(f"Unknown provider: {provider}")
    if cfg["client_kind"] == "gemini":
        from google import genai
        return genai.Client
    from openai import OpenAI
    return OpenAI

def init_client(provider: str):
    """Initialize an API client for the given provider."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")
    api_key = os.getenv(cfg["api_key_env"])
    if not api_key:
        raise RuntimeError(
            f"Provider '{provider}' needs the {cfg['api_key_env']} environment "
            "variable set (see README.md). Add it to your .env file: "
            f"{cfg['api_key_env']}=..."
        )
    if cfg["client_kind"] == "gemini":
        from google import genai
        return genai.Client(api_key=api_key)

    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=cfg["base_url"])

# Backward-compatible aliases
init_gemini = lambda: init_client("gemini")
init_openrouter = lambda: init_client("openrouter")
init_assist_or = lambda: init_client("openrouter-assist")
init_nvidia = lambda: init_client("nvidia")
init_groq = lambda: init_client("groq")
init_ollama_cloud = lambda: init_client("ollama-cloud")
