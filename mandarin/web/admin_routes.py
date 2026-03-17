"""Admin routes — dashboard, metrics, user management."""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user

from .. import db
from ..security import log_security_event, SecurityEvent, Severity
from ..settings import PRICING, STRIPE_FEE_PERCENT, STRIPE_FEE_FIXED_CENTS, HOSTING_COST_MONTHLY
from .api_errors import api_error_handler
from .middleware import paginate_params

# Derived constants for revenue calculations
_MONTHLY_PRICE = float(PRICING["monthly_display"])
_STRIPE_FEE_FIXED = STRIPE_FEE_FIXED_CENTS / 100.0

# Allowed fields for dynamic SQL SET-clause construction (security audit hardening)
_RISK_ALLOWED_FIELDS = frozenset({
    "category", "title", "description", "probability", "impact",
    "mitigation", "contingency", "status", "owner",
})
_WORK_ITEM_ALLOWED_FIELDS = frozenset({
    "category", "title", "description", "size", "effort",
    "status", "priority", "acceptance_criteria", "owner",
    "estimate", "service_class", "implementation_type",
})

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
                    return jsonify({"error": "MFA required for admin access. Enable TOTP MFA in Settings first."}), 403
                flash("Admin access requires two-factor authentication. Please set it up first.", "error")
                return redirect(url_for("index") + "#settings")
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


@admin_bp.route("/api/admin/mfa-compliance")
@admin_required
@api_error_handler("MFA Compliance")
def admin_mfa_compliance():
    """Check admin accounts without MFA — CIS 6.5 compliance."""
    with db.connection() as conn:
        non_compliant = conn.execute(
            "SELECT id, email FROM user WHERE is_admin = 1 AND totp_enabled = 0"
        ).fetchall()
        compliant = conn.execute(
            "SELECT id, email FROM user WHERE is_admin = 1 AND totp_enabled = 1"
        ).fetchall()
        return jsonify({
            "compliant_count": len(compliant),
            "non_compliant_count": len(non_compliant),
            "non_compliant": [{"id": r["id"], "email": r["email"]} for r in non_compliant],
            "all_compliant": len(non_compliant) == 0,
        })


@admin_bp.route("/api/admin/metrics")
@admin_required
@api_error_handler("Metrics")
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

            # Retention cohorts (D1/D7/D30) from metrics_report
            retention = {}
            try:
                from ..metrics_report import _retention_cohorts
                retention = _retention_cohorts(conn)
            except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
                logger.debug("retention cohorts unavailable: %s", e)

            # Activation funnel metrics
            activation = {}
            try:
                first_session_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM user WHERE first_session_at IS NOT NULL"
                ).fetchone()
                activated_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM user WHERE activation_at IS NOT NULL"
                ).fetchone()
                total_users = signups["cnt"] if signups else 0
                first_session_count = first_session_row["cnt"] if first_session_row else 0
                activated_count = activated_row["cnt"] if activated_row else 0
                activation = {
                    "signup_to_first_session": round(first_session_count / total_users * 100, 1) if total_users > 0 else 0,
                    "first_session_to_activated": round(activated_count / first_session_count * 100, 1) if first_session_count > 0 else 0,
                    "signup_to_activated": round(activated_count / total_users * 100, 1) if total_users > 0 else 0,
                    "users_with_first_session": first_session_count,
                    "users_activated": activated_count,
                }
                # UTM source breakdown
                utm_rows = conn.execute(
                    """SELECT utm_source, COUNT(*) as signups,
                              SUM(CASE WHEN activation_at IS NOT NULL THEN 1 ELSE 0 END) as activated
                       FROM user WHERE utm_source IS NOT NULL
                       GROUP BY utm_source ORDER BY signups DESC LIMIT 10"""
                ).fetchall()
                activation["by_source"] = [
                    {"source": r["utm_source"], "signups": r["signups"], "activated": r["activated"]}
                    for r in utm_rows
                ]

                # Encounter→drill pipeline (magic moment) metrics
                try:
                    row = conn.execute(
                        """SELECT COUNT(DISTINCT user_id) FROM lifecycle_event
                           WHERE event_type = 'first_lookup'"""
                    ).fetchone()
                    first_lookup_count = row[0] if row else 0
                    row = conn.execute(
                        """SELECT COUNT(DISTINCT user_id) FROM lifecycle_event
                           WHERE event_type = 'first_encounter_drilled'"""
                    ).fetchone()
                    magic_moment_count = row[0] if row else 0
                    row = conn.execute(
                        """SELECT COUNT(*) FROM lifecycle_event
                           WHERE event_type = 'encounter_drilled'
                           AND created_at >= datetime('now', '-30 days')"""
                    ).fetchone()
                    total_encounter_drills = row[0] if row else 0
                    activation["users_first_lookup"] = first_lookup_count
                    activation["users_magic_moment"] = magic_moment_count
                    activation["encounter_drill_events_30d"] = total_encounter_drills
                    activation["lookup_to_magic_pct"] = (
                        round(magic_moment_count / first_lookup_count * 100, 1)
                        if first_lookup_count > 0 else 0
                    )
                except (sqlite3.Error, KeyError, TypeError):
                    pass

            except (sqlite3.Error, KeyError, TypeError) as e:
                logger.debug("activation metrics unavailable: %s", e)

            # Platform breakdown (7 days)
            platform_stats = {}
            try:
                plat_rows = conn.execute("""
                    SELECT COALESCE(client_platform, 'web') as platform,
                           COUNT(*) as sessions,
                           COUNT(DISTINCT user_id) as users,
                           ROUND(AVG(CASE WHEN items_completed > 0 THEN
                               CAST(items_correct AS REAL) / items_completed * 100
                           END), 1) as avg_accuracy,
                           ROUND(AVG(duration_seconds), 0) as avg_duration
                    FROM session_log
                    WHERE started_at >= datetime('now', '-7 days')
                    GROUP BY COALESCE(client_platform, 'web')
                    ORDER BY sessions DESC
                """).fetchall()
                platform_stats = {
                    "platforms": [
                        {
                            "name": r["platform"],
                            "sessions": r["sessions"],
                            "users": r["users"],
                            "avg_accuracy": r["avg_accuracy"],
                            "avg_duration_s": r["avg_duration"],
                        }
                        for r in plat_rows
                    ]
                }
            except sqlite3.OperationalError:
                pass

            return jsonify({
                "total_signups": signups["cnt"] if signups else 0,
                "active_users_7d": active["cnt"] if active else 0,
                "sessions_7d": sessions_week["cnt"] if sessions_week else 0,
                "tier_distribution": {r["subscription_tier"]: r["cnt"] for r in tiers},
                "d1": retention.get("d1", 0),
                "d7": retention.get("d7", 0),
                "d30": retention.get("d30", 0),
                "d1_eligible": retention.get("d1_eligible", 0),
                "d7_eligible": retention.get("d7_eligible", 0),
                "d30_eligible": retention.get("d30_eligible", 0),
                "activation": activation,
                "platform": platform_stats,
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin metrics error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Metrics unavailable"}), 500


@admin_bp.route("/api/admin/users")
@admin_required
@api_error_handler("Users")
def admin_users():
    """User list with last activity."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT u.id, u.email, u.display_name, u.subscription_tier,
                          u.is_admin, u.created_at, u.last_login_at,
                          (SELECT MAX(started_at) FROM session_log WHERE user_id = u.id) as last_session
                   FROM user u
                   ORDER BY u.created_at DESC
                   LIMIT 100"""
            ).fetchall()
            users = []
            for r in rows:
                tier = "admin" if r["is_admin"] else (r["subscription_tier"] or "free")
                users.append({
                    "id": r["id"],
                    "email": r["email"],
                    "display_name": r["display_name"],
                    "tier": tier,
                    "created_at": r["created_at"],
                    "last_login": r["last_login_at"],
                    "last_session": r["last_session"],
                })
            return jsonify({"users": users})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin users error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Users unavailable"}), 500


@admin_bp.route("/api/admin/feedback")
@admin_required
@api_error_handler("Feedback")
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
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin feedback error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Feedback unavailable"}), 500



@admin_bp.route("/api/admin/crashes")
@admin_required
@api_error_handler("Crashes")
def admin_crashes():
    """Server crash log entries."""
    page, per_page, offset, user_id = paginate_params()
    try:
        with db.connection() as conn:
            params = []
            query = (
                "SELECT c.id, c.user_id, c.timestamp, c.error_type,"
                " c.error_message, c.traceback, c.request_method,"
                " c.request_path, c.severity,"
                " u.display_name as user_name"
                " FROM crash_log c"
                " LEFT JOIN user u ON c.user_id = u.id"
                " WHERE c.request_path NOT IN ('/unhandled', '/unhandled/')"
            )
            if user_id:
                query += " AND c.user_id = ?"
                params.append(user_id)
            query += " ORDER BY c.timestamp DESC LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = conn.execute(query, params).fetchall()
            entries = []
            for r in rows:
                entries.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "user_name": r["user_name"],
                    "timestamp": r["timestamp"],
                    "error_type": r["error_type"],
                    "error_message": r["error_message"],
                    "traceback": r["traceback"],
                    "method": r["request_method"],
                    "path": r["request_path"],
                    "severity": r["severity"],
                })
            return jsonify({"crashes": entries, "page": page, "per_page": per_page})
    except sqlite3.OperationalError:
        return jsonify({"crashes": [], "page": page, "per_page": per_page})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin crashes error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Crashes unavailable"}), 500


@admin_bp.route("/api/admin/client-errors")
@admin_required
@api_error_handler("Client errors")
def admin_client_errors():
    """Client-side error log entries."""
    page, per_page, offset, user_id = paginate_params()
    try:
        with db.connection() as conn:
            params = []
            query = (
                "SELECT c.id, c.user_id, c.timestamp, c.error_type,"
                " c.error_message, c.source_file, c.line_number,"
                " c.col_number, c.stack_trace, c.page_url,"
                " u.display_name as user_name"
                " FROM client_error_log c"
                " LEFT JOIN user u ON c.user_id = u.id"
            )
            if user_id:
                query += " WHERE c.user_id = ?"
                params.append(user_id)
            query += " ORDER BY c.timestamp DESC LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = conn.execute(query, params).fetchall()
            entries = []
            for r in rows:
                entries.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "user_name": r["user_name"],
                    "timestamp": r["timestamp"],
                    "error_type": r["error_type"],
                    "error_message": r["error_message"],
                    "source": r["source_file"],
                    "line": r["line_number"],
                    "col": r["col_number"],
                    "stack": r["stack_trace"],
                    "page_url": r["page_url"],
                })
            return jsonify({"errors": entries, "page": page, "per_page": per_page})
    except sqlite3.OperationalError:
        return jsonify({"errors": [], "page": page, "per_page": per_page})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin client errors error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Client errors unavailable"}), 500


@admin_bp.route("/api/admin/sessions")
@admin_required
@api_error_handler("Sessions")
def admin_sessions():
    """Session log with user info."""
    page, per_page, offset, user_id = paginate_params()
    try:
        with db.connection() as conn:
            params = []
            query = (
                "SELECT s.id, s.user_id, s.started_at, s.ended_at,"
                " s.duration_seconds, s.session_type,"
                " s.items_planned, s.items_completed, s.items_correct,"
                " s.session_outcome,"
                " u.display_name as user_name"
                " FROM session_log s"
                " LEFT JOIN user u ON s.user_id = u.id"
            )
            if user_id:
                query += " WHERE s.user_id = ?"
                params.append(user_id)
            query += " ORDER BY s.started_at DESC LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = conn.execute(query, params).fetchall()
            entries = []
            for r in rows:
                completed = r["items_completed"] or 0
                correct = r["items_correct"] or 0
                accuracy = round(correct / completed * 100, 1) if completed > 0 else None
                entries.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "user_name": r["user_name"],
                    "started_at": r["started_at"],
                    "ended_at": r["ended_at"],
                    "duration": r["duration_seconds"],
                    "type": r["session_type"],
                    "items_planned": r["items_planned"],
                    "items_completed": r["items_completed"],
                    "items_correct": r["items_correct"],
                    "accuracy": accuracy,
                    "outcome": r["session_outcome"],
                })
            return jsonify({"sessions": entries, "page": page, "per_page": per_page})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin sessions error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Sessions unavailable"}), 500


@admin_bp.route("/api/admin/security-events")
@admin_required
@api_error_handler("Security events")
def admin_security_events():
    """Security audit log entries."""
    page, per_page, offset, user_id = paginate_params()
    try:
        with db.connection() as conn:
            params = []
            query = (
                "SELECT s.id, s.timestamp, s.event_type, s.user_id,"
                " s.ip_address, s.user_agent, s.details, s.severity,"
                " u.display_name as user_name"
                " FROM security_audit_log s"
                " LEFT JOIN user u ON s.user_id = u.id"
            )
            if user_id:
                query += " WHERE s.user_id = ?"
                params.append(user_id)
            query += " ORDER BY s.timestamp DESC LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = conn.execute(query, params).fetchall()
            entries = []
            for r in rows:
                entries.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "event_type": r["event_type"],
                    "user_id": r["user_id"],
                    "user_name": r["user_name"],
                    "ip": r["ip_address"],
                    "severity": r["severity"],
                    "details": r["details"],
                })
            return jsonify({"events": entries, "page": page, "per_page": per_page})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin security events error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Security events unavailable"}), 500


@admin_bp.route("/api/admin/security-scans")
@admin_required
@api_error_handler("Security scans")
def admin_security_scans():
    """Security scan history."""
    try:
        from ..security_scanner import get_scan_history
        with db.connection() as conn:
            scans = get_scan_history(conn)
        return jsonify({"scans": scans})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin security scans error: %s", e)
        return jsonify({"error": "Security scans unavailable"}), 500


@admin_bp.route("/api/admin/security-scans/trigger", methods=["POST"])
@admin_required
@api_error_handler("Trigger security scan")
def admin_trigger_security_scan():
    """Manually trigger a full security scan."""
    try:
        from ..security_scanner import run_full_scan
        with db.connection() as conn:
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details="triggered security scan",
                               severity=Severity.INFO)
            results = run_full_scan(conn)
        return jsonify({"status": "completed", "results": results})
    except Exception as e:
        logger.error("Admin trigger scan error: %s", e)
        return jsonify({"error": "Scan failed: " + str(e)}), 500


@admin_bp.route("/api/admin/security-scans/<int:scan_id>")
@admin_required
@api_error_handler("Security scan detail")
def admin_security_scan_detail(scan_id):
    """Full detail for a single scan with findings."""
    try:
        with db.connection() as conn:
            scan = conn.execute(
                "SELECT * FROM security_scan WHERE id = ?", (scan_id,)
            ).fetchone()
            if not scan:
                return jsonify({"error": "Scan not found"}), 404
            scan_dict = dict(scan)
            findings = conn.execute(
                "SELECT * FROM security_scan_finding WHERE scan_id = ? ORDER BY severity, title",
                (scan_id,),
            ).fetchall()
            scan_dict["findings"] = [dict(f) for f in findings]
        return jsonify(scan_dict)
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin scan detail error: %s", e)
        return jsonify({"error": "Scan detail unavailable"}), 500


# ---------------------------------------------------------------------------
# Quality Metrics Endpoints
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/quality/dpmo")
@admin_required
@api_error_handler("Quality DPMO")
def admin_quality_dpmo():
    """DPMO and sigma level metrics."""
    try:
        from ..quality.dpmo import calculate_dpmo, get_dpmo_trend
        with db.connection() as conn:
            current = calculate_dpmo(conn, days=30)
            trend = get_dpmo_trend(conn, periods=12, period_days=7)
        return jsonify({"current": current, "trend": trend})
    except (sqlite3.Error, ImportError) as e:
        logger.error("Quality DPMO error: %s", e)
        return jsonify({"error": "DPMO unavailable"}), 500


@admin_bp.route("/api/admin/quality/spc")
@admin_required
@api_error_handler("Quality SPC")
def admin_quality_spc():
    """SPC control chart data."""
    chart_type = request.args.get("chart", "drill_accuracy")
    days = int(request.args.get("days", "30"))
    try:
        from ..quality.spc import get_spc_chart_data
        with db.connection() as conn:
            data = get_spc_chart_data(conn, chart_type, days=days)
        return jsonify(data)
    except (sqlite3.Error, ImportError, ValueError) as e:
        logger.error("Quality SPC error: %s", e)
        return jsonify({"error": "SPC data unavailable"}), 500


@admin_bp.route("/api/admin/quality/capability")
@admin_required
@api_error_handler("Quality capability")
def admin_quality_capability():
    """Process capability metrics."""
    try:
        from ..quality.capability import get_capability_summary
        with db.connection() as conn:
            data = get_capability_summary(conn)
        return jsonify(data)
    except (sqlite3.Error, ImportError) as e:
        logger.error("Quality capability error: %s", e)
        return jsonify({"error": "Capability data unavailable"}), 500


@admin_bp.route("/api/admin/quality/retention-analysis")
@admin_required
@api_error_handler("Quality retention")
def admin_quality_retention():
    """Survival analysis for learner retention."""
    try:
        from ..quality.retention import kaplan_meier, churn_risk_factors
        with db.connection() as conn:
            km = kaplan_meier(conn)
            risks = churn_risk_factors(conn)
        return jsonify({"survival": km, "risk_factors": risks})
    except (sqlite3.Error, ImportError) as e:
        logger.error("Quality retention error: %s", e)
        return jsonify({"error": "Retention analysis unavailable"}), 500


@admin_bp.route("/api/admin/quality/flow")
@admin_required
@api_error_handler("Quality flow")
def admin_quality_flow():
    """Kanban flow metrics."""
    try:
        from ..quality.flow_metrics import get_flow_summary, get_cfd_data
        with db.connection() as conn:
            summary = get_flow_summary(conn)
            cfd = get_cfd_data(conn)
        return jsonify({"summary": summary, "cfd": cfd})
    except (sqlite3.Error, ImportError) as e:
        logger.error("Quality flow error: %s", e)
        return jsonify({"error": "Flow metrics unavailable"}), 500


@admin_bp.route("/api/admin/quality/monte-carlo")
@admin_required
@api_error_handler("Quality Monte Carlo")
def admin_quality_monte_carlo():
    """Monte Carlo simulation results."""
    try:
        from ..quality.monte_carlo import simulate_user_growth, simulate_server_load
        with db.connection() as conn:
            growth = simulate_user_growth(conn, months=12, n_simulations=1000)
            load = simulate_server_load(conn, target_users=1000, n_simulations=1000)
        return jsonify({"growth": growth, "server_load": load})
    except (sqlite3.Error, ImportError) as e:
        logger.error("Quality Monte Carlo error: %s", e)
        return jsonify({"error": "Monte Carlo unavailable"}), 500


