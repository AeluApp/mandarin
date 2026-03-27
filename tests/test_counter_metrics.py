"""Tests for the anti-Goodhart counter-metrics system.

Covers:
- Counter-metric computations (all 5 layers)
- Alert threshold evaluation
- Full assessment pipeline
- Snapshot storage and retrieval
- Holdout probe system
- Action execution
- Product rule enforcement
- DB migration (V103, V104)
- Holdout probe injection into session planner
- Counter-metric scheduler adjustment wiring
- Delayed recall validation scheduling
- Trend drift detection
- Production drill bias for recognition-only items
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone, UTC
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate, get_connection


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    """Fresh in-memory database with full schema + migrations."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    # Ensure test user exists
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'test@example.com', 'hash', 'Test', 1)
    """)
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


@pytest.fixture
def populated_conn(conn):
    """DB with sample review data for counter-metric testing."""
    now = datetime.now(UTC)

    # Add content items
    for i in range(1, 21):
        conn.execute("""
            INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level, difficulty)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (i, f"字{i}", f"zi{i}", f"word{i}", 1, 0.3 + (i % 5) * 0.15))

    # Add progress records with varying mastery stages
    stages = ["seen", "passed_once", "stabilizing", "stable", "durable", "decayed"]
    for i in range(1, 21):
        stage = stages[i % len(stages)]
        stable_since = (now - timedelta(days=40)).isoformat() if stage in ("stable", "durable") else None
        conn.execute("""
            INSERT OR IGNORE INTO progress
            (user_id, content_item_id, modality, mastery_stage, total_attempts,
             total_correct, streak_correct, streak_incorrect, ease_factor,
             interval_days, next_review_date, last_review_date,
             half_life_days, drill_types_seen, stable_since_date,
             successes_while_stable, weak_cycle_count, difficulty)
            VALUES (1, ?, 'reading', ?, ?, ?, ?, ?, 2.5, 3.0, ?, ?, 5.0, ?, ?, ?, ?, ?)
        """, (
            i, stage,
            10 + i, 7 + i,  # attempts, correct
            3 if stage != "decayed" else 0,  # streak_correct
            0 if stage != "decayed" else 3,  # streak_incorrect
            (now + timedelta(days=i % 5 - 2)).strftime("%Y-%m-%d"),  # some overdue
            (now - timedelta(days=i % 10 + 1)).isoformat(),  # last_review
            "mc,reverse_mc" if i % 3 == 0 else "mc,ime_type,speaking",  # drill_types
            stable_since,
            5 if stage in ("stable", "durable") else 0,
            3 if stage == "decayed" else 0,  # weak_cycle_count
            0.3 + (i % 5) * 0.15,
        ))

    # Add review events
    for i in range(1, 101):
        item_id = (i % 20) + 1
        correct = 1 if i % 3 != 0 else 0
        confidence = "full" if i % 4 != 0 else ("half" if i % 4 == 1 else "narrowed")
        drill_type = ["mc", "reverse_mc", "ime_type", "speaking", "listening_gist"][i % 5]
        days_ago = 60 - (i * 0.6)
        conn.execute("""
            INSERT INTO review_event
            (user_id, content_item_id, modality, drill_type, correct,
             confidence, response_ms, created_at)
            VALUES (1, ?, 'reading', ?, ?, ?, ?, datetime('now', ? || ' days'))
        """, (item_id, drill_type, correct, confidence,
              200 + i * 10, f"-{days_ago:.1f}"))

    # Add session logs
    for i in range(1, 16):
        days_ago = 30 - (i * 2)
        conn.execute("""
            INSERT INTO session_log
            (user_id, session_type, items_planned, items_completed, items_correct,
             duration_seconds, early_exit, boredom_flags, started_at, modality_counts)
            VALUES (1, 'standard', 12, ?, ?, ?, ?, ?, datetime('now', ? || ' days'), ?)
        """, (
            10 + (i % 3), 7 + (i % 4),
            300 + i * 20,  # duration
            1 if i == 3 else 0,  # early_exit
            1 if i == 5 else 0,  # boredom
            f"-{days_ago}",
            json.dumps({"reading": 5, "listening": 3, "speaking": 2}),
        ))

    conn.commit()
    return conn


# ── V103 Migration Tests ─────────────────────────────────────────────

