"""Onboarding routes — new user setup wizard."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db

logger = logging.getLogger(__name__)

onboarding_bp = Blueprint("onboarding", __name__)


@onboarding_bp.route("/api/onboarding/wizard")
@login_required
def onboarding_wizard():
    """Check if user has completed the initial setup wizard."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT onboarding_complete, daily_goal FROM user WHERE id = ?",
                (current_user.id,)
            ).fetchone()
            if not row:
                return jsonify({"complete": False})
            return jsonify({
                "complete": bool(row["onboarding_complete"]),
                "daily_goal": row["daily_goal"] or "standard",
            })
    except Exception as e:
        logger.error("Onboarding status error: %s", e)
        return jsonify({"complete": True})  # Fail open — don't block existing users


@onboarding_bp.route("/api/onboarding/level", methods=["POST"])
@login_required
def set_level():
    """Set user's starting HSK level."""
    try:
        data = request.get_json(force=True)
        level = data.get("level", 1)
        if level not in (1, 2, 3, 4, 5, 6):
            return jsonify({"error": "Invalid HSK level"}), 400

        with db.connection() as conn:
            # Update learner profile levels to match starting HSK
            base_level = float(level)
            conn.execute(
                """UPDATE learner_profile
                   SET level_reading = ?, level_listening = ?,
                       level_speaking = ?, level_ime = ?, level_chunks = ?,
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (base_level, base_level, max(1.0, base_level - 0.5),
                 max(1.0, base_level - 0.5), base_level, current_user.id)
            )
            conn.commit()
            return jsonify({"level": level})
    except Exception as e:
        logger.error("Onboarding level error: %s", e)
        return jsonify({"error": "Could not set level"}), 500


@onboarding_bp.route("/api/onboarding/goal", methods=["POST"])
@login_required
def set_goal():
    """Set user's daily study goal."""
    try:
        data = request.get_json(force=True)
        goal = data.get("goal", "standard")
        if goal not in ("quick", "standard", "deep"):
            return jsonify({"error": "Invalid goal"}), 400

        session_lengths = {"quick": 6, "standard": 12, "deep": 20}
        target_sessions = {"quick": 3, "standard": 4, "deep": 5}

        with db.connection() as conn:
            conn.execute(
                "UPDATE user SET daily_goal = ?, updated_at = datetime('now') WHERE id = ?",
                (goal, current_user.id)
            )
            conn.execute(
                """UPDATE learner_profile
                   SET preferred_session_length = ?, target_sessions_per_week = ?,
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (session_lengths[goal], target_sessions[goal], current_user.id)
            )
            conn.commit()
            return jsonify({"goal": goal})
    except Exception as e:
        logger.error("Onboarding goal error: %s", e)
        return jsonify({"error": "Could not set goal"}), 500


@onboarding_bp.route("/api/onboarding/complete", methods=["POST"])
@login_required
def complete():
    """Mark onboarding as complete."""
    try:
        with db.connection() as conn:
            conn.execute(
                "UPDATE user SET onboarding_complete = 1, updated_at = datetime('now') WHERE id = ?",
                (current_user.id,)
            )
            conn.commit()
            return jsonify({"complete": True})
    except Exception as e:
        logger.error("Onboarding complete error: %s", e)
        return jsonify({"error": "Could not complete onboarding"}), 500
