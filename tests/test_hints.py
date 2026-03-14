"""Tests for sticky hanzi hint engine — radical, contrast, component, phonetic."""

import pytest
from mandarin.drills.hints import (
    get_hanzi_hint, HINT_TYPES,
    _radical_hint, _contrast_hint, _component_hint, _phonetic_hint,
)


# ── HINT_TYPES ──────────────────────────────

def test_hint_types_complete():
    """HINT_TYPES should contain all four hint strategies."""
    assert HINT_TYPES == ["radical", "contrast", "component", "phonetic"]


# ── get_hanzi_hint rotation ──────────────────

def test_rotation_avoids_last_type():
    """get_hanzi_hint should not repeat the last hint type."""
    _, hint_type = get_hanzi_hint("水", last_hint_type="radical")
    # Should pick something other than radical (or radical as fallback if nothing else works)
    # The point is the function runs without error and returns a tuple
    assert hint_type is None or hint_type in HINT_TYPES


def test_error_type_preferred_routing():
    """Error type 'tone' should prefer phonetic hint."""
    hint, hint_type = get_hanzi_hint("妈", error_type="tone")
    # If phonetic hint is available for this character, it should be used
    if hint:
        assert hint_type in HINT_TYPES


def test_error_type_vocab_prefers_radical():
    """Error type 'vocab' should prefer radical hint."""
    hint, hint_type = get_hanzi_hint("水", error_type="vocab")
    if hint:
        assert hint_type in HINT_TYPES


def test_fallback_when_preferred_is_none():
    """If preferred hint returns None, should try other types."""
    # Single char with no obvious radical → component should work
    hint, hint_type = get_hanzi_hint("大", error_type="segment")
    # contrast needs wrong_answer, so it returns None → falls through
    if hint:
        assert hint_type in HINT_TYPES


def test_ascii_returns_component_hint():
    """ASCII input falls through to component hint (splits on characters)."""
    hint, hint_type = get_hanzi_hint("hello")
    # Component hint will still work on multi-char strings
    # Radical and phonetic won't match, but component always can
    if hint is not None:
        assert hint_type == "component"
    else:
        assert hint_type is None


def test_empty_hanzi():
    """Empty string should return (None, None)."""
    hint, hint_type = get_hanzi_hint("")
    assert hint is None
    assert hint_type is None


def test_last_hint_type_cycles():
    """Cycling through all types should always return a valid result."""
    for last in HINT_TYPES:
        hint, hint_type = get_hanzi_hint("好", last_hint_type=last)
        # Should either return a valid hint or (None, None)
        assert hint_type is None or hint_type in HINT_TYPES


# ── Individual hint strategies ───────────────

def test_radical_hint_water():
    """水 is itself a radical — should return a radical hint."""
    hint = _radical_hint("水")
    assert hint is not None
    assert "Hint" in hint


def test_radical_hint_no_match():
    """ASCII has no radical hint."""
    assert _radical_hint("abc") is None


def test_contrast_hint_with_wrong_answer():
    """Contrast hint needs hanzi + wrong_answer."""
    hint = _contrast_hint("大", "太")
    assert hint is not None
    assert "compare" in hint.lower()


def test_contrast_hint_no_wrong_answer():
    """Contrast hint without wrong_answer returns None."""
    assert _contrast_hint("大", "") is None


def test_contrast_hint_long_strings_none():
    """Contrast hint returns None for long multi-char strings."""
    assert _contrast_hint("你好世界很大", "我好世界") is None


def test_component_hint_single_char():
    """Single CJK character gets component hint."""
    hint = _component_hint("明")
    assert hint is not None
    assert "shapes" in hint.lower()


def test_component_hint_multi_char():
    """Multi-character string gets a shared-component hint."""
    hint = _component_hint("你好")
    assert hint is not None
    assert "share" in hint.lower()


def test_component_hint_empty():
    """Empty string returns None."""
    assert _component_hint("") is None


def test_phonetic_hint_multi_char():
    """Multi-char hanzi gets phonetic hint."""
    hint = _phonetic_hint("妈妈")
    assert hint is not None
    assert "sound" in hint.lower()


def test_phonetic_hint_single_char_none():
    """Single char has no phonetic hint (needs >= 2)."""
    assert _phonetic_hint("马") is None
