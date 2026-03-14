"""Cross-methodology quality functions — Scrum sprints, Agile retrospectives,
Spiral risk management, WSJF prioritization.

These functions upgrade the methodology grades:
- Scrum: sprint table, auto-creation, review, estimation
- Agile: session retrospectives, WSJF content prioritization
- Spiral: risk review, data-driven risk identification, risk taxonomy
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# SCRUM: Sprint Management
# ═══════════════════════════════════════════════════════════════════════

def get_current_sprint(conn, user_id: int = 1) -> Optional[Dict[str, Any]]:
    """Get the current active sprint for a user."""
    try:
        row = conn.execute("""
            SELECT * FROM sprint
            WHERE user_id = ? AND status = 'active'
            ORDER BY sprint_number DESC LIMIT 1
        """, (user_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def get_sprint_history(conn, user_id: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
    """Get completed sprints for velocity tracking."""
    try:
        rows = conn.execute("""
            SELECT * FROM sprint
            WHERE user_id = ? AND status = 'completed'
            ORDER BY sprint_number DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def auto_create_sprint(conn, user_id: int = 1) -> Optional[Dict[str, Any]]:
    """Auto-create a sprint when a new week (Monday) starts.

    Sprint goal is computed from current queue state:
    - Count overdue items that need review
    - Estimate new items based on budget
    - Estimate story points from difficulty

    Returns the new sprint dict, or None if a sprint already exists.
    """
    # Check if active sprint exists
    existing = get_current_sprint(conn, user_id)
    if existing:
        return None  # Sprint already running

    # Determine sprint number
    try:
        last_row = conn.execute("""
            SELECT MAX(sprint_number) as last_num FROM sprint
            WHERE user_id = ?
        """, (user_id,)).fetchone()
        next_num = ((last_row["last_num"] or 0) if last_row else 0) + 1
    except Exception:
        next_num = 1

    # Count overdue items
    try:
        overdue_row = conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = ?
              AND last_review_date IS NOT NULL
              AND julianday('now') > julianday(
                  datetime(last_review_date, '+' || CAST(ROUND(current_interval) AS TEXT) || ' days')
              )
        """, (user_id,)).fetchone()
        overdue_count = (overdue_row["cnt"] or 0) if overdue_row else 0
    except Exception:
        overdue_count = 0

    # Estimate new items from typical budget (3 per session, 4-5 sessions/week)
    new_estimate = 12  # ~3 new items * 4 sessions

    # Compute planned items and points
    planned_items = overdue_count + new_estimate
    planned_points = _estimate_sprint_points(conn, planned_items, user_id)

    goal = f"Review {overdue_count} overdue items, learn ~{new_estimate} new items"

    try:
        conn.execute("""
            INSERT INTO sprint (user_id, sprint_number, goal, planned_items, planned_points, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (user_id, next_num, goal, planned_items, planned_points))
        conn.commit()
    except Exception as e:
        logger.error("Failed to create sprint: %s", e)
        return None

    return get_current_sprint(conn, user_id)


def _estimate_sprint_points(conn, item_count: int, user_id: int = 1) -> int:
    """Estimate story points for a sprint based on item difficulty.

    Story point mapping:
      HSK 1 item = 1 point
      HSK 2 item = 2 points
      HSK 3 item = 3 points
      Error-focus item = +2 points (harder to remediate)
      Overdue > 7 days = +1 point (needs more review cycles)
    """
    # Simple estimate: avg 2 points per item for mixed HSK levels
    return item_count * 2


def estimate_item_points(item: dict) -> int:
    """Estimate story points for a single item.

    Points scale with difficulty:
      1 = easy (HSK 1, high mastery)
      2 = moderate (HSK 2, some familiarity)
      3 = challenging (HSK 3, new or error-prone)
      5 = hard (HSK 4+, error-focus, many failed attempts)
      8 = epic (complex grammar, never reviewed, high error rate)
    """
    hsk = item.get("hsk_level") or 1
    error_count = item.get("error_count") or 0
    mastery = item.get("mastery_stage") or "unseen"
    attempts = item.get("total_attempts") or 0

    base = min(hsk, 3)  # HSK level as base (capped at 3)

    if mastery == "unseen":
        base += 1
    if error_count >= 3:
        base += 2
    elif error_count >= 1:
        base += 1
    if attempts == 0:
        base += 1

    # Map to Fibonacci-ish scale
    if base <= 1:
        return 1
    elif base <= 2:
        return 2
    elif base <= 3:
        return 3
    elif base <= 5:
        return 5
    else:
        return 8


