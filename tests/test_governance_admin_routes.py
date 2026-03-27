"""Tests for governance admin routes — registry, incidents, policies, data requests, learner transparency.

Admin endpoints require admin + MFA. Learner endpoints require login only.
"""

import json
from unittest.mock import patch

import pytest

from mandarin.web import create_app
from mandarin.web.auth_routes import User
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
    """Unauthenticated Flask test client."""
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as admin with TOTP enabled."""
    conn, _ = test_db

    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.commit()

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


@pytest.fixture
def nonadmin_client(test_db):
    """Flask test client logged in as a regular (non-admin) user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1, is_admin = 0 WHERE id = 1")
    conn.commit()

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


@pytest.fixture
def logged_in_client(test_db):
    """Flask test client logged in as a regular active user (for learner endpoints)."""
    conn, _ = test_db

    create_user(conn, "learner@test.com", "testpass123456", "Learner")
    conn.commit()

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            c.post("/auth/login", data={
                "email": "learner@test.com",
                "password": "testpass123456",
            }, follow_redirects=True)
            yield c, conn


# ---------------------------------------------------------------------------
# Access control — unauthenticated
# ---------------------------------------------------------------------------

class TestGovernanceUnauthenticated:

    def test_registry_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/admin/governance/registry")
        assert resp.status_code in (302, 401)

    def test_incidents_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/admin/governance/incidents")
        assert resp.status_code in (302, 401)

    def test_policies_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/admin/governance/policies")
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Access control — non-admin
# ---------------------------------------------------------------------------

class TestGovernanceNonAdmin:

    def test_registry_nonadmin_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/governance/registry")
        assert resp.status_code == 403

    def test_incidents_nonadmin_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/governance/incidents")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin access — Component Registry
# ---------------------------------------------------------------------------

class TestGovernanceRegistry:

    def test_registry_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/registry")
        assert resp.status_code == 200

    def test_registry_has_components_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/registry")
        data = resp.get_json()
        assert "components" in data
        assert isinstance(data["components"], list)


# ---------------------------------------------------------------------------
# Admin access — Incidents
# ---------------------------------------------------------------------------

class TestGovernanceIncidents:

    def test_incidents_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/incidents")
        assert resp.status_code == 200

    def test_incidents_has_incidents_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/incidents")
        data = resp.get_json()
        assert "incidents" in data
        assert isinstance(data["incidents"], list)

    def test_log_incident(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/governance/incidents",
            json={
                "severity": "P2",
                "incident_type": "model_failure",
                "description": "Test incident",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "logged"
        assert "id" in data

    def test_log_incident_invalid_type(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/governance/incidents",
            json={
                "incident_type": "invalid_type_xyz",
                "description": "Bad type",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Admin access — Policies
# ---------------------------------------------------------------------------

class TestGovernancePolicies:

    def test_policies_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/policies")
        assert resp.status_code == 200

    def test_policies_has_policies_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/policies")
        data = resp.get_json()
        assert "policies" in data
        assert isinstance(data["policies"], list)


# ---------------------------------------------------------------------------
# Admin access — Data Subject Requests
# ---------------------------------------------------------------------------

class TestGovernanceDataRequests:

    def test_data_requests_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/data-requests")
        assert resp.status_code == 200

    def test_data_requests_has_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/governance/data-requests")
        data = resp.get_json()
        assert "requests" in data
        assert isinstance(data["requests"], list)

    def test_create_data_request_invalid_type(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/governance/data-requests",
            json={"user_id": 1, "request_type": "invalid_xyz"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_create_data_request_valid(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/governance/data-requests",
            json={"user_id": 1, "request_type": "access"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "created"


# ---------------------------------------------------------------------------
# Learner endpoints — require login only
# ---------------------------------------------------------------------------

class TestLearnerTransparency:

    def test_transparency_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/learner/ai-transparency")
        assert resp.status_code in (302, 401)

    def test_transparency_authenticated(self, logged_in_client):
        c, _ = logged_in_client
        resp = c.get("/api/learner/ai-transparency")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


class TestLearnerExplainItem:

    def test_explain_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/learner/items/1/explain")
        assert resp.status_code in (302, 401)

    def test_explain_authenticated(self, logged_in_client):
        c, _ = logged_in_client
        resp = c.get("/api/learner/items/1/explain")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
