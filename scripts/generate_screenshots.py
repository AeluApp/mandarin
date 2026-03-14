#!/usr/bin/env python3
"""
Generate placeholder screenshot frames for App Store and Play Store submission.

Creates properly sized images using Pillow (if available) or SVG files as
fallback. Each screenshot depicts a different app screen with Civic Sanctuary
color scheme and screen-appropriate content placeholders.

Usage:
    python scripts/generate_screenshots.py [--format svg] [--output-dir DIR]

Screens generated:
    1. Dashboard        — mastery bars, stats row, session history
    2. Drill Session    — active drill with large hanzi, progress bar
    3. Progress Report  — per-skill HSK readiness breakdown
    4. Tone Grading     — tone contour visualization, accuracy feedback
    5. Settings         — preferences, subscription tier, study schedule

Sizes:
    iOS:     1290x2796 (6.7"), 1242x2688 (6.5"), 1170x2532 (6.1")
    Android: 1080x1920 (phone), 1024x500 (feature graphic)
"""

import argparse
import os
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Civic Sanctuary palette ─────────────────────────────────────────
COLORS = {
    "base": "#f5f0eb",       # warm stone
    "surface": "#ffffff",
    "text": "#2a3650",
    "text_secondary": "#6b7280",
    "accent": "#1a7a6d",     # teal
    "secondary": "#c4654a",  # terracotta
    "correct": "#2d8659",
    "incorrect": "#c4654a",
    "divider": "#d8d0c4",
    "faint": "#8890a0",
}

# ── Screen definitions ──────────────────────────────────────────────
SCREENS = [
    {
        "name": "Dashboard",
        "filename": "01_dashboard",
        "caption": "Where you stand, honestly.",
        "elements": [
            ("header", "Aelu", 0.06),
            ("stat_row", ["Today: 42 drills", "Accuracy: 87%", "Streak: 5d"], 0.14),
            ("bar", "Vocabulary", 0.72, 0.24),
            ("bar", "Listening", 0.58, 0.32),
            ("bar", "Reading", 0.65, 0.40),
            ("bar", "Tones", 0.81, 0.48),
            ("label", "HSK 3 projected: 14 weeks", 0.58),
            ("button", "Start Session", 0.68),
            ("session_list", ["Session 12 — 89% accuracy", "Session 11 — 84% accuracy", "Session 10 — 91% accuracy"], 0.78),
        ],
    },
    {
        "name": "Drill Session",
        "filename": "02_drill_session",
        "caption": "27 ways to practice what you missed.",
        "elements": [
            ("progress_bar", 0.6, 0.04),
            ("badge", "Tone Pair Drill", 0.10),
            ("hanzi_large", "ma", 0.30),
            ("hanzi_display", "\u5988", 0.30),
            ("prompt", "Which tone pair is correct?", 0.52),
            ("option", "\u0101. m\u0101 (1st tone)", False, 0.62),
            ("option", "\u0101. m\u00e1 (2nd tone)", False, 0.70),
            ("option", "\u0101. m\u01ce (3rd tone)", True, 0.78),
            ("option", "\u0101. m\u00e0 (4th tone)", False, 0.86),
            ("counter", "8 / 15", 0.95),
        ],
    },
    {
        "name": "Progress Report",
        "filename": "03_progress_report",
        "caption": "Per-skill HSK readiness. No blended averages.",
        "elements": [
            ("header", "Progress", 0.06),
            ("subheader", "HSK Level Readiness", 0.13),
            ("hsk_bar", "HSK 1", 0.98, 0.20),
            ("hsk_bar", "HSK 2", 0.85, 0.28),
            ("hsk_bar", "HSK 3", 0.42, 0.36),
            ("divider_line", 0.45),
            ("subheader", "Skill Breakdown (HSK 3)", 0.50),
            ("skill_detail", "Vocabulary", "312 / 600", 0.52, 0.57),
            ("skill_detail", "Listening", "248 / 600", 0.41, 0.63),
            ("skill_detail", "Reading", "289 / 600", 0.48, 0.69),
            ("skill_detail", "Tones", "384 / 600", 0.64, 0.75),
            ("label", "Forecast: HSK 3 ready in ~14 weeks at current pace", 0.84),
            ("label", "Based on 299 items studied, 15 min/day average", 0.88),
        ],
    },
    {
        "name": "Tone Grading",
        "filename": "04_tone_grading",
        "caption": "Your tones, measured honestly.",
        "elements": [
            ("header", "Tone Practice", 0.06),
            ("hanzi_display", "\u8c22\u8c22", 0.18),
            ("pinyin", "xi\u00e8xie (4th + neutral)", 0.26),
            ("tone_contour", [0.8, 0.7, 0.5, 0.3, 0.25, 0.22], 0.42),
            ("grade_badge", "Tone 4: Good", True, 0.58),
            ("detail_row", ["F0 range: 180-95 Hz", "Duration: 320ms", "HNR: 12.4 dB"], 0.66),
            ("divider_line", 0.72),
            ("subheader", "Session Tone Accuracy", 0.76),
            ("tone_summary", "1st tone", 0.91, 0.81),
            ("tone_summary", "2nd tone", 0.78, 0.86),
            ("tone_summary", "3rd tone", 0.65, 0.91),
            ("tone_summary", "4th tone", 0.84, 0.96),
        ],
    },
    {
        "name": "Settings",
        "filename": "05_settings",
        "caption": "Your study, your way.",
        "elements": [
            ("header", "Settings", 0.06),
            ("setting_group", "Study", 0.14),
            ("setting_row", "Daily target", "15 minutes", 0.19),
            ("setting_row", "Session length", "12 drills", 0.24),
            ("setting_row", "Preferred time", "Evening", 0.29),
            ("setting_group", "Content", 0.37),
            ("setting_row", "HSK range", "1 \u2013 3", 0.42),
            ("setting_row", "Include tones", "On", 0.47),
            ("setting_row", "Include listening", "On", 0.52),
            ("setting_group", "Subscription", 0.60),
            ("setting_row", "Plan", "Pro ($14.99/mo)", 0.65),
            ("setting_row", "Renewal", "April 12, 2026", 0.70),
            ("setting_group", "Display", 0.78),
            ("setting_row", "Dark mode", "System", 0.83),
            ("setting_row", "Hanzi size", "Large", 0.88),
            ("version_label", "Aelu v2.1.0", 0.95),
        ],
    },
]

