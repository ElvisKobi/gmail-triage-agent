r"""
check_models.py — one-off helper: sends a tiny "hi" to each text model your key
can use and reports which ones answer right now. Use it when you get 503 errors,
then put the working ones first in MODELS in services/gemini_utils.py.

Run from the project folder:  .\.venv\Scripts\python.exe tools\check_models.py
"""

import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Only models that generate text; skips embedding / research / image models.
candidates = [
    m.name.removeprefix("models/") for m in client.models.list()
    if "generateContent" in (getattr(m, "supported_actions", None) or ["generateContent"])
    and "flash" in m.name and not any(x in m.name for x in ("embedding", "image", "tts", "audio", "live"))
]

print(f"Testing {len(candidates)} models...\n")
for name in candidates:
    start = time.time()
    try:
        client.models.generate_content(model=name, contents="Reply with: ok")
        print(f"  OK     {name}  ({time.time() - start:.1f}s)")
    except Exception as e:
        code = getattr(e, "code", "") or type(e).__name__
        print(f"  FAIL   {name}  ({code})")