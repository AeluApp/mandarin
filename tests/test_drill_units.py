"""Unit tests for individual drill helper functions.

Tests pure functions from mandarin.drills -- no DB needed.
"""

import pytest

from mandarin.drills import (
    check_confidence_input,
    format_hanzi,
    format_hanzi_inline,
    format_scaffold_hint,
    char_overlap_score,
    marked_to_numbered,
    strip_tones,
    normalize_pinyin,
)
from mandarin.drills.production import grade_sentence_production
from mandarin.drills.speaking import grade_speaking_content
from mandarin.drills.listening import _edit_distance_score


# ---- TestCheckConfidenceInput ----

def test_question_mark_returns_half():
    assert check_confidence_input("?") == "half"


def test_uppercase_n_returns_unknown():
    assert check_confidence_input("N") == "unknown"


def test_lowercase_n_returns_unknown():
    assert check_confidence_input("n") == "unknown"


def test_regular_input_returns_none():
    assert check_confidence_input("hello") is None


def test_whitespace_question_mark():
    assert check_confidence_input(" ? ") == "half"


def test_whitespace_n():
    assert check_confidence_input(" N ") == "unknown"


def test_number_returns_none():
    assert check_confidence_input("1") is None


def test_empty_returns_none():
    assert check_confidence_input("") is None


# ---- TestFormatHanzi ----

def test_prominent_contains_hanzi():
    result = format_hanzi("\u4f60\u597d", prominent=True)
    assert "\u4f60" in result
    assert "\u597d" in result


def test_prominent_has_markup():
    result = format_hanzi("\u4f60\u597d", prominent=True)
    assert "[" in result
    assert "]" in result


def test_prominent_spaces_characters():
    result = format_hanzi("\u4f60\u597d", prominent=True)
    # Characters should be spaced out with double spaces
    assert "\u4f60  \u597d" in result


def test_compact_contains_hanzi():
    result = format_hanzi("\u4f60\u597d", prominent=False)
    assert "\u4f60\u597d" in result


def test_compact_no_spacing():
    result = format_hanzi("\u4f60\u597d", prominent=False)
    # Compact mode should not space out characters
    assert "\u4f60  \u597d" not in result


# ---- TestFormatHanziInline ----

def test_inline_contains_hanzi():
    result = format_hanzi_inline("\u4f60\u597d")
    assert "\u4f60\u597d" in result


def test_inline_compact_format():
    result = format_hanzi_inline("\u4f60\u597d")
    # Inline should not add extra spacing
    assert "\u4f60  \u597d" not in result


def test_inline_has_markup():
    result = format_hanzi_inline("\u4f60\u597d")
    assert "[" in result
    assert "]" in result


# ---- TestFormatScaffoldHint ----

def test_full_pinyin_returns_as_is():
    result = format_scaffold_hint("n\u01d0 h\u01ceo", "full_pinyin")
    assert result == "n\u01d0 h\u01ceo"


def test_none_returns_empty():
    result = format_scaffold_hint("n\u01d0 h\u01ceo", "none")
    assert result == ""


def test_tone_marks_returns_digits():
    result = format_scaffold_hint("n\u01d0 h\u01ceo", "tone_marks")
    # Should return space-separated tone numbers like "3 3"
    assert len(result) > 0
    parts = result.split()
    for part in parts:
        assert part.isdigit(), f"Expected digit, got {part!r}"


def test_initial_returns_first_consonants():
    result = format_scaffold_hint("n\u01d0 h\u01ceo", "initial")
    # Should return first letter of each syllable: "n h"
    assert len(result) > 0
    parts = result.split()
    assert len(parts) == 2


# ---- TestCharOverlapScore ----

def test_identical_strings():
    assert char_overlap_score("\u4f60\u597d", "\u4f60\u597d") == pytest.approx(1.0)


def test_partial_overlap():
    score = char_overlap_score("\u4f60\u597d", "\u4f60\u4eec")
    assert score > 0.0
    assert score < 1.0


def test_no_overlap():
    score = char_overlap_score("\u4f60\u597d", "\u4ed6\u4eec")
    assert score == pytest.approx(0.0)


def test_empty_expected():
    assert char_overlap_score("", "\u4f60\u597d") == pytest.approx(0.0)


def test_empty_user_input():
    assert char_overlap_score("\u4f60\u597d", "") == pytest.approx(0.0)


def test_both_empty():
    assert char_overlap_score("", "") == pytest.approx(0.0)


# ---- TestMarkedToNumbered ----

def test_basic_conversion():
    result = marked_to_numbered("n\u01d0 h\u01ceo")
    assert "3" in result
    assert "ni" in result
    assert "hao" in result


def test_first_tone():
    result = marked_to_numbered("m\u0101ma")
    assert "1" in result
    assert "ma" in result


def test_fourth_tone():
    result = marked_to_numbered("d\u00e0")
    assert result == "da4"


def test_no_tones():
    result = marked_to_numbered("de")
    assert result == "de"


