"""Tests for mandarin.experiments.governance — pre-registration and audit."""

from tests.shared_db import make_test_db
from mandarin.experiments.governance import (
    validate_pre_registration,
    freeze_config,
    log_audit_event,
    check_config_change_allowed,
)


def _make_experiment(conn, name="gov_test", **kwargs):
    defaults = {
        "name": name,
        "status": "draft",
        "variants": '["control","treatment"]',
        "hypothesis": "Treatment improves completion rate",
        "primary_metric": "completion_rate",
        "min_sample_size": 100,
        "outcome_window_days": 14,
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    conn.execute(
        f"INSERT OR IGNORE INTO experiment ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    conn.commit()
    return conn.execute("SELECT id FROM experiment WHERE name = ?", (name,)).fetchone()["id"]


def test_validate_missing_experiment():
    conn = make_test_db()
    valid, errors, warnings = validate_pre_registration(conn, 9999)
    assert valid is False
    assert len(errors) > 0


def test_validate_valid_experiment():
    conn = make_test_db()
    exp_id = _make_experiment(conn)
    valid, errors, warnings = validate_pre_registration(conn, exp_id)
    assert isinstance(valid, bool)
    assert isinstance(errors, list)
    assert isinstance(warnings, list)


def test_validate_missing_hypothesis():
    conn = make_test_db()
    exp_id = _make_experiment(conn, name="no_hyp_gov", hypothesis=None)
    valid, errors, warnings = validate_pre_registration(conn, exp_id)
    # Missing hypothesis means either errors or warnings
    assert isinstance(errors, list)


def test_freeze_config_missing_experiment():
    conn = make_test_db()
    result = freeze_config(conn, 9999)
    assert result == {}


def test_freeze_config_valid():
    conn = make_test_db()
    exp_id = _make_experiment(conn, name="freeze_gov_test")
    result = freeze_config(conn, exp_id)
    assert isinstance(result, dict)


def test_log_audit_event():
    conn = make_test_db()
    exp_id = _make_experiment(conn, name="audit_gov_test")
    # Should not raise
    log_audit_event(conn, "test_action", experiment_id=exp_id, data={"detail": "value"})


def test_check_config_change_unfrozen():
    conn = make_test_db()
    exp_id = _make_experiment(conn, name="unfrozen_gov_test")
    allowed, reason = check_config_change_allowed(conn, exp_id, "hypothesis", "new hypothesis")
    assert isinstance(allowed, bool)
    assert isinstance(reason, str)