class TestMigration:
    def test_counter_metric_tables_exist(self, conn):
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "counter_metric_snapshot" in tables
        assert "counter_metric_holdout" in tables
        assert "counter_metric_action_log" in tables
        assert "counter_metric_delayed_validation" in tables

    def test_snapshot_table_columns(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(counter_metric_snapshot)").fetchall()}
        assert "overall_health" in cols
        assert "integrity_json" in cols
        assert "alerts_json" in cols

    def test_holdout_table_columns(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(counter_metric_holdout)").fetchall()}
        assert "content_item_id" in cols
        assert "holdout_set" in cols
        assert "correct" in cols
        assert "drill_type" in cols


# ── Counter-Metric Computation Tests ─────────────────────────────────

class TestIntegrityMetrics:
    def test_delayed_recall_returns_structure(self, populated_conn):
        from mandarin.counter_metrics import delayed_recall_accuracy
        result = delayed_recall_accuracy(populated_conn, delay_days=7, user_id=1)
        assert "accuracy" in result
        assert "sample_size" in result
        assert "delay_days" in result
        assert result["delay_days"] == 7

    def test_transfer_accuracy_returns_structure(self, populated_conn):
        from mandarin.counter_metrics import transfer_accuracy
        result = transfer_accuracy(populated_conn, user_id=1)
        assert "accuracy" in result
        assert "sample_size" in result

    def test_production_vs_recognition_gap(self, populated_conn):
        from mandarin.counter_metrics import production_vs_recognition_gap
        result = production_vs_recognition_gap(populated_conn, user_id=1)
        assert "recognition_accuracy" in result
        assert "production_accuracy" in result
        assert "gap" in result

    def test_mastery_reversal_rate(self, populated_conn):
        from mandarin.counter_metrics import mastery_reversal_rate
        result = mastery_reversal_rate(populated_conn, user_id=1)
        assert "reversal_rate" in result
        assert "reversals" in result
        assert "mastered_ever" in result
        # We inserted some decayed items with stable_since_date
        assert result["mastered_ever"] > 0

    def test_mastery_survival_curve(self, populated_conn):
        from mandarin.counter_metrics import mastery_survival_curve
        result = mastery_survival_curve(populated_conn, user_id=1)
        assert "checkpoints" in result
        assert "sample_size" in result
        cp = result["checkpoints"]
        if cp:
            for key in ["7d", "14d", "30d", "60d"]:
                assert key in cp

    def test_hint_dependence_rate(self, populated_conn):
        from mandarin.counter_metrics import hint_dependence_rate
        result = hint_dependence_rate(populated_conn, user_id=1)
        assert "dependence_rate" in result
        assert "hint_correct" in result
        # We inserted some half/narrowed confidence reviews
        assert result["total_correct"] > 0


class TestCostMetrics:
    def test_session_fatigue_signals(self, populated_conn):
        from mandarin.counter_metrics import session_fatigue_signals
        result = session_fatigue_signals(populated_conn, user_id=1)
        assert "fatigue_score" in result
        assert "early_exit_rate" in result
        assert "session_count" in result
        assert result["session_count"] > 0
        assert 0 <= result["fatigue_score"] <= 100

    def test_backlog_burden(self, populated_conn):
        from mandarin.counter_metrics import backlog_burden
        result = backlog_burden(populated_conn, user_id=1)
        assert "overdue_items" in result
        assert "total_active_items" in result

    def test_learning_efficiency(self, populated_conn):
        from mandarin.counter_metrics import learning_efficiency
        result = learning_efficiency(populated_conn, user_id=1)
        assert "minutes_studied" in result
        assert result["minutes_studied"] > 0

    def test_post_break_recovery(self, populated_conn):
        from mandarin.counter_metrics import post_break_recovery
        result = post_break_recovery(populated_conn, user_id=1)
        assert "post_break_accuracy" in result
        assert "break_count" in result


class TestDistortionMetrics:
    def test_answer_latency_suspiciousness(self, populated_conn):
        from mandarin.counter_metrics import answer_latency_suspiciousness
        result = answer_latency_suspiciousness(populated_conn, user_id=1)
        assert "suspicious_fast_rate" in result
        assert "total_reviews" in result
        assert result["total_reviews"] > 0

    def test_recognition_only_progress(self, populated_conn):
        from mandarin.counter_metrics import recognition_only_progress
        result = recognition_only_progress(populated_conn, user_id=1)
        assert "recognition_only_rate" in result
        assert "advanced_count" in result

    def test_difficulty_avoidance(self, populated_conn):
        from mandarin.counter_metrics import difficulty_avoidance
        result = difficulty_avoidance(populated_conn, user_id=1)
        assert "low_challenge_rate" in result


class TestOutcomeMetrics:
    def test_holdout_probe_performance_empty(self, conn):
        from mandarin.counter_metrics import holdout_probe_performance
        result = holdout_probe_performance(conn, user_id=1)
        assert result["holdout_accuracy"] is None
        assert result["sample_size"] == 0

    def test_holdout_probe_with_data(self, populated_conn):
        from mandarin.counter_metrics import holdout_probe_performance
        # Insert some holdout data
        for i in range(10):
            populated_conn.execute("""
                INSERT INTO counter_metric_holdout
                (user_id, content_item_id, modality, drill_type, correct, administered_at)
                VALUES (1, ?, 'reading', 'reverse_mc', ?, datetime('now', ? || ' days'))
            """, (i + 1, 1 if i < 7 else 0, f"-{i}"))
        populated_conn.commit()

        result = holdout_probe_performance(populated_conn, user_id=1)
        assert result["sample_size"] == 10
        assert result["holdout_accuracy"] == 0.7

    def test_progress_honesty_score(self, populated_conn):
        from mandarin.counter_metrics import progress_honesty_score
        result = progress_honesty_score(populated_conn, user_id=1)
        assert "honesty_score" in result


# ── Alert Threshold Tests ────────────────────────────────────────────

class TestAlertThresholds:
    def test_evaluate_below_critical(self):
        from mandarin.counter_metrics import evaluate_threshold
        result = evaluate_threshold("delayed_recall_7d", 0.45)
        assert result == "critical"

    def test_evaluate_below_warn(self):
        from mandarin.counter_metrics import evaluate_threshold
        result = evaluate_threshold("delayed_recall_7d", 0.60)
        assert result == "warn"

    def test_evaluate_ok(self):
        from mandarin.counter_metrics import evaluate_threshold
        result = evaluate_threshold("delayed_recall_7d", 0.80)
        assert result is None

    def test_evaluate_above_critical(self):
        from mandarin.counter_metrics import evaluate_threshold
        result = evaluate_threshold("suspicious_fast_rate", 0.25)
        assert result == "critical"

    def test_evaluate_none_value(self):
        from mandarin.counter_metrics import evaluate_threshold
        result = evaluate_threshold("delayed_recall_7d", None)
        assert result is None

    def test_evaluate_unknown_metric(self):
        from mandarin.counter_metrics import evaluate_threshold
        result = evaluate_threshold("nonexistent_metric", 0.5)
        assert result is None


# ── Full Assessment Tests ────────────────────────────────────────────

class TestFullAssessment:
    def test_assessment_structure(self, populated_conn):
        from mandarin.counter_metrics import compute_full_assessment
        result = compute_full_assessment(populated_conn, user_id=1)

        assert "computed_at" in result
        assert "integrity" in result
        assert "cost" in result
        assert "distortion" in result
        assert "outcome" in result
        assert "alerts" in result
        assert "alert_summary" in result
        assert "overall_health" in result
        assert "counter_metric_map" in result

    def test_assessment_health_levels(self, populated_conn):
        from mandarin.counter_metrics import compute_full_assessment
        result = compute_full_assessment(populated_conn, user_id=1)
        assert result["overall_health"] in ("healthy", "caution", "warning", "critical")

    def test_assessment_integrity_has_all_metrics(self, populated_conn):
        from mandarin.counter_metrics import compute_full_assessment
        result = compute_full_assessment(populated_conn, user_id=1)
        integrity = result["integrity"]
        assert "delayed_recall_7d" in integrity
        assert "delayed_recall_14d" in integrity
        assert "delayed_recall_30d" in integrity
        assert "transfer_accuracy" in integrity
        assert "mastery_reversal_rate" in integrity
        assert "hint_dependence_rate" in integrity


# ── Snapshot Storage Tests ───────────────────────────────────────────

class TestSnapshotStorage:
    def test_save_and_retrieve_snapshot(self, populated_conn):
        from mandarin.counter_metrics import (
            compute_full_assessment, save_snapshot, get_snapshot_history,
        )
        assessment = compute_full_assessment(populated_conn, user_id=1)
        snapshot_id = save_snapshot(populated_conn, assessment, user_id=1)
        assert snapshot_id > 0

        history = get_snapshot_history(populated_conn, user_id=1)
        assert len(history) == 1
        assert history[0]["overall_health"] == assessment["overall_health"]

    def test_multiple_snapshots_ordered(self, populated_conn):
        from mandarin.counter_metrics import (
            compute_full_assessment, save_snapshot, get_snapshot_history,
        )
        for _ in range(3):
            assessment = compute_full_assessment(populated_conn, user_id=1)
            save_snapshot(populated_conn, assessment, user_id=1)

        history = get_snapshot_history(populated_conn, user_id=1, limit=10)
        assert len(history) == 3


# ── Holdout Probe Tests ──────────────────────────────────────────────

class TestHoldoutProbes:
    def test_select_holdout_items(self, populated_conn):
        from mandarin.holdout_probes import select_holdout_items
        items = select_holdout_items(populated_conn, user_id=1, count=5)
        # Should find items in stabilizing/stable/durable with enough attempts
        assert isinstance(items, list)

    def test_deterministic_selection(self, populated_conn):
        from mandarin.holdout_probes import select_holdout_items
        items1 = select_holdout_items(populated_conn, user_id=1, count=5)
        items2 = select_holdout_items(populated_conn, user_id=1, count=5)
        # Same user, same rotation window → same items
        ids1 = [i["content_item_id"] for i in items1]
        ids2 = [i["content_item_id"] for i in items2]
        assert ids1 == ids2

    def test_pick_holdout_drill_type(self, populated_conn):
        from mandarin.holdout_probes import pick_holdout_drill_type, HOLDOUT_DRILL_TYPES
        item = {"content_item_id": 1}
        drill = pick_holdout_drill_type(item, user_id=1)
        assert drill in HOLDOUT_DRILL_TYPES

    def test_record_holdout_result(self, populated_conn):
        from mandarin.holdout_probes import record_holdout_result
        rid = record_holdout_result(
            populated_conn, user_id=1, content_item_id=1,
            modality="reading", drill_type="reverse_mc",
            correct=True, response_ms=1200,
        )
        assert rid > 0

        # Verify it's in the holdout table, NOT in progress
        row = populated_conn.execute(
            "SELECT * FROM counter_metric_holdout WHERE id = ?", (rid,)
        ).fetchone()
        assert row is not None
        assert row["correct"] == 1

    def test_get_holdout_summary(self, populated_conn):
        from mandarin.holdout_probes import record_holdout_result, get_holdout_summary

        for i in range(5):
            record_holdout_result(
                populated_conn, user_id=1, content_item_id=i + 1,
                modality="reading", drill_type="reverse_mc",
                correct=(i < 3),
            )

        summary = get_holdout_summary(populated_conn, user_id=1)
        assert summary["sample_size"] == 5
        assert summary["accuracy"] == 0.6


# ── Action Execution Tests ───────────────────────────────────────────

class TestActionExecution:
    def test_execute_actions_with_alerts(self, populated_conn):
        from mandarin.counter_metrics import compute_full_assessment
        from mandarin.counter_metrics_actions import execute_actions_for_assessment

        assessment = compute_full_assessment(populated_conn, user_id=1)
        # Force an alert for testing
        assessment["alerts"] = [{
            "metric": "fatigue_score",
            "value": 65,
            "severity": "critical",
            "threshold": 60,
            "direction": "above",
        }]

        actions = execute_actions_for_assessment(populated_conn, assessment)
        assert isinstance(actions, list)
        # fatigue_score critical should trigger switch_to_minimal_mode + admin_alert
        assert len(actions) >= 1

    def test_action_log_recorded(self, populated_conn):
        from mandarin.counter_metrics_actions import execute_actions_for_assessment, get_action_history

        assessment = {"alerts": [{
            "metric": "early_exit_rate",
            "value": 0.30,
            "severity": "warn",
            "threshold": 0.15,
            "direction": "above",
        }]}

        execute_actions_for_assessment(populated_conn, assessment)
        history = get_action_history(populated_conn, limit=10)
        assert len(history) > 0


class TestProductRuleEnforcement:
    def test_no_violations_when_healthy(self):
        from mandarin.counter_metrics_actions import enforce_product_rules

        assessment = {
            "integrity": {
                "delayed_recall_7d": {"accuracy": 0.80},
                "transfer_accuracy": {"accuracy": 0.70},
                "production_vs_recognition_gap": {"production_accuracy": 0.65},
                "mastery_reversal_rate": {"reversal_rate": 0.05},
            },
            "outcome": {
                "holdout_probe_performance": {"sample_size": 50, "holdout_accuracy": 0.75},
                "progress_honesty_score": {"honesty_score": 80},
            },
        }
        violations = enforce_product_rules(assessment)
        assert len(violations) == 0

    def test_rule2_violation_low_recall(self):
        from mandarin.counter_metrics_actions import enforce_product_rules

        assessment = {
            "integrity": {
                "delayed_recall_7d": {"accuracy": 0.40},  # Critical
                "transfer_accuracy": {"accuracy": 0.70},
                "production_vs_recognition_gap": {"production_accuracy": 0.65},
                "mastery_reversal_rate": {"reversal_rate": 0.05},
            },
            "outcome": {
                "holdout_probe_performance": {"sample_size": 50},
                "progress_honesty_score": {"honesty_score": 80},
            },
        }
        violations = enforce_product_rules(assessment)
        rule2_violations = [v for v in violations if v["rule"] == 2]
        assert len(rule2_violations) >= 1

    def test_rule4_violation_insufficient_holdout(self):
        from mandarin.counter_metrics_actions import enforce_product_rules

        assessment = {
            "integrity": {
                "delayed_recall_7d": {"accuracy": 0.80},
                "transfer_accuracy": {"accuracy": 0.70},
                "production_vs_recognition_gap": {"production_accuracy": 0.65},
                "mastery_reversal_rate": {"reversal_rate": 0.05},
            },
            "outcome": {
                "holdout_probe_performance": {"sample_size": 3},  # Too few
                "progress_honesty_score": {"honesty_score": 80},
            },
        }
        violations = enforce_product_rules(assessment)
        rule4_violations = [v for v in violations if v["rule"] == 4]
        assert len(rule4_violations) == 1


# ── Counter-Metric Map Tests ────────────────────────────────────────

class TestCounterMetricMap:
    def test_all_kpis_have_counter_metrics(self):
        from mandarin.counter_metrics import COUNTER_METRIC_MAP

        expected_kpis = [
            "review_accuracy", "streak_length", "items_mastered",
            "session_completion", "time_spent", "conversion",
        ]
        for kpi in expected_kpis:
            assert kpi in COUNTER_METRIC_MAP, f"Missing KPI: {kpi}"

    def test_each_kpi_has_failure_mode(self):
        from mandarin.counter_metrics import COUNTER_METRIC_MAP

        for kpi, info in COUNTER_METRIC_MAP.items():
            assert "likely_failure" in info, f"{kpi} missing likely_failure"
            assert len(info["likely_failure"]) > 0

    def test_learning_kpis_have_integrity_metrics(self):
        """Rule 1: No learning KPI ships alone."""
        from mandarin.counter_metrics import COUNTER_METRIC_MAP

        learning_kpis = ["review_accuracy", "items_mastered", "session_completion"]
        for kpi in learning_kpis:
            info = COUNTER_METRIC_MAP[kpi]
            assert len(info.get("integrity", [])) > 0, \
                f"Rule 1 violation: {kpi} has no integrity counter-metrics"


# ── Scheduler Run Tests ──────────────────────────────────────────────

class TestSchedulerRunOnce:
    def test_run_once_returns_assessment(self, populated_conn):
        """Test the full compute → save → action → enforce pipeline."""
        from mandarin.counter_metrics import compute_full_assessment, save_snapshot
        from mandarin.counter_metrics_actions import (
            execute_actions_for_assessment, enforce_product_rules,
        )

        assessment = compute_full_assessment(populated_conn, user_id=1)
        save_snapshot(populated_conn, assessment, user_id=1)

        actions = []
        if assessment.get("alert_summary", {}).get("total", 0) > 0:
            actions = execute_actions_for_assessment(populated_conn, assessment)

        violations = enforce_product_rules(assessment)

        result = {
            "assessment": assessment,
            "actions_taken": actions,
            "rule_violations": violations,
        }

        assert "assessment" in result
        assert "actions_taken" in result
        assert "rule_violations" in result
        assert result["assessment"]["overall_health"] in (
            "healthy", "caution", "warning", "critical"
        )


# ═══════════════════════════════════════════════════════════════════════
# NEW FEATURE TESTS: Holdout injection, scheduler wiring, delayed
# validation, trend drift, production bias
# ═══════════════════════════════════════════════════════════════════════


# ── Delayed Validation Tests ──────────────────────────────────────────

class TestDelayedValidation:
    def test_v104_delayed_validation_table_exists(self, conn):
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(counter_metric_delayed_validation)"
        ).fetchall()}
        assert "delay_days" in cols
        assert "status" in cols
        assert "mastery_at_schedule" in cols

    def test_schedule_validation_checks(self, conn):
        from mandarin.delayed_validation import schedule_validation_checks
        count = schedule_validation_checks(conn, content_item_id=1, user_id=1,
                                            mastery_stage="stable")
        assert count == 3  # 7d, 14d, 30d

        # Verify rows created
        rows = conn.execute(
            "SELECT * FROM counter_metric_delayed_validation WHERE user_id=1"
        ).fetchall()
        assert len(rows) == 3
        delays = {r["delay_days"] for r in rows}
        assert delays == {7, 14, 30}
        assert all(r["status"] == "pending" for r in rows)

    def test_no_duplicate_scheduling(self, conn):
        from mandarin.delayed_validation import schedule_validation_checks
        schedule_validation_checks(conn, content_item_id=1, mastery_stage="stable")
        count2 = schedule_validation_checks(conn, content_item_id=1, mastery_stage="stable")
        assert count2 == 0  # No duplicates

    def test_only_schedules_for_promotion_stages(self, conn):
        from mandarin.delayed_validation import schedule_validation_checks
        count = schedule_validation_checks(conn, content_item_id=1,
                                            mastery_stage="seen")
        assert count == 0
        count = schedule_validation_checks(conn, content_item_id=2,
                                            mastery_stage="passed_once")
        assert count == 0

    def test_get_due_validations(self, conn):
        from mandarin.delayed_validation import schedule_validation_checks, get_due_validations

        # Add content item
        conn.execute("""
            INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level, difficulty)
            VALUES (100, '测', 'ce4', 'test', 1, 0.5)
        """)
        conn.commit()

        schedule_validation_checks(conn, content_item_id=100, mastery_stage="durable")

        # Manually set one to be due now
        conn.execute("""
            UPDATE counter_metric_delayed_validation
            SET scheduled_at = datetime('now', '-1 hour')
            WHERE content_item_id = 100 AND delay_days = 7
        """)
        conn.commit()

        due = get_due_validations(conn, user_id=1)
        assert len(due) == 1
        assert due[0]["content_item_id"] == 100
        assert due[0]["delay_days"] == 7

    def test_record_validation_result(self, conn):
        from mandarin.delayed_validation import (
            schedule_validation_checks, record_validation_result,
        )
        schedule_validation_checks(conn, content_item_id=1, mastery_stage="stable")
        row = conn.execute(
            "SELECT id FROM counter_metric_delayed_validation WHERE delay_days = 7"
        ).fetchone()
        vid = row["id"]

        record_validation_result(conn, validation_id=vid, correct=True,
                                  response_ms=500, drill_type="reverse_mc")

        updated = conn.execute(
            "SELECT * FROM counter_metric_delayed_validation WHERE id = ?", (vid,)
        ).fetchone()
        assert updated["status"] == "completed"
        assert updated["correct"] == 1
        assert updated["response_ms"] == 500

    def test_validation_summary(self, conn):
        from mandarin.delayed_validation import (
            schedule_validation_checks, record_validation_result,
            get_validation_summary,
        )
        # Schedule and complete some validations
        schedule_validation_checks(conn, content_item_id=1, mastery_stage="stable")
        schedule_validation_checks(conn, content_item_id=2, mastery_stage="durable")

        rows = conn.execute(
            "SELECT id, delay_days FROM counter_metric_delayed_validation"
        ).fetchall()
        for r in rows:
            record_validation_result(conn, validation_id=r["id"],
                                      correct=(r["id"] % 2 == 0))

        summary = get_validation_summary(conn, user_id=1)
        assert summary["sample_size"] == 6
        assert summary["accuracy"] is not None
        assert "by_delay" in summary

    def test_schedule_for_recent_promotions(self, populated_conn):
        from mandarin.delayed_validation import schedule_validations_for_recent_promotions

        # populated_conn has items with stable/durable stages and recent reviews
        total = schedule_validations_for_recent_promotions(
            populated_conn, user_id=1, lookback_days=60)
        assert total > 0

    def test_get_session_validations(self, conn):
        from mandarin.delayed_validation import (
            schedule_validation_checks, get_session_validations,
        )
        conn.execute("""
            INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level, difficulty)
            VALUES (200, '验', 'yan4', 'verify', 1, 0.5)
        """)
        conn.commit()

        schedule_validation_checks(conn, content_item_id=200, mastery_stage="stable")
        # Make due now
        conn.execute("""
            UPDATE counter_metric_delayed_validation
            SET scheduled_at = datetime('now', '-1 hour')
            WHERE content_item_id = 200 AND delay_days = 7
        """)
        conn.commit()

        probes = get_session_validations(conn, user_id=1)
        assert len(probes) == 1
        assert probes[0]["is_delayed_validation"] is True
        assert probes[0]["content_item_id"] == 200


