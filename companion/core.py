"""The engine: voices, moods, sounds, push-to-talk, always-on listening, hotkeys. No UI here."""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from intent import IntentResolver, apply_nudges
from library import Library
from osc_client import PluginLink
from paths import DATA_DIR, resource, whisper_model_path
from sounds import BUILTIN, SoundLibrary, wav_duration
from triggers import TriggerMatcher
from voiceparams import clamp_preset


def now_ms() -> int:
    return int(time.time() * 1000)


class Engine:
    def __init__(self, settings: dict):
        self.settings = settings
        self.link = PluginLink("127.0.0.1", settings["osc_port"], settings["osc_reply_port"])
        self.presets = json.loads(resource("presets.json").read_text(encoding="utf-8"))
        self.library = Library(DATA_DIR / "library.json", self.presets)
        self.resolver = IntentResolver(DATA_DIR / "cache.json", settings["ai_model"],
                                       presets_path=resource("presets.json"), api_key=settings.get("api_key", ""))
        self.sounds = SoundLibrary(DATA_DIR / "sounds")
        self.sounds.freesound_key = settings.get("freesound_key", "")
        self.matcher = TriggerMatcher(self.presets, self.sounds)

        self.on = False
        self.current_id: str | None = None
        self.current_params: dict = {}
        self.status = "Ready"
        self.plugin_ok = False
        self.overlay = {"kind": "idle", "title": "Instant Voicemod", "sub": "", "until": 0, "start": 0}
        self.listeners: list[Callable[[], None]] = []

        self.recorder = None
        self.transcriber = None
        self.hotkeys = None
        self.ambient = None
        self.audio_engine = None
        self._busy = threading.Lock()
        self._temp_timer: threading.Timer | None = None
        self._before_temp: tuple | None = None

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

    def show(self, kind: str, title: str, sub: str = "", seconds: float = 0):
        t = now_ms()
        self.overlay = {"kind": kind, "title": title, "sub": sub, "start": t,
                        "until": t + int(seconds * 1000) if seconds else 0}

    def idle_overlay(self):
        if self.on and self.current_id:
            v = self.library.get(self.current_id)
            self.show("voice", v["name"] if v else "Voice on", "voice on")
        else:
            listening = self.ambient is not None and self.ambient.running
            self.show("idle", "Instant Voicemod", "listening for triggers" if listening else "ready")

    # ---------- voice actions (persistent) ----------
    def apply_voice(self, voice_id: str):
        v = self.library.get(voice_id)
        if not v:
            return
        self._cancel_temp()
        self.current_id, self.current_params, self.on = voice_id, v["params"], True
        self.link.preset(v["params"])
        self.show("mood" if v.get("category") == "mood" else "voice", v["name"], "voice on")
        self.changed(f"Active: {v['name']}")

    def apply_params(self, params: dict, label: str):
        self._cancel_temp()
        self.current_params, self.on = clamp_preset(params), True
        self.link.preset(self.current_params)
        self.show("voice", label, "voice on")
        self.changed(f"Active: {label}")

    def clear(self):
        self._cancel_temp()
        self.on = False
        self.link.bypass(True)
        self.show("idle", "Normal voice", "", 2)
        self.changed("Normal voice")

    def set_on(self, on: bool):
        if on and self.current_id:
            self.apply_voice(self.current_id)
        elif on and self.current_params:
            self.apply_params(self.current_params, "Custom")
        elif on:
            self.changed("Pick a voice first")
        else:
            self.clear()

    # ---------- temporary effects (spoken in a meeting, then they cut) ----------
    def apply_temporary(self, params: dict, label: str, kind: str = "mood"):
        secs = float(self.settings.get("temp_seconds", 6))
        if self._before_temp is None:
            self._before_temp = (self.on, self.current_id, dict(self.current_params))
        if self._temp_timer:
            self._temp_timer.cancel()
        self.link.preset(clamp_preset(params))
        self.show(kind, label, f"for {int(secs)} s", secs)
        self.changed(f"{label} for {int(secs)} s")
        self._temp_timer = threading.Timer(secs, self._end_temp)
        self._temp_timer.daemon = True
        self._temp_timer.start()

    def _end_temp(self):
        prev, self._before_temp, self._temp_timer = self._before_temp, None, None
        if prev is None:
            return
        was_on, cid, params = prev
        if was_on and params:
            self.link.preset(params)
        else:
            self.link.bypass(True)
        self.idle_overlay()
        self.changed("Back to " + ("your voice" if not was_on else "previous voice"))

    def _cancel_temp(self):
        if self._temp_timer:
            self._temp_timer.cancel()
        self._temp_timer, self._before_temp = None, None

    # ---------- sounds ----------
    def play_sound(self, sound_id: str, label: str | None = None):
        path = self.sounds.path(sound_id)
        if not path.exists():
            self.changed("Sound not found")
            return
        name = label or BUILTIN.get(sound_id, (sound_id,))[0]
        self.link.sound(str(path))
        dur = wav_duration(path)
        self.show("sound", name, "playing", dur)
        self.changed(f"Playing: {name}")

    def play_online(self, phrase: str):
        if not self.sounds.freesound_key:
            self.show("error", "No sound for that", "add a Freesound key in Settings", 4)
            self.changed(f"No built-in sound for '{phrase}'. Add a Freesound key in Settings for any sound")
            return
        self.show("thinking", "Finding sound", phrase, 0)
        self.changed(f"Searching sound: {phrase}")

        def go():
            try:
                query = self.resolver.sound_query(phrase) if self.resolver.has_ai else phrase
                found = self.sounds.find_online(query)
                if found:
                    self.play_sound(found[0], phrase[:1].upper() + phrase[1:])
                else:
                    self.show("error", "No sound found", phrase, 3)
                    self.changed(f"No sound found for '{phrase}'")
            except Exception as exc:
                self.show("error", "Sound search failed", str(exc)[:60], 4)
                self.changed(f"Sound search failed: {exc}")
        threading.Thread(target=go, daemon=True).start()

    # ---------- text from anywhere ----------
    def handle_text(self, text: str, source: str = "text") -> str:
        """source: 'text' (typed), 'ptt' (shortcut), 'ambient' (always-on listening)."""
        ambient = source == "ambient"
        trig = self.matcher.ambient(text) if ambient else self.matcher.direct(text)
        if trig.kind == "none":
            return self.status
        if trig.kind == "clear":
            self.clear()
        elif trig.kind == "sound":
            self.play_sound(trig.value)
        elif trig.kind == "online_sound":
            self.play_online(trig.value)
        elif trig.kind == "mood":
            if ambient:
                v = self.library.get(trig.value)
                self.apply_temporary(v["params"], v["name"], "mood")
            else:
                self.apply_voice(trig.value)
        elif trig.kind == "voice":
            if ambient:
                action = self.resolver.resolve(trig.value, None)
                if action.kind == "preset":
                    label = self.presets.get(action.label, {}).get("name", action.label)
                    self.apply_temporary(action.preset, label[:1].upper() + label[1:], "voice")
            else:
                self.create(trig.value)
        return self.status

    def create(self, text: str) -> str:
        """A voice from a description (typed or said with the shortcut). Persistent."""
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
            self.apply_params(new, cur["name"] if cur else action.label)
        elif action.kind == "preset" and action.source == "keyword" and action.label in self.library.presets:
            self.apply_voice(action.label)
        elif action.kind == "preset":
            self.show("thinking", "Creating voice", text, 0)
            vid = self.library.add_custom(action.label or text, action.preset)
            self.apply_voice(vid)
        else:
            msg = "Couldn't match that voice" + ("" if self.resolver.has_ai else " (add an AI key in Settings for any voice)")
            self.show("error", "No match", text, 3)
            self.changed(msg)
        return self.status

    # ---------- library edits ----------
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
        if self.ambient:
            self.ambient.pause(True)
        self.link.mute(True)
        try:
            self.recorder.start()
        except Exception as exc:
            self.link.mute(False)
            self._busy.release()
            self.changed(f"Mic error: {exc}")
            return
        self.show("listening", "Listening...", "say a voice, mood or sound")
        self.changed("Listening...")

    def ptt_up(self):
        if self.recorder is None:
            return
        audio = self.recorder.stop()
        self.link.mute(False)
        if self.ambient:
            self.ambient.pause(False)
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio):
        try:
            self.show("thinking", "Thinking...", "")
            self.changed("Thinking...")
            text = self.transcriber.transcribe(audio)
            print(f"[heard]  '{text}'")
            if text:
                self.handle_text(text, "ptt")
            else:
                self.show("error", "Didn't catch that", "", 2)
                self.changed("Didn't catch that")
        except Exception as exc:
            self.changed(f"Error: {exc}")
        finally:
            if self._busy.locked():
                self._busy.release()

    # ---------- startup ----------
    def start_services(self):
        threading.Thread(target=self.sounds.ensure_builtin, daemon=True).start()

        if self.settings.get("route", "cable") == "cable":
            self.start_route()

        from audio import Recorder, Transcriber
        dev = self.settings.get("input_device") or None
        try:
            self.recorder = Recorder(dev)
            print(f"[audio]  mic: {self.recorder.device_name}")
        except Exception as exc:
            self.changed(f"Mic error: {exc}")
        self.transcriber = Transcriber(whisper_model_path(self.settings.get("whisper_model", "base")),
                                       self.settings.get("language", "es"))
        self.set_ambient(self.settings.get("ambient", True))
        self.start_hotkeys()
        threading.Thread(target=self._watch_plugin, daemon=True).start()
        self.idle_overlay()

    def start_route(self):
        from audio_engine import AudioEngine
        if self.audio_engine is None:
            self.audio_engine = AudioEngine(self.settings, lambda: self.changed())
        self.audio_engine.start()

    def stop_route(self):
        if self.audio_engine:
            self.audio_engine.stop()

    def set_ambient(self, enabled: bool):
        from ambient import AmbientListener
        if enabled and self.transcriber:
            if self.ambient is None:
                self.ambient = AmbientListener(self.settings.get("input_device") or None,
                                               lambda t: self.handle_text(t, "ambient"), self.transcriber)
            try:
                self.ambient.start()
            except Exception as exc:
                self.changed(f"Listening unavailable: {exc}")
        elif self.ambient:
            self.ambient.stop()
        self.idle_overlay()
        self.changed()

    def start_hotkeys(self):
        from hotkeys import HotkeyManager
        hk = self.settings["hotkeys"]
        self.hotkeys = HotkeyManager()
        self.hotkeys.bind(hk["push_to_talk"], self.ptt_down, self.ptt_up)
        self.hotkeys.bind(hk["clear"], self.clear)
        for n in (1, 2, 3):
            self.hotkeys.bind(hk[f"slot_{n}"], lambda n=n: self.recall_slot(n))
            self.hotkeys.bind(hk[f"save_{n}"], lambda n=n: self.save_slot(n))
        for key, sid in (self.settings.get("sound_hotkeys") or {}).items():
            self.hotkeys.bind(key, lambda sid=sid: self.play_sound(sid))
        try:
            self.hotkeys.start()
        except Exception as exc:
            self.changed(f"Hotkeys unavailable: {exc}")

    def _watch_plugin(self):
        while True:
            ok = self.link.ping(timeout=0.8)  # also the engine's heartbeat
            if ok != self.plugin_ok:
                self.plugin_ok = ok
                self.changed()
            time.sleep(5)

    def stop(self):
        if self.hotkeys:
            self.hotkeys.stop()
        if self.ambient:
            self.ambient.stop()
        self.stop_route()

    # ---------- for the UI ----------
    def snapshot(self) -> dict:
        voices = self.library.voices()
        names = {v["id"]: v["name"] for v in voices}
        eng = self.audio_engine
        return {
            "on": self.on,
            "currentId": self.current_id,
            "status": self.status,
            "pluginOk": self.plugin_ok,
            "hasAi": self.resolver.has_ai,
            "hasFreesound": bool(self.sounds.freesound_key),
            "route": self.settings.get("route", "cable"),
            "engine": {"state": eng.state if eng else "stopped", "detail": eng.detail if eng else ""},
            "ambient": bool(self.ambient and self.ambient.running),
            "tempSeconds": self.settings.get("temp_seconds", 6),
            "voices": [{**{k: v[k] for k in ("id", "name", "color", "custom", "mono", "fav", "macros")},
                        "mood": self.presets.get(v["id"], {}).get("category") == "mood"} for v in voices],
            "sounds": self.sounds.list(),
            "slots": [{"n": n, "name": names.get(self.library.slot(n) or "", "Empty")} for n in (1, 2, 3)],
            "hotkeys": self.settings["hotkeys"],
        }

    def overlay_state(self) -> dict:
        o = dict(self.overlay)
        if o["until"] and now_ms() > o["until"]:
            self.idle_overlay()
            o = dict(self.overlay)
        o["now"] = now_ms()
        o["show"] = bool(self.settings.get("overlay", True))
        return o
