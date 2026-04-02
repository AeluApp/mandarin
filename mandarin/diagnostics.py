"""Diagnostics — assess quick, assess full, calibrate.

Every output answers:
- What does this mean in calendar time?
- What specific action should I take?
- How will I know if it worked?
"""

import json
import logging
import random
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

from . import db
from .scheduler import DrillItem, SessionPlan, _item_is_drillable
from mandarin._paths import DATA_DIR

logger = logging.getLogger(__name__)


# ── HSK Requirements Registry ──────────────────────────────

_hsk_requirements_cache = None


def _load_hsk_requirements() -> dict:
    """Load HSK requirements from data/hsk_requirements.json. Cached."""
    global _hsk_requirements_cache
    if _hsk_requirements_cache is not None:
        return _hsk_requirements_cache
    json_path = DATA_DIR / "hsk_requirements.json"
    try:
        with open(json_path) as f:
            data = json.load(f)
        _hsk_requirements_cache = data.get("levels", {})
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Could not load hsk_requirements.json; using empty defaults")
        _hsk_requirements_cache = {}
    return _hsk_requirements_cache


def get_hsk_requirements(level: int) -> dict:
    """Get HSK requirements for a specific level. Returns empty dict if not found."""
    reqs = _load_hsk_requirements()
    return reqs.get(str(level), {})


# ── HSK vocabulary constants (derived from data/hsk/*.json) ──

def _compute_hsk_sizes() -> tuple:
    """Compute band and cumulative sizes from actual HSK JSON files.

    Falls back to official HSK 3.0 counts if files are missing.
    """
    _fallback_band = {1: 500, 2: 772, 3: 973, 4: 1000, 5: 1071, 6: 1140, 7: 1868, 8: 1868, 9: 1870}
    band = {}
    for level in range(1, 10):
        hsk_file = DATA_DIR / "hsk" / f"hsk{level}.json"
        if hsk_file.exists():
            try:
                data = json.load(hsk_file.open(encoding="utf-8"))
                band[level] = len(data.get("items", []))
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not parse hsk%d.json; using fallback band size", level)
                band[level] = _fallback_band.get(level, 0)
        else:
            band[level] = _fallback_band.get(level, 0)

    cumulative = {}
    running = 0
    for level in range(1, 10):
        running += band[level]
        cumulative[level] = running

    return band, cumulative

HSK_BAND_SIZE, HSK_CUMULATIVE = _compute_hsk_sizes()

# ── Forecast constants ──────────────────────────────

PACE_RELIABILITY_THRESHOLD = 8    # sessions before showing pace number
PROJECTION_RANGE_THRESHOLD = 12   # sessions before showing ranges


def assess_quick(conn, user_id: int = 1) -> dict:
    """Quick diagnostic: per-modality level, top bottlenecks, next actions.

    Requires ≥10 sessions. Returns a dict with all diagnostic data.
    """
    profile = db.get_profile(conn, user_id=user_id)
    sessions = db.get_session_history(conn, limit=50, user_id=user_id)
    total_sessions = profile.get("total_sessions") or 0

    if total_sessions < 10:
        return {
            "ready": False,
            "sessions_needed": 10 - total_sessions,
            "message": f"Need {10 - total_sessions} more sessions for assessment.",
        }

    # Calculate per-modality performance
    modality_stats = _compute_modality_stats(conn, user_id=user_id)
    estimated_levels = _estimate_levels(conn, modality_stats, user_id=user_id)
    # Attach total_attempts for confidence formatting
    for mod in estimated_levels:
        estimated_levels[mod]["total_attempts"] = modality_stats.get(mod, {}).get("total_attempts", 0)
    bottlenecks = _identify_bottlenecks(conn, modality_stats, user_id=user_id)
    error_patterns = db.get_error_summary(conn, last_n_sessions=20, user_id=user_id)

    # Calendar projections
    velocity = compute_velocity(sessions)
    projections = _project_milestones(conn, estimated_levels, velocity, user_id=user_id)

    return {
        "ready": True,
        "modality_stats": modality_stats,
        "estimated_levels": estimated_levels,
        "bottlenecks": bottlenecks[:3],
        "error_patterns": error_patterns,
        "velocity": velocity,
        "projections": projections,
        "total_sessions": total_sessions,
    }


def assess_full(conn, user_id: int = 1) -> dict:
    """Full diagnostic: everything in assess_quick plus forecast comparison.

    Requires ≥20 sessions.
    """
    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions") or 0
    if total_sessions < 20:
        return {
            "ready": False,
            "sessions_needed": 20 - total_sessions,
            "message": f"Need {20 - total_sessions} more sessions for full assessment.",
        }

    quick = assess_quick(conn, user_id=user_id)
    if not quick["ready"]:
        return quick

    # Additional full-assessment data
    sessions = db.get_session_history(conn, limit=100, user_id=user_id)
    engagement = _compute_engagement_trends(conn, sessions)
    error_trends = _compute_error_trends(conn, user_id=user_id)
    core_coverage = _check_core_coverage(conn, user_id=user_id)

    quick.update({
        "engagement_trends": engagement,
        "error_trends": error_trends,
        "core_coverage": core_coverage,
        "is_full": True,
    })
    return quick


# ── Level estimation ──────────────────────────────

def _compute_modality_stats(conn, user_id: int = 1) -> dict:
    """Compute accuracy and volume stats per modality."""
    stats = {}
    for modality in ["reading", "listening", "speaking", "ime"]:
        rows = conn.execute("""
            SELECT
                COUNT(*) as total_items,
                SUM(total_attempts) as total_attempts,
                SUM(total_correct) as total_correct,
                AVG(CASE WHEN total_attempts > 0
                    THEN CAST(total_correct AS REAL) / total_attempts
                    ELSE NULL END) as avg_accuracy,
                SUM(CASE WHEN streak_correct >= 3 THEN 1 ELSE 0 END) as mastered_count,
                SUM(CASE WHEN total_attempts > 0 AND total_correct = 0 THEN 1 ELSE 0 END) as struggling_count
            FROM progress WHERE modality = ? AND user_id = ?
        """, (modality, user_id)).fetchone()

        row = dict(rows)
        stats[modality] = {
            "total_items": row["total_items"] or 0,
            "total_attempts": row["total_attempts"] or 0,
            "total_correct": row["total_correct"] or 0,
            "avg_accuracy": row["avg_accuracy"] or 0.0,
            "mastered_count": row["mastered_count"] or 0,
            "struggling_count": row["struggling_count"] or 0,
        }
    return stats


def _estimate_levels(conn, modality_stats: dict, user_id: int = 1) -> dict:
    """Estimate HSK levels per modality using band-based measurement.

    Walks HSK bands 1-9. A band is "complete" when:
    - Mastery (streak_correct >= 3) >= 80% of items in that band
    - Accuracy >= 75% across attempts in that band

    Level = highest complete band + fractional credit from next band.
    Confidence = min(0.9, total_attempts / 200).
    """
    levels = {}
    for modality, stats in modality_stats.items():
        level = 1.0

        for hsk in range(1, 10):
            row = conn.execute("""
                SELECT
                    COUNT(DISTINCT ci.id) as band_total,
                    COUNT(DISTINCT CASE WHEN p.streak_correct >= 3 THEN ci.id END) as band_mastered,
                    SUM(COALESCE(p.total_attempts, 0)) as band_attempts,
                    SUM(COALESCE(p.total_correct, 0)) as band_correct
                FROM content_item ci
                LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = ? AND p.user_id = ?
                WHERE ci.status = 'drill_ready'
                  AND ci.hsk_level = ?
            """, (modality, user_id, hsk)).fetchone()

            band_total = row["band_total"] or 0
            band_mastered = row["band_mastered"] or 0
            band_attempts = row["band_attempts"] or 0
            band_correct = row["band_correct"] or 0

            if band_total == 0:
                break

            mastery_pct = band_mastered / band_total
            accuracy = band_correct / band_attempts if band_attempts > 0 else 0

            if mastery_pct >= 0.80 and accuracy >= 0.75:
                level = float(hsk)
            else:
                # Fractional credit from partial mastery
                fraction = min(0.9, mastery_pct)
                level = float(hsk - 1) + fraction if hsk > 1 else fraction
                break

        # Confidence based on total attempts
        attempts = stats["total_attempts"]
        # Confidence from sample size (capped at 0.9 to acknowledge model uncertainty)
        confidence = min(0.9, attempts / 200)
        levels[modality] = {
            "level": max(1.0, level),
            "confidence": round(confidence, 2),
            "attempts": attempts,
        }
    return levels


def format_confidence(confidence: float, total_attempts: int = 0) -> str:
    """Format confidence value into an explanatory label.

    Returns human-readable string explaining confidence level and
    how many more sessions are needed to improve it.
    """
    if confidence < 0.05:
        return "no data yet"
    if confidence < 0.15:
        attempts_needed = max(0, 30 - total_attempts)
        sessions_est = max(1, int(attempts_needed / 8))
        return f"very low — ~{sessions_est} more sessions"
    if confidence < 0.3:
        attempts_needed = max(0, 60 - total_attempts)
        sessions_est = max(1, int(attempts_needed / 8))
        return f"low — ~{sessions_est} more sessions"
    if confidence < 0.5:
        return f"moderate ({confidence:.0%})"
    return f"{confidence:.0%}"


