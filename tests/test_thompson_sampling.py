"""Tests for Thompson Sampling drill-type selection (Beta-Bernoulli bandit).

Covers: _thompson_sample_drill_type, _update_drill_type_posterior
from mandarin/scheduler.py.
"""

import sqlite3
import unittest

from mandarin.scheduler import (
    _thompson_sample_drill_type,
    _update_drill_type_posterior,
)


def _make_thompson_db():
    """Create in-memory DB with the drill_type_posterior table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE drill_type_posterior (
            user_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            drill_type TEXT NOT NULL,
            alpha REAL NOT NULL DEFAULT 1.0,
            beta REAL NOT NULL DEFAULT 1.0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, content_item_id, drill_type)
        );
    """)
    return conn


class TestThompsonSampleDrillType(unittest.TestCase):
    """Tests for _thompson_sample_drill_type()."""

    def setUp(self):
        self.conn = _make_thompson_db()

    def tearDown(self):
        self.conn.close()

    def test_empty_table_returns_eligible_type(self):
        """With no posteriors stored, should return one of the eligible types."""
        eligible = ["mc", "typing", "audio"]

        for _ in range(20):
            result = _thompson_sample_drill_type(self.conn, user_id=1, item_id=1,
                                                  eligible_types=eligible)
            self.assertIn(result, eligible)

    def test_empty_eligible_returns_mc(self):
        """Empty eligible_types list falls back to 'mc'."""
        result = _thompson_sample_drill_type(self.conn, user_id=1, item_id=1,
                                              eligible_types=[])
        self.assertEqual(result, "mc")

    def test_single_eligible_type_always_returned(self):
        """With a single eligible type, that type is always selected."""
        result = _thompson_sample_drill_type(self.conn, user_id=1, item_id=1,
                                              eligible_types=["typing"])
        self.assertEqual(result, "typing")

    def test_strong_prior_favors_type(self):
        """A type with very high alpha (strong prior) is selected most often."""
        # Give 'mc' a huge alpha (many successes), leave 'typing' at default
        self.conn.execute(
            "INSERT INTO drill_type_posterior (user_id, content_item_id, drill_type, alpha, beta) "
            "VALUES (1, 1, 'mc', 100.0, 1.0)"
        )
        self.conn.execute(
            "INSERT INTO drill_type_posterior (user_id, content_item_id, drill_type, alpha, beta) "
            "VALUES (1, 1, 'typing', 1.0, 1.0)"
        )
        self.conn.commit()

        mc_count = 0
        trials = 100
        for _ in range(trials):
            result = _thompson_sample_drill_type(self.conn, user_id=1, item_id=1,
                                                  eligible_types=["mc", "typing"])
            if result == "mc":
                mc_count += 1

        # With alpha=100 vs alpha=1, mc should win overwhelmingly
        self.assertGreater(mc_count, 80,
                           f"MC selected {mc_count}/100 times; expected >80 with strong prior")


