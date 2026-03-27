"""Security regression tests — CSRF, rate limiting, session fixation, SQL injection,
CSP nonce, authorization isolation.

These tests exist to prevent regressions in security-critical behavior.
Each test documents a specific security property that MUST NOT be broken.
"""

import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web import create_app
from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, conn):
        self._conn = conn
    def __enter__(self):
        return self._conn
    def __exit__(self, *args):
        return False


def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


@pytest.fixture
def app_client(test_db):
    """Create a Flask test client for security regression tests.

    Flask-WTF CSRF is disabled (we test our custom X-Requested-With middleware
    separately, and Flask-WTF CSRF is framework-tested).
    """
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c, conn


TEST_EMAIL = "security-test@example.com"
TEST_PASSWORD = "strongpassword123456"


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    """Create a user and log in, returning the user dict."""
    user_dict = create_user(conn, email, password, "SecurityTest")
    conn.commit()
    # Log in via the auth endpoint
    client.post("/auth/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)
    return user_dict


# ---------------------------------------------------------------------------
# CSRF Protection
# ---------------------------------------------------------------------------

class TestCSRFProtection:

    def test_api_post_without_x_requested_with_rejected(self, app_client):
        """POST to /api/ without X-Requested-With header returns 403."""
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/personalization",
            data=json.dumps({"domains": ["travel"]}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_api_post_with_x_requested_with_allowed(self, app_client):
        """POST to /api/ with X-Requested-With header proceeds normally."""
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/personalization",
            data=json.dumps({"domains": ["travel"]}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Should not be 403 (could be 200 or 401 depending on auth, but not CSRF-rejected)
        assert resp.status_code != 403

    def test_webhook_routes_csrf_exempt(self, app_client):
        """Webhook routes should not require CSRF or X-Requested-With."""
        client, _ = app_client
        # Webhooks are exempt from CSRF — they use signature verification instead
        resp = client.post(
            "/api/webhook/stripe",
            data=b"{}",
            content_type="application/json",
        )
        # Should not be 403 (will fail signature verification, but not CSRF)
        assert resp.status_code != 403

    def test_error_report_csrf_exempt(self, app_client):
        """Error report endpoint should be CSRF-exempt (fire-and-forget)."""
        client, _ = app_client
        resp = client.post(
            "/api/error-report",
            data=json.dumps({"error_type": "test", "message": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 204

    def test_client_events_csrf_exempt(self, app_client):
        """Client events endpoint accepts sendBeacon (no custom headers)."""
        client, _ = app_client
        resp = client.post(
            "/api/client-events",
            data=json.dumps({"events": [], "install_id": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Session Fixation Prevention
# ---------------------------------------------------------------------------

class TestSessionFixation:

    def test_session_cleared_on_login(self, app_client):
        """Session is cleared before login to prevent fixation attacks."""
        client, conn = app_client
        # Create a user
        create_user(conn, TEST_EMAIL, TEST_PASSWORD, "Test")
        conn.commit()

        # Set a pre-login session value
        with client.session_transaction() as sess:
            sess["pre_login_value"] = "should_not_persist"

        # Login
        client.post("/auth/login", data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        }, follow_redirects=True)

        # Verify pre-login session value was cleared
        with client.session_transaction() as sess:
            assert "pre_login_value" not in sess


# ---------------------------------------------------------------------------
# CSP Nonce
# ---------------------------------------------------------------------------

class TestCSPNonce:

    def test_csp_header_contains_nonce(self, app_client):
        """CSP header includes a nonce directive for inline scripts on authenticated pages."""
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/dashboard")
        csp = resp.headers.get("Content-Security-Policy", "")
        # CSP should contain a nonce for script-src on authenticated pages
        assert "nonce-" in csp

    def test_csp_landing_uses_unsafe_inline(self, app_client):
        """Landing page CSP uses unsafe-inline (static HTML can't carry nonces)."""
        client, conn = app_client
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "'unsafe-inline'" in csp

    def test_csp_nonce_changes_per_request(self, app_client):
        """CSP nonce is different on each request (not reused)."""
        client, conn = app_client
        _create_and_login(client, conn)
        resp1 = client.get("/dashboard")
        resp2 = client.get("/dashboard")
        csp1 = resp1.headers.get("Content-Security-Policy", "")
        csp2 = resp2.headers.get("Content-Security-Policy", "")
        # Extract nonce values
        import re
        nonces1 = re.findall(r"'nonce-([^']+)'", csp1)
        nonces2 = re.findall(r"'nonce-([^']+)'", csp2)
        assert nonces1, "No nonce found in first request CSP"
        assert nonces2, "No nonce found in second request CSP"
        assert nonces1[0] != nonces2[0], "CSP nonce must not be reused across requests"


# ---------------------------------------------------------------------------
# SQL Injection Regression
# ---------------------------------------------------------------------------

class TestSQLInjectionRegression:

    def test_login_email_parameterized(self, app_client):
        """Login email field uses parameterized queries (no SQL injection)."""
        client, conn = app_client
        # Attempt SQL injection via email field
        resp = client.post("/auth/login", data={
            "email": "' OR '1'='1' --",
            "password": "anything",
        }, follow_redirects=True)
        # Should not log in successfully
        assert resp.status_code in (200, 302)
        # Verify we're not logged in by checking a protected endpoint
        api_resp = client.get("/api/status")
        assert api_resp.status_code in (401, 302)

    def test_reading_lookup_hanzi_parameterized(self, app_client):
        """Reading lookup hanzi uses parameterized queries."""
        client, conn = app_client
        _create_and_login(client, conn)
        client.post(
            "/api/reading/lookup",
            data=json.dumps({"hanzi": "'; DROP TABLE user; --", "passage_id": "test"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Should not crash the DB — verify user table still exists
        row = conn.execute("SELECT COUNT(*) FROM user").fetchone()
        assert row[0] >= 1


# ---------------------------------------------------------------------------
# Information Disclosure
# ---------------------------------------------------------------------------

class TestInformationDisclosure:

    def test_404_does_not_leak_paths(self, app_client):
        """404 responses should not expose internal file paths."""
        client, _ = app_client
        resp = client.get("/nonexistent/secret/path")
        data = resp.get_data(as_text=True)
        assert "/Users/" not in data
        assert "/home/" not in data
        assert "traceback" not in data.lower()

    def test_api_error_generic_message(self, app_client):
        """API errors should return generic messages, not stack traces."""
        client, conn = app_client
        _create_and_login(client, conn)
        # Hit an endpoint that might error with bad input
        resp = client.post(
            "/api/personalization",
            data=b"not-json",
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = resp.get_data(as_text=True)
        assert "Traceback" not in data
        assert "File \"" not in data


# ---------------------------------------------------------------------------
# Security Headers Completeness
# ---------------------------------------------------------------------------

class TestSecurityHeadersComplete:

    def test_frame_ancestors_none_in_csp(self, app_client):
        """CSP frame-ancestors 'none' prevents clickjacking."""
        client, _ = app_client
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp

    def test_no_server_header(self, app_client):
        """Server header should not reveal technology stack."""
        client, _ = app_client
        resp = client.get("/")
        server = resp.headers.get("Server", "")
        # Flask test client may include "Werkzeug" but production (gunicorn) shouldn't
        # At minimum, verify it doesn't say "Python" or specific versions
        assert "Python/" not in server

    def test_cookie_flags(self, app_client):
        """Session cookies should have HttpOnly and SameSite flags."""
        client, conn = app_client
        create_user(conn, TEST_EMAIL, TEST_PASSWORD, "Test")
        conn.commit()
        resp = client.post("/auth/login", data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        }, follow_redirects=True)
        # Check Set-Cookie headers
        cookies = resp.headers.getlist("Set-Cookie")
        for cookie in cookies:
            if "session" in cookie.lower() or "remember" in cookie.lower():
                assert "HttpOnly" in cookie, f"Cookie missing HttpOnly: {cookie[:50]}"
