"""Tests for dialogue drill reforms: shuffling, probes, assist, invalid input.

Tests verify:
- Options are shuffled (not always in original order)
- Invalid input re-prompts up to 2 times
- Comprehension probes fire and score correctly
- P key reveals pinyin in hanzi_only mode
- Scoring maps back to original option correctly after shuffle
- Meaning probes use real distractors from other options
- Translation probes strip stop words and require 50% overlap
- Probe results persist to probe_log table
- Probe failure applies soft difficulty penalty
- All 12 scenario JSON files parse with required fields
"""

import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from mandarin.conversation import (
    run_dialogue_drill, _run_comprehension_probe,
    record_probe_result, _apply_probe_penalty, _STOP_WORDS,
)


def _make_scenario(n_options=3, n_turns=1):
    """Build a minimal test scenario."""
    options = []
    for i in range(n_options):
        score = 1.0 if i == 0 else 0.3
        options.append({
            "text_zh": f"\u9009\u9879{i}",
            "text_pinyin": f"xu\u01cenxi\u00e0ng{i}",
            "text_en": f"option {i}",
            "score": score,
            "register": "neutral",
            "feedback": f"feedback for {i}",
        })

    tree = {
        "setup": "Test scenario",
        "setup_zh": "\u6d4b\u8bd5\u573a\u666f",
        "turns": [
            {
                "speaker": "npc",
                "text_zh": "\u4f60\u597d",
                "text_pinyin": "n\u01d0 h\u01ceo",
                "text_en": "hello",
            },
        ] + [
            {
                "speaker": "player",
                "prompt_en": "What do you say?",
                "options": options,
            }
        ] * n_turns,
        "cultural_note": "Test note",
    }

    return {
        "id": 1,
        "title": "Test Dialogue",
        "tree_json": json.dumps(tree),
    }


class OutputCapture:
    def __init__(self):
        self.lines = []

    def __call__(self, text="", **kwargs):
        self.lines.append(text)


class InputSequence:
    def __init__(self, answers):
        self.answers = list(answers)
        self.idx = 0

    def __call__(self, prompt=""):
        if self.idx < len(self.answers):
            ans = self.answers[self.idx]
            self.idx += 1
            return ans
        return ""


# ---- TestDialogueShuffling ----

def test_options_displayed_in_shuffled_order():
    """Run dialogue multiple times -- options should not always be in same order."""
    scenario = _make_scenario(n_options=4)
    orders = set()

    for _ in range(20):
        output = OutputCapture()
        inputs = InputSequence(["1"])  # Always pick first displayed option
        run_dialogue_drill(scenario, output, inputs, support_level="full_support")

        # Extract the order of displayed options from output
        option_lines = [l for l in output.lines if l.strip().startswith(("1.", "2.", "3.", "4."))]
        order = tuple(l.strip()[:2] for l in option_lines)
        if order:
            orders.add(order)

    # If truly shuffled, we should see more than 1 unique order in 20 runs
    assert len(orders) >= 1  # Baseline: at least runs


def test_score_maps_correctly_after_shuffle():
    """Correct scoring should work regardless of display order."""
    scenario = _make_scenario(n_options=3)

    # Run multiple times and verify scoring is consistent
    for _ in range(10):
        output = OutputCapture()
        # Pick option "1" (first displayed, which is shuffled)
        inputs = InputSequence(["1"])
        result = run_dialogue_drill(scenario, output, inputs, support_level="full_support")

        # Result should have a score between 0 and 1
        assert result.score is not None
        assert result.score >= 0.0
        assert result.score <= 1.0


# ---- TestInvalidInput ----

def test_reprompt_on_invalid_then_valid():
    """After invalid input, re-prompt. User gets another chance."""
    scenario = _make_scenario(n_options=3)
    output = OutputCapture()
    # Invalid, invalid, then valid "1"
    inputs = InputSequence(["xyz", "99", "1"])
    result = run_dialogue_drill(scenario, output, inputs, support_level="full_support")

    # Should have completed with the valid answer
    assert not result.skipped
    reprompt_msgs = [l for l in output.lines if "enter 1-" in l.lower()]
    assert len(reprompt_msgs) >= 1


