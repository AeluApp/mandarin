"""Tests for grammar routes — levels, points, detail, progress, mastery."""

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
    create_user(conn, "grammar@test.com", "testpass123456", "GrammarTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": "grammar@test.com",
        "password": "testpass123456",
    }, follow_redirects=True)


def _seed_grammar(conn):
    """Insert minimal grammar test data."""
    conn.execute("""
        INSERT OR IGNORE INTO grammar_point (id, name, name_zh, hsk_level, category, description, examples_json, difficulty)
        VALUES (9001, 'Test Structure', '测试结构', 1, 'structure', 'A test grammar point.',
                '[{"zh":"这是测试。","pinyin":"zhè shì cèshì.","en":"This is a test."}]', 1)
    """)
    conn.execute("""
        INSERT OR IGNORE INTO grammar_point (id, name, name_zh, hsk_level, category, description, examples_json, difficulty)
        VALUES (9002, 'Test Particle', '测试粒子', 2, 'particle', 'Another test point.', '[]', 2)
    """)
    conn.execute("""
        INSERT OR IGNORE INTO grammar_point (id, name, name_zh, hsk_level, category, description, examples_json, difficulty)
        VALUES (9003, 'HSK 5 Point', '高级语法', 5, 'complement', 'Advanced grammar.', '[]', 3)
    """)
    conn.commit()


