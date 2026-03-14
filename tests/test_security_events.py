"""Tests for security event logging — logout, rate limit, admin access, PII redaction.

Verifies that security events are properly recorded in the audit log,
PII is redacted in structured log output, and critical alerting works.
"""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from mandarin.auth import create_user, authenticate
from mandarin.security import (
    log_security_event,
    SecurityEvent,
    Severity,
    _redact_pii,
    _send_critical_alert,
)
from werkzeug.security import generate_password_hash as _orig_gen


def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


TEST_EMAIL = "security@example.com"
TEST_PASSWORD = "securepass1234545"


def _create_test_user(conn):
    return create_user(conn, TEST_EMAIL, TEST_PASSWORD, "Test")


class TestSecurityEventLogging:

    def test_log_security_event_records_to_db(self, test_db):
        conn, _ = test_db
        log_security_event(conn, SecurityEvent.LOGIN_SUCCESS, user_id=1,
                           details="test event")
        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'login_success' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["user_id"] == 1
        assert "test event" in row["details"]

    def test_login_success_logged(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)
        authenticate(conn, TEST_EMAIL, TEST_PASSWORD)
        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'login_success' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None

    def test_login_failed_logged(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)
        authenticate(conn, TEST_EMAIL, "wrongpassword")
        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'login_failed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None

    def test_register_logged(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)
        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'register' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None

    def test_mfa_events_in_enum(self):
        """Verify MFA security events exist in the enum."""
        assert SecurityEvent.MFA_ENABLED.value == "mfa_enabled"
        assert SecurityEvent.MFA_DISABLED.value == "mfa_disabled"
        assert SecurityEvent.MFA_VERIFIED.value == "mfa_verified"
        assert SecurityEvent.MFA_FAILED.value == "mfa_failed"

    def test_all_severity_levels(self, test_db):
        conn, _ = test_db
        for sev in Severity:
            log_security_event(conn, SecurityEvent.LOGIN_SUCCESS, severity=sev)
        rows = conn.execute(
            "SELECT DISTINCT severity FROM security_audit_log"
        ).fetchall()
        severities = {r["severity"] for r in rows}
        assert severities == {"INFO", "WARNING", "ERROR", "CRITICAL"}

    def test_logout_event_type_exists(self):
        """Verify LOGOUT event type exists in enum."""
        assert SecurityEvent.LOGOUT.value == "logout"

    def test_token_event_types_exist(self):
        """Verify token event types exist in enum."""
        assert SecurityEvent.TOKEN_ISSUED.value == "token_issued"
        assert SecurityEvent.TOKEN_REFRESHED.value == "token_refreshed"
        assert SecurityEvent.TOKEN_REVOKED.value == "token_revoked"

    def test_csrf_and_rate_limit_events_exist(self):
        """Verify CSRF and rate limit event types exist."""
        assert SecurityEvent.CSRF_VIOLATION.value == "csrf_violation"
        assert SecurityEvent.RATE_LIMIT_HIT.value == "rate_limit_hit"

    def test_admin_access_event_exists(self):
        """Verify admin access event type exists."""
        assert SecurityEvent.ADMIN_ACCESS.value == "admin_access"
        assert SecurityEvent.ACCESS_DENIED.value == "access_denied"

    def test_log_event_with_string_event_type(self, test_db):
        """log_security_event accepts raw string event types, not just enums."""
        conn, _ = test_db
        log_security_event(conn, "custom_event", user_id=1, details="custom detail")
        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'custom_event' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["event_type"] == "custom_event"

    def test_log_event_with_string_severity(self, test_db):
        """log_security_event accepts raw string severity, not just Severity enum."""
        conn, _ = test_db
        log_security_event(conn, SecurityEvent.LOGIN_SUCCESS, severity="WARNING")
        row = conn.execute(
            "SELECT * FROM security_audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["severity"] == "WARNING"

    def test_log_event_without_details(self, test_db):
        """log_security_event works with no details argument."""
        conn, _ = test_db
        log_security_event(conn, SecurityEvent.LOGOUT, user_id=1)
        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'logout' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None

    def test_log_event_stores_timestamp(self, test_db):
        conn, _ = test_db
        log_security_event(conn, SecurityEvent.LOGIN_SUCCESS, user_id=1)
        row = conn.execute(
            "SELECT timestamp FROM security_audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["timestamp"] is not None
        # Verify it's a valid datetime format
        from datetime import datetime
        dt = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        assert dt.year >= 2026


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

class TestPIIRedaction:

    def test_redact_email(self):
        """Email addresses are redacted: alice@example.com -> a***@example.com."""
        text = "User login from alice@example.com failed"
        result = _redact_pii(text)
        assert "alice@example.com" not in result
        assert "a***@example.com" in result

    def test_redact_preserves_surrounding_text(self):
        text = "attempt by bob@test.org at 12:00"
        result = _redact_pii(text)
        assert "attempt by" in result
        assert "at 12:00" in result
        assert "bob@test.org" not in result
        assert "b***@test.org" in result

    def test_redact_ip_address(self):
        """IP addresses have last octet masked: 192.168.1.42 -> 192.168.1.xxx."""
        text = "Request from 192.168.1.42"
        result = _redact_pii(text)
        assert "192.168.1.42" not in result
        assert "192.168.1.xxx" in result

    def test_redact_both_email_and_ip(self):
        text = "User alice@example.com from 10.0.0.1"
        result = _redact_pii(text)
        assert "alice@example.com" not in result
        assert "10.0.0.1" not in result
        assert "a***@example.com" in result
        assert "10.0.0.xxx" in result

    def test_redact_empty_string_returns_empty(self):
        assert _redact_pii("") == ""

    def test_redact_none_returns_none(self):
        assert _redact_pii(None) is None

    def test_redact_no_pii_unchanged(self):
        text = "Normal log message with no PII"
        assert _redact_pii(text) == text

    def test_redact_multiple_emails(self):
        text = "from alice@a.com to bob@b.com"
        result = _redact_pii(text)
        assert "alice@a.com" not in result
        assert "bob@b.com" not in result
        assert "a***@a.com" in result
        assert "b***@b.com" in result


# ---------------------------------------------------------------------------
# Critical event alerting
# ---------------------------------------------------------------------------

class TestCriticalAlerting:

    def test_critical_severity_triggers_alert(self, test_db):
        """A CRITICAL severity event calls _send_critical_alert."""
        conn, _ = test_db
        with patch("mandarin.security._send_critical_alert") as mock_alert:
            log_security_event(
                conn, SecurityEvent.ACCOUNT_LOCKED, user_id=1,
                details="suspicious activity", severity=Severity.CRITICAL,
            )
            mock_alert.assert_called_once()
            args = mock_alert.call_args
            assert args[0][0] == "account_locked"  # event_str
            assert args[0][1] == 1  # user_id

    def test_non_critical_severity_does_not_trigger_alert(self, test_db):
        """Non-critical events should not trigger _send_critical_alert."""
        conn, _ = test_db
        with patch("mandarin.security._send_critical_alert") as mock_alert:
            log_security_event(
                conn, SecurityEvent.LOGIN_SUCCESS, user_id=1,
                severity=Severity.INFO,
            )
            mock_alert.assert_not_called()

    def test_alert_delivery_failure_logged_to_db(self, test_db):
        """When both webhook and email fail, alert_delivery_failure is logged."""
        conn, _ = test_db
        with patch("mandarin.settings.ALERT_WEBHOOK_URL", ""), \
             patch("mandarin.settings.ADMIN_EMAIL", ""):
            _send_critical_alert("test_event", user_id=1, details="test", conn=conn)

        row = conn.execute(
            "SELECT * FROM security_audit_log WHERE event_type = 'alert_delivery_failure' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert "test_event" in row["details"]
        assert row["severity"] == "CRITICAL"

    def test_webhook_delivery_attempted(self, test_db):
        """When ALERT_WEBHOOK_URL is set, requests.post is called."""
        conn, _ = test_db
        mock_post = MagicMock()
        with patch("mandarin.settings.ALERT_WEBHOOK_URL", "https://hooks.example.com/alert"), \
             patch("mandarin.settings.ADMIN_EMAIL", ""), \
             patch("requests.post", mock_post):
            _send_critical_alert("test_event", user_id=1, details="critical issue", conn=conn)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["severity"] == "CRITICAL"


# ---------------------------------------------------------------------------
# Table-not-exist fallback
# ---------------------------------------------------------------------------

class TestTableNotExistFallback:

    def test_log_event_graceful_when_table_missing(self):
        """log_security_event does not crash if security_audit_log table is missing."""
        # Create a bare in-memory DB with no tables
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Should not raise — just logs a warning
        log_security_event(conn, SecurityEvent.LOGIN_SUCCESS, user_id=1, details="test")
        conn.close()
