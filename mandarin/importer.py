"""Content importer — CSV, SRT subtitle, HSK level, and manual addition.

Supports:
- Quizlet CSV (term, definition columns)
- Generic CSV (hanzi, pinyin, english columns)
- SRT/VTT subtitle files → sentence extraction
- HSK level JSON files
- Manual single-item addition
"""

import csv
import json
import logging
import re
import io
import sqlite3
from pathlib import Path

from mandarin._paths import DATA_DIR

logger = logging.getLogger(__name__)
from typing import List, Optional, Tuple

from . import db


# ── CSV Import ──────────────────────────────

def import_csv(conn, file_path: str, *,
               hsk_level: int = None,
               register: str = "neutral",
               content_lens: str = None,
               source_name: str = None) -> tuple[int, int]:
    """Import vocabulary from a CSV file.

    Supports two formats:
    1. Quizlet: two columns (term, definition) — auto-detects pinyin in parens
    2. Full: columns named hanzi, pinyin, english (header row)

    Returns (items_added, items_skipped).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    return import_csv_text(conn, text,
                           hsk_level=hsk_level,
                           register=register,
                           content_lens=content_lens,
                           source_name=source_name or path.name)


def import_csv_text(conn, text: str, *,
                    hsk_level: int = None,
                    register: str = "neutral",
                    content_lens: str = None,
                    source_name: str = "csv_import") -> tuple[int, int]:
    """Import vocabulary from CSV text content.

    Runs the entire import inside one transaction — rolls back on error
    so no partial data is committed.

    Returns (items_added, items_skipped).
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return 0, 0

    # Detect format from header or first row
    header = [h.strip().lower() for h in rows[0]]
    has_header = any(h in header for h in ["hanzi", "pinyin", "english", "term", "definition"])

    if has_header:
        data_rows = rows[1:]
        col_map = _detect_columns(header)
    else:
        data_rows = rows
        col_map = None

    try:
        # Record source
        source_id = _record_source(conn, "quizlet", source_name,
                                   register=register, content_lens=content_lens)

        # Pre-fetch existing hanzi for bulk dedup
        existing = {}
        for row in conn.execute(
            "SELECT id, hanzi, pinyin, english FROM content_item"
        ).fetchall():
            existing[row["hanzi"]] = row

        added = 0
        skipped = 0

        for row in data_rows:
            if not row or all(not cell.strip() for cell in row):
                continue

            try:
                if col_map:
                    item = _extract_from_mapped(row, col_map)
                else:
                    item = _extract_from_two_col(row)

                if not item:
                    skipped += 1
                    continue

                hanzi, pinyin, english = item

                # Check for existing item with same hanzi (in-memory lookup)
                exists = existing.get(hanzi)
                if exists:
                    # If existing item has empty fields and import has data, update it
                    ex_pinyin = (exists["pinyin"] or "").strip()
                    ex_english = (exists["english"] or "").strip()
                    if (not ex_pinyin and pinyin) or (not ex_english and english):
                        updates = {}
                        if not ex_pinyin and pinyin:
                            updates["pinyin"] = pinyin
                        if not ex_english and english:
                            updates["english"] = english
                        # Safe: keys are from hardcoded "pinyin"/"english" checks above
                        set_clause = ", ".join(f"{k} = ?" for k in updates)
                        vals = list(updates.values()) + [exists["id"]]
                        conn.execute(f"UPDATE content_item SET {set_clause} WHERE id = ?", vals)
                        # Promote status if now complete
                        if (pinyin or ex_pinyin) and (english or ex_english):
                            conn.execute(
                                "UPDATE content_item SET status = 'drill_ready' WHERE id = ?",
                                (exists["id"],)
                            )
                        added += 1
                    else:
                        skipped += 1
                    continue

                db.insert_content_item(
                    conn,
                    hanzi=hanzi,
                    pinyin=pinyin,
                    english=english,
                    hsk_level=hsk_level,
                    register=register,
                    content_lens=content_lens,
                    source=f"csv:{source_name}",
                )
                # Track newly inserted hanzi so later rows dedup against it
                existing[hanzi] = {"id": None, "hanzi": hanzi, "pinyin": pinyin, "english": english}
                added += 1

            except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
                logger.debug("import skipped item %r: %s", row, e)
                skipped += 1

        # Update source stats
        if source_id:
            conn.execute(
                "UPDATE content_source SET items_extracted = ? WHERE id = ?",
                (added, source_id)
            )

        conn.commit()
        return added, skipped

    except Exception:
        conn.rollback()
        raise


