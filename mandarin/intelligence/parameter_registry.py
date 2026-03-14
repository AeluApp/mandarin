"""Product Intelligence — Parameter Registry & Influence Model.

Structured inventory of every tunable parameter in the codebase.
Learned influence edges: parameter → metric, weighted by observed outcomes.
Replaces the curated _FINDING_TO_ACTION table over time.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from ._base import _VERIFICATION_WINDOWS, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# Pending registrations — populated by @register_parameter decorator at import time
_PARAMETER_REGISTRY_PENDING = []


def register_parameter(
    name: str,
    file_path: str,
    value_type: str,
    primary_dimension: str,
    min_valid=None,
    max_valid=None,
    soft_min=None,
    soft_max=None,
    change_direction="unknown",
    secondary_dimensions=None,
    notes=None,
):
    """Decorator that registers a module-level constant in pi_parameter_registry.

    Usage:
        @register_parameter(
            name='MAX_NEW_ITEM_RATIO',
            file_path='mandarin/config.py',
            value_type='ratio',
            primary_dimension='srs_funnel',
            soft_min=0.1, soft_max=0.4,
        )
        MAX_NEW_ITEM_RATIO = 0.25
    """
    def decorator(value):
        _PARAMETER_REGISTRY_PENDING.append({
            "parameter_name": name,
            "file_path": file_path,
            "current_value": value if isinstance(value, (int, float)) else None,
            "current_value_str": str(value),
            "value_type": value_type,
            "primary_dimension": primary_dimension,
            "secondary_dimensions": json.dumps(secondary_dimensions or []),
            "min_valid": min_valid,
            "max_valid": max_valid,
            "soft_min": soft_min,
            "soft_max": soft_max,
            "change_direction": change_direction,
            "notes": notes,
        })
        return value
    return decorator


def sync_parameter_registry(conn) -> int:
    """Upsert all pending parameter registrations into the database.

    Returns count of parameters synced.
    """
    count = 0
    for p in _PARAMETER_REGISTRY_PENDING:
        param_id = str(uuid4())
        try:
            # Check if already exists
            existing = _safe_query(conn, """
                SELECT id, current_value, current_value_str
                FROM pi_parameter_registry WHERE parameter_name = ?
            """, (p["parameter_name"],))

            if existing:
                # Update current value if changed
                if (existing["current_value"] != p["current_value"]
                        or existing["current_value_str"] != p["current_value_str"]):
                    conn.execute("""
                        UPDATE pi_parameter_registry
                        SET current_value = ?, current_value_str = ?,
                            file_path = ?, value_type = ?,
                            primary_dimension = ?, secondary_dimensions = ?,
                            min_valid = ?, max_valid = ?,
                            soft_min = ?, soft_max = ?,
                            change_direction = ?, notes = ?
                        WHERE parameter_name = ?
                    """, (
                        p["current_value"], p["current_value_str"],
                        p["file_path"], p["value_type"],
                        p["primary_dimension"], p["secondary_dimensions"],
                        p["min_valid"], p["max_valid"],
                        p["soft_min"], p["soft_max"],
                        p["change_direction"], p["notes"],
                        p["parameter_name"],
                    ))
            else:
                conn.execute("""
                    INSERT INTO pi_parameter_registry
                        (id, parameter_name, file_path, current_value, current_value_str,
                         value_type, primary_dimension, secondary_dimensions,
                         min_valid, max_valid, soft_min, soft_max,
                         change_direction, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    param_id, p["parameter_name"], p["file_path"],
                    p["current_value"], p["current_value_str"],
                    p["value_type"], p["primary_dimension"],
                    p["secondary_dimensions"],
                    p["min_valid"], p["max_valid"],
                    p["soft_min"], p["soft_max"],
                    p["change_direction"], p["notes"],
                ))
            count += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to sync parameter %s: %s", p["parameter_name"], e)

    if count:
        conn.commit()
    return count


