#include "VoiceChain.h"

namespace
{
constexpr double presetRampSeconds = 0.2;   // spec: preset crossfade ~200 ms
constexpr double bypassRampSeconds = 0.03;
constexpr double muteRampSeconds   = 0.015;

// Pitch engine window. Shorter = less latency, slightly rougher sound.
constexpr double stretchBlockSeconds    = 0.04;
constexpr double stretchIntervalSeconds = 0.01;
} // namespace

void VoiceChain::prepare (double sampleRate, int maxBlockSize, int numChannels)
{
    sr = sampleRate;
    channels = juce::jlimit (1, 2, numChannels);

    for (int i = 0; i < params::count; ++i)
    {
        smooth[(size_t) i].reset (sr, presetRampSeconds);
        smooth[(size_t) i].setCurrentAndTargetValue (params::all[i].def);
    }
    bypassMix.reset (sr, bypassRampSeconds);
    bypassMix.setCurrentAndTargetValue (0.0f);
    muteGain.reset (sr, muteRampSeconds);
    muteGain.setCurrentAndTargetValue (1.0f);
    pitchEngage.reset (sr, presetRampSeconds);
    pitchEngage.setCurrentAndTargetValue (0.0f);

    stretch.configure (channels,
                       (int) (sr * stretchBlockSeconds),
                       (int) (sr * stretchIntervalSeconds));
    latency = stretch.inputLatency() + stretch.outputLatency();

    juce::dsp::ProcessSpec spec { sr, (juce::uint32) maxBlockSize, (juce::uint32) channels };

    dryDelay.prepare (spec);
    dryDelay.setMaximumDelayInSamples (latency + 1);
    dryDelay.setDelay ((float) latency);

    dryBuffer.setSize (channels, maxBlockSize);
    stretchBuffer.setSize (channels, maxBlockSize);
    inPtrs.assign ((size_t) channels, nullptr);
    outPtrs.assign ((size_t) channels, nullptr);

    highpass.prepare (spec);
    highpass.setType (juce::dsp::StateVariableTPTFilterType::highpass);
    lowpass.prepare (spec);
    lowpass.setType (juce::dsp::StateVariableTPTFilterType::lowpass);

    for (auto& f : lowShelf)
    {
        f.coefficients = new juce::dsp::IIR::Coefficients<float> (1.0f, 0.0f, 1.0f, 0.0f);
        f.prepare ({ sr, (juce::uint32) maxBlockSize, 1 });
    }
    for (auto& f : highShelf)
    {
        f.coefficients = new juce::dsp::IIR::Coefficients<float> (1.0f, 0.0f, 1.0f, 0.0f);
        f.prepare ({ sr, (juce::uint32) maxBlockSize, 1 });
    }
    lastLowShelfDb = lastHighShelfDb = 1000.0f;

    chorus.prepare (spec);
    chorus.setRate (1.2f);
    chorus.setDepth (0.35f);
    chorus.setCentreDelay (8.0f);
    chorus.setFeedback (0.0f);

    reverb.prepare (spec);

    reset();
}

void VoiceChain::reset()
{
    stretch.reset();
    dryDelay.reset();
    highpass.reset();
    lowpass.reset();
    for (auto& f : lowShelf)  f.reset();
    for (auto& f : highShelf) f.reset();
    chorus.reset();
    reverb.reset();
    ringPhase = 0.0;
}

void VoiceChain::setTargets (const std::array<float, params::count>& values, bool bypass, bool mute)
{
    for (int i = 0; i < params::count; ++i)
        smooth[(size_t) i].setTargetValue (values[(size_t) i]);

    bypassMix.setTargetValue (bypass ? 1.0f : 0.0f);
    muteGain.setTargetValue (mute ? 0.0f : 1.0f);

    const bool needsPitch = std::abs (values[params::pitch]) > 0.01f
                         || std::abs (values[params::formant]) > 0.01f;
    pitchEngage.setTargetValue (needsPitch ? 1.0f : 0.0f);
}

void VoiceChain::updateBlockRateDsp (int numSamples)
{
    auto blockValue = [&] (params::Index i)
    {
        auto& s = smooth[(size_t) i];
        s.skip (numSamples);
        return s.getCurrentValue();
    };

    const float pitch   = blockValue (params::pitch);
    const float formant = blockValue (params::formant);
    stretch.setTransposeSemitones (pitch, (float) (8000.0 / sr));
    // compensatePitch = true keeps the natural formants when pitch moves; formant then shifts on top.
    stretch.setFormantSemitones (formant, true);

    highpass.setCutoffFrequency (blockValue (params::highpass));
    lowpass.setCutoffFrequency (juce::jmin (blockValue (params::lowpass), (float) (sr * 0.45)));

    const float ls = blockValue (params::lowShelf);
    if (std::abs (ls - lastLowShelfDb) > 0.01f)
    {
        auto c = juce::dsp::IIR::Coefficients<float>::makeLowShelf (sr, 250.0, 0.707, juce::Decibels::decibelsToGain (ls));
        for (auto& f : lowShelf) *f.coefficients = *c;
        lastLowShelfDb = ls;
    }

    const float hs = blockValue (params::highShelf);
    if (std::abs (hs - lastHighShelfDb) > 0.01f)
    {
        auto c = juce::dsp::IIR::Coefficients<float>::makeHighShelf (sr, 3500.0, 0.707, juce::Decibels::decibelsToGain (hs));
        for (auto& f : highShelf) *f.coefficients = *c;
        lastHighShelfDb = hs;
    }

    chorus.setMix (blockValue (params::chorusMix));

    const float revMix = blockValue (params::reverbMix);
    juce::dsp::Reverb::Parameters rp;
    rp.roomSize   = blockValue (params::reverbSize);
    rp.damping    = 0.4f;
    // juce::dsp::Reverb scales dry by 2 and wet by 3 internally, so 0.5 dry = unity.
    rp.wetLevel   = revMix * 0.25f;
    rp.dryLevel   = 0.5f * (1.0f - revMix * 0.5f);
    rp.width      = 1.0f;
    rp.freezeMode = 0.0f;
    reverb.setParameters (rp);
}

