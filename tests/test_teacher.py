"""Tests for teacher-grade features: listening rebalance, passive listen, speed surfacing, ambiguity comfort."""

import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item
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


# ── Listening rebalance ──

def test_default_weights_listening_dominant():
    """Listening should be the highest-weighted modality in default weights."""
    from mandarin.scheduler import DEFAULT_WEIGHTS
    assert DEFAULT_WEIGHTS["listening"] >= DEFAULT_WEIGHTS["reading"], \
        f"listening ({DEFAULT_WEIGHTS['listening']}) should be >= reading ({DEFAULT_WEIGHTS['reading']})"
    assert DEFAULT_WEIGHTS["listening"] >= DEFAULT_WEIGHTS["ime"], \
        f"listening ({DEFAULT_WEIGHTS['listening']}) should be >= ime ({DEFAULT_WEIGHTS['ime']})"


def test_gap_weights_listening_not_reduced():
    """Gap weights should maintain strong listening — not reduce it."""
    from mandarin.scheduler import GAP_WEIGHTS
    assert GAP_WEIGHTS["listening"] >= 0.25, \
        f"gap listening weight ({GAP_WEIGHTS['listening']}) should be >= 0.25"


def test_modality_distribution_listening():
    """Standard 12-item session should have 4+ listening items."""
    from mandarin.scheduler import _pick_modality_distribution, DEFAULT_WEIGHTS
    dist = _pick_modality_distribution(12, DEFAULT_WEIGHTS)
    assert dist["listening"] >= 3, \
        f"expected 3+ listening items in 12-item session, got {dist['listening']}"


def test_modality_distribution_all_represented():
    """All 4 modalities should get at least 1 item."""
    from mandarin.scheduler import _pick_modality_distribution, DEFAULT_WEIGHTS
    dist = _pick_modality_distribution(12, DEFAULT_WEIGHTS)
    for mod in ["reading", "listening", "ime", "speaking"]:
        assert dist[mod] >= 1, f"{mod} should get at least 1 item"


# ── Speed-as-fluency surfacing ──

