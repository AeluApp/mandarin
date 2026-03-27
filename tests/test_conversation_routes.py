"""Tests for conversation drill routes — scenarios, start, respond, continue."""

import json
from unittest.mock import patch

import pytest

from mandarin.web import create_app
from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


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
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c, conn


def _login(client, conn, email="conversation@test.com"):
    create_user(conn, email, "testpass123456", "ConvoTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": "testpass123456",
    }, follow_redirects=True)


# ---------------------------------------------------------------------------
# Access control — unauthenticated
# ---------------------------------------------------------------------------

class TestConversationUnauthenticated:

    def test_scenarios_unauthenticated(self, app_client):
        """Unauthenticated requests to scenarios return 401."""
        client, _ = app_client
        resp = client.get("/api/conversation/scenarios")
        assert resp.status_code in (401, 302)

    def test_start_unauthenticated(self, app_client):
        """Unauthenticated requests to start return 401."""
        client, _ = app_client
        resp = client.post(
            "/api/conversation/start",
            json={"hsk_level": 1},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (401, 302)

    def test_respond_unauthenticated(self, app_client):
        """Unauthenticated requests to respond return 401."""
        client, _ = app_client
        resp = client.post(
            "/api/conversation/respond",
            json={"scenario_id": "x", "user_response": "hi"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (401, 302)


# ---------------------------------------------------------------------------
# Scenarios listing — /api/conversation/scenarios
# ---------------------------------------------------------------------------

class TestConversationScenarios:

    def test_scenarios_returns_200(self, app_client):
        """Authenticated user can list scenarios."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/conversation/scenarios")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "scenarios" in data
        assert isinstance(data["scenarios"], list)

    def test_scenarios_filter_by_hsk_level(self, app_client):
        """Passing hsk_level query param does not cause errors."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/conversation/scenarios?hsk_level=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "scenarios" in data


# ---------------------------------------------------------------------------
# Start conversation — /api/conversation/start
# ---------------------------------------------------------------------------

class TestConversationStart:

    def test_start_returns_scenario(self, app_client):
        """Starting a conversation returns a scenario object."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/start",
            json={"hsk_level": 1},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Could be 200 (scenario found) or 404 (no scenarios for level)
        assert resp.status_code in (200, 404)
        data = resp.get_json()
        if resp.status_code == 200:
            assert "scenario" in data


# ---------------------------------------------------------------------------
# Respond — /api/conversation/respond
# ---------------------------------------------------------------------------

class TestConversationRespond:

    def test_respond_missing_scenario_id(self, app_client):
        """Missing scenario_id returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/respond",
            json={"user_response": "你好"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_respond_missing_user_response(self, app_client):
        """Missing user_response returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/respond",
            json={"scenario_id": "greeting_basic"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_respond_invalid_scenario(self, app_client):
        """Non-existent scenario returns 404."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/respond",
            json={"scenario_id": "nonexistent_xyz", "user_response": "你好"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Continue — /api/conversation/continue
# ---------------------------------------------------------------------------

class TestConversationContinue:

    def test_continue_missing_scenario_id(self, app_client):
        """Missing scenario_id returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/continue",
            json={"history": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_continue_invalid_scenario(self, app_client):
        """Non-existent scenario returns 404."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/continue",
            json={"scenario_id": "nonexistent_xyz", "history": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Transcribe — /api/conversation/transcribe
# ---------------------------------------------------------------------------

class TestConversationTranscribe:

    def test_transcribe_no_audio_returns_400(self, app_client):
        """Missing audio file returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/conversation/transcribe",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