# ---------------------------------------------------------------------------
# DMAIC Project Log (via improvement_log table)
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/quality/dmaic")
@admin_required
@api_error_handler("DMAIC log")
def admin_dmaic_log():
    """View improvement_log entries as a DMAIC project log.

    Maps improvement_log fields to DMAIC phases:
      proposed → Define/Measure, approved → Analyze,
      applied → Improve, rolled_back/rejected → Control feedback.
    """
    try:
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT id, trigger_reason, observation, proposed_change,
                       status, created_at, applied_at, rolled_back_at
                FROM improvement_log
                ORDER BY created_at DESC
                LIMIT 100
            """).fetchall()

            projects = []
            for r in rows:
                status = r["status"]
                if status == "proposed":
                    phase = "define"
                elif status == "approved":
                    phase = "analyze"
                elif status == "applied":
                    phase = "improve"
                elif status in ("rolled_back", "rejected"):
                    phase = "control"
                else:
                    phase = "define"

                projects.append({
                    "id": r["id"],
                    "title": r["trigger_reason"],
                    "phase": phase,
                    "observation": r["observation"],
                    "proposed_change": r["proposed_change"],
                    "status": status,
                    "created_at": r["created_at"],
                    "applied_at": r["applied_at"],
                    "rolled_back_at": r["rolled_back_at"],
                })
        return jsonify({"projects": projects})
    except sqlite3.OperationalError:
        return jsonify({"projects": []})


# ---------------------------------------------------------------------------
# Risk Auto-Mitigation: create work items from high-risk items
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/risks/<int:risk_id>/create-mitigation", methods=["POST"])
@admin_required
@api_error_handler("Create risk mitigation")
def admin_create_risk_mitigation(risk_id):
    """Create a work item to mitigate a specific risk."""
    try:
        with db.connection() as conn:
            risk = conn.execute(
                "SELECT * FROM risk_item WHERE id = ?", (risk_id,)
            ).fetchone()
            if not risk:
                return jsonify({"error": "Risk not found"}), 404

            risk_score = (risk["probability"] or 3) * (risk["impact"] or 3)
            service_class = "expedite" if risk_score >= 20 else "standard"

            cur = conn.execute(
                """INSERT INTO work_item
                   (title, description, item_type, status, service_class, ready_at)
                   VALUES (?, ?, 'standard', 'ready', ?, datetime('now'))""",
                (
                    f"Mitigate risk: {risk['title']}",
                    f"Auto-created from risk_item #{risk_id} (score: {risk_score})\n"
                    f"Category: {risk['category']}\n"
                    f"Risk: {risk['description'] or risk['title']}\n"
                    f"Proposed mitigation: {risk['mitigation'] or 'TBD'}\n"
                    f"- [ ] Implement mitigation\n"
                    f"- [ ] Verify risk reduced\n"
                    f"- [ ] Update risk register",
                    service_class,
                ),
            )
            conn.commit()
        return jsonify({"work_item_id": cur.lastrowid, "status": "created"}), 201
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Create risk mitigation error: %s", e)
        return jsonify({"error": "Failed to create mitigation"}), 500


# ---------------------------------------------------------------------------
# Risk Management CRUD
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/risks")
@admin_required
@api_error_handler("Risk register")
def admin_risks():
    """List all active risks."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT id, category, title, description, probability, impact,
                          (probability * impact) as risk_score,
                          mitigation, contingency, status, owner,
                          created_at, updated_at
                   FROM risk_item
                   WHERE status != 'retired'
                   ORDER BY (probability * impact) DESC, created_at DESC"""
            ).fetchall()
            risks = [dict(r) for r in rows]
        return jsonify({"risks": risks})
    except sqlite3.OperationalError:
        return jsonify({"risks": []})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Risk register error: %s", e)
        return jsonify({"error": "Risk register unavailable"}), 500


@admin_bp.route("/api/admin/risks", methods=["POST"])
@admin_required
@api_error_handler("Create risk")
def admin_create_risk():
    """Add a new risk to the register."""
    data = request.get_json()
    if not data or not data.get("title") or not data.get("category"):
        return jsonify({"error": "title and category required"}), 400
    try:
        with db.connection() as conn:
            cur = conn.execute(
                """INSERT INTO risk_item (category, title, description, probability, impact,
                                          mitigation, contingency, status, owner)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["category"], data["title"], data.get("description", ""),
                 data.get("probability", 3), data.get("impact", 3),
                 data.get("mitigation", ""), data.get("contingency", ""),
                 data.get("status", "active"), data.get("owner", ""))
            )
            conn.commit()
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"created risk: {data['title']}")
        return jsonify({"id": cur.lastrowid, "status": "created"}), 201
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Create risk error: %s", e)
        return jsonify({"error": "Failed to create risk"}), 500


@admin_bp.route("/api/admin/risks/<int:risk_id>", methods=["PUT"])
@admin_required
@api_error_handler("Update risk")
def admin_update_risk(risk_id):
    """Update an existing risk."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        fields = []
        values = []
        for col in ("category", "title", "description", "probability", "impact",
                     "mitigation", "contingency", "status", "owner"):
            if col in data and col in _RISK_ALLOWED_FIELDS:
                fields.append(f"{col} = ?")
                values.append(data[col])
        if not fields:
            return jsonify({"error": "No fields to update"}), 400
        fields.append("updated_at = datetime('now')")
        values.append(risk_id)
        with db.connection() as conn:
            conn.execute(f"UPDATE risk_item SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        return jsonify({"status": "updated"})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Update risk error: %s", e)
        return jsonify({"error": "Failed to update risk"}), 500


def _parse_acceptance_criteria(description: str) -> dict:
    """Parse acceptance criteria from description lines starting with '- [ ]' or '- [x]'.

    Returns {total, completed, items: [{text, done}]}.
    """
    if not description:
        return {"total": 0, "completed": 0, "items": []}
    items = []
    for line in description.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            items.append({"text": stripped[5:].strip(), "done": True})
        elif stripped.startswith("- [ ]"):
            items.append({"text": stripped[5:].strip(), "done": False})
    completed = sum(1 for i in items if i["done"])
    return {"total": len(items), "completed": completed, "items": items}


def _suggest_next_pull(conn):
    """Suggest the next work item to pull from 'ready' based on service class priority.

    Priority order: expedite > fixed_date > standard > intangible.
    Returns dict with suggested item or None.
    """
    SERVICE_CLASS_PRIORITY = {
        "expedite": 1, "fixed_date": 2, "standard": 3, "intangible": 4,
    }
    try:
        rows = conn.execute(
            """SELECT id, title, COALESCE(service_class, 'standard') AS service_class,
                      estimate, created_at
               FROM work_item WHERE status = 'ready'
               ORDER BY created_at ASC"""
        ).fetchall()
        if not rows:
            return None
        # Sort by service class priority, then by creation date
        items = [dict(r) for r in rows]
        items.sort(key=lambda x: (
            SERVICE_CLASS_PRIORITY.get(x["service_class"], 99),
            x["created_at"] or "",
        ))
        best = items[0]
        return {
            "id": best["id"],
            "title": best["title"],
            "service_class": best["service_class"],
            "estimate": best.get("estimate"),
            "message": f"Suggested next pull: \"{best['title']}\" ({best['service_class']})",
        }
    except Exception:
        return None


@admin_bp.route("/api/admin/work-items")
@admin_required
@api_error_handler("Work items")
def admin_work_items():
    """List work items for Kanban board with acceptance criteria."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT id, title, description, item_type, status,
                          created_at, ready_at, started_at, completed_at,
                          blocked_at, unblocked_at,
                          COALESCE(service_class, 'standard') AS service_class,
                          review_at, estimate, implementation_type, blocked_reason
                   FROM work_item
                   ORDER BY
                     CASE status
                       WHEN 'in_progress' THEN 1
                       WHEN 'blocked' THEN 2
                       WHEN 'review' THEN 3
                       WHEN 'ready' THEN 4
                       WHEN 'backlog' THEN 5
                       WHEN 'done' THEN 6
                     END,
                     created_at DESC"""
            ).fetchall()
            items = []
            for r in rows:
                item = dict(r)
                item["acceptance_criteria"] = _parse_acceptance_criteria(item.get("description") or "")
                # Age in days for started items
                if item.get("started_at") and item["status"] in ("in_progress", "review"):
                    try:
                        from datetime import datetime as _dt
                        started = _dt.fromisoformat(item["started_at"])
                        age = (_dt.now(timezone.utc) - started.replace(tzinfo=timezone.utc)).days
                        item["age_days"] = age
                    except Exception:
                        item["age_days"] = None
                items.append(item)
        return jsonify({"items": items})
    except sqlite3.OperationalError:
        return jsonify({"items": []})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Work items error: %s", e)
        return jsonify({"error": "Work items unavailable"}), 500


@admin_bp.route("/api/admin/work-items", methods=["POST"])
@admin_required
@api_error_handler("Create work item")
def admin_create_work_item():
    """Create a new work item with optional service class, estimate, implementation_type."""
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "title required"}), 400
    try:
        with db.connection() as conn:
            cur = conn.execute(
                """INSERT INTO work_item
                   (title, description, item_type, status, service_class, estimate, implementation_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (data["title"], data.get("description", ""),
                 data.get("item_type", "standard"), data.get("status", "backlog"),
                 data.get("service_class", "standard"),
                 data.get("estimate"),  # S/M/L/XL or NULL
                 data.get("implementation_type"))  # prototype/full or NULL
            )
            conn.commit()
        return jsonify({"id": cur.lastrowid, "status": "created"}), 201
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Create work item error: %s", e)
        return jsonify({"error": "Failed to create work item"}), 500


@admin_bp.route("/api/admin/work-items/<int:item_id>", methods=["PUT"])
@admin_required
@api_error_handler("Update work item")
def admin_update_work_item(item_id):
    """Update work item status (auto-sets timestamps, enforces WIP limits)."""
    WIP_LIMIT_IN_PROGRESS = 5
    ESTIMATE_POINTS = {"S": 1, "M": 3, "L": 5, "XL": 8}

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        with db.connection() as conn:
            # Get current status
            current = conn.execute(
                "SELECT status, implementation_type FROM work_item WHERE id = ?", (item_id,)
            ).fetchone()
            if not current:
                return jsonify({"error": "Work item not found"}), 404

            new_status = data.get("status", current["status"])
            old_status = current["status"]

            # WIP limit enforcement: reject when moving to in_progress (unless force)
            wip_warning = None
            if new_status == "in_progress" and old_status != "in_progress":
                wip_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM work_item WHERE status = 'in_progress'"
                ).fetchone()["cnt"]
                if wip_count >= WIP_LIMIT_IN_PROGRESS:
                    force = data.get("force", False)
                    force_reason = data.get("force_reason", "")
                    if not force:
                        return jsonify({
                            "error": "WIP limit reached. Complete or move an existing item before starting new work.",
                            "wip_count": wip_count,
                            "wip_limit": WIP_LIMIT_IN_PROGRESS,
                        }), 409
                    # Force override — log the reason
                    logger.warning(
                        "WIP limit override for item %d: %d items in progress (limit %d). Reason: %s",
                        item_id, wip_count, WIP_LIMIT_IN_PROGRESS, force_reason or "none given"
                    )
                    wip_warning = (
                        f"WIP limit overridden: {wip_count + 1} items in progress "
                        f"(limit: {WIP_LIMIT_IN_PROGRESS}). Reason: {force_reason or 'none given'}"
                    )

            updates = []
            values = []

            for col in ("title", "description", "item_type", "status",
                         "service_class", "estimate", "implementation_type"):
                if col in data and col in _WORK_ITEM_ALLOWED_FIELDS:
                    updates.append(f"{col} = ?")
                    values.append(data[col])

            # Blocked work visibility: when moving to blocked, record reason + timestamp
            if new_status == "blocked" and old_status != "blocked":
                updates.append("blocked_at = datetime('now')")
                if data.get("blocked_reason"):
                    updates.append("blocked_reason = ?")
                    values.append(data["blocked_reason"])
            # When unblocking, record unblocked_at and clear blocked_reason
            if old_status == "blocked" and new_status != "blocked":
                updates.append("unblocked_at = datetime('now')")

            # Auto-set timestamps based on status transitions
            if new_status != old_status:
                if new_status == "ready" and not data.get("ready_at"):
                    updates.append("ready_at = datetime('now')")
                if new_status == "in_progress" and not data.get("started_at"):
                    updates.append("started_at = datetime('now')")
                if new_status == "review":
                    updates.append("review_at = datetime('now')")
                if new_status == "done" and not data.get("completed_at"):
                    updates.append("completed_at = datetime('now')")

            if not updates:
                return jsonify({"error": "No fields to update"}), 400

            values.append(item_id)
            conn.execute(f"UPDATE work_item SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()

            # Pull system suggestion: after marking done, suggest next item to pull
            pull_suggestion = None
            if new_status == "done" and old_status != "done":
                pull_suggestion = _suggest_next_pull(conn)

            # Prototype tracking: when a prototype is marked done, prompt for evaluation
            prototype_prompt = None
            if new_status == "done" and (current["implementation_type"] or data.get("implementation_type")) == "prototype":
                prototype_prompt = {
                    "message": "Prototype complete. Evaluate outcome: promote to full, discard, or iterate.",
                    "options": ["promote", "discard", "iterate"],
                }

        result = {"status": "updated"}
        if wip_warning:
            result["wip_warning"] = wip_warning
        if pull_suggestion:
            result["pull_suggestion"] = pull_suggestion
        if prototype_prompt:
            result["prototype_prompt"] = prototype_prompt
        return jsonify(result)
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Update work item error: %s", e)
        return jsonify({"error": "Failed to update work item"}), 500


@admin_bp.route("/api/admin/revenue")
@admin_required
@api_error_handler("Revenue")
def admin_revenue():
    """Revenue metrics: MRR, channel breakdown, conversion, churn, LTV."""
    try:
        with db.connection() as conn:
            # Tier counts
            tiers = conn.execute(
                "SELECT subscription_tier, COUNT(*) as cnt FROM user GROUP BY subscription_tier"
            ).fetchall()
            tier_map = {r["subscription_tier"]: r["cnt"] for r in tiers}

            paid_count = tier_map.get("paid", 0)
            teacher_count = tier_map.get("teacher", 0)
            free_count = tier_map.get("free", 0)
            total_users = sum(tier_map.values())

            # NOTE: Estimated MRR — derived from tier counts × list price.
            # This is NOT Stripe-verified revenue. Discounts, failed charges,
            # prorations, and refunds are not reflected here.
            mrr = round((paid_count + teacher_count) * _MONTHLY_PRICE, 2)

            # Channel revenue breakdown
            channel_revenue = {
                "individual_monthly": round(paid_count * _MONTHLY_PRICE, 2),
                "teacher": round(teacher_count * _MONTHLY_PRICE, 2),
            }

            # Conversion rate: paid / total
            conversion_rate = round(
                (paid_count + teacher_count) / total_users * 100, 1
            ) if total_users > 0 else 0

            # Churn rate: cancellations in last 30d / paying users at start of period
            churn_count_row = conn.execute(
                """SELECT COUNT(DISTINCT user_id) as cnt
                   FROM lifecycle_event
                   WHERE event_type = 'cancellation_completed'
                     AND created_at >= datetime('now', '-30 days')"""
            ).fetchone()
            churn_count = churn_count_row["cnt"] if churn_count_row else 0
            paying_base = paid_count + teacher_count + churn_count
            churn_rate = round(
                churn_count / paying_base * 100, 1
            ) if paying_base > 0 else 0

            # Estimated LTV: MRR per user / monthly churn rate
            monthly_churn_decimal = churn_rate / 100 if churn_rate > 0 else 0.05
            arpu = mrr / (paid_count + teacher_count) if (paid_count + teacher_count) > 0 else _MONTHLY_PRICE
            ltv = round(arpu / monthly_churn_decimal, 2) if monthly_churn_decimal > 0 else 0

            # ARR
            arr = round(mrr * 12, 2)

            # Trailing 3-month MRR trend (estimated from tier counts by signup month)
            mrr_trend = []
            trend_rows = conn.execute(
                """SELECT strftime('%Y-%m', created_at) as month,
                          SUM(CASE WHEN subscription_tier IN ('paid', 'teacher') THEN 1 ELSE 0 END) as paying
                   FROM user
                   WHERE created_at >= datetime('now', '-3 months')
                   GROUP BY month
                   ORDER BY month"""
            ).fetchall()
            for row in trend_rows:
                month_mrr = round((row["paying"] or 0) * _MONTHLY_PRICE, 2)
                mrr_trend.append({"month": row["month"], "mrr": month_mrr})

            # Net revenue: MRR minus estimated operating costs
            paying_users = paid_count + teacher_count
            # Stripe fees: percentage + fixed per transaction
            stripe_fees = round(paying_users * (_MONTHLY_PRICE * STRIPE_FEE_PERCENT + _STRIPE_FEE_FIXED), 2) if paying_users > 0 else 0.0
            total_costs = round(HOSTING_COST_MONTHLY + stripe_fees, 2)
            net_revenue = round(mrr - total_costs, 2)

            return jsonify({
                "mrr": mrr,
                "arr": arr,
                "revenue_source": "estimated_from_tiers",
                "paid_users": paid_count,
                "teacher_users": teacher_count,
                "free_users": free_count,
                "total_users": total_users,
                "channel_revenue": channel_revenue,
                "conversion_rate": conversion_rate,
                "churn_rate": churn_rate,
                "churn_count_30d": churn_count,
                "estimated_ltv": ltv,
                "mrr_trend_3mo": mrr_trend,
                "cost_breakdown": {
                    "hosting": hosting_cost,
                    "stripe_fees": stripe_fees,
                    "total": total_costs,
                },
                "net_revenue": net_revenue,
            })
    except (sqlite3.Error, KeyError, TypeError, ZeroDivisionError) as e:
        logger.error("Admin revenue error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Revenue metrics unavailable"}), 500


@admin_bp.route("/api/admin/retention-cohorts")
@admin_required
@api_error_handler("Retention cohorts")
def admin_retention_cohorts():
    """Weekly signup cohorts with W1-W12 retention percentages."""
    try:
        with db.connection() as conn:
            # Get weekly cohorts (last 12 weeks of signups)
            cohorts = conn.execute(
                """SELECT
                     strftime('%Y-W%W', created_at) as cohort_week,
                     MIN(date(created_at)) as week_start,
                     COUNT(*) as cohort_size
                   FROM user
                   WHERE created_at >= date('now', '-84 days')
                   GROUP BY cohort_week
                   ORDER BY cohort_week"""
            ).fetchall()

            result = []
            for cohort in cohorts:
                week_label = cohort["cohort_week"]
                week_start = cohort["week_start"]
                size = cohort["cohort_size"]

                # For each week W1-W12, count users who had a session
                retention = {}
                for w in range(1, 13):
                    day_start = (w - 1) * 7
                    day_end = w * 7
                    active_row = conn.execute(
                        """SELECT COUNT(DISTINCT sl.user_id) as cnt
                           FROM session_log sl
                           JOIN user u ON u.id = sl.user_id
                           WHERE strftime('%%Y-W%%W', u.created_at) = ?
                             AND sl.items_completed > 0
                             AND sl.started_at >= date(?, '+' || ? || ' days')
                             AND sl.started_at < date(?, '+' || ? || ' days')""",
                        (week_label, week_start, str(day_start), week_start, str(day_end))
                    ).fetchone()
                    active = active_row["cnt"] if active_row else 0
                    retention["w" + str(w)] = round(active / size * 100, 1) if size > 0 else 0

                result.append({
                    "cohort": week_label,
                    "week_start": week_start,
                    "size": size,
                    "retention": retention,
                })

            return jsonify({"cohorts": result})
    except (sqlite3.Error, KeyError, TypeError, ZeroDivisionError) as e:
        logger.error("Admin retention cohorts error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Retention cohorts unavailable"}), 500


