"""Supabase MCP preparation — multi-user database migration support.

Supabase's official MCP server lets you create tables, query data,
deploy edge functions, and manage branches. This module prepares
Aelu for the multi-user architecture migration by providing:

1. Schema comparison tools (SQLite → Supabase PostgreSQL)
2. Data migration helpers
3. Integrity verification
4. Migration state tracking

The Supabase MCP server itself is external (npx supabase-mcp).
This module provides the Aelu-side logic that works alongside it.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_migration_status(conn) -> dict:
    """Check current migration state: what's migrated, what's pending.

    Returns a structured report of all tables, their row counts,
    and whether they have Supabase equivalents.
    """
    # Get all table names
    tables = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()

    table_info = []
    for t in tables:
        name = t["name"]
        count = conn.execute(f"SELECT COUNT(*) as cnt FROM [{name}]").fetchone()
        row_count = count["cnt"] if count else 0

        # Classify table
        if name in _MULTI_USER_TABLES:
            scope = "per_user"
        elif name in _SHARED_TABLES:
            scope = "shared"
        elif name in _ADMIN_TABLES:
            scope = "admin"
        else:
            scope = "unknown"

        table_info.append({
            "name": name,
            "row_count": row_count,
            "scope": scope,
            "needs_rls": scope == "per_user",
        })

    return {
        "total_tables": len(table_info),
        "tables": table_info,
        "per_user_tables": sum(1 for t in table_info if t["scope"] == "per_user"),
        "shared_tables": sum(1 for t in table_info if t["scope"] == "shared"),
        "admin_tables": sum(1 for t in table_info if t["scope"] == "admin"),
    }


def generate_postgres_schema(conn, table_name: str) -> dict:
    """Generate PostgreSQL CREATE TABLE equivalent for a SQLite table.

    Maps SQLite types to PostgreSQL types and adds RLS policies
    for per-user tables.
    """
    # Get column info
    columns = conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
    if not columns:
        return {"error": f"Table {table_name} not found"}

    pg_columns = []
    for col in columns:
        name = col["name"]
        sqlite_type = (col["type"] or "TEXT").upper()
        notnull = col["notnull"]
        pk = col["pk"]
        default = col["dflt_value"]

        pg_type = _sqlite_to_pg_type(sqlite_type)

        col_def = f"    {name} {pg_type}"
        if pk:
            col_def = f"    {name} {'BIGSERIAL' if pg_type == 'BIGINT' else pg_type} PRIMARY KEY"
        elif notnull:
            col_def += " NOT NULL"
        if default and not pk:
            pg_default = _convert_default(default)
            if pg_default:
                col_def += f" DEFAULT {pg_default}"

        pg_columns.append(col_def)

    create_sql = f"CREATE TABLE {table_name} (\n"
    create_sql += ",\n".join(pg_columns)
    create_sql += "\n);"

    # RLS policy for per-user tables
    rls_sql = ""
    if table_name in _MULTI_USER_TABLES:
        rls_sql = f"""
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;

CREATE POLICY "{table_name}_user_access" ON {table_name}
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
"""

    return {
        "table_name": table_name,
        "create_sql": create_sql,
        "rls_sql": rls_sql.strip() if rls_sql else None,
        "column_count": len(pg_columns),
        "needs_rls": table_name in _MULTI_USER_TABLES,
    }


def verify_data_integrity(conn) -> dict:
    """Run integrity checks on the SQLite database before migration.

    Checks: foreign key violations, orphaned records, data consistency.
    """
    issues = []

    # Foreign key check
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        issues.append({
            "type": "foreign_key_violation",
            "count": len(fk_violations),
            "severity": "high",
        })

    # Integrity check
    integrity = conn.execute("PRAGMA integrity_check").fetchone()
    if integrity and integrity[0] != "ok":
        issues.append({
            "type": "integrity_error",
            "detail": integrity[0],
            "severity": "critical",
        })

    # Check for orphaned progress records
    try:
        orphaned = conn.execute("""
            SELECT COUNT(*) as cnt FROM progress p
            LEFT JOIN content_item ci ON ci.id = p.content_item_id
            WHERE ci.id IS NULL
        """).fetchone()
        if orphaned and orphaned["cnt"] > 0:
            issues.append({
                "type": "orphaned_progress",
                "count": orphaned["cnt"],
                "severity": "medium",
            })
    except Exception:
        pass

    # Check for orphaned error_log records
    try:
        orphaned_errors = conn.execute("""
            SELECT COUNT(*) as cnt FROM error_log el
            LEFT JOIN content_item ci ON ci.id = el.content_item_id
            WHERE ci.id IS NULL
        """).fetchone()
        if orphaned_errors and orphaned_errors["cnt"] > 0:
            issues.append({
                "type": "orphaned_errors",
                "count": orphaned_errors["cnt"],
                "severity": "low",
            })
    except Exception:
        pass

    return {
        "status": "clean" if not issues else "issues_found",
        "issues": issues,
        "issue_count": len(issues),
    }


def export_table_json(conn, table_name: str, limit: int = 1000) -> dict:
    """Export a table's data as JSON for migration import.

    Returns row data in a format suitable for Supabase bulk insert.
    """
    try:
        rows = conn.execute(
            f"SELECT * FROM [{table_name}] LIMIT ?", (limit,)
        ).fetchall()
    except Exception as e:
        return {"error": str(e)}

    data = [dict(r) for r in rows]
    return {
        "table_name": table_name,
        "row_count": len(data),
        "data": data,
    }


# ── Type mapping ─────────────────────────────────────

_TYPE_MAP = {
    "INTEGER": "BIGINT",
    "INT": "BIGINT",
    "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "TEXT": "TEXT",
    "BLOB": "BYTEA",
    "BOOLEAN": "BOOLEAN",
}


def _sqlite_to_pg_type(sqlite_type: str) -> str:
    """Map SQLite type to PostgreSQL type."""
    upper = sqlite_type.upper().strip()
    if upper in _TYPE_MAP:
        return _TYPE_MAP[upper]
    if "INT" in upper:
        return "BIGINT"
    if "CHAR" in upper or "TEXT" in upper or "CLOB" in upper:
        return "TEXT"
    if "REAL" in upper or "FLOA" in upper or "DOUB" in upper:
        return "DOUBLE PRECISION"
    return "TEXT"


def _convert_default(sqlite_default: str) -> Optional[str]:
    """Convert SQLite default to PostgreSQL equivalent."""
    if not sqlite_default:
        return None
    d = sqlite_default.strip()
    if d == "(datetime('now'))":
        return "NOW()"
    if d == "(date('now'))":
        return "CURRENT_DATE"
    if d.startswith("'") and d.endswith("'"):
        return d
    if d.isdigit():
        return d
    if d in ("0", "1", "0.0", "1.0"):
        return d
    return None


# ── Table classification ─────────────────────────────

_MULTI_USER_TABLES = {
    "progress", "session_log", "review_event", "error_log",
    "error_focus", "audio_recording", "reading_progress",
    "listening_progress", "vocab_encounter", "grammar_progress",
    "learner_profile", "learner_proficiency_zones",
    "media_watch", "push_token", "experiment_assignment",
    "classroom_member", "notification_preference",
}

_SHARED_TABLES = {
    "content_item", "grammar_point", "content_grammar",
    "skill", "dialogue_scenario",
}

_ADMIN_TABLES = {
    "product_audit", "content_generation_queue", "crash_log",
    "security_event", "experiment", "work_item", "risk_item",
    "spc_observation", "quality_metric", "feature_flag",
}
