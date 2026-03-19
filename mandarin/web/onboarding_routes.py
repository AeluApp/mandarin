"""Onboarding routes — new user setup wizard + placement quiz."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..placement import generate_placement_quiz, score_placement
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

onboarding_bp = Blueprint("onboarding", __name__)


_HSK_WORD_COUNTS = {1: 150, 2: 300, 3: 600, 4: 1200, 5: 2500, 6: 5000}


def _compute_endowed_progress(estimated_level: int) -> dict:
    """Compute endowed progress from placement result (Nunes & Dreze 2006).

    Frames existing knowledge as real progress toward conversational fluency.
    All numbers are factual estimates based on HSK vocabulary counts.
    """
    # Estimate words already known based on placement level
    words_known = _HSK_WORD_COUNTS.get(max(1, estimated_level - 1), 0)
    # Target: HSK 4 (conversational fluency) = ~1200 words
    target = _HSK_WORD_COUNTS.get(4, 1200)
    pct = min(100, round(words_known / target * 100))

    if estimated_level <= 1:
        message = "Starting fresh — your first words are waiting."
    elif estimated_level == 2:
        message = (f"Based on your placement, you already know approximately "
                   f"{words_known} words. Your journey to conversational "
                   f"fluency is already {pct}% underway.")
    else:
        message = (f"Based on your placement, you already know approximately "
                   f"{words_known} words — {pct}% of the way to conversational "
                   f"fluency.")

    # Modality readiness framing — learners aren't starting from zero
    modality_readiness = []
    if estimated_level >= 2:
        modality_readiness.append(
            f"Reading passages at HSK {estimated_level} level are ready for you"
        )
        modality_readiness.append(
            "Listening practice will start at a comfortable pace"
        )
    if estimated_level >= 3:
        modality_readiness.append(
            "Conversation scenarios are available for your level"
        )

    return {
        "words_known_estimate": words_known,
        "target_words": target,
        "target_label": "conversational fluency (HSK 4)",
        "percent_complete": pct,
        "message": message,
        "modality_readiness": modality_readiness,
    }


def _auto_seed_content(conn, user_id: int) -> int:
    """Seed HSK content based on the user's learner profile level.

    Always seeds HSK 1. If the user's level is 2+, also seeds up to that level.
    Returns total items added. Skips silently if content already exists.
    """
    from ..importer import import_hsk_level

    # Read user's chosen level from learner_profile
    row = conn.execute(
        "SELECT level_reading FROM learner_profile WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    user_level = int(row["level_reading"]) if row and row["level_reading"] else 1
    user_level = max(1, min(user_level, 6))

    total_added = 0
    for level in range(1, user_level + 1):
        try:
            added, _ = import_hsk_level(conn, level)
            total_added += added
            logger.info("Auto-seeded HSK %d: %d items for user %d", level, added, user_id)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("Auto-seed HSK %d failed for user %d: %s", level, user_id, e)
    return total_added


@onboarding_bp.route("/api/onboarding/wizard")
@login_required
@api_error_handler("OnboardingWizard")
def onboarding_wizard():
    """Check if user has completed the initial setup wizard."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT onboarding_complete, daily_goal FROM user WHERE id = ?",
                (current_user.id,)
            ).fetchone()
            if not row:
                return jsonify({"complete": False})
            return jsonify({
                "complete": bool(row["onboarding_complete"]),
                "daily_goal": row["daily_goal"] or "standard",
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Onboarding status error (%s): %s", type(e).__name__, e)
        return jsonify({"complete": True})  # Fail open — don't block existing users


@onboarding_bp.route("/api/onboarding/level", methods=["POST"])
@login_required
@api_error_handler("OnboardingLevel")
def set_level():
    """Set user's starting HSK level."""
    try:
        data = request.get_json(silent=True) or {}
        level = data.get("level", 1)
        if level not in (1, 2, 3, 4, 5, 6):
            return jsonify({"error": "Invalid HSK level"}), 400

        with db.connection() as conn:
            # Update learner profile levels to match starting HSK
            base_level = float(level)
            conn.execute(
                """UPDATE learner_profile
                   SET level_reading = ?, level_listening = ?,
                       level_speaking = ?, level_ime = ?, level_chunks = ?,
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (base_level, base_level, max(1.0, base_level - 0.5),
                 max(1.0, base_level - 0.5), base_level, current_user.id)
            )
            conn.commit()
            # Lifecycle: onboarding_level_set
            try:
                from ..marketing_hooks import log_lifecycle_event
                log_lifecycle_event("onboarding_level_set", user_id=str(current_user.id), conn=conn, level=level)
            except Exception:
                pass
            return jsonify({"level": level})
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Onboarding level error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not set level"}), 500


@onboarding_bp.route("/api/onboarding/goal", methods=["POST"])
@login_required
@api_error_handler("OnboardingGoal")
def set_goal():
    """Set user's daily study goal."""
    try:
        data = request.get_json(silent=True) or {}
        goal = data.get("goal", "standard")
        if goal not in ("quick", "standard", "deep"):
            return jsonify({"error": "Invalid goal"}), 400

        session_lengths = {"quick": 6, "standard": 12, "deep": 20}
        target_sessions = {"quick": 3, "standard": 4, "deep": 5}

        with db.connection() as conn:
            conn.execute(
                "UPDATE user SET daily_goal = ?, updated_at = datetime('now') WHERE id = ?",
                (goal, current_user.id)
            )
            conn.execute(
                """UPDATE learner_profile
                   SET preferred_session_length = ?, target_sessions_per_week = ?,
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (session_lengths[goal], target_sessions[goal], current_user.id)
            )
            conn.commit()
            # Lifecycle: onboarding_goal_set
            try:
                from ..marketing_hooks import log_lifecycle_event
                log_lifecycle_event("onboarding_goal_set", user_id=str(current_user.id), conn=conn, goal=goal)
            except Exception:
                pass
            return jsonify({"goal": goal})
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Onboarding goal error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not set goal"}), 500


@onboarding_bp.route("/api/onboarding/complete", methods=["POST"])
@login_required
@api_error_handler("OnboardingComplete")
def complete():
    """Mark onboarding as complete and auto-seed HSK content."""
    try:
        with db.connection() as conn:
            conn.execute(
                "UPDATE user SET onboarding_complete = 1, updated_at = datetime('now') WHERE id = ?",
                (current_user.id,)
            )
            conn.commit()

            # Auto-seed HSK content so the user can immediately start drilling
            seeded = _auto_seed_content(conn, current_user.id)

            # Lifecycle: onboarding_complete
            try:
                from ..marketing_hooks import log_lifecycle_event
                log_lifecycle_event("onboarding_complete", user_id=str(current_user.id), conn=conn)
            except Exception:
                pass
            return jsonify({"complete": True, "items_seeded": seeded})
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Onboarding complete error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not complete onboarding"}), 500


@onboarding_bp.route("/api/onboarding/placement/start")
@login_required
@api_error_handler("PlacementStart")
def placement_start():
    """Generate a placement quiz for the current user."""
    try:
        with db.connection() as conn:
            questions = generate_placement_quiz(conn)
            if not questions:
                return jsonify({"error": "Could not generate placement quiz"}), 500
            # Strip correct answers from response (client shouldn't see them)
            client_questions = []
            for q in questions:
                client_questions.append({
                    "question_number": q["question_number"],
                    "hanzi": q["hanzi"],
                    "pinyin": q["pinyin"],
                    "hsk_level": q["hsk_level"],
                    "options": q["options"],
                })
            return jsonify({"questions": client_questions})
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Placement start error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not start placement quiz"}), 500


@onboarding_bp.route("/api/onboarding/placement/submit", methods=["POST"])
@login_required
@api_error_handler("PlacementSubmit")
def placement_submit():
    """Score placement quiz, set level, seed content, mark onboarding complete.

    New flow: placement -> auto-seed content -> mark complete -> client starts
    first drill session immediately. Goal-setting is deferred until after the
    first session (optional, defaults to 5 sessions/week if skipped).
    """
    try:
        data = request.get_json(silent=True) or {}
        answers = data.get("answers", [])
        if not answers or not isinstance(answers, list):
            return jsonify({"error": "answers list required"}), 400

        result = score_placement(answers)
        estimated_level = result["estimated_level"]

        with db.connection() as conn:
            base_level = float(estimated_level)
            conn.execute(
                """UPDATE learner_profile
                   SET level_reading = ?, level_listening = ?,
                       level_speaking = ?, level_ime = ?, level_chunks = ?,
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (base_level, base_level, max(1.0, base_level - 0.5),
                 max(1.0, base_level - 0.5), base_level, current_user.id)
            )

            # Immediately seed content so the first drill session has items
            seeded = _auto_seed_content(conn, current_user.id)

            # Mark onboarding complete — goal-setting is deferred
            # Default: 5 sessions/week (standard pace), can be changed later
            conn.execute(
                """UPDATE user SET onboarding_complete = 1, daily_goal = COALESCE(daily_goal, 'standard'),
                   updated_at = datetime('now') WHERE id = ?""",
                (current_user.id,)
            )
            conn.execute(
                """UPDATE learner_profile
                   SET preferred_session_length = COALESCE(
                       NULLIF(preferred_session_length, 0), 12),
                       target_sessions_per_week = COALESCE(
                       NULLIF(target_sessions_per_week, 0), 5),
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (current_user.id,)
            )
            conn.commit()

            # Lifecycle events
            try:
                from ..marketing_hooks import log_lifecycle_event
                log_lifecycle_event("onboarding_complete", user_id=str(current_user.id), conn=conn)
            except Exception:
                pass

        # Endowed progress (Nunes & Dreze 2006): frame existing knowledge
        # as progress toward a goal. All data is real, from placement.
        endowed = _compute_endowed_progress(estimated_level)
        result["endowed_progress"] = endowed

        result["items_seeded"] = seeded
        result["ready_for_first_session"] = seeded > 0
        return jsonify(result)
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Placement submit error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not score placement quiz"}), 500


@onboarding_bp.route("/api/onboarding/goal/skip", methods=["POST"])
@login_required
@api_error_handler("OnboardingGoalSkip")
def skip_goal():
    """Skip goal-setting — defaults to 5 sessions/week (standard pace).

    Called when user taps "skip for now" on the post-first-session goal screen.
    """
    try:
        with db.connection() as conn:
            conn.execute(
                "UPDATE user SET daily_goal = COALESCE(daily_goal, 'standard'), updated_at = datetime('now') WHERE id = ?",
                (current_user.id,)
            )
            conn.execute(
                """UPDATE learner_profile
                   SET preferred_session_length = COALESCE(
                       NULLIF(preferred_session_length, 0), 12),
                       target_sessions_per_week = COALESCE(
                       NULLIF(target_sessions_per_week, 0), 5),
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (current_user.id,)
            )
            conn.commit()
            return jsonify({"goal": "standard", "skipped": True})
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Goal skip error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not skip goal"}), 500


@onboarding_bp.route("/api/onboarding/study-time", methods=["POST"])
@login_required
@api_error_handler("OnboardingStudyTime")
def set_study_time():
    """Set preferred study time (Gollwitzer implementation intentions).

    'When do you usually have 5 free minutes?' Captures a time preference
    so notifications arrive at the right moment. Research shows this
    doubles habit formation rates vs. generic goal-setting.
    """
    try:
        data = request.get_json(silent=True) or {}
        study_time = data.get("study_time", "varies")
        if study_time not in ("morning", "lunch", "evening", "varies"):
            study_time = "varies"

        with db.connection() as conn:
            # Add preferred_study_time if column exists
            try:
                conn.execute(
                    """UPDATE learner_profile
                       SET preferred_study_time = ?, updated_at = datetime('now')
                       WHERE user_id = ?""",
                    (study_time, current_user.id)
                )
            except sqlite3.OperationalError:
                # Column doesn't exist yet — migration pending
                logger.debug("preferred_study_time column not yet available")
            conn.commit()

            # Lifecycle event
            try:
                from ..marketing_hooks import log_lifecycle_event
                log_lifecycle_event(
                    "study_time_set", user_id=str(current_user.id), conn=conn,
                    study_time=study_time,
                )
            except Exception:
                pass

        return jsonify({"study_time": study_time, "set": True})
    except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
        logger.error("Study time error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not set study time preference"}), 500
