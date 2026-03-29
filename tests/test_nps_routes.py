"""Tests for NPS routes (mandarin.web.nps_routes).

Covers:
- POST /api/feedback/nps — submit a valid NPS score
- POST /api/feedback/nps — reject invalid scores
- GET /api/admin/quality/nps — admin NPS dashboard endpoint
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web.auth_routes import User
from tests.shared_db import make_test_db  # noqa: F401


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
def nps_client(test_db):
    """Flask test client with the NPS table available."""
    conn, _ = test_db

    # Ensure nps_response table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nps_response (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            score INTEGER NOT NULL,
            feedback TEXT DEFAULT '',
            responded_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn):
        # Inject conn as g.db for NPS routes
        @app.before_request
        def _inject_db():
            from flask import g
            g.db = conn

        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def nps_admin_client(test_db):
    """Flask test client logged in as admin with NPS table."""
    conn, _ = test_db

    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nps_response (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            score INTEGER NOT NULL,
            feedback TEXT DEFAULT '',
            responded_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn):

        @app.before_request
        def _inject_db():
            from flask import g
            g.db = conn

        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# POST /api/feedback/nps
# ---------------------------------------------------------------------------

class TestSubmitNps:

    def test_valid_score_returns_201(self, nps_client):
        c, _ = nps_client
        resp = c.post(
            "/api/feedback/nps",
            data=json.dumps({"score": 9, "feedback": "Great app!"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201

    def test_missing_score_returns_400(self, nps_client):
        c, _ = nps_client
        resp = c.post(
            "/api/feedback/nps",
            data=json.dumps({"feedback": "no score"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_out_of_range_score_returns_400(self, nps_client):
        c, _ = nps_client
        resp = c.post(
            "/api/feedback/nps",
            data=json.dumps({"score": 11}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_negative_score_returns_400(self, nps_client):
        c, _ = nps_client
        resp = c.post(
            "/api/feedback/nps",
            data=json.dumps({"score": -1}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/admin/quality/nps
# ---------------------------------------------------------------------------

class TestAdminNps:

    def test_admin_nps_returns_200(self, nps_admin_client):
        c, _ = nps_admin_client
        resp = c.get("/api/admin/quality/nps")
        assert resp.status_code == 200

    def test_admin_nps_empty_returns_null_nps(self, nps_admin_client):
        c, _ = nps_admin_client
        resp = c.get("/api/admin/quality/nps")
        data = json.loads(resp.data)
        assert "nps" in data
        assert "responses" in data
