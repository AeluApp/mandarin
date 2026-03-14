"""Tests for Intelligence Engine Collaborator Model (Phase 5).

Covers: interaction logging, model building, timing/override/presentation patterns,
adaptive presentation, domain trust calibration, corrections, kill switch,
and the three non-negotiable invariants:
  1. Content/presentation separation
  2. Adaptations always visible
  3. Corrections permanently logged
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
    conn.execute("""CREATE TABLE pi_decision_log (
        id INTEGER PRIMARY KEY, finding_id INTEGER,
        decision_class TEXT, escalation_level TEXT,
        presented_to TEXT, decision TEXT, decision_reason TEXT,
        override_expires_at TEXT, outcome_notes TEXT,
        requires_approval INTEGER DEFAULT 0, approved_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
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

    # Collaborator Model (v60)
    conn.execute("""CREATE TABLE pi_interaction_log (
        id TEXT PRIMARY KEY,
        occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
        interaction_type TEXT NOT NULL CHECK (interaction_type IN (
            'work_order_viewed',
            'work_order_implemented',
            'work_order_delayed',
            'work_order_overridden',
            'finding_approved',
            'finding_dismissed',
            'subordination_overridden',
            'self_audit_viewed',
            'parameter_graph_viewed',
            'override_reason_provided',
            'correction'
        )),
        work_order_id INTEGER REFERENCES pi_work_order(id),
        finding_id INTEGER,
        dimension TEXT,
        day_of_week INTEGER,
        hour_of_day INTEGER,
        days_since_work_order_issued INTEGER,
        model_confidence_at_time REAL,
        severity_at_time TEXT,
        was_constraint_dimension INTEGER,
        subsequent_outcome_class TEXT,
        notes TEXT
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_il_type ON pi_interaction_log(interaction_type)"
    )

    conn.execute("""CREATE TABLE pi_collaborator_model (
        id TEXT PRIMARY KEY DEFAULT 'singleton',
        generated_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_updated TEXT NOT NULL DEFAULT (datetime('now')),
        observation_count INTEGER NOT NULL DEFAULT 0,
        median_implementation_days REAL,
        fastest_dimension TEXT,
        slowest_dimension TEXT,
        preferred_day_of_week INTEGER,
        preferred_hour_of_day INTEGER,
        timing_confidence REAL DEFAULT 0.1,
        override_rate_overall REAL,
        override_accuracy_overall REAL,
        domains_where_human_leads TEXT,
        domains_where_engine_leads TEXT,
        override_confidence REAL DEFAULT 0.1,
        reads_self_audit INTEGER DEFAULT 0,
        reads_parameter_graph INTEGER DEFAULT 0,
        provides_override_reasons INTEGER DEFAULT 0,
        responds_to_specific_parameters INTEGER DEFAULT 0,
        responds_to_rationale INTEGER DEFAULT 0,
        responds_to_confidence_labels INTEGER DEFAULT 0,
        presentation_confidence REAL DEFAULT 0.1,
        data_quality TEXT DEFAULT 'insufficient',
        model_notes TEXT,
        adaptations_disabled INTEGER DEFAULT 0
    )""")

    conn.execute("""CREATE TABLE pi_collaborator_model_history (
        id TEXT PRIMARY KEY,
        snapshot_at TEXT NOT NULL DEFAULT (datetime('now')),
        model_json TEXT NOT NULL,
        observation_count_at_snapshot INTEGER,
        significant_change TEXT
    )""")

    conn.execute("""CREATE TABLE pi_domain_trust (
        dimension TEXT PRIMARY KEY,
        engine_confidence REAL NOT NULL DEFAULT 0.5,
        engine_scored_predictions INTEGER NOT NULL DEFAULT 0,
        human_override_count INTEGER NOT NULL DEFAULT 0,
        human_correct_count INTEGER NOT NULL DEFAULT 0,
        human_wrong_count INTEGER NOT NULL DEFAULT 0,
        human_confidence REAL NOT NULL DEFAULT 0.5,
        trust_leader TEXT CHECK (
            trust_leader IN ('engine', 'human', 'tied', 'insufficient_data')
        ) DEFAULT 'insufficient_data',
        trust_margin REAL,
        override_requires_reason INTEGER NOT NULL DEFAULT 0,
        escalation_persistence TEXT NOT NULL DEFAULT 'normal'
            CHECK (escalation_persistence IN ('low', 'normal', 'high')),
        last_updated TEXT
    )""")

    conn.commit()
    return conn


def _insert_work_order(conn, **kwargs):
    """Insert a pi_work_order row and return its id."""
    defaults = dict(
        audit_cycle_id=1, finding_id=1, constraint_dimension="retention",
        constraint_score=55.0, marginal_improvement=8.5,
        instruction="Do the thing", success_metric="retention",
        success_baseline=55.0, success_threshold=60.0,
        verification_window_days=14, status="pending",
        target_parameter=None,
    )
    defaults.update(kwargs)
    cur = conn.execute("""
        INSERT INTO pi_work_order
            (audit_cycle_id, finding_id, constraint_dimension, constraint_score,
             marginal_improvement, instruction, success_metric, success_baseline,
             success_threshold, verification_window_days, status, target_parameter)
        VALUES (:audit_cycle_id, :finding_id, :constraint_dimension, :constraint_score,
                :marginal_improvement, :instruction, :success_metric, :success_baseline,
                :success_threshold, :verification_window_days, :status, :target_parameter)
    """, defaults)
    conn.commit()
    return cur.lastrowid


def _log_interactions(conn, n, interaction_type="work_order_implemented",
                      dimension=None, days_since=None, work_order_id=None,
                      day_of_week=None, hour_of_day=None,
                      subsequent_outcome_class=None):
    """Insert n interaction log entries."""
    for _ in range(n):
        conn.execute("""
            INSERT INTO pi_interaction_log
                (id, interaction_type, dimension, days_since_work_order_issued,
                 work_order_id, day_of_week, hour_of_day, subsequent_outcome_class)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid4()), interaction_type, dimension, days_since,
            work_order_id, day_of_week, hour_of_day, subsequent_outcome_class,
        ))
    conn.commit()


