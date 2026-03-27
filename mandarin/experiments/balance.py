"""Balance monitoring — SRM detection, covariate balance, drift, exposure imbalance.

Balance checks are the early-warning system for broken experiments.  SRM in
particular is a *hard stop*: if detected, the experiment is paused automatically
because SRM almost always indicates a bug in the assignment pipeline.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone, UTC

from .audit import log_audit_event

logger = logging.getLogger(__name__)

# SRM threshold: p < 0.001 (industry standard — conservative to avoid false alarms)
SRM_THRESHOLD = 0.001

# Covariate balance: standardised mean difference
SMD_WARNING_THRESHOLD = 0.15


def check_srm(
    conn: sqlite3.Connection,
    experiment_id: int,
    expected_ratio: float = 0.5,
) -> dict:
    """Chi-squared test for sample ratio mismatch.

    Returns ``{passed, chi2, p_value, n_control, n_treatment, observed_ratio,
    expected_ratio}``.  ``passed=False`` means SRM detected — experiment
    should be paused.
    """
    try:
        counts = conn.execute(
            """SELECT variant, COUNT(*) as n
               FROM experiment_assignment WHERE experiment_id = ?
               GROUP BY variant""",
            (experiment_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"passed": True, "reason": "table_unavailable"}

    if len(counts) < 2:
        return {"passed": True, "reason": "fewer_than_two_variants"}

    # For two-variant experiments
    n_values = [r["n"] for r in counts]
    variant_names = [r["variant"] for r in counts]
    total = sum(n_values)

    if total < 20:
        return {"passed": True, "reason": "insufficient_sample", "total": total}

    # Expected counts based on ratio
    expected = [total * expected_ratio, total * (1 - expected_ratio)]
    chi2 = sum((obs - exp) ** 2 / exp for obs, exp in zip(n_values, expected, strict=False) if exp > 0)

    # Chi-squared p-value approximation (1 df)
    p_value = _chi2_sf(chi2, df=1)
    passed = p_value >= SRM_THRESHOLD

    result = {
        "passed": passed,
        "chi2": round(chi2, 4),
        "p_value": round(p_value, 6),
        "n_per_variant": dict(zip(variant_names, n_values, strict=False)),
        "total": total,
        "observed_ratio": round(n_values[0] / total, 4) if total > 0 else None,
        "expected_ratio": expected_ratio,
    }

    # Audit log
    log_audit_event(
        conn,
        "srm_check",
        experiment_id=experiment_id,
        data=result,
    )

    # Persist balance check
    _persist_balance_check(conn, experiment_id, "srm", passed, result)

    if not passed:
        logger.warning(
            "SRM DETECTED for experiment %d: chi2=%.4f, p=%.6f, counts=%s",
            experiment_id, chi2, p_value, dict(zip(variant_names, n_values, strict=False)),
        )

    return result


def check_covariate_balance(
    conn: sqlite3.Connection,
    experiment_id: int,
) -> dict:
    """Check baseline covariate balance between arms.

    Computes standardised mean difference (SMD) for key covariates.
    Returns ``{covariates: {name: {smd, control_mean, treatment_mean}}, passed, warnings}``.
    """
    try:
        exp = conn.execute(
            "SELECT variants FROM experiment WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        if not exp:
            return {"passed": True, "covariates": {}, "warnings": []}

        variant_names = json.loads(exp["variants"])
        if len(variant_names) < 2:
            return {"passed": True, "covariates": {}, "warnings": []}

        control_name = variant_names[0]
        treatment_name = variant_names[1]
    except (sqlite3.OperationalError, json.JSONDecodeError):
        return {"passed": True, "covariates": {}, "warnings": []}

    # Get user IDs per arm
    control_ids = _get_arm_user_ids(conn, experiment_id, control_name)
    treatment_ids = _get_arm_user_ids(conn, experiment_id, treatment_name)

    if not control_ids or not treatment_ids:
        return {"passed": True, "covariates": {}, "warnings": ["insufficient_users"]}

    covariates = {}
    warnings: list[str] = []

    # Check each covariate
    for name, query_fn in _COVARIATE_QUERIES.items():
        control_vals = query_fn(conn, control_ids)
        treatment_vals = query_fn(conn, treatment_ids)

        if not control_vals or not treatment_vals:
            continue

        c_mean = sum(control_vals) / len(control_vals)
        t_mean = sum(treatment_vals) / len(treatment_vals)
        smd = _standardised_mean_diff(control_vals, treatment_vals)

        covariates[name] = {
            "smd": round(smd, 4) if smd is not None else None,
            "control_mean": round(c_mean, 4),
            "treatment_mean": round(t_mean, 4),
            "control_n": len(control_vals),
            "treatment_n": len(treatment_vals),
        }

        if smd is not None and abs(smd) > SMD_WARNING_THRESHOLD:
            warnings.append(f"{name}: SMD={smd:.3f} exceeds threshold {SMD_WARNING_THRESHOLD}")

    passed = len(warnings) == 0

    result = {"covariates": covariates, "passed": passed, "warnings": warnings}

    log_audit_event(
        conn,
        "balance_check",
        experiment_id=experiment_id,
        data={"type": "covariate_balance", "passed": passed, "warnings": warnings},
    )
    _persist_balance_check(conn, experiment_id, "covariate", passed, result)

    return result


def check_assignment_drift(
    conn: sqlite3.Connection,
    experiment_id: int,
    expected_ratio: float = 0.5,
    max_deviation_pp: float = 3.0,
) -> dict:
    """Check whether cumulative assignment ratio has drifted from expected.

    Returns ``{passed, current_ratio, expected_ratio, deviation_pp}``.
    """
    try:
        counts = conn.execute(
            """SELECT variant, COUNT(*) as n
               FROM experiment_assignment WHERE experiment_id = ?
               GROUP BY variant""",
            (experiment_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"passed": True, "reason": "unavailable"}

    if len(counts) < 2:
        return {"passed": True}

    n_values = [r["n"] for r in counts]
    total = sum(n_values)
    if total < 50:
        return {"passed": True, "reason": "insufficient_sample"}

    current_ratio = n_values[0] / total
    deviation = abs(current_ratio - expected_ratio) * 100

    passed = deviation <= max_deviation_pp
    result = {
        "passed": passed,
        "current_ratio": round(current_ratio, 4),
        "expected_ratio": expected_ratio,
        "deviation_pp": round(deviation, 2),
    }

    if not passed:
        logger.warning(
            "Assignment drift for experiment %d: ratio=%.4f, expected=%.4f, drift=%.2fpp",
            experiment_id, current_ratio, expected_ratio, deviation,
        )

    return result


def check_exposure_imbalance(
    conn: sqlite3.Connection,
    experiment_id: int,
    max_differential: float = 0.05,
) -> dict:
    """Check whether exposure rates differ between arms.

    Exposure rate = users exposed / users assigned.  A differential > 5% suggests
    the experiment is not reaching one arm as intended.
    """
    try:
        exp = conn.execute(
            "SELECT variants FROM experiment WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        if not exp:
            return {"passed": True}

        variant_names = json.loads(exp["variants"])
        if len(variant_names) < 2:
            return {"passed": True}

        rates = {}
        for variant in variant_names:
            assigned = conn.execute(
                "SELECT COUNT(DISTINCT user_id) as n FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
                (experiment_id, variant),
            ).fetchone()["n"]

            exposed = conn.execute(
                "SELECT COUNT(DISTINCT user_id) as n FROM experiment_exposure WHERE experiment_id = ? AND variant = ?",
                (experiment_id, variant),
            ).fetchone()["n"]

            rates[variant] = exposed / assigned if assigned > 0 else 0.0

        rate_values = list(rates.values())
        if len(rate_values) >= 2:
            differential = abs(rate_values[0] - rate_values[1])
        else:
            differential = 0.0

        passed = differential <= max_differential

        return {
            "passed": passed,
            "exposure_rates": {k: round(v, 4) for k, v in rates.items()},
            "differential": round(differential, 4),
        }
    except sqlite3.OperationalError:
        return {"passed": True, "reason": "table_unavailable"}


# ── Internal helpers ─────────────────────────────────────────────────────────


def _get_arm_user_ids(
    conn: sqlite3.Connection, experiment_id: int, variant: str,
) -> list[int]:
    rows = conn.execute(
        "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
        (experiment_id, variant),
    ).fetchall()
    return [r["user_id"] for r in rows]


def _standardised_mean_diff(a: list[float], b: list[float]) -> float | None:
    """Cohen's d (pooled SD)."""
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return None
    m1 = sum(a) / n1
    m2 = sum(b) / n2
    v1 = sum((x - m1) ** 2 for x in a) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in b) / (n2 - 1)
    pooled_sd = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if pooled_sd == 0:
        return 0.0
    return (m1 - m2) / pooled_sd


