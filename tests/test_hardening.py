"""Hardening tests — boundary conditions, malformed input, defensive invariants.

Tests for:
- Malformed scenario JSON validation
- Empty DB state for all report paths
- Velocity with burst sessions
- Schema version tracking
- Scenario validation edge cases
- Report/diagnostics with None values
"""

import json
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from mandarin import db
from mandarin.db.core import _migrate, _get_schema_version
from mandarin.reports import generate_status_report, generate_session_summary
from mandarin.diagnostics import (
    compute_velocity, project_forecast, assess_quick,
    format_confidence, estimate_levels_lite,
)
from mandarin.scenario_loader import (
    _validate_scenario, load_scenario_file, determine_support_level,
)


# ── Test DB helpers ──────────────────────────────

def _make_test_db():
    """Create a fresh test database with schema + migrations + seed profile."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


def _seed_items(conn, n=20):
    for i in range(n):
        conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status)
            VALUES (?, ?, ?, ?, 'drill_ready')
        """, (f"字{i}", f"zi{i % 4 + 1}", f"word{i}", (i % 3) + 1))
    conn.commit()


def _seed_sessions(conn, n=1, spread_days=None):
    """Insert n sessions. If spread_days is None, spread across n days.
    If spread_days=0, put all sessions on today (burst).
    """
    for i in range(n):
        if spread_days is not None:
            day_offset = max(0, spread_days - i) if spread_days > 0 else 0
        else:
            day_offset = n - i
        session_date = (date.today() - timedelta(days=day_offset)).isoformat()
        conn.execute("""
            INSERT INTO session_log
                (session_type, items_planned, items_completed, items_correct,
                 started_at, ended_at, duration_seconds,
                 session_started_hour, session_day_of_week)
            VALUES ('standard', 10, 8, 6, ?, ?, 300, 10, ?)
        """, (
            f"{session_date} 10:00:00",
            f"{session_date} 10:05:00",
            (date.today() - timedelta(days=day_offset)).weekday(),
        ))
    conn.execute("""
        UPDATE learner_profile SET total_sessions = ? WHERE id = 1
    """, (n,))
    conn.commit()


# ── Velocity burst tests ──────────────────────────────

def test_velocity_burst_3_sessions_1_day():
    """3 sessions in 1 day should NOT report 21/week."""
    sessions = []
    today = date.today().isoformat()
    for i in range(3):
        sessions.append({
            "started_at": f"{today} {10+i}:00:00",
            "items_completed": 10,
            "items_correct": 7,
        })
    vel = compute_velocity(sessions)
    # With 7-day minimum window: 3/7*7 = 3.0, NOT 21
    assert vel["sessions_per_week"] <= 5.0, \
        f"Burst inflation: {vel['sessions_per_week']} sessions/week from 3 sessions in 1 day"


def test_velocity_burst_5_sessions_2_days():
    """5 sessions in 2 days should be dampened."""
    sessions = []
    today = date.today()
    for i in range(5):
        d = today - timedelta(days=i % 2)
        sessions.append({
            "started_at": f"{d.isoformat()} {10+i}:00:00",
            "items_completed": 10,
            "items_correct": 7,
        })
    vel = compute_velocity(sessions)
    assert vel["sessions_per_week"] <= 7.0, \
        f"Burst inflation: {vel['sessions_per_week']} sessions/week from 5 sessions in 2 days"


def test_velocity_cap():
    """Even with extreme data, sessions_per_week should be capped at 14."""
    sessions = []
    today = date.today()
    for i in range(20):
        d = today - timedelta(days=i % 3)
        sessions.append({
            "started_at": f"{d.isoformat()} {8+i}:00:00",
            "items_completed": 10,
            "items_correct": 7,
        })
    vel = compute_velocity(sessions)
    assert vel["sessions_per_week"] <= 14.0


def test_velocity_empty():
    """Empty sessions list should return 0."""
    vel = compute_velocity([])
    assert vel["sessions_per_week"] == 0


def test_velocity_single_session():
    """Single session should return low confidence."""
    sessions = [{"started_at": f"{date.today().isoformat()} 10:00:00",
                 "items_completed": 10, "items_correct": 7}]
    vel = compute_velocity(sessions)
    assert vel["confidence"] <= 0.15


# ── Scenario validation tests ──────────────────────────────

def test_validate_missing_title():
    errors = _validate_scenario({"tree": {"turns": []}}, "test.json")
    assert any("missing 'title'" in e for e in errors)


def test_validate_missing_turns():
    errors = _validate_scenario({"title": "Test", "tree": {}}, "test.json")
    assert any("turns" in e for e in errors)


def test_validate_empty_turns():
    errors = _validate_scenario({"title": "Test", "tree": {"turns": []}}, "test.json")
    assert any("turns" in e for e in errors)


def test_validate_player_missing_options():
    data = {"title": "Test", "tree": {"turns": [
        {"speaker": "player"}
    ]}}
    errors = _validate_scenario(data, "test.json")
    assert any("options" in e for e in errors)


def test_validate_npc_missing_text():
    data = {"title": "Test", "tree": {"turns": [
        {"speaker": "npc"}
    ]}}
    errors = _validate_scenario(data, "test.json")
    assert any("text_zh" in e for e in errors)


def test_validate_option_missing_score():
    data = {"title": "Test", "tree": {"turns": [
        {"speaker": "player", "options": [{"text_zh": "你好"}]}
    ]}}
    errors = _validate_scenario(data, "test.json")
    assert any("score" in e for e in errors)


