"""Dashboard routes — status, progress, diagnostics, sessions, mastery."""

import logging
import sqlite3
from datetime import date as dt_date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from .. import db
from ..tier_gate import check_tier_access
from .api_errors import api_error_handler
from .middleware import _get_user_id, _compute_streak

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


def _compute_milestones(mastery, streak_days, total_sessions):
    """Compute milestone achievements from current stats.

    Returns a list of milestone dicts with 'type', 'message', and 'value'.
    Only includes milestones that are exactly at the threshold (newly crossed).
    """
    milestones = []

    # Words in long-term memory (stable + durable stages across all levels)
    long_term = 0
    for level_data in (mastery or {}).values():
        long_term += (level_data.get("stable") or 0) + (level_data.get("durable") or 0)

    # Identity-framed capability milestones (doctrine §7: "You can now...")
    _CAPABILITY_MESSAGES = {
        25: "You can now recognize basic greetings and numbers",
        50: "You can now handle simple daily exchanges",
        100: "You can now follow basic conversational Mandarin",
        150: "You can now navigate common real-world situations",
        200: "You can now understand most everyday conversation",
        300: "You can now engage in extended discussion topics",
        500: "You can now comprehend most general-purpose Mandarin",
    }
    word_thresholds = [25, 50, 100, 150, 200, 300, 500]
    for t in word_thresholds:
        if long_term >= t:
            milestones.append({
                "type": "words_learned",
                "threshold": t,
                "value": long_term,
                "message": _CAPABILITY_MESSAGES.get(t, f"{t} words reliably recalled"),
            })

    # HSK level completion (50%, 75%, 100% of any level)
    for level, data in (mastery or {}).items():
        pct = data.get("pct") or 0
        total = data.get("total") or 0
        if total == 0:
            continue
        for p in [50, 75, 100]:
            if pct >= p:
                milestones.append({
                    "type": "hsk_progress",
                    "threshold": p,
                    "level": level,
                    "value": round(pct),
                    "message": f"HSK {level}: {p}% mastered",
                })

    # Streak milestones
    streak_thresholds = [3, 7, 14, 30, 60, 90]
    for t in streak_thresholds:
        if streak_days >= t:
            milestones.append({
                "type": "streak",
                "threshold": t,
                "value": streak_days,
                "message": f"{t}-day study streak",
            })

    # Session count milestones
    session_thresholds = [1, 5, 10, 25, 50, 100]
    for t in session_thresholds:
        if total_sessions >= t:
            milestones.append({
                "type": "sessions",
                "threshold": t,
                "value": total_sessions,
                "message": f"{t} sessions completed",
            })

    return milestones


def _compute_modality_milestones(conn, user_id=1):
    """Compute milestones for non-core modalities (reading, listening, conversation, grammar).

    Extends the core milestones (vocabulary, streak, sessions) with
    modality-specific achievements. DOCTRINE §6: progress visibility
    should cover ALL learning features, not just vocabulary.
    """
    milestones = []

    try:
        # Reading passages completed
        reading_count = conn.execute(
            "SELECT COUNT(*) FROM reading_progress WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        _READING_MESSAGES = {
            5: "You've read your first 5 passages",
            10: "You can follow short written Chinese",
            25: "You're building real reading fluency",
            50: "You can read extended Chinese text with confidence",
        }
        for t in [5, 10, 25, 50]:
            if reading_count >= t:
                milestones.append({
                    "type": "reading_progress",
                    "threshold": t,
                    "value": reading_count,
                    "message": _READING_MESSAGES.get(t, f"{t} reading passages completed"),
                })

        # Listening sessions completed
        listening_count = conn.execute(
            "SELECT COUNT(*) FROM listening_progress WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        _LISTENING_MESSAGES = {
            5: "You've completed your first 5 listening exercises",
            10: "Your ear is tuning in to spoken Mandarin",
            25: "You can follow conversational-speed Chinese",
            50: "You have strong listening comprehension",
        }
        for t in [5, 10, 25, 50]:
            if listening_count >= t:
                milestones.append({
                    "type": "listening_progress",
                    "threshold": t,
                    "value": listening_count,
                    "message": _LISTENING_MESSAGES.get(t, f"{t} listening exercises completed"),
                })

        # Conversation sessions
        conv_count = conn.execute(
            "SELECT COUNT(*) FROM review_event WHERE user_id = ? AND drill_type = 'dialogue'",
            (user_id,)
        ).fetchone()[0]

        for t in [5, 10, 25, 50]:
            if conv_count >= t:
                milestones.append({
                    "type": "conversation_progress",
                    "threshold": t,
                    "value": conv_count,
                    "message": f"{t} conversation practice sessions",
                })

        # Grammar points mastered (mastery_score >= 0.7)
        grammar_mastered = conn.execute(
            "SELECT COUNT(*) FROM grammar_progress WHERE user_id = ? AND mastery_score >= 0.7",
            (user_id,)
        ).fetchone()[0]

        for t in [10, 25, 50]:
            if grammar_mastered >= t:
                milestones.append({
                    "type": "grammar_progress",
                    "threshold": t,
                    "value": grammar_mastered,
                    "message": f"{t} grammar patterns mastered",
                })

        # First-encounter milestones (symmetric across all modalities)
        _FIRST_ENCOUNTERS = [
            ("first_reading", "SELECT COUNT(*) FROM reading_progress WHERE user_id = ?",
             "First reading passage completed"),
            ("first_listening", "SELECT COUNT(*) FROM listening_progress WHERE user_id = ?",
             "First listening exercise completed"),
            ("first_conversation",
             "SELECT COUNT(*) FROM review_event WHERE user_id = ? AND drill_type = 'dialogue'",
             "First conversation practice completed"),
            ("first_grammar",
             "SELECT COUNT(*) FROM grammar_progress WHERE user_id = ? AND drill_attempts > 0",
             "First grammar lesson studied"),
        ]
        for milestone_key, sql, message in _FIRST_ENCOUNTERS:
            count = conn.execute(sql, (user_id,)).fetchone()[0]
            if count >= 1:
                milestones.append({
                    "type": milestone_key,
                    "threshold": 1,
                    "value": count,
                    "message": message,
                })

    except Exception:
        pass

    return milestones


