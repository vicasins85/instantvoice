"""Runs the bundled audio engine (mic -> effect -> virtual cable) for people without Wave Link."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from paths import DATA_DIR, resource

# Output names of the virtual cables we know, in order of preference.
CABLE_HINTS = ["CABLE Input", "VB-Audio Virtual Cable", "BlackHole 2ch", "BlackHole", "VB-Cable"]
CABLE_SETUP_URL = {
    "win32": "https://vb-audio.com/Cable/",
    "darwin": "https://existential.audio/blackhole/",
}


def engine_path() -> Path | None:
    if sys.platform == "darwin":
        p = resource("engine", "InstantVoiceEngine.app", "Contents", "MacOS", "InstantVoiceEngine")
    elif sys.platform == "win32":
        p = resource("engine", "InstantVoiceEngine.exe")
    else:
        p = resource("engine", "InstantVoiceEngine")
    return p if p.exists() else None


def _run_once(args: list[str], timeout: float = 15) -> dict:
    exe = engine_path()
    if exe is None:
        return {"status": "error", "error": "engine_missing"}
    report = Path(tempfile.gettempdir()) / f"iv_engine_{time.time_ns()}.json"
    flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW
    try:
        subprocess.run([str(exe), *args, "--report", str(report)], timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        return json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "error": "engine_failed", "message": str(exc)}
    finally:
        report.unlink(missing_ok=True)


def list_devices() -> dict:
    return _run_once(["--list"])


def find_cable(outputs: list[str]) -> str:
    for hint in CABLE_HINTS:
        for name in outputs:
            if hint.lower() in name.lower():
                return name
    return ""


class AudioEngine:
    """Keeps the engine process running; restarts it if it dies."""

    def __init__(self, settings: dict, on_change):
        self.settings = settings
        self.on_change = on_change
        self.proc: subprocess.Popen | None = None
        self.state = "stopped"        # stopped | running | cable_missing | error | engine_missing
        self.detail = ""
        self.input_name = ""
        self.output_name = ""
        self.devices: dict = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop.clear()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._kill()
        self._set("stopped")

    def restart(self):
        self._kill()
        self.start()

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except Exception:
                self.proc.kill()
        self.proc = None

    def _set(self, state: str, detail: str = ""):
        changed = (state, detail) != (self.state, self.detail)
        self.state, self.detail = state, detail
        if changed:
            self.on_change()

    def refresh_devices(self) -> dict:
        self.devices = list_devices()
        return self.devices

    def _loop(self):
        backoff = 2
        while not self._stop.is_set():
            if engine_path() is None:
                self._set("engine_missing", "The audio engine is not part of this build")
                return
            devs = self.refresh_devices()
            outputs = devs.get("outputs", [])
            out = self.settings.get("output_device") or find_cable(outputs)
            if not out or not any(out.lower() in o.lower() for o in outputs):
                self._set("cable_missing", CABLE_SETUP_URL.get(sys.platform, ""))
                self._stop.wait(10)  # the person may be installing it right now
                continue
            mic = self.settings.get("input_device") or ""
            report = DATA_DIR / "engine.json"
            report.unlink(missing_ok=True)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            self.proc = subprocess.Popen([str(engine_path()), "--in", mic, "--out", out, "--report", str(report),
                                          "--heartbeat"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
            started = time.time()
            while not report.exists() and self.proc.poll() is None and time.time() - started < 10:
                time.sleep(0.2)
            try:
                info = json.loads(report.read_text(encoding="utf-8"))
            except Exception:
                info = {"status": "error", "message": "no report"}
            if info.get("status") == "running":
                self.input_name, self.output_name = info.get("input", ""), info.get("output", "")
                self._set("running", f"{self.input_name} -> {self.output_name}")
                backoff = 2
                while not self._stop.is_set() and self.proc and self.proc.poll() is None:
                    time.sleep(0.5)
                if self._stop.is_set():
                    return
                self._set("error", "Audio engine stopped, restarting...")
            else:
                self._kill()
                self._set("error", info.get("message", "Could not start audio"))
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30)
