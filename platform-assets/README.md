# Platform Assets

This directory holds platform-specific assets required for Aelu's native
builds on iOS, Android, and desktop (macOS, Windows, Linux).

All generated images should follow the Civic Sanctuary aesthetic:
warm Mediterranean tones, linen texture, muted bougainvillea rose and
cypress olive accents. See `BRAND.md` and `CLAUDE.md` for full guidance.

## What needs to be created

### App Icons

Source artwork should be a single high-resolution PNG (1024x1024, no
transparency for iOS) that can be scaled down to every required size.

### Splash Screens

A centered wordmark or logo on the `--color-base` background (`#F2EBE0`
light, `#1C2028` dark). No gradients, no decorative elements beyond the
logo itself.

### Desktop Icons

Tauri expects several icon files inside `src-tauri/icons/`. Generate them
from the same 1024x1024 source.

## Required sizes

See `asset-specs.md` in this directory for the full list of sizes and
formats per platform.
