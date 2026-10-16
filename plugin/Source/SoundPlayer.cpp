#include "SoundPlayer.h"

SoundPlayer::SoundPlayer()
{
    formats.registerBasicFormats();
    startTimer (2000);
}

SoundPlayer::~SoundPlayer()
{
    stopTimer();
}

void SoundPlayer::prepare (double sampleRate)
{
    sr = sampleRate;
}

double SoundPlayer::play (const juce::File& file, float gainDb)
{
    std::unique_ptr<juce::AudioFormatReader> reader (formats.createReaderFor (file));
    if (reader == nullptr || reader->lengthInSamples <= 0)
        return -1.0;

    const int maxSamples = (int) juce::jmin<juce::int64> (reader->lengthInSamples, (juce::int64) (reader->sampleRate * 20.0));
    juce::AudioBuffer<float> raw ((int) reader->numChannels, maxSamples);
    reader->read (&raw, 0, maxSamples, 0, true, true);

    // Mix down to mono.
    juce::AudioBuffer<float> mono (1, maxSamples);
    mono.clear();
    for (int c = 0; c < raw.getNumChannels(); ++c)
        mono.addFrom (0, 0, raw, c, 0, maxSamples, 1.0f / (float) raw.getNumChannels());

    Clip::Ptr clip = new Clip();
    const double ratio = reader->sampleRate / sr;
    const int outLen = (int) std::ceil (maxSamples / ratio);
    clip->audio.setSize (1, outLen);
    clip->audio.clear();
    juce::LagrangeInterpolator interp;
    interp.process (ratio, mono.getReadPointer (0), clip->audio.getWritePointer (0), outLen, maxSamples, 0);
    clip->gain = juce::Decibels::decibelsToGain (gainDb);

    keepAlive.add (clip);
    {
        const juce::SpinLock::ScopedLockType sl (lock);
        incoming = clip;
        stopRequested = false;
    }
    return outLen / sr;
}

void SoundPlayer::stop()
{
    const juce::SpinLock::ScopedLockType sl (lock);
    incoming = nullptr;
    stopRequested = true;
}

void SoundPlayer::mixInto (juce::AudioBuffer<float>& buffer, int numChannels)
{
    {
        const juce::SpinLock::ScopedTryLockType sl (lock);
        if (sl.isLocked())
        {
            if (incoming != nullptr)
            {
                active = incoming;   // keepAlive still holds a reference, so nothing is freed here
                incoming = nullptr;
                position = 0;
                fadeOut = -1;
            }
            else if (stopRequested && active != nullptr)
            {
                fadeOut = (int) (sr * 0.03);
            }
            stopRequested = false;
        }
    }

    if (active == nullptr)
        return;

    const int n = buffer.getNumSamples();
    const int len = active->audio.getNumSamples();
    const float* src = active->audio.getReadPointer (0);
    const int fadeTotal = (int) (sr * 0.03);

    for (int i = 0; i < n && position < len; ++i, ++position)
    {
        float g = active->gain;
        if (fadeOut >= 0)
        {
            g *= (float) fadeOut / (float) juce::jmax (1, fadeTotal);
            if (--fadeOut <= 0)
            {
                position = len;
                break;
            }
        }
        const float s = src[position] * g;
        for (int c = 0; c < numChannels; ++c)
            buffer.addSample (c, i, s);
    }

    if (position >= len)
        active = nullptr; // keepAlive still owns it
}

void SoundPlayer::timerCallback()
{
    // Free clips that only keepAlive references (the audio thread has finished with them).
    for (int i = keepAlive.size(); --i >= 0;)
        if (keepAlive.getObjectPointerUnchecked (i)->getReferenceCount() == 1)
            keepAlive.remove (i);
}
