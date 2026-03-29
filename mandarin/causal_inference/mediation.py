"""Baron-Kenny mediation analysis — does the treatment effect flow through a mediator?

Uses only stdlib math.  Pulls user-level data from the experiment system's
``experiment_assignment`` and ``session_log`` tables.
"""

from __future__ import annotations

import logging
import math
import sqlite3

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def _se(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    return _std(values) / math.sqrt(n)


def _correlation(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation between two lists of equal length."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
    sx, sy = _std(xs), _std(ys)
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _regression_slope(xs: list[float], ys: list[float]) -> float:
    """Simple OLS slope of y on x."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    ss_xx = sum((x - mx) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0
    ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return ss_xy / ss_xx


def _regression_slope_se(xs: list[float], ys: list[float]) -> float:
    """Standard error of the OLS slope."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return 0.0
    mx = _mean(xs)
    slope = _regression_slope(xs, ys)
    intercept = _mean(ys) - slope * mx
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    ss_res = sum(r ** 2 for r in residuals)
    ss_xx = sum((x - mx) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0
    mse = ss_res / (n - 2)
    return math.sqrt(mse / ss_xx)


def _normal_cdf(z: float) -> float:
    """Approximate CDF of the standard normal using the Abramowitz & Stegun formula."""
    if z < -8.0:
        return 0.0
    if z > 8.0:
        return 1.0
    a = abs(z)
    t = 1.0 / (1.0 + 0.2316419 * a)
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    cdf = 1.0 - d * math.exp(-0.5 * z * z) * poly
    return cdf if z >= 0 else 1.0 - cdf


def _two_sided_p(z: float) -> float:
    """Two-sided p-value from a z-score."""
    return 2.0 * (1.0 - _normal_cdf(abs(z)))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_user_metrics(
    conn: sqlite3.Connection,
    experiment_name: str,
    mediator_metric: str,
    outcome_metric: str,
) -> list[dict]:
    """Load per-user variant, mediator, and outcome from the DB.

    Returns a list of dicts with keys: variant, mediator, outcome.
    """
    # Look up experiment id
    try:
        exp = conn.execute(
            "SELECT id, variants FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        logger.warning("experiment table not found")
        return []

    if not exp:
        logger.warning("Experiment %r not found", experiment_name)
        return []

    experiment_id = exp["id"]

    # Map metric names to SQL expressions on session_log
    metric_sql = {
        "accuracy": "CASE WHEN SUM(items_completed) > 0 "
                    "THEN CAST(SUM(items_correct) AS REAL) / SUM(items_completed) "
                    "ELSE 0 END",
        "completion_rate": "CASE WHEN COUNT(*) > 0 "
                          "THEN CAST(SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) AS REAL) "
                          "/ COUNT(*) ELSE 0 END",
        "duration": "AVG(duration_seconds)",
        "sessions": "COUNT(*)",
    }

    mediator_sql = metric_sql.get(mediator_metric, metric_sql["accuracy"])
    outcome_sql = metric_sql.get(outcome_metric, metric_sql["completion_rate"])

    sql = f"""
        SELECT
            ea.variant,
            {mediator_sql} AS mediator,
            {outcome_sql}  AS outcome
        FROM experiment_assignment ea
        JOIN session_log sl ON sl.user_id = ea.user_id
        WHERE ea.experiment_id = ?
        GROUP BY ea.user_id, ea.variant
    """

    try:
        rows = conn.execute(sql, (experiment_id,)).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("Could not load mediation data: %s", exc)
        return []

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def test_mediation(
    conn: sqlite3.Connection,
    experiment_name: str,
    mediator_metric: str = "accuracy",
    outcome_metric: str = "completion_rate",
) -> dict:
    """Test for mediation of treatment effect through a mediator.

    Baron-Kenny steps:

    1. Total effect: treatment -> outcome  (c path)
    2. Treatment -> mediator  (a path)
    3. Mediator -> outcome controlling for treatment  (b path)
    4. Direct effect: treatment -> outcome controlling for mediator  (c' path)
    5. Indirect effect: a * b
    6. Mediation proportion: (c - c') / c

    For the *a* and *c* paths, difference-in-means is used (treatment is
    randomized).  For the *b* and *c'* paths, within-group OLS regression
    is used so that we partial out treatment assignment.

    Returns::

        {
            "total_effect": float,
            "direct_effect": float,
            "indirect_effect": float,
            "mediation_proportion": float,
            "a_path": float,
            "b_path": float,
            "sobel_z": float,
            "sobel_p": float,
            "interpretation": str,
        }
    """
    empty = {
        "total_effect": 0.0,
        "direct_effect": 0.0,
        "indirect_effect": 0.0,
        "mediation_proportion": 0.0,
        "a_path": 0.0,
        "b_path": 0.0,
        "sobel_z": 0.0,
        "sobel_p": 1.0,
        "interpretation": "Insufficient data for mediation analysis.",
    }

    data = _load_user_metrics(conn, experiment_name, mediator_metric, outcome_metric)
    if not data:
        return empty

    # Partition by variant — assume first alphabetically is control
    variants = sorted({d["variant"] for d in data})
    if len(variants) < 2:
        return empty

    control_name = variants[0]
    treatment_name = variants[1]

    control = [d for d in data if d["variant"] == control_name]
    treatment = [d for d in data if d["variant"] == treatment_name]

    if len(control) < 2 or len(treatment) < 2:
        return empty

    # -- Path c: total effect (treatment -> outcome) ---------------------
    control_outcome = [d["outcome"] or 0.0 for d in control]
    treatment_outcome = [d["outcome"] or 0.0 for d in treatment]
    c_total = _mean(treatment_outcome) - _mean(control_outcome)

    # -- Path a: treatment -> mediator -----------------------------------
    control_mediator = [d["mediator"] or 0.0 for d in control]
    treatment_mediator = [d["mediator"] or 0.0 for d in treatment]
    a_path = _mean(treatment_mediator) - _mean(control_mediator)

    se_a = math.sqrt(
        _se(treatment_mediator) ** 2 + _se(control_mediator) ** 2
    ) if (len(treatment_mediator) > 1 and len(control_mediator) > 1) else 0.0

    # -- Path b: mediator -> outcome (within-group regression) -----------
    # Pool within-group mediator/outcome pairs and regress outcome on mediator
    all_mediator = control_mediator + treatment_mediator
    all_outcome = control_outcome + treatment_outcome

    # Within-group: center each group's values, then regress
    centered_mediator: list[float] = []
    centered_outcome: list[float] = []

    for group_med, group_out in [
        (control_mediator, control_outcome),
        (treatment_mediator, treatment_outcome),
    ]:
        gm_med = _mean(group_med)
        gm_out = _mean(group_out)
        centered_mediator.extend(m - gm_med for m in group_med)
        centered_outcome.extend(o - gm_out for o in group_out)

    b_path = _regression_slope(centered_mediator, centered_outcome)
    se_b = _regression_slope_se(centered_mediator, centered_outcome)

    # -- Indirect effect: a * b ------------------------------------------
    indirect = a_path * b_path

    # -- Direct effect c': c - indirect ----------------------------------
    c_prime = c_total - indirect

    # -- Mediation proportion --------------------------------------------
    mediation_proportion = 0.0
    if c_total != 0:
        mediation_proportion = indirect / c_total
    # Clamp to [0, 1] for interpretability
    mediation_proportion = max(0.0, min(1.0, mediation_proportion))

    # -- Sobel test: z = a*b / sqrt(b^2 * se_a^2 + a^2 * se_b^2) -------
    sobel_denom = math.sqrt(b_path ** 2 * se_a ** 2 + a_path ** 2 * se_b ** 2)
    sobel_z = indirect / sobel_denom if sobel_denom > 0 else 0.0
    sobel_p = _two_sided_p(sobel_z) if sobel_z != 0 else 1.0

    # -- Interpretation --------------------------------------------------
    if sobel_p < 0.05 and mediation_proportion > 0.1:
        pct = mediation_proportion * 100
        interpretation = (
            f"Significant mediation detected (Sobel p={sobel_p:.4f}). "
            f"Approximately {pct:.0f}% of the treatment effect on "
            f"{outcome_metric} is mediated through {mediator_metric}."
        )
    elif sobel_p < 0.10:
        interpretation = (
            f"Marginal evidence of mediation (Sobel p={sobel_p:.4f}). "
            f"The indirect path through {mediator_metric} may partially "
            f"explain the treatment effect, but more data is needed."
        )
    else:
        interpretation = (
            f"No significant mediation detected (Sobel p={sobel_p:.4f}). "
            f"The treatment effect on {outcome_metric} does not appear to "
            f"flow through {mediator_metric}."
        )

    return {
        "total_effect": round(c_total, 6),
        "direct_effect": round(c_prime, 6),
        "indirect_effect": round(indirect, 6),
        "mediation_proportion": round(mediation_proportion, 4),
        "a_path": round(a_path, 6),
        "b_path": round(b_path, 6),
        "sobel_z": round(sobel_z, 4),
        "sobel_p": round(sobel_p, 4),
        "interpretation": interpretation,
    }
