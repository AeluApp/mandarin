"""Tests for mandarin.data_retention — get_policies, purge_expired, _trim_crash_log."""

import sqlite3
from datetime import datetime, timedelta, timezone, UTC
from unittest.mock import patch

import pytest

from mandarin.data_retention import _trim_crash_log, get_policies, purge_expired


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite DB with retention_policy and target tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row

    # Retention policy table
    c.execute("""CREATE TABLE retention_policy (
        table_name TEXT PRIMARY KEY,
        retention_days INTEGER NOT NULL,
        last_purged TEXT,
        description TEXT
    )""")

    # Target tables that retention can purge
    c.execute("""CREATE TABLE error_log (
        id INTEGER PRIMARY KEY,
        created_at TEXT,
        user_id INTEGER,
        drill_type TEXT,
        error_type TEXT
    )""")
    c.execute("""CREATE TABLE security_audit_log (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        event_type TEXT,
        user_id INTEGER,
        ip_address TEXT,
        user_agent TEXT,
        details TEXT,
        severity TEXT
    )""")
    c.execute("""CREATE TABLE rate_limit (
        id INTEGER PRIMARY KEY,
        key TEXT,
        hits INTEGER,
        window_start TEXT,
        expires_at TEXT
    )""")
    c.commit()
    yield c
    c.close()


def _days_ago(n: int) -> str:
    """Return an ISO timestamp n days in the past."""
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")


