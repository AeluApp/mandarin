"""Tests for the experiment infrastructure — A/B testing with proper
assignment, exposure logging, results analysis, guardrails, and
sequential testing (O'Brien-Fleming spending function).

Covers: CRUD lifecycle, deterministic assignment, exposure logging,
results computation, z-test math, Cohen's d, sequential testing,
guardrail checks.
"""

import json
import math
import sqlite3
import pytest
from pathlib import Path

from mandarin.experiments import (
    create_experiment,
    start_experiment,
    pause_experiment,
    conclude_experiment,
    get_variant,
    log_exposure,
    get_experiment_results,
    check_guardrails,
    sequential_test,
    list_experiments,
    _z_test_proportions,
    _cohens_d,
    _confidence_interval_proportion,
    _obrien_fleming_boundary,
    _ci_difference,
    _std,
)


@pytest.fixture
def exp_db(test_db):
    """Test DB with experiment tables pre-loaded (via schema.sql / migration)."""
    conn, path = test_db
    # Schema already has experiment, experiment_assignment, experiment_exposure,
    # session_log tables from init_db + _migrate.
    yield conn


def _seed_users(conn, n=10):
    """Insert n test users. Returns list of user_ids."""
    ids = []
    for i in range(2, 2 + n):
        conn.execute(
            """INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
               VALUES (?, ?, 'test', ?, 'free')""",
            (i, f"user{i}@test.com", f"User {i}"),
        )
        ids.append(i)
    conn.commit()
    return ids


def _seed_sessions(conn, user_id, n=5, variant=None, completed=True):
    """Insert n session_log rows for a user."""
    for _ in range(n):
        outcome = "completed" if completed else "abandoned"
        conn.execute(
            """INSERT INTO session_log
               (user_id, session_outcome, items_planned, items_completed, items_correct,
                duration_seconds, experiment_variant)
               VALUES (?, ?, 10, 10, ?, ?, ?)""",
            (user_id, outcome, 8 if completed else 2, 300, variant),
        )
    conn.commit()


# ── CRUD Lifecycle ──────────────────────────────────────────────────────────


class TestExperimentLifecycle:
    def test_create_experiment(self, exp_db):
        exp_id = create_experiment(exp_db, "test_exp", "A test", ["control", "treatment"])
        assert exp_id is not None
        row = exp_db.execute("SELECT * FROM experiment WHERE id = ?", (exp_id,)).fetchone()
        assert row["name"] == "test_exp"
        assert row["status"] == "draft"
        assert json.loads(row["variants"]) == ["control", "treatment"]

    def test_start_experiment(self, exp_db):
        create_experiment(exp_db, "start_test", "Test", ["a", "b"])
        start_experiment(exp_db, "start_test")
        row = exp_db.execute("SELECT status FROM experiment WHERE name = 'start_test'").fetchone()
        assert row["status"] == "running"

    def test_start_only_from_draft(self, exp_db):
        create_experiment(exp_db, "running_test", "Test", ["a", "b"])
        start_experiment(exp_db, "running_test")
        # Starting again should be a no-op (already running)
        start_experiment(exp_db, "running_test")
        row = exp_db.execute("SELECT status FROM experiment WHERE name = 'running_test'").fetchone()
        assert row["status"] == "running"

    def test_pause_experiment(self, exp_db):
        create_experiment(exp_db, "pause_test", "Test", ["a", "b"])
        start_experiment(exp_db, "pause_test")
        pause_experiment(exp_db, "pause_test")
        row = exp_db.execute("SELECT status FROM experiment WHERE name = 'pause_test'").fetchone()
        assert row["status"] == "paused"

    def test_conclude_experiment(self, exp_db):
        create_experiment(exp_db, "conclude_test", "Test", ["control", "treatment"])
        start_experiment(exp_db, "conclude_test")

        # Seed some data so conclude can gather results
        users = _seed_users(exp_db, 4)
        for uid in users[:2]:
            get_variant(exp_db, "conclude_test", uid)
            _seed_sessions(exp_db, uid, n=3, variant="control")
        for uid in users[2:]:
            get_variant(exp_db, "conclude_test", uid)
            _seed_sessions(exp_db, uid, n=3, variant="treatment")

        conclude_experiment(exp_db, "conclude_test", winner="treatment", notes="Treatment wins")
        row = exp_db.execute("SELECT status, conclusion FROM experiment WHERE name = 'conclude_test'").fetchone()
        assert row["status"] == "concluded"
        conclusion = json.loads(row["conclusion"])
        assert conclusion["winner"] == "treatment"
        assert conclusion["notes"] == "Treatment wins"
        assert "decided_at" in conclusion

    def test_list_experiments(self, exp_db):
        create_experiment(exp_db, "list_a", "A", ["x", "y"])
        create_experiment(exp_db, "list_b", "B", ["x", "y"])
        start_experiment(exp_db, "list_b")

        all_exps = list_experiments(exp_db)
        assert len(all_exps) >= 2

        running = list_experiments(exp_db, status="running")
        assert all(e["status"] == "running" for e in running)

        draft = list_experiments(exp_db, status="draft")
        assert all(e["status"] == "draft" for e in draft)


