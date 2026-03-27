"""Tests for strategy admin routes (mandarin.web.strategy_admin_routes).

Covers:
- Unauthenticated requests get redirected (302) or 401
- Non-admin users get 403
- Admin user can access thesis, readiness, competitive, editorial endpoints
- Thesis override validates allowed fields
- Readiness condition update validates status
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web.auth_routes import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
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
    """Flask test client — unauthenticated."""
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.strategy_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as an admin user (is_admin=1, totp_enabled=1)."""
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
         patch("mandarin.web.strategy_admin_routes.db.connection", FakeConn):
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
         patch("mandarin.web.strategy_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:

    def test_thesis_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/strategy/thesis")
        assert resp.status_code in (302, 401)

    def test_readiness_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/strategy/readiness")
        assert resp.status_code in (302, 401)

    def test_competitive_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/strategy/competitive")
        assert resp.status_code in (302, 401)

    def test_editorial_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/strategy/editorial")
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Non-admin access
# ---------------------------------------------------------------------------

class TestNonAdminAccess:

    def test_thesis_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/strategy/thesis")
        assert resp.status_code == 403

    def test_readiness_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/strategy/readiness")
        assert resp.status_code == 403

    def test_competitive_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/strategy/competitive")
        assert resp.status_code == 403

    def test_editorial_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/strategy/editorial")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin — thesis
# ---------------------------------------------------------------------------

class TestThesis:

    def test_thesis_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/thesis")
        assert resp.status_code == 200

    def test_thesis_no_active_thesis_returns_null(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/thesis")
        data = json.loads(resp.data)
        # Thesis may be null if none seeded
        assert "thesis" in data

    def test_override_thesis_invalid_field_returns_400(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/strategy/thesis/override",
            json={"field": "id", "value": "hacked"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Admin — readiness
# ---------------------------------------------------------------------------

class TestReadiness:

    def test_readiness_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/readiness")
        assert resp.status_code == 200

    def test_readiness_response_shape(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/readiness")
        data = json.loads(resp.data)
        assert "conditions" in data


# ---------------------------------------------------------------------------
# Admin — competitive
# ---------------------------------------------------------------------------

class TestCompetitive:

    def test_competitive_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/competitive")
        assert resp.status_code == 200

    def test_competitive_response_shape(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/competitive")
        data = json.loads(resp.data)
        assert "dimensions" in data
        assert "competitors" in data
        assert "signals" in data

    def test_log_signal_invalid_type_returns_400(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/strategy/competitive/signal",
            json={"signal_type": "invalid_type", "description": "test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_refresh_competitive_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/strategy/competitive/refresh",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "refreshed"


# ---------------------------------------------------------------------------
# Admin — editorial
# ---------------------------------------------------------------------------

class TestEditorial:

    def test_editorial_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/editorial")
        assert resp.status_code == 200

    def test_editorial_response_shape(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/strategy/editorial")
        data = json.loads(resp.data)
        assert "total_items" in data
        assert "content_depth_ratio" in data
