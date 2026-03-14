"""Admin routes for vibe audit, marketing intelligence, feature usage, engineering health (Doc 9)."""

import json
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import login_required

from .. import db
from .admin_routes import admin_required
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

vibe_admin_bp = Blueprint("vibe_admin", __name__)


# ── Vibe / Voice ───────────────────────────────────────────────────────────

@vibe_admin_bp.route("/api/admin/intelligence/vibe/tonal")
@admin_required
@api_error_handler("Tonal vibe")
def tonal_vibe():
    """Voice audit results + flagged strings."""
    with db.connection() as conn:
        # Low-scoring strings
        flagged = conn.execute("""
            SELECT id, string_key, copy_text, copy_context, surface, voice_score,
                   clarity_score, last_audited_at
            FROM pi_copy_registry
            WHERE voice_score IS NOT NULL AND voice_score < 70
            ORDER BY voice_score ASC
        """).fetchall()

        # Unaudited strings
        unaudited = conn.execute("""
            SELECT id, string_key, copy_text, surface
            FROM pi_copy_registry WHERE last_audited_at IS NULL
        """).fetchall()

        # Recent audits
        audits = conn.execute("""
            SELECT * FROM pi_vibe_audits
            WHERE audit_type IN ('full', 'tonal')
            ORDER BY audit_date DESC LIMIT 10
        """).fetchall()

        return jsonify({
            "flagged_strings": [dict(r) for r in flagged],
            "unaudited_count": len(unaudited),
            "unaudited_strings": [dict(r) for r in unaudited[:20]],
            "recent_audits": [dict(r) for r in audits],
        })


@vibe_admin_bp.route("/api/admin/intelligence/vibe/visual")
@admin_required
@api_error_handler("Visual vibe")
def visual_vibe():
    """Visual audit schedule status."""
    from ..intelligence.vibe_marketing_eng import VISUAL_VIBE_CHECKLIST
    with db.connection() as conn:
        schedule = []
        for category, spec in VISUAL_VIBE_CHECKLIST.items():
            row = conn.execute("""
                SELECT MAX(audit_date) as last_date, overall_pass
                FROM pi_vibe_audits
                WHERE audit_category = ? AND audit_type = 'visual'
            """, (category,)).fetchone()

            last_date = row["last_date"] if row else None
            days_since = None
            if last_date:
                ds = conn.execute(
                    "SELECT julianday('now') - julianday(?)", (last_date,)
                ).fetchone()
                days_since = int(ds[0]) if ds and ds[0] else None

            schedule.append({
                "category": category,
                "description": spec["description"],
                "frequency_days": spec["audit_frequency_days"],
                "last_audit": last_date,
                "days_since": days_since,
                "overdue": days_since is None or (days_since > spec["audit_frequency_days"]),
                "last_pass": bool(row["overall_pass"]) if row and row["overall_pass"] is not None else None,
            })

        return jsonify({"schedule": schedule})


