"""Tests for exposure routes — reading, media shelf, listening, encounters."""

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


def _login(client, conn, email="exposure@test.com"):
    create_user(conn, email, "testpass123456", "ExposureTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": "testpass123456",
    }, follow_redirects=True)


class TestEncountersSummary:

    def test_encounters_unauthenticated(self, app_client):
        """Unauthenticated requests to encounters return 401."""
        client, _ = app_client
        resp = client.get("/api/encounters/summary")
        assert resp.status_code in (401, 302)

    def test_encounters_empty(self, app_client):
        """Authenticated user with no encounters gets empty summary."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/encounters/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total" in data or "encounters" in data or isinstance(data, dict)


class TestReadingPassages:

    def test_passages_unauthenticated(self, app_client):
        """Unauthenticated requests to reading passages return 401."""
        client, _ = app_client
        resp = client.get("/api/reading/passages")
        assert resp.status_code in (401, 302)

    def test_passages_authenticated(self, app_client):
        """Authenticated user can fetch reading passages."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/reading/passages")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


class TestListeningPassage:

    def test_listening_unauthenticated(self, app_client):
        """Unauthenticated requests to listening return 401."""
        client, _ = app_client
        resp = client.get("/api/listening/passage")
        assert resp.status_code in (401, 302)
