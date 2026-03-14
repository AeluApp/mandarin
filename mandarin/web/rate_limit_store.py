"""SQLite-backed storage for flask_limiter — persists rate limits across restarts.

Implements the flask_limiter Storage interface using the rate_limit table.
"""

import logging
import time
from datetime import datetime, timezone, timedelta

from limits.storage import Storage

from .. import db

logger = logging.getLogger(__name__)


class SQLiteStorage(Storage):
    """flask_limiter storage backend backed by the rate_limit SQLite table."""

    STORAGE_SCHEME = ["sqlite"]

    def __init__(self, uri: str = None, **kwargs):
        super().__init__(uri, **kwargs)

    @property
    def base_exceptions(self):
        return (Exception,)

    def _get_conn(self):
        return db.ensure_db()

    def incr(self, key: str, expiry: int, elastic_expiry: bool = False, amount: int = 1) -> int:
        """Increment the counter for the given key."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        expires_str = (now + timedelta(seconds=expiry)).strftime("%Y-%m-%d %H:%M:%S")

        # Clean expired entries for this key
        conn.execute("DELETE FROM rate_limit WHERE key = ? AND expires_at < ?", (key, now_str))

        # Get current window
        row = conn.execute(
            "SELECT hits, window_start FROM rate_limit WHERE key = ? AND expires_at >= ?",
            (key, now_str),
        ).fetchone()

        if row:
            new_hits = row["hits"] + amount
            if elastic_expiry:
                conn.execute(
                    "UPDATE rate_limit SET hits = ?, expires_at = ? WHERE key = ? AND window_start = ?",
                    (new_hits, expires_str, key, row["window_start"]),
                )
            else:
                conn.execute(
                    "UPDATE rate_limit SET hits = ? WHERE key = ? AND window_start = ?",
                    (new_hits, key, row["window_start"]),
                )
            conn.commit()
            return new_hits
        else:
            conn.execute(
                "INSERT INTO rate_limit (key, hits, window_start, expires_at) VALUES (?, ?, ?, ?)",
                (key, amount, now_str, expires_str),
            )
            conn.commit()
            return amount

    def get(self, key: str) -> int:
        """Get the current counter value for the given key."""
        conn = self._get_conn()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            "SELECT hits FROM rate_limit WHERE key = ? AND expires_at >= ? ORDER BY window_start DESC LIMIT 1",
            (key, now_str),
        ).fetchone()
        return row["hits"] if row else 0

    def get_expiry(self, key: str) -> int:
        """Get the expiry time for the given key as a Unix timestamp."""
        conn = self._get_conn()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            "SELECT expires_at FROM rate_limit WHERE key = ? AND expires_at >= ? ORDER BY window_start DESC LIMIT 1",
            (key, now_str),
        ).fetchone()
        if row and row["expires_at"]:
            try:
                exp = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                return int(exp.timestamp())
            except (ValueError, TypeError):
                pass
        return int(time.time())

    def check(self) -> bool:
        """Check if the storage backend is healthy."""
        try:
            conn = self._get_conn()
            conn.execute("SELECT 1 FROM rate_limit LIMIT 1")
            return True
        except Exception as e:
            logger.warning("Rate limit storage check failed: %s", e)
            return False

    def reset(self) -> int:
        """Reset all rate limit counters. Returns count deleted."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM rate_limit")
        conn.commit()
        return cursor.rowcount or 0

    def clear(self, key: str) -> None:
        """Clear counters for a specific key."""
        conn = self._get_conn()
        conn.execute("DELETE FROM rate_limit WHERE key = ?", (key,))
        conn.commit()