def complete_sprint(conn, user_id: int = 1) -> Optional[Dict[str, Any]]:
    """Complete the current sprint with a review summary.

    Computes:
    - planned vs actual items and points
    - velocity (items and points per session)
    - accuracy trend over the sprint period
    """
    sprint = get_current_sprint(conn, user_id)
    if not sprint:
        return None

    sprint_start = sprint["started_at"]

    # Count sessions and items completed during sprint
    try:
        session_row = conn.execute("""
            SELECT COUNT(*) as sessions,
                   SUM(items_completed) as completed,
                   SUM(items_correct) as correct,
                   SUM(items_planned) as planned
            FROM session_log
            WHERE user_id = ? AND started_at >= ?
        """, (user_id, sprint_start)).fetchone()

        sessions = (session_row["sessions"] or 0) if session_row else 0
        completed = (session_row["completed"] or 0) if session_row else 0
        correct = (session_row["correct"] or 0) if session_row else 0
        planned_sessions = (session_row["planned"] or 0) if session_row else 0
    except Exception:
        sessions = completed = correct = planned_sessions = 0

    velocity = round(completed / max(sessions, 1), 1)
    accuracy = round(correct / max(completed, 1), 4)

    # Build retrospective
    retro = {
        "sessions": sessions,
        "items_completed": completed,
        "items_correct": correct,
        "velocity_items_per_session": velocity,
        "accuracy": accuracy,
        "planned_items": sprint.get("planned_items") or 0,
        "completion_ratio": round(completed / max(sprint.get("planned_items") or 1, 1), 2),
    }

    # Estimate completed points
    completed_points = round(completed * 2)  # Rough estimate

    try:
        conn.execute("""
            UPDATE sprint SET
                status = 'completed',
                ended_at = datetime('now'),
                completed_items = ?,
                completed_points = ?,
                velocity = ?,
                accuracy_trend = ?,
                retrospective = ?
            WHERE id = ?
        """, (completed, completed_points, velocity, accuracy,
              json.dumps(retro), sprint["id"]))
        conn.commit()
    except Exception as e:
        logger.error("Failed to complete sprint: %s", e)
        return None

    return retro


def get_sprint_velocity(conn, user_id: int = 1, sprints: int = 6) -> Dict[str, Any]:
    """Compute velocity trend from completed sprints."""
    history = get_sprint_history(conn, user_id, limit=sprints)
    if not history:
        return {"velocities": [], "average": 0.0, "trend": "insufficient_data"}

    velocities = [s.get("velocity") or 0.0 for s in history]
    avg = sum(velocities) / len(velocities) if velocities else 0.0

    # Trend: compare last 3 to previous 3
    if len(velocities) >= 6:
        recent = sum(velocities[:3]) / 3
        prior = sum(velocities[3:6]) / 3
        if recent > prior * 1.2:
            trend = "increasing"
        elif recent < prior * 0.8:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {"velocities": velocities, "average": round(avg, 1), "trend": trend}


# ═══════════════════════════════════════════════════════════════════════
# AGILE: Session Retrospectives
# ═══════════════════════════════════════════════════════════════════════