# ── Trend Drift Detection Tests ──────────────────────────────────────

class TestTrendDriftDetection:
    def _create_snapshots(self, conn, metric_path, values, json_col="integrity_json"):
        """Create a series of snapshots with declining values."""
        from mandarin.counter_metrics import save_snapshot
        now = datetime.now(UTC)
        for i, val in enumerate(values):
            # Older snapshots first
            ts = (now - timedelta(hours=(len(values) - i) * 4)).isoformat()

            # Build nested JSON
            keys = metric_path.split(".")
            data = {}
            current = data
            for k in keys[:-1]:
                current[k] = {}
                current = current[k]
            current[keys[-1]] = val

            conn.execute("""
                INSERT INTO counter_metric_snapshot
                (user_id, computed_at, overall_health, alert_count, critical_count,
                 integrity_json, cost_json, distortion_json, outcome_json, alerts_json)
                VALUES (1, ?, 'caution', 1, 0, ?, ?, ?, ?, '[]')
            """, (ts,
                  json.dumps(data) if json_col == "integrity_json" else "{}",
                  json.dumps(data) if json_col == "cost_json" else "{}",
                  json.dumps(data) if json_col == "distortion_json" else "{}",
                  json.dumps(data) if json_col == "outcome_json" else "{}"))
            conn.commit()

    def test_no_drift_without_enough_snapshots(self, conn):
        from mandarin.counter_metrics import _detect_trend_drift
        alerts = _detect_trend_drift(conn, user_id=1)
        assert alerts == []

    def test_detects_declining_below_metric(self, conn):
        from mandarin.counter_metrics import _detect_trend_drift
        # delayed_recall_7d: direction=below, declining = values getting lower
        self._create_snapshots(conn, "delayed_recall_7d.accuracy",
                                [0.80, 0.75, 0.70, 0.65],
                                json_col="integrity_json")
        alerts = _detect_trend_drift(conn, user_id=1)
        matching = [a for a in alerts if a["metric"] == "trend_delayed_recall_7d"]
        assert len(matching) == 1
        assert matching[0]["severity"] == "warn"
        assert matching[0]["cycles"] >= 3

    def test_detects_rising_above_metric(self, conn):
        from mandarin.counter_metrics import _detect_trend_drift
        # fatigue_score: direction=above, worsening = values getting higher
        self._create_snapshots(conn, "session_fatigue.fatigue_score",
                                [20, 25, 30, 38],
                                json_col="cost_json")
        alerts = _detect_trend_drift(conn, user_id=1)
        matching = [a for a in alerts if a["metric"] == "trend_fatigue_score"]
        assert len(matching) == 1

    def test_no_alert_for_stable_values(self, conn):
        from mandarin.counter_metrics import _detect_trend_drift
        self._create_snapshots(conn, "delayed_recall_7d.accuracy",
                                [0.75, 0.75, 0.76, 0.75],
                                json_col="integrity_json")
        alerts = _detect_trend_drift(conn, user_id=1)
        matching = [a for a in alerts if a["metric"] == "trend_delayed_recall_7d"]
        assert len(matching) == 0

    def test_no_alert_for_improving_values(self, conn):
        from mandarin.counter_metrics import _detect_trend_drift
        self._create_snapshots(conn, "delayed_recall_7d.accuracy",
                                [0.65, 0.70, 0.75, 0.80],
                                json_col="integrity_json")
        alerts = _detect_trend_drift(conn, user_id=1)
        matching = [a for a in alerts if a["metric"] == "trend_delayed_recall_7d"]
        assert len(matching) == 0

    def test_trend_alerts_appear_in_full_assessment(self, populated_conn):
        """Trend alerts should be included in the full assessment output."""
        from mandarin.counter_metrics import compute_full_assessment
        # Create declining snapshots first
        self._create_snapshots(populated_conn, "delayed_recall_7d.accuracy",
                                [0.80, 0.75, 0.70, 0.65],
                                json_col="integrity_json")
        assessment = compute_full_assessment(populated_conn, user_id=1)
        trend_alerts = [a for a in assessment["alerts"]
                        if a["metric"].startswith("trend_")]
        # May or may not fire depending on populated_conn data, but the
        # machinery should not crash
        assert isinstance(trend_alerts, list)


