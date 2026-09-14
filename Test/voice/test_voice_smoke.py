"""SMOKE tests for the Solaris voice stack.

These only assert the third-party voice libraries the app uses are importable
in the venv, plus two in-memory/tmp_path WAV round-trips that mirror how
chatbot.py writes audio (scipy at fs=16000, soundfile at 24000).

Deliberately NOT tested here:
- WhisperModel() instantiation (downloads models over the network)
- sd.rec / sd.play (requires a microphone / speakers)
- cats/edge_tts synthesis (requires network / model download)
- chatbot.py itself (runs an infinite main loop at module level)
"""

import numpy as np
import pytest


def test_import_sounddevice():
    import sounddevice as sd
    assert hasattr(sd, "rec")
    assert hasattr(sd, "play")


def test_import_soundfile():
    import soundfile as sf
    assert callable(sf.write)
    assert callable(sf.read)


def test_import_faster_whisper_module_only():
    from faster_whisper import WhisperModel
    assert callable(WhisperModel)


def test_import_edge_tts():
    import edge_tts
    assert callable(edge_tts.Communicate)


def test_import_kittentts():
    from kittentts import KittenTTS
    assert callable(KittenTTS)


def test_import_playsound3():
    from playsound3 import playsound
    assert callable(playsound)


def test_import_scipy_wavfile():
    from scipy.io.wavfile import read, write
    assert callable(read) and callable(write)


def test_scipy_wav_roundtrip_at_16000(tmp_path):
    from scipy.io.wavfile import read, write
    path = tmp_path / "out.wav"
    write(str(path), 16000, np.zeros(16000, dtype=np.int16))
    rate, data = read(str(path))
    assert rate == 16000
    assert data.shape == (16000,)
    assert data.dtype == np.int16


def test_soundfile_wav_roundtrip_at_24000(tmp_path):
    import soundfile as sf
    path = tmp_path / "out.wav"
    sf.write(str(path), np.zeros(24000, dtype=np.float32), 24000)
    data, rate = sf.read(str(path))
    assert rate == 24000
    assert data.shape == (24000,)