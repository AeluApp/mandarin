"""Grammar lesson routes — points, lessons, progress, mastery overview."""

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC

from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)

grammar_bp = Blueprint("grammar", __name__)


# ── Grammar Levels (for dynamic tab generation) ───────

@grammar_bp.route("/api/grammar/levels")
@api_error_handler("GrammarLevels")
def api_grammar_levels():
    """Return list of HSK levels that have grammar points."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT hsk_level FROM grammar_point
            ORDER BY hsk_level ASC
        """).fetchall()
    return jsonify({"levels": [r["hsk_level"] for r in rows]})


# ── Grammar Points ─────────────────────────────────────

@grammar_bp.route("/api/grammar/points")
@api_error_handler("GrammarPoints")
def api_grammar_points():
    """List grammar points, optionally filtered by hsk_level or category.

    Query params:
        hsk_level (int): Filter to a specific HSK level.
        category  (str): Filter to a specific category.

    Returns a list of grammar point summaries with a 'studied' flag
    derived from grammar_progress for the current user.
    """
    user_id = _get_user_id()
    hsk_level = request.args.get("hsk_level", type=int)
    category = request.args.get("category", type=str)

    conditions = []
    params = []

    if hsk_level is not None:
        conditions.append("gp.hsk_level = ?")
        params.append(hsk_level)
    if category:
        conditions.append("gp.category = ?")
        params.append(category)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with db.connection() as conn:
        sql = f"""
            SELECT
                gp.id,
                gp.name,
                gp.name_zh,
                gp.hsk_level,
                gp.category,
                gp.difficulty,
                CASE WHEN gr.grammar_point_id IS NOT NULL THEN 1 ELSE 0 END AS studied,
                gr.mastery_score,
                gr.drill_attempts
            FROM grammar_point gp
            LEFT JOIN grammar_progress gr
                ON gp.id = gr.grammar_point_id AND gr.user_id = ?
            {where_clause}
            ORDER BY gp.hsk_level ASC, gp.difficulty ASC, gp.id ASC
        """
        rows = conn.execute(sql, [user_id] + params).fetchall()

        points = [
            {
                "id": r["id"],
                "name": r["name"],
                "name_zh": r["name_zh"] or "",
                "hsk_level": r["hsk_level"],
                "category": r["category"] or "",
                "difficulty": r["difficulty"],
                "studied": bool(r["studied"]),
                "mastery_score": r["mastery_score"] or 0.0,
                "drill_attempts": r["drill_attempts"] or 0,
            }
            for r in rows
        ]

    return jsonify({"points": points})


# ── Single Grammar Point ───────────────────────────────

@grammar_bp.route("/api/grammar/point/<int:point_id>")
@api_error_handler("GrammarPoint")
def api_grammar_point(point_id):
    """Return full details for a single grammar point.

    Includes:
        - Parsed examples from examples_json
        - Linked content items (from content_grammar join content_item)
          with mastery info from the progress table
        - studied flag and mastery_score from grammar_progress
    """
    user_id = _get_user_id()

    with db.connection() as conn:
        row = conn.execute("""
            SELECT
                gp.id,
                gp.name,
                gp.name_zh,
                gp.hsk_level,
                gp.category,
                gp.description,
                gp.examples_json,
                gp.difficulty,
                gr.studied_at,
                gr.drill_attempts,
                gr.drill_correct,
                gr.mastery_score
            FROM grammar_point gp
            LEFT JOIN grammar_progress gr
                ON gp.id = gr.grammar_point_id AND gr.user_id = ?
            WHERE gp.id = ?
        """, (user_id, point_id)).fetchone()

        if not row:
            return jsonify({"error": "Grammar point not found"}), 404

        # Parse examples from JSON string
        examples = []
        if row["examples_json"]:
            try:
                examples = json.loads(row["examples_json"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse examples_json for grammar_point %d", point_id)

        # Fetch linked content items with progress info
        linked_rows = conn.execute("""
            SELECT
                ci.id,
                ci.hanzi,
                ci.pinyin,
                ci.english,
                ci.hsk_level,
                COALESCE(p.mastery_stage, 'unseen') AS mastery_stage
            FROM content_grammar cg
            JOIN content_item ci ON cg.content_item_id = ci.id
            LEFT JOIN progress p
                ON ci.id = p.content_item_id
                AND p.modality = 'reading'
                AND p.user_id = ?
            WHERE cg.grammar_point_id = ?
            ORDER BY ci.hsk_level ASC, ci.id ASC
        """, (user_id, point_id)).fetchall()

        linked_items = [
            {
                "id": lr["id"],
                "hanzi": lr["hanzi"] or "",
                "pinyin": lr["pinyin"] or "",
                "english": lr["english"] or "",
                "hsk_level": lr["hsk_level"],
                "mastery_stage": lr["mastery_stage"],
            }
            for lr in linked_rows
        ]

    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "name_zh": row["name_zh"] or "",
        "hsk_level": row["hsk_level"],
        "category": row["category"] or "",
        "description": row["description"] or "",
        "difficulty": row["difficulty"],
        "examples": examples,
        "linked_items": linked_items,
        "studied": row["studied_at"] is not None,
        "mastery_score": row["mastery_score"],
        "drill_attempts": row["drill_attempts"] or 0,
        "drill_correct": row["drill_correct"] or 0,
        "studied_at": row["studied_at"] or None,
    })