def _chi2_sf(x: float, df: int = 1) -> float:
    """Survival function (1 - CDF) of the chi-squared distribution.

    Uses the regularised incomplete gamma function approximation via the
    relationship: chi2_sf(x, k) = 1 - regularised_gamma(k/2, x/2).
    For df=1 this simplifies to: erfc(sqrt(x/2)).
    """
    if df == 1:
        return math.erfc(math.sqrt(x / 2))
    # General case: rough approximation using normal
    z = (x / df - 1 + 2 / (9 * df)) / math.sqrt(2 / (9 * df)) if df > 0 else 0
    return max(0.0, 0.5 * math.erfc(z / math.sqrt(2)))


def _persist_balance_check(
    conn: sqlite3.Connection,
    experiment_id: int,
    check_type: str,
    passed: bool,
    details: dict,
) -> None:
    try:
        conn.execute(
            """INSERT INTO experiment_balance_check
               (experiment_id, check_type, passed, details, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                experiment_id,
                check_type,
                int(passed),
                json.dumps(details),
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Table may not exist yet


# ── Covariate query functions ────────────────────────────────────────────────
# Each returns a list of floats for the given user IDs.


def _query_session_count(conn: sqlite3.Connection, user_ids: list[int]) -> list[float]:
    if not user_ids:
        return []
    ph = ",".join("?" * len(user_ids))
    sql = f"""SELECT user_id, COUNT(*) as cnt FROM session_log
            WHERE user_id IN ({ph}) GROUP BY user_id"""
    rows = conn.execute(sql, user_ids).fetchall()
    return [float(r["cnt"]) for r in rows]


def _query_avg_accuracy(conn: sqlite3.Connection, user_ids: list[int]) -> list[float]:
    if not user_ids:
        return []
    ph = ",".join("?" * len(user_ids))
    try:
        sql = f"""SELECT user_id,
                    SUM(items_correct) * 1.0 / NULLIF(SUM(items_completed), 0) as acc
                FROM session_log
                WHERE user_id IN ({ph})
                GROUP BY user_id"""
        rows = conn.execute(sql, user_ids).fetchall()
        return [float(r["acc"]) for r in rows if r["acc"] is not None]
    except sqlite3.OperationalError:
        return []


def _query_tenure_days(conn: sqlite3.Connection, user_ids: list[int]) -> list[float]:
    if not user_ids:
        return []
    ph = ",".join("?" * len(user_ids))
    try:
        sql = f"SELECT julianday('now') - julianday(created_at) as days FROM user WHERE id IN ({ph})"
        rows = conn.execute(sql, user_ids).fetchall()
        return [float(r["days"]) for r in rows if r["days"] is not None]
    except sqlite3.OperationalError:
        return []


_COVARIATE_QUERIES = {
    "session_count": _query_session_count,
    "avg_accuracy": _query_avg_accuracy,
    "tenure_days": _query_tenure_days,
}
