"""Counter-metric self-validation — does the anti-gaming system actually work?

Tracks alert precision/recall, action effectiveness, and meta-honesty.
The counter-metric system must watch itself to prevent:
- Crying wolf (too many false positive alerts that disrupt learning)
- Missing real problems (false negatives that let gaming slide)
- Ineffective countermeasures (actions that don't actually fix the problem)
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta, timezone, UTC
from typing import Any

logger = logging.getLogger(__name__)


# ── Metric-to-layer mapping ──────────────────────────────────────────
# Used for coverage analysis: which of the 5 layers is each alert metric in?

_METRIC_LAYER = {
    # Integrity
    "delayed_recall_7d": "integrity",
    "delayed_recall_30d": "integrity",
    "transfer_accuracy": "integrity",
    "production_accuracy": "integrity",
    "recognition_production_gap": "integrity",
    "mastery_reversal_rate": "integrity",
    "mastery_survival_30d": "integrity",
    "hint_dependence_rate": "integrity",
    # Cost
    "fatigue_score": "cost",
    "early_exit_rate": "cost",
    "overdue_rate": "cost",
    # Distortion
    "suspicious_fast_rate": "distortion",
    "recognition_only_rate": "distortion",
    "low_challenge_rate": "distortion",
    # Outcome
    "holdout_accuracy": "outcome",
    "progress_honesty_score": "outcome",
    # Content quality
    "content_duplicate_rate": "content",
    "content_rejection_rate": "content",
    "content_review_queue_depth": "content",
    "content_approval_latency_days": "content",
    "content_reaudit_failure_rate": "content",
    "content_rubber_stamp_rate": "content",
}

# All layers that should be producing alerts over time
_ALL_LAYERS = {"integrity", "cost", "distortion", "outcome", "content"}

# How many days after an action to check for metric improvement
_OUTCOME_WINDOW_DAYS = 14

# Ideal alert rate: alerts should fire on 20-40% of snapshots.
# Too low means thresholds are too loose; too high means crying wolf.
_IDEAL_ALERT_RATE = 0.30


# ── Helper utilities ──────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _parse_json_safe(raw: str | None) -> Any:
    """Parse JSON, returning empty structure on failure."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _iso_to_dt(iso_str: str) -> datetime | None:
    """Parse an ISO-format string to a timezone-aware datetime."""
    if not iso_str:
        return None
    try:
        # Handle both Z-suffix and +00:00 formats
        s = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _find_snapshot_near(
    conn: sqlite3.Connection,
    target_dt: datetime,
    user_id: int = 1,
    direction: str = "before",
) -> dict | None:
    """Find the snapshot closest to target_dt in the given direction.

    direction: "before" finds the latest snapshot <= target_dt
               "after"  finds the earliest snapshot >= target_dt
    """
    target_iso = target_dt.isoformat()
    if direction == "before":
        row = conn.execute("""
            SELECT * FROM counter_metric_snapshot
            WHERE user_id = ? AND computed_at <= ?
            ORDER BY computed_at DESC LIMIT 1
        """, (user_id, target_iso)).fetchone()
    else:
        row = conn.execute("""
            SELECT * FROM counter_metric_snapshot
            WHERE user_id = ? AND computed_at >= ?
            ORDER BY computed_at ASC LIMIT 1
        """, (user_id, target_iso)).fetchone()

    return dict(row) if row else None


def _extract_metric_value(snapshot: dict, metric_name: str) -> float | None:
    """Extract a specific metric value from a snapshot's JSON columns.

    Searches alerts_json first (has direct metric name -> value),
    then falls back to layer-specific JSON columns.
    """
    # Try alerts_json — each alert has {"metric": name, "value": v}
    alerts = _parse_json_safe(snapshot.get("alerts_json"))
    if isinstance(alerts, list):
        for alert in alerts:
            if alert.get("metric") == metric_name:
                val = alert.get("value")
                if val is not None:
                    return float(val)

    # Fall back: scan layer JSON columns for the metric
    # The metric name is often a key within the layer dict
    layer = _METRIC_LAYER.get(metric_name)
    layer_col_map = {
        "integrity": "integrity_json",
        "cost": "cost_json",
        "distortion": "distortion_json",
        "outcome": "outcome_json",
    }
    col = layer_col_map.get(layer)
    if col:
        layer_data = _parse_json_safe(snapshot.get(col))
        if isinstance(layer_data, dict):
            # Search nested dicts for any value that matches the metric name
            for _key, sub in layer_data.items():
                if isinstance(sub, dict):
                    # Common patterns: "accuracy", "rate", "score" suffixes
                    for val_key in (
                        "accuracy", "rate", "score", "value",
                        "reversal_rate", "dependence_rate", "gap",
                        "fatigue_score", "early_exit_rate", "overdue_rate",
                        "suspicious_fast_rate", "recognition_only_rate",
                        "low_challenge_rate", "holdout_accuracy",
                        "honesty_score",
                    ):
                        if val_key in sub:
                            # Match by convention: metric name contains the key
                            if metric_name.replace("_", "") in _key.replace("_", ""):
                                val = sub[val_key]
                                if val is not None:
                                    return float(val)

    return None


