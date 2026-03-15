"""Sync routes — offline queue push/pull for mobile clients."""

from __future__ import annotations

import hashlib
import logging
import sqlite3

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required

from datetime import datetime, timezone

from .. import db
from .api_errors import api_error, api_error_handler, AUTH_REQUIRED, VALIDATION_ERROR

logger = logging.getLogger(__name__)

# Action type translation: Flutter offline queue sends generic names,
# but the backend expects specific internal types.
_ACTION_TYPE_MAP: dict[str, str] = {
    "submit_answer": "drill_result",
    "mark_watched": "media_watched",
    "mark_complete": "media_complete",
    "lookup": "vocab_encounter",
    "encounter": "vocab_encounter",
}

sync_bp = Blueprint("sync", __name__, url_prefix="/api/sync")


@sync_bp.before_request
def require_auth():
    if not current_user.is_authenticated:
        return api_error(AUTH_REQUIRED, "Authentication required.", 401)


@sync_bp.route("/push", methods=["POST"])
@api_error_handler("Sync push")
def sync_push():
    """Accept batched actions from the offline queue.

    POST /api/sync/push
    Body: {"actions": [{"type": "drill_result", "data": {...}, "timestamp": "..."}]}
    """
    try:
        data = request.get_json(silent=True) or {}
        actions = data.get("actions", [])

        if not isinstance(actions, list):
            return api_error(VALIDATION_ERROR, "actions must be a list.")

        user_id = current_user.id
        processed = 0
        errors = []

        with db.connection() as conn:
            for i, action in enumerate(actions):
                # Support both key conventions:
                #   Backend canonical: {"type": ..., "data": ..., "timestamp": ...}
                #   Flutter offline queue: {"action": ..., "payload": ..., "timestamp": ...}
                raw_type = action.get("type") or action.get("action", "")
                action_type = _ACTION_TYPE_MAP.get(raw_type, raw_type)
                action_data = action.get("data") or action.get("payload", {})
                timestamp = action.get("timestamp", "")

                try:
                    if action_type == "drill_result":
                        _process_drill_result(conn, user_id, action_data, timestamp)
                        processed += 1
                    elif action_type == "vocab_encounter":
                        _process_vocab_encounter(conn, user_id, action_data)
                        processed += 1
                    elif action_type == "media_watched":
                        _process_media_watched(conn, action_data)
                        processed += 1
                    else:
                        errors.append({"index": i, "error": f"Unknown action type: {action_type}"})
                except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
                    logger.warning("sync push action %d failed: %s", i, e)
                    errors.append({"index": i, "error": str(e)})

        return jsonify({
            "processed": processed,
            "errors": errors,
            "total": len(actions),
        })
    except (sqlite3.Error, OSError, KeyError, TypeError) as e:
        logger.error("sync push error: %s", e, exc_info=True)
        return api_error(VALIDATION_ERROR, "Sync push failed.", 500)


@sync_bp.route("/pull")
@api_error_handler("Sync pull")
def sync_pull():
    """Return new content/progress since a timestamp.

    GET /api/sync/pull?since=2024-01-01T00:00:00
    """
    user_id = current_user.id
    since = request.args.get("since", "1970-01-01 00:00:00")

    try:
        with db.connection() as conn:
            # Recent progress updates
            progress_rows = conn.execute(
                """SELECT content_item_id, modality, mastery_stage, streak_correct,
                          next_review_date, last_review_date, half_life_days
                   FROM progress
                   WHERE user_id = ? AND last_review_date > ?
                   ORDER BY last_review_date DESC
                   LIMIT 500""",
                (user_id, since),
            ).fetchall()

            progress = [dict(r) for r in progress_rows]

            # Recent session summaries
            session_rows = conn.execute(
                """SELECT id, started_at, session_type, items_completed, items_correct,
                          early_exit, session_outcome
                   FROM session_log
                   WHERE user_id = ? AND started_at > ?
                   ORDER BY started_at DESC
                   LIMIT 50""",
                (user_id, since),
            ).fetchall()

            sessions = [dict(r) for r in session_rows]

            return jsonify({
                "progress": progress,
                "sessions": sessions,
                "since": since,
            })
    except (sqlite3.Error, OSError) as e:
        logger.error("sync pull error: %s", e)
        return jsonify({"error": "Sync pull failed"}), 500


@sync_bp.route("/state")
@api_error_handler("Sync state")
def sync_state():
    """Return a state hash for quick client-side comparison.

    GET /api/sync/state
    """
    user_id = current_user.id

    try:
        with db.connection() as conn:
            # Hash of latest progress timestamps
            row = conn.execute(
                """SELECT COUNT(*) as cnt, MAX(last_review_date) as latest
                   FROM progress WHERE user_id = ?""",
                (user_id,),
            ).fetchone()

            cnt = row["cnt"] if row else 0
            latest = row["latest"] if row else ""
            state_str = f"{user_id}:{cnt}:{latest}"
            state_hash = hashlib.sha256(state_str.encode()).hexdigest()[:12]

            return jsonify({
                "hash": state_hash,
                "last_updated": latest or "",
                "item_count": cnt,
            })
    except (sqlite3.Error, OSError) as e:
        logger.error("sync state error: %s", e)
        return jsonify({"error": "Sync state failed"}), 500


# ── Action processors ────────────────────────────────────────────────────────

def _process_drill_result(conn, user_id, data, timestamp):
    """Process a queued drill result (minimal — logs error if item not found)."""
    content_item_id = data.get("content_item_id")
    modality = data.get("modality", "reading")
    correct = data.get("correct", False)

    if not content_item_id:
        return

    # Update progress streak
    row = conn.execute(
        "SELECT id, streak_correct, streak_incorrect, total_attempts, total_correct FROM progress "
        "WHERE user_id = ? AND content_item_id = ? AND modality = ?",
        (user_id, content_item_id, modality),
    ).fetchone()

    if row:
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if correct:
            conn.execute(
                "UPDATE progress SET streak_correct = streak_correct + 1, streak_incorrect = 0, "
                "total_attempts = total_attempts + 1, total_correct = total_correct + 1, "
                "last_review_date = ? WHERE id = ?",
                (ts, row["id"]),
            )
        else:
            conn.execute(
                "UPDATE progress SET streak_incorrect = streak_incorrect + 1, streak_correct = 0, "
                "total_attempts = total_attempts + 1, last_review_date = ? WHERE id = ?",
                (ts, row["id"]),
            )
        conn.commit()


def _process_vocab_encounter(conn, user_id, data):
    """Process a queued vocab encounter."""
    hanzi = (data.get("hanzi") or "").strip()
    source_type = data.get("source_type", "reading")
    source_id = data.get("source_id", "")
    if not hanzi:
        return

    row = conn.execute(
        "SELECT id FROM content_item WHERE hanzi = ? LIMIT 1", (hanzi,)
    ).fetchone()
    content_item_id = row["id"] if row else None

    conn.execute(
        """INSERT INTO vocab_encounter
           (content_item_id, hanzi, source_type, source_id, looked_up, user_id)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (content_item_id, hanzi, source_type, source_id, user_id),
    )
    conn.commit()


def _process_media_watched(conn, data):
    """Process a queued media watch event."""
    from ..media import record_media_watched

    media_id = data.get("media_id", "")
    score = data.get("score", 0.0)
    if media_id:
        record_media_watched(conn, media_id, score, 0, 0)