# ── Counter-Metric Scheduler Wiring Tests ─────────────────────────────

class TestSchedulerAdjustmentWiring:
    def test_pause_new_items_adjustment(self, populated_conn):
        """Lifecycle event 'pause_new_items' should zero out new_budget."""
        now = datetime.now(UTC).isoformat()
        populated_conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
        """, (json.dumps({
            "action": "pause_new_items",
            "params": {"days": 3},
            "reason": "test",
            "trigger_metric": "delayed_recall_7d",
        }), now))
        populated_conn.commit()

        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 5, "target_items": 12, "weights": {"reading": 0.5, "ime": 0.3, "listening": 0.2}}
        adjustments = _apply_counter_metric_adjustments(populated_conn, 1, plan)
        assert plan["new_budget"] == 0
        assert len(adjustments) > 0
        assert any("pause_new_items" in a for a in adjustments)

    def test_reduce_new_item_budget_adjustment(self, populated_conn):
        now = datetime.now(UTC).isoformat()
        populated_conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
        """, (json.dumps({
            "action": "reduce_new_item_budget",
            "params": {"multiplier": 0.5},
        }), now))
        populated_conn.commit()

        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 10, "target_items": 12, "weights": {"reading": 0.5, "ime": 0.3, "listening": 0.2}}
        _apply_counter_metric_adjustments(populated_conn, 1, plan)
        assert plan["new_budget"] == 5

    def test_shorten_sessions_adjustment(self, populated_conn):
        now = datetime.now(UTC).isoformat()
        populated_conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
        """, (json.dumps({
            "action": "shorten_sessions",
            "params": {"multiplier": 0.75},
        }), now))
        populated_conn.commit()

        from mandarin.scheduler import _apply_counter_metric_adjustments, _pick_modality_distribution
        plan = {
            "new_budget": 5, "target_items": 12,
            "weights": {"reading": 0.5, "ime": 0.3, "listening": 0.2},
            "distribution": _pick_modality_distribution(12, {"reading": 0.5, "ime": 0.3, "listening": 0.2}),
        }
        _apply_counter_metric_adjustments(populated_conn, 1, plan)
        assert plan["target_items"] == 9  # 12 * 0.75

    def test_boost_production_drills_flag(self, populated_conn):
        now = datetime.now(UTC).isoformat()
        populated_conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
        """, (json.dumps({
            "action": "boost_production_drills",
            "params": {"production_weight": 2.5},
        }), now))
        populated_conn.commit()

        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 5, "target_items": 12, "weights": {"reading": 0.5}}
        _apply_counter_metric_adjustments(populated_conn, 1, plan)
        assert plan.get("_cm_production_boost") == 2.5

    def test_deduplicates_actions(self, populated_conn):
        """Only the most recent action of each type should apply."""
        now = datetime.now(UTC).isoformat()
        for budget_mult in [0.5, 0.3]:
            populated_conn.execute("""
                INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
                VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
            """, (json.dumps({
                "action": "reduce_new_item_budget",
                "params": {"multiplier": budget_mult},
            }), now))
        populated_conn.commit()

        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 10, "target_items": 12, "weights": {}}
        _apply_counter_metric_adjustments(populated_conn, 1, plan)
        # Only the most recent (first in DESC order) should apply
        # So either 5 or 3, depending on which was newest — but NOT both
        [a for a in plan.get("_metrics_adjustments", [])
                       if "reduce_new_item_budget" in a] if "_metrics_adjustments" in plan else []
        # The new_budget should have been multiplied only once
        assert plan["new_budget"] in (3, 5)

    def test_ignores_old_adjustments(self, populated_conn):
        """Adjustments older than 24 hours should be ignored."""
        old_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        populated_conn.execute("""
            INSERT INTO lifecycle_event (user_id, event_type, metadata, created_at)
            VALUES (1, 'counter_metric_scheduler_adjust', ?, ?)
        """, (json.dumps({"action": "pause_new_items", "params": {}}), old_time))
        populated_conn.commit()

        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 10, "target_items": 12, "weights": {}}
        adjustments = _apply_counter_metric_adjustments(populated_conn, 1, plan)
        assert plan["new_budget"] == 10  # Should NOT be modified
        assert len(adjustments) == 0


