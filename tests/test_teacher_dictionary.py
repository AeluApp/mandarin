"""Tests for teacher/classroom and dictionary features (V95).

Covers:
- Assignment creation (typed, with submissions tracking)
- Assignment listing with submission stats
- Assignment detail with per-student submissions
- Student assignment submission
- Exportable progress reports (CSV)
- Curriculum sequencing (create, get, update)
- Dictionary lookup (CC-CEDICT)
- Add to study from dictionary
- Example sentences in dictionary results
- Dictionary module unit tests
- Schema migration (tables exist)
"""

import csv
import io
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Password hashing compat for Python 3.9
# ---------------------------------------------------------------------------

from werkzeug.security import generate_password_hash as _orig_gen


def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


# ---------------------------------------------------------------------------
# Fake DB context-manager wrapper
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Test-client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(test_db):
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    fake = _FakeConn(conn)
    def fake_connection(): return fake
    def fake_ensure_db(): return conn

    with patch("mandarin.db.connection", fake_connection), \
         patch("mandarin.web.auth_routes.db.connection", fake_connection), \
         patch("mandarin.web.routes.db.connection", fake_connection), \
         patch("mandarin.web.payment_routes.db.connection", fake_connection), \
         patch("mandarin.web.onboarding_routes.db.connection", fake_connection), \
         patch("mandarin.web.admin_routes.db.connection", fake_connection), \
         patch("mandarin.web.classroom_routes.db.connection", fake_connection), \
         patch("mandarin.web.classroom_routes.db.ensure_db", fake_ensure_db), \
         patch("mandarin.web.classroom_routes.send_classroom_invite", return_value=None), \
         patch("mandarin.web.exposure_routes.db.connection", fake_connection):
        with app.test_client() as client:
            yield client, conn


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------

def _login(client, conn, email="student@example.com", password="studentpass123"):
    user = create_user(conn, email, password, "Student")
    client.post(
        "/auth/login",
        data={"email": email, "password": password},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user["id"])
        sess["_fresh"] = True
    return user


def _login_teacher(client, conn, email="teacher@example.com", password="teacherpass123"):
    user = create_user(conn, email, password, "Teacher")
    conn.execute(
        "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
        (user["id"],),
    )
    conn.commit()
    client.post(
        "/auth/login",
        data={"email": email, "password": password},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user["id"])
        sess["_fresh"] = True
    return user


def _insert_classroom(conn, teacher_id, name="Test Class", status="active"):
    import secrets
    code = secrets.token_urlsafe(8)
    cursor = conn.execute(
        """INSERT INTO classroom (teacher_user_id, name, description, invite_code, status)
           VALUES (?, ?, '', ?, ?)""",
        (teacher_id, name, code, status),
    )
    conn.commit()
    return cursor.lastrowid, code


# ---------------------------------------------------------------------------
# 1. Assignment creation (typed)
# ---------------------------------------------------------------------------

