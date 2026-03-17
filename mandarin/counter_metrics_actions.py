"""Counter-Metrics Automated Actioning — the control system.

This module turns counter-metric alerts into ACTIONS:
1. Scheduler adjustments (reduce new items, lengthen spacing, add production drills)
2. Experiment proposals (A/B test interventions for detected issues)
3. Dashboard alerts (surface to admin for review)
4. Feature flag toggles (disable risky features, enable protective ones)
5. Product rule enforcement (block features that violate integrity rules)

Design: aelu acts on counter-metric signals autonomously. The admin
sees a digest, not a decision queue.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _log_action(conn: sqlite3.Connection, action_type: str,
                metric_name: str, severity: str,
                details: Optional[Dict] = None) -> None:
    """Record an action taken in response to a counter-metric alert."""
    if not _table_exists(conn, "counter_metric_action_log"):
        return
    conn.execute("""
        INSERT INTO counter_metric_action_log
        (action_type, metric_name, severity, details_json)
        VALUES (?, ?, ?, ?)
    """, (action_type, metric_name, severity, json.dumps(details or {})))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════
# ACTION RULES — each counter-metric alert maps to concrete actions
# ═══════════════════════════════════════════════════════════════════════

ACTION_RULES = {
    # ── Integrity alerts ──
    "delayed_recall_7d": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_spacing_multiplier",
             "params": {"factor": 0.85},
             "reason": "7-day recall dropping — space reviews closer to prevent over-spacing"},
            {"type": "scheduler_adjust", "action": "reduce_new_item_budget",
             "params": {"multiplier": 0.7},
             "reason": "Slow new items to consolidate existing knowledge"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "pause_new_items",
             "params": {"days": 3},
             "reason": "Critical recall failure — freeze new items for consolidation"},
            {"type": "experiment_propose", "action": "propose",
             "params": {"name": "auto_recall_recovery", "variants": ["control", "consolidation_mode"],
                        "hypothesis": "Pausing new items and increasing review frequency improves delayed recall"},
             "reason": "Recall critically low — A/B test intensive review mode"},
        ],
    },
    "delayed_recall_30d": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_long_term_reviews",
             "params": {"boost_factor": 1.3},
             "reason": "30-day retention weak — boost durable item reviews"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "mastery_demotion_sweep",
             "params": {},
             "reason": "Systematic long-term memory failure — audit stable/durable items"},
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "Critical 30-day recall failure detected. Mastery labels may be dishonest."},
             "reason": "Product honesty at risk"},
        ],
    },

    "transfer_accuracy": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_drill_diversity",
             "params": {"min_types": 3},
             "reason": "Transfer weak — force varied drill types per item"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "require_cross_mode_before_promotion",
             "params": {},
             "reason": "Critical transfer failure — tighten mastery gates"},
            {"type": "experiment_propose", "action": "propose",
             "params": {"name": "auto_transfer_training", "variants": ["control", "cross_mode_drills"],
                        "hypothesis": "Mandating cross-mode practice improves transfer accuracy"},
             "reason": "Transfer accuracy critically low"},
        ],
    },

    "production_accuracy": {
        "warn": [
            {"type": "scheduler_adjust", "action": "boost_production_drills",
             "params": {"production_weight": 2.0},
             "reason": "Production accuracy low — more practice typing/speaking/building sentences needed"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "enforce_production_gate",
             "params": {},
             "reason": "Production accuracy critically low — block mastery promotion without production success"},
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "Users can recognize items but cannot produce them. Mastery claims are inflated."},
             "reason": "Gap between what user can recognize vs. produce is too large"},
        ],
    },

    "recognition_production_gap": {
        "warn": [
            {"type": "scheduler_adjust", "action": "boost_production_drills",
             "params": {"production_weight": 1.5},
             "reason": "Recognition-production gap widening — increase production drill frequency"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "enforce_production_gate",
             "params": {},
             "reason": "Large gap — block mastery promotion without production evidence"},
        ],
    },

    "mastery_reversal_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "tighten_promotion_criteria",
             "params": {"streak_bonus": 2},
             "reason": "Too many reversals — require longer streaks for promotion"},
        ],
        "critical": [
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "Mastery reversal rate critical (>25%). Mastery labels are unreliable."},
             "reason": "Product integrity compromised"},
        ],
    },

    "mastery_survival_30d": {
        "warn": [
            {"type": "scheduler_adjust", "action": "extend_stable_review_period",
             "params": {"days": 7},
             "reason": "Stable items not surviving — review them more often after promotion"},
        ],
    },

    "hint_dependence_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "reduce_hint_availability",
             "params": {"max_hint_rate": 0.3},
             "reason": "Hint dependence rising — reduce hint frequency in sessions"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "disable_hints_temporarily",
             "params": {"sessions": 5},
             "reason": "Critical hint dependence — force unassisted practice"},
            {"type": "feature_flag", "action": "toggle",
             "params": {"flag_name": "hints_enabled", "enabled": False},
             "reason": "Critical hint dependence — disable hints until rate recovers"},
        ],
    },

    # ── Cost alerts ──
    "fatigue_score": {
        "warn": [
            {"type": "scheduler_adjust", "action": "shorten_sessions",
             "params": {"length_multiplier": 0.75},
             "reason": "Fatigue detected — shorten sessions"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "switch_to_minimal_mode",
             "params": {},
             "reason": "Critical fatigue — switch to minimal sessions only"},
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "User fatigue score critical. Sessions may be causing harm."},
             "reason": "User wellbeing at risk"},
        ],
    },

    "early_exit_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "shorten_sessions",
             "params": {"length_multiplier": 0.8},
             "reason": "High early exits — sessions may be too long or hard"},
            {"type": "experiment_propose", "action": "propose",
             "params": {"name": "auto_session_length_optimization",
                        "variants": ["control", "adaptive_shorter"],
                        "hypothesis": "Shorter adaptive sessions reduce early exit rate"},
             "reason": "Early exits suggest session design problem"},
        ],
    },

    "overdue_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "reduce_new_item_budget",
             "params": {"multiplier": 0.5},
             "reason": "Backlog growing — slow new item introduction"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "pause_new_items",
             "params": {"days": 7},
             "reason": "Critical backlog — pause new items to clear overdue reviews"},
        ],
    },

    # ── Distortion alerts ──
    "suspicious_fast_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "add_response_floor",
             "params": {"min_ms": 800},
             "reason": "Fast tapping detected — add minimum response time"},
        ],
        "critical": [
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "High rate of suspiciously fast answers. Possible click-through gaming."},
             "reason": "Gaming behavior detected"},
            {"type": "feature_flag", "action": "toggle",
             "params": {"flag_name": "streak_rewards", "enabled": False},
             "reason": "Streak rewards may incentivize gaming — disable while fast-tap rate is critical"},
        ],
    },

    "recognition_only_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "boost_production_drills",
             "params": {"production_weight": 2.0},
             "reason": "Too many items advancing without production — force production drills"},
        ],
        "critical": [
            {"type": "scheduler_adjust", "action": "enforce_production_gate",
             "params": {},
             "reason": "Critical recognition-only advancement — block promotion without production"},
        ],
    },

    "low_challenge_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_difficulty_floor",
             "params": {"min_difficulty": 0.3},
             "reason": "Too many easy wins — raise difficulty floor in sessions"},
        ],
    },

    # ── Outcome alerts ──
    "holdout_accuracy": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_drill_diversity",
             "params": {"min_types": 4},
             "reason": "Holdout performance weak — broaden drill exposure"},
        ],
        "critical": [
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "Holdout probe accuracy critically low. Main metrics may be overfitted."},
             "reason": "Product metrics potentially detached from real learning"},
            {"type": "experiment_propose", "action": "propose",
             "params": {"name": "auto_curriculum_overhaul",
                        "variants": ["control", "diverse_practice"],
                        "hypothesis": "More diverse practice improves holdout performance"},
             "reason": "Real-world outcomes not matching dashboard claims"},
            {"type": "feature_flag", "action": "toggle",
             "params": {"flag_name": "adaptive_difficulty", "enabled": False},
             "reason": "Adaptive difficulty may be over-fitting to easy items — disable to broaden exposure"},
        ],
    },

    "progress_honesty_score": {
        "critical": [
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "PRODUCT HONESTY ALERT: mastered items perform similar to unmastered on holdouts. Progress display is misleading."},
             "reason": "The product is lying about user progress"},
            {"type": "feature_flag", "action": "toggle",
             "params": {"flag_name": "show_mastery_badges", "enabled": False},
             "reason": "Mastery badges are misleading — hide until progress honesty recovers"},
        ],
    },

    # ── Trend drift alerts (multi-cycle declining trends) ──
    "trend_delayed_recall_7d": {
        "warn": [
            {"type": "scheduler_adjust", "action": "reduce_new_item_budget",
             "params": {"multiplier": 0.6},
             "reason": "Memory is getting worse over multiple cycles — slow down new material"},
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "Declining trend: 1-week memory accuracy has dropped across 3+ consecutive checks."},
             "reason": "Sustained memory decline detected"},
        ],
    },
    "trend_transfer_accuracy": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_drill_diversity",
             "params": {"min_types": 4},
             "reason": "Transfer ability declining across cycles — force more varied practice"},
        ],
    },
    "trend_mastery_reversal_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "reduce_new_item_budget",
             "params": {"multiplier": 0.5},
             "reason": "More items are losing mastery each cycle — consolidate before adding more"},
            {"type": "experiment_propose", "action": "propose",
             "params": {"name": "auto_reversal_recovery",
                        "variants": ["control", "consolidation_sprint"],
                        "hypothesis": "Intensive review of reversed items restores mastery trend"},
             "reason": "Rising reversal trend warrants intervention experiment"},
        ],
    },
    "trend_fatigue_score": {
        "warn": [
            {"type": "scheduler_adjust", "action": "shorten_sessions",
             "params": {"multiplier": 0.8},
             "reason": "Fatigue is rising each cycle — reduce session length before burnout"},
        ],
    },
    "trend_overdue_rate": {
        "warn": [
            {"type": "scheduler_adjust", "action": "reduce_new_item_budget",
             "params": {"multiplier": 0.5},
             "reason": "Backlog growing each cycle — stop adding new items until reviews catch up"},
        ],
    },
    "trend_holdout_accuracy": {
        "warn": [
            {"type": "scheduler_adjust", "action": "increase_drill_diversity",
             "params": {"min_types": 4},
             "reason": "Secret quiz scores dropping over time — practice is becoming too narrow"},
            {"type": "notification", "action": "admin_alert",
             "params": {"message": "Declining trend: secret quiz accuracy is getting worse each cycle. Real learning may be stalling."},
             "reason": "Sustained decline in real-world learning signal"},
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════
# ACTION EXECUTOR
# ═══════════════════════════════════════════════════════════════════════

def execute_actions_for_assessment(conn: sqlite3.Connection,
                                   assessment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Process all alerts from a counter-metric assessment and execute actions.

    Returns a list of actions taken.
    """
    alerts = assessment.get("alerts", [])
    actions_taken = []

    for alert in alerts:
        metric = alert["metric"]
        severity = alert["severity"]

        rules = ACTION_RULES.get(metric, {})
        severity_actions = rules.get(severity, [])

        for action_spec in severity_actions:
            try:
                result = _execute_single_action(conn, action_spec, alert)
                if result:
                    actions_taken.append(result)
                    _log_action(conn, action_spec["type"], metric, severity,
                                {"action": action_spec["action"], "result": result})
            except Exception:
                logger.exception("Failed to execute action %s for %s",
                                 action_spec.get("action"), metric)

    return actions_taken


