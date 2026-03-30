"""Tests for milestones module -- milestone loading, validation, and evaluation."""

import json
import sqlite3
from pathlib import Path


# ---- TestMilestoneLoading ----

def test_milestones_json_exists():
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    assert path.exists(), "data/milestones.json should exist"


def test_milestones_json_valid():
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    with open(path) as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 10, "Should have at least 10 milestones"


def test_all_milestones_have_required_fields():
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    with open(path) as f:
        data = json.load(f)
    for i, m in enumerate(data):
        for field in ("key", "label", "requires", "phase"):
            assert field in m, f"Milestone {i} missing '{field}'"


def test_no_duplicate_keys():
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    with open(path) as f:
        data = json.load(f)
    keys = [m["key"] for m in data]
    assert len(keys) == len(set(keys)), "Duplicate milestone keys found"


def test_all_phases_valid():
    from mandarin.milestones import _VALID_PHASES
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    with open(path) as f:
        data = json.load(f)
    for m in data:
        assert m["phase"] in _VALID_PHASES, \
            f"Milestone '{m['key']}' has invalid phase '{m['phase']}'"


def test_all_requirement_keys_valid():
    from mandarin.milestones import _VALID_REQUIREMENT_KEYS
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    with open(path) as f:
        data = json.load(f)
    for m in data:
        for key in m["requires"]:
            assert key in _VALID_REQUIREMENT_KEYS, \
                f"Milestone '{m['key']}' has unknown requirement key '{key}'"


def test_loaded_milestones_match_json():
    from mandarin.milestones import MILESTONES
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    with open(path) as f:
        data = json.load(f)
    assert len(MILESTONES) == len(data), \
        "MILESTONES count should match JSON"


def test_hsk_stable_keys_converted_to_int():
    from mandarin.milestones import MILESTONES
    for m in MILESTONES:
        if "hsk_stable" in m["requires"]:
            for key in m["requires"]["hsk_stable"]:
                assert isinstance(key, int), \
                    f"hsk_stable key should be int, got {type(key)} in '{m['key']}'"


# ---- TestMilestoneMet ----

def test_sessions_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"sessions": 5}, "phase": "foundation"}
    stats = {"sessions": 5, "items_seen": 0, "mastery": {}, "lens_pct": {}, "scenario_avgs": {}}
    assert _milestone_met(m, stats)


def test_sessions_not_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"sessions": 5}, "phase": "foundation"}
    stats = {"sessions": 3, "items_seen": 0, "mastery": {}, "lens_pct": {}, "scenario_avgs": {}}
    assert not _milestone_met(m, stats)


def test_items_seen_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"items_seen": 50}, "phase": "foundation"}
    stats = {"sessions": 10, "items_seen": 60, "mastery": {}, "lens_pct": {}, "scenario_avgs": {}}
    assert _milestone_met(m, stats)


def test_hsk_stable_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"hsk_stable": {1: 70}}, "phase": "emerging"}
    stats = {"sessions": 10, "items_seen": 50,
             "mastery": {1: {"pct": 80}},
             "lens_pct": {}, "scenario_avgs": {}}
    assert _milestone_met(m, stats)


def test_hsk_stable_not_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"hsk_stable": {1: 70}}, "phase": "emerging"}
    stats = {"sessions": 10, "items_seen": 50,
             "mastery": {1: {"pct": 50}},
             "lens_pct": {}, "scenario_avgs": {}}
    assert not _milestone_met(m, stats)


def test_hsk_stable_missing_level():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"hsk_stable": {2: 30}}, "phase": "growing"}
    stats = {"sessions": 10, "items_seen": 50,
             "mastery": {},  # no level 2 data
             "lens_pct": {}, "scenario_avgs": {}}
    assert not _milestone_met(m, stats)


def test_lens_pct_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"lens_pct": {"food_social": 30}}, "phase": "emerging"}
    stats = {"sessions": 10, "items_seen": 50,
             "mastery": {}, "lens_pct": {"food_social": 40}, "scenario_avgs": {}}
    assert _milestone_met(m, stats)


def test_lens_pct_not_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test", "requires": {"lens_pct": {"food_social": 30}}, "phase": "emerging"}
    stats = {"sessions": 10, "items_seen": 50,
             "mastery": {}, "lens_pct": {"food_social": 20}, "scenario_avgs": {}}
    assert not _milestone_met(m, stats)


def test_multiple_requirements_all_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test",
         "requires": {"sessions": 3, "items_seen": 15},
         "phase": "foundation"}
    stats = {"sessions": 5, "items_seen": 20,
             "mastery": {}, "lens_pct": {}, "scenario_avgs": {}}
    assert _milestone_met(m, stats)


def test_multiple_requirements_partial_met():
    from mandarin.milestones import _milestone_met
    m = {"key": "test",
         "requires": {"sessions": 3, "items_seen": 15},
         "phase": "foundation"}
    stats = {"sessions": 5, "items_seen": 10,  # items_seen not met
             "mastery": {}, "lens_pct": {}, "scenario_avgs": {}}
    assert not _milestone_met(m, stats)


# ---- TestStageCountsSchema ----

def _make_milestones_db():
    from tests.shared_db import make_test_db
    return make_test_db()


def test_returns_all_expected_keys():
    from mandarin.milestones import get_stage_counts
    conn = _make_milestones_db()
    conn.execute("INSERT INTO content_item (hanzi, pinyin, english) VALUES ('\u4f60', 'n\u01d0', 'you')")
    result = get_stage_counts(conn)
    for key in ("seen", "passed_once", "stabilizing", "stable", "durable", "decayed", "unseen"):
        assert key in result, f"Missing key '{key}'"
    # Backward compat
    assert "weak" in result
    assert "improving" in result
    conn.close()


def test_unseen_item_counted():
    from mandarin.milestones import get_stage_counts
    conn = _make_milestones_db()
    conn.execute("INSERT INTO content_item (hanzi, pinyin, english) VALUES ('\u4f60', 'n\u01d0', 'you')")
    result = get_stage_counts(conn)
    assert result["unseen"] == 1
    conn.close()


def test_seen_item_counted():
    from mandarin.milestones import get_stage_counts
    conn = _make_milestones_db()
    conn.execute("INSERT INTO content_item (hanzi, pinyin, english) VALUES ('\u4f60', 'n\u01d0', 'you')")
    conn.execute("INSERT INTO progress (content_item_id, modality, mastery_stage, total_attempts) VALUES (1, 'reading', 'seen', 1)")
    result = get_stage_counts(conn)
    assert result["seen"] == 1
    assert result["unseen"] == 0
    conn.close()


def test_weak_alias_is_seen_plus_passed_once():
    from mandarin.milestones import get_stage_counts
    conn = _make_milestones_db()
    conn.execute("INSERT INTO content_item (id, hanzi, pinyin, english) VALUES (1, '\u4f60', 'n\u01d0', 'you')")
    conn.execute("INSERT INTO content_item (id, hanzi, pinyin, english) VALUES (2, '\u597d', 'h\u01ceo', 'good')")
    conn.execute("INSERT INTO progress (content_item_id, modality, mastery_stage, total_attempts) VALUES (1, 'reading', 'seen', 1)")
    conn.execute("INSERT INTO progress (content_item_id, modality, mastery_stage, total_attempts) VALUES (2, 'reading', 'passed_once', 2)")
    result = get_stage_counts(conn)
    assert result["weak"] == result["seen"] + result["passed_once"]
    conn.close()