def estimate_levels_lite(conn, user_id: int = 1) -> dict:
    """Lightweight live level estimates — no session gate.

    Returns {modality: {"level": float, "confidence": float, "total_attempts": int}}
    Falls back to {level: 1.0, confidence: 0.0, total_attempts: 0} per modality.
    """
    modality_stats = _compute_modality_stats(conn, user_id=user_id)
    if not any(s["total_attempts"] > 0 for s in modality_stats.values()):
        return {
            mod: {"level": 1.0, "confidence": 0.0, "total_attempts": 0}
            for mod in ["reading", "listening", "speaking", "ime"]
        }
    levels = _estimate_levels(conn, modality_stats, user_id=user_id)
    # Attach total_attempts for confidence formatting
    for mod in levels:
        levels[mod]["total_attempts"] = modality_stats.get(mod, {}).get("total_attempts", 0)
    return levels


# ── Bottleneck identification ──────────────────────────────

def _identify_bottlenecks(conn, modality_stats: dict, user_id: int = 1) -> list:
    """Identify top bottlenecks with concrete actions.

    Returns list of dicts: {area, severity, action, test}.
    """
    bottlenecks = []
    error_summary = db.get_error_summary(conn, last_n_sessions=20, user_id=user_id)
    total_errors = sum(error_summary.values()) if error_summary else 0

    # Check each error type
    if error_summary.get("tone", 0) > 0:
        tone_pct = error_summary["tone"] / max(total_errors, 1) * 100
        if tone_pct >= 20:
            bottlenecks.append({
                "area": "Tone accuracy",
                "severity": "high" if tone_pct >= 40 else "medium",
                "action": f"Next 4 sessions: include 2+ tone drills each. Focus on tone pairs (1st vs 4th, 2nd vs 3rd).",
                "test": "Tone error rate drops below 15% within 5 sessions.",
                "data": f"{tone_pct:.0f}% of recent errors are tone errors",
            })

    if error_summary.get("vocab", 0) > 0:
        vocab_pct = error_summary["vocab"] / max(total_errors, 1) * 100
        if vocab_pct >= 30:
            bottlenecks.append({
                "area": "Vocabulary recognition",
                "severity": "high" if vocab_pct >= 50 else "medium",
                "action": "Reduce new items per session from 3 to 1. Let existing vocab consolidate.",
                "test": "Vocab accuracy reaches 75%+ within 4 sessions.",
                "data": f"{vocab_pct:.0f}% of recent errors are vocab misses",
            })

    if error_summary.get("ime_confusable", 0) > 0:
        ime_pct = error_summary["ime_confusable"] / max(total_errors, 1) * 100
        if ime_pct >= 15:
            bottlenecks.append({
                "area": "Typing confusables",
                "severity": "medium",
                "action": "When typing pinyin, pause and say it aloud before hitting enter.",
                "test": "Typing confusable errors drop by half within 5 sessions.",
                "data": f"{ime_pct:.0f}% of recent errors are typing confusables",
            })

    # Check modality imbalances
    for modality, stats in modality_stats.items():
        if stats["total_attempts"] > 20 and stats["avg_accuracy"] < 0.60:
            bottlenecks.append({
                "area": f"{modality.title()} accuracy",
                "severity": "high",
                "action": f"{modality.title()} accuracy at {stats['avg_accuracy']:.0%}. "
                          f"Next 3 sessions should be 50% {modality} drills.",
                "test": f"{modality.title()} accuracy reaches 70%+ within 5 sessions.",
                "data": f"{stats['avg_accuracy']:.0%} accuracy over {stats['total_attempts']} attempts",
            })

    # Check struggling items
    for modality, stats in modality_stats.items():
        if stats["struggling_count"] >= 5:
            bottlenecks.append({
                "area": f"Stuck items ({modality})",
                "severity": "medium",
                "action": f"{stats['struggling_count']} items at 0% accuracy in {modality}. "
                          f"These need focused review.",
                "test": f"At least half of stuck items get 1+ correct within 3 sessions.",
                "data": f"{stats['struggling_count']} items at 0% accuracy",
            })

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    bottlenecks.sort(key=lambda b: severity_order.get(b["severity"], 3))
    return bottlenecks


# ── Velocity and projections ──────────────────────────────

def compute_velocity(sessions: list) -> dict:
    """Compute learning velocity from session history.

    Uses a minimum 7-day window to prevent burst inflation.
    3 sessions in 1 day should not report 21/week.
    """
    if not sessions:
        return {"sessions_per_week": 0, "items_per_session": 0, "confidence": 0.0}

    # Calculate sessions per week from the data
    dates = []
    for s in sessions:
        if s.get("started_at"):
            dates.append(date.fromisoformat(s["started_at"][:10]))

    if len(dates) < 2:
        return {
            "sessions_per_week": len(dates),
            "items_per_session": sessions[0].get("items_completed", 0) if sessions else 0,
            "confidence": 0.1,
        }

    # Winsorized mean of inter-session gaps (trim top/bottom 10%)
    # More robust than simple span division against burst days
    gaps = sorted([(dates[i] - dates[i+1]).days for i in range(len(dates) - 1)])
    if len(gaps) >= 5:
        trim = max(1, len(gaps) // 10)
        trimmed_gaps = gaps[trim:-trim] if trim > 0 else gaps
        avg_gap = sum(trimmed_gaps) / len(trimmed_gaps) if trimmed_gaps else 1
    elif gaps:
        avg_gap = sum(gaps) / len(gaps)
    else:
        avg_gap = 1

    # Minimum gap enforces 7-day window: prevents burst inflation
    # (e.g. 3 sessions in 1 day should not report 21/week)
    avg_gap = max(avg_gap, 7.0 / len(dates))
    sessions_per_week = 7.0 / avg_gap

    # Also compute raw span for other uses
    raw_span = max(1, (dates[0] - dates[-1]).days)

    # Cap: nobody sustains >14 sessions/week
    sessions_per_week = min(sessions_per_week, 14.0)

    avg_items = sum(s.get("items_completed", 0) for s in sessions) / len(sessions)
    avg_correct = sum(s.get("items_correct", 0) for s in sessions) / len(sessions)

    # Confidence based on sample size and recency
    confidence = min(0.9, len(sessions) / 30)
    # Decay for gaps
    if dates:
        days_since = (date.today() - dates[0]).days
        if days_since > 14:
            confidence *= max(0.3, 1 - (days_since - 14) * 0.1)

    # Confidence interval on sessions_per_week (bootstrap-free: use gap std dev)
    import math
    ci_lower = sessions_per_week
    ci_upper = sessions_per_week
    if len(gaps) >= 3:
        mean_gap = sum(gaps) / len(gaps)
        variance = sum((g - mean_gap) ** 2 for g in gaps) / (len(gaps) - 1)
        se_gap = math.sqrt(variance / len(gaps))
        # Delta method: se(7/gap) ≈ 7 * se_gap / gap^2
        gap_lo = max(1.0 / 7, mean_gap - 1.96 * se_gap)
        gap_hi = max(1.0 / 7, mean_gap + 1.96 * se_gap)
        ci_lower = round(min(14.0, 7.0 / gap_hi), 1)
        ci_upper = round(min(14.0, 7.0 / gap_lo), 1)

    return {
        "sessions_per_week": round(sessions_per_week, 1),
        "sessions_per_week_ci": [ci_lower, ci_upper],
        "items_per_session": round(avg_items, 1),
        "correct_per_session": round(avg_correct, 1),
        "confidence": round(confidence, 2),
        "span_days": raw_span,
        "total_in_sample": len(sessions),
    }


def _compute_mastery_rate(conn, user_id: int = 1) -> float:
    """Over the last 20 sessions, count items progressing through mastery stages.
    Returns effective items-mastered per session.

    Counts:
    - Full credit for items at stabilizing/stable/durable (solid progress)
    - Half credit for items at passed_once (early progress)

    This gives realistic rates for beginners who have items progressing
    through the pipeline but haven't yet reached streak >= 3.

    Falls back to a conservative default if insufficient data.
    """
    sessions = db.get_session_history(conn, limit=20, user_id=user_id)
    if len(sessions) < 5:
        return 3.0  # Default: ~3 new items/session introduction rate

    session_ids = [s["id"] for s in sessions]
    placeholders = ",".join("?" * len(session_ids))

    # Count items reviewed in these sessions by mastery stage
    row = conn.execute(f"""
        SELECT
            COUNT(DISTINCT CASE WHEN p.mastery_stage IN ('stabilizing', 'stable', 'durable')
                  THEN p.content_item_id END) as mastered,
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'passed_once'
                  THEN p.content_item_id END) as progressing
        FROM progress p
        WHERE p.user_id = ?
          AND p.content_item_id IN (
              SELECT DISTINCT el.content_item_id FROM error_log el
              WHERE el.session_id IN ({placeholders})
              UNION
              SELECT DISTINCT ci.id FROM content_item ci
              JOIN progress p2 ON ci.id = p2.content_item_id
              WHERE p2.user_id = ? AND p2.last_review_date >= (
                  SELECT date(MIN(started_at)) FROM session_log
                  WHERE id IN ({placeholders}) AND user_id = ?
              )
          )
    """, [user_id] + session_ids + [user_id] + session_ids + [user_id]).fetchone()

    mastered = row["mastered"] or 0
    progressing = row["progressing"] or 0
    effective = mastered + 0.5 * progressing
    n_sessions = len(sessions)

    rate = effective / max(n_sessions, 1)
    return max(1.0, rate)  # Floor at 1.0: even slow learners progress 1 item/session


def _compute_tone_stats(conn, user_id: int = 1) -> dict:
    """Query error_log for tone error counts and recent error rate."""
    total_row = conn.execute("""
        SELECT COUNT(*) as total FROM error_log
        WHERE error_type = 'tone' AND user_id = ?
    """, (user_id,)).fetchone()
    total_tone = total_row["total"] or 0

    recent_row = conn.execute("""
        SELECT
            COUNT(*) as recent_total,
            SUM(CASE WHEN error_type = 'tone' THEN 1 ELSE 0 END) as recent_tone
        FROM error_log
        WHERE user_id = ?
          AND session_id IN (
              SELECT id FROM session_log
              WHERE user_id = ? ORDER BY started_at DESC LIMIT 10
          )
    """, (user_id, user_id)).fetchone()
    recent_total = recent_row["recent_total"] or 0
    recent_tone = recent_row["recent_tone"] or 0
    tone_error_rate = recent_tone / recent_total if recent_total > 0 else 0.0

    return {
        "total_tone_errors": total_tone,
        "recent_total_errors": recent_total,
        "recent_tone_errors": recent_tone,
        "tone_error_rate": round(tone_error_rate, 3),
    }


def _compute_mastery_rate_per_modality(conn, user_id: int = 1) -> dict:
    """Per-modality version of _compute_mastery_rate().

    Returns {modality: mastery_rate_per_session}.
    Uses same mastery-stage-based counting as _compute_mastery_rate.
    """
    sessions = db.get_session_history(conn, limit=20, user_id=user_id)
    n_sessions = max(len(sessions), 1)
    if len(sessions) < 5:
        return {mod: 3.0 for mod in ["reading", "listening", "speaking", "ime"]}

    rates = {}
    for modality in ["reading", "listening", "speaking", "ime"]:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT CASE WHEN p.mastery_stage IN ('stabilizing', 'stable', 'durable')
                      THEN p.content_item_id END) as mastered,
                COUNT(DISTINCT CASE WHEN p.mastery_stage = 'passed_once'
                      THEN p.content_item_id END) as progressing
            FROM progress p
            WHERE p.modality = ? AND p.user_id = ?
              AND p.last_review_date >= (
                  SELECT date(MIN(started_at)) FROM session_log
                  WHERE user_id = ?
                    AND id IN (SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 20)
              )
        """, (modality, user_id, user_id, user_id)).fetchone()
        mastered = row["mastered"] or 0
        progressing = row["progressing"] or 0
        effective = mastered + 0.5 * progressing
        rate = effective / n_sessions
        rates[modality] = max(1.0, rate)

    return rates


def _compute_core_stability(conn, user_id: int = 1) -> dict:
    """Percentage of seen items with mastery_stage IN ('stable', 'durable')."""
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT content_item_id) as total_seen,
            COUNT(DISTINCT CASE WHEN mastery_stage IN ('stable', 'durable') THEN content_item_id END) as stable
        FROM progress
        WHERE total_attempts > 0 AND user_id = ?
    """, (user_id,)).fetchone()
    total_seen = row["total_seen"] or 0
    stable = row["stable"] or 0
    pct = (stable / total_seen * 100) if total_seen > 0 else 0.0

    return {
        "total_seen": total_seen,
        "stable_count": stable,
        "pct": round(pct, 1),
        "description": f"{pct:.0f}% of seen items stable",
    }


