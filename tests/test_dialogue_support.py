"""Tests for dialogue support level gating and rendering.

Verifies:
- determine_support_level() returns correct level based on scenario stats
- run_dialogue_drill() renders full_support and hanzi_only correctly
- Post-answer reveal always shows full info
"""

import json
from mandarin.scenario_loader import (
    determine_support_level,
    SUPPORT_REMOVAL_AVG_SCORE,
    SUPPORT_REMOVAL_MIN_PRESENTATIONS,
)
from mandarin.conversation import run_dialogue_drill
from mandarin.drills import DrillResult


# ── determine_support_level tests ──────────────────────────────

def test_support_level_new_scenario():
    """New scenario (0 presentations) should be full_support."""
    scenario = {"times_presented": 0, "avg_score": None}
    assert determine_support_level(scenario) == "full_support"


def test_support_level_few_presentations():
    """Scenario with <3 presentations should be full_support even with high score."""
    scenario = {"times_presented": 2, "avg_score": 0.9}
    assert determine_support_level(scenario) == "full_support"


def test_support_level_low_score():
    """Scenario with enough presentations but low score stays full_support."""
    scenario = {"times_presented": 5, "avg_score": 0.5}
    assert determine_support_level(scenario) == "full_support"


def test_support_level_threshold_exact():
    """Scenario at exactly the threshold should be hanzi_only."""
    scenario = {
        "times_presented": SUPPORT_REMOVAL_MIN_PRESENTATIONS,
        "avg_score": SUPPORT_REMOVAL_AVG_SCORE,
    }
    assert determine_support_level(scenario) == "hanzi_only"


def test_support_level_above_threshold():
    """Scenario above threshold should be hanzi_only."""
    scenario = {"times_presented": 10, "avg_score": 0.9}
    assert determine_support_level(scenario) == "hanzi_only"


def test_support_level_none_values():
    """Scenario with None values for stats should be full_support."""
    scenario = {"times_presented": None, "avg_score": None}
    assert determine_support_level(scenario) == "full_support"


def test_support_level_missing_keys():
    """Scenario missing stats keys should be full_support."""
    scenario = {}
    assert determine_support_level(scenario) == "full_support"


# ── Dialogue rendering tests ──────────────────────────────

def _make_scenario(with_pinyin=True):
    """Create a test scenario dict."""
    tree = {
        "setup": "Test setup",
        "setup_zh": "测试场景",
        "turns": [
            {
                "speaker": "npc",
                "text_zh": "你好",
                "text_pinyin": "nǐ hǎo",
                "text_en": "Hello",
            },
            {
                "speaker": "player",
                "prompt_en": "Greet them back.",
                "options": [
                    {
                        "text_zh": "你好！",
                        "text_pinyin": "nǐ hǎo!",
                        "text_en": "Hello!",
                        "score": 1.0,
                        "register": "neutral",
                        "feedback": "Great greeting.",
                    },
                    {
                        "text_zh": "嗯。",
                        "text_pinyin": "ēn.",
                        "text_en": "Mm.",
                        "score": 0.3,
                        "register": "minimal",
                        "feedback": "Too brief.",
                    },
                ],
            },
        ],
        "cultural_note": "Greetings matter.",
    }
    return {
        "id": 1,
        "title": "Test Dialogue",
        "tree_json": json.dumps(tree),
    }


def test_full_support_shows_pinyin_english():
    """In full_support mode, player options should include pinyin and english."""
    scenario = _make_scenario()
    output = []

    def show_fn(text, end="\n"):
        output.append(text)

    def input_fn(prompt):
        return "1"  # Always pick first option

    result = run_dialogue_drill(scenario, show_fn, input_fn, support_level="full_support")

    # Find the option lines (numbered 1. or 2.)
    option_lines = [l for l in output if l.strip().startswith(("1.", "2."))]
    assert len(option_lines) >= 1
    # Options are shuffled, so check across all option lines
    all_options = " ".join(option_lines)
    # Should contain pinyin and english for both options
    assert "nǐ hǎo!" in all_options or "ēn." in all_options
    assert "Hello!" in all_options or "Mm." in all_options


