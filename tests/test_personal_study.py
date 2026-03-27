"""Tests for Doc 20: Jason's Personal HSK 9 Study System."""

import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.personal_study import (
    HSK9_PERSONAL_PHASES,
    PERSONAL_CONFIG,
    get_personal_study_dashboard,
    _estimate_hsk9_year,
    _days_into_week,
)


from tests.shared_db import make_test_db as _make_db


class TestPersonalPhases(unittest.TestCase):
    def test_all_phases_present(self):
        for phase in ['phase_1', 'phase_2', 'phase_3', 'phase_4']:
            self.assertIn(phase, HSK9_PERSONAL_PHASES)

    def test_phases_progress_upward(self):
        phases = ['phase_1', 'phase_2', 'phase_3', 'phase_4']
        for i in range(len(phases) - 1):
            current = HSK9_PERSONAL_PHASES[phases[i]]
            next_p = HSK9_PERSONAL_PHASES[phases[i + 1]]
            self.assertLess(current['target_hsk'], next_p['target_hsk'])


class TestPersonalStudyDashboard(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_returns_current_hsk(self):
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate, vocab_items_mastered, grammar_patterns_mastered)
            VALUES (1, 3.5, 500, 35)
        """)
        dashboard = get_personal_study_dashboard(self.conn, 1)
        self.assertEqual(dashboard['current_hsk'], 3.5)

    def test_computes_phase_progress(self):
        # Phase 1 starts at 3.5, target 4.5
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate) VALUES (1, 4.0)
        """)
        dashboard = get_personal_study_dashboard(self.conn, 1)
        # 4.0 is 50% through phase 1 (3.5 → 4.5)
        self.assertEqual(dashboard['phase_progress_pct'], 50)

    def test_no_proficiency_returns_zero(self):
        dashboard = get_personal_study_dashboard(self.conn, 1)
        self.assertEqual(dashboard['current_hsk'], 0.0)

    def test_sessions_this_week(self):
        dashboard = get_personal_study_dashboard(self.conn, 1)
        self.assertIn('sessions_completed', dashboard['this_week'])
        self.assertIn('sessions_target', dashboard['this_week'])


class TestEstimateHSK9Year(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_returns_target_year_no_data(self):
        year = _estimate_hsk9_year(self.conn, 1, 0.0)
        self.assertEqual(year, PERSONAL_CONFIG['hsk9_target_year'])

    def test_returns_target_year_no_trend(self):
        year = _estimate_hsk9_year(self.conn, 1, 3.5)
        # With default 0.15/month progress from 3.5 → 9.0 = 36.7 months ≈ 3 years
        from datetime import date
        self.assertGreaterEqual(year, date.today().year)

    def test_uses_trend_when_available(self):
        # Insert a proficiency snapshot from 6 months ago
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate, computed_at)
            VALUES (1, 2.5, datetime('now','-200 days'))
        """)
        year = _estimate_hsk9_year(self.conn, 1, 3.5)
        # Progress of 1.0 in 6 months = 0.167/month
        from datetime import date
        self.assertGreaterEqual(year, date.today().year)


class TestDaysIntoWeek(unittest.TestCase):
    def test_returns_positive(self):
        days = _days_into_week()
        self.assertGreaterEqual(days, 1)
        self.assertLessEqual(days, 7)


class TestSchemaVersion(unittest.TestCase):
    def test_schema_includes_doc20(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 83)


if __name__ == "__main__":
    unittest.main()
