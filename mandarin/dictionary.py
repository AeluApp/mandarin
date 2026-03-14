"""CC-CEDICT dictionary integration.

Parses CC-CEDICT format files and provides lookup by hanzi, pinyin, or English.
The dictionary is loaded from data/cedict.txt if present, or from the
dictionary_entry table in SQLite (populated via load_cedict_to_db).

CC-CEDICT format (one entry per line):
    Traditional Simplified [pin yin] /English def 1/English def 2/

Lines starting with # are comments.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional

from .settings import DATA_DIR

logger = logging.getLogger(__name__)

CEDICT_PATH = DATA_DIR / "cedict.txt"

# Regex to parse CC-CEDICT lines
_CEDICT_RE = re.compile(
    r'^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$'
)


def parse_cedict_line(line: str) -> Optional[dict]:
    """Parse a single CC-CEDICT line into a dict.

    Returns None for comment lines or unparseable lines.
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    m = _CEDICT_RE.match(line)
    if not m:
        return None
    return {
        "traditional": m.group(1),
        "simplified": m.group(2),
        "pinyin": m.group(3),
        "english": m.group(4),
    }


def load_cedict_file(path: Optional[Path] = None) -> list[dict]:
    """Load and parse a CC-CEDICT file. Returns list of entry dicts."""
    path = path or CEDICT_PATH
    if not path.exists():
        logger.info("CC-CEDICT file not found at %s", path)
        return []

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            entry = parse_cedict_line(line)
            if entry:
                entries.append(entry)
    logger.info("Loaded %d CC-CEDICT entries from %s", len(entries), path)
    return entries


def load_cedict_to_db(conn: sqlite3.Connection, path: Optional[Path] = None) -> int:
    """Load CC-CEDICT entries into the dictionary_entry table.

    Returns the number of entries inserted. Skips entries already present
    (matched by simplified + pinyin).
    """
    entries = load_cedict_file(path)
    if not entries:
        return 0

    inserted = 0
    for entry in entries:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO dictionary_entry
                   (traditional, simplified, pinyin, english)
                   VALUES (?, ?, ?, ?)""",
                (entry["traditional"], entry["simplified"],
                 entry["pinyin"], entry["english"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    logger.info("Inserted %d dictionary entries into DB", inserted)
    return inserted


def lookup(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """Look up dictionary entries matching hanzi, pinyin, or English.

    Searches the dictionary_entry table. Falls back to in-memory file
    parsing if the table is empty and cedict.txt exists.

    Returns list of dicts with keys: traditional, simplified, pinyin, english.
    """
    query = query.strip()
    if not query:
        return []

    # Try DB first
    results = _lookup_db(conn, query, limit)
    if results:
        return results

    # Fall back to file-based lookup if DB is empty
    count = conn.execute("SELECT COUNT(*) FROM dictionary_entry").fetchone()[0]
    if count == 0:
        return _lookup_file(query, limit)

    return []


def _lookup_db(conn: sqlite3.Connection, query: str, limit: int) -> list[dict]:
    """Search dictionary_entry table for matches."""
    results = []

    # Exact hanzi match (simplified or traditional)
    rows = conn.execute(
        """SELECT traditional, simplified, pinyin, english, frequency_rank
           FROM dictionary_entry
           WHERE simplified = ? OR traditional = ?
           ORDER BY frequency_rank ASC NULLS LAST
           LIMIT ?""",
        (query, query, limit),
    ).fetchall()
    for r in rows:
        results.append({
            "traditional": r["traditional"],
            "simplified": r["simplified"],
            "pinyin": r["pinyin"],
            "english": r["english"],
        })

    if results:
        return results[:limit]

    # Pinyin match (case-insensitive)
    rows = conn.execute(
        """SELECT traditional, simplified, pinyin, english, frequency_rank
           FROM dictionary_entry
           WHERE LOWER(pinyin) = LOWER(?)
           ORDER BY frequency_rank ASC NULLS LAST
           LIMIT ?""",
        (query, limit),
    ).fetchall()
    for r in rows:
        results.append({
            "traditional": r["traditional"],
            "simplified": r["simplified"],
            "pinyin": r["pinyin"],
            "english": r["english"],
        })

    if results:
        return results[:limit]

    # English substring match
    rows = conn.execute(
        """SELECT traditional, simplified, pinyin, english, frequency_rank
           FROM dictionary_entry
           WHERE LOWER(english) LIKE ?
           ORDER BY frequency_rank ASC NULLS LAST
           LIMIT ?""",
        (f"%{query.lower()}%", limit),
    ).fetchall()
    for r in rows:
        results.append({
            "traditional": r["traditional"],
            "simplified": r["simplified"],
            "pinyin": r["pinyin"],
            "english": r["english"],
        })

    return results[:limit]


def _lookup_file(query: str, limit: int) -> list[dict]:
    """Search CC-CEDICT file directly (fallback when DB is empty)."""
    entries = load_cedict_file()
    if not entries:
        return []

    query_lower = query.lower()
    results = []

    # Exact hanzi match first
    for e in entries:
        if e["simplified"] == query or e["traditional"] == query:
            results.append(e)

    if results:
        return results[:limit]

    # Pinyin match
    for e in entries:
        if e["pinyin"].lower() == query_lower:
            results.append(e)

    if results:
        return results[:limit]

    # English substring match
    for e in entries:
        if query_lower in e["english"].lower():
            results.append(e)
            if len(results) >= limit:
                break

    return results[:limit]


def find_example_sentences(
    conn: sqlite3.Connection, hanzi: str, limit: int = 3
) -> list[dict]:
    """Find example sentences containing the given hanzi.

    Searches content_item (sentences, phrases) and reading passage text
    for occurrences of the word.

    Returns list of dicts with keys: source, hanzi, pinyin, english.
    """
    examples = []

    # Search content_item for sentences/phrases containing the hanzi
    try:
        rows = conn.execute(
            """SELECT hanzi, pinyin, english, item_type
               FROM content_item
               WHERE hanzi LIKE ? AND item_type IN ('sentence', 'phrase')
               AND status = 'drill_ready'
               LIMIT ?""",
            (f"%{hanzi}%", limit),
        ).fetchall()
        for r in rows:
            examples.append({
                "source": "content_library",
                "hanzi": r["hanzi"],
                "pinyin": r["pinyin"],
                "english": r["english"],
                "type": r["item_type"],
            })
    except sqlite3.OperationalError:
        pass

    remaining = limit - len(examples)
    if remaining <= 0:
        return examples[:limit]

    # Search content_item context_note for sentences containing the hanzi
    try:
        rows = conn.execute(
            """SELECT hanzi, pinyin, english, context_note
               FROM content_item
               WHERE context_note LIKE ? AND context_note IS NOT NULL
               AND status = 'drill_ready'
               LIMIT ?""",
            (f"%{hanzi}%", remaining),
        ).fetchall()
        for r in rows:
            if r["context_note"] and hanzi in (r["context_note"] or ""):
                examples.append({
                    "source": "context_note",
                    "hanzi": r["hanzi"],
                    "pinyin": r["pinyin"],
                    "english": r["english"],
                    "context": r["context_note"],
                })
    except sqlite3.OperationalError:
        pass

    return examples[:limit]
