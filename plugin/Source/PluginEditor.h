#pragma once
#include <juce_audio_utils/juce_audio_utils.h>
#include "PluginProcessor.h"

// Minimal UI: OSC status line plus the generic parameter sliders (for debugging by hand).
class VoiceCastEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit VoiceCastEditor (VoiceCastProcessor&);
    ~VoiceCastEditor() override = default;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;

    VoiceCastProcessor& proc;
    juce::Label status;
    juce::GenericAudioProcessorEditor generic;
};
