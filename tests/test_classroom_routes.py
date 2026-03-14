"""Tests for classroom routes (mandarin.web.classroom_routes).

Covers:
- Teacher can create a classroom (201 + invite_code in response)
- Teacher can list classrooms (includes created classroom)
- Non-teacher cannot create a classroom (403)
- Non-teacher cannot list classrooms (403)
- Student can join a classroom via invite code (200, tier upgraded to 'paid')
- Join with an invalid invite code (404)
- Join when already a member (400)
- Teacher can view the student list (200 + student present)
- Non-owner teacher cannot view students (403 or 404)
- Teacher can view class-level analytics (200)
- Teacher can generate bulk invite codes (200 + code list)
- Teacher can archive a classroom (200 + archived: true)
- Student cannot join an archived classroom (400)
- Teacher cannot create a classroom with an empty name (400)
- Unauthenticated requests are redirected / return 401
"""

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
    """Wraps a real sqlite3.Connection so it works as both a context manager
    (for ``with db.connection() as conn:``) and as a raw connection object
    (for ``conn = db.ensure_db()``).
    """

    def __init__(self, conn):
        self._conn = conn

    # Context-manager protocol — used by db.connection()
    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False

    # Raw-connection forwarding — used by db.ensure_db()
    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        # Do NOT actually close the connection during tests; the fixture owns it.
        pass


# ---------------------------------------------------------------------------
# Test-client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(test_db):
    """Flask test client with all DB access patched to the test database.

    Patches every module that touches ``db.connection`` or ``db.ensure_db``,
    including classroom_routes which uses both.

    Yields (client, conn).
    """
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    fake = _FakeConn(conn)

    # db.connection() is a *class* that acts as a context manager; we replace it
    # with a callable that returns our fake wrapper.
    fake_connection = lambda: fake  # noqa: E731

    # db.ensure_db() returns a raw connection; return the real conn directly.
    fake_ensure_db = lambda: conn  # noqa: E731

    with patch("mandarin.db.connection", fake_connection), \
         patch("mandarin.web.auth_routes.db.connection", fake_connection), \
         patch("mandarin.web.routes.db.connection", fake_connection), \
         patch("mandarin.web.payment_routes.db.connection", fake_connection), \
         patch("mandarin.web.onboarding_routes.db.connection", fake_connection), \
         patch("mandarin.web.admin_routes.db.connection", fake_connection), \
         patch("mandarin.web.classroom_routes.db.connection", fake_connection), \
         patch("mandarin.web.classroom_routes.db.ensure_db", fake_ensure_db), \
         patch("mandarin.web.classroom_routes.send_classroom_invite", return_value=None):
        with app.test_client() as client:
            yield client, conn


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------

