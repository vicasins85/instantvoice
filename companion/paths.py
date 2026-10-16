"""Where things live, both when running from source and inside the packaged app."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA_DIR = Path.home() / ".instantvoice"
SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "api_key": "",
    "autostart": True,
    "language": "es",          # es | en | auto
    "whisper_model": "base",
    "input_device": "",
    "hotkeys": {
        "push_to_talk": "ctrl+alt+v",
        "clear": "ctrl+alt+x",
        "slot_1": "ctrl+alt+1", "slot_2": "ctrl+alt+2", "slot_3": "ctrl+alt+3",
        "save_1": "ctrl+alt+shift+1", "save_2": "ctrl+alt+shift+2", "save_3": "ctrl+alt+shift+3",
    },
    "ai_model": "claude-haiku-5-5",
    "osc_port": 9001,
    "osc_reply_port": 9002,
}


def resource(*parts: str) -> Path:
    return RESOURCES.joinpath(*parts)


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        hotkeys = {**settings["hotkeys"], **stored.get("hotkeys", {})}
        settings.update(stored)
        settings["hotkeys"] = hotkeys
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return settings


def save_settings(settings: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    try:
        SETTINGS_PATH.chmod(0o600)  # holds the API key
    except OSError:
        pass


def whisper_model_path(size: str) -> str:
    """Bundled model folder if present, otherwise the model name (downloaded on first use)."""
    bundled = resource("models", size)
    return str(bundled) if (bundled / "model.bin").exists() else size