def compute_false_mastery_rate(conn, user_id: int = 1) -> dict:
    """System health metric: rate at which mastered items subsequently fail.

    Tracks items that ever reached stable/durable but are now decayed.
    If >10%, mastery threshold is too low (doctrine §2).
    """
    try:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT CASE WHEN mastery_stage IN ('stable', 'durable')
                                      OR stable_since_date IS NOT NULL
                                    THEN content_item_id END) as ever_mastered,
                COUNT(DISTINCT CASE WHEN mastery_stage = 'decayed'
                                      AND stable_since_date IS NOT NULL
                                    THEN content_item_id END) as now_decayed
            FROM progress
            WHERE total_attempts > 0 AND user_id = ?
        """, (user_id,)).fetchone()
    except sqlite3.OperationalError:
        # Fallback for DBs without stable_since_date column
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT CASE WHEN mastery_stage IN ('stable', 'durable')
                                    THEN content_item_id END) as ever_mastered,
                COUNT(DISTINCT CASE WHEN mastery_stage = 'decayed'
                                    THEN content_item_id END) as now_decayed
            FROM progress
            WHERE total_attempts > 0 AND user_id = ?
        """, (user_id,)).fetchone()
    ever_mastered = row["ever_mastered"] or 0
    now_decayed = row["now_decayed"] or 0
    rate = (now_decayed / ever_mastered * 100) if ever_mastered > 0 else 0.0
    healthy = rate <= 10.0

    return {
        "ever_mastered": ever_mastered,
        "now_decayed": now_decayed,
        "false_mastery_pct": round(rate, 1),
        "healthy": healthy,
        "description": (
            f"{rate:.1f}% post-mastery failure rate "
            f"({now_decayed}/{ever_mastered})"
            + ("" if healthy else " — mastery threshold may be too low")
        ),
    }


