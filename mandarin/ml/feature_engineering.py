"""Feature extraction for ML models — adapted to Aelu schema.

Tables used: content_item, review_event, error_log, session_log, learner_profile.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

import numpy as np


# Fixed feature order — must never change after first training
FEATURE_ORDER = [
    # Item features
    'hsk_level', 'modality_reading', 'modality_listening',
    'modality_speaking', 'modality_ime', 'character_count',
    'has_multiple_meanings', 'global_accuracy', 'global_review_count',
    'global_data_confidence',
    # Learner state
    'recent_accuracy_10', 'recent_accuracy_50', 'accuracy_trend',
    'sessions_today', 'days_since_last_session', 'tone_accuracy_recent',
    'listening_accuracy_recent', 'reading_accuracy_recent', 'items_reviewed_today',
    # Item-learner relationship
    'times_seen', 'personal_accuracy', 'days_since_last_review',
    'is_new_item', 'avg_response_time_ms', 'consecutive_correct',
    'last_review_correct',
    # Session context
    'position_in_session', 'session_accuracy_so_far', 'errors_so_far',
    'hour_of_day', 'time_of_day_factor',
]


def extract_item_features(conn: sqlite3.Connection, item_id) -> dict:
    """Static features of the item itself."""
    row = conn.execute("""
        SELECT ci.hsk_level, ci.hanzi, ci.english,
               COUNT(re.id) as total_reviews,
               AVG(CASE WHEN re.correct = 1 THEN 1.0 ELSE 0.0 END) as global_accuracy
        FROM content_item ci
        LEFT JOIN review_event re ON re.content_item_id = ci.id
        WHERE ci.id = ?
        GROUP BY ci.id
    """, (item_id,)).fetchone()

    if not row:
        return {}

    english = row["english"] or ""
    has_multi = 1 if (";" in english or "/" in english) else 0

    return {
        'hsk_level': row['hsk_level'] or 1,
        'character_count': len(row['hanzi'] or ''),
        'has_multiple_meanings': has_multi,
        'global_accuracy': row['global_accuracy'] if row['global_accuracy'] is not None else 0.5,
        'global_review_count': min(row['total_reviews'] or 0, 100),
        'global_data_confidence': min(1.0, (row['total_reviews'] or 0) / 20),
    }


def extract_learner_state_features(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Features describing the learner's current state."""
    recent = conn.execute("""
        SELECT correct, modality, created_at
        FROM review_event
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 50
    """, (user_id,)).fetchall()

    if not recent:
        return {
            'recent_accuracy_10': 0.5, 'recent_accuracy_50': 0.5,
            'accuracy_trend': 0.0, 'sessions_today': 0,
            'days_since_last_session': 1, 'tone_accuracy_recent': 0.5,
            'listening_accuracy_recent': 0.5, 'reading_accuracy_recent': 0.5,
            'items_reviewed_today': 0,
        }

    last_10 = recent[:10]
    acc_10 = sum(r['correct'] for r in last_10) / len(last_10) if last_10 else 0.5
    acc_50 = sum(r['correct'] for r in recent) / len(recent) if recent else 0.5

    # Trend
    if len(recent) >= 20:
        first_10_acc = sum(r['correct'] for r in recent[-10:]) / 10
        trend = acc_10 - first_10_acc
    else:
        trend = 0.0

    # Modality-specific accuracy
    def _modality_acc(mod):
        subset = [r for r in recent if r['modality'] == mod]
        return sum(r['correct'] for r in subset) / len(subset) if subset else 0.5

    # Session fatigue
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    today_row = conn.execute("""
        SELECT COUNT(*) as cnt,
               COUNT(DISTINCT session_id) as sessions
        FROM review_event
        WHERE user_id = ? AND DATE(created_at) = ?
    """, (user_id, today)).fetchone()

    # Days since last session
    last_row = conn.execute("""
        SELECT MAX(created_at) as last_review FROM review_event WHERE user_id = ?
    """, (user_id,)).fetchone()
    days_since = 1
    if last_row and last_row['last_review']:
        try:
            last_dt = datetime.fromisoformat(last_row['last_review'])
            days_since = max(0, (now - last_dt).days)
        except (ValueError, TypeError):
            days_since = 1

    return {
        'recent_accuracy_10': acc_10,
        'recent_accuracy_50': acc_50,
        'accuracy_trend': trend,
        'sessions_today': (today_row['sessions'] or 0) if today_row else 0,
        'days_since_last_session': min(days_since, 30),
        'tone_accuracy_recent': _modality_acc('speaking'),
        'listening_accuracy_recent': _modality_acc('listening'),
        'reading_accuracy_recent': _modality_acc('reading'),
        'items_reviewed_today': (today_row['cnt'] or 0) if today_row else 0,
    }


