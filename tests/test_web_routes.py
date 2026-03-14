"""Tests for web API routes — health, status, onboarding, subscription, payment."""

import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


# ---------------------------------------------------------------------------
# Python 3.9 compat: force pbkdf2 instead of scrypt
# ---------------------------------------------------------------------------

def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeConn:
    """Context manager that returns the test conn unchanged."""
    def __init__(self, conn):
        self._conn = conn
    def __enter__(self):
        return self._conn
    def __exit__(self, *args):
        return False


@pytest.fixture
def app_client(test_db):
    """Create a Flask test client wired to the test database."""
    conn, _ = test_db

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with patch("mandarin.web.routes.db.connection", return_value=fake):
            with patch("mandarin.web.payment_routes.db.connection", return_value=fake):
                with patch("mandarin.web.onboarding_routes.db.connection", return_value=fake):
                    with patch("mandarin.web.admin_routes.db.connection", return_value=fake):
                        with app.test_client() as client:
                            yield client, conn


def _login(client, conn, email="test@example.com", password="testpass12345"):
    """Create a user and log them in, returning the user dict."""
    user = create_user(conn, email, password, "Test User")
    # Log in via POST to auth route
    client.post("/auth/login", data={
        "email": email,
        "password": password,
    })
    return user


# ---------------------------------------------------------------------------
# Health endpoints (no auth required)
# ---------------------------------------------------------------------------

class TestHealthRoutes:

    def test_health_live_returns_200(self, app_client):
        client, conn = app_client
        resp = client.get("/api/health/live")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"

    def test_health_ready_returns_200(self, app_client):
        client, conn = app_client
        resp = client.get("/api/health/ready")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Subscription status (requires auth)
# ---------------------------------------------------------------------------

class TestSubscriptionStatus:

    def test_unauthenticated_returns_redirect_or_401(self, app_client):
        client, conn = app_client
        resp = client.get("/api/subscription/status")
        # Flask-Login returns 401 or redirect to login
        assert resp.status_code in (401, 302)

    def test_authenticated_returns_tier(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/subscription/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "tier" in data
        assert data["tier"] == "free"

    def test_authenticated_returns_status_fields(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/subscription/status")
        data = json.loads(resp.data)
        assert "status" in data
        assert "has_stripe" in data


# ---------------------------------------------------------------------------
# Onboarding routes (requires auth)
# ---------------------------------------------------------------------------

class TestOnboardingRoutes:

    def test_wizard_unauthenticated(self, app_client):
        client, conn = app_client
        resp = client.get("/api/onboarding/wizard")
        assert resp.status_code in (401, 302)

    def test_wizard_returns_status(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.get("/api/onboarding/wizard")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "complete" in data

    def test_set_level_valid(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/onboarding/level",
                           data=json.dumps({"level": 2}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["level"] == 2

    def test_set_level_invalid(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/onboarding/level",
                           data=json.dumps({"level": 99}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400

    def test_set_goal_valid(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "deep"}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["goal"] == "deep"

    def test_set_goal_invalid(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/onboarding/goal",
                           data=json.dumps({"goal": "extreme"}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400

    def test_complete_onboarding(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/onboarding/complete",
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["complete"] is True


# ---------------------------------------------------------------------------
# Payment routes — checkout requires Stripe, test error paths
# ---------------------------------------------------------------------------

class TestPaymentRoutes:

    def test_checkout_unauthenticated(self, app_client):
        client, conn = app_client
        resp = client.post("/api/checkout",
                           data=json.dumps({"plan": "monthly"}),
                           content_type="application/json")
        assert resp.status_code in (401, 302)

    def test_checkout_invalid_plan(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/checkout",
                           data=json.dumps({"plan": "invalid"}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_billing_portal_no_stripe(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/billing-portal",
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "No active subscription" in data["error"]

    def test_classroom_checkout_invalid_billing(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/api/checkout/classroom",
                           data=json.dumps({"billing": "invalid"}),
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 400
