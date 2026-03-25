"""Exposure logging — records when a user actually experiences their assigned variant."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)


def log_exposure(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
    context: str = "",
) -> None:
    """Log that a user was exposed to their experiment variant.

    Exposure logging is separate from assignment because a user may be assigned
    but never actually see the treatment (e.g., they don't visit the page
    where the variant is applied).  This distinction matters for per-protocol
    analysis.
    """
    try:
        row = conn.execute(
            "SELECT id FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
        if not row:
            return

        experiment_id = row["id"]

        assignment = conn.execute(
            "SELECT variant FROM experiment_assignment WHERE experiment_id = ? AND user_id = ?",
            (experiment_id, user_id),
        ).fetchone()
        if not assignment:
            return

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO experiment_exposure
               (experiment_id, user_id, variant, context, exposed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (experiment_id, user_id, assignment["variant"], context, now),
        )
        conn.commit()
    except sqlite3.OperationalError as e:
        logger.warning("Failed to log exposure for experiment %r: %s", experiment_name, e)