def test_validate_option_missing_text_zh():
    data = {"title": "Test", "tree": {"turns": [
        {"speaker": "player", "options": [{"score": 1.0}]}
    ]}}
    errors = _validate_scenario(data, "test.json")
    assert any("text_zh" in e for e in errors)


def test_validate_valid_scenario():
    data = {
        "title": "Test",
        "tree": {
            "turns": [
                {"speaker": "npc", "text_zh": "你好"},
                {"speaker": "player", "options": [
                    {"text_zh": "你好", "score": 1.0}
                ]}
            ]
        }
    }
    errors = _validate_scenario(data, "test.json")
    assert errors == []


def test_validate_bad_hsk_level():
    data = {
        "title": "Test", "hsk_level": "three",
        "tree": {"turns": [
            {"speaker": "npc", "text_zh": "你好"},
        ]}
    }
    errors = _validate_scenario(data, "test.json")
    assert any("hsk_level" in e for e in errors)


def test_load_malformed_json():
    """Loading a malformed JSON file should return error, not crash."""
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{broken json")
    tmp.close()
    conn, path = _make_test_db()
    try:
        result = load_scenario_file(conn, tmp.name)
        assert result["added"] is False
        assert "invalid JSON" in result["reason"]
    finally:
        conn.close()
        os.unlink(tmp.name)
        os.unlink(str(path))


def test_load_validation_failure():
    """Loading a JSON with missing required fields should return validation error."""
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"title": "Test", "tree": {}}, tmp)
    tmp.close()
    conn, path = _make_test_db()
    try:
        result = load_scenario_file(conn, tmp.name)
        assert result["added"] is False
        assert "validation failed" in result["reason"]
    finally:
        conn.close()
        os.unlink(tmp.name)
        os.unlink(str(path))


# ── Report boundary tests ──────────────────────────────

def test_report_empty_db():
    """Report on fresh DB should not crash."""
    conn, path = _make_test_db()
    try:
        report = generate_status_report(conn)
        assert "No sessions yet" in report
    finally:
        conn.close()
        import os; os.unlink(str(path))


def test_report_1_session():
    """Report with 1 session should work without crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, 1)
    try:
        report = generate_status_report(conn)
        assert "Sessions: 1" in report
    finally:
        conn.close()
        import os; os.unlink(str(path))


def test_report_session_summary_missing():
    """Session summary for nonexistent session should return clean message."""
    conn, path = _make_test_db()
    try:
        summary = generate_session_summary(conn, 9999)
        assert "not found" in summary
    finally:
        conn.close()
        import os; os.unlink(str(path))


# ── Forecast boundary tests ──────────────────────────────

def test_forecast_0_sessions():
    """Forecast at 0 sessions should not crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    try:
        fc = project_forecast(conn)
        assert fc["pace"]["reliable"] is False
        assert fc["pace"]["total_sessions"] == 0
    finally:
        conn.close()
        import os; os.unlink(str(path))


def test_forecast_1_session():
    """Forecast at 1 session should not crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, 1)
    try:
        fc = project_forecast(conn)
        assert fc["pace"]["reliable"] is False
    finally:
        conn.close()
        import os; os.unlink(str(path))


def test_assess_quick_below_threshold():
    """assess_quick with <10 sessions should return not ready."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, 5)
    try:
        result = assess_quick(conn)
        assert result["ready"] is False
        assert result["sessions_needed"] == 5
    finally:
        conn.close()
        import os; os.unlink(str(path))


# ── Schema version tests ──────────────────────────────

def test_schema_version_created():
    """Schema version table should be created by migration."""
    conn, path = _make_test_db()
    try:
        version = _get_schema_version(conn)
        assert version == db.SCHEMA_VERSION
    finally:
        conn.close()
        import os; os.unlink(str(path))


def test_schema_version_idempotent():
    """Running migration twice should not fail."""
    conn, path = _make_test_db()
    try:
        _migrate(conn)  # Second call
        version = _get_schema_version(conn)
        assert version == db.SCHEMA_VERSION
    finally:
        conn.close()
        import os; os.unlink(str(path))


# ── Estimate levels boundary tests ──────────────────────────────

def test_estimate_levels_empty_db():
    """Level estimation on empty DB should not crash."""
    conn, path = _make_test_db()
    try:
        levels = estimate_levels_lite(conn)
        for mod in ["reading", "listening", "speaking", "ime"]:
            assert levels[mod]["level"] >= 1.0
            assert levels[mod]["confidence"] >= 0.0
    finally:
        conn.close()
        import os; os.unlink(str(path))


def test_format_confidence_zero():
    assert format_confidence(0.0) == "no data yet"


def test_format_confidence_full():
    result = format_confidence(0.9, 200)
    assert "90%" in result


# ── Mastery display filtering ──────────────────────────────

def test_mastery_no_unseen_levels():
    """get_mastery_by_hsk should include all levels with items, but display
    should filter to seen-only."""
    conn, path = _make_test_db()
    _seed_items(conn, 20)  # HSK 1-3 items
    try:
        mastery = db.get_mastery_by_hsk(conn)
        # All levels should exist in raw data
        assert len(mastery) > 0
        # Filter like the display code does
        active = {k: v for k, v in mastery.items() if v.get("seen", 0) > 0}
        # With no sessions run, seen should be 0 for all levels
        assert len(active) == 0
    finally:
        conn.close()
        import os; os.unlink(str(path))

