"""Tests for vibe admin routes (mandarin.web.vibe_admin_routes).

Covers:
- Unauthenticated requests get redirected (302) or 401
- Non-admin users get 403
- Admin user can access tonal vibe, visual vibe, marketing, feature, engineering endpoints
- POST endpoints for logging audits and events
"""

import json
from unittest.mock import patch

import pytest

from mandarin.web.auth_routes import User


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
         patch("mandarin.web.vibe_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as an admin user (is_admin=1, totp_enabled=1)."""
    conn, _ = test_db

    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.vibe_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


@pytest.fixture
def nonadmin_client(test_db):
    """Flask test client logged in as a non-admin user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1, is_admin = 0 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn), \
         patch("mandarin.web.vibe_admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:

    def test_tonal_vibe_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/intelligence/vibe/tonal")
        assert resp.status_code in (302, 401)

    def test_visual_vibe_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/intelligence/vibe/visual")
        assert resp.status_code in (302, 401)

    def test_marketing_pages_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/marketing/pages")
        assert resp.status_code in (302, 401)

    def test_feature_usage_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/features/usage")
        assert resp.status_code in (302, 401)

    def test_engineering_health_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/api/admin/engineering/health")
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Non-admin access
# ---------------------------------------------------------------------------

class TestNonAdminAccess:

    def test_tonal_vibe_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/intelligence/vibe/tonal")
        assert resp.status_code == 403

    def test_marketing_pages_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/marketing/pages")
        assert resp.status_code == 403

    def test_feature_usage_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/features/usage")
        assert resp.status_code == 403

    def test_engineering_health_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/engineering/health")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin — tonal vibe
# ---------------------------------------------------------------------------

class TestTonalVibe:

    def test_tonal_vibe_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/intelligence/vibe/tonal")
        assert resp.status_code == 200

    def test_tonal_vibe_response_shape(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/intelligence/vibe/tonal")
        data = json.loads(resp.data)
        assert "flagged_strings" in data
        assert "unaudited_count" in data
        assert "recent_audits" in data


# ---------------------------------------------------------------------------
# Admin — visual vibe
# ---------------------------------------------------------------------------

class TestVisualVibe:

    def test_visual_vibe_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/intelligence/vibe/visual")
        assert resp.status_code == 200

    def test_visual_vibe_has_schedule(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/intelligence/vibe/visual")
        data = json.loads(resp.data)
        assert "schedule" in data
        assert isinstance(data["schedule"], list)


# ---------------------------------------------------------------------------
# Admin — log vibe audit
# ---------------------------------------------------------------------------

class TestLogVibeAudit:

    def test_log_audit_missing_category_returns_400(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/intelligence/vibe/audit",
            json={"audit_type": "visual"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_log_audit_success(self, admin_client):
        c, _ = admin_client
        resp = c.post(
            "/api/admin/intelligence/vibe/audit",
            json={
                "audit_type": "visual",
                "audit_category": "color_tokens",
                "overall_pass": True,
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "logged"
        assert "id" in data


# ---------------------------------------------------------------------------
# Admin — marketing pages
# ---------------------------------------------------------------------------

class TestMarketingPages:

    def test_marketing_pages_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/marketing/pages")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "pages" in data

    def test_funnel_metrics_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/marketing/funnel")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "latest_snapshot" in data
        assert "event_counts_30d" in data

    def test_strategy_checklist_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/marketing/strategy")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "checklist" in data


# ---------------------------------------------------------------------------
# Admin — feature usage
# ---------------------------------------------------------------------------

class TestFeatureUsage:

    def test_feature_usage_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/features/usage")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "features" in data


# ---------------------------------------------------------------------------
# Admin — engineering health
# ---------------------------------------------------------------------------

class TestEngineeringHealth:

    def test_engineering_health_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/engineering/health")
        assert resp.status_code == 200

    def test_engineering_health_response_shape(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/engineering/health")
        data = json.loads(resp.data)
        assert "latest" in data
        assert "history" in data
