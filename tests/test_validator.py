"""Tests for HSK vocabulary validator.

Tests verify:
- Canonical data loads correctly for levels with JSON files
- Missing/extra/mismatch detection works
- Coverage calculation is accurate
- validate_all aggregates correctly
"""

import sqlite3
from pathlib import Path

from mandarin.validator import _load_canonical, validate_level, validate_all


def _make_db():
    """Create an in-memory DB with content_item table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT DEFAULT '',
            english TEXT DEFAULT '',
            hsk_level INTEGER,
            status TEXT DEFAULT 'drill_ready'
        )
    """)
    conn.commit()
    return conn


# ---- TestLoadCanonical ----

def test_loads_hsk1():
    items = _load_canonical(1)
    assert len(items) > 400
    assert "hanzi" in items[0]
    assert "pinyin" in items[0]
    assert "english" in items[0]


def test_nonexistent_level_returns_empty():
    items = _load_canonical(99)
    assert items == []


def test_all_items_have_required_fields():
    for level in range(1, 10):
        items = _load_canonical(level)
        if not items:
            continue
        for item in items:
            assert "hanzi" in item, f"HSK {level} item missing hanzi"
            assert item["hanzi"].strip(), f"HSK {level} empty hanzi"


# ---- TestValidateLevel ----

def test_empty_db_all_missing():
    conn = _make_db()
    result = validate_level(conn, 1)
    assert result["level"] == 1
    assert result["canonical_count"] > 0
    assert result["db_count"] == 0
    assert len(result["missing"]) == result["canonical_count"]
    assert result["coverage_pct"] == 0.0
    conn.close()


def test_full_coverage():
    conn = _make_db()
    canonical = _load_canonical(1)
    for item in canonical:
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
            (item["hanzi"], item["pinyin"], item["english"], 1),
        )
    conn.commit()
    result = validate_level(conn, 1)
    assert result["coverage_pct"] == 100.0
    assert len(result["missing"]) == 0
    assert len(result["extra"]) == 0
    conn.close()


def test_detects_extra_items():
    conn = _make_db()
    # Add one canonical item + one extra
    canonical = _load_canonical(1)
    conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
        (canonical[0]["hanzi"], canonical[0]["pinyin"], canonical[0]["english"], 1),
    )
    conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
        ("\u6d4b\u8bd5\u8bcd", "c\u00e8 sh\u00ec c\u00ed", "test word", 1),
    )
    conn.commit()
    result = validate_level(conn, 1)
    assert len(result["extra"]) == 1
    assert result["extra"][0]["hanzi"] == "\u6d4b\u8bd5\u8bcd"
    conn.close()


def test_detects_level_mismatch():
    conn = _make_db()
    canonical = _load_canonical(1)
    # Add HSK 1 word but tagged as HSK 2
    conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
        (canonical[0]["hanzi"], canonical[0]["pinyin"], canonical[0]["english"], 2),
    )
    conn.commit()
    result = validate_level(conn, 1)
    assert len(result["level_mismatch"]) == 1
    assert result["level_mismatch"][0]["canonical_level"] == 1
    assert result["level_mismatch"][0]["db_level"] == 2
    conn.close()


def test_nonexistent_level():
    conn = _make_db()
    result = validate_level(conn, 99)
    assert "error" in result
    conn.close()


# ---- TestValidateAll ----

def test_validates_specified_levels():
    conn = _make_db()
    result = validate_all(conn, levels=[1, 2])
    assert 1 in result["levels"]
    assert 2 in result["levels"]
    assert 3 not in result["levels"]
    assert "summary" in result
    conn.close()


def test_summary_aggregates_correctly():
    conn = _make_db()
    result = validate_all(conn, levels=[1])
    summary = result["summary"]
    lvl1 = result["levels"][1]
    assert summary["total_canonical"] == lvl1["canonical_count"]
    assert summary["total_missing"] == len(lvl1["missing"])
    conn.close()


def test_coverage_percentage():
    conn = _make_db()
    # Add a few HSK 1 items
    canonical = _load_canonical(1)
    for item in canonical[:10]:
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
            (item["hanzi"], item["pinyin"], item["english"], 1),
        )
    conn.commit()
    result = validate_all(conn, levels=[1])
    # Should be about 10/506 ~ 2%
    assert result["summary"]["overall_coverage_pct"] > 1.0
    assert result["summary"]["overall_coverage_pct"] < 5.0
    conn.close()
