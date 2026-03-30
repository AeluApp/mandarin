"""Bayesian experiment analysis — Beta-Binomial posterior with decision rules.

Uses conjugate Beta-Binomial model (stdlib only, no scipy/numpy).
Provides:
- Posterior summaries (mean, credible interval)
- P(treatment > control) via Monte Carlo
- Expected loss for decision-making under uncertainty
- Bayesian sequential stopping (P(best) > 0.95 AND expected loss < threshold)
"""

from __future__ import annotations

import logging
import math
import random
import sqlite3

logger = logging.getLogger(__name__)

# Number of Monte Carlo samples for posterior comparisons
_N_SAMPLES = 10_000

# Default prior: Beta(1, 1) = uniform
_DEFAULT_ALPHA_PRIOR = 1.0
_DEFAULT_BETA_PRIOR = 1.0


def _beta_sample(alpha: float, beta_param: float, rng: random.Random) -> float:
    """Draw a single sample from Beta(alpha, beta) using Gamma decomposition.

    Beta(a, b) = Gamma(a, 1) / (Gamma(a, 1) + Gamma(b, 1))
    """
    if alpha <= 0 or beta_param <= 0:
        return 0.5
    x = rng.gammavariate(alpha, 1.0)
    y = rng.gammavariate(beta_param, 1.0)
    if x + y == 0:
        return 0.5
    return x / (x + y)


def _beta_mean(alpha: float, beta_param: float) -> float:
    """Mean of Beta distribution."""
    return alpha / (alpha + beta_param) if (alpha + beta_param) > 0 else 0.5


def _beta_mode(alpha: float, beta_param: float) -> float:
    """Mode of Beta distribution (valid when alpha > 1 and beta > 1)."""
    if alpha > 1 and beta_param > 1:
        return (alpha - 1) / (alpha + beta_param - 2)
    return _beta_mean(alpha, beta_param)


def _beta_credible_interval(
    alpha: float, beta_param: float, level: float = 0.95, n_samples: int = 10_000
) -> tuple[float, float]:
    """Monte Carlo credible interval for Beta distribution."""
    rng = random.Random(42)  # deterministic for reproducibility
    samples = sorted(_beta_sample(alpha, beta_param, rng) for _ in range(n_samples))
    lower_idx = int((1 - level) / 2 * n_samples)
    upper_idx = int((1 + level) / 2 * n_samples) - 1
    return (samples[max(0, lower_idx)], samples[min(len(samples) - 1, upper_idx)])


