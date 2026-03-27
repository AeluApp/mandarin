"""Classroom routes — teacher/student classroom management.

Blueprint providing:
- Create/list/archive classrooms (teacher)
- Join classroom by invite code (student)
- Student list with summary stats (teacher)
- Per-student analytics (teacher)
- Class-level analytics (teacher)
- Bulk invite via CSV or generated codes (teacher)
- Teacher notifications (teacher)
"""

import csv
import io
import logging
import secrets
import sqlite3
from datetime import datetime, timezone, UTC

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..email import send_classroom_invite
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

classroom_bp = Blueprint("classroom", __name__)


def _require_teacher():
    """Check if current user is a teacher or admin. Returns error response or None."""
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    with db.connection() as conn:
        row = conn.execute("SELECT role, is_admin FROM user WHERE id = ?", (current_user.id,)).fetchone()
        if not row or (row["role"] != "teacher" and not row["is_admin"]):
            return jsonify({"error": "Teacher role required"}), 403
    return None



@classroom_bp.route("/api/classroom/create", methods=["POST"])
@login_required
@api_error_handler("Create classroom")
def create_classroom():
    """Teacher creates a new classroom."""
    err = _require_teacher()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"error": "Classroom name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Name too long (max 100 chars)"}), 400

    invite_code = secrets.token_urlsafe(8)

    try:
        with db.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO classroom (teacher_user_id, name, description, invite_code)
                   VALUES (?, ?, ?, ?)""",
                (current_user.id, name, description, invite_code)
            )
            classroom_id = cursor.lastrowid
            conn.commit()
            return jsonify({
                "id": classroom_id,
                "name": name,
                "invite_code": invite_code,
            }), 201
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Create classroom error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create classroom"}), 500


@classroom_bp.route("/api/classroom/list")
@login_required
@api_error_handler("List classrooms")
def list_classrooms():
    """List teacher's classrooms with student counts."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT c.id, c.name, c.description, c.invite_code, c.max_students,
                          c.billing_type, c.status, c.created_at,
                          COUNT(cs.id) as student_count,
                          AVG(CASE WHEN sl.items_completed > 0
                              THEN CAST(sl.items_correct AS REAL) / sl.items_completed * 100
                              ELSE NULL END) as avg_accuracy
                   FROM classroom c
                   LEFT JOIN classroom_student cs ON cs.classroom_id = c.id AND cs.status = 'active'
                   LEFT JOIN session_log sl ON sl.user_id = cs.user_id
                       AND sl.items_completed > 0
                       AND sl.started_at >= datetime('now', '-30 days')
                   WHERE c.teacher_user_id = ? AND c.status = 'active'
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
                (current_user.id,)
            ).fetchall()

            classrooms = []
            for r in rows:
                classrooms.append({
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"],
                    "invite_code": r["invite_code"],
                    "max_students": r["max_students"],
                    "billing_type": r["billing_type"],
                    "status": r["status"],
                    "student_count": r["student_count"] or 0,
                    "avg_accuracy": round(r["avg_accuracy"], 1) if r["avg_accuracy"] else None,
                    "created_at": r["created_at"],
                })
            return jsonify({"classrooms": classrooms})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("List classrooms error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not list classrooms"}), 500


