"""HSK vocabulary validator — deterministic, offline comparison.

Compares the canonical HSK word lists (data/hsk/hsk{1-9}.json) against
what's actually in the database. Produces a structured diff report:
missing items, extra items, level mismatches.

Runs without network access. All comparisons use the frozen JSON files
as source of truth.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import db
from mandarin._paths import DATA_DIR

HSK_DATA_DIR = DATA_DIR / "hsk"


def _load_canonical(level: int) -> list[dict]:
    """Load the canonical word list for one HSK level."""
    path = HSK_DATA_DIR / f"hsk{level}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", [])


def validate_level(conn, level: int) -> dict:
    """Validate DB content against canonical list for one HSK level.

    Returns:
        {
            "level": int,
            "canonical_count": int,
            "db_count": int,
            "missing": [{"hanzi": ..., "pinyin": ..., "english": ...}],
            "extra": [{"hanzi": ..., "pinyin": ..., "english": ...}],
            "level_mismatch": [{"hanzi": ..., "canonical_level": int, "db_level": int}],
            "coverage_pct": float,
        }
    """
    canonical = _load_canonical(level)
    if not canonical:
        return {
            "level": level,
            "canonical_count": 0,
            "db_count": 0,
            "missing": [],
            "extra": [],
            "level_mismatch": [],
            "coverage_pct": 0.0,
            "error": f"No canonical data file for HSK {level}",
        }

    canonical_hanzi = {item["hanzi"] for item in canonical}
    canonical_by_hanzi = {item["hanzi"]: item for item in canonical}

    # Get all DB items tagged with this HSK level
    db_rows = conn.execute(
        "SELECT hanzi, pinyin, english, hsk_level FROM content_item WHERE hsk_level = ?",
        (level,)
    ).fetchall()
    db_hanzi = {row["hanzi"] for row in db_rows}

    # Also check for items that exist in DB at a different level
    # SECURITY: This format() call only generates "?,?,?" placeholders —
    # no user input is interpolated into the SQL string. Actual values are
    # passed via parameterized query (the list(canonical_hanzi) argument).
    all_db_rows = conn.execute(
        "SELECT hanzi, hsk_level FROM content_item WHERE hanzi IN ({})".format(
            ",".join("?" * len(canonical_hanzi))
        ),
        list(canonical_hanzi)
    ).fetchall() if canonical_hanzi else []

    db_level_map = {}
    for row in all_db_rows:
        db_level_map[row["hanzi"]] = row["hsk_level"]

    # Missing: in canonical but not in DB at all
    missing = []
    for hanzi in sorted(canonical_hanzi - set(db_level_map.keys())):
        item = canonical_by_hanzi[hanzi]
        missing.append({
            "hanzi": item["hanzi"],
            "pinyin": item.get("pinyin", ""),
            "english": item.get("english", "")[:60],
        })

    # Level mismatch: in DB but at wrong level
    level_mismatch = []
    for hanzi, db_lvl in sorted(db_level_map.items()):
        if db_lvl != level and hanzi in canonical_hanzi:
            level_mismatch.append({
                "hanzi": hanzi,
                "canonical_level": level,
                "db_level": db_lvl,
            })

    # Extra: in DB at this level but not in canonical for this level
    extra = []
    for row in db_rows:
        if row["hanzi"] not in canonical_hanzi:
            extra.append({
                "hanzi": row["hanzi"],
                "pinyin": row["pinyin"] or "",
                "english": (row["english"] or "")[:60],
            })

    found_count = len(canonical_hanzi) - len(missing)
    coverage = (found_count / len(canonical_hanzi) * 100) if canonical_hanzi else 0.0

    return {
        "level": level,
        "canonical_count": len(canonical_hanzi),
        "db_count": len(db_hanzi),
        "missing": missing,
        "extra": extra,
        "level_mismatch": level_mismatch,
        "coverage_pct": round(coverage, 1),
    }


def validate_all(conn, levels: list[int] | None = None) -> dict:
    """Validate all (or specified) HSK levels.

    Returns:
        {
            "levels": {1: {...}, 2: {...}, ...},
            "summary": {
                "total_canonical": int,
                "total_in_db": int,
                "total_missing": int,
                "total_extra": int,
                "total_mismatch": int,
                "overall_coverage_pct": float,
            }
        }
    """
    if levels is None:
        levels = list(range(1, 10))

    results = {}
    total_canonical = 0
    total_missing = 0
    total_extra = 0
    total_mismatch = 0

    for level in levels:
        result = validate_level(conn, level)
        results[level] = result
        total_canonical += result["canonical_count"]
        total_missing += len(result["missing"])
        total_extra += len(result["extra"])
        total_mismatch += len(result["level_mismatch"])

    total_in_db = total_canonical - total_missing
    overall_pct = (total_in_db / total_canonical * 100) if total_canonical > 0 else 0.0

    return {
        "levels": results,
        "summary": {
            "total_canonical": total_canonical,
            "total_in_db": total_in_db,
            "total_missing": total_missing,
            "total_extra": total_extra,
            "total_mismatch": total_mismatch,
            "overall_coverage_pct": round(overall_pct, 1),
        },
    }


def fix_levels(conn, levels: list[int] | None = None, dry_run: bool = False) -> dict:
    """Fix HSK level assignments in DB to match canonical data.

    For each canonical level, finds items in the DB with matching hanzi
    but wrong hsk_level, and corrects them.

    Returns {"fixed": int, "details": [{"hanzi": ..., "from": int, "to": int}]}
    """
    if levels is None:
        levels = list(range(1, 10))

    # Build canonical hanzi → level map (lowest level wins for items
    # appearing in multiple levels due to inclusive lists)
    canonical_map = {}
    for level in sorted(levels):
        for item in _load_canonical(level):
            hanzi = item["hanzi"]
            if hanzi not in canonical_map:
                canonical_map[hanzi] = level

    if not canonical_map:
        return {"fixed": 0, "details": []}

    # Find DB items with wrong levels
    placeholders = ",".join("?" * len(canonical_map))
    db_rows = conn.execute(
        f"SELECT id, hanzi, hsk_level FROM content_item WHERE hanzi IN ({placeholders})",
        list(canonical_map.keys())
    ).fetchall()

    details = []
    for row in db_rows:
        canonical_level = canonical_map.get(row["hanzi"])
        if canonical_level and row["hsk_level"] != canonical_level:
            details.append({
                "hanzi": row["hanzi"],
                "from": row["hsk_level"],
                "to": canonical_level,
            })
            if not dry_run:
                conn.execute(
                    "UPDATE content_item SET hsk_level = ? WHERE id = ?",
                    (canonical_level, row["id"])
                )

    if not dry_run and details:
        conn.commit()

    return {"fixed": len(details), "details": details}


def find_duplicates(conn) -> list[dict]:
    """Find content_item rows that share the same hanzi.

    Returns a list of dicts: {"hanzi": str, "count": int, "ids": [int, ...]}.
    Only returns hanzi values with count > 1.
    """
    rows = conn.execute(
        """SELECT hanzi, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
           FROM content_item
           GROUP BY hanzi
           HAVING cnt > 1
           ORDER BY cnt DESC"""
    ).fetchall()

    return [
        {
            "hanzi": r["hanzi"],
            "count": r["cnt"],
            "ids": [int(x) for x in r["ids"].split(",")],
        }
        for r in rows
    ]


def find_orphans(conn) -> dict:
    """Find orphaned records across content-related tables.

    Returns:
        {
            "orphan_progress": [{"id": int, "content_item_id": int}],
            "orphan_error_log": [{"id": int, "content_item_id": int}],
            "orphan_error_focus": [{"id": int, "content_item_id": int}],
            "stale_items": [{"id": int, "hanzi": str}],
        }

    orphan_progress / orphan_error_*: rows referencing a content_item_id
    that no longer exists in content_item.

    stale_items: content_items with status='raw' that have never been drilled
    (no row in progress and no row in error_log). These are safe to review
    for cleanup.
    """
    orphan_progress = conn.execute(
        """SELECT p.id, p.content_item_id
           FROM progress p
           LEFT JOIN content_item ci ON ci.id = p.content_item_id
           WHERE ci.id IS NULL"""
    ).fetchall()

    orphan_error_log = conn.execute(
        """SELECT el.id, el.content_item_id
           FROM error_log el
           LEFT JOIN content_item ci ON ci.id = el.content_item_id
           WHERE ci.id IS NULL"""
    ).fetchall()

    orphan_error_focus = conn.execute(
        """SELECT ef.id, ef.content_item_id
           FROM error_focus ef
           LEFT JOIN content_item ci ON ci.id = ef.content_item_id
           WHERE ci.id IS NULL"""
    ).fetchall()

    stale_items = conn.execute(
        """SELECT ci.id, ci.hanzi
           FROM content_item ci
           WHERE ci.status = 'raw'
             AND NOT EXISTS (SELECT 1 FROM progress p WHERE p.content_item_id = ci.id)
             AND NOT EXISTS (SELECT 1 FROM error_log el WHERE el.content_item_id = ci.id)"""
    ).fetchall()

    return {
        "orphan_progress": [{"id": r["id"], "content_item_id": r["content_item_id"]} for r in orphan_progress],
        "orphan_error_log": [{"id": r["id"], "content_item_id": r["content_item_id"]} for r in orphan_error_log],
        "orphan_error_focus": [{"id": r["id"], "content_item_id": r["content_item_id"]} for r in orphan_error_focus],
        "stale_items": [{"id": r["id"], "hanzi": r["hanzi"]} for r in stale_items],
    }
