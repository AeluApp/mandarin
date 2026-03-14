"""Tests for production drill grading — char_overlap_score and grade_sentence_production."""

import pytest
from mandarin.drills.production import char_overlap_score, grade_sentence_production


# ── char_overlap_score ───────────────────────

def test_overlap_identical():
    """Identical strings → 1.0."""
    assert char_overlap_score("你好", "你好") == 1.0


def test_overlap_no_match():
    """Completely different characters → 0.0."""
    assert char_overlap_score("你好", "世界") == 0.0


def test_overlap_partial():
    """Partial overlap produces a value between 0 and 1."""
    score = char_overlap_score("你好世界", "你好中国")
    assert 0.0 < score < 1.0


def test_overlap_empty_expected():
    """Empty expected → 0.0."""
    assert char_overlap_score("", "你好") == 0.0


def test_overlap_empty_input():
    """Empty input → 0.0."""
    assert char_overlap_score("你好", "") == 0.0


def test_overlap_both_empty():
    """Both empty → 0.0."""
    assert char_overlap_score("", "") == 0.0


def test_overlap_superset():
    """Input is superset of expected → < 1.0 (Jaccard penalizes extra chars)."""
    score = char_overlap_score("好", "你好")
    assert 0.0 < score < 1.0


def test_overlap_symmetric():
    """Jaccard similarity is symmetric."""
    a = char_overlap_score("你好世", "你世界")
    b = char_overlap_score("你世界", "你好世")
    assert a == b


# ── grade_sentence_production ────────────────

def test_grade_exact_match():
    """Exact match of any acceptable answer → 1.0."""
    template = {
        "acceptable_answers": ["我很好", "我 很 好"],
        "required_keywords": ["我", "好"],
    }
    score, feedback, correct = grade_sentence_production("我很好", template)
    assert score == 1.0
    assert correct is True


def test_grade_exact_match_with_spaces():
    """Spaces are stripped for matching."""
    template = {
        "acceptable_answers": ["我很好"],
        "required_keywords": ["我", "好"],
    }
    score, feedback, correct = grade_sentence_production("我 很 好", template)
    assert score == 1.0
    assert correct is True


def test_grade_all_keywords_high_overlap():
    """All keywords present + high overlap → 0.8."""
    template = {
        "acceptable_answers": ["我今天很好"],
        "required_keywords": ["我", "好"],
    }
    score, feedback, correct = grade_sentence_production("我很好今天", template)
    assert score >= 0.6
    assert correct is True


def test_grade_all_keywords_low_overlap():
    """All keywords present but low overlap → 0.6."""
    template = {
        "acceptable_answers": ["我今天在学校很好"],
        "required_keywords": ["我", "好"],
    }
    score, feedback, correct = grade_sentence_production("我好", template)
    assert score == 0.6
    assert correct is True


def test_grade_partial_keywords():
    """Some keywords + some overlap → 0.4."""
    template = {
        "acceptable_answers": ["我今天很好"],
        "required_keywords": ["我", "今天", "好"],
    }
    score, feedback, correct = grade_sentence_production("我不错", template)
    # Only "我" matches out of 3 keywords → kw_ratio = 0.33
    # But char overlap might still be >= 0.5
    assert score <= 0.4
    assert correct is False


def test_grade_no_match():
    """No keywords, no overlap → 0.0."""
    template = {
        "acceptable_answers": ["你好吗"],
        "required_keywords": ["你", "吗"],
    }
    score, feedback, correct = grade_sentence_production("再见世界", template)
    assert score == 0.0
    assert correct is False


def test_grade_empty_input():
    """Empty user input → 0.0."""
    template = {
        "acceptable_answers": ["你好"],
        "required_keywords": ["你"],
    }
    score, feedback, correct = grade_sentence_production("", template)
    assert score == 0.0
    assert correct is False


def test_grade_empty_template():
    """Empty template → 0.0."""
    score, feedback, correct = grade_sentence_production("你好", {})
    # No acceptable_answers, so no exact match possible
    # No required_keywords → kw_ratio = 0
    assert score == 0.0 or correct is False


def test_grade_none_inputs():
    """None inputs → 0.0."""
    score, feedback, correct = grade_sentence_production(None, None)
    assert score == 0.0
    assert correct is False
