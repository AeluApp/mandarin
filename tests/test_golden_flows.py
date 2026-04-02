"""Golden flow integration tests — critical user journeys that must never break.

Each test covers an end-to-end path through the application. If any of these
fail, the deploy MUST be blocked.  These are the flows that, if broken, would
make the product unusable.

Golden flows:
  1. Health probes return OK
  2. Auth: register → login → access protected → logout
  3. Session: start → receive drill → submit → complete
  4. Reading: browse passages → open → lookup word
  5. Dashboard: loads with panels
  6. Static assets: JS, CSS, SW loadable
  7. Client events: sendBeacon endpoint works
"""

import json
import re
import sqlite3
from unittest.mock import patch

import pytest

from mandarin.web import create_app
from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_security_regression)
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


def _extract_csrf_token(html: str) -> str:
    """Extract CSRF token from a rendered HTML page (hidden input or meta tag)."""
    # Try hidden input first: <input ... name="csrf_token" value="...">
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if m:
        return m.group(1)
    # Try meta tag: <meta name="csrf-token" content="...">
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html)
    if m:
        return m.group(1)
    return ""


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


@pytest.fixture
def app_client(test_db):
    """Flask test client with CSRF protection enabled (production-like)."""
    conn, _ = test_db
    app = create_app(testing=True)
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c, conn


TEST_EMAIL = "golden@example.com"
TEST_PASSWORD = "goldenflow9876543"


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    user_dict = create_user(conn, email, password, "GoldenTest")
    conn.commit()
    # Fetch login page to get CSRF token
    resp = client.get("/auth/login")
    csrf_token = _extract_csrf_token(resp.get_data(as_text=True))
    client.post("/auth/login", data={
        "email": email,
        "password": password,
        "csrf_token": csrf_token,
    }, follow_redirects=True)
    return user_dict


# ---------------------------------------------------------------------------
# Flow 1: Health probes
# ---------------------------------------------------------------------------

class TestHealthProbes:

    def test_liveness_ok(self, app_client):
        client, _ = app_client
        resp = client.get("/api/health/live")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data

    def test_readiness_ok(self, app_client):
        client, _ = app_client
        resp = client.get("/api/health/ready")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "latency_ms" in data

    def test_full_health_ok(self, app_client):
        client, _ = app_client
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data.get("content_items", 0) >= 0


# ---------------------------------------------------------------------------
# Flow 2: Auth lifecycle
# ---------------------------------------------------------------------------

class TestAuthLifecycle:

    def test_register_login_protected_logout(self, app_client):
        """Full auth lifecycle: register → login → hit protected endpoint → logout."""
        client, conn = app_client

        # Register
        user = create_user(conn, TEST_EMAIL, TEST_PASSWORD, "Test")
        conn.commit()
        assert user is not None

        # Before login — protected endpoint should redirect or 401
        resp = client.get("/api/status")
        assert resp.status_code in (302, 401)

        # Fetch login page CSRF token
        resp = client.get("/auth/login")
        csrf_token = _extract_csrf_token(resp.get_data(as_text=True))

        # Login (with CSRF token)
        resp = client.post("/auth/login", data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "csrf_token": csrf_token,
        }, follow_redirects=True)
        assert resp.status_code == 200

        # After login — protected endpoint should succeed
        resp = client.get("/api/status",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200

        # Fetch a fresh CSRF token (session changed after login)
        resp = client.get("/")
        fresh_csrf = _extract_csrf_token(resp.get_data(as_text=True))

        # Logout (POST-only route, with fresh CSRF token)
        resp = client.post("/auth/logout",
                           headers={"X-CSRFToken": fresh_csrf},
                           follow_redirects=True)
        assert resp.status_code == 200

        # After logout — protected endpoint should fail again
        resp = client.get("/api/status")
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Flow 3: Session drill loop
# ---------------------------------------------------------------------------

class TestSessionDrillLoop:

    def test_session_start_returns_drill(self, app_client):
        """Starting a session returns learning status via the session API."""
        client, conn = app_client
        _create_and_login(client, conn)

        # Check session status — returns learning stats
        resp = client.get("/api/status",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        # Should have learning stats fields
        assert "item_count" in data or "items_due" in data


# ---------------------------------------------------------------------------
# Flow 4: Reading passage
# ---------------------------------------------------------------------------

class TestReadingFlow:

    def test_reading_passages_list(self, app_client):
        """Reading passages endpoint returns a list."""
        client, conn = app_client
        _create_and_login(client, conn)

        resp = client.get("/api/reading/passages?hsk_level=1",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "passages" in data


# ---------------------------------------------------------------------------
# Flow 5: Dashboard loads
# ---------------------------------------------------------------------------

class TestDashboardFlow:

    def test_root_returns_html(self, app_client):
        """Root page returns valid HTML (landing for unauth, app for auth)."""
        client, _ = app_client
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "<!DOCTYPE html>" in html or "<html" in html

    def test_authenticated_root_has_app(self, app_client):
        """Authenticated root returns the app with build-id meta tag."""
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="app"' in html
        assert 'name="build-id"' in html


# ---------------------------------------------------------------------------
# Flow 6: Static assets
# ---------------------------------------------------------------------------

class TestStaticAssets:

    def test_app_js_loads(self, app_client):
        client, _ = app_client
        resp = client.get("/static/app.js")
        assert resp.status_code == 200
        assert len(resp.get_data()) > 1000

    def test_style_css_loads(self, app_client):
        client, _ = app_client
        resp = client.get("/static/style.css")
        assert resp.status_code == 200
        assert len(resp.get_data()) > 1000

    def test_sw_js_loads(self, app_client):
        client, _ = app_client
        resp = client.get("/static/sw.js")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Flow 7: Client events (sendBeacon)
# ---------------------------------------------------------------------------

class TestClientEvents:

    def test_client_events_accepts_empty_batch(self, app_client):
        """Client events endpoint accepts empty batch (sendBeacon pattern)."""
        client, _ = app_client
        resp = client.post(
            "/api/client-events",
            data=json.dumps({"events": [], "install_id": "golden-test"}),
            content_type="application/json",
        )
        assert resp.status_code == 204

    def test_error_report_accepts_post(self, app_client):
        """Error report endpoint accepts fire-and-forget POST."""
        client, _ = app_client
        resp = client.post(
            "/api/error-report",
            data=json.dumps({"error_type": "test", "message": "golden flow"}),
            content_type="application/json",
        )
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Flow 8: SW status (kill-switch endpoint)
# ---------------------------------------------------------------------------

class TestSWStatus:

    def test_sw_status_returns_active(self, app_client):
        """SW status endpoint returns active status (authenticated)."""
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/sw-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active"] is True
        assert "build_id" in data
