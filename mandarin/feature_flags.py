"""Feature flags — toggle features per-flag and per-user via rollout percentage."""

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)


# Drill types that require feature flag checks
FLAGGED_DRILLS = {
    "radical_decomposition": "drill_radical_decomposition",
    "confusable_pairs": "drill_confusable_pairs",
    "measure_word": "drill_measure_word",
    "sentence_building": "drill_sentence_building",
}


def is_drill_enabled(conn: sqlite3.Connection, drill_type: str, user_id: int = None) -> bool:
    """Check if a drill type is enabled. Unflagged drills are always enabled."""
    flag = FLAGGED_DRILLS.get(drill_type)
    if flag is None:
        return True  # Not gated
    return is_enabled(conn, flag, user_id)


def is_enabled(conn: sqlite3.Connection, flag_name: str, user_id: int = None) -> bool:
    """Check if a feature flag is enabled.

    If rollout_pct < 100, uses a deterministic hash of (flag_name, user_id)
    to decide inclusion — same user always gets the same result.
    """
    try:
        row = conn.execute(
            "SELECT enabled, rollout_pct FROM feature_flag WHERE name = ?",
            (flag_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return False

    if not row:
        return False
    if not row["enabled"]:
        return False

    pct = row["rollout_pct"]
    if pct >= 100:
        return True
    if pct <= 0:
        return False

    if user_id is None:
        return True  # No user context — treat as enabled

    # Deterministic rollout: hash(flag + user_id) mod 100 < pct
    key = f"{flag_name}:{user_id}"
    bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100
    result = bucket < pct
    logger.debug("Feature flag %r user=%s: pct=%d bucket=%d → %s", flag_name, user_id, pct, bucket, result)
    return result


def set_flag(conn: sqlite3.Connection, flag_name: str, enabled: bool,
             rollout_pct: int = 100, description: str = None) -> None:
    """Create or update a feature flag."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO feature_flag (name, enabled, rollout_pct, description, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            enabled = excluded.enabled,
            rollout_pct = excluded.rollout_pct,
            description = COALESCE(excluded.description, feature_flag.description),
            updated_at = excluded.updated_at
    """, (flag_name, int(enabled), rollout_pct, description, now))
    conn.commit()


def get_all_flags(conn: sqlite3.Connection) -> list:
    """Return all feature flags as list of dicts."""
    try:
        rows = conn.execute(
            "SELECT name, enabled, rollout_pct, description, created_at, updated_at FROM feature_flag ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