def _compute_upcoming_modality_milestones(conn, user_id=1):
    """Goal gradient for modality milestones — show proximity to next achievement."""
    upcoming = []

    try:
        checks = [
            ("reading_progress", "SELECT COUNT(*) FROM reading_progress WHERE user_id = ?",
             [5, 10, 25, 50], "reading passage"),
            ("listening_progress", "SELECT COUNT(*) FROM listening_progress WHERE user_id = ?",
             [5, 10, 25, 50], "listening exercise"),
            ("conversation_progress",
             "SELECT COUNT(*) FROM review_event WHERE user_id = ? AND drill_type = 'dialogue'",
             [5, 10, 25, 50], "conversation session"),
        ]

        for milestone_type, sql, thresholds, label in checks:
            current = conn.execute(sql, (user_id,)).fetchone()[0]
            for t in thresholds:
                if current < t:
                    remaining = t - current
                    pct = current / t * 100
                    if pct >= 80:  # Within 20% (more generous for modalities)
                        upcoming.append({
                            "type": milestone_type,
                            "threshold": t,
                            "current": current,
                            "remaining": remaining,
                            "message": f"You're {remaining} {label}{'s' if remaining != 1 else ''} from {t}",
                        })
                    break
    except Exception:
        pass

    return upcoming


def _compute_upcoming_milestones(mastery, streak_days, total_sessions):
    """Compute milestones the learner is close to reaching (goal gradient).

    Kivetz et al. (2006): effort accelerates as people approach goals.
    Returns milestones within 10% of the threshold, showing proximity
    to encourage continued effort. DOCTRINE §6: progress visibility.
    """
    upcoming = []

    # Words approaching next threshold
    long_term = 0
    for level_data in (mastery or {}).values():
        long_term += (level_data.get("stable") or 0) + (level_data.get("durable") or 0)

    word_thresholds = [25, 50, 100, 150, 200, 300, 500]
    for t in word_thresholds:
        if long_term < t:
            remaining = t - long_term
            pct_complete = long_term / t * 100
            if pct_complete >= 90:  # Within 10%
                upcoming.append({
                    "type": "words_learned",
                    "threshold": t,
                    "current": long_term,
                    "remaining": remaining,
                    "message": f"You're {remaining} word{'s' if remaining != 1 else ''} from {t} in long-term memory",
                })
            break  # Only show the nearest upcoming word milestone

    # HSK level approaching completion
    for level, data in sorted((mastery or {}).items()):
        pct = data.get("pct") or 0
        total = data.get("total") or 0
        if total == 0:
            continue
        mastered = data.get("stable", 0) + data.get("durable", 0)
        for p in [50, 75, 100]:
            if pct < p and pct >= p * 0.9:  # Within 10% of threshold
                items_needed = max(1, round(total * p / 100) - mastered)
                upcoming.append({
                    "type": "hsk_progress",
                    "threshold": p,
                    "level": level,
                    "current_pct": round(pct),
                    "remaining_items": items_needed,
                    "message": f"HSK {level}: {round(pct)}% — {items_needed} item{'s' if items_needed != 1 else ''} from {p}%",
                })
                break

    return upcoming