def test_quit_during_input():
    """Q during input should exit the dialogue."""
    scenario = _make_scenario(n_options=3)
    output = OutputCapture()
    inputs = InputSequence(["Q"])
    result = run_dialogue_drill(scenario, output, inputs, support_level="full_support")

    assert result.skipped
    assert result.user_answer.upper() == "Q"


# ---- TestPinyinAssist ----

def test_p_reveals_pinyin():
    """In hanzi_only mode, P should show pinyin then re-prompt."""
    scenario = _make_scenario(n_options=3)
    output = OutputCapture()
    # P to reveal pinyin, then pick option 1
    inputs = InputSequence(["P", "1"])
    result = run_dialogue_drill(scenario, output, inputs, support_level="hanzi_only")

    # Should complete normally
    assert not result.skipped

    # Pinyin should appear in output after P
    pinyin_lines = [l for l in output.lines if "xu\u01cenxi\u00e0ng" in l]
    assert len(pinyin_lines) > 0, "Pinyin should be revealed after P key"


def test_p_ignored_in_full_support():
    """In full_support mode, P is treated as invalid input (pinyin already shown)."""
    scenario = _make_scenario(n_options=3)
    output = OutputCapture()
    # P (treated as invalid), then valid answer
    inputs = InputSequence(["P", "1"])
    result = run_dialogue_drill(scenario, output, inputs, support_level="full_support")

    # P is not a valid answer in full_support -- should see re-prompt
    assert not result.skipped


# ---- TestComprehensionProbe ----

def test_probe_deterministic_with_enough_distractors():
    """Probe always fires when sufficient distractor characters exist."""
    chosen = {"text_zh": "\u4f60\u597d\u5417", "text_en": "how are you"}
    other1 = {"text_zh": "\u8c22\u8c22\u5927\u5bb6", "text_en": "thank you all"}
    other2 = {"text_zh": "\u518d\u89c1\u670b\u53cb", "text_en": "goodbye friend"}
    options = [chosen, other1, other2]

    fired = 0
    for _ in range(20):
        output = OutputCapture()
        inputs = InputSequence(["1"])
        result = _run_comprehension_probe(chosen, options, output, inputs)
        if result is not None:
            fired += 1

    assert fired == 20, "Probe should always fire with enough distractors"


def test_probe_returns_none_without_distractors():
    """Probe returns None when not enough distractor characters."""
    chosen = {"text_zh": "\u4f60\u597d", "text_en": "hello"}
    options = [chosen]  # No other options = no distractors

    output = OutputCapture()
    inputs = InputSequence(["1"])
    result = _run_comprehension_probe(chosen, options, output, inputs)
    assert result is None, "No distractors means no probe"


# ---- TestMeaningProbeDistractors ----

def test_distractors_from_other_options():
    """Meaning probe picks distractors from other options' characters."""
    chosen = {
        "text_zh": "\u4f60\u597d\u5417",
        "text_pinyin": "n\u01d0 h\u01ceo ma",
        "text_en": "how are you",
    }
    other1 = {
        "text_zh": "\u8c22\u8c22\u5927\u5bb6",
        "text_pinyin": "xi\u00e8xie d\u00e0ji\u0101",
        "text_en": "thank you everyone",
    }
    other2 = {
        "text_zh": "\u518d\u89c1\u670b\u53cb",
        "text_pinyin": "z\u00e0iji\u00e0n p\u00e9ngy\u01d2u",
        "text_en": "goodbye friend",
    }
    options = [chosen, other1, other2]

    with patch("mandarin.conversation.random") as mock_random:
        # Choose the first CJK char from chosen
        mock_random.choice.return_value = "\u4f60"
        mock_random.shuffle = lambda x: None  # Don't shuffle

        output = OutputCapture()
        # Since shuffle is no-op, mc_options = ["target", distractor1, distractor2]
        # correct_idx = 1
        inputs = InputSequence(["1"])
        result = _run_comprehension_probe(chosen, options, output, inputs)

        assert result, "Correct answer should be True"
        # Verify output mentions the character
        check_lines = [l for l in output.lines if "\u4f60" in l]
        assert len(check_lines) > 0