def _detect_columns(header: list) -> dict:
    """Map header names to column indices."""
    col_map = {}
    for i, h in enumerate(header):
        if h in ("hanzi", "chinese", "term", "character"):
            col_map["hanzi"] = i
        elif h in ("pinyin", "pronunciation"):
            col_map["pinyin"] = i
        elif h in ("english", "definition", "meaning", "translation"):
            col_map["english"] = i
    return col_map if "hanzi" in col_map or "english" in col_map else None


def _extract_from_mapped(row: list, col_map: dict) -> tuple[str, str, str] | None:
    """Extract hanzi, pinyin, english from a row with known columns."""
    hanzi = row[col_map["hanzi"]].strip() if "hanzi" in col_map and col_map["hanzi"] < len(row) else ""
    pinyin = row[col_map.get("pinyin", -1)].strip() if "pinyin" in col_map and col_map["pinyin"] < len(row) else ""
    english = row[col_map["english"]].strip() if "english" in col_map and col_map["english"] < len(row) else ""

    if not hanzi and not english:
        return None
    return hanzi, pinyin, english


def _extract_from_two_col(row: list) -> tuple[str, str, str] | None:
    """Extract from Quizlet two-column format (term, definition).

    Quizlet format: "八(bā)" or "八 (bā)" in term, "eight" in definition.
    Or: "八" in term, "eight" in definition (no pinyin).
    """
    if len(row) < 2:
        return None

    term = row[0].strip()
    definition = row[1].strip()

    if not term or not definition:
        return None

    # Try to extract pinyin from parentheses in term
    match = re.match(r'^(.+?)\s*[（(](.+?)[)）]\s*$', term)
    if match:
        hanzi = match.group(1).strip()
        pinyin = match.group(2).strip()
    else:
        # Check if definition has pinyin in parens
        match2 = re.match(r'^(.+?)\s*[（(](.+?)[)）]\s*$', definition)
        if match2:
            hanzi = term
            english = match2.group(1).strip()
            pinyin = match2.group(2).strip()
            return hanzi, pinyin, english
        else:
            hanzi = term
            pinyin = ""

    return hanzi, pinyin, definition


# ── SRT Subtitle Import ──────────────────────────────