class TestGrammarLevels:

    def test_levels_returns_distinct_hsk_levels(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/levels",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        levels = data["levels"]
        assert 1 in levels
        assert 2 in levels
        assert 5 in levels

    def test_levels_requires_auth(self, app_client):
        client, conn = app_client
        resp = client.get("/api/grammar/levels")
        assert resp.status_code in (302, 401)


class TestGrammarPoints:

    def test_list_all_points(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/points",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        points = resp.get_json()["points"]
        assert len(points) >= 3

    def test_filter_by_hsk_level(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/points?hsk_level=1",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        points = resp.get_json()["points"]
        for p in points:
            assert p["hsk_level"] == 1

    def test_filter_by_category(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/points?category=particle",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        points = resp.get_json()["points"]
        for p in points:
            assert p["category"] == "particle"


class TestGrammarPointDetail:

    def test_detail_returns_examples(self, app_client):
        """Detail endpoint returns parsed examples (regression: sqlite3.Row.get crash)."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/point/9001",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Test Structure"
        assert data["name_zh"] == "测试结构"
        assert len(data["examples"]) == 1
        assert data["examples"][0]["zh"] == "这是测试。"
        assert data["drill_attempts"] == 0
        assert data["drill_correct"] == 0

    def test_detail_not_found(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/grammar/point/99999",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 404

    def test_detail_with_studied_progress(self, app_client):
        """Detail shows studied state after marking progress."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        # Mark as studied
        client.post("/api/grammar/progress",
                    data=json.dumps({"grammar_point_id": 9001}),
                    content_type="application/json",
                    headers={"X-Requested-With": "XMLHttpRequest"})
        # Fetch detail — should show studied
        resp = client.get("/api/grammar/point/9001",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        data = resp.get_json()
        assert data["studied"] is True
        assert data["studied_at"] is not None


class TestGrammarProgress:

    def test_mark_studied(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.post("/api/grammar/progress",
                           data=json.dumps({"grammar_point_id": 9001}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["grammar_point_id"] == 9001

    def test_mark_studied_idempotent(self, app_client):
        """Marking the same point twice doesn't error (upsert)."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        for _ in range(2):
            resp = client.post("/api/grammar/progress",
                               data=json.dumps({"grammar_point_id": 9001}),
                               content_type="application/json",
                               headers={"X-Requested-With": "XMLHttpRequest"})
            assert resp.status_code == 200

    def test_mark_nonexistent_point(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/grammar/progress",
                           data=json.dumps({"grammar_point_id": 99999}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 404

    def test_missing_grammar_point_id(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/grammar/progress",
                           data=json.dumps({}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400


class TestGrammarLesson:

    def test_lesson_returns_ordered_points(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/lesson/1",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["hsk_level"] == 1
        assert data["total"] >= 1
        assert isinstance(data["studied_count"], int)

    def test_lesson_empty_level(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/grammar/lesson/99",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0


class TestGrammarMastery:

    def test_mastery_overview(self, app_client):
        """Mastery endpoint doesn't crash (regression: sqlite3.Row.get)."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.get("/api/grammar/mastery",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "levels" in data
        assert "overall" in data
        assert data["overall"]["total"] >= 3

    def test_mastery_reflects_progress(self, app_client):
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        # Mark one studied
        client.post("/api/grammar/progress",
                    data=json.dumps({"grammar_point_id": 9001}),
                    content_type="application/json",
                    headers={"X-Requested-With": "XMLHttpRequest"})
        resp = client.get("/api/grammar/mastery",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        data = resp.get_json()
        assert data["overall"]["studied"] >= 1


class TestGrammarPractice:

    def test_practice_updates_mastery(self, app_client):
        """POST practice results updates drill_attempts/drill_correct/mastery_score."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        resp = client.post("/api/grammar/practice",
                           data=json.dumps({"grammar_point_id": 9001, "correct": 3, "total": 5}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["drill_attempts"] == 5
        assert data["drill_correct"] == 3
        assert data["mastery_score"] > 0

    def test_practice_ema_scoring(self, app_client):
        """Two rounds of practice — verify EMA mastery calculation."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        # Round 1: 100%
        resp1 = client.post("/api/grammar/practice",
                            data=json.dumps({"grammar_point_id": 9001, "correct": 5, "total": 5}),
                            content_type="application/json",
                            headers={"X-Requested-With": "XMLHttpRequest"})
        m1 = resp1.get_json()["mastery_score"]
        # Round 1: 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert abs(m1 - 0.7) < 0.01
        # Round 2: 0%
        resp2 = client.post("/api/grammar/practice",
                            data=json.dumps({"grammar_point_id": 9001, "correct": 0, "total": 5}),
                            content_type="application/json",
                            headers={"X-Requested-With": "XMLHttpRequest"})
        m2 = resp2.get_json()["mastery_score"]
        # Round 2: 0.7 * 0.0 + 0.3 * 0.7 = 0.21
        assert abs(m2 - 0.21) < 0.01
        data2 = resp2.get_json()
        assert data2["drill_attempts"] == 10
        assert data2["drill_correct"] == 5

    def test_practice_missing_fields(self, app_client):
        """400 on missing grammar_point_id/correct/total."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        # Missing correct
        resp = client.post("/api/grammar/practice",
                           data=json.dumps({"grammar_point_id": 9001, "total": 5}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400
        # Missing total
        resp = client.post("/api/grammar/practice",
                           data=json.dumps({"grammar_point_id": 9001, "correct": 3}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400
        # Missing grammar_point_id
        resp = client.post("/api/grammar/practice",
                           data=json.dumps({"correct": 3, "total": 5}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400

    def test_practice_nonexistent_point(self, app_client):
        """404 for invalid grammar_point_id."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/grammar/practice",
                           data=json.dumps({"grammar_point_id": 99999, "correct": 3, "total": 5}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 404

    def test_points_include_mastery(self, app_client):
        """Verify list endpoint includes mastery_score and drill_attempts."""
        client, conn = app_client
        _login(client, conn)
        _seed_grammar(conn)
        # Practice a point first
        client.post("/api/grammar/practice",
                    data=json.dumps({"grammar_point_id": 9001, "correct": 4, "total": 5}),
                    content_type="application/json",
                    headers={"X-Requested-With": "XMLHttpRequest"})
        # Fetch points list
        resp = client.get("/api/grammar/points?hsk_level=1",
                          headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        points = resp.get_json()["points"]
        p9001 = next((p for p in points if p["id"] == 9001), None)
        assert p9001 is not None
        assert "mastery_score" in p9001
        assert "drill_attempts" in p9001
        assert p9001["drill_attempts"] == 5
        assert p9001["mastery_score"] > 0
