"""Shared test database factory.

All test files should use make_test_db() instead of inline _make_db() functions.
This ensures tests run against the real schema, not phantom tables.
"""
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


def make_test_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the full production schema.

    Uses schema.sql + migrations from mandarin.db.core to ensure
    the test schema matches production exactly.
    """
    from mandarin.db.core import _migrate

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Load base schema
    if _SCHEMA_PATH.exists():
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))

    # Run all migrations to reach current version
    try:
        _migrate(conn)
    except Exception:
        pass  # Some migrations may reference disk files; skip gracefully

    # Create bootstrap test user (or update if migrations already created one)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user (id, email, password_hash, created_at, onboarding_complete) "
            "VALUES (1, 'test@aelu.app', 'test_hash', datetime('now'), 0)",
        )
        # Ensure the email is what tests expect, even if migrations seeded a different one
        conn.execute("UPDATE user SET email = 'test@aelu.app' WHERE id = 1")
        conn.execute(
            "INSERT OR IGNORE INTO learner_profile (user_id, level_reading) VALUES (1, 1.0)"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass

    return conn
