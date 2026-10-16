"""Voice library: built-in presets, voices the user created, favorites, slots, per-voice tweaks.

The UI shows 5 simple sliders (macros). Each one owns a few real plugin parameters,
so moving one slider never wipes out the rest of a voice (a radio keeps its filters).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from voiceparams import PARAMS, clamp_preset

MACROS = ["size", "pitch", "grit", "space", "robot"]

CUSTOM_COLORS = ["#7A3B5C", "#2E5E7A", "#6A5A1E", "#3F6B3A", "#6B3A2A", "#4B3F7A", "#1F6E7A"]


def _c(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def macro_params(name: str, value: float) -> dict:
    """Plugin params owned by one macro slider (value 0..100)."""
    v = _c(float(value)) / 100.0
    if name == "size":       # bigger = lower formants
        return {"formant_semitones": round((0.5 - v) * 14, 2)}
    if name == "pitch":
        return {"pitch_semitones": round((v - 0.5) * 20, 2)}
    if name == "grit":
        return {"drive": round(v * 0.8, 3)}
    if name == "space":
        return {"reverb_mix": round(v * 0.65, 3), "reverb_size": round(0.2 + v * 0.75, 3)}
    if name == "robot":
        return {"ring_mix": round(v * 0.75, 3), "ring_hz": 90.0 if v > 0.01 else 0.0,
                "bitcrush_bits": round(16 - v * 6, 2)}
    raise KeyError(name)


def macros_from_params(p: dict) -> list[int]:
    get = lambda k: float(p.get(k, PARAMS[k][2]))
    return [
        round(_c(50 - get("formant_semitones") / 14 * 100)),
        round(_c(50 + get("pitch_semitones") / 20 * 100)),
        round(_c(get("drive") / 0.8 * 100)),
        round(_c(get("reverb_mix") / 0.65 * 100)),
        round(_c(get("ring_mix") / 0.75 * 100)),
    ]


def monogram(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


class Library:
    def __init__(self, path: Path, presets: dict):
        self.path = path
        self.presets = presets
        self.data = {"custom": [], "favs": [], "slots": {}, "tweaks": {}}
        try:
            self.data.update(json.loads(path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------- voices ----------
    def voices(self) -> list[dict]:
        out = []
        for c in self.data["custom"]:
            out.append({"id": c["id"], "name": c["name"], "color": c["color"], "custom": True,
                        "category": "voice", "base": c["params"]})
        for key, entry in self.presets.items():
            out.append({"id": key, "name": entry.get("name", key), "color": entry.get("color", "#4A5560"),
                        "custom": False, "category": entry.get("category", "voice"),
                        "base": clamp_preset(entry["params"])})
        favs = set(self.data["favs"])
        for v in out:
            v["params"] = self.params_for(v["id"], v["base"])
            v["macros"] = macros_from_params(v["params"])
            v["mono"] = monogram(v["name"])
            v["fav"] = v["id"] in favs
        return out

    def get(self, voice_id: str) -> dict | None:
        return next((v for v in self.voices() if v["id"] == voice_id), None)

    def params_for(self, voice_id: str, base: dict) -> dict:
        p = dict(base)
        p.update(self.data["tweaks"].get(voice_id, {}))
        return clamp_preset(p)

    def add_custom(self, name: str, params: dict) -> str:
        name = name.strip()[:40] or "New voice"
        existing = next((c for c in self.data["custom"] if c["name"].lower() == name.lower()), None)
        if existing:
            existing["params"] = clamp_preset(params)
            self.data["tweaks"].pop(existing["id"], None)
            self.save()
            return existing["id"]
        vid = f"c{int(time.time() * 1000)}"
        color = CUSTOM_COLORS[len(self.data["custom"]) % len(CUSTOM_COLORS)]
        self.data["custom"].insert(0, {"id": vid, "name": name[:1].upper() + name[1:], "color": color,
                                       "params": clamp_preset(params)})
        self.save()
        return vid

    def delete_custom(self, voice_id: str):
        self.data["custom"] = [c for c in self.data["custom"] if c["id"] != voice_id]
        self.data["tweaks"].pop(voice_id, None)
        self.data["favs"] = [f for f in self.data["favs"] if f != voice_id]
        self.save()

    def set_macro(self, voice_id: str, macro: str, value: float) -> dict:
        tw = self.data["tweaks"].setdefault(voice_id, {})
        tw.update(macro_params(macro, value))
        self.save()
        v = self.get(voice_id)
        return v["params"] if v else {}

    def reset_tweaks(self, voice_id: str):
        self.data["tweaks"].pop(voice_id, None)
        self.save()

    def toggle_fav(self, voice_id: str):
        favs = self.data["favs"]
        if voice_id in favs:
            favs.remove(voice_id)
        else:
            favs.append(voice_id)
        self.save()

    # ---------- slots ----------
    def set_slot(self, n: int, voice_id: str):
        self.data["slots"][str(n)] = voice_id
        self.save()

    def slot(self, n: int) -> str | None:
        vid = self.data["slots"].get(str(n))
        return vid if vid and self.get(vid) else None
