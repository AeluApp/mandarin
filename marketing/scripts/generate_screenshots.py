#!/usr/bin/env python3
"""
Screenshot generation helper for Mandarin app store and marketing assets.

Opens the local Flask app at specific URLs for manual screenshot capture.
Generates a checklist markdown file with dimensions and captions.

Usage:
  1. Start the app:  ./run app
  2. Run this script: python marketing/scripts/generate_screenshots.py
  3. For each view, the script opens the browser and prints instructions.
  4. Press Enter to advance to the next view.

No external dependencies beyond the standard library.
"""

import os
import sys
import time
import webbrowser
import textwrap

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

BASE_URL = "http://localhost:5000"

# Each view: (url_path, name, caption, description)
VIEWS = [
    (
        "/",
        "Dashboard",
        "Where you stand, honestly.",
        "Capture the full dashboard: mastery bars, stats row, session "
        "history, and streak/momentum indicators. Show a state with "
        "some progress (not empty, not 100%).",
    ),
    (
        "/",
        "Active Drill",
        "27 ways to practice what you missed.",
        "Start a drill session first, then capture mid-drill. Ideally "
        "show a tone pair drill or cloze deletion with the large hanzi "
        "character visible. The drill type badge and progress bar should "
        "be in frame.",
    ),
    (
        "/",
        "Graded Reader",
        "Read Chinese. Look up what you don't know.",
        "Navigate to the graded reader, open a passage, and tap a word "
        "to show the inline gloss popup. Capture with the popup visible "
        "and at least 3-4 lines of Chinese text showing.",
    ),
    (
        "/",
        "Session Complete",
        "Real data after every session.",
        "Complete a drill session (or navigate to a completed session "
        "view). Capture the completion screen showing score, accuracy "
        "breakdown, and the next-session narrative text.",
    ),
    (
        "/",
        "Diagnostics / Progress",
        "Per-skill HSK readiness. No blended averages.",
        "Open the diagnostics view. Capture the mastery bars with the "
        "detailed breakdown showing vocabulary, listening, reading, and "
        "tone accuracy tracked independently against HSK levels.",
    ),
]

IPHONE_DIMS = "1290 x 2796 px (6.7-inch) or 1242 x 2208 px (5.5-inch)"
IPAD_DIMS = "2048 x 2732 px"
DESKTOP_DIMS = "2560 x 1440 px"
MAC_STORE_DIMS = "1280 x 800 px"

BRAND_COLORS = {
    "background": "#F2EBE0",
    "text": "#2A3650",
    "accent": "#946070",
    "secondary": "#6A7A5A",
    "faint": "#8890A0",
    "divider": "#D8D0C4",
}


def generate_checklist():
    """Generate the screenshots checklist markdown file."""
    checklist_path = os.path.join(PROJECT_ROOT, "marketing", "screenshots-checklist.md")

    content = textwrap.dedent("""\
        # Screenshots Checklist

        Capture these screenshots for app store listings and marketing materials.
        Start the app with `./run app` before taking screenshots.

        ---

        ## Recommended Dimensions

        | Platform | Dimensions | Notes |
        |----------|-----------|-------|
        | iPhone 6.7" | 1290 x 2796 px | Required for App Store |
        | iPhone 5.5" | 1242 x 2208 px | Required for older device support |
        | iPad | 2048 x 2732 px | Required for iPad App Store |
        | Mac App Store | 1280 x 800 px | Required for Mac listing |
        | Desktop marketing | 2560 x 1440 px | For website and social media |
        | OG / social cards | 1200 x 630 px | For link previews |

        ---

        ## Screenshots to Capture

    """)

    for i, (_, name, caption, description) in enumerate(VIEWS, 1):
        content += f"### {i}. {name}\n\n"
        content += f"**Caption:** \"{caption}\"\n\n"
        content += f"**What to capture:** {description}\n\n"
        content += "**Checklist:**\n"
        content += f"- [ ] iPhone (1290 x 2796)\n"
        content += f"- [ ] Desktop (2560 x 1440)\n"
        content += f"- [ ] Framed version with caption overlay\n\n"

    content += textwrap.dedent("""\
        ---

        ## Color Overlay / Framing Instructions

        When creating framed screenshots for the app store:

        1. **Caption area:** Extend the image canvas upward by 25% of total height.
           Fill the extension with #F2EBE0 (warm linen).

        2. **Caption text:** Set in Cormorant Garamond (or Georgia fallback):
           - iPhone: 36pt, color #2A3650
           - iPad: 48pt, color #2A3650
           - Mac: 28pt, color #2A3650

        3. **Device frame:** Use a warm-toned mockup frame (cream/linen colored).
           If unavailable, add a 2px border in #D8D0C4 around the screenshot.

        4. **Positioning:** Device frame in the lower 75%, caption in the upper 25%.

        5. **Do not** add drop shadows heavier than rgba(42, 54, 80, 0.10).

        6. **Do not** use dark mode screenshots. Light mode is the canonical presentation.

        ---

        ## Brand Color Reference

        | Color | Hex | Usage |
        |-------|-----|-------|
        | Background | #F2EBE0 | Caption area, framing |
        | Text | #2A3650 | Caption text |
        | Accent | #946070 | Highlights, emphasis |
        | Secondary | #6A7A5A | Secondary elements |
        | Faint | #8890A0 | Tertiary text |
        | Divider | #D8D0C4 | Borders, device frames |
    """)

    with open(checklist_path, "w", encoding="utf-8") as f:
        f.write(content)

    return checklist_path


def main():
    print("=" * 60)
    print("  Mandarin Screenshot Capture Helper")
    print("=" * 60)
    print()
    print(f"Base URL: {BASE_URL}")
    print(f"Views to capture: {len(VIEWS)}")
    print()
    print("Make sure the Flask app is running:")
    print("  ./run app")
    print()
    print("Recommended browser window sizes:")
    print(f"  iPhone:  {IPHONE_DIMS}")
    print(f"  Desktop: {DESKTOP_DIMS}")
    print()

    # Generate checklist first
    checklist_path = generate_checklist()
    print(f"Checklist generated: {checklist_path}")
    print()

    # Ask before opening browser
    try:
        input("Press Enter to start opening views in the browser (Ctrl+C to cancel)...")
    except KeyboardInterrupt:
        print("\nCancelled. Checklist file was still generated.")
        sys.exit(0)

    print()

    for i, (url_path, name, caption, description) in enumerate(VIEWS, 1):
        full_url = BASE_URL + url_path

        print("-" * 60)
        print(f"  [{i}/{len(VIEWS)}] {name}")
        print(f"  Caption: \"{caption}\"")
        print(f"  URL: {full_url}")
        print()
        print(f"  Instructions:")
        print(f"  {description}")
        print()
        print("  Recommended capture dimensions:")
        print(f"    iPhone:  {IPHONE_DIMS}")
        print(f"    Desktop: {DESKTOP_DIMS}")
        print("-" * 60)

        webbrowser.open(full_url)
        time.sleep(1)

        if i < len(VIEWS):
            try:
                input("\n  Press Enter for the next view...")
            except KeyboardInterrupt:
                print("\nStopped early. Remaining views skipped.")
                break
        else:
            print("\n  All views opened.")

    print()
    print("=" * 60)
    print("  Done. Review the checklist at:")
    print(f"  {checklist_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