@vibe_admin_bp.route("/api/admin/intelligence/vibe/audit", methods=["POST"])
@admin_required
@api_error_handler("Log vibe audit")
def log_vibe_audit():
    """Log a completed vibe audit."""
    data = request.get_json(force=True)
    audit_type = data.get("audit_type", "visual")
    audit_category = data.get("audit_category", "")
    overall_pass = data.get("overall_pass", True)
    findings_text = data.get("findings_text", "")
    notes = data.get("notes", "")

    if not audit_category:
        return jsonify({"error": "audit_category required"}), 400

    with db.connection() as conn:
        audit_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO pi_vibe_audits
            (id, audit_date, audit_type, audit_category, overall_pass, findings_text, auditor, notes)
            VALUES (?, datetime('now'), ?, ?, ?, ?, 'admin', ?)
        """, (audit_id, audit_type, audit_category, int(overall_pass), findings_text, notes))
        conn.commit()
        return jsonify({"id": audit_id, "status": "logged"})


# ── Marketing ──────────────────────────────────────────────────────────────

@vibe_admin_bp.route("/api/admin/marketing/pages")
@admin_required
@api_error_handler("Marketing pages")
def marketing_pages():
    """Marketing page registry."""
    with db.connection() as conn:
        pages = conn.execute("""
            SELECT * FROM pi_marketing_pages ORDER BY page_slug
        """).fetchall()
        return jsonify({"pages": [dict(r) for r in pages]})


@vibe_admin_bp.route("/api/admin/marketing/pages/<page_id>/analytics", methods=["POST"])
@admin_required
@api_error_handler("Update page analytics")
def update_page_analytics(page_id):
    """Update conversion/visitor data for a marketing page."""
    data = request.get_json(force=True)
    with db.connection() as conn:
        conn.execute("""
            UPDATE pi_marketing_pages
            SET conversion_rate = COALESCE(?, conversion_rate),
                monthly_visitors = COALESCE(?, monthly_visitors),
                last_analytics_update = datetime('now')
            WHERE id = ?
        """, (data.get("conversion_rate"), data.get("monthly_visitors"), page_id))
        conn.commit()
        return jsonify({"status": "updated"})


@vibe_admin_bp.route("/api/admin/marketing/funnel")
@admin_required
@api_error_handler("Funnel metrics")
def funnel_metrics():
    """Funnel metrics — latest snapshot + event counts."""
    with db.connection() as conn:
        snapshot = conn.execute("""
            SELECT * FROM pi_funnel_snapshots ORDER BY snapshot_date DESC LIMIT 1
        """).fetchone()

        event_counts = conn.execute("""
            SELECT event_type, COUNT(*) as cnt
            FROM pi_funnel_events
            WHERE occurred_at >= datetime('now', '-30 days')
            GROUP BY event_type
        """).fetchall()

        return jsonify({
            "latest_snapshot": dict(snapshot) if snapshot else None,
            "event_counts_30d": {r["event_type"]: r["cnt"] for r in event_counts},
        })


@vibe_admin_bp.route("/api/admin/marketing/strategy")
@admin_required
@api_error_handler("Strategy checklist")
def strategy_checklist():
    """Strategy checklist status."""
    from ..intelligence.vibe_marketing_eng import MARKETING_STRATEGY_CHECKLIST
    with db.connection() as conn:
        items = []
        for name, spec in MARKETING_STRATEGY_CHECKLIST.items():
            row = conn.execute("""
                SELECT MAX(audit_date) as last_date FROM pi_vibe_audits
                WHERE audit_type = 'strategy' AND audit_category = ?
            """, (name,)).fetchone()
            last_date = row["last_date"] if row else None
            days_since = None
            if last_date:
                ds = conn.execute(
                    "SELECT julianday('now') - julianday(?)", (last_date,)
                ).fetchone()
                days_since = int(ds[0]) if ds and ds[0] else None
            items.append({
                "name": name,
                "description": spec["description"],
                "frequency_days": spec["review_frequency_days"],
                "last_review": last_date,
                "days_since": days_since,
                "overdue": days_since is None or days_since > spec["review_frequency_days"],
            })
        return jsonify({"checklist": items})


@vibe_admin_bp.route("/api/admin/marketing/strategy/<check_name>/review", methods=["POST"])
@admin_required
@api_error_handler("Log strategy review")
def log_strategy_review(check_name):
    """Log a strategy checklist review."""
    data = request.get_json(force=True) if request.data else {}
    with db.connection() as conn:
        audit_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO pi_vibe_audits
            (id, audit_date, audit_type, audit_category, overall_pass, findings_text, auditor, notes)
            VALUES (?, datetime('now'), 'strategy', ?, 1, ?, 'admin', ?)
        """, (audit_id, check_name, data.get("findings", ""), data.get("notes", "")))
        conn.commit()
        return jsonify({"id": audit_id, "status": "logged"})


# ── Feature Usage ──────────────────────────────────────────────────────────

@vibe_admin_bp.route("/api/admin/features/usage")
@admin_required
@api_error_handler("Feature usage")
def feature_usage():
    """Feature usage rates."""
    with db.connection() as conn:
        features = conn.execute("""
            SELECT * FROM pi_feature_registry ORDER BY current_usage_rate_30d ASC
        """).fetchall()

        return jsonify({"features": [dict(r) for r in features]})


@vibe_admin_bp.route("/api/admin/features/<feature_name>/event", methods=["POST"])
@admin_required
@api_error_handler("Log feature event")
def log_feature_event(feature_name):
    """Log a feature event (start, complete, etc.)."""
    data = request.get_json(force=True)
    user_id = data.get("user_id", "admin")
    event_type = data.get("event_type", "use")

    with db.connection() as conn:
        event_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO pi_feature_events
            (id, user_id, feature_name, event_type, session_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event_id, user_id, feature_name, event_type,
              data.get("session_id"), json.dumps(data.get("metadata")) if data.get("metadata") else None))
        conn.commit()
        return jsonify({"id": event_id, "status": "logged"})


# ── Engineering Health ─────────────────────────────────────────────────────

@vibe_admin_bp.route("/api/admin/engineering/health")
@admin_required
@api_error_handler("Engineering health")
def engineering_health():
    """Engineering health summary — latest snapshot."""
    with db.connection() as conn:
        snapshot = conn.execute("""
            SELECT * FROM pi_engineering_snapshots ORDER BY snapshot_date DESC LIMIT 1
        """).fetchone()

        # Historical trend
        history = conn.execute("""
            SELECT snapshot_date, test_coverage_pct, tests_passing, tests_failing,
                   table_count, db_size_mb, outdated_dependencies
            FROM pi_engineering_snapshots ORDER BY snapshot_date DESC LIMIT 10
        """).fetchall()

        return jsonify({
            "latest": dict(snapshot) if snapshot else None,
            "history": [dict(r) for r in history],
        })


@vibe_admin_bp.route("/api/admin/engineering/health/snapshot", methods=["POST"])
@admin_required
@api_error_handler("Engineering snapshot")
def trigger_engineering_snapshot():
    """Trigger a fresh engineering health snapshot."""
    with db.connection() as conn:
        from ..intelligence.vibe_marketing_eng import analyze_test_coverage, analyze_dependency_health
        findings = []
        findings.extend(analyze_test_coverage(conn))
        findings.extend(analyze_dependency_health(conn))

        snapshot = conn.execute("""
            SELECT * FROM pi_engineering_snapshots ORDER BY snapshot_date DESC LIMIT 1
        """).fetchone()

        return jsonify({
            "snapshot": dict(snapshot) if snapshot else None,
            "findings_count": len(findings),
        })
