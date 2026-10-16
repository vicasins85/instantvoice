#pragma once
#include <juce_audio_processors/juce_audio_processors.h>

// Single source of truth for every voice parameter.
// The OSC API, the host parameters and the companion's JSON schema all use these IDs.
namespace params
{
struct Spec
{
    const char* id;
    const char* name;
    float min, max, def;
    const char* unit;
};

inline constexpr Spec all[] = {
    { "pitch_semitones",   "Pitch",         -12.0f,   12.0f,     0.0f, "st" },
    { "formant_semitones", "Formant",       -12.0f,   12.0f,     0.0f, "st" },
    { "drive",             "Drive",           0.0f,    1.0f,     0.0f, ""   },
    { "bitcrush_bits",     "Bitcrush bits",   4.0f,   16.0f,    16.0f, "bit" },
    { "ring_hz",           "Ring mod freq",   0.0f, 2000.0f,     0.0f, "Hz" },
    { "ring_mix",          "Ring mod mix",    0.0f,    1.0f,     0.0f, ""   },
    { "highpass_hz",       "High-pass",      20.0f, 1000.0f,    20.0f, "Hz" },
    { "lowpass_hz",        "Low-pass",     1000.0f, 20000.0f, 20000.0f, "Hz" },
    { "low_shelf_db",      "Low shelf",     -12.0f,   12.0f,     0.0f, "dB" },
    { "high_shelf_db",     "High shelf",    -12.0f,   12.0f,     0.0f, "dB" },
    { "chorus_mix",        "Chorus mix",      0.0f,    1.0f,     0.0f, ""   },
    { "reverb_size",       "Reverb size",     0.0f,    1.0f,     0.3f, ""   },
    { "reverb_mix",        "Reverb mix",      0.0f,    1.0f,     0.0f, ""   },
    { "output_gain_db",    "Output gain",   -12.0f,   12.0f,     0.0f, "dB" },
};

inline constexpr int count = (int) (sizeof (all) / sizeof (all[0]));

enum Index
{
    pitch, formant, drive, bitcrush, ringHz, ringMix, highpass, lowpass,
    lowShelf, highShelf, chorusMix, reverbSize, reverbMix, outputGain
};

inline constexpr const char* bypassId = "bypass";
inline constexpr const char* muteId   = "mute";

inline const Spec* find (const juce::String& id)
{
    for (auto& s : all)
        if (id == s.id)
            return &s;
    return nullptr;
}
} // namespace params
