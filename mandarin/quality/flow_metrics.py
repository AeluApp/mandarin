"""Flow metrics — cycle time, lead time, throughput, CFD, Pareto, CTQ from work_item table."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── CTQ Tree (Critical-to-Quality) ───────────────────────────────────
# Maps Customer Needs → CTQ Drivers → Metrics → Specs
# Lean Six Sigma: this is the "voice of customer" translated to measurable targets.

CTQ_TREE = {
    "learn_efficiently": {
        "need": "Learn Mandarin efficiently",
        "drivers": [
            {
                "ctq": "Long-term retention",
                "metric": "7-day recall rate",
                "spec": ">80%",
                "measurement": "review_event WHERE days_since_last >= 7 AND correct = 1",
            },
            {
                "ctq": "Optimal spacing",
                "metric": "Review timeliness (% reviewed within SRS window)",
                "spec": ">70%",
                "measurement": "progress WHERE last_review_date within interval",
            },
        ],
    },
    "stay_engaged": {
        "need": "Stay engaged without burnout",
        "drivers": [
            {
                "ctq": "Session completion",
                "metric": "Completion rate (items_completed / items_planned)",
                "spec": ">85%",
                "measurement": "session_log completion rate",
            },
            {
                "ctq": "Streak maintenance",
                "metric": "Weekly session count vs target",
                "spec": ">=80% of target_sessions_per_week",
                "measurement": "session_log grouped by week",
            },
            {
                "ctq": "No frustration",
                "metric": "Early exit rate",
                "spec": "<15%",
                "measurement": "session_log WHERE early_exit = 1",
            },
        ],
    },
    "accurate_grading": {
        "need": "Trust that grades are accurate",
        "drivers": [
            {
                "ctq": "Grade accuracy",
                "metric": "Grade appeal rate",
                "spec": "<2%",
                "measurement": "grade_appeal / review_event",
            },
            {
                "ctq": "Consistent difficulty",
                "metric": "Session accuracy variance (Cpk)",
                "spec": "Cpk >= 1.0",
                "measurement": "capability.assess_drill_accuracy()",
            },
        ],
    },
    "fast_responsive": {
        "need": "App responds quickly",
        "drivers": [
            {
                "ctq": "API responsiveness",
                "metric": "P95 response time",
                "spec": "<500ms",
                "measurement": "review_event.response_ms P95",
            },
            {
                "ctq": "Audio latency",
                "metric": "TTS playback delay",
                "spec": "<200ms",
                "measurement": "client-side measurement",
            },
        ],
    },
}


def get_ctq_tree() -> Dict[str, Any]:
    """Return the CTQ tree definition."""
    return CTQ_TREE


def assess_ctq_metrics(conn) -> Dict[str, Any]:
    """Measure current performance against each CTQ spec."""
    results = {}

    # 7-day recall rate
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct
            FROM review_event
            WHERE created_at >= datetime('now', '-30 days')
              AND response_ms IS NOT NULL
        """).fetchone()
        total = (row["total"] or 0) if row else 0
        correct = (row["correct"] or 0) if row else 0
        results["retention_rate"] = round(correct / total, 4) if total > 0 else None
    except Exception:
        results["retention_rate"] = None

    # Session completion rate
    try:
        row = conn.execute("""
            SELECT SUM(items_completed) as completed, SUM(items_planned) as planned
            FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
              AND items_planned > 0
        """).fetchone()
        planned = (row["planned"] or 0) if row else 0
        completed = (row["completed"] or 0) if row else 0
        results["completion_rate"] = round(completed / planned, 4) if planned > 0 else None
    except Exception:
        results["completion_rate"] = None

    # Early exit rate
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) as exits
            FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
        """).fetchone()
        total = (row["total"] or 0) if row else 0
        exits = (row["exits"] or 0) if row else 0
        results["early_exit_rate"] = round(exits / total, 4) if total > 0 else None
    except Exception:
        results["early_exit_rate"] = None

    return {"tree": CTQ_TREE, "measurements": results}


def calculate_error_pareto(conn, days: int = 30) -> Dict[str, Any]:
    """Pareto analysis of error types — rank by frequency, show cumulative %.

    Identifies the 20% of error types causing 80% of errors.
    Lean Six Sigma: vital few vs. trivial many.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    try:
        rows = conn.execute("""
            SELECT error_type, COUNT(*) as count
            FROM error_log
            WHERE created_at >= ?
            GROUP BY error_type
            ORDER BY count DESC
        """, (cutoff,)).fetchall()
    except Exception:
        return {"items": [], "total_errors": 0, "vital_few": [], "days": days}

    if not rows:
        return {"items": [], "total_errors": 0, "vital_few": [], "days": days}

    total = sum(r["count"] for r in rows)
    items = []
    cumulative = 0
    vital_few = []

    for r in rows:
        count = r["count"]
        pct = round(count / total * 100, 1) if total > 0 else 0
        cumulative += pct
        item = {
            "error_type": r["error_type"],
            "count": count,
            "percentage": pct,
            "cumulative_percentage": round(cumulative, 1),
        }
        items.append(item)
        if cumulative <= 80:
            vital_few.append(r["error_type"])

    return {
        "items": items,
        "total_errors": total,
        "vital_few": vital_few,
        "vital_few_pct": round(len(vital_few) / len(items) * 100, 1) if items else 0,
        "days": days,
    }