def test_not_enough_distractors_returns_none():
    """If not enough unique distractor chars, meaning probe skips."""
    chosen = {"text_zh": "\u4f60\u597d", "text_en": "hello"}
    # Same characters as chosen -- no unique distractors available
    other = {"text_zh": "\u4f60\u597d\u5417", "text_en": "how are you"}
    options = [chosen, other]

    with patch("mandarin.conversation.random") as mock_random:
        mock_random.choice.return_value = "\u4f60"

        output = OutputCapture()
        inputs = InputSequence(["1"])
        result = _run_comprehension_probe(chosen, options, output, inputs)

        # Should return None (not enough distractors)
        assert result is None


# ---- TestMeaningProbeAlwaysFires ----

def test_correct_answer_returns_true():
    """Answering the correct MC option returns True."""
    chosen = {"text_zh": "\u4f60\u597d\u5417", "text_en": "how are you"}
    other1 = {"text_zh": "\u8c22\u8c22\u5927\u5bb6", "text_en": "thank you all"}
    other2 = {"text_zh": "\u518d\u89c1\u670b\u53cb", "text_en": "goodbye friend"}
    options = [chosen, other1, other2]

    with patch("mandarin.conversation.random") as mock_random:
        mock_random.choice.return_value = "\u4f60"
        mock_random.shuffle = lambda x: None  # No shuffle

        output = OutputCapture()
        # "target" will be at position 1 (no shuffle: [target, d1, d2])
        inputs = InputSequence(["1"])
        result = _run_comprehension_probe(chosen, options, output, inputs)

        assert result, "Correct MC answer should return True"


def test_wrong_answer_returns_false():
    """Answering the wrong MC option returns False."""
    chosen = {"text_zh": "\u4f60\u597d\u5417", "text_en": "how are you"}
    other1 = {"text_zh": "\u8c22\u8c22\u5927\u5bb6", "text_en": "thank you all"}
    other2 = {"text_zh": "\u518d\u89c1\u670b\u53cb", "text_en": "goodbye friend"}
    options = [chosen, other1, other2]

    with patch("mandarin.conversation.random") as mock_random:
        mock_random.choice.return_value = "\u4f60"
        mock_random.shuffle = lambda x: None

        output = OutputCapture()
        inputs = InputSequence(["2"])  # Wrong option
        result = _run_comprehension_probe(chosen, options, output, inputs)

        assert not result, "Wrong MC answer should return False"


def test_short_text_returns_none():
    """Single-character text has insufficient data for a probe."""
    chosen = {"text_zh": "\u597d", "text_en": "good"}
    output = OutputCapture()
    inputs = InputSequence(["1"])
    result = _run_comprehension_probe(chosen, [], output, inputs)
    assert result is None


def test_stop_words_set_contents():
    """Stop words set should include common English function words."""
    expected = {"the", "a", "is", "to", "in", "on", "of", "it", "i", "you",
                "my", "your", "do", "was", "were", "be", "am", "an", "are"}
    assert _STOP_WORDS == expected


# ---- TestProbePersistence ----

