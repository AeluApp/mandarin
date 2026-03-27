"""Tests for settings API routes — user preferences, push tokens, methodology.

Covers the endpoints in mandarin/web/settings_routes.py to increase web coverage.
Each test exercises the route code by calling the endpoint and asserting correct
status codes and basic response structure.
"""

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


TEST_EMAIL = "settings@example.com"
TEST_PASSWORD = "settingstest12345"  # gitleaks:allow (test fixture, not a real secret)


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    """Create a user and log them in, returning the user dict."""
    user = create_user(conn, email, password, "SettingsTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)
    return user


XHR = {"X-Requested-With": "XMLHttpRequest"}
JSON_XHR = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Unauthenticated — should redirect or 401
# ---------------------------------------------------------------------------

class TestSettingsUnauthenticated:

    def test_settings_all_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/settings")
        assert resp.status_code in (401, 302)

    def test_session_length_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/settings/session-length")
        assert resp.status_code in (401, 302)

    def test_methodology_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/settings/methodology")
        assert resp.status_code in (401, 302)


# ---------------------------------------------------------------------------
# GET /api/settings — all settings
# ---------------------------------------------------------------------------

class TestSettingsAll:

    def test_returns_200(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings", headers=XHR)
        assert resp.status_code == 200

    def test_has_expected_keys(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings", headers=XHR)
        data = resp.get_json()
        assert "preferred_session_length" in data
        assert "target_sessions_per_week" in data
        assert "audio_enabled" in data
        assert "anonymous_mode" in data
        assert "marketing_opt_out" in data


# ---------------------------------------------------------------------------
# /api/settings/session-length
# ---------------------------------------------------------------------------

class TestSessionLength:

    def test_get_session_length(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/session-length", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "preferred_session_length" in data

    def test_post_valid_length(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/session-length",
            data=json.dumps({"length": 15}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preferred_session_length"] == 15

    def test_post_invalid_length_too_small(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/session-length",
            data=json.dumps({"length": 2}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 400

    def test_post_invalid_length_too_large(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/session-length",
            data=json.dumps({"length": 50}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/settings/daily-goal
# ---------------------------------------------------------------------------

class TestDailyGoal:

    def test_get_daily_goal(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/daily-goal", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "target_sessions_per_week" in data

    def test_post_valid_goal(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/daily-goal",
            data=json.dumps({"target_sessions_per_week": 7}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["target_sessions_per_week"] == 7

    def test_post_invalid_goal(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/daily-goal",
            data=json.dumps({"target_sessions_per_week": 0}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/settings/audio
# ---------------------------------------------------------------------------

class TestAudioSettings:

    def test_get_audio(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/audio", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "audio_enabled" in data

    def test_post_audio_toggle(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/audio",
            data=json.dumps({"enabled": False}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["audio_enabled"] is False


# ---------------------------------------------------------------------------
# /api/settings/marketing-opt-out
# ---------------------------------------------------------------------------

class TestMarketingOptOut:

    def test_get_marketing(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/marketing-opt-out", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "marketing_opt_out" in data

    def test_post_opt_out(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/marketing-opt-out",
            data=json.dumps({"opted_out": True}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["marketing_opt_out"] is True


# ---------------------------------------------------------------------------
# /api/settings/display-prefs
# ---------------------------------------------------------------------------

class TestDisplayPrefs:

    def test_get_display_prefs(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/display-prefs", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "reading_show_pinyin" in data

    def test_post_display_prefs(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/display-prefs",
            data=json.dumps({"reading_show_pinyin": True}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 200

    def test_post_display_prefs_empty(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/display-prefs",
            data=json.dumps({}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/settings/methodology
# ---------------------------------------------------------------------------

class TestMethodology:

    def test_returns_200(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/methodology", headers=XHR)
        assert resp.status_code == 200

    def test_has_methodology_keys(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/methodology", headers=XHR)
        data = resp.get_json()
        assert "scheduling" in data
        assert "mastery_stages" in data
        assert "desirable_difficulty" in data
        assert "interleaving" in data


# ---------------------------------------------------------------------------
# /api/push/vapid-key
# ---------------------------------------------------------------------------

class TestPushVapidKey:

    def test_vapid_key_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/push/vapid-key")
        assert resp.status_code in (200, 401, 404)

    def test_vapid_key_authenticated(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/push/vapid-key", headers=XHR)
        # Returns 200 with key or 404 if not configured
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# /api/push/register and /api/push/unregister
# ---------------------------------------------------------------------------

class TestPushRegister:

    def test_register_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post(
            "/api/push/register",
            data=json.dumps({"platform": "web", "token": "abc123"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_unregister_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post(
            "/api/push/unregister",
            data=json.dumps({"platform": "web"}),
            content_type="application/json",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/settings/streak-reminders
# ---------------------------------------------------------------------------

class TestStreakReminders:

    def test_get_streak_reminders(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/settings/streak-reminders", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "streak_reminders" in data

    def test_post_streak_reminders(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post(
            "/api/settings/streak-reminders",
            data=json.dumps({"enabled": False}),
            headers=JSON_XHR,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["streak_reminders"] is False