@classroom_bp.route("/api/classroom/join", methods=["POST"])
@login_required
@api_error_handler("Join classroom")
def join_classroom():
    """Student joins a classroom by invite code."""
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()

    if not code:
        return jsonify({"error": "Invite code required"}), 400
    if len(code) > 64:
        return jsonify({"error": "Invalid invite code"}), 400

    try:
        with db.connection() as conn:
            # Find classroom by invite code
            classroom = conn.execute(
                "SELECT id, name, teacher_user_id, max_students, status FROM classroom WHERE invite_code = ?",
                (code,)
            ).fetchone()

            if not classroom:
                # Also check invite_code table for classroom-linked codes
                ic_row = conn.execute(
                    "SELECT classroom_id FROM invite_code WHERE code = ?", (code,)
                ).fetchone()
                if ic_row and ic_row["classroom_id"]:
                    classroom = conn.execute(
                        "SELECT id, name, teacher_user_id, max_students, status FROM classroom WHERE id = ?",
                        (ic_row["classroom_id"],)
                    ).fetchone()

            if not classroom:
                return jsonify({"error": "Invalid invite code"}), 404

            if classroom["status"] != "active":
                return jsonify({"error": "This classroom is no longer active"}), 400

            # Check if already joined
            existing = conn.execute(
                "SELECT id FROM classroom_student WHERE classroom_id = ? AND user_id = ?",
                (classroom["id"], current_user.id)
            ).fetchone()
            if existing:
                return jsonify({"error": "Already joined this classroom"}), 400

            # Check capacity
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM classroom_student WHERE classroom_id = ? AND status = 'active'",
                (classroom["id"],)
            ).fetchone()
            if count and count["cnt"] >= (classroom["max_students"] or 30):
                return jsonify({"error": "Classroom is full"}), 400

            # Join
            conn.execute(
                "INSERT INTO classroom_student (classroom_id, user_id) VALUES (?, ?)",
                (classroom["id"], current_user.id)
            )

            # Upgrade student to paid tier (classroom students get paid access)
            conn.execute(
                "UPDATE user SET subscription_tier = 'paid', updated_at = datetime('now') WHERE id = ?",
                (current_user.id,)
            )
            conn.commit()

            # Get teacher name
            teacher = conn.execute(
                "SELECT display_name FROM user WHERE id = ?",
                (classroom["teacher_user_id"],)
            ).fetchone()

            return jsonify({
                "classroom_id": classroom["id"],
                "classroom_name": classroom["name"],
                "teacher_name": teacher["display_name"] if teacher else "",
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Join classroom error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not join classroom"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/students")
@login_required
@api_error_handler("Classroom students")
def classroom_students(classroom_id):
    """Student list with summary stats for a classroom."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            # Verify ownership
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            rows = conn.execute(
                """SELECT u.id, u.display_name, u.email, cs.joined_at,
                          MAX(sl.started_at) as last_session,
                          COUNT(DISTINCT sl.id) as total_sessions,
                          AVG(CASE WHEN sl.items_completed > 0
                              THEN CAST(sl.items_correct AS REAL) / sl.items_completed * 100
                              ELSE NULL END) as avg_accuracy
                   FROM classroom_student cs
                   JOIN user u ON u.id = cs.user_id
                   LEFT JOIN session_log sl ON sl.user_id = cs.user_id AND sl.items_completed > 0
                   WHERE cs.classroom_id = ? AND cs.status = 'active'
                   GROUP BY u.id
                   ORDER BY u.display_name""",
                (classroom_id,)
            ).fetchall()

            from ..churn_detection import compute_churn_risk
            students = []
            for r in rows:
                churn = compute_churn_risk(conn, user_id=r["id"])
                students.append({
                    "id": r["id"],
                    "display_name": r["display_name"],
                    "email": r["email"],
                    "joined_at": r["joined_at"],
                    "last_session": r["last_session"],
                    "total_sessions": r["total_sessions"] or 0,
                    "avg_accuracy": round(r["avg_accuracy"], 1) if r["avg_accuracy"] else None,
                    "churn_risk_score": churn["score"],
                    "churn_risk_level": churn["risk_level"],
                    "churn_type": churn.get("churn_type", "unknown"),
                })
            return jsonify({"students": students})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Classroom students error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch students"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/student/<int:student_id>")
@login_required
@api_error_handler("Student detail")
def classroom_student_detail(classroom_id, student_id):
    """Detailed per-student analytics."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            # Verify ownership and enrollment
            check = conn.execute(
                """SELECT cs.id FROM classroom_student cs
                   JOIN classroom c ON c.id = cs.classroom_id
                   WHERE cs.classroom_id = ? AND cs.user_id = ?
                     AND c.teacher_user_id = ? AND cs.status = 'active'""",
                (classroom_id, student_id, current_user.id)
            ).fetchone()
            if not check:
                return jsonify({"error": "Student not found in this classroom"}), 404

            # Accuracy by drill type (from error_log drill_type)
            drill_accuracy = conn.execute(
                """SELECT el.drill_type,
                          COUNT(*) as total,
                          SUM(CASE WHEN el.error_type = 'other' THEN 0 ELSE 1 END) as errors
                   FROM error_log el
                   WHERE el.user_id = ? AND el.drill_type IS NOT NULL
                   GROUP BY el.drill_type""",
                (student_id,)
            ).fetchall()

            # HSK mastery progress
            hsk_progress = conn.execute(
                """SELECT ci.hsk_level,
                          COUNT(*) as total,
                          SUM(CASE WHEN p.mastery_stage IN ('stable', 'durable') THEN 1 ELSE 0 END) as mastered
                   FROM content_item ci
                   LEFT JOIN progress p ON p.content_item_id = ci.id AND p.user_id = ?
                   WHERE ci.status = 'drill_ready'
                   GROUP BY ci.hsk_level
                   ORDER BY ci.hsk_level""",
                (student_id,)
            ).fetchall()

            # Session frequency (last 30 days)
            sessions_30d = conn.execute(
                """SELECT date(started_at) as day, COUNT(*) as cnt
                   FROM session_log
                   WHERE user_id = ? AND items_completed > 0
                     AND started_at >= datetime('now', '-30 days')
                   GROUP BY day
                   ORDER BY day""",
                (student_id,)
            ).fetchall()

            # Items mastered count
            mastered = conn.execute(
                """SELECT COUNT(DISTINCT content_item_id) as cnt
                   FROM progress
                   WHERE user_id = ? AND mastery_stage IN ('stable', 'durable')""",
                (student_id,)
            ).fetchone()

            # Profile levels
            profile = conn.execute(
                "SELECT level_reading, level_listening, level_speaking, level_ime FROM learner_profile WHERE user_id = ?",
                (student_id,)
            ).fetchone()

            # Health metrics (Doctrine §2, §12, §13)
            from ..diagnostics import compute_false_mastery_rate, compute_graduation_rate
            from ..churn_detection import compute_churn_risk
            false_mastery = compute_false_mastery_rate(conn, user_id=student_id)
            graduation = compute_graduation_rate(conn, user_id=student_id)
            churn = compute_churn_risk(conn, user_id=student_id)

            # Per-item tone struggles
            tone_struggles = []
            try:
                tone_rows = conn.execute("""
                    SELECT ci.hanzi, ci.pinyin, p.tone_attempts, p.tone_correct
                    FROM progress p
                    JOIN content_item ci ON ci.id = p.content_item_id
                    WHERE p.user_id = ? AND p.tone_attempts >= 3
                    ORDER BY (CAST(p.tone_correct AS REAL) / p.tone_attempts) ASC
                    LIMIT 10
                """, (student_id,)).fetchall()
                tone_struggles = [
                    {"hanzi": r["hanzi"], "pinyin": r["pinyin"],
                     "attempts": r["tone_attempts"], "correct": r["tone_correct"],
                     "accuracy_pct": round(r["tone_correct"] / r["tone_attempts"] * 100, 1)}
                    for r in tone_rows
                ]
            except sqlite3.OperationalError:
                pass

            return jsonify({
                "drill_accuracy": [
                    {"drill_type": r["drill_type"], "total": r["total"], "errors": r["errors"]}
                    for r in drill_accuracy
                ],
                "hsk_progress": [
                    {"hsk_level": r["hsk_level"], "total": r["total"], "mastered": r["mastered"] or 0}
                    for r in hsk_progress
                ],
                "session_frequency": [
                    {"day": r["day"], "count": r["cnt"]}
                    for r in sessions_30d
                ],
                "items_mastered": mastered["cnt"] if mastered else 0,
                "levels": {
                    "reading": profile["level_reading"] if profile else 1.0,
                    "listening": profile["level_listening"] if profile else 1.0,
                    "speaking": profile["level_speaking"] if profile else 1.0,
                    "ime": profile["level_ime"] if profile else 1.0,
                } if profile else None,
                "false_mastery": false_mastery,
                "graduation_rate": graduation,
                "churn_risk": {
                    "score": churn["score"],
                    "risk_level": churn["risk_level"],
                    "churn_type": churn.get("churn_type", "unknown"),
                    "intervention": churn.get("intervention", ""),
                    "signals": churn["signals"],
                },
                "tone_struggles": tone_struggles,
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Student detail error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch student details"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/analytics")
@login_required
@api_error_handler("Classroom analytics")
def classroom_analytics(classroom_id):
    """Class-level aggregate analytics."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            # Average accuracy across all students
            avg_acc = conn.execute(
                """SELECT AVG(CASE WHEN sl.items_completed > 0
                       THEN CAST(sl.items_correct AS REAL) / sl.items_completed * 100
                       ELSE NULL END) as avg_accuracy
                   FROM session_log sl
                   JOIN classroom_student cs ON cs.user_id = sl.user_id
                   WHERE cs.classroom_id = ? AND cs.status = 'active'
                     AND sl.items_completed > 0
                     AND sl.started_at >= datetime('now', '-30 days')""",
                (classroom_id,)
            ).fetchone()

            # HSK level distribution
            hsk_dist = conn.execute(
                """SELECT
                       CASE
                           WHEN MAX(lp.level_reading, lp.level_listening) >= 5 THEN 5
                           WHEN MAX(lp.level_reading, lp.level_listening) >= 4 THEN 4
                           WHEN MAX(lp.level_reading, lp.level_listening) >= 3 THEN 3
                           WHEN MAX(lp.level_reading, lp.level_listening) >= 2 THEN 2
                           ELSE 1
                       END as estimated_hsk,
                       COUNT(*) as cnt
                   FROM classroom_student cs
                   JOIN learner_profile lp ON lp.user_id = cs.user_id
                   WHERE cs.classroom_id = ? AND cs.status = 'active'
                   GROUP BY estimated_hsk
                   ORDER BY estimated_hsk""",
                (classroom_id,)
            ).fetchall()

            # Weekly session trend (last 8 weeks)
            weekly = conn.execute(
                """SELECT strftime('%%Y-%%W', sl.started_at) as week,
                          COUNT(DISTINCT sl.id) as sessions,
                          COUNT(DISTINCT sl.user_id) as active_students
                   FROM session_log sl
                   JOIN classroom_student cs ON cs.user_id = sl.user_id
                   WHERE cs.classroom_id = ? AND cs.status = 'active'
                     AND sl.items_completed > 0
                     AND sl.started_at >= datetime('now', '-56 days')
                   GROUP BY week
                   ORDER BY week""",
                (classroom_id,)
            ).fetchall()

            # Struggle areas: most-errored content items across the class
            struggle_rows = conn.execute(
                """SELECT ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
                          COUNT(el.id) as error_count,
                          el.drill_type as common_drill_type
                   FROM error_log el
                   JOIN classroom_student cs ON cs.user_id = el.user_id AND cs.classroom_id = ?
                   JOIN content_item ci ON ci.id = el.content_item_id
                   WHERE cs.status = 'active'
                   GROUP BY el.content_item_id
                   ORDER BY error_count DESC
                   LIMIT 10""",
                (classroom_id,)
            ).fetchall()

            struggle_areas = [{
                "hanzi": r["hanzi"],
                "pinyin": r["pinyin"],
                "english": r["english"],
                "hsk_level": r["hsk_level"],
                "error_count": r["error_count"],
                "drill_type": r["common_drill_type"]
            } for r in struggle_rows]

            return jsonify({
                "avg_accuracy": round(avg_acc["avg_accuracy"], 1) if avg_acc and avg_acc["avg_accuracy"] else None,
                "hsk_distribution": [
                    {"hsk_level": r["estimated_hsk"], "count": r["cnt"]}
                    for r in hsk_dist
                ],
                "weekly_trend": [
                    {"week": r["week"], "sessions": r["sessions"], "active_students": r["active_students"]}
                    for r in weekly
                ],
                "struggle_areas": struggle_areas,
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Classroom analytics error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch analytics"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/invite/bulk", methods=["POST"])
@login_required
@api_error_handler("Bulk invite")
def bulk_invite(classroom_id):
    """Bulk invite: CSV email upload or generate N single-use codes."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id, name FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            teacher = conn.execute(
                "SELECT display_name FROM user WHERE id = ?", (current_user.id,)
            ).fetchone()
            teacher_name = teacher["display_name"] if teacher else ""

            data = request.get_json(silent=True) or {}
            mode = data.get("mode", "generate")

            if mode == "csv":
                # Parse CSV of emails
                csv_text = data.get("csv", "")
                if not csv_text:
                    return jsonify({"error": "CSV data required"}), 400

                reader = csv.reader(io.StringIO(csv_text))
                emails = []
                for row in reader:
                    for cell in row:
                        cell = cell.strip()
                        if "@" in cell and "." in cell:
                            emails.append(cell)

                if not emails:
                    return jsonify({"error": "No valid emails found in CSV"}), 400

                codes = []
                for email in emails[:50]:  # Limit to 50
                    code = secrets.token_urlsafe(8)
                    conn.execute(
                        """INSERT INTO invite_code (code, created_at, max_uses, classroom_id)
                           VALUES (?, datetime('now'), 1, ?)""",
                        (code, classroom_id)
                    )
                    send_classroom_invite(email, teacher_name, classroom["name"], code)
                    codes.append({"email": email, "code": code})

                conn.commit()
                return jsonify({"invited": len(codes), "codes": codes})

            else:
                # Generate N single-use codes
                count = min(data.get("count", 5), 50)
                codes = []
                for _ in range(count):
                    code = secrets.token_urlsafe(8)
                    conn.execute(
                        """INSERT INTO invite_code (code, created_at, max_uses, classroom_id)
                           VALUES (?, datetime('now'), 1, ?)""",
                        (code, classroom_id)
                    )
                    codes.append(code)
                conn.commit()
                return jsonify({"codes": codes})

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Bulk invite error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not process invites"}), 500



# ── Teacher Notifications ─────────────────────────────────────────────

def _gather_teacher_notifications(conn, teacher_id):
    """Scan teacher-relevant systems for actionable alerts."""
    notifs = []
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Get teacher's classrooms
    classrooms = conn.execute(
        "SELECT id, name FROM classroom WHERE teacher_user_id = ? AND status = 'active'",
        (teacher_id,)
    ).fetchall()
    if not classrooms:
        return notifs

    classroom_ids = [c["id"] for c in classrooms]
    placeholders = ",".join("?" * len(classroom_ids))

    # 1. Students who haven't had a session in 5+ days
    try:
        sql = f"""
            SELECT cs.user_id, u.display_name, c.name AS class_name,
                   CAST(julianday('now') - julianday(
                       COALESCE((SELECT MAX(created_at) FROM session_log WHERE user_id = cs.user_id), cs.joined_at)
                   ) AS INTEGER) AS days_inactive
            FROM classroom_student cs
            JOIN user u ON u.id = cs.user_id
            JOIN classroom c ON c.id = cs.classroom_id
            WHERE cs.classroom_id IN ({placeholders})
              AND cs.status = 'active'
            HAVING days_inactive >= 5
            ORDER BY days_inactive DESC
        """
        inactive = conn.execute(sql, classroom_ids).fetchall()
        for row in inactive:
            sev = "warning" if row["days_inactive"] >= 10 else "info"
            notifs.append({
                "id": f"inactive_student_{row['user_id']}",
                "title": f"{row['display_name'] or 'A student'} inactive for {row['days_inactive']} days",
                "detail": f"In {row['class_name']}. Consider reaching out.",
                "severity": sev,
                "category": "engagement",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 2. Students with accuracy below 50% in last 7 days
    try:
        sql = f"""
            SELECT cs.user_id, u.display_name, c.name AS class_name,
                   ROUND(AVG(CASE WHEN re.correct THEN 1.0 ELSE 0.0 END) * 100, 1) AS accuracy
            FROM classroom_student cs
            JOIN user u ON u.id = cs.user_id
            JOIN classroom c ON c.id = cs.classroom_id
            LEFT JOIN review_event re ON re.user_id = cs.user_id
              AND re.created_at >= datetime('now', '-7 days')
            WHERE cs.classroom_id IN ({placeholders})
              AND cs.status = 'active'
            GROUP BY cs.user_id
            HAVING accuracy IS NOT NULL AND accuracy < 50
            ORDER BY accuracy ASC
        """
        struggling = conn.execute(sql, classroom_ids).fetchall()
        for row in struggling:
            notifs.append({
                "id": f"struggling_student_{row['user_id']}",
                "title": f"{row['display_name'] or 'A student'} at {row['accuracy']}% accuracy this week",
                "detail": f"In {row['class_name']}. May need additional support or adjusted difficulty.",
                "severity": "warning",
                "category": "learning",
                "timestamp": now_str,
            })
    except sqlite3.OperationalError:
        pass

    # 3. Student milestones in last 7 days
    try:
        sql = f"""
            SELECT le.user_id, u.display_name, c.name AS class_name,
                   le.event_type, le.created_at
            FROM lifecycle_event le
            JOIN classroom_student cs ON cs.user_id = le.user_id
            JOIN user u ON u.id = le.user_id
            JOIN classroom c ON c.id = cs.classroom_id
            WHERE cs.classroom_id IN ({placeholders})
              AND le.event_type IN ('hsk1_complete', 'hsk2_complete', 'hsk3_complete',
                  'first_session', 'streak_7', 'streak_30', 'words_100', 'words_500')
              AND le.created_at >= datetime('now', '-7 days')
            ORDER BY le.created_at DESC
        """
        milestones = conn.execute(sql, classroom_ids).fetchall()
        labels = {
            "hsk1_complete": "completed HSK 1",
            "hsk2_complete": "completed HSK 2",
            "hsk3_complete": "completed HSK 3",
            "first_session": "completed their first session",
            "streak_7": "reached a 7-day streak",
            "streak_30": "reached a 30-day streak",
            "words_100": "learned 100 words",
            "words_500": "learned 500 words",
        }
        for row in milestones:
            label = labels.get(row["event_type"], row["event_type"])
            notifs.append({
                "id": f"milestone_{row['user_id']}_{row['event_type']}",
                "title": f"{row['display_name'] or 'A student'} {label}",
                "detail": f"In {row['class_name']}.",
                "severity": "info",
                "category": "celebration",
                "timestamp": row["created_at"],
            })
    except sqlite3.OperationalError:
        pass

    # 4. Grade appeals from teacher's students
    try:
        sql = f"""
            SELECT ga.id, u.display_name, c.name AS class_name, ga.created_at
            FROM grade_appeal ga
            JOIN classroom_student cs ON cs.user_id = ga.user_id
            JOIN user u ON u.id = ga.user_id
            JOIN classroom c ON c.id = cs.classroom_id
            WHERE cs.classroom_id IN ({placeholders})
              AND ga.status = 'pending'
        """
        appeals = conn.execute(sql, classroom_ids).fetchall()
        for row in appeals:
            notifs.append({
                "id": f"grade_appeal_{row['id']}",
                "title": f"Grade appeal from {row['display_name'] or 'a student'}",
                "detail": f"In {row['class_name']}. Review and respond.",
                "severity": "warning",
                "category": "action_needed",
                "timestamp": row["created_at"],
            })
    except sqlite3.OperationalError:
        pass

    # 5. Class completion rate dropping (any class below 60% this week)
    try:
        for c in classrooms:
            stats = conn.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN sl.created_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) AS active
                FROM classroom_student cs
                LEFT JOIN session_log sl ON sl.user_id = cs.user_id
                WHERE cs.classroom_id = ? AND cs.status = 'active'
            """, (c["id"],)).fetchone()
            if stats and stats["total"] >= 3:
                rate = round((stats["active"] or 0) / stats["total"] * 100, 1)
                if rate < 60:
                    notifs.append({
                        "id": f"class_engagement_{c['id']}",
                        "title": f"{c['name']}: only {rate}% of students active this week",
                        "detail": "Consider sending a reminder or checking in with the class.",
                        "severity": "warning",
                        "category": "engagement",
                        "timestamp": now_str,
                    })
    except sqlite3.OperationalError:
        pass

    # Sort: warnings first, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    notifs.sort(key=lambda n: severity_order.get(n["severity"], 3))

    return notifs


@classroom_bp.route("/api/classroom/notifications")
@login_required
@api_error_handler("TeacherNotifications")
def teacher_notifications():
    """Return teacher-relevant notifications."""
    err = _require_teacher()
    if err:
        return err
    try:
        with db.connection() as conn:
            notifs = _gather_teacher_notifications(conn, current_user.id)
            return jsonify({"notifications": notifs, "count": len(notifs)})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Teacher notifications error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Notifications unavailable"}), 500


@classroom_bp.route("/api/classroom/notifications/count")
@login_required
@api_error_handler("TeacherNotifCount")
def teacher_notifications_count():
    """Return teacher notification badge count."""
    err = _require_teacher()
    if err:
        return err
    try:
        with db.connection() as conn:
            notifs = _gather_teacher_notifications(conn, current_user.id)
            important = [n for n in notifs if n["severity"] in ("critical", "warning")]
            return jsonify({"count": len(important)})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Teacher notif count error (%s): %s", type(e).__name__, e)
        return jsonify({"count": 0})


@classroom_bp.route("/api/classroom/<int:classroom_id>/archive", methods=["POST"])
@login_required
@api_error_handler("Archive classroom")
def archive_classroom(classroom_id):
    """Archive (soft delete) a classroom."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            result = conn.execute(
                """UPDATE classroom SET status = 'archived', updated_at = datetime('now')
                   WHERE id = ? AND teacher_user_id = ? AND status = 'active'""",
                (classroom_id, current_user.id)
            )
            if result.rowcount == 0:
                return jsonify({"error": "Classroom not found or already archived"}), 404
            conn.commit()
            return jsonify({"archived": True})
    except (sqlite3.Error, KeyError, ValueError) as e:
        logger.error("Archive classroom error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not archive classroom"}), 500