# ── Assignment & Exposure ───────────────────────────────────────────────────


class TestAssignment:
    def test_deterministic_assignment(self, exp_db):
        """Same user gets same variant across repeated calls."""
        create_experiment(exp_db, "det_test", "Test", ["A", "B"])
        start_experiment(exp_db, "det_test")
        v1 = get_variant(exp_db, "det_test", 1)
        v2 = get_variant(exp_db, "det_test", 1)
        assert v1 == v2
        assert v1 in ("A", "B")

    def test_distribution_roughly_uniform(self, exp_db):
        """Over many users, variants should be roughly balanced."""
        create_experiment(exp_db, "dist_test", "Test", ["A", "B"], traffic_pct=100.0)
        start_experiment(exp_db, "dist_test")
        users = _seed_users(exp_db, 200)
        counts = {"A": 0, "B": 0}
        for uid in users:
            v = get_variant(exp_db, "dist_test", uid)
            if v:
                counts[v] += 1
        total = counts["A"] + counts["B"]
        assert total > 0
        # Allow 60/40 split as reasonable tolerance for SHA256 hashing
        assert counts["A"] / total > 0.3
        assert counts["B"] / total > 0.3

    def test_not_running_returns_none(self, exp_db):
        """Draft experiment should not assign variants."""
        create_experiment(exp_db, "draft_test", "Test", ["A", "B"])
        v = get_variant(exp_db, "draft_test", 1)
        assert v is None

    def test_traffic_pct_excludes(self, exp_db):
        """Traffic percentage limits enrollment."""
        create_experiment(exp_db, "traffic_test", "Test", ["A", "B"], traffic_pct=0.01)
        start_experiment(exp_db, "traffic_test")
        # With 0.01% traffic, virtually no one should be assigned
        users = _seed_users(exp_db, 50)
        assigned = sum(1 for uid in users if get_variant(exp_db, "traffic_test", uid) is not None)
        # At 0.01%, expect ~0 of 50 users (allow some)
        assert assigned < 10

    def test_nonexistent_experiment_returns_none(self, exp_db):
        assert get_variant(exp_db, "nonexistent", 1) is None


class TestExposure:
    def test_log_exposure_creates_row(self, exp_db):
        create_experiment(exp_db, "exposure_test", "Test", ["A", "B"])
        start_experiment(exp_db, "exposure_test")
        get_variant(exp_db, "exposure_test", 1)
        log_exposure(exp_db, "exposure_test", 1, context="session_planning")

        row = exp_db.execute(
            "SELECT * FROM experiment_exposure WHERE user_id = 1"
        ).fetchone()
        assert row is not None
        assert row["context"] == "session_planning"

    def test_log_exposure_missing_experiment(self, exp_db):
        """Should not raise on missing experiment."""
        log_exposure(exp_db, "nonexistent", 1, context="test")

    def test_log_exposure_unassigned_user(self, exp_db):
        """Should not create exposure for unassigned user."""
        create_experiment(exp_db, "unassigned_test", "Test", ["A", "B"])
        start_experiment(exp_db, "unassigned_test")
        log_exposure(exp_db, "unassigned_test", 999, context="test")
        row = exp_db.execute(
            "SELECT * FROM experiment_exposure WHERE user_id = 999"
        ).fetchone()
        assert row is None


# ── Results & Analysis ──────────────────────────────────────────────────────