def _seed_policy(conn, table_name, retention_days, desc="test"):
    conn.execute(
        "INSERT INTO retention_policy (table_name, retention_days, description) VALUES (?, ?, ?)",
        (table_name, retention_days, desc),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# get_policies tests
# ---------------------------------------------------------------------------

class TestGetPolicies:
    def test_empty_table_returns_empty_list(self, conn):
        """Empty retention_policy table returns []."""
        assert get_policies(conn) == []

    def test_with_policies_returns_sorted_dicts(self, conn):
        """Policies come back as a sorted list of dicts."""
        _seed_policy(conn, "error_log", 90, "Error logs 90 days")
        _seed_policy(conn, "audit_log", 365, "Audit 1 year")

        result = get_policies(conn)
        assert len(result) == 2
        # Sorted by table_name alphabetically
        assert result[0]["table_name"] == "audit_log"
        assert result[1]["table_name"] == "error_log"
        # Each entry is a plain dict
        assert isinstance(result[0], dict)
        assert result[1]["retention_days"] == 90

    def test_missing_table_returns_empty_list(self):
        """If retention_policy table doesn't exist, returns []."""
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        assert get_policies(c) == []
        c.close()


# ---------------------------------------------------------------------------
# purge_expired tests
# ---------------------------------------------------------------------------

class TestPurgeExpired:
    def test_no_policies_returns_empty_dict(self, conn):
        """No policies seeded -> empty results."""
        result = purge_expired(conn)
        assert result == {}

    def test_indefinite_retention_skipped(self, conn):
        """retention_days=-1 rows are excluded by the WHERE clause."""
        _seed_policy(conn, "error_log", -1, "Keep forever")
        # Insert an old row that would be purged if the policy were active
        conn.execute(
            "INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(999),)
        )
        conn.commit()

        result = purge_expired(conn)
        # -1 is filtered by WHERE retention_days > 0, so nothing processed
        assert result == {}
        # Row still exists
        assert conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0] == 1

    def test_purge_deletes_old_rows(self, conn):
        """Old rows past retention_days are deleted."""
        _seed_policy(conn, "error_log", 30)
        # Insert one old row (60 days ago) and one recent row (5 days ago)
        conn.execute("INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(60),))
        conn.execute("INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(5),))
        conn.commit()

        result = purge_expired(conn)
        assert result["error_log"] == 1
        # Only the recent row remains
        assert conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0] == 1

    def test_dry_run_counts_but_does_not_delete(self, conn):
        """dry_run=True returns counts but leaves rows in place."""
        _seed_policy(conn, "error_log", 30)
        conn.execute("INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(60),))
        conn.execute("INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(5),))
        conn.commit()

        result = purge_expired(conn, dry_run=True)
        assert result["error_log"] == 1
        # Both rows still present
        assert conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0] == 2

    def test_purge_updates_last_purged(self, conn):
        """After purge, last_purged is set on the policy row."""
        _seed_policy(conn, "error_log", 30)
        conn.execute("INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(60),))
        conn.commit()

        purge_expired(conn)

        row = conn.execute(
            "SELECT last_purged FROM retention_policy WHERE table_name = 'error_log'"
        ).fetchone()
        assert row["last_purged"] is not None
        # Should be a valid datetime string
        datetime.strptime(row["last_purged"], "%Y-%m-%d %H:%M:%S")

    def test_nonexistent_table_in_policy_skipped(self, conn):
        """Policy references a table that doesn't exist -> skipped gracefully."""
        _seed_policy(conn, "ghost_table", 7)

        result = purge_expired(conn)
        # ghost_table is not in timestamp_columns and PRAGMA table_info returns
        # nothing for it, so it's skipped
        assert "ghost_table" not in result

    def test_invalid_table_name_skipped(self, conn):
        """SQL-injection-style table name is caught by the regex guard."""
        _seed_policy(conn, "'; DROP TABLE error_log; --", 7)

        result = purge_expired(conn)
        assert result == {} or "'; DROP TABLE error_log; --" not in result
        # error_log still exists and is intact
        conn.execute("SELECT COUNT(*) FROM error_log").fetchone()

    def test_auto_detect_created_at_column(self, conn):
        """Table not in timestamp_columns but has created_at -> auto-detected."""
        # Create a table not in the hardcoded map
        conn.execute("""CREATE TABLE custom_log (
            id INTEGER PRIMARY KEY, created_at TEXT, message TEXT
        )""")
        _seed_policy(conn, "custom_log", 10)
        conn.execute("INSERT INTO custom_log (created_at, message) VALUES (?, 'old')", (_days_ago(20),))
        conn.execute("INSERT INTO custom_log (created_at, message) VALUES (?, 'new')", (_days_ago(1),))
        conn.commit()

        result = purge_expired(conn)
        assert result["custom_log"] == 1
        assert conn.execute("SELECT COUNT(*) FROM custom_log").fetchone()[0] == 1

    def test_table_with_no_timestamp_column_skipped(self, conn):
        """Table exists but has no recognizable timestamp column -> skipped."""
        conn.execute("CREATE TABLE opaque_data (id INTEGER PRIMARY KEY, payload TEXT)")
        _seed_policy(conn, "opaque_data", 10)
        conn.execute("INSERT INTO opaque_data (payload) VALUES ('test')")
        conn.commit()

        result = purge_expired(conn)
        assert "opaque_data" not in result
        # Row untouched
        assert conn.execute("SELECT COUNT(*) FROM opaque_data").fetchone()[0] == 1

    def test_missing_retention_policy_table_returns_empty(self):
        """No retention_policy table at all -> returns {} without crashing."""
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        result = purge_expired(c)
        assert result == {}
        c.close()

    def test_purge_security_audit_log(self, conn):
        """security_audit_log uses 'timestamp' column, not 'created_at'."""
        _seed_policy(conn, "security_audit_log", 365)
        conn.execute(
            "INSERT INTO security_audit_log (timestamp, event_type) VALUES (?, 'login')",
            (_days_ago(400),),
        )
        conn.execute(
            "INSERT INTO security_audit_log (timestamp, event_type) VALUES (?, 'login')",
            (_days_ago(30),),
        )
        conn.commit()

        result = purge_expired(conn)
        assert result["security_audit_log"] == 1
        assert conn.execute("SELECT COUNT(*) FROM security_audit_log").fetchone()[0] == 1

    def test_purge_rate_limit(self, conn):
        """rate_limit uses 'expires_at' column."""
        _seed_policy(conn, "rate_limit", 1)
        conn.execute(
            "INSERT INTO rate_limit (key, hits, window_start, expires_at) VALUES ('k', 5, ?, ?)",
            (_days_ago(3), _days_ago(3)),
        )
        conn.execute(
            "INSERT INTO rate_limit (key, hits, window_start, expires_at) VALUES ('k2', 1, ?, ?)",
            (_days_ago(0), _days_ago(0)),
        )
        conn.commit()

        result = purge_expired(conn)
        assert result["rate_limit"] == 1
        assert conn.execute("SELECT COUNT(*) FROM rate_limit").fetchone()[0] == 1

    def test_multiple_policies_purged_in_one_call(self, conn):
        """Multiple tables purged in a single purge_expired call."""
        _seed_policy(conn, "error_log", 30)
        _seed_policy(conn, "rate_limit", 1)

        conn.execute("INSERT INTO error_log (created_at) VALUES (?)", (_days_ago(60),))
        conn.execute(
            "INSERT INTO rate_limit (key, hits, window_start, expires_at) VALUES ('k', 1, ?, ?)",
            (_days_ago(5), _days_ago(5)),
        )
        conn.commit()

        result = purge_expired(conn)
        assert result["error_log"] == 1
        assert result["rate_limit"] == 1


# ---------------------------------------------------------------------------
# _trim_crash_log tests
# ---------------------------------------------------------------------------

class TestTrimCrashLog:
    def test_file_under_limit_not_trimmed(self, tmp_path):
        """File with fewer than 10K lines is left unchanged."""
        log_file = tmp_path / "crash.log"
        original = "\n".join(f"line{i}" for i in range(100)) + "\n"
        log_file.write_text(original, encoding="utf-8")

        with patch("mandarin.log_config.CRASH_LOG", log_file):
            _trim_crash_log()

        assert log_file.read_text(encoding="utf-8") == original

    def test_file_over_limit_trimmed_to_last_10k(self, tmp_path):
        """File with more than 10K lines is trimmed to the last 10K."""
        log_file = tmp_path / "crash.log"
        total = 12_000
        lines = [f"line{i}" for i in range(total)]
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with patch("mandarin.log_config.CRASH_LOG", log_file):
            _trim_crash_log()

        result_lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(result_lines) == 10_000
        # Should keep the last 10K lines
        assert result_lines[0] == "line2000"
        assert result_lines[-1] == f"line{total - 1}"

    def test_file_does_not_exist_no_error(self, tmp_path):
        """If crash.log doesn't exist, function returns silently."""
        log_file = tmp_path / "crash.log"
        assert not log_file.exists()

        with patch("mandarin.log_config.CRASH_LOG", log_file):
            _trim_crash_log()  # Should not raise

    def test_file_exactly_at_limit_not_trimmed(self, tmp_path):
        """File with exactly 10K lines is not modified."""
        log_file = tmp_path / "crash.log"
        lines = [f"line{i}" for i in range(10_000)]
        original = "\n".join(lines) + "\n"
        log_file.write_text(original, encoding="utf-8")

        with patch("mandarin.log_config.CRASH_LOG", log_file):
            _trim_crash_log()

        assert log_file.read_text(encoding="utf-8") == original
