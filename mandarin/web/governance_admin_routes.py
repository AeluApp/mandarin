"""Admin routes for AI governance & compliance (Doc 11)."""

import json
import logging
import uuid

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db
from .admin_routes import admin_required
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

governance_admin_bp = Blueprint("governance_admin", __name__)


# ── Component Registry ─────────────────────────────────────────────────────

@governance_admin_bp.route("/api/admin/governance/registry")
@admin_required
@api_error_handler("AI component registry")
def governance_registry():
    """Full component registry with risk tiers and validation status."""
    with db.connection() as conn:
        components = conn.execute("""
            SELECT * FROM ai_component_registry ORDER BY risk_tier, component_name
        """).fetchall()
        return jsonify({"components": [dict(c) for c in components]})


@governance_admin_bp.route("/api/admin/governance/registry/<component>")
@admin_required
@api_error_handler("Component detail")
def governance_component_detail(component):
    """Detail view for one component including validation history."""
    with db.connection() as conn:
        comp = conn.execute(
            "SELECT * FROM ai_component_registry WHERE component_name = ?", (component,)
        ).fetchone()
        if not comp:
            return jsonify({"error": f"Component '{component}' not found"}), 404

        validations = conn.execute("""
            SELECT * FROM ai_validation_log
            WHERE component_name = ? ORDER BY validated_at DESC LIMIT 10
        """, (component,)).fetchall()

        return jsonify({
            "component": dict(comp),
            "validation_history": [dict(v) for v in validations],
        })


@governance_admin_bp.route("/api/admin/governance/registry/<component>/validate", methods=["POST"])
@admin_required
@api_error_handler("Log validation")
def governance_validate_component(component):
    """Log completed validation."""
    data = request.get_json()
    verdict = data.get("verdict", "validated")
    notes = data.get("notes", "")

    valid_verdicts = ('validated', 'needs_review', 'validation_failed')
    if verdict not in valid_verdicts:
        return jsonify({"error": f"Invalid verdict: {verdict}"}), 400

    with db.connection() as conn:
        vid = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO ai_validation_log
            (id, component_name, verdict, notes)
            VALUES (?, ?, ?, ?)
        """, (vid, component, verdict, notes))
        conn.execute("""
            UPDATE ai_component_registry
            SET last_validated_at = date('now')
            WHERE component_name = ?
        """, (component,))
        conn.commit()
        return jsonify({"id": vid, "status": "logged"})


# ── Incidents ──────────────────────────────────────────────────────────────

@governance_admin_bp.route("/api/admin/governance/incidents")
@admin_required
@api_error_handler("Incident log")
def governance_incidents():
    """Incident log, most recent first."""
    with db.connection() as conn:
        incidents = conn.execute("""
            SELECT * FROM ai_incident_log ORDER BY detected_at DESC LIMIT 50
        """).fetchall()
        return jsonify({"incidents": [dict(i) for i in incidents]})


@governance_admin_bp.route("/api/admin/governance/incidents", methods=["POST"])
@admin_required
@api_error_handler("Log incident")
def governance_log_incident():
    """Log a new incident."""
    data = request.get_json()
    severity = data.get("severity", "P2")
    incident_type = data.get("incident_type", "other")
    description = data.get("description", "")

    valid_types = ('content_bypass', 'data_breach', 'model_failure',
                   'data_quality', 'access_violation', 'other')
    if incident_type not in valid_types:
        return jsonify({"error": f"Invalid incident_type: {incident_type}"}), 400

    with db.connection() as conn:
        iid = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO ai_incident_log
            (id, severity, incident_type, affected_component, description,
             immediate_actions_taken)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (iid, severity, incident_type, data.get("affected_component"),
              description, data.get("immediate_actions", "")))
        conn.commit()
        return jsonify({"id": iid, "status": "logged"})


@governance_admin_bp.route("/api/admin/governance/incidents/<incident_id>/resolve", methods=["POST"])
@admin_required
@api_error_handler("Resolve incident")
def governance_resolve_incident(incident_id):
    """Resolve an incident."""
    data = request.get_json()
    with db.connection() as conn:
        conn.execute("""
            UPDATE ai_incident_log
            SET resolution = ?, root_cause = ?,
                resolved_at = datetime('now'),
                post_incident_review_notes = ?
            WHERE id = ?
        """, (data.get("resolution", ""), data.get("root_cause", ""),
              data.get("recurrence_prevention", ""), incident_id))
        conn.commit()
        return jsonify({"status": "resolved"})


# ── Policies ───────────────────────────────────────────────────────────────

@governance_admin_bp.route("/api/admin/governance/policies")
@admin_required
@api_error_handler("Policy documents")
def governance_policies():
    """Policy documents with review status."""
    with db.connection() as conn:
        policies = conn.execute("""
            SELECT * FROM ai_policy_documents ORDER BY status, document_key
        """).fetchall()
        return jsonify({"policies": [dict(p) for p in policies]})


@governance_admin_bp.route("/api/admin/governance/policies/<key>/review", methods=["POST"])
@admin_required
@api_error_handler("Review policy")
def governance_review_policy(key):
    """Log policy review, update next_review_due."""
    request.get_json() if request.data else {}
    with db.connection() as conn:
        conn.execute("""
            UPDATE ai_policy_documents
            SET last_reviewed_at = date('now'),
                next_review_due = date('now', '+180 days'),
                version = version + 1
            WHERE document_key = ?
        """, (key,))
        conn.commit()
        return jsonify({"status": "reviewed"})


# ── Data Subject Requests ──────────────────────────────────────────────────

@governance_admin_bp.route("/api/admin/governance/data-requests")
@admin_required
@api_error_handler("Data requests")
def governance_data_requests():
    """All data subject requests sorted by urgency."""
    with db.connection() as conn:
        requests_list = conn.execute("""
            SELECT * FROM data_subject_requests
            ORDER BY
                CASE WHEN status = 'pending' THEN 0
                     WHEN status = 'in_progress' THEN 1
                     ELSE 2 END,
                response_due_date ASC
        """).fetchall()
        return jsonify({"requests": [dict(r) for r in requests_list]})


@governance_admin_bp.route("/api/admin/governance/data-requests", methods=["POST"])
@admin_required
@api_error_handler("Create data request")
def governance_create_data_request():
    """Create a data subject request."""
    data = request.get_json()
    user_id = data.get("user_id")
    request_type = data.get("request_type")

    valid_types = ('access', 'deletion', 'correction', 'portability', 'restriction')
    if request_type not in valid_types:
        return jsonify({"error": f"Invalid request_type: {request_type}"}), 400

    with db.connection() as conn:
        rid = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO data_subject_requests (id, user_id, request_type)
            VALUES (?, ?, ?)
        """, (rid, user_id, request_type))
        conn.commit()
        return jsonify({"id": rid, "status": "created"})