# ── Grammar Lesson Sequence ────────────────────────────

@grammar_bp.route("/api/grammar/lesson/<int:hsk_level>")
@api_error_handler("GrammarLesson")
def api_grammar_lesson(hsk_level):
    """Return an ordered lesson sequence for a given HSK level.

    Points are ordered by difficulty ascending so learners progress
    from simpler structures to more complex ones. Each point includes
    a 'studied' flag derived from grammar_progress.
    """
    user_id = _get_user_id()

    with db.connection() as conn:
        rows = conn.execute("""
            SELECT
                gp.id,
                gp.name,
                gp.name_zh,
                gp.hsk_level,
                gp.category,
                gp.difficulty,
                CASE WHEN gr.grammar_point_id IS NOT NULL THEN 1 ELSE 0 END AS studied,
                COALESCE(gr.mastery_score, 0) AS mastery_score,
                COALESCE(gr.drill_attempts, 0) AS drill_attempts
            FROM grammar_point gp
            LEFT JOIN grammar_progress gr
                ON gp.id = gr.grammar_point_id AND gr.user_id = ?
            WHERE gp.hsk_level = ?
            ORDER BY gp.difficulty ASC, gp.id ASC
        """, (user_id, hsk_level)).fetchall()

        points = [
            {
                "id": r["id"],
                "name": r["name"],
                "name_zh": r["name_zh"] or "",
                "hsk_level": r["hsk_level"],
                "category": r["category"] or "",
                "difficulty": r["difficulty"],
                "studied": bool(r["studied"]),
                "mastery_score": r["mastery_score"],
                "drill_attempts": r["drill_attempts"],
            }
            for r in rows
        ]

    total = len(points)
    studied_count = sum(1 for p in points if p["studied"])

    return jsonify({
        "hsk_level": hsk_level,
        "points": points,
        "total": total,
        "studied_count": studied_count,
    })


# ── Record Study Progress ──────────────────────────────

@grammar_bp.route("/api/grammar/progress", methods=["POST"])
@api_error_handler("GrammarProgress")
def api_grammar_progress():
    """Record study completion for a grammar point.

    Body (JSON):
        grammar_point_id (int): The grammar point that was studied.

    Upserts a grammar_progress row setting studied_at to now (UTC).
    """
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    grammar_point_id = data.get("grammar_point_id")

    if not grammar_point_id or not isinstance(grammar_point_id, int):
        return jsonify({"error": "grammar_point_id (integer) is required"}), 400

    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    with db.connection() as conn:
        # Verify the grammar point exists
        exists = conn.execute(
            "SELECT 1 FROM grammar_point WHERE id = ?", (grammar_point_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "Grammar point not found"}), 404

        # Upsert: if a row already exists update studied_at, otherwise insert
        conn.execute("""
            INSERT INTO grammar_progress (user_id, grammar_point_id, studied_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, grammar_point_id) DO UPDATE SET
                studied_at = excluded.studied_at
        """, (user_id, grammar_point_id, now_utc))
        conn.commit()

    return jsonify({"status": "ok", "grammar_point_id": grammar_point_id, "studied_at": now_utc})


