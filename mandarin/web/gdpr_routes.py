"""GDPR routes — data export (Article 20) and deletion (Article 17).

Note on audit log retention (Art. 17(3)(e)):
    security_audit_log records are intentionally retained after account deletion.
    Legal basis: legitimate interest in security forensics and compliance with
    legal obligations (fraud detection, incident response). User-identifying
    fields (IP, user_id) are retained for audit trail integrity.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, jsonify, Response
from flask_login import login_required, current_user

from .. import db
from ..security import log_security_event, SecurityEvent

logger = logging.getLogger(__name__)

gdpr_bp = Blueprint("gdpr", __name__, url_prefix="/api/account")


@gdpr_bp.before_request
@login_required
def require_auth():
    pass


@gdpr_bp.route("/export")
def export_data():
    """Export all personal data for the authenticated user (GDPR Article 20).

    Returns a JSON document containing all user data across all tables.
    """
    user_id = current_user.id

    with db.connection() as conn:
        log_security_event(conn, SecurityEvent.DATA_EXPORT_REQUESTED, user_id=user_id)

        export = {"exported_at": datetime.now(timezone.utc).isoformat(), "user_id": user_id}

        # User profile
        user_row = conn.execute(
            """SELECT id, email, display_name, subscription_tier, subscription_status,
                      created_at, updated_at, last_login_at
               FROM user WHERE id = ?""",
            (user_id,),
        ).fetchone()
        export["user"] = dict(user_row) if user_row else None

        # Learner profile
        lp_row = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        export["learner_profile"] = dict(lp_row) if lp_row else None

        # Progress data
        progress_rows = conn.execute(
            "SELECT * FROM progress WHERE user_id = ?", (user_id,)
        ).fetchall()
        export["progress"] = [dict(r) for r in progress_rows]

        # Session history
        session_rows = conn.execute(
            "SELECT * FROM session_log WHERE user_id = ?", (user_id,)
        ).fetchall()
        export["sessions"] = [dict(r) for r in session_rows]

        # Error log
        error_rows = conn.execute(
            "SELECT * FROM error_log WHERE user_id = ?", (user_id,)
        ).fetchall()
        export["errors"] = [dict(r) for r in error_rows]

        # Vocab encounters
        encounter_rows = conn.execute(
            "SELECT * FROM vocab_encounter WHERE user_id = ?", (user_id,)
        ).fetchall()
        export["vocab_encounters"] = [dict(r) for r in encounter_rows]

        # Push tokens
        push_rows = conn.execute(
            "SELECT * FROM push_token WHERE user_id = ?", (user_id,)
        ).fetchall()
        export["push_tokens"] = [dict(r) for r in push_rows]

        # Security audit log (user's own events)
        try:
            audit_rows = conn.execute(
                "SELECT timestamp, event_type, details, severity FROM security_audit_log WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            export["security_events"] = [dict(r) for r in audit_rows]
        except sqlite3.OperationalError:
            export["security_events"] = []

        # Auto-discover additional user tables (Item 23)
        from ..db.core import _table_set, _col_set
        _already_exported = {
            "user", "learner_profile", "progress", "session_log",
            "error_log", "vocab_encounter", "push_token", "security_audit_log",
        }
        for table in sorted(_table_set(conn)):
            if table in _already_exported or table.startswith("sqlite_"):
                continue
            if "user_id" in _col_set(conn, table):
                try:
                    rows = conn.execute(
                        f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)
                    ).fetchall()
                    if rows:
                        export[table] = [dict(r) for r in rows]
                except sqlite3.OperationalError:
                    pass

    return Response(
        json.dumps(export, indent=2, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=mandarin-data-export-{user_id}.json"},
    )


@gdpr_bp.route("/delete", methods=["POST"])
def request_deletion():
    """Request deletion of all personal data (GDPR Article 17).

    Immediately anonymizes the account and queues full deletion.
    """
    user_id = current_user.id

    with db.connection() as conn:
        log_security_event(conn, SecurityEvent.DATA_DELETION_REQUESTED, user_id=user_id)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Record the deletion request
        conn.execute(
            "INSERT INTO data_deletion_request (user_id, requested_at, status) VALUES (?, ?, 'processing')",
            (user_id, now),
        )

        # Delete personal data from all tables (auto-discovered — Item 23)
        from ..db.core import _table_set, _col_set
        _tables_to_clear = [
            t for t in _table_set(conn)
            if "user_id" in _col_set(conn, t)
            and t not in ("user", "data_deletion_request", "security_audit_log")
        ]
        for table in _tables_to_clear:
            # SECURITY: table names come from the hardcoded list above, not user input.
            # Assertion ensures no injection if the list is ever refactored.
            import re as _re
            assert _re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table), f"Invalid table name: {table}"
            try:
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            except sqlite3.OperationalError:
                pass  # Table might not have user_id column

        # Anonymize user record (retain for referential integrity)
        conn.execute(
            """UPDATE user SET
               email = 'deleted-' || CAST(id AS TEXT) || '@deleted.local',
               password_hash = 'DELETED',
               display_name = 'Deleted User',
               refresh_token_hash = NULL,
               refresh_token_expires = NULL,
               reset_token_hash = NULL,
               reset_token_expires = NULL,
               stripe_customer_id = NULL,
               stripe_subscription_id = NULL,
               is_active = 0,
               updated_at = ?
            WHERE id = ?""",
            (now, user_id),
        )

        # Delete learner profile
        conn.execute("DELETE FROM learner_profile WHERE user_id = ?", (user_id,))

        # Mark deletion complete
        conn.execute(
            "UPDATE data_deletion_request SET status = 'completed', completed_at = ? WHERE user_id = ? AND status = 'processing'",
            (now, user_id),
        )

        conn.commit()
        log_security_event(conn, SecurityEvent.DATA_DELETION_COMPLETED, user_id=user_id)

    return jsonify({
        "deleted": True,
        "message": "Your data has been deleted. Your account has been deactivated.",
    })
