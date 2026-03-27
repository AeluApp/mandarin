"""Audit logging for experiment decisions — eligibility, assignment, overrides, ramps."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)


def log_audit_event(
    conn: sqlite3.Connection,
    event_type: str,
    *,
    experiment_id: int | None = None,
    user_id: int | None = None,
    data: dict | None = None,
) -> None:
    """Write an audit event to the experiment_audit_log table.

    Event types: eligibility_check, assignment, exposure, exclusion,
    balance_check, srm_check, guardrail_check, pause, resume,
    ramp_change, conclude, config_change, analysis_snapshot.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(data or {})
    try:
        conn.execute(
            """INSERT INTO experiment_audit_log
               (experiment_id, event_type, user_id, data, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (experiment_id, event_type, user_id, payload, now),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # Table may not exist yet during migration
        logger.debug("audit log table not available, skipping event %s", event_type)


def get_audit_log(
    conn: sqlite3.Connection,
    experiment_id: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve audit log entries, optionally filtered."""
    try:
        clauses = []
        params: list = []
        if experiment_id is not None:
            clauses.append("experiment_id = ?")
            params.append(experiment_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM experiment_audit_log{where} ORDER BY created_at DESC LIMIT ?"
        rows = conn.execute(sql, params + [limit]).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("data"):
                try:
                    d["data"] = json.loads(d["data"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result
    except sqlite3.OperationalError:
        return []
