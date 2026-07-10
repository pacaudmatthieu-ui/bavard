"""Mic capture: continuous 500ms pre-roll ring buffer + on-demand recording."""
import collections
import threading

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate=16000, channels=1, preroll_ms=500, blocksize=320,
                 keep_open=True):
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        # keep_open=False opens the mic only while recording (no orange mic
        # indicator when idle) at the cost of the pre-roll buffer.
        self.keep_open = keep_open
        preroll_blocks = max(1, int(sample_rate * preroll_ms / 1000 / blocksize))
        self._preroll = collections.deque(maxlen=preroll_blocks)
        self._chunks = []
        self._recording = False
        self.level = 0.0
        self._last = None
        self._lock = threading.Lock()
        self._stream = self._make_stream() if keep_open else None

    def _make_stream(self):
        return sd.InputStream(
            samplerate=self.sample_rate, channels=self.channels, dtype="float32",
            blocksize=self.blocksize, callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        block = indata.copy()
        with self._lock:
            if self._recording:
                self._chunks.append(block)
                self._last = block  # most recent block, for the spectrum UI
                self.level = float(np.sqrt((block ** 2).mean()))  # RMS for the waveform UI
            else:
                self._preroll.append(block)

    def bands(self, n):
        """Log-spaced frequency band magnitudes of the latest block (for the
        equalizer UI). Raw values — the caller normalizes/smooths them."""
        with self._lock:
            block = self._last
        if block is None:
            return [0.0] * n
        x = block.flatten()
        mag = np.abs(np.fft.rfft(x * np.hanning(x.size)))
        edges = np.logspace(np.log10(3), np.log10(len(mag) - 1), n + 1)
        out = []
        for i in range(n):
            lo, hi = int(edges[i]), max(int(edges[i]) + 1, int(edges[i + 1]))
            out.append(float(mag[lo:hi].mean()))
        return out

    def start_stream(self):
        if self.keep_open:
            self._stream.start()

    def start(self):
        """Begin recording; the pre-roll buffer is prepended so the first word isn't clipped."""
        with self._lock:
            self._chunks = list(self._preroll)
            self._preroll.clear()
            self._last = None
            self._recording = True
        if not self.keep_open and self._stream is None:
            self._stream = self._make_stream()
            self._stream.start()

    def stop(self):
        """Stop recording and return mono float32 audio."""
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not self.keep_open and self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).flatten()

    def close(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
