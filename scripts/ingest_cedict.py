#!/usr/bin/env python3
"""Ingest CC-CEDICT dictionary into the database.

Downloads the CC-CEDICT file from MDBG and imports it using the existing
dictionary.load_cedict_to_db() function.

CC-CEDICT is released under CC BY-SA 4.0.
Source: https://cc-cedict.org/

Usage:
    python scripts/ingest_cedict.py [--dry-run] [--verbose]
"""

import argparse
import gzip
import logging
import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CEDICT_FILENAME = "cedict_1_0_ts_utf-8_mdbg.txt.gz"


def download_cedict(dest_dir: Path, timeout: int = 60) -> Path:
    """Download CC-CEDICT gzipped file from MDBG.

    Returns path to the downloaded .gz file.
    Raises on network error.
    """
    try:
        import requests
    except ImportError:
        logger.error("requests not installed: pip install requests")
        raise SystemExit(1)

    gz_path = dest_dir / CEDICT_FILENAME
    logger.info("Downloading CC-CEDICT from %s ...", CEDICT_URL)

    try:
        resp = requests.get(
            CEDICT_URL,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "Aelu/1.0 (Mandarin Learning)"},
        )
        resp.raise_for_status()

        with open(gz_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("Downloaded %d bytes to %s", gz_path.stat().st_size, gz_path)
        return gz_path

    except Exception as e:
        logger.error("Download failed: %s", e)
        raise


def extract_cedict(gz_path: Path, dest_path: Path) -> Path:
    """Extract the gzipped CC-CEDICT file.

    Returns path to the extracted .txt file.
    """
    logger.info("Extracting %s -> %s", gz_path, dest_path)
    with gzip.open(gz_path, "rb") as f_in:
        with open(dest_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    logger.info("Extracted %d bytes", dest_path.stat().st_size)
    return dest_path


def main():
    parser = argparse.ArgumentParser(
        description="Download and import CC-CEDICT dictionary (CC BY-SA 4.0)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Download and parse but do not write to DB",
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="Use a local cedict.txt file instead of downloading",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    from mandarin.settings import DATA_DIR
    from mandarin.dictionary import load_cedict_file, load_cedict_to_db, CEDICT_PATH

    cedict_path = Path(args.file) if args.file else CEDICT_PATH

    # Download if no local file
    if not args.file and not cedict_path.exists():
        logger.info("No local cedict.txt found at %s", cedict_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            gz_path = download_cedict(Path(tmpdir))
            extract_cedict(gz_path, cedict_path)
    elif not cedict_path.exists():
        logger.error("File not found: %s", cedict_path)
        sys.exit(1)

    # Parse to count
    entries = load_cedict_file(cedict_path)
    logger.info("Parsed %d CC-CEDICT entries", len(entries))

    if not entries:
        logger.error("No entries parsed — check file format")
        sys.exit(1)

    if args.dry_run:
        # Show sample entries
        for entry in entries[:5]:
            logger.info(
                "  %s [%s] %s",
                entry["simplified"], entry["pinyin"],
                entry["english"][:60],
            )
        logger.info("DRY RUN: would import %d entries", len(entries))
        return

    # Import to DB
    from mandarin import db

    with db.connection() as conn:
        count = load_cedict_to_db(conn, cedict_path)
        logger.info("Imported %d CC-CEDICT entries into database", count)

    # Verify
    with db.connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dictionary_entry").fetchone()[0]
        logger.info("Total dictionary entries in DB: %d", total)


if __name__ == "__main__":
    main()
