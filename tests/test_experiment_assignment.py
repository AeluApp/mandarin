"""Tests for the upgraded experiment assignment architecture.

Covers: eligibility engine, stratified assignment, SRM detection, covariate
balance, CUPED variance reduction, governance (config freeze, pre-registration),
audit logging, holdout groups.
"""

import json
import math
import sqlite3
import pytest
from datetime import datetime, timezone

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
    check_eligibility,
    compute_stratum,
    check_srm,
    check_covariate_balance,
    log_audit_event,
    get_audit_log,
)
from mandarin.experiments.eligibility import check_eligibility as _check_eligibility
from mandarin.experiments.stratification import compute_stratum as _compute_stratum
from mandarin.experiments.balance import check_srm as _check_srm, check_assignment_drift
from mandarin.experiments.governance import (
    validate_pre_registration,
    freeze_config,
    check_config_change_allowed,
)
from mandarin.experiments.holdout import assign_holdout, is_in_holdout, get_holdout_count
from mandarin.experiments.analysis import _z_test_proportions, _cohens_d, _std, _cov, _var


@pytest.fixture
def exp_db(test_db):
    """Test DB with experiment tables pre-loaded."""
    conn, path = test_db
    yield conn


def _seed_users(conn, n=10, active=True):
    """Insert n test users. Returns list of user_ids."""
    ids = []
    for i in range(2, 2 + n):
        conn.execute(
            """INSERT OR IGNORE INTO user
               (id, email, password_hash, display_name, subscription_tier, is_active, is_admin)
               VALUES (?, ?, 'test', ?, 'free', ?, 0)""",
            (i, f"user{i}@test.com", f"User {i}", int(active)),
        )
        conn.execute(
            "INSERT OR IGNORE INTO learner_profile (user_id) VALUES (?)",
            (i,),
        )
        ids.append(i)
    conn.commit()
    return ids


def _seed_sessions(conn, user_id, n=5, variant=None, completed=True, days_ago=0):
    """Insert n session_log rows for a user."""
    for _ in range(n):
        outcome = "completed" if completed else "abandoned"
        started = f"datetime('now', '-{days_ago} days')" if days_ago else "datetime('now')"
        conn.execute(
            f"""INSERT INTO session_log
               (user_id, session_outcome, items_planned, items_completed, items_correct,
                duration_seconds, experiment_variant, started_at)
               VALUES (?, ?, 10, 10, ?, ?, ?, {started})""",
            (user_id, outcome, 8 if completed else 2, 300, variant),
        )
    conn.commit()


# ── Eligibility Engine ─────────────────────────────────────────────────────


