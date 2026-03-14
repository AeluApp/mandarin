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
from .api_errors import api_error_handler
from ..security import log_security_event, SecurityEvent

logger = logging.getLogger(__name__)

gdpr_bp = Blueprint("gdpr", __name__, url_prefix="/api/account")


@gdpr_bp.before_request
@login_required
def require_auth():
    pass


@gdpr_bp.route("/export")
@api_error_handler("GDPR export")
def export_data():
    """Export all personal data for the authenticated user (GDPR Article 20).

    Returns a JSON document containing all user data across all tables.
    """
    try:
        return _export_data_impl()
    except (sqlite3.Error, OSError, KeyError, TypeError) as e:
        logger.error("GDPR export error for user_id=%s: %s", current_user.id, e, exc_info=True)
        return jsonify({"error": "Data export failed"}), 500


def _export_data_impl():
    user_id = current_user.id

    with db.connection() as conn:
        log_security_event(conn, SecurityEvent.DATA_EXPORT_REQUESTED, user_id=user_id)

        export = {"exported_at": datetime.now(timezone.utc).isoformat(), "user_id": user_id}

        # User profile — may be None for a deleted/orphaned auth session
        user_row = conn.execute(
            """SELECT id, email, display_name, subscription_tier, subscription_status,
                      created_at, updated_at, last_login_at
               FROM user WHERE id = ?""",
            (user_id,),
        ).fetchone()
        export["user"] = dict(user_row) if user_row else None

        # If user record doesn't exist, return an empty but valid export
        if not user_row:
            logger.warning("GDPR export for user_id=%s: no user record found", user_id)
            return Response(
                json.dumps(export, indent=2, default=str),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename=mandarin-data-export-{user_id}.json"},
            )

        # Learner profile
        lp_row = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        export["learner_profile"] = dict(lp_row) if lp_row else None

        # Progress data
        try:
            progress_rows = conn.execute(
                "SELECT * FROM progress WHERE user_id = ?", (user_id,)
            ).fetchall()
            export["progress"] = [dict(r) for r in progress_rows]
        except sqlite3.OperationalError:
            export["progress"] = []

        # Session history
        try:
            session_rows = conn.execute(
                "SELECT * FROM session_log WHERE user_id = ?", (user_id,)
            ).fetchall()
            export["sessions"] = [dict(r) for r in session_rows]
        except sqlite3.OperationalError:
            export["sessions"] = []

        # Error log
        try:
            error_rows = conn.execute(
                "SELECT * FROM error_log WHERE user_id = ?", (user_id,)
            ).fetchall()
            export["errors"] = [dict(r) for r in error_rows]
        except sqlite3.OperationalError:
            export["errors"] = []

        # Vocab encounters
        try:
            encounter_rows = conn.execute(
                "SELECT * FROM vocab_encounter WHERE user_id = ?", (user_id,)
            ).fetchall()
            export["vocab_encounters"] = [dict(r) for r in encounter_rows]
        except sqlite3.OperationalError:
            export["vocab_encounters"] = []

        # Push tokens
        try:
            push_rows = conn.execute(
                "SELECT * FROM push_token WHERE user_id = ?", (user_id,)
            ).fetchall()
            export["push_tokens"] = [dict(r) for r in push_rows]
        except sqlite3.OperationalError:
            export["push_tokens"] = []

        # Security audit log (user's own events)
        try:
            audit_rows = conn.execute(
                "SELECT timestamp, event_type, details, severity FROM security_audit_log WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            export["security_events"] = [dict(r) for r in audit_rows]
        except sqlite3.OperationalError:
            export["security_events"] = []

        # Export from known user-data tables (explicit allowlist)
        _GDPR_EXTRA_TABLES = frozenset({
            "error_focus", "audio_recording", "probe_log", "session_metrics",
            "improvement_log", "media_watch", "speaker_calibration",
            "crash_log", "client_error_log", "client_event", "mfa_challenge",
            "grade_appeal", "classroom_student", "data_deletion_request",
        })
        from ..db.core import _table_set, _col_set
        _already_exported = {
            "user", "learner_profile", "progress", "session_log",
            "error_log", "vocab_encounter", "push_token", "security_audit_log",
        }
        for table in sorted(_GDPR_EXTRA_TABLES & _table_set(conn)):
            if table in _already_exported:
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
@api_error_handler("GDPR deletion")
def request_deletion():
    """Request deletion of all personal data (GDPR Article 17).

    Immediately anonymizes the account and queues full deletion.
    """
    try:
        return _request_deletion_impl()
    except (sqlite3.Error, OSError, KeyError, TypeError) as e:
        logger.error("GDPR deletion error for user_id=%s: %s", current_user.id, e, exc_info=True)
        return jsonify({"error": "Data deletion failed"}), 500


def _request_deletion_impl():
    user_id = current_user.id

    with db.connection() as conn:
        # Idempotency: if deletion already completed, return success without re-processing
        existing = conn.execute(
            "SELECT status FROM data_deletion_request WHERE user_id = ? ORDER BY requested_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if existing and existing["status"] == "completed":
            logger.info("GDPR deletion already completed for user_id=%s — returning idempotent success", user_id)
            return jsonify({
                "deleted": True,
                "message": "Your data has already been deleted. Your account is deactivated.",
            })

        log_security_event(conn, SecurityEvent.DATA_DELETION_REQUESTED, user_id=user_id)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Record the deletion request (only if not already processing)
        if not existing or existing["status"] != "processing":
            conn.execute(
                "INSERT INTO data_deletion_request (user_id, requested_at, status) VALUES (?, ?, 'processing')",
                (user_id, now),
            )

        # Close any active sessions before deletion (ended_at IS NULL)
        try:
            conn.execute(
                """UPDATE session_log SET
                       ended_at = ?,
                       session_outcome = 'interrupted'
                   WHERE user_id = ? AND ended_at IS NULL""",
                (now, user_id),
            )
        except sqlite3.OperationalError:
            pass  # session_log may not have session_outcome column in older schemas

        # Delete personal data from known user-data tables (explicit allowlist)
        _GDPR_DELETE_TABLES = frozenset({
            "progress", "session_log", "error_log", "error_focus",
            "audio_recording", "probe_log", "session_metrics",
            "vocab_encounter", "improvement_log", "media_watch",
            "push_token", "speaker_calibration", "crash_log",
            "client_error_log", "client_event", "mfa_challenge",
            "grade_appeal", "classroom_student",
        })
        from ..db.core import _table_set
        for table in sorted(_GDPR_DELETE_TABLES & _table_set(conn)):
            try:
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            except sqlite3.OperationalError:
                pass

        # Anonymize user record (retain for referential integrity)
        # Uses is_active = 0 so re-deletion of already-anonymized user is harmless
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
               totp_secret = NULL,
               totp_enabled = 0,
               totp_backup_codes = NULL,
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
