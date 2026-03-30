"""Tests for mandarin.experiments.sequential — sequential stopping rules."""

from tests.shared_db import make_test_db
from mandarin.experiments.sequential import sequential_test


def _make_experiment(conn, name="seq_test", min_sample=100):
    conn.execute(
        "INSERT OR IGNORE INTO experiment "
        "(name, status, variants, min_sample_size, outcome_window_days) "
        "VALUES (?, 'running', '[\"control\",\"treatment\"]', ?, 7)",
        (name, min_sample),
    )
    conn.commit()
    return conn.execute("SELECT id FROM experiment WHERE name = ?", (name,)).fetchone()["id"]


def test_no_experiment_returns_insufficient():
    conn = make_test_db()
    result = sequential_test(conn, "nonexistent_experiment")
    assert result["recommendation"] == "insufficient_data"
    assert result["can_conclude"] is False


def test_no_assignments_returns_insufficient():
    conn = make_test_db()
    _make_experiment(conn, "empty_exp")
    result = sequential_test(conn, "empty_exp")
    assert result["recommendation"] == "insufficient_data"


def test_low_information_fraction():
    conn = make_test_db()
    exp_id = _make_experiment(conn, "low_info_exp", min_sample=1000)
    # Add only a few assignments — well below 10% of 2000 planned
    for i in range(5):
        conn.execute(
            "INSERT OR IGNORE INTO user (id, email, password_hash) VALUES (?, ?, 'x')",
            (100 + i, f"seq{i}@test.com"),
        )
        conn.execute(
            "INSERT INTO experiment_assignment (experiment_id, user_id, variant, assigned_at) "
            "VALUES (?, ?, ?, datetime('now', '-30 days'))",
            (exp_id, 100 + i, "control" if i % 2 == 0 else "treatment"),
        )
    conn.commit()
    result = sequential_test(conn, "low_info_exp")
    assert result["can_conclude"] is False


def test_result_has_required_keys():
    conn = make_test_db()
    _make_experiment(conn)
    result = sequential_test(conn, "seq_test")
    assert "can_conclude" in result
    assert "recommendation" in result
