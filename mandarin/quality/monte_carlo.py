"""Monte Carlo simulations — user growth, server load, review queue."""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _percentiles(values: list[float], ps: list[int]) -> dict[str, float]:
    """Compute percentiles from a sorted-able list."""
    if not values:
        return {f"p{p}": 0.0 for p in ps}
    s = sorted(values)
    n = len(s)
    result = {}
    for p in ps:
        k = (p / 100) * (n - 1)
        lo = int(math.floor(k))
        hi = min(lo + 1, n - 1)
        frac = k - lo
        result[f"p{p}"] = round(s[lo] + frac * (s[hi] - s[lo]), 2)
    return result


def _normal_sample(mean: float, std: float, rng: random.Random) -> float:
    """Sample from normal distribution using Box-Muller."""
    if std <= 0:
        return mean
    u1 = rng.random()
    u2 = rng.random()
    # Avoid log(0)
    u1 = max(u1, 1e-10)
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return mean + std * z


def simulate_user_growth(
    conn, months: int = 12, n_simulations: int = 10000
) -> dict[str, Any]:
    """Monte Carlo simulation of user growth over future months.

    Uses current monthly signup rate and observed variance.
    Applies monthly churn rate based on recent data.
    """
    now = datetime.now(UTC)

    # Gather monthly signup counts for the last 6 months
    monthly_signups: list[float] = []
    for i in range(6, 0, -1):
        start = (now - timedelta(days=30 * i)).isoformat()
        end = (now - timedelta(days=30 * (i - 1))).isoformat()
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM user
            WHERE created_at >= ? AND created_at < ?
            """,
            (start, end),
        ).fetchone()
        monthly_signups.append(float((row["cnt"] if row else 0) or 0))

    if not monthly_signups or sum(monthly_signups) == 0:
        # No signup data — use minimal defaults
        signup_mean = 1.0
        signup_std = 0.5
    else:
        signup_mean = sum(monthly_signups) / len(monthly_signups)
        if len(monthly_signups) > 1:
            variance = sum((x - signup_mean) ** 2 for x in monthly_signups) / (
                len(monthly_signups) - 1
            )
            signup_std = math.sqrt(variance)
        else:
            signup_std = signup_mean * 0.3  # Assume 30% CV

    # Estimate churn rate (fraction of users who churned last month)
    total_users_row = conn.execute("SELECT COUNT(*) AS cnt FROM user").fetchone()
    total_users = (total_users_row["cnt"] if total_users_row else 0) or 0

    churn_cutoff = (now - timedelta(days=14)).isoformat()
    active_row = conn.execute(
        """
        SELECT COUNT(DISTINCT user_id) AS cnt FROM session_log
        WHERE started_at >= ?
        """,
        (churn_cutoff,),
    ).fetchone()
    active_users = (active_row["cnt"] if active_row else 0) or 0

    if total_users > 0:
        monthly_churn_rate = max(0.0, 1.0 - (active_users / total_users))
    else:
        monthly_churn_rate = 0.05  # Default 5%

    rng = random.Random(42)

    # Run simulations
    final_totals: list[float] = []
    # Store monthly projections for percentile bands
    monthly_totals: list[list[float]] = [[] for _ in range(months)]

    for _ in range(n_simulations):
        current = float(total_users)
        for m in range(months):
            new = max(0, _normal_sample(signup_mean, signup_std, rng))
            churned = current * monthly_churn_rate
            current = max(0, current + new - churned)
            monthly_totals[m].append(current)
        final_totals.append(current)

    # Build monthly projection percentiles
    monthly_projections = []
    for m in range(months):
        pcts = _percentiles(monthly_totals[m], [5, 25, 50, 75, 95])
        pcts["month"] = m + 1
        monthly_projections.append(pcts)

    return {
        "percentiles": _percentiles(final_totals, [5, 25, 50, 75, 95]),
        "monthly_projections": monthly_projections,
        "assumptions": {
            "signup_mean": round(signup_mean, 2),
            "signup_std": round(signup_std, 2),
            "monthly_churn_rate": round(monthly_churn_rate, 4),
            "current_total_users": total_users,
            "n_simulations": n_simulations,
            "months_projected": months,
        },
    }


def simulate_server_load(
    conn, target_users: int, n_simulations: int = 10000
) -> dict[str, Any]:
    """Simulate concurrent session load for a target user count.

    Models concurrent sessions based on current usage patterns.
    SQLite practical limit ~100 concurrent connections.
    """
    now = datetime.now(UTC)
    cutoff = (now - timedelta(days=30)).isoformat()

    # Average sessions per user per day
    row = conn.execute(
        """
        SELECT COUNT(*) AS sessions,
               COUNT(DISTINCT user_id) AS users,
               AVG(duration_seconds) AS avg_dur
        FROM session_log
        WHERE started_at >= ?
        """,
        (cutoff,),
    ).fetchone()

    total_sessions = (row["sessions"] if row else 0) or 0
    distinct_users = (row["users"] if row else 0) or 1
    avg_duration_s = (row["avg_dur"] if row else 0) or 600  # Default 10 min

    sessions_per_user_per_day = (total_sessions / distinct_users / 30.0) if distinct_users > 0 else 1.0
    avg_duration_s / 3600.0

    # Active hours in a day (assume 16-hour window)
    active_hours = 16.0

    rng = random.Random(42)
    max_concurrent_list: list[float] = []
    avg_concurrent_list: list[float] = []

    for _ in range(n_simulations):
        # Each user starts a session with probability sessions_per_user_per_day
        # distributed over active hours. Duration ~ Normal(avg, avg*0.3).
        n_sessions_today = 0
        for _ in range(target_users):
            if rng.random() < sessions_per_user_per_day:
                n_sessions_today += 1

        if n_sessions_today == 0:
            max_concurrent_list.append(0)
            avg_concurrent_list.append(0)
            continue

        # Distribute start times uniformly over active_hours
        starts = [rng.uniform(0, active_hours) for _ in range(n_sessions_today)]
        durations = [
            max(60, _normal_sample(avg_duration_s, avg_duration_s * 0.3, rng))
            for _ in range(n_sessions_today)
        ]
        # Convert durations to hours
        dur_hours = [d / 3600.0 for d in durations]

        # Sweep to find max concurrent
        events: list[tuple[float, int]] = []
        for s, d in zip(starts, dur_hours, strict=False):
            events.append((s, 1))
            events.append((s + d, -1))
        events.sort()

        concurrent = 0
        max_c = 0
        total_concurrent_time = 0.0
        prev_time = 0.0

        for time, delta in events:
            total_concurrent_time += concurrent * (time - prev_time)
            prev_time = time
            concurrent += delta
            max_c = max(max_c, concurrent)

        avg_c = total_concurrent_time / active_hours if active_hours > 0 else 0
        max_concurrent_list.append(max_c)
        avg_concurrent_list.append(avg_c)

    p_overload = sum(1 for m in max_concurrent_list if m > 100) / n_simulations

    return {
        "p_overload": round(p_overload, 4),
        "avg_concurrent": round(sum(avg_concurrent_list) / len(avg_concurrent_list), 2),
        "max_concurrent": _percentiles(max_concurrent_list, [50, 95, 99]),
        "percentiles": _percentiles(max_concurrent_list, [5, 25, 50, 75, 95]),
        "target_users": target_users,
        "sqlite_limit": 100,
        "assumptions": {
            "sessions_per_user_per_day": round(sessions_per_user_per_day, 4),
            "avg_session_duration_s": round(avg_duration_s, 1),
            "active_hours_per_day": active_hours,
            "n_simulations": n_simulations,
        },
    }


def simulate_review_queue(
    conn,
    user_id: int | None = None,
    days: int = 30,
    n_simulations: int = 1000,
) -> dict[str, Any]:
    """Simulate daily review queue sizes based on current SRS patterns.

    Uses recent review rates and half-lives to project daily due items.
    """
    now = datetime.now(UTC)
    cutoff = (now - timedelta(days=30)).isoformat()

    # Get current queue characteristics
    user_filter = "AND user_id = ?" if user_id else ""
    params: list = [cutoff]
    if user_id:
        params.append(user_id)

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS total_reviews,
               COUNT(DISTINCT DATE(created_at)) AS active_days,
               COUNT(DISTINCT content_item_id) AS unique_items
        FROM review_event
        WHERE created_at >= ? {user_filter}
        """,
        params,
    ).fetchone()

    total_reviews = (row["total_reviews"] if row else 0) or 0
    active_days = (row["active_days"] if row else 0) or 1
    unique_items = (row["unique_items"] if row else 0) or 0

    reviews_per_day = total_reviews / active_days if active_days > 0 else 5.0

    # Estimate variance from daily counts
    daily_rows = conn.execute(
        f"""
        SELECT DATE(created_at) AS day, COUNT(*) AS cnt
        FROM review_event
        WHERE created_at >= ? {user_filter}
        GROUP BY DATE(created_at)
        ORDER BY day
        """,
        params,
    ).fetchall()

    daily_counts = [float(r["cnt"]) for r in daily_rows] if daily_rows else [reviews_per_day]

    if len(daily_counts) > 1:
        mean_dc = sum(daily_counts) / len(daily_counts)
        var_dc = sum((x - mean_dc) ** 2 for x in daily_counts) / (len(daily_counts) - 1)
        std_dc = math.sqrt(var_dc)
    else:
        mean_dc = reviews_per_day
        std_dc = reviews_per_day * 0.3

    rng = random.Random(42)

    # Simulate daily review counts over the projection period
    daily_projections: list[list[float]] = [[] for _ in range(days)]

    for _ in range(n_simulations):
        # Slight growth factor: items accumulate over time
        float(unique_items) if unique_items > 0 else 10.0
        for d in range(days):
            # Growth: ~1 new item every 2 days
            growth = d * 0.5
            day_mean = mean_dc + growth * 0.1
            count = max(0, _normal_sample(day_mean, std_dc, rng))
            daily_projections[d].append(count)

    # Aggregate
    daily_review_counts = []
    for d in range(days):
        pcts = _percentiles(daily_projections[d], [5, 50, 95])
        pcts["day"] = d + 1
        daily_review_counts.append(pcts)

    all_maxes = [max(daily_projections[d]) for d in range(days)]
    max_queue = max(all_maxes) if all_maxes else 0.0

    return {
        "daily_review_counts": daily_review_counts,
        "max_queue_size": round(max_queue, 1),
        "assumptions": {
            "current_reviews_per_day": round(mean_dc, 2),
            "std_reviews_per_day": round(std_dc, 2),
            "unique_items_in_rotation": unique_items,
            "user_id": user_id,
            "days_projected": days,
            "n_simulations": n_simulations,
        },
    }
