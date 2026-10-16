#include "PluginProcessor.h"
#include "PluginEditor.h"

juce::AudioProcessorValueTreeState::ParameterLayout VoiceCastProcessor::createLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    for (auto& s : params::all)
    {
        juce::NormalisableRange<float> range (s.min, s.max);
        if (juce::String (s.unit) == "Hz" && s.min > 0.0f)
            range.setSkewForCentre (std::sqrt (s.min * s.max)); // log-ish feel for frequencies

        layout.add (std::make_unique<juce::AudioParameterFloat> (
            juce::ParameterID { s.id, 1 }, s.name, range, s.def,
            juce::AudioParameterFloatAttributes().withLabel (s.unit)));
    }

    layout.add (std::make_unique<juce::AudioParameterBool> (juce::ParameterID { params::bypassId, 1 }, "Bypass", false));
    layout.add (std::make_unique<juce::AudioParameterBool> (juce::ParameterID { params::muteId, 1 }, "Mute", false));
    return layout;
}

VoiceCastProcessor::VoiceCastProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "VoiceCast", createLayout()),
      osc (apvts, sounds)
{
    for (int i = 0; i < params::count; ++i)
        raw[(size_t) i] = apvts.getRawParameterValue (params::all[i].id);
    rawBypass = apvts.getRawParameterValue (params::bypassId);
    rawMute   = apvts.getRawParameterValue (params::muteId);
}

bool VoiceCastProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto out = layouts.getMainOutputChannelSet();
    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;
    return layouts.getMainInputChannelSet() == out;
}

void VoiceCastProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    const int channels = juce::jmax (getTotalNumInputChannels(), getTotalNumOutputChannels());
    chain.prepare (sampleRate, samplesPerBlock, channels);
    sounds.prepare (sampleRate);
    setLatencySamples (chain.getLatencySamples());
}

void VoiceCastProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    std::array<float, params::count> values {};
    for (int i = 0; i < params::count; ++i)
        values[(size_t) i] = raw[(size_t) i]->load();

    chain.setTargets (values, rawBypass->load() > 0.5f, rawMute->load() > 0.5f);
    chain.process (buffer);

    const int ch = juce::jmin (buffer.getNumChannels(), juce::jmax (getTotalNumOutputChannels(), 1));
    sounds.mixInto (buffer, ch);
    for (int c = 0; c < ch; ++c)
    {
        auto* d = buffer.getWritePointer (c);
        for (int i = 0; i < buffer.getNumSamples(); ++i)
        {
            // Soft knee above 0.8: untouched below, never clips hard when a sound plays over the voice.
            const float a = std::abs (d[i]);
            if (a > 0.8f)
                d[i] = std::copysign (0.8f + 0.2f * std::tanh ((a - 0.8f) / 0.2f), d[i]);
        }
    }
}

juce::AudioProcessorEditor* VoiceCastProcessor::createEditor()
{
    return new VoiceCastEditor (*this);
}

void VoiceCastProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    if (auto xml = state.createXml())
        copyXmlToBinary (*xml, destData);
}

void VoiceCastProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (apvts.state.getType()))
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new VoiceCastProcessor();
}