def _login(client, conn, email="student@example.com", password="studentpass123"):
    """Create a student user and log them in. Returns the user dict."""
    user = create_user(conn, email, password, "Student")
    client.post(
        "/auth/login",
        data={"email": email, "password": password},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    # Push session directly so the login survives across requests.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user["id"])
        sess["_fresh"] = True
    return user


def _login_teacher(client, conn, email="teacher@example.com", password="teacherpass123"):
    """Create a teacher user, promote to teacher role, and log them in."""
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


# ---------------------------------------------------------------------------
# Utility: create a classroom directly in the DB
# ---------------------------------------------------------------------------

def _insert_classroom(conn, teacher_id, name="Test Class", status="active"):
    """Insert a classroom row and return its id and invite_code."""
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
# 1. Unauthenticated access
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    """All classroom endpoints require authentication."""

    def test_create_unauthenticated_redirects(self, app_client):
        client, _ = app_client
        resp = client.post(
            "/api/classroom/create",
            json={"name": "X"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (302, 401), resp.status_code

    def test_list_unauthenticated_redirects(self, app_client):
        client, _ = app_client
        resp = client.get("/api/classroom/list")
        assert resp.status_code in (302, 401), resp.status_code

    def test_join_unauthenticated_redirects(self, app_client):
        client, _ = app_client
        resp = client.post(
            "/api/classroom/join",
            json={"code": "anything"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (302, 401), resp.status_code

    def test_students_unauthenticated_redirects(self, app_client):
        client, _ = app_client
        resp = client.get("/api/classroom/999/students")
        assert resp.status_code in (302, 401), resp.status_code


# ---------------------------------------------------------------------------
# 2. Teacher — create classroom
# ---------------------------------------------------------------------------

class TestCreateClassroom:

    def test_teacher_creates_classroom_returns_201(self, app_client):
        client, conn = app_client
        _login_teacher(client, conn)
        resp = client.post(
            "/api/classroom/create",
            json={"name": "Mandarin 101", "description": "Beginner class"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201, resp.data

    def test_teacher_creates_classroom_response_has_id_and_invite_code(self, app_client):
        client, conn = app_client
        _login_teacher(client, conn)
        resp = client.post(
            "/api/classroom/create",
            json={"name": "Mandarin 202"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = json.loads(resp.data)
        assert "id" in data
        assert "invite_code" in data
        assert isinstance(data["id"], int)
        assert len(data["invite_code"]) > 0

    def test_student_cannot_create_classroom_gets_403(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/classroom/create",
            json={"name": "Should Fail"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 403, resp.data

    def test_empty_name_returns_400(self, app_client):
        client, conn = app_client
        _login_teacher(client, conn)
        resp = client.post(
            "/api/classroom/create",
            json={"name": "   ", "description": "bad"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400, resp.data
        data = json.loads(resp.data)
        assert "error" in data

    def test_name_too_long_returns_400(self, app_client):
        client, conn = app_client
        _login_teacher(client, conn)
        resp = client.post(
            "/api/classroom/create",
            json={"name": "x" * 101},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400, resp.data


# ---------------------------------------------------------------------------
# 3. Teacher — list classrooms
# ---------------------------------------------------------------------------

class TestListClassrooms:

    def test_teacher_can_list_classrooms_returns_200(self, app_client):
        client, conn = app_client
        _login_teacher(client, conn)
        resp = client.get("/api/classroom/list")
        assert resp.status_code == 200, resp.data

    def test_list_includes_created_classroom(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn)
        # Create one via the API
        client.post(
            "/api/classroom/create",
            json={"name": "Listed Class"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = client.get("/api/classroom/list")
        data = json.loads(resp.data)
        assert "classrooms" in data
        names = [c["name"] for c in data["classrooms"]]
        assert "Listed Class" in names

    def test_student_cannot_list_classrooms_gets_403(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/classroom/list")
        assert resp.status_code == 403, resp.data

    def test_list_response_shape(self, app_client):
        client, conn = app_client
        _login_teacher(client, conn)
        resp = client.get("/api/classroom/list")
        data = json.loads(resp.data)
        assert isinstance(data.get("classrooms"), list)


# ---------------------------------------------------------------------------
# 4. Student — join classroom
# ---------------------------------------------------------------------------

class TestJoinClassroom:

    def test_student_joins_with_valid_code_returns_200(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t1@example.com")
        _, code = _insert_classroom(conn, teacher["id"], name="Join Test")
        # Switch to student session
        student = create_user(conn, "s1@example.com", "studentpass123", "S1")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        resp = client.post(
            "/api/classroom/join",
            json={"code": code},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200, resp.data

    def test_student_join_upgrades_tier_to_paid(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t2@example.com")
        _, code = _insert_classroom(conn, teacher["id"], name="Tier Upgrade Test")
        student = create_user(conn, "s2@example.com", "studentpass123", "S2")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        client.post(
            "/api/classroom/join",
            json={"code": code},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        row = conn.execute(
            "SELECT subscription_tier FROM user WHERE id=?", (student["id"],)
        ).fetchone()
        assert row["subscription_tier"] == "paid"

    def test_join_returns_classroom_name(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t3@example.com")
        _, code = _insert_classroom(conn, teacher["id"], name="Named Class")
        student = create_user(conn, "s3@example.com", "studentpass123", "S3")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        resp = client.post(
            "/api/classroom/join",
            json={"code": code},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = json.loads(resp.data)
        assert data.get("classroom_name") == "Named Class"

    def test_join_invalid_code_returns_404(self, app_client):
        client, conn = app_client
        student = create_user(conn, "s4@example.com", "studentpass123", "S4")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        resp = client.post(
            "/api/classroom/join",
            json={"code": "totally-wrong-code"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404, resp.data

    def test_join_duplicate_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t4@example.com")
        _, code = _insert_classroom(conn, teacher["id"], name="Dup Test")
        student = create_user(conn, "s5@example.com", "studentpass123", "S5")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        # Join once
        client.post(
            "/api/classroom/join",
            json={"code": code},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Join again
        resp = client.post(
            "/api/classroom/join",
            json={"code": code},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400, resp.data
        data = json.loads(resp.data)
        assert "already" in data.get("error", "").lower()

    def test_join_archived_classroom_returns_400(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t5@example.com")
        _, code = _insert_classroom(conn, teacher["id"], name="Archived", status="archived")
        student = create_user(conn, "s6@example.com", "studentpass123", "S6")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        resp = client.post(
            "/api/classroom/join",
            json={"code": code},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400, resp.data

    def test_join_missing_code_returns_400(self, app_client):
        client, conn = app_client
        student = create_user(conn, "s7@example.com", "studentpass123", "S7")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(student["id"])
            sess["_fresh"] = True
        resp = client.post(
            "/api/classroom/join",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400, resp.data


# ---------------------------------------------------------------------------
# 5. Teacher — view students
# ---------------------------------------------------------------------------

class TestClassroomStudents:

    def test_teacher_owner_views_students_returns_200(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t6@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="Students Test")
        resp = client.get(f"/api/classroom/{cid}/students")
        assert resp.status_code == 200, resp.data

    def test_students_list_includes_joined_student(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t7@example.com")
        cid, code = _insert_classroom(conn, teacher["id"], name="With Student")
        # Enroll a student directly
        student = create_user(conn, "s8@example.com", "studentpass123", "StudentX")
        conn.execute(
            "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
            (cid, student["id"]),
        )
        conn.commit()
        resp = client.get(f"/api/classroom/{cid}/students")
        data = json.loads(resp.data)
        assert "students" in data
        emails = [s["email"] for s in data["students"]]
        assert "s8@example.com" in emails

    def test_non_owner_teacher_cannot_view_students(self, app_client):
        client, conn = app_client
        # Owner teacher inserts a classroom
        owner = create_user(conn, "owner@example.com", "ownerpass123", "Owner")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (owner["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, owner["id"], name="Owner's Class")
        # Non-owner teacher logs in
        _login_teacher(client, conn, email="other@example.com", password="otherpass123")
        resp = client.get(f"/api/classroom/{cid}/students")
        assert resp.status_code in (403, 404), resp.data

    def test_student_cannot_view_students(self, app_client):
        client, conn = app_client
        teacher = create_user(conn, "t8@example.com", "teacherpass123", "T8")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (teacher["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, teacher["id"], name="Blocked Class")
        _login(client, conn)
        resp = client.get(f"/api/classroom/{cid}/students")
        assert resp.status_code == 403, resp.data


# ---------------------------------------------------------------------------
# 6. Teacher — analytics
# ---------------------------------------------------------------------------

class TestClassroomAnalytics:

    def test_teacher_views_analytics_returns_200(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t9@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="Analytics Class")
        resp = client.get(f"/api/classroom/{cid}/analytics")
        assert resp.status_code == 200, resp.data

    def test_analytics_response_shape(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t10@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="Shape Class")
        resp = client.get(f"/api/classroom/{cid}/analytics")
        data = json.loads(resp.data)
        for key in ("hsk_distribution", "weekly_trend"):
            assert key in data, f"Missing key in analytics response: {key}"

    def test_non_owner_cannot_view_analytics(self, app_client):
        client, conn = app_client
        owner = create_user(conn, "owner2@example.com", "ownerpass123", "Owner2")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (owner["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, owner["id"], name="Owner2 Class")
        _login_teacher(client, conn, email="t11@example.com", password="teacherpass123")
        resp = client.get(f"/api/classroom/{cid}/analytics")
        assert resp.status_code in (403, 404), resp.data


# ---------------------------------------------------------------------------
# 7. Bulk invite
# ---------------------------------------------------------------------------

class TestBulkInvite:

    def test_generate_codes_returns_list(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t12@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="Bulk Codes")
        resp = client.post(
            f"/api/classroom/{cid}/invite/bulk",
            json={"mode": "generate", "count": 3},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200, resp.data
        data = json.loads(resp.data)
        assert "codes" in data
        assert len(data["codes"]) == 3

    def test_generate_codes_returns_strings(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t13@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="Code Strings")
        resp = client.post(
            f"/api/classroom/{cid}/invite/bulk",
            json={"mode": "generate", "count": 2},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = json.loads(resp.data)
        for code in data["codes"]:
            assert isinstance(code, str)
            assert len(code) > 0

    def test_csv_mode_sends_invites(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t14@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="CSV Class")
        resp = client.post(
            f"/api/classroom/{cid}/invite/bulk",
            json={"mode": "csv", "csv": "alice@test.com\nbob@test.com"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200, resp.data
        data = json.loads(resp.data)
        assert data.get("invited") == 2

    def test_student_cannot_bulk_invite(self, app_client):
        client, conn = app_client
        teacher = create_user(conn, "t15@example.com", "teacherpass123", "T15")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (teacher["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, teacher["id"], name="Guarded Bulk")
        _login(client, conn)
        resp = client.post(
            f"/api/classroom/{cid}/invite/bulk",
            json={"mode": "generate", "count": 1},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 403, resp.data

    def test_non_owner_cannot_bulk_invite(self, app_client):
        client, conn = app_client
        owner = create_user(conn, "owner3@example.com", "ownerpass123", "Owner3")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (owner["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, owner["id"], name="Owner3 Class")
        _login_teacher(client, conn, email="t16@example.com", password="teacherpass123")
        resp = client.post(
            f"/api/classroom/{cid}/invite/bulk",
            json={"mode": "generate", "count": 1},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (403, 404), resp.data


# ---------------------------------------------------------------------------
# 8. Archive classroom
# ---------------------------------------------------------------------------

class TestArchiveClassroom:

    def test_teacher_archives_own_classroom_returns_200(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t17@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="To Archive")
        resp = client.post(
            f"/api/classroom/{cid}/archive",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200, resp.data

    def test_archive_response_has_archived_true(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t18@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="Archive Flag")
        resp = client.post(
            f"/api/classroom/{cid}/archive",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = json.loads(resp.data)
        assert data.get("archived") is True

    def test_archive_sets_status_in_db(self, app_client):
        client, conn = app_client
        teacher = _login_teacher(client, conn, email="t19@example.com")
        cid, _ = _insert_classroom(conn, teacher["id"], name="DB Archive")
        client.post(
            f"/api/classroom/{cid}/archive",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        row = conn.execute(
            "SELECT status FROM classroom WHERE id=?", (cid,)
        ).fetchone()
        assert row["status"] == "archived"

    def test_student_cannot_archive_classroom(self, app_client):
        client, conn = app_client
        teacher = create_user(conn, "t20@example.com", "teacherpass123", "T20")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (teacher["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, teacher["id"], name="Protected Archive")
        _login(client, conn)
        resp = client.post(
            f"/api/classroom/{cid}/archive",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 403, resp.data

    def test_non_owner_cannot_archive_classroom(self, app_client):
        client, conn = app_client
        owner = create_user(conn, "owner4@example.com", "ownerpass123", "Owner4")
        conn.execute(
            "UPDATE user SET role='teacher', subscription_tier='teacher' WHERE id=?",
            (owner["id"],),
        )
        conn.commit()
        cid, _ = _insert_classroom(conn, owner["id"], name="Owner4 Class")
        _login_teacher(client, conn, email="t21@example.com", password="teacherpass123")
        resp = client.post(
            f"/api/classroom/{cid}/archive",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Either classroom not found (404) or already enforces owner check via rowcount=0
        assert resp.status_code in (403, 404), resp.data
