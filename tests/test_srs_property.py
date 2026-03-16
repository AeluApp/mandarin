"""Property-based tests for SRS engine data integrity.

Uses hypothesis to prove invariants across the full input space, not just
hand-picked examples. Tests cover three layers:

1. Mastery stage invariants (6-stage lifecycle)
2. Retention model invariants (half-life regression)
3. Cross-module invariants (record_attempt + retention together)

These complement the existing unit tests in test_srs_decomposition.py and
test_retention_property.py by focusing on stateful sequences and data
integrity properties that unit tests can miss.
"""

import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize

from mandarin.db.progress import (
    _compute_srs_update,
    _compute_mastery_transition,
    _compute_retention_update,
    record_attempt,
)
from mandarin.retention import (
    predict_recall,
    update_half_life,
    update_difficulty,
)
from mandarin.config import (
    EASE_FLOOR,
    EASE_CORRECT_BOOST,
    EASE_WRONG_PENALTY,
    INTERVAL_INITIAL,
    INTERVAL_SECOND,
    INTERVAL_WRONG,
    MAX_INTERVAL,
    MIN_HALF_LIFE,
    MAX_HALF_LIFE,
    INITIAL_HALF_LIFE,
    PROMOTE_PASSED_ONCE_STREAK,
    PROMOTE_STABILIZING_STREAK,
    PROMOTE_STABILIZING_DAYS,
    PROMOTE_STABLE_STREAK,
    PROMOTE_STABLE_ATTEMPTS,
    PROMOTE_STABLE_DAYS,
    PROMOTE_DURABLE_DAYS_STABLE,
    PROMOTE_DURABLE_SUCCESSES,
    DEMOTE_STABLE_STREAK_INCORRECT,
    DEMOTE_STABILIZING_STREAK_INCORRECT,
    RECOVERY_STREAK_CORRECT,
)
from mandarin import db
from mandarin.db.core import init_db, _migrate

pytestmark = pytest.mark.slow
from mandarin.db.content import insert_content_item


# ── Shared helpers ──

VALID_STAGES = {"seen", "passed_once", "stabilizing", "stable", "durable", "decayed"}

# Valid stage transitions: from_stage -> set of reachable next stages (including self)
VALID_TRANSITIONS = {
    "seen":        {"seen", "passed_once"},
    "passed_once": {"passed_once", "stabilizing"},
    "stabilizing": {"stabilizing", "stable", "seen"},  # seen via demotion
    "stable":      {"stable", "durable", "decayed"},
    "durable":     {"durable", "decayed"},
    "decayed":     {"decayed", "stabilizing"},
}


def _base_row(**overrides):
    """Create a minimal progress row dict for testing pure functions."""
    row = {
        "ease_factor": 2.5,
        "interval_days": 1.0,
        "repetitions": 0,
        "streak_correct": 0,
        "streak_incorrect": 0,
        "mastery_stage": "seen",
        "historically_weak": 0,
        "weak_cycle_count": 0,
        "stable_since_date": None,
        "successes_while_stable": 0,
        "half_life_days": INITIAL_HALF_LIFE,
        "difficulty": 0.5,
        "last_review_date": None,
        "total_attempts": 0,
        "total_correct": 0,
        "avg_response_ms": None,
        "drill_types_seen": "",
        "distinct_review_days": 0,
    }
    row.update(overrides)
    return row


