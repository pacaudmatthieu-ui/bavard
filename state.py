"""Small persistent key/value store next to the code (state.json).

Holds the user's UI choices — picked microphone, dictation mode — so they
survive a restart. Never versioned (see .gitignore): it is per-machine."""
import json
import os
import threading

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

_lock = threading.Lock()


def _read():
    try:
        with open(PATH) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get(key, default=None):
    return _read().get(key, default)


def set(key, value):  # noqa: A001 — reads naturally as state.set("mic", name)
    with _lock:
        data = _read()
        data[key] = value
        try:
            with open(PATH, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"Préférence non enregistrée ({e}).")