class TestResults:
    def test_results_with_data(self, exp_db):
        create_experiment(exp_db, "results_test", "Test", ["control", "treatment"], min_sample_size=2)
        start_experiment(exp_db, "results_test")

        users = _seed_users(exp_db, 20)
        for uid in users[:10]:
            get_variant(exp_db, "results_test", uid)
            _seed_sessions(exp_db, uid, n=5, variant="control", completed=True)
        for uid in users[10:]:
            get_variant(exp_db, "results_test", uid)
            _seed_sessions(exp_db, uid, n=5, variant="treatment", completed=True)

        results = get_experiment_results(exp_db, "results_test")
        assert results["experiment_name"] == "results_test"
        assert "control" in results["variants"]
        assert "treatment" in results["variants"]
        assert results["variants"]["control"]["users"] > 0
        assert results["variants"]["treatment"]["users"] > 0

    def test_results_empty_experiment(self, exp_db):
        create_experiment(exp_db, "empty_test", "Test", ["A", "B"])
        results = get_experiment_results(exp_db, "empty_test")
        assert results["experiment_name"] == "empty_test"

    def test_results_nonexistent(self, exp_db):
        results = get_experiment_results(exp_db, "nonexistent")
        assert "error" in results


# ── Statistical Functions ───────────────────────────────────────────────────


class TestZTest:
    def test_known_significant(self):
        """p1=0.5, p2=0.7, n1=n2=200 → should be significant."""
        z, p = _z_test_proportions(0.5, 0.7, 200, 200)
        assert p is not None
        assert p < 0.05

    def test_known_not_significant(self):
        """p1=0.50, p2=0.51, n1=n2=30 → should not be significant."""
        z, p = _z_test_proportions(0.50, 0.51, 30, 30)
        assert p is not None
        assert p > 0.05

    def test_zero_n(self):
        z, p = _z_test_proportions(0.5, 0.7, 0, 100)
        assert z is None and p is None

    def test_p_equals_zero(self):
        z, p = _z_test_proportions(0.0, 0.0, 100, 100)
        assert z is None and p is None

    def test_p_equals_one(self):
        z, p = _z_test_proportions(1.0, 1.0, 100, 100)
        assert z is None and p is None

    def test_symmetry(self):
        z1, p1 = _z_test_proportions(0.3, 0.5, 100, 100)
        z2, p2 = _z_test_proportions(0.5, 0.3, 100, 100)
        assert p1 == pytest.approx(p2, abs=0.001)


class TestCohensD:
    def test_known_effect(self):
        d = _cohens_d(0.5, 0.3, 0.1, 0.1, 100, 100)
        assert d is not None
        assert d > 0  # mean1 > mean2

    def test_small_n(self):
        assert _cohens_d(0.5, 0.3, 0.1, 0.1, 1, 1) is None

    def test_zero_variance(self):
        assert _cohens_d(0.5, 0.5, 0.0, 0.0, 10, 10) is None


class TestConfidenceInterval:
    def test_known_ci(self):
        low, high = _confidence_interval_proportion(0.5, 100)
        assert low < 0.5 < high
        assert low > 0.3
        assert high < 0.7

    def test_zero_n(self):
        assert _confidence_interval_proportion(0.5, 0) == (0.0, 0.0)

    def test_bounds_in_range(self):
        low, high = _confidence_interval_proportion(0.05, 20)
        assert 0.0 <= low <= high <= 1.0


class TestCIDifference:
    def test_basic(self):
        low, high = _ci_difference(0.5, 0.7, 100, 100)
        assert low > 0  # treatment is better
        assert high > low

    def test_zero_n(self):
        assert _ci_difference(0.5, 0.7, 0, 100) == (0.0, 0.0)


class TestStd:
    def test_known_values(self):
        s = _std([1.0, 2.0, 3.0, 4.0, 5.0])
        assert s == pytest.approx(math.sqrt(2.5), abs=0.01)

    def test_single_value(self):
        assert _std([5.0]) == 0.0

    def test_empty(self):
        assert _std([]) == 0.0


# ── O'Brien-Fleming & Sequential Testing ────────────────────────────────────


