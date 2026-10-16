#pragma once
#include <juce_osc/juce_osc.h>
#include <juce_audio_processors/juce_audio_processors.h>

// Listens for companion commands on UDP 127.0.0.1:9001 and turns them into host parameter changes.
// Runs on the message thread, so it never touches the audio thread directly.
//
//   /vc/preset  <json string>      crossfade to these values, unspecified params reset to default
//   /vc/nudge   <param> <delta>    relative change
//   /vc/bypass  <0|1>              clean voice
//   /vc/mute    <0|1>              silence while the user speaks a command
//   /vc/ping                       replies /vc/pong to 127.0.0.1:9002
class OscBridge : private juce::OSCReceiver,
                  private juce::OSCReceiver::Listener<juce::OSCReceiver::MessageLoopCallback>
{
public:
    static constexpr int listenPort = 9001;
    static constexpr int replyPort  = 9002;

    explicit OscBridge (juce::AudioProcessorValueTreeState& state);
    ~OscBridge() override;

    bool isListening() const { return listening; }
    juce::String getLastMessage() const { return lastMessage; }

    // Public so they can be unit-tested or called from the editor.
    void applyPreset (const juce::String& json);
    void applyNudge (const juce::String& paramId, float delta);
    void setBool (const char* paramId, bool value);

private:
    void oscMessageReceived (const juce::OSCMessage& m) override;
    void setPlain (const juce::String& paramId, float plainValue);

    juce::AudioProcessorValueTreeState& apvts;
    juce::OSCSender sender;
    bool listening = false;
    juce::String lastMessage { "none yet" };
};
