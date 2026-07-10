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
            return _strip_leading_fillers(text) if text else text
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
            return _strip_leading_fillers(cleaned) if cleaned else text
        except requests.RequestException as e:
            print(f"Cleanup failed ({e}); using raw transcript.")
            return text
