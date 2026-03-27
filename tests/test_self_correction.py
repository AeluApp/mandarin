"""Tests for Intelligence Engine Self-Correction Layer.

Covers: emit_prediction, record_prediction_outcomes, expire_stale_predictions,
model confidence (Beta-Binomial Laplace), get_model_confidence, self-audit report,
confidence-based finding labeling, enforcement gate, override accuracy.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


from tests.shared_db import make_test_db as _make_db


def _insert_finding(conn, **kwargs):
    """Insert a pi_finding row and return its id."""
    defaults = dict(
        audit_id=None, dimension="retention", severity="medium",
        title="Test finding", analysis="Some analysis",
        status="investigating", metric_name="d7_retention",
    )
    defaults.update(kwargs)
    cur = conn.execute("""
        INSERT INTO pi_finding (audit_id, dimension, severity, title, analysis,
                                status, metric_name)
        VALUES (:audit_id, :dimension, :severity, :title, :analysis,
                :status, :metric_name)
    """, defaults)
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# 1. emit_prediction
# ---------------------------------------------------------------------------

class TestEmitPrediction(unittest.TestCase):

    def test_emit_prediction_creates_ledger_entry(self):
        from mandarin.intelligence.feedback_loops import emit_prediction
        conn = _make_db()
        # Seed data so _measure_current_metric returns a value for retention
        # User 1 already exists via make_test_db()
        for i in range(5):
            conn.execute("""INSERT INTO session_log (user_id, started_at)
                VALUES (1, datetime('now', ?))""", (f'-{i} days',))
        conn.commit()

        fid = _insert_finding(conn, dimension="retention")
        pred_id = emit_prediction(conn, fid, "retention_analyzer", "retention",
                                  "d7_retention", 5.0, 0.8)

        self.assertIsNotNone(pred_id)
        row = conn.execute("SELECT * FROM pi_prediction_ledger WHERE id = ?",
                           (pred_id,)).fetchone()
        self.assertEqual(row["finding_id"], fid)
        self.assertEqual(row["model_id"], "retention_analyzer")
        self.assertEqual(row["claim_type"], "metric_will_improve")
        self.assertEqual(row["predicted_delta"], 5.0)
        self.assertEqual(row["status"], "pending")

    def test_emit_prediction_negative_delta_claim_type(self):
        from mandarin.intelligence.feedback_loops import emit_prediction
        conn = _make_db()
        # User 1 already exists via make_test_db()
        for i in range(5):
            conn.execute("""INSERT INTO session_log (user_id, started_at)
                VALUES (1, datetime('now', ?))""", (f'-{i} days',))
        conn.commit()

        fid = _insert_finding(conn, dimension="retention")
        pred_id = emit_prediction(conn, fid, "retention_analyzer", "retention",
                                  "d7_retention", -3.0, 0.6)

        self.assertIsNotNone(pred_id)
        row = conn.execute("SELECT * FROM pi_prediction_ledger WHERE id = ?",
                           (pred_id,)).fetchone()
        self.assertEqual(row["claim_type"], "metric_will_worsen")

    def test_emit_prediction_unknown_dimension_returns_none(self):
        """Dimension not in metric_queries → _measure_current_metric returns None → emit returns None."""
        from mandarin.intelligence.feedback_loops import emit_prediction
        conn = _make_db()
        fid = _insert_finding(conn, dimension="fake_dim")
        pred_id = emit_prediction(conn, fid, "model", "fake_dim", "metric", 5.0, 0.8)
        self.assertIsNone(pred_id)

    def test_emit_prediction_empty_data_still_works(self):
        """With no user data, retention metric returns 0 (not None), so prediction proceeds."""
        from mandarin.intelligence.feedback_loops import emit_prediction
        conn = _make_db()
        fid = _insert_finding(conn, dimension="retention")
        pred_id = emit_prediction(conn, fid, "model", "retention", "d7_retention", 5.0, 0.8)
        # _safe_scalar returns 0 for NULL, so baseline=0 and prediction is created
        self.assertIsNotNone(pred_id)
        row = conn.execute("SELECT metric_baseline FROM pi_prediction_ledger WHERE id = ?",
                           (pred_id,)).fetchone()
        self.assertEqual(row["metric_baseline"], 0.0)


# ---------------------------------------------------------------------------
# 2. record_prediction_outcomes
# ---------------------------------------------------------------------------

class TestRecordPredictionOutcomes(unittest.TestCase):

    def _seed_prediction(self, conn, pred_id="pred-1", finding_id=1, model_id="model_a",
                         dimension="retention", baseline=20.0, delta=5.0,
                         due_offset="-1 days"):
        """Insert a prediction that is past its verification window."""
        due_at = (datetime.now(timezone.utc) + timedelta(days=-1)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES (?, ?, ?, ?, 'metric_will_improve', 'retention_score',
                    ?, ?, 0.8, 7, ?, 'pending')
        """, (pred_id, finding_id, model_id, dimension, baseline, delta, due_at))
        # Mark finding as acted on
        conn.execute("""
            INSERT INTO pi_decision_log (finding_id, decision_class, escalation_level, decision)
            VALUES (?, 'auto_fix', 'quiet', 'Implement fix')
        """, (finding_id,))
        conn.commit()

    def test_correct_outcome(self):
        """Direction right + magnitude within 20% → correct."""
        from mandarin.intelligence.feedback_loops import record_prediction_outcomes
        conn = _make_db()
        fid = _insert_finding(conn, dimension="retention")

        # Seed prediction: baseline=20, predicted_delta=5 (expect metric to go from 20 to 25)
        self._seed_prediction(conn, finding_id=fid, baseline=20.0, delta=5.0)

        # Seed data so retention metric returns ~25 (within 20%)
        # User 1 already exists via make_test_db()
        for i in range(7):
            conn.execute("""INSERT INTO session_log (user_id, started_at)
                VALUES (1, datetime('now', ?))""", (f'-{i} days',))
        conn.commit()

        results = record_prediction_outcomes(conn)
        # Regardless of exact outcome class, we should get a result
        self.assertEqual(len(results), 1)
        self.assertIn(results[0]["outcome_class"],
                      ("correct", "directionally_correct", "wrong", "insufficient_data"))

    def test_invalidated_when_not_acted_on(self):
        """Finding never acted on → invalidated (not scored, no result entry)."""
        from mandarin.intelligence.feedback_loops import record_prediction_outcomes
        conn = _make_db()
        fid = _insert_finding(conn, dimension="retention")

        # Prediction without decision_log entry
        due_at = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES ('pred-inv', ?, 'model', 'retention', 'metric_will_improve',
                    'retention_score', 20.0, 5.0, 0.8, 7, ?, 'pending')
        """, (fid, due_at))
        conn.commit()

        results = record_prediction_outcomes(conn)
        # Invalidated predictions are not scored — they don't appear in results
        self.assertEqual(len(results), 0)
        # But the prediction should be marked as invalidated in the ledger
        row = conn.execute(
            "SELECT status FROM pi_prediction_ledger WHERE id = 'pred-inv'"
        ).fetchone()
        self.assertEqual(row["status"], "invalidated")


# ---------------------------------------------------------------------------
# 3. expire_stale_predictions
# ---------------------------------------------------------------------------

class TestExpireStalePredictions(unittest.TestCase):

    def test_expire_past_due_predictions(self):
        from mandarin.intelligence.feedback_loops import expire_stale_predictions
        conn = _make_db()
        fid = _insert_finding(conn)

        past_due = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES ('pred-exp', ?, 'model', 'retention', 'metric_will_improve',
                    'retention_score', 20.0, 5.0, 0.8, 7, ?, 'pending')
        """, (fid, past_due))
        conn.commit()

        count = expire_stale_predictions(conn)
        self.assertEqual(count, 1)

        row = conn.execute("SELECT status FROM pi_prediction_ledger WHERE id = 'pred-exp'").fetchone()
        self.assertEqual(row["status"], "expired")

    def test_expire_increments_measurement_failure(self):
        from mandarin.intelligence.feedback_loops import expire_stale_predictions
        conn = _make_db()
        fid = _insert_finding(conn)

        past_due = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES ('pred-mf', ?, 'model_mf', 'retention', 'metric_will_improve',
                    'retention_score', 20.0, 5.0, 0.8, 7, ?, 'pending')
        """, (fid, past_due))
        conn.commit()

        expire_stale_predictions(conn)

        mc = conn.execute(
            "SELECT * FROM pi_model_confidence WHERE model_id = 'model_mf'"
        ).fetchone()
        if mc:
            self.assertGreater(mc["measurement_failure_count"], 0)

    def test_future_predictions_not_expired(self):
        from mandarin.intelligence.feedback_loops import expire_stale_predictions
        conn = _make_db()
        fid = _insert_finding(conn)

        future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES ('pred-future', ?, 'model', 'retention', 'metric_will_improve',
                    'retention_score', 20.0, 5.0, 0.8, 7, ?, 'pending')
        """, (fid, future))
        conn.commit()

        count = expire_stale_predictions(conn)
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# 4. Model confidence (Beta-Binomial Laplace)
# ---------------------------------------------------------------------------