def _execute_single_action(conn: sqlite3.Connection,
                           action_spec: Dict[str, Any],
                           alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Execute a single action from an action spec.

    Returns a result dict, or None if the action was skipped.
    """
    action_type = action_spec["type"]
    action_name = action_spec["action"]
    params = action_spec.get("params", {})
    reason = action_spec.get("reason", "")

    if action_type == "scheduler_adjust":
        return _action_scheduler_adjust(conn, action_name, params, reason, alert)
    elif action_type == "experiment_propose":
        return _action_experiment_propose(conn, params, reason, alert)
    elif action_type == "notification":
        return _action_notification(conn, action_name, params, reason, alert)
    elif action_type == "feature_flag":
        return _action_feature_flag(conn, params, reason, alert)
    else:
        logger.warning("Unknown action type: %s", action_type)
        return None


def _action_scheduler_adjust(conn: sqlite3.Connection, action_name: str,
                              params: Dict, reason: str,
                              alert: Dict) -> Dict[str, Any]:
    """Apply a scheduler adjustment in response to a counter-metric alert.

    Rather than directly mutating the scheduler state, we write adjustment
    records that the scheduler reads on next session plan.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Store adjustment as a lifecycle event for the scheduler to pick up
    if _table_exists(conn, "lifecycle_event"):
        event_data = json.dumps({
            "action": action_name,
            "params": params,
            "reason": reason,
            "trigger_metric": alert.get("metric"),
            "trigger_value": alert.get("value"),
            "trigger_severity": alert.get("severity"),
        })
        conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
        """, (event_data, now))
        conn.commit()

    return {
        "type": "scheduler_adjust",
        "action": action_name,
        "params": params,
        "reason": reason,
        "executed_at": now,
    }


def _action_experiment_propose(conn: sqlite3.Connection, params: Dict,
                                reason: str, alert: Dict) -> Optional[Dict[str, Any]]:
    """Propose an A/B experiment in response to a counter-metric alert."""
    if not _table_exists(conn, "experiment_proposal"):
        return None

    name = params.get("name", "auto_counter_metric")
    variants = params.get("variants", ["control", "treatment"])

    # Check for existing proposal or running experiment
    existing = conn.execute(
        "SELECT id FROM experiment_proposal WHERE name = ? AND status IN ('pending', 'started')",
        (name,)
    ).fetchone()
    if existing:
        return {"type": "experiment_propose", "action": "skipped_existing", "name": name}

    existing_exp = conn.execute(
        "SELECT id FROM experiment WHERE name = ? AND status IN ('draft', 'running')",
        (name,)
    ).fetchone()
    if existing_exp:
        return {"type": "experiment_propose", "action": "skipped_running", "name": name}

    now = datetime.now(timezone.utc).isoformat()
    hypothesis = params.get("hypothesis", reason)

    conn.execute("""
        INSERT INTO experiment_proposal
        (name, description, hypothesis, source, source_detail, variants,
         traffic_pct, priority, status)
        VALUES (?, ?, ?, 'counter_metric', ?, ?, 50.0, ?, 'pending')
    """, (
        name,
        f"Auto-proposed from counter-metric alert: {alert.get('metric')}",
        hypothesis,
        json.dumps({"metric": alert.get("metric"), "value": alert.get("value"),
                     "severity": alert.get("severity")}),
        json.dumps(variants),
        80,  # High priority — counter-metric alerts are serious
    ))
    conn.commit()

    return {
        "type": "experiment_propose",
        "action": "proposed",
        "name": name,
        "reason": reason,
    }


def _action_notification(conn: sqlite3.Connection, action_name: str,
                          params: Dict, reason: str,
                          alert: Dict) -> Dict[str, Any]:
    """Create a notification/alert for admin review."""
    now = datetime.now(timezone.utc).isoformat()
    message = params.get("message", reason)

    # Log as lifecycle event for admin dashboard
    if _table_exists(conn, "lifecycle_event"):
        event_data = json.dumps({
            "notification_type": action_name,
            "message": message,
            "metric": alert.get("metric"),
            "value": alert.get("value"),
            "severity": alert.get("severity"),
            "reason": reason,
        })
        conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_alert', ?, ?)
        """, (event_data, now))
        conn.commit()

    return {
        "type": "notification",
        "action": action_name,
        "message": message,
        "executed_at": now,
    }