def compute_graduation_rate(conn, user_id: int = 1, days: int = 30) -> dict:
    """KPI: items graduating to stable per period (Doctrine §12).

    Counts item.graduated events in the last N days.
    """
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM client_event
            WHERE user_id = ? AND event_type = 'item.graduated'
              AND created_at >= datetime('now', ?)
        """, (user_id, f"-{days} days")).fetchone()
        graduated = row["cnt"] if row else 0
    except sqlite3.OperationalError:
        graduated = 0

    total_seen = conn.execute(
        "SELECT COUNT(DISTINCT content_item_id) as cnt FROM progress WHERE total_attempts > 0 AND user_id = ?",
        (user_id,),
    ).fetchone()
    seen = total_seen["cnt"] if total_seen else 0
    rate = (graduated / seen * 100) if seen > 0 else 0.0

    return {
        "graduated_last_period": graduated,
        "period_days": days,
        "total_seen": seen,
        "graduation_rate_pct": round(rate, 1),
        "description": f"{graduated} items graduated in last {days} days ({rate:.1f}% of seen)",
    }


def _projection_confidence_label(vel_conf: float, total_sessions: int) -> str:
    """Confidence label from data volume and velocity confidence."""
    if total_sessions < PACE_RELIABILITY_THRESHOLD:
        return "too_early"
    if vel_conf >= 0.7 and total_sessions >= 25:
        return "good"
    if vel_conf >= 0.4 and total_sessions >= PROJECTION_RANGE_THRESHOLD:
        return "fair"
    if vel_conf >= 0.2:
        return "rough"
    return "low"


def _sessions_to_mastery(vocab_gap: int, mastery_rate: float,
                         current_mastered: int, target_vocab: int,
                         efficiency: float = 0.7) -> int:
    """Estimate sessions to master vocab_gap items.

    Simple linear model: sessions = gap / effective_rate.
    Diminishing returns are already captured in the measured mastery_rate
    (harder items at higher HSK levels naturally lower the measured rate).
    The efficiency parameter creates spread between opt/exp/pess scenarios.

    Floor scales with efficiency so the three scenarios always diverge.
    """
    if vocab_gap <= 0:
        return 0
    # Floor scales with efficiency: opt(0.875)→1.875, exp(0.7)→1.7, pess(0.525)→1.525
    floor = 1.0 + efficiency
    effective_rate = max(mastery_rate * efficiency, floor)
    return max(1, round(vocab_gap / effective_rate))


def project_forecast(conn, user_id: int = 1) -> dict:
    """Full forecast: pace, per-modality projections, aspirational milestones.

    Works at any session count. Gated display:
    - <8 sessions: levels only, no timelines
    - 8-11: single expected values
    - 12+: optimistic/expected/pessimistic ranges
    """
    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions") or 0
    sessions = db.get_session_history(conn, limit=50, user_id=user_id)

    # ── Pace ──
    velocity = compute_velocity(sessions)
    spw = velocity.get("sessions_per_week", 0)
    vel_conf = velocity.get("confidence", 0)
    conf_label = _projection_confidence_label(vel_conf, total_sessions)
    reliable = total_sessions >= PACE_RELIABILITY_THRESHOLD

    # Round display to nearest 0.5 to reduce false precision
    spw_display = round(spw * 2) / 2
    if spw_display == int(spw_display):
        spw_str = f"{int(spw_display)}"
    else:
        spw_str = f"{spw_display:.1f}"

    if not reliable:
        remaining = PACE_RELIABILITY_THRESHOLD - total_sessions
        pace_message = f"Too early to estimate ({remaining} more session{'s' if remaining != 1 else ''} needed)."
    elif conf_label == "rough":
        pace_message = f"~{spw_str} sessions/week (rough estimate)"
    else:
        pace_message = f"~{spw_str} sessions/week ({conf_label})"

    spw_ci = velocity.get("sessions_per_week_ci", [spw, spw])

    pace = {
        "sessions_per_week": round(spw, 1),
        "sessions_per_week_ci": spw_ci,
        "confidence_label": conf_label,
        "reliable": reliable,
        "total_sessions": total_sessions,
        "message": pace_message,
    }

    # ── Modality levels ──
    modality_stats = _compute_modality_stats(conn, user_id=user_id)
    estimated_levels = _estimate_levels(conn, modality_stats, user_id=user_id)
    for mod in estimated_levels:
        estimated_levels[mod]["total_attempts"] = modality_stats.get(mod, {}).get("total_attempts", 0)

    # ── Per-modality projections ──
    mastery_rates = _compute_mastery_rate_per_modality(conn, user_id=user_id)
    mastery_by_hsk = db.get_mastery_by_hsk(conn, user_id=user_id)
    current_mastered = sum(m["mastered"] for m in mastery_by_hsk.values())

    modality_projections = {}
    effective_spw = max(spw, 0.5) if reliable else 4.0  # default assumption

    for modality in ["reading", "listening", "speaking", "ime"]:
        level_data = estimated_levels.get(modality, {"level": 1.0, "confidence": 0.0})
        current_level = level_data["level"]
        mr = mastery_rates.get(modality, 1.5)

        milestones = []
        next_hsk = _next_milestone(current_level)
        if next_hsk is not None and reliable:
            import math
            target_int = min(9, math.ceil(next_hsk))
            # 80% mastery threshold matches _estimate_levels band completion criteria
            target_vocab = int(HSK_CUMULATIVE.get(target_int, target_int * 500) * 0.8)
            vocab_gap = max(0, target_vocab - current_mastered)

            # Diminishing returns model: rate decays as mastered approaches target
            expected_sessions = _sessions_to_mastery(vocab_gap, mr, current_mastered, target_vocab, 0.7)

            if total_sessions >= PROJECTION_RANGE_THRESHOLD:
                optimistic_sessions = _sessions_to_mastery(vocab_gap, mr, current_mastered, target_vocab, 0.875)
                pessimistic_sessions = _sessions_to_mastery(vocab_gap, mr, current_mastered, target_vocab, 0.525)
                sessions_range = {
                    "optimistic": optimistic_sessions,
                    "expected": expected_sessions,
                    "pessimistic": pessimistic_sessions,
                }
                # Use CI-derived pace for calendar range
                spw_hi = max(0.5, spw_ci[1]) if spw_ci[1] > 0 else effective_spw
                spw_lo = max(0.5, spw_ci[0]) if spw_ci[0] > 0 else effective_spw
                calendar_range = {
                    "optimistic": _format_calendar_estimate(optimistic_sessions / spw_hi),
                    "expected": _format_calendar_estimate(expected_sessions / effective_spw),
                    "pessimistic": _format_calendar_estimate(pessimistic_sessions / spw_lo),
                }
            else:
                sessions_range = {"expected": expected_sessions}
                calendar_range = {"expected": _format_calendar_estimate(expected_sessions / effective_spw)}

            milestones.append({
                "target": f"HSK {target_int}",
                "sessions": sessions_range,
                "calendar": calendar_range,
                "confidence_label": conf_label,
                "bottleneck": "vocab",
            })

        modality_projections[modality] = {
            "current_level": round(current_level, 1),
            "milestones": milestones,
        }

    # ── Tone projection ──
    tone_stats = _compute_tone_stats(conn, user_id=user_id)
    tone_proj = {
        "tone_error_rate": tone_stats["tone_error_rate"],
        "target": 0.15,
    }
    if reliable and tone_stats["tone_error_rate"] > 0.15 and tone_stats["recent_total_errors"] > 0:
        # Rough estimate: sessions to halve the error rate
        gap = tone_stats["tone_error_rate"] - 0.15
        sessions_est_expected = max(1, int(gap / 0.02))  # assume ~2% improvement per session
        if total_sessions >= PROJECTION_RANGE_THRESHOLD:
            tone_proj["sessions_est"] = {
                "optimistic": max(1, int(sessions_est_expected * 0.6)),
                "expected": sessions_est_expected,
                "pessimistic": max(1, int(sessions_est_expected * 1.5)),
            }
        else:
            tone_proj["sessions_est"] = {"expected": sessions_est_expected}
        tone_proj["confidence_label"] = conf_label
    modality_projections["tone"] = tone_proj

    # ── Aspirational milestones ──
    core_stability = _compute_core_stability(conn, user_id=user_id)

    aspirational = {}
    if reliable:
        overall_mr = max(sum(mastery_rates.values()) / len(mastery_rates), 0.5)

        for label, hsk_target, target_label in [
            ("casual_media", 4, "4-5"),
            ("professional", 6, "6"),
            ("advanced", 8, "7-8"),
            ("near_native", 9, "9"),
        ]:
            # 80% mastery threshold matches _estimate_levels band completion
            target_vocab = int(HSK_CUMULATIVE.get(hsk_target, hsk_target * 500) * 0.8)
            vocab_gap = max(0, target_vocab - current_mastered)
            expected_sessions = _sessions_to_mastery(vocab_gap, overall_mr, current_mastered, target_vocab, 0.7)

            if total_sessions >= PROJECTION_RANGE_THRESHOLD:
                opt_sessions = _sessions_to_mastery(vocab_gap, overall_mr, current_mastered, target_vocab, 0.875)
                pess_sessions = _sessions_to_mastery(vocab_gap, overall_mr, current_mastered, target_vocab, 0.525)
                sessions_range = {"optimistic": opt_sessions, "expected": expected_sessions, "pessimistic": pess_sessions}
                calendar_range = {
                    "optimistic": _format_calendar_estimate(opt_sessions / effective_spw),
                    "expected": _format_calendar_estimate(expected_sessions / effective_spw),
                    "pessimistic": _format_calendar_estimate(pess_sessions / effective_spw),
                }
            else:
                sessions_range = {"expected": expected_sessions}
                calendar_range = {"expected": _format_calendar_estimate(expected_sessions / effective_spw)}

            aspirational[label] = {
                "hsk_target": target_label,
                "sessions": sessions_range,
                "calendar": calendar_range,
                "confidence": conf_label,
            }

    aspirational["core_stability"] = core_stability

    # ── Retention stats (from half-life model) ──
    try:
        from .retention import compute_retention_stats
        ret = compute_retention_stats(conn, user_id=user_id)
        retention = ret if ret["total_items"] > 0 else None
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.warning("Retention stats unavailable for forecast: %s", e)
        retention = None

    return {
        "pace": pace,
        "modality_projections": modality_projections,
        "estimated_levels": estimated_levels,
        "aspirational": aspirational,
        "retention": retention,
        "total_sessions": total_sessions,
    }


def _project_milestones(conn, levels: dict, velocity: dict, user_id: int = 1) -> list:
    """Project when HSK milestones will be reached using multi-criteria assessment.

    Criteria per milestone:
    - Vocab: mastered word count vs HSK_CUMULATIVE target
    - Grammar: grammar_points covered at target level
    - Listening: listening modality accuracy >= 75%
    - Reading: reading modality accuracy >= 80%
    - Speaking (HSK 3+): intuition accuracy >= 60%

    Each projection identifies which criterion is the bottleneck.
    """
    projections = []
    spw = velocity.get("sessions_per_week", 4)
    if spw <= 0:
        spw = 4

    conf = velocity.get("confidence", 0)
    if conf >= 0.7:
        confidence_label = "good"
    elif conf >= 0.4:
        confidence_label = "fair"
    elif conf >= 0.2:
        confidence_label = "rough estimate"
    else:
        confidence_label = "insufficient data — treat as very rough"

    mastery_rate = _compute_mastery_rate(conn, user_id=user_id)
    mastery_by_hsk = db.get_mastery_by_hsk(conn, user_id=user_id)
    current_mastered = sum(m["mastered"] for m in mastery_by_hsk.values())

    # Get grammar coverage per level
    grammar_by_level = {}
    grammar_rows = conn.execute("""
        SELECT hsk_level, COUNT(*) as total FROM grammar_point
        GROUP BY hsk_level
    """).fetchall()
    for r in grammar_rows:
        grammar_by_level[r["hsk_level"]] = r["total"]

    # Compute a single overall next milestone (not per-modality)
    avg_level = sum(d["level"] for d in levels.values()) / max(len(levels), 1)
    next_level = _next_milestone(avg_level)
    if next_level is None:
        return projections

    target_int = min(9, int(next_level))
    target_vocab = HSK_CUMULATIVE.get(target_int, target_int * 500)

    # 1. Vocab criterion
    max(0, target_vocab - current_mastered)
    vocab_pct = min(100, (current_mastered / target_vocab * 100) if target_vocab > 0 else 100)

    # 2. Grammar criterion
    grammar_total = sum(grammar_by_level.get(l, 0) for l in range(1, target_int + 1))
    grammar_row = conn.execute("""
        SELECT COUNT(DISTINCT cg.grammar_point_id) FROM content_grammar cg
        JOIN grammar_point gp ON gp.id = cg.grammar_point_id
        JOIN progress p ON p.content_item_id = cg.content_item_id
        WHERE gp.hsk_level <= ? AND p.streak_correct >= 2 AND p.user_id = ?
    """, (target_int, user_id)).fetchone()
    grammar_linked = (grammar_row[0] if grammar_row else 0) or 0
    grammar_pct = min(100, (grammar_linked / grammar_total * 100) if grammar_total > 0 else 100)

    # Load accuracy targets from HSK requirements registry
    hsk_reqs = get_hsk_requirements(target_int)
    listening_target = hsk_reqs.get("listening", {}).get("accuracy_target", 0.75)
    reading_target = hsk_reqs.get("reading", {}).get("accuracy_target", 0.80)

    # 3. Listening criterion (accuracy at target level)
    listen_row = conn.execute("""
        SELECT SUM(p.total_correct) as correct, SUM(p.total_attempts) as attempts
        FROM progress p JOIN content_item ci ON p.content_item_id = ci.id
        WHERE p.modality = 'listening' AND ci.hsk_level <= ? AND p.user_id = ?
    """, (target_int, user_id)).fetchone()
    listen_attempts = (listen_row["attempts"] or 0) if listen_row else 0
    listen_correct = (listen_row["correct"] or 0) if listen_row else 0
    listen_pct = min(100, (listen_correct / listen_attempts * 100) if listen_attempts > 0 else 0)

    # 4. Reading criterion
    read_row = conn.execute("""
        SELECT SUM(p.total_correct) as correct, SUM(p.total_attempts) as attempts
        FROM progress p JOIN content_item ci ON p.content_item_id = ci.id
        WHERE p.modality = 'reading' AND ci.hsk_level <= ? AND p.user_id = ?
    """, (target_int, user_id)).fetchone()
    read_attempts = (read_row["attempts"] or 0) if read_row else 0
    read_correct = (read_row["correct"] or 0) if read_row else 0
    read_pct = min(100, (read_correct / read_attempts * 100) if read_attempts > 0 else 0)

    # 5. Speaking criterion (HSK 3+ only, using intuition as proxy)
    speak_pct = 100.0  # not required below HSK 3
    if target_int >= 3:
        speak_row = conn.execute("""
            SELECT SUM(intuition_correct) as correct, SUM(intuition_attempts) as attempts
            FROM progress WHERE intuition_attempts > 0 AND user_id = ?
        """, (user_id,)).fetchone()
        speak_attempts = (speak_row["attempts"] or 0) if speak_row else 0
        speak_correct = (speak_row["correct"] or 0) if speak_row else 0
        speak_pct = min(100, (speak_correct / speak_attempts * 100) if speak_attempts > 0 else 0)

    # Build criteria list
    criteria = {
        "vocab": {"pct": round(vocab_pct, 1), "target": f"{target_vocab} words",
                  "current": f"{current_mastered}", "met": vocab_pct >= 80},
        "grammar": {"pct": round(grammar_pct, 1), "target": f"{grammar_total} points",
                    "current": f"{grammar_linked}", "met": grammar_pct >= 60 or grammar_total == 0},
        "listening": {"pct": round(listen_pct, 1), "target": f"{listening_target:.0%} accuracy",
                      "current": f"{listen_pct:.0f}%",
                      "met": listen_pct >= listening_target * 100 or listen_attempts < 5},
        "reading": {"pct": round(read_pct, 1), "target": f"{reading_target:.0%} accuracy",
                    "current": f"{read_pct:.0f}%",
                    "met": read_pct >= reading_target * 100 or read_attempts < 5},
    }
    if target_int >= 3:
        criteria["speaking"] = {
            "pct": round(speak_pct, 1), "target": "60% intuition",
            "current": f"{speak_pct:.0f}%", "met": speak_pct >= 60 or speak_attempts < 5,
        }

    # Identify bottleneck (lowest completion %)
    bottleneck = min(criteria, key=lambda k: criteria[k]["pct"])

    # Session estimate: 80% mastery threshold matches _estimate_levels
    mastery_target = int(target_vocab * 0.8)
    mastery_gap = max(0, mastery_target - current_mastered)
    sessions_needed = _sessions_to_mastery(mastery_gap, mastery_rate, current_mastered, mastery_target, 0.7)
    weeks_needed = sessions_needed / max(spw, 0.5)
    target_date = date.today() + timedelta(weeks=weeks_needed)

    projections.append({
        "current": round(avg_level, 1),
        "target": next_level,
        "target_int": target_int,
        "sessions_needed": sessions_needed,
        "weeks_needed": round(weeks_needed, 1),
        "target_date": target_date.isoformat(),
        "calendar": _format_calendar_estimate(weeks_needed),
        "confidence": confidence_label,
        "criteria": criteria,
        "bottleneck": bottleneck,
    })

    return projections


def _next_milestone(current: float) -> float:
    """Next meaningful HSK milestone from current level."""
    milestones = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    for m in milestones:
        if m > current:
            return m
    return None


def _format_calendar_estimate(weeks: float) -> str:
    """Format weeks into a readable calendar estimate."""
    if weeks <= 2:
        return f"~{int(weeks * 7)} days"
    elif weeks <= 8:
        return f"~{int(weeks)} weeks"
    elif weeks <= 52:
        months = weeks / 4.3
        return f"~{months:.0f} months"
    else:
        years = weeks / 52
        return f"~{years:.1f} years"


# ── Engagement and trends ──────────────────────────────

def _compute_engagement_trends(conn, sessions: list) -> dict:
    """Compute engagement trends: boredom flags, early exits, session length."""
    if not sessions:
        return {}

    recent = sessions[:10]
    older = sessions[10:20] if len(sessions) > 10 else []

    recent_boredom = sum(s.get("boredom_flags", 0) for s in recent)
    recent_exits = sum(1 for s in recent if s.get("early_exit"))
    recent_duration = [s.get("duration_seconds", 0) for s in recent if s.get("duration_seconds")]

    older_boredom = sum(s.get("boredom_flags", 0) for s in older) if older else 0
    older_exits = sum(1 for s in older if s.get("early_exit")) if older else 0

    return {
        "recent_boredom_flags": recent_boredom,
        "recent_early_exits": recent_exits,
        "avg_duration_seconds": sum(recent_duration) / len(recent_duration) if recent_duration else 0,
        "boredom_trending_up": recent_boredom > older_boredom * 1.5 if older_boredom else recent_boredom > 2,
        "exits_trending_up": recent_exits > older_exits * 1.5 if older_exits else recent_exits > 2,
    }


def _bonferroni_z(alpha: float, n_tests: int) -> float:
    """Bonferroni-corrected z-threshold for multiple simultaneous tests."""
    try:
        from scipy.stats import norm
        return norm.ppf(1 - alpha / (2 * n_tests))
    except ImportError:
        # Fallback: approximate for common test counts
        # alpha/n -> z: 6 tests -> 2.64, 8 tests -> 2.73, 10 tests -> 2.81
        adjusted_alpha = alpha / n_tests
        # Rational approximation (Abramowitz & Stegun)
        import math
        p = 1 - adjusted_alpha / 2
        t = math.sqrt(-2 * math.log(1 - p))
        return t - (2.515517 + 0.802853*t + 0.010328*t*t) / (1 + 1.432788*t + 0.189269*t*t + 0.001308*t*t*t)


def _compute_error_trends(conn, user_id: int = 1) -> dict:
    """Compare error patterns between recent and older sessions."""
    recent_errors = conn.execute("""
        SELECT error_type, COUNT(*) as count FROM error_log
        WHERE user_id = ?
          AND session_id IN (
              SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 10
          )
        GROUP BY error_type
    """, (user_id, user_id)).fetchall()

    older_errors = conn.execute("""
        SELECT error_type, COUNT(*) as count FROM error_log
        WHERE user_id = ?
          AND session_id IN (
              SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 20 OFFSET 10
          )
        GROUP BY error_type
    """, (user_id, user_id)).fetchall()

    recent = {r["error_type"]: r["count"] for r in recent_errors}
    older = {r["error_type"]: r["count"] for r in older_errors}

    trends = {}
    all_types = set(list(recent.keys()) + list(older.keys()))
    for etype in all_types:
        r = recent.get(etype, 0)
        o = older.get(etype, 0)
        if o > 0:
            change = (r - o) / o
            # Binomial significance test: is the change statistically meaningful?
            total = r + o
            p_null = 0.5  # Under null: equal split between periods
            observed_p = r / total if total > 0 else 0.5
            significant = False
            if total >= 5:
                import math
                se = math.sqrt(p_null * (1 - p_null) / total)
                z = abs(observed_p - p_null) / se if se > 0 else 0
                # Bonferroni correction: divide alpha by number of simultaneous tests
                n_tests = max(len(all_types), 1)
                z_threshold = 1.96 if n_tests <= 1 else _bonferroni_z(0.05, n_tests)
                significant = z >= z_threshold
            direction = "stable"
            if significant:
                direction = "improving" if change < -0.2 else "worsening" if change > 0.2 else "stable"
            elif abs(change) > 0.2:
                direction = "possibly_improving" if change < 0 else "possibly_worsening"
            trends[etype] = {
                "recent": r, "older": o,
                "direction": direction,
                "significant": significant,
            }
        else:
            trends[etype] = {"recent": r, "older": o, "direction": "new" if r > 0 else "none", "significant": False}

    return trends


def _check_core_coverage(conn, user_id: int = 1) -> dict:
    """Check coverage of low-affinity but required domains.

    Returns status per core domain.
    """
    # Check items tagged with low-affinity content lenses
    core_lenses = [
        "time_sequence", "numbers_measure", "function_words",
    ]

    coverage = {}
    for lens in core_lenses:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN times_shown > 0 THEN 1 ELSE 0 END) as seen,
                SUM(CASE WHEN times_correct > 0 THEN 1 ELSE 0 END) as correct_once
            FROM content_item WHERE content_lens = ?
        """, (lens,)).fetchone()

        total = row["total"] or 0
        seen = row["seen"] or 0
        coverage[lens] = {
            "total": total,
            "seen": seen,
            "coverage_pct": (seen / total * 100) if total > 0 else 0,
            "needs_attention": total > 0 and (seen / total) < 0.5,
        }

    return coverage


