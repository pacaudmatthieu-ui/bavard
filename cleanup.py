"""Transcript cleanup via a local Ollama LLM. Model name comes ONLY from config."""
import re

import requests

# Small models reliably miss fillers at the very start of the text; strip them
# deterministically (also covers short utterances that skip the LLM).
_LEADING_FILLERS = re.compile(
    r"^(?:\s*(?:euh|heu|hum|um|uh|ben|bah)\b[,.\s]*)+", re.IGNORECASE
)


def _strip_leading_fillers(text):
    out = _LEADING_FILLERS.sub("", text).lstrip()
    if not out:
        return text
    return out[0].upper() + out[1:]


# Spoken punctuation commands (French dictation style): saying « à la ligne »
# inserts a line break, « point d'interrogation » a question mark, etc.
# Done in code, not by the LLM, so it is deterministic and also works on
# short utterances that skip the LLM. Surrounding commas/periods that
# Whisper may add around the command are absorbed by the patterns.
_APO = r"['’]"
_SPOKEN_COMMANDS = [
    (re.compile(r"[ \t,.]*\b(?:nouveau|nouvelle)\s+paragraphe\b[ \t,.]*", re.I), "\n\n"),
    (re.compile(r"[ \t,.]*\b(?:à|a)\s+la\s+ligne\b[ \t,.]*", re.I), "\n"),
    (re.compile(r"[ \t,.]*\bnouvelle\s+ligne\b[ \t,.]*", re.I), "\n"),
    (re.compile(r"[ \t,.]*\bpoints?\s+d" + _APO + r"\s*interrogation\b[ \t,.]*", re.I), " ? "),
    (re.compile(r"[ \t,.]*\bpoints?\s+d" + _APO + r"\s*exclamation\b[ \t,.]*", re.I), " ! "),
    (re.compile(r"[ \t,.]*\bpoints\s+de\s+suspension\b[ \t,.]*", re.I), "… "),
    (re.compile(r"[ \t,.]*\bpoint[- ]virgule\b[ \t,.]*", re.I), " ; "),
    (re.compile(r"[ \t,.]*\bdeux[- ]points\b[ \t,.]*", re.I), " : "),
]


def _apply_spoken_commands(text):
    for rx, rep in _SPOKEN_COMMANDS:
        text = rx.sub(rep, text)
    text = re.sub(r"[ \t]+\n", "\n", text)      # no trailing spaces before breaks
    text = re.sub(r"\n[ \t]+", "\n", text)      # nor leading spaces after them
    text = re.sub(r"[ \t]{2,}", " ", text)
    # capitalize after a line break or after ? / ! / …
    text = re.sub(r"(\n+)([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), text)
    text = re.sub(r"([?!…] )([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip()


class Cleaner:
    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled = bool(cfg.get("enabled", True))
        self.model = cfg["model"]
        self.base_url = cfg.get("base_url", "http://localhost:11434").rstrip("/")
        self.min_words = int(cfg.get("min_words_for_cleanup", 10))
        if self.enabled and not self._model_available():
            print(f"Model {self.model} not installed — run: ollama pull {self.model}")
            print("Falling back to raw transcripts (cleanup disabled).")
            self.enabled = False

    def _model_available(self):
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            names = [m["name"] for m in r.json().get("models", [])]
            return any(n == self.model or n.split(":")[0] == self.model for n in names)
        except requests.RequestException:
            print(f"Ollama not reachable at {self.base_url} — cleanup disabled.")
            return False

    def clean(self, text):
        # LATENCY RULE: short utterances skip the LLM entirely.
        if not self.enabled or not text or len(text.split()) < self.min_words:
            return _apply_spoken_commands(_strip_leading_fillers(text)) if text else text
        try:
            # Small models treat bare text as something to answer, not clean.
            # Wrap it with an explicit instruction + one example to force edit-only behavior.
            prompt = (
                "Copy the following text word for word, in its original language. "
                "Only delete filler words (including at the start), add punctuation "
                "and apostrophes, capitalize sentence starts, and insert blank "
                "lines between distinct ideas. Every non-filler word must be kept "
                "exactly as written. Do not reply to the text, do not add "
                "anything.\n\n"
                f"{text}"
            )
            r = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "system": self.cfg.get("system_prompt", ""),
                    "prompt": prompt,
                    "stream": False,
                    "think": False,  # disable reasoning mode (qwen3 etc.) — cleanup must be instant
                    "options": {"temperature": float(self.cfg.get("temperature", 0.1))},
                },
                timeout=30,
            )
            cleaned = r.json().get("response", "").strip()
            if not cleaned:
                return _apply_spoken_commands(text)
            return _apply_spoken_commands(_strip_leading_fillers(cleaned))
        except requests.RequestException as e:
            print(f"Cleanup failed ({e}); using raw transcript.")
            return text
