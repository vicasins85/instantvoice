"""Sound effects: a built-in pack synthesized on first run (no downloads, no licensing),
plus any sound from Freesound when a Freesound API key is set.

Every sound ends up as a 48 kHz mono WAV in ~/.instantvoice/sounds, which the effect plays.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

SR = 48000

# id -> (display name, color, keywords). Keywords are matched as whole words on normalized text.
BUILTIN = {
    "fart":      ("Fart", "#6B5B2E", ["pedo", "pedos", "fart", "farts", "flatulencia", "cuesco", "ventosidad"]),
    "explosion": ("Explosion", "#9C3D1F", ["bomba", "explosion", "explosiones", "explotar", "boom", "kaboom", "bomb", "explode"]),
    "airhorn":   ("Air horn", "#2B6CB0", ["bocina", "airhorn", "air horn", "claxon", "mlg"]),
    "rimshot":   ("Ba dum tss", "#4A5568", ["ba dum tss", "badum", "badumtss", "rimshot", "redoble", "chiste malo"]),
    "trombone":  ("Sad trombone", "#2C5282", ["trombon", "trombon triste", "sad trombone", "fracaso", "fail", "fallo"]),
    "applause":  ("Applause", "#2F855A", ["aplausos", "aplauso", "applause", "clap", "bravo", "ovacion"]),
    "boing":     ("Boing", "#B7791F", ["boing", "rebote", "muelle", "bounce"]),
    "laser":     ("Laser", "#6B46C1", ["laser", "pew", "pew pew", "pium", "disparo laser"]),
    "ding":      ("Ding", "#2C7A7B", ["ding", "campana", "campanita", "correcto", "bell"]),
    "crickets":  ("Crickets", "#276749", ["grillos", "grillo", "crickets", "silencio incomodo", "awkward silence"]),
}


# ---------------- synthesis helpers ----------------
def _t(secs: float) -> np.ndarray:
    return np.arange(int(SR * secs)) / SR


def _onepole_lp(x: np.ndarray, cutoff) -> np.ndarray:
    """One-pole low-pass; cutoff may be a scalar or an array (time-varying)."""
    cutoff = np.broadcast_to(np.asarray(cutoff, dtype=np.float64), x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    prev = 0.0
    for i in range(len(x)):
        prev = (1 - a[i]) * x[i] + a[i] * prev
        y[i] = prev
    return y


def _env(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _saw_phase(freq: np.ndarray) -> np.ndarray:
    phase = np.cumsum(freq / SR)
    return 2 * (phase % 1.0) - 1


def _norm(x: np.ndarray, peak: float = 0.8) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return (x / m * peak).astype(np.float32)


def synth(sound_id: str, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if sound_id == "fart":
        t = _t(1.4)
        f = 85 + 25 * np.sin(2 * np.pi * 3.1 * t) + rng.normal(0, 6, len(t)).cumsum() * 0.01
        buzz = _saw_phase(np.clip(f, 40, 160))
        flutter = 0.6 + 0.4 * np.sin(2 * np.pi * (14 + 6 * t) * t)
        noise = rng.normal(0, 0.3, len(t))
        x = _onepole_lp(buzz * flutter + noise * 0.5, 600)
        sputter = (rng.random(len(t) // 2400 + 1) > 0.25).repeat(2400)[: len(t)]
        x *= _env(len(t), 0.02, 0.35) * (0.5 + 0.5 * sputter)
        return _norm(x)
    if sound_id == "explosion":
        t = _t(2.8)
        noise = rng.normal(0, 1, len(t))
        cutoff = 6000 * np.exp(-t * 2.2) + 120
        rumble = _onepole_lp(noise, cutoff)
        boom = np.sin(2 * np.pi * (55 * np.exp(-t * 1.5) + 30) * t) * np.exp(-t * 2.0)
        crack = noise * np.exp(-t * 30) * 0.6
        x = rumble * np.exp(-t * 1.2) * 1.4 + boom * 1.2 + crack
        return _norm(x * _env(len(t), 0.002, 0.6), 0.9)
    if sound_id == "airhorn":
        out = []
        for dur in (0.28, 0.28, 0.9):
            t = _t(dur)
            f = np.full(len(t), 415.0)
            tone = sum(_saw_phase(f * r) for r in (1.0, 1.005, 1.5, 2.0)) / 4
            tone = np.tanh(tone * 3) * _env(len(t), 0.01, 0.05)
            out += [tone, np.zeros(int(SR * 0.07))]
        return _norm(_onepole_lp(np.concatenate(out), 4500))
    if sound_id == "rimshot":
        def tom(freq, dur=0.25):
            t = _t(dur)
            return np.sin(2 * np.pi * freq * (1 + np.exp(-t * 20)) * t) * np.exp(-t * 14)
        t = _t(1.2)
        cym = rng.normal(0, 1, len(t))
        cym = (cym - _onepole_lp(cym, 6000)) * np.exp(-t * 3.5)
        x = np.concatenate([tom(180), np.zeros(int(SR * 0.05)), tom(130), np.zeros(int(SR * 0.04)), cym * 0.7])
        return _norm(x)
    if sound_id == "trombone":
        notes = [(311, 0.45), (294, 0.45), (277, 0.45), (262, 1.4)]
        out = []
        for i, (freq, dur) in enumerate(notes):
            t = _t(dur)
            vib = 1 + (0.02 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t * 2, 0, 1) if i == 3 else 0)
            tone = _saw_phase(freq * vib * np.ones(len(t)))
            out.append(_onepole_lp(tone, 1400) * _env(len(t), 0.04, 0.12))
        return _norm(np.concatenate(out))
    if sound_id == "applause":
        n = int(SR * 3.2)
        x = np.zeros(n)
        for _ in range(900):
            start = int(rng.random() * (n - 3000))
            length = int(rng.uniform(600, 1800))
            clap = rng.normal(0, 1, length) * np.exp(-np.arange(length) / (length / 5))
            x[start:start + length] += clap * rng.uniform(0.3, 1)
        x = x - _onepole_lp(x, 500)
        return _norm(x * _env(n, 0.3, 1.0))
    if sound_id == "boing":
        t = _t(1.0)
        f = 140 + 260 * np.exp(-t * 6) + 25 * np.sin(2 * np.pi * 18 * t) * np.exp(-t * 3)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
        return _norm(x)
    if sound_id == "laser":
        out = []
        for _ in range(3):
            t = _t(0.22)
            f = 2200 * np.exp(-t * 14) + 180
            sq = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR))
            out += [sq * np.exp(-t * 9) * 0.6, np.zeros(int(SR * 0.06))]
        return _norm(_onepole_lp(np.concatenate(out), 7000))
    if sound_id == "ding":
        t = _t(2.0)
        x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in
                [(1320, 1.0, 2.5), (2640, 0.4, 4), (3960, 0.25, 6), (1980, 0.3, 3)])
        return _norm(x * _env(len(t), 0.002, 0.2))
    if sound_id == "crickets":
        n = int(SR * 3.0)
        x = np.zeros(n)
        t = _t(0.012)
        chirp = np.sin(2 * np.pi * 4300 * t) * np.hanning(len(t))
        pos = 0
        while pos < n - SR // 2:
            for k in range(4):
                s = pos + k * int(SR * 0.025)
                x[s:s + len(chirp)] += chirp
            pos += int(SR * rng.uniform(0.35, 0.6))
        return _norm(x, 0.5)
    raise KeyError(sound_id)


def write_wav(path: Path, audio: np.ndarray, sr: int = SR):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 2.0


def decode_to_wav(src: Path, dst: Path) -> Path:
    """Any audio file (mp3, ogg...) -> 48 kHz mono WAV, using PyAV (shipped with faster-whisper)."""
    import av
    container = av.open(str(src))
    resampler = av.AudioResampler(format="flt", layout="mono", rate=SR)
    chunks = []
    for frame in container.decode(audio=0):
        for f in resampler.resample(frame):
            chunks.append(f.to_ndarray().reshape(-1))
    container.close()
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    audio = audio[: SR * 15]
    write_wav(dst, _norm(audio, 0.8))
    return dst


def _normalize(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def _ssl_context():
    try:
        import certifi  # ships with the AI client; the packaged app has no system CA path
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class SoundLibrary:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.freesound_key = ""

    def ensure_builtin(self):
        for sid in BUILTIN:
            p = self.path(sid)
            if not p.exists():
                write_wav(p, synth(sid))

    def path(self, sound_id: str) -> Path:
        return self.folder / f"{sound_id}.wav"

    def list(self) -> list[dict]:
        out = [{"id": sid, "name": name, "color": color, "builtin": True} for sid, (name, color, _) in BUILTIN.items()]
        meta = self._meta()
        for sid, m in meta.items():
            if self.path(sid).exists():
                out.append({"id": sid, "name": m["name"], "color": "#4A5568", "builtin": False})
        return out

    def match_builtin(self, text: str) -> str | None:
        words = f" {_normalize(text)} "
        for sid, (_, _, kws) in BUILTIN.items():
            for kw in kws:
                if f" {_normalize(kw)} " in words:
                    return sid
        return None

    # ---------- Freesound ----------
    def _meta(self) -> dict:
        try:
            return json.loads((self.folder / "downloaded.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_meta(self, meta: dict):
        (self.folder / "downloaded.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    def find_online(self, query: str) -> tuple[str, str] | None:
        """Search Freesound, download the best short match, return (sound_id, display name)."""
        if not self.freesound_key or not query.strip():
            return None
        slug = "fs_" + re.sub(r"[^a-z0-9]+", "_", _normalize(query))[:40]
        meta = self._meta()
        if slug in meta and self.path(slug).exists():
            return slug, meta[slug]["name"]
        params = urllib.parse.urlencode({
            "query": query, "fields": "id,name,previews,duration", "page_size": 5,
            "filter": "duration:[0.3 TO 8]", "sort": "score", "token": self.freesound_key,
        })
        with urllib.request.urlopen(f"https://freesound.org/apiv2/search/text/?{params}", timeout=8,
                                    context=_ssl_context()) as r:
            results = json.loads(r.read().decode("utf-8")).get("results", [])
        if not results:
            return None
        hit = results[0]
        url = hit["previews"].get("preview-hq-mp3") or hit["previews"].get("preview-lq-mp3")
        tmp = self.folder / f"{slug}.download"
        with urllib.request.urlopen(url, timeout=15, context=_ssl_context()) as r:
            tmp.write_bytes(r.read())
        decode_to_wav(tmp, self.path(slug))
        tmp.unlink(missing_ok=True)
        meta[slug] = {"name": query[:1].upper() + query[1:], "freesound_id": hit["id"], "title": hit["name"]}
        self._save_meta(meta)
        return slug, meta[slug]["name"]