@dashboard_bp.route("/api/status")
@api_error_handler("Status")
def api_status():
    """JSON status endpoint."""
    user_id = _get_user_id()
    with db.connection() as conn:
        profile = db.get_profile(conn, user_id=user_id)
        item_count = db.content_count(conn)
        days_gap = db.get_days_since_last_session(conn, user_id=user_id)
        mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
        items_due = db.get_items_due_count(conn, user_id=user_id)
        session_length = profile.get("preferred_session_length") or 12
        total_sessions = profile.get("total_sessions") or 0
        streak_days = _compute_streak(conn, user_id=user_id)
        milestones = _compute_milestones(mastery, streak_days, total_sessions)
        milestones += _compute_modality_milestones(conn, user_id=user_id)
        upcoming_milestones = _compute_upcoming_milestones(mastery, streak_days, total_sessions)
        upcoming_milestones += _compute_upcoming_modality_milestones(conn, user_id=user_id)

        # Next session estimate (items_due × 35s ÷ 60, capped to session_length)
        next_session_mins = min(
            round(items_due * 35 / 60),
            session_length
        ) if items_due > 0 else 0

        # Weekly progress stats
        week_row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(items_completed), 0) as items
               FROM session_log
               WHERE user_id = ?
                 AND started_at >= date('now', '-7 days')""",
            (user_id,)
        ).fetchone()
        sessions_this_week = week_row["cnt"] if week_row else 0
        items_reviewed_week = week_row["items"] if week_row else 0

        # Words in long-term memory (stable + durable across all levels)
        words_long_term = 0
        for level_data in (mastery or {}).values():
            words_long_term += (level_data.get("stable") or 0) + (level_data.get("durable") or 0)

        # Weekly accuracy + previous session accuracy for delta display
        accuracy_this_week = None
        prev_session_accuracy = None
        acc_week_row = conn.execute(
            """SELECT COALESCE(SUM(items_correct), 0) as correct,
                      COALESCE(SUM(items_completed), 0) as completed
               FROM session_log
               WHERE user_id = ? AND items_completed > 0
                 AND started_at >= date('now', '-7 days')""",
            (user_id,)
        ).fetchone()
        if acc_week_row and acc_week_row["completed"] > 0:
            accuracy_this_week = round(acc_week_row["correct"] / acc_week_row["completed"] * 100, 1)

        prev_sessions = conn.execute(
            """SELECT items_correct, items_completed
               FROM session_log
               WHERE user_id = ? AND items_completed > 0
               ORDER BY started_at DESC LIMIT 2""",
            (user_id,)
        ).fetchall()
        if len(prev_sessions) >= 2:
            ps = prev_sessions[1]  # second most recent
            if ps["items_completed"] > 0:
                prev_session_accuracy = round(ps["items_correct"] / ps["items_completed"] * 100, 1)

        # Simple forecast for users with 1-7 sessions
        simple_forecast = None
        if 1 <= total_sessions <= 7:
            # Average items correct per session
            avg_row = conn.execute(
                """SELECT AVG(items_correct) as avg_correct
                   FROM session_log
                   WHERE user_id = ? AND items_completed > 0""",
                (user_id,)
            ).fetchone()
            items_per_session = round(avg_row["avg_correct"] or 0, 1) if avg_row else 0

            # Next word milestone
            thresholds = [25, 50, 100, 150, 200, 300, 500]
            next_milestone = None
            sessions_to_milestone = None
            for t in thresholds:
                if words_long_term < t:
                    next_milestone = t
                    remaining = t - words_long_term
                    if items_per_session > 0:
                        sessions_to_milestone = max(1, round(remaining / items_per_session))
                    break

            simple_forecast = {
                "words_long_term": words_long_term,
                "items_per_session": items_per_session,
                "next_milestone": next_milestone,
                "sessions_to_milestone": sessions_to_milestone,
            }

        # Subscription tier for client-side tier gating
        from ..tier_gate import get_user_tier
        subscription_tier = get_user_tier(conn, user_id)

        # Upgrade context for free-tier users (smart paywall)
        upgrade_context = None
        if subscription_tier == "free" and not getattr(current_user, "is_admin", False):
            days_active_row = conn.execute(
                """SELECT COUNT(DISTINCT date(started_at)) as cnt
                   FROM session_log
                   WHERE user_id = ? AND items_completed > 0""",
                (user_id,)
            ).fetchone()
            days_active = days_active_row["cnt"] if days_active_row else 0

            hsk2_pct = 0
            if mastery:
                hsk2 = mastery.get(2, mastery.get("2"))
                if hsk2:
                    hsk2_pct = round(hsk2.get("pct", 0))

            upgrade_context = {
                "total_sessions": total_sessions,
                "items_learned": words_long_term,
                "days_active": days_active,
                "hsk2_pct": hsk2_pct,
            }

        # Streak recovery: detect broken streak and previous streak length
        streak_broken = False
        previous_streak = 0
        streak_freezes = 0
        if days_gap is not None and days_gap >= 2 and streak_days == 0:
            # User broke their streak — compute what it was before the gap
            streak_broken = True
            try:
                # Find sessions before the gap to compute previous streak
                gap_rows = conn.execute(
                    """SELECT DISTINCT date(started_at) as d
                       FROM session_log
                       WHERE user_id = ? AND items_completed > 0
                         AND started_at < date('now', ? || ' days')
                         AND started_at >= date('now', '-120 days')
                       ORDER BY d DESC""",
                    (user_id, str(-days_gap))
                ).fetchall()
                if gap_rows:
                    from datetime import date as dt_date
                    prev_dates = []
                    for r in gap_rows:
                        try:
                            prev_dates.append(dt_date.fromisoformat(r["d"]))
                        except (ValueError, TypeError):
                            pass
                    if prev_dates:
                        previous_streak = 1
                        for i in range(1, len(prev_dates)):
                            if (prev_dates[i - 1] - prev_dates[i]).days == 1:
                                previous_streak += 1
                            else:
                                break
            except Exception:
                pass

            # Check streak freezes available
            try:
                freeze_row = conn.execute(
                    "SELECT streak_freezes_available FROM user WHERE id = ?",
                    (user_id,)
                ).fetchone()
                streak_freezes = (freeze_row["streak_freezes_available"] or 0) if freeze_row else 0
            except sqlite3.OperationalError:
                pass

        # False-mastery health metric (doctrine §2)
        from ..diagnostics import compute_false_mastery_rate, compute_graduation_rate
        false_mastery = compute_false_mastery_rate(conn, user_id=user_id)
        graduation_rate = compute_graduation_rate(conn, user_id=user_id)

        # Top 3 tone focus items for learner (Doctrine §3: actionable feedback)
        tone_focus = []
        try:
            tone_rows = conn.execute("""
                SELECT ci.hanzi, ci.pinyin, p.tone_attempts, p.tone_correct
                FROM progress p
                JOIN content_item ci ON ci.id = p.content_item_id
                WHERE p.user_id = ? AND p.tone_attempts >= 3
                ORDER BY (CAST(p.tone_correct AS REAL) / p.tone_attempts) ASC
                LIMIT 3
            """, (user_id,)).fetchall()
            tone_focus = [
                {"hanzi": r["hanzi"], "pinyin": r["pinyin"],
                 "accuracy_pct": round(r["tone_correct"] / r["tone_attempts"] * 100, 1)}
                for r in tone_rows
            ]
        except sqlite3.OperationalError:
            pass

        return jsonify({
            "item_count": item_count,
            "total_sessions": total_sessions,
            "days_since_last": days_gap,
            "items_due": items_due,
            "mastery": {str(k): v for k, v in mastery.items()} if mastery else {},
            "user_role": getattr(current_user, "role", "student"),
            "is_admin": getattr(current_user, "is_admin", False),
            "session_length": session_length,
            "streak_days": streak_days,
            "milestones": milestones,
            "upcoming_milestones": upcoming_milestones,
            "next_session_mins": next_session_mins,
            "sessions_this_week": sessions_this_week,
            "items_reviewed_week": items_reviewed_week,
            "words_long_term": words_long_term,
            "simple_forecast": simple_forecast,
            "accuracy_this_week": accuracy_this_week,
            "prev_session_accuracy": prev_session_accuracy,
            "subscription_tier": subscription_tier,
            "upgrade_context": upgrade_context,
            "false_mastery": false_mastery,
            "graduation_rate": graduation_rate,
            "tone_focus": tone_focus,
            "streak_broken": streak_broken,
            "previous_streak": previous_streak,
            "streak_freezes": streak_freezes,
        })


@dashboard_bp.route("/api/forecast")
@api_error_handler("Forecast")
def api_forecast():
    """JSON forecast — pace, milestones, HSK projections."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if not check_tier_access(conn, user_id, "forecast"):
            return jsonify({"error": "Upgrade to access forecast"}), 403
        from ..diagnostics import project_forecast
        forecast = project_forecast(conn, user_id=user_id)
        return jsonify(forecast)


