"""Tests for mandarin.web.andon — quality alerting system."""

from tests.shared_db import make_test_db
from mandarin.web.andon import fire_andon, get_andon_dashboard


def _make_conn():
    return make_test_db()


def test_fire_andon_basic():
    conn = _make_conn()
    fire_andon(conn, "spc_violation", "warning", "Test alert")
    row = conn.execute("SELECT * FROM andon_event LIMIT 1").fetchone()
    assert row is not None
    assert row["event_type"] == "spc_violation"
    assert row["severity"] == "warning"
    assert row["summary"] == "Test alert"


def test_fire_andon_with_details():
    conn = _make_conn()
    fire_andon(conn, "dpmo_exceeded", "critical", "DPMO above threshold", {"dpmo": 70000})
    row = conn.execute("SELECT details FROM andon_event LIMIT 1").fetchone()
    assert row is not None
    assert "70000" in row["details"]


def test_fire_andon_info_severity():
    conn = _make_conn()
    fire_andon(conn, "routine_check", "info", "All clear")
    row = conn.execute("SELECT * FROM andon_event LIMIT 1").fetchone()
    assert row["severity"] == "info"


def test_get_dashboard_empty():
    conn = _make_conn()
    events = get_andon_dashboard(conn, hours=72)
    assert events == []


def test_get_dashboard_with_events():
    conn = _make_conn()
    fire_andon(conn, "spc_violation", "warning", "Alert 1")
    fire_andon(conn, "dpmo_exceeded", "critical", "Alert 2")
    events = get_andon_dashboard(conn, hours=72)
    assert len(events) == 2
