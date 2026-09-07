"""Vision analysis for Solaris - sends images to vision-capable models."""

import base64
import json
from datetime import datetime
import os
from typing import List, Dict, Any

try:
    from google.genai import types as genai_types
except Exception:
    genai_types = None


def system_log(category: str, level: str, message: str) -> None:
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")


def current_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_vision_prompt(question: str, num_images: int) -> str:
    img_word = "image" if num_images == 1 else "images"
    return (
        f"You are Solaris' vision analysis assistant. "
        f"Analyze the attached {img_word} carefully and answer the user's question.\n\n"
        f"Instructions:\n"
        f"- Describe what you see accurately and concisely.\n"
        f"- Answer the user's specific question directly.\n"
        f"- If multiple images are provided, consider them together.\n"
        f"- Do not guess or hallucinate details not visible in the {img_word}.\n"
        f"- If the image is unclear or you cannot answer, say so honestly.\n\n"
        f"User's question: {question}"
    )


def _build_google_parts(images: List[Dict[str, Any]]):
    """Build google-genai Part objects from image files."""
    if genai_types is None:
        raise RuntimeError("google.genai not available")
    parts = []
    for img in images:
        with open(img['path'], 'rb') as f:
            data = f.read()
        parts.append(genai_types.Part.from_bytes(data=data, mime_type=img['mime_type']))
    return parts


def _build_openai_parts(images: List[Dict[str, Any]]):
    """Build OpenAI-compatible image_url content parts (base64 data URLs)."""
    parts = []
    for img in images:
        with open(img['path'], 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        data_url = f"data:{img['mime_type']};base64,{b64}"
        parts.append({
            "type": "image_url",
            "image_url": {"url": data_url}
        })
    return parts


def _call(client, provider: str, model: str, prompt: str, images: List[Dict[str, Any]]) -> str:
    if provider == "google":
        image_parts = _build_google_parts(images)
        contents = [prompt] + image_parts
        response = client.models.generate_content(model=model, contents=contents)
        return response.text
    else:
        image_parts = _build_openai_parts(images)
        messages_content = [{"type": "text", "text": prompt}] + image_parts
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": messages_content}]
        )
        return response.choices[0].message.content


def vision(question: str, p_client, s_client, images: List[Dict[str, Any]]) -> str:
    """
    Analyze images with a vision model.

    Args:
        question: user's question about the images
        p_client: primary API client
        s_client: secondary/fallback API client
        images: list of dicts with 'path' and 'mime_type'
    """
    with open("config.json", "r") as f:
        config = json.load(f)

    vm = config.get("vision_model", {})
    primary_model = vm.get("primary", {}).get("model", "")
    primary_provider = vm.get("primary", {}).get("provider", "")
    secondary_model = vm.get("secondary", {}).get("model", "")
    secondary_provider = vm.get("secondary", {}).get("provider", "")

    if not primary_model or not primary_provider:
        return "No primary vision model configured. Add vision_model.primary to config.json."

    prompt = _build_vision_prompt(question, len(images))

    # Llama-3.2-90B-Vision only accepts 1 image per request (NVIDIA NIM docs)
    # If using llama as primary and multiple images, only send first
    primary_is_llama = "llama" in primary_model.lower() and "vision" in primary_model.lower()
    if primary_is_llama and len(images) > 1:
        system_log("AI", "WARNING", f"Llama Vision only supports 1 image; sending first of {len(images)}")
        images = images[:1]

    try:
        system_log("AI", "INFO", f"Vision primary: {primary_model} ({primary_provider})")
        return _call(p_client, primary_provider, primary_model, prompt, images)
    except Exception as e:
        system_log("AI", "ERROR", f"Vision primary failed: {e}. Trying secondary.")
        if not secondary_model or not secondary_provider:
            return f"Primary vision model failed: {e}. No secondary configured."

        secondary_is_llama = "llama" in secondary_model.lower() and "vision" in secondary_model.lower()
        sec_images = images[:1] if secondary_is_llama and len(images) > 1 else images
        try:
            return _call(s_client, secondary_provider, secondary_model, prompt, sec_images)
        except Exception as e2:
            system_log("AI", "ERROR", f"Vision secondary failed: {e2}")
            return "Both vision models failed to analyze the image."