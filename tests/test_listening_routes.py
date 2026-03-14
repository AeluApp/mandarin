"""Tests for listening progress routes — completion persistence, stats, tier gating."""

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


def _login(client, conn):
    create_user(conn, "listen@test.com", "testpass123456", "ListenTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": "listen@test.com",
        "password": "testpass123456",
    }, follow_redirects=True)


class TestListeningComplete:

    def test_listening_complete_saves_progress(self, app_client):
        """POST completion saves a listening_progress row."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/listening/complete",
                           data=json.dumps({
                               "passage_id": "test-passage-1",
                               "comprehension_score": 0.8,
                               "questions_correct": 4,
                               "questions_total": 5,
                               "hsk_level": 2,
                               "words_encountered": []
                           }),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

        # Verify row in listening_progress
        row = conn.execute(
            "SELECT * FROM listening_progress WHERE passage_id = 'test-passage-1'"
        ).fetchone()
        assert row is not None
        assert row["comprehension_score"] == 0.8
        assert row["questions_correct"] == 4
        assert row["questions_total"] == 5
        assert row["hsk_level"] == 2


class TestListeningStats:

    def test_listening_stats_empty(self, app_client):
        """Stats endpoint returns zeros for new user."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/listening/stats",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_completed"] == 0
        assert data["avg_comprehension"] == 0
        assert data["by_level"] == []

    def test_listening_stats_after_completion(self, app_client):
        """Stats reflect completed passages."""
        client, conn = app_client
        _login(client, conn)
        # Complete two passages
        for pid, score in [("p1", 0.8), ("p2", 0.6)]:
            client.post("/api/listening/complete",
                        data=json.dumps({
                            "passage_id": pid,
                            "comprehension_score": score,
                            "questions_correct": int(score * 5),
                            "questions_total": 5,
                            "hsk_level": 1,
                            "words_encountered": []
                        }),
                        content_type="application/json",
                        headers={"X-Requested-With": "XMLHttpRequest"})

        resp = client.get("/api/listening/stats",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_completed"] == 2
        assert data["avg_comprehension"] == 70  # avg of 80% and 60%
        assert len(data["by_level"]) == 1
        assert data["by_level"][0]["hsk_level"] == 1
        assert data["by_level"][0]["completed"] == 2


class TestListeningTierGating:

    def test_listening_free_tier_hsk_gating(self, app_client):
        """Free user gets HSK 1-2, blocked from HSK 5."""
        client, conn = app_client
        # Create a free-tier user
        create_user(conn, "free@test.com", "testpass123456", "FreeUser")
        conn.execute("UPDATE user SET subscription_tier = 'free' WHERE email = 'free@test.com'")
        conn.commit()
        client.post("/auth/login", data={
            "email": "free@test.com",
            "password": "testpass123456",
        }, follow_redirects=True)

        # HSK 5 should be blocked
        resp = client.get("/api/listening/passage?hsk_level=5",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "upgrade_required"