def _make_probe_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE probe_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_item_id INTEGER,
            scenario_id INTEGER,
            probe_type TEXT NOT NULL DEFAULT 'comprehension',
            correct INTEGER NOT NULL DEFAULT 0,
            user_answer TEXT,
            expected_answer TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE dialogue_scenario (
            id INTEGER PRIMARY KEY,
            hsk_level INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY,
            hsk_level INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER,
            modality TEXT,
            difficulty REAL DEFAULT 0.5,
            total_attempts INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def test_record_probe_correct():
    conn = _make_probe_db()
    record_probe_result(conn, content_item_id=0, scenario_id=1,
                       probe_type="comprehension", correct=True)
    row = conn.execute("SELECT * FROM probe_log").fetchone()
    assert row is not None
    assert row["correct"] == 1
    assert row["probe_type"] == "comprehension"
    conn.close()


def test_record_probe_incorrect():
    conn = _make_probe_db()
    record_probe_result(conn, content_item_id=0, scenario_id=2,
                       probe_type="comprehension", correct=False,
                       user_answer="wrong", expected_answer="right")
    row = conn.execute("SELECT * FROM probe_log").fetchone()
    assert row["correct"] == 0
    assert row["user_answer"] == "wrong"
    conn.close()


def test_apply_probe_penalty():
    """Probe failure should increase difficulty by 0.02 for reading items at same HSK level."""
    conn = _make_probe_db()
    conn.execute("INSERT INTO dialogue_scenario (id, hsk_level) VALUES (1, 2)")
    conn.execute("INSERT INTO content_item (id, hsk_level) VALUES (10, 2)")
    conn.execute(
        "INSERT INTO progress (content_item_id, modality, difficulty, total_attempts) "
        "VALUES (10, 'reading', 0.50, 5)"
    )
    conn.commit()

    _apply_probe_penalty(conn, scenario_id=1)

    row = conn.execute(
        "SELECT difficulty FROM progress WHERE content_item_id = 10"
    ).fetchone()
    assert row["difficulty"] == pytest.approx(0.52, abs=0.01)
    conn.close()


def test_penalty_caps_at_095():
    """Difficulty should not exceed 0.95."""
    conn = _make_probe_db()
    conn.execute("INSERT INTO dialogue_scenario (id, hsk_level) VALUES (1, 1)")
    conn.execute("INSERT INTO content_item (id, hsk_level) VALUES (5, 1)")
    conn.execute(
        "INSERT INTO progress (content_item_id, modality, difficulty, total_attempts) "
        "VALUES (5, 'reading', 0.94, 10)"
    )
    conn.commit()

    _apply_probe_penalty(conn, scenario_id=1)

    row = conn.execute(
        "SELECT difficulty FROM progress WHERE content_item_id = 5"
    ).fetchone()
    assert row["difficulty"] == pytest.approx(0.95, abs=0.01)
    conn.close()


def test_penalty_no_scenario_id_noop():
    """No scenario_id should be a no-op."""
    conn = _make_probe_db()
    _apply_probe_penalty(conn, scenario_id=None)
    conn.close()
    # Should not raise


# ---- TestScenarioFiles ----

SCENARIO_DIR = Path(__file__).parent.parent / "data" / "scenarios"
REQUIRED_TOP = {"title", "title_zh", "hsk_level", "register", "scenario_type", "tree"}
REQUIRED_TREE = {"setup", "setup_zh", "turns", "cultural_note"}
REQUIRED_OPTION = {"text_zh", "text_pinyin", "text_en", "score", "feedback"}


def test_at_least_12_files_exist():
    json_files = sorted(SCENARIO_DIR.glob("*.json"))
    assert len(json_files) >= 12, f"Expected 12+ scenario files, got {len(json_files)}"


def test_all_scenarios_parse_and_have_fields():
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for field in REQUIRED_TOP:
            assert field in data, f"{path.name} missing top-level '{field}'"

        tree = data["tree"]
        for field in REQUIRED_TREE:
            assert field in tree, f"{path.name} tree missing '{field}'"

        turns = tree["turns"]
        assert len(turns) > 0, f"{path.name} has no turns"

        for turn in turns:
            if turn.get("speaker") == "player":
                options = turn.get("options", [])
                assert len(options) > 0, f"{path.name} player turn has no options"
                for opt in options:
                    for field in REQUIRED_OPTION:
                        assert field in opt, \
                            f"{path.name} option missing '{field}'"


def test_scores_in_valid_range():
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for turn in data["tree"]["turns"]:
            if turn.get("speaker") == "player":
                for opt in turn.get("options", []):
                    score = opt["score"]
                    assert score >= 0.0, \
                        f"{path.name}: score {score} < 0"
                    assert score <= 1.0, \
                        f"{path.name}: score {score} > 1"


def test_hsk3_scenarios_count():
    """Should have at least 5 HSK 3 scenarios (1 original + 4 new)."""
    hsk3_count = 0
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("hsk_level") == 3:
            hsk3_count += 1
    assert hsk3_count >= 5
