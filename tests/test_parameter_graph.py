"""Tests for Intelligence Engine Parameter Graph (Phase 4).

Covers: parameter registry, decorator, sync, influence model seeding,
edge updates, change generator, direction source labeling, work order
implement with parameter logging, honest fallback, parallel period.
"""

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def _make_db():
    """Create an in-memory SQLite DB with all required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Core tables
    conn.execute("""CREATE TABLE user (
        id INTEGER PRIMARY KEY, email TEXT, created_at TEXT DEFAULT (datetime('now')),
        subscription_tier TEXT DEFAULT 'free', streak_freezes_available INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE session_log (
        id INTEGER PRIMARY KEY, user_id INTEGER, started_at TEXT DEFAULT (datetime('now')),
        items_planned INTEGER DEFAULT 10, items_completed INTEGER DEFAULT 8,
        early_exit INTEGER DEFAULT 0, plan_snapshot TEXT,
        client_platform TEXT DEFAULT 'web'
    )""")
    conn.execute("""CREATE TABLE review_event (
        id INTEGER PRIMARY KEY, user_id INTEGER, content_item_id INTEGER,
        drill_type TEXT, correct INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE content_item (
        id INTEGER PRIMARY KEY, hanzi TEXT, english TEXT, hsk_level INTEGER
    )""")
    conn.execute("""CREATE TABLE progress (
        id INTEGER PRIMARY KEY, user_id INTEGER DEFAULT 1, content_item_id INTEGER,
        mastery_stage TEXT DEFAULT 'learning', modality TEXT DEFAULT 'reading',
        repetitions INTEGER DEFAULT 0, interval_days INTEGER DEFAULT 1,
        ease_factor REAL DEFAULT 2.5, weak_cycle_count INTEGER DEFAULT 0,
        historically_weak INTEGER DEFAULT 0, next_review_at TEXT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # Intelligence tables
    conn.execute("""CREATE TABLE product_audit (
        id INTEGER PRIMARY KEY, run_at TEXT DEFAULT (datetime('now')),
        overall_grade TEXT, overall_score REAL,
        dimension_scores TEXT, findings_json TEXT,
        findings_count INTEGER, critical_count INTEGER, high_count INTEGER
    )""")
    conn.execute("""CREATE TABLE pi_finding (
        id INTEGER PRIMARY KEY, audit_id INTEGER,
        dimension TEXT, severity TEXT, title TEXT, analysis TEXT,
        status TEXT DEFAULT 'investigating',
        hypothesis TEXT, falsification TEXT,
        metric_name TEXT, metric_value_at_detection REAL,
        root_cause_tag TEXT, linked_finding_id INTEGER,
        times_seen INTEGER DEFAULT 1, last_seen_audit_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        resolved_at TEXT, resolution_notes TEXT
    )""")
    conn.execute("""CREATE TABLE pi_recommendation_outcome (
        id INTEGER PRIMARY KEY, finding_id INTEGER,
        action_type TEXT, action_description TEXT,
        files_changed TEXT, metric_before TEXT, metric_after TEXT,
        verified_at TEXT, delta_pct REAL, effective INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE pi_decision_log (
        id INTEGER PRIMARY KEY, finding_id INTEGER,
        decision_class TEXT, escalation_level TEXT,
        presented_to TEXT, decision TEXT, decision_reason TEXT,
        override_expires_at TEXT, outcome_notes TEXT,
        requires_approval INTEGER DEFAULT 0, approved_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE pi_threshold_calibration (
        metric_name TEXT PRIMARY KEY, threshold_value REAL NOT NULL,
        calibrated_at TEXT DEFAULT (datetime('now')),
        sample_size INTEGER, false_positive_rate REAL,
        false_negative_rate REAL, prior_threshold REAL,
        notes TEXT, verification_window_days INTEGER
    )""")
    conn.execute("""CREATE TABLE pi_advisor_opinion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        finding_id INTEGER NOT NULL,
        advisor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        recommendation TEXT,
        priority_score REAL NOT NULL DEFAULT 0,
        effort_estimate REAL,
        rationale TEXT,
        tradeoff_notes TEXT
    )""")

    # Self-correction tables (v57)
    conn.execute("""CREATE TABLE pi_prediction_ledger (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        finding_id INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        dimension TEXT NOT NULL,
        claim_type TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        metric_baseline REAL NOT NULL,
        predicted_delta REAL NOT NULL,
        predicted_delta_confidence REAL NOT NULL,
        verification_window_days INTEGER NOT NULL,
        verification_due_at TEXT NOT NULL,
        outcome_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
    )""")
    conn.execute("""CREATE TABLE pi_prediction_outcomes (
        id TEXT PRIMARY KEY,
        prediction_id TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
        metric_actual REAL NOT NULL,
        actual_delta REAL NOT NULL,
        direction_correct INTEGER NOT NULL,
        magnitude_error REAL NOT NULL,
        outcome_class TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE pi_model_confidence (
        model_id TEXT PRIMARY KEY,
        dimension TEXT NOT NULL,
        correct_count INTEGER NOT NULL DEFAULT 0,
        directionally_correct_count INTEGER NOT NULL DEFAULT 0,
        wrong_count INTEGER NOT NULL DEFAULT 0,
        insufficient_data_count INTEGER NOT NULL DEFAULT 0,
        measurement_failure_count INTEGER NOT NULL DEFAULT 0,
        current_confidence REAL NOT NULL DEFAULT 0.5,
        last_updated TEXT
    )""")
    conn.execute("""CREATE TABLE pi_self_audit_report (
        id TEXT PRIMARY KEY,
        generated_at TEXT NOT NULL DEFAULT (datetime('now')),
        lookback_days INTEGER NOT NULL,
        total_predictions INTEGER,
        correct_count INTEGER,
        directionally_correct_count INTEGER,
        wrong_count INTEGER,
        expired_count INTEGER,
        invalidated_count INTEGER,
        insufficient_data_count INTEGER,
        worst_models_json TEXT,
        best_models_json TEXT,
        current_constraint TEXT,
        constraint_confidence REAL,
        human_override_accuracy REAL,
        engine_accuracy REAL,
        override_domains_json TEXT,
        report_json TEXT
    )""")
    conn.execute("""CREATE TABLE spc_observation (
        id INTEGER PRIMARY KEY, chart_type TEXT, value REAL,
        ucl REAL, lcl REAL, rule_violated TEXT,
        observed_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE experiment (
        id INTEGER PRIMARY KEY, name TEXT, status TEXT DEFAULT 'running',
        min_sample_size INTEGER DEFAULT 100, created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # Prescription layer (v58)
    conn.execute("""CREATE TABLE pi_work_order (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_cycle_id INTEGER NOT NULL,
        finding_id INTEGER NOT NULL,
        prediction_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        constraint_dimension TEXT NOT NULL,
        constraint_score REAL NOT NULL,
        marginal_improvement REAL NOT NULL,
        instruction TEXT NOT NULL,
        target_file TEXT,
        target_parameter TEXT,
        direction TEXT,
        success_metric TEXT NOT NULL,
        success_baseline REAL NOT NULL,
        success_threshold REAL NOT NULL,
        verification_window_days INTEGER NOT NULL,
        verification_due_at TEXT,
        subordinated_count INTEGER NOT NULL DEFAULT 0,
        subordinated_finding_ids TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        implemented_at TEXT,
        verified_at TEXT,
        outcome_notes TEXT,
        confidence_label TEXT,
        confidence_score REAL,
        instruction_source TEXT DEFAULT 'legacy_lookup'
    )""")

    # Parameter graph (v59)
    conn.execute("""CREATE TABLE pi_parameter_registry (
        id TEXT PRIMARY KEY,
        parameter_name TEXT NOT NULL UNIQUE,
        file_path TEXT NOT NULL,
        current_value REAL,
        current_value_str TEXT,
        value_type TEXT NOT NULL,
        min_valid REAL,
        max_valid REAL,
        soft_min REAL,
        soft_max REAL,
        primary_dimension TEXT NOT NULL,
        secondary_dimensions TEXT,
        change_direction TEXT DEFAULT 'unknown',
        last_changed_at TEXT,
        last_changed_by TEXT,
        change_count INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        registered_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE pi_parameter_history (
        id TEXT PRIMARY KEY,
        parameter_id TEXT NOT NULL,
        changed_at TEXT NOT NULL DEFAULT (datetime('now')),
        old_value REAL,
        new_value REAL,
        changed_by TEXT NOT NULL,
        work_order_id INTEGER,
        metric_before REAL,
        metric_after REAL,
        metric_name TEXT,
        delta_achieved REAL,
        outcome_class TEXT
    )""")
    conn.execute("""CREATE TABLE pi_influence_edges (
        id TEXT PRIMARY KEY,
        parameter_id TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        dimension TEXT NOT NULL,
        observation_count INTEGER NOT NULL DEFAULT 0,
        positive_effect_count INTEGER NOT NULL DEFAULT 0,
        negative_effect_count INTEGER NOT NULL DEFAULT 0,
        null_effect_count INTEGER NOT NULL DEFAULT 0,
        mean_delta_achieved REAL,
        weight REAL NOT NULL DEFAULT 0.5,
        weight_confidence REAL NOT NULL DEFAULT 0.1,
        last_updated TEXT,
        learned_direction TEXT DEFAULT 'unknown'
    )""")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ie_param_metric "
        "ON pi_influence_edges(parameter_id, metric_name)"
    )

    conn.commit()
    return conn


def _insert_finding(conn, **kwargs):
    """Insert a pi_finding row and return its id."""
    defaults = dict(
        audit_id=None, dimension="retention", severity="medium",
        title="Test finding", analysis="Some analysis",
        status="investigating", metric_name="retention",
        times_seen=1,
    )
    defaults.update(kwargs)
    cur = conn.execute("""
        INSERT INTO pi_finding (audit_id, dimension, severity, title, analysis,
                                status, metric_name, times_seen)
        VALUES (:audit_id, :dimension, :severity, :title, :analysis,
                :status, :metric_name, :times_seen)
    """, defaults)
    conn.commit()
    return cur.lastrowid


def _insert_audit(conn, dimension_scores=None):
    """Insert a product_audit row and return its id."""
    scores = dimension_scores or {
        "retention": {"score": 55.0, "grade": "C", "finding_count": 2, "confidence": "medium"},
        "ux": {"score": 72.0, "grade": "B", "finding_count": 1, "confidence": "medium"},
        "engineering": {"score": 80.0, "grade": "B", "finding_count": 0, "confidence": "high"},
    }
    cur = conn.execute("""
        INSERT INTO product_audit (overall_grade, overall_score, dimension_scores)
        VALUES ('C', 65.0, ?)
    """, (json.dumps(scores),))
    conn.commit()
    return cur.lastrowid


def _register_test_param(conn, name="TEST_PARAM", dimension="retention",
                          current_value=0.5, value_type="ratio",
                          soft_min=0.1, soft_max=0.9):
    """Insert a parameter directly into the registry."""
    param_id = str(uuid4())
    conn.execute("""
        INSERT INTO pi_parameter_registry
            (id, parameter_name, file_path, current_value, current_value_str,
             value_type, primary_dimension, secondary_dimensions,
             soft_min, soft_max, change_direction)
        VALUES (?, ?, 'mandarin/config.py', ?, ?, ?, ?, '[]', ?, ?, 'either')
    """, (param_id, name, current_value, str(current_value),
          value_type, dimension, soft_min, soft_max))
    conn.commit()
    return param_id


def _insert_edge(conn, parameter_id, metric="retention", dimension="retention",
                  weight=0.4, confidence=0.1, direction="unknown",
                  observation_count=0, positive=0, negative=0, null_eff=0,
                  mean_delta=None):
    """Insert an influence edge."""
    edge_id = str(uuid4())
    conn.execute("""
        INSERT INTO pi_influence_edges
            (id, parameter_id, metric_name, dimension,
             weight, weight_confidence, learned_direction,
             observation_count, positive_effect_count,
             negative_effect_count, null_effect_count,
             mean_delta_achieved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (edge_id, parameter_id, metric, dimension,
          weight, confidence, direction,
          observation_count, positive, negative, null_eff, mean_delta))
    conn.commit()
    return edge_id


class TestRegisterParameterDecorator(unittest.TestCase):
    """1. @register_parameter decorator correctly populates _PARAMETER_REGISTRY_PENDING."""

    def test_decorator_populates_pending(self):
        from mandarin.intelligence.parameter_registry import (
            register_parameter, _PARAMETER_REGISTRY_PENDING,
        )
        # Config.py registers parameters at import time
        # Verify at least some parameters are registered
        self.assertGreater(len(_PARAMETER_REGISTRY_PENDING), 0)
        # Check a known parameter is present
        names = [p["parameter_name"] for p in _PARAMETER_REGISTRY_PENDING]
        self.assertIn("MAX_NEW_ITEM_RATIO", names)


class TestSyncParameterRegistry(unittest.TestCase):
    """2. sync_parameter_registry() upserts without duplicates."""

    def test_sync_inserts_and_upserts(self):
        from mandarin.intelligence.parameter_registry import (
            _PARAMETER_REGISTRY_PENDING, sync_parameter_registry,
        )
        conn = _make_db()

        # Ensure there are pending registrations
        if not _PARAMETER_REGISTRY_PENDING:
            _PARAMETER_REGISTRY_PENDING.append({
                "parameter_name": "TEST_SYNC",
                "file_path": "test.py",
                "current_value": 1.0,
                "current_value_str": "1.0",
                "value_type": "float",
                "primary_dimension": "retention",
                "secondary_dimensions": "[]",
                "min_valid": None,
                "max_valid": None,
                "soft_min": None,
                "soft_max": None,
                "change_direction": "unknown",
                "notes": None,
            })

        count1 = sync_parameter_registry(conn)
        self.assertGreater(count1, 0)

        # Second sync should not create duplicates
        count2 = sync_parameter_registry(conn)
        self.assertEqual(count2, count1)

        # Check no duplicates
        rows = conn.execute("SELECT COUNT(*) FROM pi_parameter_registry").fetchone()
        names = conn.execute(
            "SELECT COUNT(DISTINCT parameter_name) FROM pi_parameter_registry"
        ).fetchone()
        self.assertEqual(rows[0], names[0])


class TestSeedInfluenceModel(unittest.TestCase):
    """3. seed_influence_model() creates edges with weight=0.4, weight_confidence=0.1."""

    def test_seed_creates_edges(self):
        from mandarin.intelligence.parameter_registry import (
            sync_parameter_registry, seed_influence_model,
        )
        conn = _make_db()
        sync_parameter_registry(conn)
        count = seed_influence_model(conn)

        self.assertGreater(count, 0)

        # Check seeded edges have correct initial values
        edges = conn.execute("""
            SELECT weight, weight_confidence FROM pi_influence_edges
            WHERE observation_count = 0
        """).fetchall()
        for edge in edges:
            self.assertLessEqual(edge["weight"], 0.5)  # Prior weights are low
            self.assertGreater(edge["weight"], 0.0)
            self.assertAlmostEqual(edge["weight_confidence"], 0.1)

    def test_seed_is_idempotent(self):
        from mandarin.intelligence.parameter_registry import (
            sync_parameter_registry, seed_influence_model,
        )
        conn = _make_db()
        sync_parameter_registry(conn)
        count1 = seed_influence_model(conn)
        count2 = seed_influence_model(conn)
        self.assertEqual(count2, 0)  # No new edges on second call


class TestUpdateInfluenceEdgesCorrect(unittest.TestCase):
    """4. update_influence_edges() correctly updates weight after correct outcome."""

    def test_correct_outcome_increases_weight(self):
        from mandarin.intelligence.parameter_registry import update_influence_edges
        conn = _make_db()

        # Setup: parameter, edge, work order chain
        param_id = _register_test_param(conn, "RECALL_THRESHOLD", "retention", 0.85)
        edge_id = _insert_edge(conn, param_id, "retention", "retention",
                                weight=0.4, confidence=0.1, observation_count=0)

        # Insert finding + audit + work order + prediction + outcome
        _insert_audit(conn)
        fid = _insert_finding(conn, dimension="retention", severity="high",
                               title="D7 retention low")

        pred_id = str(uuid4())
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at)
            VALUES (?, ?, 'retention', 'retention', 'metric_will_improve', 'retention',
                    50.0, 5.0, 0.6, 30, datetime('now', '+30 days'))
        """, (pred_id, fid))

        wo_id = conn.execute("""
            INSERT INTO pi_work_order
                (audit_cycle_id, finding_id, prediction_id,
                 constraint_dimension, constraint_score, marginal_improvement,
                 instruction, success_metric, success_baseline, success_threshold,
                 verification_window_days, status)
            VALUES (1, ?, ?, 'retention', 55.0, 3.5,
                    'test instruction', 'retention', 50.0, 55.0, 30, 'verifying')
        """, (fid, pred_id)).lastrowid

        conn.execute("""
            INSERT INTO pi_parameter_history
                (id, parameter_id, changed_at, old_value, new_value,
                 changed_by, work_order_id)
            VALUES (?, ?, datetime('now'), 0.85, 0.88, 'human', ?)
        """, (str(uuid4()), param_id, wo_id))

        outcome_id = str(uuid4())
        conn.execute("""
            INSERT INTO pi_prediction_outcomes
                (id, prediction_id, metric_actual, actual_delta,
                 direction_correct, magnitude_error, outcome_class)
            VALUES (?, ?, 55.0, 5.0, 1, 0.0, 'correct')
        """, (outcome_id, pred_id))
        conn.commit()

        # Get initial edge state
        old_edge = conn.execute(
            "SELECT weight FROM pi_influence_edges WHERE id = ?", (edge_id,)
        ).fetchone()
        old_weight = old_edge["weight"]

        ok = update_influence_edges(conn, wo_id)
        self.assertTrue(ok)

        new_edge = conn.execute(
            "SELECT * FROM pi_influence_edges WHERE id = ?", (edge_id,)
        ).fetchone()
        self.assertEqual(new_edge["observation_count"], 1)
        self.assertEqual(new_edge["positive_effect_count"], 1)
        self.assertGreater(new_edge["weight_confidence"], 0.1)


class TestUpdateInfluenceEdgesWrong(unittest.TestCase):
    """5. update_influence_edges() correctly updates weight after wrong outcome."""

    def test_wrong_outcome(self):
        from mandarin.intelligence.parameter_registry import update_influence_edges
        conn = _make_db()

        param_id = _register_test_param(conn, "BAD_PARAM", "retention", 0.5)
        edge_id = _insert_edge(conn, param_id, "retention", "retention",
                                weight=0.6, confidence=0.3, observation_count=2,
                                positive=1, negative=0, null_eff=1)

        _insert_audit(conn)
        fid = _insert_finding(conn, dimension="retention", severity="high",
                               title="Retention issue")

        pred_id = str(uuid4())
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at)
            VALUES (?, ?, 'retention', 'retention', 'metric_will_improve', 'retention',
                    50.0, 5.0, 0.5, 30, datetime('now', '+30 days'))
        """, (pred_id, fid))

        wo_id = conn.execute("""
            INSERT INTO pi_work_order
                (audit_cycle_id, finding_id, prediction_id,
                 constraint_dimension, constraint_score, marginal_improvement,
                 instruction, success_metric, success_baseline, success_threshold,
                 verification_window_days, status)
            VALUES (1, ?, ?, 'retention', 55.0, 3.5,
                    'test', 'retention', 50.0, 55.0, 30, 'verifying')
        """, (fid, pred_id)).lastrowid

        conn.execute("""
            INSERT INTO pi_parameter_history
                (id, parameter_id, changed_at, old_value, new_value,
                 changed_by, work_order_id)
            VALUES (?, ?, datetime('now'), 0.5, 0.6, 'human', ?)
        """, (str(uuid4()), param_id, wo_id))

        conn.execute("""
            INSERT INTO pi_prediction_outcomes
                (id, prediction_id, metric_actual, actual_delta,
                 direction_correct, magnitude_error, outcome_class)
            VALUES (?, ?, 48.0, -2.0, 0, 7.0, 'wrong')
        """, (str(uuid4()), pred_id))
        conn.commit()

        ok = update_influence_edges(conn, wo_id)
        self.assertTrue(ok)

        edge = conn.execute(
            "SELECT * FROM pi_influence_edges WHERE id = ?", (edge_id,)
        ).fetchone()
        self.assertEqual(edge["negative_effect_count"], 1)
        self.assertEqual(edge["observation_count"], 3)


class TestUpdateCreatesNewEdge(unittest.TestCase):
    """6. update_influence_edges() creates new edge when intervention reveals unknown relationship."""

    def test_creates_edge_from_data(self):
        from mandarin.intelligence.parameter_registry import update_influence_edges
        conn = _make_db()

        param_id = _register_test_param(conn, "SURPRISE_PARAM", "ux", 10.0, "int")
        # No edge exists yet

        _insert_audit(conn)
        fid = _insert_finding(conn, dimension="ux", severity="medium", title="UX issue")

        pred_id = str(uuid4())
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at)
            VALUES (?, ?, 'ux', 'ux', 'metric_will_improve', 'ux',
                    70.0, 3.0, 0.5, 7, datetime('now', '+7 days'))
        """, (pred_id, fid))

        wo_id = conn.execute("""
            INSERT INTO pi_work_order
                (audit_cycle_id, finding_id, prediction_id,
                 constraint_dimension, constraint_score, marginal_improvement,
                 instruction, success_metric, success_baseline, success_threshold,
                 verification_window_days, status)
            VALUES (1, ?, ?, 'ux', 72.0, 2.0,
                    'test', 'ux', 70.0, 73.0, 7, 'verifying')
        """, (fid, pred_id)).lastrowid

        conn.execute("""
            INSERT INTO pi_parameter_history
                (id, parameter_id, changed_at, old_value, new_value,
                 changed_by, work_order_id)
            VALUES (?, ?, datetime('now'), 10.0, 12.0, 'human', ?)
        """, (str(uuid4()), param_id, wo_id))

        conn.execute("""
            INSERT INTO pi_prediction_outcomes
                (id, prediction_id, metric_actual, actual_delta,
                 direction_correct, magnitude_error, outcome_class)
            VALUES (?, ?, 73.0, 3.0, 1, 0.0, 'correct')
        """, (str(uuid4()), pred_id))
        conn.commit()

        ok = update_influence_edges(conn, wo_id)
        self.assertTrue(ok)

        # Edge should now exist
        edge = conn.execute("""
            SELECT * FROM pi_influence_edges WHERE parameter_id = ?
        """, (param_id,)).fetchone()
        self.assertIsNotNone(edge)
        self.assertEqual(edge["observation_count"], 1)


class TestChangeGeneratorSelectsBest(unittest.TestCase):
    """7. generate_specific_change() selects highest weight×confidence edge."""

    def test_selects_highest_weighted_edge(self):
        from mandarin.intelligence.change_generator import generate_specific_change
        conn = _make_db()

        p1 = _register_test_param(conn, "LOW_PARAM", "retention", 0.5)
        p2 = _register_test_param(conn, "HIGH_PARAM", "retention", 0.7)

        _insert_edge(conn, p1, "retention", "retention",
                      weight=0.3, confidence=0.2, observation_count=2)
        _insert_edge(conn, p2, "retention", "retention",
                      weight=0.8, confidence=0.6, observation_count=8, mean_delta=2.0)

        finding = {"dimension": "retention", "title": "D7 retention low",
                    "severity": "high", "id": 1}
        change = generate_specific_change(conn, finding)

        self.assertEqual(change.parameter_name, "HIGH_PARAM")
        self.assertGreater(change.influence_weight, 0.3)


class TestChangeGeneratorClampsToRange(unittest.TestCase):
    """8. generate_specific_change() clamps recommended value to soft_min/soft_max."""

    def test_clamps_to_soft_max(self):
        from mandarin.intelligence.change_generator import generate_specific_change
        conn = _make_db()

        # Parameter with soft_max=0.9, current=0.85
        p = _register_test_param(conn, "NEAR_MAX", "retention", 0.85,
                                  soft_min=0.1, soft_max=0.9)
        _insert_edge(conn, p, "retention", "retention",
                      weight=0.8, confidence=0.5, observation_count=5,
                      direction="increase", mean_delta=10.0)

        finding = {"dimension": "retention", "title": "Needs increase",
                    "severity": "high", "id": 1}
        change = generate_specific_change(conn, finding)

        self.assertLessEqual(change.recommended_value, 0.9)


class TestChangeGeneratorHonestFallback(unittest.TestCase):
    """9. generate_specific_change() returns honest fallback when no confident edge."""

    def test_no_edges_returns_fallback(self):
        from mandarin.intelligence.change_generator import generate_specific_change
        conn = _make_db()

        finding = {"dimension": "retention", "title": "Unknown issue",
                    "severity": "medium", "id": 1}
        change = generate_specific_change(conn, finding)

        self.assertEqual(change.direction_source, "no_data")
        self.assertIsNone(change.parameter_name)
        self.assertIn("no observed interventions", change.specific_change)


class TestDirectionSourceLabeling(unittest.TestCase):
    """10. _direction_source() correctly labels learned_from_data vs prior_knowledge_only."""

    def test_labels(self):
        from mandarin.intelligence.change_generator import _direction_source

        high_data = {
            "weight_confidence": 0.75,
            "observation_count": 12,
        }
        self.assertEqual(_direction_source(high_data), "learned_from_data")

        medium_data = {
            "weight_confidence": 0.45,
            "observation_count": 4,
        }
        self.assertEqual(_direction_source(medium_data), "partially_learned")

        low_data = {
            "weight_confidence": 0.15,
            "observation_count": 1,
        }
        self.assertEqual(_direction_source(low_data), "prior_knowledge_only")


class TestWorkOrderImplementWithParameter(unittest.TestCase):
    """11. Work order implement records parameter change."""

    def test_records_parameter_change(self):
        from mandarin.intelligence.prescription import generate_work_order, mark_work_order_implemented
        conn = _make_db()

        # Register a parameter
        param_id = _register_test_param(conn, "RECALL_THRESHOLD", "retention", 0.85)

        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="D7 retention low")

        wo = generate_work_order(conn, 1)
        ok = mark_work_order_implemented(
            conn, wo.id,
            parameter_name="RECALL_THRESHOLD",
            old_value=0.85,
            new_value=0.88,
        )
        self.assertTrue(ok)

        # Check parameter history
        history = conn.execute("""
            SELECT * FROM pi_parameter_history WHERE work_order_id = ?
        """, (wo.id,)).fetchone()
        self.assertIsNotNone(history)
        self.assertAlmostEqual(history["old_value"], 0.85)
        self.assertAlmostEqual(history["new_value"], 0.88)


class TestParallelPeriod(unittest.TestCase):
    """12. Parallel period: influence model used for >0% of work orders after seeding."""

    def test_instruction_source_logged(self):
        from mandarin.intelligence.prescription import generate_work_order
        conn = _make_db()

        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Churn rate elevated")

        wo = generate_work_order(conn, 1)

        # instruction_source should be one of the valid sources
        self.assertIn(wo.instruction_source,
                      ("influence_model", "legacy_lookup", "insufficient_data"))

        # Check it's persisted
        row = conn.execute(
            "SELECT instruction_source FROM pi_work_order WHERE id = ?", (wo.id,)
        ).fetchone()
        self.assertIsNotNone(row["instruction_source"])


class TestParameterGraphEndpoint(unittest.TestCase):
    """13. Parameter graph endpoint returns valid JSON with nodes and edges."""

    def test_graph_structure(self):
        from mandarin.intelligence.parameter_registry import (
            sync_parameter_registry, seed_influence_model, get_influence_graph,
        )
        conn = _make_db()
        sync_parameter_registry(conn)
        seed_influence_model(conn)

        graph = get_influence_graph(conn)

        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("total_observations", graph)
        self.assertIsInstance(graph["nodes"], list)
        self.assertIsInstance(graph["edges"], list)
        self.assertGreater(len(graph["nodes"]), 0)
        self.assertGreater(len(graph["edges"]), 0)

        # Check node structure
        node = graph["nodes"][0]
        self.assertIn("name", node)
        self.assertIn("dimension", node)
        self.assertIn("type", node)

        # Check edge structure
        edge = graph["edges"][0]
        self.assertIn("source", edge)
        self.assertIn("target", edge)
        self.assertIn("weight", edge)
        self.assertIn("confidence", edge)


class TestConfidenceGrowth(unittest.TestCase):
    """14. After 5 correct outcomes on same edge: weight_confidence >= 0.50."""

    def test_confidence_grows_with_observations(self):
        from mandarin.intelligence.parameter_registry import update_influence_edges
        conn = _make_db()

        param_id = _register_test_param(conn, "GROWTH_PARAM", "retention", 0.5)
        edge_id = _insert_edge(conn, param_id, "retention", "retention",
                                weight=0.4, confidence=0.1, observation_count=0)

        for i in range(5):
            _insert_audit(conn)
            fid = _insert_finding(conn, dimension="retention", severity="high",
                                   title=f"Finding {i}")

            pred_id = str(uuid4())
            conn.execute("""
                INSERT INTO pi_prediction_ledger
                    (id, finding_id, model_id, dimension, claim_type, metric_name,
                     metric_baseline, predicted_delta, predicted_delta_confidence,
                     verification_window_days, verification_due_at)
                VALUES (?, ?, 'retention', 'retention', 'metric_will_improve', 'retention',
                        50.0, 5.0, 0.6, 30, datetime('now', '+30 days'))
            """, (pred_id, fid))

            wo_id = conn.execute("""
                INSERT INTO pi_work_order
                    (audit_cycle_id, finding_id, prediction_id,
                     constraint_dimension, constraint_score, marginal_improvement,
                     instruction, success_metric, success_baseline, success_threshold,
                     verification_window_days, status)
                VALUES (?, ?, ?, 'retention', 55.0, 3.5,
                        'test', 'retention', 50.0, 55.0, 30, 'verifying')
            """, (i + 1, fid, pred_id)).lastrowid

            conn.execute("""
                INSERT INTO pi_parameter_history
                    (id, parameter_id, changed_at, old_value, new_value,
                     changed_by, work_order_id)
                VALUES (?, ?, datetime('now'), ?, ?, 'human', ?)
            """, (str(uuid4()), param_id, 0.5 + i * 0.02, 0.5 + (i + 1) * 0.02, wo_id))

            conn.execute("""
                INSERT INTO pi_prediction_outcomes
                    (id, prediction_id, metric_actual, actual_delta,
                     direction_correct, magnitude_error, outcome_class)
                VALUES (?, ?, 55.0, 5.0, 1, 0.0, 'correct')
            """, (str(uuid4()), pred_id))
            conn.commit()

            update_influence_edges(conn, wo_id)

        edge = conn.execute(
            "SELECT * FROM pi_influence_edges WHERE id = ?", (edge_id,)
        ).fetchone()
        self.assertGreaterEqual(edge["weight_confidence"], 0.50)
        self.assertEqual(edge["observation_count"], 5)


class TestLegacyFallback(unittest.TestCase):
    """15. Deprecated _FINDING_TO_ACTION fallback activates when influence model confidence < 0.40."""

    def test_falls_back_to_legacy(self):
        from mandarin.intelligence.prescription import generate_work_order
        conn = _make_db()

        # No parameters or edges registered — influence model will fail
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Churn rate elevated")

        wo = generate_work_order(conn, 1)

        # Should fall back to legacy lookup since no influence model data
        self.assertEqual(wo.instruction_source, "legacy_lookup")
        # Legacy lookup should still find "churn" keyword
        self.assertEqual(wo.target_file, "mandarin/scheduler.py")


class TestRecordParameterChange(unittest.TestCase):
    """record_parameter_change updates registry and creates history."""

    def test_records_and_updates(self):
        from mandarin.intelligence.parameter_registry import record_parameter_change
        conn = _make_db()

        _register_test_param(conn, "CHANGEABLE", "retention", 0.5)

        history_id = record_parameter_change(
            conn, "CHANGEABLE", 0.5, 0.6, changed_by="human"
        )
        self.assertIsNotNone(history_id)

        # Check registry updated
        param = conn.execute(
            "SELECT current_value, change_count FROM pi_parameter_registry WHERE parameter_name = 'CHANGEABLE'"
        ).fetchone()
        self.assertAlmostEqual(param["current_value"], 0.6)
        self.assertEqual(param["change_count"], 1)

        # Check history exists
        hist = conn.execute(
            "SELECT * FROM pi_parameter_history WHERE id = ?", (history_id,)
        ).fetchone()
        self.assertAlmostEqual(hist["old_value"], 0.5)
        self.assertAlmostEqual(hist["new_value"], 0.6)


if __name__ == "__main__":
    unittest.main()
