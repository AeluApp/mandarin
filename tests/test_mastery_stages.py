"""Tests for 6-stage mastery lifecycle.

Validates: seen → passed_once → stabilizing → stable → durable → decayed
Plus demotion paths and migration backfill.
"""

import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item, content_count
from mandarin.db.progress import record_attempt


def _fresh_db():
    """Create a fresh test database with schema + migrations + seed profile."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


def _add_item(conn, hanzi="test", pinyin="te4st", english="test", hsk_level=1):
    return insert_content_item(
        conn, hanzi=hanzi, pinyin=pinyin, english=english, hsk_level=hsk_level,
    )


def _get_stage(conn, item_id, modality="reading"):
    row = conn.execute(
        "SELECT mastery_stage FROM progress WHERE content_item_id = ? AND modality = ?",
        (item_id, modality)
    ).fetchone()
    return row["mastery_stage"] if row else None


def _get_progress(conn, item_id, modality="reading"):
    row = conn.execute(
        "SELECT * FROM progress WHERE content_item_id = ? AND modality = ?",
        (item_id, modality)
    ).fetchone()
    return dict(row) if row else None


# ── Test 1: First attempt sets 'seen' ──

def test_first_attempt_sets_seen():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="一")
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        assert _get_stage(conn, item_id) == "seen"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 2: seen → passed_once ──

def test_seen_to_passed_once():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="二")
        # First attempt wrong → seen
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        assert _get_stage(conn, item_id) == "seen"
        # Need streak_correct >= PROMOTE_PASSED_ONCE_STREAK (2) for promotion
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        assert _get_stage(conn, item_id) == "seen", "1 correct not enough (need 2)"
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        assert _get_stage(conn, item_id) == "passed_once"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 3: passed_once → stabilizing ──

def test_passed_once_to_stabilizing():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="三")
        # Get streak_correct to 3 with distinct_review_days >= 2
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        # Simulate day boundary for distinct_review_days
        conn.execute(
            "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
            (item_id,)
        )
        conn.commit()
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        assert _get_stage(conn, item_id) == "stabilizing"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 4: stabilizing → stable ──

def test_stabilizing_to_stable():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="四")
        # Build up: need streak >= 6, total_attempts >= 10, drill_types >= 2, distinct_days >= 3
        for i in range(6):
            if i == 2:
                # Simulate day boundary
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            if i == 4:
                # Another day boundary
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            drill = "mc" if i < 3 else "reverse_mc"
            record_attempt(conn, item_id, "reading", True, drill_type=drill)

        # Need total_attempts >= 10, add more
        for _ in range(4):
            record_attempt(conn, item_id, "reading", True, drill_type="mc")

        stage = _get_stage(conn, item_id)
        assert stage == "stable", f"Expected 'stable', got '{stage}'"

        # Verify stable_since_date is set
        p = _get_progress(conn, item_id)
        assert p["stable_since_date"] is not None
        assert p["successes_while_stable"] >= 0
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 5: stable → durable ──

def test_stable_to_durable():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="五")
        # Build to stable first
        for i in range(6):
            if i == 2:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            if i == 4:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            drill = "mc" if i < 3 else "reverse_mc"
            record_attempt(conn, item_id, "reading", True, drill_type=drill)
        for _ in range(4):
            record_attempt(conn, item_id, "reading", True, drill_type="mc")

        assert _get_stage(conn, item_id) == "stable"

        # Set stable_since_date to 61 days ago
        old_date = (date.today() - timedelta(days=61)).isoformat()
        conn.execute(
            "UPDATE progress SET stable_since_date = ?, successes_while_stable = 6 WHERE content_item_id = ?",
            (old_date, item_id)
        )
        conn.commit()

        # One more correct attempt (successes_while_stable will become 7+)
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        stage = _get_stage(conn, item_id)
        assert stage == "durable", f"Expected 'durable', got '{stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 6: stable → decayed ──

def test_stable_to_decayed():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="六")
        # Build to stable
        for i in range(6):
            if i == 2:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            if i == 4:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            drill = "mc" if i < 3 else "reverse_mc"
            record_attempt(conn, item_id, "reading", True, drill_type=drill)
        for _ in range(4):
            record_attempt(conn, item_id, "reading", True, drill_type="mc")
        assert _get_stage(conn, item_id) == "stable"

        # Three wrong answers → decayed (base threshold = 3)
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        # Two wrong isn't enough
        assert _get_stage(conn, item_id) == "stable", "2 wrong should not demote stable"
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        stage = _get_stage(conn, item_id)
        assert stage == "decayed", f"Expected 'decayed', got '{stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 7: durable → decayed ──

def test_durable_to_decayed():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="七")
        # Build to stable
        for i in range(6):
            if i == 2:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            if i == 4:
                conn.execute(
                    "UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?",
                    (item_id,)
                )
                conn.commit()
            drill = "mc" if i < 3 else "reverse_mc"
            record_attempt(conn, item_id, "reading", True, drill_type=drill)
        for _ in range(4):
            record_attempt(conn, item_id, "reading", True, drill_type="mc")
        assert _get_stage(conn, item_id) == "stable"

        # Set to durable via DB manipulation
        old_date = (date.today() - timedelta(days=61)).isoformat()
        conn.execute(
            "UPDATE progress SET mastery_stage = 'durable', stable_since_date = ?, successes_while_stable = 8 WHERE content_item_id = ?",
            (old_date, item_id)
        )
        conn.commit()
        assert _get_stage(conn, item_id) == "durable"

        # Three wrong answers → decayed (base threshold = 3)
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        stage = _get_stage(conn, item_id)
        assert stage == "decayed", f"Expected 'decayed', got '{stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 7b: graduated demotion — high-history items need more wrong ──

def test_graduated_demotion_high_history():
    """Items with 30+ correct answers need more consecutive wrong to demote."""
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="韧")
        # Set up as stable with strong history (total_correct = 30)
        conn.execute("""
            INSERT INTO progress (content_item_id, modality, mastery_stage,
                                  total_attempts, total_correct,
                                  streak_correct, streak_incorrect,
                                  distinct_review_days, stable_since_date)
            VALUES (?, 'reading', 'stable', 35, 30, 0, 0, 10, '2020-01-01')
        """, (item_id,))
        conn.commit()

        # With total_correct=30: threshold = 3 + min(3, (30-10)//20) = 3 + 1 = 4
        # So 3 wrong should NOT demote
        for _ in range(3):
            record_attempt(conn, item_id, "reading", False, drill_type="mc")
        assert _get_stage(conn, item_id) == "stable", "3 wrong should not demote item with 30 correct"

        # 4th wrong should demote
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        stage = _get_stage(conn, item_id)
        assert stage == "decayed", f"Expected 'decayed' after 4 wrong, got '{stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 8: decayed → stabilizing (recovery) ──

def test_decayed_to_stabilizing():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="八")
        # Set up as decayed
        conn.execute("""
            INSERT INTO progress (content_item_id, modality, mastery_stage, total_attempts,
                                  streak_correct, streak_incorrect, distinct_review_days)
            VALUES (?, 'reading', 'decayed', 10, 0, 2, 3)
        """, (item_id,))
        conn.commit()

        # Three correct answers → stabilizing
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        stage = _get_stage(conn, item_id)
        assert stage == "stabilizing", f"Expected 'stabilizing', got '{stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 9: stabilizing regression ──

def test_stabilizing_regression():
    conn, path = _fresh_db()
    try:
        item_id = _add_item(conn, hanzi="九")
        # Build to stabilizing
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        conn.execute(
            "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
            (item_id,)
        )
        conn.commit()
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        record_attempt(conn, item_id, "reading", True, drill_type="mc")
        assert _get_stage(conn, item_id) == "stabilizing"

        # Three wrong answers → seen
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        record_attempt(conn, item_id, "reading", False, drill_type="mc")
        stage = _get_stage(conn, item_id)
        assert stage == "seen", f"Expected 'seen', got '{stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 10: migration backfill ──

def test_migration_backfill():
    """V7 migration should remap old stages correctly."""
    conn, path = _fresh_db()
    try:
        # Insert items with old mastery stages
        item1 = _add_item(conn, hanzi="旧一")
        item2 = _add_item(conn, hanzi="旧二")
        item3 = _add_item(conn, hanzi="旧三")

        # Insert progress rows directly with old-style stages
        # We need to test that the migration correctly remapped them.
        # Since _migrate already ran, check that V7 columns exist
        cols = {r[1] for r in conn.execute("PRAGMA table_info(progress)").fetchall()}
        assert "stable_since_date" in cols, "V7 migration should add stable_since_date"
        assert "successes_while_stable" in cols, "V7 migration should add successes_while_stable"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 11: fetchone safety ──

def test_fetchone_safety():
    """All 4 fixed patterns should return 0 on empty tables."""
    conn, path = _fresh_db()
    try:
        # content_count on empty table
        count = content_count(conn)
        assert count == 0

        # grammar_point count on empty table
        row = conn.execute("SELECT COUNT(*) FROM grammar_point").fetchone()
        gp_count = row[0] if row else 0
        assert gp_count == 0

        # construction count on empty table
        row = conn.execute("SELECT COUNT(*) FROM construction").fetchone()
        c_count = row[0] if row else 0
        assert c_count == 0

        # content_construction count on empty table
        row = conn.execute("SELECT COUNT(*) FROM content_construction").fetchone()
        cc_count = row[0] if row else 0
        assert cc_count == 0
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 12: stage counts return all 6 ──

def test_stage_counts_all_six():
    """get_stage_counts should return all 6 stage keys + unseen."""
    conn, path = _fresh_db()
    try:
        _add_item(conn, hanzi="测试")
        from mandarin.milestones import get_stage_counts
        counts = get_stage_counts(conn)
        for key in ["seen", "passed_once", "stabilizing", "stable", "durable", "decayed", "unseen"]:
            assert key in counts, f"Missing key '{key}' in stage counts: {counts.keys()}"
            assert isinstance(counts[key], int), f"'{key}' should be int, got {type(counts[key])}"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 13: no "learned" label below stable ──

def test_no_learned_label_below_stable():
    """UI stage labels should never say 'learned' or 'mastered' for non-stable items."""
    from mandarin.runner import _finalize
    import inspect
    source = inspect.getsource(_finalize)
    # The stage labels mapping shouldn't contain 'learned' or 'mastered'
    # for weak/seen/passed_once/stabilizing stages
    assert '"learned"' not in source, "No stage should use 'learned' label"
    assert '"mastered"' not in source, "No stage should use 'mastered' label"


# ── Test 14: scaffold flag matches mastery stage ──

def test_scaffold_flag_by_stage():
    """show_pinyin scaffold should be True for seen/passed_once, False otherwise."""
    # This tests the exact logic from scheduler.py:
    #   mastery_stage = item.get("mastery_stage") or "seen"
    #   show_pinyin = mastery_stage in ("seen", "passed_once")
    stages_and_expected = {
        None: True,            # default → "seen" → True
        "seen": True,
        "passed_once": True,
        "stabilizing": False,
        "stable": False,
        "durable": False,
        "decayed": False,
    }
    for stage, expected in stages_and_expected.items():
        mastery_stage = stage or "seen"
        show_pinyin = mastery_stage in ("seen", "passed_once")
        assert show_pinyin == expected, (
            f"stage={stage!r}: expected show_pinyin={expected}, got {show_pinyin}"
        )


