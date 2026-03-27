"""Tests for mandarin.intelligence_audit — audit report generation."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("INSERT OR IGNORE INTO user (id, email, password_hash, display_name) VALUES (1, 'test@test.com', 'h', 'T')")
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestIntelligenceAudit:
    def test_import(self):
        import mandarin.intelligence_audit as mod
        assert hasattr(mod, 'run_monthly_audit')
        assert hasattr(mod, 'compute_brier_score')
        assert hasattr(mod, 'get_audit_history')

    def test_compute_brier_score(self, conn):
        from mandarin.intelligence_audit import compute_brier_score
        # Signature: (conn, lookback_days=90) -> dict
        result = compute_brier_score(conn)
        assert isinstance(result, dict)

    def test_compute_classification_accuracy(self, conn):
        from mandarin.intelligence_audit import compute_classification_accuracy
        result = compute_classification_accuracy(conn)
        assert isinstance(result, dict)

    def test_compute_proposal_win_rate(self, conn):
        from mandarin.intelligence_audit import compute_proposal_win_rate
        result = compute_proposal_win_rate(conn)
        assert isinstance(result, dict)

    def test_compute_guardrail_accuracy(self, conn):
        from mandarin.intelligence_audit import compute_guardrail_accuracy
        result = compute_guardrail_accuracy(conn)
        assert isinstance(result, dict)

    def test_get_audit_history(self, conn):
        from mandarin.intelligence_audit import get_audit_history
        history = get_audit_history(conn)
        assert isinstance(history, list)

    def test_run_monthly_audit(self, conn):
        from mandarin.intelligence_audit import run_monthly_audit
        result = run_monthly_audit(conn)
        assert isinstance(result, dict)
