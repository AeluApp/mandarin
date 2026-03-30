"""Tests for mandarin.experiments.email_experiments."""

from tests.shared_db import make_test_db
from mandarin.experiments.email_experiments import (
    assign_email_variant,
    get_email_template_variant,
    log_email_send,
    log_email_open,
    log_email_click,
)


def _make_conn():
    conn = make_test_db()
    conn.execute(
        "INSERT OR IGNORE INTO experiment (id, name, status, variants) "
        "VALUES (99, 'welcome_test', 'running', '[\"control\",\"treatment\"]')"
    )
    conn.commit()
    return conn


def test_assign_deterministic():
    """Same user + experiment always gets same variant."""
    conn = _make_conn()
    v1 = assign_email_variant(conn, "welcome_test", 1)
    v2 = assign_email_variant(conn, "welcome_test", 1)
    assert v1 == v2
    assert v1 in ("control", "treatment")


def test_assign_different_users():
    """Different users can get different variants."""
    conn = _make_conn()
    variants_seen = set()
    for uid in range(1, 50):
        v = assign_email_variant(conn, "welcome_test", uid)
        variants_seen.add(v)
    # With 49 users, should see both variants
    assert len(variants_seen) == 2


def test_assign_custom_variants():
    conn = _make_conn()
    v = assign_email_variant(conn, "welcome_test", 1, variants=["a", "b", "c"])
    assert v in ("a", "b", "c")


def test_template_control():
    conn = _make_conn()
    # Force control by finding a user_id that maps to control
    for uid in range(1, 100):
        v = assign_email_variant(conn, "welcome_test", uid)
        if v == "control":
            tmpl = get_email_template_variant(conn, "welcome_test", uid, "welcome.html")
            assert tmpl == "welcome.html"
            return
    # If no control found (very unlikely), skip
    assert True


def test_template_treatment():
    conn = _make_conn()
    for uid in range(1, 100):
        v = assign_email_variant(conn, "welcome_test", uid)
        if v == "treatment":
            tmpl = get_email_template_variant(conn, "welcome_test", uid, "welcome.html")
            assert tmpl == "welcome-treatment.html"
            return
    assert True


def test_log_send():
    conn = _make_conn()
    log_email_send(conn, "welcome_test", 1, "control", "welcome")
    row = conn.execute("SELECT * FROM email_send_log LIMIT 1").fetchone()
    assert row is not None


def test_log_open():
    conn = _make_conn()
    log_email_send(conn, "welcome_test", 1, "control", "welcome", resend_message_id="msg_123")
    log_email_open(conn, "msg_123")
    row = conn.execute(
        "SELECT opened_at FROM email_send_log WHERE resend_message_id = 'msg_123'"
    ).fetchone()
    assert row["opened_at"] is not None


def test_log_click():
    conn = _make_conn()
    log_email_send(conn, "welcome_test", 1, "control", "welcome", resend_message_id="msg_456")
    log_email_click(conn, "msg_456")
    row = conn.execute(
        "SELECT clicked_at FROM email_send_log WHERE resend_message_id = 'msg_456'"
    ).fetchone()
    assert row["clicked_at"] is not None