def _metric_improved(
    before_val: float | None,
    after_val: float | None,
    metric_name: str,
) -> bool | None:
    """Did the metric improve (move in the healthy direction)?

    Returns True if improved, False if worsened, None if indeterminate.
    """
    if before_val is None or after_val is None:
        return None

    # Import direction from ALERT_THRESHOLDS to know which way is "good"
    try:
        from .counter_metrics import ALERT_THRESHOLDS
        thresh = ALERT_THRESHOLDS.get(metric_name, {})
        direction = thresh.get("direction")
    except ImportError:
        direction = None

    if direction is None:
        # Guess from metric name: rates and scores "above" = bad
        if any(kw in metric_name for kw in ("rate", "gap", "fatigue", "fast")):
            direction = "above"
        else:
            direction = "below"

    if direction == "below":
        # Lower is worse, so improvement means after > before
        return after_val > before_val
    else:
        # Higher is worse, so improvement means after < before
        return after_val < before_val


# ═══════════════════════════════════════════════════════════════════════
# ALERT OUTCOME VALIDATION — precision of the alerting system
# ═══════════════════════════════════════════════════════════════════════

def validate_alert_outcomes(
    conn: sqlite3.Connection,
    lookback_days: int = 30,
    user_id: int = 1,
) -> dict:
    """For each resolved alert, check if the target metric actually improved.

    True positive: alert fired AND metric improved within 14 days
    False positive: alert fired AND metric did NOT improve
    False negative: no alert BUT metric degraded (detected post-hoc)

    Returns:
        {
            "total_alerts": int,
            "true_positives": int,
            "false_positives": int,
            "indeterminate": int,
            "precision": float (0-1),
            "by_metric": {metric_name: {"tp": int, "fp": int, "precision": float}},
        }
    """
    result = {
        "total_alerts": 0,
        "true_positives": 0,
        "false_positives": 0,
        "indeterminate": 0,
        "precision": 0.0,
        "by_metric": {},
    }

    if not _table_exists(conn, "counter_metric_action_log"):
        logger.debug("counter_metric_action_log table not found")
        return result

    if not _table_exists(conn, "counter_metric_snapshot"):
        logger.debug("counter_metric_snapshot table not found")
        return result

    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

    try:
        rows = conn.execute("""
            SELECT action_type, metric_name, severity, details_json, created_at
            FROM counter_metric_action_log
            WHERE created_at >= ?
            ORDER BY created_at ASC
        """, (cutoff,)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Failed to query counter_metric_action_log", exc_info=True)
        return result

    by_metric: dict[str, dict] = {}

    for row in rows:
        row_dict = dict(row) if hasattr(row, "keys") else {
            "action_type": row[0], "metric_name": row[1],
            "severity": row[2], "details_json": row[3], "created_at": row[4],
        }
        metric_name = row_dict["metric_name"]
        action_dt = _iso_to_dt(row_dict["created_at"])
        if not action_dt:
            continue

        # Find snapshot BEFORE the action (baseline)
        snap_before = _find_snapshot_near(conn, action_dt, user_id, "before")
        # Find snapshot AFTER the outcome window
        outcome_dt = action_dt + timedelta(days=_OUTCOME_WINDOW_DAYS)
        snap_after = _find_snapshot_near(conn, outcome_dt, user_id, "after")

        # If the outcome window hasn't elapsed yet, try the most recent snapshot
        if snap_after is None:
            snap_after = _find_snapshot_near(
                conn, datetime.now(UTC), user_id, "before"
            )

        val_before = _extract_metric_value(snap_before, metric_name) if snap_before else None
        val_after = _extract_metric_value(snap_after, metric_name) if snap_after else None

        improved = _metric_improved(val_before, val_after, metric_name)

        if metric_name not in by_metric:
            by_metric[metric_name] = {"tp": 0, "fp": 0, "indeterminate": 0}

        result["total_alerts"] += 1

        if improved is True:
            result["true_positives"] += 1
            by_metric[metric_name]["tp"] += 1
        elif improved is False:
            result["false_positives"] += 1
            by_metric[metric_name]["fp"] += 1
        else:
            result["indeterminate"] += 1
            by_metric[metric_name]["indeterminate"] += 1

    # Compute precision per metric and overall
    determined = result["true_positives"] + result["false_positives"]
    if determined > 0:
        result["precision"] = round(result["true_positives"] / determined, 4)

    for metric_name, counts in by_metric.items():
        m_determined = counts["tp"] + counts["fp"]
        counts["precision"] = round(counts["tp"] / m_determined, 4) if m_determined > 0 else 0.0

    result["by_metric"] = by_metric
    return result


# ═══════════════════════════════════════════════════════════════════════
# ACTION EFFECTIVENESS — do countermeasures actually fix the problem?
# ═══════════════════════════════════════════════════════════════════════

def score_action_effectiveness(
    conn: sqlite3.Connection,
    metric_name: str | None = None,
    user_id: int = 1,
    lookback_days: int = 90,
) -> dict:
    """Score how effective each action rule is at fixing problems.

    For each (metric, action_type) pair, compute:
    - success_rate: % of times the metric improved after action
    - avg_improvement: average metric change after action
    - sample_size: number of times this action was triggered

    Returns:
        {
            "actions": {
                "delayed_recall_7d:scheduler_adjust": {
                    "success_rate": float,
                    "avg_improvement": float,
                    "sample_size": int,
                    "effective": bool (success_rate > 0.30)
                },
                ...
            },
            "ineffective_actions": [list of action keys with success_rate < 0.30 and sample >= 5],
        }
    """
    result: dict[str, Any] = {"actions": {}, "ineffective_actions": []}

    if not _table_exists(conn, "counter_metric_action_log"):
        return result

    if not _table_exists(conn, "counter_metric_snapshot"):
        return result

    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

    try:
        query = """
            SELECT action_type, metric_name, severity, details_json, created_at
            FROM counter_metric_action_log
            WHERE created_at >= ?
        """
        params: list = [cutoff]
        if metric_name:
            query += " AND metric_name = ?"
            params.append(metric_name)
        query += " ORDER BY created_at ASC"

        rows = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Failed to query counter_metric_action_log", exc_info=True)
        return result

    # Group by (metric_name, action_type)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        row_dict = dict(row) if hasattr(row, "keys") else {
            "action_type": row[0], "metric_name": row[1],
            "severity": row[2], "details_json": row[3], "created_at": row[4],
        }
        key = f"{row_dict['metric_name']}:{row_dict['action_type']}"
        groups.setdefault(key, []).append(row_dict)

    for key, action_rows in groups.items():
        successes = 0
        improvements: list[float] = []
        total = 0

        for action_row in action_rows:
            action_dt = _iso_to_dt(action_row["created_at"])
            if not action_dt:
                continue

            m_name = action_row["metric_name"]
            snap_before = _find_snapshot_near(conn, action_dt, user_id, "before")
            outcome_dt = action_dt + timedelta(days=_OUTCOME_WINDOW_DAYS)
            snap_after = _find_snapshot_near(conn, outcome_dt, user_id, "after")

            if snap_after is None:
                snap_after = _find_snapshot_near(
                    conn, datetime.now(UTC), user_id, "before"
                )

            val_before = _extract_metric_value(snap_before, m_name) if snap_before else None
            val_after = _extract_metric_value(snap_after, m_name) if snap_after else None

            improved = _metric_improved(val_before, val_after, m_name)
            total += 1

            if improved is True:
                successes += 1

            if val_before is not None and val_after is not None:
                improvements.append(val_after - val_before)

        success_rate = round(successes / total, 4) if total > 0 else 0.0
        avg_improvement = (
            round(sum(improvements) / len(improvements), 4)
            if improvements
            else 0.0
        )

        action_entry = {
            "success_rate": success_rate,
            "avg_improvement": avg_improvement,
            "sample_size": total,
            "effective": success_rate > 0.30,
        }
        result["actions"][key] = action_entry

        # Flag ineffective actions with sufficient sample size
        if success_rate < 0.30 and total >= 5:
            result["ineffective_actions"].append(key)

    return result


