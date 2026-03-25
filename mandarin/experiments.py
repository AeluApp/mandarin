"""Experiment infrastructure — A/B testing with proper assignment, exposure logging,
guardrail metrics, and sequential testing (O'Brien-Fleming spending function).

Replaces ad-hoc feature flag experiments with a structured registry.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)


# ── Experiment CRUD ──────────────────────────────────────────────────────────


def create_experiment(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    variants: list[str],
    traffic_pct: float = 100.0,
    guardrail_metrics: list[str] | None = None,
    min_sample_size: int = 100,
) -> int:
    """Create a new experiment in draft status. Returns the experiment id."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    guardrails = guardrail_metrics or ["session_completion_rate", "crash_rate", "churn_days"]
    cur = conn.execute(
        """INSERT INTO experiment
           (name, description, variants, traffic_pct, guardrail_metrics, min_sample_size, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            description,
            json.dumps(variants),
            traffic_pct,
            json.dumps(guardrails),
            min_sample_size,
            now,
        ),
    )
    conn.commit()
    logger.info("Created experiment %r (id=%d) with variants %s", name, cur.lastrowid, variants)
    return cur.lastrowid


def start_experiment(conn: sqlite3.Connection, experiment_name: str) -> None:
    """Move an experiment from draft to running."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE experiment SET status = 'running', started_at = ? WHERE name = ? AND status = 'draft'",
        (now, experiment_name),
    )
    conn.commit()


def pause_experiment(conn: sqlite3.Connection, experiment_name: str) -> None:
    """Pause a running experiment."""
    conn.execute(
        "UPDATE experiment SET status = 'paused' WHERE name = ? AND status = 'running'",
        (experiment_name,),
    )
    conn.commit()


def conclude_experiment(
    conn: sqlite3.Connection,
    experiment_name: str,
    winner: str,
    notes: str = "",
) -> None:
    """Conclude an experiment, recording the winner and decision metadata."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    # Gather final results for the conclusion record
    results = get_experiment_results(conn, experiment_name)
    conclusion = {
        "winner": winner,
        "notes": notes,
        "variants": results.get("variants", {}),
        "p_value": results.get("p_value"),
        "effect_size": results.get("effect_size"),
        "decided_at": now,
    }
    conn.execute(
        "UPDATE experiment SET status = 'concluded', concluded_at = ?, conclusion = ? WHERE name = ?",
        (now, json.dumps(conclusion), experiment_name),
    )
    conn.commit()
    logger.info("Concluded experiment %r — winner: %s", experiment_name, winner)


# ── Assignment & Exposure ────────────────────────────────────────────────────


def get_variant(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
) -> str | None:
    """Get the variant for a user in an experiment.

    - Returns None if the experiment is not running or user is outside traffic %.
    - Assignment is deterministic via SHA256(experiment_name + user_id).
    - Persists assignment in experiment_assignment (INSERT OR IGNORE).
    """
    try:
        row = conn.execute(
            "SELECT id, status, variants, traffic_pct FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None

    if not row or row["status"] != "running":
        return None

    experiment_id = row["id"]
    variants = json.loads(row["variants"])
    traffic_pct = row["traffic_pct"]

    if not variants:
        return None

    # Check if user is in the traffic allocation
    traffic_key = f"traffic:{experiment_name}:{user_id}"
    traffic_bucket = int(hashlib.sha256(traffic_key.encode()).hexdigest()[:8], 16) % 10000
    if traffic_bucket >= traffic_pct * 100:
        return None  # User is outside the traffic %

    # Check for existing assignment first
    existing = conn.execute(
        "SELECT variant FROM experiment_assignment WHERE experiment_id = ? AND user_id = ?",
        (experiment_id, user_id),
    ).fetchone()
    if existing:
        return existing["variant"]

    # Deterministic variant assignment
    assign_key = f"{experiment_name}:{user_id}"
    variant_index = int(hashlib.sha256(assign_key.encode()).hexdigest()[:8], 16) % len(variants)
    variant = variants[variant_index]

    # Persist assignment
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT OR IGNORE INTO experiment_assignment
           (experiment_id, user_id, variant, assigned_at)
           VALUES (?, ?, ?, ?)""",
        (experiment_id, user_id, variant, now),
    )
    conn.commit()

    logger.debug("Assigned user %d to variant %r in experiment %r", user_id, variant, experiment_name)
    return variant


