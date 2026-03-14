"""Tests for Operations Research A+ modules: sensitivity, queue model, optimization.

Uses the shared conftest.py test_db fixture for a fresh SQLite database.
"""
import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.conftest import make_test_db


# ── Helpers: seed test data ──────────────────────────────────────────

def _seed_content_items(conn, n=20):
    """Insert n drill-ready content items at HSK 1-2."""
    for i in range(1, n + 1):
        conn.execute("""
            INSERT OR IGNORE INTO content_item
                (id, hanzi, pinyin, english, hsk_level, item_type, status,
                 review_status, difficulty, times_shown, is_mined_out)
            VALUES (?, ?, ?, ?, ?, 'vocab', 'drill_ready', 'approved', ?, 0, 0)
        """, (
            i,
            f"字{i}",
            f"zi{i}",
            f"word{i}",
            1 if i <= 10 else 2,
            round(0.3 + (i % 5) * 0.1, 2),
        ))
    conn.commit()


def _seed_progress(conn, user_id=1, n=15):
    """Seed progress records for items 1..n with varied mastery states."""
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    for i in range(1, n + 1):
        streak = i % 6
        mastery = ["seen", "passed_once", "stabilizing", "stable", "durable", "decayed"][streak]
        interval = max(1, i * 2)
        half_life = max(1.0, float(i))
        attempts = i * 3
        correct = int(attempts * 0.7)
        next_review = yesterday if i % 3 == 0 else today

        conn.execute("""
            INSERT OR IGNORE INTO progress
                (content_item_id, modality, user_id, total_attempts, total_correct,
                 streak_correct, interval_days, half_life_days, mastery_stage,
                 next_review_date, last_review_date, difficulty)
            VALUES (?, 'reading', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            i, user_id, attempts, correct, streak, interval,
            half_life, mastery, next_review, week_ago,
            round(0.3 + (i % 5) * 0.1, 2),
        ))
    conn.commit()


def _seed_sessions(conn, user_id=1, n=15):
    """Seed session_log entries spread over the last 30 days."""
    for i in range(n):
        day = date.today() - timedelta(days=i * 2)
        conn.execute("""
            INSERT INTO session_log
                (user_id, started_at, ended_at, items_planned, items_completed,
                 items_correct, duration_seconds, session_day_of_week, early_exit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            user_id,
            f"{day.isoformat()} 10:00:00",
            f"{day.isoformat()} 10:15:00",
            12, 10, 7, 900, day.weekday(),
        ))
    conn.commit()


def _seed_full(conn, user_id=1):
    """Seed content + progress + sessions for a realistic learner state."""
    _seed_content_items(conn, n=20)
    _seed_progress(conn, user_id=user_id, n=15)
    _seed_sessions(conn, user_id=user_id, n=15)


# ── Sensitivity Analysis Tests ───────────────────────────────────────