@dashboard_bp.route("/api/session-items")
@api_error_handler("SessionItems")
def api_session_items():
    """Items drilled in the most recent session with current mastery stages."""
    user_id = _get_user_id()
    with db.connection() as conn:
        # Get the most recent completed session
        session = conn.execute(
            """SELECT id, plan_snapshot FROM session_log
               WHERE user_id = ? AND items_completed > 0
               ORDER BY started_at DESC LIMIT 1""",
            (user_id,)
        ).fetchone()
        if not session or not session["plan_snapshot"]:
            return jsonify({"items": []})

        import json as _json
        try:
            snapshot = _json.loads(session["plan_snapshot"])
        except (ValueError, TypeError):
            return jsonify({"items": []})

        drills = snapshot.get("drills", [])
        if not drills:
            return jsonify({"items": []})

        # Collect unique item_ids from the session
        seen_ids = set()
        ordered_items = []
        for d in drills:
            item_id = d.get("item_id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                ordered_items.append({"item_id": item_id, "hanzi": d.get("hanzi", "")})

        if not ordered_items:
            return jsonify({"items": []})

        # Get content + progress info for each item
        id_list = [o["item_id"] for o in ordered_items]
        placeholders = ",".join("?" * len(id_list))

        # Content item data
        sql = f"""SELECT id, hanzi, pinyin, english, hsk_level
                FROM content_item WHERE id IN ({placeholders})"""
        content_rows = conn.execute(sql, id_list).fetchall()
        content_map = {r["id"]: dict(r) for r in content_rows}

        # Best mastery stage per item (across modalities)
        stage_order = ["seen", "passed_once", "stabilizing", "stable", "durable"]
        sql = f"""SELECT content_item_id, mastery_stage
                FROM progress
                WHERE user_id = ? AND content_item_id IN ({placeholders})"""
        progress_rows = conn.execute(sql, [user_id] + id_list).fetchall()
        best_stage = {}
        for pr in progress_rows:
            cid = pr["content_item_id"]
            stage = pr["mastery_stage"] or "seen"
            prev = best_stage.get(cid, "seen")
            s_idx = stage_order.index(stage) if stage in stage_order else 0
            p_idx = stage_order.index(prev) if prev in stage_order else 0
            if s_idx > p_idx:
                best_stage[cid] = stage

        # Error data from this session — items the user got wrong
        session_id = session["id"]
        sql = f"""SELECT content_item_id, user_answer, expected_answer,
                       drill_type, error_type
                FROM error_log
                WHERE session_id = ? AND content_item_id IN ({placeholders})
                ORDER BY created_at ASC"""
        error_rows = conn.execute(sql, [session_id] + id_list).fetchall()
        # Map: content_item_id → first error (most relevant)
        error_map = {}
        for er in error_rows:
            cid = er["content_item_id"]
            if cid not in error_map:
                error_map[cid] = {
                    "user_answer": er["user_answer"] or "",
                    "expected_answer": er["expected_answer"] or "",
                    "drill_type": er["drill_type"] or "",
                    "error_type": er["error_type"] or "",
                }

        result = []
        for o in ordered_items:
            cid = o["item_id"]
            ci = content_map.get(cid, {})
            stage = best_stage.get(cid, "seen")
            item = {
                "hanzi": ci.get("hanzi", o["hanzi"]),
                "pinyin": ci.get("pinyin", ""),
                "english": ci.get("english", ""),
                "stage": stage,
                "correct": cid not in error_map,
            }
            if cid in error_map:
                item["user_answer"] = error_map[cid]["user_answer"]
                item["expected_answer"] = error_map[cid]["expected_answer"]
            result.append(item)

        return jsonify({"items": result})


@dashboard_bp.route("/api/progress")
@api_error_handler("Progress")
def api_progress():
    """JSON progress — retention stats + mastery by HSK."""
    user_id = _get_user_id()
    with db.connection() as conn:
        mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
        mastery_json = {str(k): v for k, v in mastery.items()} if mastery else {}

        retention = {}
        try:
            from ..retention import compute_retention_stats
            retention = compute_retention_stats(conn)
        except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
            logger.debug("retention stats unavailable: %s", e)

        return jsonify({
            "mastery": mastery_json,
            "retention": retention,
        })


_session_preview_cache = {}  # {user_id: (timestamp, data)}
_SESSION_PREVIEW_TTL = 30  # Cache for 30 seconds

@dashboard_bp.route("/api/session-preview")
@api_error_handler("Session preview")
def api_session_preview():
    """Lightweight preview of what the next session will focus on.

    Shows adaptive intelligence without running the full planner.
    Cached per-user for 30s to reduce p95 tail latency on repeated calls.
    """
    import time
    user_id = _get_user_id()

    # Check cache
    cached = _session_preview_cache.get(user_id)
    if cached:
        cache_ts, cache_data = cached
        if time.time() - cache_ts < _SESSION_PREVIEW_TTL:
            return jsonify(cache_data)

    with db.connection() as conn:
        preview = {}

        # Day profile
        try:
            from ..scheduler import get_day_profile
            day_profile = get_day_profile(conn, user_id=user_id)
            mode = day_profile.get("mode", "normal")
            preview["day_mode"] = mode
            preview["day_label"] = day_profile.get("name", "")
            if mode == "consolidation":
                preview["day_note"] = "Consolidation day — shorter session, familiar items"
            elif mode == "gentle":
                preview["day_note"] = "Light day — review-focused"
            elif mode == "stretch":
                preview["day_note"] = "Stretch day — extra items and new material"
        except (sqlite3.Error, KeyError, TypeError) as e:
            logger.debug("session preview: day profile failed: %s", e)

        # Error focus items waiting
        try:
            error_items = db.get_error_focus_items(conn, limit=5, user_id=user_id)
            if error_items:
                preview["error_focus_count"] = len(error_items)
                types = {}
                for ei in error_items:
                    et = ei.get("focus_error_type", "other")
                    types[et] = types.get(et, 0) + 1
                preview["error_focus_types"] = types
        except (sqlite3.Error, KeyError, TypeError) as e:
            logger.debug("session preview: error focus failed: %s", e)

        # Encounter boost items from reading/listening
        try:
            encounter_rows = conn.execute("""
                SELECT COUNT(DISTINCT ve.content_item_id) as cnt
                FROM vocab_encounter ve
                WHERE ve.looked_up = 1
                  AND ve.created_at >= datetime('now', '-14 days')
                  AND ve.user_id = ?
            """, (user_id,)).fetchone()
            if encounter_rows and encounter_rows["cnt"] > 0:
                preview["encounter_boost_count"] = encounter_rows["cnt"]
        except (sqlite3.Error, KeyError, TypeError) as e:
            logger.debug("session preview: encounters failed: %s", e)

        # Tone accuracy trend
        try:
            from ..tone_grading import get_tone_accuracy
            tone_acc = get_tone_accuracy(conn, days=14, user_id=user_id)
            if tone_acc["total_recordings"] >= 3:
                preview["tone_accuracy"] = round(tone_acc["overall_accuracy"] * 100)
                preview["tone_recordings"] = tone_acc["total_recordings"]
                if tone_acc.get("confused_pairs"):
                    preview["tone_confused"] = tone_acc["confused_pairs"][:3]
        except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
            logger.debug("session preview: tone accuracy failed: %s", e)

        # Days since last session
        try:
            days_gap = db.get_days_since_last_session(conn, user_id=user_id)
            if days_gap is not None:
                preview["days_since_last"] = days_gap
        except (sqlite3.Error, KeyError, TypeError) as e:
            logger.debug("session preview: days gap failed: %s", e)

        # Last session performance
        try:
            last = conn.execute("""
                SELECT items_completed, items_correct, duration_seconds,
                       session_type, started_at
                FROM session_log
                WHERE user_id = ? AND session_outcome = 'completed'
                ORDER BY started_at DESC LIMIT 1
            """, (user_id,)).fetchone()
            if last and last["items_completed"]:
                preview["last_session"] = {
                    "correct": last["items_correct"] or 0,
                    "total": last["items_completed"],
                    "accuracy": round((last["items_correct"] or 0) / last["items_completed"] * 100),
                    "duration_min": round((last["duration_seconds"] or 0) / 60, 1),
                }
        except (sqlite3.Error, KeyError, TypeError) as e:
            logger.debug("session preview: last session failed: %s", e)

        # Cache result
        _session_preview_cache[user_id] = (time.time(), preview)
        return jsonify(preview)


@dashboard_bp.route("/api/diagnostics")
@api_error_handler("Diagnostics")
def api_diagnostics():
    """JSON diagnostics — quick assessment + queue saturation forecast."""
    user_id = _get_user_id()
    with db.connection() as conn:
        from ..diagnostics import assess_quick, queue_saturation_forecast
        result = assess_quick(conn, user_id=user_id)
        try:
            result["queue_saturation"] = queue_saturation_forecast(conn, user_id=user_id)
        except Exception:
            pass
        return jsonify(result)


@dashboard_bp.route("/api/personalization", methods=["GET", "POST"])
@api_error_handler("Personalization")
def api_personalization():
    """JSON — personalization domains and current preference."""
    user_id = _get_user_id()
    with db.connection() as conn:
        from ..personalization import INTEREST_DOMAINS, get_available_domains, get_domain_stats

        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            new_domains = (data.get("domains") or "").strip()
            available = get_available_domains()
            if new_domains:
                keys = [k.strip() for k in new_domains.split(",") if k.strip()]
                valid_keys = [k for k in keys if k in INTEREST_DOMAINS and k in available]
                new_domains = ",".join(valid_keys)
            conn.execute(
                "UPDATE learner_profile SET preferred_domains = ?, updated_at = datetime('now') WHERE user_id = ?",
                (new_domains, user_id),
            )
            conn.commit()
            return jsonify({"preferred_domains": new_domains})

        profile = db.get_profile(conn, user_id=user_id)
        current = (profile.get("preferred_domains") or "").strip()
        available = get_available_domains()
        stats = get_domain_stats()

        domains = {}
        for key, meta in INTEREST_DOMAINS.items():
            domains[key] = {
                "label": meta["label"],
                "description": meta["description"],
                "active": key in current.split(",") if current else False,
                "available": key in available,
                "sentence_count": stats.get(key, {}).get("total", 0),
            }
        return jsonify({
            "preferred_domains": current,
            "domains": domains,
        })


@dashboard_bp.route("/api/sessions")
@api_error_handler("Sessions")
def api_sessions():
    """JSON — last 20 sessions with scores + 14-day study streak data."""
    user_id = _get_user_id()
    with db.connection() as conn:
        sessions = db.get_session_history(conn, limit=20, user_id=user_id)
        result = []
        for s in sessions:
            result.append({
                "id": s["id"],
                "started_at": s.get("started_at"),
                "session_type": s.get("session_type"),
                "items_completed": s.get("items_completed") or 0,
                "items_correct": s.get("items_correct") or 0,
                "early_exit": bool(s.get("early_exit")),
                "duration_seconds": s.get("duration_seconds"),
                "session_outcome": s.get("session_outcome", "completed"),
            })

        today = dt_date.today()
        streak_data = []
        day_counts = {}
        rows = conn.execute("""
            SELECT date(started_at) as d, COUNT(*) as cnt
            FROM session_log
            WHERE user_id = ? AND started_at >= date('now', '-27 days')
              AND items_completed > 0
            GROUP BY date(started_at)
        """, (user_id,)).fetchall()
        for r in rows:
            day_counts[r["d"]] = r["cnt"]
        for i in range(27, -1, -1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            streak_data.append({
                "date": d_str,
                "sessions": day_counts.get(d_str, 0),
            })

        return jsonify({"sessions": result, "study_streak_data": streak_data})


@dashboard_bp.route("/api/session/checkpoint/<int:session_id>")
@api_error_handler("Checkpoint")
def api_session_checkpoint(session_id):
    """Check if a session is resumable."""
    user_id = _get_user_id()
    with db.connection() as conn:
        row = conn.execute("""
            SELECT id, session_type, items_planned, items_completed, items_correct,
                   session_outcome, plan_snapshot
            FROM session_log
            WHERE id = ? AND user_id = ?
        """, (session_id, user_id)).fetchone()
        if not row:
            return jsonify({"resumable": False, "reason": "not_found"})
        outcome = row["session_outcome"]
        if outcome in ("completed", "bounced", "interrupted"):
            return jsonify({"resumable": False, "reason": "already_ended"})
        planned = row["items_planned"] or 0
        completed = row["items_completed"] or 0
        if completed >= planned:
            return jsonify({"resumable": False, "reason": "all_drills_done"})
        if not row["plan_snapshot"]:
            return jsonify({"resumable": False, "reason": "no_plan"})
        return jsonify({
            "resumable": True,
            "session_id": row["id"],
            "session_type": row["session_type"],
            "items_planned": planned,
            "items_completed": completed,
            "items_correct": row["items_correct"] or 0,
        })


@dashboard_bp.route("/api/onboarding/status")
def api_onboarding_status():
    """Return which onboarding milestones the user has hit."""
    try:
        user_id = _get_user_id()
        with db.connection() as conn:
            milestones = {}

            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM session_log WHERE user_id = ? AND items_completed > 0",
                (user_id,)
            ).fetchone()
            milestones["first_session"] = (row["cnt"] if row else 0) >= 1

            first_session_row = conn.execute(
                "SELECT MIN(date(started_at)) as first_day FROM session_log WHERE user_id = ? AND items_completed > 0",
                (user_id,)
            ).fetchone()
            if first_session_row and first_session_row["first_day"]:
                first_day = first_session_row["first_day"]
                distinct_days_row = conn.execute(
                    """SELECT COUNT(DISTINCT date(started_at)) as cnt
                       FROM session_log
                       WHERE user_id = ? AND items_completed > 0
                         AND date(started_at) >= ?
                         AND date(started_at) <= date(?, '+6 days')""",
                    (user_id, first_day, first_day)
                ).fetchone()
                milestones["first_week"] = (distinct_days_row["cnt"] if distinct_days_row else 0) >= 3
            else:
                milestones["first_week"] = False

            try:
                reading_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM vocab_encounter WHERE user_id = ? AND source_type = 'reading'",
                    (user_id,)
                ).fetchone()
                milestones["first_reading"] = (reading_row["cnt"] if reading_row else 0) >= 1
            except sqlite3.OperationalError:
                milestones["first_reading"] = False

            try:
                variety_row = conn.execute(
                    "SELECT COUNT(DISTINCT session_type) as cnt FROM session_log WHERE user_id = ? AND items_completed > 0",
                    (user_id,)
                ).fetchone()
                milestones["drill_variety"] = (variety_row["cnt"] if variety_row else 0) >= 3
            except sqlite3.OperationalError:
                milestones["drill_variety"] = False

            streak = _compute_streak(conn, user_id=user_id)
            if streak >= 3:
                milestones["first_streak"] = True
            else:
                all_days = conn.execute(
                    """SELECT DISTINCT date(started_at) as d
                       FROM session_log
                       WHERE user_id = ? AND items_completed > 0
                         AND started_at >= date('now', '-90 days')
                       ORDER BY d ASC""",
                    (user_id,)
                ).fetchall()
                dates = []
                for r in all_days:
                    try:
                        dates.append(dt_date.fromisoformat(r["d"]))
                    except (ValueError, TypeError):
                        pass
                max_streak = 0
                current_s = 1
                for i in range(1, len(dates)):
                    if (dates[i] - dates[i - 1]).days == 1:
                        current_s += 1
                        max_streak = max(max_streak, current_s)
                    else:
                        current_s = 1
                if len(dates) >= 1:
                    max_streak = max(max_streak, 1)
                milestones["first_streak"] = max_streak >= 3

            milestones["all_complete"] = all(milestones.values())

            return jsonify(milestones)
    except (sqlite3.Error, OSError, KeyError, TypeError) as e:
        logger.error("onboarding status error: %s", e)
        return jsonify({"error": "Onboarding status unavailable"}), 500


