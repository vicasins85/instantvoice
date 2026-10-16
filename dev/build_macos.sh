#!/usr/bin/env bash
# Builds VoiceCast.component (Audio Unit, what Wave Link on Mac loads) + VoiceCast.app (standalone)
# as universal binaries (Apple Silicon + Intel), and installs the AU.
# Needs: Xcode Command Line Tools (xcode-select --install) and CMake (brew install cmake).
set -euo pipefail
cd "$(dirname "$0")/../plugin"

cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --target VoiceCast_AU VoiceCast_Standalone -j"$(sysctl -n hw.ncpu)"

ART="build/VoiceCast_artefacts/Release"
codesign --force --deep -s - "$ART/AU/Instant Voicemod.component"
codesign --force --deep -s - "$ART/Standalone/Instant Voicemod.app"

echo "Installing AU to /Library/Audio/Plug-Ins/Components (asks for your password)..."
sudo rm -rf "/Library/Audio/Plug-Ins/Components/Instant Voicemod.component"
sudo cp -R "$ART/AU/Instant Voicemod.component" /Library/Audio/Plug-Ins/Components/
killall -9 AudioComponentRegistrar 2>/dev/null || true

echo "Validating Audio Unit..."
auval -v aufx Vcs1 Vcst | tail -n 3 || true

cat <<MSG

Done.
 - Quit and reopen Wave Link, then add "VoiceCast" as an effect on your mic.
 - Standalone app (no Wave Link needed): plugin/$ART/Standalone/Instant Voicemod.app
MSG