# ═══════════════════════════════════════════════════════════════════════
# META-HONESTY — is the counter-metric system itself honest?
# ═══════════════════════════════════════════════════════════════════════

def compute_meta_honesty(
    conn: sqlite3.Connection,
    user_id: int = 1,
    lookback_days: int = 90,
) -> dict:
    """Is the counter-metric system itself honest?

    Checks:
    1. Alert rate: if <10% over 90 days, thresholds may be too loose
    2. False positive rate: if >50%, thresholds may be too tight (crying wolf)
    3. Action correlation: do actions correlate with downstream improvement?
    4. Coverage: are all 5 layers producing alerts, or is one silent?

    Returns:
        {
            "meta_honesty_score": float (0-100),
            "alert_rate": float,
            "false_positive_rate": float,
            "action_correlation": float,
            "layer_coverage": dict,
            "interpretation": str,
        }
    """
    result = {
        "meta_honesty_score": 0.0,
        "alert_rate": 0.0,
        "false_positive_rate": 0.0,
        "action_correlation": 0.0,
        "layer_coverage": {},
        "interpretation": "insufficient data",
    }

    if not _table_exists(conn, "counter_metric_snapshot"):
        return result

    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

    # ── 1. Alert rate: fraction of snapshots that had at least one alert ──
    try:
        total_snapshots_row = conn.execute("""
            SELECT COUNT(*) FROM counter_metric_snapshot
            WHERE user_id = ? AND computed_at >= ?
        """, (user_id, cutoff)).fetchone()
        total_snapshots = total_snapshots_row[0] if total_snapshots_row else 0

        alerting_snapshots_row = conn.execute("""
            SELECT COUNT(*) FROM counter_metric_snapshot
            WHERE user_id = ? AND computed_at >= ? AND alert_count > 0
        """, (user_id, cutoff)).fetchone()
        alerting_snapshots = alerting_snapshots_row[0] if alerting_snapshots_row else 0
    except sqlite3.OperationalError:
        logger.warning("Failed to query snapshot counts", exc_info=True)
        total_snapshots = 0
        alerting_snapshots = 0

    alert_rate = (
        round(alerting_snapshots / total_snapshots, 4)
        if total_snapshots > 0
        else 0.0
    )
    result["alert_rate"] = alert_rate

    # ── 2. False positive rate from alert outcome validation ──
    try:
        outcomes = validate_alert_outcomes(conn, lookback_days=lookback_days, user_id=user_id)
        determined = outcomes["true_positives"] + outcomes["false_positives"]
        fp_rate = (
            round(outcomes["false_positives"] / determined, 4)
            if determined > 0
            else 0.0
        )
    except Exception:
        logger.warning("Failed to compute alert outcomes for meta-honesty", exc_info=True)
        outcomes = {"true_positives": 0, "false_positives": 0}
        fp_rate = 0.0

    result["false_positive_rate"] = fp_rate

    # ── 3. Action correlation: fraction of actions that led to improvement ──
    try:
        effectiveness = score_action_effectiveness(
            conn, user_id=user_id, lookback_days=lookback_days
        )
        action_entries = effectiveness.get("actions", {})
        if action_entries:
            # Weighted average of success rates by sample size
            total_samples = sum(a["sample_size"] for a in action_entries.values())
            if total_samples > 0:
                weighted_sum = sum(
                    a["success_rate"] * a["sample_size"]
                    for a in action_entries.values()
                )
                action_correlation = round(weighted_sum / total_samples, 4)
            else:
                action_correlation = 0.0
        else:
            action_correlation = 0.0
    except Exception:
        logger.warning("Failed to compute action effectiveness for meta-honesty", exc_info=True)
        action_correlation = 0.0

    result["action_correlation"] = action_correlation

    # ── 4. Layer coverage: which layers have produced at least one alert? ──
    layers_seen: set[str] = set()
    try:
        snap_rows = conn.execute("""
            SELECT alerts_json FROM counter_metric_snapshot
            WHERE user_id = ? AND computed_at >= ?
        """, (user_id, cutoff)).fetchall()

        for snap_row in snap_rows:
            raw = snap_row[0] if snap_row else None
            alerts = _parse_json_safe(raw)
            if isinstance(alerts, list):
                for alert in alerts:
                    metric = alert.get("metric", "")
                    layer = _METRIC_LAYER.get(metric)
                    if layer:
                        layers_seen.add(layer)
    except sqlite3.OperationalError:
        logger.warning("Failed to scan snapshots for layer coverage", exc_info=True)

    layer_coverage = {
        layer: layer in layers_seen for layer in sorted(_ALL_LAYERS)
    }
    result["layer_coverage"] = layer_coverage
    coverage_fraction = len(layers_seen) / len(_ALL_LAYERS) if _ALL_LAYERS else 0.0

    # ── Composite meta-honesty score ──
    # 100 * (1 - |ideal_alert_rate - actual_alert_rate|) *
    #        (1 - false_positive_rate) *
    #        coverage_fraction
    #
    # Clamp each factor to [0, 1] for robustness.

    alert_rate_factor = max(0.0, 1.0 - abs(_IDEAL_ALERT_RATE - alert_rate))
    fp_factor = max(0.0, 1.0 - fp_rate)
    coverage_factor = min(1.0, coverage_fraction)

    raw_score = 100.0 * alert_rate_factor * fp_factor * coverage_factor
    meta_score = round(max(0.0, min(100.0, raw_score)), 1)
    result["meta_honesty_score"] = meta_score

    # ── Interpretation ──
    if total_snapshots < 5:
        interpretation = "insufficient data — need at least 5 snapshots for meaningful analysis"
    elif meta_score >= 80:
        interpretation = (
            "counter-metric system is well-calibrated: alerts fire at a reasonable rate, "
            "actions correlate with improvement, and all layers are active"
        )
    elif meta_score >= 50:
        problems = []
        if alert_rate < 0.10:
            problems.append("alert rate too low (thresholds may be too loose)")
        elif alert_rate > 0.60:
            problems.append("alert rate too high (thresholds may be too tight)")
        if fp_rate > 0.50:
            problems.append("high false positive rate (crying wolf)")
        if coverage_fraction < 0.80:
            silent = [l for l in _ALL_LAYERS if l not in layers_seen]
            problems.append(f"silent layers: {', '.join(sorted(silent))}")
        interpretation = (
            "counter-metric system needs attention: " + "; ".join(problems)
            if problems
            else "moderate calibration — some room for improvement"
        )
    else:
        problems = []
        if alert_rate < 0.10:
            problems.append("nearly silent — thresholds may be meaningless")
        if fp_rate > 0.70:
            problems.append("mostly false positives — alerts are noise, not signal")
        if coverage_fraction < 0.60:
            silent = [l for l in _ALL_LAYERS if l not in layers_seen]
            problems.append(f"major blind spots in layers: {', '.join(sorted(silent))}")
        if action_correlation < 0.20:
            problems.append("actions rarely lead to improvement — interventions may be wrong")
        interpretation = (
            "counter-metric system is poorly calibrated: " + "; ".join(problems)
            if problems
            else "low meta-honesty — the system watching for gaming may itself be broken"
        )

    result["interpretation"] = interpretation
    return result


