"""Survival analysis for learner retention — Kaplan-Meier, cohorts, churn risk."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# A user is considered churned if they have no session for this many days.
_CHURN_THRESHOLD_DAYS = 14


def _pearson_r(xs: list[float], ys: list[float]) -> float | None:
    """Basic Pearson correlation coefficient. Returns None if undefined."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return None
    return cov / denom


def _build_user_timelines(conn, days: int) -> list[dict[str, Any]]:
    """Build per-user timeline data for survival analysis.

    Returns list of dicts: user_id, first_session, last_session,
    observation_time (days), event (1=churned, 0=censored).
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    now = datetime.now(UTC)

    rows = conn.execute(
        """
        SELECT u.id AS user_id,
               u.first_session_at,
               MAX(s.started_at) AS last_session
        FROM user u
        LEFT JOIN session_log s ON s.user_id = u.id
        WHERE u.first_session_at IS NOT NULL
          AND u.first_session_at >= ?
        GROUP BY u.id
        """,
        (cutoff,),
    ).fetchall()

    timelines = []
    for r in rows:
        first = r["first_session_at"]
        last = r["last_session"]

        if not first:
            continue

        # Parse dates — handle both ISO and other common formats
        try:
            first_dt = datetime.fromisoformat(first.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                last_dt = first_dt
        else:
            last_dt = first_dt

        # Make both offset-aware for comparison
        if first_dt.tzinfo is None:
            first_dt = first_dt.replace(tzinfo=UTC)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)

        days_since_last = (now - last_dt).total_seconds() / 86400
        churned = days_since_last >= _CHURN_THRESHOLD_DAYS

        if churned:
            # Observation time = days from first session to last session + threshold
            obs_time = (last_dt - first_dt).total_seconds() / 86400
        else:
            # Censored — observation time = days from first session to now
            obs_time = (now - first_dt).total_seconds() / 86400

        obs_time = max(obs_time, 0.0)

        timelines.append({
            "user_id": r["user_id"],
            "first_session": first,
            "last_session": last,
            "observation_time": obs_time,
            "event": 1 if churned else 0,
        })

    return timelines


def _kaplan_meier_from_timelines(
    timelines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute Kaplan-Meier survival curve from timeline data."""
    if not timelines:
        return {
            "time_points": [],
            "survival_probabilities": [],
            "n_at_risk": [],
            "n_events": [],
            "n_censored": [],
            "median_survival": None,
        }

    # Collect event times, sorted
    events: list[tuple[float, int]] = []  # (time, event_flag)
    for t in timelines:
        events.append((t["observation_time"], t["event"]))

    events.sort(key=lambda x: x[0])

    # Distinct time points where events (churns) occur
    event_times: list[float] = sorted(set(
        time for time, event in events if event == 1
    ))

    n_total = len(events)
    time_points: list[float] = []
    survival_probs: list[float] = []
    n_at_risk_list: list[int] = []
    n_events_list: list[int] = []
    n_censored_list: list[int] = []

    survival = 1.0
    idx = 0  # pointer into sorted events

    for t in event_times:
        # Count censored before this time
        censored_before = 0
        while idx < len(events) and events[idx][0] < t:
            if events[idx][1] == 0:
                censored_before += 1
            idx += 1

        # n at risk at time t
        n_at_risk = n_total
        # Subtract those who had events or were censored before time t
        for time_val, _event_flag in events:
            if time_val < t:
                n_at_risk -= 1

        # Count events at this time
        d = sum(1 for time_val, ev in events if time_val == t and ev == 1)
        c = sum(1 for time_val, ev in events if time_val == t and ev == 0)

        if n_at_risk > 0:
            survival *= (1 - d / n_at_risk)

        time_points.append(round(t, 1))
        survival_probs.append(round(survival, 6))
        n_at_risk_list.append(n_at_risk)
        n_events_list.append(d)
        n_censored_list.append(c)

    # Median survival = first time where survival <= 0.5
    median = None
    for tp, sp in zip(time_points, survival_probs, strict=False):
        if sp <= 0.5:
            median = tp
            break

    return {
        "time_points": time_points,
        "survival_probabilities": survival_probs,
        "n_at_risk": n_at_risk_list,
        "n_events": n_events_list,
        "n_censored": n_censored_list,
        "median_survival": median,
    }