def extract_item_learner_features(
    conn: sqlite3.Connection, item_id, user_id: int = 1,
) -> dict:
    """Features describing the relationship between this item and this learner."""
    history = conn.execute("""
        SELECT
            COUNT(*) as times_seen,
            SUM(correct) as times_correct,
            MAX(created_at) as last_reviewed_at,
            AVG(response_ms) as avg_response_time_ms
        FROM review_event
        WHERE content_item_id = ? AND user_id = ?
    """, (item_id, user_id)).fetchone()

    if not history or (history['times_seen'] or 0) == 0:
        return {
            'times_seen': 0, 'personal_accuracy': 0.5,
            'days_since_last_review': 30, 'is_new_item': 1,
            'avg_response_time_ms': 5000, 'consecutive_correct': 0,
            'last_review_correct': 0,
        }

    times_seen = history['times_seen'] or 0
    personal_acc = (history['times_correct'] or 0) / times_seen if times_seen > 0 else 0.5

    days_since = 30
    if history['last_reviewed_at']:
        try:
            last_dt = datetime.fromisoformat(history['last_reviewed_at'])
            days_since = max(0, (datetime.now(timezone.utc) - last_dt).days)
        except (ValueError, TypeError):
            pass

    # Consecutive correct streak
    streak_rows = conn.execute("""
        SELECT correct FROM review_event
        WHERE content_item_id = ? AND user_id = ?
        ORDER BY created_at DESC LIMIT 5
    """, (item_id, user_id)).fetchall()

    consecutive = 0
    for r in streak_rows:
        if r['correct']:
            consecutive += 1
        else:
            break

    last_correct = streak_rows[0]['correct'] if streak_rows else 0

    return {
        'times_seen': min(times_seen, 50),
        'personal_accuracy': personal_acc,
        'days_since_last_review': min(days_since, 60),
        'is_new_item': 0,
        'avg_response_time_ms': min(history['avg_response_time_ms'] or 5000, 30000),
        'consecutive_correct': consecutive,
        'last_review_correct': last_correct,
    }


def extract_session_context_features(
    conn: sqlite3.Connection, session_id, position_in_session: int,
) -> dict:
    """Features about the current session context."""
    session_so_far = conn.execute("""
        SELECT
            COUNT(*) as items_done,
            AVG(CASE WHEN correct = 1 THEN 1.0 ELSE 0.0 END) as session_accuracy,
            SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) as errors_so_far
        FROM review_event
        WHERE session_id = ?
    """, (session_id,)).fetchone()

    hour = datetime.now(timezone.utc).hour

    if 6 <= hour <= 10:
        tod_factor = 1.0
    elif 11 <= hour <= 14:
        tod_factor = 0.9
    elif 15 <= hour <= 19:
        tod_factor = 0.95
    else:
        tod_factor = 0.85

    return {
        'position_in_session': min(position_in_session, 50),
        'session_accuracy_so_far': (session_so_far['session_accuracy'] or 0.5) if session_so_far else 0.5,
        'errors_so_far': min((session_so_far['errors_so_far'] or 0) if session_so_far else 0, 20),
        'hour_of_day': hour,
        'time_of_day_factor': tod_factor,
    }


def build_feature_vector(
    conn: sqlite3.Connection, item_id, user_id: int = 1,
    session_id=None, position_in_session: int = 0,
    modality: str = "reading",
) -> np.ndarray:
    """Combine all feature groups into a single numpy array for model input."""
    item_feats = extract_item_features(conn, item_id)
    learner_feats = extract_learner_state_features(conn, user_id)
    item_learner_feats = extract_item_learner_features(conn, item_id, user_id)
    session_feats = extract_session_context_features(conn, session_id, position_in_session)

    # Modality one-hot encoding
    modality_feats = {
        'modality_reading': 1 if modality == 'reading' else 0,
        'modality_listening': 1 if modality == 'listening' else 0,
        'modality_speaking': 1 if modality == 'speaking' else 0,
        'modality_ime': 1 if modality == 'ime' else 0,
    }

    all_feats = {**modality_feats, **item_feats, **learner_feats,
                 **item_learner_feats, **session_feats}
    return np.array([all_feats.get(f, 0.0) for f in FEATURE_ORDER], dtype=np.float32)
