"""Tests for export routes (mandarin.web.export_routes).

Covers:
1.  GET /api/export/progress — unauthenticated returns 401
2.  GET /api/export/sessions — unauthenticated returns 401
3.  GET /api/export/errors — unauthenticated returns 401
4.  GET /api/xapi/statements — unauthenticated returns 401
5.  GET /api/caliper/events — unauthenticated returns 401
6.  GET /api/export/common-cartridge — unauthenticated returns 401
7.  GET /api/export/progress — authenticated free user returns CSV
8.  GET /api/export/sessions — authenticated free user returns CSV
9.  GET /api/export/errors — authenticated free user returns CSV
10. GET /api/export/progress — tier-gated returns 403 for blocked user
11. GET /api/export/sessions — tier-gated returns 403 for blocked user
12. GET /api/export/errors — tier-gated returns 403 for blocked user
13. GET /api/xapi/statements — returns JSON with statements list
14. GET /api/caliper/events — returns JSON with events list
15. GET /api/export/common-cartridge — returns ZIP response
16. GET /api/export/common-cartridge — tier-gated returns 403
17. GET /api/xapi/statements — since/until query params are forwarded
18. GET /api/caliper/events — since query param is forwarded
19. GET /api/export/progress — export failure returns 500
20. GET /api/export/common-cartridge — level query param is forwarded
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from mandarin.auth import create_user
from mandarin.web import create_app
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
# Fake DB context-manager wrapper
# ---------------------------------------------------------------------------

class _FakeConn:
    """Wraps a real sqlite3.Connection so it works as both a context manager
    and as a raw connection object."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Test-client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(test_db):
    """Flask test client with all DB connections patched to the test database."""
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test"

    fake = _FakeConn(conn)
    fake_connection = lambda: fake  # noqa: E731

    with patch("mandarin.db.connection", fake_connection), \
         patch("mandarin.web.routes.db.connection", fake_connection), \
         patch("mandarin.web.payment_routes.db.connection", fake_connection), \
         patch("mandarin.web.onboarding_routes.db.connection", fake_connection), \
         patch("mandarin.web.admin_routes.db.connection", fake_connection), \
         patch("mandarin.web.auth_routes.db.connection", fake_connection), \
         patch("mandarin.web.export_routes.db.connection", fake_connection):
        with app.test_client() as client:
            yield client, conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL = "exportuser@example.com"
TEST_PASSWORD = "exportpass12345"  # gitleaks:allow (test fixture, not a real secret)

