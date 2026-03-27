"""Tests for untested experiments modules — governance, holdout, balance,
stratification, eligibility, audit.

Targets ~5.4% coverage lift for the mandarin.experiments package by exercising
helper functions and edge cases in modules that existing tests don't cover.
"""

import json
import sqlite3
import pytest

from mandarin.experiments.governance import (
    validate_pre_registration,
    freeze_config,
    check_config_change_allowed,
    log_ramp_change,
    REQUIRED_FIELDS,
    RECOMMENDED_FIELDS,
    FROZEN_FIELDS,
)
from mandarin.experiments.holdout import (
    assign_holdout,
    is_in_holdout,
    get_holdout_users,
    get_holdout_count,
)
from mandarin.experiments.balance import (
    check_srm,
    check_covariate_balance,
    check_assignment_drift,
    check_exposure_imbalance,
    _chi2_sf,
    _standardised_mean_diff,
)
from mandarin.experiments.stratification import (
    compute_stratum,
    validate_strata,
    get_stratum_sizes,
    DEFAULT_STRATIFICATION_CONFIG,
)
from mandarin.experiments.eligibility import (
    check_eligibility,
    DEFAULT_ELIGIBILITY,
)
from mandarin.experiments.audit import log_audit_event, get_audit_log
from mandarin.experiments.registry import (
    create_experiment,
    start_experiment,
    get_experiment,
    list_experiments,
)


@pytest.fixture
def exp_db(test_db):
    """Test DB with experiment tables."""
    conn, _path = test_db
    yield conn


def _make_experiment(conn, name="gov_exp", variants=None, start=False):
    """Helper: create (and optionally start) an experiment, return its id."""
    variants = variants or ["control", "treatment"]
    exp_id = create_experiment(conn, name, "A test experiment", variants)
    if start:
        start_experiment(conn, name)
    return exp_id


def _seed_users(conn, n=5, start_id=10):
    """Insert n test users and return their ids."""
    ids = []
    for i in range(start_id, start_id + n):
        conn.execute(
            """INSERT OR IGNORE INTO user (id, email, password_hash, display_name,
               subscription_tier, is_active)
               VALUES (?, ?, 'hash', ?, 'free', 1)""",
            (i, f"user{i}@test.com", f"User {i}"),
        )
        ids.append(i)
    conn.commit()
    return ids


def _seed_sessions(conn, user_id, n=3, completed=True, variant=None):
    """Seed session_log rows for a user."""
    outcome = "completed" if completed else "abandoned"
    for _ in range(n):
        conn.execute(
            """INSERT INTO session_log
               (user_id, session_outcome, items_planned, items_completed,
                items_correct, duration_seconds, experiment_variant)
               VALUES (?, ?, 10, 10, 8, 300, ?)""",
            (user_id, outcome, variant),
        )
    conn.commit()


# ── Governance ────────────────────────────────────────────────────────────


class TestValidatePreRegistration:
    def test_valid_draft(self, exp_db):
        exp_id = _make_experiment(exp_db, "gov_valid")
        valid, errors, warnings = validate_pre_registration(exp_db, exp_id)
        # Errors expected because hypothesis/primary_metric are empty
        assert isinstance(valid, bool)
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_nonexistent_experiment(self, exp_db):
        valid, errors, warnings = validate_pre_registration(exp_db, 99999)
        assert valid is False
        assert any("not found" in e for e in errors)

    def test_small_sample_warning(self, exp_db):
        exp_id = create_experiment(
            exp_db, "small_sample", "test", ["a", "b"],
            min_sample_size=5,
            hypothesis="test hyp",
            primary_metric="completion_rate",
        )
        _valid, _errors, warnings = validate_pre_registration(exp_db, exp_id)
        assert any("small" in w.lower() for w in warnings)


class TestFreezeConfig:
    def test_freeze_returns_snapshot(self, exp_db):
        exp_id = _make_experiment(exp_db, "freeze_test")
        snapshot = freeze_config(exp_db, exp_id)
        assert isinstance(snapshot, dict)
        assert "min_sample_size" in snapshot

    def test_freeze_nonexistent(self, exp_db):
        result = freeze_config(exp_db, 99999)
        assert result == {}


class TestCheckConfigChangeAllowed:
    def test_draft_allows_any_change(self, exp_db):
        exp_id = _make_experiment(exp_db, "draft_change")
        allowed, reason = check_config_change_allowed(exp_db, exp_id, "hypothesis", "new")
        assert allowed is True

    def test_running_blocks_frozen_field(self, exp_db):
        exp_id = _make_experiment(exp_db, "frozen_field", start=True)
        allowed, reason = check_config_change_allowed(exp_db, exp_id, "hypothesis", "new")
        assert allowed is False
        assert "frozen" in reason

    def test_running_allows_nonfrozen_field(self, exp_db):
        exp_id = _make_experiment(exp_db, "nonfrozen_field", start=True)
        allowed, _reason = check_config_change_allowed(
            exp_db, exp_id, "description", "updated",
        )
        assert allowed is True

    def test_nonexistent_experiment(self, exp_db):
        allowed, reason = check_config_change_allowed(exp_db, 99999, "x", "y")
        assert reason == "experiment not found"


