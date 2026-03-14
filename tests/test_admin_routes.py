"""Tests for admin dashboard routes (mandarin.web.admin_routes).

Covers:
- Non-admin and unauthenticated users get 403/401/302 on admin routes
- Admin user gets 200 + correct JSON shape on all API endpoints
- Pagination params (page, per_page)
- user_id filter param
- /admin/ dashboard page access control
"""

import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web.auth_routes import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_admin_row(is_admin=1, totp_enabled=1):
    """Return a sqlite3.Row-like dict for the admin_required permission check."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {"is_admin": is_admin, "totp_enabled": totp_enabled}[key]
    row.__bool__ = lambda self: True
    return row


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
def client(test_db):
    """Flask test client with DB patched to the test database."""
    conn, _ = test_db

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as an admin user (is_admin=1, totp_enabled=1)."""
    conn, _ = test_db

    # Promote the bootstrap user (id=1) to admin with TOTP enabled and active.
    # is_active=1 is required so load_user can find the user from the session.
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
         patch("mandarin.web.admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            # Log in by pushing an authenticated user into the session via
            # Flask-Login's test request context.
            with app.test_request_context():
                from flask_login import login_user
                user_dict = {
                    "id": 1,
                    "email": "local@localhost",
                    "display_name": "Local",
                    "subscription_tier": "admin",
                    "is_admin": True,
                }
                login_user(User(user_dict))

            # Force session cookie: POST to login endpoint is simpler and
            # more robust than manipulating the session directly.
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True

            yield c, conn


@pytest.fixture
def nonadmin_client(test_db):
    """Flask test client logged in as a regular (non-admin) user."""
    conn, _ = test_db

    # Set is_active=1 so load_user can find the user; leave is_admin=0.
    conn.execute("UPDATE user SET is_active = 1, is_admin = 0 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            # Bootstrap user (id=1) is active but not admin.
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True

            yield c, conn


# ---------------------------------------------------------------------------
# Access control — unauthenticated
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    """Unauthenticated requests are redirected to login (302) or get 401."""

    def test_admin_dashboard_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.get("/admin/", follow_redirects=False)
        assert resp.status_code in (302, 401), (
            f"Expected redirect/401, got {resp.status_code}"
        )

    def test_api_metrics_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.get("/api/admin/metrics", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_api_users_unauthenticated_redirects(self, client):
        c, _ = client
        resp = c.get("/api/admin/users", follow_redirects=False)
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Access control — non-admin authenticated user
# ---------------------------------------------------------------------------

class TestNonAdminAccess:
    """Logged-in users without is_admin=1 must receive 403."""

    def test_admin_dashboard_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/admin/", follow_redirects=False)
        assert resp.status_code == 403

    def test_api_metrics_non_admin_gets_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/metrics", follow_redirects=False)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin user — successful access
# ---------------------------------------------------------------------------

class TestAdminMetrics:

    def test_metrics_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/metrics")
        assert resp.status_code == 200

    def test_metrics_returns_json(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/metrics")
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_metrics_has_expected_keys(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/metrics")
        data = json.loads(resp.data)
        for key in ("total_signups", "active_users_7d", "sessions_7d", "tier_distribution"):
            assert key in data, f"Missing key: {key}"

    def test_metrics_total_signups_is_int(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/metrics")
        data = json.loads(resp.data)
        assert isinstance(data["total_signups"], int)
        assert data["total_signups"] >= 1  # bootstrap user always present

    def test_metrics_tier_distribution_is_dict(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/metrics")
        data = json.loads(resp.data)
        assert isinstance(data["tier_distribution"], dict)


class TestAdminUsers:

    def test_users_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/users")
        assert resp.status_code == 200

    def test_users_response_has_users_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/users")
        data = json.loads(resp.data)
        assert "users" in data
        assert isinstance(data["users"], list)

    def test_users_contains_bootstrap_user(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/users")
        data = json.loads(resp.data)
        ids = [u["id"] for u in data["users"]]
        assert 1 in ids

    def test_user_entries_have_expected_fields(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/users")
        data = json.loads(resp.data)
        if data["users"]:
            entry = data["users"][0]
            for field in ("id", "email", "display_name", "tier", "created_at"):
                assert field in entry, f"User entry missing field: {field}"


class TestAdminFeedback:

    def test_feedback_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/feedback")
        assert resp.status_code == 200

    def test_feedback_has_feedback_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/feedback")
        data = json.loads(resp.data)
        assert "feedback" in data
        assert isinstance(data["feedback"], list)


class TestAdminCrashes:

    def test_crashes_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/crashes")
        assert resp.status_code == 200

    def test_crashes_has_crashes_key(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/crashes")
        data = json.loads(resp.data)
        assert "crashes" in data
        assert isinstance(data["crashes"], list)

    def test_crashes_has_pagination_keys(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/crashes")
        data = json.loads(resp.data)
        assert "page" in data
        assert "per_page" in data


class TestAdminClientErrors:

    def test_client_errors_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/client-errors")
        assert resp.status_code == 200

    def test_client_errors_has_errors_key(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/client-errors")
        data = json.loads(resp.data)
        assert "errors" in data
        assert isinstance(data["errors"], list)


class TestAdminSessions:

    def test_sessions_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/sessions")
        assert resp.status_code == 200

    def test_sessions_has_sessions_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/sessions")
        data = json.loads(resp.data)
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_sessions_has_pagination_keys(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/sessions")
        data = json.loads(resp.data)
        assert "page" in data
        assert "per_page" in data


class TestAdminSecurityEvents:

    def test_security_events_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/security-events")
        assert resp.status_code == 200

    def test_security_events_has_events_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/security-events")
        data = json.loads(resp.data)
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_security_events_has_pagination_keys(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/security-events")
        data = json.loads(resp.data)
        assert "page" in data
        assert "per_page" in data


class TestAdminErrorPatterns:

    def test_error_patterns_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/error-patterns")
        assert resp.status_code == 200

    def test_error_patterns_has_patterns_list(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/error-patterns")
        data = json.loads(resp.data)
        assert "patterns" in data
        assert isinstance(data["patterns"], list)


# ---------------------------------------------------------------------------
# Pagination params
# ---------------------------------------------------------------------------

class TestPagination:

    def test_crashes_pagination_params_respected(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/crashes?page=2&per_page=10")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["page"] == 2
        assert data["per_page"] == 10

    def test_sessions_pagination_defaults(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/sessions")
        data = json.loads(resp.data)
        assert data["page"] == 1
        assert data["per_page"] == 50  # default in paginate_params

    def test_per_page_capped_at_100(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/client-errors?per_page=9999")
        data = json.loads(resp.data)
        assert data["per_page"] == 100

    def test_page_minimum_is_1(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/sessions?page=-5")
        data = json.loads(resp.data)
        assert data["page"] == 1


# ---------------------------------------------------------------------------
# user_id filter param
# ---------------------------------------------------------------------------

class TestUserIdFilter:

    def test_crashes_user_id_filter_accepted(self, admin_client):
        """Passing user_id=1 should not cause an error even if no rows match."""
        c, _ = admin_client
        resp = c.get("/api/admin/crashes?user_id=1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "crashes" in data

    def test_sessions_user_id_filter_accepted(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/sessions?user_id=1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "sessions" in data

    def test_security_events_user_id_filter_accepted(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/security-events?user_id=1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "events" in data

    def test_error_patterns_user_id_filter_accepted(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/error-patterns?user_id=1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "patterns" in data
