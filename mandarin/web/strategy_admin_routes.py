"""Admin routes for strategic intelligence — thesis, readiness, competitive, editorial (Doc 10)."""

import json
import logging
import uuid

from flask import Blueprint, jsonify, request
from flask_login import login_required

from .. import db
from .admin_routes import admin_required
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

strategy_admin_bp = Blueprint("strategy_admin", __name__)


# ── Thesis ─────────────────────────────────────────────────────────────────

@strategy_admin_bp.route("/api/admin/strategy/thesis")
@admin_required
@api_error_handler("Strategy thesis")
def strategy_thesis():
    """Current active thesis with all components."""
    with db.connection() as conn:
        thesis = conn.execute("""
            SELECT * FROM pi_strategic_theses
            WHERE status = 'active' ORDER BY version DESC LIMIT 1
        """).fetchone()

        if not thesis:
            return jsonify({"thesis": None, "message": "No active thesis. Run audit to derive one."})

        t = dict(thesis)
        # Parse JSON fields for client
        for field in ('key_assumptions', 'disconfirming_conditions',
                      'confirming_conditions', 'monetization_blockers'):
            try:
                t[field] = json.loads(t[field] or '[]')
            except (json.JSONDecodeError, TypeError):
                t[field] = []

        # Get hypotheses
        hypotheses = conn.execute("""
            SELECT * FROM pi_strategic_hypotheses WHERE thesis_id = ?
            ORDER BY created_at DESC
        """, (thesis['id'],)).fetchall()

        return jsonify({
            "thesis": t,
            "hypotheses": [dict(h) for h in hypotheses],
        })


@strategy_admin_bp.route("/api/admin/strategy/thesis/override", methods=["POST"])
@admin_required
@api_error_handler("Override thesis")
def override_thesis():
    """Override a thesis component."""
    data = request.get_json(force=True)
    field = data.get("field")
    value = data.get("value")
    rationale = data.get("rationale", "")

    allowed_fields = {
        'target_user', 'value_proposition', 'revenue_model',
        'price_point_rationale', 'primary_moat', 'notes',
    }
    if field not in allowed_fields:
        return jsonify({"error": f"Cannot override field '{field}'"}), 400

    with db.connection() as conn:
        thesis = conn.execute("""
            SELECT id FROM pi_strategic_theses
            WHERE status = 'active' ORDER BY version DESC LIMIT 1
        """).fetchone()
        if not thesis:
            return jsonify({"error": "No active thesis"}), 404

        # Validate revenue_model if overriding
        if field == 'revenue_model':
            valid_models = ('b2c_subscription', 'b2b2c_teachers', 'enterprise',
                            'hybrid_b2c_b2b2c', 'undetermined')
            if value not in valid_models:
                return jsonify({"error": f"Invalid revenue model: {value}"}), 400

        conn.execute(
            f"UPDATE pi_strategic_theses SET {field} = ?, notes = COALESCE(notes, '') || ? WHERE id = ?",
            (value, f'\n[Override {field}] {rationale}', thesis['id']),
        )
        conn.commit()
        return jsonify({"status": "overridden", "field": field})


# ── Commercial Readiness ───────────────────────────────────────────────────

@strategy_admin_bp.route("/api/admin/strategy/readiness")
@admin_required
@api_error_handler("Commercial readiness")
def commercial_readiness():
    """Full commercial readiness gap analysis."""
    with db.connection() as conn:
        thesis = conn.execute("""
            SELECT id, revenue_model FROM pi_strategic_theses
            WHERE status = 'active' ORDER BY version DESC LIMIT 1
        """).fetchone()
        if not thesis:
            return jsonify({"conditions": [], "thesis": None})

        conditions = conn.execute("""
            SELECT * FROM pi_commercial_readiness
            WHERE thesis_id = ? ORDER BY priority, condition_type
        """, (thesis['id'],)).fetchall()

        met = sum(1 for c in conditions if c['current_status'] == 'met')

        return jsonify({
            "thesis_id": thesis['id'],
            "revenue_model": thesis['revenue_model'],
            "conditions": [dict(c) for c in conditions],
            "total": len(conditions),
            "met": met,
            "readiness_pct": round(met / len(conditions) * 100, 1) if conditions else 0,
        })


@strategy_admin_bp.route("/api/admin/strategy/readiness/<condition_name>", methods=["POST"])
@admin_required
@api_error_handler("Update readiness condition")
def update_readiness_condition(condition_name):
    """Update a commercial readiness condition status."""
    data = request.get_json(force=True)
    status = data.get("status")
    evidence = data.get("evidence", "")

    valid_statuses = ('met', 'partial', 'not_met', 'not_assessed')
    if status not in valid_statuses:
        return jsonify({"error": f"Invalid status: {status}"}), 400

    with db.connection() as conn:
        thesis = conn.execute("""
            SELECT id FROM pi_strategic_theses
            WHERE status = 'active' ORDER BY version DESC LIMIT 1
        """).fetchone()
        if not thesis:
            return jsonify({"error": "No active thesis"}), 404

        conn.execute("""
            UPDATE pi_commercial_readiness
            SET current_status = ?, evidence = ?, last_assessed_at = datetime('now')
            WHERE thesis_id = ? AND condition_name = ?
        """, (status, evidence, thesis['id'], condition_name))
        conn.commit()
        return jsonify({"status": "updated", "condition": condition_name})