class TestAssignmentCreation:

    def test_teacher_creates_assignment_returns_201(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={
                "title": "HSK 1 Drill Set",
                "assignment_type": "drill",
                "content_ids": [1, 2, 3],
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201, resp.data
        data = json.loads(resp.data)
        assert "id" in data
        assert data["title"] == "HSK 1 Drill Set"
        assert data["assignment_type"] == "drill"

    def test_assignment_creates_submissions_for_students(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        cid, _ = _insert_classroom(conn, teacher["id"])
        # Add a student
        student = create_user(conn, "s1@example.com", "studentpass123", "S1")
        conn.execute(
            "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
            (cid, student["id"]),
        )
        conn.commit()
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"title": "Reading Task", "assignment_type": "reading"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["student_count"] == 1
        # Verify submission record exists
        sub = conn.execute(
            "SELECT * FROM assignment_submission WHERE assignment_id = ? AND user_id = ?",
            (data["id"], student["id"]),
        ).fetchone()
        assert sub is not None
        assert sub["status"] == "pending"

    def test_assignment_missing_title_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"assignment_type": "drill"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_assignment_invalid_type_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"title": "Bad", "assignment_type": "invalid"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Assignment listing and detail
# ---------------------------------------------------------------------------

class TestAssignmentListing:

    def test_list_assignments_returns_200(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        cid, _ = _insert_classroom(conn, teacher["id"])
        # Create one
        client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"title": "Test Assignment", "assignment_type": "mixed"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = client.get(f"/api/classroom/{cid}/assignments/list")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["assignments"]) == 1
        assert data["assignments"][0]["title"] == "Test Assignment"

    def test_assignment_detail_includes_submissions(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        cid, _ = _insert_classroom(conn, teacher["id"])
        student = create_user(conn, "s2@example.com", "studentpass123", "S2")
        conn.execute(
            "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
            (cid, student["id"]),
        )
        conn.commit()
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"title": "Detail Test", "assignment_type": "grammar"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        aid = json.loads(resp.data)["id"]
        resp = client.get(f"/api/assignments/{aid}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["title"] == "Detail Test"
        assert len(data["submissions"]) == 1
        assert data["submissions"][0]["status"] == "pending"


# ---------------------------------------------------------------------------
# 3. Student assignment submission
# ---------------------------------------------------------------------------

class TestAssignmentSubmission:

    def test_student_submits_assignment(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t3@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        student = create_user(conn, "s3@example.com", "studentpass123", "S3")
        conn.execute(
            "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
            (cid, student["id"]),
        )
        conn.commit()
        # Teacher creates assignment
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"title": "Submit Test", "assignment_type": "drill"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        aid = json.loads(resp.data)["id"]
        # Switch to student
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        resp = client.post(
            f"/api/assignments/{aid}/submit",
            json={"items_completed": 10, "items_correct": 8, "time_spent_seconds": 300},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["score"] == 80.0
        assert data["status"] == "completed"

    def test_double_submit_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t4@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        student = create_user(conn, "s4@example.com", "studentpass123", "S4")
        conn.execute(
            "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
            (cid, student["id"]),
        )
        conn.commit()
        resp = client.post(
            f"/api/classroom/{cid}/assignments/create",
            json={"title": "Double Submit", "assignment_type": "drill"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        aid = json.loads(resp.data)["id"]
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        client.post(
            f"/api/assignments/{aid}/submit",
            json={"items_completed": 5, "items_correct": 5, "time_spent_seconds": 100},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = client.post(
            f"/api/assignments/{aid}/submit",
            json={"items_completed": 5, "items_correct": 5, "time_spent_seconds": 100},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Exportable progress reports
# ---------------------------------------------------------------------------

class TestExportProgress:

    def test_export_csv_returns_valid_csv(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t5@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        student = create_user(conn, "s5@example.com", "studentpass123", "S5")
        conn.execute(
            "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
            (cid, student["id"]),
        )
        conn.commit()
        resp = client.get(f"/api/classroom/{cid}/export?format=csv")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert "Content-Disposition" in resp.headers
        # Parse CSV
        reader = csv.reader(io.StringIO(resp.data.decode("utf-8")))
        rows = list(reader)
        assert rows[0][0] == "Name"
        assert rows[0][1] == "Email"
        assert len(rows) == 2  # header + 1 student

    def test_export_invalid_format_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t6@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.get(f"/api/classroom/{cid}/export?format=xlsx")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 5. Curriculum sequencing
# ---------------------------------------------------------------------------

class TestCurriculum:

    def test_create_curriculum_returns_201(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t7@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/curriculum",
            json={
                "name": "Semester 1 Path",
                "sequence": [
                    {"type": "hsk_level", "id": 1, "order": 1},
                    {"type": "grammar", "id": 5, "order": 2},
                    {"type": "reading", "id": 10, "order": 3},
                ],
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["name"] == "Semester 1 Path"
        assert data["sequence_length"] == 3

    def test_get_curriculum_returns_paths(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t8@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        client.post(
            f"/api/classroom/{cid}/curriculum",
            json={"name": "Path A", "sequence": [{"type": "hsk_level", "id": 1, "order": 1}]},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = client.get(f"/api/classroom/{cid}/curriculum")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["curriculum_paths"]) == 1
        assert data["curriculum_paths"][0]["name"] == "Path A"

    def test_update_curriculum_sequence(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t9@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/curriculum",
            json={"name": "Updatable", "sequence": [{"type": "hsk_level", "id": 1, "order": 1}]},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        path_id = json.loads(resp.data)["id"]
        resp = client.put(
            f"/api/classroom/{cid}/curriculum/{path_id}",
            json={
                "name": "Updated Path",
                "sequence": [
                    {"type": "hsk_level", "id": 1, "order": 1},
                    {"type": "grammar", "id": 2, "order": 2},
                ],
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["updated"] is True

    def test_curriculum_empty_sequence_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t10@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/curriculum",
            json={"name": "Empty", "sequence": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_curriculum_invalid_type_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t11@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"])
        resp = client.post(
            f"/api/classroom/{cid}/curriculum",
            json={"name": "Bad", "sequence": [{"type": "invalid", "id": 1, "order": 1}]},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. Dictionary lookup
# ---------------------------------------------------------------------------

class TestDictionaryLookup:

    def test_lookup_cedict_returns_results(self, app_client):
        client, conn = app_client
        _login(client, conn)
        # Seed a dictionary entry
        conn.execute(
            "INSERT INTO dictionary_entry (traditional, simplified, pinyin, english) VALUES (?, ?, ?, ?)",
            ("你好", "你好", "ni3 hao3", "hello/hi"),
        )
        conn.commit()
        resp = client.get("/api/dictionary/lookup?q=你好")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["found"] is True
        assert len(data.get("cedict_results", [])) >= 1
        assert data["cedict_results"][0]["simplified"] == "你好"

    def test_lookup_empty_query_returns_400(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/dictionary/lookup?q=")
        assert resp.status_code == 400

    def test_lookup_english_cedict_match(self, app_client):
        client, conn = app_client
        _login(client, conn)
        conn.execute(
            "INSERT INTO dictionary_entry (traditional, simplified, pinyin, english) VALUES (?, ?, ?, ?)",
            ("貓", "猫", "mao1", "cat"),
        )
        conn.commit()
        resp = client.get("/api/dictionary/lookup?q=cat")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["found"] is True
        assert len(data.get("cedict_results", [])) >= 1
        assert "cat" in data["cedict_results"][0]["english"].lower()


# ---------------------------------------------------------------------------
# 7. Add to study from dictionary
# ---------------------------------------------------------------------------

class TestAddToStudy:

    def test_add_to_study_creates_content_item(self, app_client):
        client, conn = app_client
        _login(client, conn, email="study1@example.com")
        resp = client.post(
            "/api/dictionary/add-to-study",
            json={"simplified": "学习", "pinyin": "xué xí", "english": "to study"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["hanzi"] == "学习"
        assert data["content_item_id"] > 0
        # Verify in DB
        item = conn.execute(
            "SELECT * FROM content_item WHERE id = ?", (data["content_item_id"],)
        ).fetchone()
        assert item["status"] == "drill_ready"
        assert item["source"] == "dictionary_import"

    def test_add_duplicate_returns_409(self, app_client):
        client, conn = app_client
        _login(client, conn, email="study2@example.com")
        # First add
        client.post(
            "/api/dictionary/add-to-study",
            json={"simplified": "重复", "pinyin": "chóng fù", "english": "to repeat"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Second add — duplicate
        resp = client.post(
            "/api/dictionary/add-to-study",
            json={"simplified": "重复", "pinyin": "chóng fù", "english": "to repeat"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 409

    def test_add_missing_fields_returns_400(self, app_client):
        client, conn = app_client
        _login(client, conn, email="study3@example.com")
        resp = client.post(
            "/api/dictionary/add-to-study",
            json={"simplified": "只有汉字"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 8. Dictionary module unit tests
# ---------------------------------------------------------------------------

class TestDictionaryModule:

    def test_parse_cedict_line(self):
        from mandarin.dictionary import parse_cedict_line
        entry = parse_cedict_line("你好 你好 [ni3 hao3] /hello/hi/")
        assert entry is not None
        assert entry["traditional"] == "你好"
        assert entry["simplified"] == "你好"
        assert entry["pinyin"] == "ni3 hao3"
        assert entry["english"] == "hello/hi"

    def test_parse_cedict_comment_returns_none(self):
        from mandarin.dictionary import parse_cedict_line
        assert parse_cedict_line("# This is a comment") is None
        assert parse_cedict_line("") is None

    def test_lookup_db_exact_match(self, test_db):
        conn, _ = test_db
        from mandarin.dictionary import lookup
        conn.execute(
            "INSERT INTO dictionary_entry (traditional, simplified, pinyin, english) VALUES (?, ?, ?, ?)",
            ("書", "书", "shu1", "book"),
        )
        conn.commit()
        results = lookup(conn, "书")
        assert len(results) >= 1
        assert results[0]["simplified"] == "书"

    def test_find_example_sentences(self, test_db):
        conn, _ = test_db
        from mandarin.dictionary import find_example_sentences
        # Seed a sentence containing the word
        conn.execute(
            """INSERT INTO content_item (hanzi, pinyin, english, item_type, status)
               VALUES (?, ?, ?, 'sentence', 'drill_ready')""",
            ("我喜欢看书", "wǒ xǐ huān kàn shū", "I like reading books"),
        )
        conn.commit()
        examples = find_example_sentences(conn, "看书")
        assert len(examples) >= 1
        assert "看书" in examples[0]["hanzi"]


# ---------------------------------------------------------------------------
# 9. Schema migration tests
# ---------------------------------------------------------------------------

class TestSchemaMigration:

    def test_assignment_table_exists(self, test_db):
        conn, _ = test_db
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "assignment" in tables
        assert "assignment_submission" in tables

    def test_curriculum_path_table_exists(self, test_db):
        conn, _ = test_db
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "curriculum_path" in tables

    def test_dictionary_entry_table_exists(self, test_db):
        conn, _ = test_db
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "dictionary_entry" in tables
