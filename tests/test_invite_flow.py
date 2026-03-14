"""Tests for the invite code beta registration flow.

Covers:
- Registration with valid invite code succeeds
- Registration with invalid/expired/used-up code fails
- Registration without code fails when feature flag is on
- Registration without code succeeds when feature flag is off
- Admin can create and list invite codes
- robots.txt and sitemap.xml routes
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash as _orig_gen

from mandarin.auth import create_user
from mandarin import db


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
# Helpers
# ---------------------------------------------------------------------------

TEST_PASSWORD = "securepass1234545"


def _insert_invite_code(conn, code="BETA2026", max_uses=1, expires_at=None):
    """Insert a test invite code."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT INTO invite_code (code, created_at, max_uses, use_count, expires_at)
           VALUES (?, ?, ?, 0, ?)""",
        (code, now, max_uses, expires_at),
    )
    conn.commit()


def _enable_invite_flag(conn, enabled=True):
    """Set the require_invite_code feature flag."""
    conn.execute(
        """INSERT OR REPLACE INTO feature_flag (name, enabled, updated_at)
           VALUES ('require_invite_code', ?, datetime('now'))""",
        (1 if enabled else 0,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Flask test client fixture
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    """Return a context manager class whose __enter__ yields *conn*."""

    class _FakeConnection:
        def __enter__(self):
            return conn

        def __exit__(self, *args):
            return False

    return _FakeConnection


@pytest.fixture
def app_client(test_db):
    """Create a Flask test client wired to the test database."""
    conn, _ = test_db

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.routes.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn):
        with app.test_client() as client:
            yield client, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as an admin user (is_admin=1, totp_enabled=1)."""
    conn, _ = test_db

    # Promote the bootstrap user (id=1) to admin with TOTP enabled
    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.routes.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            # Inject admin session directly (bypasses MFA challenge)
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True

            yield c, conn


# ---------------------------------------------------------------------------
# Direct auth module tests (no Flask)
# ---------------------------------------------------------------------------

class TestInviteCodeAuth:
    """Tests for invite code validation in mandarin.auth.create_user."""

    def test_valid_invite_code_succeeds(self, test_db):
        conn, _ = test_db
        _insert_invite_code(conn, "GOOD123", max_uses=5)
        user = create_user(conn, "a@b.com", TEST_PASSWORD, "Test", invite_code="GOOD123")
        assert user["id"] > 0
        # Check use_count incremented
        row = conn.execute("SELECT use_count FROM invite_code WHERE code = 'GOOD123'").fetchone()
        assert row["use_count"] == 1

    def test_invalid_code_raises(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="Invalid invite code"):
            create_user(conn, "a@b.com", TEST_PASSWORD, "Test", invite_code="DOESNOTEXIST")

    def test_expired_code_raises(self, test_db):
        conn, _ = test_db
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_invite_code(conn, "EXPIRED1", max_uses=5, expires_at=past)
        with pytest.raises(ValueError, match="expired"):
            create_user(conn, "a@b.com", TEST_PASSWORD, "Test", invite_code="EXPIRED1")

    def test_used_up_code_raises(self, test_db):
        conn, _ = test_db
        _insert_invite_code(conn, "ONCE1", max_uses=1)
        # Use it once
        create_user(conn, "first@b.com", TEST_PASSWORD, "First", invite_code="ONCE1")
        # Second use should fail
        with pytest.raises(ValueError, match="usage limit"):
            create_user(conn, "second@b.com", TEST_PASSWORD, "Second", invite_code="ONCE1")

    def test_multi_use_code_allows_multiple(self, test_db):
        conn, _ = test_db
        _insert_invite_code(conn, "MULTI3", max_uses=3)
        for i in range(3):
            create_user(conn, f"user{i}@b.com", TEST_PASSWORD, f"User{i}", invite_code="MULTI3")
        # Fourth should fail
        with pytest.raises(ValueError, match="usage limit"):
            create_user(conn, "user3@b.com", TEST_PASSWORD, "User3", invite_code="MULTI3")

    def test_flag_on_requires_code(self, test_db):
        conn, _ = test_db
        _enable_invite_flag(conn, enabled=True)
        with pytest.raises(ValueError, match="invite code is required"):
            create_user(conn, "a@b.com", TEST_PASSWORD, "Test")

    def test_flag_off_allows_no_code(self, test_db):
        conn, _ = test_db
        _enable_invite_flag(conn, enabled=False)
        user = create_user(conn, "a@b.com", TEST_PASSWORD, "Test")
        assert user["id"] > 0

    def test_no_flag_row_allows_registration(self, test_db):
        """If the feature_flag row doesn't exist, registration is open."""
        conn, _ = test_db
        # Ensure no flag row
        conn.execute("DELETE FROM feature_flag WHERE name = 'require_invite_code'")
        conn.commit()
        user = create_user(conn, "a@b.com", TEST_PASSWORD, "Test")
        assert user["id"] > 0

    def test_flag_on_with_valid_code_succeeds(self, test_db):
        conn, _ = test_db
        _enable_invite_flag(conn, enabled=True)
        _insert_invite_code(conn, "BETA1", max_uses=10)
        user = create_user(conn, "a@b.com", TEST_PASSWORD, "Test", invite_code="BETA1")
        assert user["id"] > 0

    def test_future_expiry_code_works(self, test_db):
        conn, _ = test_db
        future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_invite_code(conn, "FUTURE1", max_uses=5, expires_at=future)
        user = create_user(conn, "a@b.com", TEST_PASSWORD, "Test", invite_code="FUTURE1")
        assert user["id"] > 0

    def test_user_invited_by_recorded(self, test_db):
        conn, _ = test_db
        _insert_invite_code(conn, "TRACK1", max_uses=5)
        user = create_user(conn, "a@b.com", TEST_PASSWORD, "Test", invite_code="TRACK1")
        row = conn.execute("SELECT invited_by FROM user WHERE id = ?", (user["id"],)).fetchone()
        assert row["invited_by"] == "TRACK1"