# ── Competitive ────────────────────────────────────────────────────────────

@strategy_admin_bp.route("/api/admin/strategy/competitive")
@admin_required
@api_error_handler("Competitive scorecard")
def competitive_scorecard():
    """Full competitive scorecard."""
    with db.connection() as conn:
        dimensions = conn.execute("""
            SELECT * FROM pi_evaluation_dimensions ORDER BY weight DESC
        """).fetchall()

        competitors = conn.execute("""
            SELECT * FROM pi_competitors ORDER BY aelu_overlap_degree, name
        """).fetchall()

        # Recent signals
        signals = conn.execute("""
            SELECT * FROM pi_competitive_signals
            ORDER BY detected_at DESC LIMIT 20
        """).fetchall()

        return jsonify({
            "dimensions": [dict(d) for d in dimensions],
            "competitors": [dict(c) for c in competitors],
            "signals": [dict(s) for s in signals],
        })


@strategy_admin_bp.route("/api/admin/strategy/competitive/<competitor_name>/score", methods=["POST"])
@admin_required
@api_error_handler("Update competitor score")
def update_competitor_score(competitor_name):
    """Update a competitor dimension score."""
    data = request.get_json(force=True)
    dimension = data.get("dimension")
    score = data.get("score")
    evidence = data.get("evidence", "")

    if not dimension or score is None:
        return jsonify({"error": "dimension and score required"}), 400

    with db.connection() as conn:
        competitor = conn.execute(
            "SELECT id FROM pi_competitors WHERE name = ?", (competitor_name,)
        ).fetchone()
        if not competitor:
            return jsonify({"error": f"Competitor '{competitor_name}' not found"}), 404

        conn.execute("""
            INSERT INTO pi_competitor_dimensions (id, competitor_id, dimension, score, evidence, assessed_at)
            VALUES (?, ?, ?, ?, ?, date('now'))
            ON CONFLICT(competitor_id, dimension) DO UPDATE SET
                score = excluded.score, evidence = excluded.evidence, assessed_at = excluded.assessed_at
        """, (str(uuid.uuid4()), competitor['id'], dimension, score, evidence))
        conn.commit()
        return jsonify({"status": "updated"})


@strategy_admin_bp.route("/api/admin/strategy/competitive/signal", methods=["POST"])
@admin_required
@api_error_handler("Log competitive signal")
def log_competitive_signal():
    """Log a competitive signal."""
    data = request.get_json(force=True)
    competitor_id = data.get("competitor_id")
    signal_type = data.get("signal_type")
    description = data.get("description", "")
    requires_response = data.get("requires_response", False)

    valid_types = ('new_feature', 'pricing_change', 'new_market_entry', 'partnership',
                   'funding', 'user_review_pattern', 'content_expansion', 'strategic_pivot')
    if signal_type not in valid_types:
        return jsonify({"error": f"Invalid signal_type: {signal_type}"}), 400

    with db.connection() as conn:
        signal_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO pi_competitive_signals
            (id, competitor_id, signal_type, signal_description,
             strategic_implication, requires_aelu_response)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (signal_id, competitor_id, signal_type, description,
              data.get("strategic_implication", ""), int(requires_response)))
        conn.commit()
        return jsonify({"id": signal_id, "status": "logged"})


@strategy_admin_bp.route("/api/admin/strategy/competitive/refresh", methods=["POST"])
@admin_required
@api_error_handler("Refresh competitive data")
def refresh_competitive_data():
    """Update last_assessed_at for all competitors (quarterly refresh trigger)."""
    with db.connection() as conn:
        conn.execute("UPDATE pi_competitors SET last_assessed_at = date('now')")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM pi_competitors").fetchone()[0]
        return jsonify({"status": "refreshed", "competitors_updated": count})


# ── Editorial ──────────────────────────────────────────────────────────────

@strategy_admin_bp.route("/api/admin/strategy/editorial")
@admin_required
@api_error_handler("Editorial quality")
def editorial_quality():
    """Editorial quality distribution across content corpus."""
    with db.connection() as conn:
        total = conn.execute("""
            SELECT COUNT(*) as cnt FROM content_item WHERE status = 'drill_ready'
        """).fetchone()['cnt']

        short = conn.execute("""
            SELECT COUNT(*) as cnt FROM content_item
            WHERE status = 'drill_ready' AND length(hanzi) < 4
        """).fetchone()['cnt']

        return jsonify({
            "total_items": total,
            "short_vocabulary_items": short,
            "content_depth_ratio": round((total - short) / total, 3) if total > 0 else 0,
        })
