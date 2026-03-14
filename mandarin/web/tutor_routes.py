"""Tutor integration API endpoints (Doc 8).

Allows logging external tutor sessions, corrections, vocabulary flags,
and triggering auto-matching to SRS items.
"""

import logging

from flask import Blueprint, jsonify, request as flask_request
from flask_login import login_required, current_user

from .. import db
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

tutor_bp = Blueprint("tutor", __name__)


@tutor_bp.route("/api/tutor/sessions", methods=["POST"])
@login_required
@api_error_handler("Tutor session create")
def create_tutor_session():
    """Log a new tutor session."""
    data = flask_request.get_json(force=True)
    with db.connection() as conn:
        cursor = conn.execute("""
            INSERT INTO tutor_sessions
                (user_id, tutor_name, platform, session_date, duration_minutes,
                 session_type, self_assessment, topics_covered, tutor_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            current_user.id,
            data.get("tutor_name"),
            data.get("platform"),
            data["session_date"],
            data.get("duration_minutes"),
            data.get("session_type"),
            data.get("self_assessment"),
            data.get("topics_covered"),
            data.get("notes"),
        ))
        conn.commit()
        return jsonify({"id": cursor.lastrowid, "status": "created"}), 201


@tutor_bp.route("/api/tutor/sessions", methods=["GET"])
@login_required
@api_error_handler("Tutor session list")
def list_tutor_sessions():
    """List the user's tutor sessions."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT id, tutor_name, platform, session_date, duration_minutes,
                   session_type, self_assessment, topics_covered, tutor_notes, processed
            FROM tutor_sessions
            WHERE user_id = ?
            ORDER BY session_date DESC
        """, (current_user.id,)).fetchall()
        sessions = []
        for r in rows:
            sessions.append({
                "id": r[0], "tutor_name": r[1], "platform": r[2],
                "session_date": r[3], "duration_minutes": r[4],
                "session_type": r[5], "self_assessment": r[6],
                "topics_covered": r[7], "tutor_notes": r[8], "processed": r[9],
            })
        return jsonify({"sessions": sessions})


@tutor_bp.route("/api/tutor/sessions/<int:session_id>/corrections", methods=["POST"])
@login_required
@api_error_handler("Tutor corrections")
def add_corrections(session_id):
    """Add corrections for a tutor session."""
    data = flask_request.get_json(force=True)
    corrections = data.get("corrections", [])
    with db.connection() as conn:
        # Verify session belongs to user
        session = conn.execute(
            "SELECT id FROM tutor_sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user.id),
        ).fetchone()
        if not session:
            return jsonify({"error": "Session not found"}), 404

        added = 0
        for c in corrections:
            conn.execute("""
                INSERT INTO tutor_corrections
                    (tutor_session_id, correction_type, wrong_form, correct_form,
                     explanation, srs_priority_boost)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                c.get("correction_type", "grammar"),
                c["wrong_form"],
                c["correct_form"],
                c.get("explanation"),
                c.get("srs_priority_boost", 0),
            ))
            added += 1
        conn.commit()
        return jsonify({"added": added})


@tutor_bp.route("/api/tutor/sessions/<int:session_id>/flags", methods=["POST"])
@login_required
@api_error_handler("Tutor vocabulary flags")
def add_vocabulary_flags(session_id):
    """Add vocabulary flags for a tutor session."""
    data = flask_request.get_json(force=True)
    flags = data.get("flags", [])
    with db.connection() as conn:
        # Verify session belongs to user
        session = conn.execute(
            "SELECT id FROM tutor_sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user.id),
        ).fetchone()
        if not session:
            return jsonify({"error": "Session not found"}), 404

        added = 0
        for f in flags:
            conn.execute("""
                INSERT INTO tutor_vocabulary_flags
                    (tutor_session_id, hanzi, pinyin, meaning, flag_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                f["hanzi"],
                f.get("pinyin"),
                f.get("meaning"),
                f.get("flag_reason", "tutor_introduced"),
            ))
            added += 1
        conn.commit()
        return jsonify({"added": added})


@tutor_bp.route("/api/tutor/sessions/<int:session_id>/process", methods=["POST"])
@login_required
@api_error_handler("Tutor session process")
def process_session(session_id):
    """Trigger auto-matching of corrections and vocabulary flags to SRS items."""
    with db.connection() as conn:
        # Verify session belongs to user
        session = conn.execute(
            "SELECT id FROM tutor_sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user.id),
        ).fetchone()
        if not session:
            return jsonify({"error": "Session not found"}), 404

        from ..intelligence.output_tone_tutor import process_tutor_session
        result = process_tutor_session(conn, session_id)
        return jsonify(result)


@tutor_bp.route("/api/tutor/stats", methods=["GET"])
@login_required
@api_error_handler("Tutor stats")
def tutor_stats():
    """Summary stats for tutor integration."""
    with db.connection() as conn:
        total_sessions = conn.execute(
            "SELECT COUNT(*) FROM tutor_sessions WHERE user_id = ?",
            (current_user.id,),
        ).fetchone()[0]
        total_corrections = conn.execute("""
            SELECT COUNT(*) FROM tutor_corrections tc
            JOIN tutor_sessions ts ON tc.tutor_session_id = ts.id
            WHERE ts.user_id = ?
        """, (current_user.id,)).fetchone()[0]
        matched_corrections = conn.execute("""
            SELECT COUNT(*) FROM tutor_corrections tc
            JOIN tutor_sessions ts ON tc.tutor_session_id = ts.id
            WHERE ts.user_id = ? AND tc.linked_content_item_id IS NOT NULL
        """, (current_user.id,)).fetchone()[0]
        total_flags = conn.execute("""
            SELECT COUNT(*) FROM tutor_vocabulary_flags tvf
            JOIN tutor_sessions ts ON tvf.tutor_session_id = ts.id
            WHERE ts.user_id = ?
        """, (current_user.id,)).fetchone()[0]
        last_session = conn.execute(
            "SELECT MAX(session_date) FROM tutor_sessions WHERE user_id = ?",
            (current_user.id,),
        ).fetchone()[0]

        return jsonify({
            "total_sessions": total_sessions,
            "total_corrections": total_corrections,
            "matched_corrections": matched_corrections,
            "total_flags": total_flags,
            "last_session": last_session,
        })
