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


# ═══════════════════════════════════════════════════════════════════════
# Cox Proportional Hazards — multivariate survival regression
# ═══════════════════════════════════════════════════════════════════════


def cox_proportional_hazards(
    conn,
    covariates: list[str] | None = None,
    churn_days: int = _CHURN_THRESHOLD_DAYS,
) -> dict:
    """Semi-parametric Cox regression for identifying churn risk factors.

    Partial likelihood estimation via Newton-Raphson.
    Returns hazard ratios with 95% CI and p-values per covariate.

    Example output: "Users with accuracy <60% have 2.3x higher churn hazard"
    """
    if covariates is None:
        covariates = ["sessions_per_week", "avg_accuracy", "items_mastered"]

    try:
        rows = conn.execute(
            """
            SELECT u.id AS user_id,
                   u.created_at,
                   (SELECT MAX(sl.started_at) FROM session_log sl WHERE sl.user_id = u.id) AS last_session,
                   (SELECT COUNT(*) FROM session_log sl2 WHERE sl2.user_id = u.id
                    AND sl2.started_at >= datetime('now', '-30 days')) AS sessions_30d,
                   (SELECT AVG(CASE WHEN re.correct THEN 1.0 ELSE 0.0 END)
                    FROM review_event re WHERE re.user_id = u.id) AS avg_accuracy,
                   (SELECT COUNT(*) FROM progress p WHERE p.user_id = u.id
                    AND p.mastery_stage IN ('stable', 'durable')) AS items_mastered
            FROM user u
            WHERE u.created_at IS NOT NULL
            LIMIT 500
            """
        ).fetchall()
    except Exception:
        return {"error": "Could not query user data", "coefficients": {}}

    if len(rows) < 10:
        return {"error": "Insufficient data", "n_users": len(rows), "coefficients": {}}

    # Build survival data: (time, event, covariates)
    now = datetime.now(UTC)
    survival_data = []

    for r in rows:
        try:
            created = datetime.fromisoformat(r["created_at"]).replace(tzinfo=UTC)
            if r["last_session"]:
                last = datetime.fromisoformat(r["last_session"]).replace(tzinfo=UTC)
                days_since_last = (now - last).days
                event = 1 if days_since_last >= churn_days else 0
                time_days = max(1, (last - created).days) if event else max(1, (now - created).days)
            else:
                event = 1  # Never had a session = churned immediately
                time_days = max(1, (now - created).days)

            # Covariate vector
            x = []
            for cov in covariates:
                if cov == "sessions_per_week":
                    weeks = max(1, time_days / 7)
                    x.append((r["sessions_30d"] or 0) / weeks * (30 / 7))  # normalize to per-week
                elif cov == "avg_accuracy":
                    x.append(r["avg_accuracy"] or 0.5)
                elif cov == "items_mastered":
                    x.append(min((r["items_mastered"] or 0) / 50.0, 1.0))  # normalize
                else:
                    x.append(0.0)

            survival_data.append((time_days, event, x))
        except (ValueError, TypeError):
            continue

    if len(survival_data) < 10:
        return {"error": "Insufficient valid data", "coefficients": {}}

    # Sort by time (descending for risk set computation)
    survival_data.sort(key=lambda d: d[0])

    n_covariates = len(covariates)

    # Newton-Raphson for partial likelihood
    beta = [0.0] * n_covariates

    for iteration in range(30):
        gradient = [0.0] * n_covariates
        hessian = [[0.0] * n_covariates for _ in range(n_covariates)]

        # Compute risk sets and partial likelihood derivatives
        risk_sum = 0.0
        risk_weighted = [0.0] * n_covariates
        risk_weighted_sq = [[0.0] * n_covariates for _ in range(n_covariates)]

        # Reverse iterate (build risk set from the end)
        for i in range(len(survival_data) - 1, -1, -1):
            time_i, event_i, x_i = survival_data[i]

            # exp(beta . x)
            lin_pred = sum(beta[j] * x_i[j] for j in range(n_covariates))
            lin_pred = max(-20, min(20, lin_pred))
            exp_bx = math.exp(lin_pred)

            risk_sum += exp_bx
            for j in range(n_covariates):
                risk_weighted[j] += exp_bx * x_i[j]
                for k in range(n_covariates):
                    risk_weighted_sq[j][k] += exp_bx * x_i[j] * x_i[k]

            if event_i == 1 and risk_sum > 0:
                for j in range(n_covariates):
                    gradient[j] += x_i[j] - risk_weighted[j] / risk_sum
                    for k in range(n_covariates):
                        hessian[j][k] -= (
                            risk_weighted_sq[j][k] / risk_sum
                            - (risk_weighted[j] * risk_weighted[k]) / (risk_sum ** 2)
                        )

        # Newton step: beta -= H^(-1) * g
        # For simplicity, use diagonal Hessian approximation
        max_step = 0.0
        for j in range(n_covariates):
            if abs(hessian[j][j]) > 1e-10:
                step = gradient[j] / (-hessian[j][j])
                step = max(-1.0, min(1.0, step))  # clamp step size
                beta[j] += step
                max_step = max(max_step, abs(step))

        if max_step < 0.001:
            break

    # Compute hazard ratios and standard errors
    coefficients = {}
    for j, cov in enumerate(covariates):
        se = 1.0 / math.sqrt(max(abs(hessian[j][j]), 1e-10))
        hr = math.exp(beta[j])
        hr_lower = math.exp(beta[j] - 1.96 * se)
        hr_upper = math.exp(beta[j] + 1.96 * se)
        z = beta[j] / max(se, 1e-10)
        p_value = 2 * _norm_sf(abs(z))

        coefficients[cov] = {
            "beta": round(beta[j], 4),
            "hazard_ratio": round(hr, 4),
            "ci_95": [round(hr_lower, 4), round(hr_upper, 4)],
            "se": round(se, 4),
            "z": round(z, 4),
            "p_value": round(p_value, 6),
            "interpretation": (
                f"{'Higher' if beta[j] > 0 else 'Lower'} {cov} → "
                f"{'higher' if beta[j] > 0 else 'lower'} churn risk "
                f"(HR={hr:.2f}, p={p_value:.3f})"
            ),
        }

    return {
        "coefficients": coefficients,
        "n_users": len(survival_data),
        "n_events": sum(1 for _, e, _ in survival_data if e == 1),
        "covariates": covariates,
    }