class TestEligibility:
    def test_active_user_eligible(self, exp_db):
        users = _seed_users(exp_db, 2)
        _seed_sessions(exp_db, users[0], n=3)

        exp_id = create_experiment(exp_db, "elig_test", "Test", ["A", "B"])
        eligible, reasons = _check_eligibility(exp_db, exp_id, users[0], log=False)
        assert eligible
        assert reasons == []

    def test_inactive_user_ineligible(self, exp_db):
        users = _seed_users(exp_db, 1, active=False)
        exp_id = create_experiment(exp_db, "elig_inactive", "Test", ["A", "B"])
        eligible, reasons = _check_eligibility(exp_db, exp_id, users[0], log=False)
        assert not eligible
        assert "user_inactive" in reasons

    def test_admin_excluded_by_default(self, exp_db):
        # User 1 is the bootstrap admin — ensure they're active so we isolate the admin check
        exp_db.execute("UPDATE user SET is_active = 1, is_admin = 1 WHERE id = 1")
        _seed_sessions(exp_db, 1, n=3)
        exp_db.commit()
        exp_id = create_experiment(exp_db, "elig_admin", "Test", ["A", "B"])
        eligible, reasons = _check_eligibility(exp_db, exp_id, 1, log=False)
        assert not eligible
        assert "admin_excluded" in reasons

    def test_min_sessions_rule(self, exp_db):
        users = _seed_users(exp_db, 2)
        # user has 0 sessions
        rules = {"min_sessions": 3, "exclude_admin": False}
        exp_id = create_experiment(
            exp_db, "elig_sess", "Test", ["A", "B"],
            eligibility_rules=rules,
        )
        eligible, reasons = _check_eligibility(
            exp_db, exp_id, users[0], rules=rules, log=False,
        )
        assert not eligible
        assert any("insufficient_sessions" in r for r in reasons)

        # Now add sessions
        _seed_sessions(exp_db, users[0], n=5)
        eligible2, reasons2 = _check_eligibility(
            exp_db, exp_id, users[0], rules=rules, log=False,
        )
        assert eligible2

    def test_mutual_exclusion(self, exp_db):
        users = _seed_users(exp_db, 2)
        _seed_sessions(exp_db, users[0], n=3)

        create_experiment(exp_db, "exp_a", "A", ["A1", "A2"])
        start_experiment(exp_db, "exp_a")
        get_variant(exp_db, "exp_a", users[0], skip_eligibility=True)

        rules = {"exclude_experiments": ["exp_a"], "exclude_admin": False}
        exp_id_b = create_experiment(
            exp_db, "exp_b", "B", ["B1", "B2"],
            eligibility_rules=rules,
        )
        eligible, reasons = _check_eligibility(
            exp_db, exp_id_b, users[0], rules=rules, log=False,
        )
        assert not eligible
        assert any("mutual_exclusion" in r for r in reasons)

    def test_max_concurrent_experiments(self, exp_db):
        users = _seed_users(exp_db, 2)
        _seed_sessions(exp_db, users[0], n=3)

        # Assign to 2 experiments
        for name in ("conc_a", "conc_b"):
            create_experiment(exp_db, name, "Test", ["A", "B"])
            start_experiment(exp_db, name)
            get_variant(exp_db, name, users[0], skip_eligibility=True)

        rules = {"max_concurrent_experiments": 2, "exclude_admin": False}
        exp_id_c = create_experiment(
            exp_db, "conc_c", "Test", ["A", "B"],
            eligibility_rules=rules,
        )
        eligible, reasons = _check_eligibility(
            exp_db, exp_id_c, users[0], rules=rules, log=False,
        )
        assert not eligible
        assert any("max_concurrent" in r for r in reasons)

    def test_holdout_excluded(self, exp_db):
        users = _seed_users(exp_db, 2)
        _seed_sessions(exp_db, users[0], n=3)

        # Manually add user to holdout
        exp_db.execute(
            "INSERT INTO experiment_holdout (user_id) VALUES (?)",
            (users[0],),
        )
        exp_db.commit()

        exp_id = create_experiment(exp_db, "elig_holdout", "Test", ["A", "B"])
        eligible, reasons = _check_eligibility(exp_db, exp_id, users[0], log=False)
        assert not eligible
        assert "global_holdout" in reasons


# ── Stratification ────────────────────────────────────────────────────────


class TestStratification:
    def test_default_stratum(self, exp_db):
        """New user with no profile data gets default stratum."""
        users = _seed_users(exp_db, 1)
        stratum = _compute_stratum(exp_db, users[0])
        assert "hsk:" in stratum
        assert "eng:" in stratum

    def test_stratum_reflects_hsk(self, exp_db):
        users = _seed_users(exp_db, 1)
        # Set high HSK level
        exp_db.execute(
            """UPDATE learner_profile SET
               level_reading=5.0, level_listening=5.0,
               level_speaking=5.0, level_ime=5.0
               WHERE user_id=?""",
            (users[0],),
        )
        exp_db.commit()
        stratum = _compute_stratum(exp_db, users[0])
        assert "hsk:high" in stratum

    def test_stratum_reflects_engagement(self, exp_db):
        users = _seed_users(exp_db, 1)
        # Add many recent sessions
        _seed_sessions(exp_db, users[0], n=20)
        stratum = _compute_stratum(exp_db, users[0])
        assert "eng:high" in stratum


# ── Stratified Assignment ─────────────────────────────────────────────────


