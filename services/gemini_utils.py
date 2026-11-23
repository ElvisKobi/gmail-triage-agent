"""
gemini_utils.py — the connection to Gemini.
Sends one prompt, returns the text. Paces requests and retries automatically on
rate limits, server errors, and dropped network connections.
"""

import os
import time

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()  # works no matter which file imports this one first
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Full Flash (not Lite): no flash-lite model was available to this key, and the agent
# now makes only a handful of calls a day (new mail only, hard rules skip the AI),
# so the free-tier daily limit is no longer the bottleneck. Better writing for drafts.
MODEL = "gemini-3.8-flash"

# Was 5s when the agent processed 800-email backlogs. A daily run makes ~4 calls.
MIN_SECONDS_BETWEEN_CALLS = 1
MAX_RETRIES = 4

_last_call_time = 0.0


def generate(prompt: str) -> str:
    """Sends one prompt to Gemini and returns the response text. Paces itself
    to respect the free-tier rate limit and retries automatically on 429s,
    503s, and dropped network connections."""
    global _last_call_time

    # throttle: wait out whatever's left of the minimum gap since the last call
    elapsed = time.time() - _last_call_time
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=MODEL, contents=prompt)
            _last_call_time = time.time()
            return response.text.strip()
        except errors.ClientError as e:
            is_rate_limit = getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt < MAX_RETRIES:
                wait_time = 20 * attempt  # back off a bit more each retry
                print(f"  Rate limited — waiting {wait_time}s before retry ({attempt}/{MAX_RETRIES})...")
                time.sleep(wait_time)
                continue
            raise
        except errors.ServerError:
            # 503 etc — the model is temporarily overloaded on Google's end, not our fault.
            if attempt < MAX_RETRIES:
                wait_time = 15 * attempt
                print(f"  Model temporarily unavailable — waiting {wait_time}s before retry ({attempt}/{MAX_RETRIES})...")
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
