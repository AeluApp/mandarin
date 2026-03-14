"""Tests for reading progress and media stats routes."""

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


def _login(client, conn, email="readmedia@test.com"):
    create_user(conn, email, "testpass123456", "ReadMediaTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": "testpass123456",
    }, follow_redirects=True)


class TestReadingProgress:

    def test_reading_progress_saves(self, app_client):
        """POST reading progress saves a reading_progress row."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/reading/progress",
                           data=json.dumps({
                               "passage_id": "test-read-1",
                               "words_looked_up": 5,
                               "questions_correct": 3,
                               "questions_total": 4,
                               "reading_time_seconds": 120
                           }),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

        # Verify row
        row = conn.execute(
            "SELECT * FROM reading_progress WHERE passage_id = 'test-read-1'"
        ).fetchone()
        assert row is not None
        assert row["words_looked_up"] == 5
        assert row["questions_correct"] == 3
        assert row["questions_total"] == 4
        assert row["reading_time_seconds"] == 120

    def test_reading_stats_empty(self, app_client):
        """Stats endpoint returns zeros for new user."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/reading/stats",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_passages"] == 0
        assert data["comprehension_pct"] == 0

    def test_reading_stats_after_progress(self, app_client):
        """Stats reflect recorded reading progress."""
        client, conn = app_client
        _login(client, conn)
        # Record two passages
        for pid, qc, qt in [("p1", 4, 5), ("p2", 3, 5)]:
            client.post("/api/reading/progress",
                        data=json.dumps({
                            "passage_id": pid,
                            "words_looked_up": 2,
                            "questions_correct": qc,
                            "questions_total": qt,
                            "reading_time_seconds": 90
                        }),
                        content_type="application/json",
                        headers={"X-Requested-With": "XMLHttpRequest"})

        resp = client.get("/api/reading/stats",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_passages"] == 2
        assert data["comprehension_pct"] == 70  # 7 / 10 = 70%
        assert data["total_words_looked_up"] == 4


class TestMediaStats:

    def test_media_stats_empty(self, app_client):
        """Stats endpoint returns zeros for new user."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/media/stats",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_watched"] == 0
        assert data["avg_comprehension"] == 0
        assert data["liked_count"] == 0


class TestMediaTierGating:

    def test_media_free_tier_gets_recommendations(self, app_client):
        """Free tier user gets recommendations (not fully blocked)."""
        client, conn = app_client
        create_user(conn, "freemedia@test.com", "testpass123456", "FreeMedia")
        conn.execute("UPDATE user SET subscription_tier = 'free' WHERE email = 'freemedia@test.com'")
        conn.commit()
        client.post("/auth/login", data={
            "email": "freemedia@test.com",
            "password": "testpass123456",
        }, follow_redirects=True)

        resp = client.get("/api/media/recommendations?limit=3",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        # Should get 200 with free_only flag, not 403
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("free_only") is True