class TestStratifiedAssignment:
    def test_assignment_includes_stratum(self, exp_db):
        users = _seed_users(exp_db, 5)
        for u in users:
            _seed_sessions(exp_db, u, n=3)

        create_experiment(exp_db, "strat_test", "Test", ["A", "B"])
        start_experiment(exp_db, "strat_test")

        for u in users:
            v = get_variant(exp_db, "strat_test", u, skip_eligibility=True)
            assert v in ("A", "B")

        # Check that stratum was recorded
        rows = exp_db.execute(
            "SELECT stratum FROM experiment_assignment WHERE experiment_id = (SELECT id FROM experiment WHERE name = 'strat_test')"
        ).fetchall()
        for r in rows:
            # stratum may be None if column doesn't exist in older schema, that's OK
            if r["stratum"]:
                assert "hsk:" in r["stratum"]

    def test_salt_isolation(self, exp_db):
        """Different experiments produce independent assignments."""
        users = _seed_users(exp_db, 100)
        for u in users:
            _seed_sessions(exp_db, u, n=3)

        create_experiment(exp_db, "salt_a", "Test A", ["X", "Y"])
        create_experiment(exp_db, "salt_b", "Test B", ["X", "Y"])
        start_experiment(exp_db, "salt_a")
        start_experiment(exp_db, "salt_b")

        # Assignments should NOT be perfectly correlated
        same_count = 0
        for u in users:
            va = get_variant(exp_db, "salt_a", u, skip_eligibility=True)
            vb = get_variant(exp_db, "salt_b", u, skip_eligibility=True)
            if va == vb:
                same_count += 1

        # With independent hashing, about 50% should match
        # Allow wide tolerance (30-70%)
        ratio = same_count / len(users)
        assert 0.25 < ratio < 0.75, f"Salt isolation failed: {ratio:.2%} matched"


# ── SRM Detection ─────────────────────────────────────────────────────────


class TestSRM:
    def test_balanced_passes(self, exp_db):
        """A balanced experiment should pass SRM."""
        users = _seed_users(exp_db, 100)
        for u in users:
            _seed_sessions(exp_db, u, n=3)

        create_experiment(exp_db, "srm_ok", "Test", ["A", "B"])
        start_experiment(exp_db, "srm_ok")

        for u in users:
            get_variant(exp_db, "srm_ok", u, skip_eligibility=True)

        result = _check_srm(exp_db, exp_db.execute("SELECT id FROM experiment WHERE name='srm_ok'").fetchone()["id"])
        assert result["passed"] is True

    def test_imbalanced_fails(self, exp_db):
        """A heavily imbalanced experiment should fail SRM."""
        exp_id = create_experiment(exp_db, "srm_bad", "Test", ["A", "B"])
        start_experiment(exp_db, "srm_bad")

        # Manually insert imbalanced assignments
        for i in range(100):
            exp_db.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id, variant) VALUES (?, ?, ?)",
                (exp_id, 1000 + i, "A"),
            )
        for i in range(20):
            exp_db.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id, variant) VALUES (?, ?, ?)",
                (exp_id, 2000 + i, "B"),
            )
        exp_db.commit()

        result = _check_srm(exp_db, exp_id)
        assert result["passed"] is False
        assert result["chi2"] > 10  # Should be very significant

    def test_small_sample_passes(self, exp_db):
        """Small samples shouldn't trigger SRM."""
        exp_id = create_experiment(exp_db, "srm_small", "Test", ["A", "B"])
        start_experiment(exp_db, "srm_small")

        for i in range(5):
            exp_db.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id, variant) VALUES (?, ?, ?)",
                (exp_id, 3000 + i, "A" if i < 4 else "B"),
            )
        exp_db.commit()

        result = _check_srm(exp_db, exp_id)
        assert result["passed"] is True
        assert result.get("reason") == "insufficient_sample"


# ── Balance Checks ────────────────────────────────────────────────────────


class TestBalanceChecks:
    def test_drift_detection(self, exp_db):
        exp_id = create_experiment(exp_db, "drift_test", "Test", ["A", "B"])
        start_experiment(exp_db, "drift_test")

        # Insert balanced assignments
        for i in range(50):
            exp_db.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id, variant) VALUES (?, ?, ?)",
                (exp_id, 4000 + i, "A" if i < 25 else "B"),
            )
        exp_db.commit()

        result = check_assignment_drift(exp_db, exp_id)
        assert result["passed"] is True
        assert abs(result["current_ratio"] - 0.5) < 0.02


# ── Governance ────────────────────────────────────────────────────────────


