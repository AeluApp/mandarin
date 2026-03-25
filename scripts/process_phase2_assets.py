#!/usr/bin/env python3
"""
Process Phase 2 assets for Aelu:
- Background removal on calligraphy characters and plant sprites
- Image optimization (resize, compress, WebP generation)
- Email header processing
"""

import os
import sys
import shutil
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:
    print("ERROR: Pillow not installed. Run: pip3 install Pillow")
    sys.exit(1)

# Paths
SRC = Path("/Users/jasongerson/Desktop/Aelu/phase 2")
PROJ = Path(__file__).resolve().parent.parent
OUT = PROJ / "mandarin" / "web" / "static" / "assets" / "phase2"

# Create output directories
for d in ["videos", "calligraphy", "textures", "plants", "email"]:
    (OUT / d).mkdir(parents=True, exist_ok=True)


def remove_background_calligraphy(src_path, dst_path, size=512):
    """
    Remove background from calligraphy characters.
    Strategy: Characters are dark ink on dark/gray gradient backgrounds.
    The ink strokes have texture/detail the background doesn't.
    We detect the uniform background and make it transparent.
    """
    img = Image.open(src_path).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)

    pixels = img.load()
    w, h = img.size

    # Sample corners to get background color range
    corner_samples = []
    margin = 10
    for x in range(margin):
        for y in range(margin):
            corner_samples.append(pixels[x, y][:3])
            corner_samples.append(pixels[w - 1 - x, y][:3])
            corner_samples.append(pixels[x, h - 1 - y][:3])
            corner_samples.append(pixels[w - 1 - x, h - 1 - y][:3])

    # Calculate background luminance range
    bg_lums = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in corner_samples]
    bg_mean = sum(bg_lums) / len(bg_lums)
    bg_std = (sum((l - bg_mean) ** 2 for l in bg_lums) / len(bg_lums)) ** 0.5

    # Threshold: anything within ~2 std devs of background luminance is background
    threshold = max(bg_std * 3, 15)

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            diff = abs(lum - bg_mean)

            if diff < threshold:
                # Background pixel — make transparent
                pixels[x, y] = (0, 0, 0, 0)
            else:
                # Ink pixel — keep as black with proportional alpha
                # The more different from bg, the more opaque
                ink_alpha = min(255, int((diff / max(bg_mean, 1)) * 255 * 2))
                pixels[x, y] = (0, 0, 0, ink_alpha)

    # Light feather to smooth edges
    alpha = img.split()[3]
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.5))
    img.putalpha(alpha)

    img.save(dst_path, "PNG", optimize=True)
    return dst_path