def test_mixed_tones():
    result = marked_to_numbered("xi\u00e8xie")
    assert "4" in result
    assert "xie" in result


# ---- TestStripTones ----

def test_removes_tone_marks():
    result = strip_tones("n\u01d0 h\u01ceo")
    assert result == "ni hao"


def test_removes_tone_numbers():
    result = strip_tones("ni3 hao3")
    assert result == "ni hao"


def test_already_toneless():
    result = strip_tones("ni hao")
    assert result == "ni hao"


def test_all_tone_marks():
    result = strip_tones("m\u0101m\u00e1m\u01cem\u00e0")
    assert result == "mamamama"


def test_lowercase_output():
    # strip_tones only maps lowercase tone marks; uppercase accented
    # chars pass through translate, then .lower() preserves them.
    result = strip_tones("NI HAO")
    assert result == "ni hao"


# ---- TestNormalizePinyin ----

def test_removes_spaces():
    result = normalize_pinyin("ni hao")
    assert result == "nihao"


def test_removes_apostrophe():
    result = normalize_pinyin("xi\u2019an")
    assert result == "xian"


def test_handles_straight_apostrophe_variants():
    # normalize_pinyin strips straight apostrophes (U+0027)
    result = normalize_pinyin("xi'an")
    assert result == "xian"


def test_lowercases():
    result = normalize_pinyin("NI HAO")
    assert result == "nihao"


def test_combined():
    result = normalize_pinyin("Xi\u2019An Shi")
    assert result == "xianshi"


def test_already_normalized():
    result = normalize_pinyin("nihao")
    assert result == "nihao"


# ---- TestGradeSpeakingContent ----

def test_speaking_content_exact_match():
    assert grade_speaking_content("你好", "你好") == pytest.approx(1.0)


def test_speaking_content_with_punctuation():
    assert grade_speaking_content("你好！", "你好") == pytest.approx(1.0)


def test_speaking_content_partial():
    score = grade_speaking_content("你", "你好")
    assert 0.0 < score < 1.0


def test_speaking_content_empty_transcript():
    assert grade_speaking_content("", "你好") == pytest.approx(0.0)


def test_speaking_content_empty_expected():
    assert grade_speaking_content("你好", "") == pytest.approx(0.0)


def test_speaking_content_both_empty():
    assert grade_speaking_content("", "") == pytest.approx(0.0)


# ---- TestGradeSentenceProduction ----

def test_sentence_exact_match():
    template = {
        "acceptable_answers": ["我去过北京。", "我去过北京"],
        "required_keywords": ["去过", "北京"],
    }
    score, feedback, correct = grade_sentence_production("我去过北京。", template)
    assert score == 1.0
    assert correct is True


def test_sentence_exact_match_no_spaces():
    template = {
        "acceptable_answers": ["我 去过 北京"],
        "required_keywords": ["去过", "北京"],
    }
    score, feedback, correct = grade_sentence_production("我去过北京", template)
    assert score == 1.0
    assert correct is True


def test_sentence_all_keywords_high_overlap():
    template = {
        "acceptable_answers": ["我以前去过北京。"],
        "required_keywords": ["去过", "北京"],
    }
    score, feedback, correct = grade_sentence_production("我去过北京了", template)
    assert score >= 0.6
    assert correct is True


def test_sentence_partial_match():
    template = {
        "acceptable_answers": ["我以前去过北京。"],
        "required_keywords": ["去过", "北京"],
    }
    score, feedback, correct = grade_sentence_production("去过吧", template)
    assert 0.0 < score < 1.0


def test_sentence_no_match():
    template = {
        "acceptable_answers": ["我以前去过北京。"],
        "required_keywords": ["去过", "北京"],
    }
    score, feedback, correct = grade_sentence_production("今天天气很好", template)
    assert score == 0.0
    assert correct is False


def test_sentence_empty_input():
    template = {
        "acceptable_answers": ["我去过北京。"],
        "required_keywords": ["去过"],
    }
    score, feedback, correct = grade_sentence_production("", template)
    assert score == 0.0
    assert correct is False


def test_sentence_empty_template():
    score, feedback, correct = grade_sentence_production("你好", {})
    assert score == 0.0


# ---- TestEditDistanceScore ----

def test_edit_distance_identical():
    assert _edit_distance_score("你好", "你好") == pytest.approx(1.0)


def test_edit_distance_empty_both():
    assert _edit_distance_score("", "") == pytest.approx(1.0)


def test_edit_distance_one_empty():
    assert _edit_distance_score("你好", "") == pytest.approx(0.0)
    assert _edit_distance_score("", "你好") == pytest.approx(0.0)


def test_edit_distance_one_char_diff():
    score = _edit_distance_score("你好", "你们")
    assert 0.0 < score < 1.0
    assert score == pytest.approx(0.5)  # 1 edit / 2 chars


def test_edit_distance_completely_different():
    score = _edit_distance_score("你好", "他们吃饭了")
    assert score < 0.5