def log_exposure(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
    context: str = "",
) -> None:
    """Log that a user was exposed to their experiment variant."""
    try:
        row = conn.execute(
            "SELECT id FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
        if not row:
            return

        experiment_id = row["id"]

        # Get the user's assigned variant
        assignment = conn.execute(
            "SELECT variant FROM experiment_assignment WHERE experiment_id = ? AND user_id = ?",
            (experiment_id, user_id),
        ).fetchone()
        if not assignment:
            return

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO experiment_exposure
               (experiment_id, user_id, variant, context, exposed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (experiment_id, user_id, assignment["variant"], context, now),
        )
        conn.commit()
    except sqlite3.OperationalError as e:
        logger.warning("Failed to log exposure for experiment %r: %s", experiment_name, e)


# ── Results & Analysis ───────────────────────────────────────────────────────


def _cohens_d(mean1: float, mean2: float, std1: float, std2: float, n1: int, n2: int) -> float | None:
    """Compute Cohen's d (pooled standard deviation effect size)."""
    if n1 < 2 or n2 < 2:
        return None
    pooled_var = ((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / (n1 + n2 - 2)
    if pooled_var <= 0:
        return None
    return (mean1 - mean2) / math.sqrt(pooled_var)


def _z_test_proportions(p1: float, p2: float, n1: int, n2: int) -> tuple[float | None, float | None]:
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
    # Two-tailed p-value using error function approximation
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return z, p_value


def _confidence_interval_proportion(p: float, n: int, z_crit: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z_crit**2 / n
    center = (p + z_crit**2 / (2 * n)) / denom
    half_width = (z_crit / denom) * math.sqrt(p * (1 - p) / n + z_crit**2 / (4 * n**2))
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def get_experiment_results(conn: sqlite3.Connection, experiment_name: str) -> dict:
    """Compute per-variant metrics for an experiment.

    Performs user-level analysis (not session-level) to avoid Simpson's paradox.
    Returns: {
        experiment_name, status, variants: {variant_name: {users, ...}},
        p_value, effect_size, significant, min_sample_met
    }
    """
    try:
        exp = conn.execute(
            "SELECT id, name, status, variants, min_sample_size, guardrail_metrics FROM experiment WHERE name = ?",
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
    }

    # User-level analysis: aggregate per user, then compute variant stats
    for variant in variant_names:
        # Get all users assigned to this variant
        users = conn.execute(
            "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
            (experiment_id, variant),
        ).fetchall()
        user_ids = [u["user_id"] for u in users]

        if not user_ids:
            result["variants"][variant] = {
                "users": 0,
                "sessions": 0,
                "completion_rate": 0.0,
                "avg_accuracy": 0.0,
                "avg_duration": 0.0,
            }
            continue

        placeholders = ",".join("?" * len(user_ids))

        # Per-user session stats (user-level aggregation)
        # Only include sessions that have the experiment_variant column matching
        # Fall back to all sessions for users in the assignment if column missing
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
            # experiment_variant column may not exist yet — fall back
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

        n_users = len(user_stats)
        total_sessions = sum(u["sessions"] for u in user_stats)
        total_completed = sum(u["completed"] or 0 for u in user_stats)
        total_correct = sum(u["total_correct"] or 0 for u in user_stats)
        total_items = sum(u["total_items"] or 0 for u in user_stats)

        completion_rate = total_completed / total_sessions if total_sessions else 0.0
        accuracy = total_correct / total_items if total_items else 0.0
        avg_duration = sum(u["avg_duration"] or 0 for u in user_stats) / n_users if n_users else 0.0

        # Per-user completion rates for variance estimation
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

    # Statistical test (first variant = control, second = treatment)
    if len(variant_names) >= 2:
        control = result["variants"].get(variant_names[0], {})
        treatment = result["variants"].get(variant_names[1], {})
        n1 = control.get("users", 0)
        n2 = treatment.get("users", 0)

        result["min_sample_met"] = n1 >= min_sample and n2 >= min_sample

        if n1 > 0 and n2 > 0:
            p1 = control.get("completion_rate", 0) / 100
            p2 = treatment.get("completion_rate", 0) / 100
            z, p_value = _z_test_proportions(p1, p2, n1, n2)
            result["p_value"] = round(p_value, 4) if p_value is not None else None
            result["significant"] = (
                p_value is not None
                and p_value < 0.05
                and result["min_sample_met"]
            )

            # Effect size (Cohen's d on user-level completion rates)
            std1 = control.get("completion_std", 0)
            std2 = treatment.get("completion_std", 0)
            d = _cohens_d(p2, p1, std2, std1, n2, n1)
            result["effect_size"] = round(d, 4) if d is not None else None

            # Confidence interval on the difference
            ci_low, ci_high = _ci_difference(p1, p2, n1, n2)
            result["ci_95"] = [round(ci_low, 4), round(ci_high, 4)]

    return result


def _std(values: list[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _ci_difference(p1: float, p2: float, n1: int, n2: int, z_crit: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for the difference in proportions (p2 - p1)."""
    if n1 == 0 or n2 == 0:
        return (0.0, 0.0)
    diff = p2 - p1
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return (diff - z_crit * se, diff + z_crit * se)


# ── Guardrail Metrics ────────────────────────────────────────────────────────

DEFAULT_GUARDRAILS = ["session_completion_rate", "crash_rate", "churn_days"]
GUARDRAIL_DEGRADATION_THRESHOLD = 0.05  # 5% relative degradation triggers alert


def check_guardrails(conn: sqlite3.Connection, experiment_name: str) -> dict:
    """Check guardrail metrics for an experiment.

    Returns: {metric_name: {control_value, treatment_value, degraded: bool}}
    """
    try:
        exp = conn.execute(
            "SELECT id, variants, guardrail_metrics FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {}

    if not exp:
        return {}

    experiment_id = exp["id"]
    variant_names = json.loads(exp["variants"])
    guardrails_config = json.loads(exp["guardrail_metrics"] or "[]") or DEFAULT_GUARDRAILS

    if len(variant_names) < 2:
        return {}

    control_name = variant_names[0]
    treatment_name = variant_names[1]

    # Get user IDs per variant
    control_users = [
        r["user_id"] for r in conn.execute(
            "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
            (experiment_id, control_name),
        ).fetchall()
    ]
    treatment_users = [
        r["user_id"] for r in conn.execute(
            "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
            (experiment_id, treatment_name),
        ).fetchall()
    ]

    results = {}

    for metric in guardrails_config:
        control_val = _compute_guardrail_metric(conn, metric, control_users)
        treatment_val = _compute_guardrail_metric(conn, metric, treatment_users)

        # Determine degradation direction per metric
        if metric == "crash_rate" or metric == "churn_days":
            # Higher is worse
            degraded = (
                control_val > 0
                and treatment_val > control_val * (1 + GUARDRAIL_DEGRADATION_THRESHOLD)
            )
        else:
            # Higher is better (completion rate, etc.)
            degraded = (
                control_val > 0
                and treatment_val < control_val * (1 - GUARDRAIL_DEGRADATION_THRESHOLD)
            )

        results[metric] = {
            "control_value": round(control_val, 4),
            "treatment_value": round(treatment_val, 4),
            "degraded": degraded,
        }

    return results


def _compute_guardrail_metric(conn: sqlite3.Connection, metric: str, user_ids: list[int]) -> float:
    """Compute a single guardrail metric for a set of users."""
    if not user_ids:
        return 0.0

    placeholders = ",".join("?" * len(user_ids))

    if metric == "session_completion_rate":
        row = conn.execute(
            f"""SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) as completed
                FROM session_log WHERE user_id IN ({placeholders})""",
            user_ids,
        ).fetchone()
        total = row["total"] or 0
        completed = row["completed"] or 0
        return completed / total if total > 0 else 0.0

    elif metric == "crash_rate":
        # Crashes tracked in error_log with error_type containing 'crash'
        try:
            row = conn.execute(
                f"""SELECT COUNT(*) as cnt FROM error_log
                    WHERE session_id IN (
                        SELECT id FROM session_log WHERE user_id IN ({placeholders})
                    ) AND error_type LIKE '%crash%'""",
                user_ids,
            ).fetchone()
            crashes = row["cnt"] or 0
            session_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM session_log WHERE user_id IN ({placeholders})",
                user_ids,
            ).fetchone()
            sessions = session_row["cnt"] or 0
            return crashes / sessions if sessions > 0 else 0.0
        except sqlite3.OperationalError:
            return 0.0

    elif metric == "churn_days":
        # Average days since each user's last session
        try:
            row = conn.execute(
                f"""SELECT AVG(julianday('now') - julianday(MAX(started_at))) as avg_gap
                    FROM session_log
                    WHERE user_id IN ({placeholders})
                    GROUP BY user_id""",
                user_ids,
            ).fetchone()
            return float(row["avg_gap"]) if row and row["avg_gap"] else 0.0
        except (sqlite3.OperationalError, TypeError):
            return 0.0

    return 0.0


# ── Sequential Testing (O'Brien-Fleming) ─────────────────────────────────────


def _obrien_fleming_boundary(alpha: float, information_fraction: float) -> float:
    """Compute the O'Brien-Fleming adjusted critical z-value.

    The O'Brien-Fleming spending function: alpha_spent = 2 * (1 - Phi(z_alpha/2 / sqrt(t)))
    where t is the information fraction.

    Returns the adjusted alpha at this information fraction.
    """
    if information_fraction <= 0 or information_fraction > 1:
        return 0.0

    # z_alpha/2 for the overall alpha
    z_alpha = _inv_normal(1 - alpha / 2)

    # O'Brien-Fleming: z boundary = z_alpha / sqrt(information_fraction)
    z_boundary = z_alpha / math.sqrt(information_fraction)

    # Convert back to alpha spent at this look
    adjusted_alpha = 2 * (1 - 0.5 * (1 + math.erf(z_boundary / math.sqrt(2))))
    return adjusted_alpha


def _inv_normal(p: float) -> float:
    """Approximate inverse normal CDF (Abramowitz & Stegun)."""
    if p <= 0 or p >= 1:
        return 0.0
    if p < 0.5:
        return -_inv_normal(1 - p)

    # Rational approximation
    t = math.sqrt(-2 * math.log(1 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return t - (c0 + c1 * t + c2 * t**2) / (1 + d1 * t + d2 * t**2 + d3 * t**3)


def sequential_test(conn: sqlite3.Connection, experiment_name: str, alpha: float = 0.05) -> dict:
    """Run a sequential test on an experiment using O'Brien-Fleming spending function.

    Returns: {
        can_conclude: bool,
        adjusted_alpha: float,
        current_p: float | None,
        information_fraction: float,
        recommendation: str  -- "continue", "stop_winner", "stop_futility", "insufficient_data"
    }
    """
    try:
        exp = conn.execute(
            "SELECT id, variants, min_sample_size FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"can_conclude": False, "recommendation": "insufficient_data"}

    if not exp:
        return {"can_conclude": False, "recommendation": "insufficient_data"}

    experiment_id = exp["id"]
    variant_names = json.loads(exp["variants"])
    planned_n = (exp["min_sample_size"] or 100) * len(variant_names)

    # Current sample sizes
    assignment_counts = conn.execute(
        "SELECT variant, COUNT(*) as n FROM experiment_assignment WHERE experiment_id = ? GROUP BY variant",
        (experiment_id,),
    ).fetchall()
    current_n = sum(r["n"] for r in assignment_counts)

    if current_n == 0 or len(variant_names) < 2:
        return {
            "can_conclude": False,
            "adjusted_alpha": 0.0,
            "current_p": None,
            "information_fraction": 0.0,
            "recommendation": "insufficient_data",
        }

    information_fraction = min(1.0, current_n / planned_n)
    adjusted_alpha = _obrien_fleming_boundary(alpha, information_fraction)

    # Get current p-value from results
    results = get_experiment_results(conn, experiment_name)
    current_p = results.get("p_value")

    can_conclude = current_p is not None and current_p < adjusted_alpha
    min_met = results.get("min_sample_met", False)

    if current_p is None or information_fraction < 0.1:
        recommendation = "insufficient_data"
    elif can_conclude and min_met:
        recommendation = "stop_winner"
    elif information_fraction >= 1.0 and (current_p is None or current_p > 0.2):
        recommendation = "stop_futility"
    else:
        recommendation = "continue"

    return {
        "can_conclude": can_conclude,
        "adjusted_alpha": round(adjusted_alpha, 6),
        "current_p": current_p,
        "information_fraction": round(information_fraction, 3),
        "recommendation": recommendation,
    }


# ── Listing ──────────────────────────────────────────────────────────────────


def list_experiments(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """List experiments, optionally filtered by status."""
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM experiment WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM experiment ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
