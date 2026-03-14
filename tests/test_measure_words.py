"""Tests for measure word drill system."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mandarin.drills.advanced import (
    _load_measure_words, _build_noun_to_mw_map, _load_confusable_groups,
    _get_confusable_distractors, _get_semantic_feedback, _get_mw_entry,
    _find_correct_mw,
    run_measure_word_drill, run_measure_word_cloze_drill,
    run_measure_word_production_drill, run_measure_word_discrimination_drill,
)
from mandarin.drills.base import DrillResult


# ── Data loading ─────────────────────────────────────────────────

def test_load_measure_words_returns_list():
    """measure_words.json loads as a list of classifier entries."""
    mw_data = _load_measure_words()
    assert isinstance(mw_data, list)
    assert len(mw_data) > 50  # We have ~98 entries


def test_load_confusable_groups():
    """confusable_groups loads as a dict with 10 groups."""
    groups = _load_confusable_groups()
    assert isinstance(groups, dict)
    assert len(groups) >= 10
    assert "long_things" in groups
    assert "animals" in groups
    assert "vehicles" in groups


def test_classifier_field_present():
    """Every entry has a 'classifier' field (not 'measure_word')."""
    mw_data = _load_measure_words()
    for entry in mw_data:
        assert "classifier" in entry, f"Missing 'classifier' in {entry}"


def test_enriched_entries_have_nouns_and_semantic_rule():
    """HSK 1-4 entries have nouns and semantic_rule."""
    mw_data = _load_measure_words()
    hsk14 = [e for e in mw_data if e.get("hsk_level", 99) <= 4]
    assert len(hsk14) >= 30
    for entry in hsk14:
        # Most HSK 1-4 entries should have nouns and semantic_rule
        # (a few like 些 might be lighter)
        if entry.get("nouns"):
            assert len(entry["nouns"]) >= 2, f"{entry['classifier']} has too few nouns"
        assert entry.get("semantic_rule"), f"{entry['classifier']} missing semantic_rule"


# ── Noun map building ────────────────────────────────────────────

def test_noun_map_has_many_entries():
    """Noun map should have 100+ nouns (not the old 14)."""
    mw_data = _load_measure_words()
    noun_map = _build_noun_to_mw_map(mw_data)
    assert len(noun_map) >= 100, f"Only {len(noun_map)} nouns mapped, expected 100+"


def test_noun_map_key_entries():
    """Known nouns map to correct classifiers."""
    mw_data = _load_measure_words()
    noun_map = _build_noun_to_mw_map(mw_data)

    assert noun_map["书"]["measure_word"] == "本"
    assert noun_map["猫"]["measure_word"] == "只"
    assert noun_map["车"]["measure_word"] == "辆"
    assert noun_map["茶"]["measure_word"] == "杯"


def test_noun_map_example_fallback():
    """Entries without explicit nouns parse them from examples."""
    # HSK 7+ entries don't have nouns field, should parse from examples
    mw_data = _load_measure_words()
    noun_map = _build_noun_to_mw_map(mw_data)
    # 缕 has examples like "一缕阳光" → should extract "阳光"
    assert "阳光" in noun_map


# ── Confusable distractors ───────────────────────────────────────

def test_confusable_distractors_from_same_group():
    """Distractors for 条 should include other long_things like 根, 支."""
    mw_data = _load_measure_words()
    groups = _load_confusable_groups()
    distractors = _get_confusable_distractors("条", mw_data, groups, n=3)
    assert len(distractors) == 3
    # At least one should be from the long_things group
    long_things = groups["long_things"]["classifiers"]
    overlap = [d for d in distractors if d in long_things]
    assert len(overlap) >= 1, f"Expected confusable distractors, got {distractors}"


def test_confusable_distractors_exclude_correct():
    """Correct MW never appears as a distractor."""
    mw_data = _load_measure_words()
    groups = _load_confusable_groups()
    for correct in ["条", "只", "张", "个"]:
        distractors = _get_confusable_distractors(correct, mw_data, groups, n=3)
        assert correct not in distractors


# ── Semantic feedback ────────────────────────────────────────────

def test_semantic_feedback_includes_rule():
    """Feedback for wrong answer includes the semantic rule."""
    mw_data = _load_measure_words()
    groups = _load_confusable_groups()
    feedback = _get_semantic_feedback("条", "根", mw_data, groups)
    assert "条" in feedback
    assert "bend" in feedback.lower() or "flexible" in feedback.lower()


def test_semantic_feedback_includes_discrimination_tip():
    """When wrong answer is from same confusable group, tip appears."""
    mw_data = _load_measure_words()
    groups = _load_confusable_groups()
    feedback = _get_semantic_feedback("条", "根", mw_data, groups)
    assert "Tip:" in feedback


def test_semantic_feedback_no_tip_for_unrelated():
    """No discrimination tip when wrong answer is from a different group."""
    mw_data = _load_measure_words()
    groups = _load_confusable_groups()
    feedback = _get_semantic_feedback("条", "杯", mw_data, groups)
    assert "Tip:" not in feedback


# ── Drill smoke tests ───────────────────────────────────────────

def _make_item(hanzi="书", english="book", hsk_level=1, item_id=1):
    return {"id": item_id, "hanzi": hanzi, "english": english,
            "pinyin": "shū", "hsk_level": hsk_level}


def _make_show():
    lines = []
    def show(text, **kw):
        lines.append(text)
    return show, lines


def _make_input(answer):
    """Return an input_fn that returns the given answer."""
    return lambda prompt: answer


def test_measure_word_drill_smoke():
    """run_measure_word_drill returns DrillResult for a known noun."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    item = _make_item("书", "book")
    # Answer "1" — may or may not be correct, just check no crash
    result = run_measure_word_drill(item, conn, show_fn, _make_input("1"))
    assert isinstance(result, DrillResult)
    assert result.drill_type == "measure_word"


