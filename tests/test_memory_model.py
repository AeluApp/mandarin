"""Tests for Doc 13: FSRS memory model, interference, interleaving, load management."""

import sqlite3
import math
import pytest

from mandarin.ai.memory_model import (
    compute_retrievability,
    compute_next_interval,
    update_stability_after_review,
    update_difficulty,
    process_review,
    _next_state,
    _initialize_memory_state,
    _interleave_items,
    apply_interference_separation,
    build_interleaved_session,
    check_session_load,
    analyze_memory_model,
    calibrate_fsrs_parameters,
    backfill_memory_states,
    RATING_AGAIN,
    RATING_HARD,
    RATING_GOOD,
    RATING_EASY,
    FSRS_DEFAULTS,
)


from tests.shared_db import make_test_db as _make_db


def _seed_items(conn, count=5):
    """Insert test content items."""
    for i in range(1, count + 1):
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level, content_lens) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"字{i}", f"zi{i}", f"word{i}", (i % 3) + 1,
             "travel" if i % 2 == 0 else "culture"),
        )
    conn.commit()


# ─────────────────────────────────────────────
# RETRIEVABILITY TESTS
# ─────────────────────────────────────────────


class TestRetrievability:
    def test_zero_elapsed_returns_1(self):
        assert compute_retrievability(7.0, 0) == 1.0

    def test_decays_over_time(self):
        s = 7.0
        r7 = compute_retrievability(s, 7)
        r14 = compute_retrievability(s, 14)
        r30 = compute_retrievability(s, 30)
        assert r7 > r14 > r30
        assert 0 < r30 < r7 < 1.0

    def test_higher_stability_decays_slower(self):
        r_low = compute_retrievability(3.0, 10)
        r_high = compute_retrievability(30.0, 10)
        assert r_high > r_low

    def test_negative_elapsed(self):
        assert compute_retrievability(7.0, -1) == 1.0

    def test_zero_stability(self):
        assert compute_retrievability(0, 5) == 0.0


# ─────────────────────────────────────────────
# INTERVAL TESTS
# ─────────────────────────────────────────────


class TestNextInterval:
    def test_low_stability_returns_1(self):
        assert compute_next_interval(0.5) == 1

    def test_achieves_target_retention(self):
        s = 10.0
        interval = compute_next_interval(s, 0.90)
        r_at_interval = compute_retrievability(s, interval)
        assert abs(r_at_interval - 0.90) < 0.05

    def test_zero_stability(self):
        assert compute_next_interval(0) == 1


# ─────────────────────────────────────────────
# PROCESS REVIEW TESTS
# ─────────────────────────────────────────────


class TestProcessReview:
    def test_initializes_new_item(self):
        conn = _make_db()
        _seed_items(conn, 1)
        result = process_review(conn, 1, 1, RATING_GOOD)
        assert result["new_state"] == "learning"
        assert result["new_stability"] > 0

        row = conn.execute(
            "SELECT * FROM memory_states WHERE content_item_id=1"
        ).fetchone()
        assert row is not None
        assert row["reps"] == 1

    def test_updates_stability_on_correct(self):
        conn = _make_db()
        _seed_items(conn, 1)
        process_review(conn, 1, 1, RATING_GOOD)
        r2 = process_review(conn, 1, 1, RATING_GOOD)
        # Second review in learning state — stability should update
        assert r2["new_stability"] > 0

    def test_again_reduces_stability(self):
        conn = _make_db()
        _seed_items(conn, 1)
        # Initialize and promote to review
        process_review(conn, 1, 1, RATING_GOOD)
        process_review(conn, 1, 1, RATING_GOOD)
        # Force to review state
        conn.execute(
            "UPDATE memory_states SET state='review', stability=10.0 WHERE content_item_id=1"
        )
        r = process_review(conn, 1, 1, RATING_AGAIN)
        assert r["new_stability"] < 10.0

    def test_lapse_only_on_again_in_review(self):
        conn = _make_db()
        _seed_items(conn, 1)
        process_review(conn, 1, 1, RATING_GOOD)
        conn.execute(
            "UPDATE memory_states SET state='review', stability=10.0 WHERE content_item_id=1"
        )
        process_review(conn, 1, 1, RATING_AGAIN)
        row = conn.execute(
            "SELECT lapses FROM memory_states WHERE content_item_id=1"
        ).fetchone()
        assert row["lapses"] == 1

    def test_lapse_not_incremented_in_learning(self):
        conn = _make_db()
        _seed_items(conn, 1)
        process_review(conn, 1, 1, RATING_AGAIN)
        row = conn.execute(
            "SELECT lapses FROM memory_states WHERE content_item_id=1"
        ).fetchone()
        assert row["lapses"] == 0