class TestUpdateDrillTypePosterior(unittest.TestCase):
    """Tests for _update_drill_type_posterior()."""

    def setUp(self):
        self.conn = _make_thompson_db()

    def tearDown(self):
        self.conn.close()

    def _get_posterior(self, drill_type):
        row = self.conn.execute(
            "SELECT alpha, beta FROM drill_type_posterior "
            "WHERE user_id = 1 AND content_item_id = 1 AND drill_type = ?",
            (drill_type,)
        ).fetchone()
        return (row["alpha"], row["beta"]) if row else None

    def test_correct_increases_alpha(self):
        """correct=True should increase alpha."""
        _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                     drill_type="mc", correct=True)

        alpha, beta = self._get_posterior("mc")
        # Initial insert with correct=True: alpha=2.0, beta=1.0
        self.assertGreater(alpha, 1.0)
        self.assertEqual(beta, 1.0)

    def test_incorrect_increases_beta(self):
        """correct=False should increase beta."""
        _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                     drill_type="mc", correct=False)

        alpha, beta = self._get_posterior("mc")
        # Initial insert with correct=False: alpha=1.0, beta=2.0
        self.assertEqual(alpha, 1.0)
        self.assertGreater(beta, 1.0)

    def test_successive_correct_updates_accumulate(self):
        """Multiple correct updates accumulate in alpha."""
        for _ in range(5):
            _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                         drill_type="mc", correct=True)

        alpha, beta = self._get_posterior("mc")
        # First insert: alpha=2.0, beta=1.0; then 4 more correct: alpha += 4.0
        self.assertGreaterEqual(alpha, 6.0)
        self.assertEqual(beta, 1.0)

    def test_successive_incorrect_updates_accumulate(self):
        """Multiple incorrect updates accumulate in beta."""
        for _ in range(5):
            _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                         drill_type="mc", correct=False)

        alpha, beta = self._get_posterior("mc")
        self.assertEqual(alpha, 1.0)
        self.assertGreaterEqual(beta, 6.0)

    def test_separate_drill_types_independent(self):
        """Posteriors for different drill types are independent."""
        _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                     drill_type="mc", correct=True)
        _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                     drill_type="typing", correct=False)

        mc_alpha, mc_beta = self._get_posterior("mc")
        typing_alpha, typing_beta = self._get_posterior("typing")

        self.assertGreater(mc_alpha, 1.0)
        self.assertEqual(mc_beta, 1.0)
        self.assertEqual(typing_alpha, 1.0)
        self.assertGreater(typing_beta, 1.0)


class TestThompsonSamplingIntegration(unittest.TestCase):
    """Integration test: after many updates, sampling reflects learned posteriors."""

    def setUp(self):
        self.conn = _make_thompson_db()

    def tearDown(self):
        self.conn.close()

    def test_mc_favored_after_20_correct(self):
        """After 20 correct MC drills and 0 correct typing, MC selected >60%."""
        # 20 correct MC drills
        for _ in range(20):
            _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                         drill_type="mc", correct=True)

        # 20 incorrect typing drills (beta grows, alpha stays low)
        for _ in range(20):
            _update_drill_type_posterior(self.conn, user_id=1, item_id=1,
                                         drill_type="typing", correct=False)

        mc_count = 0
        trials = 100
        for _ in range(trials):
            result = _thompson_sample_drill_type(self.conn, user_id=1, item_id=1,
                                                  eligible_types=["mc", "typing"])
            if result == "mc":
                mc_count += 1

        self.assertGreater(mc_count, 60,
                           f"MC selected {mc_count}/100 times; expected >60 after 20 correct drills")

    def test_balanced_posteriors_produce_exploration(self):
        """With equal posteriors, both types should be sampled (neither <10%)."""
        # Give both types identical weak priors
        self.conn.execute(
            "INSERT INTO drill_type_posterior (user_id, content_item_id, drill_type, alpha, beta) "
            "VALUES (1, 1, 'mc', 2.0, 2.0)"
        )
        self.conn.execute(
            "INSERT INTO drill_type_posterior (user_id, content_item_id, drill_type, alpha, beta) "
            "VALUES (1, 1, 'typing', 2.0, 2.0)"
        )
        self.conn.commit()

        mc_count = 0
        trials = 200
        for _ in range(trials):
            result = _thompson_sample_drill_type(self.conn, user_id=1, item_id=1,
                                                  eligible_types=["mc", "typing"])
            if result == "mc":
                mc_count += 1

        typing_count = trials - mc_count
        # Neither arm should dominate with equal priors
        self.assertGreater(mc_count, 20,
                           f"MC only selected {mc_count}/{trials}; expected exploration")
        self.assertGreater(typing_count, 20,
                           f"Typing only selected {typing_count}/{trials}; expected exploration")


if __name__ == "__main__":
    unittest.main()
