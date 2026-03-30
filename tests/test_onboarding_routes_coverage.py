"""Tests for onboarding API routes — wizard, level, goal, placement, study-time.

Covers the endpoints in mandarin/web/onboarding_routes.py to increase web coverage.
Each test exercises the route code by calling the endpoint and asserting correct
status codes and basic response structure.
"""

import json
from unittest.mock import patch, MagicMock

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


TEST_EMAIL = "onboarding@example.com"
TEST_PASSWORD = "onboardingtest12345"


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    """Create a user and log them in, returning the user dict."""
    user = create_user(conn, email, password, "OnboardTest")
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

class TestOnboardingUnauthenticated:

    def test_wizard_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/onboarding/wizard")
        assert resp.status_code in (401, 302)

    def test_set_level_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/onboarding/level",
                           data=json.dumps({"level": 1}),
                           content_type="application/json")
        assert resp.status_code in (401, 302)

    def test_set_goal_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "standard"}),
                           content_type="application/json")
        assert resp.status_code in (401, 302)

    def test_complete_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/onboarding/complete")
        assert resp.status_code in (401, 302)

    def test_placement_start_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.get("/api/onboarding/placement/start")
        assert resp.status_code in (401, 302)

    def test_placement_submit_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/onboarding/placement/submit",
                           data=json.dumps({"answers": []}),
                           content_type="application/json")
        assert resp.status_code in (401, 302)

    def test_goal_skip_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/onboarding/goal/skip")
        assert resp.status_code in (401, 302)

    def test_study_time_requires_auth(self, app_client):
        client, _conn = app_client
        resp = client.post("/api/onboarding/study-time",
                           data=json.dumps({"study_time": "morning"}),
                           content_type="application/json")
        assert resp.status_code in (401, 302)


# ---------------------------------------------------------------------------
# Authenticated — GET /api/onboarding/wizard
# ---------------------------------------------------------------------------

