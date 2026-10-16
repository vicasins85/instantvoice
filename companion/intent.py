"""Turns a spoken sentence into an action for the plugin.

Order: clear command -> relative nudge -> cache -> AI -> keyword fallback (offline).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from voiceparams import PARAMS, clamp_preset, full_preset, json_schema

HERE = Path(__file__).resolve().parent

CLEAR_PHRASES = [
    "voz normal", "normal voice", "quitar", "quita", "quitalo", "quita el efecto", "sin efecto",
    "apagar", "apaga", "off", "stop", "reset", "clear", "remove", "my voice", "mi voz", "normal",
]

# Relative changes: regex on the normalized text -> list of (param, delta)
NUDGES = [
    (r"\b(mas grave|mas profund[ao]|deeper|lower)\b", [("pitch_semitones", -2.0)]),
    (r"\b(mas agud[ao]|higher|mas fin[ao])\b", [("pitch_semitones", 2.0)]),
    (r"\b(mas (de )?(eco|reverb)|more (echo|reverb))\b", [("reverb_mix", 0.15)]),
    (r"\b(menos (de )?(eco|reverb)|less (echo|reverb))\b", [("reverb_mix", -0.15)]),
    (r"\b(mas (de )?distorsion|more distortion|mas rot[ao]|more grit|mas enfadad[ao]|angrier)\b", [("drive", 0.15)]),
    (r"\b(menos (de )?distorsion|less distortion|mas limpi[ao]|cleaner)\b", [("drive", -0.15)]),
    (r"\b(mas fuerte|louder|mas volumen|more volume)\b", [("output_gain_db", 3.0)]),
    (r"\b(mas bajo|mas suave|quieter|less volume|menos volumen)\b", [("output_gain_db", -3.0)]),
    (r"\b(mas grande|bigger)\b", [("formant_semitones", -2.0)]),
    (r"\b(mas pequen[oa]|smaller)\b", [("formant_semitones", 2.0)]),
]

PREFIXES = [
    "quiero sonar como", "quiero sonar a", "hazme sonar como", "haz que suene como", "suena como",
    "sonar como", "ponme la voz de", "ponme voz de", "pon la voz de", "pon voz de", "voz de",
    "i want to sound like", "make me sound like", "make me sound", "sound like", "voice of", "give me",
]
ARTICLES = {"un", "una", "unos", "el", "la", "los", "las", "a", "an", "the", "de", "del", "como", "like"}

SYSTEM_PROMPT = """You are the sound designer inside a real-time voice changer.
The user describes how they want to sound. Call set_voice with the parameter values that best create that voice.

Rules:
- Only set the parameters you need. Unset ones stay at their default (clean).
- Keep it intelligible: the user is talking to friends in a game or on a stream.
- Pitch and formant usually move together for size: big creatures go negative on both, small ones positive.
- Emotion: anger/aggression -> some drive and a bass boost. Fear/creepy -> chorus, reverb, slight pitch up. Sad/tired -> slight pitch down, darker high shelf.
- Spaces (cave, bathroom, stadium) are mostly reverb_size and reverb_mix.
- Devices (radio, phone, megaphone, intercom) are mostly highpass_hz + lowpass_hz + drive.
- Machines (robot, AI, dalek) use ring_hz/ring_mix and bitcrush_bits.

Reference presets (good starting points, adapt them to the description):
{examples}
"""


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def core_description(text: str) -> str:
    """'Quiero sonar como un ogro enfadado.' -> 'ogro enfadado'"""
    t = normalize(text)
    for p in sorted(PREFIXES, key=len, reverse=True):
        if t.startswith(p + " ") or t == p:
            t = t[len(p):].strip()
            break
    words = [w for w in t.split() if w not in ARTICLES]
    return " ".join(words)


@dataclass
class Action:
    kind: str                      # "preset" | "nudge" | "bypass" | "none"
    preset: dict = field(default_factory=dict)
    nudges: list = field(default_factory=list)
    source: str = ""               # "cache" | "ai" | "keyword" | "rule"
    label: str = ""


class IntentResolver:
    def __init__(self, cache_path: Path, model: str, api_key_env: str = "ANTHROPIC_API_KEY",
                 presets_path: Path = HERE / "presets.json", api_key: str = ""):
        self.cache_path = cache_path
        self.model = model
        self.api_key_env = api_key_env
        self.api_key = api_key
        self.presets = json.loads(presets_path.read_text(encoding="utf-8"))
        self.cache = self._load_cache()
        self._client = None

    # ---------- cache ----------
    def _load_cache(self) -> dict:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2, ensure_ascii=False), encoding="utf-8")

    def remember(self, description: str, preset: dict):
        self.cache[description] = clamp_preset(preset)
        self._save_cache()

    # ---------- resolution ----------
    def resolve(self, text: str, current: dict | None = None) -> Action:
        norm = normalize(text)
        if not norm:
            return Action("none", label="(nothing heard)")

        core = core_description(text)
        if norm in CLEAR_PHRASES or core in CLEAR_PHRASES:
            return Action("bypass", source="rule", label="clean voice")

        nudges = []
        for pattern, changes in NUDGES:
            if re.search(pattern, norm):
                nudges.extend(changes)
        # Only treat as relative if it's a short tweak ("más grave", "less echo"), not a new voice.
        if nudges and len(core.split()) <= 3:
            return Action("nudge", nudges=nudges, source="rule", label=core)

        if core in self.cache:
            return Action("preset", preset=self.cache[core], source="cache", label=core)

        preset = self._ask_ai(core or norm, current)
        if preset is not None:
            self.remember(core, preset)
            return Action("preset", preset=preset, source="ai", label=core)

        kw = self.keyword_preset(core)
        if kw:
            name, preset = kw
            return Action("preset", preset=preset, source="keyword", label=name)

        return Action("none", label=f"no match for '{core}'")

    def keyword_preset(self, description: str):
        words = f" {normalize(description)} "
        for name, entry in self.presets.items():
            for kw in entry["keywords"]:
                if f" {normalize(kw)} " in words:
                    return name, clamp_preset(entry["params"])
        return None

    # ---------- AI ----------
    def _client_or_none(self):
        if self._client is None:
            key = self.api_key or os.environ.get(self.api_key_env, "")
            if not key:
                return None
            try:
                import anthropic
            except ImportError:
                return None
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def set_api_key(self, key: str):
        self.api_key = key.strip()
        self._client = None

    @property
    def has_ai(self) -> bool:
        return bool(self.api_key or os.environ.get(self.api_key_env))

    def _ask_ai(self, description: str, current: dict | None):
        client = self._client_or_none()
        if client is None:
            return None
        examples = "\n".join(
            f"- {entry.get('name', name)}: {json.dumps(entry['params'])}" for name, entry in self.presets.items()
        )
        user = f"Voice description: {description}"
        if current:
            user += f"\nCurrent settings (only relevant if the request is relative): {json.dumps(current)}"
        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=400,
                system=SYSTEM_PROMPT.format(examples=examples),
                tools=[{
                    "name": "set_voice",
                    "description": "Apply voice effect parameters to the live microphone.",
                    "input_schema": json_schema(),
                }],
                tool_choice={"type": "tool", "name": "set_voice"},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # network, auth, rate limit: fall back to keywords
            print(f"[intent] AI call failed: {exc}")
            return None
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use":
                return clamp_preset(block.input)
        return None


def apply_nudges(current: dict, nudges: list) -> dict:
    preset = full_preset(current)
    for key, delta in nudges:
        lo, hi, _, _ = PARAMS[key]
        preset[key] = max(lo, min(hi, preset[key] + delta))
    return preset
