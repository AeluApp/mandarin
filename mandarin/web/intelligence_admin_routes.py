"""Admin routes for the Intelligence approval dashboard.

Provides a server-rendered approval dashboard for product intelligence
findings, plus JSON endpoints for approve/reject/defer actions.
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime

from flask import Blueprint, jsonify, render_template, request, abort

from .. import db
from .admin_routes import admin_required
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

intelligence_admin_bp = Blueprint("intelligence_admin", __name__)


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------

@intelligence_admin_bp.route("/admin/intelligence")
@admin_required
def intelligence_dashboard():
    """Server-rendered intelligence approval dashboard."""
    with db.connection() as conn:
        # Summary stats
        total_findings = _scalar(conn, "SELECT COUNT(*) FROM pi_finding") or 0

        auto_fixed_7d = _scalar(conn, """
            SELECT COUNT(*) FROM pi_finding
            WHERE status = 'resolved'
              AND resolved_at >= datetime('now', '-7 days')
        """) or 0

        pending_approval = _scalar(conn, """
            SELECT COUNT(DISTINCT pf.id)
            FROM pi_finding pf
            JOIN pi_decision_log dl ON dl.finding_id = pf.id
            WHERE pf.status IN ('investigating', 'diagnosed', 'recommended')
              AND dl.decision_class IN ('informed_fix', 'judgment_call', 'values_decision')
              AND dl.approved_at IS NULL
              AND (dl.decision IS NULL OR dl.decision = '')
        """) or 0

        # Findings needing approval, grouped by decision_class
        approval_rows = conn.execute("""
            SELECT pf.id, pf.dimension, pf.severity, pf.title, pf.analysis,
                   pf.status, pf.times_seen, pf.created_at, pf.updated_at,
                   dl.decision_class, dl.escalation_level
            FROM pi_finding pf
            JOIN pi_decision_log dl ON dl.finding_id = pf.id
            WHERE pf.status IN ('investigating', 'diagnosed', 'recommended')
              AND dl.decision_class IN ('informed_fix', 'judgment_call', 'values_decision')
              AND dl.approved_at IS NULL
              AND (dl.decision IS NULL OR dl.decision = '')
            ORDER BY
                CASE dl.decision_class
                    WHEN 'values_decision' THEN 0
                    WHEN 'judgment_call' THEN 1
                    WHEN 'informed_fix' THEN 2
                    ELSE 3
                END,
                CASE pf.severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END
        """).fetchall()

        # Group by decision_class
        grouped = {}
        for row in approval_rows:
            dc = row["decision_class"]
            if dc not in grouped:
                grouped[dc] = []
            grouped[dc].append(dict(row))

        # Recently auto-fixed (last 7 days)
        recent_auto_fixed = conn.execute("""
            SELECT id, dimension, severity, title, resolved_at, resolution_notes
            FROM pi_finding
            WHERE status = 'resolved'
              AND resolved_at >= datetime('now', '-7 days')
            ORDER BY resolved_at DESC
            LIMIT 50
        """).fetchall()

        return render_template(
            "admin/intelligence.html",
            total_findings=total_findings,
            auto_fixed_7d=auto_fixed_7d,
            pending_approval=pending_approval,
            grouped_approval=grouped,
            recent_auto_fixed=[dict(r) for r in recent_auto_fixed],
            decision_class_labels={
                "values_decision": "Values Decision",
                "judgment_call": "Judgment Call",
                "informed_fix": "Informed Fix",
            },
        )


# ---------------------------------------------------------------------------
# Approve / Reject / Defer actions
# ---------------------------------------------------------------------------

@intelligence_admin_bp.route("/admin/intelligence/<int:finding_id>/approve", methods=["POST"])
@admin_required
@api_error_handler("Approve finding")
def approve_finding(finding_id):
    """Approve a finding's recommendation.

    Transitions the finding forward (to 'recommended' if investigating/diagnosed,
    or marks the decision_log as approved).
    """
    with db.connection() as conn:
        finding = conn.execute(
            "SELECT id, status, title FROM pi_finding WHERE id = ?",
            (finding_id,),
        ).fetchone()
        if not finding:
            abort(404)

        notes = (request.json or {}).get("notes", "") if request.is_json else ""

        current_status = finding["status"]

        # Advance the finding state
        _ADVANCE_MAP = {
            "investigating": "diagnosed",
            "diagnosed": "recommended",
            "recommended": "implemented",
        }
        next_status = _ADVANCE_MAP.get(current_status)

        if next_status:
            # For transition to 'implemented', we need a prediction record.
            # If one doesn't exist, advance to 'recommended' instead.
            if next_status == "implemented":
                has_pred = _scalar(conn, """
                    SELECT COUNT(*) FROM pi_prediction_ledger WHERE finding_id = ?
                """, (finding_id,))
                if not has_pred:
                    next_status = "recommended"

            try:
                from ..intelligence.finding_lifecycle import transition_finding
                transition_finding(conn, finding_id, next_status, notes=notes)
            except Exception:
                # Direct update as fallback
                conn.execute("""
                    UPDATE pi_finding
                    SET status = ?, updated_at = datetime('now'),
                        resolution_notes = CASE WHEN ? != '' THEN ? ELSE resolution_notes END
                    WHERE id = ?
                """, (next_status, notes, notes, finding_id))

        # Mark decision_log as approved
        conn.execute("""
            UPDATE pi_decision_log
            SET approved_at = datetime('now'),
                decision = 'approved',
                decision_reason = ?
            WHERE finding_id = ? AND approved_at IS NULL
        """, (notes or "Approved via dashboard", finding_id))
        conn.commit()

        return jsonify({
            "status": "approved",
            "finding_id": finding_id,
            "new_status": next_status or current_status,
        })


@intelligence_admin_bp.route("/admin/intelligence/<int:finding_id>/reject", methods=["POST"])
@admin_required
@api_error_handler("Reject finding")
def reject_finding(finding_id):
    """Reject/dismiss a finding. Transitions to 'resolved' with resolution='rejected'."""
    with db.connection() as conn:
        finding = conn.execute(
            "SELECT id, status, title FROM pi_finding WHERE id = ?",
            (finding_id,),
        ).fetchone()
        if not finding:
            abort(404)

        notes = (request.json or {}).get("notes", "") if request.is_json else ""

        # Transition directly to rejected
        conn.execute("""
            UPDATE pi_finding
            SET status = 'rejected',
                updated_at = datetime('now'),
                resolved_at = datetime('now'),
                resolution_notes = ?
            WHERE id = ?
        """, (notes or "Rejected via dashboard", finding_id))

        # Mark decision_log
        conn.execute("""
            UPDATE pi_decision_log
            SET approved_at = datetime('now'),
                decision = 'rejected',
                decision_reason = ?
            WHERE finding_id = ? AND approved_at IS NULL
        """, (notes or "Rejected via dashboard", finding_id))
        conn.commit()

        return jsonify({
            "status": "rejected",
            "finding_id": finding_id,
        })


@intelligence_admin_bp.route("/admin/intelligence/<int:finding_id>/defer", methods=["POST"])
@admin_required
@api_error_handler("Defer finding")
def defer_finding(finding_id):
    """Defer a finding for later review. Keeps current state, adds a note."""
    with db.connection() as conn:
        finding = conn.execute(
            "SELECT id, status, title FROM pi_finding WHERE id = ?",
            (finding_id,),
        ).fetchone()
        if not finding:
            abort(404)

        notes = (request.json or {}).get("notes", "") if request.is_json else ""

        # Add deferral note without changing state
        conn.execute("""
            UPDATE pi_finding
            SET updated_at = datetime('now'),
                resolution_notes = COALESCE(resolution_notes, '') || ?
            WHERE id = ?
        """, (f"\n[Deferred {datetime.now(UTC).strftime('%Y-%m-%d')}] {notes}", finding_id))

        # Log the deferral
        conn.execute("""
            UPDATE pi_decision_log
            SET decision = 'deferred',
                decision_reason = ?
            WHERE finding_id = ? AND approved_at IS NULL
        """, (notes or "Deferred via dashboard", finding_id))
        conn.commit()

        return jsonify({
            "status": "deferred",
            "finding_id": finding_id,
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalar(conn, sql, params=None):
    """Execute a scalar query, return the first column of the first row."""
    try:
        row = conn.execute(sql, params or ()).fetchone()
        return row[0] if row else None
    except (sqlite3.OperationalError, sqlite3.Error):
        return None