# ── Calibrate ──────────────────────────────

def plan_calibrate_session(conn, user_id: int = 1) -> SessionPlan:
    """Plan a 20-item calibration session across all modalities and HSK levels.

    Distinct from assess (which analyzes history) — calibrate is an active test.
    Samples items from multiple HSK levels to find the learner's boundaries.
    """
    drills = []
    seen_ids = set()

    # Drill type per modality for calibration
    modality_drill = {
        "reading": "mc",
        "ime": "ime_type",
        "listening": "listening_gist",
    }

    # Sample 5 items per modality, spread across HSK levels
    for modality, drill_type in modality_drill.items():
        # Try to get items at varying difficulty: HSK 1, 2, 3+
        for hsk_target in range(1, 10):
            rows = conn.execute("""
                SELECT ci.* FROM content_item ci
                WHERE ci.status = 'drill_ready'
                  AND ci.review_status = 'approved'
                  AND ci.is_mined_out = 0
                  AND ci.hsk_level = ?
                ORDER BY RANDOM() LIMIT 3
            """, (hsk_target,)).fetchall()

            for row in rows:
                if len([d for d in drills if d.modality == modality]) >= 5:
                    break
                item = dict(row)
                if item["id"] in seen_ids:
                    continue
                if not _item_is_drillable(item, drill_type):
                    continue
                seen_ids.add(item["id"])
                drills.append(DrillItem(
                    content_item_id=item["id"],
                    hanzi=item["hanzi"],
                    pinyin=item["pinyin"],
                    english=item["english"],
                    modality=modality,
                    drill_type=drill_type,
                ))

    # Add 5 tone drills spread across levels
    for hsk_target in range(1, 10):
        rows = conn.execute("""
            SELECT ci.* FROM content_item ci
            WHERE ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
              AND ci.is_mined_out = 0
              AND ci.hsk_level = ?
              AND ci.pinyin != ''
            ORDER BY RANDOM() LIMIT 2
        """, (hsk_target,)).fetchall()
        for row in rows:
            if len([d for d in drills if d.drill_type == "tone"]) >= 5:
                break
            item = dict(row)
            if item["id"] in seen_ids:
                continue
            if not _item_is_drillable(item, "tone"):
                continue
            seen_ids.add(item["id"])
            drills.append(DrillItem(
                content_item_id=item["id"],
                hanzi=item["hanzi"],
                pinyin=item["pinyin"],
                english=item["english"],
                modality="reading",
                drill_type="tone",
            ))

    random.shuffle(drills)

    return SessionPlan(
        session_type="calibrate",
        drills=drills,
        micro_plan=f"Calibration: {len(drills)} items across modalities & levels",
        estimated_seconds=len(drills) * 30,
    )


