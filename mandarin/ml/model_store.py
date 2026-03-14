"""Model persistence and versioning."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    model_name: str
    trained_at: str
    samples: int
    val_accuracy: float
    baseline_accuracy: float
    improvement: float


def save_model(model, path: Path, metrics: dict, conn: sqlite3.Connection) -> None:
    """Save model to disk and register in pi_ml_model_versions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    model_id = str(uuid.uuid4())
    model_name = path.stem

    conn.execute("""
        INSERT INTO pi_ml_model_versions
        (id, model_name, trained_at, model_path, sample_count,
         val_accuracy, baseline_accuracy, improvement, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        model_id, model_name, now, str(path),
        metrics.get('samples', 0),
        metrics.get('val_accuracy', 0),
        metrics.get('baseline_accuracy', 0),
        metrics.get('improvement_over_baseline', 0),
    ))

    # Deactivate old versions
    conn.execute("""
        UPDATE pi_ml_model_versions
        SET active = 0, retired_at = ?
        WHERE model_name = ? AND id != ?
    """, (now, model_name, model_id))
    conn.commit()


def load_model(path: Path):
    """Load a model from disk. Returns None if not found or corrupt."""
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        logger.debug("Failed to load model from %s", path, exc_info=True)
        return None


def load_model_metadata(conn: sqlite3.Connection, model_name: str) -> Optional[ModelMetadata]:
    """Load metadata for the active version of a model."""
    row = conn.execute("""
        SELECT model_name, trained_at, sample_count, val_accuracy,
               baseline_accuracy, improvement
        FROM pi_ml_model_versions
        WHERE model_name = ? AND active = 1
        ORDER BY trained_at DESC LIMIT 1
    """, (model_name,)).fetchone()
    if not row:
        return None
    return ModelMetadata(
        model_name=row["model_name"],
        trained_at=row["trained_at"],
        samples=row["sample_count"],
        val_accuracy=row["val_accuracy"] or 0,
        baseline_accuracy=row["baseline_accuracy"] or 0,
        improvement=row["improvement"] or 0,
    )
