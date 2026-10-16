#!/usr/bin/env bash
# Builds the macOS installer: the app goes to /Applications, the Audio Unit to /Library/Audio/Plug-Ins/Components.
# Usage (from repo root): packaging/macos/build_pkg.sh <version> <arch-label>
set -euo pipefail
VERSION="${1:-0.1.0}"
LABEL="${2:-mac}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT_DIR/companion/dist/Instant Voicemod.app"
AU="$ROOT_DIR/plugin/build/VoiceCast_artefacts/Release/AU/Instant Voicemod.component"
WORK="$ROOT_DIR/packaging/macos/work"
OUT="$ROOT_DIR/packaging/macos/Output"

rm -rf "$WORK" "$OUT"
mkdir -p "$WORK/root/Applications" "$WORK/root/Library/Audio/Plug-Ins/Components" "$OUT"

# Ad-hoc signatures so macOS accepts the bundles (no Apple Developer ID needed). Inner engine first.
ENGINE_IN_APP=$(find "$APP/Contents" -maxdepth 4 -name "InstantVoiceEngine.app" | head -n 1 || true)
if [ -n "$ENGINE_IN_APP" ]; then codesign --force --deep -s - "$ENGINE_IN_APP"; fi
codesign --force --deep -s - "$APP"
codesign --force --deep -s - "$AU"

cp -R "$APP" "$WORK/root/Applications/"
cp -R "$AU" "$WORK/root/Library/Audio/Plug-Ins/Components/"

# Install bundles exactly where we say, even if another copy exists elsewhere.
pkgbuild --analyze --root "$WORK/root" "$WORK/components.plist"
i=0
while /usr/libexec/PlistBuddy -c "Print :$i" "$WORK/components.plist" >/dev/null 2>&1; do
  /usr/libexec/PlistBuddy -c "Set :$i:BundleIsRelocatable false" "$WORK/components.plist"
  i=$((i + 1))
done

pkgbuild \
  --root "$WORK/root" \
  --component-plist "$WORK/components.plist" \
  --scripts "$ROOT_DIR/packaging/macos/scripts" \
  --identifier com.instantvoice.pkg \
  --version "$VERSION" \
  --install-location / \
  "$OUT/Instant-Voicemod-$LABEL.pkg"

echo "Built $OUT/Instant-Voicemod-$LABEL.pkg"
