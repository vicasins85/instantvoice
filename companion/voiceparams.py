"""Parameter table. Must match plugin/Source/Params.h."""

PARAMS = {
    # id: (min, max, default, description for the model)
    "pitch_semitones":   (-12.0, 12.0, 0.0, "Pitch shift in semitones. Negative = deeper/bigger, positive = higher/smaller."),
    "formant_semitones": (-12.0, 12.0, 0.0, "Formant (vocal tract size) shift. Negative = bigger body/throat, positive = smaller/cartoonish."),
    "drive":             (0.0, 1.0, 0.0, "Distortion/growl amount. Anger, monsters, megaphones."),
    "bitcrush_bits":     (4.0, 16.0, 16.0, "Digital degradation. 16 = off, 8 = lo-fi, 4 = destroyed."),
    "ring_hz":           (0.0, 2000.0, 0.0, "Ring modulator frequency. 30-60 Hz = dalek/demonic wobble, 80-150 Hz = robot, 400+ = alien/metallic."),
    "ring_mix":          (0.0, 1.0, 0.0, "Ring modulator mix."),
    "highpass_hz":       (20.0, 1000.0, 20.0, "Remove lows below this. 300-600 Hz = radio/phone/small speaker."),
    "lowpass_hz":        (1000.0, 20000.0, 20000.0, "Remove highs above this. 1000-1500 = muffled/underwater/behind a wall, 2500-3500 = radio."),
    "low_shelf_db":      (-12.0, 12.0, 0.0, "Bass boost/cut around 250 Hz."),
    "high_shelf_db":     (-12.0, 12.0, 0.0, "Treble boost/cut above 3.5 kHz. Positive = airy/crisp, negative = dark."),
    "chorus_mix":        (0.0, 1.0, 0.0, "Chorus/doubling. Ghostly, underwater, choir, alien."),
    "reverb_size":       (0.0, 1.0, 0.3, "Room size. 0.2 = small room, 0.6 = hall, 0.95 = cave/cathedral."),
    "reverb_mix":        (0.0, 1.0, 0.0, "Reverb amount. Keep under 0.4 unless the space is the point."),
    "output_gain_db":    (-12.0, 12.0, 0.0, "Output volume compensation."),
}


def clamp_preset(raw: dict) -> dict:
    """Keep only known params, cast to float and clamp to range."""
    out = {}
    for key, value in (raw or {}).items():
        if key not in PARAMS:
            continue
        lo, hi, _, _ = PARAMS[key]
        try:
            out[key] = round(max(lo, min(hi, float(value))), 3)
        except (TypeError, ValueError):
            continue
    return out


def full_preset(partial: dict) -> dict:
    """Partial preset with defaults filled in (what the plugin will actually be set to)."""
    preset = {k: v[2] for k, v in PARAMS.items()}
    preset.update(clamp_preset(partial))
    return preset


def json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            k: {"type": "number", "minimum": lo, "maximum": hi, "description": f"{desc} Default {d}."}
            for k, (lo, hi, d, desc) in PARAMS.items()
        },
        "additionalProperties": False,
    }