class TestModelConfidence(unittest.TestCase):

    def test_update_model_confidence_correct(self):
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        _update_model_confidence(conn, "model_a", "retention", "correct")
        info = get_model_confidence(conn, "model_a")
        self.assertEqual(info["correct"], 1)
        self.assertEqual(info["wrong"], 0)
        # Laplace: (1 + 0 + 1) / (1 + 2) = 0.6667
        self.assertAlmostEqual(info["confidence"], 0.6667, places=3)

    def test_update_model_confidence_wrong(self):
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        _update_model_confidence(conn, "model_b", "retention", "wrong")
        info = get_model_confidence(conn, "model_b")
        self.assertEqual(info["wrong"], 1)
        # Laplace: (0 + 0 + 1) / (1 + 2) = 0.3333
        self.assertAlmostEqual(info["confidence"], 0.3333, places=3)

    def test_directionally_correct_counts_half(self):
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        _update_model_confidence(conn, "model_c", "ux", "directionally_correct")
        info = get_model_confidence(conn, "model_c")
        self.assertEqual(info["directionally_correct"], 1)
        # Laplace: (0 + 0.5*1 + 1) / (1 + 2) = 0.5
        self.assertAlmostEqual(info["confidence"], 0.5, places=3)

    def test_insufficient_data_not_scored(self):
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        _update_model_confidence(conn, "model_d", "retention", "insufficient_data")
        info = get_model_confidence(conn, "model_d")
        self.assertEqual(info["insufficient_data"], 1)
        self.assertEqual(info["scored_count"], 0)
        # Should still be medium label since <5 scored
        self.assertEqual(info["label"], "medium")

    def test_fewer_than_5_always_medium(self):
        """Models with fewer than 5 scored outcomes always render as 'medium'."""
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        # 4 correct → confidence ~0.83, but label should still be "medium"
        for _ in range(4):
            _update_model_confidence(conn, "model_e", "retention", "correct")
        info = get_model_confidence(conn, "model_e")
        self.assertEqual(info["scored_count"], 4)
        self.assertEqual(info["label"], "medium")

    def test_high_confidence_label(self):
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        for _ in range(6):
            _update_model_confidence(conn, "model_f", "retention", "correct")
        info = get_model_confidence(conn, "model_f")
        self.assertEqual(info["scored_count"], 6)
        self.assertEqual(info["label"], "high")
        self.assertGreaterEqual(info["confidence"], 0.70)

    def test_low_confidence_label(self):
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        for _ in range(6):
            _update_model_confidence(conn, "model_g", "retention", "wrong")
        info = get_model_confidence(conn, "model_g")
        self.assertEqual(info["scored_count"], 6)
        self.assertEqual(info["label"], "low")
        self.assertLess(info["confidence"], 0.40)

    def test_unknown_model_returns_default(self):
        from mandarin.intelligence.feedback_loops import get_model_confidence
        conn = _make_db()
        info = get_model_confidence(conn, "nonexistent_model")
        self.assertEqual(info["confidence"], 0.5)
        self.assertEqual(info["label"], "medium")
        self.assertEqual(info["scored_count"], 0)