@dashboard_bp.route("/api/session/explain")
def api_session_explain():
    """Return readable rationale for how the next session would be planned."""
    user_id = _get_user_id()
    try:
        with db.connection() as conn:
            from ..scheduler import (
                get_day_profile, _adjust_weights_for_errors,
                _new_item_budget, _get_hsk_bounce_levels,
                _adaptive_session_length, _time_of_day_penalty,
                _compute_interleave_weight, DEFAULT_WEIGHTS, GAP_WEIGHTS,
            )
            from ..config import LONG_GAP_DAYS

            profile = db.get_profile(conn, user_id=user_id)
            day_profile = get_day_profile(conn, user_id=user_id)
            days_gap = db.get_days_since_last_session(conn, user_id=user_id)
            is_long_gap = days_gap is not None and days_gap >= LONG_GAP_DAYS

            base_length = profile.get("preferred_session_length") or 12
            adaptive_length = _adaptive_session_length(conn, base_length, user_id=user_id)
            final_length = max(4, round(adaptive_length * day_profile["length_mult"]))

            base_weights = GAP_WEIGHTS if is_long_gap else DEFAULT_WEIGHTS
            weights = _adjust_weights_for_errors(conn, base_weights, user_id=user_id) if not is_long_gap else base_weights

            new_budget = _new_item_budget(conn, user_id=user_id) if not is_long_gap else 0
            tod_mult = _time_of_day_penalty(conn, user_id=user_id)
            bounce_levels = list(_get_hsk_bounce_levels(conn, user_id=user_id)) if not is_long_gap else []
            interleave_weight = _compute_interleave_weight(conn, user_id=user_id)

            return jsonify({
                "day_profile": day_profile,
                "gap_days": days_gap,
                "is_long_gap": is_long_gap,
                "base_session_length": base_length,
                "adaptive_session_length": adaptive_length,
                "final_session_length": final_length,
                "modality_weights": weights,
                "new_item_budget": new_budget,
                "time_of_day_penalty": tod_mult,
                "bounce_levels": bounce_levels,
                "interleave_weight": round(interleave_weight, 3),
                "focus_areas": [
                    f"{'Long gap recovery' if is_long_gap else 'Standard review'}",
                    f"Day profile: {day_profile.get('name', 'Standard')} ({day_profile.get('mode', 'standard')})",
                    f"New items budget: {new_budget}",
                ] + ([f"Bounce-detected HSK levels: {bounce_levels}"] if bounce_levels else []),
            })
    except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
        logger.error("session explain error: %s", e)
        return jsonify({"error": "Explanation unavailable"}), 500