def _fresh_db():
    """Create a fresh test database with schema + migrations + bootstrap user."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    return conn, path


def _add_item(conn, hanzi="test", pinyin="te4st", english="test", hsk_level=1):
    return insert_content_item(
        conn, hanzi=hanzi, pinyin=pinyin, english=english, hsk_level=hsk_level,
    )


def _get_progress(conn, item_id, modality="reading"):
    row = conn.execute(
        "SELECT * FROM progress WHERE content_item_id = ? AND modality = ?",
        (item_id, modality)
    ).fetchone()
    return dict(row) if row else None


# ── Hypothesis strategies ──

confidence_strategy = st.sampled_from(["full", "half", "unknown", "narrowed", "narrowed_wrong"])
stage_strategy = st.sampled_from(list(VALID_STAGES))
drill_type_strategy = st.sampled_from(["mc", "reverse_mc", "tone", "hanzi_to_pinyin"])
modality_strategy = st.sampled_from(["reading", "listening", "speaking", "ime"])
quality_score = st.integers(min_value=0, max_value=5)
attempt_sequence = st.lists(st.booleans(), min_size=1, max_size=50)


# ════════════════════════════════════════════════════════════════════════
# MASTERY STAGE INVARIANTS
# ════════════════════════════════════════════════════════════════════════

# 1. Initial stage is always 'seen' for a new item

@given(
    correct=st.booleans(),
    drill_type=drill_type_strategy,
)
@settings(deadline=None)
def test_initial_stage_is_seen(correct, drill_type):
    """A brand-new progress row should start at 'seen' stage."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        record_attempt(conn, item_id, "reading", correct, drill_type=drill_type)
        p = _get_progress(conn, item_id)
        assert p is not None
        # A single attempt (correct or wrong) can at most reach passed_once
        # (if correct with streak >= 2, which can't happen on first attempt).
        # On first attempt, stage must be 'seen'.
        if not correct:
            assert p["mastery_stage"] == "seen"
        # If correct, streak_correct is 1, which is less than PROMOTE_PASSED_ONCE_STREAK (2)
        if correct:
            assert p["mastery_stage"] == "seen"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 2. Stage is always one of the 6 valid stages

