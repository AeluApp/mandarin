"""Engagement analysis — abandonment risk, snapshots, intervention scoring (Doc 7).

Feature extraction adapted to real schema:
- session_log (items_completed, items_correct, early_exit, boredom_flags, duration_seconds)
- review_event (response_ms)
- vocab_encounter (encounter count)

Zero Claude tokens at runtime — all deterministic.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Feature Extraction ──────────────────────────────────────────────────────


def _extract_session_features(conn: sqlite3.Connection, user_id: int, days: int = 7) -> dict:
    """Extract session-level features from session_log for a user over N days."""
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE user_id = ? AND started_at >= datetime('now', ?)
    """, (user_id, f"-{days} days")) or 0

    avg_accuracy = _safe_scalar(conn, """
        SELECT AVG(CASE WHEN items_completed > 0
                        THEN items_correct * 1.0 / items_completed
                        ELSE NULL END)
        FROM session_log
        WHERE user_id = ? AND started_at >= datetime('now', ?)
          AND items_completed > 0
    """, (user_id, f"-{days} days"))

    avg_duration = _safe_scalar(conn, """
        SELECT AVG(duration_seconds) FROM session_log
        WHERE user_id = ? AND started_at >= datetime('now', ?)
          AND duration_seconds IS NOT NULL AND duration_seconds > 0
    """, (user_id, f"-{days} days"))

    early_exits = _safe_scalar(conn, """
        SELECT SUM(early_exit) FROM session_log
        WHERE user_id = ? AND started_at >= datetime('now', ?)
    """, (user_id, f"-{days} days")) or 0

    boredom_flags = _safe_scalar(conn, """
        SELECT SUM(boredom_flags) FROM session_log
        WHERE user_id = ? AND started_at >= datetime('now', ?)
    """, (user_id, f"-{days} days")) or 0

    return {
        "sessions": count,
        "avg_accuracy": avg_accuracy,
        "avg_duration": avg_duration,
        "early_exits": early_exits,
        "boredom_flags": boredom_flags,
    }


def _extract_review_features(conn: sqlite3.Connection, user_id: int, days: int = 7) -> dict:
    """Extract review-level features from review_event."""
    items_reviewed = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE user_id = ? AND created_at >= datetime('now', ?)
    """, (user_id, f"-{days} days")) or 0

    avg_response_ms = _safe_scalar(conn, """
        SELECT AVG(response_ms) FROM review_event
        WHERE user_id = ? AND created_at >= datetime('now', ?)
          AND response_ms IS NOT NULL AND response_ms > 0
    """, (user_id, f"-{days} days"))

    return {
        "items_reviewed": items_reviewed,
        "avg_response_ms": avg_response_ms,
    }


def _extract_encounter_features(conn: sqlite3.Connection, user_id: int, days: int = 7) -> dict:
    """Extract encounter count from vocab_encounter."""
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM vocab_encounter
        WHERE user_id = ? AND created_at >= datetime('now', ?)
    """, (user_id, f"-{days} days")) or 0

    return {"encounters": count}


# ── Abandonment Risk Model ──────────────────────────────────────────────────