# ═══════════════════════════════════════════════════════════════════════
# ALERT HISTORY — trend analysis of the alerting system itself
# ═══════════════════════════════════════════════════════════════════════

def get_alert_history(
    conn: sqlite3.Connection,
    days: int = 90,
    user_id: int = 1,
) -> list[dict]:
    """Get historical alerts for trend analysis.

    Returns a list of dicts, one per snapshot that had alerts:
        [
            {
                "computed_at": str,
                "overall_health": str,
                "alert_count": int,
                "critical_count": int,
                "alerts": [{"metric": ..., "severity": ..., "value": ...}, ...],
            },
            ...
        ]
    """
    if not _table_exists(conn, "counter_metric_snapshot"):
        return []

    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    try:
        rows = conn.execute("""
            SELECT computed_at, overall_health, alert_count, critical_count, alerts_json
            FROM counter_metric_snapshot
            WHERE user_id = ? AND computed_at >= ?
            ORDER BY computed_at ASC
        """, (user_id, cutoff)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Failed to query alert history", exc_info=True)
        return []

    history = []
    for row in rows:
        row_dict = dict(row) if hasattr(row, "keys") else {
            "computed_at": row[0], "overall_health": row[1],
            "alert_count": row[2], "critical_count": row[3], "alerts_json": row[4],
        }
        alerts = _parse_json_safe(row_dict.get("alerts_json"))
        if not isinstance(alerts, list):
            alerts = []

        history.append({
            "computed_at": row_dict["computed_at"],
            "overall_health": row_dict["overall_health"],
            "alert_count": row_dict.get("alert_count", len(alerts)),
            "critical_count": row_dict.get("critical_count", 0),
            "alerts": alerts,
        })

    return history


# ═══════════════════════════════════════════════════════════════════════
# FULL VALIDATION REPORT — run everything and return a summary
# ═══════════════════════════════════════════════════════════════════════

def run_full_validation(
    conn: sqlite3.Connection,
    user_id: int = 1,
    lookback_days: int = 90,
) -> dict:
    """Run all self-validation checks and return a combined report.

    This is the entry point for scheduled validation runs.

    Returns:
        {
            "computed_at": str,
            "alert_outcomes": {...},
            "action_effectiveness": {...},
            "meta_honesty": {...},
            "alert_history_length": int,
            "recommendations": [str, ...],
        }
    """
    now = datetime.now(UTC).isoformat()

    alert_outcomes = validate_alert_outcomes(
        conn, lookback_days=lookback_days, user_id=user_id
    )
    action_effectiveness = score_action_effectiveness(
        conn, user_id=user_id, lookback_days=lookback_days
    )
    meta = compute_meta_honesty(
        conn, user_id=user_id, lookback_days=lookback_days
    )
    history = get_alert_history(conn, days=lookback_days, user_id=user_id)

    # Generate actionable recommendations
    recommendations: list[str] = []

    # Precision-based recommendations
    precision = alert_outcomes.get("precision", 0.0)
    total = alert_outcomes.get("total_alerts", 0)
    if total >= 10 and precision < 0.40:
        recommendations.append(
            f"Alert precision is only {precision:.0%} — consider tightening thresholds "
            f"for metrics with high false positive rates"
        )

    # Ineffective action recommendations
    ineffective = action_effectiveness.get("ineffective_actions", [])
    if ineffective:
        recommendations.append(
            f"{len(ineffective)} action rule(s) have <30% success rate with "
            f"sufficient samples: {', '.join(ineffective)}. "
            f"Review whether these interventions are appropriate."
        )

    # Layer coverage recommendations
    coverage = meta.get("layer_coverage", {})
    silent_layers = [layer for layer, active in coverage.items() if not active]
    if silent_layers:
        recommendations.append(
            f"Layers with no alerts in {lookback_days} days: "
            f"{', '.join(silent_layers)}. "
            f"Either thresholds are too loose or metrics are not being computed."
        )

    # Alert rate recommendations
    alert_rate = meta.get("alert_rate", 0.0)
    if alert_rate < 0.10 and len(history) >= 10:
        recommendations.append(
            "Alert rate is below 10% — the system may be too permissive. "
            "Review whether ALERT_THRESHOLDS are still appropriate."
        )
    elif alert_rate > 0.60 and len(history) >= 10:
        recommendations.append(
            "Alert rate exceeds 60% — the system may be crying wolf. "
            "Consider relaxing thresholds for frequently-firing metrics."
        )

    # Meta-honesty score recommendation
    meta_score = meta.get("meta_honesty_score", 0.0)
    if meta_score < 50 and len(history) >= 10:
        recommendations.append(
            f"Meta-honesty score is {meta_score:.0f}/100 — the counter-metric system "
            f"itself may not be trustworthy. Manual audit recommended."
        )

    return {
        "computed_at": now,
        "alert_outcomes": alert_outcomes,
        "action_effectiveness": action_effectiveness,
        "meta_honesty": meta,
        "alert_history_length": len(history),
        "recommendations": recommendations,
    }
