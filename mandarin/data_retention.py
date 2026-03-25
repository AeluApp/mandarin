"""Data retention — auto-purge expired data per retention_policy table.

Implements ISO/IEC 25010 data quality and COSO ERM data governance requirements.
Each table's retention period is defined in the retention_policy table (seeded in v20 migration).
A retention_days value of -1 means indefinite retention (no purge).
"""

import logging
import re
import sqlite3
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)


def get_policies(conn: sqlite3.Connection) -> list:
    """Return all retention policies."""
    try:
        rows = conn.execute(
            "SELECT table_name, retention_days, last_purged, description FROM retention_policy ORDER BY table_name"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def purge_expired(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """Purge rows past their retention period.

    Returns dict mapping table_name -> rows_deleted.
    Skips tables with retention_days = -1 (indefinite).
    """
    results = {}

    try:
        policies = conn.execute(
            "SELECT table_name, retention_days FROM retention_policy WHERE retention_days > 0"
        ).fetchall()
    except sqlite3.OperationalError:
        logger.warning("retention_policy table not found")
        return results

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Map table -> timestamp column to use for age check
    timestamp_columns = {
        "error_log": "created_at",
        "security_audit_log": "timestamp",
        "rate_limit": "expires_at",
        "vocab_encounter": "created_at",
    }

    for policy in policies:
        table = policy["table_name"]

        # Validate table name to prevent injection
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
            logger.warning("Skipping invalid table name in retention policy: %s", table)
            continue

        ts_col = timestamp_columns.get(table)
        if not ts_col:
            # Try common column names
            try:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            except sqlite3.OperationalError:
                logger.debug("Table %s does not exist, skipping purge", table)
                continue
            for candidate in ("created_at", "timestamp", "expires_at"):
                if candidate in cols:
                    ts_col = candidate
                    break
            if not ts_col:
                logger.debug("No timestamp column found for %s, skipping", table)
                continue

        days = policy["retention_days"]

        if dry_run:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM {table} WHERE {ts_col} < datetime('now', ? || ' days')",
                (f"-{days}",),
            ).fetchone()
            results[table] = row["cnt"] if row else 0
        else:
            cursor = conn.execute(
                f"DELETE FROM {table} WHERE {ts_col} < datetime('now', ? || ' days')",
                (f"-{days}",),
            )
            deleted = cursor.rowcount or 0
            results[table] = deleted

            # Update last_purged timestamp
            conn.execute(
                "UPDATE retention_policy SET last_purged = ? WHERE table_name = ?",
                (now, table),
            )
            logger.info("Purged %d rows from %s (retention: %d days)", deleted, table, days)

    if not dry_run:
        conn.commit()

    # Trim crash.log to 10K lines max (not auto-rotated like the others)
    if not dry_run:
        _trim_crash_log()

    return results


_MAX_CRASH_LOG_LINES = 10_000


def _trim_crash_log():
    """Keep only the last 10K lines of crash.log."""
    from .log_config import CRASH_LOG
    try:
        if not CRASH_LOG.exists():
            return
        lines = CRASH_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_CRASH_LOG_LINES:
            trimmed = lines[-_MAX_CRASH_LOG_LINES:]
            CRASH_LOG.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
            logger.info("Trimmed crash.log from %d to %d lines", len(lines), len(trimmed))
    except OSError as e:
        logger.debug("crash.log trim failed: %s", e)
