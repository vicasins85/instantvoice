#pragma once
#include <juce_audio_formats/juce_audio_formats.h>
#include <juce_events/juce_events.h>

// Plays one-shot sound effects (fart, explosion...) mixed into the voice output, so the
// other side of the call hears them. Files are decoded on the message thread; the audio
// thread only swaps a pointer and copies samples.
class SoundPlayer : private juce::Timer
{
public:
    SoundPlayer();
    ~SoundPlayer() override;

    void prepare (double sampleRate);

    // Message thread. Returns the clip length in seconds, or < 0 if the file could not be read.
    double play (const juce::File& file, float gainDb = 0.0f);
    void stop();

    // Audio thread.
    void mixInto (juce::AudioBuffer<float>& buffer, int numChannels);

private:
    struct Clip : public juce::ReferenceCountedObject
    {
        using Ptr = juce::ReferenceCountedObjectPtr<Clip>;
        juce::AudioBuffer<float> audio; // mono, at the session rate
        float gain = 1.0f;
    };

    void timerCallback() override;

    double sr = 48000.0;
    juce::AudioFormatManager formats;

    juce::SpinLock lock;
    Clip::Ptr incoming;           // set by message thread
    bool stopRequested = false;   // set by message thread

    Clip::Ptr active;             // audio thread only
    int position = 0;             // audio thread only
    int fadeOut = -1;             // audio thread only

    juce::ReferenceCountedArray<Clip> keepAlive; // message thread: clips are freed here, never on the audio thread
};
