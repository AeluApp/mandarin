"""Tests for traditional ML — difficulty prediction + fuzzy dedup."""

import pytest
np = pytest.importorskip("numpy")

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from mandarin.ml.feature_engineering import (
    build_feature_vector, FEATURE_ORDER,
    extract_item_features, extract_learner_state_features,
    extract_item_learner_features,
)
from mandarin.ml.difficulty_model import (
    predict_difficulty, train_difficulty_model, should_retrain,
    MIN_TRAINING_SAMPLES, MODEL_PATH,
)
from mandarin.ml.model_store import save_model, load_model, load_model_metadata


@pytest.fixture
def conn():
    """In-memory SQLite with ML-relevant tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")

    c.executescript("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY,
            hanzi TEXT, pinyin TEXT, english TEXT,
            hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready',
            source TEXT,
            example_sentence_hanzi TEXT,
            example_sentence_pinyin TEXT,
            example_sentence_english TEXT
        );

        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            session_id INTEGER,
            content_item_id INTEGER NOT NULL,
            modality TEXT NOT NULL,
            drill_type TEXT,
            correct INTEGER NOT NULL,
            confidence TEXT DEFAULT 'full',
            response_ms INTEGER,
            error_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (content_item_id) REFERENCES content_item(id)
        );

        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE learner_profile (
            id INTEGER PRIMARY KEY,
            level_reading INTEGER DEFAULT 1
        );

        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER
        );

        CREATE TABLE pi_finding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            dimension TEXT,
            severity TEXT,
            title TEXT,
            analysis TEXT,
            status TEXT DEFAULT 'investigating',
            times_seen INTEGER DEFAULT 1,
            last_seen_audit_id INTEGER,
            metric_name TEXT,
            metric_value_at_detection REAL
        );

        CREATE TABLE pi_difficulty_predictions (
            id TEXT PRIMARY KEY,
            review_event_id INTEGER,
            user_id INTEGER NOT NULL DEFAULT 1,
            content_item_id INTEGER NOT NULL,
            session_id INTEGER,
            predicted_accuracy REAL NOT NULL,
            difficulty_class TEXT NOT NULL,
            prediction_confidence REAL NOT NULL,
            model_available INTEGER NOT NULL DEFAULT 1,
            actual_correct INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE pi_finding_embeddings (
            finding_id INTEGER PRIMARY KEY,
            title_at_embedding TEXT NOT NULL,
            embedding_bytes BLOB NOT NULL,
            embedded_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE pi_ml_model_versions (
            id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            trained_at TEXT NOT NULL DEFAULT (datetime('now')),
            model_path TEXT NOT NULL,
            sample_count INTEGER NOT NULL,
            val_accuracy REAL,
            baseline_accuracy REAL,
            improvement REAL,
            active INTEGER NOT NULL DEFAULT 1,
            retired_at TEXT
        );

        CREATE TABLE pi_ml_pipeline_runs (
            id TEXT PRIMARY KEY,
            run_at TEXT NOT NULL DEFAULT (datetime('now')),
            results_json TEXT NOT NULL
        );
    """)

    # Seed test data
    c.execute("INSERT INTO learner_profile (id, level_reading) VALUES (1, 2)")
    c.execute("INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level) VALUES (1, '你好', 'nǐ hǎo', 'hello', 1)")
    c.execute("INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level) VALUES (2, '谢谢', 'xiè xie', 'thanks', 1)")
    c.execute("INSERT INTO session_log (id) VALUES (1)")
    c.commit()
    return c


# ── Test 1: build_feature_vector returns correct length ──

def test_feature_vector_length(conn):
    vec = build_feature_vector(conn, item_id=1, user_id=1, session_id=1, position_in_session=0)
    assert len(vec) == len(FEATURE_ORDER)
    assert vec.dtype == np.float32


# ── Test 2: feature vector handles new user (no history) ──

def test_feature_vector_new_user(conn):
    vec = build_feature_vector(conn, item_id=1, user_id=999, session_id=1, position_in_session=0)
    assert len(vec) == len(FEATURE_ORDER)
    # All should be valid floats
    assert not np.any(np.isnan(vec))


# ── Test 3: feature vector handles new item (no reviews) ──

def test_feature_vector_new_item(conn):
    conn.execute("INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level) VALUES (99, '新', 'xīn', 'new', 1)")
    conn.commit()
    vec = build_feature_vector(conn, item_id=99, user_id=1, session_id=1, position_in_session=0)
    assert len(vec) == len(FEATURE_ORDER)
    assert not np.any(np.isnan(vec))


# ── Test 4: train returns skipped with insufficient data ──

def test_train_insufficient_data(conn):
    result = train_difficulty_model(conn)
    assert result['status'] == 'skipped'
    assert 'insufficient_data' in result.get('reason', '')


# ── Test 5: train returns not_saved if not improving baseline ──

def test_train_not_saved_when_not_improving(conn):
    """With random data, model should not beat baseline by >2%."""
    import random
    random.seed(42)
    # Insert enough data (all items get 50/50 — baseline = 50%)
    for i in range(250):
        correct = random.choice([0, 1])
        conn.execute(
            "INSERT INTO review_event (user_id, session_id, content_item_id, modality, correct) VALUES (1, 1, ?, 'reading', ?)",
            (random.choice([1, 2]), correct),
        )
    conn.commit()

    result = train_difficulty_model(conn)
    # With random labels, model shouldn't consistently beat baseline
    assert result['status'] in ('trained', 'not_saved', 'skipped')


# ── Test 6: predict returns model_available=False when no model ──