@dashboard_bp.route("/api/mastery/<int:item_id>/criteria")
def api_mastery_criteria(item_id):
    """Return 4-gate mastery status for a specific content item."""
    user_id = _get_user_id()
    try:
        with db.connection() as conn:
            from ..config import (
                PROMOTE_STABLE_STREAK, PROMOTE_STABLE_ATTEMPTS,
                PROMOTE_STABLE_DRILL_TYPES, PROMOTE_STABLE_DAYS,
            )

            rows = conn.execute("""
                SELECT mastery_stage, streak_correct, total_attempts,
                       drill_types_seen, distinct_review_days, difficulty
                FROM progress
                WHERE content_item_id = ? AND user_id = ?
            """, (item_id, user_id)).fetchall()

            if not rows:
                return jsonify({"error": "No progress data for this item"}), 404

            best_streak = max(r["streak_correct"] or 0 for r in rows)
            total_attempts = sum(r["total_attempts"] or 0 for r in rows)
            all_types = set()
            for r in rows:
                for t in (r["drill_types_seen"] or "").split(","):
                    if t.strip():
                        all_types.add(t.strip())
            max_days = max(r["distinct_review_days"] or 0 for r in rows)
            current_stage = rows[0]["mastery_stage"] or "seen"
            difficulty = rows[0]["difficulty"] or 0.5

            diff_scale = 0.5 + difficulty
            scaled_streak = max(3, round(PROMOTE_STABLE_STREAK * diff_scale))
            scaled_attempts = max(5, round(PROMOTE_STABLE_ATTEMPTS * diff_scale))

            gates = {
                "streak": {
                    "current": best_streak,
                    "needed": scaled_streak,
                    "met": best_streak >= scaled_streak,
                },
                "attempts": {
                    "current": total_attempts,
                    "needed": scaled_attempts,
                    "met": total_attempts >= scaled_attempts,
                },
                "diversity": {
                    "current": len(all_types),
                    "needed": PROMOTE_STABLE_DRILL_TYPES,
                    "met": len(all_types) >= PROMOTE_STABLE_DRILL_TYPES,
                },
                "days": {
                    "current": max_days,
                    "needed": PROMOTE_STABLE_DAYS,
                    "met": max_days >= PROMOTE_STABLE_DAYS,
                },
            }

            gates_met = sum(1 for g in gates.values() if g["met"])
            summary = f"{current_stage}: {gates_met}/4 gates met"
            if gates_met >= 4:
                summary = f"{current_stage}: all gates met — eligible for promotion"

            return jsonify({
                "item_id": item_id,
                "mastery_stage": current_stage,
                "difficulty": round(difficulty, 3),
                "gates": gates,
                "gates_met": gates_met,
                "summary": summary,
            })
    except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
        logger.error("mastery criteria error: %s", e)
        return jsonify({"error": "Criteria unavailable"}), 500


