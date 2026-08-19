"""Local STT via faster-whisper (CTranslate2) with Silero VAD gating silence."""
import threading


def _stamp(seconds):
    s = int(seconds)
    return f"[{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}]"


class Transcriber:
    def __init__(self, cfg):
        self.cfg = cfg
        # dictation and meeting transcription can overlap; the model is not
        # thread-safe, so serialize access
        self._lock = threading.Lock()
        engine = cfg.get("engine", "faster-whisper")
        if engine == "mlx-whisper":
            import mlx_whisper  # optional Neural-Engine path
            self._mlx = mlx_whisper
            self._model = None
        else:
            from faster_whisper import WhisperModel
            self._mlx = None
            self._model = WhisperModel(
                cfg.get("model", "base"),
                device="cpu",
                compute_type=cfg.get("compute_type", "int8"),
            )

    def transcribe(self, audio, initial_prompt=None):
        """audio: mono float32 numpy array at 16kHz. Returns text.

        initial_prompt biases the decoder toward the speaker's own vocabulary
        (proper nouns, brands, jargon) so they come back spelled right instead
        of phonetically mangled. Keep it short — a long prompt makes Whisper
        drift and invent text."""
        if audio.size == 0:
            return ""
        with self._lock:
            if self._mlx is not None:
                result = self._mlx.transcribe(
                    audio, language=self.cfg.get("language"),
                    initial_prompt=initial_prompt)
                return result.get("text", "").strip()
            segments, _ = self._model.transcribe(
                audio,
                language=self.cfg.get("language"),
                vad_filter=True,
                beam_size=1,
                initial_prompt=initial_prompt,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe_file(self, path, on_progress=None):
        """Long-form transcription of an audio file (meeting recordings).

        Returns (timestamped, plain): one "[HH:MM:SS] text" line per segment,
        and the plain text without timestamps. on_progress(fraction) is called
        as segments stream in (faster-whisper path only)."""
        with self._lock:
            if self._mlx is not None:
                result = self._mlx.transcribe(path, language=self.cfg.get("language"))
                text = result.get("text", "").strip()
                return text, text
            segments, info = self._model.transcribe(
                path,
                language=self.cfg.get("language"),
                vad_filter=True,
                beam_size=1,
            )
            lines, plain = [], []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                lines.append(f"{_stamp(seg.start)} {text}")
                plain.append(text)
                if on_progress and info.duration:
                    on_progress(min(1.0, seg.end / info.duration))
            return "\n".join(lines), " ".join(plain)
