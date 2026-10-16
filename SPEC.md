# Instant Voicemod: spec

> Updated: the companion is now a desktop app (window + tray, start at login), shipped as one-click installers built by GitHub Actions. See README.md.

Say "make me sound like an angry ogre" while holding a hotkey. The effect is applied to your mic in real time inside Elgato Wave Link. Another hotkey (or saying "normal voice") removes it.

## Architecture

| Component | Role | Stack |
|---|---|---|
| `plugin/` | VST3 (Windows) / AU (macOS) effect loaded in Wave Link on the mic channel, plus a standalone app. Real-time DSP chain driven by parameters received over OSC | C++, JUCE (via CMake FetchContent), Signalsmith Stretch for pitch + formant |
| `companion/` | System tray app. Global hotkeys, push-to-talk capture, local transcription, intent-to-parameters translation, OSC sender | Python 3.11, `pynput`, `sounddevice`, `faster-whisper`, `anthropic`, `python-osc`, `pystray` |
| Transport | Companion sends commands to plugin | OSC over UDP, `127.0.0.1:9001` |

Target platforms: Windows 10/11 (Wave Link loads VST3) and macOS 11+ (Wave Link loads Audio Units only). Universal binary on Mac.

## DSP chain (plugin)

Order: High-pass → Pitch/Formant → Drive → Bitcrush → Ring mod → EQ (low shelf, high shelf, low-pass) → Chorus → Reverb → Output gain

| Parameter | Range | Default |
|---|---|---|
| `pitch_semitones` | -12 to +12 | 0 |
| `formant_semitones` | -12 to +12 | 0 |
| `drive` | 0 to 1 | 0 |
| `bitcrush_bits` | 4 to 16 (16 = off) | 16 |
| `ring_hz` | 0 to 2000 | 0 |
| `ring_mix` | 0 to 1 | 0 |
| `highpass_hz` | 20 to 1000 | 20 |
| `lowpass_hz` | 1000 to 20000 | 20000 |
| `low_shelf_db` | -12 to +12 | 0 |
| `high_shelf_db` | -12 to +12 | 0 |
| `chorus_mix` | 0 to 1 | 0 |
| `reverb_size` | 0 to 1 | 0.3 |
| `reverb_mix` | 0 to 1 | 0 |
| `output_gain_db` | -12 to +12 | 0 |

Requirements:
- All parameters smoothed (no zipper noise). Preset changes crossfade over ~200 ms.
- Total added latency 40 ms (pitch engine window; tunable in VoiceChain.cpp).
- Exposed as normal host parameters too, so they can be tweaked by hand for debugging.

## OSC API (plugin listens on UDP 9001)

| Address | Args | Effect |
|---|---|---|
| `/vc/preset` | string (JSON object, any subset of parameters) | Crossfade to these values; unspecified params reset to default |
| `/vc/nudge` | string param, float delta | Relative change ("deeper", "less echo") |
| `/vc/bypass` | int 0/1 | 1 = clean voice instantly |
| `/vc/mute` | int 0/1 | Silence output while the user speaks a command |
| `/vc/ping` | none | Plugin replies `/vc/pong` to 127.0.0.1:9002 (health check) |

## Companion behavior

| Trigger | Action |
|---|---|
| Hold `Ctrl+Alt+V` | Send `/vc/mute 1`, record mic |
| Release `Ctrl+Alt+V` | Send `/vc/mute 0`, transcribe, resolve intent, send result |
| `Ctrl+Alt+X` | Send `/vc/bypass 1` |
| `Ctrl+Alt+Shift+1..3` | Save current preset to slot 1 to 3 |
| `Ctrl+Alt+1..3` | Recall slot |

Intent resolution:
1. Normalize transcript. If it matches a clear/off phrase ("normal voice", "voz normal", "quitar"), send bypass.
2. If it matches a cached description, send cached preset (no API call).
3. If it is relative ("more", "less", "más grave"), send `/vc/nudge`.
4. Otherwise call Claude (`claude-haiku-5-5`) with a tool whose input schema is the parameter table above. Include 10 to 15 few-shot examples (ogre, robot, radio, demon, chipmunk, cave, alien, giant, old radio, underwater). Cache the result. If there is no API key or the call fails, fall back to keyword matching on presets.json.

Transcription: `faster-whisper` `small` model on CPU, language auto (Spanish + English).

Config file `companion/config.toml`: hotkeys, mic device, OSC port, API key env var name, whisper model size.

## Phases and acceptance

| Phase | Done when |
|---|---|
| 1. Plugin | `.vst3` loads in Wave Link mic channel; `scripts/send_preset.py ogre` audibly changes voice; bypass works; no clicks |
| 2. Companion skeleton | Holding the hotkey mutes, releasing sends a hardcoded preset |
| 3. Intent | Spoken description produces a sensible preset in under 2 s end to end |
| 4. Polish | Voice clear command, cache, nudges, slots, tray icon with status |

## Repo layout

```
voicecast/
  SPEC.md
  plugin/            CMakeLists.txt, Source/
  companion/         main.py, intent.py, audio.py, osc_client.py, config.toml, presets.json
  scripts/           send_preset.py
```
