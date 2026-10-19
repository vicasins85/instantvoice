"""Instant Voicemod desktop app: main window, floating status overlay, tray / menu bar icon, start at login."""
from __future__ import annotations

import os
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


# ---------- bridges exposed to JavaScript ----------
class Api:
    def __init__(self, engine: Engine, settings: dict, on_overlay_toggle):
        self._engine = engine
        self._settings = settings
        self._on_overlay_toggle = on_overlay_toggle

    def state(self):
        return self._engine.snapshot()

    def pick(self, voice_id):
        self._engine.apply_voice(voice_id)

    def toggle(self, on):
        self._engine.set_on(bool(on))

    def clear(self):
        self._engine.clear()

    def create(self, text):
        return self._engine.handle_text(str(text), "text")

    def play(self, sound_id):
        self._engine.play_sound(str(sound_id))

    def listen(self, on):
        self._settings["ambient"] = bool(on)
        save_settings(self._settings)
        self._engine.set_ambient(bool(on))

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

    def devices(self):
        from audio_engine import list_devices
        d = list_devices()
        if d.get("status") == "error":  # engine missing (running from source): fall back to sounddevice
            try:
                import sounddevice as sd
                devs = sd.query_devices()
                d = {"inputs": [x["name"] for x in devs if x["max_input_channels"] > 0],
                     "outputs": [x["name"] for x in devs if x["max_output_channels"] > 0]}
            except Exception:
                d = {"inputs": [], "outputs": []}
        return d

    def get_settings(self):
        s = self._settings
        return {"hasKey": bool(s.get("api_key")), "hasFreesound": bool(s.get("freesound_key")),
                "autostart": s.get("autostart", True), "language": s.get("language", "es"),
                "route": s.get("route", "cable"), "inputDevice": s.get("input_device", ""),
                "outputDevice": s.get("output_device", ""), "ambient": s.get("ambient", True),
                "tempSeconds": s.get("temp_seconds", 6), "overlay": s.get("overlay", True),
                "hotkeys": s["hotkeys"], "platform": sys.platform}

    def save_settings(self, data):
        s, e = self._settings, self._engine
        key = (data.get("apiKey") or "").strip()
        if key:
            s["api_key"] = key
            e.resolver.set_api_key(key)
        if data.get("removeKey"):
            s["api_key"] = ""
            e.resolver.set_api_key("")
        fkey = (data.get("freesoundKey") or "").strip()
        if fkey:
            s["freesound_key"] = fkey
            e.sounds.freesound_key = fkey
        if "autostart" in data:
            s["autostart"] = bool(data["autostart"])
            set_autostart(s["autostart"])
        if data.get("language") in ("es", "en", "auto"):
            s["language"] = data["language"]
            if e.transcriber:
                e.transcriber.language = None if s["language"] == "auto" else s["language"]
        if "tempSeconds" in data:
            s["temp_seconds"] = max(2, min(60, int(data["tempSeconds"] or 6)))
        if "overlay" in data:
            s["overlay"] = bool(data["overlay"])
            self._on_overlay_toggle(s["overlay"])
        restart_audio = False
        for src, dst in (("inputDevice", "input_device"), ("outputDevice", "output_device")):
            if src in data and data[src] != s.get(dst, ""):
                s[dst] = data[src]
                restart_audio = True
        if data.get("route") in ("cable", "wavelink") and data["route"] != s.get("route"):
            s["route"] = data["route"]
            restart_audio = True
        save_settings(s)
        if restart_audio:
            if s["route"] == "cable":
                e.stop_route()
                e.start_route()
            else:
                e.stop_route()
            if e.recorder is not None:
                try:
                    from audio import Recorder
                    e.recorder = Recorder(s.get("input_device") or None)
                except Exception as exc:
                    e.changed(f"Mic error: {exc}")
            if e.ambient and e.ambient.running:
                e.ambient.stop()
                e.ambient = None
                e.set_ambient(True)
        e.changed("Settings saved")
        return self.get_settings()


class OverlayApi:
    def __init__(self, engine: Engine):
        self._engine = engine

    def state(self):
        return self._engine.overlay_state()


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
    holder = {"overlay": None, "quitting": False, "tray": None}

    def overlay_toggle(on: bool):
        w = holder["overlay"]
        if w is None:
            return
        (w.show if on else w.hide)()

    api = Api(engine, settings, overlay_toggle)
    if settings.get("autostart", True):
        set_autostart(True)

    window = webview.create_window(
        APP_NAME, url=str(resource("ui", "index.html")), js_api=api,
        width=1240, height=820, min_size=(880, 620), hidden=hidden, background_color="#0C0E16",
    )

    # Floating status pill, always on top of every app.
    try:
        ow, oh = 400, 76
        try:
            screen = webview.screens[0]
            ox, oy = int(screen.width / 2 - ow / 2), 18
        except Exception:
            ox, oy = None, None
        holder["overlay"] = webview.create_window(
            "Instant Voicemod status", url=str(resource("ui", "overlay.html")), js_api=OverlayApi(engine),
            width=ow, height=oh, x=ox, y=oy,
            frameless=True, on_top=True, transparent=True, easy_drag=True, focus=False,
            resizable=False, hidden=not settings.get("overlay", True), background_color="#000000",
        )
    except Exception as exc:
        print(f"[overlay] unavailable: {exc}")

    def show():
        window.show()
        try:
            window.restore()
        except Exception:
            pass

    def quit_app():
        holder["quitting"] = True
        engine.stop()
        if holder["tray"]:
            holder["tray"].stop()
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass
        os._exit(0)

    def on_closing():
        if holder["quitting"]:
            return True
        window.hide()  # keep running in the background, hotkeys and listening stay alive
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

    # macOS: read the keyboard layout on the main thread now; hotkeys start later on a worker thread.
    try:
        from hotkeys import prime_macos
        prime_macos()
    except Exception as exc:
        print(f"[hotkey] {exc}")

    tray = make_tray(show, engine, quit_app)
    if tray is not None:
        try:
            tray.run_detached()  # must happen on the main thread before the window loop (macOS)
            holder["tray"] = tray
        except Exception as exc:
            print(f"[tray] {exc}")

    def on_started():
        engine.start_services()
        ptt = settings["hotkeys"]["push_to_talk"].upper().replace("+", " + ")
        engine.changed(f"Ready. Say 'estoy feliz' or hold {ptt}")

    webview.start(on_started, debug=not FROZEN and os.environ.get("IV_DEBUG") == "1")
