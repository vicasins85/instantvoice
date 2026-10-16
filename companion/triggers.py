"""Decides what a sentence asks for: a sound, a mood, a voice, or going back to normal.

Two modes:
- direct (shortcut, typed text): the whole sentence is a command, so plain keywords work ("pedo", "feliz").
- ambient (always-on listening in a meeting): only explicit phrases fire ("estoy enfadado",
  "quiero que suene una bomba", "quiero tirarme un pedo"), so normal conversation never triggers anything.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from intent import CLEAR_PHRASES, normalize

FILLERS = {"un", "una", "el", "la", "a", "an", "the", "muy", "tan", "super", "so", "really", "very", "un poco",
           "bastante", "estoy", "me", "siento", "i", "m", "im", "am", "feel", "voz", "de", "modo", "mode", "voice",
           "pon", "ponme", "quiero", "estar", "sonar", "sound", "like", "como"}

AMBIENT_CLEAR = [r"\bvoz normal\b", r"\bnormal voice\b", r"\bquita(r)? (el )?efecto\b", r"\bmi voz normal\b"]
AMBIENT_SOUND = [
    r"\b(?:quiero|voy a|me voy a) (?:tirarme|tirar|echarme) (?:un )?(pedo|pedos)\b",
    r"\bme (?:tiro|he tirado) un (pedo)\b",
    r"\b(?:quiero que suene|que suene|haz que suene|pon el sonido de|pon un sonido de|play the sound of|play a|play an|play the|cue the)\s+(?:un |una |el |la |unos |unas |a |an |the )?(.+)",
]
AMBIENT_MOOD = r"\b(?:estoy|me siento|i m|im|i am|i feel)\s+(?:muy |tan |super |so |really |very |un poco |bastante )?([a-z]+)"
AMBIENT_VOICE = r"\b(?:quiero sonar como|quiero sonar a|haz que suene como|hazme sonar como|make me sound like|i want to sound like)\s+(?:un |una |a |an |el |la |the )?(.+)"


@dataclass
class Trigger:
    kind: str          # "clear" | "sound" | "online_sound" | "mood" | "voice" | "none"
    value: str = ""
    label: str = ""


class TriggerMatcher:
    def __init__(self, presets: dict, sound_lib):
        self.sounds = sound_lib
        self.moods = {k: v for k, v in presets.items() if v.get("category") == "mood"}
        self.mood_words = {}
        for mid, m in self.moods.items():
            for kw in m["keywords"]:
                self.mood_words[normalize(kw)] = mid

    def _mood_for(self, word: str) -> str | None:
        return self.mood_words.get(normalize(word))

    def _sound_for(self, phrase: str) -> Trigger:
        phrase = phrase.strip()
        sid = self.sounds.match_builtin(phrase)
        if sid:
            return Trigger("sound", sid, sid)
        return Trigger("online_sound", phrase, phrase)

    def ambient(self, text: str) -> Trigger:
        t = normalize(text)
        if not t:
            return Trigger("none")
        if any(re.search(p, t) for p in AMBIENT_CLEAR):
            return Trigger("clear")
        for p in AMBIENT_SOUND:
            m = re.search(p, t)
            if m:
                return self._sound_for(m.group(1))
        m = re.search(AMBIENT_VOICE, t)
        if m:
            return Trigger("voice", m.group(1), m.group(1))
        for m in re.finditer(AMBIENT_MOOD, t):
            mid = self._mood_for(m.group(1))
            if mid:
                return Trigger("mood", mid, self.moods[mid]["name"])
        return Trigger("none")

    def direct(self, text: str) -> Trigger:
        t = normalize(text)
        if not t:
            return Trigger("none")
        if t in CLEAR_PHRASES:
            return Trigger("clear")
        amb = self.ambient(text)
        if amb.kind in ("sound", "online_sound", "mood", "clear"):
            return amb
        sid = self.sounds.match_builtin(t)
        if sid:
            return Trigger("sound", sid, sid)
        words = [w for w in t.split() if w not in FILLERS]
        if words and all(self._mood_for(w) for w in words):
            mid = self._mood_for(words[0])
            return Trigger("mood", mid, self.moods[mid]["name"])
        return Trigger("voice", text, text)