class TestSensitivityAnalysis:

    def test_returns_valid_structure(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(conn, user_id=1)

            assert "user_id" in result
            assert "current_state" in result
            assert "baseline" in result
            assert "sweeps" in result
            assert isinstance(result["sweeps"], dict)
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_sweep_arrays_have_matching_lengths(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(conn, user_id=1)

            for param_name, sweep in result["sweeps"].items():
                n = len(sweep["sweep_values"])
                assert len(sweep["retention_rate"]) == n, f"{param_name} retention_rate length mismatch"
                assert len(sweep["queue_depth"]) == n, f"{param_name} queue_depth length mismatch"
                assert len(sweep["weeks_to_next_hsk"]) == n, f"{param_name} weeks_to_next_hsk length mismatch"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_retention_values_in_valid_range(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(conn, user_id=1)

            for param_name, sweep in result["sweeps"].items():
                for val in sweep["retention_rate"]:
                    assert 0.0 <= val <= 1.0, f"{param_name} retention {val} out of range"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_queue_depth_non_negative(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(conn, user_id=1)

            for param_name, sweep in result["sweeps"].items():
                for val in sweep["queue_depth"]:
                    assert val >= 0, f"{param_name} queue_depth {val} is negative"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_hsk_time_non_negative(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(conn, user_id=1)

            for param_name, sweep in result["sweeps"].items():
                for val in sweep["weeks_to_next_hsk"]:
                    assert val >= 0, f"{param_name} weeks_to_next_hsk {val} is negative"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_selective_parameter_sweep(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(
                conn, user_id=1,
                parameters={"sessions_per_week": True}
            )
            assert "sessions_per_week" in result["sweeps"]
            assert len(result["sweeps"]) == 1
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_empty_db_no_crash(self):
        conn, path = make_test_db()
        try:
            from mandarin.quality.sensitivity import sensitivity_analysis
            result = sensitivity_analysis(conn, user_id=1)
            assert "sweeps" in result
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ── Queue Model Tests ────────────────────────────────────────────────

class TestQueueModel:

    def test_returns_valid_structure(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.queue_model import queue_model
            result = queue_model(conn, user_id=1)

            assert "arrival_rate" in result
            assert "service_rate" in result
            assert "utilization" in result
            assert "stability" in result
            assert "recommendation" in result
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_utilization_in_valid_range_when_stable(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.queue_model import queue_model
            result = queue_model(conn, user_id=1)

            if result["stability"]:
                rho = result["utilization"]
                assert 0.0 <= rho < 1.0, f"Stable queue utilization {rho} out of [0, 1)"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_no_data_returns_gracefully(self):
        conn, path = make_test_db()
        try:
            from mandarin.quality.queue_model import queue_model
            result = queue_model(conn, user_id=1)

            assert result["stability"] is True
            assert result["utilization"] == 0.0
            assert "No activity data" in result["recommendation"]
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_very_new_user(self):
        conn, path = make_test_db()
        try:
            _seed_content_items(conn, n=5)
            _seed_sessions(conn, user_id=1, n=2)
            from mandarin.quality.queue_model import queue_model
            result = queue_model(conn, user_id=1)

            # Should not crash, should return some result
            assert "utilization" in result
            assert isinstance(result["recommendation"], str)
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_littles_law_validation(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.queue_model import queue_model
            result = queue_model(conn, user_id=1)

            if result["stability"] and result["arrival_rate"] > 0:
                # Little's Law: L = lambda * W
                # The check should be near zero
                assert result["littles_law_check"] < 1.0, \
                    f"Little's Law violation: residual {result['littles_law_check']}"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_queue_capacity_respected(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.queue_model import queue_model
            result = queue_model(conn, user_id=1, queue_capacity=30)
            assert result["queue_capacity"] == 30
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ── Optimization Tests ───────────────────────────────────────────────

class TestOptimizeSession:

    def test_returns_valid_structure(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import optimize_session
            result = optimize_session(conn, user_id=1, time_budget_minutes=15)

            assert "items" in result
            assert "total_items" in result
            assert "new_items" in result
            assert "review_items" in result
            assert "estimated_minutes" in result
            assert "method" in result
            assert "constraints_satisfied" in result
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_respects_time_budget(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import optimize_session

            for budget in [5, 10, 15, 20]:
                result = optimize_session(conn, user_id=1,
                                          time_budget_minutes=budget)
                assert result["estimated_minutes"] <= budget + 0.5, \
                    f"Budget {budget}min exceeded: {result['estimated_minutes']}min"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_respects_cognitive_load_constraint(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import optimize_session, MAX_NEW_PER_5MIN

            result = optimize_session(conn, user_id=1, time_budget_minutes=15)
            five_min_slots = max(1, int(15 / 5))
            max_new = MAX_NEW_PER_5MIN * five_min_slots

            assert result["new_items"] <= max_new, \
                f"Cognitive load violated: {result['new_items']} new items > {max_new} max"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_review_fraction_constraint(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import optimize_session, MIN_REVIEW_FRACTION

            result = optimize_session(conn, user_id=1, time_budget_minutes=15)
            total = result["total_items"]
            if total > 0:
                review_frac = result["review_items"] / total
                assert review_frac >= MIN_REVIEW_FRACTION - 0.01, \
                    f"Review fraction {review_frac:.2f} < minimum {MIN_REVIEW_FRACTION}"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_empty_db_returns_empty_plan(self):
        conn, path = make_test_db()
        try:
            from mandarin.quality.optimization import optimize_session
            result = optimize_session(conn, user_id=1, time_budget_minutes=15)
            assert result["total_items"] == 0
            assert result["method"] == "empty"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_greedy_fallback_works(self):
        """Verify the greedy path works even if scipy is not available."""
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import _optimize_greedy, _estimate_retention_gain, _estimate_drill_time, _get_candidate_items

            candidates = _get_candidate_items(conn, user_id=1)
            for item in candidates:
                item["_retention_gain"] = _estimate_retention_gain(item)
                item["_drill_time_min"] = _estimate_drill_time(item)
                item["_gain_per_minute"] = (
                    item["_retention_gain"] / max(item["_drill_time_min"], 0.01)
                )

            review = [i for i in candidates if not i.get("is_new")]
            new = [i for i in candidates if i.get("is_new")]
            review.sort(key=lambda x: x["_gain_per_minute"], reverse=True)
            new.sort(key=lambda x: x["_gain_per_minute"], reverse=True)

            result = _optimize_greedy(review, new, time_budget=15)
            assert result["method"] == "greedy"
            assert result["constraints_satisfied"] is True
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ── Decision Table Tests ─────────────────────────────────────────────

class TestDecisionTable:

    def test_returns_valid_structure(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import decision_table
            result = decision_table(conn, user_id=1)

            assert "matrix" in result
            assert "current_state" in result
            assert "recommendation" in result
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_all_cells_filled(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import decision_table
            result = decision_table(conn, user_id=1)

            return_probs = ["daily", "sporadic", "unknown"]
            queue_states = ["low", "medium", "high", "overflowed"]

            for rp in return_probs:
                assert rp in result["matrix"], f"Missing return probability: {rp}"
                for qs in queue_states:
                    cell = result["matrix"][rp].get(qs)
                    assert cell is not None, f"Missing cell: [{rp}][{qs}]"
                    assert "new_items" in cell, f"Missing new_items in [{rp}][{qs}]"
                    assert "rationale" in cell, f"Missing rationale in [{rp}][{qs}]"
                    assert isinstance(cell["new_items"], int), \
                        f"new_items not int in [{rp}][{qs}]"
                    assert cell["new_items"] >= 0, \
                        f"Negative new_items in [{rp}][{qs}]"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_recommendation_present(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import decision_table
            result = decision_table(conn, user_id=1)

            rec = result["recommendation"]
            assert "new_items" in rec
            assert "rationale" in rec
            assert isinstance(rec["new_items"], int)
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_no_data_still_works(self):
        conn, path = make_test_db()
        try:
            from mandarin.quality.optimization import decision_table
            result = decision_table(conn, user_id=1)
            assert "matrix" in result
            assert result["current_state"]["return_probability"] in ("daily", "sporadic", "unknown")
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ── Pareto Frontier Tests ────────────────────────────────────────────

class TestParetoFrontier:

    def test_returns_valid_structure(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import pareto_frontier
            result = pareto_frontier(conn, user_id=1)

            assert "pareto_points" in result
            assert "total_candidates_evaluated" in result
            assert "objectives" in result
            assert isinstance(result["pareto_points"], list)
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_pareto_points_are_non_dominated(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import pareto_frontier
            result = pareto_frontier(conn, user_id=1)

            points = result["pareto_points"]
            objectives = result["objectives"]

            for i, p in enumerate(points):
                for j, q in enumerate(points):
                    if i == j:
                        continue
                    # q should NOT dominate p (all >= and at least one >)
                    all_ge = all(q[o] >= p[o] for o in objectives)
                    any_gt = any(q[o] > p[o] for o in objectives)
                    assert not (all_ge and any_gt), \
                        f"Point {i} is dominated by point {j}"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_pareto_points_have_required_fields(self):
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            from mandarin.quality.optimization import pareto_frontier
            result = pareto_frontier(conn, user_id=1)

            required = {"session_minutes", "total_items", "new_items",
                        "review_items", "retention_rate", "breadth_coverage",
                        "time_efficiency"}
            for point in result["pareto_points"]:
                for field in required:
                    assert field in point, f"Missing field {field} in Pareto point"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_empty_db_returns_empty_frontier(self):
        conn, path = make_test_db()
        try:
            from mandarin.quality.optimization import pareto_frontier
            result = pareto_frontier(conn, user_id=1)
            # Should return without error; may have 0 points
            assert "pareto_points" in result
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ── Scipy Graceful Degradation ───────────────────────────────────────

class TestScipyFallback:

    def test_optimize_works_without_scipy(self):
        """Optimization should work even if scipy is not installed."""
        conn, path = make_test_db()
        try:
            _seed_full(conn)
            # Monkey-patch to simulate scipy unavailability
            import sys
            scipy_backup = sys.modules.get("scipy")
            scipy_opt_backup = sys.modules.get("scipy.optimize")
            sys.modules["scipy"] = None
            sys.modules["scipy.optimize"] = None

            try:
                from mandarin.quality.optimization import _optimize_greedy, _estimate_retention_gain, _estimate_drill_time, _get_candidate_items

                candidates = _get_candidate_items(conn, user_id=1)
                for item in candidates:
                    item["_retention_gain"] = _estimate_retention_gain(item)
                    item["_drill_time_min"] = _estimate_drill_time(item)
                    item["_gain_per_minute"] = (
                        item["_retention_gain"] / max(item["_drill_time_min"], 0.01)
                    )

                review = [i for i in candidates if not i.get("is_new")]
                new = [i for i in candidates if i.get("is_new")]

                result = _optimize_greedy(review, new, time_budget=15)
                assert result["method"] == "greedy"
                assert result["constraints_satisfied"] is True
            finally:
                # Restore scipy
                if scipy_backup is not None:
                    sys.modules["scipy"] = scipy_backup
                else:
                    sys.modules.pop("scipy", None)
                if scipy_opt_backup is not None:
                    sys.modules["scipy.optimize"] = scipy_opt_backup
                else:
                    sys.modules.pop("scipy.optimize", None)
        finally:
            conn.close()
            path.unlink(missing_ok=True)