def update_calibration_levels(conn, results: list, user_id: int = 1):
    """Update learner_profile level estimates from calibration results.

    Groups results by modality, computes accuracy per HSK level,
    and estimates the highest level where accuracy ≥ 70%.
    """
    # Group results by modality
    modality_results = {}
    for r in results:
        if r.skipped:
            continue
        # Look up the item's HSK level
        row = conn.execute(
            "SELECT hsk_level FROM content_item WHERE id = ?",
            (r.content_item_id,)
        ).fetchone()
        hsk = row["hsk_level"] if row and row["hsk_level"] else 1
        modality_results.setdefault(r.modality, []).append({
            "hsk": hsk, "correct": r.correct,
        })

    for modality, items in modality_results.items():
        # Group by HSK level
        by_hsk = {}
        for item in items:
            by_hsk.setdefault(item["hsk"], []).append(item["correct"])

        # Find highest level with ≥70% accuracy
        best_level = 1.0
        for hsk_level in sorted(by_hsk.keys()):
            attempts = by_hsk[hsk_level]
            accuracy = sum(attempts) / len(attempts)
            if accuracy >= 0.70:
                best_level = float(hsk_level)

        # Higher confidence from calibration than from passive tracking
        confidence = min(0.8, len(items) / 8)

        if modality not in {"reading", "listening", "speaking", "ime"}:
            continue
        level_col = f"level_{modality}"
        conf_col = f"confidence_{modality}"
        conn.execute(f"""
            UPDATE learner_profile SET
                {level_col} = ?, {conf_col} = ?, updated_at = datetime('now')
            WHERE user_id = ?
        """, (best_level, confidence, user_id))

    conn.commit()


# ── North star: readiness assessment ──────────────────────

def get_tone_confusion_matrix(conn, user_id: int = 1) -> dict:
    """Analyze tone errors to build a perceptual confusion matrix.

    Queries error_log for tone errors where user_answer and expected_answer
    contain tone numbers (1-4). Returns:
    {
        "matrix": {expected_tone: {guessed_tone: count}},
        "top_confusions": [(expected, guessed, count), ...],
        "total_tone_errors": int,
        "summary": str,
    }
    """
    rows = conn.execute("""
        SELECT user_answer, expected_answer FROM error_log
        WHERE error_type = 'tone' AND user_answer IS NOT NULL AND expected_answer IS NOT NULL
          AND user_id = ?
    """, (user_id,)).fetchall()

    matrix = {t: {g: 0 for g in range(1, 6)} for t in range(1, 6)}
    tone_num_pat = re.compile(r'[1-5]')

    # Map diacritical tone marks to tone numbers
    _TONE_MARK_MAP = {
        'ā': 1, 'á': 2, 'ǎ': 3, 'à': 4,
        'ē': 1, 'é': 2, 'ě': 3, 'è': 4,
        'ī': 1, 'í': 2, 'ǐ': 3, 'ì': 4,
        'ō': 1, 'ó': 2, 'ǒ': 3, 'ò': 4,
        'ū': 1, 'ú': 2, 'ǔ': 3, 'ù': 4,
        'ǖ': 1, 'ǘ': 2, 'ǚ': 3, 'ǜ': 4,
    }

    def _extract_tones(pinyin_str: str) -> list:
        """Extract tone numbers from pinyin, handling both diacritics and numbers."""
        # First try tone numbers (ma1, ma2)
        nums = tone_num_pat.findall(pinyin_str)
        if nums:
            return [int(n) for n in nums]
        # Fall back to diacritical marks
        tones = []
        # Split into syllables by spaces or transitions
        syllable_tones = []
        current_tone = 5  # neutral/default
        for ch in pinyin_str:
            if ch in _TONE_MARK_MAP:
                current_tone = _TONE_MARK_MAP[ch]
            elif ch == ' ' or ch == "'" or (ch.isalpha() and current_tone != 5 and ch in 'bpmfdtnlgkhjqxzcsryw'):
                if current_tone != 5:
                    syllable_tones.append(current_tone)
                    current_tone = 5
        if current_tone != 5:
            syllable_tones.append(current_tone)
        return syllable_tones if syllable_tones else tones

    for r in rows:
        user = r["user_answer"] or ""
        expected = r["expected_answer"] or ""
        user_tones = _extract_tones(user)
        expected_tones = _extract_tones(expected)

        # Match tone-by-tone where lengths match
        for et, ut in zip(expected_tones, user_tones, strict=False):
            ei, ui = int(et), int(ut)
            if ei != ui:
                matrix[ei][ui] += 1

    # Flatten to top confusions
    confusions = []
    for expected_t in range(1, 6):
        for guessed_t in range(1, 6):
            if expected_t != guessed_t and matrix[expected_t][guessed_t] > 0:
                confusions.append((expected_t, guessed_t, matrix[expected_t][guessed_t]))
    confusions.sort(key=lambda x: x[2], reverse=True)

    total = sum(c[2] for c in confusions)

    if confusions:
        top = confusions[0]
        summary = f"Most confused: tone {top[0]} heard as tone {top[1]} ({top[2]} times)"
    else:
        summary = "No tone confusion data yet"

    return {
        "matrix": matrix,
        "top_confusions": confusions[:5],
        "total_tone_errors": total,
        "summary": summary,
    }