@admin_bp.route("/api/admin/engagement")
@admin_required
@api_error_handler("Engagement")
def admin_engagement():
    """Engagement analytics: daily sessions, sessions per active user, top error types."""
    try:
        with db.connection() as conn:
            # Daily sessions for last 30 days
            daily_rows = conn.execute(
                """SELECT date(started_at) as day,
                          COUNT(*) as total_sessions,
                          COUNT(DISTINCT user_id) as unique_users
                   FROM session_log
                   WHERE started_at >= date('now', '-30 days')
                   GROUP BY day
                   ORDER BY day"""
            ).fetchall()

            daily_sessions = []
            total_sessions_sum = 0
            total_active_days = 0
            for r in daily_rows:
                unique = r["unique_users"] or 0
                total = r["total_sessions"] or 0
                spu = round(total / unique, 2) if unique > 0 else 0
                daily_sessions.append({
                    "date": r["day"],
                    "total_sessions": total,
                    "unique_users": unique,
                    "sessions_per_user": spu,
                })
                total_sessions_sum += total
                if unique > 0:
                    total_active_days += 1

            # Overall avg sessions per active user per day
            if total_active_days > 0 and daily_sessions:
                total_unique_user_days = sum(d["unique_users"] for d in daily_sessions)
                avg_spu = round(total_sessions_sum / total_unique_user_days, 2) if total_unique_user_days > 0 else 0
            else:
                avg_spu = 0

            # Top error types (aggregate across all users) from error_focus
            error_rows = conn.execute(
                """SELECT error_type,
                          SUM(error_count) as total_count
                   FROM error_focus
                   WHERE resolved = 0
                   GROUP BY error_type
                   ORDER BY total_count DESC
                   LIMIT 20"""
            ).fetchall()

            top_errors = []
            for r in error_rows:
                error_type = r["error_type"]
                total_count = r["total_count"] or 0

                # 7-day trend: compare last 7d errors to previous 7d
                recent_row = conn.execute(
                    """SELECT SUM(error_count) as cnt FROM error_focus
                       WHERE error_type = ? AND last_error_at >= date('now', '-7 days')""",
                    (error_type,)
                ).fetchone()
                prev_row = conn.execute(
                    """SELECT SUM(error_count) as cnt FROM error_focus
                       WHERE error_type = ?
                         AND last_error_at >= date('now', '-14 days')
                         AND last_error_at < date('now', '-7 days')""",
                    (error_type,)
                ).fetchone()
                recent = (recent_row["cnt"] or 0) if recent_row else 0
                prev = (prev_row["cnt"] or 0) if prev_row else 0

                if recent > prev:
                    trend = "up"
                elif recent < prev:
                    trend = "down"
                else:
                    trend = "flat"

                top_errors.append({
                    "error_type": error_type,
                    "count": total_count,
                    "recent_7d": recent,
                    "prev_7d": prev,
                    "trend": trend,
                })

            # Also include crash_log aggregate error types
            crash_error_rows = conn.execute(
                """SELECT error_type,
                          COUNT(*) as total_count
                   FROM crash_log
                   GROUP BY error_type
                   ORDER BY total_count DESC
                   LIMIT 10"""
            ).fetchall()

            crash_errors = []
            for r in crash_error_rows:
                error_type = r["error_type"]
                total_count = r["total_count"] or 0

                recent_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM crash_log
                       WHERE error_type = ? AND timestamp >= date('now', '-7 days')""",
                    (error_type,)
                ).fetchone()
                prev_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM crash_log
                       WHERE error_type = ?
                         AND timestamp >= date('now', '-14 days')
                         AND timestamp < date('now', '-7 days')""",
                    (error_type,)
                ).fetchone()
                recent = (recent_row["cnt"] or 0) if recent_row else 0
                prev = (prev_row["cnt"] or 0) if prev_row else 0

                if recent > prev:
                    trend = "up"
                elif recent < prev:
                    trend = "down"
                else:
                    trend = "flat"

                crash_errors.append({
                    "error_type": error_type,
                    "count": total_count,
                    "recent_7d": recent,
                    "prev_7d": prev,
                    "trend": trend,
                    "source": "crash_log",
                })

            return jsonify({
                "daily_sessions": daily_sessions,
                "avg_sessions_per_active_user": avg_spu,
                "top_error_types": top_errors,
                "top_crash_types": crash_errors,
            })
    except sqlite3.OperationalError as e:
        logger.debug("Engagement query unavailable: %s", e)
        return jsonify({
            "daily_sessions": [],
            "avg_sessions_per_active_user": 0,
            "top_error_types": [],
            "top_crash_types": [],
        })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin engagement error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Engagement metrics unavailable"}), 500


