"""Instant Voicemod desktop app: window + menu bar / tray icon + start at login."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from core import Engine
from paths import FROZEN, load_settings, resource, save_settings

APP_NAME = "Instant Voicemod"
BUNDLE_ID = "com.instantvoice.app"


# ---------- start at login ----------
def set_autostart(enabled: bool):
    if not FROZEN:
        return  # only the installed app registers itself
    try:
        if sys.platform == "darwin":
            agent = Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"
            if not enabled:
                agent.unlink(missing_ok=True)
                return
            app_path = Path(sys.executable).resolve().parents[2]  # .../Instant Voicemod.app
            agent.parent.mkdir(parents=True, exist_ok=True)
            agent.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{BUNDLE_ID}</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/open</string><string>-a</string><string>{app_path}</string>
    <string>--args</string><string>--hidden</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
""", encoding="utf-8")
        elif sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                 winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, "InstantVoicemod", 0, winreg.REG_SZ, f'"{sys.executable}" --hidden')
            else:
                try:
                    winreg.DeleteValue(key, "InstantVoicemod")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
    except Exception as exc:
        print(f"[autostart] {exc}")


# ---------- bridge exposed to the window's JavaScript ----------
class Api:
    def __init__(self, engine: Engine, settings: dict):
        self._engine = engine
        self._settings = settings

    def state(self):
        return self._engine.snapshot()

    def pick(self, voice_id):
        self._engine.apply_voice(voice_id)

    def toggle(self, on):
        self._engine.set_on(bool(on))

    def clear(self):
        self._engine.clear()

    def create(self, text):
        return self._engine.create(str(text))

    def macro(self, voice_id, name, value):
        self._engine.set_macro(voice_id, name, float(value))

    def reset(self, voice_id):
        self._engine.reset_voice(voice_id)

    def fav(self, voice_id):
        self._engine.toggle_fav(voice_id)

    def remove(self, voice_id):
        self._engine.delete_voice(voice_id)

    def slot_save(self, n):
        self._engine.save_slot(int(n))

    def slot_recall(self, n):
        self._engine.recall_slot(int(n))

    def get_settings(self):
        s = self._settings
        return {"hasKey": bool(s.get("api_key")), "autostart": s.get("autostart", True),
                "language": s.get("language", "es"), "hotkeys": s["hotkeys"]}

    def save_settings(self, data):
        s = self._settings
        key = (data.get("apiKey") or "").strip()
        if key:
            s["api_key"] = key
            self._engine.resolver.set_api_key(key)
        if data.get("removeKey"):
            s["api_key"] = ""
            self._engine.resolver.set_api_key("")
        if "autostart" in data:
            s["autostart"] = bool(data["autostart"])
            set_autostart(s["autostart"])
        if data.get("language") in ("es", "en", "auto"):
            s["language"] = data["language"]
            if self._engine.transcriber:
                self._engine.transcriber.language = None if s["language"] == "auto" else s["language"]
        save_settings(s)
        self._engine.changed("Settings saved")
        return self.get_settings()


# ---------- tray / menu bar ----------
def make_tray(show, engine: Engine, quit_app):
    try:
        import pystray
        from tray import tray_image
    except Exception as exc:
        print(f"[tray] unavailable: {exc}")
        return None
    icon = pystray.Icon("InstantVoicemod", tray_image(False), APP_NAME, menu=pystray.Menu(
        pystray.MenuItem("Open Instant Voicemod", lambda: show(), default=True),
        pystray.MenuItem("Normal voice", lambda: engine.clear()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda: quit_app()),
    ))

    def refresh():
        try:
            icon.icon = tray_image(engine.on, engine.status)
            icon.title = f"{APP_NAME}: {engine.status}"
        except Exception:
            pass
    engine.listeners.append(refresh)
    return icon


def run(hidden: bool = False):
    import webview

    settings = load_settings()
    engine = Engine(settings)
    api = Api(engine, settings)
    if settings.get("autostart", True):
        set_autostart(True)

    window = webview.create_window(
        APP_NAME, url=str(resource("ui", "index.html")), js_api=api,
        width=1220, height=800, min_size=(860, 600), hidden=hidden, background_color="#0C0E16",
    )
    state = {"quitting": False}

    def show():
        window.show()
        try:
            window.restore()
        except Exception:
            pass

    def quit_app():
        state["quitting"] = True
        engine.stop()
        if tray:
            tray.stop()
        window.destroy()
        os._exit(0)

    def on_closing():
        if state["quitting"]:
            return True
        window.hide()  # keep running in the background, hotkeys stay alive
        return False

    window.events.closing += on_closing

    pending = threading.Event()

    def push_update():
        if pending.is_set():
            return
        pending.set()

        def go():
            pending.clear()
            try:
                window.evaluate_js("window.__refresh && window.__refresh()")
            except Exception:
                pass
        threading.Timer(0.05, go).start()

    engine.listeners.append(push_update)

    tray = make_tray(show, engine, quit_app)
    if tray is not None:
        try:
            tray.run_detached()  # must happen on the main thread before the window loop (macOS)
        except Exception as exc:
            print(f"[tray] {exc}")
            tray = None

    def on_started():
        engine.start_audio_and_keys()
        engine.changed("Ready. Hold " + settings["hotkeys"]["push_to_talk"].upper().replace("+", " + ") + " and say a voice")

    webview.start(on_started, debug=not FROZEN and os.environ.get("IV_DEBUG") == "1")
