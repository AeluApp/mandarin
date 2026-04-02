"""Tests for GDPR compliance routes and data retention.

Covers:
1.  export_data has try/except error handling (source inspection)
2.  request_deletion has try/except error handling (source inspection)
3.  export_data regex guard exists on auto-discovered table SELECT
4.  request_deletion regex guard exists on DELETE path
5.  data_retention purge_expired with mock retention policies purges old rows
6.  data_retention purge_expired skips tables with retention_days = -1
7.  data_retention purge_expired handles missing retention_policy table gracefully
8.  GDPR export response has Content-Disposition header
9.  GDPR delete anonymizes user record (email becomes deleted-N@deleted.local)
10. GDPR delete creates data_deletion_request record
"""
# phantom-schema-checked

from __future__ import annotations

import inspect
import re
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from mandarin.data_retention import purge_expired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from tests.shared_db import make_test_db


class _NullPath:
    """Placeholder for in-memory DBs so callers can still call path.unlink()."""
    def unlink(self, missing_ok=False):
        pass


def _make_db():
    """Create a fresh test database using the shared factory."""
    conn = make_test_db()
    return conn, _NullPath()


# ---------------------------------------------------------------------------
# Source-inspection tests (1–4): no DB needed
# ---------------------------------------------------------------------------

class TestSourceInspection:
    """Verify security properties by reading the source code directly."""

    def _get_gdpr_source(self):
        import mandarin.web.gdpr_routes as m
        return inspect.getsource(m)

    def _get_export_impl_source(self):
        import mandarin.web.gdpr_routes as m
        return inspect.getsource(m._export_data_impl)

    def _get_deletion_impl_source(self):
        import mandarin.web.gdpr_routes as m
        return inspect.getsource(m._request_deletion_impl)

    # 1. export_data has try/except error handling
    def test_export_data_has_try_except(self):
        import mandarin.web.gdpr_routes as m
        source = inspect.getsource(m.export_data)
        assert "try:" in source, "export_data must contain a try block"
        assert "except" in source, "export_data must contain an except clause"

    # 2. request_deletion has try/except error handling
    def test_request_deletion_has_try_except(self):
        import mandarin.web.gdpr_routes as m
        source = inspect.getsource(m.request_deletion)
        assert "try:" in source, "request_deletion must contain a try block"
        assert "except" in source, "request_deletion must contain an except clause"

    # 3. export_data uses explicit table allowlist (frozenset) instead of auto-discovery
    def test_export_data_has_table_allowlist(self):
        source = self._get_export_impl_source()
        assert re.search(r'_GDPR_EXTRA_TABLES\s*=\s*frozenset', source), (
            "_export_data_impl must use an explicit _GDPR_EXTRA_TABLES frozenset allowlist"
        )

    # 4. request_deletion uses explicit table allowlist instead of auto-discovery
    def test_request_deletion_has_table_allowlist(self):
        source = self._get_deletion_impl_source()
        assert re.search(r'_GDPR_DELETE_TABLES\s*=\s*frozenset', source), (
            "_request_deletion_impl must use an explicit _GDPR_DELETE_TABLES frozenset allowlist"
        )


# ---------------------------------------------------------------------------
# data_retention tests (5–7): use real in-memory SQLite
# ---------------------------------------------------------------------------