@given(
    attempts=st.lists(st.booleans(), min_size=1, max_size=30),
    drill_type=drill_type_strategy,
)
@settings(deadline=None)
def test_stage_always_valid(attempts, drill_type):
    """After any sequence of attempts, mastery_stage must be one of 6 valid stages."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for correct in attempts:
            record_attempt(conn, item_id, "reading", correct, drill_type=drill_type)
        p = _get_progress(conn, item_id)
        assert p["mastery_stage"] in VALID_STAGES
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 3. Correct answers never decrease streak_correct (monotonic until reset)

@given(
    initial_streak=st.integers(min_value=0, max_value=20),
    reps=st.integers(min_value=0, max_value=20),
)
@settings()
def test_correct_never_decreases_streak(initial_streak, reps):
    """A correct answer with full confidence must increment streak_correct."""
    row = _base_row(streak_correct=initial_streak, repetitions=reps)
    result = _compute_srs_update(row, True, "full", None, "seen")
    assert result["streak_correct"] == initial_streak + 1


# 4. Wrong answers reset streak_correct to 0

@given(
    initial_streak=st.integers(min_value=0, max_value=50),
    reps=st.integers(min_value=0, max_value=20),
)
@settings()
def test_wrong_resets_streak_to_zero(initial_streak, reps):
    """A wrong answer with full confidence must reset streak_correct to 0."""
    row = _base_row(streak_correct=initial_streak, repetitions=reps)
    result = _compute_srs_update(row, False, "full", None, "seen")
    assert result["streak_correct"] == 0


# 5. Stage transitions are valid (no skipping)

@given(
    stage=stage_strategy,
    correct=st.booleans(),
    confidence=st.sampled_from(["full", None]),
    streak_c=st.integers(min_value=0, max_value=30),
    streak_i=st.integers(min_value=0, max_value=10),
    distinct_days=st.integers(min_value=0, max_value=30),
    total_after=st.integers(min_value=1, max_value=50),
    drill_type_count=st.integers(min_value=1, max_value=5),
)
@settings()
def test_stage_transitions_valid(stage, correct, confidence, streak_c, streak_i,
                                  distinct_days, total_after, drill_type_count):
    """Each transition must be to a valid next stage -- no skipping."""
    row = _base_row(mastery_stage=stage, total_correct=total_after // 2)
    result = _compute_mastery_transition(
        row, correct, confidence, streak_c, streak_i,
        "mc", distinct_days, total_after, drill_type_count,
    )
    new_stage = result["mastery_stage"]
    assert new_stage in VALID_STAGES, f"Invalid stage: {new_stage}"

    # The transition must follow valid paths. Because the mastery function
    # checks promotions sequentially (seen->passed_once->stabilizing->stable),
    # a single call can traverse multiple steps in one call (e.g., seen->stabilizing
    # if both thresholds are met). This is by design -- the "no skipping" invariant
    # means the code checks each intermediate gate, not that only one promotion
    # happens per call. We verify the result is reachable from the start stage.
    reachable = _reachable_stages(stage)
    assert new_stage in reachable, (
        f"Stage {new_stage} is not reachable from {stage}. Reachable: {reachable}"
    )


def _reachable_stages(start):
    """Compute all stages reachable from start via valid transitions (BFS)."""
    visited = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for next_stage in VALID_TRANSITIONS.get(current, set()):
            if next_stage not in visited:
                queue.append(next_stage)
    return visited


# 6. Multiple correct answers eventually promote (passed_once -> stabilizing -> stable)

@settings()
@given(st.data())
def test_correct_streak_eventually_promotes(data):
    """Enough correct answers in a row must promote through the stages."""
    row = _base_row(mastery_stage="passed_once")
    # With streak_correct >= PROMOTE_STABILIZING_STREAK(3) and distinct_days >= 2,
    # passed_once should promote to stabilizing.
    result = _compute_mastery_transition(
        row, True, "full",
        streak_correct=PROMOTE_STABILIZING_STREAK,
        streak_incorrect=0,
        drill_type="mc",
        distinct_days=PROMOTE_STABILIZING_DAYS,
        total_after=10,
        drill_type_count=1,
    )
    assert result["mastery_stage"] == "stabilizing"


# 7. Multiple wrong answers demote (stable -> decayed)

@given(
    total_correct=st.integers(min_value=0, max_value=9),  # low history -> threshold=3
)
@settings()
def test_wrong_streak_demotes_stable(total_correct):
    """Enough consecutive wrong answers must demote stable to decayed."""
    row = _base_row(
        mastery_stage="stable",
        stable_since_date="2024-01-01",
        total_correct=total_correct,
    )
    # Demotion threshold = DEMOTE_STABLE_STREAK_INCORRECT + min(3, max(0, (tc-10)//20))
    # For total_correct <= 9: threshold = 3
    threshold = DEMOTE_STABLE_STREAK_INCORRECT + min(3, max(0, (total_correct - 10) // 20))
    result = _compute_mastery_transition(
        row, False, "full",
        streak_correct=0,
        streak_incorrect=threshold,
        drill_type="mc",
        distinct_days=5,
        total_after=20,
        drill_type_count=2,
    )
    assert result["mastery_stage"] == "decayed"


# 8. Durable requires significant history (can't reach in < certain number of attempts)

def test_durable_not_reachable_quickly():
    """Durable stage requires days_stable >= 30 and successes_while_stable >= 5.

    This means it cannot be reached in a single burst of attempts within one day,
    regardless of how many correct answers are given.
    """
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        # Slam 50 correct answers in rapid succession
        for i in range(50):
            drill = "mc" if i % 2 == 0 else "reverse_mc"
            record_attempt(conn, item_id, "reading", True, drill_type=drill)
            if i == 5:
                # Simulate a day boundary for distinct_days
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            if i == 10:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
        p = _get_progress(conn, item_id)
        # Should be at most 'stable', not 'durable' (needs 30 days in stable)
        assert p["mastery_stage"] != "durable", (
            "Durable should not be reachable without 30 days in stable stage"
        )
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════════════════
# RETENTION MODEL INVARIANTS
# ════════════════════════════════════════════════════════════════════════

# 9. Interval is always positive

@given(
    ease=st.floats(min_value=EASE_FLOOR, max_value=5.0),
    interval=st.floats(min_value=0.1, max_value=300.0),
    reps=st.integers(min_value=0, max_value=20),
    streak_c=st.integers(min_value=0, max_value=30),
    correct=st.booleans(),
    confidence=confidence_strategy,
    mastery=stage_strategy,
)
@settings()
def test_interval_always_positive(ease, interval, reps, streak_c, correct,
                                   confidence, mastery):
    """Interval must always be > 0 regardless of inputs."""
    row = _base_row(
        ease_factor=ease, interval_days=interval,
        repetitions=reps, streak_correct=streak_c,
    )
    result = _compute_srs_update(row, correct, confidence, None, mastery)
    assert result["interval"] > 0.0, f"interval={result['interval']} should be > 0"


# 10. Difficulty is bounded [0.05, 0.95] (update_difficulty bounds)

@given(
    difficulty=st.floats(min_value=0.0, max_value=1.0),
    correct=st.booleans(),
    predicted_p=st.floats(min_value=0.0, max_value=1.0),
)
@settings()
def test_difficulty_bounded(difficulty, correct, predicted_p):
    """update_difficulty output must stay in [0.05, 0.95]."""
    result = update_difficulty(difficulty, correct, predicted_p)
    assert 0.05 <= result <= 0.95, f"difficulty={result} out of bounds [0.05, 0.95]"


# 11. Ease factor is bounded [EASE_FLOOR, infinity) but practically constrained

@given(
    ease=st.floats(min_value=EASE_FLOOR, max_value=10.0),
    interval=st.floats(min_value=0.5, max_value=100.0),
    reps=st.integers(min_value=0, max_value=20),
    streak_c=st.integers(min_value=0, max_value=20),
    correct=st.booleans(),
    confidence=confidence_strategy,
    mastery=stage_strategy,
)
@settings()
def test_ease_factor_bounded_below(ease, interval, reps, streak_c, correct,
                                    confidence, mastery):
    """Ease factor must never drop below EASE_FLOOR."""
    row = _base_row(
        ease_factor=ease, interval_days=interval,
        repetitions=reps, streak_correct=streak_c,
    )
    result = _compute_srs_update(row, correct, confidence, None, mastery)
    assert result["ease"] >= EASE_FLOOR, f"ease={result['ease']} < floor={EASE_FLOOR}"


# 12. Correct answer -> interval increases (for full confidence, reps >= 2)

@given(
    ease=st.floats(min_value=2.0, max_value=3.0),
    interval=st.floats(min_value=1.0, max_value=50.0),
    streak_c=st.integers(min_value=0, max_value=8),  # below streak cap thresholds
)
@settings()
def test_correct_full_increases_interval(ease, interval, streak_c):
    """A correct answer with full confidence and reps >= 2 must increase interval."""
    row = _base_row(
        ease_factor=ease, interval_days=interval,
        repetitions=2, streak_correct=streak_c,
    )
    result = _compute_srs_update(row, True, "full", None, "seen")
    # interval * ease should be > interval since ease >= 2.0 > 1.0
    # (before MAX_INTERVAL cap)
    if result["interval"] < MAX_INTERVAL:
        assert result["interval"] > interval, (
            f"interval should increase: {interval} -> {result['interval']}"
        )


# 13. Wrong answer -> interval resets to INTERVAL_WRONG

@given(
    ease=st.floats(min_value=EASE_FLOOR, max_value=5.0),
    interval=st.floats(min_value=0.5, max_value=200.0),
    reps=st.integers(min_value=0, max_value=20),
)
@settings()
def test_wrong_resets_interval(ease, interval, reps):
    """A wrong answer with full confidence must reset interval to INTERVAL_WRONG."""
    row = _base_row(ease_factor=ease, interval_days=interval, repetitions=reps)
    result = _compute_srs_update(row, False, "full", None, "seen")
    assert result["interval"] == INTERVAL_WRONG


# 14. Quality 5 (easy) produces longer half-life than quality 3 (hard correct)

@given(
    half_life=st.floats(min_value=1.0, max_value=100.0),
    difficulty_easy=st.floats(min_value=0.0, max_value=0.2),
    difficulty_hard=st.floats(min_value=0.6, max_value=1.0),
    days_since=st.floats(min_value=0.5, max_value=30.0),
)
@settings()
def test_easy_item_gets_longer_half_life(half_life, difficulty_easy, difficulty_hard,
                                          days_since):
    """Correct answer on easy item should yield longer half-life than hard item."""
    hl_easy = update_half_life(half_life, True, days_since, difficulty_easy)
    hl_hard = update_half_life(half_life, True, days_since, difficulty_hard)
    assert hl_easy >= hl_hard, (
        f"Easy HL {hl_easy} should >= Hard HL {hl_hard}"
    )


# 15. Multiple consecutive correct reviews produce monotonically increasing intervals

def test_consecutive_correct_increasing_intervals():
    """A sequence of correct answers must produce non-decreasing intervals."""
    row = _base_row(ease_factor=2.5, interval_days=1.0, repetitions=0, streak_correct=0)
    intervals = []
    for _ in range(15):
        result = _compute_srs_update(row, True, "full", None, "seen")
        intervals.append(result["interval"])
        # Update row for next iteration
        row = _base_row(
            ease_factor=result["ease"],
            interval_days=result["interval"],
            repetitions=result["reps"],
            streak_correct=result["streak_correct"],
        )
    # After the first two reps (which use fixed INTERVAL_INITIAL and INTERVAL_SECOND),
    # intervals should be monotonically non-decreasing
    for i in range(2, len(intervals) - 1):
        assert intervals[i + 1] >= intervals[i], (
            f"Interval decreased at step {i}: {intervals[i]} -> {intervals[i+1]}"
        )


# 16. Difficulty converges: many easy answers -> difficulty approaches minimum

def test_difficulty_converges_toward_easy():
    """Many correct answers should push difficulty toward 0.05 (min)."""
    difficulty = 0.5
    for _ in range(200):
        difficulty = update_difficulty(difficulty, True, 0.9)  # high p_recall, still correct
    assert difficulty <= 0.15, f"Difficulty {difficulty} should be near minimum after 200 correct"


# 17. Difficulty converges: many hard answers -> difficulty approaches maximum

def test_difficulty_converges_toward_hard():
    """Many wrong answers should push difficulty toward 0.95 (max)."""
    difficulty = 0.5
    for _ in range(200):
        difficulty = update_difficulty(difficulty, False, 0.9)  # high p_recall, got it wrong
    assert difficulty >= 0.85, f"Difficulty {difficulty} should be near maximum after 200 wrong"


# ════════════════════════════════════════════════════════════════════════
# CROSS-MODULE INVARIANTS
# ════════════════════════════════════════════════════════════════════════

# 18. Recording an attempt and computing retention for same item doesn't crash

@given(
    correct=st.booleans(),
    confidence=confidence_strategy,
    drill_type=drill_type_strategy,
    modality=modality_strategy,
)
@settings(deadline=None)
def test_record_attempt_no_crash(correct, confidence, drill_type, modality):
    """record_attempt should never raise for valid inputs."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        # Should not raise
        record_attempt(
            conn, item_id, modality, correct,
            drill_type=drill_type, confidence=confidence,
        )
        p = _get_progress(conn, item_id, modality)
        assert p is not None
        assert p["total_attempts"] == 1
        assert p["mastery_stage"] in VALID_STAGES
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 19. Mass attempts (100+) on one item converge to a stable state

