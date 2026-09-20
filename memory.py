"""
memory.py — Persistent preferences that survive process exit and restart.

Reused from Assignment 5 (SkyVault). A preference is a key-value pair
stored in prefs.json. add() rejects if the key already exists; update()
overwrites with history. recall() returns all preferences.
"""
import json
from config import PREFS_PATH


def _load():
    if not PREFS_PATH.exists():
        return {}
    with open(PREFS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add(key, value):
    """Store a new preference. Rejects if the key already exists."""
    data = _load()
    if key in data:
        raise KeyError(f"Preference '{key}' already exists. Use update() to change it.")
    data[key] = value
    _save(data)
    return f"Stored preference: {key} = {value}"


def update(key, value):
    """Overwrite an existing preference."""
    data = _load()
    data[key] = value
    _save(data)
    return f"Updated preference: {key} = {value}"


def recall(key=None):
    """Return one preference by key, or all if key is None."""
    data = _load()
    if key is not None:
        return data.get(key)
    return data


def remove(key):
    """Delete a preference."""
    data = _load()
    if key in data:
        del data[key]
        _save(data)
        return f"Removed preference: {key}"
    return f"Preference '{key}' not found."


def has(key):
    """Check if a preference exists."""
    return key in _load()
