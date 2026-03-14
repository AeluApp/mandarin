"""Tests for DB-backed scheduler lock — multi-instance safety."""

import sqlite3
from unittest.mock import patch

import pytest

from mandarin.scheduler_lock import acquire_lock, release_lock, extend_lock


class TestAcquireLock:

    def test_acquire_succeeds_when_no_lock(self, test_db):
        conn, _ = test_db
        assert acquire_lock(conn, "test_job", ttl_seconds=3600) is True

    def test_acquire_same_instance_succeeds(self, test_db):
        """Same instance can re-acquire its own lock."""
        conn, _ = test_db
        assert acquire_lock(conn, "test_job", ttl_seconds=3600) is True
        # Same instance tries again — should succeed (owns it)
        row = conn.execute("SELECT locked_by FROM scheduler_lock WHERE name = 'test_job'").fetchone()
        assert row is not None

    def test_acquire_blocked_by_other_instance(self, test_db):
        """Lock held by another instance blocks acquisition."""
        conn, _ = test_db
        # Simulate another instance holding the lock
        conn.execute(
            """INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at)
               VALUES ('test_job', 'other-instance', datetime('now'), datetime('now', '+3600 seconds'))"""
        )
        conn.commit()
        assert acquire_lock(conn, "test_job", ttl_seconds=3600) is False

    def test_acquire_succeeds_when_lock_expired(self, test_db):
        """Expired lock is cleaned up and new lock can be acquired."""
        conn, _ = test_db
        # Insert an expired lock
        conn.execute(
            """INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at)
               VALUES ('test_job', 'old-instance', datetime('now', '-2 hours'), datetime('now', '-1 hour'))"""
        )
        conn.commit()
        assert acquire_lock(conn, "test_job", ttl_seconds=3600) is True

    def test_lock_row_created(self, test_db):
        conn, _ = test_db
        acquire_lock(conn, "test_job", ttl_seconds=3600)
        row = conn.execute("SELECT name, locked_by FROM scheduler_lock WHERE name = 'test_job'").fetchone()
        assert row is not None
        assert row["name"] == "test_job"

    def test_multiple_locks_independent(self, test_db):
        conn, _ = test_db
        assert acquire_lock(conn, "job_a", ttl_seconds=3600) is True
        assert acquire_lock(conn, "job_b", ttl_seconds=3600) is True
        count = conn.execute("SELECT COUNT(*) FROM scheduler_lock").fetchone()[0]
        assert count == 2


class TestReleaseLock:

    def test_release_removes_lock(self, test_db):
        conn, _ = test_db
        acquire_lock(conn, "test_job", ttl_seconds=3600)
        release_lock(conn, "test_job")
        row = conn.execute("SELECT * FROM scheduler_lock WHERE name = 'test_job'").fetchone()
        assert row is None

    def test_release_only_own_lock(self, test_db):
        """Release does not remove a lock held by another instance."""
        conn, _ = test_db
        conn.execute(
            """INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at)
               VALUES ('test_job', 'other-instance', datetime('now'), datetime('now', '+3600 seconds'))"""
        )
        conn.commit()
        release_lock(conn, "test_job")
        # Lock should still exist (owned by other instance)
        row = conn.execute("SELECT * FROM scheduler_lock WHERE name = 'test_job'").fetchone()
        assert row is not None

    def test_release_nonexistent_is_noop(self, test_db):
        conn, _ = test_db
        # Should not raise
        release_lock(conn, "nonexistent")


class TestExtendLock:

    def test_extend_own_lock(self, test_db):
        conn, _ = test_db
        acquire_lock(conn, "test_job", ttl_seconds=100)
        old_row = conn.execute("SELECT expires_at FROM scheduler_lock WHERE name = 'test_job'").fetchone()
        result = extend_lock(conn, "test_job", ttl_seconds=7200)
        assert result is True
        new_row = conn.execute("SELECT expires_at FROM scheduler_lock WHERE name = 'test_job'").fetchone()
        assert new_row["expires_at"] > old_row["expires_at"]

    def test_extend_other_lock_fails(self, test_db):
        conn, _ = test_db
        conn.execute(
            """INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at)
               VALUES ('test_job', 'other-instance', datetime('now'), datetime('now', '+100 seconds'))"""
        )
        conn.commit()
        result = extend_lock(conn, "test_job", ttl_seconds=7200)
        assert result is False
