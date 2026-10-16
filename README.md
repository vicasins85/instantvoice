# Instant Voicemod

Say it and it happens. In a call, say "estoy enfadado" and your voice turns angry for a few seconds. Say "quiero tirarme un pedo" and everyone hears a fart. Or hold a shortcut, say "angry ogre", let go: you are an ogre until you say "voz normal".

Works in Zoom, Google Meet, Teams, Discord and any app with a microphone setting. Starts with your computer. A small status pill floats over every app.

**Full step-by-step setup guide:** see the Notion guide (link in the project page), or the summary below.

## Install

| Step | Windows | Mac |
|---|---|---|
| 1. Virtual cable (once) | [VB-CABLE](https://vb-audio.com/Cable/): unzip, right-click `VBCABLE_Setup_x64.exe` → Run as administrator → Install Driver → restart | [BlackHole 2ch](https://existential.audio/blackhole/) installer, or `brew install blackhole-2ch` |
| 2. The app | `Instant-Voicemod-Setup.exe` from [Releases](../../releases/tag/latest) | `Instant-Voicemod-mac-AppleSilicon.pkg` or `-Intel.pkg` from [Releases](../../releases/tag/latest) |
| 3. First-time warning | "Windows protected your PC" → More info → Run anyway | Right-click the `.pkg` → Open → Open |
| 4. Permissions | Allow microphone if asked | Allow Microphone, then System Settings → Privacy & Security → enable Instant Voicemod in **Accessibility** and **Input Monitoring** |
| 5. In your call app | Microphone: **CABLE Output (VB-Audio Virtual Cable)** | Microphone: **BlackHole 2ch** |

Using Wave Link instead? In the app: Settings → "How your voice reaches calls" → Wave Link effect, then add the **Instant Voicemod** effect to your mic in Wave Link.

## Use

| Say (with "Listen for triggers" on) | Result |
|---|---|
| "estoy enfadado" / "I'm angry" | Angry voice for a few seconds (set the length in Settings) |
| "estoy feliz", "estoy triste", "tengo miedo", "estoy cansado", "estoy emocionado" | That mood, then back to normal |
| "quiero tirarme un pedo" | Fart |
| "que suene una bomba" / "que suene una bocina" / "que suene ..." | Explosion / air horn / anything (anything needs a Freesound key) |
| "quiero sonar como un ogro" | Any voice for a few seconds (any description needs an AI key) |
| "voz normal" | Back to you |

| Shortcut | Result |
|---|---|
| Hold `Ctrl + Alt + V` (Mac: `Ctrl + Option + V`), speak, release | Same phrases, but the voice **stays** and nobody hears the command |
| `Ctrl + Alt + X` | Normal voice |
| `Ctrl + Alt + Shift + 1/2/3`, `Ctrl + Alt + 1/2/3` | Save / recall slots |

Listening happens on your computer (Whisper runs locally). Ordinary conversation never triggers anything or leaves your machine; only an explicit trigger phrase that needs AI or an online sound makes a request.

## For developers

| Folder | What |
|---|---|
| `plugin/` | JUCE: the voice effect (VST3 / AU for Wave Link), `InstantVoiceEngine` (mic → effect → virtual cable), DSP chain, sound-effect player, OSC on `127.0.0.1:9001` |
| `companion/` | Python app: window + overlay (pywebview, `ui/`), tray, hotkeys, Whisper, always-on trigger listener, moods, sounds, AI intent, voice library |
| `packaging/` | PyInstaller spec, Mac `.pkg` builder, Windows Inno Setup script |
| `.github/workflows/build.yml` | Builds all installers on every push to `main` and publishes them to the `latest` release |

Run from source: `cd companion && pip install -r requirements.txt && python main.py`. User data: `~/.instantvoice/`.