def get_error_pattern_analysis(conn, user_id: int = 1) -> dict:
    """Identify systematic error patterns across items using error_shape_summary.

    Detects recurring patterns like "all tone errors are tone 2→3" or
    "visual confusion clusters on characters with shared radicals."

    Returns:
        {
            "tone_patterns": [{"pattern": "tone_2_as_3", "count": 12, "items": [...]}],
            "phonetic_patterns": [{"pattern": "phonetic_similar", "count": N}],
            "top_shapes": [{"shape": str, "count": int, "items": int}],
            "top_pattern": str or None,
            "total_active_shapes": int,
            "interference_pairs": int,
            "summary": str,
        }
    """
    result = {
        "tone_patterns": [],
        "phonetic_patterns": [],
        "top_shapes": [],
        "top_pattern": None,
        "total_active_shapes": 0,
        "interference_pairs": 0,
        "summary": "No error shape data yet",
    }

    try:
        # Aggregate unresolved error shapes
        shapes = conn.execute("""
            SELECT error_shape, SUM(occurrence_count) as total,
                   COUNT(DISTINCT content_item_id) as item_count
            FROM error_shape_summary
            WHERE user_id = ? AND resolved = 0
            GROUP BY error_shape
            ORDER BY total DESC
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        return result

    if not shapes:
        return result

    tone_re = re.compile(r'^tone_(\d)_as_(\d)$')
    tone_patterns = []
    top_shapes = []

    for row in shapes:
        shape = row["error_shape"]
        total = row["total"]
        items = row["item_count"]
        top_shapes.append({"shape": shape, "count": total, "items": items})

        m = tone_re.match(shape)
        if m:
            tone_patterns.append({
                "pattern": shape,
                "expected_tone": int(m.group(1)),
                "guessed_tone": int(m.group(2)),
                "count": total,
                "items": items,
            })

    # Count phonetic patterns
    phonetic_shapes = [s for s in top_shapes if "phonetic" in s["shape"]]

    # Count active interference pairs
    try:
        pair_count = conn.execute("""
            SELECT COUNT(*) as cnt FROM interference_pairs
            WHERE interference_strength IN ('high', 'medium')
        """).fetchone()["cnt"]
    except (sqlite3.OperationalError, TypeError):
        pair_count = 0

    total_active = sum(s["count"] for s in top_shapes)
    top_pattern = top_shapes[0]["shape"] if top_shapes else None

    if tone_patterns:
        top_tone = tone_patterns[0]
        summary = (f"Top error pattern: tone {top_tone['expected_tone']}→"
                   f"{top_tone['guessed_tone']} ({top_tone['count']} errors across "
                   f"{top_tone['items']} items)")
    elif top_shapes:
        summary = f"Top error pattern: {top_shapes[0]['shape']} ({top_shapes[0]['count']} errors)"
    else:
        summary = "No error shape data yet"

    result.update({
        "tone_patterns": sorted(tone_patterns, key=lambda x: x["count"], reverse=True),
        "phonetic_patterns": phonetic_shapes,
        "top_shapes": top_shapes[:10],
        "top_pattern": top_pattern,
        "total_active_shapes": total_active,
        "interference_pairs": pair_count,
        "summary": summary,
    })
    return result


def get_speed_trend(conn, modality: str = None, user_id: int = 1) -> dict:
    """Analyze response time trends from progress.avg_response_ms.

    Returns:
    {
        "avg_ms": float or None,
        "fast_count": int,    # items with avg < 3000ms
        "slow_count": int,    # items with avg > 8000ms
        "total_timed": int,
        "by_hsk": {level: avg_ms},
        "summary": str,
    }
    """
    where = "WHERE p.avg_response_ms IS NOT NULL AND p.total_attempts > 0 AND p.user_id = ?"
    params = [user_id]
    if modality:
        where += " AND p.modality = ?"
        params.append(modality)

    row = conn.execute(f"""
        SELECT
            AVG(p.avg_response_ms) as avg_ms,
            COUNT(*) as total_timed,
            SUM(CASE WHEN p.avg_response_ms < 3000 THEN 1 ELSE 0 END) as fast_count,
            SUM(CASE WHEN p.avg_response_ms > 8000 THEN 1 ELSE 0 END) as slow_count
        FROM progress p
        {where}
    """, params).fetchone()

    avg_ms = row["avg_ms"]
    total_timed = row["total_timed"] or 0
    fast_count = row["fast_count"] or 0
    slow_count = row["slow_count"] or 0

    # By HSK level
    by_hsk = {}
    hsk_rows = conn.execute(f"""
        SELECT ci.hsk_level, AVG(p.avg_response_ms) as avg_ms
        FROM progress p
        JOIN content_item ci ON p.content_item_id = ci.id
        {where} AND ci.hsk_level IS NOT NULL
        GROUP BY ci.hsk_level
        ORDER BY ci.hsk_level
    """, params).fetchall()
    for r in hsk_rows:
        by_hsk[r["hsk_level"]] = round(r["avg_ms"])

    if total_timed == 0:
        summary = "No response time data yet"
    elif avg_ms and avg_ms < 4000:
        summary = f"Fast average: {avg_ms:.0f}ms — good automaticity"
    elif avg_ms and avg_ms < 7000:
        summary = f"Moderate: {avg_ms:.0f}ms — processing speed developing"
    else:
        summary = f"Slow: {avg_ms:.0f}ms — still translating, not yet automatic"

    return {
        "avg_ms": round(avg_ms) if avg_ms else None,
        "fast_count": fast_count,
        "slow_count": slow_count,
        "total_timed": total_timed,
        "by_hsk": by_hsk,
        "summary": summary,
    }


def compute_ambiguity_comfort(conn, user_id: int = 1) -> dict:
    """Measure how comfortably the learner handles uncertainty.

    Tracks:
    - "unknown" confidence rate (admitted uncertainty — positive signal)
    - "narrowed" usage (needed scaffolding)
    - Skip rate (avoidance — negative signal)

    Returns:
    {
        "unknown_count": int,
        "narrowed_count": int,
        "total_attempts": int,
        "unknown_rate": float,
        "comfort_label": str,
        "summary": str,
    }
    """
    row = conn.execute("""
        SELECT
            SUM(total_attempts) as total,
            COUNT(*) as items_with_progress
        FROM progress
        WHERE total_attempts > 0 AND user_id = ?
    """, (user_id,)).fetchone()
    total = row["total"] or 0

    # Count narrowed and unknown from session data
    # These are tracked via confidence parameter in record_attempt
    # We don't store confidence per-attempt, but we can check error_log patterns
    # and progress streaks. For now, count items where streak was broken (implies
    # learner encountered difficulty and kept going)
    resilience_row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) as bounced_back
        FROM progress
        WHERE weak_cycle_count >= 1 AND total_attempts >= 5 AND user_id = ?
    """, (user_id,)).fetchone()
    bounced = resilience_row["bounced_back"] or 0

    # Items attempted despite being hard (historically_weak but still practiced)
    persistence_row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) as persistent
        FROM progress
        WHERE historically_weak = 1 AND total_attempts >= 8 AND user_id = ?
    """, (user_id,)).fetchone()
    persistent = persistence_row["persistent"] or 0

    # Variety of drill types encountered (willingness to try different formats)
    variety_row = conn.execute("""
        SELECT AVG(
            LENGTH(drill_types_seen) - LENGTH(REPLACE(drill_types_seen, ',', '')) + 1
        ) as avg_types
        FROM progress
        WHERE drill_types_seen != '' AND total_attempts > 0 AND user_id = ?
    """, (user_id,)).fetchone()
    avg_types = variety_row["avg_types"] or 0

    # Compute comfort score (0-100)
    if total == 0:
        return {
            "bounced_back": 0,
            "persistent_items": 0,
            "avg_drill_types": 0,
            "total_attempts": 0,
            "comfort_score": 0,
            "comfort_label": "No data yet",
            "summary": "Ambiguity comfort appears after more sessions.",
        }

    # Score components:
    # - Bounce-back items: recovered from weak cycles (max 40 pts)
    bounce_score = min(40, bounced * 10)
    # - Persistence with hard items (max 30 pts)
    persist_score = min(30, persistent * 15)
    # - Drill type variety (max 30 pts)
    variety_score = min(30, avg_types * 15)

    comfort_score = bounce_score + persist_score + variety_score

    if comfort_score >= 60:
        label = "Comfortable with difficulty"
        summary = "You engage with hard items instead of avoiding them."
    elif comfort_score >= 30:
        label = "Building tolerance"
        summary = "You're starting to stick with difficult items."
    elif total >= 50:
        label = "Needs more challenge"
        summary = "Try harder items — getting things wrong is how you learn."
    else:
        label = "Too early to tell"
        summary = "Keep practicing — comfort with difficulty comes with exposure."

    return {
        "bounced_back": bounced,
        "persistent_items": persistent,
        "avg_drill_types": round(avg_types, 1),
        "total_attempts": total,
        "comfort_score": round(comfort_score, 1),
        "comfort_label": label,
        "summary": summary,
    }


def compute_readiness(conn, user_id: int = 1) -> dict:
    """Compute a composite "real-world readiness" score.

    Combines:
    - Scenario mastery (40%): avg dialogue scores across attempted scenarios
    - Item stability (30%): % of seen items at improving or stable
    - Modality breadth (20%): how many modalities have meaningful data
    - Practice consistency (10%): cadence regularity

    Returns:
        {
            "score": 0-100,
            "components": {name: {score, weight, detail}},
            "focus": str,  # single most impactful next action
            "label": str,  # human-readable readiness label
        }
    """
    from .milestones import get_stage_counts

    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions", 0) or 0

    # ── Component 1: Scenario mastery (40%) ──
    scenario_rows = conn.execute("""
        SELECT avg_score, times_presented
        FROM dialogue_scenario WHERE times_presented > 0
    """).fetchall()
    if scenario_rows:
        scenario_avg = sum(r["avg_score"] or 0 for r in scenario_rows) / len(scenario_rows)
        scenario_score = min(100, scenario_avg * 100)
    else:
        scenario_score = 0.0
    scenario_detail = (f"{len(scenario_rows)} scenarios attempted"
                       if scenario_rows else "no scenarios attempted yet")

    # ── Component 2: Item stability (30%) ──
    stages = get_stage_counts(conn)
    solid = stages["stable"] + stages["durable"]
    growing = stages["stabilizing"]
    early = stages["seen"] + stages["passed_once"]
    needs_review = stages["decayed"]
    seen = solid + growing + early + needs_review
    if seen > 0:
        stability_score = (growing + solid) / seen * 100
    else:
        stability_score = 0.0
    stability_detail = (f"{growing + solid}/{seen} items stabilizing or solid"
                        if seen > 0 else "no items attempted yet")

    # ── Component 3: Modality breadth (20%) ──
    modality_stats = _compute_modality_stats(conn, user_id=user_id)
    active_modalities = sum(
        1 for m in ["reading", "listening", "speaking", "ime"]
        if modality_stats.get(m, {}).get("total_attempts", 0) >= 5
    )
    breadth_score = active_modalities / 4 * 100
    breadth_detail = f"{active_modalities}/4 modalities active"

    # ── Component 4: Practice consistency (10%) ──
    sessions = db.get_session_history(conn, limit=14, user_id=user_id)
    completed = [s for s in sessions if (s.get("items_completed") or 0) > 0]
    if len(completed) >= 2:
        velocity = compute_velocity(sessions)
        spw = velocity.get("sessions_per_week", 0)
        consistency_score = min(100, spw / 5 * 100)  # 5x/week = 100%
    else:
        consistency_score = 0.0
        spw = 0
    if spw > 0:
        # Round to nearest 0.5 — no false precision
        spw_rounded = round(spw * 2) / 2
        if spw_rounded == int(spw_rounded):
            consistency_detail = f"~{int(spw_rounded)} sessions/week"
        else:
            consistency_detail = f"~{spw_rounded:.1f} sessions/week"
    else:
        consistency_detail = "not enough data"

    # ── Composite ──
    score = (
        scenario_score * 0.40 +
        stability_score * 0.30 +
        breadth_score * 0.20 +
        consistency_score * 0.10
    )

    # ── Determine focus ──
    weakest = min(
        [("Scenario practice", scenario_score),
         ("Item stability", stability_score),
         ("Modality breadth", breadth_score),
         ("Practice consistency", consistency_score)],
        key=lambda x: x[1],
    )

    focus_actions = {
        "Scenario practice": "Try a dialogue scenario — they build real-world skills.",
        "Item stability": "Keep reviewing — items need repetition to solidify.",
        "Modality breadth": "Listening or typing drills would broaden coverage.",
        "Practice consistency": "Aim for one more session this week.",
    }
    focus = focus_actions[weakest[0]]

    # ── Label ──
    if score >= 75:
        label = "Strong foundation"
    elif score >= 50:
        label = "Making progress"
    elif score >= 25:
        label = "Building up"
    elif total_sessions > 0:
        label = "Just getting started"
    else:
        label = "Ready to begin"

    return {
        "score": round(score, 1),
        "label": label,
        "focus": focus,
        "components": {
            "scenario_mastery": {"score": round(scenario_score, 1), "weight": 0.40, "detail": scenario_detail},
            "item_stability": {"score": round(stability_score, 1), "weight": 0.30, "detail": stability_detail},
            "modality_breadth": {"score": round(breadth_score, 1), "weight": 0.20, "detail": breadth_detail},
            "practice_consistency": {"score": round(consistency_score, 1), "weight": 0.10, "detail": consistency_detail},
        },
        "total_sessions": total_sessions,
    }


# ── Queue Saturation Forecast ──────────────────────────────

def queue_saturation_forecast(conn: sqlite3.Connection, user_id: int = 1,
                               session_length: int = 12) -> dict:
    """Predict sessions until review queue overflows.

    Model:
      arrival_rate = new items introduced per session (from session_log)
      service_rate = items graduating to stable per session
      overflow = items_due > 2 * session_length

    Returns dict with arrival_rate, service_rate, current_due,
    sessions_until_overflow, status.
    """
    # Arrival rate: new items introduced per session (last 30 sessions)
    try:
        rows = conn.execute("""
            SELECT sl.id AS session_id,
                   COUNT(DISTINCT p.content_item_id) AS new_items
            FROM session_log sl
            LEFT JOIN progress p ON p.user_id = sl.user_id
                AND p.repetitions = 1
                AND date(p.last_review_date) = date(sl.started_at)
            WHERE sl.user_id = ?
            ORDER BY sl.started_at DESC
            LIMIT 30
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if rows:
        new_per_session = [float(r["new_items"] or 0) for r in rows]
        arrival_rate = sum(new_per_session) / len(new_per_session) if new_per_session else 1.0
    else:
        arrival_rate = 1.0

    # Service rate: items graduating to stable per session
    try:
        stable_rows = conn.execute("""
            SELECT COUNT(*) AS cnt FROM progress
            WHERE user_id = ?
              AND mastery_stage = 'stable'
              AND stable_since_date >= date('now', '-30 days')
        """, (user_id,)).fetchone()
        stable_count = (stable_rows["cnt"] if stable_rows else 0) or 0

        session_count_row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM session_log
            WHERE user_id = ? AND started_at >= date('now', '-30 days')
        """, (user_id,)).fetchone()
        recent_sessions = (session_count_row["cnt"] if session_count_row else 0) or 1
        service_rate = stable_count / recent_sessions
    except sqlite3.OperationalError:
        service_rate = 0.5

    # Current queue size: items due for review
    try:
        due_row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM progress
            WHERE user_id = ?
              AND next_review_date IS NOT NULL
              AND next_review_date <= date('now', '+1 day')
              AND mastery_stage != 'stable'
        """, (user_id,)).fetchone()
        current_due = (due_row["cnt"] if due_row else 0) or 0
    except sqlite3.OperationalError:
        current_due = 0

    overflow_threshold = 2 * session_length
    net_growth = arrival_rate - service_rate

    if net_growth <= 0:
        sessions_until_overflow = -1  # Queue is shrinking, no overflow
        status = "healthy"
    elif current_due >= overflow_threshold:
        sessions_until_overflow = 0
        status = "overflowed"
    else:
        remaining = overflow_threshold - current_due
        sessions_until_overflow = int(remaining / net_growth) if net_growth > 0 else -1
        if sessions_until_overflow > 50:
            status = "healthy"
        elif sessions_until_overflow > 20:
            status = "caution"
        else:
            status = "warning"

    return {
        "arrival_rate": round(arrival_rate, 2),
        "service_rate": round(service_rate, 2),
        "net_growth_per_session": round(net_growth, 2),
        "current_due": current_due,
        "overflow_threshold": overflow_threshold,
        "sessions_until_overflow": sessions_until_overflow,
        "status": status,
        "session_length": session_length,
    }