# ── Test: Interaction Logging ────────────────────────────────────────────────

class TestInteractionLogging(unittest.TestCase):
    def test_log_interaction_basic(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import log_interaction
        log_interaction(conn, "work_order_viewed", dimension="retention")
        row = conn.execute("SELECT * FROM pi_interaction_log").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["interaction_type"], "work_order_viewed")
        self.assertEqual(row["dimension"], "retention")
        self.assertIsNotNone(row["day_of_week"])
        self.assertIsNotNone(row["hour_of_day"])

    def test_log_interaction_with_work_order(self):
        conn = _make_db()
        wo_id = _insert_work_order(conn)
        from mandarin.intelligence.collaborator import log_interaction
        log_interaction(conn, "work_order_implemented", work_order_id=wo_id)
        row = conn.execute("SELECT * FROM pi_interaction_log").fetchone()
        self.assertEqual(row["work_order_id"], wo_id)
        # days_since_work_order_issued should be 0 (just created)
        self.assertIsNotNone(row["days_since_work_order_issued"])


# ── Test: Model Building — Insufficient Data ────────────────────────────────

class TestModelBuildInsufficient(unittest.TestCase):
    def test_insufficient_data(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        self.assertEqual(model["data_quality"], "insufficient")
        self.assertIn("at least 10", model["model_notes"])

    def test_insufficient_with_few_interactions(self):
        conn = _make_db()
        _log_interactions(conn, 5, "work_order_viewed")
        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        self.assertEqual(model["data_quality"], "insufficient")


# ── Test: Model Building — With Data ─────────────────────────────────────────

class TestModelBuildWithData(unittest.TestCase):
    def test_thin_data_quality(self):
        conn = _make_db()
        _log_interactions(conn, 15, "work_order_implemented",
                          dimension="retention", days_since=3,
                          day_of_week=2, hour_of_day=14)
        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        self.assertEqual(model["data_quality"], "thin")
        self.assertIsNotNone(model.get("median_implementation_days"))

    def test_adequate_data_quality(self):
        conn = _make_db()
        _log_interactions(conn, 30, "work_order_implemented",
                          dimension="retention", days_since=2,
                          day_of_week=0, hour_of_day=10)
        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        self.assertEqual(model["data_quality"], "adequate")


# ── Test: Timing Patterns ────────────────────────────────────────────────────

class TestTimingPatterns(unittest.TestCase):
    def test_timing_patterns_computed(self):
        conn = _make_db()
        # 5+ implemented interactions with timing data
        _log_interactions(conn, 6, "work_order_implemented",
                          dimension="retention", days_since=2,
                          day_of_week=3, hour_of_day=15)
        # Add more total interactions to pass 10 threshold
        _log_interactions(conn, 5, "work_order_viewed")

        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        self.assertEqual(model["median_implementation_days"], 2)
        self.assertEqual(model["preferred_day_of_week"], 3)
        self.assertEqual(model["preferred_hour_of_day"], 15)

    def test_fastest_slowest_dimension(self):
        conn = _make_db()
        # Fast dimension: retention (1 day)
        _log_interactions(conn, 5, "work_order_implemented",
                          dimension="retention", days_since=1, day_of_week=0)
        # Slow dimension: engineering (7 days)
        _log_interactions(conn, 5, "work_order_implemented",
                          dimension="engineering", days_since=7, day_of_week=1)
        # Filler to hit 10
        _log_interactions(conn, 2, "work_order_viewed")

        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        # Need 3+ per dimension for dim_medians, we have 5 each
        self.assertEqual(model["fastest_dimension"], "retention")
        self.assertEqual(model["slowest_dimension"], "engineering")


# ── Test: Override Patterns ──────────────────────────────────────────────────

class TestOverridePatterns(unittest.TestCase):
    def test_override_rate(self):
        conn = _make_db()
        _log_interactions(conn, 8, "work_order_implemented")
        _log_interactions(conn, 2, "work_order_overridden")
        # Need 10 total
        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        # 2 overridden / 10 total = 0.2
        self.assertAlmostEqual(model["override_rate_overall"], 0.2, places=2)


# ── Test: Model Persistence ──────────────────────────────────────────────────

class TestModelPersistence(unittest.TestCase):
    def test_model_saved_to_db(self):
        conn = _make_db()
        _log_interactions(conn, 12, "work_order_implemented",
                          dimension="retention", days_since=3)
        from mandarin.intelligence.collaborator import rebuild_collaborator_model, get_collaborator_model
        rebuild_collaborator_model(conn)
        model = get_collaborator_model(conn)
        self.assertEqual(model["observation_count"], 12)
        self.assertEqual(model["data_quality"], "thin")

    def test_model_history_snapshot(self):
        conn = _make_db()
        _log_interactions(conn, 12, "work_order_implemented",
                          dimension="retention", days_since=3)
        from mandarin.intelligence.collaborator import rebuild_collaborator_model, get_collaborator_model_history
        rebuild_collaborator_model(conn)
        history = get_collaborator_model_history(conn)
        self.assertEqual(len(history), 1)
        self.assertIn("Initial model build", history[0]["significant_change"])

    def test_second_rebuild_records_changes(self):
        conn = _make_db()
        _log_interactions(conn, 12, "work_order_implemented",
                          dimension="retention", days_since=3)
        from mandarin.intelligence.collaborator import rebuild_collaborator_model, get_collaborator_model_history
        rebuild_collaborator_model(conn)
        # Add more data and rebuild
        _log_interactions(conn, 10, "work_order_implemented",
                          dimension="retention", days_since=5)
        rebuild_collaborator_model(conn)
        history = get_collaborator_model_history(conn)
        self.assertEqual(len(history), 2)
        # Both snapshots should have change descriptions
        self.assertIsNotNone(history[0]["significant_change"])
        self.assertIsNotNone(history[1]["significant_change"])


# ── Test: Adaptive Presentation ──────────────────────────────────────────────

class TestAdaptivePresentation(unittest.TestCase):
    def test_neutral_presentation_by_default(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import build_adaptive_presentation
        wo = {"id": 1, "constraint_dimension": "retention", "instruction": "Do X"}
        result = build_adaptive_presentation(conn, wo)
        self.assertEqual(result["lead_element"], "instruction")
        self.assertTrue(result["rationale_collapsed"])
        self.assertEqual(result["adaptations"], [])

    def test_disabled_returns_no_adaptations(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import disable_all_adaptations, build_adaptive_presentation
        disable_all_adaptations(conn)
        wo = {"id": 1, "constraint_dimension": "retention"}
        result = build_adaptive_presentation(conn, wo)
        self.assertTrue(result["adaptations_disabled"])
        self.assertEqual(result["adaptations"], [])

    def test_adaptations_always_labeled(self):
        """INVARIANT 2: Every adaptation must have id, what, why, confidence."""
        conn = _make_db()
        # Set up model that would trigger adaptations
        conn.execute("""
            INSERT INTO pi_collaborator_model
                (id, generated_at, last_updated, observation_count,
                 responds_to_specific_parameters, presentation_confidence,
                 data_quality)
            VALUES ('singleton', datetime('now'), datetime('now'), 50,
                    1, 0.80, 'good')
        """)
        conn.commit()

        from mandarin.intelligence.collaborator import build_adaptive_presentation
        wo = {"id": 1, "constraint_dimension": "retention"}
        result = build_adaptive_presentation(conn, wo)

        for adaptation in result["adaptations"]:
            self.assertIn("id", adaptation)
            self.assertIn("what", adaptation)
            self.assertIn("why", adaptation)
            self.assertIn("confidence", adaptation)


# ── Test: Domain Trust Calibration ───────────────────────────────────────────

class TestDomainTrust(unittest.TestCase):
    def test_initial_trust_creation(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import update_domain_trust
        result = update_domain_trust(conn, "retention", was_correct=True)
        self.assertEqual(result["dimension"], "retention")
        self.assertEqual(result["trust_leader"], "insufficient_data")
        # Beta-Binomial: (1+1)/(1+2) = 2/3
        self.assertAlmostEqual(result["human_confidence"], 2/3, places=3)

    def test_trust_leader_after_many_correct(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import update_domain_trust
        # 6 correct overrides: human leads
        for _ in range(6):
            result = update_domain_trust(conn, "retention", was_correct=True)
        # After 6 correct: human_conf = (6+1)/(6+2) = 0.875, engine = 0.5
        self.assertEqual(result["trust_leader"], "human")
        self.assertEqual(result["escalation_persistence"], "low")

    def test_trust_leader_after_many_wrong(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import update_domain_trust
        # 6 wrong overrides: engine leads
        for _ in range(6):
            result = update_domain_trust(conn, "retention", was_correct=False)
        # After 6 wrong: human_conf = (0+1)/(6+2) = 0.125, engine = 0.5
        self.assertEqual(result["trust_leader"], "engine")
        self.assertTrue(result["override_requires_reason"])
        self.assertEqual(result["escalation_persistence"], "high")

    def test_get_domain_trust(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import update_domain_trust, get_domain_trust
        update_domain_trust(conn, "retention", was_correct=True)
        update_domain_trust(conn, "engagement", was_correct=False)
        trust = get_domain_trust(conn)
        self.assertEqual(len(trust), 2)
        dims = {t["dimension"] for t in trust}
        self.assertIn("retention", dims)
        self.assertIn("engagement", dims)

    def test_get_trust_for_unknown_dimension(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import get_trust_for_dimension
        result = get_trust_for_dimension(conn, "unknown_dim")
        self.assertEqual(result["trust_leader"], "insufficient_data")
        self.assertEqual(result["escalation_persistence"], "normal")


# ── Test: Correction Interface ───────────────────────────────────────────────

class TestCorrectionInterface(unittest.TestCase):
    def test_correction_logged_permanently(self):
        """INVARIANT 3: Corrections are permanently logged."""
        conn = _make_db()
        from mandarin.intelligence.collaborator import record_correction
        record_correction(conn, "timing_wrong", dimension="retention",
                          notes="I never work on Mondays")
        row = conn.execute("""
            SELECT * FROM pi_interaction_log
            WHERE interaction_type = 'correction'
        """).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("timing_wrong", row["notes"])
        self.assertIn("I never work on Mondays", row["notes"])

    def test_correction_triggers_rebuild(self):
        conn = _make_db()
        _log_interactions(conn, 12, "work_order_implemented",
                          dimension="retention", days_since=3)
        from mandarin.intelligence.collaborator import record_correction, get_collaborator_model
        record_correction(conn, "override_accuracy_wrong")
        model = get_collaborator_model(conn)
        # Model should exist after correction triggers rebuild
        # 12 + 1 correction = 13
        self.assertEqual(model["observation_count"], 13)


# ── Test: Kill Switch ────────────────────────────────────────────────────────

class TestKillSwitch(unittest.TestCase):
    def test_disable_and_enable(self):
        conn = _make_db()
        from mandarin.intelligence.collaborator import (
            disable_all_adaptations, enable_adaptations, get_collaborator_model,
        )
        disable_all_adaptations(conn)
        model = get_collaborator_model(conn)
        self.assertEqual(model["adaptations_disabled"], 1)

        enable_adaptations(conn)
        model = get_collaborator_model(conn)
        self.assertEqual(model["adaptations_disabled"], 0)


# ── Test: Content/Presentation Separation (INVARIANT 1) ─────────────────────

class TestContentPresentationSeparation(unittest.TestCase):
    def test_presentation_never_changes_work_order_content(self):
        """Adaptive presentation must NOT modify instruction, metric, threshold."""
        conn = _make_db()
        wo = {
            "id": 1,
            "constraint_dimension": "retention",
            "instruction": "Lower MAX_NEW_ITEM_RATIO from 0.25 to 0.20",
            "success_metric": "retention",
            "success_threshold": 60.0,
        }

        # Set up model with all adaptations enabled
        conn.execute("""
            INSERT INTO pi_collaborator_model
                (id, generated_at, last_updated, observation_count,
                 responds_to_specific_parameters, presentation_confidence,
                 responds_to_rationale, timing_confidence,
                 preferred_day_of_week, data_quality)
            VALUES ('singleton', datetime('now'), datetime('now'), 100,
                    1, 0.90, 1, 0.80, 3, 'good')
        """)
        conn.commit()

        from mandarin.intelligence.collaborator import build_adaptive_presentation
        result = build_adaptive_presentation(conn, wo)

        # Presentation can adapt lead_element, rationale visibility, timing
        # But NEVER changes the work order content fields
        self.assertNotIn("instruction", result)
        self.assertNotIn("success_metric", result)
        self.assertNotIn("success_threshold", result)


# ── Test: Model Notes (Plain Language) ───────────────────────────────────────

class TestModelNotes(unittest.TestCase):
    def test_notes_are_readable(self):
        conn = _make_db()
        _log_interactions(conn, 6, "work_order_implemented",
                          dimension="retention", days_since=2,
                          day_of_week=1, hour_of_day=10)
        _log_interactions(conn, 5, "work_order_viewed")

        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        notes = model["model_notes"]
        # Notes should be plain language, not JSON or code
        self.assertNotIn("{", notes)
        self.assertIn("observed interactions", notes)

    def test_notes_mention_correction_count(self):
        conn = _make_db()
        _log_interactions(conn, 12, "work_order_implemented", days_since=3)
        from mandarin.intelligence.collaborator import rebuild_collaborator_model
        model = rebuild_collaborator_model(conn)
        # Notes should mention observation count
        self.assertIn("12", model["model_notes"])


# ── Test: Describe Significant Change ────────────────────────────────────────

class TestDescribeChange(unittest.TestCase):
    def test_no_change(self):
        from mandarin.intelligence.collaborator import _describe_significant_change
        old = {"data_quality": "thin", "observation_count": 20}
        new = {"data_quality": "thin", "observation_count": 20}
        result = _describe_significant_change(old, new)
        self.assertIn("No significant changes", result)

    def test_quality_change(self):
        from mandarin.intelligence.collaborator import _describe_significant_change
        old = {"data_quality": "thin", "observation_count": 20}
        new = {"data_quality": "adequate", "observation_count": 30}
        result = _describe_significant_change(old, new)
        self.assertIn("thin", result)
        self.assertIn("adequate", result)
        self.assertIn("10 new interactions", result)


if __name__ == "__main__":
    unittest.main()