void VoiceChain::process (juce::AudioBuffer<float>& buffer)
{
    // Hosts (Wave Link on macOS especially) may send blocks larger than announced. Split them.
    const int maxChunk = dryBuffer.getNumSamples();
    const int total = buffer.getNumSamples();
    if (total <= maxChunk)
    {
        processChunk (buffer);
        return;
    }
    for (int start = 0; start < total; start += maxChunk)
    {
        const int len = juce::jmin (maxChunk, total - start);
        juce::AudioBuffer<float> view (buffer.getArrayOfWritePointers(), buffer.getNumChannels(), start, len);
        processChunk (view);
    }
}

void VoiceChain::processChunk (juce::AudioBuffer<float>& buffer)
{
    const int n  = buffer.getNumSamples();
    const int ch = juce::jmin (channels, buffer.getNumChannels());
    if (n == 0 || ch == 0)
        return;

    // 1. Clean signal, delayed by the plugin latency so wet and dry stay aligned.
    for (int c = 0; c < ch; ++c)
        dryBuffer.copyFrom (c, 0, buffer, c, 0, n);
    {
        auto block = juce::dsp::AudioBlock<float> (dryBuffer).getSubsetChannelBlock (0, (size_t) ch).getSubBlock (0, (size_t) n);
        juce::dsp::ProcessContextReplacing<float> ctx (block);
        dryDelay.process (ctx);
    }

    // 2. Pitch / formant engine (always running so latency stays constant).
    updateBlockRateDsp (n);
    for (int c = 0; c < ch; ++c)
    {
        inPtrs[(size_t) c]  = buffer.getWritePointer (c);
        outPtrs[(size_t) c] = stretchBuffer.getWritePointer (c);
    }
    for (int c = ch; c < channels; ++c)
    {
        inPtrs[(size_t) c]  = dryBuffer.getWritePointer (0); // unused extra channels
        outPtrs[(size_t) c] = stretchBuffer.getWritePointer (c);
    }
    stretch.process (inPtrs.data(), n, outPtrs.data(), n);

    // 3. Per-sample stages.
    auto& sDrive  = smooth[params::drive];
    auto& sBits   = smooth[params::bitcrush];
    auto& sRingHz = smooth[params::ringHz];
    auto& sRingMx = smooth[params::ringMix];
    auto& sOut    = smooth[params::outputGain];

    for (int i = 0; i < n; ++i)
    {
        const float engage = pitchEngage.getNextValue();
        const float drive  = sDrive.getNextValue();
        const float bits   = sBits.getNextValue();
        const float ringHz = sRingHz.getNextValue();
        const float ringMx = sRingMx.getNextValue();

        const float driveGain = 1.0f + 19.0f * drive;
        const float driveComp = 1.0f / std::sqrt (driveGain);
        const float step      = bits < 15.9f ? 2.0f / std::pow (2.0f, bits) : 0.0f;

        const float carrier = (float) std::sin (ringPhase);
        ringPhase += juce::MathConstants<double>::twoPi * ringHz / sr;
        if (ringPhase > juce::MathConstants<double>::twoPi)
            ringPhase -= juce::MathConstants<double>::twoPi;

        for (int c = 0; c < ch; ++c)
        {
            const float dry = dryBuffer.getSample (c, i);
            float x = dry + engage * (stretchBuffer.getSample (c, i) - dry);

            x = highpass.processSample (c, x);

            if (drive > 0.001f)
                x = x + drive * (std::tanh (x * driveGain) * driveComp - x);

            if (step > 0.0f)
                x = std::round (x / step) * step;

            if (ringMx > 0.001f)
                x = x * (1.0f - ringMx) + x * carrier * ringMx;

            x = lowShelf[(size_t) c].processSample (x);
            x = highShelf[(size_t) c].processSample (x);
            x = lowpass.processSample (c, x);

            buffer.setSample (c, i, x);
        }
    }

    // 4. Chorus + reverb (block based).
    {
        auto block = juce::dsp::AudioBlock<float> (buffer).getSubsetChannelBlock (0, (size_t) ch).getSubBlock (0, (size_t) n);
        juce::dsp::ProcessContextReplacing<float> ctx (block);
        chorus.process (ctx);
        reverb.process (ctx);
    }

    // 5. Output gain, bypass crossfade, mute.
    for (int i = 0; i < n; ++i)
    {
        const float gain   = juce::Decibels::decibelsToGain (sOut.getNextValue());
        const float bypass = bypassMix.getNextValue();
        const float mute   = muteGain.getNextValue();

        for (int c = 0; c < ch; ++c)
        {
            const float wet = buffer.getSample (c, i) * gain;
            const float dry = dryBuffer.getSample (c, i);
            const float y   = (wet + bypass * (dry - wet)) * mute;
            buffer.setSample (c, i, juce::jlimit (-1.0f, 1.0f, y));
        }
    }

    for (int c = ch; c < buffer.getNumChannels(); ++c)
        buffer.clear (c, 0, n);
}