@dashboard_bp.route("/api/growth")
@api_error_handler("Growth")
def api_growth():
    """Known-word growth over recent sessions for sparkline visualization."""
    user_id = _get_user_id()
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT date(sl.started_at) as day,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage IN ('stable', 'durable')
                         THEN p.content_item_id END) as mastered
            FROM session_log sl
            LEFT JOIN progress p ON p.user_id = sl.user_id
                AND p.last_review_date <= date(sl.started_at)
                AND p.mastery_stage IN ('stable', 'durable')
            WHERE sl.user_id = ? AND sl.items_completed > 0
            GROUP BY date(sl.started_at)
            ORDER BY day DESC
            LIMIT 14
        """, (user_id,)).fetchall()
        points = [{"day": r["day"], "mastered": r["mastered"] or 0} for r in reversed(rows)]

        # Also get current total mastered
        total = conn.execute("""
            SELECT COUNT(DISTINCT content_item_id) as cnt
            FROM progress WHERE user_id = ?
              AND mastery_stage IN ('stable', 'durable')
        """, (user_id,)).fetchone()

        return jsonify({
            "points": points,
            "total_mastered": total["cnt"] if total else 0,
        })


@dashboard_bp.route("/api/mark-correct", methods=["POST"])
def api_mark_correct():
    """Override the most recent wrong attempt as correct."""
    try:
        user_id = _get_user_id()
        data = request.get_json(silent=True) or {}
        content_item_id = data.get("content_item_id")
        modality = data.get("modality", "reading")
        if not content_item_id or not isinstance(content_item_id, int):
            return jsonify({"error": "content_item_id required (int)"}), 400
        from ..db.progress import override_last_attempt
        with db.connection() as conn:
            ok = override_last_attempt(conn, content_item_id, modality, user_id=user_id)
            if ok:
                return jsonify({"status": "ok"})
            return jsonify({"error": "No progress row found"}), 404
    except (sqlite3.Error, OSError, TypeError, ValueError) as e:
        logger.error("mark-correct API error: %s", e)
        return jsonify({"error": "Override failed"}), 500


@dashboard_bp.route("/api/dashboard/retention_curve")
@api_error_handler("RetentionCurve")
def api_retention_curve():
    """Return retention curve data: items per mastery stage and 7-day review forecast."""
    user_id = _get_user_id()
    with db.connection() as conn:
        # Items per mastery stage
        stages = conn.execute("""
            SELECT mastery_stage, COUNT(DISTINCT content_item_id) as cnt
            FROM progress WHERE user_id = ?
            GROUP BY mastery_stage
        """, (user_id,)).fetchall()
        stage_counts = {r["mastery_stage"]: r["cnt"] for r in stages}

        # 7-day review forecast: items due each day
        forecast = []
        for day_offset in range(7):
            due_row = conn.execute("""
                SELECT COUNT(*) as cnt FROM progress
                WHERE user_id = ?
                  AND next_review_date <= datetime('now', ? || ' days')
                  AND next_review_date > datetime('now', ? || ' days')
            """, (user_id, str(day_offset + 1), str(day_offset))).fetchone()
            forecast.append({
                "day_offset": day_offset,
                "items_due": due_row["cnt"] if due_row else 0,
            })

        # Total active items
        total_row = conn.execute("""
            SELECT COUNT(DISTINCT content_item_id) as cnt
            FROM progress WHERE user_id = ?
        """, (user_id,)).fetchone()

        # Overdue items (due before now)
        overdue_row = conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = ?
              AND next_review_date <= datetime('now')
              AND mastery_stage NOT IN ('durable')
        """, (user_id,)).fetchone()

        return jsonify({
            "stage_counts": stage_counts,
            "forecast": forecast,
            "total_active": total_row["cnt"] if total_row else 0,
            "overdue": overdue_row["cnt"] if overdue_row else 0,
        })