class TestLogRampChange:
    def test_ramp_change_logged(self, exp_db):
        exp_id = _make_experiment(exp_db, "ramp_test")
        log_ramp_change(exp_db, exp_id, 50.0, 75.0, "Scaling up")
        logs = get_audit_log(exp_db, experiment_id=exp_id, event_type="ramp_change")
        assert len(logs) >= 1
        assert logs[0]["data"]["old_pct"] == 50.0


# ── Holdout ───────────────────────────────────────────────────────────────


class TestHoldout:
    def test_assign_and_check_holdout(self, exp_db):
        # Use a range of user_ids to get at least one holdout hit
        _seed_users(exp_db, 200, start_id=1000)
        holdout_count = 0
        for uid in range(1000, 1200):
            if assign_holdout(exp_db, uid, holdout_rate=1.0):
                holdout_count += 1
        # With rate=1.0 everyone should be holdout
        assert holdout_count == 200

    def test_is_in_holdout_false(self, exp_db):
        assert is_in_holdout(exp_db, 999999) is False

    def test_get_holdout_users_empty(self, exp_db):
        users = get_holdout_users(exp_db)
        assert isinstance(users, list)

    def test_get_holdout_count(self, exp_db):
        count = get_holdout_count(exp_db)
        assert isinstance(count, int)
        assert count >= 0

    def test_assign_holdout_deterministic(self, exp_db):
        uid = 5555
        _seed_users(exp_db, 1, start_id=uid)
        r1 = assign_holdout(exp_db, uid)
        r2 = assign_holdout(exp_db, uid)
        # Second call returns same result
        assert r1 == r2


# ── Balance ───────────────────────────────────────────────────────────────


class TestSRM:
    def test_srm_no_assignments(self, exp_db):
        exp_id = _make_experiment(exp_db, "srm_empty", start=True)
        result = check_srm(exp_db, exp_id)
        assert result["passed"] is True

    def test_srm_balanced(self, exp_db):
        exp_id = _make_experiment(exp_db, "srm_balanced", start=True)
        users = _seed_users(exp_db, 40, start_id=2000)
        now = "2026-01-01 00:00:00"
        for uid in users[:20]:
            exp_db.execute(
                "INSERT OR IGNORE INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, ?, 'control', ?)",
                (exp_id, uid, now),
            )
        for uid in users[20:]:
            exp_db.execute(
                "INSERT OR IGNORE INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, ?, 'treatment', ?)",
                (exp_id, uid, now),
            )
        exp_db.commit()
        result = check_srm(exp_db, exp_id)
        assert result["passed"] is True

    def test_srm_insufficient_sample(self, exp_db):
        exp_id = _make_experiment(exp_db, "srm_small", start=True)
        now = "2026-01-01 00:00:00"
        exp_db.execute(
            "INSERT INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, 9001, 'control', ?)",
            (exp_id, now),
        )
        exp_db.execute(
            "INSERT INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, 9002, 'treatment', ?)",
            (exp_id, now),
        )
        exp_db.commit()
        result = check_srm(exp_db, exp_id)
        assert result["passed"] is True
        assert result.get("reason") == "insufficient_sample"


class TestCovariateBalance:
    def test_empty_experiment(self, exp_db):
        exp_id = _make_experiment(exp_db, "cov_empty", start=True)
        result = check_covariate_balance(exp_db, exp_id)
        assert result["passed"] is True

    def test_nonexistent_experiment(self, exp_db):
        result = check_covariate_balance(exp_db, 99999)
        assert result["passed"] is True


class TestAssignmentDrift:
    def test_no_assignments(self, exp_db):
        exp_id = _make_experiment(exp_db, "drift_empty", start=True)
        result = check_assignment_drift(exp_db, exp_id)
        assert result["passed"] is True

    def test_balanced_assignments(self, exp_db):
        exp_id = _make_experiment(exp_db, "drift_ok", start=True)
        users = _seed_users(exp_db, 60, start_id=3000)
        now = "2026-01-01 00:00:00"
        for uid in users[:30]:
            exp_db.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, ?, 'control', ?)",
                (exp_id, uid, now),
            )
        for uid in users[30:]:
            exp_db.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) VALUES (?, ?, 'treatment', ?)",
                (exp_id, uid, now),
            )
        exp_db.commit()
        result = check_assignment_drift(exp_db, exp_id)
        assert result["passed"] is True