def remove_background_plant(src_path, dst_path, size=256):
    """
    Remove background from plant sprites.
    Plants have colored content (greens, pinks) on gray/dark backgrounds.
    Strategy: detect uniform background from corners, preserve colored content.
    """
    img = Image.open(src_path).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)

    pixels = img.load()
    w, h = img.size

    # Sample corners for background
    corner_samples = []
    margin = 15
    for x in range(margin):
        for y in range(margin):
            corner_samples.append(pixels[x, y][:3])
            corner_samples.append(pixels[w - 1 - x, y][:3])
            corner_samples.append(pixels[x, h - 1 - y][:3])
            corner_samples.append(pixels[w - 1 - x, h - 1 - y][:3])

    bg_r = sum(c[0] for c in corner_samples) / len(corner_samples)
    bg_g = sum(c[1] for c in corner_samples) / len(corner_samples)
    bg_b = sum(c[2] for c in corner_samples) / len(corner_samples)

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            # Color distance from background
            dist = ((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2) ** 0.5

            if dist < 25:
                # Very close to background — fully transparent
                pixels[x, y] = (0, 0, 0, 0)
            elif dist < 50:
                # Transition zone — partial transparency
                alpha = int((dist - 25) / 25 * 255)
                pixels[x, y] = (r, g, b, alpha)
            # else: keep original pixel fully opaque

    # Smooth alpha edges
    alpha = img.split()[3]
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    img.putalpha(alpha)

    img.save(dst_path, "PNG", optimize=True)
    return dst_path


def optimize_texture(src_path, dst_path, max_size=None):
    """Resize and compress a texture."""
    img = Image.open(src_path)
    if max_size:
        img = img.resize(max_size, Image.LANCZOS)
    img.save(dst_path, "PNG", optimize=True)
    return dst_path


def make_webp(png_path, quality=85):
    """Generate WebP variant alongside PNG."""
    webp_path = png_path.with_suffix(".webp")
    img = Image.open(png_path)
    if img.mode == "RGBA":
        img.save(webp_path, "WEBP", quality=quality, method=6)
    else:
        img.save(webp_path, "WEBP", quality=quality, method=6)
    return webp_path


def process_email_header(src_path, dst_path, width=600):
    """Resize email header to 600px wide, optimize."""
    img = Image.open(src_path).convert("RGB")
    ratio = width / img.width
    new_h = int(img.height * ratio)
    img = img.resize((width, new_h), Image.LANCZOS)
    # Save as both JPG and PNG
    jpg_path = dst_path.with_suffix(".jpg")
    img.save(jpg_path, "JPEG", quality=85, optimize=True)
    img.save(dst_path, "PNG", optimize=True)
    return dst_path


def make_dark_email(src_path, dst_path):
    """Create dark mode variant of email header by shifting colors."""
    img = Image.open(src_path).convert("RGB")
    # Reduce brightness significantly, shift cool
    from PIL import ImageEnhance
    img = ImageEnhance.Brightness(img).enhance(0.35)
    img = ImageEnhance.Color(img).enhance(0.7)
    img.save(dst_path, "PNG", optimize=True)
    return dst_path


# ============================================================
# Main processing
# ============================================================

print("=" * 60)
print("Phase 2 Asset Processing")
print("=" * 60)

# --- Calligraphy Characters ---
print("\n--- Calligraphy Characters (background removal) ---")
char_map = {
    "xue.png": "xue",
    "ji.png": "ji",
    "ting.png": "ting",
    "shuo.png": "shuo",
    "du.png": "du",
    "xie.png": "xie",
    "man.png": "man",
    "zhong.png": "zhong",
    "wen": "wen",  # no .png extension in source
    "xin.png": "xin",
}

for src_name, dst_name in char_map.items():
    src = SRC / src_name
    if not src.exists():
        print(f"  SKIP {src_name} (not found)")
        continue
    dst = OUT / "calligraphy" / f"{dst_name}.png"
    remove_background_calligraphy(src, dst)
    webp = make_webp(dst)
    size_kb = dst.stat().st_size / 1024
    print(f"  ✓ {dst_name}.png ({size_kb:.0f}KB) + .webp")

# --- Plant Sprites ---
print("\n--- Plant Sprites (background removal) ---")
plant_map = {
    "bamboo sprout.png": "bamboo",
    "plum blossom branch.png": "plum-blossom",
    "lotus bud.png": "lotus",
    "pine sapling.png": "pine",
    "orchid grass.png": "orchid",
}

for src_name, dst_name in plant_map.items():
    src = SRC / src_name
    if not src.exists():
        print(f"  SKIP {src_name} (not found)")
        continue
    dst = OUT / "plants" / f"{dst_name}.png"
    remove_background_plant(src, dst)
    webp = make_webp(dst)
    size_kb = dst.stat().st_size / 1024
    print(f"  ✓ {dst_name}.png ({size_kb:.0f}KB) + .webp")

# --- Textures ---
print("\n--- Textures ---")
texture_map = {
    "Terrain Displacement Map.png": ("terrain-heightmap.png", (512, 512)),
    "paper-plaster-albedo.png": ("paper-albedo.png", (1024, 1024)),
    "ink stroke atlas": ("ink-strokes.png", (1024, 512)),
    "garden ground texture.png": ("garden-ground.png", (1200, 200)),
    "scroll edge border.png": ("scroll-border.png", (800, 24)),
    "rain particle": ("rain-particle.png", (32, 32)),
}

for src_name, (dst_name, size) in texture_map.items():
    src = SRC / src_name
    if not src.exists():
        print(f"  SKIP {src_name} (not found)")
        continue
    dst = OUT / "textures" / dst_name
    optimize_texture(src, dst, max_size=size)
    webp = make_webp(dst)
    size_kb = dst.stat().st_size / 1024
    print(f"  ✓ {dst_name} ({size_kb:.0f}KB, {size[0]}x{size[1]}) + .webp")

# --- Email Headers ---
print("\n--- Email Headers ---")
email_map = {
    "welcome email header.png": "welcome",
    "streak reminder email header.png": "streak",
    "weekly progress email header.png": "progress",
    "re-engagement email header.png": "reengagement",
}

for src_name, dst_name in email_map.items():
    src = SRC / src_name
    if not src.exists():
        print(f"  SKIP {src_name} (not found)")
        continue
    dst = OUT / "email" / f"{dst_name}.png"
    process_email_header(src, dst, width=600)
    make_webp(dst)
    # Dark variant
    dark_dst = OUT / "email" / f"{dst_name}-dark.png"
    make_dark_email(dst, dark_dst)
    make_webp(dark_dst)
    size_kb = dst.stat().st_size / 1024
    print(f"  ✓ {dst_name}.png ({size_kb:.0f}KB, 600px) + dark + .webp")

# --- Videos (just copy for now, ffmpeg later) ---
print("\n--- Videos (copy raw, will transcode with ffmpeg) ---")
for f in SRC.glob("*.mp4"):
    if "hero" in f.name.lower():
        dst = OUT / "videos" / "hero-ink.mp4"
    elif "ambient" in f.name.lower() or "login" in f.name.lower():
        dst = OUT / "videos" / "login-mountains.mp4"
    else:
        continue
    shutil.copy2(f, dst)
    size_mb = dst.stat().st_size / (1024 * 1024)
    print(f"  ✓ {dst.name} ({size_mb:.1f}MB)")

# --- Summary ---
print("\n" + "=" * 60)
total_files = sum(1 for _ in OUT.rglob("*") if _.is_file())
total_size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
print(f"Total: {total_files} files, {total_size / (1024 * 1024):.1f}MB")
print(f"Output: {OUT}")
print("=" * 60)
