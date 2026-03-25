"""Learner intelligence API — aggregated SRS metrics for the dashboard."""

import logging
import math
from datetime import date, datetime, timedelta, timezone, UTC

from flask import Blueprint, jsonify
from flask_login import login_required

from .. import db
from ..ai.memory_model import compute_retrievability
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)

intelligence_bp = Blueprint("intelligence", __name__)

# Human-readable labels for error_type codes stored in error_log.
_ERROR_TYPE_LABELS = {
    "tone": "tone confusion",
    "segment": "word segmentation",
    "ime_confusable": "IME confusable",
    "grammar": "grammar pattern",
    "vocab": "lexical selection",
    "other": "other",
    "register_mismatch": "register mismatch",
    "particle_misuse": "particle misuse",
    "function_word_omission": "function word omission",
    "temporal_sequencing": "temporal sequencing",
    "measure_word": "measure word",
    "politeness_softening": "politeness softening",
    "reference_tracking": "reference tracking",
    "pragmatics_mismatch": "pragmatics mismatch",
    "number": "number error",
}


@intelligence_bp.route("/api/learner-intelligence")
@login_required
@api_error_handler("LearnerIntelligence")
def api_learner_intelligence():
    """Aggregated learner intelligence snapshot."""
    user_id = _get_user_id()

    with db.connection() as conn:
        # ── Retrievability zone counts ────────────────────────
        rows = conn.execute(
            """SELECT half_life_days, last_review_date
               FROM progress
               WHERE user_id = ? AND last_review_date IS NOT NULL
                 AND half_life_days > 0""",
            (user_id,),
        ).fetchall()

        now = datetime.now(UTC)
        optimal_zone_count = 0
        total_items_learning = len(rows)

        for r in rows:
            try:
                last_review = datetime.fromisoformat(r["last_review_date"])
                if last_review.tzinfo is None:
                    last_review = last_review.replace(tzinfo=UTC)
                elapsed = max(0.0, (now - last_review).total_seconds() / 86400)
                ret = compute_retrievability(r["half_life_days"], elapsed)
                if 0.70 <= ret <= 0.85:
                    optimal_zone_count += 1
            except (ValueError, TypeError):
                continue

        # ── Velocity: avg items correct per session (last 10) ─
        sessions = conn.execute(
            """SELECT items_correct FROM session_log
               WHERE user_id = ? AND items_correct > 0
               ORDER BY started_at DESC LIMIT 10""",
            (user_id,),
        ).fetchall()

        if sessions:
            velocity = round(
                sum(s["items_correct"] for s in sessions) / len(sessions), 1
            )
        else:
            velocity = 0.0

        # ── Top errors this week ──────────────────────────────
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        error_rows = conn.execute(
            """SELECT error_type, COUNT(*) AS cnt
               FROM error_log
               WHERE user_id = ? AND created_at >= ?
               GROUP BY error_type
               ORDER BY cnt DESC
               LIMIT 3""",
            (user_id, week_ago),
        ).fetchall()

        top_errors = [
            {
                "type": _ERROR_TYPE_LABELS.get(e["error_type"], e["error_type"]),
                "count": e["cnt"],
            }
            for e in error_rows
        ]

        # ── Forecast ──────────────────────────────────────────
        durable_count = conn.execute(
            """SELECT COUNT(*) AS n FROM progress
               WHERE user_id = ? AND mastery_stage IN ('stable', 'durable')""",
            (user_id,),
        ).fetchone()["n"]

        if velocity > 0 and durable_count < 500:
            sessions_needed = math.ceil((500 - durable_count) / velocity)
            target_date = (now + timedelta(days=sessions_needed)).strftime("%B %d")
            forecast = (
                f"At this pace, you'll have 500 durable items by {target_date}"
            )
        elif durable_count >= 500:
            forecast = f"You already have {durable_count} durable items — keep going!"
        else:
            forecast = "Complete a few sessions to unlock your forecast"

        # ── Difficulty note ───────────────────────────────────
        if total_items_learning == 0:
            difficulty_note = "No items tracked yet — start a session to begin"
        elif optimal_zone_count > total_items_learning * 0.5:
            difficulty_note = (
                "Today's session should feel productive — most items are "
                "in the optimal challenge zone"
            )
        elif optimal_zone_count < total_items_learning * 0.15:
            difficulty_note = (
                "Expect a tougher session — many items have drifted "
                "outside the ideal recall window"
            )
        else:
            difficulty_note = "Normal difficulty — a healthy mix of easy and challenging items"

    return jsonify({
        "optimal_zone_count": optimal_zone_count,
        "total_items_learning": total_items_learning,
        "velocity": velocity,
        "top_errors": top_errors,
        "forecast": forecast,
        "difficulty_note": difficulty_note,
    })