class TestDataRetention:
    """Test purge_expired logic against an in-memory SQLite database.

    Inline schemas are intentional — these test edge cases (missing tables,
    minimal schemas) to verify purge_expired handles them gracefully.
    """

    def _make_conn(self):
        """Return a fresh in-memory connection with Row factory."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    def _seed_retention_policy(self, conn, policies):
        """Create retention_policy table and insert rows."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retention_policy (
                table_name TEXT PRIMARY KEY,
                retention_days INTEGER NOT NULL,
                last_purged TEXT,
                description TEXT
            )
        """)
        for table_name, days in policies:
            conn.execute(
                "INSERT INTO retention_policy (table_name, retention_days) VALUES (?, ?)",
                (table_name, days),
            )
        conn.commit()

    # 5. purge_expired with mock retention policies purges old rows
    def test_purge_expired_deletes_old_rows(self):
        conn = self._make_conn()

        # Create a simple table with a created_at column
        conn.execute("""
            CREATE TABLE error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        # Insert one old row (200 days ago) and one fresh row (1 day ago)
        conn.execute(
            "INSERT INTO error_log (user_id, created_at) VALUES (1, datetime('now', '-200 days'))"
        )
        conn.execute(
            "INSERT INTO error_log (user_id, created_at) VALUES (1, datetime('now', '-1 day'))"
        )
        conn.commit()

        self._seed_retention_policy(conn, [("error_log", 30)])

        # Patch _trim_crash_log so it doesn't try to read the filesystem
        with patch("mandarin.data_retention._trim_crash_log"):
            results = purge_expired(conn)

        assert results.get("error_log", 0) == 1, (
            "purge_expired should delete exactly the one row older than 30 days"
        )
        remaining = conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0]
        assert remaining == 1, "One fresh row should remain after purge"

    # 6. purge_expired skips tables with retention_days = -1
    def test_purge_expired_skips_indefinite_retention(self):
        conn = self._make_conn()

        conn.execute("""
            CREATE TABLE security_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO security_audit_log (timestamp) VALUES (datetime('now', '-999 days'))"
        )
        conn.commit()

        # retention_days = -1 means indefinite — the WHERE clause filters these out
        self._seed_retention_policy(conn, [("security_audit_log", -1)])

        with patch("mandarin.data_retention._trim_crash_log"):
            results = purge_expired(conn)

        # The table should NOT appear in results (filtered by WHERE retention_days > 0)
        assert "security_audit_log" not in results, (
            "Tables with retention_days = -1 must be skipped entirely"
        )
        remaining = conn.execute("SELECT COUNT(*) FROM security_audit_log").fetchone()[0]
        assert remaining == 1, "Row must not be deleted when retention_days = -1"

    # 7. purge_expired handles missing retention_policy table gracefully
    def test_purge_expired_missing_policy_table_returns_empty(self):
        conn = self._make_conn()
        # No retention_policy table at all

        with patch("mandarin.data_retention._trim_crash_log"):
            results = purge_expired(conn)

        assert results == {}, (
            "purge_expired must return an empty dict when retention_policy table is absent"
        )


# ---------------------------------------------------------------------------
# Flask route tests (8–10): use a real test client with a patched DB
# ---------------------------------------------------------------------------

TEST_EMAIL = "gdpr_test@example.com"
TEST_PASSWORD = "testpass"
TEST_PASSWORD_HASH = generate_password_hash(TEST_PASSWORD, method="pbkdf2:sha256")


@pytest.fixture
def gdpr_client(test_db):
    """Flask test client wired to the test database, with a logged-in GDPR user."""
    conn, _ = test_db

    # Insert a test user with a real password hash so login works
    conn.execute("""
        INSERT INTO user (email, password_hash, display_name, subscription_tier)
        VALUES (?, ?, 'GDPR Tester', 'free')
    """, (TEST_EMAIL, TEST_PASSWORD_HASH))
    conn.commit()

    user_row = conn.execute(
        "SELECT id FROM user WHERE email = ?", (TEST_EMAIL,)
    ).fetchone()
    user_id = user_row["id"]

    # Ensure learner_profile exists for the new user
    conn.execute(
        "INSERT OR IGNORE INTO learner_profile (user_id) VALUES (?)", (user_id,)
    )
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    class _FakeConnection:
        def __enter__(self):
            return conn
        def __exit__(self, *args):
            return False

    with patch("mandarin.db.connection", _FakeConnection):
        with patch("mandarin.web.auth_routes.db.connection", _FakeConnection):
            with patch("mandarin.web.gdpr_routes.db.connection", _FakeConnection):
                with app.test_client() as client:
                    # Log in as the test user
                    client.post("/auth/login", data={
                        "email": TEST_EMAIL,
                        "password": TEST_PASSWORD,
                    })
                    yield client, conn, user_id


class TestGdprRoutes:
    """Integration tests for /api/account/export and /api/account/delete."""

    # 8. GDPR export response has Content-Disposition header
    def test_export_has_content_disposition_header(self, gdpr_client):
        client, conn, user_id = gdpr_client

        # X-Requested-With is required by the app's CSRF guard for API POST routes;
        # GET routes also need it to be safe, but export is a GET — still add it for
        # completeness. The delete endpoint is a POST so it definitely needs it.
        resp = client.get(
            "/api/account/export",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200, (
            f"Expected 200 from /api/account/export, got {resp.status_code}: {resp.data[:200]}"
        )
        cd = resp.headers.get("Content-Disposition", "")
        assert "attachment" in cd, f"Content-Disposition must say 'attachment'; got: {cd!r}"
        assert "mandarin-data-export" in cd, (
            f"Content-Disposition filename should contain 'mandarin-data-export'; got: {cd!r}"
        )

    # 9. GDPR delete anonymizes user record
    def test_delete_anonymizes_user_email(self, gdpr_client):
        client, conn, user_id = gdpr_client

        resp = client.post(
            "/api/account/delete",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200, (
            f"Expected 200 from /api/account/delete, got {resp.status_code}: {resp.data[:200]}"
        )

        row = conn.execute(
            "SELECT email, is_active, password_hash FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        assert row is not None, "User row must still exist after deletion (referential integrity)"

        expected_email = f"deleted-{user_id}@deleted.local"
        assert row["email"] == expected_email, (
            f"Email must be anonymized to '{expected_email}'; got '{row['email']}'"
        )
        assert row["is_active"] == 0, "Deleted user must be deactivated (is_active = 0)"
        assert row["password_hash"] == "DELETED", (
            "Password hash must be replaced with 'DELETED' sentinel"
        )

    # 10. GDPR delete creates data_deletion_request record
    def test_delete_creates_deletion_request_record(self, gdpr_client):
        client, conn, user_id = gdpr_client

        resp = client.post(
            "/api/account/delete",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200, (
            f"Expected 200 from /api/account/delete, got {resp.status_code}: {resp.data[:200]}"
        )

        record = conn.execute(
            "SELECT status FROM data_deletion_request WHERE user_id = ?", (user_id,)
        ).fetchone()
        assert record is not None, (
            "A data_deletion_request row must be created for the user"
        )
        assert record["status"] == "completed", (
            f"Deletion request status must be 'completed'; got '{record['status']}'"
        )
