"""Always-on listening: cuts the mic into utterances with a simple energy detector and hands each
one to a callback. Everything stays on this computer; the callback decides if it is a trigger.
"""
from __future__ import annotations

import collections
import queue
import threading
import time

import numpy as np

from audio import WHISPER_RATE, resample

FRAME_MS = 30


class Segmenter:
    """Pure logic (no audio device) so it can be tested with synthetic audio."""

    def __init__(self, rate: int, on_utterance, min_speech_ms=350, end_silence_ms=650, max_ms=7000, preroll_ms=300):
        self.rate = rate
        self.frame = int(rate * FRAME_MS / 1000)
        self.on_utterance = on_utterance
        self.min_frames = min_speech_ms // FRAME_MS
        self.end_frames = end_silence_ms // FRAME_MS
        self.max_frames = max_ms // FRAME_MS
        self.preroll = collections.deque(maxlen=preroll_ms // FRAME_MS)
        self.noise = 0.003
        self.buf = np.zeros(0, dtype=np.float32)
        self.active: list[np.ndarray] = []
        self.voiced = 0
        self.silent = 0
        self.paused = False

    def feed(self, samples: np.ndarray):
        self.buf = np.concatenate([self.buf, samples.astype(np.float32)])
        while len(self.buf) >= self.frame:
            f, self.buf = self.buf[: self.frame], self.buf[self.frame:]
            self._frame(f)

    def _frame(self, f: np.ndarray):
        rms = float(np.sqrt(np.mean(f * f)) + 1e-9)
        threshold = max(self.noise * 3.0, 0.006)
        speech = rms > threshold
        if not self.active:
            self.noise = 0.97 * self.noise + 0.03 * min(rms, 0.05) if not speech else self.noise
            self.preroll.append(f)
            if speech and not self.paused:
                self.active = list(self.preroll)
                self.voiced, self.silent = 1, 0
            return
        self.active.append(f)
        if speech:
            self.voiced += 1
            self.silent = 0
        else:
            self.silent += 1
        if self.silent >= self.end_frames or len(self.active) >= self.max_frames:
            audio = np.concatenate(self.active)
            enough = self.voiced >= self.min_frames
            self.active, self.voiced, self.silent = [], 0, 0
            self.preroll.clear()
            if enough:
                self.on_utterance(audio)


class AmbientListener:
    def __init__(self, device, handle_text, transcriber):
        self.device = device
        self.handle_text = handle_text
        self.transcriber = transcriber
        self.stream = None
        self.queue: queue.Queue = queue.Queue(maxsize=4)
        self.segmenter = None
        self.running = False

    def start(self):
        if self.running:
            return
        import sounddevice as sd
        info = sd.query_devices(self.device, "input")
        rate = int(info["default_samplerate"])
        self.segmenter = Segmenter(rate, self._utterance)
        self.stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32", device=self.device,
                                     blocksize=int(rate * 0.03), callback=self._callback)
        self.stream.start()
        self.running = True
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self.running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def pause(self, paused: bool):
        if self.segmenter:
            self.segmenter.paused = paused

    def _callback(self, indata, frames, time_info, status):
        try:
            self.segmenter.feed(indata[:, 0])
        except Exception:
            pass

    def _utterance(self, audio: np.ndarray):
        try:
            self.queue.put_nowait(resample(audio, self.segmenter.rate, WHISPER_RATE))
        except queue.Full:
            pass  # falling behind: drop, never block the audio callback

    def _worker(self):
        while self.running:
            try:
                audio = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                t0 = time.time()
                text = self.transcriber.transcribe(audio)
                if text:
                    print(f"[ambient] '{text}' ({time.time() - t0:.2f}s)")
                    self.handle_text(text)
            except Exception as exc:
                print(f"[ambient] {exc}")