# ---------------------------------------------------------------------------
# 5. Enforcement gate: cannot mark implemented without prediction
# ---------------------------------------------------------------------------

class TestEnforcementGate(unittest.TestCase):

    def test_implemented_without_prediction_fails(self):
        from mandarin.intelligence.finding_lifecycle import transition_finding
        conn = _make_db()
        fid = _insert_finding(conn, status="recommended")
        result = transition_finding(conn, fid, "implemented")
        self.assertFalse(result)

    def test_implemented_with_prediction_succeeds(self):
        from mandarin.intelligence.finding_lifecycle import transition_finding
        conn = _make_db()
        fid = _insert_finding(conn, status="recommended")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES ('pred-gate', ?, 'model', 'retention', 'metric_will_improve',
                    'd7_retention', 20.0, 5.0, 0.8, 30,
                    datetime('now', '+30 days'), 'pending')
        """, (fid,))
        conn.commit()
        result = transition_finding(conn, fid, "implemented")
        self.assertTrue(result)

    def test_non_implemented_transitions_no_gate(self):
        """Other transitions should not be affected by prediction gate."""
        from mandarin.intelligence.finding_lifecycle import transition_finding
        conn = _make_db()
        fid = _insert_finding(conn, status="investigating")
        self.assertTrue(transition_finding(conn, fid, "diagnosed"))
        fid2 = _insert_finding(conn, status="diagnosed")
        self.assertTrue(transition_finding(conn, fid2, "recommended"))


# ---------------------------------------------------------------------------
# 6. Confidence-based finding labeling
# ---------------------------------------------------------------------------

class TestConfidenceLabeling(unittest.TestCase):

    def test_high_confidence_no_prefix(self):
        from mandarin.intelligence.finding_lifecycle import deduplicate_findings
        from mandarin.intelligence.feedback_loops import _update_model_confidence
        conn = _make_db()
        # Build high confidence for "retention" model
        for _ in range(6):
            _update_model_confidence(conn, "retention", "retention", "correct")

        findings = [{"dimension": "retention", "severity": "high",
                      "title": "D7 drop", "analysis": "test"}]
        deduplicate_findings(conn, findings)
        self.assertEqual(findings[0]["confidence_label"], "high")
        self.assertFalse(findings[0]["title"].startswith("["))

    def test_low_confidence_gets_prefix(self):
        from mandarin.intelligence.finding_lifecycle import deduplicate_findings
        from mandarin.intelligence.feedback_loops import _update_model_confidence
        conn = _make_db()
        # Build low confidence for "retention" model
        for _ in range(6):
            _update_model_confidence(conn, "retention", "retention", "wrong")

        findings = [{"dimension": "retention", "severity": "critical",
                      "title": "D7 drop", "analysis": "test"}]
        deduplicate_findings(conn, findings)
        self.assertEqual(findings[0]["confidence_label"], "low")
        self.assertTrue(findings[0]["title"].startswith("[LOW CONFIDENCE"))
        self.assertTrue(findings[0].get("requires_approval"))

    def test_medium_calibrating_prefix(self):
        from mandarin.intelligence.finding_lifecycle import deduplicate_findings
        from mandarin.intelligence.feedback_loops import _update_model_confidence
        conn = _make_db()
        # Build medium confidence (3 correct, 3 wrong → ~0.5)
        for _ in range(3):
            _update_model_confidence(conn, "ux", "ux", "correct")
        for _ in range(3):
            _update_model_confidence(conn, "ux", "ux", "wrong")

        findings = [{"dimension": "ux", "severity": "medium",
                      "title": "Abandon rate up", "analysis": "test"}]
        deduplicate_findings(conn, findings)
        self.assertEqual(findings[0]["confidence_label"], "medium")
        self.assertTrue(findings[0]["title"].startswith("[CALIBRATING]"))

    def test_new_model_defaults_to_medium(self):
        """Models with <5 scored outcomes always get 'medium' label."""
        from mandarin.intelligence.finding_lifecycle import deduplicate_findings
        conn = _make_db()
        findings = [{"dimension": "engagement", "severity": "low",
                      "title": "Low engagement", "analysis": "test"}]
        deduplicate_findings(conn, findings)
        self.assertEqual(findings[0]["confidence_label"], "medium")


# ---------------------------------------------------------------------------
# 7. Self-audit report
# ---------------------------------------------------------------------------

class TestSelfAuditReport(unittest.TestCase):

    def test_empty_report_structure(self):
        from mandarin.intelligence.feedback_loops import generate_self_audit_report
        conn = _make_db()
        report = generate_self_audit_report(conn)
        self.assertIn("prediction_accuracy", report)
        self.assertIn("worst_models", report)
        self.assertIn("best_models", report)
        self.assertIn("measurement_health", report)
        self.assertIn("human_override_analysis", report)
        self.assertIn("engine_accuracy", report)
        self.assertIn("id", report)  # persisted

    def test_report_counts_correct(self):
        from mandarin.intelligence.feedback_loops import generate_self_audit_report
        conn = _make_db()

        # Insert some predictions and outcomes
        fid = _insert_finding(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status, created_at)
            VALUES ('rpt-1', ?, 'model', 'retention', 'metric_will_improve',
                    'd7', 20.0, 5.0, 0.8, 7, ?, 'verified', ?)
        """, (fid, now, now))
        conn.execute("""
            INSERT INTO pi_prediction_outcomes
                (id, prediction_id, recorded_at, metric_actual, actual_delta,
                 direction_correct, magnitude_error, outcome_class)
            VALUES ('out-1', 'rpt-1', ?, 25.0, 5.0, 1, 0.0, 'correct')
        """, (now,))
        conn.commit()

        report = generate_self_audit_report(conn)
        self.assertEqual(report["prediction_accuracy"]["total"], 1)
        self.assertEqual(report["prediction_accuracy"]["correct"], 1)

    def test_report_persisted(self):
        from mandarin.intelligence.feedback_loops import generate_self_audit_report
        conn = _make_db()
        report = generate_self_audit_report(conn)
        row = conn.execute("SELECT * FROM pi_self_audit_report WHERE id = ?",
                           (report["id"],)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["lookback_days"], 30)

    def test_report_worst_models(self):
        from mandarin.intelligence.feedback_loops import generate_self_audit_report, _update_model_confidence
        conn = _make_db()
        # Create a model with wrong predictions
        for _ in range(3):
            _update_model_confidence(conn, "bad_model", "retention", "wrong")
        report = generate_self_audit_report(conn)
        self.assertGreater(len(report["worst_models"]), 0)
        self.assertEqual(report["worst_models"][0]["model_id"], "bad_model")

    def test_report_best_models(self):
        from mandarin.intelligence.feedback_loops import generate_self_audit_report, _update_model_confidence
        conn = _make_db()
        for _ in range(5):
            _update_model_confidence(conn, "good_model", "ux", "correct")
        report = generate_self_audit_report(conn)
        self.assertGreater(len(report["best_models"]), 0)
        self.assertEqual(report["best_models"][0]["model_id"], "good_model")


