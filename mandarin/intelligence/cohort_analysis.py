"""Cohort analysis — classroom-level health, snapshots, teacher dashboard data (Doc 7).

Uses existing classroom/classroom_student tables. Computes per-student risk
via engagement.compute_abandonment_risk and aggregates to classroom level.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar
from .engagement import compute_abandonment_risk

logger = logging.getLogger(__name__)


def generate_cohort_snapshot(
    conn: sqlite3.Connection, classroom_id: int, snapshot_date: str | None = None
) -> dict:
    """Generate and upsert a cohort snapshot for a classroom.

    Computes per-student abandonment risk, aggregates to classroom level,
    detects trend vs previous snapshot.
    """
    if snapshot_date is None:
        snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Get all active students in this classroom
    students = _safe_query_all(conn, """
        SELECT user_id FROM classroom_student
        WHERE classroom_id = ? AND status = 'active'
    """, (classroom_id,)) or []

    total_students = len(students)

    # Compute per-student risk
    risks = []
    at_risk_count = 0
    high_risk_count = 0
    accuracy_sum = 0.0
    accuracy_n = 0
    sessions_sum = 0

    for student in students:
        uid = student["user_id"]
        result = compute_abandonment_risk(conn, uid)
        risks.append(result)

        if result["level"] in ("high", "critical"):
            at_risk_count += 1
        if result["level"] == "critical":
            high_risk_count += 1

        acc = result["features"].get("avg_accuracy_7d")
        if acc is not None:
            accuracy_sum += acc
            accuracy_n += 1
        sessions_sum += result["features"].get("sessions_7d", 0)

    avg_accuracy = round(accuracy_sum / accuracy_n, 3) if accuracy_n > 0 else None
    avg_sessions = round(sessions_sum / total_students, 2) if total_students > 0 else 0
    avg_risk = round(sum(r["risk"] for r in risks) / len(risks), 3) if risks else 0.0

    # Count active students (at least 1 session in 7 days)
    active_7d = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT sl.user_id) FROM session_log sl
        JOIN classroom_student cs ON cs.user_id = sl.user_id
        WHERE cs.classroom_id = ? AND cs.status = 'active'
          AND sl.started_at >= datetime('now', '-7 days')
    """, (classroom_id,)) or 0

    # Detect trend vs previous snapshot
    prev = _safe_query(conn, """
        SELECT avg_abandonment_risk FROM pi_cohort_snapshots
        WHERE classroom_id = ? AND snapshot_date < ?
        ORDER BY snapshot_date DESC LIMIT 1
    """, (classroom_id, snapshot_date))

    if prev and prev["avg_abandonment_risk"] is not None:
        prev_risk = prev["avg_abandonment_risk"]
        delta = avg_risk - prev_risk
        if delta > 0.05:
            trend = "declining"
        elif delta < -0.05:
            trend = "improving"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Upsert
    try:
        conn.execute("""
            INSERT INTO pi_cohort_snapshots (
                classroom_id, snapshot_date,
                total_students, active_students_7d,
                avg_accuracy, avg_sessions_per_student,
                at_risk_count, high_risk_count,
                avg_abandonment_risk, engagement_trend
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(classroom_id, snapshot_date) DO UPDATE SET
                total_students = excluded.total_students,
                active_students_7d = excluded.active_students_7d,
                avg_accuracy = excluded.avg_accuracy,
                avg_sessions_per_student = excluded.avg_sessions_per_student,
                at_risk_count = excluded.at_risk_count,
                high_risk_count = excluded.high_risk_count,
                avg_abandonment_risk = excluded.avg_abandonment_risk,
                engagement_trend = excluded.engagement_trend
        """, (
            classroom_id, snapshot_date,
            total_students, active_7d,
            avg_accuracy, avg_sessions,
            at_risk_count, high_risk_count,
            avg_risk, trend,
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to upsert cohort snapshot: %s", e)

    return {
        "classroom_id": classroom_id,
        "snapshot_date": snapshot_date,
        "total_students": total_students,
        "active_students_7d": active_7d,
        "avg_accuracy": avg_accuracy,
        "avg_sessions_per_student": avg_sessions,
        "at_risk_count": at_risk_count,
        "high_risk_count": high_risk_count,
        "avg_abandonment_risk": avg_risk,
        "engagement_trend": trend,
    }


def get_classroom_health(conn: sqlite3.Connection, classroom_id: int) -> dict:
    """Real-time computed classroom health summary for teacher dashboard."""
    students = _safe_query_all(conn, """
        SELECT user_id FROM classroom_student
        WHERE classroom_id = ? AND status = 'active'
    """, (classroom_id,)) or []

    by_risk = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    total_accuracy = 0.0
    accuracy_n = 0
    total_sessions = 0
    top_risk = []

    for student in students:
        uid = student["user_id"]
        result = compute_abandonment_risk(conn, uid)
        level = result["level"]
        by_risk[level] = by_risk.get(level, 0) + 1

        acc = result["features"].get("avg_accuracy_7d")
        if acc is not None:
            total_accuracy += acc
            accuracy_n += 1
        total_sessions += result["features"].get("sessions_7d", 0)

        if level in ("high", "critical"):
            top_risk.append({
                "user_id": uid,
                "risk": result["risk"],
                "level": level,
                "factors": result["factors"],
            })

    top_risk.sort(key=lambda x: x["risk"], reverse=True)

    total = len(students)
    return {
        "total_students": total,
        "risk_distribution": by_risk,
        "avg_accuracy": round(total_accuracy / accuracy_n, 3) if accuracy_n > 0 else None,
        "avg_sessions_per_student": round(total_sessions / total, 2) if total > 0 else 0,
        "at_risk_count": by_risk.get("high", 0) + by_risk.get("critical", 0),
        "top_risk_students": top_risk[:10],
    }


# ── Analyzer ────────────────────────────────────────────────────────────────


def _analyze_cohort_health(conn: sqlite3.Connection) -> list[dict]:
    """Emit finding when any classroom has >30% at-risk students (from latest snapshot)."""
    findings = []

    rows = _safe_query_all(conn, """
        SELECT cs.classroom_id, cs.total_students, cs.at_risk_count, cs.high_risk_count,
               cs.engagement_trend, c.name
        FROM pi_cohort_snapshots cs
        JOIN classroom c ON c.id = cs.classroom_id
        WHERE cs.snapshot_date = (
            SELECT MAX(snapshot_date) FROM pi_cohort_snapshots
            WHERE classroom_id = cs.classroom_id
        )
    """)

    if not rows:
        return findings

    for row in rows:
        total = row["total_students"] or 0
        at_risk = row["at_risk_count"] or 0
        if total > 0 and (at_risk / total) > 0.30:
            pct = at_risk / total * 100
            name = row["name"] or f"classroom {row['classroom_id']}"
            findings.append(_finding(
                dimension="engagement",
                severity="high",
                title=f"Classroom '{name}' has {pct:.0f}% at-risk students",
                analysis=(
                    f"Classroom '{name}' has {at_risk}/{total} students "
                    f"({pct:.0f}%) at high or critical abandonment risk. "
                    f"Engagement trend: {row['engagement_trend']}."
                ),
                recommendation=(
                    f"Teacher should review at-risk students in classroom '{name}' "
                    "and consider targeted interventions."
                ),
                claude_prompt=(
                    f"Analyze engagement data for classroom '{name}' (id={row['classroom_id']}). "
                    "Identify common risk factors among at-risk students."
                ),
                impact="retention",
                files=["mandarin/intelligence/cohort_analysis.py"],
            ))

    return findings


ANALYZERS = [_analyze_cohort_health]