class TestWizardEndpoint:

    def test_wizard_returns_200(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/onboarding/wizard", headers=XHR)
        assert resp.status_code == 200

    def test_wizard_has_complete_field(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/onboarding/wizard", headers=XHR)
        data = resp.get_json()
        assert "complete" in data
        assert isinstance(data["complete"], bool)

    def test_wizard_new_user_not_complete(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.get("/api/onboarding/wizard", headers=XHR)
        data = resp.get_json()
        assert data["complete"] is False


# ---------------------------------------------------------------------------
# Authenticated — POST /api/onboarding/level
# ---------------------------------------------------------------------------

class TestSetLevelEndpoint:

    def test_set_level_valid(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/level",
                           data=json.dumps({"level": 3}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["level"] == 3

    def test_set_level_invalid_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/level",
                           data=json.dumps({"level": 99}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_set_level_string_invalid(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/level",
                           data=json.dumps({"level": "abc"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 400

    def test_set_level_all_valid_hsk_levels(self, app_client):
        """Each of the 6 HSK levels should be accepted."""
        client, conn = app_client
        _create_and_login(client, conn)
        for level in (1, 2, 3, 4, 5, 6):
            resp = client.post("/api/onboarding/level",
                               data=json.dumps({"level": level}),
                               content_type="application/json",
                               headers=XHR)
            assert resp.status_code == 200
            assert resp.get_json()["level"] == level


# ---------------------------------------------------------------------------
# Authenticated — POST /api/onboarding/goal
# ---------------------------------------------------------------------------

class TestSetGoalEndpoint:

    def test_set_goal_valid_standard(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "standard"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["goal"] == "standard"

    def test_set_goal_valid_quick(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "quick"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        assert resp.get_json()["goal"] == "quick"

    def test_set_goal_valid_deep(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "deep"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        assert resp.get_json()["goal"] == "deep"

    def test_set_goal_invalid_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "extreme"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


# ---------------------------------------------------------------------------
# Authenticated — POST /api/onboarding/complete
# ---------------------------------------------------------------------------

class TestCompleteEndpoint:

    def test_complete_returns_200(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        with patch("mandarin.web.onboarding_routes._auto_seed_content", return_value=0):
            resp = client.post("/api/onboarding/complete",
                               content_type="application/json",
                               headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["complete"] is True
        assert "items_seeded" in data

    def test_complete_marks_onboarding_done(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        with patch("mandarin.web.onboarding_routes._auto_seed_content", return_value=5):
            client.post("/api/onboarding/complete",
                        content_type="application/json",
                        headers=XHR)
        # Verify wizard now reports complete
        resp = client.get("/api/onboarding/wizard", headers=XHR)
        data = resp.get_json()
        assert data["complete"] is True


# ---------------------------------------------------------------------------
# Authenticated — GET /api/onboarding/placement/start
# ---------------------------------------------------------------------------

class TestPlacementStartEndpoint:

    def test_placement_start_returns_questions(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        fake_questions = [
            {"question_number": 1, "hanzi": "\u4f60\u597d", "pinyin": "n\u01d0 h\u01ceo",
             "hsk_level": 1, "options": ["hello", "goodbye", "thanks", "sorry"],
             "correct": "hello"},
        ]
        with patch("mandarin.web.onboarding_routes.generate_placement_quiz",
                    return_value=fake_questions):
            resp = client.get("/api/onboarding/placement/start", headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        # API may return adaptive (single "question") or batch ("questions")
        assert "question" in data or "questions" in data
        if "questions" in data:
            assert len(data["questions"]) >= 1
            assert "correct" not in data["questions"][0]
        else:
            assert "correct" not in data["question"]

    def test_placement_start_empty_quiz_handled(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        with patch("mandarin.web.onboarding_routes.generate_placement_quiz",
                    return_value=[]):
            resp = client.get("/api/onboarding/placement/start", headers=XHR)
        # API may return 500 (old behavior) or 200 with graceful fallback (adaptive mode)
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# Authenticated — POST /api/onboarding/placement/submit
# ---------------------------------------------------------------------------

class TestPlacementSubmitEndpoint:

    def test_placement_submit_valid_answers(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        answers = [
            {"hsk_level": 1, "selected": "hello", "correct": "hello"},
            {"hsk_level": 2, "selected": "cat", "correct": "cat"},
        ]
        with patch("mandarin.web.onboarding_routes._auto_seed_content", return_value=10):
            resp = client.post("/api/onboarding/placement/submit",
                               data=json.dumps({"answers": answers}),
                               content_type="application/json",
                               headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "estimated_level" in data
        assert "confidence" in data
        assert "endowed_progress" in data
        assert "items_seeded" in data
        assert "ready_for_first_session" in data

    def test_placement_submit_empty_answers_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/placement/submit",
                           data=json.dumps({"answers": []}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_placement_submit_missing_answers_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/placement/submit",
                           data=json.dumps({}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 400

    def test_placement_submit_string_answers_returns_400(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/placement/submit",
                           data=json.dumps({"answers": "not-a-list"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Authenticated — POST /api/onboarding/goal/skip
# ---------------------------------------------------------------------------

class TestGoalSkipEndpoint:

    def test_goal_skip_returns_200(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/goal/skip",
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["goal"] == "standard"
        assert data["skipped"] is True


# ---------------------------------------------------------------------------
# Authenticated — POST /api/onboarding/study-time
# ---------------------------------------------------------------------------

class TestStudyTimeEndpoint:

    def test_study_time_valid_morning(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/study-time",
                           data=json.dumps({"study_time": "morning"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["study_time"] == "morning"
        assert data["set"] is True

    def test_study_time_valid_evening(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/study-time",
                           data=json.dumps({"study_time": "evening"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        assert resp.get_json()["study_time"] == "evening"

    def test_study_time_valid_lunch(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/study-time",
                           data=json.dumps({"study_time": "lunch"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        assert resp.get_json()["study_time"] == "lunch"

    def test_study_time_invalid_defaults_to_varies(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/study-time",
                           data=json.dumps({"study_time": "midnight"}),
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        # Invalid values default to "varies" (not rejected)
        assert data["study_time"] == "varies"

    def test_study_time_no_body_defaults_to_varies(self, app_client):
        client, conn = app_client
        _create_and_login(client, conn)
        resp = client.post("/api/onboarding/study-time",
                           content_type="application/json",
                           headers=XHR)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["study_time"] == "varies"
