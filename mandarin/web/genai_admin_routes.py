"""GenAI admin routes — corpus coverage, usage maps, prompt registry, session analysis."""

import logging

from flask import Blueprint, jsonify, request
from flask_login import login_required

from .admin_routes import admin_required
from .api_errors import api_error_handler
from .. import db

logger = logging.getLogger(__name__)

genai_admin_bp = Blueprint("genai_admin", __name__)


@genai_admin_bp.route("/api/admin/genai/corpus-coverage")
@admin_required
def genai_corpus_coverage():
    """Corpus coverage report."""
    from ..ai.genai_layer import analyze_corpus_coverage
    with db.connection() as conn:
        report = analyze_corpus_coverage(conn)
    return jsonify(report)


@genai_admin_bp.route("/api/admin/genai/populate-usage-maps", methods=["POST"])
@admin_required
def genai_populate_usage_maps():
    """Trigger usage map generation."""
    from ..ai.genai_layer import populate_usage_maps
    batch_size = request.json.get("batch_size", 10) if request.is_json else 10
    batch_size = min(int(batch_size), 50)
    with db.connection() as conn:
        result = populate_usage_maps(conn, batch_size=batch_size)
    return jsonify(result)


@genai_admin_bp.route("/api/admin/genai/prompt-registry")
@admin_required
def genai_prompt_registry():
    """Prompt registry view."""
    from ..ai.genai_layer import PROMPT_REGISTRY, seed_prompt_registry
    with db.connection() as conn:
        seeded = seed_prompt_registry(conn)
        # Read back from DB
        try:
            rows = conn.execute(
                "SELECT prompt_key, version, category, created_at, updated_at "
                "FROM genai_prompt_registry ORDER BY prompt_key"
            ).fetchall()
            db_entries = [dict(r) for r in rows]
        except Exception:
            db_entries = []
    return jsonify({
        "registry": {k: {"category": v["category"], "version": v["version"]}
                     for k, v in PROMPT_REGISTRY.items()},
        "db_entries": db_entries,
        "seeded_this_call": seeded,
    })


@genai_admin_bp.route("/api/admin/genai/session-analysis/<int:session_id>")
@admin_required
def genai_session_analysis(session_id):
    """Session analysis — error shapes + diagnostics."""
    from ..ai.genai_layer import diagnose_session
    with db.connection() as conn:
        result = diagnose_session(conn, session_id)
    return jsonify(result)