def compute_abandonment_risk(conn: sqlite3.Connection, user_id: int) -> dict:
    """Compute abandonment risk for a user. Returns {risk, level, factors, features}.

    Rule-based scoring with 5 weighted factors:
    - Session recency (0-0.30): days since last completed session
    - Frequency trend (0-0.20): week-over-week session decline
    - Frustration proxy (0-0.25): early_exit + boredom_flags + slow response
    - Accuracy (0-0.15): low recent accuracy
    - Duration trend (0-0.10): declining session duration
    """
    features_7d = _extract_session_features(conn, user_id, days=7)
    features_14d = _extract_session_features(conn, user_id, days=14)
    review_7d = _extract_review_features(conn, user_id, days=7)
    encounter_7d = _extract_encounter_features(conn, user_id, days=7)

    risk = 0.0
    factors = []

    # 1. Session recency (weight: 0.30)
    # Check if any completed sessions exist first
    has_sessions = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE user_id = ? AND items_completed > 0
    """, (user_id,)) or 0

    if has_sessions > 0:
        last_session_days = _safe_scalar(conn, """
            SELECT julianday('now') - julianday(MAX(started_at))
            FROM session_log
            WHERE user_id = ? AND items_completed > 0
        """, (user_id,))
    else:
        last_session_days = None

    if last_session_days is None:
        # No completed sessions at all
        recency_score = 0.30
        factors.append("no_completed_sessions")
    elif last_session_days > 14:
        recency_score = 0.30
        factors.append("inactive_14d_plus")
    elif last_session_days > 7:
        recency_score = 0.20
        factors.append("inactive_7d_plus")
    elif last_session_days > 3:
        recency_score = 0.10
        factors.append("slowing_activity")
    else:
        recency_score = 0.0
    risk += recency_score

    # 2. Frequency trend (weight: 0.20)
    sessions_7d = features_7d["sessions"]
    sessions_prior_7d = (features_14d["sessions"] or 0) - sessions_7d
    if sessions_prior_7d > 0 and sessions_7d == 0:
        freq_score = 0.20
        factors.append("session_frequency_dropped_to_zero")
    elif sessions_prior_7d > 0 and sessions_7d < sessions_prior_7d * 0.5:
        freq_score = 0.12
        factors.append("session_frequency_halved")
    elif sessions_prior_7d > 0 and sessions_7d < sessions_prior_7d:
        freq_score = 0.06
        factors.append("session_frequency_declining")
    else:
        freq_score = 0.0
    risk += freq_score

    # 3. Frustration proxy (weight: 0.25)
    early = features_7d["early_exits"] or 0
    boredom = features_7d["boredom_flags"] or 0
    avg_resp = review_7d["avg_response_ms"]
    slow_penalty = 0
    if avg_resp and avg_resp > 8000:
        slow_penalty = min(25, (avg_resp - 8000) / 400)
    frustration_raw = early * 15 + boredom * 10 + slow_penalty
    frustration_score = min(0.25, frustration_raw / 100.0)
    if frustration_score > 0.05:
        factors.append("frustration_signals")
    risk += frustration_score

    # 4. Accuracy (weight: 0.15)
    acc = features_7d["avg_accuracy"]
    has_accuracy_data = features_7d["sessions"] > 0 and acc != 0
    if has_accuracy_data and acc < 0.4:
        acc_score = 0.15
        factors.append("very_low_accuracy")
    elif has_accuracy_data and acc < 0.6:
        acc_score = 0.08
        factors.append("low_accuracy")
    else:
        acc_score = 0.0
    risk += acc_score

    # 5. Duration trend (weight: 0.10)
    dur_7d = features_7d["avg_duration"]
    # Get prior week's avg duration
    dur_prior = _safe_scalar(conn, """
        SELECT AVG(duration_seconds) FROM session_log
        WHERE user_id = ? AND started_at >= datetime('now', '-14 days')
          AND started_at < datetime('now', '-7 days')
          AND duration_seconds IS NOT NULL AND duration_seconds > 0
    """, (user_id,))
    if dur_prior and dur_7d and dur_7d < dur_prior * 0.5:
        dur_score = 0.10
        factors.append("session_duration_halved")
    elif dur_prior and dur_7d and dur_7d < dur_prior * 0.75:
        dur_score = 0.05
        factors.append("session_duration_declining")
    else:
        dur_score = 0.0
    risk += dur_score

    risk = round(min(1.0, max(0.0, risk)), 3)

    if risk >= 0.75:
        level = "critical"
    elif risk >= 0.50:
        level = "high"
    elif risk >= 0.25:
        level = "medium"
    else:
        level = "low"

    return {
        "risk": risk,
        "level": level,
        "factors": factors,
        "features": {
            "sessions_7d": features_7d["sessions"],
            "sessions_14d": features_14d["sessions"],
            "avg_accuracy_7d": features_7d["avg_accuracy"],
            "avg_duration_7d": features_7d["avg_duration"],
            "early_exits_7d": features_7d["early_exits"],
            "boredom_flags_7d": features_7d["boredom_flags"],
            "avg_response_ms_7d": review_7d["avg_response_ms"],
            "items_reviewed_7d": review_7d["items_reviewed"],
            "encounters_7d": encounter_7d["encounters"],
        },
    }


# ── Snapshot Generation ─────────────────────────────────────────────────────


def generate_engagement_snapshot(
    conn: sqlite3.Connection, user_id: int, snapshot_date: str | None = None
) -> dict:
    """Generate and upsert an engagement snapshot for a user."""
    if snapshot_date is None:
        snapshot_date = datetime.now(UTC).strftime("%Y-%m-%d")

    result = compute_abandonment_risk(conn, user_id)
    features = result["features"]

    try:
        conn.execute("""
            INSERT INTO pi_engagement_snapshots (
                user_id, snapshot_date,
                sessions_7d, sessions_14d,
                avg_accuracy_7d, avg_duration_7d,
                early_exits_7d, boredom_flags_7d,
                avg_response_ms_7d,
                items_reviewed_7d, encounters_7d,
                abandonment_risk, risk_level, risk_factors
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, snapshot_date) DO UPDATE SET
                sessions_7d = excluded.sessions_7d,
                sessions_14d = excluded.sessions_14d,
                avg_accuracy_7d = excluded.avg_accuracy_7d,
                avg_duration_7d = excluded.avg_duration_7d,
                early_exits_7d = excluded.early_exits_7d,
                boredom_flags_7d = excluded.boredom_flags_7d,
                avg_response_ms_7d = excluded.avg_response_ms_7d,
                items_reviewed_7d = excluded.items_reviewed_7d,
                encounters_7d = excluded.encounters_7d,
                abandonment_risk = excluded.abandonment_risk,
                risk_level = excluded.risk_level,
                risk_factors = excluded.risk_factors
        """, (
            user_id, snapshot_date,
            features["sessions_7d"], features["sessions_14d"],
            features["avg_accuracy_7d"], features["avg_duration_7d"],
            features["early_exits_7d"], features["boredom_flags_7d"],
            features["avg_response_ms_7d"],
            features["items_reviewed_7d"], features["encounters_7d"],
            result["risk"], result["level"],
            json.dumps(result["factors"]),
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to upsert engagement snapshot: %s", e)

    return result


# ── Intervention Effectiveness ──────────────────────────────────────────────


def score_intervention_effectiveness(conn: sqlite3.Connection) -> int:
    """Score interventions 7+ days old by comparing risk_at_intervention with current risk.

    Sets effective=1 if risk dropped >= 0.15. Returns count of scored interventions.
    """
    try:
        rows = _safe_query_all(conn, """
            SELECT id, student_user_id, risk_at_intervention
            FROM pi_teacher_interventions
            WHERE effective IS NULL
              AND created_at <= datetime('now', '-7 days')
        """)
    except Exception:
        return 0

    if not rows:
        return 0

    scored = 0
    for row in rows:
        current = compute_abandonment_risk(conn, row["student_user_id"])
        current_risk = current["risk"]
        risk_drop = (row["risk_at_intervention"] or 0) - current_risk
        effective = 1 if risk_drop >= 0.15 else 0

        try:
            conn.execute("""
                UPDATE pi_teacher_interventions
                SET risk_after_7d = ?, effective = ?
                WHERE id = ?
            """, (current_risk, effective, row["id"]))
            scored += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.error("Failed to score intervention %s: %s", row["id"], e)

    conn.commit()
    return scored


# ── Analyzers ───────────────────────────────────────────────────────────────


def _analyze_engagement_risk(conn: sqlite3.Connection) -> list[dict]:
    """Emit finding when >20% of snapped users are at high/critical risk,
    or when >=3 users show rapidly worsening trend."""
    findings = []

    total_snapped = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM pi_engagement_snapshots
        WHERE snapshot_date >= date('now', '-3 days')
    """) or 0

    if total_snapped == 0:
        return findings

    at_risk = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM pi_engagement_snapshots
        WHERE snapshot_date >= date('now', '-3 days')
          AND risk_level IN ('high', 'critical')
    """) or 0

    risk_pct = at_risk / total_snapped * 100 if total_snapped > 0 else 0

    if risk_pct > 20:
        findings.append(_finding(
            dimension="engagement",
            severity="high",
            title=f"{at_risk}/{total_snapped} users ({risk_pct:.0f}%) at high/critical abandonment risk",
            analysis=(
                f"{at_risk} out of {total_snapped} recently snapped users show "
                f"high or critical abandonment risk ({risk_pct:.0f}%). "
                "This indicates systemic engagement issues that need immediate attention."
            ),
            recommendation="Run engagement snapshots for all active users, review top risk factors, and consider targeted interventions.",
            claude_prompt=(
                "Analyze the engagement risk distribution across users. "
                "Identify common risk factors and recommend targeted interventions."
            ),
            impact="retention",
            files=["mandarin/intelligence/engagement.py"],
        ))

    # Check for rapidly worsening users (risk increased >=0.20 in last 7 days)
    worsening = _safe_query_all(conn, """
        SELECT s1.user_id,
               s1.abandonment_risk as current_risk,
               s2.abandonment_risk as prior_risk
        FROM pi_engagement_snapshots s1
        JOIN pi_engagement_snapshots s2
            ON s1.user_id = s2.user_id
        WHERE s1.snapshot_date >= date('now', '-3 days')
          AND s2.snapshot_date >= date('now', '-10 days')
          AND s2.snapshot_date < date('now', '-3 days')
          AND (s1.abandonment_risk - s2.abandonment_risk) >= 0.20
    """)

    if worsening and len(worsening) >= 3:
        findings.append(_finding(
            dimension="engagement",
            severity="high",
            title=f"{len(worsening)} users show rapidly worsening engagement",
            analysis=(
                f"{len(worsening)} users have seen their abandonment risk increase by "
                ">=0.20 in the past week. This suggests a recent change is driving disengagement."
            ),
            recommendation="Investigate recent changes (content, UX, scheduling) that may correlate with worsening engagement.",
            claude_prompt=(
                "Check for recent changes that correlate with worsening user engagement. "
                "Look at content updates, UX changes, and scheduler behavior."
            ),
            impact="retention",
            files=["mandarin/intelligence/engagement.py"],
        ))

    return findings


def _analyze_intervention_effectiveness(conn: sqlite3.Connection) -> list[dict]:
    """Emit finding when intervention effectiveness is below 40%."""
    findings = []

    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_teacher_interventions
        WHERE effective IS NOT NULL
    """) or 0

    if total < 5:
        return findings

    effective_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_teacher_interventions
        WHERE effective = 1
    """) or 0

    effectiveness = effective_count / total * 100 if total > 0 else 0

    if effectiveness < 40:
        findings.append(_finding(
            dimension="engagement",
            severity="medium",
            title=f"Teacher intervention effectiveness low ({effectiveness:.0f}%)",
            analysis=(
                f"Only {effective_count}/{total} teacher interventions ({effectiveness:.0f}%) "
                "resulted in meaningful risk reduction (>=0.15 drop). "
                "Current intervention strategies may need revision."
            ),
            recommendation="Review intervention types and timing. Consider providing teachers with more targeted guidance based on risk factors.",
            claude_prompt=(
                "Analyze teacher intervention patterns and outcomes. "
                "Identify which intervention types are most effective and recommend improvements."
            ),
            impact="retention",
            files=["mandarin/web/classroom_routes.py", "mandarin/intelligence/engagement.py"],
        ))

    return findings


ANALYZERS = [_analyze_engagement_risk, _analyze_intervention_effectiveness]