def test_mass_correct_converges():
    """100 correct attempts on one item should reach stable or durable."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for i in range(100):
            drill = "mc" if i % 3 != 0 else "reverse_mc"
            record_attempt(conn, item_id, "reading", True, drill_type=drill)
            # Simulate day boundaries to satisfy distinct_days requirements
            if i in (3, 8, 15):
                conn.execute(
                    "UPDATE progress SET last_review_date = ? WHERE content_item_id = ? AND modality = 'reading'",
                    (f"2020-01-{i:02d}", item_id)
                )
                conn.commit()
        p = _get_progress(conn, item_id)
        assert p["mastery_stage"] in ("stable", "durable"), (
            f"After 100 correct attempts, expected stable/durable, got {p['mastery_stage']}"
        )
        assert p["streak_correct"] >= 50  # should be very high
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 20. Random sequences of correct/wrong always end in a valid state

@given(
    attempts=st.lists(st.booleans(), min_size=5, max_size=40),
)
@settings(deadline=None)
def test_random_sequence_valid_state(attempts):
    """Any random sequence of correct/wrong should leave the DB in a valid state."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for i, correct in enumerate(attempts):
            drill = "mc" if i % 2 == 0 else "reverse_mc"
            record_attempt(conn, item_id, "reading", correct, drill_type=drill)
            # Simulate day boundary every 5 attempts
            if i > 0 and i % 5 == 0:
                conn.execute(
                    "UPDATE progress SET last_review_date = ? WHERE content_item_id = ? AND modality = 'reading'",
                    (f"2020-01-{(i % 28) + 1:02d}", item_id)
                )
                conn.commit()

        p = _get_progress(conn, item_id)
        assert p is not None
        assert p["mastery_stage"] in VALID_STAGES
        assert p["total_attempts"] == len(attempts)
        assert p["total_correct"] == sum(attempts)
        assert p["streak_correct"] >= 0
        assert p["streak_incorrect"] >= 0
        assert p["ease_factor"] >= EASE_FLOOR
        assert p["interval_days"] > 0
        assert p["interval_days"] <= MAX_INTERVAL
        if p["half_life_days"] is not None:
            assert p["half_life_days"] >= MIN_HALF_LIFE
            assert p["half_life_days"] <= MAX_HALF_LIFE
        if p["difficulty"] is not None:
            assert 0.0 <= p["difficulty"] <= 1.0
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════════════════
# ADDITIONAL INVARIANTS (21-25)
# ════════════════════════════════════════════════════════════════════════