def test_measure_word_drill_unknown_noun():
    """Unknown noun returns None (dispatch will fall back to MC)."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    # Use something with no substring in noun map
    item = _make_item("哈哈", "haha")
    result = run_measure_word_drill(item, conn, show_fn, _make_input("1"))
    assert result is None


def test_cloze_drill_smoke():
    """run_measure_word_cloze_drill returns DrillResult for a known noun."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    item = _make_item("书", "book")
    result = run_measure_word_cloze_drill(item, conn, show_fn, _make_input("1"))
    assert isinstance(result, DrillResult)
    assert result.drill_type == "measure_word_cloze"


def test_production_drill_smoke():
    """run_measure_word_production_drill returns DrillResult."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    item = _make_item("书", "book")
    result = run_measure_word_production_drill(item, conn, show_fn, _make_input("本"))
    assert isinstance(result, DrillResult)
    assert result.drill_type == "measure_word_production"
    assert result.correct is True


def test_production_drill_accepts_pinyin():
    """Production drill accepts pinyin input."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    item = _make_item("书", "book")
    result = run_measure_word_production_drill(item, conn, show_fn, _make_input("běn"))
    assert isinstance(result, DrillResult)
    assert result.correct is True


def test_discrimination_drill_smoke():
    """run_measure_word_discrimination_drill returns DrillResult."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    item = _make_item("猫", "cat")
    result = run_measure_word_discrimination_drill(item, conn, show_fn, _make_input("1"))
    assert isinstance(result, DrillResult)
    assert result.drill_type == "measure_word_disc"


def test_error_type_is_measure_word():
    """Wrong answers produce error_type='measure_word', not 'vocab'."""
    show_fn, lines = _make_show()
    conn = MagicMock()
    item = _make_item("书", "book")
    # Force wrong answer by guessing
    result = run_measure_word_production_drill(item, conn, show_fn, _make_input("只"))
    assert result.error_type == "measure_word"


# ── Registry integration ────────────────────────────────────────

def test_new_drills_in_registry():
    """New drill types are registered in DRILL_REGISTRY."""
    from mandarin.drills.dispatch import DRILL_REGISTRY
    assert "measure_word_cloze" in DRILL_REGISTRY
    assert "measure_word_production" in DRILL_REGISTRY
    assert "measure_word_disc" in DRILL_REGISTRY


def test_new_drills_in_ui_labels():
    """New drill types have UI labels."""
    from mandarin.ui_labels import DRILL_LABELS
    assert "measure_word_cloze" in DRILL_LABELS
    assert "measure_word_production" in DRILL_LABELS
    assert "measure_word_disc" in DRILL_LABELS
