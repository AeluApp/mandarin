"""DB-backed scheduler lock for multi-instance safety.

Prevents duplicate execution of periodic tasks (email sending, retention purge,
stale session cleanup) when multiple app instances run concurrently (e.g. Fly.io).

Uses a SQLite advisory lock pattern: a scheduler acquires a named lock with an
expiry. Other instances skip their run if a valid lock exists. Locks expire
automatically so a crashed instance doesn't hold the lock forever.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone, UTC

from . import db

logger = logging.getLogger(__name__)

# Unique instance identifier (PID + hostname for multi-machine deploys)
from .settings import FLY_MACHINE_ID, HOSTNAME
_INSTANCE_ID = f"{os.getpid()}@{FLY_MACHINE_ID or HOSTNAME}"


def acquire_lock(conn: sqlite3.Connection, name: str, ttl_seconds: int) -> bool:
    """Try to acquire a named scheduler lock.

    Returns True if the lock was acquired (this instance should proceed).
    Returns False if another instance holds a valid lock (skip this run).

    The lock auto-expires after ttl_seconds, so a crashed instance doesn't
    block others permanently.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Try to take the lock: INSERT if missing, or UPDATE if expired
    try:
        # First, clean up expired locks
        conn.execute(
            """DELETE FROM scheduler_lock
               WHERE name = ? AND expires_at < ?""",
            (name, now),
        )

        # Try to insert our lock
        conn.execute(
            """INSERT OR IGNORE INTO scheduler_lock (name, locked_by, locked_at, expires_at)
               VALUES (?, ?, ?, datetime(?, '+' || ? || ' seconds'))""",
            (name, _INSTANCE_ID, now, now, str(ttl_seconds)),
        )
        conn.commit()

        # Check if we got the lock
        row = conn.execute(
            "SELECT locked_by FROM scheduler_lock WHERE name = ?",
            (name,),
        ).fetchone()

        if row and row[0] == _INSTANCE_ID:
            return True

        logger.debug("Lock '%s' held by %s, skipping", name, row[0] if row else "unknown")
        return False

    except sqlite3.Error as e:
        logger.warning("Failed to acquire lock '%s': %s", name, e)
        return False


def release_lock(conn: sqlite3.Connection, name: str) -> None:
    """Release a named scheduler lock (only if we own it)."""
    try:
        conn.execute(
            "DELETE FROM scheduler_lock WHERE name = ? AND locked_by = ?",
            (name, _INSTANCE_ID),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.warning("Failed to release lock '%s': %s", name, e)


def extend_lock(conn: sqlite3.Connection, name: str, ttl_seconds: int) -> bool:
    """Extend the TTL of a lock we own. Returns True if successful."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cur = conn.execute(
            """UPDATE scheduler_lock
               SET expires_at = datetime(?, '+' || ? || ' seconds')
               WHERE name = ? AND locked_by = ?""",
            (now, str(ttl_seconds), name, _INSTANCE_ID),
        )
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error:
        return False