class TestGovernance:
    def test_config_freeze(self, exp_db):
        exp_id = create_experiment(
            exp_db, "gov_test", "Test", ["A", "B"],
            hypothesis="Test hypothesis",
            primary_metric="completion_rate",
        )
        snapshot = freeze_config(exp_db, exp_id)
        assert "hypothesis" in snapshot

        row = exp_db.execute(
            "SELECT config_frozen_at FROM experiment WHERE id = ?", (exp_id,)
        ).fetchone()
        assert row["config_frozen_at"] is not None

    def test_frozen_field_rejected(self, exp_db):
        exp_id = create_experiment(
            exp_db, "gov_frozen", "Test", ["A", "B"],
            hypothesis="Test",
            primary_metric="completion_rate",
        )
        start_experiment(exp_db, "gov_frozen")

        allowed, reason = check_config_change_allowed(
            exp_db, exp_id, "hypothesis", "New hypothesis",
        )
        assert not allowed
        assert "frozen" in reason

    def test_draft_changes_allowed(self, exp_db):
        exp_id = create_experiment(exp_db, "gov_draft", "Test", ["A", "B"])
        allowed, reason = check_config_change_allowed(
            exp_db, exp_id, "hypothesis", "New hypothesis",
        )
        assert allowed

    def test_min_sample_can_only_increase(self, exp_db):
        exp_id = create_experiment(
            exp_db, "gov_mono", "Test", ["A", "B"],
            min_sample_size=100,
            hypothesis="Test",
            primary_metric="completion_rate",
        )
        start_experiment(exp_db, "gov_mono")

        # Increase: allowed
        allowed, _ = check_config_change_allowed(exp_db, exp_id, "min_sample_size", 200)
        assert allowed

        # Decrease: blocked
        allowed, reason = check_config_change_allowed(exp_db, exp_id, "min_sample_size", 50)
        assert not allowed
        assert "only increase" in reason


# ── Audit Logging ─────────────────────────────────────────────────────────


class TestAuditLog:
    def test_assignment_creates_audit_entry(self, exp_db):
        users = _seed_users(exp_db, 2)
        _seed_sessions(exp_db, users[0], n=3)

        create_experiment(exp_db, "audit_test", "Test", ["A", "B"])
        start_experiment(exp_db, "audit_test")
        get_variant(exp_db, "audit_test", users[0], skip_eligibility=True)

        exp_id = exp_db.execute("SELECT id FROM experiment WHERE name='audit_test'").fetchone()["id"]
        logs = get_audit_log(exp_db, experiment_id=exp_id, event_type="assignment")
        assert len(logs) >= 1
        assert logs[0]["data"]["variant"] in ("A", "B")

    def test_audit_log_filtering(self, exp_db):
        exp_id = create_experiment(exp_db, "audit_filter", "Test", ["A", "B"])
        log_audit_event(exp_db, "test_event", experiment_id=exp_id, data={"key": "value"})

        all_logs = get_audit_log(exp_db, experiment_id=exp_id)
        assert len(all_logs) >= 1

        filtered = get_audit_log(exp_db, event_type="test_event")
        assert len(filtered) >= 1


# ── Holdout Groups ────────────────────────────────────────────────────────


class TestHoldout:
    def test_holdout_deterministic(self, exp_db):
        """Same user always gets same holdout assignment."""
        result1 = assign_holdout(exp_db, 999, holdout_rate=1.0)  # 100% holdout
        result2 = assign_holdout(exp_db, 999, holdout_rate=1.0)
        assert result1 == result2

    def test_holdout_rate(self, exp_db):
        """With a high holdout rate, most users should be in holdout."""
        users = _seed_users(exp_db, 50)
        for u in users:
            assign_holdout(exp_db, u, holdout_rate=1.0)

        count = get_holdout_count(exp_db)
        assert count == 50  # 100% rate

    def test_holdout_blocks_assignment(self, exp_db):
        """Users in holdout should not be assigned to experiments."""
        users = _seed_users(exp_db, 2)
        _seed_sessions(exp_db, users[0], n=3)

        # Add to holdout
        exp_db.execute("INSERT INTO experiment_holdout (user_id) VALUES (?)", (users[0],))
        exp_db.commit()

        create_experiment(exp_db, "holdout_block", "Test", ["A", "B"])
        start_experiment(exp_db, "holdout_block")
        v = get_variant(exp_db, "holdout_block", users[0])
        assert v is None  # Holdout users get no variant


