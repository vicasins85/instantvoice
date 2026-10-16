#include "OscBridge.h"
#include "Params.h"

OscBridge::OscBridge (juce::AudioProcessorValueTreeState& state, SoundPlayer& soundPlayer)
    : apvts (state), sounds (soundPlayer)
{
    // Bind to localhost only: nothing outside this computer can talk to it, and no firewall prompt.
    socket = std::make_unique<juce::DatagramSocket> (false);
    listening = socket->bindToPort (listenPort, "127.0.0.1") && connectToSocket (*socket);
    if (listening)
        addListener (this);
    else
    {
        DBG ("VoiceCast: could not bind UDP port " << listenPort << " (another instance running?)");
    }
}

OscBridge::~OscBridge()
{
    removeListener (this);
    disconnect();
}

void OscBridge::setPlain (const juce::String& paramId, float plainValue)
{
    if (auto* p = apvts.getParameter (paramId))
    {
        const auto& range = apvts.getParameterRange (paramId);
        p->beginChangeGesture();
        p->setValueNotifyingHost (range.convertTo0to1 (range.snapToLegalValue (plainValue)));
        p->endChangeGesture();
    }
}

void OscBridge::setBool (const char* paramId, bool value)
{
    if (auto* p = apvts.getParameter (paramId))
    {
        p->beginChangeGesture();
        p->setValueNotifyingHost (value ? 1.0f : 0.0f);
        p->endChangeGesture();
    }
}

void OscBridge::applyPreset (const juce::String& json)
{
    const auto parsed = juce::JSON::parse (json);
    auto* obj = parsed.getDynamicObject();
    if (obj == nullptr)
    {
        lastMessage = "invalid preset JSON";
        return;
    }

    for (auto& spec : params::all)
    {
        const juce::Identifier key (spec.id);
        const float value = obj->hasProperty (key) ? (float) obj->getProperty (key) : spec.def;
        setPlain (spec.id, juce::jlimit (spec.min, spec.max, value));
    }
    setBool (params::bypassId, false);
    lastMessage = "preset applied";
}

void OscBridge::applyNudge (const juce::String& paramId, float delta)
{
    const auto* spec = params::find (paramId);
    if (spec == nullptr)
    {
        lastMessage = "unknown param " + paramId;
        return;
    }
    const float current = apvts.getRawParameterValue (paramId)->load();
    setPlain (paramId, juce::jlimit (spec->min, spec->max, current + delta));
    setBool (params::bypassId, false);
    lastMessage = "nudge " + paramId;
}

void OscBridge::oscMessageReceived (const juce::OSCMessage& m)
{
    const auto address = m.getAddressPattern().toString();

    auto intArg = [&m] (int idx, int fallback)
    {
        if (m.size() <= idx) return fallback;
        if (m[idx].isInt32())   return (int) m[idx].getInt32();
        if (m[idx].isFloat32()) return (int) m[idx].getFloat32();
        return fallback;
    };

    if (address == "/vc/preset" && m.size() >= 1 && m[0].isString())
        applyPreset (m[0].getString());
    else if (address == "/vc/nudge" && m.size() >= 2 && m[0].isString())
        applyNudge (m[0].getString(), m[1].isFloat32() ? m[1].getFloat32() : (float) intArg (1, 0));
    else if (address == "/vc/bypass")
        setBool (params::bypassId, intArg (0, 1) != 0);
    else if (address == "/vc/mute")
        setBool (params::muteId, intArg (0, 1) != 0);
    else if (address == "/vc/sound" && m.size() >= 1 && m[0].isString())
    {
        const float gain = (m.size() >= 2 && m[1].isFloat32()) ? m[1].getFloat32() : 0.0f;
        const double secs = sounds.play (juce::File (m[0].getString()), gain);
        lastMessage = secs < 0 ? juce::String ("sound not found") : "sound " + juce::String (secs, 1) + "s";
        return;
    }
    else if (address == "/vc/sound_stop")
        sounds.stop();
    else if (address == "/vc/ping")
    {
        lastPingMs = juce::Time::getMillisecondCounter();
        if (sender.connect ("127.0.0.1", replyPort))
            sender.send ("/vc/pong");
    }
    else
    {
        lastMessage = "ignored " + address;
        return;
    }

    if (address != "/vc/preset" && address != "/vc/nudge")
        lastMessage = address;
}