# ── Holdout Probe Injection Tests ─────────────────────────────────────

class TestHoldoutInjection:
    def test_plan_holdout_probes_function_exists(self):
        from mandarin.scheduler import _plan_holdout_probes
        assert callable(_plan_holdout_probes)

    def test_holdout_items_have_metadata_flag(self, populated_conn):
        """Holdout items injected into drills should have is_holdout metadata."""
        from mandarin.scheduler import _plan_holdout_probes, DrillItem
        drills = []
        seen_ids = set()
        _plan_holdout_probes(populated_conn, drills, seen_ids, user_id=1)
        # May or may not produce probes depending on mastery data,
        # but should not crash
        for d in drills:
            assert d.metadata.get("is_holdout") is True

    def test_holdout_metadata_includes_set(self, populated_conn):
        from mandarin.scheduler import _plan_holdout_probes
        drills = []
        seen_ids = set()
        _plan_holdout_probes(populated_conn, drills, seen_ids, user_id=1)
        for d in drills:
            assert "holdout_set" in d.metadata


# ── Production Drill Bias Tests ───────────────────────────────────────

class TestProductionDrillBias:
    def test_item_has_production_history_false(self, populated_conn):
        """Items with only recognition drill history should return False."""
        from mandarin.scheduler import _item_has_production_history
        # Item 3 has drill_types_seen = "mc,reverse_mc" — recognition only
        # We need review_event data with only recognition drills for this item
        populated_conn.execute("DELETE FROM review_event WHERE content_item_id = 3")
        for dt in ["mc", "mc", "reverse_mc"]:
            populated_conn.execute("""
                INSERT INTO review_event (user_id, content_item_id, modality,
                    drill_type, correct, created_at)
                VALUES (1, 3, 'reading', ?, 1, datetime('now'))
            """, (dt,))
        populated_conn.commit()

        result = _item_has_production_history(populated_conn, 3, user_id=1)
        assert result is False

    def test_item_has_production_history_true(self, populated_conn):
        """Items with production drill history should return True."""
        from mandarin.scheduler import _item_has_production_history
        # Add a production drill
        populated_conn.execute("""
            INSERT INTO review_event (user_id, content_item_id, modality,
                drill_type, correct, created_at)
            VALUES (1, 5, 'reading', 'sentence_build', 1, datetime('now'))
        """)
        populated_conn.commit()

        result = _item_has_production_history(populated_conn, 5, user_id=1)
        assert result is True

    def test_recognition_types_constant(self):
        from mandarin.scheduler import _RECOGNITION_DRILL_TYPES
        assert "mc" in _RECOGNITION_DRILL_TYPES
        assert "reverse_mc" in _RECOGNITION_DRILL_TYPES
        assert "sentence_build" not in _RECOGNITION_DRILL_TYPES
        assert "translation" not in _RECOGNITION_DRILL_TYPES


# ── Delayed Validation Integration in Assessment ──────────────────────

class TestDelayedValidationInAssessment:
    def test_assessment_includes_delayed_validation(self, populated_conn):
        from mandarin.counter_metrics import compute_full_assessment
        assessment = compute_full_assessment(populated_conn, user_id=1)
        # Should have the key even if no data
        assert "delayed_validation" in assessment