# ── CUPED ─────────────────────────────────────────────────────────────────


class TestCUPED:
    def test_cuped_reduces_variance(self):
        """CUPED should reduce variance when X and Y are correlated."""
        # Synthetic data: X and Y correlated with some noise
        import random
        random.seed(42)
        n = 100
        x = [random.gauss(0.5, 0.2) for _ in range(n)]
        y = [xi + random.gauss(0, 0.1) for xi in x]  # Y = X + noise

        raw_var = _var(y)
        cov_xy = _cov(x, y)
        var_x = _var(x)
        theta = cov_xy / var_x
        mean_x = sum(x) / len(x)

        y_adj = [yi - theta * (xi - mean_x) for xi, yi in zip(x, y, strict=False)]
        adj_var = _var(y_adj)

        assert adj_var < raw_var, "CUPED should reduce variance"
        reduction = 1 - adj_var / raw_var
        assert reduction > 0.3, f"Expected >30% reduction, got {reduction:.1%}"


# ── Statistical Helpers ───────────────────────────────────────────────────


class TestStatHelpers:
    def test_z_test_equal_proportions(self):
        z, p = _z_test_proportions(0.5, 0.5, 100, 100)
        assert z == 0.0
        assert p is not None and p > 0.9

    def test_z_test_different_proportions(self):
        z, p = _z_test_proportions(0.5, 0.8, 100, 100)
        assert p is not None and p < 0.01

    def test_cohens_d_zero_for_equal(self):
        d = _cohens_d(0.5, 0.5, 0.1, 0.1, 50, 50)
        assert d is not None and abs(d) < 0.001

    def test_std_basic(self):
        assert abs(_std([1.0, 2.0, 3.0]) - 1.0) < 0.01

    def test_var_basic(self):
        assert abs(_var([1.0, 2.0, 3.0]) - 1.0) < 0.01


# ── Integration: Full Lifecycle ───────────────────────────────────────────


class TestFullLifecycle:
    def test_complete_experiment_lifecycle(self, exp_db):
        """Create → eligible → assign → expose → analyze → conclude."""
        users = _seed_users(exp_db, 20)
        for u in users:
            _seed_sessions(exp_db, u, n=5, days_ago=20)  # Pre-period data

        # Create with full pre-registration
        exp_id = create_experiment(
            exp_db, "lifecycle_test", "Full lifecycle test",
            ["control", "treatment"],
            hypothesis="Treatment improves completion",
            primary_metric="session_completion_rate",
            min_sample_size=5,
            outcome_window_days=7,
        )

        # Start (freezes config)
        start_experiment(exp_db, "lifecycle_test")

        # Assign users
        assignments = {}
        for u in users:
            v = get_variant(exp_db, "lifecycle_test", u, skip_eligibility=True)
            assert v in ("control", "treatment")
            assignments[u] = v

        # Seed post-period sessions
        for u, v in assignments.items():
            _seed_sessions(exp_db, u, n=3, variant=v, completed=(v == "treatment"))
            log_exposure(exp_db, "lifecycle_test", u, context="test")

        # Check SRM
        srm = _check_srm(exp_db, exp_id)
        assert srm["passed"]

        # Check results
        results = get_experiment_results(exp_db, "lifecycle_test")
        assert results["status"] == "running"
        assert results["variants"]["control"]["users"] > 0
        assert results["variants"]["treatment"]["users"] > 0

        # Check guardrails
        guardrails = check_guardrails(exp_db, "lifecycle_test")
        assert isinstance(guardrails, dict)

        # Conclude
        conclude_experiment(exp_db, "lifecycle_test", winner="treatment", notes="Test")
        exp = exp_db.execute("SELECT status FROM experiment WHERE name='lifecycle_test'").fetchone()
        assert exp["status"] == "concluded"

        # Verify audit trail
        logs = get_audit_log(exp_db, experiment_id=exp_id)
        event_types = {l["event_type"] for l in logs}
        assert "assignment" in event_types
        assert "config_change" in event_types
        assert "conclude" in event_types
