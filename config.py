"""
config.py — Configuration and model access for InboxHero.

Loads model settings from environment variables with sensible defaults.
All Ollama API calls go through a single ollama_chat() function here.
"""

import os
import json
import requests
from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent
INBOX_PATH = ROOT / "inbox.json"
OUTBOX_DIR = ROOT / "outbox"
TRACE_PATH = ROOT / "trace.jsonl"
DECISIONS_PATH = ROOT / "decisions.json"
DASHBOARD_HTML = ROOT / "dashboard.html"
DASHBOARD_JSON = ROOT / "dashboard.json"
PREFS_PATH = ROOT / "prefs.json"

# --- Model ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("INBOXHERO_MODEL", "gemma3:4b")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

# --- Disposition vocabulary ---
DISPOSITIONS = ["reply", "archive", "defer", "delegate", "escalate"]


def ollama_chat(
    messages: list,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    """Single entry point for all Ollama API calls.

    Returns the assistant's text response.
    Retries once on HTTP 429 (rate limit).
    """
    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": model or MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=LLM_TIMEOUT)
            if resp.status_code == 429 and attempt == 0:
                import time
                time.sleep(5)
                continue
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.exceptions.RequestException as e:
            if attempt == 1:
                raise
            import time
            time.sleep(3)
    return ""


def load_inbox() -> list[dict]:
    """Load and return all messages from inbox.json."""
    with open(INBOX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs():
    """Create output directories if they don't exist."""
    OUTBOX_DIR.mkdir(exist_ok=True)
