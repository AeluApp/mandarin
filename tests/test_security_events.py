"""Tests for security event logging — logout, rate limit, admin access.

Verifies that security events are properly recorded in the audit log.
"""

from unittest.mock import patch

import pytest

from mandarin.auth import create_user, authenticate
from mandarin.security import log_security_event, SecurityEvent, Severity
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
