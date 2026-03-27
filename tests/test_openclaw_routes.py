"""Tests for OpenClaw n8n integration routes (mandarin.web.openclaw_routes).

Covers:
- Health endpoint (no auth required)
- API-key-protected endpoints return 401 without valid key
- API-key-protected endpoints return expected responses with valid key
- WhatsApp webhook verify returns 403 without valid token
"""

import json
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    class _FakeConnection:
        def __enter__(self):
            return conn

        def __exit__(self, *args):
            return False

    return _FakeConnection


TEST_API_KEY = "test-openclaw-key-12345"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(test_db):
    """Flask test client with DB patched and OpenClaw API key set."""
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.openclaw_routes._get_api_key", return_value=TEST_API_KEY):
        with app.test_client() as c:
            yield c, conn


# ---------------------------------------------------------------------------
# Health endpoint (no auth)
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_health_returns_200(self, client):
        c, _ = client
        resp = c.get("/api/openclaw/health")
        assert resp.status_code == 200

    def test_health_returns_json_with_status(self, client):
        c, _ = client
        resp = c.get("/api/openclaw/health")
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert "api_key_configured" in data
        assert "telegram_configured" in data


# ---------------------------------------------------------------------------
# API key enforcement
# ---------------------------------------------------------------------------

class TestApiKeyEnforcement:

    def test_review_queue_without_key_returns_401(self, client):
        c, _ = client
        resp = c.get("/api/openclaw/review-queue")
        assert resp.status_code == 401

    def test_status_without_key_returns_401(self, client):
        c, _ = client
        resp = c.get("/api/openclaw/status")
        assert resp.status_code == 401

    def test_audit_without_key_returns_401(self, client):
        c, _ = client
        resp = c.get("/api/openclaw/audit")
        assert resp.status_code == 401

    def test_errors_without_key_returns_401(self, client):
        c, _ = client
        resp = c.get("/api/openclaw/errors")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        c, _ = client
        resp = c.get(
            "/api/openclaw/review-queue",
            headers={"X-OpenClaw-Key": "wrong-key"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Authenticated access (with valid API key)
# ---------------------------------------------------------------------------

class TestAuthenticatedAccess:

    def test_review_queue_with_key(self, client):
        c, _ = client
        with patch("mandarin.web.openclaw_routes.commands") as mock_cmds:
            mock_cmds.cmd_review.return_value = "No items"
            mock_cmds.cmd_review_items.return_value = []
            resp = c.get(
                "/api/openclaw/review-queue",
                headers={"X-OpenClaw-Key": TEST_API_KEY},
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "summary" in data
            assert "items" in data

    def test_status_with_key(self, client):
        c, _ = client
        with patch("mandarin.web.openclaw_routes.commands") as mock_cmds:
            mock_cmds.cmd_status.return_value = "All good"
            resp = c.get(
                "/api/openclaw/status",
                headers={"X-OpenClaw-Key": TEST_API_KEY},
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "status" in data

    def test_audit_with_key(self, client):
        c, _ = client
        with patch("mandarin.web.openclaw_routes.commands") as mock_cmds:
            mock_cmds.cmd_audit.return_value = "Audit OK"
            resp = c.get(
                "/api/openclaw/audit",
                headers={"X-OpenClaw-Key": TEST_API_KEY},
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "audit" in data


# ---------------------------------------------------------------------------
# Notify endpoint
# ---------------------------------------------------------------------------

class TestNotifyEndpoint:

    def test_notify_without_key_returns_401(self, client):
        c, _ = client
        resp = c.post(
            "/api/openclaw/notify",
            json={"message": "hello"},
        )
        assert resp.status_code == 401

    def test_notify_missing_message_returns_400(self, client):
        c, _ = client
        resp = c.post(
            "/api/openclaw/notify",
            json={},
            headers={"X-OpenClaw-Key": TEST_API_KEY},
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data


# ---------------------------------------------------------------------------
# WhatsApp webhook verification
# ---------------------------------------------------------------------------

class TestWhatsAppWebhook:

    def test_whatsapp_verify_without_valid_token_returns_403(self, client):
        c, _ = client
        with patch("mandarin.web.openclaw_routes.whatsapp_bot") as mock_wa:
            mock_wa.verify_webhook.return_value = None
            resp = c.get("/api/openclaw/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=bad&hub.challenge=test")
            assert resp.status_code == 403

    def test_whatsapp_post_webhook_returns_200(self, client):
        c, _ = client
        with patch("mandarin.web.openclaw_routes.whatsapp_bot") as mock_wa:
            mock_wa.handle_webhook.return_value = None
            resp = c.post(
                "/api/openclaw/webhook/whatsapp",
                json={"object": "whatsapp_business_account", "entry": []},
            )
            assert resp.status_code == 200
