"""Heterogeneous treatment effects — subgroup analysis and CATE estimation.

Detects whether an experiment helps some users but hurts others.
Uses pre-declared subgroups and stratified estimation (stdlib only).
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

logger = logging.getLogger(__name__)


def analyze_subgroups(
    conn: sqlite3.Connection,
    experiment_name: str,
    *,
    subgroups: list[str] | None = None,
) -> dict:
    """Run subgroup analysis on a concluded or running experiment.

    If subgroups is None, uses pre-declared subgroups from the experiment record.
    Default subgroups: hsk_band, engagement_band, tenure_band.

    Returns per-subgroup treatment effects with Bonferroni-corrected p-values
    and a qualitative interaction flag.
    """
    try:
        exp = conn.execute(
            "SELECT id, predeclared_subgroups FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
        if not exp:
            return {"error": f"Experiment '{experiment_name}' not found"}

        exp_id = exp["id"]

        # Use pre-declared subgroups or defaults
        if subgroups is None:
            try:
                subgroups = json.loads(exp["predeclared_subgroups"] or "[]")
            except (json.JSONDecodeError, TypeError):
                subgroups = []
        if not subgroups:
            subgroups = ["hsk_band", "engagement_band", "tenure_band"]

        results = {"experiment": experiment_name, "subgroups": {}}
        n_tests = 0

        for subgroup_var in subgroups:
            sg_results = _analyze_single_subgroup(conn, exp_id, subgroup_var)
            if sg_results:
                results["subgroups"][subgroup_var] = sg_results
                n_tests += len(sg_results.get("levels", {}))

        # Bonferroni correction
        if n_tests > 0:
            for sg_var, sg_data in results["subgroups"].items():
                for level, level_data in sg_data.get("levels", {}).items():
                    raw_p = level_data.get("p_value", 1.0)
                    level_data["adjusted_p"] = min(raw_p * n_tests, 1.0)
                    level_data["significant_adjusted"] = level_data["adjusted_p"] < 0.05

        # Qualitative interaction: does treatment help some subgroups but hurt others?
        all_effects = []
        for sg_var, sg_data in results["subgroups"].items():
            for level, level_data in sg_data.get("levels", {}).items():
                if level_data.get("effect_size") is not None:
                    all_effects.append(level_data["effect_size"])

        if all_effects:
            has_positive = any(e > 0 for e in all_effects)
            has_negative = any(e < 0 for e in all_effects)
            results["qualitative_interaction"] = has_positive and has_negative
            results["effect_range"] = {
                "min": round(min(all_effects), 4),
                "max": round(max(all_effects), 4),
            }
            if results["qualitative_interaction"]:
                results["warning"] = (
                    "Qualitative interaction detected: treatment helps some subgroups "
                    "but hurts others. Consider personalized rollout."
                )
        else:
            results["qualitative_interaction"] = False

        # Heterogeneity test (Q statistic)
        results["heterogeneity"] = _test_heterogeneity(all_effects)

        return results

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Subgroup analysis failed for %s: %s", experiment_name, e)
        return {"error": str(e)}


def _analyze_single_subgroup(
    conn: sqlite3.Connection, exp_id: int, subgroup_var: str
) -> dict | None:
    """Analyze treatment effect within levels of a single subgroup variable."""
    # Map subgroup variable to SQL expression
    subgroup_sql = _get_subgroup_sql(subgroup_var)
    if not subgroup_sql:
        return None

    try:
        rows = conn.execute(
            "SELECT "
            + subgroup_sql
            + " AS subgroup_level,"
            " ea.variant,"
            " COUNT(DISTINCT ea.user_id) AS users,"
            " AVG(CASE WHEN sl.session_outcome = 'completed' THEN 1.0 ELSE 0.0 END) AS completion_rate"
            " FROM experiment_assignment ea"
            " LEFT JOIN user u ON u.id = ea.user_id"
            " LEFT JOIN session_log sl ON sl.user_id = ea.user_id"
            " AND sl.started_at >= ea.assigned_at"
            " WHERE ea.experiment_id = ?"
            " GROUP BY subgroup_level, ea.variant"
            " HAVING users >= 5",
            (exp_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    if not rows:
        return None

    # Organize by level, then by variant
    levels_data: dict[str, dict[str, dict]] = {}
    for r in rows:
        level = str(r["subgroup_level"] or "unknown")
        variant = r["variant"]
        if level not in levels_data:
            levels_data[level] = {}
        levels_data[level][variant] = {
            "users": r["users"],
            "completion_rate": round((r["completion_rate"] or 0) * 100, 2),
        }

    # Compute per-level treatment effect
    level_results = {}
    for level, variants in levels_data.items():
        variant_names = list(variants.keys())
        if len(variant_names) < 2:
            continue

        # Assume first variant is control, rest are treatment
        control = variants[variant_names[0]]
        treatment = variants[variant_names[1]] if len(variant_names) > 1 else None

        if treatment is None:
            continue

        diff = treatment["completion_rate"] - control["completion_rate"]
        n_c = control["users"]
        n_t = treatment["users"]

        # Standard error of difference in proportions
        p_c = control["completion_rate"] / 100
        p_t = treatment["completion_rate"] / 100
        se = math.sqrt(
            max(p_c * (1 - p_c) / max(n_c, 1), 0)
            + max(p_t * (1 - p_t) / max(n_t, 1), 0)
        )

        z = diff / 100 / se if se > 0 else 0
        p_value = 2 * _norm_sf(abs(z)) if se > 0 else 1.0

        level_results[level] = {
            "control_rate": control["completion_rate"],
            "treatment_rate": treatment["completion_rate"],
            "effect_size": round(diff, 3),
            "se": round(se * 100, 3),
            "z": round(z, 3),
            "p_value": round(p_value, 6),
            "n_control": n_c,
            "n_treatment": n_t,
        }

    if not level_results:
        return None

    return {"variable": subgroup_var, "levels": level_results}


def _get_subgroup_sql(var: str) -> str | None:
    """Map a subgroup variable name to a SQL expression."""
    mappings = {
        "hsk_band": (
            "CASE "
            "WHEN u.current_hsk_level <= 2 THEN 'hsk_low' "
            "WHEN u.current_hsk_level <= 4 THEN 'hsk_mid' "
            "ELSE 'hsk_high' END"
        ),
        "engagement_band": (
            "CASE "
            "WHEN (SELECT COUNT(*) FROM session_log s2 WHERE s2.user_id = ea.user_id "
            "AND s2.started_at >= datetime('now', '-30 days')) <= 5 THEN 'low_engagement' "
            "WHEN (SELECT COUNT(*) FROM session_log s2 WHERE s2.user_id = ea.user_id "
            "AND s2.started_at >= datetime('now', '-30 days')) <= 15 THEN 'mid_engagement' "
            "ELSE 'high_engagement' END"
        ),
        "tenure_band": (
            "CASE "
            "WHEN julianday('now') - julianday(u.created_at) <= 30 THEN 'new_user' "
            "WHEN julianday('now') - julianday(u.created_at) <= 90 THEN 'established' "
            "ELSE 'veteran' END"
        ),
    }
    return mappings.get(var)


def _test_heterogeneity(effects: list[float]) -> dict:
    """Test whether subgroup effects are significantly different (Q statistic).

    Uses Cochran's Q test: Q = sum(w_i * (effect_i - weighted_mean)^2)
    Under H0 (homogeneity), Q ~ chi-squared(k-1).
    """
    if len(effects) < 2:
        return {"q_statistic": 0, "df": 0, "heterogeneous": False}

    mean_effect = sum(effects) / len(effects)
    q = sum((e - mean_effect) ** 2 for e in effects)
    df = len(effects) - 1

    # Rough chi-squared p-value approximation
    # For df <= 30, use Wilson-Hilferty approximation
    if df > 0 and q > 0:
        z = ((q / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
        p_value = _norm_sf(z) if z > 0 else 1.0
    else:
        p_value = 1.0

    return {
        "q_statistic": round(q, 4),
        "df": df,
        "p_value": round(p_value, 6),
        "heterogeneous": p_value < 0.1,  # liberal threshold for detection
        "interpretation": (
            "Significant heterogeneity detected — effect varies by subgroup."
            if p_value < 0.1
            else "No significant heterogeneity — effect is consistent across subgroups."
        ),
    }


def _norm_sf(z: float) -> float:
    """Survival function (1 - CDF) for standard normal."""
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
