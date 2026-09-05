import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

with open("config.json", "r") as f:
    config = json.load(f)

DEPTHS = config.get("web", {}).get("depths", {"quick": 3, "standard": 5, "deep": 8})

DEPTH_ALIASES = {
    1: "quick",
    2: "standard",
    3: "deep",
    "quick": "quick",
    "standard": "standard",
    "deep": "deep",
}

MAX_CONTENT_CHARS = 1500

def _depth_key(depth):
    return DEPTH_ALIASES.get(depth, "standard")

def _tavily(query, max_results):
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        system_log("WEB", "WARNING", "Tavily API key not set; skipping Tavily.")
        return None

    system_log("WEB", "INFO", f"Querying Tavily: '{query}' (max_results={max_results}).")
    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])

    system_log("WEB", "INFO", f"Tavily returned {len(results)} results for '{query}'.")
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": (item.get("content") or "")[:MAX_CONTENT_CHARS],
            "source": "tavily",
        }
        for item in results
    ]

def _firecrawl(query, max_results):
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        system_log("WEB", "WARNING", "Firecrawl API key not set; skipping Firecrawl.")
        return None

    system_log("WEB", "INFO", f"Querying Firecrawl: '{query}' (limit={max_results}).")
    response = requests.post(
        "https://api.firecrawl.dev/v1/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "limit": max_results,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json().get("data", [])

    system_log("WEB", "INFO", f"Firecrawl returned {len(data)} results for '{query}'.")
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": (item.get("description") or "")[:MAX_CONTENT_CHARS],
            "source": "firecrawl",
        }
        for item in data
    ]

def search_web(query, depth="standard"):
    provider_order = [_tavily, _firecrawl]

    for provider in provider_order:
        try:
            results = provider(query, DEPTHS.get(_depth_key(depth), DEPTHS["standard"]))
            if results:
                return results
        except Exception as e:
            system_log("WEB", "WARNING", f"{provider.__name__} failed: {e}. Trying next provider.")

    system_log("WEB", "ERROR", f"Web search failed for '{query}': all providers unavailable.")
    return None