def get_parameter(conn, parameter_name: str):
    """Look up a parameter by name. Returns Row or None."""
    return _safe_query(conn, """
        SELECT * FROM pi_parameter_registry WHERE parameter_name = ?
    """, (parameter_name,))


def get_all_parameters(conn) -> list:
    """Return all registered parameters."""
    return _safe_query_all(conn, "SELECT * FROM pi_parameter_registry ORDER BY primary_dimension, parameter_name")


def record_parameter_change(
    conn, parameter_name: str, old_value, new_value,
    changed_by: str = "human", work_order_id=None,
) -> str:
    """Record a parameter change in pi_parameter_history.

    Returns the history entry id.
    """
    param = get_parameter(conn, parameter_name)
    if not param:
        logger.warning("Parameter %s not found in registry", parameter_name)
        return None

    history_id = str(uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn.execute("""
            INSERT INTO pi_parameter_history
                (id, parameter_id, changed_at, old_value, new_value,
                 changed_by, work_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            history_id, param["id"], now,
            float(old_value) if old_value is not None else None,
            float(new_value) if new_value is not None else None,
            changed_by, work_order_id,
        ))

        # Update registry
        conn.execute("""
            UPDATE pi_parameter_registry
            SET current_value = ?, current_value_str = ?,
                last_changed_at = ?, last_changed_by = ?,
                change_count = change_count + 1
            WHERE id = ?
        """, (
            float(new_value) if new_value is not None else None,
            str(new_value), now, changed_by, param["id"],
        ))
        conn.commit()
        return history_id
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to record parameter change: %s", e)
        return None


# ── Prior edges for influence model seeding ──────────────────────────────────
# (parameter_name, metric_name, dimension, direction, weight, confidence)

_PRIOR_EDGES = [
    ("MAX_NEW_ITEM_RATIO", "srs_funnel", "srs_funnel", "decrease", 0.4, 0.1),
    ("INTERVAL_INITIAL", "srs_funnel", "srs_funnel", "increase", 0.4, 0.1),
    ("INTERVAL_SECOND", "srs_funnel", "srs_funnel", "increase", 0.4, 0.1),
    ("LEARNING_WIP_LIMIT", "srs_funnel", "srs_funnel", "decrease", 0.4, 0.1),
    ("RECALL_THRESHOLD", "retention", "retention", "increase", 0.4, 0.1),
    ("PROMOTE_STABILIZING_STREAK", "srs_funnel", "srs_funnel", "increase", 0.4, 0.1),
    ("PROMOTE_STABLE_STREAK", "srs_funnel", "srs_funnel", "increase", 0.4, 0.1),
    ("SESSION_TIME_CAP_SECONDS", "engagement", "engagement", "increase", 0.4, 0.1),
    ("MIN_SESSION_ITEMS", "engagement", "engagement", "increase", 0.4, 0.1),
    ("TONE_BOOST_ACCURACY_THRESHOLD", "tone_phonology", "tone_phonology", "decrease", 0.4, 0.1),
    ("TONE_BOOST_MULTIPLIER", "tone_phonology", "tone_phonology", "increase", 0.4, 0.1),
    ("TONE_BOOST_MAX_WEIGHT", "tone_phonology", "tone_phonology", "increase", 0.4, 0.1),
    ("ERROR_FOCUS_LIMIT", "drill_quality", "drill_quality", "increase", 0.4, 0.1),
    ("BOUNCE_ERROR_RATE", "frustration", "frustration", "decrease", 0.4, 0.1),
    ("DIFFICULTY_CORRECT_ALPHA", "drill_quality", "drill_quality", "either", 0.4, 0.1),
    ("DIFFICULTY_WRONG_BETA", "drill_quality", "drill_quality", "either", 0.4, 0.1),
    ("DEMOTE_WEAK_CYCLE_THRESHOLD", "srs_funnel", "srs_funnel", "either", 0.4, 0.1),
    ("MAX_NEW_ITEM_RATIO", "retention", "retention", "decrease", 0.3, 0.1),
    ("CONFUSABLE_BOOST_MULT", "drill_quality", "drill_quality", "increase", 0.4, 0.1),
    ("ADAPTIVE_LOW_COMPLETION", "ux", "ux", "increase", 0.4, 0.1),
    ("ADAPTIVE_EXIT_RATE", "ux", "ux", "decrease", 0.4, 0.1),
    ("NEW_BUDGET_DEFAULT", "srs_funnel", "srs_funnel", "either", 0.4, 0.1),
    ("EASE_FLOOR", "srs_funnel", "srs_funnel", "either", 0.4, 0.1),
]


def seed_influence_model(conn) -> int:
    """Initialize influence edges from prior knowledge.

    weight=0.4, weight_confidence=0.1 — low trust, overridden quickly by data.
    Only creates edges for parameters that exist in the registry.
    Idempotent — skips edges that already exist.

    Returns count of edges created.
    """
    count = 0
    for (param_name, metric, dim, direction, weight, conf) in _PRIOR_EDGES:
        param = _safe_query(conn, """
            SELECT id FROM pi_parameter_registry WHERE parameter_name = ?
        """, (param_name,))
        if not param:
            continue

        # Check if edge already exists
        existing = _safe_query(conn, """
            SELECT id FROM pi_influence_edges
            WHERE parameter_id = ? AND metric_name = ?
        """, (param["id"], metric))
        if existing:
            continue

        try:
            conn.execute("""
                INSERT INTO pi_influence_edges
                    (id, parameter_id, metric_name, dimension,
                     weight, weight_confidence, learned_direction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid4()), param["id"], metric, dim,
                  weight, conf, direction))
            count += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to seed edge %s→%s: %s", param_name, metric, e)

    if count:
        conn.commit()
    return count