def generate_five_why_template(chart_type: str, violation_detail: str = "") -> Dict[str, Any]:
    """Generate a structured 5-Why root cause analysis template.

    Called when SPC detects an out-of-control point. Provides a framework
    for systematic investigation rather than ad-hoc debugging.
    """
    templates = {
        "drill_accuracy": {
            "problem_statement": f"Drill accuracy control chart is out of control. {violation_detail}",
            "whys": [
                {"level": 1, "question": "Why did accuracy drop?",
                 "possible_causes": ["New items too difficult", "Spacing intervals too long", "Drill type mismatch"],
                 "investigation": "Check error_log for dominant error types in last 7 days"},
                {"level": 2, "question": "Why were items too difficult / intervals too long?",
                 "possible_causes": ["HSK level gating too permissive", "Ease factor decay too aggressive", "Scheduler bug"],
                 "investigation": "Compare difficulty distribution of failed vs passed items"},
                {"level": 3, "question": "Why is the gating/scheduling producing this outcome?",
                 "possible_causes": ["Insufficient data for adaptive adjustment", "Config values need tuning", "Edge case in algorithm"],
                 "investigation": "Check config.py thresholds: NEW_BUDGET, BOUNCE_ERROR_RATE"},
                {"level": 4, "question": "Why weren't the thresholds catching this earlier?",
                 "possible_causes": ["SPC control limits too wide", "Sample size too small", "Metric definition issue"],
                 "investigation": "Review SPC chart history for trend before violation"},
                {"level": 5, "question": "What systemic gap allowed this?",
                 "possible_causes": ["No sensitivity analysis on key parameters", "Missing integration test", "No regression test"],
                 "investigation": "Add test coverage for the identified failure mode"},
            ],
        },
        "response_time": {
            "problem_statement": f"Response time control chart is out of control. {violation_detail}",
            "whys": [
                {"level": 1, "question": "Why did response times increase?",
                 "possible_causes": ["DB queries slowed", "Server load increased", "Network issue"],
                 "investigation": "Check request_timing for slowest endpoints"},
                {"level": 2, "question": "Why did queries slow down?",
                 "possible_causes": ["Missing index", "Table size grew", "Complex join"],
                 "investigation": "EXPLAIN QUERY PLAN on slow queries"},
                {"level": 3, "question": "Why was the index missing / table growing?",
                 "possible_causes": ["Schema migration gap", "No pruning policy", "Unexpected usage pattern"],
                 "investigation": "Check schema.sql indexes and data retention policy"},
                {"level": 4, "question": "Why wasn't this caught in testing?",
                 "possible_causes": ["Test data too small", "No load testing", "Performance not in CI"],
                 "investigation": "Review test fixtures for realistic data volume"},
                {"level": 5, "question": "What systemic gap allowed this?",
                 "possible_causes": ["No performance monitoring baseline", "No regression testing for latency"],
                 "investigation": "Add P95 latency assertion to test suite"},
            ],
        },
        "session_completion": {
            "problem_statement": f"Session completion control chart is out of control. {violation_detail}",
            "whys": [
                {"level": 1, "question": "Why are sessions not being completed?",
                 "possible_causes": ["Sessions too long", "Content too frustrating", "UI bug", "External factors"],
                 "investigation": "Check session_log: avg items_planned vs items_completed, early_exit rate"},
                {"level": 2, "question": "Why are sessions too long/frustrating?",
                 "possible_causes": ["Adaptive length not shrinking", "Too many new items", "Difficulty mismatch"],
                 "investigation": "Check scheduler adaptive_session_length, new_budget"},
                {"level": 3, "question": "Why isn't the scheduler adapting?",
                 "possible_causes": ["Not enough history", "Threshold too aggressive", "Day profile override"],
                 "investigation": "Check ADAPTIVE_LENGTH constants in config.py"},
                {"level": 4, "question": "Why weren't adaptive thresholds calibrated?",
                 "possible_causes": ["No sensitivity analysis", "Changed user behavior", "A/B test interference"],
                 "investigation": "Run sensitivity analysis on adaptive parameters"},
                {"level": 5, "question": "What systemic gap allowed this?",
                 "possible_causes": ["No completion rate SLO", "No alert threshold", "Manual override needed"],
                 "investigation": "Define completion rate SLO and add to monitoring"},
            ],
        },
    }

    template = templates.get(chart_type, {
        "problem_statement": f"Control chart violation: {chart_type}. {violation_detail}",
        "whys": [{"level": i, "question": f"Why? (level {i})", "possible_causes": [], "investigation": ""}
                 for i in range(1, 6)],
    })

    template["chart_type"] = chart_type
    template["generated_at"] = datetime.now(timezone.utc).isoformat()

    return template


