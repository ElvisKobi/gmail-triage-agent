"""
speaker.py — the agent's MOUTH.
Turns text into speech, fully offline.

Uses Piper (a neural voice that sounds human) when its voice file is present,
otherwise falls back to the built-in Windows voice (pyttsx3).

Setup for Piper (once):
    pip install piper-tts
    python -m piper.download_voices en_US-lessac-medium --data-dir voices
"""

import os
import re

import numpy as np
import sounddevice as sd

PIPER_VOICE = os.path.join("voices", "en_US-lessac-medium.onnx")
PIPER_SPEED = 1.1   # Piper "length_scale": >1 = slower, <1 = faster
RATE = 150          # fallback voice speed, words per minute

_piper = None
if os.path.exists(PIPER_VOICE):
    from piper import PiperVoice, SynthesisConfig
    _piper = PiperVoice.load(PIPER_VOICE)
    _piper_config = SynthesisConfig(length_scale=PIPER_SPEED)
else:
    print(f"(Piper voice not found at {PIPER_VOICE}; using the Windows voice.)")


def _clean_line(line: str) -> str:
    """One line of markdown -> one speakable sentence (or '' to skip it)."""
    line = line.strip()
    if not line or set(line) <= set("-=*_ "):            # blank lines and --- dividers
        return ""
    if line.lower().startswith("# email digest"):        # the timestamp title
        return ""
    line = re.sub(r"<[^>]+@[^>]+>", "", line)            # <noreply@uber.com>
    line = re.sub(r"`[^`]*`", "", line)                  # `anything in backticks`
    line = re.sub(r"^[#>*\-\s]+", "", line)              # leading bullets / heading marks
    line = line.replace("(", ", ").replace(")", ", ")    # (aside) -> , aside,
    line = re.sub(r"[*_`#|\[\]]", "", line)              # remaining markdown
    line = re.sub(r"[^\w\s.,:;!?'%$/–-]", "", line)      # emoji and other symbols
    line = re.sub(r"\s*,\s*(,\s*)+", ", ", line)         # collapse ", ,"
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"\s+([,.:;!?])", r"\1", line)         # no space before punctuation
    line = re.sub(r",([.:;!?])", r"\1", line)            # ",:" -> ":"   ",." -> "."
    line = line.strip(" ,")
    if line and line[-1] not in ".!?:":
        line += "."                                      # every line ends -> a real pause
    return line


def _clean_for_speech(text: str) -> str:
    """Turns markdown into sentences: each line becomes its own sentence so the
    voice pauses between headings and bullets instead of running them together."""
    sentences = [_clean_line(l) for l in text.splitlines()]
    return " ".join(s for s in sentences if s)


def _say_piper(text: str):
    chunks = list(_piper.synthesize(text, syn_config=_piper_config))
    if not chunks:
        return
    audio = np.concatenate([c.audio_float_array for c in chunks])
    sd.play(audio, chunks[0].sample_rate)
    sd.wait()


def _say_windows(text: str):
    """A fresh engine each time avoids a pyttsx3 bug where it goes silent on Windows."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", RATE)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def say(text: str):
    """Prints the text and speaks it."""
    print(f"Agent: {text}")
    spoken = _clean_for_speech(text)
    if not spoken:
        return
    if _piper:
        _say_piper(spoken)
    else:
        _say_windows(spoken)
