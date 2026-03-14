"""Settings routes — user preferences, push token management, methodology."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from .api_errors import api_error_handler
from .middleware import _get_user_id

# ── Methodology references (Doctrine §9: Trust & Transparency) ──
_METHODOLOGY = {
    "scheduling": {
        "name": "Spaced Repetition (SM-2 + Half-Life Regression)",
        "summary": "Items are scheduled based on how well you remember them. "
                   "Intervals grow as recall strengthens.",
        "references": [
            "Pimsleur, P. (1967). A Memory Schedule. Modern Language Journal, 51(2), 73-75.",
            "Settles, B. & Meeder, B. (2016). A Trainable Spaced Repetition Model for Language Learning. ACL.",
        ],
    },
    "mastery_stages": {
        "name": "Six-Stage Mastery Model",
        "summary": "Items progress: seen → passed_once → stabilizing → stable → durable. "
                   "Each stage requires consistent recall over increasing intervals.",
        "references": [
            "Bjork, R.A. & Bjork, E.L. (2011). Making things hard on yourself, but in a good way.",
        ],
    },
    "desirable_difficulty": {
        "name": "Desirable Difficulty",
        "summary": "Harder retrieval practice leads to stronger long-term memory. "
                   "The system varies drill types to maintain productive challenge.",
        "references": [
            "Bjork, R.A. (1994). Memory and metamemory considerations in the training of human beings.",
            "Roediger, H.L. & Karpicke, J.D. (2006). Test-Enhanced Learning. Psychological Science, 17(3).",
        ],
    },
    "interleaving": {
        "name": "Interleaved Practice",
        "summary": "Mixing different item types in a session improves discrimination and retention.",
        "references": [
            "Rohrer, D. (2012). Interleaving helps students distinguish among similar concepts. "
            "Educational Psychology Review, 24(3), 355-367.",
        ],
    },
}

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/api/settings/anonymous-mode", methods=["GET", "POST"])
@api_error_handler("Anonymous mode")
def api_anonymous_mode():
    """Get or toggle anonymous learning mode."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            from ..feature_flags import is_enabled
            if not is_enabled(conn, "anonymous_mode", user_id):
                return jsonify({"error": "Feature not available"}), 403
            data = request.get_json(silent=True) or {}
            enabled = bool(data.get("enabled", False))
            conn.execute(
                "UPDATE user SET anonymous_mode = ? WHERE id = ?",
                (int(enabled), user_id),
            )
            conn.commit()
            return jsonify({"anonymous_mode": enabled})
        else:
            row = conn.execute(
                "SELECT anonymous_mode FROM user WHERE id = ?", (user_id,)
            ).fetchone()
            return jsonify({"anonymous_mode": bool(row["anonymous_mode"]) if row else False})


@settings_bp.route("/api/settings/marketing-opt-out", methods=["GET", "POST"])
@api_error_handler("Marketing opt-out")
def api_marketing_opt_out():
    """Get or toggle marketing email opt-out."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            opted_out = bool(data.get("opted_out", True))
            conn.execute(
                "UPDATE user SET marketing_opt_out = ? WHERE id = ?",
                (int(opted_out), user_id),
            )
            conn.commit()
            return jsonify({"marketing_opt_out": opted_out})
        else:
            row = conn.execute(
                "SELECT marketing_opt_out FROM user WHERE id = ?", (user_id,)
            ).fetchone()
            return jsonify({"marketing_opt_out": bool(row["marketing_opt_out"]) if row else False})


@settings_bp.route("/api/settings/session-length", methods=["GET", "POST"])
@api_error_handler("Session length")
def api_session_length():
    """Get or update preferred session length."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            length = data.get("length")
            if not isinstance(length, int) or length < 4 or length > 30:
                return jsonify({"error": "length must be integer 4-30"}), 400
            conn.execute(
                "UPDATE learner_profile SET preferred_session_length = ? WHERE user_id = ?",
                (length, user_id),
            )
            conn.commit()
            return jsonify({"preferred_session_length": length})
        else:
            profile = db.get_profile(conn, user_id=user_id)
            return jsonify({"preferred_session_length": profile.get("preferred_session_length") or 12})


@settings_bp.route("/api/settings/audio", methods=["GET", "POST"])
@api_error_handler("Audio settings")
def api_audio_settings():
    """Get or update audio playback preference."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            enabled = bool(data.get("enabled", True))
            conn.execute(
                "UPDATE learner_profile SET audio_enabled = ? WHERE user_id = ?",
                (int(enabled), user_id),
            )
            conn.commit()
            return jsonify({"audio_enabled": enabled})
        else:
            profile = db.get_profile(conn, user_id=user_id)
            return jsonify({"audio_enabled": bool(profile.get("audio_enabled", 1))})


@settings_bp.route("/api/settings/daily-goal", methods=["GET", "POST"])
@api_error_handler("Daily goal")
def api_daily_goal():
    """Get or update target sessions per week."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            goal = data.get("target_sessions_per_week")
            if not isinstance(goal, int) or goal < 1 or goal > 14:
                return jsonify({"error": "target_sessions_per_week must be integer 1-14"}), 400
            conn.execute(
                "UPDATE learner_profile SET target_sessions_per_week = ? WHERE user_id = ?",
                (goal, user_id),
            )
            conn.commit()
            return jsonify({"target_sessions_per_week": goal})
        else:
            profile = db.get_profile(conn, user_id=user_id)
            return jsonify({"target_sessions_per_week": profile.get("target_sessions_per_week") or 4})


