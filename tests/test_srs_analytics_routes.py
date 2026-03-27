"""Tests for SRS analytics routes (mandarin.web.srs_analytics_routes).

Covers:
- Unauthenticated requests get 401
- Authenticated user can GET/PUT retention target
- Authenticated user can suspend/unsuspend/bury/reschedule items
- Exam readiness and retention forecast endpoints respond 200
- Content import endpoints validate input
- Reading passage endpoints respond correctly
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web.auth_routes import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    """Return a callable whose return value acts as a context manager yielding *conn*."""

    class _FakeConnection:
        def __enter__(self):
            return conn

        def __exit__(self, *args):
            return False

    return _FakeConnection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(test_db):
    """Flask test client — unauthenticated."""
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.srs_analytics_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def auth_client(test_db):
    """Flask test client logged in as a regular user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.srs_analytics_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:

    def test_retention_target_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/settings/retention-target")
        assert resp.status_code in (302, 401)

    def test_suspend_unauthenticated(self, client):
        c, _ = client
        resp = c.post("/api/items/1/suspend",
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code in (302, 401)

    def test_exam_readiness_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/analytics/exam-readiness")
        assert resp.status_code in (302, 401)

    def test_retention_forecast_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/analytics/retention-forecast")
        assert resp.status_code in (302, 401)

    def test_import_text_unauthenticated(self, client):
        c, _ = client
        resp = c.post("/api/content/import-text",
                       json={"text": "hello"},
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Retention target
# ---------------------------------------------------------------------------

class TestRetentionTarget:

    def test_get_retention_target_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/settings/retention-target")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "target_retention_rate" in data

    def test_put_retention_target_valid(self, auth_client):
        c, _ = auth_client
        resp = c.put(
            "/api/settings/retention-target",
            json={"target_retention_rate": 0.90},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["target_retention_rate"] == 0.90

    def test_put_retention_target_out_of_range(self, auth_client):
        c, _ = auth_client
        resp = c.put(
            "/api/settings/retention-target",
            json={"target_retention_rate": 0.50},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_put_retention_target_missing_value(self, auth_client):
        c, _ = auth_client
        resp = c.put(
            "/api/settings/retention-target",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Suspend / unsuspend / bury
# ---------------------------------------------------------------------------

class TestItemActions:

    def _insert_item(self, conn):
        """Insert a content_item and return its id."""
        cursor = conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES ('你', 'nǐ', 'you', 1)"
        )
        conn.commit()
        return cursor.lastrowid

    def test_suspend_item_not_found(self, auth_client):
        c, _ = auth_client
        resp = c.post("/api/items/99999/suspend",
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 404

    def test_suspend_item_success(self, auth_client):
        c, conn = auth_client
        item_id = self._insert_item(conn)
        resp = c.post(f"/api/items/{item_id}/suspend",
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "suspended"

    def test_unsuspend_item(self, auth_client):
        c, conn = auth_client
        item_id = self._insert_item(conn)
        # Suspend first
        c.post(f"/api/items/{item_id}/suspend",
               headers={"X-Requested-With": "XMLHttpRequest"})
        # Unsuspend
        resp = c.post(f"/api/items/{item_id}/unsuspend",
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "unsuspended"

    def test_bury_item_success(self, auth_client):
        c, conn = auth_client
        item_id = self._insert_item(conn)
        resp = c.post(f"/api/items/{item_id}/bury",
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "buried"
        assert "until" in data

    def test_bury_item_not_found(self, auth_client):
        c, _ = auth_client
        resp = c.post("/api/items/99999/bury",
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------

class TestReschedule:

    def _setup_item_with_progress(self, conn):
        """Insert a content_item + progress row, return item_id."""
        cursor = conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES ('好', 'hǎo', 'good', 1)"
        )
        item_id = cursor.lastrowid
        conn.execute(
            """INSERT INTO progress (user_id, content_item_id, modality, total_attempts)
               VALUES (1, ?, 'reading', 1)""",
            (item_id,),
        )
        conn.commit()
        return item_id

    def test_reschedule_missing_date(self, auth_client):
        c, _ = auth_client
        resp = c.post("/api/items/1/reschedule",
                       json={},
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400

    def test_reschedule_invalid_date_format(self, auth_client):
        c, _ = auth_client
        resp = c.post("/api/items/1/reschedule",
                       json={"next_review_date": "not-a-date"},
                       headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400

    def test_reschedule_success(self, auth_client):
        c, conn = auth_client
        item_id = self._setup_item_with_progress(conn)
        resp = c.post(
            f"/api/items/{item_id}/reschedule",
            json={"next_review_date": "2099-12-31"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "rescheduled"


# ---------------------------------------------------------------------------
# Content import — text
# ---------------------------------------------------------------------------

class TestContentImportText:

    def test_import_text_empty_returns_400(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/content/import-text",
            json={"text": ""},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_import_text_too_short_returns_400(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/content/import-text",
            json={"text": "a"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_import_text_success(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/content/import-text",
            json={"text": "你好世界欢迎来到中国"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "summary" in data
        assert "total_tokens" in data["summary"]


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

class TestContentImportCSV:

    def test_import_csv_no_data_returns_400(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/content/import-csv",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_import_csv_missing_hanzi_column_returns_400(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/content/import-csv",
            json={"csv_data": "word,meaning\nhi,hello"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_import_csv_success(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/api/content/import-csv",
            json={"csv_data": "hanzi,pinyin,english,hsk_level\n你,nǐ,you,1\n好,hǎo,good,1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "imported" in data
        assert "skipped" in data


# ---------------------------------------------------------------------------
# Reading passages filtered (no auth required by _get_user_id but endpoint exists)
# ---------------------------------------------------------------------------

class TestReadingPassagesFiltered:

    def test_invalid_source_type_returns_400(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/reading/passages/filtered?source_type=invalid")
        assert resp.status_code == 400

    def test_filtered_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/api/reading/passages/filtered")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "passages" in data
        assert "count" in data