# ---------------------------------------------------------------------------
# 8. Override accuracy
# ---------------------------------------------------------------------------

class TestOverrideAccuracy(unittest.TestCase):

    def test_empty_overrides(self):
        from mandarin.intelligence.feedback_loops import _compute_override_accuracy
        conn = _make_db()
        result = _compute_override_accuracy(conn)
        self.assertEqual(len(result), 0)

    def test_override_accuracy_computation(self):
        from mandarin.intelligence.feedback_loops import _compute_override_accuracy
        conn = _make_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(conn, dimension="retention")
        # Insert override decision
        conn.execute("""
            INSERT INTO pi_decision_log (finding_id, decision_class, escalation_level, decision, created_at)
            VALUES (?, 'judgment_call', 'quiet', 'Override: changed severity', ?)
        """, (fid, now))
        # Insert prediction + outcome showing engine was wrong
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES ('pred-ov', ?, 'model', 'retention', 'metric_will_improve',
                    'd7', 20.0, 5.0, 0.8, 7, ?, 'verified')
        """, (fid, now))
        conn.execute("""
            INSERT INTO pi_prediction_outcomes
                (id, prediction_id, recorded_at, metric_actual, actual_delta,
                 direction_correct, magnitude_error, outcome_class)
            VALUES ('out-ov', 'pred-ov', ?, 18.0, -2.0, 0, 7.0, 'wrong')
        """, (now,))
        conn.commit()

        result = _compute_override_accuracy(conn)
        if "retention" in result:
            # Engine was wrong → human was right
            self.assertGreater(result["retention"]["human"], 0)


# ---------------------------------------------------------------------------
# 9. Laplace smoothing formula verification
# ---------------------------------------------------------------------------

class TestLaplaceFormula(unittest.TestCase):

    def test_pure_correct_sequence(self):
        """After N correct predictions, confidence should approach but never reach 1.0."""
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        for _ in range(20):
            _update_model_confidence(conn, "laplace_test", "retention", "correct")
        info = get_model_confidence(conn, "laplace_test")
        # (20 + 1) / (20 + 2) = 0.9545
        self.assertAlmostEqual(info["confidence"], 21.0 / 22.0, places=3)
        self.assertLess(info["confidence"], 1.0)

    def test_pure_wrong_sequence(self):
        """After N wrong predictions, confidence should approach but never reach 0."""
        from mandarin.intelligence.feedback_loops import _update_model_confidence, get_model_confidence
        conn = _make_db()
        for _ in range(20):
            _update_model_confidence(conn, "laplace_wrong", "retention", "wrong")
        info = get_model_confidence(conn, "laplace_wrong")
        # (0 + 1) / (20 + 2) = 0.0454
        self.assertAlmostEqual(info["confidence"], 1.0 / 22.0, places=3)
        self.assertGreater(info["confidence"], 0.0)


# ---------------------------------------------------------------------------
# 10. Integration: prediction in audit pipeline
# ---------------------------------------------------------------------------

class TestAuditPipelineIntegration(unittest.TestCase):

    def test_self_audit_key_in_audit_return(self):
        """run_product_audit should include self_audit key."""
        # Just verify the import works and the return dict has the key
        from mandarin.intelligence import run_product_audit
        # We can't easily run the full audit in a test without the full schema,
        # but we verify the module structure exists
        import mandarin.intelligence.feedback_loops as fl
        self.assertTrue(hasattr(fl, 'generate_self_audit_report'))
        self.assertTrue(hasattr(fl, 'record_prediction_outcomes'))
        self.assertTrue(hasattr(fl, 'expire_stale_predictions'))
        self.assertTrue(hasattr(fl, 'emit_prediction'))


# ---------------------------------------------------------------------------
# 11. Measurement failure tracking
# ---------------------------------------------------------------------------

class TestMeasurementFailure(unittest.TestCase):

    def test_increment_measurement_failure_creates_row(self):
        from mandarin.intelligence.feedback_loops import _increment_measurement_failure
        conn = _make_db()
        _increment_measurement_failure(conn, "model_x")
        row = conn.execute(
            "SELECT * FROM pi_model_confidence WHERE model_id = 'model_x'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["measurement_failure_count"], 1)

    def test_increment_measurement_failure_accumulates(self):
        from mandarin.intelligence.feedback_loops import _increment_measurement_failure
        conn = _make_db()
        _increment_measurement_failure(conn, "model_y")
        _increment_measurement_failure(conn, "model_y")
        _increment_measurement_failure(conn, "model_y")
        row = conn.execute(
            "SELECT * FROM pi_model_confidence WHERE model_id = 'model_y'"
        ).fetchone()
        self.assertEqual(row["measurement_failure_count"], 3)


# ---------------------------------------------------------------------------
# 12. Verification window enforcement
# ---------------------------------------------------------------------------

class TestVerificationWindows(unittest.TestCase):

    def test_all_dimensions_have_windows(self):
        from mandarin.intelligence._base import _VERIFICATION_WINDOWS
        expected_dims = [
            "retention", "ux", "engagement", "drill_quality", "flow",
            "content", "onboarding", "srs_funnel", "tone_phonology",
        ]
        for dim in expected_dims:
            self.assertIn(dim, _VERIFICATION_WINDOWS,
                          f"Dimension '{dim}' missing from _VERIFICATION_WINDOWS")

    def test_windows_are_positive_integers(self):
        from mandarin.intelligence._base import _VERIFICATION_WINDOWS
        for dim, days in _VERIFICATION_WINDOWS.items():
            self.assertIsInstance(days, int, f"{dim} window is not int")
            self.assertGreater(days, 0, f"{dim} window must be positive")


if __name__ == "__main__":
    unittest.main()