class TestOBrienFleming:
    def test_early_look_very_conservative(self):
        """At 10% information fraction, adjusted alpha should be tiny."""
        alpha = _obrien_fleming_boundary(0.05, 0.1)
        assert alpha < 0.001

    def test_full_information_equals_alpha(self):
        """At 100% information, adjusted alpha should be close to overall alpha."""
        alpha = _obrien_fleming_boundary(0.05, 1.0)
        assert alpha == pytest.approx(0.05, abs=0.01)

    def test_monotonically_increasing(self):
        """Alpha should increase as information fraction increases."""
        alphas = [_obrien_fleming_boundary(0.05, t) for t in [0.2, 0.4, 0.6, 0.8, 1.0]]
        for i in range(1, len(alphas)):
            assert alphas[i] >= alphas[i - 1]

    def test_invalid_fraction(self):
        assert _obrien_fleming_boundary(0.05, 0) == 0.0
        assert _obrien_fleming_boundary(0.05, -1) == 0.0


class TestSequentialTest:
    def test_insufficient_data(self, exp_db):
        create_experiment(exp_db, "seq_empty", "Test", ["A", "B"])
        result = sequential_test(exp_db, "seq_empty")
        assert result["recommendation"] == "insufficient_data"

    def test_nonexistent_experiment(self, exp_db):
        result = sequential_test(exp_db, "nonexistent")
        assert result["recommendation"] == "insufficient_data"

    def test_with_data_returns_recommendation(self, exp_db):
        create_experiment(exp_db, "seq_data", "Test", ["control", "treatment"], min_sample_size=5)
        start_experiment(exp_db, "seq_data")

        users = _seed_users(exp_db, 20)
        for uid in users[:10]:
            get_variant(exp_db, "seq_data", uid)
            _seed_sessions(exp_db, uid, n=5, variant="control", completed=True)
        for uid in users[10:]:
            get_variant(exp_db, "seq_data", uid)
            _seed_sessions(exp_db, uid, n=5, variant="treatment", completed=True)

        result = sequential_test(exp_db, "seq_data")
        assert result["recommendation"] in ("continue", "stop_winner", "stop_futility", "insufficient_data")
        assert "information_fraction" in result
        assert "adjusted_alpha" in result


# ── Guardrails ──────────────────────────────────────────────────────────────


class TestGuardrails:
    def test_no_degradation(self, exp_db):
        """Same completion rate → no guardrail triggers."""
        create_experiment(exp_db, "guard_ok", "Test", ["control", "treatment"])
        start_experiment(exp_db, "guard_ok")

        users = _seed_users(exp_db, 10)
        for uid in users[:5]:
            get_variant(exp_db, "guard_ok", uid)
            _seed_sessions(exp_db, uid, n=5, variant="control", completed=True)
        for uid in users[5:]:
            get_variant(exp_db, "guard_ok", uid)
            _seed_sessions(exp_db, uid, n=5, variant="treatment", completed=True)

        guardrails = check_guardrails(exp_db, "guard_ok")
        if "session_completion_rate" in guardrails:
            assert guardrails["session_completion_rate"]["degraded"] is False

    def test_degradation_detected(self, exp_db):
        """Treatment with much worse completion → guardrail triggers."""
        exp_id = create_experiment(exp_db, "guard_bad", "Test", ["control", "treatment"])
        start_experiment(exp_db, "guard_bad")

        users = _seed_users(exp_db, 10)
        now = "2026-01-01 00:00:00"
        # Directly assign variants to avoid hash-based randomness
        for uid in users[:5]:
            exp_db.execute(
                "INSERT OR IGNORE INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, ?, 'control', ?)",
                (exp_id, uid, now))
            _seed_sessions(exp_db, uid, n=10, variant="control", completed=True)
        for uid in users[5:]:
            exp_db.execute(
                "INSERT OR IGNORE INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, ?, 'treatment', ?)",
                (exp_id, uid, now))
            _seed_sessions(exp_db, uid, n=10, variant="treatment", completed=False)
        exp_db.commit()

        guardrails = check_guardrails(exp_db, "guard_bad")
        assert "session_completion_rate" in guardrails
        assert guardrails["session_completion_rate"]["degraded"] is True

    def test_empty_experiment(self, exp_db):
        create_experiment(exp_db, "guard_empty", "Test", ["A", "B"])
        guardrails = check_guardrails(exp_db, "guard_empty")
        assert isinstance(guardrails, dict)

    def test_nonexistent_experiment(self, exp_db):
        guardrails = check_guardrails(exp_db, "nonexistent")
        assert guardrails == {}