def _safe_median(values: List[float]) -> float:
    """Median of a sorted-able list. Returns 0.0 if empty."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _percentile(values: List[float], p: float) -> float:
    """Single percentile from a list. p in [0, 100]."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    k = (p / 100) * (n - 1)
    lo = int(k)
    hi = min(lo + 1, n - 1)
    frac = k - lo
    return s[lo] + frac * (s[hi] - s[lo])


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return (row["cnt"] if row else 0) > 0


def calculate_cycle_time(conn, days: int = 90) -> Dict[str, Any]:
    """Cycle time analysis from work_item table.

    cycle_time = completed_at - started_at (in hours) for completed items.
    Returns mean, median, p85, p95, count, by_type breakdown.
    """
    if not _table_exists(conn, "work_item"):
        logger.info("work_item table does not exist yet")
        return {
            "mean": 0.0,
            "median": 0.0,
            "p85": 0.0,
            "p95": 0.0,
            "count": 0,
            "by_type": {},
        }

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = conn.execute(
        """
        SELECT
            (julianday(completed_at) - julianday(started_at)) * 24.0 AS cycle_hours,
            COALESCE(service_class, 'standard') AS sclass
        FROM work_item
        WHERE completed_at IS NOT NULL
          AND started_at IS NOT NULL
          AND completed_at >= ?
        """,
        (cutoff,),
    ).fetchall()

    if not rows:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p85": 0.0,
            "p95": 0.0,
            "count": 0,
            "by_type": {},
        }

    all_times = [float(r["cycle_hours"]) for r in rows if r["cycle_hours"] is not None]

    # By service class
    by_type: Dict[str, Dict[str, Any]] = {}
    type_groups: Dict[str, List[float]] = {}
    for r in rows:
        if r["cycle_hours"] is None:
            continue
        sc = r["sclass"]
        type_groups.setdefault(sc, []).append(float(r["cycle_hours"]))

    for sc, times in type_groups.items():
        by_type[sc] = {
            "mean": round(sum(times) / len(times), 2),
            "median": round(_safe_median(times), 2),
            "count": len(times),
        }

    return {
        "mean": round(sum(all_times) / len(all_times), 2) if all_times else 0.0,
        "median": round(_safe_median(all_times), 2),
        "p85": round(_percentile(all_times, 85), 2),
        "p95": round(_percentile(all_times, 95), 2),
        "count": len(all_times),
        "by_type": by_type,
    }


