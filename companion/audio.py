"""Push-to-talk recording and local Whisper transcription."""
from __future__ import annotations

import threading
import time

import numpy as np

WHISPER_RATE = 16000


class Recorder:
    """Records the mic while the hotkey is held. Uses the device's native rate, resamples to 16 kHz."""

    def __init__(self, device=None):
        import sounddevice as sd
        self.sd = sd
        self.device = device
        info = sd.query_devices(device, "input")
        self.rate = int(info["default_samplerate"])
        self.device_name = info["name"]
        self._frames: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._stream is not None:
                return
            self._frames = []
            self._stream = self.sd.InputStream(
                samplerate=self.rate, channels=1, dtype="float32",
                device=self.device, callback=self._callback,
            )
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        self._frames.append(indata[:, 0].copy())

    def stop(self) -> np.ndarray:
        with self._lock:
            if self._stream is None:
                return np.zeros(0, dtype=np.float32)
            self._stream.stop()
            self._stream.close()
            self._stream = None
            audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.float32)
        return resample(audio, self.rate, WHISPER_RATE)


def resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or audio.size == 0:
        return audio.astype(np.float32)
    n = int(round(audio.size * dst / src))
    x_old = np.linspace(0.0, 1.0, audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


class Transcriber:
    """faster-whisper, loaded in the background so startup is instant."""

    def __init__(self, model_size: str = "small", language: str | None = "es"):
        self.model_size = model_size
        self.language = None if language in (None, "", "auto") else language
        self._model = None
        self._ready = threading.Event()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        from faster_whisper import WhisperModel
        t0 = time.time()
        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        print(f"[whisper] '{self.model_size}' ready in {time.time() - t0:.1f}s")
        self._ready.set()

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size < WHISPER_RATE * 0.3:
            return ""
        self._ready.wait()
        segments, _ = self._model.transcribe(
            audio, language=self.language, beam_size=1, vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()