# ─────────────────────────────────────────────
# STATE TRANSITIONS
# ─────────────────────────────────────────────


class TestStateTransitions:
    def test_new_to_learning(self):
        assert _next_state("new", RATING_GOOD) == "learning"
        assert _next_state("new", RATING_AGAIN) == "learning"

    def test_learning_to_review_on_good(self):
        assert _next_state("learning", RATING_GOOD) == "review"
        assert _next_state("learning", RATING_EASY) == "review"

    def test_learning_stays_on_hard(self):
        assert _next_state("learning", RATING_HARD) == "learning"
        assert _next_state("learning", RATING_AGAIN) == "learning"

    def test_review_to_relearning_on_again(self):
        assert _next_state("review", RATING_AGAIN) == "relearning"

    def test_review_stays_on_good(self):
        assert _next_state("review", RATING_GOOD) == "review"

    def test_relearning_to_review_on_good(self):
        assert _next_state("relearning", RATING_GOOD) == "review"

    def test_relearning_stays_on_again(self):
        assert _next_state("relearning", RATING_AGAIN) == "relearning"


# ─────────────────────────────────────────────
# DIFFICULTY UPDATE
# ─────────────────────────────────────────────


class TestDifficulty:
    def test_again_increases_difficulty(self):
        d0 = 5.0
        d1 = update_difficulty(d0, RATING_AGAIN)
        assert d1 > d0

    def test_easy_decreases_difficulty(self):
        d0 = 5.0
        d1 = update_difficulty(d0, RATING_EASY)
        assert d1 < d0

    def test_difficulty_bounded(self):
        d_max = update_difficulty(10.0, RATING_AGAIN)
        d_min = update_difficulty(1.0, RATING_EASY)
        assert d_max <= 10.0
        assert d_min >= 1.0


# ─────────────────────────────────────────────
# STABILITY COMPARISONS
# ─────────────────────────────────────────────


class TestStabilityComparisons:
    def test_easy_exceeds_good(self):
        s = 5.0
        d = 5.0
        r = 0.8
        s_good = update_stability_after_review(s, d, r, RATING_GOOD, "review")
        s_easy = update_stability_after_review(s, d, r, RATING_EASY, "review")
        assert s_easy > s_good

    def test_relearning_items_next_day(self):
        conn = _make_db()
        _seed_items(conn, 1)
        process_review(conn, 1, 1, RATING_GOOD)
        conn.execute(
            "UPDATE memory_states SET state='review', stability=10.0 WHERE content_item_id=1"
        )
        result = process_review(conn, 1, 1, RATING_AGAIN)
        assert result["new_state"] == "relearning"
        assert result["next_review_days"] == 1


# ─────────────────────────────────────────────
# INTERFERENCE TESTS
# ─────────────────────────────────────────────


class TestInterference:
    def test_separation_removes_blocked(self):
        conn = _make_db()
        _seed_items(conn, 5)
        # Insert a high-interference pair: item 1 and item 2
        conn.execute("""
            INSERT INTO interference_pairs
            (item_id_a, item_id_b, interference_type, interference_strength, detected_by)
            VALUES (1, 2, 'near_synonym', 'high', 'human_flagged')
        """)
        conn.commit()

        result = apply_interference_separation(conn, 1, [2, 3, 4], [1])
        assert 2 not in result
        assert 3 in result
        assert 4 in result

    def test_separation_returns_all_when_session_empty(self):
        conn = _make_db()
        _seed_items(conn, 3)
        result = apply_interference_separation(conn, 1, [1, 2, 3], [])
        assert result == [1, 2, 3]

    def test_idempotent_insertion(self):
        conn = _make_db()
        _seed_items(conn, 2)
        from mandarin.ai.memory_model import _insert_interference_pairs
        pairs = [{
            "item_id_a": 1, "item_id_b": 2,
            "interference_type": "near_synonym",
            "interference_strength": "high",
            "detected_by": "human_flagged",
        }]
        _insert_interference_pairs(conn, pairs)
        _insert_interference_pairs(conn, pairs)  # Should not duplicate
        count = conn.execute("SELECT COUNT(*) as cnt FROM interference_pairs").fetchone()["cnt"]
        assert count == 1


