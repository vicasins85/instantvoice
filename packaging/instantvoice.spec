# PyInstaller spec for the Instant Voicemod desktop app.
# Run from the companion/ folder:  pyinstaller --noconfirm ../packaging/instantvoice.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all

APP = "Instant Voicemod"
SRC = os.path.abspath(os.path.join(SPECPATH, "..", "companion"))
ICON_DIR = os.path.join(SRC, "build_icon")

datas = [
    (os.path.join(SRC, "ui"), "ui"),
    (os.path.join(SRC, "presets.json"), "."),
]
if os.path.isdir(os.path.join(SRC, "models")):
    datas.append((os.path.join(SRC, "models"), "models"))
if os.path.isdir(os.path.join(SRC, "engine")):  # audio engine for the virtual-cable route, copied in by CI
    datas.append((os.path.join(SRC, "engine"), "engine"))

binaries, hiddenimports = [], []
for pkg in ["faster_whisper", "ctranslate2", "tokenizers", "av", "onnxruntime",
            "webview", "pystray", "pynput", "sounddevice", "_sounddevice_data", "anthropic"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # optional packages
        print(f"[spec] skipping {pkg}: {exc}")

if sys.platform == "darwin":
    hiddenimports += ["pynput.keyboard._darwin", "pynput.mouse._darwin", "pystray._darwin"]
elif sys.platform == "win32":
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32", "pystray._win32"]

a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = None
if sys.platform == "win32" and os.path.exists(os.path.join(ICON_DIR, "icon.ico")):
    icon = os.path.join(ICON_DIR, "icon.ico")
elif sys.platform == "darwin":
    for name in ("icon.icns", "icon.png"):
        if os.path.exists(os.path.join(ICON_DIR, name)):
            icon = os.path.join(ICON_DIR, name)
            break

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP,
    console=False,
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon=icon,
        bundle_identifier="com.instantvoice.app",
        info_plist={
            "CFBundleName": APP,
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": os.environ.get("APP_VERSION", "0.1.0"),
            "CFBundleVersion": os.environ.get("APP_VERSION", "0.1.0"),
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "Instant Voicemod listens to your voice commands while you hold the shortcut.",
            "NSAppleEventsUsageDescription": "Instant Voicemod uses this to start at login.",
        },
    )