# ── Record Practice Results ────────────────────────────

@grammar_bp.route("/api/grammar/practice", methods=["POST"])
@api_error_handler("GrammarPractice")
def api_grammar_practice():
    """Record practice quiz results for a grammar point.

    Body (JSON):
        grammar_point_id (int): The grammar point practiced.
        correct (int): Number of correct answers.
        total (int): Total number of questions.

    Updates drill_attempts, drill_correct, and computes mastery_score
    via EMA: mastery = 0.7 * new_score + 0.3 * old_score.
    """
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    grammar_point_id = data.get("grammar_point_id")
    correct = data.get("correct")
    total = data.get("total")

    if not grammar_point_id or not isinstance(grammar_point_id, int):
        return jsonify({"error": "grammar_point_id (integer) is required"}), 400
    if correct is None or not isinstance(correct, int):
        return jsonify({"error": "correct (integer) is required"}), 400
    if total is None or not isinstance(total, int) or total <= 0:
        return jsonify({"error": "total (positive integer) is required"}), 400

    with db.connection() as conn:
        # Verify grammar point exists
        exists = conn.execute(
            "SELECT 1 FROM grammar_point WHERE id = ?", (grammar_point_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "Grammar point not found"}), 404

        # Ensure grammar_progress row exists
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO grammar_progress (user_id, grammar_point_id, studied_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, grammar_point_id) DO UPDATE SET
                studied_at = excluded.studied_at
        """, (user_id, grammar_point_id, now_utc))

        # Read current values
        row = conn.execute("""
            SELECT drill_attempts, drill_correct, mastery_score
            FROM grammar_progress
            WHERE user_id = ? AND grammar_point_id = ?
        """, (user_id, grammar_point_id)).fetchone()

        old_attempts = row["drill_attempts"] or 0
        old_correct = row["drill_correct"] or 0
        old_mastery = row["mastery_score"] or 0.0

        new_score = correct / total
        mastery_score = 0.7 * new_score + 0.3 * old_mastery

        conn.execute("""
            UPDATE grammar_progress
            SET drill_attempts = ?, drill_correct = ?, mastery_score = ?
            WHERE user_id = ? AND grammar_point_id = ?
        """, (old_attempts + total, old_correct + correct, mastery_score,
              user_id, grammar_point_id))
        conn.commit()

    return jsonify({
        "status": "ok",
        "grammar_point_id": grammar_point_id,
        "mastery_score": round(mastery_score, 4),
        "drill_attempts": old_attempts + total,
        "drill_correct": old_correct + correct,
    })


# ── Mastery Overview ───────────────────────────────────

@grammar_bp.route("/api/grammar/mastery")
@api_error_handler("GrammarMastery")
def api_grammar_mastery():
    """Return a per-HSK-level overview of studied vs total grammar points.

    Response shape:
        {
          "levels": {
            "1": {"total": N, "studied": M},
            ...
          },
          "overall": {"total": N, "studied": M}
        }
    """
    user_id = _get_user_id()

    with db.connection() as conn:
        rows = conn.execute("""
            SELECT
                gp.hsk_level,
                COUNT(gp.id) AS total,
                SUM(CASE WHEN gr.grammar_point_id IS NOT NULL THEN 1 ELSE 0 END) AS studied
            FROM grammar_point gp
            LEFT JOIN grammar_progress gr
                ON gp.id = gr.grammar_point_id AND gr.user_id = ?
            GROUP BY gp.hsk_level
            ORDER BY gp.hsk_level ASC
        """, (user_id,)).fetchall()

        levels = {}
        overall_total = 0
        overall_studied = 0

        for r in rows:
            level_key = str(r["hsk_level"])
            total = r["total"] or 0
            studied = r["studied"] or 0
            levels[level_key] = {"total": total, "studied": studied}
            overall_total += total
            overall_studied += studied

    return jsonify({
        "levels": levels,
        "overall": {"total": overall_total, "studied": overall_studied},
    })


# ── Grammar Error Pattern Analysis ────────────────────

@grammar_bp.route("/api/grammar/errors")
@api_error_handler("GrammarErrors")
def api_grammar_errors():
    """Analyze which grammar patterns cause the most errors.

    Groups errors by grammar_point (via content_grammar join),
    showing which patterns need more practice. Supports ?user_id
    for teacher views, otherwise uses current user.

    Returns:
        {
          "error_patterns": [
            {
              "grammar_point_id": 1,
              "grammar_name": "...",
              "grammar_name_zh": "...",
              "hsk_level": 1,
              "total_errors": N,
              "unique_items": M,
              "recent_errors_7d": K,
              "mastery_score": 0.5,
              "explanation": "..."
            }, ...
          ]
        }
    """
    user_id = _get_user_id()
    # Allow teacher to view student errors
    target_user = request.args.get("user_id", user_id, type=int)

    with db.connection() as conn:
        rows = conn.execute("""
            SELECT gp.id AS grammar_point_id,
                   gp.name, gp.name_zh, gp.hsk_level,
                   gp.explanation, gp.pattern,
                   COUNT(el.id) AS total_errors,
                   COUNT(DISTINCT el.content_item_id) AS unique_items,
                   SUM(CASE WHEN el.created_at >= datetime('now', '-7 days')
                       THEN 1 ELSE 0 END) AS recent_errors_7d,
                   COALESCE(gpr.mastery_score, 0.0) AS mastery_score
            FROM error_log el
            JOIN content_grammar cg ON cg.content_item_id = el.content_item_id
            JOIN grammar_point gp ON gp.id = cg.grammar_point_id
            LEFT JOIN grammar_progress gpr
                ON gpr.grammar_point_id = gp.id AND gpr.user_id = ?
            WHERE el.user_id = ?
              AND el.error_type IN ('grammar', 'particle_misuse',
                  'function_word_omission', 'temporal_sequencing',
                  'politeness_softening', 'reference_tracking')
            GROUP BY gp.id
            ORDER BY total_errors DESC
            LIMIT 20
        """, (target_user, target_user)).fetchall()

        error_patterns = []
        for r in rows:
            error_patterns.append({
                "grammar_point_id": r["grammar_point_id"],
                "grammar_name": r["name"],
                "grammar_name_zh": r["name_zh"],
                "hsk_level": r["hsk_level"],
                "total_errors": r["total_errors"],
                "unique_items": r["unique_items"],
                "recent_errors_7d": r["recent_errors_7d"],
                "mastery_score": round(r["mastery_score"], 3),
                "explanation": r["explanation"] or "",
                "pattern": r["pattern"] or "",
            })

    return jsonify({"error_patterns": error_patterns})


@grammar_bp.route("/api/grammar/explanation/<int:grammar_point_id>")
@api_error_handler("GrammarExplanation")
def api_grammar_explanation(grammar_point_id):
    """Return detailed explanation for a grammar point.

    Used when a grammar drill is answered incorrectly to show the rule.
    Returns the grammar point's explanation, pattern, examples, and
    related content items.
    """
    user_id = _get_user_id()

    with db.connection() as conn:
        gp = conn.execute("""
            SELECT id, name, name_zh, hsk_level, category,
                   pattern, explanation, examples
            FROM grammar_point WHERE id = ?
        """, (grammar_point_id,)).fetchone()

        if not gp:
            return jsonify({"error": "Grammar point not found"}), 404

        # Get related content items for examples
        related = conn.execute("""
            SELECT ci.hanzi, ci.pinyin, ci.english
            FROM content_grammar cg
            JOIN content_item ci ON ci.id = cg.content_item_id
            WHERE cg.grammar_point_id = ?
            ORDER BY ci.hsk_level ASC
            LIMIT 5
        """, (grammar_point_id,)).fetchall()

        # Get user's error history for this grammar point
        errors = conn.execute("""
            SELECT el.user_answer, el.expected_answer, el.drill_type,
                   el.created_at, ci.hanzi
            FROM error_log el
            JOIN content_grammar cg ON cg.content_item_id = el.content_item_id
            JOIN content_item ci ON ci.id = el.content_item_id
            WHERE cg.grammar_point_id = ? AND el.user_id = ?
            ORDER BY el.created_at DESC
            LIMIT 5
        """, (grammar_point_id, user_id)).fetchall()

        # Parse examples JSON if stored as string
        examples = gp["examples"]
        if isinstance(examples, str):
            try:
                examples = json.loads(examples)
            except (json.JSONDecodeError, TypeError):
                examples = []

        return jsonify({
            "grammar_point_id": gp["id"],
            "name": gp["name"],
            "name_zh": gp["name_zh"],
            "hsk_level": gp["hsk_level"],
            "category": gp["category"],
            "pattern": gp["pattern"],
            "explanation": gp["explanation"] or "",
            "examples": examples or [],
            "related_vocab": [
                {"hanzi": r["hanzi"], "pinyin": r["pinyin"], "english": r["english"]}
                for r in related
            ],
            "recent_errors": [
                {
                    "user_answer": r["user_answer"],
                    "expected_answer": r["expected_answer"],
                    "drill_type": r["drill_type"],
                    "hanzi": r["hanzi"],
                    "created_at": r["created_at"],
                }
                for r in errors
            ],
        })


# ── Grammar Q&A (ask why) ────────────────────────────

@grammar_bp.route("/api/grammar/ask", methods=["POST"])
@api_error_handler("GrammarAsk")
def api_grammar_ask():
    """Answer a free-form grammar question via LLM with DB fallback.

    Body (JSON):
        question (str): The learner's question.
        grammar_point_id (int, optional): Specific grammar point context.
        content_item_id (int, optional): Item that prompted the question.

    Returns:
        {"answer": str, "grammar_point_id": int|None,
         "examples": list, "source": "llm"|"db"}
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    grammar_point_id = data.get("grammar_point_id")
    content_item_id = data.get("content_item_id")

    with db.connection() as conn:
        from ..ai.grammar_tutor import answer_grammar_question
        result = answer_grammar_question(
            conn,
            question=question,
            grammar_point_id=grammar_point_id,
            content_item_id=content_item_id,
        )

    return jsonify(result)


