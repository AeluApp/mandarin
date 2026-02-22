"""Learner profile queries."""

import sqlite3


def get_profile(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Get the learner profile."""
    row = conn.execute("SELECT * FROM learner_profile WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else {}
