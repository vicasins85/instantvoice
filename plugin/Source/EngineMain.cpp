// InstantVoiceEngine: the voice effect as a small background process, for people without Wave Link.
// Mic in -> Instant Voicemod effect -> virtual cable out (VB-CABLE on Windows, BlackHole on Mac).
// Meeting apps (Zoom, Meet, Teams, Discord) then use the virtual cable as their microphone.
//
//   InstantVoiceEngine --list --report <file>             write available devices as JSON
//   InstantVoiceEngine --in <name> --out <name> --report <file> [--heartbeat]
//
// Device names match by case-insensitive substring. Empty --in = system default mic.
// --heartbeat: quit if the companion stops pinging for 30 s (so no orphan process keeps the mic).
#include <juce_audio_utils/juce_audio_utils.h>
#include "PluginProcessor.h"

namespace
{
juce::String argValue (const juce::StringArray& args, const juce::String& key)
{
    const int i = args.indexOf (key);
    return (i >= 0 && i + 1 < args.size()) ? args[i + 1].unquoted() : juce::String();
}

void writeReport (const juce::String& path, const juce::var& data)
{
    const auto json = juce::JSON::toString (data, true);
    if (path.isNotEmpty())
        juce::File (path).replaceWithText (json);
    std::printf ("%s\n", json.toRawUTF8());
    std::fflush (stdout);
}

juce::var obj()
{
    return juce::var (new juce::DynamicObject());
}

juce::String findDevice (const juce::StringArray& names, const juce::String& wanted)
{
    if (wanted.isEmpty())
        return {};
    for (auto& n : names)
        if (n.equalsIgnoreCase (wanted))
            return n;
    for (auto& n : names)
        if (n.containsIgnoreCase (wanted))
            return n;
    return {};
}
} // namespace

class EngineCallback : public juce::AudioIODeviceCallback
{
public:
    explicit EngineCallback (VoiceCastProcessor& p) : proc (p) {}

    void audioDeviceAboutToStart (juce::AudioIODevice* device) override
    {
        const int bs = device->getCurrentBufferSizeSamples();
        stereo.setSize (2, juce::jmax (bs, 4096));
        proc.setPlayConfigDetails (2, 2, device->getCurrentSampleRate(), bs);
        proc.prepareToPlay (device->getCurrentSampleRate(), juce::jmax (bs, 4096));
    }

    void audioDeviceStopped() override { proc.releaseResources(); }

    void audioDeviceIOCallbackWithContext (const float* const* in, int numIn, float* const* out, int numOut,
                                           int numSamples, const juce::AudioIODeviceCallbackContext&) override
    {
        juce::AudioBuffer<float> buf (stereo.getArrayOfWritePointers(), 2, numSamples);
        // Mic is usually mono: feed channel 0 (or the average of what we have) to both sides.
        if (numIn > 0 && in[0] != nullptr)
        {
            buf.copyFrom (0, 0, in[0], numSamples);
            if (numIn > 1 && in[1] != nullptr)
            {
                buf.addFrom (0, 0, in[1], numSamples);
                buf.applyGain (0, 0, numSamples, 0.5f);
            }
            buf.copyFrom (1, 0, buf, 0, 0, numSamples);
        }
        else
            buf.clear();

        juce::MidiBuffer midi;
        proc.processBlock (buf, midi);

        for (int c = 0; c < numOut; ++c)
            if (out[c] != nullptr)
                juce::FloatVectorOperations::copy (out[c], buf.getReadPointer (juce::jmin (c, 1)), numSamples);
    }

private:
    VoiceCastProcessor& proc;
    juce::AudioBuffer<float> stereo;
};

class EngineApp : public juce::JUCEApplication, private juce::Timer
{
public:
    const juce::String getApplicationName() override { return "InstantVoiceEngine"; }
    const juce::String getApplicationVersion() override { return "0.2.0"; }
    bool moreThanOneInstanceAllowed() override { return true; }

