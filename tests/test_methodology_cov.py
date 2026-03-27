"""Tests for mandarin.quality.methodology — sprint/agile/spiral quality functions.

Covers:
- get_current_sprint / get_sprint_history
- auto_create_sprint / complete_sprint
- _estimate_sprint_points / estimate_item_points
- get_sprint_velocity
- generate_session_retrospective
- calculate_wsjf / rank_content_backlog
- get_risk_taxonomy / run_risk_review / get_risk_summary
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    """Fresh DB with full schema for methodology tests."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'test@example.com', 'hash', 'Test', 0)
    """)
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestSprints:
    def test_no_sprint(self, conn):
        from mandarin.quality.methodology import get_current_sprint
        sprint = get_current_sprint(conn)
        assert sprint is None

    def test_empty_history(self, conn):
        from mandarin.quality.methodology import get_sprint_history
        history = get_sprint_history(conn)
        assert history == []

    def test_auto_create_sprint(self, conn):
        from mandarin.quality.methodology import auto_create_sprint
        sprint = auto_create_sprint(conn)
        assert sprint is None or isinstance(sprint, dict)

    def test_no_duplicate_sprint(self, conn):
        from mandarin.quality.methodology import auto_create_sprint, get_current_sprint
        sprint1 = auto_create_sprint(conn)
        if sprint1 is not None:
            sprint2 = auto_create_sprint(conn)
            assert sprint2 is None

    def test_complete_sprint_no_active(self, conn):
        from mandarin.quality.methodology import complete_sprint
        result = complete_sprint(conn)
        assert result is None

    def test_get_sprint_velocity(self, conn):
        from mandarin.quality.methodology import get_sprint_velocity
        velocity = get_sprint_velocity(conn)
        assert isinstance(velocity, dict)


class TestEstimation:
    def test_estimate_sprint_points(self, conn):
        from mandarin.quality.methodology import _estimate_sprint_points
        points = _estimate_sprint_points(conn, item_count=10)
        assert isinstance(points, int)
        assert points >= 0

    def test_estimate_item_points(self):
        from mandarin.quality.methodology import estimate_item_points
        item = {"difficulty": 0.5, "hsk_level": 3}
        points = estimate_item_points(item)
        assert isinstance(points, int)
        assert points > 0

    def test_estimate_item_points_easy(self):
        from mandarin.quality.methodology import estimate_item_points
        item = {"difficulty": 0.1, "hsk_level": 1}
        points = estimate_item_points(item)
        assert points >= 1

    def test_estimate_item_points_hard(self):
        from mandarin.quality.methodology import estimate_item_points
        item = {"difficulty": 0.9, "hsk_level": 9}
        points = estimate_item_points(item)
        assert points >= 1


class TestWSJF:
    def test_calculate_wsjf(self):
        from mandarin.quality.methodology import calculate_wsjf
        item = {
            "business_value": 8,
            "time_criticality": 5,
            "risk_reduction": 3,
            "job_size": 4,
        }
        score = calculate_wsjf(item)
        assert isinstance(score, float)
        assert score > 0

    def test_calculate_wsjf_zero_job_size(self):
        from mandarin.quality.methodology import calculate_wsjf
        item = {
            "business_value": 8,
            "time_criticality": 5,
            "risk_reduction": 3,
            "job_size": 0,
        }
        score = calculate_wsjf(item)
        assert isinstance(score, float)

    def test_rank_content_backlog(self, conn):
        from mandarin.quality.methodology import rank_content_backlog
        results = rank_content_backlog(conn)
        assert isinstance(results, list)


class TestRetrospective:
    def test_generate_session_retrospective(self, conn):
        from mandarin.quality.methodology import generate_session_retrospective
        # Create a session
        conn.execute("""
            INSERT INTO session_log (id, user_id, session_outcome, items_completed,
                                     items_correct, duration_seconds, started_at)
            VALUES (1, 1, 'completed', 10, 7, 300, datetime('now'))
        """)
        conn.commit()
        retro = generate_session_retrospective(conn, session_id=1)
        assert retro is None or isinstance(retro, dict)


class TestRisks:
    def test_get_risk_taxonomy(self):
        from mandarin.quality.methodology import get_risk_taxonomy
        taxonomy = get_risk_taxonomy()
        assert isinstance(taxonomy, dict)
        assert len(taxonomy) > 0

    def test_run_risk_review(self, conn):
        from mandarin.quality.methodology import run_risk_review
        risks = run_risk_review(conn)
        assert isinstance(risks, list)

    def test_get_risk_summary(self, conn):
        from mandarin.quality.methodology import get_risk_summary
        summary = get_risk_summary(conn)
        assert isinstance(summary, dict)
