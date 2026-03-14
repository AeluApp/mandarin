#!/usr/bin/env python3
"""Manifest and status tracker for open-source Chinese learning content.

Lists all available CC/open-source content sources with license info,
estimated item counts, ingestion commands, and current status.

Usage:
    python scripts/content_sources.py                # Show all sources
    python scripts/content_sources.py --status       # Show status from DB
    python scripts/content_sources.py --json         # Output as JSON
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ── Content source manifest ──────────────────────────────────────────

SOURCES = [
    {
        "name": "CC-CEDICT",
        "url": "https://cc-cedict.org/",
        "download_url": "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz",
        "license": "CC BY-SA 4.0",
        "content_type": "dictionary",
        "description": "Community-maintained Chinese-English dictionary",
        "estimated_items": 120000,
        "ingestion_command": "python scripts/ingest_cedict.py",
        "source_key": "cedict",
    },
    {
        "name": "Tatoeba",
        "url": "https://tatoeba.org/",
        "download_url": "https://downloads.tatoeba.org/exports/sentences.tar.bz2",
        "license": "CC BY 2.0 FR",
        "content_type": "sentence_pairs",
        "description": "Crowd-sourced sentence translations (Chinese-English pairs)",
        "estimated_items": 50000,
        "ingestion_command": "python scripts/ingest_tatoeba.py --limit 10000",
        "source_key": "tatoeba",
    },
    {
        "name": "Forvo (user-provided)",
        "url": "https://forvo.com/",
        "download_url": None,
        "license": "CC BY-NC-SA 3.0 (personal use)",
        "content_type": "pronunciation_audio",
        "description": "Native speaker pronunciation recordings (user downloads separately)",
        "estimated_items": 5000,
        "ingestion_command": "python scripts/ingest_forvo.py --dir data/audio/forvo",
        "source_key": "forvo",
    },
    {
        "name": "Wikimedia Commons Audio",
        "url": "https://commons.wikimedia.org/",
        "download_url": None,
        "license": "CC BY-SA 3.0 / CC BY-SA 4.0",
        "content_type": "pronunciation_audio",
        "description": "Chinese pronunciation recordings from Wikimedia Commons",
        "estimated_items": 2000,
        "ingestion_command": "python scripts/ingest_wikimedia_audio.py --limit 300",
        "source_key": "wikimedia",
    },
    {
        "name": "OpenSubtitles",
        "url": "https://opensubtitles.org/",
        "download_url": None,
        "license": "Various (user-contributed)",
        "content_type": "subtitles_dialogue",
        "description": "Chinese film/TV subtitles for listening and dialogue practice",
        "estimated_items": 10000,
        "ingestion_command": "python scripts/ingest_open_subtitles.py <dir> --source <name>",
        "source_key": "subtitle",
    },
    {
        "name": "RSS News Feed",
        "url": "Various Chinese news RSS feeds",
        "download_url": None,
        "license": "Various (check per feed)",
        "content_type": "reading_passages",
        "description": "Chinese news articles for reading practice",
        "estimated_items": 1000,
        "ingestion_command": "python scripts/ingest_news.py <rss_url>",
        "source_key": "rss",
    },
    {
        "name": "HSK Word Lists",
        "url": "https://www.chinesetest.cn/",
        "download_url": None,
        "license": "Public standard (HSK 3.0)",
        "content_type": "vocabulary",
        "description": "Official HSK 1-9 vocabulary (seeded at system init)",
        "estimated_items": 11000,
        "ingestion_command": "(built-in seed data)",
        "source_key": "seed",
    },
]


def get_source_status(conn) -> dict:
    """Query the DB for current ingestion counts per source.

    Returns dict of {source_key: {count, has_audio}}.
    """
    status = {}

    # CC-CEDICT dictionary entries
    try:
        row = conn.execute("SELECT COUNT(*) FROM dictionary_entry").fetchone()
        status["cedict"] = {"count": row[0] if row else 0, "table": "dictionary_entry"}
    except sqlite3.OperationalError:
        status["cedict"] = {"count": 0, "table": "dictionary_entry", "note": "table not created"}

    # Tatoeba sentences
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE source = 'tatoeba'"
        ).fetchone()
        status["tatoeba"] = {"count": row[0] if row else 0, "table": "content_item"}
    except sqlite3.OperationalError:
        status["tatoeba"] = {"count": 0}

    # Subtitle dialogues
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM dialogue_scenario WHERE scenario_type = 'subtitle'"
        ).fetchone()
        status["subtitle"] = {"count": row[0] if row else 0, "table": "dialogue_scenario"}
    except sqlite3.OperationalError:
        status["subtitle"] = {"count": 0}

    # RSS news articles
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE source LIKE 'rss:%'"
        ).fetchone()
        status["rss"] = {"count": row[0] if row else 0, "table": "content_item"}
    except sqlite3.OperationalError:
        status["rss"] = {"count": 0}

    # Audio coverage (Forvo + Wikimedia)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE audio_available = 1"
        ).fetchone()
        audio_count = row[0] if row else 0

        forvo_row = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE audio_file_path LIKE '%forvo%'"
        ).fetchone()
        wikimedia_row = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE audio_file_path LIKE '%wikimedia%'"
        ).fetchone()

        status["forvo"] = {
            "count": forvo_row[0] if forvo_row else 0,
            "table": "content_item (audio_file_path)",
        }
        status["wikimedia"] = {
            "count": wikimedia_row[0] if wikimedia_row else 0,
            "table": "content_item (audio_file_path)",
        }
        status["_audio_total"] = audio_count
    except sqlite3.OperationalError:
        status["forvo"] = {"count": 0}
        status["wikimedia"] = {"count": 0}

    # Seed data
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE source IS NULL OR source = ''"
        ).fetchone()
        total_row = conn.execute("SELECT COUNT(*) FROM content_item").fetchone()
        status["seed"] = {
            "count": total_row[0] if total_row else 0,
            "table": "content_item (total)",
        }
    except sqlite3.OperationalError:
        status["seed"] = {"count": 0}

    return status


def print_sources(sources: list, status: dict = None, as_json: bool = False):
    """Display the content source manifest."""
    if as_json:
        output = []
        for src in sources:
            entry = dict(src)
            if status and src["source_key"] in status:
                entry["status"] = status[src["source_key"]]
            output.append(entry)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    print("\n=== Open-Source Chinese Learning Content Sources ===\n")

    for src in sources:
        key = src["source_key"]
        count_str = ""
        if status and key in status:
            s = status[key]
            count_str = f"  [{s['count']:,} ingested]"

        print(f"  {src['name']}{count_str}")
        print(f"    License:     {src['license']}")
        print(f"    Type:        {src['content_type']}")
        print(f"    Est. items:  ~{src['estimated_items']:,}")
        print(f"    URL:         {src['url']}")
        print(f"    Ingest:      {src['ingestion_command']}")
        print()

    if status:
        audio_total = status.get("_audio_total", 0)
        print(f"  Audio coverage: {audio_total} items with audio")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="List and track open-source Chinese content sources"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Query DB for current ingestion counts",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="(No-op for this script; included for consistency)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    status = None
    if args.status:
        from mandarin import db
        try:
            with db.connection() as conn:
                status = get_source_status(conn)
        except Exception as e:
            logger.warning("Could not read DB status: %s", e)

    print_sources(SOURCES, status=status, as_json=args.json)


if __name__ == "__main__":
    main()
