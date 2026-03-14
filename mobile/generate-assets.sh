#!/bin/bash
# Generate iOS and Android icon/splash assets from source files.
# Requires: sips (macOS built-in)
#
# Source files:
#   resources/icon.png    — 1024x1024 app icon
#   resources/splash.png  — 2732x2732 splash screen
#
# Usage: ./generate-assets.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$SCRIPT_DIR/resources"

if [ ! -f "$RESOURCES/icon.png" ]; then
  echo "Error: resources/icon.png not found (1024x1024 required)"
  exit 1
fi

if [ ! -f "$RESOURCES/splash.png" ]; then
  echo "Error: resources/splash.png not found (2732x2732 required)"
  exit 1
fi

# ── iOS Icons ────────────────────────────────────────────
IOS_DIR="$RESOURCES/ios"
mkdir -p "$IOS_DIR"

for size in 20 29 40 58 60 76 80 87 120 152 167 180 1024; do
  echo "  icon ${size}x${size}"
  sips -z "$size" "$size" "$RESOURCES/icon.png" --out "$IOS_DIR/icon-${size}.png" >/dev/null 2>&1
done

# ── Android Icons ────────────────────────────────────────
ANDROID_DIR="$RESOURCES/android"
mkdir -p "$ANDROID_DIR"

for pair in "mdpi:48" "hdpi:72" "xhdpi:96" "xxhdpi:144" "xxxhdpi:192"; do
  density="${pair%%:*}"
  size="${pair##*:}"
  echo "  icon ${density} (${size}x${size})"
  sips -z "$size" "$size" "$RESOURCES/icon.png" --out "$ANDROID_DIR/icon-${density}.png" >/dev/null 2>&1
done

# Adaptive icon foreground (108dp with 18dp padding = 72dp visible)
for pair in "mdpi:48" "hdpi:72" "xhdpi:96" "xxhdpi:144" "xxxhdpi:192"; do
  density="${pair%%:*}"
  size="${pair##*:}"
  fg_size=$((size * 108 / 48))
  echo "  foreground ${density} (${fg_size}x${fg_size})"
  sips -z "$fg_size" "$fg_size" "$RESOURCES/icon.png" --out "$ANDROID_DIR/ic_launcher_foreground-${density}.png" >/dev/null 2>&1
done

# ── iOS Splash screens ──────────────────────────────────
IOS_SPLASH="$RESOURCES/ios-splash"
mkdir -p "$IOS_SPLASH"

# Common iOS splash dimensions (portrait)
for dims in "1170x2532" "1284x2778" "1125x2436" "828x1792" "1242x2688" "750x1334" "640x1136" "1536x2048" "2048x2732"; do
  w="${dims%x*}"
  h="${dims#*x}"
  echo "  splash ${w}x${h}"
  sips -z "$h" "$w" "$RESOURCES/splash.png" --out "$IOS_SPLASH/splash-${w}x${h}.png" >/dev/null 2>&1
done

# ── Android Splash ──────────────────────────────────────
ANDROID_SPLASH="$RESOURCES/android-splash"
mkdir -p "$ANDROID_SPLASH"

for dims in "480x800" "720x1280" "1080x1920" "1440x2560"; do
  w="${dims%x*}"
  h="${dims#*x}"
  echo "  splash ${w}x${h}"
  sips -z "$h" "$w" "$RESOURCES/splash.png" --out "$ANDROID_SPLASH/splash-${w}x${h}.png" >/dev/null 2>&1
done

echo ""
echo "Assets generated in $RESOURCES/"
echo "Run 'npx cap sync' to copy into native projects."