# ── Assignment Creation ──────────────────────────────────

@classroom_bp.route("/api/classroom/assignment", methods=["POST"])
@login_required
@api_error_handler("CreateAssignment")
def create_assignment():
    """Teacher creates an assignment for a class.

    Body (JSON):
        classroom_id (int): Target classroom.
        title (str): Assignment title.
        hsk_level (int, optional): HSK level for items.
        content_item_ids (list[int], optional): Specific content items.
        drill_types (list[str], optional): Specific drill types to assign.
        due_date (str, optional): ISO date string for due date.
        notes (str, optional): Teacher notes.

    Creates assignment record; students see assigned items prioritized in sessions.
    """
    err = _require_teacher()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    classroom_id = data.get("classroom_id")
    title = (data.get("title") or "").strip()
    assignment_type = data.get("assignment_type", "drill")
    if assignment_type not in ("drill", "reading", "listening", "conversation", "grammar"):
        assignment_type = "drill"
    hsk_level = data.get("hsk_level")
    content_item_ids = data.get("content_item_ids", [])
    drill_types = data.get("drill_types", [])
    due_date = data.get("due_date")
    notes = (data.get("notes") or "").strip()

    if not classroom_id:
        return jsonify({"error": "classroom_id is required"}), 400
    if not title:
        return jsonify({"error": "title is required"}), 400
    if len(title) > 200:
        return jsonify({"error": "Title too long (max 200 chars)"}), 400

    try:
        import json as _json
        with db.connection() as conn:
            # Verify teacher owns this classroom
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            # If hsk_level specified but no specific items, auto-select items
            if hsk_level and not content_item_ids:
                items = conn.execute("""
                    SELECT id FROM content_item
                    WHERE hsk_level = ? AND status = 'drill_ready'
                    ORDER BY RANDOM() LIMIT 20
                """, (hsk_level,)).fetchall()
                content_item_ids = [r["id"] for r in items]

            cursor = conn.execute("""
                INSERT INTO classroom_assignment
                (classroom_id, teacher_user_id, title, hsk_level,
                 content_item_ids, drill_types, due_date, notes, assignment_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (classroom_id, current_user.id, title, hsk_level,
                  _json.dumps(content_item_ids),
                  _json.dumps(drill_types) if drill_types else None,
                  due_date, notes, assignment_type))
            assignment_id = cursor.lastrowid
            conn.commit()

            return jsonify({
                "id": assignment_id,
                "title": title,
                "classroom_id": classroom_id,
                "item_count": len(content_item_ids),
            }), 201

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Create assignment error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create assignment"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/assignments")
@login_required
@api_error_handler("ListAssignments")
def list_assignments(classroom_id):
    """List assignments for a classroom."""
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            rows = conn.execute("""
                SELECT id, title, hsk_level, due_date, notes, created_at,
                       content_item_ids, drill_types
                FROM classroom_assignment
                WHERE classroom_id = ?
                ORDER BY created_at DESC
            """, (classroom_id,)).fetchall()

            import json as _json
            assignments = []
            for r in rows:
                item_ids = _json.loads(r["content_item_ids"]) if r["content_item_ids"] else []
                assignments.append({
                    "id": r["id"],
                    "title": r["title"],
                    "hsk_level": r["hsk_level"],
                    "due_date": r["due_date"],
                    "notes": r["notes"],
                    "item_count": len(item_ids),
                    "created_at": r["created_at"],
                })
            return jsonify({"assignments": assignments})

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("List assignments error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch assignments"}), 500


# ── Student Progress Export ──────────────────────────────

@classroom_bp.route("/api/classroom/export")
@login_required
@api_error_handler("ExportProgress")
def export_progress():
    """Export student progress data as CSV for gradebooks.

    Query params:
        class_id (int): Classroom ID (required).
        format (str): Export format, currently only 'csv' (default).
    """
    from flask import Response
    err = _require_teacher()
    if err:
        return err

    class_id = request.args.get("class_id", type=int)
    if not class_id:
        return jsonify({"error": "class_id is required"}), 400

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id, name FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (class_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            rows = conn.execute("""
                SELECT u.display_name, u.email,
                       COALESCE(lp.level_reading, 1.0) AS level_reading,
                       COALESCE(lp.level_listening, 1.0) AS level_listening,
                       COALESCE(lp.level_speaking, 1.0) AS level_speaking,
                       COALESCE(lp.total_sessions, 0) AS total_sessions,
                       COUNT(DISTINCT CASE WHEN p.mastery_stage IN ('stable', 'durable')
                           THEN p.content_item_id END) AS words_mastered,
                       ROUND(AVG(CASE WHEN sl.items_completed > 0
                           THEN CAST(sl.items_correct AS REAL) / sl.items_completed * 100
                           ELSE NULL END), 1) AS avg_accuracy,
                       MAX(sl.started_at) AS last_session
                FROM classroom_student cs
                JOIN user u ON u.id = cs.user_id
                LEFT JOIN learner_profile lp ON lp.user_id = cs.user_id
                LEFT JOIN progress p ON p.user_id = cs.user_id
                LEFT JOIN session_log sl ON sl.user_id = cs.user_id
                    AND sl.items_completed > 0
                WHERE cs.classroom_id = ? AND cs.status = 'active'
                GROUP BY u.id
                ORDER BY u.display_name
            """, (class_id,)).fetchall()

            # Build CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Name", "Email", "Reading Level", "Listening Level",
                "Speaking Level", "Total Sessions", "Words Mastered",
                "Avg Accuracy %", "Last Session"
            ])
            for r in rows:
                writer.writerow([
                    r["display_name"] or "", r["email"] or "",
                    r["level_reading"], r["level_listening"],
                    r["level_speaking"], r["total_sessions"],
                    r["words_mastered"] or 0,
                    r["avg_accuracy"] or "",
                    r["last_session"] or "",
                ])

            csv_content = output.getvalue()
            filename = f"aelu_{classroom['name'].replace(' ', '_')}_progress.csv"

            return Response(
                csv_content,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Export progress error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Export failed"}), 500


# ── Class Leaderboard ────────────────────────────────────

@classroom_bp.route("/api/classroom/leaderboard")
@login_required
@api_error_handler("ClassLeaderboard")
def class_leaderboard():
    """Return anonymized accuracy/streak rankings for a class.

    Query params:
        class_id (int): Classroom ID (required).
        period (str): 'week' or 'month' (default: 'week').

    Students are shown by display_name (or "Learner N").
    Rankings are by composite score: accuracy * 0.6 + streak * 0.2 + sessions * 0.2.
    """
    class_id = request.args.get("class_id", type=int)
    period = request.args.get("period", "week")

    if not class_id:
        return jsonify({"error": "class_id is required"}), 400

    days = 7 if period == "week" else 30

    try:
        with db.connection() as conn:
            # Verify user is teacher of this class OR a student in it
            is_teacher = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (class_id, current_user.id)
            ).fetchone()
            is_student = conn.execute(
                "SELECT id FROM classroom_student WHERE classroom_id = ? AND user_id = ? AND status = 'active'",
                (class_id, current_user.id)
            ).fetchone()
            if not is_teacher and not is_student:
                return jsonify({"error": "Not a member of this classroom"}), 403

            rows = conn.execute("""
                SELECT u.id, u.display_name, u.anonymous_mode,
                       COUNT(DISTINCT sl.id) AS sessions,
                       ROUND(AVG(CASE WHEN sl.items_completed > 0
                           THEN CAST(sl.items_correct AS REAL) / sl.items_completed * 100
                           ELSE NULL END), 1) AS accuracy,
                       COUNT(DISTINCT CASE WHEN p.mastery_stage IN ('stable', 'durable')
                           THEN p.content_item_id END) AS words_mastered
                FROM classroom_student cs
                JOIN user u ON u.id = cs.user_id
                LEFT JOIN session_log sl ON sl.user_id = cs.user_id
                    AND sl.items_completed > 0
                    AND sl.started_at >= datetime('now', ?)
                LEFT JOIN progress p ON p.user_id = cs.user_id
                WHERE cs.classroom_id = ? AND cs.status = 'active'
                GROUP BY u.id
                ORDER BY accuracy DESC, sessions DESC
            """, (f"-{days} days", class_id)).fetchall()

            leaderboard = []
            for i, r in enumerate(rows):
                name = r["display_name"] or f"Learner {i + 1}"
                if r["anonymous_mode"]:
                    name = f"Learner {i + 1}"
                accuracy = r["accuracy"] or 0
                sessions = r["sessions"] or 0

                # Composite score
                score = accuracy * 0.6 + min(sessions * 5, 100) * 0.2 + min(r["words_mastered"] or 0, 100) * 0.2

                leaderboard.append({
                    "rank": i + 1,
                    "display_name": name,
                    "accuracy": accuracy,
                    "sessions": sessions,
                    "words_mastered": r["words_mastered"] or 0,
                    "score": round(score, 1),
                    "is_you": r["id"] == current_user.id,
                })

            # Sort by score descending, re-rank
            leaderboard.sort(key=lambda x: x["score"], reverse=True)
            for i, entry in enumerate(leaderboard):
                entry["rank"] = i + 1

            return jsonify({"leaderboard": leaderboard, "period": period})

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Leaderboard error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Leaderboard unavailable"}), 500


# ── Teacher Dashboard Intelligence (Doc 7) ──────────────────────────────────


@classroom_bp.route("/api/classroom/<int:classroom_id>/intelligence", methods=["GET"])
@login_required
@api_error_handler("Classroom intelligence")
def classroom_intelligence(classroom_id):
    """Classroom health overview + 14-day snapshot trend."""
    err = _require_teacher()
    if err:
        return err

    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
            (classroom_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Classroom not found"}), 404

        from ..intelligence.cohort_analysis import get_classroom_health
        from ..intelligence.engagement import score_intervention_effectiveness

        health = get_classroom_health(conn, classroom_id)

        # 14-day snapshot trend
        snapshots = conn.execute("""
            SELECT snapshot_date, total_students, active_students_7d,
                   avg_accuracy, avg_sessions_per_student,
                   at_risk_count, high_risk_count, avg_abandonment_risk,
                   engagement_trend
            FROM pi_cohort_snapshots
            WHERE classroom_id = ? AND snapshot_date >= date('now', '-14 days')
            ORDER BY snapshot_date ASC
        """, (classroom_id,)).fetchall()

        trend = [dict(s) for s in snapshots]

        return jsonify({"health": health, "trend": trend})


@classroom_bp.route("/api/classroom/<int:classroom_id>/students/risk", methods=["GET"])
@login_required
@api_error_handler("Student risk list")
def classroom_student_risk(classroom_id):
    """Per-student risk list sorted by risk desc."""
    err = _require_teacher()
    if err:
        return err

    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
            (classroom_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Classroom not found"}), 404

        from ..intelligence.engagement import compute_abandonment_risk

        students = conn.execute("""
            SELECT cs.user_id, u.display_name, u.email
            FROM classroom_student cs
            JOIN user u ON u.id = cs.user_id
            WHERE cs.classroom_id = ? AND cs.status = 'active'
        """, (classroom_id,)).fetchall()

        risk_list = []
        for s in students:
            result = compute_abandonment_risk(conn, s["user_id"])
            risk_list.append({
                "user_id": s["user_id"],
                "display_name": s["display_name"],
                "email": s["email"],
                "risk": result["risk"],
                "level": result["level"],
                "factors": result["factors"],
                "sessions_7d": result["features"]["sessions_7d"],
                "avg_accuracy_7d": result["features"]["avg_accuracy_7d"],
            })

        risk_list.sort(key=lambda x: x["risk"], reverse=True)
        return jsonify({"students": risk_list})


@classroom_bp.route("/api/classroom/<int:classroom_id>/student/<int:student_id>/engagement", methods=["GET"])
@login_required
@api_error_handler("Student engagement")
def student_engagement(classroom_id, student_id):
    """Individual student engagement history + current risk."""
    err = _require_teacher()
    if err:
        return err

    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
            (classroom_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Classroom not found"}), 404

        # Verify student is in classroom
        membership = conn.execute(
            "SELECT id FROM classroom_student WHERE classroom_id = ? AND user_id = ? AND status = 'active'",
            (classroom_id, student_id),
        ).fetchone()
        if not membership:
            return jsonify({"error": "Student not in classroom"}), 404

        from ..intelligence.engagement import compute_abandonment_risk

        current_risk = compute_abandonment_risk(conn, student_id)

        # Historical snapshots
        snapshots = conn.execute("""
            SELECT snapshot_date, sessions_7d, avg_accuracy_7d,
                   avg_duration_7d, abandonment_risk, risk_level, risk_factors
            FROM pi_engagement_snapshots
            WHERE user_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 30
        """, (student_id,)).fetchall()

        history = [dict(s) for s in snapshots]

        return jsonify({"current": current_risk, "history": history})


@classroom_bp.route("/api/classroom/intervention", methods=["POST"])
@login_required
@api_error_handler("Log intervention")
def log_intervention():
    """Log a teacher intervention with risk_at_intervention."""
    err = _require_teacher()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    intervention_type = data.get("type")
    notes = data.get("notes", "")
    classroom_id = data.get("classroom_id")

    if not student_id or not intervention_type:
        return jsonify({"error": "student_id and type are required"}), 400

    with db.connection() as conn:
        # Verify teacher owns the classroom if specified
        if classroom_id:
            row = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id),
            ).fetchone()
            if not row:
                return jsonify({"error": "Classroom not found"}), 404

        from ..intelligence.engagement import compute_abandonment_risk

        current_risk = compute_abandonment_risk(conn, student_id)

        cursor = conn.execute("""
            INSERT INTO pi_teacher_interventions
                (teacher_user_id, student_user_id, classroom_id,
                 intervention_type, notes, risk_at_intervention)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            current_user.id, student_id, classroom_id,
            intervention_type, notes, current_risk["risk"],
        ))
        conn.commit()

        return jsonify({
            "id": cursor.lastrowid,
            "risk_at_intervention": current_risk["risk"],
            "risk_level": current_risk["level"],
        })


