"""Edge case tests — empty state, degenerate inputs, boundary conditions, fuzz.

Targets code paths that caused or could cause session crashes, organized by:
A. Empty state — 0 items, 0 sessions, 0 progress
B. Degenerate inputs — None hanzi, empty pinyin, 1-option MC, 0-option dialogue
C. Boundary conditions — empty mastery dict, struggle pivot at threshold
D. Fuzz-like input — garbage user input, special commands, edge characters
"""

import random
import sqlite3
import pytest
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import patch

from tests.conftest import OutputCapture, InputSequence
from tests.shared_db import make_test_db
from mandarin.scheduler import SessionPlan, DrillItem, _validate_plan, _interleave
from mandarin.drills.base import (
    DrillResult, _handle_confidence, _handle_narrowed_choice, _run_mc_input,
    check_confidence_input, classify_error_cause, cause_to_error_type,
)
from mandarin.conversation import run_dialogue_drill
from mandarin.db.progress import (
    record_attempt, get_mastery_by_hsk, _compute_srs_update,
    _compute_mastery_transition, _compute_retention_update,
)


# ── Helpers ──────────────────────────────────────────

def _make_item(**overrides):
    """Minimal content_item dict for testing."""
    d = {
        "id": 1,
        "hanzi": "你好",
        "pinyin": "nǐ hǎo",
        "english": "hello",
        "hsk_level": 1,
        "item_type": "vocab",
        "register": "neutral",
        "content_lens": None,
        "times_shown": 0,
        "difficulty": 0.5,
        "mastery_stage": "seen",
        "streak_correct": 0,
        "total_attempts": 0,
        "total_correct": 0,
        "status": "drill_ready",
    }
    d.update(overrides)
    return d


def _make_drill_item(**overrides):
    """Minimal DrillItem for testing."""
    defaults = {
        "content_item_id": 1,
        "hanzi": "你好",
        "pinyin": "nǐ hǎo",
        "english": "hello",
        "modality": "reading",
        "drill_type": "mc",
    }
    defaults.update(overrides)
    return DrillItem(**defaults)


def _progress_row(**overrides):
    """Minimal progress row dict for pure-function tests."""
    d = {
        "ease_factor": 2.5,
        "interval_days": 1,
        "repetitions": 0,
        "streak_correct": 0,
        "streak_incorrect": 0,
        "mastery_stage": "seen",
        "historically_weak": 0,
        "weak_cycle_count": 0,
        "stable_since_date": None,
        "successes_while_stable": 0,
        "total_correct": 0,
        "difficulty": 0.5,
        "half_life_days": 1.0,
        "last_review_date": None,
        "distinct_review_days": 0,
        "drill_types_seen": "",
        "total_attempts": 0,
        "avg_response_ms": None,
    }
    d.update(overrides)
    return d


# ══════════════════════════════════════════════════════
# A. Empty state
# ══════════════════════════════════════════════════════