# ── Grammar Mini-Lesson (teach) ───────────────────────

@grammar_bp.route("/api/grammar/point/<int:point_id>/teach")
@api_error_handler("GrammarTeach")
def api_grammar_teach(point_id):
    """Generate a structured mini-lesson for a grammar point.

    Returns a full lesson: overview, rule, graduated examples,
    practice items, common mistakes. Always deterministic (no LLM).
    """
    with db.connection() as conn:
        from ..ai.grammar_tutor import generate_mini_lesson
        result = generate_mini_lesson(conn, point_id)

    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# ── Contextual Error Explanation ──────────────────────

@grammar_bp.route("/api/grammar/explain-mistake", methods=["POST"])
@api_error_handler("GrammarExplainMistake")
def api_grammar_explain_mistake():
    """Generate a contextual explanation after a drill error.

    Body (JSON):
        content_item_id (int): The item that was answered incorrectly.
        user_answer (str): What the learner typed.
        expected_answer (str): The correct answer.
        error_count (int): How many times this pattern has been wrong.

    Only triggers when error_count >= 2. Returns None-equivalent if
    no grammar point is linked or threshold not met.
    """
    data = request.get_json(silent=True) or {}
    content_item_id = data.get("content_item_id")
    if not content_item_id:
        return jsonify({"error": "content_item_id is required"}), 400

    with db.connection() as conn:
        from ..ai.grammar_tutor import explain_in_context
        result = explain_in_context(
            conn,
            content_item_id=content_item_id,
            user_answer=data.get("user_answer", ""),
            expected_answer=data.get("expected_answer", ""),
            error_count=data.get("error_count", 1),
        )

    if result is None:
        return jsonify({"triggered": False})
    return jsonify({"triggered": True, **result})