def compute_bayesian_results(
    variant_data: dict[str, dict],
    *,
    alpha_prior: float = _DEFAULT_ALPHA_PRIOR,
    beta_prior: float = _DEFAULT_BETA_PRIOR,
    metric: str = "completion_rate",
    seed: int = 42,
) -> dict:
    """Compute Bayesian posterior analysis for an experiment.

    Args:
        variant_data: Dict of variant_name -> {"successes": int, "trials": int}
                      or {"users": int, "completion_rate": float (0-100)}
        alpha_prior: Prior alpha parameter (default: 1.0 = uniform)
        beta_prior: Prior beta parameter (default: 1.0 = uniform)
        metric: Name of the metric being analyzed
        seed: Random seed for reproducibility

    Returns:
        Dict with posterior summaries, P(best), expected loss, credible intervals.
    """
    if not variant_data or len(variant_data) < 2:
        return {"error": "Need at least 2 variants", "posteriors": {}}

    rng = random.Random(seed)
    posteriors = {}

    for name, data in variant_data.items():
        # Handle both input formats
        if "successes" in data and "trials" in data:
            successes = data["successes"]
            trials = data["trials"]
        elif "users" in data and "completion_rate" in data:
            trials = data["users"]
            rate = data["completion_rate"] / 100.0  # convert from percentage
            successes = int(round(rate * trials))
        else:
            continue

        failures = trials - successes
        post_alpha = alpha_prior + successes
        post_beta = beta_prior + failures

        ci_lower, ci_upper = _beta_credible_interval(post_alpha, post_beta)

        posteriors[name] = {
            "alpha": post_alpha,
            "beta": post_beta,
            "mean": round(_beta_mean(post_alpha, post_beta) * 100, 3),
            "mode": round(_beta_mode(post_alpha, post_beta) * 100, 3),
            "ci_95_lower": round(ci_lower * 100, 3),
            "ci_95_upper": round(ci_upper * 100, 3),
            "successes": successes,
            "trials": trials,
        }

    if len(posteriors) < 2:
        return {"error": "Insufficient data for analysis", "posteriors": posteriors}

    # Monte Carlo: draw samples from each posterior
    variant_names = list(posteriors.keys())
    samples = {}
    for name in variant_names:
        p = posteriors[name]
        samples[name] = [_beta_sample(p["alpha"], p["beta"], rng) for _ in range(_N_SAMPLES)]

    # P(each variant is best)
    best_counts = {name: 0 for name in variant_names}
    for i in range(_N_SAMPLES):
        best_name = max(variant_names, key=lambda n: samples[n][i])
        best_counts[best_name] += 1

    prob_best = {name: round(count / _N_SAMPLES, 4) for name, count in best_counts.items()}

    # Expected loss for each variant
    expected_loss = {}
    for name in variant_names:
        loss_sum = 0.0
        for i in range(_N_SAMPLES):
            best_value = max(samples[n][i] for n in variant_names)
            loss_sum += max(0.0, best_value - samples[name][i])
        expected_loss[name] = round(loss_sum / _N_SAMPLES * 100, 4)  # as percentage points

    # Recommended variant: lowest expected loss
    recommended = min(expected_loss, key=expected_loss.get)

    # P(treatment > control) for two-variant case
    prob_treatment_wins = None
    if len(variant_names) == 2:
        control_name = variant_names[0]
        treatment_name = variant_names[1]
        wins = sum(
            1 for i in range(_N_SAMPLES)
            if samples[treatment_name][i] > samples[control_name][i]
        )
        prob_treatment_wins = round(wins / _N_SAMPLES, 4)

    # Bayesian sequential stopping check
    max_prob_best = max(prob_best.values())
    min_expected_loss = min(expected_loss.values())
    can_stop = max_prob_best > 0.95 and min_expected_loss < 0.5  # < 0.5 pp

    return {
        "metric": metric,
        "posteriors": posteriors,
        "prob_best": prob_best,
        "expected_loss": expected_loss,
        "recommended_variant": recommended,
        "prob_treatment_wins": prob_treatment_wins,
        "can_stop": can_stop,
        "stopping_criteria": {
            "prob_best_threshold": 0.95,
            "expected_loss_threshold_pp": 0.5,
            "max_prob_best": max_prob_best,
            "min_expected_loss_pp": min_expected_loss,
        },
    }