@classroom_bp.route("/api/classroom/interventions", methods=["GET"])
@login_required
@api_error_handler("List interventions")
def list_interventions():
    """List teacher's recent interventions with effectiveness."""
    err = _require_teacher()
    if err:
        return err

    with db.connection() as conn:
        rows = conn.execute("""
            SELECT i.id, i.student_user_id, i.classroom_id,
                   i.intervention_type, i.notes,
                   i.risk_at_intervention, i.risk_after_7d,
                   i.effective, i.created_at,
                   u.display_name as student_name
            FROM pi_teacher_interventions i
            LEFT JOIN user u ON u.id = i.student_user_id
            WHERE i.teacher_user_id = ?
            ORDER BY i.created_at DESC
            LIMIT 50
        """, (current_user.id,)).fetchall()

        interventions = [dict(r) for r in rows]
        return jsonify({"interventions": interventions})


# ── Enhanced Assignment System (V95+) ──────────────────────────────

@classroom_bp.route("/api/classroom/<int:classroom_id>/assignments/create", methods=["POST"])
@login_required
@api_error_handler("CreateAssignmentV2")
def create_assignment_v2(classroom_id):
    """Create a typed assignment with submissions tracking.

    Body (JSON):
        title (str): Assignment title.
        description (str, optional): Description.
        assignment_type (str): 'drill', 'reading', 'grammar', or 'mixed'.
        content_ids (list, optional): IDs of content items/passages/grammar points.
        due_date (str, optional): ISO date string.
    """
    import json as _json
    err = _require_teacher()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    assignment_type = data.get("assignment_type", "mixed")
    content_ids = data.get("content_ids", [])
    due_date = data.get("due_date")

    if not title:
        return jsonify({"error": "title is required"}), 400
    if len(title) > 200:
        return jsonify({"error": "Title too long (max 200 chars)"}), 400
    if assignment_type not in ("drill", "reading", "grammar", "mixed"):
        return jsonify({"error": "Invalid assignment_type"}), 400

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            cursor = conn.execute("""
                INSERT INTO assignment
                (classroom_id, title, description, assignment_type, content_ids, due_date, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (classroom_id, title, description, assignment_type,
                  _json.dumps(content_ids), due_date, current_user.id))
            assignment_id = cursor.lastrowid

            # Create pending submissions for all enrolled students
            students = conn.execute(
                "SELECT user_id FROM classroom_student WHERE classroom_id = ? AND status = 'active'",
                (classroom_id,)
            ).fetchall()
            for s in students:
                conn.execute(
                    "INSERT OR IGNORE INTO assignment_submission (assignment_id, user_id) VALUES (?, ?)",
                    (assignment_id, s["user_id"])
                )

            conn.commit()

            return jsonify({
                "id": assignment_id,
                "title": title,
                "assignment_type": assignment_type,
                "student_count": len(students),
            }), 201

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Create assignment v2 error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create assignment"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/assignments/list")
@login_required
@api_error_handler("ListAssignmentsV2")
def list_assignments_v2(classroom_id):
    """List typed assignments for a classroom with submission stats."""
    import json as _json
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            rows = conn.execute("""
                SELECT a.id, a.title, a.description, a.assignment_type,
                       a.content_ids, a.due_date, a.status, a.created_at,
                       COUNT(sub.id) as total_submissions,
                       SUM(CASE WHEN sub.status = 'completed' THEN 1 ELSE 0 END) as completed_submissions,
                       AVG(sub.score) as avg_score
                FROM assignment a
                LEFT JOIN assignment_submission sub ON sub.assignment_id = a.id
                WHERE a.classroom_id = ?
                GROUP BY a.id
                ORDER BY a.created_at DESC
            """, (classroom_id,)).fetchall()

            assignments = []
            for r in rows:
                cids = _json.loads(r["content_ids"]) if r["content_ids"] else []
                assignments.append({
                    "id": r["id"],
                    "title": r["title"],
                    "description": r["description"],
                    "assignment_type": r["assignment_type"],
                    "content_count": len(cids),
                    "due_date": r["due_date"],
                    "status": r["status"],
                    "total_submissions": r["total_submissions"] or 0,
                    "completed_submissions": r["completed_submissions"] or 0,
                    "avg_score": round(r["avg_score"], 1) if r["avg_score"] else None,
                    "created_at": r["created_at"],
                })
            return jsonify({"assignments": assignments})

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("List assignments v2 error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch assignments"}), 500


@classroom_bp.route("/api/assignments/<int:assignment_id>")
@login_required
@api_error_handler("AssignmentDetail")
def assignment_detail(assignment_id):
    """Get assignment detail with all submissions."""
    import json as _json
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            row = conn.execute("""
                SELECT a.id, a.classroom_id, a.title, a.description,
                       a.assignment_type, a.content_ids, a.due_date,
                       a.status, a.created_at
                FROM assignment a
                JOIN classroom c ON c.id = a.classroom_id
                WHERE a.id = ? AND c.teacher_user_id = ?
            """, (assignment_id, current_user.id)).fetchone()
            if not row:
                return jsonify({"error": "Assignment not found"}), 404

            # Get submissions
            subs = conn.execute("""
                SELECT sub.id, sub.user_id, u.display_name, u.email,
                       sub.completed_at, sub.score,
                       sub.items_completed, sub.items_correct,
                       sub.time_spent_seconds, sub.status
                FROM assignment_submission sub
                JOIN user u ON u.id = sub.user_id
                WHERE sub.assignment_id = ?
                ORDER BY sub.status, u.display_name
            """, (assignment_id,)).fetchall()

            submissions = []
            for s in subs:
                submissions.append({
                    "id": s["id"],
                    "user_id": s["user_id"],
                    "display_name": s["display_name"],
                    "email": s["email"],
                    "completed_at": s["completed_at"],
                    "score": s["score"],
                    "items_completed": s["items_completed"] or 0,
                    "items_correct": s["items_correct"] or 0,
                    "time_spent_seconds": s["time_spent_seconds"] or 0,
                    "status": s["status"],
                })

            content_ids = _json.loads(row["content_ids"]) if row["content_ids"] else []

            return jsonify({
                "id": row["id"],
                "classroom_id": row["classroom_id"],
                "title": row["title"],
                "description": row["description"],
                "assignment_type": row["assignment_type"],
                "content_ids": content_ids,
                "due_date": row["due_date"],
                "status": row["status"],
                "created_at": row["created_at"],
                "submissions": submissions,
            })

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Assignment detail error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch assignment"}), 500


@classroom_bp.route("/api/assignments/<int:assignment_id>/submit", methods=["POST"])
@login_required
@api_error_handler("SubmitAssignment")
def submit_assignment(assignment_id):
    """Student submits assignment completion data.

    Body (JSON):
        items_completed (int): Number of items done.
        items_correct (int): Number correct.
        time_spent_seconds (int): Time spent.
    """
    data = request.get_json(silent=True) or {}
    items_completed = data.get("items_completed", 0)
    items_correct = data.get("items_correct", 0)
    time_spent = data.get("time_spent_seconds", 0)

    try:
        with db.connection() as conn:
            # Verify assignment exists and student has a submission
            assignment = conn.execute(
                "SELECT id, due_date, status FROM assignment WHERE id = ?",
                (assignment_id,)
            ).fetchone()
            if not assignment:
                return jsonify({"error": "Assignment not found"}), 404
            if assignment["status"] != "active":
                return jsonify({"error": "Assignment is no longer active"}), 400

            sub = conn.execute(
                "SELECT id, status FROM assignment_submission WHERE assignment_id = ? AND user_id = ?",
                (assignment_id, current_user.id)
            ).fetchone()
            if not sub:
                return jsonify({"error": "You are not assigned this assignment"}), 403

            if sub["status"] == "completed":
                return jsonify({"error": "Already submitted"}), 400

            # Determine if late
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            status = "completed"
            if assignment["due_date"] and now_str > assignment["due_date"]:
                status = "late"

            score = round(items_correct / items_completed * 100, 1) if items_completed > 0 else 0.0

            conn.execute("""
                UPDATE assignment_submission
                SET completed_at = ?, score = ?, items_completed = ?,
                    items_correct = ?, time_spent_seconds = ?, status = ?
                WHERE assignment_id = ? AND user_id = ?
            """, (now_str, score, items_completed, items_correct,
                  time_spent, status, assignment_id, current_user.id))
            conn.commit()

            return jsonify({
                "status": status,
                "score": score,
            })

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Submit assignment error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not submit assignment"}), 500


# ── Exportable Progress Reports (V95+) ──────────────────────────────

@classroom_bp.route("/api/classroom/<int:classroom_id>/export")
@login_required
@api_error_handler("ExportProgressV2")
def export_progress_v2(classroom_id):
    """Export student progress as CSV with full metrics.

    Query params:
        format (str): 'csv' (default and only option).

    Returns CSV with columns: name, email, sessions_this_week, accuracy,
    active_hsk_level, streak, last_session_date.
    """
    from flask import Response
    err = _require_teacher()
    if err:
        return err

    fmt = request.args.get("format", "csv")
    if fmt != "csv":
        return jsonify({"error": "Only csv format is supported"}), 400

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id, name FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            rows = conn.execute("""
                SELECT u.display_name, u.email,
                       COUNT(DISTINCT CASE
                           WHEN sl.started_at >= datetime('now', '-7 days')
                           THEN sl.id END) AS sessions_this_week,
                       ROUND(AVG(CASE WHEN sl.items_completed > 0
                           THEN CAST(sl.items_correct AS REAL) / sl.items_completed * 100
                           ELSE NULL END), 1) AS accuracy,
                       COALESCE(
                           CAST(MAX(lp.level_reading, lp.level_listening) AS INTEGER),
                           1
                       ) AS active_hsk_level,
                       COALESCE(lp.total_sessions, 0) AS streak,
                       MAX(sl.started_at) AS last_session_date
                FROM classroom_student cs
                JOIN user u ON u.id = cs.user_id
                LEFT JOIN learner_profile lp ON lp.user_id = cs.user_id
                LEFT JOIN session_log sl ON sl.user_id = cs.user_id AND sl.items_completed > 0
                WHERE cs.classroom_id = ? AND cs.status = 'active'
                GROUP BY u.id
                ORDER BY u.display_name
            """, (classroom_id,)).fetchall()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Name", "Email", "Sessions This Week", "Accuracy %",
                "Active HSK Level", "Streak", "Last Session Date"
            ])
            for r in rows:
                writer.writerow([
                    r["display_name"] or "", r["email"] or "",
                    r["sessions_this_week"] or 0,
                    r["accuracy"] or "",
                    r["active_hsk_level"],
                    r["streak"] or 0,
                    r["last_session_date"] or "",
                ])

            csv_content = output.getvalue()
            filename = f"aelu_{classroom['name'].replace(' ', '_')}_report.csv"

            return Response(
                csv_content,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Export progress v2 error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Export failed"}), 500


# ── Curriculum Sequencing (V95+) ────────────────────────────────────

@classroom_bp.route("/api/classroom/<int:classroom_id>/curriculum", methods=["POST"])
@login_required
@api_error_handler("CreateCurriculum")
def create_curriculum(classroom_id):
    """Create a curriculum path for a classroom.

    Body (JSON):
        name (str): Curriculum name.
        description (str, optional): Description.
        sequence (list): Ordered list of {type, id, order} dicts.
    """
    import json as _json
    err = _require_teacher()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    sequence = data.get("sequence", [])

    if not name:
        return jsonify({"error": "name is required"}), 400
    if len(name) > 200:
        return jsonify({"error": "Name too long (max 200 chars)"}), 400
    if not sequence or not isinstance(sequence, list):
        return jsonify({"error": "sequence must be a non-empty list"}), 400

    # Validate sequence items
    valid_types = {"hsk_level", "grammar", "reading"}
    for item in sequence:
        if not isinstance(item, dict):
            return jsonify({"error": "Each sequence item must be an object"}), 400
        if item.get("type") not in valid_types:
            return jsonify({"error": f"Invalid sequence type: {item.get('type')}"}), 400

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            cursor = conn.execute("""
                INSERT INTO curriculum_path
                (classroom_id, name, description, sequence_json, created_by)
                VALUES (?, ?, ?, ?, ?)
            """, (classroom_id, name, description,
                  _json.dumps(sequence), current_user.id))
            conn.commit()

            return jsonify({
                "id": cursor.lastrowid,
                "name": name,
                "sequence_length": len(sequence),
            }), 201

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Create curriculum error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create curriculum path"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/curriculum", methods=["GET"])
@login_required
@api_error_handler("GetCurriculum")
def get_curriculum(classroom_id):
    """Get current curriculum paths for a classroom."""
    import json as _json
    err = _require_teacher()
    if err:
        return err

    try:
        with db.connection() as conn:
            classroom = conn.execute(
                "SELECT id FROM classroom WHERE id = ? AND teacher_user_id = ?",
                (classroom_id, current_user.id)
            ).fetchone()
            if not classroom:
                return jsonify({"error": "Classroom not found"}), 404

            rows = conn.execute("""
                SELECT id, name, description, sequence_json, created_at
                FROM curriculum_path
                WHERE classroom_id = ?
                ORDER BY created_at DESC
            """, (classroom_id,)).fetchall()

            paths = []
            for r in rows:
                seq = _json.loads(r["sequence_json"]) if r["sequence_json"] else []
                paths.append({
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"],
                    "sequence": seq,
                    "created_at": r["created_at"],
                })
            return jsonify({"curriculum_paths": paths})

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Get curriculum error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch curriculum"}), 500


@classroom_bp.route("/api/classroom/<int:classroom_id>/curriculum/<int:path_id>", methods=["PUT"])
@login_required
@api_error_handler("UpdateCurriculum")
def update_curriculum(classroom_id, path_id):
    """Update a curriculum path's sequence.

    Body (JSON):
        name (str, optional): Updated name.
        description (str, optional): Updated description.
        sequence (list): Updated ordered sequence.
    """
    import json as _json
    err = _require_teacher()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = data.get("name")
    description = data.get("description")
    sequence = data.get("sequence")

    if sequence is not None:
        if not isinstance(sequence, list) or not sequence:
            return jsonify({"error": "sequence must be a non-empty list"}), 400
        valid_types = {"hsk_level", "grammar", "reading"}
        for item in sequence:
            if not isinstance(item, dict) or item.get("type") not in valid_types:
                return jsonify({"error": "Invalid sequence item"}), 400

    try:
        with db.connection() as conn:
            # Verify ownership
            path = conn.execute("""
                SELECT cp.id FROM curriculum_path cp
                JOIN classroom c ON c.id = cp.classroom_id
                WHERE cp.id = ? AND cp.classroom_id = ? AND c.teacher_user_id = ?
            """, (path_id, classroom_id, current_user.id)).fetchone()
            if not path:
                return jsonify({"error": "Curriculum path not found"}), 404

            updates = []
            params = []
            if name is not None:
                name = name.strip()
                if not name:
                    return jsonify({"error": "name cannot be empty"}), 400
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description.strip())
            if sequence is not None:
                updates.append("sequence_json = ?")
                params.append(_json.dumps(sequence))

            if not updates:
                return jsonify({"error": "No fields to update"}), 400

            params.append(path_id)
            sql = f"UPDATE curriculum_path SET {', '.join(updates)} WHERE id = ?"
            conn.execute(sql, params)
            conn.commit()

            return jsonify({"updated": True, "id": path_id})

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Update curriculum error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not update curriculum path"}), 500


# ── Dictionary Endpoints (V95+) ─────────────────────────────────────

@classroom_bp.route("/api/dictionary/add-to-study", methods=["POST"])
@login_required
@api_error_handler("AddToStudy")
def dictionary_add_to_study():
    """Add a dictionary entry to the user's study list.

    Body (JSON):
        simplified (str): Simplified hanzi.
        traditional (str, optional): Traditional hanzi.
        pinyin (str): Pinyin.
        english (str): English definition.
        hsk_level (int, optional): Estimated HSK level.

    Creates a content_item if no duplicate (matching hanzi) exists.
    """
    data = request.get_json(silent=True) or {}
    simplified = (data.get("simplified") or "").strip()
    pinyin = (data.get("pinyin") or "").strip()
    english = (data.get("english") or "").strip()
    hsk_level = data.get("hsk_level")

    if not simplified or not pinyin or not english:
        return jsonify({"error": "simplified, pinyin, and english are required"}), 400

    try:
        with db.connection() as conn:
            # Check for duplicate
            existing = conn.execute(
                "SELECT id FROM content_item WHERE hanzi = ?",
                (simplified,)
            ).fetchone()
            if existing:
                return jsonify({
                    "error": "Already in study list",
                    "content_item_id": existing["id"],
                }), 409

            # Estimate HSK level from user's current level if not provided
            if not hsk_level:
                profile = conn.execute(
                    "SELECT level_reading FROM learner_profile WHERE user_id = ?",
                    (current_user.id,)
                ).fetchone()
                hsk_level = int(profile["level_reading"]) if profile else 1

            cursor = conn.execute("""
                INSERT INTO content_item
                (hanzi, pinyin, english, item_type, hsk_level, status, source)
                VALUES (?, ?, ?, 'vocab', ?, 'drill_ready', 'dictionary_import')
            """, (simplified, pinyin, english, hsk_level))
            content_item_id = cursor.lastrowid
            conn.commit()

            return jsonify({
                "content_item_id": content_item_id,
                "hanzi": simplified,
                "pinyin": pinyin,
                "english": english,
                "hsk_level": hsk_level,
            }), 201

    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Add to study error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not add to study list"}), 500


@classroom_bp.route("/api/classroom/snapshots/generate", methods=["POST"])
@login_required
@api_error_handler("Generate snapshots")
def generate_snapshots():
    """Generate engagement + cohort snapshots for teacher's classrooms."""
    err = _require_teacher()
    if err:
        return err

    with db.connection() as conn:
        classrooms = conn.execute("""
            SELECT id FROM classroom
            WHERE teacher_user_id = ? AND status = 'active'
        """, (current_user.id,)).fetchall()

        from ..intelligence.engagement import generate_engagement_snapshot
        from ..intelligence.cohort_analysis import generate_cohort_snapshot

        engagement_count = 0
        cohort_count = 0

        for classroom in classrooms:
            cid = classroom["id"]

            # Generate engagement snapshots for all students
            students = conn.execute("""
                SELECT user_id FROM classroom_student
                WHERE classroom_id = ? AND status = 'active'
            """, (cid,)).fetchall()

            for student in students:
                generate_engagement_snapshot(conn, student["user_id"])
                engagement_count += 1

            # Generate cohort snapshot
            generate_cohort_snapshot(conn, cid)
            cohort_count += 1

        return jsonify({
            "engagement_snapshots": engagement_count,
            "cohort_snapshots": cohort_count,
        })
