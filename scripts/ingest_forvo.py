#!/usr/bin/env python3
"""Match local pronunciation audio files to content_items.

WARNING: Forvo audio is CC BY-NC-SA 3.0 — NOT cleared for commercial use.
This script is for PERSONAL/EDUCATIONAL use only, NOT for Aelu production.
For production, use Kokoro TTS (MIT license) or commissioned recordings.

Expects audio files in data/audio/forvo/ directory. User downloads these
separately (Forvo content is CC BY-NC-SA 3.0 for personal use only).

Filenames are expected to match hanzi, e.g.:
    你好.mp3, 你好.wav, pronunciation_zh_你好.mp3

The script matches filenames to content_item.hanzi and sets
audio_available=1 and audio_file_path on matching records.

Usage:
    python scripts/ingest_forvo.py [--dir data/audio/forvo] [--dry-run] [--verbose]
"""

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "audio" / "forvo"


def extract_hanzi_from_filename(filename: str) -> str:
    """Extract Chinese characters from an audio filename.

    Handles patterns:
    - 你好.mp3 -> 你好
    - pronunciation_zh_你好.mp3 -> 你好
    - zh_你好_12345.mp3 -> 你好
    """
    stem = Path(filename).stem

    # Pattern: pronunciation_zh_<hanzi> or zh_<hanzi>_<id>
    # Strip common prefixes
    for prefix in ["pronunciation_zh_", "pronunciation_cmn_", "zh_", "cmn_"]:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break

    # Strip trailing numeric IDs (e.g., _12345)
    stem = re.sub(r'_\d+$', '', stem)

    # Extract just the Chinese characters
    hanzi_chars = re.findall(r'[\u4e00-\u9fff]+', stem)
    if hanzi_chars:
        return "".join(hanzi_chars)

    return stem


def validate_audio_file(filepath: Path) -> bool:
    """Check that a file is a valid audio file (by extension and non-empty)."""
    if filepath.suffix.lower() not in VALID_EXTENSIONS:
        return False
    if not filepath.is_file():
        return False
    if filepath.stat().st_size == 0:
        return False
    return True


def scan_audio_files(audio_dir: Path) -> list:
    """Scan directory for audio files. Returns list of (path, hanzi) tuples."""
    if not audio_dir.exists():
        logger.warning("Audio directory does not exist: %s", audio_dir)
        return []

    results = []
    for filepath in sorted(audio_dir.iterdir()):
        if not validate_audio_file(filepath):
            continue
        hanzi = extract_hanzi_from_filename(filepath.name)
        if hanzi and re.search(r'[\u4e00-\u9fff]', hanzi):
            results.append((filepath, hanzi))

    return results


def match_and_update(conn, audio_files: list, dry_run: bool = False) -> dict:
    """Match audio files to content_items and update audio fields.

    Returns counts: {matched, unmatched, already_set, updated}.
    """
    counts = {"matched": 0, "unmatched": 0, "already_set": 0, "updated": 0}

    for filepath, hanzi in audio_files:
        # Find matching content_items
        rows = conn.execute(
            "SELECT id, audio_available, audio_file_path FROM content_item WHERE hanzi = ?",
            (hanzi,),
        ).fetchall()

        if not rows:
            counts["unmatched"] += 1
            logger.debug("No content_item match for: %s (%s)", hanzi, filepath.name)
            continue

        counts["matched"] += 1
        relative_path = str(filepath.relative_to(PROJECT_ROOT))

        for row in rows:
            if row["audio_available"] == 1 and row["audio_file_path"]:
                counts["already_set"] += 1
                continue

            if dry_run:
                logger.info(
                    "  [DRY] Would set audio for content_item %d (%s) -> %s",
                    row["id"], hanzi, relative_path,
                )
            else:
                conn.execute(
                    """UPDATE content_item
                       SET audio_available = 1, audio_file_path = ?
                       WHERE id = ?""",
                    (relative_path, row["id"]),
                )

            counts["updated"] += 1

    if not dry_run:
        conn.commit()

    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Match Forvo audio files to content_items"
    )
    parser.add_argument(
        "--dir", type=str, default=str(DEFAULT_AUDIO_DIR),
        help=f"Audio files directory (default: {DEFAULT_AUDIO_DIR})",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show matches without writing to DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    audio_dir = Path(args.dir)

    if not audio_dir.exists():
        logger.info("Audio directory does not exist: %s", audio_dir)
        logger.info("Create it and add audio files, e.g.:")
        logger.info("  mkdir -p %s", audio_dir)
        logger.info("  # Add files like: 你好.mp3, 谢谢.wav, etc.")
        return

    # Scan files
    audio_files = scan_audio_files(audio_dir)
    logger.info("Found %d valid audio files in %s", len(audio_files), audio_dir)

    if not audio_files:
        logger.info("No audio files to process")
        return

    # Match and update
    from mandarin import db

    with db.connection() as conn:
        counts = match_and_update(conn, audio_files, dry_run=args.dry_run)

    prefix = "DRY RUN:" if args.dry_run else "Done."
    logger.info(
        "%s Matched: %d, Updated: %d, Already set: %d, Unmatched: %d",
        prefix, counts["matched"], counts["updated"],
        counts["already_set"], counts["unmatched"],
    )

    if counts["unmatched"] > 0:
        logger.info(
            "Tip: %d files had no content_item match. Use --verbose to see details.",
            counts["unmatched"],
        )


if __name__ == "__main__":
    main()