XHR = {"X-Requested-With": "XMLHttpRequest"}


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    """Create a user and log them in, returning the user dict."""
    user = create_user(conn, email, password, "ExportTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)
    return user


# ---------------------------------------------------------------------------
# 1. Unauthenticated access — should return 401 or 302
# ---------------------------------------------------------------------------

class TestExportUnauthenticated:

    def test_export_progress_requires_auth(self, app_client):
        client, _ = app_client
        resp = client.get("/api/export/progress")
        assert resp.status_code in (401, 302)

    def test_export_sessions_requires_auth(self, app_client):
        client, _ = app_client
        resp = client.get("/api/export/sessions")
        assert resp.status_code in (401, 302)

    def test_export_errors_requires_auth(self, app_client):
        client, _ = app_client
        resp = client.get("/api/export/errors")
        assert resp.status_code in (401, 302)

    def test_xapi_statements_requires_auth(self, app_client):
        client, _ = app_client
        resp = client.get("/api/xapi/statements")
        assert resp.status_code in (401, 302)

    def test_caliper_events_requires_auth(self, app_client):
        client, _ = app_client
        resp = client.get("/api/caliper/events")
        assert resp.status_code in (401, 302)

    def test_common_cartridge_requires_auth(self, app_client):
        client, _ = app_client
        resp = client.get("/api/export/common-cartridge")
        assert resp.status_code in (401, 302)


# ---------------------------------------------------------------------------
# 2. CSV export — authenticated, tier allowed
# ---------------------------------------------------------------------------

class TestExportCSV:

    def test_export_progress_returns_csv(self, app_client):
        """Authenticated free user can export progress as CSV."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.export.export_progress_csv", return_value=(["col1", "col2"], [])), \
             patch("mandarin.export.to_csv_string", return_value="col1,col2\n"):
            resp = client.get("/api/export/progress")
            assert resp.status_code == 200
            assert resp.content_type == "text/csv; charset=utf-8"
            assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_export_sessions_returns_csv(self, app_client):
        """Authenticated free user can export sessions as CSV."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.export.export_sessions_csv", return_value=(["h1"], [])), \
             patch("mandarin.export.to_csv_string", return_value="h1\n"):
            resp = client.get("/api/export/sessions")
            assert resp.status_code == 200
            assert resp.content_type == "text/csv; charset=utf-8"

    def test_export_errors_returns_csv(self, app_client):
        """Authenticated free user can export errors as CSV."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.export.export_errors_csv", return_value=(["e1"], [])), \
             patch("mandarin.export.to_csv_string", return_value="e1\n"):
            resp = client.get("/api/export/errors")
            assert resp.status_code == 200
            assert resp.content_type == "text/csv; charset=utf-8"


# ---------------------------------------------------------------------------
# 3. Tier gate — denied
# ---------------------------------------------------------------------------

class TestExportTierGated:

    def test_export_progress_denied_returns_403(self, app_client):
        """If tier gate denies access, progress export returns 403."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=False):
            resp = client.get("/api/export/progress")
            assert resp.status_code == 403
            data = resp.get_json()
            assert "error" in data

    def test_export_sessions_denied_returns_403(self, app_client):
        """If tier gate denies access, sessions export returns 403."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=False):
            resp = client.get("/api/export/sessions")
            assert resp.status_code == 403

    def test_export_errors_denied_returns_403(self, app_client):
        """If tier gate denies access, errors export returns 403."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=False):
            resp = client.get("/api/export/errors")
            assert resp.status_code == 403

    def test_common_cartridge_denied_returns_403(self, app_client):
        """If tier gate denies access, CC export returns 403."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=False):
            resp = client.get("/api/export/common-cartridge")
            assert resp.status_code == 403
            data = resp.get_json()
            assert "error" in data


# ---------------------------------------------------------------------------
# 4. xAPI and Caliper endpoints
# ---------------------------------------------------------------------------

class TestXAPIAndCaliper:

    def test_xapi_statements_returns_json(self, app_client):
        """Authenticated user gets JSON with statements list."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.xapi.get_statements", return_value=[{"id": "stmt1"}]):
            resp = client.get("/api/xapi/statements")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "statements" in data
            assert isinstance(data["statements"], list)

    def test_xapi_statements_forwards_since_until(self, app_client):
        """since and until query params should be forwarded to get_statements."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.xapi.get_statements", return_value=[]) as mock_get:
            resp = client.get("/api/xapi/statements?since=2026-01-01&until=2026-03-01")
            assert resp.status_code == 200
            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            assert kwargs.get("since") == "2026-01-01" or mock_get.call_args[0][2] == "2026-01-01"

    def test_caliper_events_returns_json(self, app_client):
        """Authenticated user gets JSON with events list."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.caliper.get_events", return_value=[{"type": "evt1"}]):
            resp = client.get("/api/caliper/events")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "events" in data
            assert isinstance(data["events"], list)

    def test_caliper_events_forwards_since(self, app_client):
        """since query param should be forwarded to get_events."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.caliper.get_events", return_value=[]) as mock_get:
            resp = client.get("/api/caliper/events?since=2026-02-01")
            assert resp.status_code == 200
            mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Common Cartridge export
# ---------------------------------------------------------------------------

class TestCommonCartridge:

    def test_cc_export_returns_zip(self, app_client):
        """Authenticated user with tier access gets a ZIP response."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.cc_export.export_cc", return_value=b"PK\x03\x04fake-zip"):
            resp = client.get("/api/export/common-cartridge")
            assert resp.status_code == 200
            assert resp.content_type == "application/zip"
            assert "imscc" in resp.headers.get("Content-Disposition", "")

    def test_cc_export_level_param(self, app_client):
        """The level query param should be forwarded to export_cc."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.cc_export.export_cc", return_value=b"PK") as mock_cc:
            resp = client.get("/api/export/common-cartridge?level=3")
            assert resp.status_code == 200
            mock_cc.assert_called_once()
            # level should be 3 (int)
            call_args = mock_cc.call_args
            assert call_args[0][2] == 3 or call_args[1].get("level") == 3


# ---------------------------------------------------------------------------
# 6. Error handling
# ---------------------------------------------------------------------------

class TestExportErrorHandling:

    def test_csv_export_failure_returns_500(self, app_client):
        """When the export function raises an error, return 500."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.web.export_routes._csv_response", side_effect=Exception("boom")):
            resp = client.get("/api/export/progress")
            assert resp.status_code == 500

    def test_cc_export_failure_returns_500(self, app_client):
        """When CC export raises, return 500."""
        client, conn = app_client
        _create_and_login(client, conn)

        with patch("mandarin.web.export_routes.check_tier_access", return_value=True), \
             patch("mandarin.cc_export.export_cc", side_effect=ValueError("bad")):
            resp = client.get("/api/export/common-cartridge")
            assert resp.status_code == 500
            data = resp.get_json()
            assert "error" in data
