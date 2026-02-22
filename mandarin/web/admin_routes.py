"""Admin routes — dashboard, metrics, user management."""

import logging
import sqlite3
from functools import wraps

from flask import Blueprint, jsonify, render_template, abort, request, redirect, url_for
from flask_login import login_required, current_user

from .. import db
from ..security import log_security_event, SecurityEvent, Severity

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """Decorator: require is_admin flag AND MFA on user (CIS 6.5).

    Admin accounts MUST have TOTP MFA enabled. If an admin user hasn't
    set up MFA yet, they get a 403 with instructions to enable it first.
    """
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        with db.connection() as conn:
            row = conn.execute(
                "SELECT is_admin, totp_enabled FROM user WHERE id = ?", (current_user.id,)
            ).fetchone()
            if not row or not row["is_admin"]:
                log_security_event(conn, SecurityEvent.ACCESS_DENIED,
                                   user_id=current_user.id,
                                   details=f"admin access denied: {request.path}",
                                   severity=Severity.WARNING)
                abort(403)
            # CIS 6.5: Require MFA for all administrative access
            if not row["totp_enabled"]:
                log_security_event(conn, SecurityEvent.ACCESS_DENIED,
                                   user_id=current_user.id,
                                   details=f"admin MFA not enabled: {request.path}",
                                   severity=Severity.WARNING)
                if request.path.startswith("/api/"):
                    return jsonify({"error": "MFA required for admin access. Enable TOTP MFA first."}), 403
                abort(403)
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"{request.method} {request.path}")
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/admin/")
@admin_required
def admin_dashboard():
    """Admin dashboard page."""
    return render_template("admin.html")


@admin_bp.route("/api/admin/metrics")
@admin_required
def admin_metrics():
    """Key business metrics."""
    try:
        with db.connection() as conn:
            # Total signups
            signups = conn.execute("SELECT COUNT(*) as cnt FROM user").fetchone()

            # Active users (session in last 7 days)
            active = conn.execute(
                """SELECT COUNT(DISTINCT user_id) as cnt FROM session_log
                   WHERE started_at >= datetime('now', '-7 days')
                     AND items_completed > 0"""
            ).fetchone()

            # Total sessions this week
            sessions_week = conn.execute(
                """SELECT COUNT(*) as cnt FROM session_log
                   WHERE started_at >= datetime('now', '-7 days')"""
            ).fetchone()

            # Tier distribution
            tiers = conn.execute(
                "SELECT subscription_tier, COUNT(*) as cnt FROM user GROUP BY subscription_tier"
            ).fetchall()

            return jsonify({
                "total_signups": signups["cnt"] if signups else 0,
                "active_users_7d": active["cnt"] if active else 0,
                "sessions_7d": sessions_week["cnt"] if sessions_week else 0,
                "tier_distribution": {r["subscription_tier"]: r["cnt"] for r in tiers},
            })
    except Exception as e:
        logger.error("Admin metrics error: %s", e)
        return jsonify({"error": "Metrics unavailable"}), 500


@admin_bp.route("/api/admin/users")
@admin_required
def admin_users():
    """User list with last activity."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT u.id, u.email, u.display_name, u.subscription_tier,
                          u.created_at, u.last_login_at,
                          (SELECT MAX(started_at) FROM session_log WHERE user_id = u.id) as last_session
                   FROM user u
                   ORDER BY u.created_at DESC
                   LIMIT 100"""
            ).fetchall()
            users = []
            for r in rows:
                users.append({
                    "id": r["id"],
                    "email": r["email"],
                    "display_name": r["display_name"],
                    "tier": r["subscription_tier"],
                    "created_at": r["created_at"],
                    "last_login": r["last_login_at"],
                    "last_session": r["last_session"],
                })
            return jsonify({"users": users})
    except Exception as e:
        logger.error("Admin users error: %s", e)
        return jsonify({"error": "Users unavailable"}), 500


@admin_bp.route("/api/admin/feedback")
@admin_required
def admin_feedback():
    """Feedback entries."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT id, rating, comment, feedback_type, created_at
                   FROM user_feedback
                   ORDER BY created_at DESC
                   LIMIT 50"""
            ).fetchall()
            entries = []
            for r in rows:
                entries.append({
                    "id": r["id"],
                    "rating": r["rating"],
                    "comment": r["comment"],
                    "type": r["feedback_type"],
                    "created_at": r["created_at"],
                })
            return jsonify({"feedback": entries})
    except sqlite3.OperationalError:
        return jsonify({"feedback": []})
    except Exception as e:
        logger.error("Admin feedback error: %s", e)
        return jsonify({"error": "Feedback unavailable"}), 500