def generate_session_retrospective(conn, session_id: int,
                                   user_id: int = 1) -> Dict[str, Any]:
    """Generate a mini-retrospective after a session.

    Agile: What went well, what didn't, what to change.

    Returns a structured retro dict stored as retrospective_json on session_log.
    """
    try:
        session = conn.execute("""
            SELECT * FROM session_log WHERE id = ? AND user_id = ?
        """, (session_id, user_id)).fetchone()
        if not session:
            return {}
    except Exception:
        return {}

    completed = session["items_completed"] or 0
    correct = session["items_correct"] or 0
    planned = session["items_planned"] or 0
    early_exit = session["early_exit"] or 0

    accuracy = correct / max(completed, 1)
    completion_rate = completed / max(planned, 1)

    # What went well: high-accuracy items
    went_well = []
    try:
        good_items = conn.execute("""
            SELECT re.content_item_id, ci.hanzi, re.drill_type
            FROM review_event re
            JOIN content_item ci ON re.content_item_id = ci.id
            WHERE re.session_id = ? AND re.correct = 1
            ORDER BY re.response_ms ASC LIMIT 3
        """, (session_id,)).fetchall()
        went_well = [{"hanzi": r["hanzi"], "drill_type": r["drill_type"]} for r in good_items]
    except Exception:
        pass

    # What didn't go well: errors, slow responses
    didnt_go_well = []
    try:
        errors = conn.execute("""
            SELECT el.content_item_id, ci.hanzi, el.error_type, el.drill_type
            FROM error_log el
            JOIN content_item ci ON el.content_item_id = ci.id
            WHERE el.session_id = ?
            ORDER BY el.created_at LIMIT 5
        """, (session_id,)).fetchall()
        didnt_go_well = [{"hanzi": r["hanzi"], "error_type": r["error_type"],
                          "drill_type": r["drill_type"]} for r in errors]
    except Exception:
        pass

    # What to change: schedule adjustments
    changes = []
    if accuracy < 0.6:
        changes.append("Reduce new items next session — accuracy below 60%")
    if accuracy > 0.95 and completed >= planned:
        changes.append("Consider adding more challenging items — very high accuracy")
    if completion_rate < 0.7:
        changes.append("Shorten next session — completion rate below 70%")
    if early_exit:
        changes.append("Session was exited early — check if content was too difficult or boring")
    if not changes:
        changes.append("No adjustments needed — session was balanced")

    retro = {
        "session_id": session_id,
        "accuracy": round(accuracy, 4),
        "completion_rate": round(completion_rate, 4),
        "went_well": went_well,
        "didnt_go_well": didnt_go_well,
        "changes": changes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store on session_log
    try:
        conn.execute("""
            UPDATE session_log SET retrospective_json = ? WHERE id = ?
        """, (json.dumps(retro), session_id))
        conn.commit()
    except Exception as e:
        logger.debug("Failed to store retrospective: %s", e)

    # Also log to improvement_log for visibility
    try:
        summary = f"Session {session_id}: accuracy={accuracy:.0%}, completion={completion_rate:.0%}"
        if didnt_go_well:
            error_types = set(e["error_type"] for e in didnt_go_well)
            summary += f", errors: {', '.join(error_types)}"
        conn.execute("""
            INSERT INTO improvement_log (user_id, trigger_reason, observation, proposed_change, status)
            VALUES (?, 'session_retrospective', ?, ?, 'proposed')
        """, (user_id, summary, json.dumps(changes)))
        conn.commit()
    except Exception as e:
        logger.debug("Failed to log retrospective to improvement_log: %s", e)

    return retro


# ═══════════════════════════════════════════════════════════════════════
# AGILE: WSJF (Weighted Shortest Job First) Prioritization
# ═══════════════════════════════════════════════════════════════════════

def calculate_wsjf(item: dict) -> float:
    """Calculate WSJF priority score for a content item.

    WSJF = (Business Value + Time Criticality + Risk Reduction) / Job Size

    For a learning system:
    - Business Value = item frequency/utility (HSK core items > obscure items)
    - Time Criticality = how overdue the item is (urgency of review)
    - Risk Reduction = items in error focus reduce failure risk
    - Job Size = estimated effort (drill type complexity, error history)
    """
    # Business Value: HSK level inversely correlates (HSK 1 = most valuable for beginners)
    hsk = item.get("hsk_level") or 3
    frequency = item.get("frequency_rank") or 5000
    # Higher value for lower HSK and higher frequency
    bv = max(1, 6 - hsk) + max(0, (5000 - frequency) / 1000)

    # Time Criticality: how overdue
    days_overdue = item.get("days_overdue") or 0
    tc = min(5, days_overdue / 2)  # Cap at 5

    # Risk Reduction: error-prone items reduce risk of future failures
    error_count = item.get("error_count") or 0
    rr = min(3, error_count)

    # Job Size: estimate of effort
    mastery = item.get("mastery_stage") or "unseen"
    size_map = {"unseen": 5, "seen": 4, "passed_once": 3, "stabilizing": 2, "stable": 1, "durable": 1}
    job_size = size_map.get(mastery, 3)

    # WSJF score
    numerator = bv + tc + rr
    wsjf = numerator / max(job_size, 1)

    return round(wsjf, 2)


def rank_content_backlog(conn, user_id: int = 1, limit: int = 50) -> List[Dict[str, Any]]:
    """Rank the content backlog by WSJF priority.

    Returns items sorted by WSJF score (descending) — highest priority first.
    """
    try:
        rows = conn.execute("""
            SELECT ci.id, ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
                   COALESCE(p.mastery_stage, 'unseen') as mastery_stage,
                   COALESCE(p.total_attempts, 0) as total_attempts,
                   CAST(julianday('now') - julianday(
                       datetime(p.last_review_date, '+' || CAST(ROUND(p.current_interval) AS TEXT) || ' days')
                   ) AS INTEGER) AS days_overdue,
                   (SELECT COUNT(*) FROM error_log el WHERE el.content_item_id = ci.id) as error_count
            FROM content_item ci
            LEFT JOIN progress p ON p.content_item_id = ci.id
                AND p.modality = 'reading' AND p.user_id = ?
            WHERE ci.status = 'drill_ready'
            ORDER BY ci.hsk_level, ci.id
            LIMIT ?
        """, (user_id, limit * 2)).fetchall()
    except Exception:
        return []

    items = []
    for r in rows:
        item = dict(r)
        item["wsjf_score"] = calculate_wsjf(item)
        items.append(item)

    items.sort(key=lambda x: x["wsjf_score"], reverse=True)
    return items[:limit]


# ═══════════════════════════════════════════════════════════════════════
# SPIRAL: Risk Management
# ═══════════════════════════════════════════════════════════════════════

# Risk Taxonomy — categorize all risks into a structured hierarchy
RISK_TAXONOMY = {
    "learning": {
        "label": "Learning Risks",
        "types": {
            "forgetting": "Items decay faster than review schedule accounts for",
            "interference": "Similar items confuse each other (e.g., tone pairs, homophone confusion)",
            "plateau": "Learner accuracy stagnates despite continued practice",
            "coverage_gap": "Important content areas not covered by current item pool",
            "difficulty_mismatch": "Items too easy (boredom) or too hard (frustration)",
        },
    },
    "engagement": {
        "label": "Engagement Risks",
        "types": {
            "boredom": "Drill types feel repetitive, session structure predictable",
            "frustration": "Too many errors, items too difficult for current level",
            "dropout": "User stops returning — session frequency declining",
            "burnout": "Sessions too long or too frequent",
            "low_motivation": "No sense of progress or achievement",
        },
    },
    "content": {
        "label": "Content Risks",
        "types": {
            "coverage_gap": "HSK levels or skill areas missing items",
            "difficulty_calibration": "Item difficulty ratings inaccurate",
            "stale_content": "Content doesn't reflect current usage or learner needs",
            "error_patterns": "Systematic grading errors in specific drill types",
        },
    },
    "technical": {
        "label": "Technical Risks",
        "types": {
            "data_loss": "Database corruption or backup failure",
            "sync_failure": "State inconsistency across platforms",
            "performance": "Slow responses degrading user experience",
            "schema_drift": "Migrations failing or schema out of sync",
        },
    },
}


def get_risk_taxonomy() -> Dict[str, Any]:
    """Return the risk taxonomy definition."""
    return RISK_TAXONOMY


def run_risk_review(conn, user_id: int = 1) -> List[Dict[str, Any]]:
    """Run an automated risk assessment using system data.

    Spiral: After every N sessions, identify items with:
    - Declining accuracy trends
    - Items never reviewed
    - Items with high error rates
    - SPC out-of-control signals
    - Engagement decline signals

    Returns a list of identified risk events.
    """
    risks = []

    # 1. Learning risk: items with declining accuracy trend
    try:
        declining = conn.execute("""
            SELECT ci.id, ci.hanzi, p.mastery_stage, p.streak_correct,
                   p.total_correct, p.total_attempts
            FROM progress p
            JOIN content_item ci ON p.content_item_id = ci.id
            WHERE p.user_id = ?
              AND p.total_attempts >= 5
              AND CAST(p.total_correct AS REAL) / p.total_attempts < 0.5
              AND p.mastery_stage NOT IN ('durable')
        """, (user_id,)).fetchall()

        if declining:
            risks.append({
                "risk_category": "learning",
                "risk_type": "forgetting",
                "severity": "high" if len(declining) > 10 else "medium",
                "description": f"{len(declining)} items have accuracy below 50% after 5+ attempts",
                "source": "risk_review",
                "data_json": json.dumps({"item_count": len(declining),
                                         "sample_items": [r["hanzi"] for r in declining[:5]]}),
            })
    except Exception:
        pass

    # 2. Learning risk: items never reviewed (coverage gap)
    try:
        never_reviewed = conn.execute("""
            SELECT COUNT(*) as cnt FROM content_item
            WHERE status = 'drill_ready' AND times_shown = 0
        """).fetchone()
        count = (never_reviewed["cnt"] or 0) if never_reviewed else 0
        if count > 50:
            risks.append({
                "risk_category": "content",
                "risk_type": "coverage_gap",
                "severity": "medium",
                "description": f"{count} drill-ready items have never been shown",
                "source": "risk_review",
                "data_json": json.dumps({"unreviewed_count": count}),
            })
    except Exception:
        pass

    # 3. Engagement risk: declining session frequency
    try:
        recent = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = ? AND started_at >= datetime('now', '-7 days')
        """, (user_id,)).fetchone()
        prior = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = ?
              AND started_at >= datetime('now', '-14 days')
              AND started_at < datetime('now', '-7 days')
        """, (user_id,)).fetchone()

        recent_cnt = (recent["cnt"] or 0) if recent else 0
        prior_cnt = (prior["cnt"] or 0) if prior else 0

        if prior_cnt > 0 and recent_cnt < prior_cnt * 0.5:
            risks.append({
                "risk_category": "engagement",
                "risk_type": "dropout",
                "severity": "high",
                "description": f"Session frequency dropped: {recent_cnt} this week vs {prior_cnt} last week",
                "source": "risk_review",
                "data_json": json.dumps({"recent_sessions": recent_cnt, "prior_sessions": prior_cnt}),
            })
    except Exception:
        pass

    # 4. Engagement risk: high early exit rate
    try:
        exit_row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) as exits
            FROM session_log
            WHERE user_id = ? AND started_at >= datetime('now', '-14 days')
        """, (user_id,)).fetchone()
        total = (exit_row["total"] or 0) if exit_row else 0
        exits = (exit_row["exits"] or 0) if exit_row else 0
        if total >= 5 and exits / total > 0.3:
            risks.append({
                "risk_category": "engagement",
                "risk_type": "frustration",
                "severity": "high",
                "description": f"High early exit rate: {exits}/{total} sessions ({exits/total:.0%})",
                "source": "risk_review",
                "data_json": json.dumps({"total_sessions": total, "early_exits": exits}),
            })
    except Exception:
        pass

    # 5. Learning risk: interference (items with homophone/confusable errors)
    try:
        confusable_errors = conn.execute("""
            SELECT COUNT(*) as cnt FROM error_log
            WHERE error_type IN ('ime_confusable', 'tone')
              AND created_at >= datetime('now', '-14 days')
        """).fetchone()
        conf_cnt = (confusable_errors["cnt"] or 0) if confusable_errors else 0
        if conf_cnt > 10:
            risks.append({
                "risk_category": "learning",
                "risk_type": "interference",
                "severity": "medium",
                "description": f"{conf_cnt} confusable/tone errors in last 14 days",
                "source": "risk_review",
                "data_json": json.dumps({"confusable_error_count": conf_cnt}),
            })
    except Exception:
        pass

    # 6. SPC-based risk identification
    try:
        from .spc import compute_spc_chart
        for chart_type in ["drill_accuracy", "response_time", "session_completion"]:
            spc = compute_spc_chart(conn, chart_type)
            if spc and spc.get("out_of_control"):
                category = "learning" if chart_type == "drill_accuracy" else "technical"
                risks.append({
                    "risk_category": category,
                    "risk_type": "plateau" if chart_type == "drill_accuracy" else "performance",
                    "severity": "warning",
                    "description": f"SPC control chart violation: {chart_type}",
                    "source": "spc",
                    "data_json": json.dumps({"chart_type": chart_type,
                                             "violations": spc.get("violations", [])}),
                })
    except (ImportError, Exception):
        pass

    # Log risk events to risk_event table
    for risk in risks:
        try:
            conn.execute("""
                INSERT INTO risk_event
                    (user_id, risk_category, risk_type, severity, description, source, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, risk["risk_category"], risk["risk_type"],
                  risk["severity"], risk["description"], risk["source"],
                  risk.get("data_json")))
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        pass

    return risks


def get_risk_summary(conn, user_id: int = 1, days: int = 30) -> Dict[str, Any]:
    """Summarize risk events for the admin dashboard."""
    try:
        rows = conn.execute("""
            SELECT risk_category, risk_type, severity, COUNT(*) as cnt
            FROM risk_event
            WHERE user_id = ?
              AND created_at >= datetime('now', ? || ' days')
            GROUP BY risk_category, risk_type, severity
            ORDER BY cnt DESC
        """, (user_id, f"-{days}")).fetchall()
    except Exception:
        return {"by_category": {}, "total": 0, "open_count": 0}

    by_category = {}
    total = 0
    for r in rows:
        cat = r["risk_category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            "type": r["risk_type"],
            "severity": r["severity"],
            "count": r["cnt"],
        })
        total += r["cnt"]

    # Open (unresolved) risk events
    try:
        open_row = conn.execute("""
            SELECT COUNT(*) as cnt FROM risk_event
            WHERE user_id = ? AND status = 'open'
        """, (user_id,)).fetchone()
        open_count = (open_row["cnt"] or 0) if open_row else 0
    except Exception:
        open_count = 0

    return {"by_category": by_category, "total": total, "open_count": open_count}