class TestEmptyState:
    """New user: 0 items, 0 sessions, 0 progress rows."""

    def test_get_mastery_by_hsk_no_items(self, test_db):
        """get_mastery_by_hsk returns empty dict when no content items exist."""
        conn, _ = test_db
        result = get_mastery_by_hsk(conn)
        assert result == {}

    def test_validate_plan_empty_drills(self):
        """_validate_plan handles plan with zero drills."""
        plan = SessionPlan(session_type="standard", drills=[])
        result = _validate_plan(plan)
        assert result.drills == []
        assert result.session_type == "standard"

    def test_interleave_empty_list(self):
        """_interleave handles empty list."""
        assert _interleave([]) == []

    def test_interleave_single_item(self):
        """_interleave handles single-item list."""
        d = _make_drill_item()
        assert _interleave([d]) == [d]

    def test_dialogue_no_turns(self):
        """Dialogue with zero turns returns skipped result."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": '{"setup": "test", "turns": []}',
        }
        out = OutputCapture()
        inp = InputSequence([])
        result = run_dialogue_drill(scenario, out, inp)
        assert result.skipped is True

    def test_dialogue_corrupted_json(self):
        """Dialogue with invalid JSON returns skipped result."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": "NOT JSON {{{{",
        }
        out = OutputCapture()
        inp = InputSequence([])
        result = run_dialogue_drill(scenario, out, inp)
        assert result.skipped is True

    def test_srs_update_zero_state(self):
        """SRS update from zero state doesn't crash."""
        row = _progress_row()
        result = _compute_srs_update(row, correct=True, confidence="full",
                                     response_ms=500, mastery_stage="seen")
        assert result["streak_correct"] == 1
        assert result["ease"] >= 2.5

    def test_mastery_transition_zero_state(self):
        """Mastery transition from zero state stays at 'seen' (streak=1 < threshold=2)."""
        row = _progress_row()
        result = _compute_mastery_transition(
            row, correct=True, confidence="full",
            streak_correct=1, streak_incorrect=0,
            drill_type="mc", distinct_days=1,
            total_after=1, drill_type_count=1,
        )
        # streak=1 < PROMOTE_PASSED_ONCE_STREAK=2, so stays at 'seen'
        assert result["mastery_stage"] == "seen"

    def test_retention_update_zero_state(self):
        """Retention update from zero state produces valid half-life."""
        row = _progress_row()
        result = _compute_retention_update(row, correct=True, confidence="full")
        assert result["half_life"] > 0
        assert 0 <= result["p_recall"] <= 1


# ══════════════════════════════════════════════════════
# B. Degenerate inputs
# ══════════════════════════════════════════════════════

