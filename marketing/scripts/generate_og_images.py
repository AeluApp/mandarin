#!/usr/bin/env python3
"""
Generate Open Graph images (1200x630) for all Mandarin landing pages.

Generates both SVG files and PNG files (via Pillow).
Output directory: marketing/landing/og/

Brand colors:
  Background: #F2EBE0 (warm linen)
  Text: #2A3650 (coastal indigo)
  Accent: #946070 (bougainvillea rose)

Usage:
  python marketing/scripts/generate_og_images.py
"""

import os
import sys

# --- Page definitions ---
# (filename_slug, page_title)
PAGES = [
    ("index", "Adaptive Chinese Learning\nfor Serious Learners"),
    ("pricing", "Simple Pricing.\nNo Tricks."),
    ("about", "Built by a Learner,\nfor Learners"),
    ("faq", "Frequently Asked\nQuestions"),
    ("blog-index", "Blog"),
    ("hsk3-study-plan", "How to Pass HSK 3:\nA Study Plan That\nActually Works"),
    ("anki-vs-chinese-apps", "Anki vs Dedicated\nChinese Apps"),
    ("learn-chinese-characters", "The Best Way to Learn\nChinese Characters"),
    ("chinese-listening-practice", "Chinese Listening Practice:\nHow to Improve"),
    ("hsk-levels-real-world", "What HSK Level Do You\nNeed for Real-World Goals?"),
    ("founder-story", "I Built a Chinese\nLearning App"),
    ("vs-duolingo", "Mandarin vs Duolingo"),
    ("vs-anki", "Mandarin vs Anki"),
    ("vs-hack-chinese", "Mandarin vs Hack Chinese"),
    ("vs-hellochinese", "Mandarin vs HelloChinese"),
    ("partner-kit", "Partner Content Kit"),
    ("affiliates", "Partner Program"),
]

# --- Brand constants ---
BG_COLOR = "#F2EBE0"
TEXT_COLOR = "#2A3650"
ACCENT_COLOR = "#946070"
FAINT_COLOR = "#8B8680"

WIDTH = 1200
HEIGHT = 630

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "marketing", "landing", "og")


def generate_svg(slug, title):
    """Generate an SVG OG image for a given page."""
    lines = title.split("\n")
    num_lines = len(lines)

    # Adjust font size based on line count
    if num_lines <= 1:
        font_size = 56
    elif num_lines <= 2:
        font_size = 48
    else:
        font_size = 40

    line_height = font_size * 1.3

    # Calculate vertical starting position to center the title block
    title_block_height = num_lines * line_height
    # Wordmark at y=80, URL at y=590, so content zone is roughly 120-560
    content_center_y = 320
    title_start_y = content_center_y - (title_block_height / 2) + font_size * 0.35

    title_lines_svg = ""
    for i, line in enumerate(lines):
        y = title_start_y + (i * line_height)
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        title_lines_svg += (
            f'  <text x="600" y="{y:.0f}" '
            f'font-family="Cormorant Garamond, Georgia, serif" '
            f'font-size="{font_size}" font-weight="600" '
            f'fill="{TEXT_COLOR}" text-anchor="middle">'
            f'{escaped}</text>\n'
        )

    # Accent bar below the title block
    bar_y = title_start_y + (num_lines * line_height) + 16

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <!-- Background -->
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BG_COLOR}"/>

  <!-- Wordmark -->
  <text x="600" y="80" font-family="Noto Serif SC, Songti SC, serif" font-size="28" font-weight="700" fill="{ACCENT_COLOR}" text-anchor="middle" opacity="0.7">&#28459;</text>
  <text x="640" y="80" font-family="Cormorant Garamond, Georgia, serif" font-size="28" font-weight="600" fill="{TEXT_COLOR}" text-anchor="middle">Mandarin</text>

  <!-- Page title -->
{title_lines_svg}
  <!-- Accent bar -->
  <rect x="552" y="{bar_y:.0f}" width="96" height="3" fill="{ACCENT_COLOR}"/>

  <!-- URL -->
  <text x="600" y="590" font-family="Source Serif 4, Georgia, serif" font-size="18" fill="{FAINT_COLOR}" text-anchor="middle">mandarinapp.com</text>
