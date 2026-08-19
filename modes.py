"""Dictation modes: the same voice, formatted for where it lands.

A mode adds a formatting instruction to the cleanup model, and can adjust a
couple of deterministic knobs. Which mode applies is decided when you press
the hotkey, from the app that has focus (and its window title, so webmail in
a browser is recognised too). The menu bar can pin a mode instead.

Built-in modes live here — they ship with the app. Personal modes live in
`~/Documents/Bavard/modes.yaml` on the user's machine (never in the repo) and
are merged on top: same key = override a built-in, new key = a new mode.

Mode fields:
  label       French name, shown in the menu
  prompt      instruction appended to the cleanup system prompt (English:
              small models follow English instructions more reliably)
  apps        lowercase substrings matched against the frontmost app name
  titles      lowercase substrings matched against its window title
  min_words   optional override of llm.min_words_for_cleanup
  one_block   collapse blank lines afterwards (done in code, not by the LLM)
  signature   append the context file's signature (e-mail mode, opt-in)
"""
import os

import yaml

AUTO = "auto"
DEFAULT = "standard"
USER_MODES_PATH = "~/Documents/Bavard/modes.yaml"

# Order matters: the first mode whose app/title matches wins.
BUILT_IN = {
    "email": {
        "label": "E-mail",
        "apps": ["mail", "spark", "outlook", "airmail", "thunderbird",
                 "superhuman", "canary", "mimestream", "postbox"],
        "titles": ["gmail", "outlook", "boîte de réception", "inbox",
                   "nouveau message", "new message", "compose"],
        "min_words": 5,
        "signature": True,
        "prompt": (
            "FORMAT: this text is the body of an e-mail. Put the greeting on "
            "its own line if one was spoken, separate paragraphs with a blank "
            "line, and put the closing formula on its own line if one was "
            "spoken. NEVER invent a greeting, a closing formula or a "
            "signature that was not spoken."
        ),
    },
    "chat": {
        "label": "Message court",
        "apps": ["slack", "messages", "whatsapp", "discord", "telegram",
                 "teams", "signal", "messenger"],
        "titles": [],
        "one_block": True,
        "prompt": (
            "FORMAT: this text is a short instant message. Keep it as a "
            "single block: no blank lines, no bullet points, no headings. "
            "Punctuate lightly and keep the spoken, conversational tone."
        ),
    },
    "code": {
        "label": "Technique",
        "apps": ["terminal", "iterm", "visual studio code", "xcode", "cursor",
                 "warp", "ghostty", "zed", "sublime", "nova", "windsurf",
                 "alacritty", "kitty"],
        "titles": [],
        "one_block": True,
        "prompt": (
            "FORMAT: this text is a technical instruction or a prompt for a "
            "developer tool. Keep technical terms, file names, commands, "
            "English words and code identifiers EXACTLY as spoken — never "
            "translate them, never reformat them. Plain sentences, no bullet "
            "points, no blank lines."
        ),
    },
    "notes": {
        "label": "Notes",
        "apps": ["notes", "notion", "obsidian", "bear", "craft", "evernote",
                 "logseq", "drafts"],
        "titles": [],
        "prompt": (
            "FORMAT: this text is a note. When the speaker enumerates things, "
            "put each item on its own line starting with '- '. Keep lines "
            "short. Do not add a title."
        ),
    },
    "standard": {
        "label": "Texte standard",
        "apps": [],
        "titles": [],
        "prompt": "",  # the base system prompt, unchanged
    },
}


class Modes:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.email_signature = bool(cfg.get("email_signature", False))
        self.path = os.path.expanduser(cfg.get("user_modes", USER_MODES_PATH))
        self.modes = {k: dict(v) for k, v in BUILT_IN.items()}
        self._load_user_modes()
        default = cfg.get("default", AUTO)
        self.default = default if default in self.modes or default == AUTO else AUTO

    def _load_user_modes(self):
        """Merge the user's own modes.yaml over the built-ins, if it exists."""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                user = yaml.safe_load(f) or {}
            if not isinstance(user, dict):
                raise ValueError("le fichier doit contenir un dictionnaire de modes")
            for key, spec in user.items():
                if not isinstance(spec, dict):
                    continue
                merged = dict(self.modes.get(key, {"label": key, "prompt": ""}))
                merged.update(spec)
                self.modes[key] = merged
            print(f"Modes personnels chargés : {', '.join(user)}")
        except Exception as e:
            print(f"modes.yaml ignoré ({e}).")

    # ── resolution ───────────────────────────────────────────────────────────

    def keys(self):
        """Mode keys in menu order (built-ins first, then personal ones)."""
        order = [k for k in BUILT_IN if k in self.modes]
        return order + [k for k in self.modes if k not in order]

    def label(self, key):
        return self.modes.get(key, {}).get("label", key)

    def detect(self, app_name, window_title=""):
        """Which mode the focused app calls for."""
        app = (app_name or "").lower()
        title = (window_title or "").lower()
        for key in self.keys():
            spec = self.modes[key]
            if any(t in title for t in spec.get("titles") or []):
                return key
            if any(a in app for a in spec.get("apps") or []):
                return key
        return DEFAULT

    def resolve(self, app_name, window_title="", override=None):
        """-> (mode_key, was_detected). override wins over detection; AUTO or
        an unknown key falls back to detection."""
        if not self.enabled:
            return DEFAULT, False
        if override and override != AUTO and override in self.modes:
            return override, False
        return self.detect(app_name, window_title), True

    def spec(self, key):
        """The mode's settings, with `signature` already resolved against the
        config toggle so callers never have to know about both."""
        spec = dict(self.modes.get(key) or self.modes.get(DEFAULT, {}))
        spec["signature"] = bool(spec.get("signature")) and self.email_signature
        return spec


def current_override():
    """The mode pinned from the menu bar, or AUTO."""
    import state
    return state.get("mode", AUTO)


def save_override(key):
    import state
    state.set("mode", key or AUTO)
