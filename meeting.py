"""Meeting mode: long-form recording straight to a WAV file, then full
transcription (transcribe.py) and an LLM-written compte rendu — all local.

Audio is written to disk as it arrives (int16 mono 16 kHz ≈ 115 MB/h), so a
two-hour meeting never sits in RAM and a crash loses nothing already written.
"""
import queue
import threading
import time
import wave

import requests
import sounddevice as sd

import devices


class MeetingRecorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.active = False
        self.mic_name = ""
        self._stream = None
        self._wav = None
        self._q = None
        self._writer = None
        self._writer_stop = False
        self._t0 = 0.0

    def start(self, wav_path):
        index, name, missing = devices.resolve_input_device()
        if missing:
            print(f"Micro choisi introuvable — bascule sur « {name} »")
        self.mic_name = name
        self._wav = wave.open(wav_path, "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.sample_rate)
        self._q = queue.Queue()
        self._writer_stop = False
        self._writer = threading.Thread(target=self._drain, daemon=True)
        self._writer.start()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="int16",
            device=index, callback=self._callback,
        )
        self._stream.start()
        self._t0 = time.time()
        self.active = True
        print(f"Enregistrement réunion démarré ({name}) → {wav_path}")

    def _callback(self, indata, frames, time_info, status):
        self._q.put(indata.tobytes())

    def _drain(self):
        while True:
            try:
                data = self._q.get(timeout=0.5)
            except queue.Empty:
                if self._writer_stop:
                    return
                continue
            self._wav.writeframes(data)

    def elapsed(self):
        return time.time() - self._t0 if self.active else 0.0

    def stop(self):
        """Stop and flush; returns the recording duration in seconds."""
        duration = self.elapsed()
        self.active = False
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._writer_stop = True
        self._writer.join(timeout=5)
        self._wav.close()
        return duration


def fmt_duration(seconds):
    m = int(seconds) // 60
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


# ── compte rendu ─────────────────────────────────────────────────────────────

_CHUNK_WORDS = 1400  # ≈ 2500 French tokens, safe inside an 8k context

_NOTES_PROMPT = (
    "Voici la partie {i}/{n} de la transcription brute d'une réunion "
    "(reconnaissance vocale, ponctuation approximative). Rédige des notes "
    "factuelles et concises, en puces : sujets abordés, informations et "
    "chiffres importants, décisions prises, actions à faire (qui / quoi / "
    "quand si mentionné). N'invente rien, ne commente pas.\n\n{text}"
)

_REPORT_PROMPT = (
    "Voici {source} d'une réunion du {date} (durée : {duration}). Rédige son "
    "compte rendu en français, en Markdown, avec exactement cette structure :\n"
    "# Compte rendu — réunion du {date}\n"
    "## L'essentiel\n(3 à 5 phrases)\n"
    "## Points abordés\n(puces)\n"
    "## Décisions\n(puces ; « Aucune » si rien)\n"
    "## Actions à suivre\n(cases à cocher « - [ ] » ; « Aucune » si rien)\n\n"
    "Base-toi uniquement sur le contenu fourni, n'invente rien.\n\n{text}"
)


def _ollama(cfg, prompt, timeout=600):
    r = requests.post(
        f"{cfg.get('base_url', 'http://localhost:11434').rstrip('/')}/api/generate",
        json={
            "model": cfg["model"],
            "prompt": prompt,
            "stream": False,
            "think": False,
            # long transcripts need more than Ollama's default 4k context
            "options": {"temperature": 0.3, "num_ctx": 8192},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()


def write_summary(llm_cfg, transcript, date_str, duration_s, on_progress=None):
    """Full transcript -> structured French compte rendu (Markdown).

    Long transcripts are summarized chunk by chunk (map), then merged into the
    final report (reduce) so everything fits the local model's context."""
    words = transcript.split()
    duration = fmt_duration(duration_s)
    if len(words) <= _CHUNK_WORDS:
        return _ollama(llm_cfg, _REPORT_PROMPT.format(
            source="la transcription", date=date_str, duration=duration,
            text=transcript,
        ))
    chunks = [
        " ".join(words[i:i + _CHUNK_WORDS])
        for i in range(0, len(words), _CHUNK_WORDS)
    ]
    notes = []
    for i, chunk in enumerate(chunks, 1):
        if on_progress:
            on_progress(i, len(chunks))
        notes.append(_ollama(llm_cfg, _NOTES_PROMPT.format(
            i=i, n=len(chunks), text=chunk,
        )))
    return _ollama(llm_cfg, _REPORT_PROMPT.format(
        source="les notes chronologiques", date=date_str, duration=duration,
        text="\n\n".join(notes),
    ))
