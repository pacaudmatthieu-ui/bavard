"""Input-device discovery and the user's mic choice (menu bar picker).

Policy: Bavard records from the Mac's built-in microphone by default, even if
the system default input is something else (e.g. a Bluetooth headset, which
would drop music to HFP quality). The user can pick another mic from the menu
bar; the choice is persisted by name in state.json and survives restarts.
"""
import json
import os

import sounddevice as sd

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# substrings identifying the built-in mic across system languages / Mac models
_BUILTIN_HINTS = ("macbook", "built-in", "intégré", "interne")


def refresh(safe):
    """Re-scan hardware so hot-plugged mics show up. PortAudio only re-scans on
    re-init, which kills open streams — so callers pass safe=False while any
    stream is open, and the list stays as of app start."""
    if not safe:
        return
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def list_input_devices():
    devs, seen = [], set()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and d["name"] not in seen:
            seen.add(d["name"])
            devs.append({"index": i, "name": d["name"]})
    return devs


def current_choice():
    """The mic name picked in the menu, or None for automatic (built-in)."""
    try:
        with open(STATE_PATH) as f:
            return json.load(f).get("mic")
    except Exception:
        return None


def save_choice(name):
    data = {}
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
    except Exception:
        pass
    data["mic"] = name
    with open(STATE_PATH, "w") as f:
        json.dump(data, f)


def resolve_input_device():
    """-> (device_index_or_None, display_name, chosen_mic_missing).

    Order: the user's menu choice if that mic is connected, else the built-in
    mic, else the system default (index None)."""
    devs = list_input_devices()
    choice = current_choice()
    if choice:
        for d in devs:
            if d["name"] == choice:
                return d["index"], d["name"], False
    for d in devs:
        if any(h in d["name"].lower() for h in _BUILTIN_HINTS):
            return d["index"], d["name"], choice is not None
    return None, "micro par défaut du système", choice is not None
