"""
listener.py — the agent's EARS.
Records from the microphone (push-to-talk) and turns speech into text with
Whisper running locally. Your voice never leaves the laptop.

    pip install faster-whisper sounddevice numpy

The first run downloads the Whisper model once (~145 MB for base.en);
after that it works with no internet.
"""

import msvcrt   # Windows built-in: reads single keypresses (needs a real terminal)
import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000          # Whisper expects 16 kHz audio
MODEL_SIZE = "base.en"       # tiny.en = faster/less accurate, small.en = slower/more accurate

print("Loading speech model (first time downloads it)...")
_model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")


def record_until_keypress() -> np.ndarray:
    """Records from the default microphone until you tap any key."""
    chunks = []

    def on_audio(indata, frames, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=on_audio):
        print("  Listening... tap any key when you're done.")
        while not msvcrt.kbhit():      # keep recording until a key is pressed
            time.sleep(0.05)
        msvcrt.getwch()                # consume that keypress

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).flatten()


def transcribe(audio: np.ndarray) -> str:
    """Speech -> text, locally."""
    if audio.size < SAMPLE_RATE * 0.3:   # under 0.3 s: nothing was said
        return ""
    segments, _ = _model.transcribe(audio, language="en")
    return " ".join(seg.text for seg in segments).strip()


def listen() -> str:
    """One push-to-talk turn: record, then return what you said as text."""
    return transcribe(record_until_keypress())