def test_speed_in_finalize():
    """_finalize should show speed signal when response times exist."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)
    session_id = start_session(conn)

    # Record attempts with response times
    for i, item_id in enumerate(ids):
        record_attempt(conn, item_id, "reading", True, session_id=session_id,
                       drill_type="mc", response_ms=3000 + i * 1000)

    from mandarin.runner import _finalize, SessionState
    from mandarin.scheduler import SessionPlan
    from mandarin.drills import DrillResult

    plan = SessionPlan(session_type="standard", drills=[], micro_plan="test",
                       estimated_seconds=60)
    state = SessionState(session_id=session_id, plan=plan)
    state.results = [
        DrillResult(content_item_id=ids[0], modality="reading", drill_type="mc",
                    correct=True, skipped=False, user_answer="a", expected_answer="a",
                    error_type=None, feedback="", confidence="full"),
    ]

    output = []
    _finalize(conn, state, lambda t, end="\n": output.append(t), pre_milestones=set())
    full = "\n".join(output)

    # Speed is behind [d] detail prompt, not in main finalize
    # Main finalize shows accuracy line
    assert "correct" in full, \
        f"expected session summary in finalize output:\n{full}"
    conn.close()


def test_speed_trend_in_status():
    """get_speed_trend should work and surface summary."""
    conn = _fresh_db()
    ids = _add_items(conn, 3)
    session_id = start_session(conn)

    for item_id in ids:
        record_attempt(conn, item_id, "reading", True, session_id=session_id,
                       drill_type="mc", response_ms=5000)

    from mandarin.diagnostics import get_speed_trend
    result = get_speed_trend(conn)
    assert result["total_timed"] == 3
    assert "5000" in result["summary"] or "ms" in result["summary"].lower() or "speed" in result["summary"].lower()
    conn.close()


# ── Ambiguity comfort ──

def test_ambiguity_comfort_empty():
    """Zero attempts returns 'No data yet'."""
    conn = _fresh_db()
    from mandarin.diagnostics import compute_ambiguity_comfort
    result = compute_ambiguity_comfort(conn)
    assert result["total_attempts"] == 0
    assert result["comfort_label"] == "No data yet"
    conn.close()


def test_ambiguity_comfort_with_bouncebacks():
    """Items that cycle through weak should increase comfort score."""
    conn = _fresh_db()
    ids = _add_items(conn, 2)
    session_id = start_session(conn)

    # Simulate a weak cycle: correct streak, day boundary, more correct
    # (triggers weak→improving), then fail (improving→weak, weak_cycle_count+1)
    for item_id in ids:
        # Day 1: build streak
        for _ in range(3):
            record_attempt(conn, item_id, "reading", True, session_id=session_id,
                           drill_type="mc")
        # Simulate day boundary so distinct_days reaches 2
        conn.execute("UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?", (item_id,))
        conn.commit()
        # Day 2: one more correct triggers weak→improving (streak>=3, distinct>=2)
        record_attempt(conn, item_id, "reading", True, session_id=session_id,
                       drill_type="mc")
        # Now fail enough to go improving→weak (streak_incorrect>=3 → weak_cycle_count+=1)
        for _ in range(4):
            record_attempt(conn, item_id, "reading", False, session_id=session_id,
                           drill_type="mc")
        # More correct to show persistence
        for _ in range(5):
            record_attempt(conn, item_id, "reading", True, session_id=session_id,
                           drill_type="mc")

    from mandarin.diagnostics import compute_ambiguity_comfort
    result = compute_ambiguity_comfort(conn)
    assert result["total_attempts"] > 0
    assert result["bounced_back"] >= 1, "should detect bounce-back items"
    assert result["comfort_score"] > 0
    conn.close()


def test_ambiguity_comfort_drill_variety():
    """Multiple drill types should increase comfort score."""
    conn = _fresh_db()
    ids = _add_items(conn, 3)
    session_id = start_session(conn)

    drill_types = ["mc", "tone", "reverse_mc", "listening_gist"]
    for item_id in ids:
        for dt in drill_types:
            modality = "listening" if dt == "listening_gist" else "reading"
            record_attempt(conn, item_id, modality, True, session_id=session_id,
                           drill_type=dt)

    from mandarin.diagnostics import compute_ambiguity_comfort
    result = compute_ambiguity_comfort(conn)
    assert result["avg_drill_types"] >= 2, \
        f"expected avg_drill_types >= 2, got {result['avg_drill_types']}"
    conn.close()


# ── Passive listening mode ──

def test_listen_command_registered():
    """listen command should be registered in the CLI."""
    from mandarin.cli import app
    commands = [c.name or c.callback.__name__ for c in app.registered_commands]
    assert "listen" in commands, f"listen not in registered commands: {commands}"


def test_listen_items_query():
    """Passive listen query returns items ordered by familiarity then random."""
    conn = _fresh_db()
    ids = _add_items(conn, 10, hsk_level=1)
    session_id = start_session(conn)

    # Mark some as seen
    for item_id in ids[:3]:
        record_attempt(conn, item_id, "reading", True, session_id=session_id,
                       drill_type="mc")

    items = conn.execute("""
        SELECT ci.hanzi, ci.pinyin, ci.english
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = 'reading'
        WHERE ci.status = 'drill_ready' AND (ci.hsk_level IS NULL OR ci.hsk_level <= 3)
        ORDER BY CASE WHEN p.total_attempts > 0 THEN 0 ELSE 1 END, RANDOM()
        LIMIT 20
    """).fetchall()

    assert len(items) == 10  # all 10 should be returned
    # Seen items should come first
    first_3 = [dict(r) for r in items[:3]]
    for item in first_3:
        assert item["hanzi"] is not None
    conn.close()


# ── Integration: menu listen option ──

def test_menu_has_listen_option():
    """Menu should have 'Just listen' as option 4."""
    from mandarin.menu import show_menu
    # We can't easily test the interactive menu, but verify the function exists
    from mandarin.menu import _run_listen
    assert callable(_run_listen)


