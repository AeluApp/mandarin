"""Tests for content routes — gap analysis, reading generation, comprehension."""

import json
from unittest.mock import patch, MagicMock

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


def _login(client, conn, email="content@test.com"):
    create_user(conn, email, "testpass123456", "ContentTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": "testpass123456",
    }, follow_redirects=True)


# ---------------------------------------------------------------------------
# Content Gaps — /api/content/gaps
# ---------------------------------------------------------------------------

class TestContentGaps:

    def test_gaps_returns_200(self, app_client):
        """Authenticated user can fetch content gap analysis."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/content/gaps")
        assert resp.status_code == 200

    def test_gaps_returns_json(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/content/gaps")
        data = resp.get_json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# User Gaps — /api/content/gaps/user
# ---------------------------------------------------------------------------

class TestContentUserGaps:

    def test_user_gaps_unauthenticated(self, app_client):
        """Unauthenticated requests return 401 or redirect."""
        client, _ = app_client
        resp = client.get("/api/content/gaps/user")
        assert resp.status_code in (401, 302)

    def test_user_gaps_authenticated(self, app_client):
        """Authenticated user can fetch user-specific gap analysis."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/content/gaps/user")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Reading Comprehension — /api/reading/comprehension
# ---------------------------------------------------------------------------

class TestReadingComprehension:

    def test_comprehension_missing_text(self, app_client):
        """Missing text_zh returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/reading/comprehension",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_comprehension_returns_questions(self, app_client):
        """Valid text_zh returns comprehension questions."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/reading/comprehension",
            json={"text_zh": "今天我和朋友去学校。", "hsk_level": 1},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "questions" in data
        assert isinstance(data["questions"], list)
        assert len(data["questions"]) >= 1

    def test_comprehension_text_too_long(self, app_client):
        """text_zh exceeding 2000 chars returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/reading/comprehension",
            json={"text_zh": "你" * 2001},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_comprehension_gist_question_always_present(self, app_client):
        """The gist question type is always included."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/reading/comprehension",
            json={"text_zh": "这是一个简单的句子。"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        types = [q["type"] for q in data["questions"]]
        assert "gist" in types
