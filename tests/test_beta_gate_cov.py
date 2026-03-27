"""Tests for mandarin.intelligence.beta_gate — launch readiness checks.

Covers:
- CHECKS definition
- _CHECK_FUNCTIONS mapping
- Individual check functions (DB-based ones)
- run_beta_gate
- ANALYZERS
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    """Fresh DB with full schema for beta gate tests."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'admin@example.com', 'hash', 'Admin', 1)
    """)
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestChecksDefinition:
    def test_checks_list(self):
        from mandarin.intelligence.beta_gate import CHECKS
        assert isinstance(CHECKS, list)
        assert len(CHECKS) >= 18
        for check_id, desc, blocking in CHECKS:
            assert isinstance(check_id, str)
            assert isinstance(desc, str)
            assert isinstance(blocking, bool)

    def test_check_functions_map(self):
        from mandarin.intelligence.beta_gate import _CHECK_FUNCTIONS
        assert isinstance(_CHECK_FUNCTIONS, dict)
        assert len(_CHECK_FUNCTIONS) >= 18


class TestDBChecks:
    def test_hsk1_vocab_not_enough(self, conn):
        from mandarin.intelligence.beta_gate import _check_hsk1_vocab
        passed, msg = _check_hsk1_vocab(conn)
        assert passed is False
        assert "need" in msg.lower() or "0" in msg

    def test_hsk2_vocab_not_enough(self, conn):
        from mandarin.intelligence.beta_gate import _check_hsk2_vocab
        passed, msg = _check_hsk2_vocab(conn)
        assert passed is False

    def test_hsk3_vocab_not_enough(self, conn):
        from mandarin.intelligence.beta_gate import _check_hsk3_vocab
        passed, msg = _check_hsk3_vocab(conn)
        assert passed is False

    def test_grammar_seeded_not_enough(self, conn):
        from mandarin.intelligence.beta_gate import _check_grammar_seeded
        passed, msg = _check_grammar_seeded(conn)
        assert passed is False

    def test_admin_exists_yes(self, conn):
        from mandarin.intelligence.beta_gate import _check_admin_exists
        # Bootstrap user has is_admin=0; update it to 1 for this test
        conn.execute("UPDATE user SET is_admin = 1 WHERE id = 1")
        conn.commit()
        passed, msg = _check_admin_exists(conn)
        assert passed is True
        assert "1" in msg or "admin" in msg.lower()

    def test_admin_exists_no(self, conn):
        from mandarin.intelligence.beta_gate import _check_admin_exists
        # Bootstrap user has is_admin=0 by default
        passed, msg = _check_admin_exists(conn)
        assert passed is False

    def test_srs_tables(self, conn):
        from mandarin.intelligence.beta_gate import _check_srs_tables
        passed, msg = _check_srs_tables(conn)
        # No approved content, should fail
        assert passed is False

    def test_db_writable(self, conn):
        from mandarin.intelligence.beta_gate import _check_db_writable
        passed, msg = _check_db_writable(conn)
        assert passed is True
        assert "writable" in msg.lower()

    def test_cost_tracking_table(self, conn):
        from mandarin.intelligence.beta_gate import _check_cost_tracking
        passed, msg = _check_cost_tracking(conn)
        # This depends on whether the migration creates the table
        assert isinstance(passed, bool)
        assert isinstance(msg, str)

    def test_tts_available(self, conn):
        from mandarin.intelligence.beta_gate import _check_tts_available
        passed, msg = _check_tts_available(conn)
        # May or may not be installed
        assert isinstance(passed, bool)

    def test_check_sentry_configured(self, conn):
        from mandarin.intelligence.beta_gate import _check_sentry_configured
        passed, msg = _check_sentry_configured(conn)
        assert isinstance(passed, bool)

    def test_check_email_configured(self, conn):
        from mandarin.intelligence.beta_gate import _check_email_configured
        passed, msg = _check_email_configured(conn)
        assert isinstance(passed, bool)

    def test_check_stripe_live(self, conn):
        from mandarin.intelligence.beta_gate import _check_stripe_live
        passed, msg = _check_stripe_live(conn)
        assert isinstance(passed, bool)

    def test_check_stripe_products(self, conn):
        from mandarin.intelligence.beta_gate import _check_stripe_products
        passed, msg = _check_stripe_products(conn)
        assert isinstance(passed, bool)

    def test_check_plausible_configured(self, conn):
        from mandarin.intelligence.beta_gate import _check_plausible_configured
        passed, msg = _check_plausible_configured(conn)
        assert isinstance(passed, bool)

    def test_check_analytics_configured(self, conn):
        from mandarin.intelligence.beta_gate import _check_analytics_configured
        passed, msg = _check_analytics_configured(conn)
        assert isinstance(passed, bool)

    def test_check_uptime_monitor(self, conn):
        from mandarin.intelligence.beta_gate import _check_uptime_monitor
        passed, msg = _check_uptime_monitor(conn)
        assert isinstance(passed, bool)

    def test_check_health_200(self, conn):
        from mandarin.intelligence.beta_gate import _check_health_200
        passed, msg = _check_health_200(conn)
        # Will fail since no server is running
        assert isinstance(passed, bool)

    def test_check_llm_available(self, conn):
        from mandarin.intelligence.beta_gate import _check_llm_available
        passed, msg = _check_llm_available(conn)
        assert isinstance(passed, bool)


class TestRunBetaGate:
    def test_run_beta_gate(self, conn):
        from mandarin.intelligence.beta_gate import run_beta_gate
        result = run_beta_gate(conn)
        assert isinstance(result, dict)
        assert "checks" in result or "results" in result or "passed" in result or "summary" in result

    def test_analyzers_exist(self):
        from mandarin.intelligence.beta_gate import ANALYZERS
        assert isinstance(ANALYZERS, list)
        assert len(ANALYZERS) > 0