class TestDegenerateInputs:
    """Degenerate item data, missing fields, minimal options."""

    def test_record_attempt_bad_item_id_zero(self, test_db):
        """record_attempt with item_id=0 is silently skipped."""
        conn, _ = test_db
        # Should not crash — just logs and returns
        record_attempt(conn, content_item_id=0, modality="reading", correct=True)

    def test_record_attempt_bad_item_id_negative(self, test_db):
        """record_attempt with negative item_id is silently skipped."""
        conn, _ = test_db
        record_attempt(conn, content_item_id=-5, modality="reading", correct=True)

    def test_record_attempt_bad_item_id_string(self, test_db):
        """record_attempt with string item_id is silently skipped."""
        conn, _ = test_db
        record_attempt(conn, content_item_id="abc", modality="reading", correct=True)

    def test_record_attempt_invalid_modality(self, test_db):
        """record_attempt with invalid modality defaults to 'reading'."""
        conn, _ = test_db
        # Insert a content item first
        conn.execute("""
            INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level, status)
            VALUES (1, '你好', 'nǐ hǎo', 'hello', 1, 'drill_ready')
        """)
        conn.commit()
        # Should not crash — modality gets defaulted
        record_attempt(conn, content_item_id=1, modality="telepathy",
                       correct=True)
        # Verify it was recorded with default modality
        row = conn.execute(
            "SELECT modality FROM progress WHERE content_item_id = 1"
        ).fetchone()
        assert row["modality"] == "reading"

    def test_record_attempt_invalid_confidence(self, test_db):
        """record_attempt with invalid confidence defaults to 'full'."""
        conn, _ = test_db
        conn.execute("""
            INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level, status)
            VALUES (1, '你好', 'nǐ hǎo', 'hello', 1, 'drill_ready')
        """)
        conn.commit()
        record_attempt(conn, content_item_id=1, modality="reading",
                       correct=True, confidence="very_confident")

    def test_dialogue_empty_options(self):
        """Player turn with zero options is skipped gracefully."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Say hello",
                     "options": []},
                ],
            },
        }
        out = OutputCapture()
        inp = InputSequence([])
        result = run_dialogue_drill(scenario, out, inp)
        # Should complete without crash — no player turns scored
        assert result.score == 0.0
        assert not result.skipped

    def test_dialogue_missing_text_zh(self):
        """Option without text_zh doesn't crash."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"score": 1.0, "feedback": "Good"},
                         {"text_zh": "不好", "score": 0.0, "feedback": "Wrong"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        inp = InputSequence(["1"])
        result = run_dialogue_drill(scenario, out, inp)
        assert not result.skipped

    def test_validate_plan_all_invalid_drills(self):
        """Plan where all drills have invalid modalities becomes empty."""
        plan = SessionPlan(
            session_type="standard",
            drills=[
                _make_drill_item(modality="telepathy", drill_type="mc"),
                _make_drill_item(modality="xray_vision", drill_type="mc"),
            ],
        )
        result = _validate_plan(plan)
        assert len(result.drills) == 0

    def test_validate_plan_all_invalid_drill_types(self):
        """Plan where all drills have invalid drill_types becomes empty."""
        plan = SessionPlan(
            session_type="standard",
            drills=[
                _make_drill_item(drill_type="telepathy_quiz"),
                _make_drill_item(drill_type="crystal_ball"),
            ],
        )
        result = _validate_plan(plan)
        assert len(result.drills) == 0

    def test_classify_error_cause_empty_strings(self):
        """classify_error_cause with empty answers returns 'other'."""
        assert classify_error_cause("", "", "mc", _make_item()) == "other"
        assert classify_error_cause("", "hello", "mc", _make_item()) == "other"
        assert classify_error_cause("hi", "", "mc", _make_item()) == "other"

    def test_cause_to_error_type_unknown_cause(self):
        """Unknown cause maps to fallback."""
        assert cause_to_error_type("totally_unknown") == "other"
        assert cause_to_error_type("something_weird", fallback="vocab") == "vocab"

    def test_check_confidence_various(self):
        """check_confidence_input handles various edge inputs."""
        assert check_confidence_input("?") == "half"
        assert check_confidence_input("N") == "unknown"
        assert check_confidence_input("n") == "unknown"
        assert check_confidence_input("") is None
        assert check_confidence_input("  ? ") == "half"
        assert check_confidence_input("  N  ") == "unknown"
        assert check_confidence_input("hello") is None
        assert check_confidence_input("1") is None


# ══════════════════════════════════════════════════════
# C. Boundary conditions
# ══════════════════════════════════════════════════════

class TestBoundaryConditions:
    """Threshold-exact values and edge-of-range behavior."""

    def test_mastery_empty_dict(self, test_db):
        """get_mastery_by_hsk with items but no progress returns correct counts."""
        conn, _ = test_db
        conn.execute("""
            INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level, status)
            VALUES (1, '你好', 'nǐ hǎo', 'hello', 1, 'drill_ready')
        """)
        conn.commit()
        mastery = get_mastery_by_hsk(conn)
        assert 1 in mastery
        assert mastery[1]["total"] == 1
        assert mastery[1]["mastered"] == 0
        assert mastery[1]["pct"] == 0

    def test_validate_plan_dedup_preserves_dialogues(self):
        """Dedup skips dialogue drills (they use content_item_id=0)."""
        plan = SessionPlan(
            session_type="standard",
            drills=[
                _make_drill_item(content_item_id=0, drill_type="dialogue",
                                 modality="reading"),
                _make_drill_item(content_item_id=0, drill_type="dialogue",
                                 modality="reading"),
            ],
        )
        result = _validate_plan(plan)
        # Both dialogues should survive dedup
        assert len(result.drills) == 2

    def test_validate_plan_dedup_real_ids(self):
        """Duplicate real item_ids are deduplicated to one."""
        plan = SessionPlan(
            session_type="standard",
            drills=[
                _make_drill_item(content_item_id=42),
                _make_drill_item(content_item_id=42),
            ],
        )
        result = _validate_plan(plan)
        assert len(result.drills) == 1

    def test_validate_plan_unknown_session_type(self):
        """Unknown session_type defaults to 'standard'."""
        plan = SessionPlan(
            session_type="speed_run",
            drills=[],
        )
        result = _validate_plan(plan)
        assert result.session_type == "standard"

    def test_srs_streak_boundary_correct(self):
        """SRS update at streak=0 → streak=1 on correct answer."""
        row = _progress_row(streak_correct=0, streak_incorrect=3)
        result = _compute_srs_update(row, correct=True, confidence="full",
                                     response_ms=500, mastery_stage="seen")
        assert result["streak_correct"] == 1
        assert result["streak_incorrect"] == 0

    def test_srs_streak_boundary_wrong(self):
        """SRS update resets streak on wrong answer."""
        row = _progress_row(streak_correct=5, streak_incorrect=0)
        result = _compute_srs_update(row, correct=False, confidence="full",
                                     response_ms=500, mastery_stage="stabilizing")
        assert result["streak_correct"] == 0
        assert result["streak_incorrect"] == 1

    def test_mastery_seen_to_passed_once_at_streak_2(self):
        """Mastery promotes from seen to passed_once at streak=2 (threshold)."""
        row = _progress_row(mastery_stage="seen")
        result = _compute_mastery_transition(
            row, correct=True, confidence="full",
            streak_correct=2, streak_incorrect=0,
            drill_type="mc", distinct_days=1,
            total_after=2, drill_type_count=1,
        )
        assert result["mastery_stage"] == "passed_once"

    def test_mastery_seen_stays_at_streak_1(self):
        """Mastery stays at 'seen' when streak=1 (below threshold=2)."""
        row = _progress_row(mastery_stage="seen")
        result = _compute_mastery_transition(
            row, correct=True, confidence="full",
            streak_correct=1, streak_incorrect=0,
            drill_type="mc", distinct_days=1,
            total_after=1, drill_type_count=1,
        )
        assert result["mastery_stage"] == "seen"

    def test_mastery_no_promote_on_narrowed_confidence(self):
        """Mastery does NOT promote when confidence is 'narrowed'."""
        row = _progress_row(mastery_stage="seen")
        result = _compute_mastery_transition(
            row, correct=True, confidence="narrowed",
            streak_correct=1, streak_incorrect=0,
            drill_type="mc", distinct_days=1,
            total_after=1, drill_type_count=1,
        )
        # Narrowed confidence doesn't count for promotion
        assert result["mastery_stage"] == "seen"

    def test_mastery_demotion_threshold(self):
        """Demotion of stable item happens at streak_incorrect threshold."""
        row = _progress_row(
            mastery_stage="stable",
            total_correct=5,  # Low total → demotion threshold = 3
        )
        # At streak_incorrect=3, should demote
        result = _compute_mastery_transition(
            row, correct=False, confidence="full",
            streak_correct=0, streak_incorrect=3,
            drill_type="mc", distinct_days=5,
            total_after=10, drill_type_count=3,
        )
        assert result["mastery_stage"] == "decayed"

    def test_mastery_demotion_high_history_resilience(self):
        """Items with many correct answers have higher demotion threshold."""
        row = _progress_row(
            mastery_stage="stable",
            total_correct=50,  # High history → threshold = 3 + 2 = 5
        )
        # At streak_incorrect=3, should NOT demote (threshold is higher)
        result = _compute_mastery_transition(
            row, correct=False, confidence="full",
            streak_correct=0, streak_incorrect=3,
            drill_type="mc", distinct_days=5,
            total_after=55, drill_type_count=3,
        )
        assert result["mastery_stage"] == "stable"

    def test_retention_zero_half_life(self):
        """Retention update doesn't crash with zero-ish half-life."""
        row = _progress_row(half_life_days=0.01, difficulty=0.9)
        result = _compute_retention_update(row, correct=True, confidence="full")
        assert result["half_life"] > 0

    def test_interleave_two_items(self):
        """_interleave with exactly 2 items returns them unchanged."""
        d1 = _make_drill_item(content_item_id=1)
        d2 = _make_drill_item(content_item_id=2)
        result = _interleave([d1, d2])
        assert len(result) == 2


# ══════════════════════════════════════════════════════
# D. Fuzz-like input
# ══════════════════════════════════════════════════════

class TestFuzzInput:
    """Garbage, out-of-range, and unexpected user input."""

    def test_dialogue_input_out_of_range(self):
        """Dialogue gracefully handles input '999' (out of range)."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                         {"text_zh": "谢谢", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        # 3 invalid inputs → falls through to best option
        inp = InputSequence(["999", "999", "999"])
        result = run_dialogue_drill(scenario, out, inp)
        assert not result.skipped

    def test_dialogue_input_empty_string(self):
        """Dialogue handles empty string input without crash."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        inp = InputSequence(["", "", ""])
        result = run_dialogue_drill(scenario, out, inp)
        assert not result.skipped

    def test_dialogue_input_unicode_garbage(self):
        """Dialogue handles unicode garbage input."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        inp = InputSequence(["🎃💀🎉", "é̷̗̓", "999"])
        result = run_dialogue_drill(scenario, out, inp)
        assert not result.skipped

    def test_dialogue_quit_mid_turn(self):
        """Dialogue Q input quits immediately."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        inp = InputSequence(["Q"])
        result = run_dialogue_drill(scenario, out, inp)
        assert result.skipped is True

    def test_dialogue_back_mid_turn(self):
        """Dialogue B input exits with skip."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        inp = InputSequence(["B"])
        result = run_dialogue_drill(scenario, out, inp)
        assert result.skipped is True

    def test_mc_input_out_of_range(self):
        """_run_mc_input with out-of-range choice returns raw string."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["999"])
        result = _run_mc_input(
            item, ["hello", "world", "bye"], "hello",
            "reading", "mc", out, inp,
        )
        # Out of range returns the raw string
        assert result == "999"

    def test_mc_input_negative_number(self):
        """_run_mc_input with negative number returns raw string."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["-1"])
        result = _run_mc_input(
            item, ["hello", "world", "bye"], "hello",
            "reading", "mc", out, inp,
        )
        assert result == "-1"

    def test_mc_input_quit(self):
        """_run_mc_input with Q returns skip DrillResult."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["Q"])
        result = _run_mc_input(
            item, ["hello", "world", "bye"], "hello",
            "reading", "mc", out, inp,
        )
        assert isinstance(result, DrillResult)
        assert result.skipped is True

    def test_mc_input_confidence_half(self):
        """_run_mc_input with ? returns half-confidence DrillResult."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["?"])
        result = _run_mc_input(
            item, ["hello", "world", "bye"], "hello",
            "reading", "mc", out, inp,
        )
        assert isinstance(result, DrillResult)
        assert result.confidence == "half"
        assert result.score == 0.5

    def test_mc_input_confidence_unknown_narrows(self):
        """_run_mc_input with N narrows to 2 choices when >2 options."""
        item = _make_item()
        out = OutputCapture()
        # N narrows, then pick option 1
        inp = InputSequence(["N", "1"])
        result = _run_mc_input(
            item, ["hello", "world", "bye", "test"], "hello",
            "reading", "mc", out, inp,
        )
        assert isinstance(result, DrillResult)

    def test_handle_narrowed_choice_quit(self):
        """Narrowed choice Q exits cleanly."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["Q"])
        result = _handle_narrowed_choice(
            item, "reading", "mc", "hello",
            ["hello", "world", "bye"], out, inp,
        )
        assert result.skipped is True

    def test_handle_narrowed_choice_second_N(self):
        """Narrowed choice with second N reveals answer."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["N"])
        result = _handle_narrowed_choice(
            item, "reading", "mc", "hello",
            ["hello", "world", "bye"], out, inp,
        )
        assert result.confidence == "unknown"
        assert result.score == 0.0

    def test_handle_narrowed_choice_invalid_then_valid(self):
        """Narrowed choice handles invalid input then valid input."""
        item = _make_item()
        out = OutputCapture()
        # First invalid, then valid
        inp = InputSequence(["abc", "1"])
        result = _handle_narrowed_choice(
            item, "reading", "mc", "hello",
            ["hello", "world", "bye"], out, inp,
        )
        # Got a result (correct or not depending on shuffle)
        assert isinstance(result, DrillResult)
        assert not result.skipped

    def test_handle_narrowed_choice_three_invalid(self):
        """Narrowed choice with 3 invalid inputs treats last as wrong."""
        item = _make_item()
        out = OutputCapture()
        inp = InputSequence(["abc", "xyz", "!!!"])
        result = _handle_narrowed_choice(
            item, "reading", "mc", "hello",
            ["hello", "world", "bye"], out, inp,
        )
        assert isinstance(result, DrillResult)
        # The last invalid input is treated as a wrong answer
        assert not result.correct

    def test_srs_unknown_confidence(self):
        """SRS update with 'unknown' confidence resets interval."""
        row = _progress_row(streak_correct=3, interval_days=10)
        result = _compute_srs_update(row, correct=False, confidence="unknown",
                                     response_ms=0, mastery_stage="stabilizing")
        # Unknown confidence resets interval to initial
        assert result["interval"] == 1  # INTERVAL_INITIAL

    def test_srs_narrowed_confidence(self):
        """SRS update with 'narrowed' confidence reduces interval."""
        row = _progress_row(streak_correct=3, interval_days=10)
        result = _compute_srs_update(row, correct=True, confidence="narrowed",
                                     response_ms=500, mastery_stage="stabilizing")
        # Narrowed confidence dampens interval
        assert result["interval"] < 10

    def test_dialogue_all_wrong(self):
        """Dialogue where every turn is wrong completes with low score."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "score": 0.0, "feedback": "Wrong"},
                         {"text_zh": "谢谢", "score": 0.0, "feedback": "Wrong"},
                     ]},
                    {"speaker": "npc", "text_zh": "你是谁？"},
                    {"speaker": "player", "prompt_en": "Introduce yourself",
                     "options": [
                         {"text_zh": "我是学生", "score": 1.0, "feedback": "Good"},
                         {"text_zh": "太贵了", "score": 0.0, "feedback": "Wrong"},
                         {"text_zh": "不知道", "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        # Pick wrong options (3 = last option, which after shuffle is unpredictable,
        # but we seed random for determinism)
        random.seed(42)
        inp = InputSequence(["3", "3"])
        result = run_dialogue_drill(scenario, out, inp)
        assert not result.skipped
        assert result.score is not None

    def test_dialogue_pinyin_assist_then_answer(self):
        """Dialogue P key for pinyin assist in hanzi_only mode, then answer."""
        scenario = {
            "id": 1,
            "title": "Test",
            "tree_json": {
                "setup": "test",
                "turns": [
                    {"speaker": "npc", "text_zh": "你好"},
                    {"speaker": "player", "prompt_en": "Respond",
                     "options": [
                         {"text_zh": "你好", "text_pinyin": "nǐ hǎo",
                          "score": 1.0, "feedback": "Good"},
                         {"text_zh": "再见", "text_pinyin": "zài jiàn",
                          "score": 0.0, "feedback": "Wrong"},
                     ]},
                ],
            },
        }
        out = OutputCapture()
        # P for assist, then pick 1
        inp = InputSequence(["P", "1"])
        result = run_dialogue_drill(scenario, out, inp,
                                    support_level="hanzi_only")
        assert not result.skipped
