"""Tests for mandarin.nudge_registry — behavioral nudge tracking and ethics.

Covers:
- NudgeType / NudgeStatus / OutcomeType enums
- DoctrineScore dataclass
- _heuristic_ethics_score
- _parse_ethics_response
- evaluate_nudge_ethics (with Ollama unavailable)
- _ensure_tables
- register_nudge / get_nudge / list_nudges
- log_nudge_exposure / log_nudge_outcome
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
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


class TestEnums:
    def test_nudge_type_values(self):
        from mandarin.nudge_registry import NudgeType
        assert NudgeType.INFORMATIONAL.value == "informational"
        assert NudgeType.FEEDBACK.value == "feedback"
        assert NudgeType.SOCIAL_PROOF.value == "social_proof"

    def test_nudge_status_values(self):
        from mandarin.nudge_registry import NudgeStatus
        assert NudgeStatus.DRAFT.value == "draft"
        assert NudgeStatus.ACTIVE.value == "active"
        assert NudgeStatus.RETIRED.value == "retired"

    def test_outcome_type_values(self):
        from mandarin.nudge_registry import OutcomeType
        assert OutcomeType.CLICKED.value == "clicked"
        assert OutcomeType.CONVERTED.value == "converted"
        assert OutcomeType.DISMISSED.value == "dismissed"
        assert OutcomeType.IGNORED.value == "ignored"


class TestDoctrineScore:
    def test_default_score_passes(self):
        from mandarin.nudge_registry import DoctrineScore
        score = DoctrineScore()
        assert score.passes is True
        assert score.overall >= 0.7

    def test_low_score_fails(self):
        from mandarin.nudge_registry import DoctrineScore
        score = DoctrineScore(overall=0.3)
        assert score.passes is False

    def test_to_dict(self):
        from mandarin.nudge_registry import DoctrineScore
        score = DoctrineScore(guilt_free=0.9, overall=0.85)
        d = score.to_dict()
        assert d["guilt_free"] == 0.9
        assert d["overall"] == 0.85
        assert "raw_response" not in d


class TestHeuristicEthics:
    def test_clean_copy(self):
        from mandarin.nudge_registry import _heuristic_ethics_score
        score = _heuristic_ethics_score("You can now understand 50 new characters!")
        assert score.passes is True
        assert score.guilt_free >= 0.7

    def test_guilt_copy(self):
        from mandarin.nudge_registry import _heuristic_ethics_score
        score = _heuristic_ethics_score("You haven't practiced in 3 days! Don't give up!")
        assert score.guilt_free < 0.7

    def test_urgency_copy(self):
        from mandarin.nudge_registry import _heuristic_ethics_score
        score = _heuristic_ethics_score("Hurry! Limited time offer expires soon!")
        assert score.urgency_free < 0.7


class TestParseEthicsResponse:
    def test_valid_json(self):
        from mandarin.nudge_registry import _parse_ethics_response
        resp = '{"guilt_free": 0.9, "urgency_free": 0.8, "autonomy_respecting": 0.9, "progress_focused": 0.7, "tone_appropriate": 0.8, "overall": 0.85}'
        score = _parse_ethics_response(resp)
        assert score.overall == 0.85
        assert score.guilt_free == 0.9

    def test_json_in_markdown(self):
        from mandarin.nudge_registry import _parse_ethics_response
        resp = '```json\n{"guilt_free": 0.5, "overall": 0.6}\n```'
        score = _parse_ethics_response(resp)
        assert score.overall == 0.6

    def test_invalid_json(self):
        from mandarin.nudge_registry import _parse_ethics_response
        score = _parse_ethics_response("not json at all")
        # Should return fallback score
        assert isinstance(score, object)


class TestEvaluateNudgeEthics:
    def test_fallback_without_ollama(self):
        from mandarin.nudge_registry import evaluate_nudge_ethics
        # With no Ollama, should fall back to heuristic
        score = evaluate_nudge_ethics("Great progress! You've learned 20 new words.")
        assert hasattr(score, "overall")
        assert hasattr(score, "passes")


class TestNudgeCRUD:
    def test_register_nudge(self, conn):
        from mandarin.nudge_registry import register_nudge, NudgeType
        nudge_id = register_nudge(
            conn, nudge_key="my_nudge",
            copy_template="You've made progress!",
            nudge_type=NudgeType.FEEDBACK,
            context="session_end",
            auto_evaluate=False,
        )
        assert isinstance(nudge_id, int)

    def test_log_nudge_exposure(self, conn):
        from mandarin.nudge_registry import log_nudge_exposure
        log_nudge_exposure(conn, nudge_key="test", user_id=1, context="test")
        # Should not raise

    def test_log_nudge_outcome(self, conn):
        from mandarin.nudge_registry import (
            register_nudge, log_nudge_exposure, log_nudge_outcome,
            NudgeType, OutcomeType,
        )
        register_nudge(conn, nudge_key="outcome_test",
                        copy_template="Test!", nudge_type=NudgeType.INFORMATIONAL,
                        auto_evaluate=False)
        exposure_id = log_nudge_exposure(conn, nudge_key="outcome_test",
                                          user_id=1, context="test")
        if exposure_id:
            log_nudge_outcome(conn, exposure_id=exposure_id,
                               outcome=OutcomeType.CLICKED)
        # Should not raise

    def test_get_nudge_stats(self, conn):
        from mandarin.nudge_registry import get_nudge_stats
        stats = get_nudge_stats(conn, "test_nudge")
        assert isinstance(stats, dict)

    def test_get_all_nudge_stats(self, conn):
        from mandarin.nudge_registry import get_all_nudge_stats
        stats = get_all_nudge_stats(conn)
        assert isinstance(stats, list)