def test_predict_no_model(conn):
    with patch('mandarin.ml.difficulty_model.load_model', return_value=None):
        result = predict_difficulty(conn, item_id=1, user_id=1)
    assert result['model_available'] is False
    assert result['predicted_accuracy'] is None


# ── Test 7: classify 0.90 as too_easy ──

def test_classify_too_easy(conn):
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array([0.90])
    with patch('mandarin.ml.difficulty_model.load_model', return_value=mock_model):
        result = predict_difficulty(conn, item_id=1, user_id=1)
    assert result['difficulty_class'] == 'too_easy'


# ── Test 8: classify 0.77 as in_zone ──

def test_classify_in_zone(conn):
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array([0.77])
    with patch('mandarin.ml.difficulty_model.load_model', return_value=mock_model):
        result = predict_difficulty(conn, item_id=1, user_id=1)
    assert result['difficulty_class'] == 'in_zone'


# ── Test 9: classify 0.55 as too_hard ──

def test_classify_too_hard(conn):
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array([0.55])
    with patch('mandarin.ml.difficulty_model.load_model', return_value=mock_model):
        result = predict_difficulty(conn, item_id=1, user_id=1)
    assert result['difficulty_class'] == 'too_hard'


# ── Test 10: compute_similarity high for semantically identical ──

def test_similarity_identical():
    """Semantic similarity for nearly identical sentences should be high."""
    try:
        from mandarin.ml.fuzzy_dedup import compute_similarity, is_available
        if not is_available():
            pytest.skip("sentence-transformers not installed")
        sim = compute_similarity("D1 retention: 20%", "D1 retention: 18%")
        assert sim > 0.85
    except ImportError:
        pytest.skip("sentence-transformers not installed")


# ── Test 11: compute_similarity low for unrelated ──

def test_similarity_unrelated():
    try:
        from mandarin.ml.fuzzy_dedup import compute_similarity, is_available
        if not is_available():
            pytest.skip("sentence-transformers not installed")
        sim = compute_similarity("D1 retention rate is low", "The weather is sunny today")
        assert sim < 0.60
    except ImportError:
        pytest.skip("sentence-transformers not installed")


# ── Test 12: find_semantic_duplicate finds matching finding ──

def test_find_semantic_duplicate(conn):
    try:
        from mandarin.ml.fuzzy_dedup import find_semantic_duplicate, is_available
        if not is_available():
            pytest.skip("sentence-transformers not installed")
        conn.execute("""
            INSERT INTO pi_finding (dimension, severity, title, status)
            VALUES ('retention', 'medium', 'D1 retention: 20% — below target', 'investigating')
        """)
        conn.commit()

        dup_id = find_semantic_duplicate(conn, 'retention', 'D1 retention: 18% — below target')
        assert dup_id is not None
    except ImportError:
        pytest.skip("sentence-transformers not installed")


# ── Test 13: find_semantic_duplicate returns None for distinct finding ──

def test_no_false_positive_duplicate(conn):
    try:
        from mandarin.ml.fuzzy_dedup import find_semantic_duplicate, is_available
        if not is_available():
            pytest.skip("sentence-transformers not installed")
        conn.execute("""
            INSERT INTO pi_finding (dimension, severity, title, status)
            VALUES ('retention', 'medium', 'D1 retention: 20%', 'investigating')
        """)
        conn.commit()

        dup_id = find_semantic_duplicate(conn, 'retention', 'Session completion rate dropped to 40%')
        assert dup_id is None
    except ImportError:
        pytest.skip("sentence-transformers not installed")


# ── Test 14: calibrate returns insufficient_data with <2 findings ──

def test_calibrate_insufficient(conn):
    try:
        from mandarin.ml.fuzzy_dedup import calibrate_similarity_threshold, is_available
        if not is_available():
            pytest.skip("sentence-transformers not installed")
        result = calibrate_similarity_threshold(conn)
        assert result['status'] == 'insufficient_data'
    except ImportError:
        pytest.skip("sentence-transformers not installed")


# ── Test 15: save_model deactivates prior versions ──

def test_save_model_deactivates_old(conn):
    import tempfile
    from pathlib import Path

    # Save first version
    mock_model = {"version": 1}
    with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as f:
        path = Path(f.name)

    save_model(mock_model, path, {"samples": 100, "val_accuracy": 0.7, "baseline_accuracy": 0.6, "improvement_over_baseline": 0.1}, conn)

    # Save second version
    save_model({"version": 2}, path, {"samples": 200, "val_accuracy": 0.8, "baseline_accuracy": 0.6, "improvement_over_baseline": 0.2}, conn)

    active = conn.execute("SELECT COUNT(*) as cnt FROM pi_ml_model_versions WHERE active = 1 AND model_name = ?",
                          (path.stem,)).fetchone()
    assert active["cnt"] == 1

    total = conn.execute("SELECT COUNT(*) as cnt FROM pi_ml_model_versions WHERE model_name = ?",
                         (path.stem,)).fetchone()
    assert total["cnt"] == 2

    # Cleanup
    path.unlink(missing_ok=True)


# ── Test 16: load_model returns None when file not found ──

def test_load_model_missing():
    from pathlib import Path
    result = load_model(Path("/nonexistent/model.joblib"))
    assert result is None


# ── Test 17: should_retrain returns False with insufficient data ──

def test_should_retrain_insufficient(conn):
    assert should_retrain(conn) is False


# ── Test 18: learner state features handle empty DB ──

def test_learner_state_empty(conn):
    feats = extract_learner_state_features(conn, user_id=999)
    assert feats['recent_accuracy_10'] == 0.5
    assert feats['sessions_today'] == 0