# ─────────────────────────────────────────────
# INTERLEAVING TESTS
# ─────────────────────────────────────────────


class TestInterleaving:
    def test_alternates_content_lens(self):
        items = [
            {"content_lens": "travel", "state": "review"},
            {"content_lens": "travel", "state": "review"},
            {"content_lens": "culture", "state": "review"},
            {"content_lens": "culture", "state": "review"},
        ]
        result = _interleave_items(items)
        # Should not have two consecutive same-lens items if avoidable
        consecutive_same = sum(
            1 for i in range(len(result) - 1)
            if result[i]["content_lens"] == result[i + 1]["content_lens"]
        )
        # With 2+2, perfect interleaving = 0 consecutive
        assert consecutive_same <= 1

    def test_single_item(self):
        items = [{"content_lens": "travel", "state": "review"}]
        assert _interleave_items(items) == items

    def test_empty(self):
        assert _interleave_items([]) == []

    def test_build_session_respects_ceiling(self):
        conn = _make_db()
        _seed_items(conn, 10)
        conn.execute(
            "INSERT INTO learner_dd_config (user_id, new_item_ceiling) VALUES (1, 3)"
        )
        # Create memory_states for all items as new, due now
        for i in range(1, 11):
            conn.execute("""
                INSERT INTO memory_states
                (user_id, content_item_id, state, next_review_due, stability)
                VALUES (1, ?, 'new', datetime('now', '-1 hour'), 1.0)
            """, (i,))
        conn.commit()

        result = build_interleaved_session(conn, user_id=1, target_count=20)
        new_count = sum(1 for r in result if r["state"] in ("new", "learning"))
        assert new_count <= 3


# ─────────────────────────────────────────────
# COGNITIVE LOAD TESTS
# ─────────────────────────────────────────────


class TestCognitiveLoad:
    def test_within_ceiling(self):
        conn = _make_db()
        _seed_items(conn, 1)
        conn.execute("INSERT INTO session_log (id) VALUES (1)")
        conn.execute(
            "INSERT INTO learner_dd_config (user_id, new_item_ceiling) VALUES (1, 5)"
        )
        conn.commit()
        result = check_session_load(conn, session_id=1, user_id=1)
        assert result["within_ceiling"] is True
        assert result["ceiling"] == 5

    def test_ceiling_reached(self):
        conn = _make_db()
        _seed_items(conn, 6)
        conn.execute("INSERT INTO session_log (id) VALUES (1)")
        conn.execute(
            "INSERT INTO learner_dd_config (user_id, new_item_ceiling) VALUES (1, 3)"
        )
        # Create memory states for 4 items as new with reps=1
        for i in range(1, 5):
            conn.execute("""
                INSERT INTO memory_states
                (user_id, content_item_id, state, reps)
                VALUES (1, ?, 'new', 1)
            """, (i,))
            conn.execute("""
                INSERT INTO review_event
                (user_id, session_id, content_item_id, modality, correct)
                VALUES (1, 1, ?, 'recognition', 1)
            """, (i,))
        conn.commit()

        result = check_session_load(conn, session_id=1, user_id=1)
        assert result["within_ceiling"] is False


# ─────────────────────────────────────────────
# ANALYZER TESTS
# ─────────────────────────────────────────────