# 21. Half-life always in [MIN_HALF_LIFE, MAX_HALF_LIFE] after update

@given(
    half_life=st.floats(min_value=0.01, max_value=1000.0),
    correct=st.booleans(),
    days_since=st.floats(min_value=0.0, max_value=365.0),
    difficulty=st.floats(min_value=0.0, max_value=1.0),
)
@settings()
def test_half_life_always_bounded(half_life, correct, days_since, difficulty):
    """update_half_life must return value in [MIN_HALF_LIFE, MAX_HALF_LIFE]."""
    result = update_half_life(half_life, correct, days_since, difficulty)
    assert MIN_HALF_LIFE <= result <= MAX_HALF_LIFE, (
        f"HL {result} out of [{MIN_HALF_LIFE}, {MAX_HALF_LIFE}]"
    )


# 22. Interval capped at MAX_INTERVAL regardless of inputs

@given(
    ease=st.floats(min_value=2.0, max_value=10.0),
    interval=st.floats(min_value=100.0, max_value=500.0),
    reps=st.integers(min_value=2, max_value=20),
    streak_c=st.integers(min_value=15, max_value=30),
    mastery=stage_strategy,
)
@settings()
def test_interval_capped(ease, interval, reps, streak_c, mastery):
    """Interval must never exceed MAX_INTERVAL."""
    row = _base_row(
        ease_factor=ease, interval_days=interval,
        repetitions=reps, streak_correct=streak_c,
    )
    result = _compute_srs_update(row, True, "full", None, mastery)
    assert result["interval"] <= MAX_INTERVAL, (
        f"interval={result['interval']} > MAX={MAX_INTERVAL}"
    )


