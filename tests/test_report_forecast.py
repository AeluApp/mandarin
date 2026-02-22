"""Regression tests for progress report and forecast.

Verifies that reports and forecasts don't crash at any session count,
including fresh DBs, <8 sessions, 8-11, 12+, and >=25 sessions.
Also tests the new project_forecast() structure.
"""

import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from mandarin import db
from mandarin.db.core import _migrate
from mandarin.reports import generate_status_report
from mandarin.diagnostics import (
    assess_quick, _project_milestones, compute_velocity,
    project_forecast, _compute_tone_stats, _compute_mastery_rate_per_modality,
    _compute_core_stability, _projection_confidence_label,
    PACE_RELIABILITY_THRESHOLD, PROJECTION_RANGE_THRESHOLD,
)


def _make_test_db():
    """Create a fresh test database with schema + migrations + seed profile."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)  # Apply all migrations (adds columns not in base schema)
    # Ensure profile exists
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


def _seed_items(conn, n=20):
    """Insert n dummy content items."""
    for i in range(n):
        conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status)
            VALUES (?, ?, ?, ?, 'drill_ready')
        """, (f"字{i}", f"zi{i % 4 + 1}", f"word{i}", (i % 3) + 1))
    conn.commit()


def _seed_sessions(conn, n=1):
    """Insert n dummy sessions and some progress data."""
    for i in range(n):
        session_date = (date.today() - timedelta(days=n - i)).isoformat()
        conn.execute("""
            INSERT INTO session_log
                (session_type, items_planned, items_completed, items_correct,
                 started_at, ended_at, duration_seconds,
                 session_started_hour, session_day_of_week)
            VALUES ('standard', 10, 8, 6, ?, ?, 300, 10, ?)
        """, (
            f"{session_date} 10:00:00",
            f"{session_date} 10:05:00",
            (date.today() - timedelta(days=n - i)).weekday(),
        ))
    conn.execute("""
        UPDATE learner_profile SET total_sessions = ?, last_session_date = ?
        WHERE id = 1
    """, (n, date.today().isoformat()))
    conn.commit()

    # Seed some progress rows
    items = conn.execute("SELECT id FROM content_item LIMIT 10").fetchall()
    for item in items:
        conn.execute("""
            INSERT OR IGNORE INTO progress
                (content_item_id, modality, total_attempts, total_correct,
                 streak_correct, last_review_date, next_review_date)
            VALUES (?, 'reading', 5, 4, 2, ?, ?)
        """, (item["id"], date.today().isoformat(), date.today().isoformat()))
    conn.commit()


