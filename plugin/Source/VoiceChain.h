#pragma once
#include <juce_dsp/juce_dsp.h>
#include <signalsmith-stretch/signalsmith-stretch.h>
#include <array>
#include "Params.h"

// Real-time voice effect chain.
// Signal flow: Pitch/Formant -> High-pass -> Drive -> Bitcrush -> Ring mod
//              -> Low shelf / High shelf / Low-pass -> Chorus -> Reverb -> Output gain
// Then: wet/dry crossfade for bypass, and a fast mute gain for push-to-talk commands.
class VoiceChain
{
public:
    void prepare (double sampleRate, int maxBlockSize, int numChannels);
    void reset();

    // Targets are plain (non-normalised) values. All changes are smoothed internally.
    void setTargets (const std::array<float, params::count>& values, bool bypass, bool mute);

    void process (juce::AudioBuffer<float>& buffer);

    int getLatencySamples() const { return latency; }

private:
    void processChunk (juce::AudioBuffer<float>& buffer);
    void updateBlockRateDsp (int numSamples);

    double sr = 48000.0;
    int channels = 1;
    int latency = 0;

    // Smoothing: ~200 ms crossfade for preset changes, faster for bypass and mute.
    std::array<juce::SmoothedValue<float>, params::count> smooth;
    juce::SmoothedValue<float> bypassMix;   // 0 = effect, 1 = clean
    juce::SmoothedValue<float> muteGain;    // 1 = audible, 0 = muted
    juce::SmoothedValue<float> pitchEngage; // 0 = pitch engine idle (delayed dry), 1 = engaged

    signalsmith::stretch::SignalsmithStretch<float> stretch;
    juce::dsp::DelayLine<float, juce::dsp::DelayLineInterpolationTypes::None> dryDelay { 1 << 16 };

    juce::AudioBuffer<float> dryBuffer, stretchBuffer;
    std::vector<float*> inPtrs, outPtrs;

    juce::dsp::StateVariableTPTFilter<float> highpass, lowpass;
    std::array<juce::dsp::IIR::Filter<float>, 2> lowShelf, highShelf; // max 2 channels
    juce::dsp::Chorus<float> chorus;
    juce::dsp::Reverb reverb;

    double ringPhase = 0.0;
    float lastLowShelfDb = 1000.0f, lastHighShelfDb = 1000.0f;
};
