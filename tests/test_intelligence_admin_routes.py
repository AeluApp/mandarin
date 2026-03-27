"""Tests for intelligence admin routes (mandarin.web.intelligence_admin_routes).

Covers:
- Unauthenticated users get 302/401
- Non-admin users get 403
- Admin users can access action endpoints (nonexistent finding returns error)
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web.auth_routes import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    """Return a context manager class whose __enter__ yields *conn*."""

    class _FakeConnection:
        def __enter__(self):
            return conn

        def __exit__(self, *args):
            return False

    return _FakeConnection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(test_db):
    """Flask test client with DB patched (unauthenticated)."""
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.intelligence_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as an admin user."""
    conn, _ = test_db

    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.intelligence_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


@pytest.fixture
def nonadmin_client(test_db):
    """Flask test client logged in as a non-admin user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1, is_admin = 0 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.intelligence_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Access control — unauthenticated
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:

    def test_dashboard_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.get("/admin/intelligence", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_approve_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.post("/admin/intelligence/1/approve", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_reject_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.post("/admin/intelligence/1/reject", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_defer_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.post("/admin/intelligence/1/defer", follow_redirects=False)
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Access control — non-admin
# ---------------------------------------------------------------------------

class TestNonAdminAccess:

    def test_dashboard_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/admin/intelligence", follow_redirects=False)
        assert resp.status_code == 403

    def test_approve_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.post(
            "/admin/intelligence/1/approve",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin access — action endpoints with nonexistent finding
# The api_error_handler decorator wraps these routes and converts abort(404)
# into a 500 error response. We verify the endpoint returns an error status.
# ---------------------------------------------------------------------------

class TestAdminActions:

    def test_approve_nonexistent_finding_returns_error(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/admin/intelligence/99999/approve",
            json={"notes": "test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # api_error_handler catches abort(404) and returns 500
        assert resp.status_code in (404, 500)
        data = json.loads(resp.data)
        assert "error" in data

    def test_reject_nonexistent_finding_returns_error(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/admin/intelligence/99999/reject",
            json={"notes": "test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (404, 500)
        data = json.loads(resp.data)
        assert "error" in data

    def test_defer_nonexistent_finding_returns_error(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/admin/intelligence/99999/defer",
            json={"notes": "test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (404, 500)
        data = json.loads(resp.data)
        assert "error" in data
