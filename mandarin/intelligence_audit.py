"""Intelligence engine self-audit — measures how well the system reasons.

Tracks:
- Churn classification accuracy (predicted type vs. actual behavior)
- Churn score calibration (Brier score)
- Experiment proposal win rate
- Guardrail false positive/negative rates
- Prediction drift over time

All functions are deterministic. No runtime LLM calls.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Churn Score Calibration (Brier Score) ────────────────────────────────────


def compute_brier_score(conn: sqlite3.Connection, lookback_days: int = 90) -> dict:
    """Compute Brier score for churn risk predictions.

    Compares predicted churn risk (0-1 scale) against actual churn
    (no session for 14+ days after prediction).

    Lower Brier score = better calibration. Target: < 0.20.

    Returns {brier_score, n_predictions, calibration_bins, target_met}.
    """
    try:
        # Get churn risk predictions from lifecycle events
        predictions = conn.execute(
            """SELECT user_id,
                      json_extract(metadata, '$.score') as risk_score,
                      created_at
               FROM lifecycle_event
               WHERE event_type = 'churn_risk_detected'
                 AND created_at >= datetime('now', ? || ' days')
                 AND json_extract(metadata, '$.score') IS NOT NULL
               ORDER BY created_at""",
            (str(-lookback_days),),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"brier_score": None, "n_predictions": 0, "calibration_bins": [],
                "target_met": False}

    if not predictions:
        return {"brier_score": None, "n_predictions": 0, "calibration_bins": [],
                "target_met": False}

    squared_errors = []
    bin_data = {}  # bin_idx -> {predicted_sum, actual_sum, count}

    for pred in predictions:
        user_id = pred["user_id"]
        risk_score = (pred["risk_score"] or 0) / 100.0  # Convert 0-100 to 0-1
        pred_time = pred["created_at"]

        # Check if user actually churned (no session for 14+ days after prediction)
        try:
            next_session = conn.execute(
                """SELECT started_at FROM session_log
                   WHERE user_id = ? AND started_at > ? AND items_completed > 0
                   ORDER BY started_at ASC LIMIT 1""",
                (int(user_id), pred_time),
            ).fetchone()
        except (sqlite3.OperationalError, ValueError):
            continue

        if next_session:
            # User had a session — compute gap
            try:
                pred_dt = datetime.fromisoformat(pred_time.replace("Z", "+00:00"))
                sess_dt = datetime.fromisoformat(next_session["started_at"].replace("Z", "+00:00"))
                gap_days = (sess_dt - pred_dt).total_seconds() / 86400
                actual_churn = 1.0 if gap_days > 14 else 0.0
            except (ValueError, TypeError):
                continue
        else:
            # No subsequent session found — check if enough time has passed
            try:
                pred_dt = datetime.fromisoformat(pred_time.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_since = (now - pred_dt.replace(tzinfo=timezone.utc if pred_dt.tzinfo is None else pred_dt.tzinfo)).total_seconds() / 86400
                if days_since < 14:
                    continue  # Not enough time to judge
                actual_churn = 1.0
            except (ValueError, TypeError):
                continue

        se = (risk_score - actual_churn) ** 2
        squared_errors.append(se)

        # Binning for calibration analysis (10 bins)
        bin_idx = min(9, int(risk_score * 10))
        if bin_idx not in bin_data:
            bin_data[bin_idx] = {"predicted_sum": 0.0, "actual_sum": 0.0, "count": 0}
        bin_data[bin_idx]["predicted_sum"] += risk_score
        bin_data[bin_idx]["actual_sum"] += actual_churn
        bin_data[bin_idx]["count"] += 1

    if not squared_errors:
        return {"brier_score": None, "n_predictions": 0, "calibration_bins": [],
                "target_met": False}

    brier = sum(squared_errors) / len(squared_errors)

    calibration_bins = []
    for i in range(10):
        if i in bin_data:
            d = bin_data[i]
            calibration_bins.append({
                "bin": f"{i * 10}-{(i + 1) * 10}%",
                "predicted_avg": round(d["predicted_sum"] / d["count"], 3),
                "actual_avg": round(d["actual_sum"] / d["count"], 3),
                "count": d["count"],
                "calibration_error": round(
                    abs(d["predicted_sum"] / d["count"] - d["actual_sum"] / d["count"]), 3
                ),
            })

    return {
        "brier_score": round(brier, 4),
        "n_predictions": len(squared_errors),
        "calibration_bins": calibration_bins,
        "target_met": brier < 0.20,
    }


# ── Churn Classification Accuracy ────────────────────────────────────────────


def compute_classification_accuracy(conn: sqlite3.Connection, lookback_days: int = 90) -> dict:
    """Assess whether churn type classifications match actual behavior.

    For each classified churn type, check if the predicted behavior pattern
    (e.g., "habit_fade" should show gradual decline) matches what actually happened.

    Returns {accuracy, n_evaluated, by_type: {type: {n, correct, accuracy}}}.
    """
    try:
        classifications = conn.execute(
            """SELECT user_id,
                      json_extract(metadata, '$.churn_type') as churn_type,
                      json_extract(metadata, '$.score') as risk_score,
                      created_at
               FROM lifecycle_event
               WHERE event_type = 'churn_risk_detected'
                 AND created_at >= datetime('now', ? || ' days')
                 AND json_extract(metadata, '$.churn_type') IS NOT NULL""",
            (str(-lookback_days),),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"accuracy": None, "n_evaluated": 0, "by_type": {}}

    by_type = {}
    total_evaluated = 0
    total_correct = 0

    for cls in classifications:
        user_id = cls["user_id"]
        churn_type = cls["churn_type"]
        pred_time = cls["created_at"]

        if churn_type not in by_type:
            by_type[churn_type] = {"n": 0, "correct": 0}

        # Validate classification against actual behavior in the 30 days after
        correct = _validate_churn_classification(conn, int(user_id), churn_type, pred_time)
        if correct is None:
            continue  # Insufficient data to evaluate

        by_type[churn_type]["n"] += 1
        total_evaluated += 1
        if correct:
            by_type[churn_type]["correct"] += 1
            total_correct += 1

    # Compute per-type accuracy
    for ct in by_type:
        n = by_type[ct]["n"]
        by_type[ct]["accuracy"] = round(by_type[ct]["correct"] / n, 3) if n > 0 else 0.0

    overall_accuracy = total_correct / total_evaluated if total_evaluated > 0 else None

    return {
        "accuracy": round(overall_accuracy, 3) if overall_accuracy is not None else None,
        "n_evaluated": total_evaluated,
        "by_type": by_type,
    }


def _validate_churn_classification(
    conn: sqlite3.Connection, user_id: int, churn_type: str, pred_time: str
) -> bool | None:
    """Validate a single churn classification against subsequent behavior.

    Returns True if classification appears correct, False if wrong, None if insufficient data.
    """
    try:
        # Get sessions in 30 days after prediction
        sessions = conn.execute(
            """SELECT started_at, duration_seconds, items_completed, items_correct,
                      modality_counts
               FROM session_log
               WHERE user_id = ?
                 AND started_at > ?
                 AND started_at <= datetime(?, '+30 days')
                 AND items_completed > 0
               ORDER BY started_at""",
            (user_id, pred_time, pred_time),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    n_sessions = len(sessions)

    if churn_type == "life_event":
        # Life event: expect either full return (3+ sessions) or no return
        # A life event classification is "correct" if user either:
        # - Came back with roughly normal cadence (life event passed)
        # - Didn't come back at all (life event ongoing)
        return n_sessions >= 3 or n_sessions == 0

    elif churn_type == "boredom":
        # Boredom: if user returns, expect they use more varied drills
        # or shorter sessions. If they don't return, classification plausible.
        if n_sessions == 0:
            return True  # Plausible — bored and left
        # Check drill variety in return sessions
        modalities_seen = set()
        for s in sessions:
            if s["modality_counts"]:
                try:
                    mc = json.loads(s["modality_counts"])
                    for k, v in mc.items():
                        if v and v > 0:
                            modalities_seen.add(k)
                except (json.JSONDecodeError, TypeError):
                    pass
        return len(modalities_seen) <= 2  # Low variety confirms boredom

    elif churn_type == "frustration":
        # Frustration: expect accuracy issues in return sessions
        if n_sessions == 0:
            return True
        total_correct = sum(s["items_correct"] or 0 for s in sessions)
        total_items = sum(s["items_completed"] or 0 for s in sessions)
        accuracy = total_correct / total_items if total_items > 0 else 0
        return accuracy < 0.70  # Low accuracy confirms frustration

    elif churn_type == "habit_fade":
        # Habit fade: expect sporadic, declining sessions
        if n_sessions == 0:
            return True
        # Check if sessions are sporadic (large gaps between them)
        if n_sessions >= 2:
            try:
                first = datetime.fromisoformat(sessions[0]["started_at"])
                last = datetime.fromisoformat(sessions[-1]["started_at"])
                span = (last - first).days
                avg_gap = span / (n_sessions - 1) if n_sessions > 1 else 0
                return avg_gap > 3  # Sporadic confirms habit fade
            except (ValueError, TypeError):
                pass
        return True  # Single session after prediction — plausible

    return None  # Unknown type


# ── Experiment Proposal Win Rate ─────────────────────────────────────────────


def compute_proposal_win_rate(conn: sqlite3.Connection) -> dict:
    """Track how often daemon-proposed experiments produce a winner.

    Returns {win_rate, n_started, n_concluded, n_treatment_won, n_control_won, n_futility}.
    """
    try:
        proposals = conn.execute(
            """SELECT ep.id, ep.name, ep.started_experiment_id,
                      e.status as exp_status, e.conclusion
               FROM experiment_proposal ep
               LEFT JOIN experiment e ON e.id = ep.started_experiment_id
               WHERE ep.status = 'started'
                 AND ep.started_experiment_id IS NOT NULL"""
        ).fetchall()
    except sqlite3.OperationalError:
        return {"win_rate": 0.0, "n_started": 0, "n_concluded": 0,
                "n_treatment_won": 0, "n_control_won": 0, "n_futility": 0}

    n_started = len(proposals)
    n_concluded = 0
    n_treatment_won = 0
    n_control_won = 0
    n_futility = 0

    for prop in proposals:
        if prop["exp_status"] != "concluded":
            continue
        n_concluded += 1

        conclusion = {}
        if prop["conclusion"]:
            try:
                conclusion = json.loads(prop["conclusion"])
            except (json.JSONDecodeError, TypeError):
                pass

        winner = conclusion.get("winner", "")
        notes = conclusion.get("notes", "")

        if "futility" in notes.lower():
            n_futility += 1
        elif winner == "control":
            n_control_won += 1
        else:
            n_treatment_won += 1

    win_rate = n_treatment_won / n_concluded if n_concluded > 0 else 0.0

    return {
        "win_rate": round(win_rate, 3),
        "n_started": n_started,
        "n_concluded": n_concluded,
        "n_treatment_won": n_treatment_won,
        "n_control_won": n_control_won,
        "n_futility": n_futility,
    }


# ── Guardrail Accuracy ──────────────────────────────────────────────────────


def compute_guardrail_accuracy(conn: sqlite3.Connection) -> dict:
    """Measure false positive rate for guardrail-triggered pauses.

    A false positive = experiment was paused by guardrail but, on re-analysis
    with full data, the degradation was within noise.

    Returns {false_positive_rate, n_paused, n_evaluated, n_false_positives}.
    """
    try:
        paused = conn.execute(
            """SELECT name, conclusion FROM experiment
               WHERE status = 'paused'
                  OR (status = 'concluded'
                      AND json_extract(conclusion, '$.notes') LIKE '%guardrail%')"""
        ).fetchall()
    except sqlite3.OperationalError:
        return {"false_positive_rate": 0.0, "n_paused": 0, "n_evaluated": 0,
                "n_false_positives": 0}

    # For now, track counts. Full false-positive analysis requires re-running
    # guardrail checks with accumulated data, which is done in monthly audit.
    return {
        "false_positive_rate": None,  # Requires manual monthly analysis
        "n_paused": len(paused),
        "n_evaluated": 0,
        "n_false_positives": 0,
        "note": "Full false-positive analysis requires monthly manual review",
    }


# ── Monthly Audit Summary ───────────────────────────────────────────────────


def run_monthly_audit(conn: sqlite3.Connection, period: str | None = None) -> dict:
    """Run the complete monthly intelligence self-audit.

    Args:
        conn: Database connection.
        period: Audit period label (e.g., '2026-03'). Defaults to current month.

    Returns the complete audit metrics dict and logs it to intelligence_audit table.
    """
    now = datetime.now(timezone.utc)
    if period is None:
        period = now.strftime("%Y-%m")

    brier = compute_brier_score(conn)
    classification = compute_classification_accuracy(conn)
    win_rate = compute_proposal_win_rate(conn)
    guardrail = compute_guardrail_accuracy(conn)

    metrics = {
        "brier_score": brier.get("brier_score"),
        "brier_n": brier.get("n_predictions", 0),
        "brier_target_met": brier.get("target_met", False),
        "classification_accuracy": classification.get("accuracy"),
        "classification_n": classification.get("n_evaluated", 0),
        "classification_by_type": classification.get("by_type", {}),
        "proposal_win_rate": win_rate.get("win_rate", 0),
        "proposals_started": win_rate.get("n_started", 0),
        "proposals_concluded": win_rate.get("n_concluded", 0),
        "guardrail_pauses": guardrail.get("n_paused", 0),
    }

    # Log to intelligence_audit table
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT INTO intelligence_audit (audit_type, audit_period, metrics, created_at)
               VALUES ('monthly_summary', ?, ?, ?)""",
            (period, json.dumps(metrics), now_str),
        )
        conn.commit()
        logger.info("Monthly intelligence audit logged for period %s", period)
    except sqlite3.OperationalError as e:
        logger.warning("Failed to log intelligence audit: %s", e)

    return metrics


def get_audit_history(conn: sqlite3.Connection, audit_type: str = "monthly_summary",
                      limit: int = 12) -> list[dict]:
    """Retrieve audit history for trend analysis.

    Returns list of {audit_period, metrics, created_at} ordered by most recent first.
    """
    try:
        rows = conn.execute(
            """SELECT audit_period, metrics, created_at
               FROM intelligence_audit
               WHERE audit_type = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (audit_type, limit),
        ).fetchall()
        results = []
        for r in rows:
            metrics = {}
            if r["metrics"]:
                try:
                    metrics = json.loads(r["metrics"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append({
                "audit_period": r["audit_period"],
                "metrics": metrics,
                "created_at": r["created_at"],
            })
        return results
    except sqlite3.OperationalError:
        return []
