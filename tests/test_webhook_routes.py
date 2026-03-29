"""Tests for webhook routes (mandarin.web.webhook_routes).

Covers:
- GET /api/webhooks/health — health check returns JSON with config status
- POST /api/webhooks/sentry — missing header returns 400
- POST /api/webhooks/uptime — missing monitorID returns 400
"""

import json
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    """Return a context manager class whose __enter__ yields *conn*."""

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
def webhook_client(test_db):
    """Flask test client for webhook endpoints."""
    conn, _ = test_db

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.webhook_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


# ---------------------------------------------------------------------------
# GET /api/webhooks/health
# ---------------------------------------------------------------------------

class TestWebhookHealth:

    def test_health_returns_200(self, webhook_client):
        c, _ = webhook_client
        resp = c.get("/api/webhooks/health")
        assert resp.status_code == 200

    def test_health_returns_json_with_status(self, webhook_client):
        c, _ = webhook_client
        resp = c.get("/api/webhooks/health")
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert "sentry_configured" in data
        assert "uptime_configured" in data


# ---------------------------------------------------------------------------
# POST /api/webhooks/sentry
# ---------------------------------------------------------------------------

class TestSentryWebhook:

    def test_missing_header_returns_400(self, webhook_client):
        c, _ = webhook_client
        resp = c.post(
            "/api/webhooks/sentry",
            data=json.dumps({"action": "created"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_non_issue_resource_returns_ignored(self, webhook_client):
        c, _ = webhook_client
        resp = c.post(
            "/api/webhooks/sentry",
            data=json.dumps({"action": "created"}),
            content_type="application/json",
            headers={
                "Sentry-Hook-Resource": "installation",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ignored"


# ---------------------------------------------------------------------------
# POST /api/webhooks/uptime
# ---------------------------------------------------------------------------

class TestUptimeWebhook:

    def test_missing_monitor_id_returns_400(self, webhook_client):
        c, _ = webhook_client
        resp = c.post(
            "/api/webhooks/uptime",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_recovery_alert_returns_noted(self, webhook_client):
        c, _ = webhook_client
        resp = c.post(
            "/api/webhooks/uptime",
            data=json.dumps({
                "monitorID": "123",
                "monitorFriendlyName": "TestMonitor",
                "alertType": 2,
            }),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "noted"
