#!/usr/bin/env python3
"""Visual regression testing — screenshot comparison against saved baselines.

Captures key pages at desktop and mobile viewports, then compares pixel-by-pixel
against baseline images in tests/visual-baselines/. Reports diff percentage and
saves diff images for review.

Prerequisites:
    pip install playwright Pillow
    playwright install chromium

Usage:
    # Capture new baselines (run against known-good state):
    python scripts/visual_regression.py --update-baselines

    # Run regression check (compare against baselines):
    python scripts/visual_regression.py

    # Run with custom threshold:
    python scripts/visual_regression.py --threshold 1.0

Exit codes:
    0 — all pages within threshold
    1 — one or more pages exceed threshold (regression detected)
    2 — baselines missing (run --update-baselines first)
"""
import argparse
import os
import sys
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINES_DIR = PROJECT_ROOT / "tests" / "visual-baselines"

# Pages to capture with their expected paths
PAGES = [
    {"name": "landing", "path": "/", "wait_for": "body"},
    {"name": "login", "path": "/login", "wait_for": "form"},
]

# Viewports: (name, width, height)
VIEWPORTS = [
    ("desktop", 1280, 800),
    ("mobile", 375, 812),
]

# Default diff threshold (percentage of pixels that can differ)
DEFAULT_THRESHOLD = 0.5
# WebGL pages get a higher threshold due to GPU rendering variance
WEBGL_THRESHOLD = 2.0
WEBGL_PAGES = {"landing"}


def _ensure_playwright():
    """Check playwright is available, provide install instructions if not."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        return False


def _ensure_pillow():
    """Check Pillow is available for image comparison."""
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        return False


def _pixel_diff(img1_path, img2_path):
    """Compare two images pixel-by-pixel, return diff percentage."""
    from PIL import Image
    import math

    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    # Resize to same dimensions if different
    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.LANCZOS)

    pixels1 = img1.load()
    pixels2 = img2.load()
    width, height = img1.size
    total = width * height
    diff_count = 0
    threshold = 30  # per-channel tolerance for anti-aliasing differences

    for y in range(height):
        for x in range(width):
            r1, g1, b1 = pixels1[x, y]
            r2, g2, b2 = pixels2[x, y]
            if (abs(r1 - r2) > threshold or
                abs(g1 - g2) > threshold or
                abs(b1 - b2) > threshold):
                diff_count += 1

    return (diff_count / total) * 100 if total > 0 else 0


def _save_diff_image(img1_path, img2_path, diff_path):
    """Create a visual diff image highlighting changed pixels in red."""
    from PIL import Image

    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.LANCZOS)

    diff = Image.new("RGB", img1.size)
    pixels1 = img1.load()
    pixels2 = img2.load()
    diff_pixels = diff.load()
    width, height = img1.size
    threshold = 30

    for y in range(height):
        for x in range(width):
            r1, g1, b1 = pixels1[x, y]
            r2, g2, b2 = pixels2[x, y]
            if (abs(r1 - r2) > threshold or
                abs(g1 - g2) > threshold or
                abs(b1 - b2) > threshold):
                diff_pixels[x, y] = (255, 0, 0)  # Red for differences
            else:
                # Dimmed version of original
                diff_pixels[x, y] = (r1 // 3, g1 // 3, b1 // 3)

    diff.save(diff_path)


def capture_screenshots(base_url, output_dir, dark_mode=False):
    """Capture screenshots of all pages at all viewports."""
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for viewport_name, width, height in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme="dark" if dark_mode else "light",
            )
            page = context.new_page()

            for page_config in PAGES:
                name = page_config["name"]
                url = base_url + page_config["path"]
                mode_suffix = "-dark" if dark_mode else ""
                filename = f"{name}-{viewport_name}{mode_suffix}.png"
                filepath = output_dir / filename

                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                    # Wait for any animations to settle
                    page.wait_for_timeout(1000)
                    page.screenshot(path=str(filepath), full_page=False)
                    captured.append((name, viewport_name, filepath))
                    print(f"  Captured: {filename}")
                except Exception as e:
                    print(f"  WARN: Failed to capture {filename}: {e}")

            context.close()
        browser.close()

    return captured


def update_baselines(base_url):
    """Capture new baseline screenshots."""
    print("Updating visual baselines...")
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    # Light mode
    captured = capture_screenshots(base_url, BASELINES_DIR)
    # Dark mode
    captured += capture_screenshots(base_url, BASELINES_DIR, dark_mode=True)

    print(f"\nBaselines updated: {len(captured)} screenshots saved to {BASELINES_DIR}")
    return 0


def run_regression(base_url, threshold):
    """Compare current screenshots against baselines."""
    if not BASELINES_DIR.exists() or not any(BASELINES_DIR.glob("*.png")):
        print("ERROR: No baselines found. Run with --update-baselines first.")
        return 2

    current_dir = PROJECT_ROOT / "tests" / "visual-current"
    diff_dir = PROJECT_ROOT / "tests" / "visual-diffs"

    # Clean previous runs
    for d in (current_dir, diff_dir):
        if d.exists():
            for f in d.glob("*.png"):
                f.unlink()
        d.mkdir(parents=True, exist_ok=True)

    print("Capturing current screenshots...")
    captured = capture_screenshots(base_url, current_dir)
    captured += capture_screenshots(base_url, current_dir, dark_mode=True)

    print("\nComparing against baselines...")
    failures = []
    passes = []

    for name, viewport_name, current_path in captured:
        baseline_path = BASELINES_DIR / current_path.name
        if not baseline_path.exists():
            print(f"  SKIP: No baseline for {current_path.name}")
            continue

        diff_pct = _pixel_diff(baseline_path, current_path)
        page_threshold = WEBGL_THRESHOLD if name in WEBGL_PAGES else threshold

        if diff_pct > page_threshold:
            diff_path = diff_dir / f"diff-{current_path.name}"
            _save_diff_image(baseline_path, current_path, diff_path)
            failures.append((current_path.name, diff_pct, page_threshold))
            print(f"  FAIL: {current_path.name} — {diff_pct:.2f}% diff "
                  f"(threshold: {page_threshold}%)")
        else:
            passes.append((current_path.name, diff_pct))
            print(f"  PASS: {current_path.name} — {diff_pct:.2f}% diff")

    print(f"\nResults: {len(passes)} passed, {len(failures)} failed")

    if failures:
        print(f"\nDiff images saved to {diff_dir}")
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Visual regression testing")
    parser.add_argument("--update-baselines", action="store_true",
                        help="Capture new baseline screenshots")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Pixel diff threshold percentage (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--url", default="http://localhost:5000",
                        help="Base URL of the dev server")
    args = parser.parse_args()

    if not _ensure_playwright() or not _ensure_pillow():
        return 2

    if args.update_baselines:
        return update_baselines(args.url)
    else:
        return run_regression(args.url, args.threshold)


if __name__ == "__main__":
    sys.exit(main())