# ── Size definitions ────────────────────────────────────────────────
IOS_SIZES = [
    ("6.7in", 1290, 2796),
    ("6.5in", 1242, 2688),
    ("6.1in", 1170, 2532),
]

ANDROID_SIZES = [
    ("phone", 1080, 1920),
]

ANDROID_FEATURE_GRAPHIC = ("feature", 1024, 500)


# ── SVG generation ──────────────────────────────────────────────────

def _svg_rect(x, y, w, h, fill, rx=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" rx="{rx}"/>'


def _svg_text(x, y, text, size=16, fill=None, anchor="start", weight="normal", font="Source Sans 3, sans-serif"):
    fill = fill or COLORS["text"]
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-family="{font}" font-weight="{weight}" text-anchor="{anchor}">'
            f'{text}</text>')


def _svg_bar(x, y, w, h, progress, label, screen_w):
    """Render a labeled progress bar."""
    parts = []
    # Label
    parts.append(_svg_text(x, y - 6, label, size=14, fill=COLORS["text_secondary"]))
    # Track
    parts.append(_svg_rect(x, y, w, h, COLORS["divider"], rx=h // 2))
    # Fill
    fill_w = max(int(w * progress), h)
    parts.append(_svg_rect(x, y, fill_w, h, COLORS["accent"], rx=h // 2))
    # Percentage
    parts.append(_svg_text(x + w + 10, y + h - 2, f"{int(progress * 100)}%", size=13, fill=COLORS["faint"]))
    return "\n".join(parts)


def generate_screen_svg(screen, width, height):
    """Generate SVG content for a single screen at given dimensions."""
    margin_x = int(width * 0.08)
    content_w = width - 2 * margin_x
    scale = width / 1290  # normalize to 6.7" baseline

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<defs><style>',
        f'  @import url("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Source+Sans+3:wght@400;600&family=Noto+Serif+SC:wght@400;700");',
        f'</style></defs>',
        # Background
        _svg_rect(0, 0, width, height, COLORS["base"]),
        # Status bar area
        _svg_rect(0, 0, width, int(50 * scale), COLORS["base"]),
    ]

    for elem in screen["elements"]:
        kind = elem[0]
        if kind == "header":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(margin_x, y, text, size=int(36 * scale), weight="600",
                                   font="Cormorant Garamond, Georgia, serif"))

        elif kind == "subheader":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(margin_x, y, text, size=int(20 * scale), weight="600",
                                   fill=COLORS["text_secondary"]))

        elif kind == "stat_row":
            _, stats, y_pct = elem
            y = int(height * y_pct)
            col_w = content_w // len(stats)
            for i, stat in enumerate(stats):
                cx = margin_x + col_w * i + col_w // 2
                # Stat card
                parts.append(_svg_rect(margin_x + col_w * i + 4, y - int(20 * scale),
                                       col_w - 8, int(50 * scale), COLORS["surface"], rx=8))
                parts.append(_svg_text(cx, y + int(8 * scale), stat, size=int(14 * scale),
                                       fill=COLORS["text"], anchor="middle"))

        elif kind == "bar":
            _, label, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(16 * scale)
            parts.append(_svg_bar(margin_x, y, content_w - int(60 * scale), bar_h, progress, label, width))

        elif kind == "hsk_bar":
            _, label, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(20 * scale)
            parts.append(_svg_bar(margin_x + int(80 * scale), y, content_w - int(140 * scale),
                                  bar_h, progress, label, width))

        elif kind == "label":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(margin_x, y, text, size=int(14 * scale), fill=COLORS["faint"]))

        elif kind == "button":
            _, text, y_pct = elem
            y = int(height * y_pct)
            btn_h = int(52 * scale)
            parts.append(_svg_rect(margin_x, y, content_w, btn_h, COLORS["accent"], rx=12))
            parts.append(_svg_text(width // 2, y + btn_h // 2 + int(6 * scale), text,
                                   size=int(18 * scale), fill="#ffffff", anchor="middle", weight="600"))

        elif kind == "session_list":
            _, items, y_pct = elem
            y = int(height * y_pct)
            for i, item in enumerate(items):
                iy = y + i * int(40 * scale)
                parts.append(_svg_rect(margin_x, iy, content_w, int(34 * scale), COLORS["surface"], rx=6))
                parts.append(_svg_text(margin_x + 12, iy + int(22 * scale), item,
                                       size=int(13 * scale), fill=COLORS["text_secondary"]))

        elif kind == "progress_bar":
            _, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(6 * scale)
            parts.append(_svg_rect(margin_x, y, content_w, bar_h, COLORS["divider"], rx=3))
            parts.append(_svg_rect(margin_x, y, int(content_w * progress), bar_h, COLORS["accent"], rx=3))

        elif kind == "badge":
            _, text, y_pct = elem
            y = int(height * y_pct)
            badge_w = int(200 * scale)
            badge_h = int(30 * scale)
            parts.append(_svg_rect(width // 2 - badge_w // 2, y, badge_w, badge_h,
                                   COLORS["accent"] + "20", rx=badge_h // 2))
            parts.append(_svg_text(width // 2, y + badge_h // 2 + int(5 * scale), text,
                                   size=int(13 * scale), fill=COLORS["accent"], anchor="middle", weight="600"))

        elif kind == "hanzi_large" or kind == "hanzi_display":
            _, char, y_pct = elem
            y = int(height * y_pct)
            if kind == "hanzi_display":
                parts.append(_svg_text(width // 2, y + int(60 * scale), char,
                                       size=int(80 * scale), fill=COLORS["text"], anchor="middle",
                                       weight="700", font="Noto Serif SC, serif"))

        elif kind == "prompt":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(width // 2, y, text, size=int(18 * scale),
                                   fill=COLORS["text"], anchor="middle"))

        elif kind == "option":
            _, text, is_correct, y_pct = elem
            y = int(height * y_pct)
            opt_h = int(48 * scale)
            border_color = COLORS["correct"] if is_correct else COLORS["divider"]
            bg = COLORS["correct"] + "15" if is_correct else COLORS["surface"]
            parts.append(_svg_rect(margin_x, y, content_w, opt_h, bg, rx=10))
            parts.append(f'<rect x="{margin_x}" y="{y}" width="{content_w}" height="{opt_h}" '
                         f'fill="none" stroke="{border_color}" stroke-width="2" rx="10"/>')
            parts.append(_svg_text(margin_x + 20, y + opt_h // 2 + int(5 * scale), text,
                                   size=int(16 * scale), fill=COLORS["text"]))

        elif kind == "counter":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(width // 2, y, text, size=int(14 * scale),
                                   fill=COLORS["faint"], anchor="middle"))

        elif kind == "divider_line":
            _, y_pct = elem
            y = int(height * y_pct)
            parts.append(f'<line x1="{margin_x}" y1="{y}" x2="{width - margin_x}" y2="{y}" '
                         f'stroke="{COLORS["divider"]}" stroke-width="1"/>')

        elif kind == "skill_detail":
            _, label, count, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(12 * scale)
            # Label and count
            parts.append(_svg_text(margin_x, y - 4, label, size=int(14 * scale), fill=COLORS["text"]))
            parts.append(_svg_text(width - margin_x, y - 4, count,
                                   size=int(12 * scale), fill=COLORS["faint"], anchor="end"))
            # Bar
            bar_w = content_w
            parts.append(_svg_rect(margin_x, y + 4, bar_w, bar_h, COLORS["divider"], rx=bar_h // 2))
            parts.append(_svg_rect(margin_x, y + 4, int(bar_w * progress), bar_h,
                                   COLORS["accent"], rx=bar_h // 2))

        elif kind == "tone_contour":
            _, points, y_pct = elem
            y_start = int(height * (y_pct - 0.10))
            y_end = int(height * y_pct)
            contour_h = y_end - y_start
            # Background
            parts.append(_svg_rect(margin_x, y_start - 10, content_w, contour_h + 20,
                                   COLORS["surface"], rx=8))
            # Contour line
            n = len(points)
            svg_points = []
            for i, p in enumerate(points):
                px = margin_x + 20 + int((content_w - 40) * i / (n - 1))
                py = y_start + int(contour_h * (1 - p))
                svg_points.append(f"{px},{py}")
            parts.append(f'<polyline points="{" ".join(svg_points)}" fill="none" '
                         f'stroke="{COLORS["accent"]}" stroke-width="{int(3 * scale)}" '
                         f'stroke-linecap="round" stroke-linejoin="round"/>')
            # Reference line (dashed)
            ref_points = []
            ref_curve = [0.85, 0.75, 0.5, 0.28, 0.22, 0.20]
            for i, p in enumerate(ref_curve):
                px = margin_x + 20 + int((content_w - 40) * i / (n - 1))
                py = y_start + int(contour_h * (1 - p))
                ref_points.append(f"{px},{py}")
            parts.append(f'<polyline points="{" ".join(ref_points)}" fill="none" '
                         f'stroke="{COLORS["faint"]}" stroke-width="{int(2 * scale)}" '
                         f'stroke-dasharray="6,4" stroke-linecap="round"/>')
            # Legend
            parts.append(_svg_text(margin_x + 20, y_end + int(16 * scale), "-- native reference",
                                   size=int(11 * scale), fill=COLORS["faint"]))
            parts.append(f'<line x1="{margin_x + 20}" y1="{y_end + int(20 * scale)}" '
                         f'x2="{margin_x + 50}" y2="{y_end + int(20 * scale)}" '
                         f'stroke="{COLORS["accent"]}" stroke-width="2"/>')
            parts.append(_svg_text(margin_x + 56, y_end + int(24 * scale), "your recording",
                                   size=int(11 * scale), fill=COLORS["accent"]))

        elif kind == "grade_badge":
            _, text, is_good, y_pct = elem
            y = int(height * y_pct)
            badge_color = COLORS["correct"] if is_good else COLORS["secondary"]
            badge_w = int(240 * scale)
            badge_h = int(36 * scale)
            parts.append(_svg_rect(width // 2 - badge_w // 2, y, badge_w, badge_h,
                                   badge_color + "18", rx=badge_h // 2))
            parts.append(_svg_text(width // 2, y + badge_h // 2 + int(5 * scale), text,
                                   size=int(16 * scale), fill=badge_color, anchor="middle", weight="600"))

        elif kind == "detail_row":
            _, items, y_pct = elem
            y = int(height * y_pct)
            col_w = content_w // len(items)
            for i, item in enumerate(items):
                parts.append(_svg_text(margin_x + col_w * i, y, item,
                                       size=int(11 * scale), fill=COLORS["faint"]))

        elif kind == "pinyin":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(width // 2, y, text, size=int(18 * scale),
                                   fill=COLORS["text_secondary"], anchor="middle"))

        elif kind == "tone_summary":
            _, label, accuracy, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(10 * scale)
            parts.append(_svg_text(margin_x, y, label, size=int(13 * scale), fill=COLORS["text"]))
            bar_x = margin_x + int(100 * scale)
            bar_w = content_w - int(160 * scale)
            parts.append(_svg_rect(bar_x, y - bar_h + 2, bar_w, bar_h, COLORS["divider"], rx=bar_h // 2))
            parts.append(_svg_rect(bar_x, y - bar_h + 2, int(bar_w * accuracy), bar_h,
                                   COLORS["accent"], rx=bar_h // 2))
            parts.append(_svg_text(bar_x + bar_w + 10, y, f"{int(accuracy * 100)}%",
                                   size=int(12 * scale), fill=COLORS["faint"]))

        elif kind == "setting_group":
            _, label, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(margin_x, y, label, size=int(14 * scale),
                                   fill=COLORS["accent"], weight="600"))

        elif kind == "setting_row":
            _, label, value, y_pct = elem
            y = int(height * y_pct)
            row_h = int(36 * scale)
            parts.append(_svg_rect(margin_x, y, content_w, row_h, COLORS["surface"], rx=6))
            parts.append(_svg_text(margin_x + 14, y + row_h // 2 + int(5 * scale), label,
                                   size=int(15 * scale), fill=COLORS["text"]))
            parts.append(_svg_text(width - margin_x - 14, y + row_h // 2 + int(5 * scale), value,
                                   size=int(14 * scale), fill=COLORS["faint"], anchor="end"))

        elif kind == "version_label":
            _, text, y_pct = elem
            y = int(height * y_pct)
            parts.append(_svg_text(width // 2, y, text, size=int(12 * scale),
                                   fill=COLORS["faint"], anchor="middle"))

    # Caption overlay at top (for framed version)
    # We include it as a subtle watermark-style label
    caption_y = height - int(40 * scale)
    parts.append(_svg_text(width // 2, caption_y, screen["caption"],
                           size=int(14 * scale), fill=COLORS["faint"], anchor="middle",
                           font="Cormorant Garamond, Georgia, serif"))

    parts.append("</svg>")
    return "\n".join(parts)


def generate_feature_graphic_svg(width, height):
    """Generate the Android feature graphic (1024x500)."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<defs><style>',
        f'  @import url("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Source+Sans+3:wght@400;600&family=Noto+Serif+SC:wght@700");',
        f'</style></defs>',
        _svg_rect(0, 0, width, height, COLORS["base"]),
        # Large hanzi character on the left
        _svg_text(int(width * 0.22), int(height * 0.62), "\u6f2b",
                  size=180, fill=COLORS["secondary"] + "40", anchor="middle",
                  font="Noto Serif SC, serif", weight="700"),
        # App name
        _svg_text(int(width * 0.58), int(height * 0.45), "Aelu",
                  size=72, fill=COLORS["text"], anchor="middle", weight="600",
                  font="Cormorant Garamond, Georgia, serif"),
        # Divider line
        f'<line x1="{int(width * 0.42)}" y1="{int(height * 0.54)}" '
        f'x2="{int(width * 0.74)}" y2="{int(height * 0.54)}" '
        f'stroke="{COLORS["divider"]}" stroke-width="1"/>',
        # Subtitle
        _svg_text(int(width * 0.58), int(height * 0.66), "Patient Chinese Study",
                  size=22, fill=COLORS["text_secondary"], anchor="middle",
                  font="Source Sans 3, sans-serif"),
        "</svg>",
    ]
    return "\n".join(parts)


# ── Pillow generation ───────────────────────────────────────────────

def _try_pillow():
    """Check if Pillow is available and return the module or None."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        return True
    except ImportError:
        return False


def _pillow_bar(draw, x, y, w, h, progress, label, colors, scale, font_small):
    """Draw a labeled progress bar using Pillow."""
    from PIL import ImageDraw
    # Label
    draw.text((x, y - int(20 * scale)), label, fill=colors["text_secondary"], font=font_small)
    # Track
    draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=h // 2, fill=colors["divider"])
    # Fill
    fill_w = max(int(w * progress), h)
    draw.rounded_rectangle([(x, y), (x + fill_w, y + h)], radius=h // 2, fill=colors["accent"])
    # Percentage text
    draw.text((x + w + 10, y - 2), f"{int(progress * 100)}%", fill=colors["faint"], font=font_small)


def generate_screen_pillow(screen, width, height):
    """Generate a PNG image for a single screen using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), COLORS["base"])
    draw = ImageDraw.Draw(img)

    margin_x = int(width * 0.08)
    content_w = width - 2 * margin_x
    scale = width / 1290

    # Try to load fonts; fall back to default
    def _font(size, bold=False):
        try:
            # Try system fonts on macOS
            if bold:
                return ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", size)
            return ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", size)
        except (OSError, IOError):
            try:
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except (OSError, IOError):
                return ImageFont.load_default()

    font_large = _font(int(36 * scale), bold=True)
    font_medium = _font(int(18 * scale))
    font_small = _font(int(14 * scale))
    font_tiny = _font(int(12 * scale))
    font_hanzi = _font(int(80 * scale), bold=True)

    for elem in screen["elements"]:
        kind = elem[0]

        if kind == "header":
            _, text, y_pct = elem
            y = int(height * y_pct)
            draw.text((margin_x, y - int(30 * scale)), text, fill=COLORS["text"], font=font_large)

        elif kind == "subheader":
            _, text, y_pct = elem
            y = int(height * y_pct)
            draw.text((margin_x, y - int(16 * scale)), text, fill=COLORS["text_secondary"], font=font_medium)

        elif kind == "stat_row":
            _, stats, y_pct = elem
            y = int(height * y_pct)
            col_w = content_w // len(stats)
            for i, stat in enumerate(stats):
                cx = margin_x + col_w * i
                draw.rounded_rectangle(
                    [(cx + 4, y - int(20 * scale)), (cx + col_w - 4, y + int(30 * scale))],
                    radius=8, fill=COLORS["surface"]
                )
                draw.text((cx + col_w // 2 - len(stat) * int(3.5 * scale), y - int(4 * scale)),
                          stat, fill=COLORS["text"], font=font_small)

        elif kind == "bar":
            _, label, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(16 * scale)
            _pillow_bar(draw, margin_x, y, content_w - int(60 * scale), bar_h,
                        progress, label, COLORS, scale, font_small)

        elif kind == "hsk_bar":
            _, label, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(20 * scale)
            draw.text((margin_x, y - 2), label, fill=COLORS["text"], font=font_small)
            bar_x = margin_x + int(80 * scale)
            bar_w = content_w - int(140 * scale)
            draw.rounded_rectangle([(bar_x, y), (bar_x + bar_w, y + bar_h)],
                                   radius=bar_h // 2, fill=COLORS["divider"])
            fill_w = max(int(bar_w * progress), bar_h)
            draw.rounded_rectangle([(bar_x, y), (bar_x + fill_w, y + bar_h)],
                                   radius=bar_h // 2, fill=COLORS["accent"])
            draw.text((bar_x + bar_w + 10, y), f"{int(progress * 100)}%",
                      fill=COLORS["faint"], font=font_small)

        elif kind == "button":
            _, text, y_pct = elem
            y = int(height * y_pct)
            btn_h = int(52 * scale)
            draw.rounded_rectangle([(margin_x, y), (margin_x + content_w, y + btn_h)],
                                   radius=12, fill=COLORS["accent"])
            tw = len(text) * int(9 * scale)
            draw.text((width // 2 - tw // 2, y + btn_h // 2 - int(10 * scale)),
                      text, fill="#ffffff", font=font_medium)

        elif kind == "session_list":
            _, items, y_pct = elem
            y = int(height * y_pct)
            for i, item in enumerate(items):
                iy = y + i * int(40 * scale)
                draw.rounded_rectangle(
                    [(margin_x, iy), (margin_x + content_w, iy + int(34 * scale))],
                    radius=6, fill=COLORS["surface"]
                )
                draw.text((margin_x + 12, iy + int(8 * scale)), item,
                          fill=COLORS["text_secondary"], font=font_small)

        elif kind == "progress_bar":
            _, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(6 * scale)
            draw.rounded_rectangle([(margin_x, y), (margin_x + content_w, y + bar_h)],
                                   radius=3, fill=COLORS["divider"])
            draw.rounded_rectangle(
                [(margin_x, y), (margin_x + int(content_w * progress), y + bar_h)],
                radius=3, fill=COLORS["accent"]
            )

        elif kind == "badge":
            _, text, y_pct = elem
            y = int(height * y_pct)
            badge_w = int(200 * scale)
            badge_h = int(30 * scale)
            bx = width // 2 - badge_w // 2
            draw.rounded_rectangle([(bx, y), (bx + badge_w, y + badge_h)],
                                   radius=badge_h // 2, fill=COLORS["surface"])
            draw.text((bx + badge_w // 2 - len(text) * int(3.5 * scale), y + int(6 * scale)),
                      text, fill=COLORS["accent"], font=font_small)

        elif kind == "hanzi_display":
            _, char, y_pct = elem
            y = int(height * y_pct)
            draw.text((width // 2 - int(40 * scale), y), char,
                      fill=COLORS["text"], font=font_hanzi)

        elif kind == "prompt":
            _, text, y_pct = elem
            y = int(height * y_pct)
            tw = len(text) * int(5 * scale)
            draw.text((width // 2 - tw, y - int(10 * scale)), text,
                      fill=COLORS["text"], font=font_medium)

        elif kind == "option":
            _, text, is_correct, y_pct = elem
            y = int(height * y_pct)
            opt_h = int(48 * scale)
            bg = "#e8f5e9" if is_correct else COLORS["surface"]
            border = COLORS["correct"] if is_correct else COLORS["divider"]
            draw.rounded_rectangle([(margin_x, y), (margin_x + content_w, y + opt_h)],
                                   radius=10, fill=bg, outline=border, width=2)
            draw.text((margin_x + 20, y + opt_h // 2 - int(8 * scale)), text,
                      fill=COLORS["text"], font=font_medium)

        elif kind == "label":
            _, text, y_pct = elem
            y = int(height * y_pct)
            draw.text((margin_x, y - int(8 * scale)), text, fill=COLORS["faint"], font=font_small)

        elif kind == "counter":
            _, text, y_pct = elem
            y = int(height * y_pct)
            tw = len(text) * int(4 * scale)
            draw.text((width // 2 - tw, y - int(8 * scale)), text,
                      fill=COLORS["faint"], font=font_small)

        elif kind == "divider_line":
            _, y_pct = elem
            y = int(height * y_pct)
            draw.line([(margin_x, y), (width - margin_x, y)], fill=COLORS["divider"], width=1)

        elif kind == "skill_detail":
            _, label, count, progress, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(12 * scale)
            draw.text((margin_x, y - int(16 * scale)), label, fill=COLORS["text"], font=font_small)
            draw.text((width - margin_x - len(count) * int(7 * scale), y - int(16 * scale)),
                      count, fill=COLORS["faint"], font=font_tiny)
            draw.rounded_rectangle([(margin_x, y + 4), (margin_x + content_w, y + 4 + bar_h)],
                                   radius=bar_h // 2, fill=COLORS["divider"])
            draw.rounded_rectangle(
                [(margin_x, y + 4), (margin_x + int(content_w * progress), y + 4 + bar_h)],
                radius=bar_h // 2, fill=COLORS["accent"]
            )

        elif kind == "tone_contour":
            _, points, y_pct = elem
            y_start = int(height * (y_pct - 0.10))
            y_end = int(height * y_pct)
            contour_h = y_end - y_start
            draw.rounded_rectangle(
                [(margin_x, y_start - 10), (margin_x + content_w, y_end + 10)],
                radius=8, fill=COLORS["surface"]
            )
            n = len(points)
            coords = []
            for i, p in enumerate(points):
                px = margin_x + 20 + int((content_w - 40) * i / (n - 1))
                py = y_start + int(contour_h * (1 - p))
                coords.append((px, py))
            if len(coords) >= 2:
                draw.line(coords, fill=COLORS["accent"], width=int(3 * scale))

        elif kind == "grade_badge":
            _, text, is_good, y_pct = elem
            y = int(height * y_pct)
            badge_color = COLORS["correct"] if is_good else COLORS["secondary"]
            badge_w = int(240 * scale)
            badge_h = int(36 * scale)
            bx = width // 2 - badge_w // 2
            draw.rounded_rectangle([(bx, y), (bx + badge_w, y + badge_h)],
                                   radius=badge_h // 2, fill=COLORS["surface"])
            draw.text((bx + badge_w // 2 - len(text) * int(4.5 * scale), y + int(8 * scale)),
                      text, fill=badge_color, font=font_medium)

        elif kind == "detail_row":
            _, items, y_pct = elem
            y = int(height * y_pct)
            col_w = content_w // len(items)
            for i, item in enumerate(items):
                draw.text((margin_x + col_w * i, y - int(6 * scale)), item,
                          fill=COLORS["faint"], font=font_tiny)

        elif kind == "pinyin":
            _, text, y_pct = elem
            y = int(height * y_pct)
            tw = len(text) * int(5 * scale)
            draw.text((width // 2 - tw, y - int(10 * scale)), text,
                      fill=COLORS["text_secondary"], font=font_medium)

        elif kind == "tone_summary":
            _, label, accuracy, y_pct = elem
            y = int(height * y_pct)
            bar_h = int(10 * scale)
            draw.text((margin_x, y - int(10 * scale)), label, fill=COLORS["text"], font=font_small)
            bar_x = margin_x + int(100 * scale)
            bar_w = content_w - int(160 * scale)
            draw.rounded_rectangle([(bar_x, y - bar_h), (bar_x + bar_w, y)],
                                   radius=bar_h // 2, fill=COLORS["divider"])
            draw.rounded_rectangle(
                [(bar_x, y - bar_h), (bar_x + int(bar_w * accuracy), y)],
                radius=bar_h // 2, fill=COLORS["accent"]
            )
            draw.text((bar_x + bar_w + 10, y - int(10 * scale)),
                      f"{int(accuracy * 100)}%", fill=COLORS["faint"], font=font_tiny)

        elif kind == "setting_group":
            _, label, y_pct = elem
            y = int(height * y_pct)
            draw.text((margin_x, y - int(10 * scale)), label,
                      fill=COLORS["accent"], font=font_small)

        elif kind == "setting_row":
            _, label, value, y_pct = elem
            y = int(height * y_pct)
            row_h = int(36 * scale)
            draw.rounded_rectangle([(margin_x, y), (margin_x + content_w, y + row_h)],
                                   radius=6, fill=COLORS["surface"])
            draw.text((margin_x + 14, y + row_h // 2 - int(8 * scale)),
                      label, fill=COLORS["text"], font=font_small)
            draw.text((width - margin_x - 14 - len(value) * int(7 * scale),
                       y + row_h // 2 - int(8 * scale)),
                      value, fill=COLORS["faint"], font=font_small)

        elif kind == "version_label":
            _, text, y_pct = elem
            y = int(height * y_pct)
            tw = len(text) * int(4 * scale)
            draw.text((width // 2 - tw, y - int(6 * scale)), text,
                      fill=COLORS["faint"], font=font_tiny)

    # Caption at bottom
    draw.text((width // 2 - len(screen["caption"]) * int(3.5 * scale),
               height - int(40 * scale)),
              screen["caption"], fill=COLORS["faint"], font=font_small)

    return img


def generate_feature_graphic_pillow(width, height):
    """Generate the Android feature graphic using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), COLORS["base"])
    draw = ImageDraw.Draw(img)

    def _font(size, bold=False):
        try:
            if bold:
                return ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", size)
            return ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", size)
        except (OSError, IOError):
            try:
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except (OSError, IOError):
                return ImageFont.load_default()

    # Large hanzi character (faint)
    font_hanzi = _font(160, bold=True)
    draw.text((int(width * 0.10), int(height * 0.12)), "\u6f2b",
              fill=COLORS["divider"], font=font_hanzi)

    # App name
    font_title = _font(64, bold=True)
    draw.text((int(width * 0.42), int(height * 0.25)), "Aelu",
              fill=COLORS["text"], font=font_title)

    # Divider
    draw.line([(int(width * 0.42), int(height * 0.54)),
               (int(width * 0.74), int(height * 0.54))],
              fill=COLORS["divider"], width=1)

    # Subtitle
    font_sub = _font(22)
    draw.text((int(width * 0.42), int(height * 0.60)), "Patient Chinese Study",
              fill=COLORS["text_secondary"], font=font_sub)

    return img


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate app store screenshot placeholders")
    parser.add_argument("--format", choices=["auto", "svg", "png"], default="auto",
                        help="Output format: auto (PNG if Pillow available, else SVG), svg, or png")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: mobile/store-assets/screenshots)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "mobile" / "store-assets" / "screenshots"

    has_pillow = _try_pillow()

    if args.format == "png" and not has_pillow:
        print("Error: PNG format requested but Pillow is not installed.")
        print("Install with: pip install Pillow")
        print("Falling back to SVG.")
        use_png = False
    elif args.format == "svg":
        use_png = False
    elif args.format == "png":
        use_png = True
    else:  # auto
        use_png = has_pillow

    fmt = "PNG" if use_png else "SVG"
    ext = "png" if use_png else "svg"

    # Create output directories
    ios_dir = output_dir / "ios"
    android_dir = output_dir / "android"
    ios_dir.mkdir(parents=True, exist_ok=True)
    android_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Aelu Screenshot Generator")
    print("=" * 60)
    print(f"  Format:  {fmt}")
    print(f"  Output:  {output_dir}")
    print(f"  Screens: {len(SCREENS)}")
    print()

    generated = 0

    # iOS screenshots
    print("  iOS Screenshots")
    print("  " + "-" * 40)
    for screen in SCREENS:
        for size_name, w, h in IOS_SIZES:
            fname = f"{screen['filename']}_{size_name}.{ext}"
            fpath = ios_dir / fname

            if use_png:
                img = generate_screen_pillow(screen, w, h)
                img.save(str(fpath), "PNG")
            else:
                svg = generate_screen_svg(screen, w, h)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(svg)

            print(f"    {fname} ({w}x{h})")
            generated += 1

    print()

    # Android screenshots
    print("  Android Screenshots")
    print("  " + "-" * 40)
    for screen in SCREENS:
        for size_name, w, h in ANDROID_SIZES:
            fname = f"{screen['filename']}_{size_name}.{ext}"
            fpath = android_dir / fname

            if use_png:
                img = generate_screen_pillow(screen, w, h)
                img.save(str(fpath), "PNG")
            else:
                svg = generate_screen_svg(screen, w, h)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(svg)

            print(f"    {fname} ({w}x{h})")
            generated += 1

    # Android feature graphic
    fg_name, fg_w, fg_h = ANDROID_FEATURE_GRAPHIC
    fg_fname = f"feature_graphic.{ext}"
    fg_path = android_dir / fg_fname

    if use_png:
        img = generate_feature_graphic_pillow(fg_w, fg_h)
        img.save(str(fg_path), "PNG")
    else:
        svg = generate_feature_graphic_svg(fg_w, fg_h)
        with open(fg_path, "w", encoding="utf-8") as f:
            f.write(svg)

    print(f"    {fg_fname} ({fg_w}x{fg_h})")
    generated += 1

    print()
    print(f"  Generated {generated} files in {output_dir}")
    print()
    print("  Next steps:")
    print("  1. Review placeholders and replace with real screenshots")
    print("  2. Add caption overlays per marketing/screenshots-checklist.md")
    print("  3. Frame screenshots in device mockups for store listings")
    print("=" * 60)


if __name__ == "__main__":
    main()
