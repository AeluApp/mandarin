"""Analysis engine — experiment results computation with CUPED variance reduction.

Performs user-level analysis (not session-level) to avoid Simpson's paradox.
Supports CUPED (Controlled-experiment Using Pre-Experiment Data) for variance
reduction, which can improve power by 20-40%.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

logger = logging.getLogger(__name__)


def get_experiment_results(
    conn: sqlite3.Connection,
    experiment_name: str,
    *,
    use_cuped: bool = True,
) -> dict:
    """Compute per-variant metrics for an experiment.

    Performs user-level analysis.  If ``use_cuped`` is True and pre-period data
    is available, applies CUPED variance reduction to the primary metric
    (completion rate).

    Returns::

        {
            experiment_name, status, variants: {variant: {users, sessions, ...}},
            p_value, effect_size, significant, min_sample_met,
            ci_95, cuped_applied, cuped_variance_reduction
        }
    """
    try:
        exp = conn.execute(
            "SELECT id, name, status, variants, min_sample_size, guardrail_metrics "
            "FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"experiment_name": experiment_name, "error": "experiment table not found"}

    if not exp:
        return {"experiment_name": experiment_name, "error": "experiment not found"}

    experiment_id = exp["id"]
    variant_names = json.loads(exp["variants"])
    min_sample = exp["min_sample_size"] or 100

    result = {
        "experiment_name": experiment_name,
        "status": exp["status"],
        "min_sample_size": min_sample,
        "variants": {},
        "p_value": None,
        "effect_size": None,
        "significant": False,
        "min_sample_met": False,
        "cuped_applied": False,
    }

    # ── Per-variant metrics ──────────────────────────────────────────────
    user_data_by_variant: dict[str, list[dict]] = {}

    for variant in variant_names:
        users = conn.execute(
            "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
            (experiment_id, variant),
        ).fetchall()
        user_ids = [u["user_id"] for u in users]

        if not user_ids:
            result["variants"][variant] = {
                "users": 0, "sessions": 0, "completion_rate": 0.0,
                "avg_accuracy": 0.0, "avg_duration": 0.0,
            }
            user_data_by_variant[variant] = []
            continue

        placeholders = ",".join("?" * len(user_ids))

        try:
            user_stats = conn.execute(
                f"""SELECT
                        user_id,
                        COUNT(*) as sessions,
                        SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(items_correct) as total_correct,
                        SUM(items_completed) as total_items,
                        AVG(duration_seconds) as avg_duration
                    FROM session_log
                    WHERE user_id IN ({placeholders})
                      AND experiment_variant = ?
                    GROUP BY user_id""",
                user_ids + [variant],
            ).fetchall()
        except sqlite3.OperationalError:
            user_stats = conn.execute(
                f"""SELECT
                        user_id,
                        COUNT(*) as sessions,
                        SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(items_correct) as total_correct,
                        SUM(items_completed) as total_items,
                        AVG(duration_seconds) as avg_duration
                    FROM session_log
                    WHERE user_id IN ({placeholders})
                    GROUP BY user_id""",
                user_ids,
            ).fetchall()

        user_data_by_variant[variant] = [dict(u) for u in user_stats]

        n_users = len(user_stats)
        total_sessions = sum(u["sessions"] for u in user_stats)
        total_completed = sum(u["completed"] or 0 for u in user_stats)
        total_correct = sum(u["total_correct"] or 0 for u in user_stats)
        total_items = sum(u["total_items"] or 0 for u in user_stats)

        completion_rate = total_completed / total_sessions if total_sessions else 0.0
        accuracy = total_correct / total_items if total_items else 0.0
        avg_duration = sum(u["avg_duration"] or 0 for u in user_stats) / n_users if n_users else 0.0

        user_completion_rates = [
            (u["completed"] or 0) / u["sessions"] if u["sessions"] else 0.0
            for u in user_stats
        ]
        completion_std = _std(user_completion_rates) if user_completion_rates else 0.0

        result["variants"][variant] = {
            "users": n_users,
            "sessions": total_sessions,
            "completion_rate": round(completion_rate * 100, 1),
            "avg_accuracy": round(accuracy * 100, 1),
            "avg_duration": round(avg_duration, 1),
            "completion_std": round(completion_std, 4),
        }

    # ── Statistical test ─────────────────────────────────────────────────
    if len(variant_names) >= 2:
        control = result["variants"].get(variant_names[0], {})
        treatment = result["variants"].get(variant_names[1], {})
        n1 = control.get("users", 0)
        n2 = treatment.get("users", 0)

        result["min_sample_met"] = n1 >= min_sample and n2 >= min_sample

        if n1 > 0 and n2 > 0:
            p1 = control.get("completion_rate", 0) / 100
            p2 = treatment.get("completion_rate", 0) / 100

            # Try CUPED
            cuped_result = None
            if use_cuped:
                cuped_result = _try_cuped(
                    conn, experiment_id, variant_names,
                    user_data_by_variant,
                )

            if cuped_result and cuped_result.get("applied"):
                result["cuped_applied"] = True
                result["cuped_variance_reduction"] = cuped_result.get("variance_reduction")
                z, p_value = cuped_result["z"], cuped_result["p_value"]
                result["p_value"] = round(p_value, 4) if p_value is not None else None
                result["significant"] = (
                    p_value is not None
                    and p_value < 0.05
                    and result["min_sample_met"]
                )
                ci_low, ci_high = cuped_result.get("ci", (0.0, 0.0))
                result["ci_95"] = [round(ci_low, 4), round(ci_high, 4)]
            else:
                # Standard z-test
                z, p_value = _z_test_proportions(p1, p2, n1, n2)
                result["p_value"] = round(p_value, 4) if p_value is not None else None
                result["significant"] = (
                    p_value is not None
                    and p_value < 0.05
                    and result["min_sample_met"]
                )
                ci_low, ci_high = _ci_difference(p1, p2, n1, n2)
                result["ci_95"] = [round(ci_low, 4), round(ci_high, 4)]

            # Effect size
            std1 = control.get("completion_std", 0)
            std2 = treatment.get("completion_std", 0)
            d = _cohens_d(p2, p1, std2, std1, n2, n1)
            result["effect_size"] = round(d, 4) if d is not None else None

    return result


# ── CUPED ────────────────────────────────────────────────────────────────────


def _try_cuped(
    conn: sqlite3.Connection,
    experiment_id: int,
    variant_names: list[str],
    user_data_by_variant: dict[str, list[dict]],
) -> dict | None:
    """Attempt CUPED variance reduction using pre-period completion rate.

    Returns ``{applied, z, p_value, ci, variance_reduction}`` or ``None``.
    """
    if len(variant_names) < 2:
        return None

    # Load pre-period data for all assigned users
    try:
        rows = conn.execute(
            "SELECT user_id, variant, pre_period_data FROM experiment_assignment WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    pre_data: dict[int, dict] = {}
    user_variants: dict[int, str] = {}
    for r in rows:
        if r["pre_period_data"]:
            try:
                pre_data[r["user_id"]] = json.loads(r["pre_period_data"])
                user_variants[r["user_id"]] = r["variant"]
            except json.JSONDecodeError:
                pass

    if len(pre_data) < 20:
        return None  # Not enough pre-period data for CUPED

    # Build paired (X, Y) for each user
    # X = pre-period completion rate, Y = post-period completion rate
    control_name = variant_names[0]
    treatment_name = variant_names[1]

    control_xy: list[tuple[float, float]] = []
    treatment_xy: list[tuple[float, float]] = []

    # Post-period user completion rates
    post_rates: dict[int, float] = {}
    for variant, user_stats in user_data_by_variant.items():
        for u in user_stats:
            uid = u["user_id"]
            rate = (u["completed"] or 0) / u["sessions"] if u["sessions"] else 0.0
            post_rates[uid] = rate

    for uid, pre in pre_data.items():
        pre_rate = pre.get("completion_rate_14d", 0.0)
        post_rate = post_rates.get(uid)
        if post_rate is None:
            continue

        variant = user_variants.get(uid)
        if variant == control_name:
            control_xy.append((pre_rate, post_rate))
        elif variant == treatment_name:
            treatment_xy.append((pre_rate, post_rate))

    if len(control_xy) < 10 or len(treatment_xy) < 10:
        return None

    # Compute theta from pooled data
    all_xy = control_xy + treatment_xy
    all_x = [p[0] for p in all_xy]
    all_y = [p[1] for p in all_xy]

    cov_xy = _cov(all_x, all_y)
    var_x = _var(all_x)

    if var_x <= 0:
        return None

    theta = cov_xy / var_x
    mean_x = sum(all_x) / len(all_x)

    # CUPED-adjusted outcomes
    control_adj = [y - theta * (x - mean_x) for x, y in control_xy]
    treatment_adj = [y - theta * (x - mean_x) for x, y in treatment_xy]

    # Unadjusted variance for comparison
    control_raw = [y for _, y in control_xy]
    treatment_raw = [y for _, y in treatment_xy]
    raw_var = _var(control_raw + treatment_raw)
    adj_var = _var(control_adj + treatment_adj)
    variance_reduction = 1 - (adj_var / raw_var) if raw_var > 0 else 0.0

    # z-test on adjusted means
    n1 = len(control_adj)
    n2 = len(treatment_adj)
    m1 = sum(control_adj) / n1
    m2 = sum(treatment_adj) / n2
    s1 = _std(control_adj)
    s2 = _std(treatment_adj)

    se = math.sqrt(s1**2 / n1 + s2**2 / n2) if n1 > 0 and n2 > 0 else 0
    if se == 0:
        return None

    z = (m2 - m1) / se
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))

    diff = m2 - m1
    ci = (diff - 1.96 * se, diff + 1.96 * se)

    return {
        "applied": True,
        "z": round(z, 4),
        "p_value": round(p_value, 4),
        "ci": ci,
        "theta": round(theta, 4),
        "variance_reduction": round(variance_reduction, 4),
        "n_control": n1,
        "n_treatment": n2,
    }


# ── Statistical helpers ──────────────────────────────────────────────────────


def _cohens_d(
    mean1: float, mean2: float, std1: float, std2: float, n1: int, n2: int,
) -> float | None:
    """Cohen's d (pooled standard deviation effect size)."""
    if n1 < 2 or n2 < 2:
        return None
    pooled_var = ((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / (n1 + n2 - 2)
    if pooled_var <= 0:
        return None
    return (mean1 - mean2) / math.sqrt(pooled_var)


def _z_test_proportions(
    p1: float, p2: float, n1: int, n2: int,
) -> tuple[float | None, float | None]:
    """Two-proportion z-test. Returns (z_stat, p_value)."""
    if n1 == 0 or n2 == 0:
        return None, None
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return None, None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return z, p_value


def _confidence_interval_proportion(
    p: float, n: int, z_crit: float = 1.96,
) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z_crit**2 / n
    center = (p + z_crit**2 / (2 * n)) / denom
    half_width = (z_crit / denom) * math.sqrt(
        p * (1 - p) / n + z_crit**2 / (4 * n**2)
    )
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def _ci_difference(
    p1: float, p2: float, n1: int, n2: int, z_crit: float = 1.96,
) -> tuple[float, float]:
    """95% CI for the difference in proportions (p2 - p1)."""
    if n1 == 0 or n2 == 0:
        return (0.0, 0.0)
    diff = p2 - p1
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return (diff - z_crit * se, diff + z_crit * se)


def _std(values: list[float]) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _var(values: list[float]) -> float:
    """Sample variance."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / (len(values) - 1)


def _cov(x: list[float], y: list[float]) -> float:
    """Sample covariance."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    mx = sum(x[:n]) / n
    my = sum(y[:n]) / n
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n - 1)
