"""Global holdout group — a persistent 5-10% of users excluded from all experiments.

The holdout group serves as a long-run truth check: by comparing holdout users
(who never receive any treatment) against experiment participants, we can detect
whether the cumulative effect of many experiments is net-positive.

Holdout assignment is deterministic (hash-based) and persistent.  Once a user
is assigned to the holdout, they stay there across all experiments.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

HOLDOUT_RATE = 0.05  # 5% of users reserved as global holdout


def assign_holdout(
    conn: sqlite3.Connection,
    user_id: int,
    holdout_rate: float = HOLDOUT_RATE,
) -> bool:
    """Determine and persist whether a user is in the global holdout.

    Returns ``True`` if the user is in the holdout group.  Assignment is
    deterministic and persistent — the same user always gets the same result.
    """
    # Check existing assignment
    try:
        existing = conn.execute(
            "SELECT 1 FROM experiment_holdout WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if existing:
            return True
    except sqlite3.OperationalError:
        return False

    # Deterministic assignment
    key = f"global_holdout:{user_id}"
    bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 10000
    in_holdout = bucket < holdout_rate * 10000

    if in_holdout:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO experiment_holdout (user_id, assigned_at) VALUES (?, ?)",
                (user_id, now),
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass

    return in_holdout


def is_in_holdout(conn: sqlite3.Connection, user_id: int) -> bool:
    """Check if a user is in the global holdout group."""
    try:
        row = conn.execute(
            "SELECT 1 FROM experiment_holdout WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def get_holdout_users(conn: sqlite3.Connection) -> list[int]:
    """Return all user IDs in the global holdout."""
    try:
        rows = conn.execute("SELECT user_id FROM experiment_holdout").fetchall()
        return [r["user_id"] for r in rows]
    except sqlite3.OperationalError:
        return []


def get_holdout_count(conn: sqlite3.Connection) -> int:
    """Return the count of holdout users."""
    try:
        row = conn.execute("SELECT COUNT(*) as n FROM experiment_holdout").fetchone()
        return row["n"] if row else 0
    except sqlite3.OperationalError:
        return 0
