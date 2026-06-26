# CLI AI Assistant

A terminal-based AI assistant built in Python featuring voice interaction, persistent memory, multiple user profiles, and automatic fallback between cloud and local language models.

## Features

* Text and voice interaction
* Speech-to-text using Faster Whisper
* Text-to-speech using Edge TTS
* Multiple AI providers (Gemini + OpenRouter)
* Automatic fallback to local Ollama models
* Persistent memory across sessions
* Multiple user profiles
* User preference customization
* SQLite-based storage
* Conversation history
* Session summarization
* Runtime profile switching using .change

## Tech Stack

* Python
* SQLite
* Gemini API
* OpenRouter
* Ollama
* Faster Whisper
* Edge TTS
* SoundDevice

## Current Status

This project currently runs entirely in the terminal (CLI).

The desktop companion and system-control features are being developed separately and will be merged into a future version.

## Future Plans

* Desktop GUI
* System control
* Gesture control
* Improved memory retrieval
* Better context management

## Why I Built This

I started this project to learn how modern AI assistants work beyond simply calling an API. During development, I explored speech recognition, text-to-speech, database design, persistent memory, user profile management, fallback systems, local LLM integration, and software architecture.