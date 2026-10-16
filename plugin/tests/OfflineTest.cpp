// Renders a synthetic voice-like signal through each preset and checks the output is sane.
#include <juce_audio_formats/juce_audio_formats.h>
#include "../Source/PluginProcessor.h"

static juce::String presets[][2] = {
    { "clean",    "{}" },
    { "ogre",     R"({"pitch_semitones":-6,"formant_semitones":-4,"drive":0.35,"low_shelf_db":5,"reverb_size":0.3,"reverb_mix":0.12})" },
    { "robot",    R"({"ring_hz":90,"ring_mix":0.7,"bitcrush_bits":10,"highpass_hz":150})" },
    { "radio",    R"({"highpass_hz":400,"lowpass_hz":3200,"drive":0.25,"bitcrush_bits":12})" },
    { "chipmunk", R"({"pitch_semitones":8,"formant_semitones":5})" },
    { "cave",     R"({"reverb_size":0.95,"reverb_mix":0.6,"low_shelf_db":3})" },
};

// Optional: VoiceCastTest <input.wav> <outDir> renders every preset to a WAV so you can listen.
static int renderWav (const juce::File& in, const juce::File& outDir)
{
    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader (fm.createReaderFor (in));
    if (reader == nullptr) { std::printf ("cannot read %s\n", in.getFullPathName().toRawUTF8()); return 1; }
    juce::AudioBuffer<float> src (2, (int) reader->lengthInSamples);
    reader->read (&src, 0, src.getNumSamples(), 0, true, true);
    outDir.createDirectory();
    for (auto& p : presets)
    {
        VoiceCastProcessor proc;
        proc.setPlayConfigDetails (2, 2, reader->sampleRate, 512);
        proc.prepareToPlay (reader->sampleRate, 512);
        proc.osc.applyPreset (p[1]);
        const int lat = proc.getLatencySamples();
        juce::AudioBuffer<float> out (2, src.getNumSamples() + lat + (int) reader->sampleRate);
        out.clear();
        for (int c = 0; c < 2; ++c) out.copyFrom (c, 0, src, c, 0, src.getNumSamples());
        juce::MidiBuffer midi;
        // Skip the 200 ms crossfade from default so the file starts on the preset.
        { juce::AudioBuffer<float> warm (2, 512); for (int k = 0; k < 40; ++k) { warm.clear(); proc.processBlock (warm, midi); } }
        for (int pos = 0; pos < out.getNumSamples(); pos += 512)
        {
            const int n = juce::jmin (512, out.getNumSamples() - pos);
            juce::AudioBuffer<float> view (out.getArrayOfWritePointers(), 2, pos, n);
            proc.processBlock (view, midi);
        }
        auto f = outDir.getChildFile (p[0] + ".wav");
        f.deleteFile();
        juce::WavAudioFormat wav;
        std::unique_ptr<juce::AudioFormatWriter> w (wav.createWriterFor (new juce::FileOutputStream (f), reader->sampleRate, 2, 16, {}, 0));
        w->writeFromAudioSampleBuffer (out, lat, out.getNumSamples() - lat);
        std::printf ("wrote %s\n", f.getFullPathName().toRawUTF8());
    }
    return 0;
}

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI init;
    if (argc == 3)
        return renderWav (juce::File (argv[1]), juce::File (argv[2]));

    VoiceCastProcessor proc;
    const double sr = 48000.0;
    const int block = 512;
    proc.setPlayConfigDetails (2, 2, sr, block);
    proc.prepareToPlay (sr, block);
    std::printf ("osc listening: %s\n", proc.osc.isListening() ? "yes" : "no");
    std::printf ("latency: %d samples (%.1f ms)\n", proc.getLatencySamples(), proc.getLatencySamples() * 1000.0 / sr);

    juce::MidiBuffer midi;
    double phase = 0.0;
    bool ok = true;

    for (auto& p : presets)
    {
        proc.osc.applyPreset (p[1]);
        double inE = 0, outE = 0;
        bool finite = true;
        const int blocks = (int) (1.5 * sr / block);
        for (int b = 0; b < blocks; ++b)
        {
            // Vary block size to mimic macOS hosts (including oversize blocks).
            const int n = (b % 7 == 3) ? 1500 : block;
            juce::AudioBuffer<float> buf (2, n);
            for (int i = 0; i < n; ++i)
            {
                // 140 Hz "voice": harmonics with a slow amplitude envelope
                float s = 0;
                for (int h = 1; h <= 12; ++h) s += std::sin (phase * h) / (float) h;
                s *= 0.15f * (0.6f + 0.4f * (float) std::sin (phase * 0.01));
                phase += juce::MathConstants<double>::twoPi * 140.0 / sr;
                buf.setSample (0, i, s); buf.setSample (1, i, s);
                if (b > blocks / 2) inE += s * s;
            }
            proc.processBlock (buf, midi);
            for (int i = 0; i < n; ++i)
            {
                const float y = buf.getSample (0, i);
                if (! std::isfinite (y)) finite = false;
                if (b > blocks / 2) outE += y * y;
            }
        }
        const double ratioDb = 10.0 * std::log10 ((outE + 1e-12) / (inE + 1e-12));
        const bool pass = finite && ratioDb > -20.0 && ratioDb < 12.0;
        ok = ok && pass;
        std::printf ("%-9s out/in level %+6.1f dB  %s\n", p[0].toRawUTF8(), ratioDb, pass ? "OK" : "FAIL");
    }

    // Mute and bypass
    proc.osc.setBool (params::muteId, true);
    juce::AudioBuffer<float> buf (2, block);
    for (int k = 0; k < 10; ++k) { buf.applyGain (0); for (int i = 0; i < block; ++i) buf.setSample (0, i, 0.3f * (float) std::sin (i * 0.05)); proc.processBlock (buf, midi); }
    const bool muted = buf.getMagnitude (0, 0, block) < 1e-4f;
    std::printf ("mute     %s\n", muted ? "OK" : "FAIL");
    proc.osc.setBool (params::muteId, false);
    proc.osc.applyNudge ("pitch_semitones", -2.0f);

    // Sound effect mixed over silence, plus delay
    {
        auto tmp = juce::File::getSpecialLocation (juce::File::tempDirectory).getChildFile ("iv_test_tone.wav");
        juce::AudioBuffer<float> tone (1, 22050);
        for (int i = 0; i < tone.getNumSamples(); ++i) tone.setSample (0, i, 0.5f * (float) std::sin (i * 0.06));
        tmp.deleteFile();
        juce::WavAudioFormat wav;
        { std::unique_ptr<juce::AudioFormatWriter> w (wav.createWriterFor (new juce::FileOutputStream (tmp), 44100.0, 1, 16, {}, 0));
          w->writeFromAudioSampleBuffer (tone, 0, tone.getNumSamples()); }
        const double secs = proc.sounds.play (tmp);
        juce::AudioBuffer<float> b (2, block); float peak = 0;
        for (int k = 0; k < 20; ++k) { b.clear(); proc.processBlock (b, midi); peak = juce::jmax (peak, b.getMagnitude (0, 0, block)); }
        std::printf ("sound    len %.2fs peak %.2f %s\n", secs, peak, (secs > 0.45 && peak > 0.2f) ? "OK" : "FAIL");
        ok = ok && secs > 0.45 && peak > 0.2f;
        proc.osc.applyPreset (R"({"delay_ms":250,"delay_mix":0.5})");
        float tail = 0;
        for (int k = 0; k < 60; ++k) { b.clear(); if (k == 0) b.setSample (0, 10, 0.8f), b.setSample (1, 10, 0.8f); proc.processBlock (b, midi); if (k > 25) tail = juce::jmax (tail, b.getMagnitude (0, 0, block)); }
        std::printf ("delay    echo tail %.3f %s\n", tail, tail > 0.001f ? "OK" : "FAIL");
    }
    std::printf ("nudge    pitch now %.1f\n", proc.apvts.getRawParameterValue ("pitch_semitones")->load());
    return ok && muted ? 0 : 1;
}