    void initialise (const juce::String&) override
    {
        const auto args = getCommandLineParameterArray();
        report = argValue (args, "--report");

        auto& types = devices.getAvailableDeviceTypes(); // creates the device types
#if JUCE_WINDOWS
        devices.setCurrentAudioDeviceType ("Windows Audio", true);
#endif
        if (devices.getCurrentDeviceTypeObject() == nullptr && ! types.isEmpty())
            devices.setCurrentAudioDeviceType (types.getFirst()->getTypeName(), true);
        auto* type = devices.getCurrentDeviceTypeObject();
        if (type == nullptr)
            return fail ("no_audio_system", "No audio system available");
        type->scanForDevices();
        const auto inputs = type->getDeviceNames (true);
        const auto outputs = type->getDeviceNames (false);

        if (args.contains ("--list"))
        {
            auto r = obj();
            r.getDynamicObject()->setProperty ("type", type->getTypeName());
            r.getDynamicObject()->setProperty ("inputs", toVar (inputs));
            r.getDynamicObject()->setProperty ("outputs", toVar (outputs));
            r.getDynamicObject()->setProperty ("defaultInput", inputs[type->getDefaultDeviceIndex (true)]);
            r.getDynamicObject()->setProperty ("defaultOutput", outputs[type->getDefaultDeviceIndex (false)]);
            writeReport (report, r);
            setApplicationReturnValue (0);
            quit();
            return;
        }

        const auto wantIn = argValue (args, "--in");
        const auto wantOut = argValue (args, "--out");
        auto inName = findDevice (inputs, wantIn);
        if (inName.isEmpty())
            inName = inputs[type->getDefaultDeviceIndex (true)];
        const auto outName = findDevice (outputs, wantOut);
        if (outName.isEmpty())
            return fail ("output_not_found", "Virtual cable '" + wantOut + "' not found");

        devices.initialise (2, 2, nullptr, false);
        auto setup = devices.getAudioDeviceSetup();
        setup.inputDeviceName = inName;
        setup.outputDeviceName = outName;
        setup.useDefaultInputChannels = true;
        setup.useDefaultOutputChannels = true;
        setup.sampleRate = 48000.0;
        setup.bufferSize = 256;
        auto err = devices.setAudioDeviceSetup (setup, true);
        if (err.isNotEmpty())
        {
            setup.sampleRate = 0; // let the devices pick
            err = devices.setAudioDeviceSetup (setup, true);
        }
        if (err.isNotEmpty() || devices.getCurrentAudioDevice() == nullptr)
            return fail ("open_failed", err.isNotEmpty() ? err : juce::String ("Could not open audio devices"));

        processor = std::make_unique<VoiceCastProcessor>();
        callback = std::make_unique<EngineCallback> (*processor);
        devices.addAudioCallback (callback.get());

        auto* dev = devices.getCurrentAudioDevice();
        auto r = obj();
        r.getDynamicObject()->setProperty ("status", "running");
        r.getDynamicObject()->setProperty ("input", inName);
        r.getDynamicObject()->setProperty ("output", outName);
        r.getDynamicObject()->setProperty ("sampleRate", dev->getCurrentSampleRate());
        r.getDynamicObject()->setProperty ("bufferSize", dev->getCurrentBufferSizeSamples());
        r.getDynamicObject()->setProperty ("oscListening", processor->osc.isListening());
        writeReport (report, r);

        heartbeat = args.contains ("--heartbeat");
        startTimer (2000);
    }

    void shutdown() override
    {
        stopTimer();
        if (callback)
            devices.removeAudioCallback (callback.get());
        devices.closeAudioDevice();
        callback.reset();
        processor.reset();
    }

    void systemRequestedQuit() override { quit(); }
    void anotherInstanceStarted (const juce::String&) override {}

private:
    void timerCallback() override
    {
        if (heartbeat && processor != nullptr
            && juce::Time::getMillisecondCounter() - processor->osc.getLastPingMs() > 30000)
        {
            std::printf ("{\"status\":\"stopped\",\"reason\":\"no heartbeat\"}\n");
            quit();
        }
    }

    void fail (const juce::String& code, const juce::String& message)
    {
        auto r = obj();
        r.getDynamicObject()->setProperty ("status", "error");
        r.getDynamicObject()->setProperty ("error", code);
        r.getDynamicObject()->setProperty ("message", message);
        writeReport (report, r);
        setApplicationReturnValue (3);
        quit();
    }

    static juce::var toVar (const juce::StringArray& a)
    {
        juce::Array<juce::var> v;
        for (auto& s : a)
            v.add (s);
        return v;
    }

    juce::AudioDeviceManager devices;
    std::unique_ptr<VoiceCastProcessor> processor;
    std::unique_ptr<EngineCallback> callback;
    juce::String report;
    bool heartbeat = false;
};

START_JUCE_APPLICATION (EngineApp)