class TestExposureImbalance:
    def test_no_experiment(self, exp_db):
        result = check_exposure_imbalance(exp_db, 99999)
        assert result["passed"] is True


class TestChi2SF:
    def test_df1(self):
        p = _chi2_sf(3.84, df=1)
        assert 0.04 < p < 0.06

    def test_general_df(self):
        p = _chi2_sf(5.99, df=2)
        assert 0.0 <= p <= 1.0


class TestStandardisedMeanDiff:
    def test_equal_lists(self):
        smd = _standardised_mean_diff([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert smd is not None
        assert abs(smd) < 0.01

    def test_too_small(self):
        assert _standardised_mean_diff([1.0], [2.0]) is None


# ── Stratification ────────────────────────────────────────────────────────


class TestStratification:
    def test_default_stratum(self, exp_db):
        s = compute_stratum(exp_db, 1)
        assert isinstance(s, str)
        assert "hsk:" in s or "eng:" in s or s == "default"

    def test_tenure_band_variable(self, exp_db):
        config = {"variables": ["tenure_band"]}
        s = compute_stratum(exp_db, 1, config=config)
        assert "ten:" in s

    def test_unknown_variable(self, exp_db):
        config = {"variables": ["nonexistent_var"]}
        s = compute_stratum(exp_db, 1, config=config)
        assert s == "default"

    def test_validate_strata_empty(self, exp_db):
        exp_id = _make_experiment(exp_db, "strata_empty", start=True)
        result = validate_strata(exp_db, exp_id)
        assert "strata" in result
        assert "warnings" in result

    def test_get_stratum_sizes_empty(self, exp_db):
        exp_id = _make_experiment(exp_db, "sizes_empty", start=True)
        sizes = get_stratum_sizes(exp_db, exp_id)
        assert isinstance(sizes, dict)


# ── Eligibility ───────────────────────────────────────────────────────────


class TestEligibility:
    def test_admin_excluded(self, exp_db):
        exp_id = _make_experiment(exp_db, "elig_admin")
        # Make user 1 an active admin so the admin exclusion fires
        exp_db.execute(
            "UPDATE user SET is_active = 1, is_admin = 1 WHERE id = 1",
        )
        exp_db.commit()
        _seed_sessions(exp_db, 1, n=2, completed=True)
        eligible, reasons = check_eligibility(exp_db, exp_id, 1)
        assert "admin_excluded" in reasons

    def test_inactive_user(self, exp_db):
        exp_id = _make_experiment(exp_db, "elig_inactive")
        # Create an inactive user
        exp_db.execute(
            """INSERT OR IGNORE INTO user (id, email, password_hash, display_name,
               subscription_tier, is_active)
               VALUES (8888, 'inactive@t.com', 'hash', 'Inactive', 'free', 0)""",
        )
        exp_db.commit()
        eligible, reasons = check_eligibility(exp_db, exp_id, 8888)
        assert "user_inactive" in reasons

    def test_eligible_user(self, exp_db):
        exp_id = _make_experiment(exp_db, "elig_ok")
        _seed_users(exp_db, 1, start_id=7777)
        _seed_sessions(exp_db, 7777, n=3, completed=True)
        eligible, reasons = check_eligibility(
            exp_db, exp_id, 7777,
            rules={"min_sessions": 1, "exclude_admin": True},
        )
        assert eligible is True
        assert reasons == []


# ── Audit ─────────────────────────────────────────────────────────────────


class TestAudit:
    def test_log_and_retrieve(self, exp_db):
        exp_id = _make_experiment(exp_db, "audit_test")
        log_audit_event(exp_db, "test_event", experiment_id=exp_id, data={"key": "val"})
        logs = get_audit_log(exp_db, experiment_id=exp_id, event_type="test_event")
        assert len(logs) >= 1
        assert logs[0]["data"]["key"] == "val"

    def test_get_audit_log_empty(self, exp_db):
        logs = get_audit_log(exp_db, experiment_id=99999)
        assert logs == []

    def test_get_audit_log_no_filter(self, exp_db):
        exp_id = _make_experiment(exp_db, "audit_all")
        log_audit_event(exp_db, "ev1", experiment_id=exp_id)
        logs = get_audit_log(exp_db)
        assert len(logs) >= 1


# ── Registry extras ───────────────────────────────────────────────────────


class TestRegistryExtras:
    def test_get_experiment(self, exp_db):
        _make_experiment(exp_db, "get_test")
        exp = get_experiment(exp_db, "get_test")
        assert exp is not None
        assert exp["name"] == "get_test"

    def test_get_experiment_nonexistent(self, exp_db):
        assert get_experiment(exp_db, "nope") is None

    def test_list_experiments_all(self, exp_db):
        _make_experiment(exp_db, "list_all_1")
        _make_experiment(exp_db, "list_all_2")
        exps = list_experiments(exp_db)
        assert len(exps) >= 2