@admin_bp.route("/api/admin/partners")
@admin_required
@api_error_handler("Partners")
def admin_partners():
    """Partner attribution: signups, activations, paid conversions, sessions by partner."""
    try:
        with db.connection() as conn:
            # Get all affiliate partners with their referral stats
            partner_rows = conn.execute(
                """SELECT ap.partner_code, ap.partner_name, ap.partner_email,
                          ap.commission_rate, ap.tier, ap.status,
                          ap.created_at,
                          COUNT(rt.id) as total_referrals,
                          SUM(CASE WHEN rt.signed_up = 1 THEN 1 ELSE 0 END) as signups,
                          SUM(CASE WHEN rt.converted_to_paid = 1 THEN 1 ELSE 0 END) as paid_conversions
                   FROM affiliate_partner ap
                   LEFT JOIN referral_tracking rt ON rt.partner_code = ap.partner_code
                   GROUP BY ap.partner_code
                   ORDER BY signups DESC"""
            ).fetchall()

            partners = []
            for r in partner_rows:
                partner_code = r["partner_code"]

                # Count activated users (users who signed up via this partner and activated)
                # We match via utm_source on user table
                activated_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM user
                       WHERE utm_source = ? AND activation_at IS NOT NULL""",
                    (partner_code,)
                ).fetchone()
                activated = (activated_row["cnt"] or 0) if activated_row else 0

                # Total sessions by users attributed to this partner
                sessions_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM session_log sl
                       JOIN user u ON sl.user_id = u.id
                       WHERE u.utm_source = ?""",
                    (partner_code,)
                ).fetchone()
                total_sessions = (sessions_row["cnt"] or 0) if sessions_row else 0

                # Total commissions earned
                commission_row = conn.execute(
                    """SELECT SUM(amount) as total, COUNT(*) as cnt
                       FROM affiliate_commission
                       WHERE partner_code = ?""",
                    (partner_code,)
                ).fetchone()
                total_commission = round(commission_row["total"] or 0, 2) if commission_row else 0
                commission_count = (commission_row["cnt"] or 0) if commission_row else 0

                partners.append({
                    "partner_code": partner_code,
                    "partner_name": r["partner_name"],
                    "partner_email": r["partner_email"],
                    "commission_rate": r["commission_rate"],
                    "tier": r["tier"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "total_referrals": r["total_referrals"] or 0,
                    "signups": r["signups"] or 0,
                    "activated": activated,
                    "paid_conversions": r["paid_conversions"] or 0,
                    "total_sessions": total_sessions,
                    "total_commission": total_commission,
                    "commission_count": commission_count,
                })

            # Also include utm_source-based attribution for non-affiliate partners
            utm_rows = conn.execute(
                """SELECT utm_source,
                          COUNT(*) as signups,
                          SUM(CASE WHEN activation_at IS NOT NULL THEN 1 ELSE 0 END) as activated,
                          SUM(CASE WHEN subscription_tier IN ('paid', 'teacher') THEN 1 ELSE 0 END) as paid
                   FROM user
                   WHERE utm_source IS NOT NULL
                     AND utm_source NOT IN (SELECT partner_code FROM affiliate_partner)
                   GROUP BY utm_source
                   ORDER BY signups DESC
                   LIMIT 20"""
            ).fetchall()

            utm_sources = []
            for r in utm_rows:
                source = r["utm_source"]
                # Total sessions by users from this source
                sessions_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM session_log sl
                       JOIN user u ON sl.user_id = u.id
                       WHERE u.utm_source = ?""",
                    (source,)
                ).fetchone()
                total_sessions = (sessions_row["cnt"] or 0) if sessions_row else 0

                utm_sources.append({
                    "source": source,
                    "signups": r["signups"] or 0,
                    "activated": r["activated"] or 0,
                    "paid": r["paid"] or 0,
                    "total_sessions": total_sessions,
                })

            return jsonify({
                "partners": partners,
                "utm_sources": utm_sources,
            })
    except sqlite3.OperationalError as e:
        logger.debug("Partners query unavailable: %s", e)
        return jsonify({"partners": [], "utm_sources": []})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin partners error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Partner data unavailable"}), 500


@admin_bp.route("/api/admin/thread-health")
@admin_required
@api_error_handler("Thread health")
def admin_thread_health():
    """Background thread health status — scheduler locks, thread states."""
    import threading

    # Enumerate all known background threads
    threads = []
    for t in threading.enumerate():
        if t.name in ("email-scheduler", "retention-purge", "stale-session-cleanup", "edge-tts", "quality-metrics", "security-scan"):
            threads.append({
                "name": t.name,
                "alive": t.is_alive(),
                "daemon": t.daemon,
            })

    # Check scheduler lock status
    locks = []
    try:
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT name, locked_by, locked_at, expires_at FROM scheduler_lock"
            ).fetchall()
            for r in rows:
                locks.append({
                    "name": r["name"],
                    "locked_by": r["locked_by"],
                    "locked_at": r["locked_at"],
                    "expires_at": r["expires_at"],
                })
    except sqlite3.OperationalError:
        pass  # Table may not exist yet

    return jsonify({"threads": threads, "scheduler_locks": locks})


@admin_bp.route("/api/admin/telemetry-health")
@admin_required
@api_error_handler("Telemetry health")
def admin_telemetry_health():
    """Telemetry health dashboard — event volume, top categories, dedup stats."""
    try:
        with db.connection() as conn:
            # Total events in last 24h / 7d / 30d
            windows = {}
            for label, interval in [("24h", "-1 day"), ("7d", "-7 days"), ("30d", "-30 days")]:
                row = conn.execute(
                    "SELECT COUNT(*) FROM client_event WHERE created_at > datetime('now', ?)",
                    (interval,),
                ).fetchone()
                windows[label] = row[0] if row else 0

            # Top categories (last 7 days)
            cat_rows = conn.execute(
                """SELECT category, COUNT(*) as cnt
                   FROM client_event WHERE created_at > datetime('now', '-7 days')
                   GROUP BY category ORDER BY cnt DESC LIMIT 15"""
            ).fetchall()
            top_categories = [{"category": r[0], "count": r[1]} for r in cat_rows]

            # Top events (last 7 days)
            evt_rows = conn.execute(
                """SELECT category, event, COUNT(*) as cnt
                   FROM client_event WHERE created_at > datetime('now', '-7 days')
                   GROUP BY category, event ORDER BY cnt DESC LIMIT 20"""
            ).fetchall()
            top_events = [{"category": r[0], "event": r[1], "count": r[2]} for r in evt_rows]

            # Unique install_ids in last 7 days
            installs = conn.execute(
                """SELECT COUNT(DISTINCT install_id) FROM client_event
                   WHERE created_at > datetime('now', '-7 days') AND install_id IS NOT NULL"""
            ).fetchone()[0]

            # Events with event_id (dedup-capable) vs without
            dedup_row = conn.execute(
                """SELECT
                     SUM(CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) as with_id,
                     SUM(CASE WHEN event_id IS NULL THEN 1 ELSE 0 END) as without_id
                   FROM client_event WHERE created_at > datetime('now', '-7 days')"""
            ).fetchone()
            dedup_stats = {
                "with_event_id": dedup_row[0] or 0 if dedup_row else 0,
                "without_event_id": dedup_row[1] or 0 if dedup_row else 0,
            }

            # Hourly volume (last 24h)
            hourly_rows = conn.execute(
                """SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
                   FROM client_event WHERE created_at > datetime('now', '-1 day')
                   GROUP BY hour ORDER BY hour"""
            ).fetchall()
            hourly = [{"hour": r[0], "count": r[1]} for r in hourly_rows]

            # Client errors in last 7 days
            error_count = 0
            try:
                err_row = conn.execute(
                    "SELECT COUNT(*) FROM client_error_log WHERE timestamp > datetime('now', '-7 days')"
                ).fetchone()
                error_count = err_row[0] if err_row else 0
            except sqlite3.OperationalError:
                pass

            # Top install_ids by volume (detect noisy clients)
            noisy_rows = conn.execute(
                """SELECT install_id, COUNT(*) as cnt
                   FROM client_event WHERE created_at > datetime('now', '-1 day')
                   AND install_id IS NOT NULL
                   GROUP BY install_id ORDER BY cnt DESC LIMIT 10"""
            ).fetchall()
            noisy_clients = [{"install_id": r[0], "count": r[1]} for r in noisy_rows]

            return jsonify({
                "event_volume": windows,
                "top_categories": top_categories,
                "top_events": top_events,
                "unique_installs_7d": installs,
                "dedup_stats": dedup_stats,
                "hourly_volume": hourly,
                "client_errors_7d": error_count,
                "noisy_clients": noisy_clients,
            })
    except sqlite3.OperationalError as e:
        logger.debug("Telemetry health query unavailable: %s", e)
        return jsonify({"event_volume": {}, "top_categories": [], "top_events": []})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin telemetry health error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Telemetry data unavailable"}), 500


@admin_bp.route("/api/admin/error-patterns")
@admin_required
@api_error_handler("Error patterns")
def admin_error_patterns():
    """Unresolved error focus patterns sorted by count."""
    page, per_page, offset, user_id = paginate_params()
    try:
        with db.connection() as conn:
            params = []
            query = (
                "SELECT ef.id, ef.user_id, ef.content_item_id,"
                " ef.error_type, ef.error_count,"
                " ef.first_flagged_at, ef.last_error_at,"
                " ef.consecutive_correct,"
                " ci.hanzi, ci.pinyin, ci.english,"
                " u.display_name as user_name"
                " FROM error_focus ef"
                " JOIN content_item ci ON ef.content_item_id = ci.id"
                " LEFT JOIN user u ON ef.user_id = u.id"
                " WHERE ef.resolved = 0"
            )
            if user_id:
                query += " AND ef.user_id = ?"
                params.append(user_id)
            query += " ORDER BY ef.error_count DESC LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = conn.execute(query, params).fetchall()
            entries = []
            for r in rows:
                entries.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "user_name": r["user_name"],
                    "hanzi": r["hanzi"],
                    "pinyin": r["pinyin"],
                    "english": r["english"],
                    "error_type": r["error_type"],
                    "count": r["error_count"],
                    "first_flagged": r["first_flagged_at"],
                    "last_error": r["last_error_at"],
                    "consecutive_correct": r["consecutive_correct"],
                })
            return jsonify({"patterns": entries, "page": page, "per_page": per_page})
    except sqlite3.OperationalError:
        return jsonify({"patterns": [], "page": page, "per_page": per_page})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin error patterns error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Error patterns unavailable"}), 500


def _get_catalog_path():
    """Return the path to media_catalog.json."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "data", "media_catalog.json")


def _load_catalog():
    """Load the media catalog from disk."""
    path = _get_catalog_path()
    if not os.path.exists(path):
        return {"entries": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_catalog(catalog):
    """Save the media catalog to disk."""
    path = _get_catalog_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


@admin_bp.route("/api/admin/content-ingest", methods=["POST"])
@admin_required
@api_error_handler("Content ingest")
def admin_content_ingest():
    """Add a new entry to the media catalog from the admin ingestion form."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    url = (data.get("url") or "").strip()
    title = (data.get("title") or "").strip()
    summary = (data.get("summary") or "").strip()
    hsk_level = data.get("hsk_level")
    quiz_questions = data.get("quiz_questions") or []

    errors = []
    if not url:
        errors.append("URL is required")
    elif not re.match(r"^https://", url):
        errors.append("URL must start with https://")
    if not title:
        errors.append("Title is required")
    if not summary:
        errors.append("Summary is required")
    if not hsk_level or not isinstance(hsk_level, int) or hsk_level < 1 or hsk_level > 9:
        errors.append("HSK level must be 1-9")
    if len(quiz_questions) < 1:
        errors.append("At least 1 quiz question is required")
    else:
        for i, q in enumerate(quiz_questions):
            if not q.get("question"):
                errors.append(f"Quiz question {i+1} has no text")
            if len(q.get("options", [])) < 2:
                errors.append(f"Quiz question {i+1} needs at least 2 options")

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    # Check for duplicate URL
    catalog = _load_catalog()
    for entry in catalog.get("entries", []):
        entry_url = entry.get("url") or entry.get("where_to_find", {}).get("primary", "")
        if entry_url == url:
            return jsonify({"error": "This URL is already in the catalog"}), 409

    # Build the new entry
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower())[:40]
    entry_id = f"m_admin_{slug}_{int(datetime.now(timezone.utc).timestamp())}"

    new_entry = {
        "id": entry_id,
        "title": title,
        "title_zh": (data.get("title_zh") or "").strip() or None,
        "media_type": data.get("content_type", "series"),
        "platform": (data.get("platform") or "Other").lower(),
        "hsk_level": hsk_level,
        "url": url,
        "where_to_find": {"primary": url},
        "content_lenses": data.get("tags", []),
        "summary": summary,
        "curator_note": (data.get("curator_note") or "").strip() or None,
        "key_vocab": data.get("key_vocab", []),
        "quiz": [
            {
                "question": q["question"],
                "options": q["options"],
                "correct": q.get("correct", 0),
            }
            for q in quiz_questions
        ],
        "verified": data.get("verified", True),
        "verified_by": "admin_form",
        "added_at": now,
    }

    catalog.setdefault("entries", []).append(new_entry)
    _save_catalog(catalog)

    logger.info("Content ingested: %s (%s)", title, entry_id)
    return jsonify(new_entry), 201


@admin_bp.route("/api/admin/content-catalog")
@admin_required
@api_error_handler("Content catalog")
def admin_content_catalog():
    """List all media catalog entries, sorted by added_at desc."""
    catalog = _load_catalog()
    entries = catalog.get("entries", [])

    # Sort by added_at descending (entries without added_at go to end)
    entries_with_date = []
    for e in entries:
        entries_with_date.append({
            "id": e.get("id", ""),
            "title": e.get("title", ""),
            "title_zh": e.get("title_zh"),
            "hsk_level": e.get("hsk_level"),
            "platform": e.get("platform", ""),
            "url": e.get("url") or e.get("where_to_find", {}).get("primary", ""),
            "verified": e.get("verified", False),
            "added_at": e.get("added_at", ""),
        })

    entries_with_date.sort(key=lambda x: x.get("added_at", ""), reverse=True)
    return jsonify({"entries": entries_with_date})


@admin_bp.route("/api/admin/funnel")
@admin_required
@api_error_handler("Funnel")
def admin_funnel():
    """Signup -> first session -> activated -> retained -> paid funnel."""
    try:
        with db.connection() as conn:
            # Stage 1: Total signups
            total_signups = conn.execute("SELECT COUNT(*) as cnt FROM user").fetchone()["cnt"] or 0

            # Stage 2: First session
            first_session = conn.execute(
                "SELECT COUNT(*) as cnt FROM user WHERE first_session_at IS NOT NULL"
            ).fetchone()["cnt"] or 0

            # Stage 3: Activated
            activated = conn.execute(
                "SELECT COUNT(*) as cnt FROM user WHERE activation_at IS NOT NULL"
            ).fetchone()["cnt"] or 0

            # Stage 4: Week 2 retained — users who had a session 7-14 days after first_session_at
            retained_w2 = 0
            try:
                retained_w2 = conn.execute(
                    """SELECT COUNT(DISTINCT sl.user_id) as cnt
                       FROM session_log sl
                       JOIN user u ON sl.user_id = u.id
                       WHERE u.first_session_at IS NOT NULL
                         AND sl.started_at >= datetime(u.first_session_at, '+7 days')
                         AND sl.started_at < datetime(u.first_session_at, '+14 days')"""
                ).fetchone()["cnt"] or 0
            except sqlite3.Error:
                pass

            # Stage 5: Paid
            paid = conn.execute(
                "SELECT COUNT(*) as cnt FROM user WHERE subscription_tier IN ('paid', 'teacher')"
            ).fetchone()["cnt"] or 0

            # Build funnel stages with conversion rates
            stages = [
                {"stage": "Signups", "count": total_signups, "rate": 100.0},
                {
                    "stage": "First Session",
                    "count": first_session,
                    "rate": round(first_session / total_signups * 100, 1) if total_signups > 0 else 0,
                },
                {
                    "stage": "Activated",
                    "count": activated,
                    "rate": round(activated / first_session * 100, 1) if first_session > 0 else 0,
                },
                {
                    "stage": "Retained (W2)",
                    "count": retained_w2,
                    "rate": round(retained_w2 / activated * 100, 1) if activated > 0 else 0,
                },
                {
                    "stage": "Paid",
                    "count": paid,
                    "rate": round(paid / retained_w2 * 100, 1) if retained_w2 > 0 else 0,
                },
            ]

            # Overall conversion: signup to paid
            overall_rate = round(paid / total_signups * 100, 1) if total_signups > 0 else 0

            # UTM source breakdown
            by_source = []
            try:
                utm_rows = conn.execute(
                    """SELECT
                        u.utm_source,
                        COUNT(*) as signups,
                        SUM(CASE WHEN u.first_session_at IS NOT NULL THEN 1 ELSE 0 END) as first_session,
                        SUM(CASE WHEN u.activation_at IS NOT NULL THEN 1 ELSE 0 END) as activated,
                        SUM(CASE WHEN u.subscription_tier IN ('paid', 'teacher') THEN 1 ELSE 0 END) as paid
                       FROM user u
                       WHERE u.utm_source IS NOT NULL AND u.utm_source != ''
                       GROUP BY u.utm_source
                       ORDER BY signups DESC
                       LIMIT 15"""
                ).fetchall()
                for r in utm_rows:
                    s = r["signups"] or 0
                    fs = r["first_session"] or 0
                    act = r["activated"] or 0
                    p = r["paid"] or 0
                    by_source.append({
                        "source": r["utm_source"],
                        "signups": s,
                        "first_session": fs,
                        "activated": act,
                        "paid": p,
                        "signup_to_paid_pct": round(p / s * 100, 1) if s > 0 else 0,
                    })
            except sqlite3.Error:
                pass

            return jsonify({
                "stages": stages,
                "overall_rate": overall_rate,
                "by_source": by_source,
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin funnel error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Funnel data unavailable"}), 500


@admin_bp.route("/api/admin/completion-segments")
@admin_required
@api_error_handler("Completion segments")
def admin_completion_segments():
    """Session completion rate broken down by type, time-of-day, and HSK level."""
    try:
        with db.connection() as conn:
            # By session_type
            by_type = []
            type_rows = conn.execute(
                """SELECT session_type,
                          COUNT(*) as cnt,
                          AVG(CASE WHEN items_planned > 0
                              THEN CAST(items_completed AS REAL) / items_planned
                              ELSE NULL END) as avg_completion,
                          AVG(items_completed) as avg_items
                   FROM session_log
                   WHERE items_planned > 0
                   GROUP BY session_type
                   ORDER BY cnt DESC"""
            ).fetchall()
            for r in type_rows:
                by_type.append({
                    "segment": r["session_type"] or "unknown",
                    "count": r["cnt"] or 0,
                    "avg_completion": round((r["avg_completion"] or 0) * 100, 1),
                    "avg_items": round(r["avg_items"] or 0, 1),
                })

            # By time of day (hour bins)
            by_time = []
            time_rows = conn.execute(
                """SELECT
                      CASE
                        WHEN CAST(strftime('%H', started_at) AS INTEGER) >= 6
                             AND CAST(strftime('%H', started_at) AS INTEGER) < 12 THEN 'morning'
                        WHEN CAST(strftime('%H', started_at) AS INTEGER) >= 12
                             AND CAST(strftime('%H', started_at) AS INTEGER) < 18 THEN 'afternoon'
                        WHEN CAST(strftime('%H', started_at) AS INTEGER) >= 18 THEN 'evening'
                        ELSE 'night'
                      END as time_bin,
                      COUNT(*) as cnt,
                      AVG(CASE WHEN items_planned > 0
                          THEN CAST(items_completed AS REAL) / items_planned
                          ELSE NULL END) as avg_completion,
                      AVG(items_completed) as avg_items
                   FROM session_log
                   WHERE items_planned > 0
                   GROUP BY time_bin
                   ORDER BY CASE time_bin
                     WHEN 'morning' THEN 1
                     WHEN 'afternoon' THEN 2
                     WHEN 'evening' THEN 3
                     WHEN 'night' THEN 4
                   END"""
            ).fetchall()
            for r in time_rows:
                by_time.append({
                    "segment": r["time_bin"],
                    "count": r["cnt"] or 0,
                    "avg_completion": round((r["avg_completion"] or 0) * 100, 1),
                    "avg_items": round(r["avg_items"] or 0, 1),
                })

            return jsonify({
                "by_type": by_type,
                "by_time": by_time,
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin completion segments error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Completion segments unavailable"}), 500

# ── Experiments ────────────────────────────────────────────────────

@admin_bp.route("/api/admin/experiments")
@admin_required
@api_error_handler("AdminExperiments")
def admin_experiments():
    """A/B experiment analysis — uses experiment module for proper user-level analysis."""
    try:
        from .. import experiments as exp_module

        with db.connection() as conn:
            # Get all running and concluded experiments
            all_experiments = exp_module.list_experiments(conn)
            results = []

            for exp in all_experiments:
                exp_name = exp["name"]
                exp_results = exp_module.get_experiment_results(conn, exp_name)
                guardrails = exp_module.check_guardrails(conn, exp_name)
                seq_test = exp_module.sequential_test(conn, exp_name)

                variants_list = json.loads(exp["variants"])
                variant_data = exp_results.get("variants", {})

                # Build recommendation
                recommendation = seq_test.get("recommendation", "continue")
                if any(g.get("degraded") for g in guardrails.values()):
                    recommendation = "alert_guardrail"

                results.append({
                    "name": exp_name,
                    "description": exp.get("description", ""),
                    "status": exp.get("status", "draft"),
                    "traffic_pct": exp.get("traffic_pct", 100),
                    "min_sample_size": exp.get("min_sample_size", 100),
                    "variants": variant_data,
                    "variant_names": variants_list,
                    "p_value": exp_results.get("p_value"),
                    "effect_size": exp_results.get("effect_size"),
                    "ci_95": exp_results.get("ci_95"),
                    "significant": exp_results.get("significant", False),
                    "min_sample_met": exp_results.get("min_sample_met", False),
                    "guardrails": guardrails,
                    "sequential": {
                        "can_conclude": seq_test.get("can_conclude", False),
                        "adjusted_alpha": seq_test.get("adjusted_alpha"),
                        "information_fraction": seq_test.get("information_fraction", 0),
                        "recommendation": recommendation,
                    },
                    "conclusion": json.loads(exp["conclusion"]) if exp.get("conclusion") else None,
                })

            return jsonify({"experiments": results})
    except (sqlite3.Error, KeyError, TypeError, ImportError) as e:
        logger.error("Admin experiments error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Experiments unavailable"}), 500

# ── Onboarding Funnel ──────────────────────────────────────────────

@admin_bp.route("/api/admin/onboarding-funnel")
@admin_required
@api_error_handler("AdminOnboardingFunnel")
def admin_onboarding_funnel():
    """Onboarding funnel: registered → level set → goal set → placement → complete → first session."""
    try:
        with db.connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM user WHERE is_active = 1").fetchone()
            total_users = row["cnt"] if row else 0

            # Count users at each stage via lifecycle events
            stages = []

            stages.append({
                "stage": "Registered",
                "count": total_users,
            })

            for event_type, label in [
                ("onboarding_level_set", "Level Set"),
                ("onboarding_goal_set", "Goal Set"),
                ("onboarding_complete", "Onboarding Complete"),
                ("first_session_started", "First Session"),
            ]:
                try:
                    row = conn.execute(
                        "SELECT COUNT(DISTINCT user_id) as cnt FROM lifecycle_event WHERE event_type = ?",
                        (event_type,)
                    ).fetchone()
                    count = row["cnt"] if row else 0
                except sqlite3.OperationalError:
                    count = 0
                stages.append({"stage": label, "count": count})

            return jsonify({"stages": stages, "total_users": total_users})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin onboarding funnel error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Onboarding funnel unavailable"}), 500

# ── Passage Difficulty Calibration ─────────────────────────────────

@admin_bp.route("/api/admin/content/passage-difficulty")
@admin_required
@api_error_handler("AdminPassageDifficulty")
def admin_passage_difficulty():
    """Calculate readability metrics for reading passages and flag miscalibrated ones."""
    try:
        from ..media_ingest import calculate_passage_difficulty
        import json as _json

        with db.connection() as conn:
            passages = conn.execute("""
                SELECT id, title, hsk_level, content_zh
                FROM reading_passage
                ORDER BY hsk_level, id
            """).fetchall()

            results = []
            for p in passages:
                text = p["content_zh"] or ""
                metrics = calculate_passage_difficulty(text)
                labeled_level = p["hsk_level"] or 0
                estimated_level = metrics.get("estimated_hsk", 0)
                miscalibrated = abs(labeled_level - estimated_level) >= 2

                results.append({
                    "id": p["id"],
                    "title": p["title"],
                    "labeled_hsk": labeled_level,
                    "estimated_hsk": estimated_level,
                    "char_count": metrics["char_count"],
                    "unique_ratio": metrics["unique_ratio"],
                    "avg_sentence_length": metrics["avg_sentence_length"],
                    "hsk_coverage": metrics.get("hsk_coverage", {}),
                    "miscalibrated": miscalibrated,
                })

            return jsonify({
                "passages": results,
                "total": len(results),
                "miscalibrated_count": sum(1 for r in results if r["miscalibrated"]),
            })
    except ImportError:
        return jsonify({"error": "media_ingest module not available"}), 500
    except sqlite3.OperationalError:
        return jsonify({"passages": [], "total": 0, "miscalibrated_count": 0})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin passage difficulty error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Passage difficulty unavailable"}), 500

# ── Interview Volunteers (NPS promoters) ───────────────────────────

@admin_bp.route("/api/admin/interview-volunteers")
@admin_required
@api_error_handler("AdminInterviewVolunteers")
def admin_interview_volunteers():
    """List users who volunteered for interviews via NPS promoter flow."""
    try:
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT le.user_id, u.email, u.display_name, le.created_at,
                       json_extract(le.metadata, '$.score') as nps_score
                FROM lifecycle_event le
                LEFT JOIN user u ON u.id = CAST(le.user_id AS INTEGER)
                WHERE le.event_type = 'interview_volunteered'
                ORDER BY le.created_at DESC
                LIMIT 100
            """).fetchall()

            volunteers = [{
                "user_id": r["user_id"],
                "email": r["email"] or "unknown",
                "name": r["display_name"] or "",
                "volunteered_at": r["created_at"],
                "nps_score": r["nps_score"],
            } for r in rows]

            return jsonify({"volunteers": volunteers, "count": len(volunteers)})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin interview volunteers error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Interview volunteers unavailable"}), 500

# ── Notifications ──────────────────────────────────────────────────

def _gather_admin_notifications(conn):
    """Scan all systems for actionable alerts. Returns list of notification dicts."""
    notifs = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Crashes in last 24h
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM crash_log WHERE created_at >= datetime('now', '-24 hours')"
        ).fetchone()
        crash_count = row["cnt"] if row else 0
        if crash_count > 0:
            notifs.append({
                "id": "crashes_24h",
                "title": f"{crash_count} crash{'es' if crash_count != 1 else ''} in last 24 hours",
                "detail": "Check the Issues tab for tracebacks.",
                "severity": "critical" if crash_count >= 5 else "warning",
                "tab": "Issues",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 2. Client errors in last 24h
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM client_error_log WHERE created_at >= datetime('now', '-24 hours')"
        ).fetchone()
        client_errors = row["cnt"] if row else 0
        if client_errors >= 10:
            notifs.append({
                "id": "client_errors_24h",
                "title": f"{client_errors} client errors in last 24 hours",
                "detail": "JavaScript errors reported by users. Check Issues tab.",
                "severity": "warning",
                "tab": "Issues",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 3. Churn risk — users at high risk
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT user_id) as cnt FROM lifecycle_event
            WHERE event_type = 'churn_risk_detected'
              AND created_at >= datetime('now', '-7 days')
              AND json_extract(metadata, '$.risk_level') IN ('high', 'critical')
        """).fetchone()
        high_risk = row["cnt"] if row else 0
        if high_risk > 0:
            notifs.append({
                "id": "churn_risk",
                "title": f"{high_risk} user{'s' if high_risk != 1 else ''} at high churn risk",
                "detail": "Review retention data and consider intervention.",
                "severity": "warning",
                "tab": "Retention",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 4. NPS detractors (score 0-6) in last 7 days
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM user_feedback
            WHERE feedback_type = 'nps' AND rating <= 6
              AND created_at >= datetime('now', '-7 days')
        """).fetchone()
        detractors = row["cnt"] if row else 0
        if detractors > 0:
            notifs.append({
                "id": "nps_detractors",
                "title": f"{detractors} NPS detractor{'s' if detractors != 1 else ''} this week",
                "detail": "Read their feedback in the Feedback section.",
                "severity": "warning" if detractors >= 3 else "info",
                "tab": "Overview",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 5. Interview volunteers waiting
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT user_id) as cnt FROM lifecycle_event
            WHERE event_type = 'interview_volunteered'
              AND created_at >= datetime('now', '-14 days')
        """).fetchone()
        volunteers = row["cnt"] if row else 0
        if volunteers > 0:
            notifs.append({
                "id": "interview_volunteers",
                "title": f"{volunteers} interview volunteer{'s' if volunteers != 1 else ''} waiting",
                "detail": "Promoters who want to chat. Reach out within a week.",
                "severity": "info",
                "tab": "Overview",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 6. Security events in last 24h
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM security_audit_log
            WHERE severity IN ('ERROR', 'CRITICAL')
              AND created_at >= datetime('now', '-24 hours')
        """).fetchone()
        sec_events = row["cnt"] if row else 0
        if sec_events > 0:
            notifs.append({
                "id": "security_events",
                "title": f"{sec_events} security event{'s' if sec_events != 1 else ''} in 24h",
                "detail": "Check Security tab for details.",
                "severity": "critical",
                "tab": "Security",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 7. SPC out-of-control (with 5-Why template)
    try:
        from ..quality.spc import compute_spc_chart
        from ..quality.flow_metrics import generate_five_why_template
        for chart_type in ["drill_accuracy", "response_time", "session_completion"]:
            spc = compute_spc_chart(conn, chart_type)
            if spc and spc.get("out_of_control"):
                violations = spc.get("violations", [])
                violation_str = ", ".join(str(v) for v in violations[:3]) if violations else "unknown"
                five_why = generate_five_why_template(chart_type, f"Violations: {violation_str}")
                notifs.append({
                    "id": f"spc_{chart_type}",
                    "title": f"SPC out-of-control: {chart_type.replace('_', ' ')}",
                    "detail": f"Control chart violation detected. 5-Why analysis available at /api/admin/quality/five-why/{chart_type}",
                    "severity": "warning",
                    "tab": "Quality",
                    "timestamp": now_str,
                    "five_why": five_why,
                })
    except (ImportError, Exception):
        pass

    # 8. Experiments: check running experiments and guardrails
    try:
        from .. import experiments as exp_module
        running = exp_module.list_experiments(conn, status="running")
        for exp in running:
            exp_name = exp["name"]
            guardrails = exp_module.check_guardrails(conn, exp_name)
            degraded = [m for m, g in guardrails.items() if g.get("degraded")]
            seq = exp_module.sequential_test(conn, exp_name)

            if degraded:
                notifs.append({
                    "id": f"experiment_guardrail_{exp_name}",
                    "title": f"Guardrail alert: {exp_name}",
                    "detail": f"Metrics degraded: {', '.join(degraded)}. Consider pausing.",
                    "severity": "critical",
                    "tab": "Quality",
                    "timestamp": now_str,
                })
            elif seq.get("can_conclude"):
                notifs.append({
                    "id": f"experiment_significant_{exp_name}",
                    "title": f"Experiment ready to conclude: {exp_name}",
                    "detail": f"p={seq.get('current_p')}, recommendation: {seq.get('recommendation')}",
                    "severity": "info",
                    "tab": "Quality",
                    "timestamp": now_str,
                })
            else:
                notifs.append({
                    "id": "experiment_active",
                    "title": f"A/B experiment running: {exp_name}",
                    "detail": f"Traffic: {exp.get('traffic_pct', 100)}%. Info fraction: {seq.get('information_fraction', 0):.0%}. Check Quality > Experiments.",
                    "severity": "info",
                    "tab": "Quality",
                    "timestamp": now_str,
                })
    except (sqlite3.OperationalError, ImportError):
        pass

    # 9. Grade appeals pending
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM grade_appeal WHERE status = 'pending'"
        ).fetchone()
        appeals = row["cnt"] if row else 0
        if appeals > 0:
            notifs.append({
                "id": "grade_appeals",
                "title": f"{appeals} grade appeal{'s' if appeals != 1 else ''} pending review",
                "detail": "Students disputed their grades. Review in Content tab.",
                "severity": "warning" if appeals >= 3 else "info",
                "tab": "Content",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 10. Slow API responses
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM request_timing
            WHERE duration_ms > 2000
              AND recorded_at >= datetime('now', '-24 hours')
        """).fetchone()
        slow = row["cnt"] if row else 0
        if slow >= 5:
            notifs.append({
                "id": "slow_api",
                "title": f"{slow} slow API responses (>2s) in 24h",
                "detail": "Performance degradation detected.",
                "severity": "warning",
                "tab": "Quality",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 11. Kanban WIP limit breach
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM work_item WHERE status = 'in_progress'"
        ).fetchone()
        wip_count = row["cnt"] if row else 0
        if wip_count > 5:
            notifs.append({
                "id": "wip_exceeded",
                "title": f"WIP limit exceeded: {wip_count} items in progress (limit: 5)",
                "detail": "Finish or park existing work before starting new items.",
                "severity": "warning",
                "tab": "Quality",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 12. Kanban aging alerts with escalation tiers
    # Standard items: >14d = warning, >21d = critical
    # Expedite items: >2d = warning, >5d = critical
    try:
        aging_rows = conn.execute("""
            SELECT id, title,
                   CAST(julianday('now') - julianday(started_at) AS INTEGER) AS age_days,
                   COALESCE(service_class, 'standard') AS service_class
            FROM work_item
            WHERE status IN ('in_progress', 'blocked')
              AND started_at IS NOT NULL
        """).fetchall()
        for r in aging_rows:
            age = r["age_days"]
            sc = r["service_class"]
            severity = None
            if sc == "expedite":
                if age > 5:
                    severity = "critical"
                elif age > 2:
                    severity = "warning"
            else:
                # standard, fixed_date, intangible
                if age > 21:
                    severity = "critical"
                elif age > 14:
                    severity = "warning"
            if severity:
                notifs.append({
                    "id": f"aging_work_item_{r['id']}",
                    "title": f"Work item aging: \"{r['title']}\" ({age}d in progress, {sc})",
                    "detail": f"Age: {age} days. Service class: {sc}. "
                              f"Consider breaking it down, parking it, or finishing it.",
                    "severity": severity,
                    "tab": "Quality",
                    "timestamp": now_str,
                })
    except sqlite3.OperationalError:
        pass

    # 13. Spiral: Risk register staleness (no risk updated in 30 days)
    try:
        latest_risk = conn.execute("""
            SELECT MAX(updated_at) AS last_updated FROM risk_item
            WHERE status = 'active'
        """).fetchone()
        if latest_risk and latest_risk["last_updated"]:
            from datetime import datetime as _dt, timedelta as _td
            last = _dt.fromisoformat(latest_risk["last_updated"])
            if (_dt.now(timezone.utc) - last.replace(tzinfo=timezone.utc)) > _td(days=30):
                notifs.append({
                    "id": "risk_register_stale",
                    "title": "Risk register stale: no updates in 30+ days",
                    "detail": "Review and update risk items. Good practice: monthly risk review.",
                    "severity": "warning",
                    "tab": "Quality",
                    "timestamp": now_str,
                })
        else:
            # No active risks at all — nudge to create some
            notifs.append({
                "id": "risk_register_empty",
                "title": "Risk register empty: no active risks tracked",
                "detail": "Add technical, operational, and learning risks to the register.",
                "severity": "info",
                "tab": "Quality",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 14. Spiral: High-risk items (score >= 15) without mitigation work items
    try:
        high_risks = conn.execute("""
            SELECT id, title, probability, impact,
                   (probability * impact) AS risk_score
            FROM risk_item
            WHERE status = 'active'
              AND (probability * impact) >= 15
        """).fetchall()
        for r in high_risks:
            severity = "critical" if r["risk_score"] >= 20 else "warning"
            notifs.append({
                "id": f"high_risk_{r['id']}",
                "title": f"High risk (score {r['risk_score']}): {r['title']}",
                "detail": "Create a mitigation work item if not already tracked.",
                "severity": severity,
                "tab": "Quality",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 15. Intelligence escalations (alert+ within 24h)
    try:
        escalations = conn.execute("""
            SELECT dl.id, dl.finding_id, dl.escalation_level, dl.decision_class,
                   dl.requires_approval, pf.dimension, pf.title, pf.severity
            FROM pi_decision_log dl
            JOIN pi_finding pf ON dl.finding_id = pf.id
            WHERE dl.created_at >= datetime('now', '-24 hours')
              AND dl.escalation_level IN ('alert', 'escalate', 'emergency')
              AND dl.approved_at IS NULL
              AND dl.decision IS NULL
        """).fetchall()
        for esc in escalations:
            sev = "critical" if esc["escalation_level"] == "emergency" else "warning"
            notifs.append({
                "id": f"intelligence_escalation_{esc['id']}",
                "title": f"Intelligence {esc['escalation_level']}: {esc['title']}",
                "detail": f"Finding in {esc['dimension']} ({esc['severity']}) "
                          f"requires {esc['decision_class']} decision.",
                "severity": sev,
                "tab": "Intelligence",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    notifs.sort(key=lambda n: severity_order.get(n["severity"], 3))

    # Enrich with actionable Claude Code prompts
    _add_action_prompts(notifs, conn)

    return notifs

def _add_action_prompts(notifs, conn):
    """Add action_prompt to notifications that can be addressed by Claude Code."""
    # Map notification IDs to prompt generators
    for n in notifs:
        nid = n["id"]

        if nid == "crashes_24h":
            # Fetch recent crash tracebacks for context
            try:
                crashes = conn.execute(
                    "SELECT traceback, endpoint FROM crash_log WHERE created_at >= datetime('now', '-24 hours') ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
                traces = "\n---\n".join(f"Endpoint: {c['endpoint']}\n{c['traceback']}" for c in crashes if c["traceback"])
            except Exception:
                traces = "(unable to fetch)"
            n["action_prompt"] = (
                f"There are {n['title']}. Here are the most recent tracebacks:\n\n"
                f"{traces}\n\n"
                f"Diagnose the root cause(s) and fix the code. Run tests after."
            )

        elif nid == "client_errors_24h":
            try:
                errors = conn.execute(
                    "SELECT message, url, user_agent FROM client_error_log WHERE created_at >= datetime('now', '-24 hours') ORDER BY created_at DESC LIMIT 10"
                ).fetchall()
                errs = "\n".join(f"- {e['message']} (at {e['url']})" for e in errors)
            except Exception:
                errs = "(unable to fetch)"
            n["action_prompt"] = (
                f"There are client-side errors occurring. Recent errors:\n\n{errs}\n\n"
                f"Check mandarin/web/static/app.js and related JS for the root cause. Fix and test."
            )

        elif nid == "churn_risk":
            n["action_prompt"] = (
                "Users are at high churn risk. Analyze the churn signals:\n\n"
                "1. Read mandarin/churn_detection.py to understand the churn model\n"
                "2. Check what's driving churn (session frequency drop, accuracy decline, etc.)\n"
                "3. Review the re-engagement email sequence in mandarin/email.py send_churn_prevention()\n"
                "4. Check if the onboarding flow has drop-off points via /api/admin/onboarding-funnel\n"
                "5. Suggest and implement product changes to reduce churn risk"
            )

        elif nid == "nps_detractors":
            try:
                feedback = conn.execute(
                    "SELECT rating, comment FROM user_feedback WHERE feedback_type = 'nps' AND rating <= 6 AND created_at >= datetime('now', '-7 days') ORDER BY rating ASC LIMIT 10"
                ).fetchall()
                fb = "\n".join(f"- Score {f['rating']}: {f['comment'] or '(no comment)'}" for f in feedback)
            except Exception:
                fb = "(unable to fetch)"
            n["action_prompt"] = (
                f"NPS detractors this week. Their feedback:\n\n{fb}\n\n"
                "Analyze the feedback themes. For each actionable complaint:\n"
                "1. Identify the relevant code/feature\n"
                "2. Implement fixes or improvements\n"
                "3. If it's a positioning/messaging issue, update marketing copy in marketing/landing/ and mandarin/email.py"
            )

        elif nid == "security_events":
            n["action_prompt"] = (
                "Security events detected in the last 24 hours. Steps:\n\n"
                "1. Read the security_audit_log for details\n"
                "2. Check mandarin/web/routes.py and middleware.py for the security layer\n"
                "3. Fix any vulnerabilities found\n"
                "4. Add regression tests in tests/test_security_regression.py\n"
                "5. Review OWASP top 10 against the codebase"
            )

        elif nid.startswith("spc_"):
            chart_type = nid.replace("spc_", "")
            n["action_prompt"] = (
                f"SPC control chart '{chart_type}' is out of control.\n\n"
                "1. Read mandarin/quality/spc.py to understand which Western Electric rule was violated\n"
                "2. Query the recent observations to identify the trend\n"
                "3. If drill_accuracy: check mandarin/drills/ for broken drill logic\n"
                "4. If response_time: profile slow endpoints, check DB queries\n"
                "5. If session_completion: check mandarin/scheduler.py for session length/difficulty issues\n"
                "6. Fix the root cause and verify the chart returns to control"
            )

        elif nid == "slow_api":
            try:
                slow = conn.execute(
                    "SELECT endpoint, duration_ms FROM request_timing WHERE duration_ms > 2000 AND recorded_at >= datetime('now', '-24 hours') ORDER BY duration_ms DESC LIMIT 10"
                ).fetchall()
                endpoints = "\n".join(f"- {s['endpoint']}: {s['duration_ms']}ms" for s in slow)
            except Exception:
                endpoints = "(unable to fetch)"
            n["action_prompt"] = (
                f"Slow API responses detected. Slowest endpoints:\n\n{endpoints}\n\n"
                "1. Profile the slow queries (add EXPLAIN QUERY PLAN)\n"
                "2. Add missing indexes to schema.sql if needed\n"
                "3. Check for N+1 queries in the route handlers\n"
                "4. Consider caching for read-heavy endpoints\n"
                "5. Run tests after any changes"
            )

        elif nid == "wip_exceeded":
            n["action_prompt"] = (
                "WIP limit exceeded — too many work items in progress.\n\n"
                "1. List current in-progress work items via /api/admin/quality/work-items\n"
                "2. Identify items that are stalled or blocked\n"
                "3. Either complete, park, or descope stalled items\n"
                "4. Consider if any items should be broken into smaller tasks"
            )

        elif nid.startswith("aging_work_item_"):
            n["action_prompt"] = (
                f"Work item has been in progress too long: {n['title']}\n\n"
                "1. Check if the item is blocked on external dependencies\n"
                "2. If the scope grew, break it into smaller items\n"
                "3. If it's a code task, try to complete it now\n"
                "4. If it's not code-addressable, park it with a note"
            )

        elif nid.startswith("high_risk_"):
            n["action_prompt"] = (
                f"High risk detected: {n['title']}\n\n"
                "1. Review the risk details in the Quality tab\n"
                "2. If it's a technical risk, implement the mitigation strategy\n"
                "3. If it's a business risk, update marketing/positioning in marketing/landing/\n"
                "4. If it's an operational risk, add monitoring or automation\n"
                "5. Update the risk register with mitigation status"
            )

        elif nid == "experiment_active" or nid.startswith("experiment_"):
            n["action_prompt"] = (
                "A/B experiment notification. Check Quality > Experiments for full details:\n\n"
                "1. Query /api/admin/experiments for current results, guardrails, and sequential test\n"
                "2. If recommendation is 'stop_winner', use experiments.conclude_experiment() with the winner\n"
                "3. If guardrails are degraded, pause the experiment immediately\n"
                "4. If recommendation is 'stop_futility', conclude with no winner\n"
                "5. After concluding, update the relevant code to hardcode the winning variant"
            )

        elif nid == "grade_appeals":
            n["action_prompt"] = (
                "Grade appeals are pending review.\n\n"
                "1. Fetch appeals from the grade_appeal table\n"
                "2. For each appeal, check if the drill answer was genuinely correct\n"
                "3. If the grading logic was wrong, fix it in the relevant mandarin/drills/ module\n"
                "4. Update the appeal status\n"
                "5. If this is a systemic issue, add test cases"
            )

        elif nid == "risk_register_stale" or nid == "risk_register_empty":
            n["action_prompt"] = (
                "The risk register needs attention.\n\n"
                "Scan the codebase and business context for risks:\n"
                "1. Technical: single points of failure, unhandled error paths, dependency risks\n"
                "2. Business: competitive gaps, churn drivers, pricing sensitivity\n"
                "3. Operational: monitoring gaps, backup/recovery, scaling limits\n"
                "4. Add each as a risk_item via /api/admin/quality/risks with probability and impact scores\n"
                "5. Create mitigation work items for anything scoring >= 15"
            )

@admin_bp.route("/api/admin/notifications")
@admin_required
@api_error_handler("AdminNotifications")
def admin_notifications():
    """Return all current admin notifications."""
    try:
        with db.connection() as conn:
            notifs = _gather_admin_notifications(conn)
            return jsonify({"notifications": notifs, "count": len(notifs)})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin notifications error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Notifications unavailable"}), 500

@admin_bp.route("/api/admin/notifications/count")
@admin_required
@api_error_handler("AdminNotifCount")
def admin_notifications_count():
    """Return just the notification count for the badge."""
    try:
        with db.connection() as conn:
            notifs = _gather_admin_notifications(conn)
            # Filter to only warning+ severity for badge count
            important = [n for n in notifs if n["severity"] in ("critical", "warning")]
            return jsonify({"count": len(important)})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Admin notif count error (%s): %s", type(e).__name__, e)
        return jsonify({"count": 0})

@admin_bp.route("/api/admin/notifications/mark-read", methods=["POST"])
@admin_required
@api_error_handler("AdminNotifMarkRead")
def admin_notifications_mark_read():
    """Mark all notifications as read (clears badge until new ones appear)."""
    # Notifications are computed live from system state, not stored.
    # "Mark read" is a no-op for now — badge auto-clears on tab visit.
    return jsonify({"ok": True})

# ── Lean Six Sigma: Pareto Analysis ──────────────────────────────
@admin_bp.route("/api/admin/quality/pareto")
@admin_required
@api_error_handler("Pareto")
def admin_pareto():
    """Error Pareto: rank error types by frequency, cumulative %, vital few."""
    days = request.args.get("days", 30, type=int)
    with db.connection() as conn:
        from ..quality.flow_metrics import calculate_error_pareto
        return jsonify(calculate_error_pareto(conn, days=days))

# ── Lean Six Sigma: CTQ Tree ─────────────────────────────────────
@admin_bp.route("/api/admin/quality/ctq")
@admin_required
@api_error_handler("CTQ")
def admin_ctq():
    """Critical-to-Quality tree with live measurements."""
    with db.connection() as conn:
        from ..quality.flow_metrics import assess_ctq_metrics
        return jsonify(assess_ctq_metrics(conn))

# ── Lean Six Sigma: Process Performance (Pp/Ppk) ─────────────────
@admin_bp.route("/api/admin/quality/performance")
@admin_required
@api_error_handler("Performance")
def admin_process_performance():
    """Process performance indices Pp and Ppk."""
    with db.connection() as conn:
        from ..quality.capability import assess_accuracy_performance
        return jsonify(assess_accuracy_performance(conn))

# ── Lean Six Sigma: 5-Why Template ───────────────────────────────
@admin_bp.route("/api/admin/quality/five-why/<chart_type>")
@admin_required
@api_error_handler("FiveWhy")
def admin_five_why(chart_type):
    """Generate a 5-Why root cause analysis template for an SPC violation."""
    from ..quality.flow_metrics import generate_five_why_template
    detail = request.args.get("detail", "")
    return jsonify(generate_five_why_template(chart_type, detail))

# ── Operations Research: Sensitivity Analysis ────────────────────
@admin_bp.route("/api/admin/quality/sensitivity")
@admin_required
@api_error_handler("Sensitivity")
def admin_sensitivity():
    """Parameter sensitivity analysis for scheduling decisions."""
    with db.connection() as conn:
        from ..scheduler import sensitivity_analysis
        return jsonify(sensitivity_analysis(conn))

# ── Operations Research: Decision Table ──────────────────────────
@admin_bp.route("/api/admin/quality/decision-table")
@admin_required
@api_error_handler("DecisionTable")
def admin_decision_table():
    """Return the scheduling decision table (auditable rules)."""
    from ..scheduler import SCHEDULING_DECISION_TABLE
    return jsonify({"rules": SCHEDULING_DECISION_TABLE})

# ── Kanban: Aging Summary ────────────────────────────────────────
@admin_bp.route("/api/admin/quality/aging")
@admin_required
@api_error_handler("Aging")
def admin_aging():
    """Item aging tiers: green/yellow/orange/red overdue counts."""
    with db.connection() as conn:
        from ..scheduler import get_aging_summary
        return jsonify(get_aging_summary(conn))

# ── Kanban: Explicit Policies ────────────────────────────────────
@admin_bp.route("/api/admin/quality/policies")
@admin_required
@api_error_handler("Policies")
def admin_policies():
    """Return Kanban explicit policies (DoD, entry/exit criteria, escalation)."""
    from ..scheduler import KANBAN_POLICIES
    return jsonify(KANBAN_POLICIES)

# ── Scrum: Sprint Management ─────────────────────────────────────
@admin_bp.route("/api/admin/sprint")
@admin_required
@api_error_handler("Sprint")
def admin_sprint():
    """Get current sprint and velocity."""
    with db.connection() as conn:
        from ..quality.methodology import (
            get_current_sprint, get_sprint_velocity, get_sprint_history
        )
        current = get_current_sprint(conn)
        velocity = get_sprint_velocity(conn)
        history = get_sprint_history(conn, limit=5)
        return jsonify({
            "current": current,
            "velocity": velocity,
            "history": history,
        })

@admin_bp.route("/api/admin/sprint/create", methods=["POST"])
@admin_required
@api_error_handler("SprintCreate")
def admin_sprint_create():
    """Create a new sprint (auto-generates goal from queue state)."""
    with db.connection() as conn:
        from ..quality.methodology import auto_create_sprint
        sprint = auto_create_sprint(conn)
        if sprint:
            return jsonify({"sprint": sprint})
        return jsonify({"error": "Sprint already active or creation failed"}), 400

@admin_bp.route("/api/admin/sprint/complete", methods=["POST"])
@admin_required
@api_error_handler("SprintComplete")
def admin_sprint_complete():
    """Complete the current sprint with review."""
    with db.connection() as conn:
        from ..quality.methodology import complete_sprint
        retro = complete_sprint(conn)
        if retro:
            return jsonify({"retrospective": retro})
        return jsonify({"error": "No active sprint to complete"}), 400

# ── Agile: WSJF Backlog ──────────────────────────────────────────
@admin_bp.route("/api/admin/quality/wsjf")
@admin_required
@api_error_handler("WSJF")
def admin_wsjf():
    """Content backlog ranked by WSJF (Weighted Shortest Job First)."""
    limit = request.args.get("limit", 50, type=int)
    with db.connection() as conn:
        from ..quality.methodology import rank_content_backlog
        return jsonify({"items": rank_content_backlog(conn, limit=limit)})

# ── Spiral: Risk Assessment ──────────────────────────────────────
@admin_bp.route("/api/admin/quality/risk-review", methods=["POST"])
@admin_required
@api_error_handler("RiskReview")
def admin_risk_review():
    """Run an automated risk assessment."""
    with db.connection() as conn:
        from ..quality.methodology import run_risk_review
        risks = run_risk_review(conn)
        return jsonify({"risks": risks, "count": len(risks)})

@admin_bp.route("/api/admin/quality/risk-summary")
@admin_required
@api_error_handler("RiskSummary")
def admin_risk_summary():
    """Risk event summary with categorization."""
    days = request.args.get("days", 30, type=int)
    with db.connection() as conn:
        from ..quality.methodology import get_risk_summary
        return jsonify(get_risk_summary(conn, days=days))

@admin_bp.route("/api/admin/quality/risk-taxonomy")
@admin_required
@api_error_handler("RiskTaxonomy")
def admin_risk_taxonomy():
    """Return the risk taxonomy definition."""
    from ..quality.methodology import get_risk_taxonomy
    return jsonify(get_risk_taxonomy())

# ── Product Intelligence Engine ──────────────────────────────────
@admin_bp.route("/api/admin/product-intelligence")
@admin_required
@api_error_handler("ProductIntelligence")
def admin_product_intelligence():
    """Run product audit and return findings with dimension scores."""
    try:
        from ..product_intelligence import run_product_audit
        with db.connection() as conn:
            result = run_product_audit(conn)
            return jsonify(result)
    except Exception as e:
        logger.error("Product intelligence error: %s", e)
        return jsonify({"error": "Product intelligence unavailable: " + str(e)}), 500

@admin_bp.route("/api/admin/product-intelligence/history")
@admin_required
@api_error_handler("ProductIntelligenceHistory")
def admin_product_intelligence_history():
    """Return last 20 audit runs with scores."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT id, run_at, overall_grade, overall_score,
                          dimension_scores, findings_count, critical_count, high_count
                   FROM product_audit
                   ORDER BY run_at DESC LIMIT 20"""
            ).fetchall()
            history = []
            for r in rows:
                history.append({
                    "id": r["id"],
                    "run_at": r["run_at"],
                    "overall_grade": r["overall_grade"],
                    "overall_score": r["overall_score"],
                    "dimension_scores": json.loads(r["dimension_scores"]) if r["dimension_scores"] else {},
                    "findings_count": r["findings_count"],
                    "critical_count": r["critical_count"],
                    "high_count": r["high_count"],
                })
            return jsonify({"history": history})
    except sqlite3.OperationalError:
        return jsonify({"history": []})

# ── Intelligence Engine V4 Endpoints ─────────────────────────────
@admin_bp.route("/api/admin/intelligence/findings")
@admin_required
@api_error_handler("IntelligenceFindings")
def admin_intelligence_findings():
    """Open findings with lifecycle state, advisor opinions, escalation."""
    with db.connection() as conn:
        findings = conn.execute("""
            SELECT pf.id, pf.dimension, pf.severity, pf.title, pf.analysis,
                   pf.status, pf.hypothesis, pf.root_cause_tag,
                   pf.linked_finding_id, pf.times_seen,
                   pf.created_at, pf.updated_at,
                   julianday('now') - julianday(pf.updated_at) as days_in_state
            FROM pi_finding pf
            WHERE pf.status NOT IN ('resolved', 'rejected')
            ORDER BY
                CASE pf.severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END,
                pf.updated_at DESC
        """).fetchall()

        result = []
        for f in findings:
            item = dict(f)
            item["days_in_state"] = round(f["days_in_state"], 1) if f["days_in_state"] else 0
            # Attach advisor opinions
            opinions = conn.execute("""
                SELECT advisor, priority_score, effort_estimate, rationale, tradeoff_notes
                FROM pi_advisor_opinion
                WHERE finding_id = ?
                ORDER BY priority_score DESC
            """, (f["id"],)).fetchall()
            item["advisor_opinions"] = [dict(o) for o in opinions]
            # Attach resolution if any
            resolution = conn.execute("""
                SELECT winning_advisor, resolution_rationale, tradeoff_summary
                FROM pi_advisor_resolution
                WHERE finding_id = ?
                ORDER BY created_at DESC LIMIT 1
            """, (f["id"],)).fetchall()
            item["resolution"] = dict(resolution[0]) if resolution else None
            result.append(item)

        return jsonify({"findings": result})

@admin_bp.route("/api/admin/intelligence/findings/<int:finding_id>/transition", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceTransition")
def admin_intelligence_transition(finding_id):
    """Advance finding state machine."""
    from ..intelligence.finding_lifecycle import transition_finding
    data = request.get_json(silent=True) or {}
    status = data.get("status", "")
    notes = data.get("notes", "")
    with db.connection() as conn:
        ok = transition_finding(conn, finding_id, status, notes)
        result = {"success": ok}
        if ok:
            try:
                from ..intelligence.prescription import _check_subordination
                warning = _check_subordination(conn, finding_id)
                if warning:
                    result["subordination_warning"] = warning
            except ImportError:
                pass
            try:
                from ..intelligence.collaborator import log_interaction
                itype = "finding_dismissed" if status == "rejected" else "finding_approved"
                log_interaction(conn, itype, finding_id=finding_id,
                                notes=f"transition to {status}")
            except (ImportError, Exception):
                pass
            return jsonify(result)
        return jsonify({"error": "Invalid transition"}), 400

@admin_bp.route("/api/admin/intelligence/findings/<int:finding_id>/decide", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceDecide")
def admin_intelligence_decide(finding_id):
    """Record human decision on a finding."""
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "")
    reason = data.get("reason", "")
    override_expires = data.get("override_expires_at")
    with db.connection() as conn:
        try:
            conn.execute("""
                INSERT INTO pi_decision_log
                    (finding_id, decision_class, escalation_level,
                     presented_to, decision, decision_reason,
                     override_expires_at)
                VALUES (?, ?, ?, 'solo', ?, ?, ?)
            """, (
                finding_id,
                data.get("decision_class", "judgment_call"),
                data.get("escalation_level", "alert"),
                decision, reason, override_expires,
            ))
            conn.commit()
            result = {"success": True}
            try:
                from ..intelligence.prescription import _check_subordination
                warning = _check_subordination(conn, finding_id)
                if warning:
                    result["subordination_warning"] = warning
            except ImportError:
                pass
            try:
                from ..intelligence.collaborator import log_interaction
                itype = "finding_dismissed" if decision in ("reject", "defer") else "finding_approved"
                log_interaction(conn, itype, finding_id=finding_id,
                                notes=f"decision: {decision}, reason: {reason}")
            except (ImportError, Exception):
                pass
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/findings/<int:finding_id>/outcome", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceOutcome")
def admin_intelligence_outcome(finding_id):
    """Record recommendation outcome."""
    from ..intelligence.feedback_loops import record_recommendation_outcome
    data = request.get_json(silent=True) or {}
    with db.connection() as conn:
        outcome_id = record_recommendation_outcome(
            conn, finding_id,
            data.get("action_type", "code_change"),
            data.get("description", ""),
            data.get("files_changed"),
            data.get("metric_before"),
        )
        if outcome_id > 0:
            return jsonify({"success": True, "outcome_id": outcome_id})
        return jsonify({"error": "Failed to record outcome"}), 500

@admin_bp.route("/api/admin/intelligence/sprint-plan")
@admin_required
@api_error_handler("IntelligenceSprintPlan")
def admin_intelligence_sprint_plan():
    """Current sprint plan from mediator."""
    try:
        from ..intelligence import run_product_audit
        from ..intelligence.advisors import Mediator
        with db.connection() as conn:
            audit = run_product_audit(conn)
            return jsonify({"sprint_plan": audit.get("sprint_plan", {})})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/feedback-summary")
@admin_required
@api_error_handler("IntelligenceFeedback")
def admin_intelligence_feedback():
    """Feedback loop closure rates and threshold calibrations."""
    try:
        from ..intelligence.feedback_loops import get_loop_closure_summary
        with db.connection() as conn:
            summary = get_loop_closure_summary(conn)
            # Add calibration details
            calibrations = conn.execute("""
                SELECT metric_name, threshold_value, calibrated_at,
                       sample_size, false_positive_rate, prior_threshold, notes
                FROM pi_threshold_calibration
                ORDER BY calibrated_at DESC
            """).fetchall()
            summary["calibrations"] = [dict(c) for c in calibrations]
            return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/engine-meta")
@admin_required
@api_error_handler("IntelligenceEngineMeta")
def admin_intelligence_engine_meta():
    """Engine self-assessment: accuracy, FPR, avg resolution time."""
    try:
        from ..intelligence.finding_lifecycle import compute_engine_accuracy
        with db.connection() as conn:
            accuracy = compute_engine_accuracy(conn)
            return jsonify(accuracy)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Intelligence Engine A+ Endpoints ────────────────────────────

@admin_bp.route("/api/admin/intelligence/findings/<int:finding_id>/approve", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceApprove")
def admin_intelligence_approve(finding_id):
    """Approve a finding that requires approval."""
    with db.connection() as conn:
        try:
            conn.execute("""
                UPDATE pi_decision_log
                SET approved_at = datetime('now')
                WHERE finding_id = ?
                  AND approved_at IS NULL
            """, (finding_id,))
            conn.commit()
            result = {"success": True}
            try:
                from ..intelligence.prescription import _check_subordination
                warning = _check_subordination(conn, finding_id)
                if warning:
                    result["subordination_warning"] = warning
            except ImportError:
                pass
            try:
                from ..intelligence.collaborator import log_interaction
                log_interaction(conn, "finding_approved", finding_id=finding_id)
            except (ImportError, Exception):
                pass
            return jsonify(result)
        except Exception as e_inner:
            return jsonify({"error": str(e_inner)}), 500

@admin_bp.route("/api/admin/intelligence/constraint")
@admin_required
@api_error_handler("IntelligenceConstraint")
def admin_intelligence_constraint():
    """Theory of Constraints: identify system bottleneck."""
    try:
        from ..intelligence import run_product_audit
        with db.connection() as conn:
            audit = run_product_audit(conn)
            return jsonify(audit.get("constraint", {}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/copq")
@admin_required
@api_error_handler("IntelligenceCOPQ")
def admin_intelligence_copq():
    """Six Sigma: Cost of Poor Quality estimation."""
    try:
        from ..intelligence.feedback_loops import estimate_copq
        with db.connection() as conn:
            return jsonify(estimate_copq(conn))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/false-negatives")
@admin_required
@api_error_handler("IntelligenceFalseNegatives")
def admin_intelligence_false_negatives():
    """Six Sigma: false negative signal detection."""
    try:
        from ..intelligence.finding_lifecycle import estimate_false_negatives
        with db.connection() as conn:
            return jsonify(estimate_false_negatives(conn))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/power-analysis/<int:experiment_id>")
@admin_required
@api_error_handler("IntelligencePowerAnalysis")
def admin_intelligence_power_analysis(experiment_id):
    """DoE: power analysis for a running experiment."""
    try:
        from ..intelligence.feedback_loops import compute_power_analysis
        with db.connection() as conn:
            return jsonify(compute_power_analysis(conn, experiment_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/dmaic/<dimension>")
@admin_required
@api_error_handler("IntelligenceDMAIC")
def admin_intelligence_dmaic(dimension):
    """Six Sigma: run DMAIC cycle for a dimension."""
    try:
        from ..intelligence._synthesis import run_dmaic_cycle
        with db.connection() as conn:
            return jsonify(run_dmaic_cycle(conn, dimension))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/cycle-times")
@admin_required
@api_error_handler("IntelligenceCycleTimes")
def admin_intelligence_cycle_times():
    """Lean: finding lifecycle cycle time analysis."""
    try:
        from ..intelligence._synthesis import compute_cycle_times
        with db.connection() as conn:
            return jsonify(compute_cycle_times(conn))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/queue-model")
@admin_required
@api_error_handler("IntelligenceQueueModel")
def admin_intelligence_queue_model():
    """Operations Research: session queue model (Little's Law)."""
    try:
        from ..intelligence.analyzers_domain import analyze_session_queue
        with db.connection() as conn:
            queue_findings = analyze_session_queue(conn)
            return jsonify({
                "findings": [{"title": f["title"], "severity": f["severity"],
                              "analysis": f["analysis"]} for f in queue_findings],
                "count": len(queue_findings),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/self-audit")
@admin_required
@api_error_handler("IntelligenceSelfAudit")
def admin_intelligence_self_audit():
    """Self-Correction Layer: engine self-audit report."""
    try:
        from ..intelligence.feedback_loops import generate_self_audit_report
        lookback = request.args.get("lookback_days", 30, type=int)
        with db.connection() as conn:
            report = generate_self_audit_report(conn, lookback)
            try:
                from ..intelligence.collaborator import log_interaction
                log_interaction(conn, "self_audit_viewed")
            except (ImportError, Exception):
                pass
            return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Prescription Layer endpoints ──

@admin_bp.route("/api/admin/intelligence/work-order/current")
@admin_required
@api_error_handler("IntelligenceWorkOrderCurrent")
def admin_intelligence_work_order_current():
    """Returns active WorkOrder or 404."""
    try:
        from ..intelligence.prescription import get_current_work_order
        with db.connection() as conn:
            wo = get_current_work_order(conn)
            if wo:
                try:
                    from ..intelligence.collaborator import log_interaction, build_adaptive_presentation
                    log_interaction(conn, "work_order_viewed",
                                    work_order_id=wo.get("id"),
                                    dimension=wo.get("constraint_dimension"))
                    presentation = build_adaptive_presentation(conn, wo)
                    wo["presentation"] = presentation
                except (ImportError, Exception):
                    pass
                return jsonify(wo)
            return jsonify({"error": "No active work order"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/work-order/<int:wo_id>/implement", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceWorkOrderImplement")
def admin_intelligence_work_order_implement(wo_id):
    """Marks work order as implemented, starts verification.

    Body (optional): {parameter_name, old_value, new_value}
    If structural change: {parameter_name: null, notes: "description"}
    """
    try:
        from ..intelligence.prescription import mark_work_order_implemented
        data = request.get_json(silent=True) or {}
        with db.connection() as conn:
            ok = mark_work_order_implemented(
                conn, wo_id,
                parameter_name=data.get("parameter_name"),
                old_value=data.get("old_value"),
                new_value=data.get("new_value"),
                notes=data.get("notes"),
            )
            if ok:
                try:
                    from ..intelligence.collaborator import log_interaction
                    log_interaction(conn, "work_order_implemented",
                                    work_order_id=wo_id,
                                    notes=data.get("notes"))
                except (ImportError, Exception):
                    pass
                return jsonify({"success": True, "status": "verifying"})
            return jsonify({"error": "Cannot implement this work order"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/subordination/override", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceSubordinationOverride")
def admin_intelligence_subordination_override():
    """Log a subordination override to pi_decision_log."""
    data = request.get_json(silent=True) or {}
    finding_id = data.get("finding_id")
    reason = data.get("reason", "")
    if not finding_id:
        return jsonify({"error": "finding_id required"}), 400
    with db.connection() as conn:
        try:
            conn.execute("""
                INSERT INTO pi_decision_log
                    (finding_id, decision_class, escalation_level,
                     presented_to, decision, decision_reason)
                VALUES (?, 'subordination_override', 'alert', 'solo',
                        'override_subordination', ?)
            """, (finding_id, reason))
            conn.commit()
            try:
                from ..intelligence.collaborator import log_interaction
                log_interaction(conn, "subordination_overridden",
                                finding_id=finding_id, notes=reason)
            except (ImportError, Exception):
                pass
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/work-order/history")
@admin_required
@api_error_handler("IntelligenceWorkOrderHistory")
def admin_intelligence_work_order_history():
    """Last 20 work orders with outcomes."""
    try:
        from ..intelligence.prescription import get_work_order_history
        limit = request.args.get("limit", 20, type=int)
        with db.connection() as conn:
            history = get_work_order_history(conn, limit)
            return jsonify({"work_orders": history, "count": len(history)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Parameter Graph endpoints ──

@admin_bp.route("/api/admin/intelligence/parameter-graph")
@admin_required
@api_error_handler("IntelligenceParameterGraph")
def admin_intelligence_parameter_graph():
    """Parameter influence graph: nodes (parameters) + edges (influence)."""
    try:
        from ..intelligence.parameter_registry import get_influence_graph
        with db.connection() as conn:
            graph = get_influence_graph(conn)
            return jsonify(graph)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/parameters")
@admin_required
@api_error_handler("IntelligenceParameters")
def admin_intelligence_parameters():
    """List all registered parameters."""
    try:
        from ..intelligence.parameter_registry import get_all_parameters
        with db.connection() as conn:
            params = get_all_parameters(conn)
            return jsonify({
                "parameters": [dict(p) for p in (params or [])],
                "count": len(params or []),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/parameters/sync", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceParameterSync")
def admin_intelligence_parameter_sync():
    """Sync parameter registry and seed influence model."""
    try:
        from ..intelligence.parameter_registry import sync_parameter_registry, seed_influence_model
        with db.connection() as conn:
            synced = sync_parameter_registry(conn)
            seeded = seed_influence_model(conn)
            return jsonify({
                "parameters_synced": synced,
                "edges_seeded": seeded,
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Collaborator Model endpoints ──

@admin_bp.route("/api/admin/intelligence/collaborator-model")
@admin_required
@api_error_handler("IntelligenceCollaboratorModel")
def admin_intelligence_collaborator_model():
    """Current collaborator model — timing, overrides, presentation prefs."""
    try:
        from ..intelligence.collaborator import get_collaborator_model, rebuild_collaborator_model
        with db.connection() as conn:
            model = get_collaborator_model(conn)
            if not model:
                rebuild_collaborator_model(conn)
                model = get_collaborator_model(conn)
            return jsonify(dict(model) if model else {"status": "no_data"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/collaborator-model/history")
@admin_required
@api_error_handler("IntelligenceCollaboratorModelHistory")
def admin_intelligence_collaborator_model_history():
    """Collaborator model snapshots over time."""
    try:
        from ..intelligence.collaborator import get_collaborator_model_history
        limit = request.args.get("limit", 20, type=int)
        with db.connection() as conn:
            history = get_collaborator_model_history(conn, limit)
            return jsonify({"snapshots": [dict(h) for h in history], "count": len(history)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/domain-trust")
@admin_required
@api_error_handler("IntelligenceDomainTrust")
def admin_intelligence_domain_trust():
    """Bidirectional trust scores by dimension."""
    try:
        from ..intelligence.collaborator import get_domain_trust
        with db.connection() as conn:
            trust = get_domain_trust(conn)
            return jsonify({"domains": [dict(t) for t in trust], "count": len(trust)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/collaborator-model/correct", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceCollaboratorCorrect")
def admin_intelligence_collaborator_correct():
    """Record a correction to the collaborator model."""
    try:
        from ..intelligence.collaborator import record_correction
        data = request.get_json(silent=True) or {}
        correction_type = data.get("correction_type", "")
        dimension = data.get("dimension")
        notes = data.get("notes", "")
        if not correction_type:
            return jsonify({"error": "correction_type required"}), 400
        with db.connection() as conn:
            record_correction(conn, correction_type, dimension, notes)
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/adaptations/disable-all", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceDisableAllAdaptations")
def admin_intelligence_disable_all_adaptations():
    """Kill switch: disable all collaborator model adaptations."""
    try:
        from ..intelligence.collaborator import disable_all_adaptations
        with db.connection() as conn:
            disable_all_adaptations(conn)
            return jsonify({"success": True, "adaptations_enabled": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/adaptations/enable", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceEnableAdaptations")
def admin_intelligence_enable_adaptations():
    """Re-enable collaborator model adaptations."""
    try:
        from ..intelligence.collaborator import enable_adaptations
        with db.connection() as conn:
            enable_adaptations(conn)
            return jsonify({"success": True, "adaptations_enabled": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── External Grounding endpoints ──

@admin_bp.route("/api/admin/intelligence/knowledge-base")
@admin_required
@api_error_handler("IntelligenceKnowledgeBase")
def admin_intelligence_knowledge_base():
    """All active pedagogical knowledge entries."""
    try:
        from ..intelligence.external_grounding import get_knowledge_base
        with db.connection() as conn:
            entries = get_knowledge_base(conn)
            return jsonify({"entries": entries, "count": len(entries)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/knowledge-base", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceKnowledgeBaseAdd")
def admin_intelligence_knowledge_base_add():
    """Add a new knowledge entry (human only)."""
    try:
        from ..intelligence.external_grounding import add_knowledge_entry
        data = request.get_json(silent=True) or {}
        required = ["domain", "finding_text", "source_author",
                    "source_year", "source_title", "evidence_quality"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
        with db.connection() as conn:
            entry_id = add_knowledge_entry(conn, data)
            if entry_id:
                return jsonify({"success": True, "id": entry_id})
            return jsonify({"error": "Failed to add entry"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/knowledge-conflicts")
@admin_required
@api_error_handler("IntelligenceKnowledgeConflicts")
def admin_intelligence_knowledge_conflicts():
    """Active and resolved knowledge conflicts."""
    try:
        from ..intelligence.external_grounding import get_knowledge_conflicts
        include_resolved = request.args.get("include_resolved", "true").lower() == "true"
        with db.connection() as conn:
            conflicts = get_knowledge_conflicts(conn, include_resolved)
            return jsonify({"conflicts": conflicts, "count": len(conflicts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/knowledge-conflicts/<conflict_id>/resolve", methods=["POST"])
@admin_required
@api_error_handler("IntelligenceResolveConflict")
def admin_intelligence_resolve_conflict(conflict_id):
    """Human resolves a flagged knowledge conflict."""
    try:
        from ..intelligence.external_grounding import resolve_conflict
        data = request.get_json(silent=True) or {}
        resolution = data.get("resolution", "")
        rationale = data.get("resolution_rationale", "")
        if not resolution:
            return jsonify({"error": "resolution required"}), 400
        with db.connection() as conn:
            ok = resolve_conflict(conn, conflict_id, resolution, rationale)
            if ok:
                return jsonify({"success": True})
            return jsonify({"error": "Failed to resolve conflict"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/benchmarks")
@admin_required
@api_error_handler("IntelligenceBenchmarks")
def admin_intelligence_benchmarks():
    """Benchmark registry with most recent comparisons."""
    try:
        from ..intelligence.external_grounding import get_benchmark_comparisons
        with db.connection() as conn:
            benchmarks = get_benchmark_comparisons(conn)
            return jsonify({"benchmarks": benchmarks, "count": len(benchmarks)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/goal-coherence")
@admin_required
@api_error_handler("IntelligenceGoalCoherence")
def admin_intelligence_goal_coherence():
    """Most recent goal coherence check result."""
    try:
        from ..intelligence.external_grounding import get_latest_goal_coherence
        with db.connection() as conn:
            result = get_latest_goal_coherence(conn)
            return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Product Experience endpoints ──

@admin_bp.route("/api/events/batch", methods=["POST"])
def ingest_interaction_events():
    """Accept batched interaction events from client. Never errors."""
    try:
        from ..intelligence.product_experience import ingest_events
        data = request.get_json(force=True, silent=True) or {}
        events = data.get("events", [])
        with db.connection() as conn:
            accepted = ingest_events(conn, events)
            return jsonify({"accepted": accepted}), 200
    except Exception:
        return jsonify({"accepted": 0}), 200

@admin_bp.route("/api/admin/releases", methods=["POST"])
@admin_required
@api_error_handler("RegisterRelease")
def admin_register_release():
    """Register a new release with change categories."""
    try:
        from ..intelligence.product_experience import register_release
        data = request.get_json(silent=True) or {}
        version = data.get("app_version")
        if not version:
            return jsonify({"error": "app_version required"}), 400
        with db.connection() as conn:
            release_id = register_release(
                conn, version,
                release_notes=data.get("release_notes"),
                changed_ux=data.get("changed_ux", False),
                changed_srs=data.get("changed_srs", False),
                changed_content=data.get("changed_content", False),
                changed_auth=data.get("changed_auth", False),
                changed_api=data.get("changed_api", False),
            )
            if release_id:
                return jsonify({"success": True, "release_id": release_id}), 201
            return jsonify({"error": "Failed to register release"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/releases")
@admin_required
@api_error_handler("ListReleases")
def admin_list_releases():
    """List releases with analysis status."""
    try:
        from ..intelligence.product_experience import get_releases
        with db.connection() as conn:
            releases = get_releases(conn)
            return jsonify({"releases": releases, "count": len(releases)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/releases/<release_id>/analysis")
@admin_required
@api_error_handler("ReleaseAnalysis")
def admin_release_analysis(release_id):
    """Full regression analysis for a specific release."""
    try:
        from ..intelligence.product_experience import get_release_analysis
        with db.connection() as conn:
            analysis = get_release_analysis(conn, release_id)
            if analysis:
                return jsonify(analysis)
            return jsonify({"error": "Release not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/ux-summary")
@admin_required
@api_error_handler("IntelligenceUXSummary")
def admin_intelligence_ux_summary():
    """Aggregated UX signal: feedback trends, rage clicks, errors."""
    try:
        from ..intelligence.product_experience import get_ux_summary
        lookback = request.args.get("lookback_days", 14, type=int)
        with db.connection() as conn:
            summary = get_ux_summary(conn, lookback)
            return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/screen-health")
@admin_required
@api_error_handler("IntelligenceScreenHealth")
def admin_intelligence_screen_health():
    """Per-screen friction score and health metrics."""
    try:
        from ..intelligence.product_experience import get_screen_health
        lookback = request.args.get("lookback_days", 14, type=int)
        with db.connection() as conn:
            screens = get_screen_health(conn, lookback)
            return jsonify({"screens": screens, "count": len(screens)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Methodology Coverage endpoints ──

@admin_bp.route("/api/admin/intelligence/methodology")
@admin_required
@api_error_handler("IntelligenceMethodology")
def admin_intelligence_methodology():
    """All framework summary grades and trends."""
    try:
        from ..intelligence.methodology_coverage import grade_all_frameworks
        with db.connection() as conn:
            grades = grade_all_frameworks(conn)
            return jsonify(grades)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/methodology/<framework>")
@admin_required
@api_error_handler("IntelligenceMethodologyDetail")
def admin_intelligence_methodology_detail(framework):
    """Component-level grades for one framework."""
    try:
        from ..intelligence.methodology_coverage import grade_all_frameworks
        with db.connection() as conn:
            grades = grade_all_frameworks(conn)
            fw = grades.get("frameworks", {}).get(framework)
            if not fw:
                return jsonify({"error": f"Framework '{framework}' not found"}), 404
            return jsonify({"framework": framework, **fw})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route(
    "/api/admin/intelligence/methodology/<framework>/<component>/override",
    methods=["POST"],
)
@admin_required
@api_error_handler("IntelligenceMethodologyOverride")
def admin_intelligence_methodology_override(framework, component):
    """Human grade override for a specific component."""
    try:
        import uuid as _uuid
        data = request.get_json(silent=True) or {}
        score = data.get("score")
        reason = data.get("reason")
        if score is None or reason is None:
            return jsonify({"error": "score and reason required"}), 400
        score = float(score)
        if not (0 <= score <= 100):
            return jsonify({"error": "score must be 0-100"}), 400
        from ..intelligence.methodology_coverage import _score_to_grade
        grade_label = _score_to_grade(score)
        with db.connection() as conn:
            conn.execute(
                """INSERT INTO pi_framework_grades
                   (id, framework, component_name, raw_score, weighted_score,
                    grade_label, evidence, solo_dev_applicable,
                    was_overridden, override_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (str(_uuid.uuid4()), framework, component,
                 score, score, grade_label, "[]", "yes", reason),
            )
            conn.commit()
            return jsonify({
                "status": "overridden",
                "framework": framework,
                "component": component,
                "score": score,
                "grade": grade_label,
                "reason": reason,
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/api/admin/intelligence/methodology/history")
@admin_required
@api_error_handler("IntelligenceMethodologyHistory")
def admin_intelligence_methodology_history():
    """Last 12 audits of framework grades."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT framework, overall_score, overall_grade,
                          applicable_component_count, na_component_count,
                          gap_count, prior_grade, trend, summary_text, graded_at
                   FROM pi_framework_summary_grades
                   ORDER BY graded_at DESC
                   LIMIT ?""",
                (12 * 9,),  # 12 audits × 9 frameworks
            ).fetchall()
            history = [
                {
                    "framework": r["framework"],
                    "score": r["overall_score"],
                    "grade": r["overall_grade"],
                    "applicable_count": r["applicable_component_count"],
                    "na_count": r["na_component_count"],
                    "gap_count": r["gap_count"],
                    "prior_grade": r["prior_grade"],
                    "trend": r["trend"],
                    "summary": r["summary_text"],
                    "graded_at": r["graded_at"],
                }
                for r in rows
            ]
            return jsonify({"history": history, "count": len(history)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── AI / Ollama endpoints ────────────────────────────────────────────────


@admin_bp.route("/api/admin/ai/health")
@admin_required
@api_error_handler("AI Health")
def admin_ai_health():
    """Ollama health + generation stats."""
    from ..ai.health import check_ollama_health
    with db.connection() as conn:
        return jsonify(check_ollama_health(conn))


@admin_bp.route("/api/admin/ai/review-queue")
@admin_required
@api_error_handler("AI Review Queue")
def admin_ai_review_queue():
    """Pending items needing review."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, queued_at, content_type, content_json, validation_issues,
                   encounter_id, reviewed_at, review_decision, provenance_checked
            FROM pi_ai_review_queue
            WHERE reviewed_at IS NULL
            ORDER BY queued_at ASC
            LIMIT 100
        """).fetchall()
        items = [
            {
                "id": r["id"],
                "queued_at": r["queued_at"],
                "content_type": r["content_type"],
                "content": json.loads(r["content_json"]) if r["content_json"] else {},
                "validation_issues": json.loads(r["validation_issues"]) if r["validation_issues"] else [],
                "encounter_id": r["encounter_id"],
                "provenance_checked": r["provenance_checked"] or 0,
            }
            for r in rows
        ]
        return jsonify({"items": items, "count": len(items)})


@admin_bp.route("/api/admin/ai/review-queue/<item_id>/approve", methods=["POST"])
@admin_required
@api_error_handler("AI Review Approve")
def admin_ai_review_approve(item_id):
    """Approve a review item → insert into content_item.

    Requires provenance_checked=1 in the request body to confirm the
    reviewer has verified content does not come from a published source.
    """
    import uuid
    data = request.get_json(silent=True) or {}
    provenance_checked = data.get("provenance_checked", 0)

    if not provenance_checked:
        return jsonify({
            "error": "Provenance check required. Confirm content does not "
                     "appear to be from a published source before approving."
        }), 400

    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM pi_ai_review_queue WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404

        content = json.loads(row["content_json"])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Insert into content_item (approved — admin has reviewed)
        new_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO content_item
               (id, hanzi, pinyin, english, hsk_level, status, source,
                example_sentence_hanzi, example_sentence_pinyin, example_sentence_english,
                review_status)
               VALUES (?, ?, ?, ?, ?, 'drill_ready', 'ai_generated', ?, ?, ?,
                       'approved')""",
            (new_id, content.get("hanzi", ""), content.get("pinyin", ""),
             content.get("english", ""), content.get("hsk_level", 1),
             content.get("example_sentence_hanzi", ""),
             content.get("example_sentence_pinyin", ""),
             content.get("example_sentence_english", "")),
        )

        # Mark reviewed with provenance check recorded
        conn.execute(
            """UPDATE pi_ai_review_queue
               SET reviewed_at = ?, reviewed_by = 'admin',
                   review_decision = 'approved', provenance_checked = 1
               WHERE id = ?""",
            (now, item_id),
        )

        # Update encounter if linked
        if row["encounter_id"]:
            conn.execute(
                """UPDATE vocab_encounter
                   SET drill_generation_status = 'generated', generated_item_id = ?
                   WHERE id = ?""",
                (new_id, row["encounter_id"]),
            )

        conn.commit()
        return jsonify({"status": "approved", "content_item_id": new_id})


@admin_bp.route("/api/admin/ai/review-queue/<item_id>/reject", methods=["POST"])
@admin_required
@api_error_handler("AI Review Reject")
def admin_ai_review_reject(item_id):
    """Reject a review item with notes."""
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM pi_ai_review_queue WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404

        conn.execute(
            """UPDATE pi_ai_review_queue
               SET reviewed_at = ?, reviewed_by = 'admin',
                   review_decision = 'rejected', review_notes = ?
               WHERE id = ?""",
            (now, notes, item_id),
        )
        conn.commit()
        return jsonify({"status": "rejected"})


@admin_bp.route("/api/admin/ai/review-queue/<item_id>/edit", methods=["POST"])
@admin_required
@api_error_handler("AI Review Edit")
def admin_ai_review_edit(item_id):
    """Edit content + approve.

    Requires provenance_checked=1 to confirm the reviewer has verified
    content does not come from a published source.
    """
    import uuid
    data = request.get_json(silent=True) or {}
    edited = data.get("content", {})
    notes = data.get("notes", "")
    provenance_checked = data.get("provenance_checked", 0)

    if not edited:
        return jsonify({"error": "content required"}), 400

    if not provenance_checked:
        return jsonify({
            "error": "Provenance check required. Confirm content does not "
                     "appear to be from a published source before approving."
        }), 400

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM pi_ai_review_queue WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404

        # Insert edited content into content_item (approved — admin edited + approved)
        new_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO content_item
               (id, hanzi, pinyin, english, hsk_level, status, source,
                example_sentence_hanzi, example_sentence_pinyin, example_sentence_english,
                review_status)
               VALUES (?, ?, ?, ?, ?, 'drill_ready', 'ai_generated', ?, ?, ?,
                       'approved')""",
            (new_id, edited.get("hanzi", ""), edited.get("pinyin", ""),
             edited.get("english", ""), edited.get("hsk_level", 1),
             edited.get("example_sentence_hanzi", ""),
             edited.get("example_sentence_pinyin", ""),
             edited.get("example_sentence_english", "")),
        )

        conn.execute(
            """UPDATE pi_ai_review_queue
               SET reviewed_at = ?, reviewed_by = 'admin',
                   review_decision = 'edited',
                   edited_content_json = ?, review_notes = ?,
                   provenance_checked = 1
               WHERE id = ?""",
            (now, json.dumps(edited, ensure_ascii=False), notes, item_id),
        )

        if row["encounter_id"]:
            conn.execute(
                """UPDATE vocab_encounter
                   SET drill_generation_status = 'generated', generated_item_id = ?
                   WHERE id = ?""",
                (new_id, row["encounter_id"]),
            )

        conn.commit()
        return jsonify({"status": "edited", "content_item_id": new_id})


# ── ML endpoints ─────────────────────────────────────────────────────


@admin_bp.route("/api/admin/intelligence/ai-portfolio")
@admin_required
@api_error_handler("AI Portfolio")
def admin_ai_portfolio():
    """AI portfolio verdict — are AI components net positive?"""
    from ..intelligence.ai_outcome import compute_ai_portfolio_verdict
    with db.connection() as conn:
        return jsonify(compute_ai_portfolio_verdict(conn))


@admin_bp.route("/api/admin/intelligence/ai-portfolio/history")
@admin_required
@api_error_handler("AI Portfolio History")
def admin_ai_portfolio_history():
    """Historical AI portfolio assessments."""
    limit = request.args.get("limit", 20, type=int)
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, assessed_at, net_verdict, component_verdicts_json,
                   top_ai_win, top_ai_risk, maintenance_burden_estimate_hrs_week,
                   recommendation, prior_verdict, trend
            FROM pi_ai_portfolio_assessments
            ORDER BY assessed_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return jsonify([dict(r) for r in rows])


@admin_bp.route("/api/admin/intelligence/ai-portfolio/component/<component>")
@admin_required
@api_error_handler("AI Component Detail")
def admin_ai_component_detail(component):
    """Per-component measurements over time."""
    limit = request.args.get("limit", 50, type=int)
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, measured_at, dimension, metric_name, metric_value,
                   metric_unit, status, evidence, sample_size, confidence
            FROM pi_ai_outcome_measurements
            WHERE component = ?
            ORDER BY measured_at DESC LIMIT ?
        """, (component, limit)).fetchall()
        return jsonify([dict(r) for r in rows])


@admin_bp.route("/api/admin/intelligence/ai-portfolio/suspend/<component>", methods=["POST"])
@admin_required
@api_error_handler("AI Component Suspend")
def admin_ai_component_suspend(component):
    """Suspend an AI component via feature flag."""
    from ..intelligence.ai_outcome import COMPONENTS
    if component not in COMPONENTS:
        return jsonify({"error": f"Unknown component: {component}"}), 400
    with db.connection() as conn:
        flag_name = f"ai_component_{component}_suspended"
        conn.execute("""
            INSERT OR REPLACE INTO feature_flag (name, enabled, updated_at)
            VALUES (?, 1, datetime('now'))
        """, (flag_name,))
        conn.commit()
        return jsonify({"status": "suspended", "component": component, "flag": flag_name})


@admin_bp.route("/api/admin/intelligence/ai-portfolio/resume/<component>", methods=["POST"])
@admin_required
@api_error_handler("AI Component Resume")
def admin_ai_component_resume(component):
    """Resume a suspended AI component."""
    from ..intelligence.ai_outcome import COMPONENTS
    if component not in COMPONENTS:
        return jsonify({"error": f"Unknown component: {component}"}), 400
    with db.connection() as conn:
        flag_name = f"ai_component_{component}_suspended"
        conn.execute("""
            UPDATE feature_flag SET enabled = 0, updated_at = datetime('now')
            WHERE name = ?
        """, (flag_name,))
        conn.commit()
        return jsonify({"status": "resumed", "component": component, "flag": flag_name})


@admin_bp.route("/api/admin/ml/health")
@admin_required
@api_error_handler("ML Health")
def admin_ml_health():
    """ML system health — model status, predictions, pipeline runs."""
    from ..intelligence.feedback_loops import _collect_ml_health
    with db.connection() as conn:
        return jsonify(_collect_ml_health(conn))


@admin_bp.route("/api/admin/ml/train", methods=["POST"])
@admin_required
@api_error_handler("ML Train")
def admin_ml_train():
    """Trigger ML training pipeline."""
    from ..ml.training_pipeline import run_ml_pipeline
    with db.connection() as conn:
        results = run_ml_pipeline(conn)
        return jsonify(results)


@admin_bp.route("/api/admin/intelligence/coverage")
@admin_required
@api_error_handler("Coverage Audit")
def admin_intelligence_coverage():
    """Coverage audit summary with gap list and closure priorities."""
    from ..intelligence.coverage_audit import get_coverage_summary, get_gap_closure_priority
    with db.connection() as conn:
        summary = get_coverage_summary(conn)
        summary["gap_closure_priority"] = get_gap_closure_priority()
        return jsonify(summary)


@admin_bp.route("/api/admin/intelligence/constraint-history")
@admin_required
@api_error_handler("Constraint History")
def admin_intelligence_constraint_history():
    """Historical constraints from pi_system_constraint_history."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, identified_at, constraint_type, domain, severity,
                   description, resolved_at, resolution
            FROM pi_system_constraint_history
            ORDER BY identified_at DESC
            LIMIT 50
        """).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Email Drafts (Doc 23 B-04) ──────────────────────────────────────────────

@admin_bp.route("/api/admin/email-drafts")
@admin_required
def get_email_drafts():
    """List pending email drafts."""
    from ..ai.teacher_comms import get_pending_drafts
    with db.connection() as conn:
        drafts = get_pending_drafts(conn)
        return jsonify(drafts)


@admin_bp.route("/api/admin/email-drafts/<int:draft_id>/approve", methods=["POST"])
@admin_required
def approve_email_draft(draft_id):
    """Approve an email draft. Does NOT auto-send."""
    from ..ai.teacher_comms import approve_draft
    with db.connection() as conn:
        success = approve_draft(conn, draft_id, current_user.id)
        if success:
            return jsonify({"status": "approved", "id": draft_id})
        return jsonify({"error": "draft not found or not in draft status"}), 404


@admin_bp.route("/api/admin/email-drafts/<int:draft_id>/reject", methods=["POST"])
@admin_required
def reject_email_draft(draft_id):
    """Reject an email draft with optional reason."""
    from ..ai.teacher_comms import reject_draft
    data = request.get_json(silent=True) or {}
    with db.connection() as conn:
        success = reject_draft(conn, draft_id, reason=data.get("reason", ""))
        if success:
            return jsonify({"status": "rejected", "id": draft_id})
        return jsonify({"error": "draft not found or not in draft status"}), 404


@admin_bp.route("/api/admin/email-drafts/<int:draft_id>/edit", methods=["POST"])
@admin_required
def edit_email_draft(draft_id):
    """Edit a draft's subject and/or body."""
    from ..ai.teacher_comms import edit_draft
    data = request.get_json(silent=True) or {}
    with db.connection() as conn:
        success = edit_draft(
            conn, draft_id,
            subject=data.get("subject"),
            body_text=data.get("body_text"),
        )
        if success:
            return jsonify({"status": "updated", "id": draft_id})
        return jsonify({"error": "draft not found or not in draft status"}), 404


@admin_bp.route("/api/admin/email-drafts/<int:draft_id>/send", methods=["POST"])
@admin_required
def send_email_draft(draft_id):
    """Mark approved draft as sent (separate step from approve)."""
    from ..ai.teacher_comms import mark_sent
    with db.connection() as conn:
        success = mark_sent(conn, draft_id)
        if success:
            return jsonify({"status": "sent", "id": draft_id})
        return jsonify({"error": "draft not found or not in approved status"}), 404


# ── Invite Code Management ─────────────────────────────────────────

@admin_bp.route("/api/admin/invite-codes", methods=["GET"])
@admin_required
@api_error_handler("Invite codes list")
def list_invite_codes():
    """List all invite codes with usage stats."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT code, created_at, used_by, used_at, max_uses, use_count,
                   expires_at, created_by, label
            FROM invite_code
            ORDER BY created_at DESC
        """).fetchall()
        codes = []
        for r in rows:
            codes.append({
                "code": r["code"],
                "created_at": r["created_at"],
                "used_by": r["used_by"],
                "used_at": r["used_at"],
                "max_uses": r["max_uses"] or 1,
                "use_count": r["use_count"] or 0,
                "uses_remaining": max(0, (r["max_uses"] or 1) - (r["use_count"] or 0)),
                "expires_at": r["expires_at"],
                "created_by": r["created_by"],
                "label": r["label"] or "",
            })
        return jsonify({"invite_codes": codes})


@admin_bp.route("/api/admin/invite-codes", methods=["POST"])
@admin_required
@api_error_handler("Create invite code")
def create_invite_code():
    """Create a new invite code.

    JSON body:
    - code (optional): custom code string; auto-generated if omitted
    - max_uses (optional): number of allowed uses, default 1
    - expires_at (optional): ISO datetime string for expiration
    - label (optional): human-readable label/note
    """
    import secrets as _secrets

    data = request.get_json(silent=True) or {}
    code = (str(data.get("code") or "")).strip()
    if not code:
        code = _secrets.token_urlsafe(8)

    max_uses = data.get("max_uses", 1)
    try:
        max_uses = int(max_uses)
        if max_uses < 1:
            max_uses = 1
    except (TypeError, ValueError):
        max_uses = 1

    expires_at = data.get("expires_at")
    if expires_at:
        expires_at = str(expires_at).strip()
    else:
        expires_at = None

    label = (str(data.get("label") or "")).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with db.connection() as conn:
        # Check for duplicate
        existing = conn.execute(
            "SELECT code FROM invite_code WHERE code = ?", (code,)
        ).fetchone()
        if existing:
            return jsonify({"error": "Invite code already exists"}), 409

        conn.execute("""
            INSERT INTO invite_code (code, created_at, max_uses, use_count, expires_at, created_by, label)
            VALUES (?, ?, ?, 0, ?, ?, ?)
        """, (code, now, max_uses, expires_at, current_user.id, label))
        conn.commit()

        return jsonify({
            "code": code,
            "max_uses": max_uses,
            "use_count": 0,
            "uses_remaining": max_uses,
            "expires_at": expires_at,
            "label": label,
            "created_at": now,
        }), 201


# ---------------------------------------------------------------------------
# Blocked work visibility (item 4)
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/work-items/blocked")
@admin_required
@api_error_handler("Blocked work items")
def admin_blocked_work_items():
    """Return all blocked work items with duration."""
    try:
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT id, title, description, service_class, blocked_at, blocked_reason,
                       CAST(julianday('now') - julianday(blocked_at) AS INTEGER) AS blocked_days
                FROM work_item
                WHERE status = 'blocked'
                  AND blocked_at IS NOT NULL
                ORDER BY blocked_at ASC
            """).fetchall()
            items = [dict(r) for r in rows]
        return jsonify({"blocked_items": items, "count": len(items)})
    except sqlite3.OperationalError:
        return jsonify({"blocked_items": [], "count": 0})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Blocked work items error: %s", e)
        return jsonify({"error": "Blocked items unavailable"}), 500


# ---------------------------------------------------------------------------
# Work items filtered by implementation type (item 8)
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/work-items/by-type")
@admin_required
@api_error_handler("Work items by type")
def admin_work_items_by_type():
    """Filter work items by implementation_type (prototype/full)."""
    impl_type = request.args.get("implementation_type")
    try:
        with db.connection() as conn:
            if impl_type:
                rows = conn.execute(
                    """SELECT id, title, status, service_class, implementation_type,
                              estimate, created_at, completed_at
                       FROM work_item WHERE implementation_type = ?
                       ORDER BY created_at DESC""",
                    (impl_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, title, status, service_class, implementation_type,
                              estimate, created_at, completed_at
                       FROM work_item WHERE implementation_type IS NOT NULL
                       ORDER BY created_at DESC"""
                ).fetchall()
            items = [dict(r) for r in rows]
        return jsonify({"items": items, "count": len(items)})
    except sqlite3.OperationalError:
        return jsonify({"items": [], "count": 0})


# ---------------------------------------------------------------------------
# Spiral: Risk taxonomy coverage check (item 10)
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/risks/coverage")
@admin_required
@api_error_handler("Risk coverage")
def admin_risk_coverage():
    """Check which predefined risk categories have active risks and which have none."""
    REQUIRED_CATEGORIES = ["technical", "operational", "business", "security", "compliance"]
    try:
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT category, COUNT(*) as count
                FROM risk_item
                WHERE status = 'active'
                GROUP BY category
            """).fetchall()
            active_map = {r["category"]: r["count"] for r in rows}

            coverage = []
            gaps = []
            for cat in REQUIRED_CATEGORIES:
                count = active_map.get(cat, 0)
                coverage.append({
                    "category": cat,
                    "active_count": count,
                    "covered": count > 0,
                })
                if count == 0:
                    gaps.append(cat)

        return jsonify({
            "coverage": coverage,
            "gaps": gaps,
            "all_covered": len(gaps) == 0,
            "alert": f"No active risks in: {', '.join(gaps)}" if gaps else None,
        })
    except sqlite3.OperationalError:
        return jsonify({"coverage": [], "gaps": REQUIRED_CATEGORIES, "all_covered": False})


# ---------------------------------------------------------------------------
# Lean Six Sigma: Pareto analysis of defect types (item 6)
# Already exists at /api/admin/quality/pareto — verified functional.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Lean Six Sigma: Pp/Ppk process performance (item 5)
# Already exists at /api/admin/quality/performance via assess_accuracy_performance.
# Verified: capability.py has calculate_process_performance with Pp/Ppk.
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════════════════════════
# Methodology A+ Gap Closures — Phase 2
# ═══════════════════════════════════════════════════════════════════════════


# ── Scrum: Sprint CRUD ──────────────────────────────────────────────────

@admin_bp.route("/api/admin/sprints", methods=["POST"])
@admin_required
@api_error_handler("Create sprint")
def admin_create_sprint():
    """Create a sprint with goal, start_date, end_date."""
    data = request.get_json()
    if not data or not data.get("start_date") or not data.get("end_date"):
        return jsonify({"error": "start_date and end_date required"}), 400
    with db.connection() as conn:
        # Check for existing active sprint
        active = conn.execute(
            "SELECT id FROM sprint WHERE status = 'active' LIMIT 1"
        ).fetchone()
        if active:
            return jsonify({"error": "An active sprint already exists (id={})".format(active["id"])}), 409
        # Determine sprint number
        last = conn.execute("SELECT MAX(sprint_number) as n FROM sprint").fetchone()
        next_num = ((last["n"] or 0) if last else 0) + 1
        cur = conn.execute("""
            INSERT INTO sprint (user_id, sprint_number, goal, started_at, ended_at,
                                planned_points, status)
            VALUES (1, ?, ?, ?, NULL, ?, 'active')
        """, (next_num, data.get("goal", ""),
              data["start_date"], data.get("planned_points", 0)))
        conn.commit()
        sprint_id = cur.lastrowid
    return jsonify({"id": sprint_id, "sprint_number": next_num, "status": "created"}), 201


@admin_bp.route("/api/admin/sprints")
@admin_required
@api_error_handler("List sprints")
def admin_list_sprints():
    """List sprints with stats."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM work_item WHERE sprint_id = s.id) as item_count,
                   (SELECT COUNT(*) FROM work_item WHERE sprint_id = s.id AND status = 'done') as done_count
            FROM sprint s
            ORDER BY s.sprint_number DESC
            LIMIT 50
        """).fetchall()
        sprints = []
        for r in rows:
            d = dict(r)
            d["item_count"] = d.get("item_count") or 0
            d["done_count"] = d.get("done_count") or 0
            sprints.append(d)
    return jsonify({"sprints": sprints})


@admin_bp.route("/api/admin/sprints/current")
@admin_required
@api_error_handler("Current sprint")
def admin_current_sprint():
    """Get the active sprint."""
    with db.connection() as conn:
        row = conn.execute("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM work_item WHERE sprint_id = s.id) as item_count,
                   (SELECT COUNT(*) FROM work_item WHERE sprint_id = s.id AND status = 'done') as done_count
            FROM sprint s
            WHERE s.status = 'active'
            ORDER BY s.sprint_number DESC LIMIT 1
        """).fetchone()
        if not row:
            return jsonify({"sprint": None})
        sprint = dict(row)
        sprint["item_count"] = sprint.get("item_count") or 0
        sprint["done_count"] = sprint.get("done_count") or 0
    return jsonify({"sprint": sprint})


@admin_bp.route("/api/admin/sprints/<int:sprint_id>/complete", methods=["PUT"])
@admin_required
@api_error_handler("Complete sprint")
def admin_complete_sprint(sprint_id):
    """Complete a sprint, compute velocity."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM sprint WHERE id = ?", (sprint_id,)).fetchone()
        if not row:
            return jsonify({"error": "Sprint not found"}), 404
        if row["status"] != "active":
            return jsonify({"error": "Sprint is not active"}), 400

        # Compute velocity from work items in this sprint
        stats = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done
            FROM work_item WHERE sprint_id = ?
        """, (sprint_id,)).fetchone()
        total = (stats["total"] or 0) if stats else 0
        done = (stats["done"] or 0) if stats else 0
        completed_points = done * 2  # rough estimate

        conn.execute("""
            UPDATE sprint SET status = 'completed', ended_at = datetime('now'),
                   completed_items = ?, completed_points = ?,
                   velocity = ?
            WHERE id = ?
        """, (done, completed_points,
              round(done / max(total, 1), 2), sprint_id))
        conn.commit()
    return jsonify({"status": "completed", "completed_items": done,
                     "completed_points": completed_points, "total_items": total})


@admin_bp.route("/api/admin/sprints/<int:sprint_id>/retro", methods=["PUT"])
@admin_required
@api_error_handler("Sprint retrospective")
def admin_sprint_retro(sprint_id):
    """Save retrospective data on a sprint."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    with db.connection() as conn:
        row = conn.execute("SELECT id FROM sprint WHERE id = ?", (sprint_id,)).fetchone()
        if not row:
            return jsonify({"error": "Sprint not found"}), 404
        conn.execute("""
            UPDATE sprint SET review_notes = ?,
                   retro_went_well = ?, retro_improve = ?, retro_action_items = ?
            WHERE id = ?
        """, (data.get("review_notes"), data.get("went_well"),
              data.get("improve"), data.get("action_items"), sprint_id))
        conn.commit()
    return jsonify({"status": "retrospective saved", "sprint_id": sprint_id})


# ── Agile: Standalone Retrospectives ────────────────────────────────────

@admin_bp.route("/api/admin/retrospectives", methods=["POST"])
@admin_required
@api_error_handler("Create retrospective")
def admin_create_retrospective():
    """Save a retrospective (standalone, not sprint-bound)."""
    data = request.get_json()
    if not data or not data.get("went_well"):
        return jsonify({"error": "went_well is required"}), 400
    with db.connection() as conn:
        cur = conn.execute("""
            INSERT INTO retrospective (period, went_well, improve, action_items, sprint_id)
            VALUES (?, ?, ?, ?, ?)
        """, (data.get("period"), data["went_well"],
              data.get("improve"), data.get("action_items"),
              data.get("sprint_id")))
        conn.commit()
    return jsonify({"id": cur.lastrowid, "status": "created"}), 201


@admin_bp.route("/api/admin/retrospectives")
@admin_required
@api_error_handler("List retrospectives")
def admin_list_retrospectives():
    """List all retrospectives."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, period, went_well, improve, action_items, sprint_id, created_at
            FROM retrospective ORDER BY created_at DESC LIMIT 50
        """).fetchall()
    return jsonify({"retrospectives": [dict(r) for r in rows]})


# ── Agile: WSJF Backlog Prioritization on work_items ───────────────────

@admin_bp.route("/api/admin/work-items/prioritized")
@admin_required
@api_error_handler("WSJF prioritized work items")
def admin_work_items_prioritized():
    """Return work items sorted by WSJF descending."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, title, description, item_type, status,
                   COALESCE(business_value, 5) as business_value,
                   COALESCE(time_criticality, 5) as time_criticality,
                   COALESCE(risk_reduction, 5) as risk_reduction,
                   COALESCE(job_size, 5) as job_size,
                   service_class, sprint_id, created_at
            FROM work_item
            WHERE status NOT IN ('done')
            ORDER BY created_at DESC
        """).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            js = item["job_size"] or 5
            if js < 1:
                js = 1
            item["wsjf"] = round(
                (item["business_value"] + item["time_criticality"] + item["risk_reduction"]) / js, 2
            )
            items.append(item)
        items.sort(key=lambda x: x["wsjf"], reverse=True)
    return jsonify({"items": items})


# ── Lean Six Sigma: Root Cause Analysis (5 Whys + Ishikawa) ────────────

@admin_bp.route("/api/admin/rca", methods=["POST"])
@admin_required
@api_error_handler("Create RCA")
def admin_create_rca():
    """Create a root cause analysis (5 Whys)."""
    data = request.get_json()
    if not data or not data.get("why_1"):
        return jsonify({"error": "why_1 is required"}), 400
    category = data.get("category")
    valid_cats = ('method', 'measurement', 'material', 'machine', 'man', 'environment')
    if category and category not in valid_cats:
        return jsonify({"error": f"category must be one of: {', '.join(valid_cats)}"}), 400
    with db.connection() as conn:
        cur = conn.execute("""
            INSERT INTO root_cause_analysis
                (work_item_id, improvement_id, why_1, why_2, why_3, why_4, why_5,
                 root_cause, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data.get("work_item_id"), data.get("improvement_id"),
              data["why_1"], data.get("why_2"), data.get("why_3"),
              data.get("why_4"), data.get("why_5"),
              data.get("root_cause"), category))
        conn.commit()
    return jsonify({"id": cur.lastrowid, "status": "created"}), 201


@admin_bp.route("/api/admin/rca")
@admin_required
@api_error_handler("List RCA")
def admin_list_rca():
    """List root cause analyses."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT rca.*, wi.title as work_item_title
            FROM root_cause_analysis rca
            LEFT JOIN work_item wi ON rca.work_item_id = wi.id
            ORDER BY rca.created_at DESC LIMIT 50
        """).fetchall()
    return jsonify({"analyses": [dict(r) for r in rows]})


@admin_bp.route("/api/admin/rca/ishikawa")
@admin_required
@api_error_handler("Ishikawa distribution")
def admin_rca_ishikawa():
    """Group root causes by Ishikawa category and return distribution."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT category, COUNT(*) as count,
                   GROUP_CONCAT(root_cause, ' | ') as root_causes
            FROM root_cause_analysis
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
        """).fetchall()
        distribution = {r["category"]: {"count": r["count"],
                                         "root_causes": (r["root_causes"] or "").split(" | ")}
                        for r in rows}
        # Ensure all 6 categories present
        for cat in ('method', 'measurement', 'material', 'machine', 'man', 'environment'):
            if cat not in distribution:
                distribution[cat] = {"count": 0, "root_causes": []}
        total = sum(d["count"] for d in distribution.values())
    return jsonify({"distribution": distribution, "total": total})


# ── Spiral: Risk Review with Burndown ───────────────────────────────────

@admin_bp.route("/api/admin/risks/<int:risk_id>/review", methods=["PUT"])
@admin_required
@api_error_handler("Review risk")
def admin_review_risk(risk_id):
    """Record a risk reassessment (stores previous and new score)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    with db.connection() as conn:
        risk = conn.execute(
            "SELECT probability, impact FROM risk_item WHERE id = ?", (risk_id,)
        ).fetchone()
        if not risk:
            return jsonify({"error": "Risk not found"}), 404
        previous_score = (risk["probability"] or 3) * (risk["impact"] or 3)
        new_prob = data.get("probability", risk["probability"])
        new_impact = data.get("impact", risk["impact"])
        new_score = new_prob * new_impact
        # Record the review
        conn.execute("""
            INSERT INTO risk_review (risk_item_id, previous_score, new_score, notes)
            VALUES (?, ?, ?, ?)
        """, (risk_id, previous_score, new_score, data.get("notes", "")))
        # Update the risk item
        conn.execute("""
            UPDATE risk_item SET probability = ?, impact = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (new_prob, new_impact, risk_id))
        conn.commit()
    return jsonify({"status": "reviewed", "previous_score": previous_score,
                     "new_score": new_score})


@admin_bp.route("/api/admin/risks/burndown")
@admin_required
@api_error_handler("Risk burndown")
def admin_risk_burndown():
    """Aggregate risk scores over time for burndown chart."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT date(reviewed_at) as review_date,
                   SUM(new_score) as total_score,
                   COUNT(*) as review_count,
                   AVG(new_score) as avg_score
            FROM risk_review
            GROUP BY date(reviewed_at)
            ORDER BY review_date ASC
        """).fetchall()
        burndown = [{"date": r["review_date"],
                      "total_score": r["total_score"],
                      "review_count": r["review_count"],
                      "avg_score": round(r["avg_score"], 2)} for r in rows]
        # Current total risk score
        current = conn.execute("""
            SELECT SUM(probability * impact) as total,
                   COUNT(*) as active_count
            FROM risk_item WHERE status = 'active'
        """).fetchone()
        current_total = (current["total"] or 0) if current else 0
        active_count = (current["active_count"] or 0) if current else 0
    return jsonify({"burndown": burndown,
                     "current_total_score": current_total,
                     "active_risk_count": active_count})


# ── Operations Research: Quality Analytics ────────────────────────────


@admin_bp.route("/api/admin/quality/sensitivity")
@admin_required
@api_error_handler("Sensitivity analysis")
def admin_quality_sensitivity():
    """Sensitivity analysis: parameter sweeps and projected impact."""
    user_id = request.args.get("user_id", 1, type=int)
    from ..quality.sensitivity import sensitivity_analysis as run_sensitivity
    with db.connection() as conn:
        if user_id != current_user.id:
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"Inspected user {user_id} data via {request.path}")
        result = run_sensitivity(conn, user_id=user_id)
    return jsonify(result)


@admin_bp.route("/api/admin/quality/queue-model")
@admin_required
@api_error_handler("Queue model")
def admin_quality_queue_model():
    """M/G/1 queue model stats for the review queue."""
    user_id = request.args.get("user_id", 1, type=int)
    from ..quality.queue_model import queue_model
    with db.connection() as conn:
        if user_id != current_user.id:
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"Inspected user {user_id} data via {request.path}")
        result = queue_model(conn, user_id=user_id)
    return jsonify(result)


@admin_bp.route("/api/admin/quality/optimization")
@admin_required
@api_error_handler("Session optimization")
def admin_quality_optimization():
    """Optimized session plan maximizing retention gain per minute."""
    user_id = request.args.get("user_id", 1, type=int)
    minutes = request.args.get("minutes", 15, type=int)
    minutes = max(1, min(60, minutes))
    from ..quality.optimization import optimize_session
    with db.connection() as conn:
        if user_id != current_user.id:
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"Inspected user {user_id} data via {request.path}")
        result = optimize_session(conn, user_id=user_id,
                                  time_budget_minutes=minutes)
    return jsonify(result)


@admin_bp.route("/api/admin/quality/decision-table")
@admin_required
@api_error_handler("Decision table")
def admin_quality_decision_table():
    """Decision table: return-probability x queue-state matrix."""
    user_id = request.args.get("user_id", 1, type=int)
    from ..quality.optimization import decision_table
    with db.connection() as conn:
        if user_id != current_user.id:
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"Inspected user {user_id} data via {request.path}")
        result = decision_table(conn, user_id=user_id)
    return jsonify(result)


@admin_bp.route("/api/admin/quality/pareto")
@admin_required
@api_error_handler("Pareto frontier")
def admin_quality_pareto():
    """Multi-objective Pareto frontier: retention vs breadth vs time."""
    user_id = request.args.get("user_id", 1, type=int)
    from ..quality.optimization import pareto_frontier
    with db.connection() as conn:
        if user_id != current_user.id:
            log_security_event(conn, SecurityEvent.ADMIN_ACCESS,
                               user_id=current_user.id,
                               details=f"Inspected user {user_id} data via {request.path}")
        result = pareto_frontier(conn, user_id=user_id)
    return jsonify(result)


@admin_bp.route("/api/admin/churn-dashboard")
@admin_required
@api_error_handler("Churn dashboard")
def admin_churn_dashboard():
    """At-risk users dashboard for churn analytics.

    Returns a JSON list of users whose churn risk score meets the
    minimum threshold (default 40).  Each entry includes risk_score,
    churn_type, user_id, and days_since_last_session.

    Query params:
        min_risk (int): minimum score to include (default 40)
    """
    min_risk = request.args.get("min_risk", 40, type=int)

    from ..churn_detection import compute_churn_risk, _days_since_last_session

    with db.connection() as conn:
        rows = conn.execute("SELECT id FROM user").fetchall()
        at_risk = []
        for row in rows:
            uid = row["id"]
            try:
                risk = compute_churn_risk(conn, user_id=uid)
            except Exception as e:
                logger.debug("churn_risk skipped for user %s: %s", uid, e)
                continue
            if risk["score"] < min_risk:
                continue
            days = _days_since_last_session(conn, user_id=uid)
            at_risk.append({
                "user_id": uid,
                "risk_score": risk["score"],
                "churn_type": risk.get("churn_type", "unknown"),
                "days_since_last_session": round(days, 1) if days is not None else None,
            })

        at_risk.sort(key=lambda u: u["risk_score"], reverse=True)

    return jsonify({"at_risk_users": at_risk, "count": len(at_risk)})


# ═══════════════════════════════════════════════════════════════════════
# Anti-Goodhart Counter-Metrics Admin Routes
# ═══════════════════════════════════════════════════════════════════════

@admin_bp.route("/api/admin/counter-metrics")
@admin_required
@api_error_handler("Counter-metrics assessment")
def admin_counter_metrics():
    """Full counter-metric assessment — all 5 layers with alerts."""
    from ..counter_metrics import compute_full_assessment

    user_id = request.args.get("user_id", 1, type=int)
    with db.connection() as conn:
        assessment = compute_full_assessment(conn, user_id=user_id)
    return jsonify(assessment)


@admin_bp.route("/api/admin/counter-metrics/snapshot-history")
@admin_required
@api_error_handler("Counter-metrics history")
def admin_counter_metrics_history():
    """Counter-metric snapshot history for trend charts."""
    from ..counter_metrics import get_snapshot_history

    user_id = request.args.get("user_id", 1, type=int)
    limit = request.args.get("limit", 30, type=int)
    with db.connection() as conn:
        history = get_snapshot_history(conn, user_id=user_id, limit=limit)
    return jsonify({"snapshots": history, "count": len(history)})


@admin_bp.route("/api/admin/counter-metrics/run", methods=["POST"])
@admin_required
@api_error_handler("Counter-metrics manual run")
def admin_counter_metrics_run():
    """Manually trigger a counter-metrics assessment + actioning cycle."""
    from .counter_metrics_scheduler import run_once

    with db.connection() as conn:
        result = run_once(conn)
    return jsonify(result)


@admin_bp.route("/api/admin/counter-metrics/actions")
@admin_required
@api_error_handler("Counter-metrics action log")
def admin_counter_metrics_actions():
    """Action log — what the system has done in response to alerts."""
    from ..counter_metrics_actions import get_action_history

    limit = request.args.get("limit", 50, type=int)
    with db.connection() as conn:
        actions = get_action_history(conn, limit=limit)
    return jsonify({"actions": actions, "count": len(actions)})


@admin_bp.route("/api/admin/counter-metrics/product-rules")
@admin_required
@api_error_handler("Counter-metrics product rules")
def admin_counter_metrics_rules():
    """Check product rule compliance against latest assessment."""
    from ..counter_metrics import compute_full_assessment
    from ..counter_metrics_actions import enforce_product_rules

    user_id = request.args.get("user_id", 1, type=int)
    with db.connection() as conn:
        assessment = compute_full_assessment(conn, user_id=user_id)
    violations = enforce_product_rules(assessment)
    return jsonify({
        "violations": violations,
        "violation_count": len(violations),
        "overall_health": assessment.get("overall_health"),
    })


@admin_bp.route("/api/admin/counter-metrics/holdout")
@admin_required
@api_error_handler("Counter-metrics holdout probes")
def admin_counter_metrics_holdout():
    """Holdout probe performance summary."""
    from ..holdout_probes import get_holdout_summary

    user_id = request.args.get("user_id", 1, type=int)
    window_days = request.args.get("window_days", 30, type=int)
    with db.connection() as conn:
        summary = get_holdout_summary(conn, user_id=user_id, window_days=window_days)
    return jsonify(summary)


@admin_bp.route("/api/admin/counter-metrics/map")
@admin_required
@api_error_handler("Counter-metrics mapping")
def admin_counter_metrics_map():
    """Return the KPI → counter-metric mapping table."""
    from ..counter_metrics import COUNTER_METRIC_MAP, ALERT_THRESHOLDS
    return jsonify({
        "map": COUNTER_METRIC_MAP,
        "thresholds": ALERT_THRESHOLDS,
    })