def _require_admin():
    """Check if current user is admin. Returns error response or None."""
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    if not getattr(current_user, "is_admin", False):
        return jsonify({"error": "Admin required"}), 403
    return None


@dashboard_bp.route("/api/admin/students")
@login_required
@api_error_handler("Admin students")
def admin_students():
    """Admin view: list the admin user as the only student."""
    err = _require_admin()
    if err:
        return err

    user_id = current_user.id
    with db.connection() as conn:
        user = conn.execute(
            "SELECT id, display_name, email FROM user WHERE id = ?",
            (user_id,)
        ).fetchone()
        if not user:
            return jsonify({"students": []})

        last_session = conn.execute(
            "SELECT MAX(started_at) as last FROM session_log WHERE user_id = ? AND items_completed > 0",
            (user_id,)
        ).fetchone()

        total_sessions = conn.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE user_id = ? AND items_completed > 0",
            (user_id,)
        ).fetchone()

        avg_acc = conn.execute(
            """SELECT AVG(CAST(items_correct AS REAL) / items_completed * 100) as avg
               FROM session_log WHERE user_id = ? AND items_completed > 0
               AND started_at >= datetime('now', '-30 days')""",
            (user_id,)
        ).fetchone()

        # Churn risk for list view (Doctrine §13)
        from ..churn_detection import compute_churn_risk
        churn = compute_churn_risk(conn, user_id=user_id)

        return jsonify({"students": [{
            "id": user["id"],
            "display_name": user["display_name"],
            "email": user["email"],
            "joined_at": None,
            "last_session": last_session["last"] if last_session else None,
            "total_sessions": total_sessions["cnt"] if total_sessions else 0,
            "avg_accuracy": round(avg_acc["avg"], 1) if avg_acc and avg_acc["avg"] else None,
            "churn_risk_score": churn["score"],
            "churn_risk_level": churn["risk_level"],
            "churn_type": churn.get("churn_type", "unknown"),
        }]})


@dashboard_bp.route("/api/admin/student/<int:student_id>")
@login_required
@api_error_handler("Admin student detail")
def admin_student_detail(student_id):
    """Admin view: detailed analytics for a student (admin can view self)."""
    err = _require_admin()
    if err:
        return err

    with db.connection() as conn:
        # Accuracy by drill type
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

        # Per-item tone accuracy (top struggling items)
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
            pass  # tone columns not yet migrated

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


@dashboard_bp.route("/api/streak/use-freeze", methods=["POST"])
@login_required
@api_error_handler("StreakUseFreeze")
def api_streak_use_freeze():
    """Use a streak freeze to restore the user's streak after a gap."""
    user_id = _get_user_id()
    with db.connection() as conn:
        # Check freeze availability
        row = conn.execute(
            "SELECT streak_freezes_available FROM user WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not row or (row["streak_freezes_available"] or 0) < 1:
            return jsonify({"applied": False, "error": "No streak freezes available"}), 400

        # Decrement freeze count
        conn.execute(
            "UPDATE user SET streak_freezes_available = streak_freezes_available - 1 WHERE id = ?",
            (user_id,)
        )

        # Insert a synthetic session_log entry for yesterday to bridge the gap
        from datetime import date as dt_date, timedelta
        yesterday = (dt_date.today() - timedelta(days=1)).isoformat()
        conn.execute("""
            INSERT INTO session_log (user_id, session_type, items_planned, items_completed,
                                     items_correct, started_at, ended_at)
            VALUES (?, 'freeze', 0, 0, 0, ? || ' 12:00:00', ? || ' 12:00:00')
        """, (user_id, yesterday, yesterday))
        conn.commit()

        return jsonify({"applied": True})
