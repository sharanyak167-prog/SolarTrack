"""Prints the Gemini models your API key can use for reading bills.

Run from the backend folder:   python list_models.py
Then put one in .env as GEMINI_MODEL, and one or two more as GEMINI_FALLBACK_MODELS
(comma separated, no spaces), for example:  GEMINI_FALLBACK_MODELS=model-a,model-b
"""
import os
import sys

from app import config  # loads ../.env  # noqa: F401

key = os.getenv("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY is not set. Fill it in .env first.")

from google import genai  # noqa: E402

try:
    for m in genai.Client(api_key=key).models.list():
        if "generateContent" in (getattr(m, "supported_actions", None) or []):
            print((m.name or "").removeprefix("models/"))
except Exception as e:  # noqa: BLE001
    sys.exit(f"Could not list models: {e}")