def update_influence_edges(conn, work_order_id: int) -> bool:
    """Update influence edges after a work order outcome is verified.

    Called after prediction outcome is recorded. Updates the edge between
    the changed parameter and the affected metric.
    Returns True if an edge was updated.
    """
    # Get work order + parameter history + prediction outcome
    wo = _safe_query(conn, """
        SELECT wo.finding_id, wo.constraint_dimension,
               ph.parameter_id, ph.old_value, ph.new_value,
               pl.metric_name, pl.metric_baseline,
               po.actual_delta, po.outcome_class
        FROM pi_work_order wo
        JOIN pi_parameter_history ph ON ph.work_order_id = wo.id
        JOIN pi_prediction_ledger pl ON pl.finding_id = wo.finding_id
        LEFT JOIN pi_prediction_outcomes po ON po.prediction_id = pl.id
        WHERE wo.id = ?
        LIMIT 1
    """, (work_order_id,))

    if not wo or wo["parameter_id"] is None:
        return False

    parameter_id = wo["parameter_id"]
    metric_name = wo["metric_name"]
    actual_delta = wo["actual_delta"] if wo["actual_delta"] is not None else 0.0
    outcome_class = wo["outcome_class"] or "insufficient_data"

    # Find or create edge
    edge = _safe_query(conn, """
        SELECT * FROM pi_influence_edges
        WHERE parameter_id = ? AND metric_name = ?
    """, (parameter_id, metric_name))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if not edge:
        # New edge discovered from data — start at 0, will be incremented below
        edge_id = str(uuid4())
        try:
            conn.execute("""
                INSERT INTO pi_influence_edges
                    (id, parameter_id, metric_name, dimension,
                     observation_count, weight, weight_confidence,
                     last_updated)
                VALUES (?, ?, ?, ?, 0, 0.5, 0.1, ?)
            """, (edge_id, parameter_id, metric_name,
                  wo["constraint_dimension"], now))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.error("Failed to create influence edge: %s", e)
            return False
        edge = _safe_query(conn, """
            SELECT * FROM pi_influence_edges WHERE id = ?
        """, (edge_id,))
        if not edge:
            return False

    # Update counts
    obs = edge["observation_count"] + 1
    pos = edge["positive_effect_count"]
    neg = edge["negative_effect_count"]
    null_count = edge["null_effect_count"]

    if outcome_class == "correct":
        pos += 1
    elif outcome_class == "wrong":
        neg += 1
    else:
        null_count += 1

    # Update mean delta (running average)
    old_mean = edge["mean_delta_achieved"] or 0.0
    new_mean = old_mean + (actual_delta - old_mean) / obs

    # Bayesian weight update (Beta-Binomial on positive/negative)
    effective_pos = pos + 0.5 * null_count + 1
    effective_total = pos + neg + null_count + 2
    new_weight = effective_pos / effective_total

    # Confidence grows with observations
    new_confidence = min(0.95, 0.1 + 0.85 * (1 - 1 / (obs + 1)))

    # Learn direction from data
    learned_dir = edge["learned_direction"]
    if obs >= 5 and wo["old_value"] is not None and wo["new_value"] is not None:
        param_increased = wo["new_value"] > wo["old_value"]
        metric_improved = actual_delta > 0
        if param_increased == metric_improved:
            learned_dir = "increase"
        else:
            learned_dir = "decrease"

    try:
        conn.execute("""
            UPDATE pi_influence_edges
            SET observation_count = ?, positive_effect_count = ?,
                negative_effect_count = ?, null_effect_count = ?,
                mean_delta_achieved = ?, weight = ?, weight_confidence = ?,
                learned_direction = ?, last_updated = ?
            WHERE id = ?
        """, (obs, pos, neg, null_count, new_mean, new_weight,
              new_confidence, learned_dir, now, edge["id"]))
        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to update influence edge: %s", e)
        return False