def _action_feature_flag(conn: sqlite3.Connection, params: Dict,
                          reason: str, alert: Dict) -> Optional[Dict[str, Any]]:
    """Toggle a feature flag in response to a counter-metric alert."""
    try:
        from .feature_flags import set_flag
    except ImportError:
        return None

    flag_name = params.get("flag_name")
    enabled = params.get("enabled", False)
    rollout_pct = params.get("rollout_pct", 100)

    if not flag_name:
        return None

    set_flag(conn, flag_name, enabled=enabled, rollout_pct=rollout_pct,
             description=f"Counter-metric action: {reason}")

    return {
        "type": "feature_flag",
        "flag": flag_name,
        "enabled": enabled,
        "rollout_pct": rollout_pct,
        "reason": reason,
    }


# ═══════════════════════════════════════════════════════════════════════
# PRODUCT RULE ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════

def enforce_product_rules(assessment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check the 5 product rules and return any violations.

    Rule 1: No learning KPI ships alone.
    Rule 2: No feature succeeds if it degrades delayed recall/transfer/trust.
    Rule 3: User-visible progress must be anchored to time-surviving evidence.
    Rule 4: Benchmark sets must include holdout tasks.
    Rule 5: Growth experiments must pass educational integrity check.
    """
    violations = []

    # Rule 2: Check if immediate accuracy is good but delayed/transfer is bad
    integrity = assessment.get("integrity", {})
    dr_7 = integrity.get("delayed_recall_7d", {}).get("accuracy")
    transfer = integrity.get("transfer_accuracy", {}).get("accuracy")
    prod_acc = integrity.get("production_vs_recognition_gap", {}).get("production_accuracy")

    if dr_7 is not None and dr_7 < 0.50:
        violations.append({
            "rule": 2,
            "description": "Delayed recall critically low despite possible good immediate performance",
            "metric": "delayed_recall_7d",
            "value": dr_7,
            "action": "Block any feature launches until delayed recall improves above 0.65",
        })

    if transfer is not None and transfer < 0.40:
        violations.append({
            "rule": 2,
            "description": "Transfer accuracy critically low",
            "metric": "transfer_accuracy",
            "value": transfer,
            "action": "Block mastery promotions until transfer accuracy improves",
        })

    # Rule 3: Check progress honesty
    outcome = assessment.get("outcome", {})
    honesty = outcome.get("progress_honesty_score", {}).get("honesty_score")
    if honesty is not None and honesty < 30:
        violations.append({
            "rule": 3,
            "description": "Progress claims not anchored to evidence (honesty score < 30)",
            "metric": "progress_honesty_score",
            "value": honesty,
            "action": "Add disclaimers to progress display; audit mastery criteria",
        })

    # Rule 4: Check holdout system is producing data
    holdout = outcome.get("holdout_probe_performance", {})
    if holdout.get("sample_size", 0) < 10:
        violations.append({
            "rule": 4,
            "description": "Insufficient holdout probe data (< 10 samples)",
            "metric": "holdout_sample_size",
            "value": holdout.get("sample_size", 0),
            "action": "Increase holdout probe injection rate",
        })

    # Rule 2 (mastery version): High reversal rate
    reversal = integrity.get("mastery_reversal_rate", {}).get("reversal_rate")
    if reversal is not None and reversal > 0.25:
        violations.append({
            "rule": 2,
            "description": "Mastery reversal rate > 25% — mastery labels are unreliable",
            "metric": "mastery_reversal_rate",
            "value": reversal,
            "action": "Tighten mastery promotion gates; add post-promotion review checkpoints",
        })

    return violations


def get_action_history(conn: sqlite3.Connection,
                       limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent counter-metric actions for audit trail."""
    if not _table_exists(conn, "counter_metric_action_log"):
        return []

    rows = conn.execute("""
        SELECT * FROM counter_metric_action_log
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    return [dict(r) for r in rows]
