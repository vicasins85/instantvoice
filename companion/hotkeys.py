"""Global hotkeys with press AND release (pynput's GlobalHotKeys only gives press).

Matching uses virtual key codes as well as characters, because modifiers change the
character a key produces (Ctrl+V is '\\x16' on Windows, Option+V is '√' on macOS).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from pynput import keyboard

K = keyboard.Key
MODIFIERS = {
    K.ctrl: "ctrl", K.ctrl_l: "ctrl", K.ctrl_r: "ctrl",
    K.alt: "alt", K.alt_l: "alt", K.alt_r: "alt",
    K.shift: "shift", K.shift_l: "shift", K.shift_r: "shift",
    K.cmd: "cmd", K.cmd_l: "cmd", K.cmd_r: "cmd",
}
if hasattr(K, "alt_gr"):
    MODIFIERS[K.alt_gr] = "alt"

# macOS ANSI virtual key codes
MAC_VK = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
}


def key_token(key) -> str | None:
    if key in MODIFIERS:
        return MODIFIERS[key]
    if isinstance(key, keyboard.KeyCode):
        vk = getattr(key, "vk", None)
        if vk is not None:
            if sys.platform == "darwin":
                for ch, code in MAC_VK.items():
                    if code == vk:
                        return ch
            elif sys.platform == "win32":
                if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
                    return chr(vk).lower()
        if key.char and key.char.isprintable():
            return key.char.lower()
        if vk is not None and 32 < vk < 127:
            return chr(vk).lower()
    return None


@dataclass
class Combo:
    mods: frozenset
    key: str

    @staticmethod
    def parse(text: str) -> "Combo":
        parts = [p.strip().lower() for p in text.split("+") if p.strip()]
        aliases = {"control": "ctrl", "option": "alt", "opt": "alt", "command": "cmd", "win": "cmd"}
        parts = [aliases.get(p, p) for p in parts]
        return Combo(frozenset(parts[:-1]), parts[-1])


class HotkeyManager:
    """bind(combo, on_press, on_release=None). Modifiers must match exactly."""

    def __init__(self):
        self.bindings: list[tuple[Combo, Callable, Callable | None]] = []
        self.mods: set[str] = set()
        self.active: Combo | None = None
        self.listener = None

    def bind(self, combo: str, on_press: Callable, on_release: Callable | None = None):
        self.bindings.append((Combo.parse(combo), on_press, on_release))

    def _press(self, key):
        tok = key_token(key)
        if tok is None:
            return
        if tok in ("ctrl", "alt", "shift", "cmd"):
            self.mods.add(tok)
            return
        if self.active is not None:
            return  # key repeat while held
        for combo, on_press, _ in self.bindings:
            if combo.key == tok and combo.mods == frozenset(self.mods):
                self.active = combo
                _safe(on_press)
                return

    def _release(self, key):
        tok = key_token(key)
        if tok is None:
            return
        if self.active is not None and (tok == self.active.key or tok in self.active.mods):
            combo, self.active = self.active, None
            for c, _, on_release in self.bindings:
                if c == combo and on_release:
                    _safe(on_release)
        if tok in self.mods:
            self.mods.discard(tok)

    def start(self):
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()


def _safe(fn):
    try:
        fn()
    except Exception as exc:
        print(f"[hotkey] handler error: {exc}")