def log_rank_test(conn, group_var: str = "subscription_tier") -> dict:
    """Compare survival curves between groups using log-rank test.

    Returns chi-squared statistic, df, and p-value.
    """
    try:
        rows = conn.execute(
            f"""
            SELECT u.{group_var} AS grp,
                   u.created_at,
                   (SELECT MAX(sl.started_at) FROM session_log sl WHERE sl.user_id = u.id) AS last_session
            FROM user u
            WHERE u.created_at IS NOT NULL AND u.{group_var} IS NOT NULL
            LIMIT 500
            """
        ).fetchall()
    except Exception:
        return {"error": f"Could not query {group_var}"}

    if len(rows) < 10:
        return {"error": "Insufficient data"}

    now = datetime.now(UTC)
    groups: dict[str, list[tuple[int, int]]] = {}  # group -> [(time, event)]

    for r in rows:
        try:
            grp = str(r["grp"])
            created = datetime.fromisoformat(r["created_at"]).replace(tzinfo=UTC)
            if r["last_session"]:
                last = datetime.fromisoformat(r["last_session"]).replace(tzinfo=UTC)
                days = max(1, (now - last).days)
                event = 1 if days >= _CHURN_THRESHOLD_DAYS else 0
                time = max(1, (last - created).days) if event else max(1, (now - created).days)
            else:
                event = 1
                time = max(1, (now - created).days)
            groups.setdefault(grp, []).append((time, event))
        except (ValueError, TypeError):
            continue

    if len(groups) < 2:
        return {"error": "Need at least 2 groups"}

    # Compute log-rank statistic
    # Pool all event times
    all_times = set()
    for g_data in groups.values():
        for t, e in g_data:
            if e == 1:
                all_times.add(t)

    sorted_times = sorted(all_times)

    group_names = list(groups.keys())
    observed = {g: 0 for g in group_names}
    expected = {g: 0.0 for g in group_names}

    for t in sorted_times:
        # At risk and events at time t
        n_total = 0
        d_total = 0
        n_by_group = {}
        d_by_group = {}

        for g in group_names:
            at_risk = sum(1 for ti, _ in groups[g] if ti >= t)
            events = sum(1 for ti, ei in groups[g] if ti == t and ei == 1)
            n_by_group[g] = at_risk
            d_by_group[g] = events
            n_total += at_risk
            d_total += events

        if n_total == 0:
            continue

        for g in group_names:
            observed[g] += d_by_group[g]
            expected[g] += n_by_group[g] * d_total / n_total

    # Chi-squared statistic
    chi2 = sum(
        (observed[g] - expected[g]) ** 2 / max(expected[g], 1e-10)
        for g in group_names
    )
    df = len(group_names) - 1

    # p-value (chi-squared approximation)
    if df > 0 and chi2 > 0:
        z = ((chi2 / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
        p_value = _norm_sf(z) if z > 0 else 1.0
    else:
        p_value = 1.0

    return {
        "chi2": round(chi2, 4),
        "df": df,
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
        "groups": {
            g: {"observed": observed[g], "expected": round(expected[g], 2),
                "n": len(groups[g])}
            for g in group_names
        },
        "interpretation": (
            f"Significant difference in survival between {group_var} groups (p={p_value:.3f})"
            if p_value < 0.05
            else f"No significant difference in survival between {group_var} groups (p={p_value:.3f})"
        ),
    }


def fit_weibull(conn, churn_days: int = _CHURN_THRESHOLD_DAYS) -> dict:
    """Fit Weibull distribution to time-to-churn.

    Returns shape (k) and scale (λ) parameters.
    Shape >1: increasing hazard (users more likely to churn over time)
    Shape <1: decreasing hazard (early dropoff, survivors stay)
    Shape =1: constant hazard (exponential)
    """
    try:
        rows = conn.execute(
            """
            SELECT u.created_at,
                   (SELECT MAX(sl.started_at) FROM session_log sl WHERE sl.user_id = u.id) AS last_session
            FROM user u
            WHERE u.created_at IS NOT NULL
            LIMIT 500
            """
        ).fetchall()
    except Exception:
        return {"error": "Could not query data"}

    now = datetime.now(UTC)
    times = []

    for r in rows:
        try:
            created = datetime.fromisoformat(r["created_at"]).replace(tzinfo=UTC)
            if r["last_session"]:
                last = datetime.fromisoformat(r["last_session"]).replace(tzinfo=UTC)
                days = max(1, (last - created).days)
                if (now - last).days >= churn_days:
                    times.append(days)
            else:
                times.append(max(1, (now - created).days))
        except (ValueError, TypeError):
            continue

    if len(times) < 10:
        return {"error": "Insufficient churn data"}

    # MLE for Weibull: k (shape), λ (scale)
    # Method: iterative MLE using Newton-Raphson on k
    n = len(times)
    log_times = [math.log(max(t, 0.1)) for t in times]
    _mean_log = sum(log_times) / n  # noqa: F841

    # Initial k estimate from method of moments
    mean_t = sum(times) / n
    var_t = sum((t - mean_t) ** 2 for t in times) / max(n - 1, 1)
    cv = math.sqrt(var_t) / max(mean_t, 1e-10)
    k = max(0.1, 1.0 / max(cv, 0.01))

    # Newton-Raphson for shape parameter
    for _ in range(50):
        tk = [t ** k for t in times]
        sum_tk = sum(tk)
        sum_tk_log = sum(tk_i * log_times[i] for i, tk_i in enumerate(tk))

        if sum_tk < 1e-10:
            break

        f = n / k + sum(log_times) - n * sum_tk_log / sum_tk
        # Approximate derivative
        f_prime = -n / (k ** 2) - n * (
            sum(tk_i * log_times[i] ** 2 for i, tk_i in enumerate(tk)) * sum_tk
            - sum_tk_log ** 2
        ) / (sum_tk ** 2)

        if abs(f_prime) < 1e-10:
            break
        step = f / f_prime
        k -= max(-0.5, min(0.5, step))
        k = max(0.01, min(50.0, k))

        if abs(step) < 0.001:
            break

    # Scale parameter
    lam = (sum(t ** k for t in times) / n) ** (1 / k)

    # Median survival time
    median = lam * (math.log(2)) ** (1 / k)

    return {
        "shape": round(k, 4),
        "scale": round(lam, 4),
        "median_survival_days": round(median, 1),
        "n_events": n,
        "hazard_type": (
            "increasing" if k > 1.1 else
            "decreasing" if k < 0.9 else
            "constant"
        ),
        "interpretation": (
            f"Shape={k:.2f}: {'Users become more likely to leave over time' if k > 1.1 else 'Early dropoff — survivors tend to stay' if k < 0.9 else 'Constant hazard — churn is random'}. "
            f"Median survival: {median:.0f} days."
        ),
    }


def _norm_sf(z: float) -> float:
    """Standard normal survival function."""
    if z < -8:
        return 1.0
    if z > 8:
        return 0.0
    if z < 0:
        return 1.0 - _norm_sf(-z)
    p = 0.2316419
    b1, b2, b3, b4, b5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
    t = 1.0 / (1.0 + p * z)
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return pdf * t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))))