def get_bayesian_experiment_results(
    conn: sqlite3.Connection,
    experiment_name: str,
    *,
    alpha_prior: float = _DEFAULT_ALPHA_PRIOR,
    beta_prior: float = _DEFAULT_BETA_PRIOR,
) -> dict:
    """Run Bayesian analysis on an experiment using DB data.

    Queries experiment_assignment + session outcomes to compute per-variant
    success/trial counts, then runs compute_bayesian_results().
    """
    try:
        # Get experiment
        exp = conn.execute(
            "SELECT id, status, variants FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
        if not exp:
            return {"error": f"Experiment '{experiment_name}' not found"}

        exp_id = exp["id"]

        # Get per-variant user-level completion data
        rows = conn.execute(
            """
            SELECT
                ea.variant,
                COUNT(DISTINCT ea.user_id) AS users,
                COUNT(DISTINCT CASE WHEN sl.session_outcome = 'completed' THEN sl.id END) AS completed_sessions,
                COUNT(DISTINCT sl.id) AS total_sessions
            FROM experiment_assignment ea
            LEFT JOIN session_log sl ON sl.user_id = ea.user_id
                AND sl.started_at >= ea.assigned_at
            WHERE ea.experiment_id = ?
            GROUP BY ea.variant
            """,
            (exp_id,),
        ).fetchall()

        if not rows:
            return {"error": "No assignment data", "experiment": experiment_name}

        variant_data = {}
        for r in rows:
            total = r["total_sessions"] or 1
            completed = r["completed_sessions"] or 0
            variant_data[r["variant"]] = {
                "successes": completed,
                "trials": total,
                "users": r["users"],
            }

        result = compute_bayesian_results(
            variant_data,
            alpha_prior=alpha_prior,
            beta_prior=beta_prior,
        )
        result["experiment"] = experiment_name
        result["status"] = exp["status"]
        return result

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Bayesian analysis failed for %s: %s", experiment_name, e)
        return {"error": str(e), "experiment": experiment_name}


def benjamini_hochberg(p_values: list[tuple[str, float]], alpha: float = 0.05) -> list[dict]:
    """Apply Benjamini-Hochberg FDR correction to a list of p-values.

    Args:
        p_values: List of (metric_name, p_value) tuples
        alpha: Target FDR (default: 0.05)

    Returns:
        List of dicts with metric, raw_p, adjusted_p, significant, rank.
    """
    if not p_values:
        return []

    # Sort by p-value
    sorted_pvals = sorted(p_values, key=lambda x: x[1])
    m = len(sorted_pvals)

    results = []
    for rank, (metric, p) in enumerate(sorted_pvals, 1):
        # BH adjusted p-value: p * m / rank (capped at 1.0)
        adjusted = min(p * m / rank, 1.0)
        results.append({
            "metric": metric,
            "raw_p": round(p, 6),
            "adjusted_p": round(adjusted, 6),
            "significant": adjusted < alpha,
            "rank": rank,
        })

    # Enforce monotonicity: adjusted p-values should be non-decreasing from bottom
    for i in range(len(results) - 2, -1, -1):
        results[i]["adjusted_p"] = min(results[i]["adjusted_p"], results[i + 1]["adjusted_p"])

    # Re-sort by original order
    metric_order = {name: i for i, (name, _) in enumerate(p_values)}
    results.sort(key=lambda x: metric_order[x["metric"]])

    return results


def test_equivalence(
    rate_a: float,
    n_a: int,
    rate_b: float,
    n_b: int,
    margin: float = 0.02,
) -> dict:
    """Two One-Sided Tests (TOST) for equivalence.

    Tests whether the difference between two proportions falls within
    [-margin, +margin], i.e., the treatments are practically equivalent.

    Args:
        rate_a: Proportion in group A (0-1)
        n_a: Sample size group A
        rate_b: Proportion in group B (0-1)
        n_b: Sample size group B
        margin: Equivalence margin (default: 2 percentage points = 0.02)

    Returns:
        Dict with equivalent (bool), tost_p_value, confidence interval, interpretation.
    """
    diff = rate_b - rate_a
    se = math.sqrt(rate_a * (1 - rate_a) / max(n_a, 1) + rate_b * (1 - rate_b) / max(n_b, 1))

    if se == 0:
        return {
            "equivalent": abs(diff) <= margin,
            "tost_p_value": 0.0 if abs(diff) <= margin else 1.0,
            "difference": round(diff, 6),
            "margin": margin,
            "interpretation": "Zero variance — no statistical test possible.",
        }

    # Two one-sided tests
    # H0_lower: diff <= -margin (test: z_lower)
    # H0_upper: diff >= +margin (test: z_upper)
    z_lower = (diff - (-margin)) / se  # should be positive to reject
    z_upper = (margin - diff) / se  # should be positive to reject

    # p-values (one-sided): P(Z > z)
    p_lower = _norm_sf(z_lower)
    p_upper = _norm_sf(z_upper)

    # TOST p-value = max of the two
    tost_p = max(p_lower, p_upper)

    # 90% CI (corresponds to two one-sided alpha=0.05 tests)
    z_90 = 1.645
    ci_lower = diff - z_90 * se
    ci_upper = diff + z_90 * se

    equivalent = tost_p < 0.05

    if equivalent:
        interpretation = (
            f"Equivalent: the difference ({diff:.4f}) falls within "
            f"±{margin:.4f} (TOST p={tost_p:.4f}). "
            f"The treatments are practically interchangeable."
        )
    else:
        interpretation = (
            f"Not equivalent: cannot confirm the difference ({diff:.4f}) "
            f"is within ±{margin:.4f} (TOST p={tost_p:.4f})."
        )

    return {
        "equivalent": equivalent,
        "tost_p_value": round(tost_p, 6),
        "difference": round(diff, 6),
        "margin": margin,
        "ci_90": [round(ci_lower, 6), round(ci_upper, 6)],
        "z_lower": round(z_lower, 4),
        "z_upper": round(z_upper, 4),
        "interpretation": interpretation,
    }


def _norm_sf(z: float) -> float:
    """Survival function (1 - CDF) for standard normal, stdlib only.

    Uses Abramowitz & Stegun approximation (error < 7.5e-8).
    """
    if z < -8:
        return 1.0
    if z > 8:
        return 0.0
    # For negative z, use symmetry
    if z < 0:
        return 1.0 - _norm_sf(-z)
    # Rational approximation
    p = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    t = 1.0 / (1.0 + p * z)
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return pdf * t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))))