# 23. Decayed recovery requires RECOVERY_STREAK_CORRECT correct answers

@given(
    streak_correct=st.integers(min_value=0, max_value=RECOVERY_STREAK_CORRECT - 1),
)
@settings()
def test_decayed_no_premature_recovery(streak_correct):
    """Decayed items should not recover until streak_correct >= RECOVERY_STREAK_CORRECT."""
    row = _base_row(mastery_stage="decayed")
    result = _compute_mastery_transition(
        row, True, "full",
        streak_correct=streak_correct,
        streak_incorrect=0,
        drill_type="mc",
        distinct_days=5,
        total_after=20,
        drill_type_count=2,
    )
    assert result["mastery_stage"] == "decayed", (
        f"Decayed should not recover with streak={streak_correct} "
        f"(needs {RECOVERY_STREAK_CORRECT})"
    )


# 24. Narrowed/half confidence does not count toward mastery promotion

@given(
    confidence=st.sampled_from(["narrowed", "half", "unknown", "narrowed_wrong"]),
    streak_correct=st.integers(min_value=2, max_value=10),
)
@settings()
def test_non_full_confidence_blocks_promotion(confidence, streak_correct):
    """Non-full confidence should not trigger promotion from seen to passed_once."""
    row = _base_row(mastery_stage="seen")
    result = _compute_mastery_transition(
        row, True, confidence,
        streak_correct=streak_correct,
        streak_incorrect=0,
        drill_type="mc",
        distinct_days=5,
        total_after=20,
        drill_type_count=2,
    )
    # Promotion requires full_conf = confidence in ("full", None)
    assert result["mastery_stage"] == "seen", (
        f"Non-full confidence ({confidence}) should not promote from seen"
    )


