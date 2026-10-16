#include "PluginEditor.h"

VoiceCastEditor::VoiceCastEditor (VoiceCastProcessor& p)
    : AudioProcessorEditor (p), proc (p), generic (p)
{
    status.setFont (juce::FontOptions (14.0f));
    status.setColour (juce::Label::textColourId, juce::Colours::white);
    addAndMakeVisible (status);
    addAndMakeVisible (generic);
    setSize (460, 560);
    setResizable (true, false);
    timerCallback();
    startTimerHz (4);
}

void VoiceCastEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff1b1d24));
}

void VoiceCastEditor::resized()
{
    auto area = getLocalBounds();
    status.setBounds (area.removeFromTop (32).reduced (10, 4));
    generic.setBounds (area);
}

void VoiceCastEditor::timerCallback()
{
    const auto osc = proc.osc.isListening()
        ? juce::String ("OSC listening on ") + juce::String (OscBridge::listenPort)
        : juce::String ("Port busy: another Instant Voicemod effect is loaded");
    status.setText ("Instant Voicemod  |  " + osc + "  |  last: " + proc.osc.getLastMessage(),
                    juce::dontSendNotification);
}