def test_report_fresh_db():
    """Progress report on a fresh DB with 0 sessions should not crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    try:
        report = generate_status_report(conn)
        assert isinstance(report, str)
        assert "No sessions yet" in report
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_report_few_sessions():
    """Progress report with <10 sessions should not crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=5)
    try:
        report = generate_status_report(conn)
        assert isinstance(report, str)
        assert "more session" in report  # "N more sessions until diagnostics"
        assert "KeyError" not in report
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_report_with_diagnostics():
    """Progress report with >=10 sessions should show projections without crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=15)
    try:
        report = generate_status_report(conn)
        assert isinstance(report, str)
        # Should reach the projections section without KeyError
        assert "Projections" in report or "Estimated Levels" in report or "more session" not in report
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_assess_quick_projection_schema():
    """Projection dicts from assess_quick should have required keys."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=15)
    try:
        result = assess_quick(conn)
        if result.get("ready") and result.get("projections"):
            for p in result["projections"]:
                # These keys are required by all consumers
                assert "current" in p, f"Missing 'current' in projection: {p.keys()}"
                assert "target" in p, f"Missing 'target' in projection: {p.keys()}"
                assert "calendar" in p, f"Missing 'calendar' in projection: {p.keys()}"
                assert "confidence" in p, f"Missing 'confidence' in projection: {p.keys()}"
                # 'modality' should NOT be expected (it's an overall milestone)
                # but criteria and bottleneck should be present
                assert "criteria" in p, f"Missing 'criteria' in projection: {p.keys()}"
                assert "bottleneck" in p, f"Missing 'bottleneck' in projection: {p.keys()}"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_forecast_no_crash_at_low_volume():
    """Forecast on a DB with <15 sessions should not crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=12)
    try:
        result = assess_quick(conn)
        # Should either be not ready, or have valid projections
        if result.get("ready"):
            projections = result.get("projections", [])
            # Projections may be empty (no next milestone) — that's OK
            for p in projections:
                # Verify no KeyError when formatting
                _ = f"HSK {p['current']:.1f} → {p['target']:.0f} {p['calendar']} · {p['confidence']}"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_project_milestones_empty_velocity():
    """_project_milestones with zero velocity should not crash or infinite-loop."""
    conn, path = _make_test_db()
    _seed_items(conn)
    try:
        levels = {"reading": {"level": 1.0, "confidence": 0.1}}
        velocity = {"sessions_per_week": 0, "confidence": 0.0}
        projections = _project_milestones(conn, levels, velocity)
        assert isinstance(projections, list)
        for p in projections:
            assert "sessions_needed" in p
            assert p["sessions_needed"] >= 1  # No infinite/zero
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── New project_forecast() tests ──────────────────────────────

def test_project_forecast_fresh_db():
    """project_forecast on a fresh DB (0 sessions) should not crash."""
    conn, path = _make_test_db()
    _seed_items(conn)
    try:
        fc = project_forecast(conn)
        assert isinstance(fc, dict)
        assert "pace" in fc
        assert "modality_projections" in fc
        assert "aspirational" in fc
        assert "total_sessions" in fc
        assert fc["total_sessions"] == 0
        assert fc["pace"]["reliable"] is False
        assert fc["pace"]["confidence_label"] == "too_early"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_project_forecast_low_sessions():
    """project_forecast with <8 sessions: no timeline projections, pace unreliable."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=5)
    try:
        fc = project_forecast(conn)
        assert fc["pace"]["reliable"] is False
        # Modality projections should have levels but no milestones
        for mod in ["reading", "listening", "speaking", "ime"]:
            mp = fc["modality_projections"][mod]
            assert "current_level" in mp
            assert mp["milestones"] == []
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_project_forecast_mid_sessions():
    """project_forecast with 8-11 sessions: single expected values, no ranges."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=10)
    try:
        fc = project_forecast(conn)
        assert fc["pace"]["reliable"] is True
        # Check that milestones have expected but NOT optimistic/pessimistic
        for mod in ["reading", "listening", "speaking", "ime"]:
            milestones = fc["modality_projections"][mod].get("milestones", [])
            for m in milestones:
                assert "expected" in m["sessions"]
                assert "optimistic" not in m["sessions"], \
                    f"Shouldn't have ranges at {fc['total_sessions']} sessions"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_project_forecast_high_sessions():
    """project_forecast with >=12 sessions: ranges should be present."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=15)
    try:
        fc = project_forecast(conn)
        assert fc["pace"]["reliable"] is True
        # Check that milestones have ranges
        for mod in ["reading", "listening", "speaking", "ime"]:
            milestones = fc["modality_projections"][mod].get("milestones", [])
            for m in milestones:
                assert "expected" in m["sessions"]
                assert "optimistic" in m["sessions"], \
                    f"Should have ranges at {fc['total_sessions']} sessions"
                assert "pessimistic" in m["sessions"]
                assert m["sessions"]["optimistic"] <= m["sessions"]["expected"]
                assert m["sessions"]["expected"] <= m["sessions"]["pessimistic"]
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_project_forecast_structure_complete():
    """project_forecast returns all expected keys in a complete structure."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=15)
    try:
        fc = project_forecast(conn)
        # Pace
        pace = fc["pace"]
        assert "sessions_per_week" in pace
        assert "confidence_label" in pace
        assert "reliable" in pace
        assert "total_sessions" in pace
        assert "message" in pace

        # Modality projections
        for mod in ["reading", "listening", "speaking", "ime"]:
            assert mod in fc["modality_projections"]
            mp = fc["modality_projections"][mod]
            assert "current_level" in mp
            assert "milestones" in mp

        # Tone
        assert "tone" in fc["modality_projections"]
        tone = fc["modality_projections"]["tone"]
        assert "tone_error_rate" in tone
        assert "target" in tone

        # Aspirational
        assert "core_stability" in fc["aspirational"]
        cs = fc["aspirational"]["core_stability"]
        assert "pct" in cs
        assert "description" in cs
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_projection_confidence_label():
    """_projection_confidence_label returns correct labels for session thresholds."""
    assert _projection_confidence_label(0.0, 3) == "too_early"
    assert _projection_confidence_label(0.5, 5) == "too_early"
    assert _projection_confidence_label(0.3, 10) == "rough"
    assert _projection_confidence_label(0.5, 14) == "fair"
    assert _projection_confidence_label(0.8, 30) == "good"
    assert _projection_confidence_label(0.1, 9) == "low"


def test_compute_tone_stats():
    """_compute_tone_stats should not crash on empty error_log."""
    conn, path = _make_test_db()
    _seed_items(conn)
    try:
        stats = _compute_tone_stats(conn)
        assert isinstance(stats, dict)
        assert "tone_error_rate" in stats
        assert stats["tone_error_rate"] >= 0.0
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_compute_core_stability():
    """_compute_core_stability should not crash and return valid percentages."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=5)
    try:
        cs = _compute_core_stability(conn)
        assert isinstance(cs, dict)
        assert 0 <= cs["pct"] <= 100
        assert "description" in cs
    finally:
        conn.close()
        path.unlink(missing_ok=True)


def test_compute_mastery_rate_per_modality():
    """_compute_mastery_rate_per_modality should return rates for all 4 modalities."""
    conn, path = _make_test_db()
    _seed_items(conn)
    _seed_sessions(conn, n=5)
    try:
        rates = _compute_mastery_rate_per_modality(conn)
        assert isinstance(rates, dict)
        for mod in ["reading", "listening", "speaking", "ime"]:
            assert mod in rates
            assert rates[mod] >= 0.5  # Floor is 0.5
    finally:
        conn.close()
        path.unlink(missing_ok=True)

