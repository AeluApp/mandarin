"""Tests for security response headers."""

import sqlite3
from unittest.mock import patch

import pytest

from mandarin.web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeConn:
    """Context manager that returns the test conn unchanged."""
    def __init__(self, conn):
        self._conn = conn
    def __enter__(self):
        return self._conn
    def __exit__(self, *args):
        return False


@pytest.fixture
def client(test_db):
    """Create a Flask test client wired to the test database."""
    conn, _ = test_db

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        resp = client.get("/nonexistent-page-12345")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/nonexistent-page-12345")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_referrer_policy(self, client):
        resp = client.get("/nonexistent-page-12345")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_csp_present(self, client):
        resp = client.get("/nonexistent-page-12345")
        csp = resp.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_xss_protection(self, client):
        resp = client.get("/nonexistent-page-12345")
        assert resp.headers.get("X-XSS-Protection") == "0"

    def test_no_hsts_in_non_production(self, client):
        resp = client.get("/nonexistent-page-12345")
        # In testing mode IS_PRODUCTION is False
        assert resp.headers.get("Strict-Transport-Security") is None
