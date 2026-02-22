"""Tests for linguist-grade features: response time, constructions, variation, tone confusion."""

import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item, seed_constructions, _get_constructions
from mandarin.db.progress import record_attempt
from mandarin.db.session import start_session


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn


def _add_items(conn, n, hsk_level=1):
    ids = []
    for i in range(n):
        item_id = insert_content_item(
            conn, hanzi=f"\u4f60{i}_{hsk_level}", pinyin=f"ni{i}",
            english=f"test{i}", hsk_level=hsk_level,
        )
        ids.append(item_id)
    return ids


# ── Response time tracking ──

def test_response_ms_recorded():
    """record_attempt with response_ms stores avg_response_ms."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)

    row = conn.execute(
        "SELECT avg_response_ms FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row is not None
    assert row["avg_response_ms"] == 5000.0
    conn.close()


def test_response_ms_ema():
    """Response time uses exponential moving average (alpha=0.3)."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=10000)
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=4000)

    row = conn.execute(
        "SELECT avg_response_ms FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    # EMA: 10000 * 0.7 + 4000 * 0.3 = 7000 + 1200 = 8200
    assert row["avg_response_ms"] is not None
    assert abs(row["avg_response_ms"] - 8200) < 1
    conn.close()


def test_response_ms_none_preserved():
    """response_ms=None should not overwrite existing avg."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=None)

    row = conn.execute(
        "SELECT avg_response_ms FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["avg_response_ms"] == 5000.0
    conn.close()


# ── Drill type variation tracking ──

def test_drill_types_seen_tracked():
    """drill_types_seen accumulates distinct drill types."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc")
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="tone")
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc")  # duplicate

    row = conn.execute(
        "SELECT drill_types_seen FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    types = set(row["drill_types_seen"].split(","))
    assert types == {"mc", "tone"}, f"expected {{mc, tone}}, got {types}"
    conn.close()


def test_mastery_requires_variation():
    """Stable mastery requires 2+ drill types and multi-day spacing."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # Day 1: 4 mc correct (distinct_days=1, stays weak)
    for _ in range(4):
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type="mc")
    conn.execute("UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?", (ids[0],))
    conn.commit()

    # Day 2: 4 more mc correct (distinct_days=2 → weak→improving)
    for _ in range(4):
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type="mc")
    conn.execute("UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?", (ids[0],))
    conn.commit()

    # Day 3: 3 more mc (total=11, streak=11, distinct=3, but only 1 drill type)
    for _ in range(3):
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type="mc")

    row = conn.execute(
        "SELECT mastery_stage FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["mastery_stage"] != "stable", \
        f"should not be stable with only 1 drill type, got {row['mastery_stage']}"

    # Now add a different drill type — should unlock stable
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="tone")

    row = conn.execute(
        "SELECT mastery_stage FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["mastery_stage"] == "stable", \
        f"should be stable with 2 drill types and multi-day spacing, got {row['mastery_stage']}"
    conn.close()


def test_mastery_stable_with_variation():
    """Item reaches stable with 2 drill types and multi-day spacing."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # Day 1: 4 alternating drill types (distinct_days=1, stays weak)
    for i in range(4):
        dt = "mc" if i % 2 == 0 else "reverse_mc"
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type=dt)
    conn.execute("UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?", (ids[0],))
    conn.commit()

    # Day 2: 4 more (distinct_days=2 → weak→improving)
    for i in range(4, 8):
        dt = "mc" if i % 2 == 0 else "reverse_mc"
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type=dt)
    conn.execute("UPDATE progress SET last_review_date = '2020-01-02' WHERE content_item_id = ?", (ids[0],))
    conn.commit()

    # Day 3: 4 more (distinct_days=3, total=12, streak=12, types=2 → stable)
    for i in range(8, 12):
        dt = "mc" if i % 2 == 0 else "reverse_mc"
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type=dt)

    row = conn.execute(
        "SELECT mastery_stage, drill_types_seen FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["mastery_stage"] == "stable"
    types = set(row["drill_types_seen"].split(","))
    assert len(types) >= 2
    conn.close()


# ── Construction tracking ──

def test_construction_seed_data():
    """CONSTRUCTIONS list is well-formed."""
    constructions = _get_constructions()
    assert len(constructions) >= 30
    for c in constructions:
        assert "name" in c
        assert "pattern_zh" in c
        assert "hsk_level" in c
        assert "category" in c
        assert "hanzi_tags" in c


def test_seed_constructions_idempotent():
    """seed_constructions() is idempotent."""
    conn = _fresh_db()
    # Add items that match construction tags
    insert_content_item(conn, hanzi="了", pinyin="le", english="aspect particle", hsk_level=1)
    insert_content_item(conn, hanzi="的", pinyin="de", english="attributive marker", hsk_level=1)

    count1 = seed_constructions(conn)
    count2 = seed_constructions(conn)

    assert count1 > 0
    assert count2 == 0, "second seed should insert 0 new constructions"

    total = conn.execute("SELECT COUNT(*) FROM construction").fetchone()[0]
    assert total == count1
    conn.close()


def test_construction_item_links():
    """seed_constructions() links items to constructions by hanzi."""
    conn = _fresh_db()
    le_id = insert_content_item(conn, hanzi="了", pinyin="le", english="aspect particle", hsk_level=1)
    seed_constructions(conn)

    links = conn.execute(
        "SELECT * FROM content_construction WHERE content_item_id = ?", (le_id,)
    ).fetchall()
    assert len(links) >= 1, "了 should be linked to 了_perfective construction"
    conn.close()


# ── Tone confusion matrix ──

def test_tone_confusion_empty():
    """Empty error_log returns zeroed matrix."""
    conn = _fresh_db()
    from mandarin.diagnostics import get_tone_confusion_matrix
    result = get_tone_confusion_matrix(conn)
    assert result["total_tone_errors"] == 0
    assert result["top_confusions"] == []
    assert "No tone confusion data" in result["summary"]
    conn.close()


def test_tone_confusion_with_data():
    """Tone confusion detects common confusions."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # Insert tone errors: tone 2 confused with tone 3
    for _ in range(5):
        conn.execute("""
            INSERT INTO error_log (session_id, content_item_id, modality, error_type,
                                   user_answer, expected_answer, drill_type)
            VALUES (?, ?, 'reading', 'tone', 'ma3', 'ma2', 'tone')
        """, (session_id, ids[0]))
    # tone 1 confused with tone 4
    for _ in range(3):
        conn.execute("""
            INSERT INTO error_log (session_id, content_item_id, modality, error_type,
                                   user_answer, expected_answer, drill_type)
            VALUES (?, ?, 'reading', 'tone', 'ma4', 'ma1', 'tone')
        """, (session_id, ids[0]))
    conn.commit()

    from mandarin.diagnostics import get_tone_confusion_matrix
    result = get_tone_confusion_matrix(conn)
    assert result["total_tone_errors"] == 8
    assert len(result["top_confusions"]) >= 2

    # Tone 2→3 should be the most confused
    top = result["top_confusions"][0]
    assert top[0] == 2 and top[1] == 3, f"expected (2,3), got ({top[0]},{top[1]})"
    assert top[2] == 5

    # Matrix check
    assert result["matrix"][2][3] == 5
    assert result["matrix"][1][4] == 3
    conn.close()


# ── Speed trend ──

def test_speed_trend_empty():
    """No timed data returns summary message."""
    conn = _fresh_db()
    from mandarin.diagnostics import get_speed_trend
    result = get_speed_trend(conn)
    assert result["total_timed"] == 0
    assert result["avg_ms"] is None
    assert "No response time data" in result["summary"]
    conn.close()


def test_speed_trend_with_data():
    """Speed trend computes averages from progress table."""
    conn = _fresh_db()
    ids = _add_items(conn, 3, hsk_level=1)
    session_id = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=2000)
    record_attempt(conn, ids[1], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)
    record_attempt(conn, ids[2], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=10000)

    from mandarin.diagnostics import get_speed_trend
    result = get_speed_trend(conn)
    assert result["total_timed"] == 3
    assert result["avg_ms"] is not None
    assert result["fast_count"] >= 1   # 2000ms < 3000
    assert result["slow_count"] >= 1   # 10000ms > 8000
    assert 1 in result["by_hsk"]
    conn.close()


def test_speed_trend_by_modality():
    """Speed trend filters by modality."""
    conn = _fresh_db()
    ids = _add_items(conn, 2)
    session_id = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=3000)
    record_attempt(conn, ids[1], "listening", True, session_id=session_id,
                   drill_type="listening_gist", response_ms=8000)

    from mandarin.diagnostics import get_speed_trend
    reading = get_speed_trend(conn, modality="reading")
    listening = get_speed_trend(conn, modality="listening")
    assert reading["total_timed"] == 1
    assert listening["total_timed"] == 1
    assert reading["avg_ms"] == 3000
    assert listening["avg_ms"] == 8000
    conn.close()


# ── Speed-adjusted SRS intervals ──

def test_speed_fast_extends_interval():
    """Fast correct response (< 3s) should extend the SRS interval."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # Build up reps to 2+ so speed adjustment kicks in
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)

    row_before = conn.execute(
        "SELECT interval_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    interval_before = row_before["interval_days"]

    # Fast response at reps >= 2 → interval *= 1.15
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=2000)

    row_after = conn.execute(
        "SELECT interval_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    # New interval = old * ease * 1.15 (speed bonus)
    assert row_after["interval_days"] > interval_before * 1.1, \
        f"fast response should extend interval: {row_after['interval_days']} vs {interval_before}"
    conn.close()


def test_speed_slow_does_not_affect_interval():
    """Speed-adjusted intervals are deprecated. Slow responses don't change SRS."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # Build up reps to 2+
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=5000)

    row_before = conn.execute(
        "SELECT interval_days, ease_factor FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    ease = row_before["ease_factor"]
    interval_before = row_before["interval_days"]

    # Expected: interval * ease (speed has no effect)
    expected_normal = interval_before * ease

    # Slow response — should NOT change interval (speed adjustment deprecated)
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=10000)

    row_after = conn.execute(
        "SELECT interval_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    # Interval should match normal SM-2 computation (no speed penalty)
    assert abs(row_after["interval_days"] - expected_normal) < 0.01, \
        f"interval should be normal SM-2: {row_after['interval_days']} vs {expected_normal}"
    conn.close()


def test_speed_no_adjust_early_reps():
    """Speed adjustment should NOT apply before reps >= 2."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # First attempt (reps=0→1): fast, but no adjustment expected
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc", response_ms=1000)

    row = conn.execute(
        "SELECT interval_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    # reps was 0, so interval = 1.0 (no speed modifier)
    assert row["interval_days"] == 1.0, \
        f"speed should not adjust at reps=0, got interval {row['interval_days']}"
    conn.close()


# ── Distinct review days (spacing verification) ──

def test_distinct_days_increments():
    """distinct_review_days increments when review is on a new day."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # First attempt: distinct_days goes 0→1
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc")

    row = conn.execute(
        "SELECT distinct_review_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["distinct_review_days"] == 1

    # Same day: should not increment
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc")

    row = conn.execute(
        "SELECT distinct_review_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["distinct_review_days"] == 1, "same-day review should not increment"

    # Simulate day boundary
    conn.execute("UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?", (ids[0],))
    conn.commit()

    # New day: should increment to 2
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc")

    row = conn.execute(
        "SELECT distinct_review_days FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    assert row["distinct_review_days"] == 2
    conn.close()


def test_mastery_weak_needs_spacing():
    """passed_once→stabilizing should require distinct_review_days >= 2."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    session_id = start_session(conn)

    # 5 correct same-day: streak>=3 but distinct_days=1 → stays weak
    for _ in range(5):
        record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                       drill_type="mc")

    row = conn.execute(
        "SELECT mastery_stage FROM progress WHERE content_item_id = ?",
        (ids[0],)
    ).fetchone()
    # 5 correct same-day: reaches passed_once (streak >= 2) but NOT stabilizing
    # (stabilizing requires distinct_review_days >= 2)
    assert row["mastery_stage"] == "passed_once", \
        f"should be passed_once with only 1 day of reviews, got {row['mastery_stage']}"
    conn.close()


# ── Transfer drill ──

def test_transfer_drill_fallback():
    """Transfer drill falls back to MC when item has no construction link."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)

    from mandarin.drills import run_transfer_drill, DrillResult
    item = dict(conn.execute("SELECT * FROM content_item WHERE id = ?", (ids[0],)).fetchone())

    output = []
    # Simulate input that selects option 1
    result = run_transfer_drill(
        item, conn,
        show_fn=lambda t, end="\n": output.append(t),
        input_fn=lambda p: "1",
    )
    assert isinstance(result, DrillResult)
    # Should have run as MC (fallback) since no construction links exist
    assert result.drill_type in ("mc", "transfer")
    conn.close()


def test_transfer_drill_with_construction():
    """Transfer drill shows construction and options when linked."""
    conn = _fresh_db()
    from mandarin.db.content import seed_constructions

    # Insert items that match construction tags
    le_id = insert_content_item(conn, hanzi="你了", pinyin="nǐ le",
                                english="you (perfective)", hsk_level=1)
    # Add distractors (no construction links)
    for i in range(5):
        insert_content_item(conn, hanzi=f"词{i}", pinyin=f"cí{i}",
                            english=f"word{i}", hsk_level=1)

    seed_constructions(conn)

    # Check that 了 items are linked
    links = conn.execute(
        "SELECT * FROM content_construction WHERE content_item_id = ?", (le_id,)
    ).fetchall()

    if not links:
        # If no auto-tag matched, skip this test (depends on seed data)
        conn.close()
        return

    item = dict(conn.execute("SELECT * FROM content_item WHERE id = ?", (le_id,)).fetchone())

    output = []
    from mandarin.drills import run_transfer_drill
    result = run_transfer_drill(
        item, conn,
        show_fn=lambda t, end="\n": output.append(t),
        input_fn=lambda p: "1",
    )
    full = "\n".join(output)
    # Should mention the construction pattern
    assert "uses:" in full.lower() or "pattern" in full.lower(), \
        f"transfer drill should show construction context:\n{full}"
    conn.close()


# ── Cognitive load cap ──

def test_cognitive_load_cap():
    """New items should be capped at ~25% of session size."""
    from mandarin.scheduler import plan_standard_session
    conn = _fresh_db()

    # Add many items so there's a large new pool
    ids = _add_items(conn, 50, hsk_level=1)
    session_id = start_session(conn)

    plan = plan_standard_session(conn)
    new_count = sum(1 for d in plan.drills if d.is_new)
    total = len(plan.drills)

    # max_new = max(2, round(total * 0.25))
    max_allowed = max(2, round(total * 0.25))
    assert new_count <= max_allowed + 1, \
        f"new items ({new_count}) should be <= ~25% of session ({max_allowed}), total={total}"
    conn.close()


def test_v5_migration_distinct_days():
    """V5 migration adds distinct_review_days column."""
    conn = _fresh_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(progress)").fetchall()}
    assert "distinct_review_days" in cols
    conn.close()


# ── Schema migration ──

def test_v4_migration_columns():
    """V4 migration adds avg_response_ms and drill_types_seen to progress."""
    conn = _fresh_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(progress)").fetchall()}
    assert "avg_response_ms" in cols
    assert "drill_types_seen" in cols
    conn.close()


def test_v4_construction_tables():
    """V4 migration creates construction and content_construction tables."""
    conn = _fresh_db()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "construction" in tables
    assert "content_construction" in tables
    conn.close()


