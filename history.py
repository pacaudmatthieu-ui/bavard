"""Dictation history: nothing spoken is ever lost.

Every dictation is written to disk as soon as the transcription exists — before
the LLM cleanup, before the paste. If the cleanup fails, if no text field was
focused, if the target app swallows the paste, or if the app crashes mid-way,
the text is already on disk.

Two files, on purpose:

  historique/journal.jsonl   append-only event log, one JSON object per line.
                             An entry is written at transcription time, then
                             *amended* by appending another line with the same
                             id (never rewritten in place — a truncated write
                             can only lose the amendment, never the text).
  historique/AAAA-MM.md      the human archive, one Markdown file per month,
                             appended once the dictation is finished.

Optionally the raw audio is kept too (`keep_audio`), which is what lets you
recover a dictation whose mic cut out or whose transcription came back partial.
"""
import json
import os
import threading
import time
import uuid
import wave

import numpy as np

_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre",
]

DEFAULT_DIR = "~/Documents/Bavard/historique"


class History:
    """Thread-safe (the dictation worker thread and the menu bar both use it)."""

    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.dir = os.path.expanduser(cfg.get("dir", DEFAULT_DIR))
        self.keep_days = int(cfg.get("keep_days", 90))
        self.keep_audio = bool(cfg.get("keep_audio", False))
        self.menu_entries = int(cfg.get("menu_entries", 10))
        self.journal = os.path.join(self.dir, "journal.jsonl")
        self.audio_dir = os.path.join(self.dir, "audio")
        self._lock = threading.Lock()
        if self.enabled:
            try:
                os.makedirs(self.dir, exist_ok=True)
                self.prune()
                self.recover_pending()
            except OSError as e:
                print(f"Historique désactivé ({e}).")
                self.enabled = False

    # ── writing ──────────────────────────────────────────────────────────────

    def record(self, raw, audio=None, sample_rate=16000):
        """Called the moment the transcription exists. Returns an entry id
        (or None when history is off) to pass to finish()."""
        if not self.enabled:
            return None
        entry = {
            "id": uuid.uuid4().hex[:12],
            "at": time.time(),
            "raw": raw,
            "text": raw,          # best text known so far, replaced by finish()
            "state": "pending",   # pending | ok | not-pasted | failed
        }
        if audio is not None and self.keep_audio and getattr(audio, "size", 0):
            entry["audio"] = self._save_audio(entry, audio, sample_rate)
        self._append(entry)
        return entry["id"]

    def finish(self, entry_id, text=None, state="ok", app=None, error=None,
               mode=None):
        """Amend an entry once the dictation is done (or has failed), and write
        it to the readable monthly archive."""
        if not self.enabled or entry_id is None:
            return
        patch = {"id": entry_id, "state": state}
        if text is not None:
            patch["text"] = text
        if app:
            patch["app"] = app
        if mode:
            patch["mode"] = mode
        if error:
            patch["error"] = str(error)
        self._append(patch)
        self._append_markdown(self.get(entry_id))

    def recover_pending(self):
        """Entries left `pending` by a crash (or a forced quit) never reached
        the Markdown archive — close them at the next start so the raw text
        shows up there too."""
        for e in self.entries():
            if e.get("state") == "pending":
                self.finish(e["id"], state="interrupted")
                print(f"Dictée interrompue récupérée : « {preview(e['text'])} »")

    def _save_audio(self, entry, audio, sample_rate):
        try:
            os.makedirs(self.audio_dir, exist_ok=True)
            name = time.strftime("%Y-%m-%d_%Hh%Mm%S", time.localtime(entry["at"]))
            path = os.path.join(self.audio_dir, f"{name}_{entry['id']}.wav")
            pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sample_rate)
                w.writeframes((pcm * 32767).astype("<i2").tobytes())
            return path
        except Exception as e:
            print(f"Audio de la dictée non conservé ({e}).")
            return None

    def _append(self, record):
        try:
            with self._lock:
                with open(self.journal, "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())  # survive a crash / forced quit
        except OSError as e:
            print(f"Écriture de l'historique impossible ({e}).")

    def _append_markdown(self, entry):
        if not entry or not entry.get("text"):
            return
        t = time.localtime(entry["at"])
        path = os.path.join(self.dir, time.strftime("%Y-%m.md", t))
        try:
            with self._lock:
                new = not os.path.exists(path)
                with open(path, "a") as f:
                    if new:
                        f.write(f"# Historique Bavard — "
                                f"{_MONTHS_FR[t.tm_mon - 1]} {t.tm_year}\n")
                    f.write(f"\n## {time.strftime('%d/%m/%Y %Hh%M', t)}"
                            f"{_suffix(entry)}\n\n{entry['text'].strip()}\n")
        except OSError as e:
            print(f"Archive Markdown de l'historique impossible ({e}).")

    # ── reading ──────────────────────────────────────────────────────────────

    def entries(self):
        """All entries, oldest first, with amendments merged onto their entry."""
        if not self.enabled:
            return []
        merged = {}
        try:
            with open(self.journal) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # torn last line after a hard crash
                    merged.setdefault(rec["id"], {}).update(rec)
        except OSError:
            return []
        return list(merged.values())

    def get(self, entry_id):
        for e in self.entries():
            if e["id"] == entry_id:
                return e
        return None

    def recent(self, n=None):
        """Newest first, empty transcriptions excluded."""
        n = self.menu_entries if n is None else n
        return [e for e in self.entries() if e.get("text")][::-1][:n]

    def month_file(self):
        """The current month's archive, or the newest one that exists."""
        if not self.enabled:
            return None
        path = os.path.join(self.dir, time.strftime("%Y-%m.md"))
        if os.path.exists(path):
            return path
        try:
            months = sorted(f for f in os.listdir(self.dir) if f.endswith(".md"))
        except OSError:
            return None
        return os.path.join(self.dir, months[-1]) if months else None

    # ── retention ────────────────────────────────────────────────────────────

    def prune(self):
        """Drop journal entries and audio files older than keep_days. The
        Markdown archive is never pruned — it is the long-term record."""
        if not self.enabled or self.keep_days <= 0:
            return
        cutoff = time.time() - self.keep_days * 86400
        kept, dropped = [], []
        for e in self.entries():
            (kept if e.get("at", 0) >= cutoff else dropped).append(e)
        for e in dropped:
            if e.get("audio"):
                try:
                    os.remove(e["audio"])
                except OSError:
                    pass
        if not dropped:
            return
        tmp = self.journal + ".tmp"
        try:
            with self._lock:
                with open(tmp, "w") as f:
                    for e in sorted(kept, key=lambda e: e.get("at", 0)):
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                os.replace(tmp, self.journal)
        except OSError as e:
            print(f"Nettoyage de l'historique impossible ({e}).")


def _suffix(entry):
    """Archive heading tail: where the text went, and how it was formatted."""
    state = entry.get("state")
    app = entry.get("app")
    mode = entry.get("mode")
    if state == "ok":
        tail = " · ".join(x for x in (app, mode) if x)
        return f" — {tail}" if tail else ""
    if state == "not-pasted":
        return " — ⚠️ non collé (aucun champ de texte)"
    if state == "failed":
        return f" — ⚠️ échec du collage ({entry.get('error', 'erreur')})"
    return " — ⚠️ interrompue (récupérée au redémarrage)"


def preview(text, width=48):
    """Single-line preview for the menu bar."""
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[:width - 1].rstrip() + "…"