def test_hanzi_only_hides_pinyin_english():
    """In hanzi_only mode, player options should only show Chinese text."""
    from unittest.mock import patch
    scenario = _make_scenario()
    output = []

    def show_fn(text, end="\n"):
        output.append(text)

    def input_fn(prompt):
        return "1"

    # Patch shuffle to preserve option order
    with patch("mandarin.conversation.random.shuffle"):
        result = run_dialogue_drill(scenario, show_fn, input_fn, support_level="hanzi_only")

    # Find the option lines
    option_lines = [l for l in output if l.strip().startswith("1.")]
    assert len(option_lines) >= 1
    # Should NOT contain pinyin or english in the option
    assert "nǐ hǎo!" not in option_lines[0]
    assert "Hello!" not in option_lines[0]
    # But should contain hanzi
    assert "你好！" in option_lines[0]


def test_hanzi_only_shows_support_reduced_message():
    """In hanzi_only mode, should show support reduction notice."""
    scenario = _make_scenario()
    output = []

    def show_fn(text, end="\n"):
        output.append(text)

    def input_fn(prompt):
        return "1"

    run_dialogue_drill(scenario, show_fn, input_fn, support_level="hanzi_only")
    assert any("Support reduced" in l for l in output)


def test_post_answer_always_reveals_full_info():
    """After answering, full info should always be revealed regardless of support level."""
    from unittest.mock import patch
    for support_level in ["full_support", "hanzi_only"]:
        scenario = _make_scenario()
        output = []

        def show_fn(text, end="\n"):
            output.append(text)

        def input_fn(prompt):
            return "1"

        # Patch shuffle to preserve option order (option 1 = 你好！)
        with patch("mandarin.conversation.random.shuffle"):
            run_dialogue_drill(scenario, show_fn, input_fn, support_level=support_level)

        # Should see "Your answer:" with full reveal
        answer_lines = [l for l in output if "Your answer:" in l]
        assert len(answer_lines) >= 1, f"No 'Your answer:' line in {support_level} mode"
        # The reveal should contain pinyin
        assert any("nǐ hǎo!" in l for l in answer_lines), \
            f"Post-answer reveal missing pinyin in {support_level} mode"


def test_wrong_answer_shows_better_option():
    """When picking a low-score option, should show the better option."""
    from unittest.mock import patch
    scenario = _make_scenario()
    output = []

    def show_fn(text, end="\n"):
        output.append(text)

    def input_fn(prompt):
        return "2"  # Pick the low-score option (嗯。 at position 2 with no shuffle)

    # Patch shuffle to preserve option order (option 2 = low-score 嗯。)
    with patch("mandarin.conversation.random.shuffle"):
        result = run_dialogue_drill(scenario, show_fn, input_fn, support_level="full_support")

    # Should see "Better:" line
    better_lines = [l for l in output if "Better:" in l]
    assert len(better_lines) >= 1
    # The better option should be the high-score one
    assert any("你好！" in l for l in better_lines)


def test_dialogue_returns_valid_result():
    """run_dialogue_drill should return a valid DrillResult."""
    scenario = _make_scenario()

    def show_fn(text, end="\n"):
        pass

    def input_fn(prompt):
        return "1"

    result = run_dialogue_drill(scenario, show_fn, input_fn, support_level="full_support")
    assert isinstance(result, DrillResult)
    assert result.drill_type == "dialogue"
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0


def test_dialogue_quit():
    """Pressing Q should return a skipped result."""
    scenario = _make_scenario()

    def show_fn(text, end="\n"):
        pass

    def input_fn(prompt):
        return "Q"

    result = run_dialogue_drill(scenario, show_fn, input_fn, support_level="full_support")
    assert result.skipped is True
    assert result.user_answer == "Q"

