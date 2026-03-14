"""ML system health — intelligence analyzer integration."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def analyze_ml_health(conn: sqlite3.Connection) -> list[dict]:
    """Intelligence findings for ML subsystem health."""
    findings = []

    # Difficulty model status
    try:
        from .difficulty_model import load_model, MODEL_PATH, MIN_TRAINING_SAMPLES

        model = load_model(MODEL_PATH)
        sample_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_event WHERE session_id IS NOT NULL"
        ).fetchone()
        count = (sample_count["cnt"] if sample_count else 0) or 0

        if model is None and count >= MIN_TRAINING_SAMPLES:
            findings.append({
                "dimension": "scheduler_audit",
                "severity": "medium",
                "title": "Difficulty prediction model not trained (sufficient data available)",
                "analysis": f"{count} review events available. Model should be trained.",
                "recommendation": "Run ML training pipeline via admin endpoint or CLI.",
                "claude_prompt": "Train the difficulty prediction model: run_ml_pipeline(conn)",
                "impact": "Scheduler uses static difficulty instead of learned predictions",
                "files": ["mandarin/ml/difficulty_model.py"],
            })

        # Check recent prediction accuracy (if predictions exist)
        if model is not None:
            cal_row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    AVG(CASE
                        WHEN actual_correct IS NOT NULL
                        THEN ABS(predicted_accuracy - actual_correct)
                    END) as calibration_error
                FROM pi_difficulty_predictions
                WHERE created_at >= datetime('now', '-14 days')
                AND actual_correct IS NOT NULL
            """).fetchone()

            if cal_row and (cal_row["total"] or 0) >= 50:
                cal_error = cal_row["calibration_error"] or 0
                if cal_error > 0.15:
                    findings.append({
                        "dimension": "scheduler_audit",
                        "severity": "medium",
                        "title": f"Difficulty model calibration degraded: {cal_error:.2f} error",
                        "analysis": (
                            f"Calibration error {cal_error:.2f} exceeds 0.15 threshold "
                            f"over {cal_row['total']} predictions. Model may need retraining."
                        ),
                        "recommendation": "Retrain difficulty model with latest data.",
                        "claude_prompt": "Retrain difficulty model: train_difficulty_model(conn)",
                        "impact": "Item selection less effective — accuracy zone targeting degraded",
                        "files": ["mandarin/ml/difficulty_model.py"],
                    })
    except ImportError:
        pass
    except Exception as e:
        logger.debug("ML health check failed: %s", e)

    return findings


ANALYZERS = [analyze_ml_health]