</svg>'''

    return svg


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_png(slug, title, output_path):
    """Generate a PNG OG image using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False

    img = Image.new("RGB", (WIDTH, HEIGHT), hex_to_rgb(BG_COLOR))
    draw = ImageDraw.Draw(img)

    bg_rgb = hex_to_rgb(BG_COLOR)
    text_rgb = hex_to_rgb(TEXT_COLOR)
    accent_rgb = hex_to_rgb(ACCENT_COLOR)
    faint_rgb = hex_to_rgb(FAINT_COLOR)

    # Try to load fonts, fall back to default
    def load_font(names, size):
        """Try loading fonts by name, falling back to default."""
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except (OSError, IOError):
                pass
        # Try common macOS font paths
        mac_fonts = {
            "Georgia": "/System/Library/Fonts/Supplemental/Georgia.ttf",
            "Georgia Bold": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        }
        for name in names:
            path = mac_fonts.get(name)
            if path and os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except (OSError, IOError):
                    pass
        return ImageFont.load_default()

    heading_font_names = [
        "Cormorant Garamond",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "Georgia",
    ]
    body_font_names = [
        "Source Serif 4",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "Georgia",
    ]

    lines = title.split("\n")
    num_lines = len(lines)

    if num_lines <= 1:
        font_size = 56
    elif num_lines <= 2:
        font_size = 48
    else:
        font_size = 40

    heading_font = load_font(heading_font_names, font_size)
    wordmark_font = load_font(heading_font_names, 28)
    url_font = load_font(body_font_names, 18)

    # Draw wordmark
    wm_text = "Mandarin"
    wm_bbox = draw.textbbox((0, 0), wm_text, font=wordmark_font)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text(((WIDTH - wm_w) / 2, 48), wm_text, fill=text_rgb, font=wordmark_font)

    # Draw title lines centered
    line_height = font_size * 1.4
    title_block_height = num_lines * line_height
    content_center_y = HEIGHT / 2 - 20
    start_y = content_center_y - (title_block_height / 2)

    for i, line in enumerate(lines):
        y = start_y + (i * line_height)
        bbox = draw.textbbox((0, 0), line, font=heading_font)
        tw = bbox[2] - bbox[0]
        draw.text(((WIDTH - tw) / 2, y), line, fill=text_rgb, font=heading_font)

    # Draw accent bar
    bar_y = start_y + title_block_height + 12
    bar_w = 96
    draw.rectangle(
        [(WIDTH / 2 - bar_w / 2, bar_y), (WIDTH / 2 + bar_w / 2, bar_y + 3)],
        fill=accent_rgb,
    )

    # Draw URL
    url_text = "mandarinapp.com"
    url_bbox = draw.textbbox((0, 0), url_text, font=url_font)
    url_w = url_bbox[2] - url_bbox[0]
    draw.text(((WIDTH - url_w) / 2, 580), url_text, fill=faint_rgb, font=url_font)

    img.save(output_path, "PNG", quality=95)
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pillow_available = False
    try:
        import PIL  # noqa: F401
        pillow_available = True
    except ImportError:
        pass

    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Pillow available: {pillow_available}")
    print(f"Generating OG images for {len(PAGES)} pages...\n")

    svg_count = 0
    png_count = 0

    for slug, title in PAGES:
        filename_base = f"og-{slug}"

        # Always generate SVG
        svg_content = generate_svg(slug, title)
        svg_path = os.path.join(OUTPUT_DIR, f"{filename_base}.svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        svg_count += 1
        print(f"  SVG: {filename_base}.svg")

        # Generate PNG if Pillow is available
        if pillow_available:
            png_path = os.path.join(OUTPUT_DIR, f"{filename_base}.png")
            display_title = title.replace("\n", " ")
            if generate_png(slug, title, png_path):
                png_count += 1
                print(f"  PNG: {filename_base}.png")
            else:
                print(f"  PNG: FAILED for {slug}")

    print(f"\nDone. Generated {svg_count} SVG files, {png_count} PNG files.")

    if not pillow_available:
        print("\n--- Pillow not installed ---")
        print("To generate PNG files, install Pillow:")
        print("  pip install Pillow")
        print("\nAlternatively, open the SVG files in a browser and take")
        print("screenshots at 1200x630 resolution.")

    print(f"\nFiles are in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
