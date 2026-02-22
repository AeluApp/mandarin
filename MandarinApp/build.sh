#!/bin/bash
# Build MandarinApp — a minimal macOS WKWebView wrapper
# Usage: ./build.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Mandarin"
APP_BUNDLE="$SCRIPT_DIR/$APP_NAME.app"

echo "Building $APP_NAME.app..."

# ── Fix SwiftBridging modulemap conflict (if present) ──────────────
# CLT bug: both module.modulemap and bridging.modulemap define SwiftBridging
MODULEMAP="/Library/Developer/CommandLineTools/usr/include/swift/module.modulemap"
if [ -f "$MODULEMAP" ] && [ -f "${MODULEMAP%.modulemap}/../bridging.modulemap" ]; then
    if grep -q "SwiftBridging" "$MODULEMAP" 2>/dev/null; then
        echo "NOTE: Detected SwiftBridging modulemap conflict."
        echo "  Fix: sudo mv '$MODULEMAP' '${MODULEMAP}.bak'"
        echo "  Attempting build anyway..."
    fi
fi

# ── Clean previous build ───────────────────────────────────────────
rm -rf "$APP_BUNDLE"

# ── Create .app bundle structure ───────────────────────────────────
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# ── Copy Info.plist ────────────────────────────────────────────────
cp "$SCRIPT_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"

# ── Generate app icon ──────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    echo "Generating app icon..."
    python3 "$SCRIPT_DIR/gen_icon.py"
fi
if [ -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
fi

# ── Compile Swift ──────────────────────────────────────────────────
echo "Compiling Swift..."

# Try xcrun first (picks correct SDK), fall back to raw swiftc
ARCH="$(uname -m)"
compile_swift() {
    local COMPILER="$1"
    $COMPILER \
        -O \
        -target "${ARCH}-apple-macosx12.0" \
        -framework Cocoa \
        -framework WebKit \
        -o "$APP_BUNDLE/Contents/MacOS/$APP_NAME" \
        "$SCRIPT_DIR/MandarinApp.swift"
}

if compile_swift "xcrun --sdk macosx swiftc" 2>/dev/null; then
    echo "  Compiled with xcrun."
elif compile_swift "swiftc" 2>/dev/null; then
    echo "  Compiled with swiftc."
else
    echo ""
    echo "ERROR: Swift compilation failed."
    echo ""
    echo "This is likely caused by the SwiftBridging modulemap bug."
    echo "Fix it by running:"
    echo ""
    echo "  sudo mv /Library/Developer/CommandLineTools/usr/include/swift/module.modulemap \\"
    echo "          /Library/Developer/CommandLineTools/usr/include/swift/module.modulemap.bak"
    echo ""
    echo "Then re-run ./build.sh"
    exit 1
fi

# ── Write PkgInfo ──────────────────────────────────────────────────
echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

echo ""
echo "Built: $APP_BUNDLE"
echo ""
echo "To install to /Applications:"
echo "  cp -R \"$APP_BUNDLE\" /Applications/"
echo ""
echo "To run:"
echo "  open \"$APP_BUNDLE\""