class TestAnalyzer:
    def test_high_lapse_finding(self):
        conn = _make_db()
        _seed_items(conn, 1)
        # Item with 50% lapse rate
        conn.execute("""
            INSERT INTO memory_states
            (user_id, content_item_id, reps, lapses, state, stability)
            VALUES (1, 1, 10, 5, 'review', 2.0)
        """)
        conn.commit()
        findings = analyze_memory_model(conn)
        lapse_findings = [f for f in findings if "lapse" in f["title"].lower()]
        assert len(lapse_findings) == 1

    def test_load_violation_finding(self):
        conn = _make_db()
        conn.execute("INSERT INTO session_log (id) VALUES (1)")
        # Insert 4 load violations in the past week
        for i in range(4):
            conn.execute("""
                INSERT INTO session_load_log
                (session_id, user_id, load_exceeded, started_at)
                VALUES (1, 1, 1, datetime('now', '-1 day'))
            """)
        conn.commit()
        findings = analyze_memory_model(conn)
        load_findings = [f for f in findings if "ceiling" in f["title"].lower()]
        assert len(load_findings) == 1

    def test_no_findings_when_healthy(self):
        conn = _make_db()
        findings = analyze_memory_model(conn)
        assert findings == []


# ─────────────────────────────────────────────
# CALIBRATION TEST
# ─────────────────────────────────────────────


class TestCalibration:
    def test_returns_none_for_few_reviews(self):
        conn = _make_db()
        result = calibrate_fsrs_parameters(conn, user_id=1)
        assert result is None

    def test_returns_params_with_enough_reviews(self):
        conn = _make_db()
        _seed_items(conn, 1)
        for i in range(200):
            conn.execute("""
                INSERT INTO review_event
                (user_id, content_item_id, modality, correct)
                VALUES (1, 1, 'recognition', 1)
            """)
        conn.commit()
        result = calibrate_fsrs_parameters(conn, user_id=1)
        assert result is not None
        assert "w" in result


# ─────────────────────────────────────────────
# BACKFILL TEST
# ─────────────────────────────────────────────


class TestBackfill:
    def test_creates_states_from_history(self):
        conn = _make_db()
        _seed_items(conn, 2)
        # Add review history for item 1
        for _ in range(5):
            conn.execute("""
                INSERT INTO review_event
                (user_id, content_item_id, modality, correct, created_at)
                VALUES (1, 1, 'recognition', 1, datetime('now', '-7 days'))
            """)
        conn.commit()

        count = backfill_memory_states(conn, user_id=1)
        assert count == 1

        row = conn.execute(
            "SELECT * FROM memory_states WHERE content_item_id=1"
        ).fetchone()
        assert row is not None
        assert row["state"] == "review"
        assert row["reps"] == 5

    def test_skips_existing_states(self):
        conn = _make_db()
        _seed_items(conn, 1)
        conn.execute("""
            INSERT INTO memory_states
            (user_id, content_item_id, state, reps) VALUES (1, 1, 'review', 3)
        """)
        conn.execute("""
            INSERT INTO review_event
            (user_id, content_item_id, modality, correct)
            VALUES (1, 1, 'recognition', 1)
        """)
        conn.commit()

        count = backfill_memory_states(conn, user_id=1)
        assert count == 0


# ─────────────────────────────────────────────
# SCHEMA MIGRATION TEST
# ─────────────────────────────────────────────


class TestSchemaMigration:
    def test_migration_creates_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Minimal pre-existing schema
        conn.executescript("""
            CREATE TABLE content_item (id INTEGER PRIMARY KEY, hanzi TEXT, pinyin TEXT, english TEXT);
            CREATE TABLE session_log (id INTEGER PRIMARY KEY);
            CREATE TABLE user (id INTEGER PRIMARY KEY);
        """)

        from mandarin.db.core import _migrate_v73_to_v74
        _migrate_v73_to_v74(conn)

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "memory_states" in tables
        assert "interference_pairs" in tables
        assert "session_load_log" in tables
        assert "learner_dd_config" in tables
        assert "learner_fsrs_params" in tables

    def test_migration_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE content_item (id INTEGER PRIMARY KEY, hanzi TEXT, pinyin TEXT, english TEXT);
            CREATE TABLE session_log (id INTEGER PRIMARY KEY);
            CREATE TABLE user (id INTEGER PRIMARY KEY);
        """)

        from mandarin.db.core import _migrate_v73_to_v74
        _migrate_v73_to_v74(conn)
        _migrate_v73_to_v74(conn)  # Should not error

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "memory_states" in tables