def import_srt(conn, file_path: str, *,
               register: str = "mixed",
               content_lens: str = None,
               source_name: str = None,
               min_chars: int = 2,
               max_chars: int = 40) -> tuple[int, int]:
    """Import sentences from an SRT subtitle file.

    Extracts Chinese text lines, deduplicates, and imports as sentence items.
    Returns (items_added, items_skipped).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    source_name = source_name or path.name

    # Parse SRT
    sentences = _parse_srt(text, min_chars=min_chars, max_chars=max_chars)

    if not sentences:
        return 0, 0

    try:
        # Record source
        source_id = _record_source(conn, "subtitle", source_name,
                                   register=register, content_lens=content_lens)

        # Pre-fetch existing hanzi for bulk dedup
        existing_hanzi = {
            r["hanzi"] for r in conn.execute("SELECT hanzi FROM content_item").fetchall()
        }

        added = 0
        skipped = 0

        for hanzi in sentences:
            if hanzi in existing_hanzi:
                skipped += 1
                continue

            item_id = db.insert_content_item(
                conn,
                hanzi=hanzi,
                pinyin="",  # Pinyin not available from subtitles
                english="",  # Translation not available
                item_type="sentence",
                register=register,
                content_lens=content_lens,
                source=f"subtitle:{source_name}",
                difficulty=_estimate_sentence_difficulty(hanzi),
            )
            # SRT imports lack pinyin/english — mark as raw
            conn.execute("UPDATE content_item SET status = 'raw' WHERE id = ?", (item_id,))
            existing_hanzi.add(hanzi)
            added += 1

        if source_id:
            conn.execute(
                "UPDATE content_source SET items_extracted = ? WHERE id = ?",
                (added, source_id)
            )

        conn.commit()
        return added, skipped

    except Exception:
        conn.rollback()
        raise


def _parse_srt(text: str, min_chars: int = 2, max_chars: int = 40) -> list[str]:
    """Parse SRT text and extract unique Chinese sentences."""
    # Remove SRT timing lines and sequence numbers
    lines = text.split("\n")
    chinese_lines = []

    for line in lines:
        line = line.strip()
        # Skip empty lines, sequence numbers, and timing lines
        if not line:
            continue
        if re.match(r'^\d+$', line):
            continue
        if re.match(r'\d{2}:\d{2}:\d{2}', line):
            continue
        if '-->' in line:
            continue

        # Remove HTML tags
        line = re.sub(r'<[^>]+>', '', line)
        # Remove VTT positioning
        line = re.sub(r'align:.*|position:.*|size:.*', '', line).strip()

        # Check if line contains Chinese characters
        if re.search(r'[\u4e00-\u9fff]', line):
            # Clean up
            clean = line.strip()
            if min_chars <= len(clean) <= max_chars:
                chinese_lines.append(clean)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for line in chinese_lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)

    return unique


def _estimate_sentence_difficulty(hanzi: str) -> float:
    """Rough difficulty estimate based on sentence length."""
    length = len(hanzi)
    if length <= 4:
        return 0.3
    elif length <= 8:
        return 0.4
    elif length <= 15:
        return 0.5
    elif length <= 25:
        return 0.7
    else:
        return 0.8


# ── HSK Level Import ──────────────────────────────

def _validate_content_row(hanzi: str, pinyin: str, english: str,
                          hsk_level: int = None) -> str | None:
    """Validate a content item before import.

    Returns an error message string if invalid, None if valid.
    """
    if not hanzi or not hanzi.strip():
        return "empty hanzi"
    if hsk_level is not None and not (1 <= hsk_level <= 9):
        return f"hsk_level {hsk_level} out of range (1-9)"
    # Hanzi should contain at least one CJK character for drill_ready items
    if pinyin and english and not re.search(r'[\u4e00-\u9fff]', hanzi):
        return f"hanzi '{hanzi}' contains no Chinese characters"
    return None


def import_hsk_level(conn, level: int, dry_run: bool = False) -> tuple[int, int]:
    """Import vocabulary from an HSK level JSON file.

    Reads data/hsk/hskN.json, inserts items with hsk_level=N, source="hskN",
    status="drill_ready". Skips existing hanzi.

    Returns (items_added, items_skipped).
    """
    if not (1 <= level <= 9):
        raise ValueError(f"HSK level must be 1-9, got {level}")

    hsk_file = DATA_DIR / "hsk" / f"hsk{level}.json"
    if not hsk_file.exists():
        raise FileNotFoundError(f"HSK {level} data file not found: {hsk_file}")

    data = json.loads(hsk_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError(f"HSK {level} file must contain an 'items' array")
    items = data.get("items", [])

    added = 0
    skipped = 0

    for item in items:
        hanzi = item.get("hanzi", "").strip()
        pinyin = item.get("pinyin", "").strip()
        english = item.get("english", "").strip()

        error = _validate_content_row(hanzi, pinyin, english, hsk_level=level)
        if error:
            skipped += 1
            continue

        # Check for existing item with same hanzi
        exists = conn.execute(
            "SELECT id FROM content_item WHERE hanzi = ?", (hanzi,)
        ).fetchone()
        if exists:
            skipped += 1
            continue

        if dry_run:
            added += 1
            continue

        db.insert_content_item(
            conn,
            hanzi=hanzi,
            pinyin=pinyin,
            english=english,
            hsk_level=level,
            source=f"hsk{level}",
            status="drill_ready",
        )
        added += 1

    if not dry_run:
        conn.commit()

    return added, skipped


# ── Manual Addition ──────────────────────────────

def add_item(conn, hanzi: str, pinyin: str, english: str, *,
             item_type: str = "vocab",
             hsk_level: int = None,
             register: str = "neutral",
             content_lens: str = None) -> int | None:
    """Add a single content item manually.

    Returns the item ID, or None if it's a duplicate.
    Raises ValueError if inputs are invalid.
    """
    error = _validate_content_row(hanzi, pinyin, english, hsk_level=hsk_level)
    if error:
        raise ValueError(f"Invalid content item: {error}")

    exists = conn.execute(
        "SELECT id FROM content_item WHERE hanzi = ?", (hanzi,)
    ).fetchone()
    if exists:
        return None

    item_id = db.insert_content_item(
        conn,
        hanzi=hanzi,
        pinyin=pinyin,
        english=english,
        item_type=item_type,
        hsk_level=hsk_level,
        register=register,
        content_lens=content_lens,
        source="manual",
    )
    conn.commit()
    return item_id


# ── Content lens auto-tagging ──────────────────────────────

# Keywords that suggest a content lens for vocabulary items
LENS_KEYWORDS = {
    "urban_texture": [
        "city", "street", "shop", "store", "restaurant", "hotel", "taxi",
        "bus", "station", "airport", "road", "room", "door", "table", "chair",
        "desk", "building", "hospital", "school", "classroom", "company",
    ],
    "food_social": [
        "eat", "drink", "tea", "coffee", "rice", "fruit", "vegetable",
        "egg", "fish", "meat", "mutton", "apple", "watermelon", "milk",
        "delicious", "dish", "cook",
    ],
    "identity": [
        "name", "surname", "father", "mother", "son", "daughter", "brother",
        "sister", "friend", "child", "husband", "wife", "family", "home",
        "Mr.", "Miss", "doctor", "teacher", "student", "waiter",
    ],
    "time_sequence": [
        "today", "tomorrow", "yesterday", "morning", "afternoon", "evening",
        "noon", "o'clock", "minute", "hour", "week", "month", "year",
        "birthday", "now", "time", "moment",
    ],
    "numbers_measure": [
        "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "zero", "hundred", "thousand", "measure word",
        "how many", "how much",
    ],
    "function_words": [
        "particle", "not", "question", "marker", "aspect", "complement",
        "also", "very", "all", "still", "already", "again",
    ],
}


def auto_tag_lens(conn, dry_run: bool = False) -> dict:
    """Auto-tag content items with content lenses based on English definitions.

    Returns dict of {lens: count_tagged}.
    """
    items = conn.execute(
        "SELECT id, english, content_lens FROM content_item WHERE content_lens IS NULL"
    ).fetchall()

    counts = {}
    for item in items:
        english = (item["english"] or "").lower()
        best_lens = None
        best_score = 0

        for lens, keywords in LENS_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in english)
            if score > best_score:
                best_score = score
                best_lens = lens

        if best_lens and best_score > 0:
            if not dry_run:
                conn.execute(
                    "UPDATE content_item SET content_lens = ? WHERE id = ?",
                    (best_lens, item["id"])
                )
            counts[best_lens] = counts.get(best_lens, 0) + 1

    if not dry_run:
        conn.commit()
    return counts


# ── Helpers ──────────────────────────────

def _record_source(conn, source_type: str, name: str, *,
                   register: str = None,
                   content_lens: str = None,
                   url: str = None,
                   file_path: str = None) -> int | None:
    """Record a content source in the database."""
    try:
        cur = conn.execute("""
            INSERT INTO content_source (source_type, name, url, file_path, register, content_lens)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (source_type, name, url, file_path, register, content_lens))
        return cur.lastrowid
    except sqlite3.Error as e:
        logger.debug("content source insert failed: %s", e)
        return None