def kaplan_meier(conn, days: int = 90) -> dict[str, Any]:
    """Kaplan-Meier survival analysis for learner retention.

    Event = user churns (no session for 14+ consecutive days).
    Censored = user still active.
    Time = days from first_session_at.
    """
    timelines = _build_user_timelines(conn, days)
    return _kaplan_meier_from_timelines(timelines)


def retention_by_cohort(
    conn, cohort_type: str = "weekly"
) -> list[dict[str, Any]]:
    """Separate Kaplan-Meier curves grouped by signup cohort.

    cohort_type: 'weekly' groups by ISO week of first_session_at.
    Returns list of dicts with cohort_label and survival data.
    """
    # Get all users with first sessions
    timelines = _build_user_timelines(conn, days=365)

    if not timelines:
        return []

    # Group by cohort
    cohorts: dict[str, list[dict[str, Any]]] = {}
    for t in timelines:
        first = t["first_session"]
        try:
            dt = datetime.fromisoformat(first.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if cohort_type == "weekly":
            iso = dt.isocalendar()
            label = f"{iso[0]}-W{iso[1]:02d}"
        else:
            label = dt.strftime("%Y-%m")

        cohorts.setdefault(label, []).append(t)

    results = []
    for label in sorted(cohorts.keys()):
        km = _kaplan_meier_from_timelines(cohorts[label])
        km["cohort_label"] = label
        km["cohort_size"] = len(cohorts[label])
        results.append(km)

    return results


def churn_risk_factors(conn) -> dict[str, Any]:
    """Analyze correlations between user behavior features and churn.

    Features: avg sessions per week, avg drill accuracy,
    avg time between sessions.
    Returns Pearson r for each feature vs. churned (0/1).
    """
    timelines = _build_user_timelines(conn, days=365)
    if len(timelines) < 5:
        return {"n_users": len(timelines), "factors": {}}

    [t["user_id"] for t in timelines]
    churn_flags = [float(t["event"]) for t in timelines]

    # Feature 1: sessions per week
    sessions_per_week: list[float] = []
    # Feature 2: avg accuracy
    avg_accuracy: list[float] = []

    for t in timelines:
        uid = t["user_id"]
        obs_weeks = max(t["observation_time"] / 7.0, 1.0)

        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt,
                   AVG(CASE WHEN items_completed > 0
                        THEN CAST(items_correct AS REAL) / items_completed
                        ELSE NULL END) AS avg_acc
            FROM session_log
            WHERE user_id = ?
            """,
            (uid,),
        ).fetchone()

        cnt = (row["cnt"] if row else 0) or 0
        acc = (row["avg_acc"] if row else None)

        sessions_per_week.append(cnt / obs_weeks)
        avg_accuracy.append(acc if acc is not None else 0.0)

    factors: dict[str, Any] = {}

    r_spw = _pearson_r(sessions_per_week, churn_flags)
    if r_spw is not None:
        factors["sessions_per_week"] = {
            "pearson_r": round(r_spw, 4),
            "interpretation": (
                "Negative = more sessions → less churn"
                if r_spw < 0
                else "Positive = more sessions → more churn (unexpected)"
            ),
        }

    r_acc = _pearson_r(avg_accuracy, churn_flags)
    if r_acc is not None:
        factors["avg_drill_accuracy"] = {
            "pearson_r": round(r_acc, 4),
            "interpretation": (
                "Negative = higher accuracy → less churn"
                if r_acc < 0
                else "Positive = higher accuracy → more churn (unexpected)"
            ),
        }

    return {
        "n_users": len(timelines),
        "factors": factors,
    }
