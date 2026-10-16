"""The engine: voices, push-to-talk, hotkeys, talking to the plugin. No UI here."""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from intent import IntentResolver, apply_nudges
from library import Library
from osc_client import PluginLink
from paths import DATA_DIR, resource, whisper_model_path
from voiceparams import PARAMS, clamp_preset


class Engine:
    def __init__(self, settings: dict):
        self.settings = settings
        self.link = PluginLink("127.0.0.1", settings["osc_port"], settings["osc_reply_port"])
        presets = json.loads(resource("presets.json").read_text(encoding="utf-8"))
        self.library = Library(DATA_DIR / "library.json", presets)
        self.resolver = IntentResolver(DATA_DIR / "cache.json", settings["ai_model"],
                                       presets_path=resource("presets.json"), api_key=settings.get("api_key", ""))
        self.on = False
        self.current_id: str | None = None
        self.current_params: dict = {}
        self.status = "Ready"
        self.plugin_ok = False
        self.listeners: list[Callable[[], None]] = []
        self.recorder = None
        self.transcriber = None
        self.hotkeys = None
        self._busy = threading.Lock()

    # ---------- notifications ----------
    def changed(self, status: str | None = None):
        if status is not None:
            self.status = status
            print(f"[status] {status}")
        for fn in list(self.listeners):
            try:
                fn()
            except Exception as exc:
                print(f"[ui] listener error: {exc}")

    # ---------- voice actions ----------
    def apply_voice(self, voice_id: str):
        v = self.library.get(voice_id)
        if not v:
            return
        self.current_id, self.current_params, self.on = voice_id, v["params"], True
        self.link.preset(v["params"])
        self.changed(f"Active: {v['name']}")

    def apply_params(self, params: dict, label: str):
        self.current_params, self.on = clamp_preset(params), True
        self.link.preset(self.current_params)
        self.changed(f"Active: {label}")

    def clear(self):
        self.on = False
        self.link.bypass(True)
        self.changed("Normal voice")

    def set_on(self, on: bool):
        if on and self.current_id:
            self.apply_voice(self.current_id)
        elif on and self.current_params:
            self.apply_params(self.current_params, "custom")
        elif on:
            self.changed("Pick a voice first")
        else:
            self.clear()

    def create(self, text: str) -> str:
        """Text from the box or from speech. Returns a short result for the UI."""
        action = self.resolver.resolve(text, self.current_params or None)
        if action.kind == "bypass":
            self.clear()
        elif action.kind == "nudge":
            new = apply_nudges(self.current_params, action.nudges)
            if self.current_id:
                tw = self.library.data["tweaks"].setdefault(self.current_id, {})
                tw.update({k: new[k] for k, _ in action.nudges})
                self.library.save()
            cur = self.library.get(self.current_id) if self.current_id else None
            self.apply_params(new, cur['name'] if cur else action.label)
        elif action.kind == "preset" and action.source == "keyword" and action.label in self.library.presets:
            self.apply_voice(action.label)
        elif action.kind == "preset":
            vid = self.library.add_custom(action.label or text, action.preset)
            self.apply_voice(vid)
        else:
            msg = "Couldn't match that voice" + ("" if self.resolver.has_ai else " (add an AI key in Settings for any voice)")
            self.changed(msg)
        return self.status

    def set_macro(self, voice_id: str, macro: str, value: float):
        params = self.library.set_macro(voice_id, macro, value)
        if voice_id == self.current_id and self.on:
            self.current_params = params
            self.link.preset(params)
        self.changed()

    def reset_voice(self, voice_id: str):
        self.library.reset_tweaks(voice_id)
        if voice_id == self.current_id and self.on:
            self.apply_voice(voice_id)
        else:
            self.changed()

    def toggle_fav(self, voice_id: str):
        self.library.toggle_fav(voice_id)
        self.changed()

    def delete_voice(self, voice_id: str):
        self.library.delete_custom(voice_id)
        if voice_id == self.current_id:
            self.current_id = None
            self.clear()
        else:
            self.changed()

    def save_slot(self, n: int):
        if not self.current_id:
            self.changed(f"Slot {n}: pick a voice first")
            return
        self.library.set_slot(n, self.current_id)
        self.changed(f"Saved to slot {n}")

    def recall_slot(self, n: int):
        vid = self.library.slot(n)
        if vid:
            self.apply_voice(vid)
        else:
            self.changed(f"Slot {n} is empty")

    # ---------- push to talk ----------
    def ptt_down(self):
        if self.recorder is None or not self._busy.acquire(blocking=False):
            return
        self.link.mute(True)
        try:
            self.recorder.start()
        except Exception as exc:
            self.link.mute(False)
            self._busy.release()
            self.changed(f"Mic error: {exc}")
            return
        self.changed("Listening...")

    def ptt_up(self):
        if self.recorder is None:
            return
        audio = self.recorder.stop()
        self.link.mute(False)
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio):
        try:
            self.changed("Thinking...")
            t0 = time.time()
            text = self.transcriber.transcribe(audio)
            print(f"[heard]  '{text}' ({time.time() - t0:.2f}s)")
            if text:
                self.create(text)
            else:
                self.changed("Didn't catch that")
        except Exception as exc:
            self.changed(f"Error: {exc}")
        finally:
            if self._busy.locked():
                self._busy.release()

    # ---------- startup ----------
    def start_audio_and_keys(self):
        from audio import Recorder, Transcriber
        from hotkeys import HotkeyManager

        dev = self.settings.get("input_device") or None
        if isinstance(dev, str) and dev.isdigit():
            dev = int(dev)
        try:
            self.recorder = Recorder(dev)
            print(f"[audio]  mic: {self.recorder.device_name}")
        except Exception as exc:
            self.changed(f"Mic error: {exc}")
        lang = self.settings.get("language", "es")
        self.transcriber = Transcriber(whisper_model_path(self.settings.get("whisper_model", "base")), lang)

        hk = self.settings["hotkeys"]
        self.hotkeys = HotkeyManager()
        self.hotkeys.bind(hk["push_to_talk"], self.ptt_down, self.ptt_up)
        self.hotkeys.bind(hk["clear"], self.clear)
        for n in (1, 2, 3):
            self.hotkeys.bind(hk[f"slot_{n}"], lambda n=n: self.recall_slot(n))
            self.hotkeys.bind(hk[f"save_{n}"], lambda n=n: self.save_slot(n))
        try:
            self.hotkeys.start()
        except Exception as exc:
            self.changed(f"Hotkeys unavailable: {exc}")

        threading.Thread(target=self._watch_plugin, daemon=True).start()

    def _watch_plugin(self):
        while True:
            ok = self.link.ping(timeout=0.8)
            if ok != self.plugin_ok:
                self.plugin_ok = ok
                self.changed()
            time.sleep(5)

    def stop(self):
        if self.hotkeys:
            self.hotkeys.stop()

    # ---------- for the UI ----------
    def snapshot(self) -> dict:
        voices = self.library.voices()
        names = {v["id"]: v["name"] for v in voices}
        return {
            "on": self.on,
            "currentId": self.current_id,
            "status": self.status,
            "pluginOk": self.plugin_ok,
            "hasAi": self.resolver.has_ai,
            "voices": [{k: v[k] for k in ("id", "name", "color", "custom", "mono", "fav", "macros")} for v in voices],
            "slots": [{"n": n, "name": names.get(self.library.slot(n) or "", "Empty")} for n in (1, 2, 3)],
            "hotkeys": self.settings["hotkeys"],
        }
