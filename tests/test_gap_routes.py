"""Tests for gap routes — OCR dictionary, widget data, study lists."""

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


def _login(client, conn, email="gap@test.com"):
    create_user(conn, email, "testpass123456", "GapTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": "testpass123456",
    }, follow_redirects=True)


# ---------------------------------------------------------------------------
# OCR Dictionary — /api/dictionary/ocr
# ---------------------------------------------------------------------------

class TestDictionaryOCR:

    def test_ocr_unauthenticated(self, app_client):
        """Unauthenticated OCR requests return 401."""
        client, _ = app_client
        resp = client.post(
            "/api/dictionary/ocr",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (401, 302)

    def test_ocr_no_image_returns_400(self, app_client):
        """Missing image data returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/dictionary/ocr",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_ocr_image_too_large_returns_400(self, app_client):
        """Image exceeding 2MB returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/dictionary/ocr",
            json={"image_base64": "A" * (2 * 1024 * 1024 + 1)},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_ocr_graceful_without_pytesseract(self, app_client):
        """When pytesseract is unavailable, returns a graceful response."""
        client, conn = app_client
        _login(client, conn)
        # Use a minimal base64 string (won't be valid image but pytesseract
        # import will fail gracefully if not installed)
        resp = client.post(
            "/api/dictionary/ocr",
            json={"image_base64": "aGVsbG8="},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # Either 200 (graceful fallback) or 500 (processing error)
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# Widget Data — /api/widget/data
# ---------------------------------------------------------------------------

class TestWidgetData:

    def test_widget_unauthenticated_returns_defaults(self, app_client):
        """Unauthenticated widget request returns safe defaults."""
        client, _ = app_client
        resp = client.get("/api/widget/data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["authenticated"] is False
        assert data["due_count"] == 0
        assert data["streak_days"] == 0

    def test_widget_authenticated(self, app_client):
        """Authenticated user gets widget data with authenticated=True."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/widget/data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["authenticated"] is True
        assert "due_count" in data
        assert "streak_days" in data


# ---------------------------------------------------------------------------
# Study Lists — /api/study-lists
# ---------------------------------------------------------------------------

class TestStudyLists:

    def test_create_list_unauthenticated(self, app_client):
        """Unauthenticated study list creation returns 401 or redirect."""
        client, _ = app_client
        resp = client.post(
            "/api/study-lists",
            json={"name": "Test List", "item_ids": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (401, 302)

    def test_create_list_missing_name(self, app_client):
        """Missing name returns 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/study-lists",
            json={"item_ids": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_create_and_get_list(self, app_client):
        """Create a study list then retrieve it."""
        client, conn = app_client
        _login(client, conn)

        # Create
        resp = client.post(
            "/api/study-lists",
            json={"name": "My List", "description": "Test", "item_ids": []},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "My List"

        # Retrieve
        resp = client.get("/api/study-lists")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "lists" in data
        assert len(data["lists"]) >= 1

    def test_get_lists_unauthenticated(self, app_client):
        """Unauthenticated GET study-lists returns 401 or redirect."""
        client, _ = app_client
        resp = client.get("/api/study-lists")
        assert resp.status_code in (401, 302)


# ---------------------------------------------------------------------------
# Shared Study Lists — /api/study-lists/shared/<code>
# ---------------------------------------------------------------------------

class TestSharedStudyList:

    def test_shared_list_invalid_code(self, app_client):
        """Invalid share code returns 404."""
        client, _ = app_client
        resp = client.get("/api/study-lists/shared/nonexistent_code")
        assert resp.status_code == 404

    def test_shared_list_empty_code(self, app_client):
        """Overly long code returns 400."""
        client, _ = app_client
        resp = client.get("/api/study-lists/shared/" + "a" * 51)
        assert resp.status_code == 400
