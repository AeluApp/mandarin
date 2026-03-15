#!/usr/bin/env python3
"""Build passage_vocab_map — maps which content_item vocab words appear in each passage.

Uses jieba to segment passage text_zh, then matches tokens against content_item.hanzi.
Stores results in passage_vocab_map table for the session planner to join against.

Usage:
    python scripts/build_passage_vocab_index.py          # full rebuild
    python scripts/build_passage_vocab_index.py --dry-run # show stats only
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _tokenize_chinese(text: str) -> list[str]:
    """Segment Chinese text into words via jieba."""
    import jieba
    return list(jieba.cut(text))


def _load_passages(path: Path) -> list[dict]:
    """Load reading passages from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("passages", data) if isinstance(data, dict) else data


def _load_content_items(conn: sqlite3.Connection) -> dict[str, int]:
    """Build hanzi → content_item_id lookup. Multi-char words first for greedy matching."""
    rows = conn.execute(
        "SELECT id, hanzi FROM content_item WHERE status = 'drill_ready'"
    ).fetchall()
    # If multiple items share the same hanzi, keep the first (lowest id)
    lookup: dict[str, int] = {}
    for row in rows:
        hanzi = row[0] if isinstance(row, (list, tuple)) else row["hanzi"]
        item_id = row[1] if isinstance(row, (list, tuple)) else row["id"]
        # Wait — row is (id, hanzi), so:
        item_id = row[0] if isinstance(row, (list, tuple)) else row["id"]
        hanzi = row[1] if isinstance(row, (list, tuple)) else row["hanzi"]
        if hanzi not in lookup:
            lookup[hanzi] = item_id
    return lookup


def build_index(
    passages_path: Path,
    db_path: Path,
    dry_run: bool = False,
) -> dict:
    """Build the passage-vocab index.

    Returns stats dict with counts.
    """
    logger.info("Loading passages from %s", passages_path)
    passages = _load_passages(passages_path)
    logger.info("  %d passages loaded", len(passages))

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    logger.info("Loading content items from %s", db_path)
    hanzi_to_id = _load_content_items(conn)
    logger.info("  %d unique hanzi in content_item", len(hanzi_to_id))

    # Pre-warm jieba
    logger.info("Warming jieba segmenter...")
    _tokenize_chinese("测试")

    total_mappings = 0
    passages_with_vocab = 0
    rows_to_insert: list[tuple] = []

    t0 = time.monotonic()
    for i, passage in enumerate(passages):
        pid = passage.get("id", str(i))
        text_zh = passage.get("text_zh", "")
        if not text_zh:
            continue

        # Segment and count tokens
        tokens = _tokenize_chinese(text_zh)
        token_counts = Counter(tokens)

        # Match against content items
        passage_matches: dict[int, tuple[str, int]] = {}  # item_id → (hanzi, count)
        for token, count in token_counts.items():
            if token in hanzi_to_id:
                item_id = hanzi_to_id[token]
                if item_id not in passage_matches:
                    passage_matches[item_id] = (token, count)
                else:
                    # Same item_id matched by different token — keep higher count
                    existing = passage_matches[item_id]
                    if count > existing[1]:
                        passage_matches[item_id] = (token, count)

        if passage_matches:
            passages_with_vocab += 1
            for item_id, (hanzi, count) in passage_matches.items():
                rows_to_insert.append((str(pid), item_id, hanzi, count))
            total_mappings += len(passage_matches)

        if (i + 1) % 200 == 0:
            logger.info("  processed %d/%d passages...", i + 1, len(passages))

    elapsed = time.monotonic() - t0
    stats = {
        "passages_total": len(passages),
        "passages_with_vocab": passages_with_vocab,
        "total_mappings": total_mappings,
        "avg_vocab_per_passage": round(total_mappings / max(passages_with_vocab, 1), 1),
        "build_time_s": round(elapsed, 1),
    }

    logger.info("\n── Index Stats ──")
    for k, v in stats.items():
        logger.info("  %s: %s", k, v)

    if dry_run:
        logger.info("\nDry run — no database changes.")
        conn.close()
        return stats

    # Write to DB
    logger.info("\nWriting %d rows to passage_vocab_map...", len(rows_to_insert))

    # Create table if not exists
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS passage_vocab_map (
            passage_id TEXT NOT NULL,
            content_item_id INTEGER NOT NULL,
            hanzi TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (passage_id, content_item_id),
            FOREIGN KEY (content_item_id) REFERENCES content_item(id)
        );
        CREATE INDEX IF NOT EXISTS idx_pvm_content_item ON passage_vocab_map(content_item_id);
        CREATE INDEX IF NOT EXISTS idx_pvm_hanzi ON passage_vocab_map(hanzi);
    """)

    # Clear existing data and insert fresh
    conn.execute("DELETE FROM passage_vocab_map")
    conn.executemany(
        "INSERT OR REPLACE INTO passage_vocab_map (passage_id, content_item_id, hanzi, occurrence_count) VALUES (?, ?, ?, ?)",
        rows_to_insert,
    )
    conn.commit()

    # Verify
    count = conn.execute("SELECT COUNT(*) FROM passage_vocab_map").fetchone()[0]
    logger.info("  Verified: %d rows in passage_vocab_map", count)

    conn.close()
    return stats


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    passages_path = ROOT / "data" / "reading_passages.json"
    db_path = ROOT / "data" / "mandarin.db"

    if not passages_path.exists():
        logger.error("Passages file not found: %s", passages_path)
        sys.exit(1)
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    build_index(passages_path, db_path, dry_run=dry_run)
