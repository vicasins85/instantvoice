"""Instant Voicemod.

  Instant Voicemod                    open the app (window + menu bar / tray icon)
  main.py --hidden                    start in the background (used at login)
  main.py --headless                  hotkeys only, no window
  main.py --text "ogro enfadado"      resolve a description and send it, then exit
  main.py --devices                   list audio input devices
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import time

_LOCK = None


def single_instance() -> bool:
    """True if we are the only running copy. A second copy would otherwise start a second
    engine, tray icon and overlay on top of the first one."""
    global _LOCK
    path = os.path.join(os.path.expanduser("~"), ".instantvoice", "app.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if sys.platform == "win32":
            import msvcrt
            _LOCK = open(path, "a+")
            msvcrt.locking(_LOCK.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            _LOCK = open(path, "a+")
            fcntl.flock(_LOCK.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description="Instant Voicemod")
    parser.add_argument("--text", help="resolve this description and send it, then exit")
    parser.add_argument("--devices", action="store_true", help="list audio input devices")
    parser.add_argument("--hidden", action="store_true", help="start without showing the window")
    parser.add_argument("--headless", action="store_true", help="no window, hotkeys only")
    args, _ = parser.parse_known_args()  # macOS may pass extra -psn_ args

    if args.devices:
        import sounddevice as sd
        print(sd.query_devices())
        return 0

    from paths import load_settings

    if args.text or args.headless:
        from core import Engine
        engine = Engine(load_settings())
        if args.text:
            print(engine.create(args.text))
            print(engine.current_params)
            return 0
        engine.start_audio_and_keys()
        print("[ready] headless mode. Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            engine.stop()
        return 0

    if not single_instance():
        print("[app] already running")
        return 0

    from app import run
    run(hidden=args.hidden)
    return 0


if __name__ == "__main__":
    # Frozen apps: libraries that use multiprocessing (tqdm locks, resource tracker) re-run
    # sys.executable, which is this app. Without this, each child opens a new app window.
    multiprocessing.freeze_support()
    if any(a in ("-c", "-B", "-s") or a.startswith("--multiprocessing") for a in sys.argv[1:]):
        sys.exit(0)  # a helper process that freeze_support did not claim: never open the UI
    sys.exit(main())
