#!/usr/bin/env python3
"""Download Chinese pronunciation audio from Wikimedia Commons.

Wikimedia Commons audio is typically CC BY-SA 3.0 or CC BY-SA 4.0.

Builds URLs for Wikimedia Commons audio files matching content_item hanzi,
downloads them to data/audio/wikimedia/, and updates content_items with
audio paths.

Usage:
    python scripts/ingest_wikimedia_audio.py [--limit 300] [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

AUDIO_DIR = PROJECT_ROOT / "data" / "audio" / "wikimedia"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Common filename patterns on Wikimedia Commons for Chinese pronunciation
FILENAME_PATTERNS = [
    "zh-{hanzi}.ogg",
    "Zh-{hanzi}.ogg",
    "zh-cmn-{hanzi}.ogg",
    "cmn-{hanzi}.ogg",
    "lzh-{hanzi}.ogg",
]


def build_commons_url(filename: str) -> str:
    """Build the direct download URL for a Wikimedia Commons file.

    Wikimedia uses MD5 hashing to distribute files across directories.
    URL: https://upload.wikimedia.org/wikipedia/commons/<a>/<ab>/<filename>
    where a = md5[0], ab = md5[0:2].
    """
    md5 = hashlib.md5(filename.encode("utf-8")).hexdigest()
    encoded_filename = quote(filename)
    return (
        f"https://upload.wikimedia.org/wikipedia/commons/"
        f"{md5[0]}/{md5[0:2]}/{encoded_filename}"
    )


def check_file_exists_on_commons(filename: str, timeout: int = 10) -> bool:
    """Check if a file exists on Wikimedia Commons via the API."""
    try:
        import requests
    except ImportError:
        return False

    try:
        resp = requests.get(
            COMMONS_API,
            params={
                "action": "query",
                "titles": f"File:{filename}",
                "format": "json",
            },
            timeout=timeout,
            headers={"User-Agent": "Aelu/1.0 (Mandarin Learning; contact@aeluapp.com)"},
        )
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        # If page ID is -1, file doesn't exist
        for page_id, page_data in pages.items():
            if int(page_id) != -1:
                return True
        return False
    except Exception as e:
        logger.debug("API check failed for %s: %s", filename, e)
        return False


def find_audio_for_hanzi(hanzi: str, verify: bool = True) -> str | None:
    """Find a Wikimedia Commons audio filename for the given hanzi.

    Tries several naming patterns. If verify=True, checks the API to confirm
    the file exists (slower but accurate). Returns the filename or None.
    """
    for pattern in FILENAME_PATTERNS:
        filename = pattern.format(hanzi=hanzi)
        if verify:
            if check_file_exists_on_commons(filename):
                return filename
        else:
            return filename  # Return first candidate without verifying

    return None


def download_audio_file(filename: str, dest_dir: Path, timeout: int = 30) -> Path | None:
    """Download a single audio file from Wikimedia Commons.

    Returns the local path on success, None on failure.
    """
    try:
        import requests
    except ImportError:
        logger.error("requests not installed: pip install requests")
        return None

    url = build_commons_url(filename)
    dest_path = dest_dir / filename

    if dest_path.exists() and dest_path.stat().st_size > 0:
        logger.debug("Already downloaded: %s", filename)
        return dest_path

    try:
        resp = requests.get(
            url, timeout=timeout, stream=True,
            headers={"User-Agent": "Aelu/1.0 (Mandarin Learning; contact@aeluapp.com)"},
        )
        if resp.status_code == 404:
            logger.debug("Not found: %s", url)
            return None
        resp.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.debug("Downloaded: %s (%d bytes)", filename, dest_path.stat().st_size)
        return dest_path

    except Exception as e:
        logger.debug("Download failed for %s: %s", filename, e)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Download Chinese pronunciation from Wikimedia Commons (CC BY-SA)"
    )
    parser.add_argument(
        "--limit", type=int, default=300,
        help="Maximum items to process (default: 300)",
    )
    parser.add_argument(
        "--no-verify", action="store_true",
        help="Skip API verification of file existence (faster, more 404s)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Delay between API requests in seconds (default: 0.5)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Build URLs but do not download or update DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    from mandarin import db

    # Create output directory
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    counts = {"checked": 0, "found": 0, "downloaded": 0, "updated": 0, "skipped": 0}

    with db.connection() as conn:
        # Get content_items that need audio (vocab words, no audio yet)
        rows = conn.execute(
            """SELECT id, hanzi FROM content_item
               WHERE audio_available = 0
                 AND item_type = 'vocab'
                 AND status = 'drill_ready'
               ORDER BY hsk_level ASC, id ASC
               LIMIT ?""",
            (args.limit,),
        ).fetchall()

        logger.info("Found %d content_items needing audio", len(rows))

        for row in rows:
            item_id = row["id"]
            hanzi = row["hanzi"]
            counts["checked"] += 1

            # Find audio filename
            filename = find_audio_for_hanzi(hanzi, verify=not args.no_verify)

            if not filename:
                logger.debug("No audio found for: %s (id=%d)", hanzi, item_id)
                continue

            counts["found"] += 1
            url = build_commons_url(filename)

            if args.dry_run:
                logger.info("  [DRY] %s -> %s", hanzi, url)
                continue

            # Download
            local_path = download_audio_file(filename, AUDIO_DIR)
            if not local_path:
                continue

            counts["downloaded"] += 1
            relative_path = str(local_path.relative_to(PROJECT_ROOT))

            # Update content_item
            try:
                conn.execute(
                    """UPDATE content_item
                       SET audio_available = 1, audio_file_path = ?
                       WHERE id = ?""",
                    (relative_path, item_id),
                )
                counts["updated"] += 1
            except sqlite3.Error as e:
                logger.warning("DB update failed for %s: %s", hanzi, e)

            # Rate limit
            if args.delay > 0:
                time.sleep(args.delay)

            # Progress
            if counts["checked"] % 50 == 0:
                conn.commit()
                logger.info(
                    "  Progress: checked %d, found %d, downloaded %d",
                    counts["checked"], counts["found"], counts["downloaded"],
                )

        conn.commit()

    prefix = "DRY RUN:" if args.dry_run else "Done."
    logger.info(
        "%s Checked: %d, Found: %d, Downloaded: %d, Updated in DB: %d",
        prefix, counts["checked"], counts["found"],
        counts["downloaded"], counts["updated"],
    )


if __name__ == "__main__":
    main()