def calculate_lead_time(conn, days: int = 90) -> Dict[str, Any]:
    """Lead time analysis from work_item table.

    lead_time = completed_at - ready_at (in hours) for completed items.
    """
    if not _table_exists(conn, "work_item"):
        logger.info("work_item table does not exist yet")
        return {"mean": 0.0, "median": 0.0, "p85": 0.0, "p95": 0.0, "count": 0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = conn.execute(
        """
        SELECT (julianday(completed_at) - julianday(ready_at)) * 24.0 AS lead_hours
        FROM work_item
        WHERE completed_at IS NOT NULL
          AND ready_at IS NOT NULL
          AND completed_at >= ?
        """,
        (cutoff,),
    ).fetchall()

    times = [float(r["lead_hours"]) for r in rows if r["lead_hours"] is not None]

    if not times:
        return {"mean": 0.0, "median": 0.0, "p85": 0.0, "p95": 0.0, "count": 0}

    return {
        "mean": round(sum(times) / len(times), 2),
        "median": round(_safe_median(times), 2),
        "p85": round(_percentile(times, 85), 2),
        "p95": round(_percentile(times, 95), 2),
        "count": len(times),
    }


def calculate_throughput(conn, days: int = 30) -> Dict[str, Any]:
    """Throughput: items completed per day and per week.

    Returns daily_avg, weekly_avg, by_type breakdown.
    """
    if not _table_exists(conn, "work_item"):
        logger.info("work_item table does not exist yet")
        return {"daily_avg": 0.0, "weekly_avg": 0.0, "by_type": {}}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = conn.execute(
        """
        SELECT DATE(completed_at) AS day,
               COALESCE(service_class, 'standard') AS sclass,
               COUNT(*) AS cnt
        FROM work_item
        WHERE completed_at IS NOT NULL AND completed_at >= ?
        GROUP BY DATE(completed_at), service_class
        ORDER BY day
        """,
        (cutoff,),
    ).fetchall()

    if not rows:
        return {"daily_avg": 0.0, "weekly_avg": 0.0, "by_type": {}}

    # Daily totals
    daily_totals: Dict[str, int] = {}
    type_totals: Dict[str, int] = {}
    for r in rows:
        day = r["day"]
        daily_totals[day] = daily_totals.get(day, 0) + r["cnt"]
        sc = r["sclass"]
        type_totals[sc] = type_totals.get(sc, 0) + r["cnt"]

    n_days = max(len(daily_totals), 1)
    total = sum(daily_totals.values())
    daily_avg = total / n_days
    weekly_avg = daily_avg * 7

    by_type = {}
    for sc, cnt in type_totals.items():
        by_type[sc] = {
            "total": cnt,
            "daily_avg": round(cnt / n_days, 2),
        }

    return {
        "daily_avg": round(daily_avg, 2),
        "weekly_avg": round(weekly_avg, 2),
        "by_type": by_type,
    }


# Service class cycle time targets (hours)
SERVICE_CLASS_TARGETS = {
    "expedite": {"target_hours": 24, "max_hours": 48, "label": "Expedite (drop everything)"},
    "fixed_date": {"target_hours": 72, "max_hours": 168, "label": "Fixed date (deadline-driven)"},
    "standard": {"target_hours": 168, "max_hours": 336, "label": "Standard (first-in-first-out)"},
    "intangible": {"target_hours": 336, "max_hours": 672, "label": "Intangible (when capacity allows)"},
}


def assess_service_class_compliance(conn, days: int = 90) -> Dict[str, Any]:
    """Check cycle time compliance against service class targets.

    Returns per-class stats: count, avg_cycle_hours, target_hours, violations.
    """
    if not _table_exists(conn, "work_item"):
        return {"classes": {}, "overall_compliance": 1.0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(service_class, 'standard') AS sclass,
                (julianday(completed_at) - julianday(started_at)) * 24.0 AS cycle_hours
            FROM work_item
            WHERE completed_at IS NOT NULL
              AND started_at IS NOT NULL
              AND completed_at >= ?
            """,
            (cutoff,),
        ).fetchall()
    except Exception:
        return {"classes": {}, "overall_compliance": 1.0}

    classes: Dict[str, Dict[str, Any]] = {}
    total_items = 0
    total_compliant = 0

    for r in rows:
        sc = r["sclass"]
        hours = float(r["cycle_hours"]) if r["cycle_hours"] is not None else 0.0
        target = SERVICE_CLASS_TARGETS.get(sc, SERVICE_CLASS_TARGETS["standard"])

        if sc not in classes:
            classes[sc] = {
                "count": 0,
                "total_hours": 0.0,
                "violations": 0,
                "target_hours": target["target_hours"],
                "max_hours": target["max_hours"],
                "label": target["label"],
            }

        classes[sc]["count"] += 1
        classes[sc]["total_hours"] += hours
        total_items += 1

        if hours <= target["max_hours"]:
            total_compliant += 1
        else:
            classes[sc]["violations"] += 1

    for sc, data in classes.items():
        if data["count"] > 0:
            data["avg_hours"] = round(data["total_hours"] / data["count"], 2)
        else:
            data["avg_hours"] = 0.0
        del data["total_hours"]

    compliance = total_compliant / total_items if total_items > 0 else 1.0

    return {
        "classes": classes,
        "overall_compliance": round(compliance, 4),
        "total_items": total_items,
    }


def calculate_velocity(conn, weeks: int = 12) -> Dict[str, Any]:
    """Compute items completed per week over last N weeks.

    Solo-adapted Scrum velocity tracking.
    Returns weekly_velocity list, average, trend.
    """
    if not _table_exists(conn, "work_item"):
        return {"weekly": [], "average": 0.0, "trend": "stable"}

    now = datetime.now(timezone.utc)
    weekly: List[Dict[str, Any]] = []

    for i in range(weeks - 1, -1, -1):
        week_end = now - timedelta(weeks=i)
        week_start = week_end - timedelta(weeks=1)

        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM work_item
                WHERE completed_at IS NOT NULL
                  AND completed_at >= ? AND completed_at < ?
                """,
                (week_start.isoformat(), week_end.isoformat()),
            ).fetchone()
            count = (row["cnt"] if row else 0) or 0
        except Exception:
            count = 0

        weekly.append({
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": week_end.strftime("%Y-%m-%d"),
            "completed": count,
        })

    counts = [w["completed"] for w in weekly]
    avg = sum(counts) / len(counts) if counts else 0.0

    # Simple trend: compare last 4 weeks to previous 4
    if len(counts) >= 8:
        recent = sum(counts[-4:]) / 4
        prior = sum(counts[-8:-4]) / 4
        if recent > prior * 1.2:
            trend = "increasing"
        elif recent < prior * 0.8:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {
        "weekly": weekly,
        "average": round(avg, 2),
        "trend": trend,
        "weeks": weeks,
    }


def get_flow_summary(conn) -> Dict[str, Any]:
    """Combined flow metrics."""
    return {
        "cycle_time": calculate_cycle_time(conn),
        "lead_time": calculate_lead_time(conn),
        "throughput": calculate_throughput(conn),
        "service_class_compliance": assess_service_class_compliance(conn),
        "velocity": calculate_velocity(conn),
    }


def get_cfd_data(conn, days: int = 30) -> Dict[str, Any]:
    """Cumulative flow diagram data: daily counts by status.

    Statuses: backlog, ready, in_progress, review, done.
    Returns {dates: [...], series: {status: [counts]}}.
    """
    if not _table_exists(conn, "work_item"):
        logger.info("work_item table does not exist yet")
        return {"dates": [], "series": {}}

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    # Generate date range
    dates: List[str] = []
    current = start
    while current <= now:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    statuses = ["backlog", "ready", "in_progress", "review", "done"]
    series: Dict[str, List[int]] = {s: [] for s in statuses}

    for date_str in dates:
        # End of the given day
        as_of = date_str + "T23:59:59"

        for status in statuses:
            if status == "done":
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM work_item
                    WHERE completed_at IS NOT NULL AND completed_at <= ?
                    """,
                    (as_of,),
                ).fetchone()
            elif status == "backlog":
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM work_item
                    WHERE created_at <= ?
                      AND (ready_at IS NULL OR ready_at > ?)
                    """,
                    (as_of, as_of),
                ).fetchone()
            elif status == "ready":
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM work_item
                    WHERE ready_at IS NOT NULL AND ready_at <= ?
                      AND (started_at IS NULL OR started_at > ?)
                    """,
                    (as_of, as_of),
                ).fetchone()
            elif status == "in_progress":
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM work_item
                    WHERE started_at IS NOT NULL AND started_at <= ?
                      AND (completed_at IS NULL OR completed_at > ?)
                      AND (review_at IS NULL OR review_at > ?)
                    """,
                    (as_of, as_of, as_of),
                ).fetchone()
            elif status == "review":
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM work_item
                    WHERE review_at IS NOT NULL AND review_at <= ?
                      AND (completed_at IS NULL OR completed_at > ?)
                    """,
                    (as_of, as_of),
                ).fetchone()
            else:
                row = None

            series[status].append((row["cnt"] if row else 0) or 0)

    return {
        "dates": dates,
        "series": series,
    }
