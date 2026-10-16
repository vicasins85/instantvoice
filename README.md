# Instant Voicemod

Change your voice by saying what you want. Hold a shortcut, say "angry ogre", let go: your mic sounds like an angry ogre, live, inside Wave Link. Or pick a voice from the window with one click.

## Install (users)

1. Open the [latest release](../../releases/tag/latest) and download the file for your computer.

| Computer | File |
|---|---|
| Windows 10/11 | `Instant-Voicemod-Setup.exe` |
| Mac with Apple chip (M1 to M4) | `Instant-Voicemod-mac-AppleSilicon.pkg` |
| Mac with Intel chip | `Instant-Voicemod-mac-Intel.pkg` |

2. Double-click it and follow the steps.

| First time warning | What to do |
|---|---|
| Windows: "Windows protected your PC" | Click **More info** → **Run anyway** |
| Mac: "can't be opened because it is from an unidentified developer" | **Right-click** the `.pkg` → **Open** → **Open** |

These warnings disappear once the installers are signed with a company certificate.

## First run

| Step | Do this |
|---|---|
| 1 | The app opens by itself after installing |
| 2 | Open **Wave Link** (quit and reopen it if it was open). On your microphone, add the effect **Instant Voicemod** |
| 3 | Mac only: when asked, allow **Instant Voicemod** in **Privacy & Security** under **Microphone**, **Accessibility** and **Input Monitoring** |
| 4 | Optional: in the app, **Settings** → paste your AI key to create any voice from a description. The 12 built-in voices work without it |

From then on it starts with your computer and lives in the menu bar (Mac) or next to the clock (Windows). Click the icon to open the window.

## Use

| Do this | Result |
|---|---|
| Click a voice card | Voice on |
| Type "vampire whispering" → **Create voice** | New voice, saved in **My voices** |
| Hold `Ctrl + Alt + V` (Mac: `Ctrl + Option + V`), say a voice, let go | Same as typing it. Nobody hears the command |
| Say "deeper", "more echo", "más grave" | Tweaks the current voice |
| `Ctrl + Alt + X` or say "normal voice" | Your own voice back |
| Sliders: Size, Pitch, Grit, Space, Robot | Fine-tune the active voice |
| `Ctrl + Alt + Shift + 1/2/3` / `Ctrl + Alt + 1/2/3` | Save / recall slots |

Commands are understood in Spanish by default. Change it in **Settings**.

## Troubleshooting

| Problem | Fix |
|---|---|
| Yellow banner "The voice effect isn't connected yet" | Add **Instant Voicemod** as an effect on your mic in Wave Link. Restart Wave Link if it isn't listed |
| Effect missing from Wave Link | Windows: `C:\Program Files\Common Files\VST3\Instant Voicemod.vst3`. Mac: `/Library/Audio/Plug-Ins/Components/Instant Voicemod.component`. Reinstall if missing |
| Shortcut does nothing on Mac | Allow the app in Accessibility and Input Monitoring, then quit and reopen it |
| "Port busy" inside the effect | The effect is loaded twice in Wave Link. Keep one |

## For developers

| Folder | What |
|---|---|
| `plugin/` | JUCE effect (VST3 for Windows, AU for Mac). DSP chain + OSC listener on UDP 9001 |
| `companion/` | Python app: window (pywebview, `ui/index.html`), tray, hotkeys, Whisper, AI intent, voice library |
| `packaging/` | PyInstaller spec, Mac `.pkg` builder, Windows Inno Setup script, icon and model fetchers |
| `.github/workflows/build.yml` | Builds all installers on every push to `main` and publishes them to the `latest` release |
| `dev/` | Local build scripts for working on the effect |
| `scripts/send_preset.py` | Send presets to the effect without the app |

Run the app from source: `cd companion && pip install -r requirements.txt && python main.py`

User data lives in `~/.instantvoice/` (settings, created voices, slots, cache).
