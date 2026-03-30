"""NPS (Net Promoter Score) routes — persist feedback from Flutter/web clients."""

import logging
import sqlite3
from flask import Blueprint, request, jsonify, g

from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

nps_bp = Blueprint("nps", __name__)


def _get_db():
    return g.db


@nps_bp.route("/api/feedback/nps", methods=["POST"])
@api_error_handler("NPS")
def submit_nps():
    """Save an NPS response (score 0-10 + optional feedback)."""
    db = _get_db()
    data = request.get_json(silent=True) or {}
    score = data.get("score")
    feedback = data.get("feedback", "")

    if score is None or not isinstance(score, int) or score < 0 or score > 10:
        return jsonify({"error": "score must be an integer 0-10"}), 400

    user_id = getattr(g, "current_user_id", None)
    try:
        db.execute(
            "INSERT INTO nps_response (user_id, score, feedback) VALUES (?, ?, ?)",
            (user_id, score, feedback),
        )
        db.commit()
    except sqlite3.Error:
        pass  # Table may not exist yet

    return jsonify({"status": "ok"}), 201


@nps_bp.route("/api/admin/quality/nps")
@api_error_handler("NPS Admin")
def admin_nps():
    """Return NPS score, trend, and recent feedback for the admin dashboard."""
    db = _get_db()
    try:
        # Current NPS (last 30 days)
        rows = db.execute(
            "SELECT score FROM nps_response WHERE responded_at > datetime('now', '-30 days')"
        ).fetchall()

        if not rows:
            return jsonify({"nps": None, "responses": 0, "trend": [], "feedback": []})

        scores = [r[0] for r in rows]
        promoters = sum(1 for s in scores if s >= 9) / len(scores) * 100
        detractors = sum(1 for s in scores if s <= 6) / len(scores) * 100
        nps = round(promoters - detractors, 1)

        # 12-week trend
        trend = db.execute("""
            SELECT
                strftime('%Y-W%W', responded_at) AS week,
                COUNT(*) AS responses,
                ROUND(
                    (SUM(CASE WHEN score >= 9 THEN 1.0 ELSE 0 END) / COUNT(*) * 100) -
                    (SUM(CASE WHEN score <= 6 THEN 1.0 ELSE 0 END) / COUNT(*) * 100),
                    1
                ) AS nps
            FROM nps_response
            WHERE responded_at > datetime('now', '-84 days')
            GROUP BY week
            ORDER BY week
        """).fetchall()

        # Recent feedback (last 10 with text)
        feedback = db.execute(
            "SELECT score, feedback, responded_at FROM nps_response "
            "WHERE feedback IS NOT NULL AND feedback != '' "
            "ORDER BY responded_at DESC LIMIT 10"
        ).fetchall()

        return jsonify({
            "nps": nps,
            "responses": len(scores),
            "promoters_pct": round(promoters, 1),
            "passives_pct": round(100 - promoters - detractors, 1),
            "detractors_pct": round(detractors, 1),
            "trend": [{"week": r[0], "responses": r[1], "nps": r[2]} for r in trend],
            "feedback": [{"score": r[0], "text": r[1], "date": r[2]} for r in feedback],
        })
    except sqlite3.Error:
        return jsonify({"nps": None, "responses": 0, "trend": [], "feedback": []})