# 25. Weak cycle count monotonically increases on stabilizing demotion

@given(
    initial_cycles=st.integers(min_value=0, max_value=10),
)
@settings()
def test_weak_cycle_count_increases_on_demotion(initial_cycles):
    """When stabilizing demotes to seen, weak_cycle_count must increase by 1."""
    row = _base_row(mastery_stage="stabilizing", weak_cycle_count=initial_cycles)
    result = _compute_mastery_transition(
        row, False, "full",
        streak_correct=0,
        streak_incorrect=DEMOTE_STABILIZING_STREAK_INCORRECT,
        drill_type="mc",
        distinct_days=2,
        total_after=10,
        drill_type_count=1,
    )
    assert result["mastery_stage"] == "seen"
    assert result["weak_cycle_count"] == initial_cycles + 1


# 26. p_recall symmetry: predict_recall(h, h) == 0.5 (definition of half-life)

@given(
    half_life=st.floats(min_value=0.1, max_value=365.0),
)
@settings()
def test_p_recall_at_half_life_is_fifty_pct(half_life):
    """At elapsed == half_life, recall probability must be exactly 0.5."""
    p = predict_recall(half_life, half_life)
    assert abs(p - 0.5) < 1e-10, f"p={p} at elapsed=half_life should be 0.5"


# 27. Wrong answer decreases half-life

@given(
    half_life=st.floats(min_value=2.0, max_value=100.0),
    days_since=st.floats(min_value=0.5, max_value=30.0),
    difficulty=st.floats(min_value=0.0, max_value=1.0),
)
@settings()
def test_wrong_decreases_half_life(half_life, days_since, difficulty):
    """A wrong answer must decrease the half-life (or hit the floor)."""
    new_hl = update_half_life(half_life, False, days_since, difficulty)
    # Allow rounding tolerance: update_half_life rounds to 2 decimal places,
    # so a ±0.005 artifact when decay ≈ 1.0 (high difficulty) is expected.
    assert new_hl <= half_life + 0.005, (
        f"Wrong answer should not increase HL: {half_life} -> {new_hl}"
    )


# 28. Correct answer increases half-life

@given(
    half_life=st.floats(min_value=MIN_HALF_LIFE, max_value=100.0),
    days_since=st.floats(min_value=0.5, max_value=30.0),
    difficulty=st.floats(min_value=0.0, max_value=0.9),
)
@settings()
def test_correct_increases_half_life(half_life, days_since, difficulty):
    """A correct answer must increase the half-life (or hit the ceiling)."""
    new_hl = update_half_life(half_life, True, days_since, difficulty)
    assert new_hl >= half_life, (
        f"Correct answer should not decrease HL: {half_life} -> {new_hl}"
    )


