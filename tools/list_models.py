"""
list_models.py — one-off helper: lists the Gemini models your API key can use.
Run from the project folder:  .\.venv\Scripts\python.exe tools\list_models.py
"""

from dotenv import load_dotenv
load_dotenv()
from google import genai
import os

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for m in client.models.list():
    print(m.name)
