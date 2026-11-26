"""
gemini_utils.py — the connection to Gemini.
Sends one prompt, returns the text. Paces requests, retries on rate limits,
server errors and dropped connections, and falls back to a second model
when the first one is overloaded (503).
"""

import os
import time

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()  # works no matter which file imports this one first
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Tried in order. If a model is overloaded (503) after all retries, the next one is used.
# Pick the order with tools/check_models.py. On Nov 26, 2026 every full Flash model
# returned 503 while both Flash-Lite models answered, so Lite goes first; full Flash
# stays in the list because it writes better drafts when it's available.
MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]

# Was 5s when the agent processed 800-email backlogs. A daily run makes ~4 calls.
MIN_SECONDS_BETWEEN_CALLS = 1
MAX_RETRIES = 3   # per model

_last_call_time = 0.0
_overloaded = set()   # models that failed this run; skipped for the rest of it


def _call_with_retries(model: str, prompt: str) -> str:
    """Tries one model up to MAX_RETRIES times. Raises errors.ServerError if the
    model stays overloaded, so generate() can move on to the next model."""
    global _last_call_time

    for attempt in range(1, MAX_RETRIES + 1):
        # throttle: wait out whatever's left of the minimum gap since the last call
        elapsed = time.time() - _last_call_time
        if elapsed < MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)

        try:
            response = client.models.generate_content(model=model, contents=prompt)
            _last_call_time = time.time()
            return response.text.strip()
        except errors.ClientError as e:
            is_rate_limit = getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt < MAX_RETRIES:
                wait_time = 20 * attempt
                print(f"  Rate limited — waiting {wait_time}s before retry ({attempt}/{MAX_RETRIES})...")
                time.sleep(wait_time)
                continue
            raise
        except errors.ServerError:
            # 503 etc — the model is overloaded on Google's end, not our fault.
            if attempt < MAX_RETRIES:
                wait_time = 15 * attempt
                print(f"  {model} unavailable — waiting {wait_time}s before retry ({attempt}/{MAX_RETRIES})...")
                time.sleep(wait_time)
                continue
            raise
        except (httpx.TransportError, ConnectionError):
            # Dropped/reset connection (Wi-Fi blip, VPN/antivirus interference) — just retry.
            if attempt < MAX_RETRIES:
                wait_time = 10 * attempt
                print(f"  Connection dropped — waiting {wait_time}s before retry ({attempt}/{MAX_RETRIES})...")
                time.sleep(wait_time)
                continue
            raise

    raise RuntimeError("Exceeded max retries calling Gemini API.")


def generate(prompt: str) -> str:
    """Sends one prompt to Gemini and returns the response text.
    Tries each model in MODELS in order, moving on only when one is overloaded.
    A model that was overloaded once is skipped for the rest of this run, so later
    calls don't waste time retrying it."""
    available = [m for m in MODELS if m not in _overloaded] or MODELS
    for i, model in enumerate(available):
        try:
            return _call_with_retries(model, prompt)
        except errors.ServerError:
            _overloaded.add(model)
            if i + 1 < len(available):
                print(f"  {model} is overloaded — switching to {available[i + 1]} for the rest of this run...")
                continue
            raise   # every model is overloaded: fail, so state.json isn't advanced