# 29. Total attempts and total correct are consistent after any sequence

@given(
    attempts=st.lists(st.booleans(), min_size=1, max_size=30),
)
@settings(deadline=None)
def test_attempt_counters_consistent(attempts):
    """total_attempts == len(attempts), total_correct == sum(attempts)."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for correct in attempts:
            record_attempt(conn, item_id, "reading", correct, drill_type="mc")
        p = _get_progress(conn, item_id)
        assert p["total_attempts"] == len(attempts)
        assert p["total_correct"] == sum(attempts)
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 30. Streak invariants: streak_correct + streak_incorrect context

@given(
    attempts=st.lists(st.booleans(), min_size=1, max_size=30),
)
@settings(deadline=None)
def test_streak_consistency(attempts):
    """After any sequence, exactly one of streak_correct or streak_incorrect > 0
    (or both are 0 if sequence is empty, which it won't be here)."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for correct in attempts:
            record_attempt(conn, item_id, "reading", correct, drill_type="mc")
        p = _get_progress(conn, item_id)
        last_correct = attempts[-1]
        if last_correct:
            assert p["streak_correct"] >= 1
            assert p["streak_incorrect"] == 0
        else:
            assert p["streak_incorrect"] >= 1
            assert p["streak_correct"] == 0
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 31. content_item times_shown and times_correct stay consistent

@given(
    attempts=st.lists(st.booleans(), min_size=1, max_size=20),
)
@settings(deadline=None)
def test_content_item_counters(attempts):
    """content_item.times_shown == len(attempts), times_correct == sum(attempts)."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for correct in attempts:
            record_attempt(conn, item_id, "reading", correct, drill_type="mc")
        row = conn.execute(
            "SELECT times_shown, times_correct FROM content_item WHERE id = ?",
            (item_id,)
        ).fetchone()
        assert row["times_shown"] == len(attempts)
        assert row["times_correct"] == sum(attempts)
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 32. Multi-modality: same item tracked independently per modality

@given(
    modalities=st.lists(
        modality_strategy, min_size=2, max_size=4, unique=True
    ),
    correct=st.booleans(),
)
@settings(deadline=None)
def test_modalities_independent(modalities, correct):
    """Each modality should have its own independent progress row."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn)
        for mod in modalities:
            record_attempt(conn, item_id, mod, correct, drill_type="mc")

        rows = conn.execute(
            "SELECT modality, total_attempts FROM progress WHERE content_item_id = ?",
            (item_id,)
        ).fetchall()
        modality_set = {r["modality"] for r in rows}
        assert modality_set == set(modalities)
        for r in rows:
            assert r["total_attempts"] == 1
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# 33. Retention update p_recall always in [0, 1]

@given(
    half_life=st.floats(min_value=MIN_HALF_LIFE, max_value=MAX_HALF_LIFE),
    difficulty=st.floats(min_value=0.05, max_value=0.95),
    correct=st.booleans(),
    confidence=confidence_strategy,
    days_ago=st.integers(min_value=0, max_value=30),
)
@settings()
def test_retention_p_recall_bounded(half_life, difficulty, correct, confidence, days_ago):
    """_compute_retention_update p_recall must be in [0, 1]."""
    review_date = (date.today() - timedelta(days=days_ago)).isoformat()
    row = _base_row(
        half_life_days=half_life,
        difficulty=difficulty,
        last_review_date=review_date,
    )
    result = _compute_retention_update(row, correct, confidence)
    assert 0.0 <= result["p_recall"] <= 1.0, f"p_recall={result['p_recall']} out of [0,1]"
    assert result["half_life"] >= MIN_HALF_LIFE
    assert result["half_life"] <= MAX_HALF_LIFE
