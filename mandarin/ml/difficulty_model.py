"""Gradient boosted item difficulty predictor (LightGBM).

Predicts whether a specific item will be too hard or too easy for this
specific learner at this specific moment. Feeds into scheduler as a soft
preference — items predicted "in_zone" get priority.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Optional

import numpy as np

from .feature_engineering import build_feature_vector, FEATURE_ORDER
from .model_store import save_model, load_model, load_model_metadata

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "models" / "difficulty_model.joblib"
MIN_TRAINING_SAMPLES = 200
RETRAIN_INTERVAL_DAYS = 7


def should_retrain(conn: sqlite3.Connection) -> bool:
    """Check if model needs retraining."""
    sample_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM review_event WHERE session_id IS NOT NULL"
    ).fetchone()
    count = sample_count["cnt"] if sample_count else 0

    if count < MIN_TRAINING_SAMPLES:
        return False

    meta = load_model_metadata(conn, "difficulty_model")
    if meta is None:
        return True

    try:
        trained_dt = datetime.fromisoformat(meta.trained_at)
        days_since = (datetime.now(UTC) - trained_dt).days
    except (ValueError, TypeError):
        return True

    return days_since >= RETRAIN_INTERVAL_DAYS


def train_difficulty_model(conn: sqlite3.Connection) -> dict:
    """Train gradient boosted model on historical review data."""
    try:
        import lightgbm as lgb
    except ImportError:
        return {'status': 'skipped', 'reason': 'lightgbm not installed'}

    X, y = _build_training_data(conn)

    if len(X) < MIN_TRAINING_SAMPLES:
        return {
            'status': 'skipped',
            'reason': f'insufficient_data: {len(X)} samples, need {MIN_TRAINING_SAMPLES}',
        }

    # Time-ordered train/val split (no future leakage)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.9,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': -1,
        'min_child_samples': 20,
    }

    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    model = lgb.train(
        params, train_data,
        num_boost_round=200,
        valid_sets=[val_data],
        callbacks=[
            lgb.early_stopping(stopping_rounds=20, verbose=False),
            lgb.log_evaluation(period=-1),
        ],
    )

    val_preds = model.predict(X_val)
    val_accuracy = float(np.mean((val_preds >= 0.5) == y_val))
    baseline_accuracy = float(max(y_val.mean(), 1 - y_val.mean()))

    metrics = {
        'status': 'trained',
        'samples': len(X),
        'val_accuracy': val_accuracy,
        'baseline_accuracy': baseline_accuracy,
        'improvement_over_baseline': val_accuracy - baseline_accuracy,
        'feature_importances': dict(zip(
            FEATURE_ORDER,
            model.feature_importance(importance_type='gain').tolist(), strict=False,
        )),
    }

    if val_accuracy > baseline_accuracy + 0.02:
        save_model(model, MODEL_PATH, metrics, conn)
        logger.info("Difficulty model saved. Val: %.3f (baseline: %.3f)", val_accuracy, baseline_accuracy)
    else:
        metrics['status'] = 'not_saved'
        metrics['reason'] = f'not better than baseline ({val_accuracy:.3f} vs {baseline_accuracy:.3f})'

    return metrics


def _build_training_data(conn: sqlite3.Connection):
    """Build (X, y) from historical review events."""
    reviews = conn.execute("""
        SELECT re.id, re.content_item_id, re.user_id, re.session_id,
               re.correct, re.modality, re.created_at
        FROM review_event re
        WHERE re.session_id IS NOT NULL
        ORDER BY re.created_at
    """).fetchall()

    X_rows, y_rows = [], []
    # Track position within each session
    session_positions = {}

    for review in reviews:
        sid = review['session_id']
        session_positions[sid] = session_positions.get(sid, 0) + 1

        try:
            features = build_feature_vector(
                conn,
                item_id=review['content_item_id'],
                user_id=review['user_id'],
                session_id=sid,
                position_in_session=session_positions[sid],
                modality=review['modality'] or 'reading',
            )
            X_rows.append(features)
            y_rows.append(float(review['correct']))
        except Exception:
            continue

    if not X_rows:
        return np.array([]), np.array([])

    return np.array(X_rows), np.array(y_rows)


def predict_difficulty(
    conn: sqlite3.Connection,
    item_id,
    user_id: int = 1,
    session_id=None,
    position_in_session: int = 0,
    modality: str = "reading",
) -> dict:
    """Predict difficulty for a specific (item, learner, session) tuple.

    Returns dict with predicted_accuracy, difficulty_class, prediction_confidence, model_available.
    """
    model = load_model(MODEL_PATH)

    if model is None:
        return {
            'predicted_accuracy': None,
            'difficulty_class': None,
            'prediction_confidence': 0.0,
            'model_available': False,
            'reason': 'model_not_trained',
        }

    features = build_feature_vector(
        conn, item_id, user_id, session_id, position_in_session, modality,
    )
    features_2d = features.reshape(1, -1)

    predicted_acc = float(model.predict(features_2d)[0])

    # Classify using desirable difficulty zone (70-85%)
    if predicted_acc >= 0.85:
        difficulty_class = 'too_easy'
    elif predicted_acc >= 0.70:
        difficulty_class = 'in_zone'
    else:
        difficulty_class = 'too_hard'

    # Confidence: higher when prediction is decisive
    confidence = min(1.0, abs(predicted_acc - 0.5) * 4)

    return {
        'predicted_accuracy': predicted_acc,
        'difficulty_class': difficulty_class,
        'prediction_confidence': confidence,
        'model_available': True,
    }


def log_prediction(conn: sqlite3.Connection, prediction: dict,
                   item_id, user_id: int = 1, session_id=None,
                   review_event_id=None) -> None:
    """Log a difficulty prediction for later evaluation."""
    if not prediction.get('model_available'):
        return
    try:
        conn.execute("""
            INSERT INTO pi_difficulty_predictions
            (id, review_event_id, user_id, content_item_id, session_id,
             predicted_accuracy, difficulty_class, prediction_confidence, model_available)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            str(uuid.uuid4()), review_event_id, user_id, item_id, session_id,
            prediction['predicted_accuracy'],
            prediction['difficulty_class'],
            prediction['prediction_confidence'],
        ))
    except Exception:
        logger.debug("Failed to log difficulty prediction", exc_info=True)
