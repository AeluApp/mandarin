"""Test that CSRF enforcement works correctly on API routes.

Verifies that POST/PUT/DELETE/PATCH requests to /api/ endpoints
require the X-Requested-With header (or a Bearer JWT token).
This is a deploy-gate test — CSRF bugs must never ship.
"""

import pytest
from unittest.mock import patch

from mandarin.web import create_app


class _FakeConn:
    def __init__(self, conn):
        self._conn = conn
    def __enter__(self):
        return self._conn
    def __exit__(self, *args):
        return False


@pytest.fixture
def csrf_client(test_db):
    """Flask test client with CSRF ENABLED (unlike most test fixtures)."""
    conn, _ = test_db
    app = create_app(testing=True)
    # CSRF stays enabled — this is what we're testing
    app.config["WTF_CSRF_ENABLED"] = True
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c, conn


class TestCSRFEnforcement:
    """API routes must reject POST without X-Requested-With header."""

    def test_api_post_without_header_returns_403(self, csrf_client):
        client, conn = csrf_client
        # Log in first
        from mandarin.auth import create_user
        from werkzeug.security import generate_password_hash
        with patch("mandarin.auth.generate_password_hash",
                   lambda p, **kw: generate_password_hash(p, method="pbkdf2:sha256")):
            create_user(conn, "csrf@test.com", "password123", "CSRFTest")
            conn.commit()
        client.post("/auth/login", data={
            "email": "csrf@test.com",
            "password": "password123",
        })

        # POST to an API endpoint WITHOUT X-Requested-With
        resp = client.post("/api/onboarding/goal",
                           json={"goal": "standard"})
        assert resp.status_code == 403, (
            f"Expected 403 for POST without X-Requested-With, got {resp.status_code}"
        )

    def test_api_post_with_header_succeeds(self, csrf_client):
        client, conn = csrf_client
        from mandarin.auth import create_user
        from werkzeug.security import generate_password_hash
        with patch("mandarin.auth.generate_password_hash",
                   lambda p, **kw: generate_password_hash(p, method="pbkdf2:sha256")):
            create_user(conn, "csrf2@test.com", "password123", "CSRFTest2")
            conn.commit()
        client.post("/auth/login", data={
            "email": "csrf2@test.com",
            "password": "password123",
        })

        # POST WITH the X-Requested-With header should not get 403
        resp = client.post("/api/onboarding/goal",
                           json={"goal": "standard"},
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code != 403, (
            f"Expected non-403 with X-Requested-With header, got {resp.status_code}"
        )

    def test_webhook_exempt_from_csrf(self, csrf_client):
        """Webhook endpoints should not require X-Requested-With."""
        client, _ = csrf_client
        # Webhook endpoints are exempted from CSRF
        resp = client.post("/api/webhook/stripe",
                           data=b"test",
                           content_type="application/json")
        # Should NOT be 403 (may be 400 or 401 for bad webhook, but not CSRF)
        assert resp.status_code != 403