@settings_bp.route("/api/settings/streak-reminders", methods=["GET", "POST"])
@api_error_handler("Streak reminders")
def api_streak_reminders():
    """Get or update streak reminder preference."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            enabled = 1 if data.get("enabled", True) else 0
            conn.execute(
                "UPDATE learner_profile SET streak_reminders = ? WHERE user_id = ?",
                (enabled, user_id),
            )
            conn.commit()
            return jsonify({"streak_reminders": bool(enabled)})
        else:
            profile = db.get_profile(conn, user_id=user_id)
            val = profile.get("streak_reminders")
            return jsonify({"streak_reminders": bool(val) if val is not None else True})


@settings_bp.route("/api/settings/display-prefs", methods=["GET", "POST"])
@api_error_handler("Display preferences")
def api_display_prefs():
    """Get or update reading/listening display preferences."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            updates = []
            params = []
            if "reading_show_pinyin" in data:
                updates.append("reading_show_pinyin = ?")
                params.append(1 if data["reading_show_pinyin"] else 0)
            if "reading_show_translation" in data:
                updates.append("reading_show_translation = ?")
                params.append(1 if data["reading_show_translation"] else 0)
            if not updates:
                return jsonify({"error": "No valid fields provided"}), 400
            params.append(user_id)
            conn.execute(
                "UPDATE learner_profile SET " + ", ".join(updates) + " WHERE user_id = ?",
                params,
            )
            conn.commit()
            profile = db.get_profile(conn, user_id=user_id)
            return jsonify({
                "reading_show_pinyin": bool(profile.get("reading_show_pinyin", 0)),
                "reading_show_translation": bool(profile.get("reading_show_translation", 0)),
            })
        else:
            profile = db.get_profile(conn, user_id=user_id)
            return jsonify({
                "reading_show_pinyin": bool(profile.get("reading_show_pinyin", 0)),
                "reading_show_translation": bool(profile.get("reading_show_translation", 0)),
            })


@settings_bp.route("/api/settings")
@api_error_handler("Settings")
def api_settings_all():
    """Get all user settings in one call."""
    user_id = _get_user_id()
    with db.connection() as conn:
        profile = db.get_profile(conn, user_id=user_id)
        user_row = conn.execute(
            "SELECT anonymous_mode, marketing_opt_out FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        sr = profile.get("streak_reminders")
        return jsonify({
            "preferred_session_length": profile.get("preferred_session_length") or 12,
            "target_sessions_per_week": profile.get("target_sessions_per_week") or 4,
            "audio_enabled": bool(profile.get("audio_enabled", 1)),
            "anonymous_mode": bool(user_row["anonymous_mode"]) if user_row else False,
            "marketing_opt_out": bool(user_row["marketing_opt_out"]) if user_row else False,
            "streak_reminders": bool(sr) if sr is not None else True,
            "reading_show_pinyin": bool(profile.get("reading_show_pinyin", 0)),
            "reading_show_translation": bool(profile.get("reading_show_translation", 0)),
        })


# ── Push Notification ─────────────────────────────────────────────

@settings_bp.route("/api/push/vapid-key")
def api_push_vapid_key():
    """Return the VAPID public key for web push subscription."""
    from ..settings import VAPID_PUBLIC_KEY
    if not VAPID_PUBLIC_KEY:
        return jsonify({"error": "Push not configured"}), 404
    return jsonify({"vapid_public_key": VAPID_PUBLIC_KEY})


@settings_bp.route("/api/push/register", methods=["POST"])
def api_push_register():
    """Register a push notification token for the current user."""
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    try:
        data = request.get_json(silent=True) or {}
        platform = (data.get("platform") or "").strip()
        token = (data.get("token") or "").strip()
        if not platform or not token:
            return jsonify({"error": "platform and token required"}), 400
        if platform not in ("ios", "android", "web"):
            return jsonify({"error": "platform must be 'ios', 'android', or 'web'"}), 400

        with db.connection() as conn:
            conn.execute(
                """INSERT INTO push_token (user_id, platform, token)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, platform) DO UPDATE SET token = excluded.token,
                   created_at = datetime('now')""",
                (current_user.id, platform, token),
            )
            conn.commit()
            return jsonify({"status": "ok"})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("push register error: %s", e)
        return jsonify({"error": "Registration failed"}), 500


@settings_bp.route("/api/push/unregister", methods=["POST"])
def api_push_unregister():
    """Remove push notification token on logout."""
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    try:
        data = request.get_json(silent=True) or {}
        platform = (data.get("platform") or "").strip()

        with db.connection() as conn:
            if platform:
                conn.execute(
                    "DELETE FROM push_token WHERE user_id = ? AND platform = ?",
                    (current_user.id, platform),
                )
            else:
                conn.execute(
                    "DELETE FROM push_token WHERE user_id = ?",
                    (current_user.id,),
                )
            conn.commit()
            return jsonify({"status": "ok"})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("push unregister error: %s", e)
        return jsonify({"error": "Unregistration failed"}), 500


@settings_bp.route("/api/settings/methodology")
def api_methodology():
    """Return methodology references — Doctrine §9 Trust & Transparency."""
    return jsonify(_METHODOLOGY)