def get_influence_graph(conn) -> dict:
    """Return the full parameter influence graph for visualization.

    Returns {nodes: [...], edges: [...], last_updated, total_observations}.
    """
    params = _safe_query_all(conn, """
        SELECT id, parameter_name, file_path, current_value,
               primary_dimension, change_count
        FROM pi_parameter_registry
        ORDER BY parameter_name
    """) or []

    edges = _safe_query_all(conn, """
        SELECT ie.id, ie.parameter_id, ie.metric_name, ie.dimension,
               ie.observation_count, ie.weight, ie.weight_confidence,
               ie.learned_direction, ie.mean_delta_achieved,
               ie.last_updated,
               pr.parameter_name
        FROM pi_influence_edges ie
        JOIN pi_parameter_registry pr ON pr.id = ie.parameter_id
        ORDER BY ie.weight * ie.weight_confidence DESC
    """) or []

    # Compute totals
    total_obs = sum(e["observation_count"] for e in edges)
    last_updated = None
    for e in edges:
        if e["last_updated"]:
            if last_updated is None or e["last_updated"] > last_updated:
                last_updated = e["last_updated"]

    return {
        "nodes": [
            {
                "id": p["id"],
                "name": p["parameter_name"],
                "file_path": p["file_path"],
                "current_value": p["current_value"],
                "dimension": p["primary_dimension"],
                "type": "parameter",
                "change_count": p["change_count"],
            }
            for p in params
        ],
        "edges": [
            {
                "id": e["id"],
                "source": e["parameter_id"],
                "source_name": e["parameter_name"],
                "target": e["metric_name"],
                "dimension": e["dimension"],
                "weight": e["weight"],
                "confidence": e["weight_confidence"],
                "observations": e["observation_count"],
                "direction": e["learned_direction"],
                "mean_effect": e["mean_delta_achieved"],
            }
            for e in edges
        ],
        "last_updated": last_updated,
        "total_observations": total_obs,
    }
