"""Tests for the autonomous experiment daemon.

Validates:
- Tick with no running experiments is a no-op
- Tick concludes winner when sequential test recommends stop_winner
- Tick pauses on guardrail degradation
- Tick advances rollout stages
- Tick proposes experiments from churn signals
- Tick auto-starts top proposal when no conflicts
- Tick skips start when running experiment exists
"""

import json
from datetime import datetime, timedelta, timezone, UTC
from unittest.mock import patch

import pytest

from mandarin.experiments import (
    create_experiment,
    start_experiment,
    conclude_experiment,
)
from mandarin.feature_flags import set_flag
from mandarin.web.experiment_daemon import _daemon_tick


@pytest.fixture
def daemon_db(test_db):
    """Test DB with experiment + daemon tables."""
    conn, path = test_db
    yield conn


def _seed_users(conn, n=10):
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


def _assign_variant(conn, experiment_name, user_id):
    """Directly assign a variant (bypass traffic % check)."""
    from mandarin.experiments import get_variant
    return get_variant(conn, experiment_name, user_id)


class TestDaemonTick:
    def test_tick_no_experiments_is_noop(self, daemon_db):
        """Empty DB — daemon tick should complete without error."""
        _daemon_tick(daemon_db)

    def test_tick_concludes_winner(self, daemon_db):
        """Daemon should auto-conclude when sequential test says stop_winner."""
        create_experiment(daemon_db, "auto_conclude", "Test", ["control", "treatment"], min_sample_size=5)
        start_experiment(daemon_db, "auto_conclude")

        users = _seed_users(daemon_db, 20)
        for uid in users[:10]:
            _assign_variant(daemon_db, "auto_conclude", uid)
            _seed_sessions(daemon_db, uid, n=10, variant="control", completed=True)
        for uid in users[10:]:
            _assign_variant(daemon_db, "auto_conclude", uid)
            _seed_sessions(daemon_db, uid, n=10, variant="treatment", completed=True)

        with patch("mandarin.web.experiment_daemon.sequential_test") as mock_seq:
            mock_seq.return_value = {
                "can_conclude": True,
                "recommendation": "stop_winner",
                "current_p": 0.01,
                "information_fraction": 1.0,
                "adjusted_alpha": 0.05,
            }
            _daemon_tick(daemon_db)

        row = daemon_db.execute(
            "SELECT status FROM experiment WHERE name = 'auto_conclude'"
        ).fetchone()
        assert row["status"] == "concluded"

    def test_tick_pauses_on_guardrail_degradation(self, daemon_db):
        """Daemon should pause experiment when guardrails degrade."""
        create_experiment(daemon_db, "guard_pause", "Test", ["control", "treatment"])
        start_experiment(daemon_db, "guard_pause")

        users = _seed_users(daemon_db, 10)
        for uid in users[:5]:
            _assign_variant(daemon_db, "guard_pause", uid)
        for uid in users[5:]:
            _assign_variant(daemon_db, "guard_pause", uid)

        with patch("mandarin.web.experiment_daemon.sequential_test") as mock_seq, \
             patch("mandarin.web.experiment_daemon.check_guardrails") as mock_guard:
            mock_seq.return_value = {"recommendation": "continue"}
            mock_guard.return_value = {
                "session_completion_rate": {
                    "control_value": 0.9,
                    "treatment_value": 0.5,
                    "degraded": True,
                }
            }
            _daemon_tick(daemon_db)

        row = daemon_db.execute(
            "SELECT status FROM experiment WHERE name = 'guard_pause'"
        ).fetchone()
        assert row["status"] == "paused"

    def test_tick_advances_rollout(self, daemon_db):
        """Daemon should advance rollout stages when next_stage_at is past."""
        # Create a concluded experiment with rollout
        exp_id = create_experiment(daemon_db, "rollout_test", "Test", ["control", "treatment"])
        start_experiment(daemon_db, "rollout_test")
        conclude_experiment(daemon_db, "rollout_test", winner="treatment")

        flag_name = "exp_rollout_test_rollout"
        set_flag(daemon_db, flag_name, enabled=True, rollout_pct=0)

        past = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        daemon_db.execute("""
            INSERT INTO experiment_rollout
            (experiment_id, winner_variant, rollout_stage, current_pct,
             stage_started_at, next_stage_at, feature_flag_name)
            VALUES (?, 'treatment', 'pending', 0, ?, ?, ?)
        """, (exp_id, past, past, flag_name))
        daemon_db.commit()

        _daemon_tick(daemon_db)

        rollout = daemon_db.execute(
            "SELECT rollout_stage, current_pct FROM experiment_rollout WHERE experiment_id = ?",
            (exp_id,)
        ).fetchone()
        assert rollout["rollout_stage"] == "25pct"
        assert rollout["current_pct"] == 25

        # Verify feature flag was updated
        flag = daemon_db.execute(
            "SELECT rollout_pct FROM feature_flag WHERE name = ?",
            (flag_name,)
        ).fetchone()
        assert flag["rollout_pct"] == 25

    def test_tick_proposes_from_churn(self, daemon_db):
        """Daemon should propose experiments when churn signals are detected."""
        with patch("mandarin.web.experiment_daemon.get_at_risk_users") as mock_churn:
            mock_churn.return_value = [
                {"user_id": i, "risk_score": 70, "churn_type": "boredom"}
                for i in range(10)
            ]
            _daemon_tick(daemon_db)

        proposal = daemon_db.execute(
            "SELECT * FROM experiment_proposal WHERE name = 'auto_drill_variety'"
        ).fetchone()
        assert proposal is not None
        # Daemon proposes then auto-starts (no running experiments), so status is 'started'
        assert proposal["status"] in ("pending", "started")
        assert proposal["source"] == "churn_signal"

    def test_tick_auto_starts_proposal(self, daemon_db):
        """Daemon should auto-start top proposal when no experiments running."""
        # Insert a pending proposal
        daemon_db.execute("""
            INSERT INTO experiment_proposal
            (name, description, hypothesis, source, variants, priority, status)
            VALUES ('test_proposal', 'Test', 'Testing hypothesis', 'manual',
                    '["control", "treatment"]', 10, 'pending')
        """)
        daemon_db.commit()

        with patch("mandarin.web.experiment_daemon.get_at_risk_users") as mock_churn:
            mock_churn.return_value = []
            _daemon_tick(daemon_db)

        # Proposal should be started
        proposal = daemon_db.execute(
            "SELECT status, started_experiment_id FROM experiment_proposal WHERE name = 'test_proposal'"
        ).fetchone()
        assert proposal["status"] == "started"
        assert proposal["started_experiment_id"] is not None

        # Experiment should exist and be running
        exp = daemon_db.execute(
            "SELECT status FROM experiment WHERE id = ?",
            (proposal["started_experiment_id"],)
        ).fetchone()
        assert exp["status"] == "running"

    def test_tick_skips_start_when_experiment_running(self, daemon_db):
        """Daemon should not auto-start proposals when an experiment is already running."""
        create_experiment(daemon_db, "blocking_exp", "Blocks proposals", ["A", "B"])
        start_experiment(daemon_db, "blocking_exp")

        # Seed enough users/data so it doesn't immediately conclude
        users = _seed_users(daemon_db, 4)
        for uid in users:
            _assign_variant(daemon_db, "blocking_exp", uid)

        daemon_db.execute("""
            INSERT INTO experiment_proposal
            (name, description, hypothesis, source, variants, priority, status)
            VALUES ('blocked_proposal', 'Test', 'Test', 'manual',
                    '["control", "treatment"]', 10, 'pending')
        """)
        daemon_db.commit()

        with patch("mandarin.web.experiment_daemon.sequential_test") as mock_seq, \
             patch("mandarin.web.experiment_daemon.check_guardrails") as mock_guard, \
             patch("mandarin.web.experiment_daemon.get_at_risk_users") as mock_churn:
            mock_seq.return_value = {"recommendation": "continue", "information_fraction": 0.1}
            mock_guard.return_value = {}
            mock_churn.return_value = []
            _daemon_tick(daemon_db)

        proposal = daemon_db.execute(
            "SELECT status FROM experiment_proposal WHERE name = 'blocked_proposal'"
        ).fetchone()
        assert proposal["status"] == "pending"  # Should still be pending
