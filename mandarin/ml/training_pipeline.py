"""ML training orchestration — called on-demand from admin or weekly job."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)


def run_ml_pipeline(conn: sqlite3.Connection) -> dict:
    """Orchestrate all ML training and health checks."""
    results = {}

    # 1. Difficulty model
    try:
        from .difficulty_model import should_retrain, train_difficulty_model
        if should_retrain(conn):
            logger.info("Retraining difficulty model...")
            results['difficulty_model'] = train_difficulty_model(conn)
        else:
            results['difficulty_model'] = {'status': 'skipped', 'reason': 'not_due'}
    except ImportError:
        results['difficulty_model'] = {'status': 'skipped', 'reason': 'lightgbm_not_installed'}
    except Exception as e:
        results['difficulty_model'] = {'status': 'error', 'error': str(e)}
        logger.exception("Difficulty model training failed")

    # 2. Similarity threshold calibration
    try:
        from .fuzzy_dedup import calibrate_similarity_threshold
        results['similarity_calibration'] = calibrate_similarity_threshold(conn)
    except Exception as e:
        results['similarity_calibration'] = {'status': 'error', 'error': str(e)}

    # 3. Log results
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO pi_ml_pipeline_runs (id, run_at, results_json)
            VALUES (?, ?, ?)
        """, (str(uuid.uuid4()), now, json.dumps(results, default=str)))
        conn.commit()
    except Exception:
        logger.debug("Failed to log pipeline run", exc_info=True)

    return results
