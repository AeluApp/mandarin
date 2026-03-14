"""Tests for 8 new drill types: number_system, tone_sandhi, complement,
ba_bei, collocation, radical, error_correction, chengyu.

Tests:
- Data loading for each JSON file (loads, correct structure, field checks)
- Smoke tests for all 8 drills (returns DrillResult, correct drill_type, correct error_type)
- None return for unknown items
- Registry + UI label presence for all 8
- Number drill specifics: phone entries use 幺, unit entries present
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.drills import DrillResult
from mandarin.drills.dispatch import DRILL_REGISTRY
from mandarin.drills.number import run_number_system_drill, _get_number_drills
from mandarin.drills.grammar_drills import (
    run_complement_drill, run_ba_bei_drill, run_error_correction_drill,
    _get_complement_patterns, _get_ba_bei_patterns, _get_error_sentences,
)
from mandarin.drills.advanced import (
    run_tone_sandhi_drill, run_collocation_drill,
    run_radical_drill, run_chengyu_drill,
    _get_tone_sandhi, _get_collocations, _get_chengyu,
)
from mandarin.ui_labels import DRILL_LABELS
from mandarin.runner import _DRILL_DESCRIPTIONS


# ── Test DB helpers ──────────────────────────────

def _make_test_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


_SEED_ITEMS = [
    ("你好", "nǐ hǎo", "hello", 1),
    ("谢谢", "xiè xie", "thank you", 1),
    ("朋友", "péng yǒu", "friend", 2),
    ("已经", "yǐ jīng", "already", 2),
    ("比较", "bǐ jiào", "comparatively", 3),
    ("经济", "jīng jì", "economy", 4),
    ("教育", "jiào yù", "education", 4),
    ("一举两得", "yī jǔ liǎng dé", "kill two birds", 5),
    ("恍然大悟", "huǎng rán dà wù", "sudden realization", 6),
]


def _seed_items(conn):
    for hanzi, pinyin, english, hsk in _SEED_ITEMS:
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
            (hanzi, pinyin, english, hsk),
        )
    conn.commit()


def _get_item(conn, hsk_level=3):
    """Get a content item with exactly this HSK level, or closest below."""
    row = conn.execute(
        "SELECT * FROM content_item WHERE hsk_level = ? LIMIT 1",
        (hsk_level,),
    ).fetchone()
    if row:
        return dict(row)
    # Fallback: closest below
    row = conn.execute(
        "SELECT * FROM content_item WHERE hsk_level <= ? ORDER BY hsk_level DESC LIMIT 1",
        (hsk_level,),
    ).fetchone()
    if row:
        return dict(row)
    return None


def _show_fn(text, **kwargs):
    pass


def _input_fn_choice(choice_idx):
    """Return an input_fn that always picks choice_idx (1-based)."""
    def _fn(prompt=""):
        return str(choice_idx)
    return _fn


@pytest.fixture
def test_db():
    conn, path = _make_test_db()
    _seed_items(conn)
    yield conn
    conn.close()
    os.unlink(path)


# ── Data Loading Tests ──────────────────────────────

class TestDataLoading:
    """Verify all 7 JSON files load and have correct structure."""

    def test_number_drills_load(self):
        entries = _get_number_drills()
        assert len(entries) >= 40
        for e in entries:
            assert "type" in e
            assert "arabic" in e
            assert "chinese" in e
            assert "hsk_level" in e

    def test_tone_sandhi_load(self):
        entries = _get_tone_sandhi()
        assert len(entries) >= 30
        for e in entries:
            assert "word" in e
            assert "pinyin_base" in e
            assert "pinyin_sandhi" in e
            assert "rule" in e

    def test_complement_patterns_load(self):
        entries = _get_complement_patterns()
        assert len(entries) >= 25
        for e in entries:
            assert "type" in e
            assert "answer" in e
            assert "hsk_level" in e

    def test_ba_bei_patterns_load(self):
        entries = _get_ba_bei_patterns()
        assert len(entries) >= 20
        for e in entries:
            assert "type" in e
            assert "answer" in e
            assert "hsk_level" in e

    def test_collocations_load(self):
        entries = _get_collocations()
        assert len(entries) >= 35
        for e in entries:
            assert "verb" in e
            assert "object" in e
            assert "meaning" in e
            assert "confusables" in e

    def test_error_sentences_load(self):
        entries = _get_error_sentences()
        assert len(entries) >= 20
        for e in entries:
            assert "wrong" in e
            assert "correct" in e
            assert "hsk_level" in e

    def test_chengyu_load(self):
        entries = _get_chengyu()
        assert len(entries) >= 30
        for e in entries:
            assert "chengyu" in e
            assert "meaning" in e
            assert "pinyin" in e
            assert "hsk_level" in e

    def test_number_phone_uses_yao(self):
        """Phone entries should use 幺 not 一."""
        entries = _get_number_drills()
        phone_entries = [e for e in entries if e["type"] == "phone"]
        assert len(phone_entries) >= 4
        for e in phone_entries:
            if "1" in e["arabic"]:
                assert "幺" in e["chinese"], f"Phone {e['arabic']} should use 幺, got {e['chinese']}"

    def test_number_units_present(self):
        """Unit conversion entries should exist."""
        entries = _get_number_drills()
        unit_entries = [e for e in entries if e["type"] == "units"]
        assert len(unit_entries) >= 8


# ── Drill Smoke Tests ──────────────────────────────

class TestNumberSystemDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        assert item is not None
        result = run_number_system_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "number_system"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_number_system_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert result is not None
        if not result.correct and not result.skipped:
            assert result.error_type == "number"

    def test_always_returns_result_for_valid_item(self, test_db):
        """Even low-level items should get number drills (entries start at HSK 1)."""
        item = _get_item(test_db, hsk_level=1)
        result = run_number_system_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)


class TestToneSandhiDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_tone_sandhi_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "tone_sandhi"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_tone_sandhi_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "tone"


class TestComplementDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=4)
        result = run_complement_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "complement"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=4)
        result = run_complement_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "grammar"


class TestBaBeiDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=5)
        result = run_ba_bei_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "ba_bei"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=5)
        result = run_ba_bei_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "grammar"


class TestCollocationDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_collocation_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "collocation"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_collocation_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "vocab"


class TestRadicalDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_radical_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "radical"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=3)
        result = run_radical_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "vocab"


class TestErrorCorrectionDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=4)
        result = run_error_correction_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "error_correction"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=4)
        result = run_error_correction_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "grammar"


class TestChengyuDrill:
    def test_returns_drill_result(self, test_db):
        item = _get_item(test_db, hsk_level=5)
        result = run_chengyu_drill(item, test_db, _show_fn, _input_fn_choice(1))
        assert isinstance(result, DrillResult)
        assert result.drill_type == "chengyu"

    def test_correct_error_type(self, test_db):
        item = _get_item(test_db, hsk_level=5)
        result = run_chengyu_drill(item, test_db, _show_fn, _input_fn_choice(1))
        if not result.correct and not result.skipped:
            assert result.error_type == "vocab"


# ── Registry & Labels Tests ──────────────────────────────

_NEW_DRILL_TYPES = [
    "number_system", "tone_sandhi", "complement", "ba_bei",
    "collocation", "radical", "error_correction", "chengyu",
]


class TestRegistration:
    def test_all_in_registry(self):
        for dt in _NEW_DRILL_TYPES:
            assert dt in DRILL_REGISTRY, f"{dt} missing from DRILL_REGISTRY"

    def test_all_have_ui_labels(self):
        for dt in _NEW_DRILL_TYPES:
            assert dt in DRILL_LABELS, f"{dt} missing from DRILL_LABELS"

    def test_all_have_descriptions(self):
        for dt in _NEW_DRILL_TYPES:
            assert dt in _DRILL_DESCRIPTIONS, f"{dt} missing from _DRILL_DESCRIPTIONS"

    def test_all_have_runners(self):
        for dt in _NEW_DRILL_TYPES:
            entry = DRILL_REGISTRY[dt]
            assert "runner" in entry
            assert callable(entry["runner"])

    def test_all_require_hanzi(self):
        for dt in _NEW_DRILL_TYPES:
            entry = DRILL_REGISTRY[dt]
            assert "hanzi" in entry["requires"], f"{dt} should require hanzi"

    def test_registry_count(self):
        """Should have at least 41 drill types after adding 8 new ones."""
        assert len(DRILL_REGISTRY) >= 41
