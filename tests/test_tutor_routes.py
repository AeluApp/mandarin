"""Tests for tutor routes (mandarin.web.tutor_routes).

Covers:
- Unauthenticated requests get redirected (302) or 401
- Authenticated user can list tutor sessions (empty at start)
- Authenticated user can view tutor stats
- Session creation requires a body with session_date
- Corrections/flags require a valid session belonging to the user
"""

import json
from unittest.mock import patch

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
         patch("mandarin.web.tutor_routes.db.connection", FakeConn):
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
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.tutor_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:

    def test_list_sessions_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/tutor/sessions")
        assert resp.status_code in (302, 401)

    def test_create_session_unauthenticated(self, client):
        c, _ = client
        resp = c.post(
            "/api/tutor/sessions",
            json={"session_date": "2026-01-01"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (302, 401)

    def test_stats_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/tutor/stats")
        assert resp.status_code in (302, 401)

    def test_corrections_unauthenticated(self, client):
        c, _ = client
        resp = c.post(
            "/api/tutor/sessions/1/corrections",
            json={"corrections": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# List sessions
# ---------------------------------------------------------------------------

class TestListSessions:

    def test_list_sessions_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/tutor/sessions")
        assert resp.status_code == 200

    def test_list_sessions_empty_initially(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/tutor/sessions")
        data = json.loads(resp.data)
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        assert len(data["sessions"]) == 0


# ---------------------------------------------------------------------------
# Create session
# ---------------------------------------------------------------------------

class TestCreateSession:

    def test_create_session_returns_201(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/tutor/sessions",
            json={
                "session_date": "2026-03-01",
                "tutor_name": "Li Laoshi",
                "duration_minutes": 30,
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert "id" in data
        assert data["status"] == "created"

    def test_create_session_appears_in_list(self, auth_client):
        c, _ = auth_client
        c.post(
            "/api/tutor/sessions",
            json={"session_date": "2026-03-15", "tutor_name": "Wang Laoshi"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = c.get("/api/tutor/sessions")
        data = json.loads(resp.data)
        assert len(data["sessions"]) >= 1


# ---------------------------------------------------------------------------
# Tutor stats
# ---------------------------------------------------------------------------

class TestTutorStats:

    def test_stats_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/tutor/stats")
        assert resp.status_code == 200

    def test_stats_response_shape(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/tutor/stats")
        data = json.loads(resp.data)
        for key in ("total_sessions", "total_corrections", "total_flags"):
            assert key in data, f"Missing key: {key}"

    def test_stats_zero_initially(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/tutor/stats")
        data = json.loads(resp.data)
        assert data["total_sessions"] == 0


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

class TestCorrections:

    def _create_session(self, client, conn):
        """Create a tutor session and return its id."""
        resp = client.post(
            "/api/tutor/sessions",
            json={"session_date": "2026-03-20", "tutor_name": "Test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        return json.loads(resp.data)["id"]

    def test_add_corrections_to_valid_session(self, auth_client):
        c, conn = auth_client
        sid = self._create_session(c, conn)
        resp = c.post(
            f"/api/tutor/sessions/{sid}/corrections",
            json={
                "corrections": [
                    {"wrong_form": "我去了学校", "correct_form": "我去了学校了"},
                ]
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["added"] == 1

    def test_corrections_nonexistent_session_returns_404(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/tutor/sessions/99999/corrections",
            json={"corrections": [{"wrong_form": "x", "correct_form": "y"}]},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Vocabulary flags
# ---------------------------------------------------------------------------

class TestVocabularyFlags:

    def _create_session(self, client):
        resp = client.post(
            "/api/tutor/sessions",
            json={"session_date": "2026-03-20", "tutor_name": "Test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        return json.loads(resp.data)["id"]

    def test_add_flags_to_valid_session(self, auth_client):
        c, _ = auth_client
        sid = self._create_session(c)
        resp = c.post(
            f"/api/tutor/sessions/{sid}/flags",
            json={
                "flags": [
                    {"hanzi": "苹果", "pinyin": "píngguǒ", "meaning": "apple"},
                ]
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["added"] == 1

    def test_flags_nonexistent_session_returns_404(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/tutor/sessions/99999/flags",
            json={"flags": [{"hanzi": "苹果"}]},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404
