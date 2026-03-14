"""Tests for onboarding routes — wizard, placement quiz, content seeding."""

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


def _login(client, conn, email="onboard@test.com"):
    create_user(conn, email, "testpass123456", "OnboardTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": "testpass123456",
    }, follow_redirects=True)


class TestOnboardingWizard:

    def test_wizard_unauthenticated(self, app_client):
        """Unauthenticated requests to wizard return 401."""
        client, _ = app_client
        resp = client.get("/api/onboarding/wizard")
        assert resp.status_code in (401, 302)

    def test_wizard_authenticated(self, app_client):
        """Authenticated user can check wizard status."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/onboarding/wizard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


class TestPlacementQuiz:

    def test_placement_unauthenticated(self, app_client):
        """Unauthenticated requests to placement quiz return 401."""
        client, _ = app_client
        resp = client.get("/api/onboarding/placement/start")
        assert resp.status_code in (401, 302)

    def test_placement_authenticated(self, app_client):
        """Authenticated user can get placement quiz."""
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/onboarding/placement/start")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


class TestOnboardingComplete:

    def test_complete_unauthenticated(self, app_client):
        """Unauthenticated requests to complete onboarding return 401."""
        client, _ = app_client
        resp = client.post("/api/onboarding/complete",
                           data=json.dumps({"level": 1}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code in (401, 302)