# ---------------------------------------------------------------------------
# Admin API tests (via Flask test client)
# ---------------------------------------------------------------------------

class TestAdminInviteCodes:

    def test_create_invite_code(self, admin_client):
        client, conn = admin_client
        resp = client.post("/api/admin/invite-codes",
                           json={"code": "NEWCODE", "max_uses": 5, "label": "test batch"},
                           content_type="application/json",
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["code"] == "NEWCODE"
        assert data["max_uses"] == 5
        assert data["uses_remaining"] == 5

    def test_list_invite_codes(self, admin_client):
        client, conn = admin_client
        _insert_invite_code(conn, "LIST1", max_uses=3)
        _insert_invite_code(conn, "LIST2", max_uses=1)
        resp = client.get("/api/admin/invite-codes")
        assert resp.status_code == 200
        data = resp.get_json()
        codes = {c["code"] for c in data["invite_codes"]}
        assert "LIST1" in codes
        assert "LIST2" in codes


# ---------------------------------------------------------------------------
# robots.txt and sitemap.xml route tests
# ---------------------------------------------------------------------------

class TestSEORoutes:

    def test_robots_txt(self, app_client):
        client, _ = app_client
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/plain")
        text = resp.data.decode()
        assert "User-agent: *" in text
        assert "Disallow: /api/" in text
        assert "Disallow: /admin/" in text
        assert "Sitemap:" in text
        assert "sitemap.xml" in text

    def test_sitemap_xml(self, app_client):
        client, _ = app_client
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert "xml" in resp.content_type
        text = resp.data.decode()
        assert '<?xml version="1.0"' in text
        assert "<urlset" in text
        assert "<loc>" in text
        # Check key pages are present
        assert "/pricing" in text
        assert "/about" in text
        assert "/learn/tone-pairs/" in text
        assert "/learn/hsk-1/" in text
        assert "/privacy" in text

    def test_sitemap_has_correct_structure(self, app_client):
        client, _ = app_client
        resp = client.get("/sitemap.xml")
        text = resp.data.decode()
        # Every <url> should have <loc>, <lastmod>, <changefreq>, <priority>
        assert text.count("<url>") == text.count("</url>")
        assert text.count("<loc>") == text.count("</loc>")
        assert text.count("<lastmod>") == text.count("</lastmod>")
        assert text.count("<changefreq>") == text.count("</changefreq>")
        assert text.count("<priority>") == text.count("</priority>")
        # Should have a good number of pages
        assert text.count("<url>") >= 30  # 17 base + 20 tone pairs + 6 HSK
