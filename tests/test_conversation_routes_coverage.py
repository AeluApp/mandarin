"""Tests for conversation drill API routes.

Covers the endpoints in mandarin/web/conversation_routes.py to increase web coverage.
Each test exercises the route code by calling the endpoint and asserting correct
status codes and basic response structure.
"""

import io
import json
from unittest.mock import patch

import pytest

from mandarin.web import create_app
from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_dashboard_routes)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Context manager that returns the test conn unchanged."""
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
    """Flask test client wired to the test database."""
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as client:
            yield client, conn


TEST_EMAIL = "convo@example.com"
TEST_PASSWORD = "convotest12345"  # gitleaks:allow (test fixture, not a real secret)


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    """Create a user and log them in, returning the user dict."""
    user = create_user(conn, email, password, "ConvoTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)
    return user


XHR = {"X-Requested-With": "XMLHttpRequest"}


# ---------------------------------------------------------------------------
# Unauthenticated access — should return 401 or 302 redirect
# ---------------------------------------------------------------------------

class TestConversationUnauthenticated:

    def test_scenarios_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/conversation/scenarios")
        assert resp.status_code in (401, 302)

    def test_start_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/conversation/start")
        assert resp.status_code in (401, 302)

    def test_respond_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/conversation/respond")
        assert resp.status_code in (401, 302)

    def test_continue_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/conversation/continue")
        assert resp.status_code in (401, 302)

    def test_transcribe_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/conversation/transcribe")
        assert resp.status_code in (401, 302)


# ---------------------------------------------------------------------------
# Authenticated — /api/conversation/scenarios (GET)
# ---------------------------------------------------------------------------

class TestConversationScenarios:

    def test_scenarios_returns_200(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/conversation/scenarios", headers=XHR)
        assert resp.status_code == 200

    def test_scenarios_returns_list(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/conversation/scenarios", headers=XHR)
        data = resp.get_json()
        assert "scenarios" in data
        assert isinstance(data["scenarios"], list)
        assert len(data["scenarios"]) > 0

    def test_scenarios_filter_by_hsk_level(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/conversation/scenarios?hsk_level=1", headers=XHR)
        data = resp.get_json()
        assert "scenarios" in data
        for s in data["scenarios"]:
            assert s["hsk_level"] == 1


# ---------------------------------------------------------------------------
# Authenticated — /api/conversation/start (POST)
# ---------------------------------------------------------------------------

class TestConversationStart:

    def test_start_returns_scenario(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/start",
            data=json.dumps({"hsk_level": 1}),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "scenario" in data
        assert "id" in data["scenario"]
        assert "title" in data["scenario"]
        assert "prompt_zh" in data["scenario"]

    def test_start_with_invalid_scenario_id_returns_404(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/start",
            data=json.dumps({"scenario_id": "nonexistent_scenario_xyz"}),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data


# ---------------------------------------------------------------------------
# Authenticated — /api/conversation/respond (POST, validation)
# ---------------------------------------------------------------------------

class TestConversationRespond:

    def test_respond_missing_scenario_id_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/respond",
            data=json.dumps({"user_response": "你好"}),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "scenario_id is required"

    def test_respond_missing_user_response_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/respond",
            data=json.dumps({"scenario_id": "greet_1", "user_response": ""}),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "user_response is required"

    def test_respond_nonexistent_scenario_returns_404(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/respond",
            data=json.dumps({
                "scenario_id": "nonexistent_xyz",
                "user_response": "你好",
            }),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "Scenario not found"


# ---------------------------------------------------------------------------
# Authenticated — /api/conversation/continue (POST, validation)
# ---------------------------------------------------------------------------

class TestConversationContinue:

    def test_continue_missing_scenario_id_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/continue",
            data=json.dumps({"history": []}),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "scenario_id is required"

    def test_continue_nonexistent_scenario_returns_404(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/continue",
            data=json.dumps({
                "scenario_id": "nonexistent_xyz",
                "history": [{"role": "user", "text": "你好"}],
            }),
            content_type="application/json",
            headers=XHR,
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "Scenario not found"


# ---------------------------------------------------------------------------
# Authenticated — /api/conversation/transcribe (POST, validation)
# ---------------------------------------------------------------------------

class TestConversationTranscribe:

    def test_transcribe_missing_audio_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/conversation/transcribe",
            headers=XHR,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "audio file is required"

    def test_transcribe_empty_filename_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        form_data = {"audio": (io.BytesIO(b"fake audio"), "")}
        resp = client.post(
            "/api/conversation/transcribe",
            data=form_data,
            content_type="multipart/form-data",
            headers=XHR,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "empty filename"