@governance_admin_bp.route("/api/admin/governance/data-requests/<request_id>/process", methods=["POST"])
@admin_required
@api_error_handler("Process data request")
def governance_process_data_request(request_id):
    """Process a data subject request."""
    from ..intelligence.governance import handle_deletion_request, handle_access_request

    with db.connection() as conn:
        req = conn.execute(
            "SELECT * FROM data_subject_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not req:
            return jsonify({"error": "Request not found"}), 404

        conn.execute("""
            UPDATE data_subject_requests SET status = 'in_progress' WHERE id = ?
        """, (request_id,))

        result = {}
        if req['request_type'] == 'deletion':
            result = handle_deletion_request(conn, req['user_id'])
        elif req['request_type'] == 'access':
            result = handle_access_request(conn, req['user_id'])

        conn.execute("""
            UPDATE data_subject_requests
            SET status = 'completed', completed_at = datetime('now')
            WHERE id = ?
        """, (request_id,))
        conn.commit()

        return jsonify({"status": "processed", "result": result})


# ── Learner Endpoints ──────────────────────────────────────────────────────

@governance_admin_bp.route("/api/learner/ai-transparency")
@login_required
def learner_transparency():
    """Learner-facing transparency report."""
    from ..intelligence.governance import get_transparency_report
    with db.connection() as conn:
        report = get_transparency_report(conn, current_user.id)
        return jsonify(report)


@governance_admin_bp.route("/api/learner/items/<item_id>/explain")
@login_required
def learner_explain_item(item_id):
    """Why am I seeing this item."""
    from ..intelligence.governance import explain_item_scheduling
    with db.connection() as conn:
        explanation = explain_item_scheduling(conn, item_id, current_user.id)
        return jsonify(explanation)
