"""Tests for learner intelligence routes (mandarin.web.intelligence_routes).

Covers:
- Unauthenticated users get 302/401
- Authenticated users get 200 + correct JSON shape
"""

import json
from unittest.mock import patch

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
         patch("mandarin.web.intelligence_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def auth_client(test_db):
    """Flask test client logged in as a regular user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.intelligence_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Access control — unauthenticated
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:

    def test_learner_intelligence_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.get("/api/learner-intelligence", follow_redirects=False)
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Authenticated access
# ---------------------------------------------------------------------------

class TestLearnerIntelligence:

    def test_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/learner-intelligence")
        assert resp.status_code == 200

    def test_returns_json(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/learner-intelligence")
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_has_expected_keys(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/learner-intelligence")
        data = json.loads(resp.data)
        for key in (
            "optimal_zone_count",
            "total_items_learning",
            "velocity",
            "top_errors",
            "forecast",
            "difficulty_note",
        ):
            assert key in data, f"Missing key: {key}"

    def test_velocity_is_number(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/learner-intelligence")
        data = json.loads(resp.data)
        assert isinstance(data["velocity"], (int, float))

    def test_top_errors_is_list(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/learner-intelligence")
        data = json.loads(resp.data)
        assert isinstance(data["top_errors"], list)
