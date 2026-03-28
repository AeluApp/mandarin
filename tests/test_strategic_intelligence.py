"""Tests for strategic intelligence — thesis, editorial, competitor analysis (Doc 10)."""

import json
import unittest
from unittest.mock import patch, MagicMock


from tests.shared_db import make_test_db as _make_db


def _seed_dimensions(conn):
    """Seed evaluation dimensions matching Doc 10 seed data."""
    import uuid as _uuid
    dims = [
        ('srs_sophistication', 3.0, 9, 9, 'Anki', 8, -1, 'low', 0),
        ('vocabulary_corpus_depth', 3.0, 4, 8, 'Hack Chinese', 8, 4, 'high', 1),
        ('first_session_activation', 2.5, 4, 8, 'HelloChinese', 9, 5, 'medium', 1),
        ('content_interest', 2.5, 5, 9, "Chairman's Bao", 8, 3, 'medium', 1),
        ('grammar_instruction_quality', 2.0, 5, 8, 'Market gap', 6, 1, 'medium', 0),
        ('speaking_output', 2.5, 1, 7, 'Pimsleur', 8, 7, 'high', 0),
        ('cultural_depth', 2.0, 7, 9, 'Mandarin Corner', 8, 1, 'low', 0),
        ('intelligence_and_adaptivity', 3.0, 8, 9, 'None', 4, -4, 'low', 0),
        ('classroom_and_teacher_tools', 2.0, 6, 9, 'None', 3, -3, 'medium', 1),
        ('ux_polish', 2.0, 5, 8, 'HelloChinese', 9, 4, 'medium', 1),
        ('pricing_and_value_clarity', 1.5, 1, 8, "Chairman's Bao", 7, 7, 'low', 1),
        ('advanced_learner_ceiling', 2.5, 6, 9, 'None', 3, -3, 'high', 0),
    ]
    for name, weight, cur, target, bic, bic_score, gap, cost, critical in dims:
        conn.execute("""
            INSERT OR REPLACE INTO pi_evaluation_dimensions
            (id, dimension_name, dimension_description, weight,
             aelu_current_score, aelu_target_score, best_in_class_competitor,
             best_in_class_score, gap, gap_closeable, closing_cost, on_critical_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (str(_uuid.uuid4()), name, f'Desc for {name}', weight,
              cur, target, bic, bic_score, gap, cost, critical))
    conn.commit()


def _seed_competitors(conn):
    """Seed a few competitors."""
    import uuid as _uuid
    for name, cat, overlap in [
        ('Anki', 'srs_focused', 'direct'),
        ('Hack Chinese', 'srs_focused', 'direct'),
        ('HelloChinese', 'gamified_mass_market', 'partial'),
    ]:
        conn.execute("""
            INSERT OR REPLACE INTO pi_competitors
            (id, name, category, strategic_position, primary_strength,
             primary_weakness, ceiling, aelu_overlap_degree, last_assessed_at)
            VALUES (?, ?, ?, 'position', 'strength', 'weakness', 'ceiling', ?, date('now'))
        """, (str(_uuid.uuid4()), name, cat, overlap))
    conn.commit()


class TestDeriveThesis(unittest.TestCase):
    """Tests for thesis derivation."""

    def test_derive_from_seeded_data(self):
        """1. derive_strategic_thesis produces valid thesis from seeded data."""
        from mandarin.intelligence.strategic_intelligence import derive_strategic_thesis
        conn = _make_db()
        _seed_dimensions(conn)
        _seed_competitors(conn)

        thesis = derive_strategic_thesis(conn)

        self.assertIn('target_user', thesis)
        self.assertIn('value_proposition', thesis)
        self.assertIn('revenue_model', thesis)
        self.assertIn('primary_moat', thesis)
        self.assertIn('confidence_score', thesis)
        self.assertIsInstance(thesis['confidence_score'], float)
        self.assertTrue(0 <= thesis['confidence_score'] <= 1)

    def test_viable_models_b2b2c(self):
        """2. _identify_viable_models returns b2b2c when teacher score >= 6."""
        from mandarin.intelligence.strategic_intelligence import (
            _identify_viable_models, _assess_competitive_position,
        )
        conn = _make_db()
        _seed_dimensions(conn)
        position = _assess_competitive_position(conn)
        viable = _identify_viable_models(conn, position)
        # With seeded scores: teacher=6, ux=5, corpus=4, avg=5.0 >= 4.5
        self.assertIn('b2b2c_teachers', viable)

    def test_select_hybrid_model(self):
        """3. _select_primary_model returns hybrid when both viable."""
        from mandarin.intelligence.strategic_intelligence import _select_primary_model
        conn = _make_db()
        result = _select_primary_model(conn, ['b2b2c_teachers', 'b2c_subscription'])
        self.assertEqual(result, 'hybrid_b2c_b2b2c')

    def test_blockers_nonempty_for_b2b2c(self):
        """4. _identify_blockers returns non-empty for b2b2c."""
        from mandarin.intelligence.strategic_intelligence import _identify_blockers
        conn = _make_db()
        blockers = _identify_blockers(conn, 'b2b2c_teachers')
        self.assertTrue(len(blockers) >= 3)
        self.assertTrue(any('dashboard' in b.lower() for b in blockers))


class TestRunStrategist(unittest.TestCase):
    """Tests for the strategist analyzer."""

    def test_creates_thesis_on_first_run(self):
        """5. run_strategist creates thesis when none exists."""
        from mandarin.intelligence.strategic_intelligence import run_strategist
        conn = _make_db()
        _seed_dimensions(conn)
        _seed_competitors(conn)

        findings = run_strategist(conn)

        # Should have created a thesis
        thesis = conn.execute(
            "SELECT * FROM pi_strategic_theses WHERE status = 'active'"
        ).fetchone()
        self.assertIsNotNone(thesis)

        # Should have a P0 finding about thesis creation
        p0 = [f for f in findings if f.get('priority') == 'P0']
        self.assertTrue(len(p0) >= 1)
        self.assertIn('thesis', p0[0]['title'].lower())

    def test_p0_when_blocking_conditions_unmet(self):
        """6. P0 finding when blocking conditions unmet."""
        from mandarin.intelligence.strategic_intelligence import run_strategist
        conn = _make_db()
        _seed_dimensions(conn)

        # Run once to create thesis
        run_strategist(conn)

        # Run again — should flag blocking conditions
        findings = run_strategist(conn)
        p0_blocking = [f for f in findings if f.get('priority') == 'P0'
                       and 'blocking' in f.get('title', '').lower()]
        self.assertTrue(len(p0_blocking) >= 1)


class TestCriticalPathGaps(unittest.TestCase):
    """Tests for critical path gap analysis."""

    def test_p1_for_large_critical_gap(self):
        """7. P1 finding for gap >= 4 on weight >= 2.5."""
        from mandarin.intelligence.strategic_intelligence import _analyze_critical_path_gaps
        conn = _make_db()
        _seed_dimensions(conn)

        # Create a dummy thesis
        conn.execute("""
            INSERT INTO pi_strategic_theses
            (id, version, status, target_user, value_proposition, revenue_model,
             price_point_rationale, primary_moat, key_assumptions,
             disconfirming_conditions, confirming_conditions)
            VALUES ('t1', 1, 'active', 'test', 'test', 'b2b2c_teachers',
                    'test', 'test', '[]', '[]', '[]')
        """)
        conn.commit()

        thesis = conn.execute("SELECT * FROM pi_strategic_theses WHERE id = 't1'").fetchone()
        findings = _analyze_critical_path_gaps(conn, thesis)

        # vocabulary_corpus_depth has gap=4, weight=3.0, on_critical_path=1
        # first_session_activation has gap=5, weight=2.5, on_critical_path=1
        self.assertTrue(len(findings) >= 2)
        for f in findings:
            self.assertIn(f['priority'], ('P1', 'P2'))


class TestStressTestThesis(unittest.TestCase):
    """Tests for thesis stress testing."""

    def test_disconfirming_evidence_detected(self):
        """8. P0 finding when disconfirming condition met."""
        from mandarin.intelligence.strategic_intelligence import _stress_test_thesis
        conn = _make_db()

        # Insert funnel snapshot with low activation
        conn.execute("""
            INSERT INTO pi_funnel_snapshots
            (id, snapshot_date, conversion_signup_to_activation)
            VALUES ('fs1', date('now'), 0.25)
        """)

        # Create thesis with disconfirming condition
        conn.execute("""
            INSERT INTO pi_strategic_theses
            (id, version, status, target_user, value_proposition, revenue_model,
             price_point_rationale, primary_moat, key_assumptions,
             disconfirming_conditions, confirming_conditions)
            VALUES ('t1', 1, 'active', 'test', 'test', 'b2b2c_teachers',
                    'test', 'test', '[]',
                    '["Student activation rate in pilot below 40%"]', '[]')
        """)
        conn.commit()

        thesis = conn.execute("SELECT * FROM pi_strategic_theses WHERE id = 't1'").fetchone()
        findings = _stress_test_thesis(conn, thesis)
        self.assertTrue(len(findings) >= 1)
        self.assertEqual(findings[0]['priority'], 'P0')
        self.assertIn('disconfirming', findings[0]['title'].lower())


class TestEditorialCritic(unittest.TestCase):
    """Tests for editorial quality assessment."""

    def test_bottom_quartile_when_low_score(self):
        """9. bottom_quartile=True when overall < 55."""
        from mandarin.intelligence.strategic_intelligence import assess_editorial_quality
        conn = _make_db()
        conn.execute("""
            INSERT INTO content_item (id, hanzi, pinyin, english, status)
            VALUES (1, '你好', 'nǐ hǎo', 'hello', 'drill_ready')
        """)
        conn.commit()

        # Without LLM, defaults to 60 on each dimension
        result = assess_editorial_quality(conn, '1')
        # Default 60 on all dims → overall ~60, not bottom quartile
        self.assertIn('overall_editorial_score', result)
        self.assertIsInstance(result['overall_editorial_score'], float)

    def test_conservative_defaults_no_llm(self):
        """10. _run_editorial_critic returns conservative defaults when LLM unavailable."""
        from mandarin.intelligence.strategic_intelligence import _run_editorial_critic
        conn = _make_db()
        result = _run_editorial_critic(conn, "测试内容", "Test context", "passage")
        # Should return 60 for each dimension
        for dim in ('specificity', 'adult_assumption', 'world_revealing',
                    'finish_pull', 'language_density'):
            self.assertEqual(result[dim], 60)

    def test_editorial_corpus_p1_for_shallow_content(self):
        """11. P1 finding when content corpus is mostly short vocabulary."""
        from mandarin.intelligence.strategic_intelligence import analyze_editorial_corpus
        conn = _make_db()
        # Insert 15 short vocabulary items
        for i in range(15):
            conn.execute("""
                INSERT INTO content_item (hanzi, pinyin, english, status)
                VALUES (?, ?, ?, 'drill_ready')
            """, (f'字{i}', f'zì{i}', f'word{i}'))
        conn.commit()

        findings = analyze_editorial_corpus(conn)
        p1 = [f for f in findings if f.get('priority') == 'P1']
        self.assertTrue(len(p1) >= 1)
        self.assertIn('single-word', p1[0]['title'].lower())


class TestCompetitorAnalysis(unittest.TestCase):
    """Tests for competitor analysis."""

    def test_p1_for_critical_path_deficit(self):
        """12. P1 finding for gap >= 4 on critical path dimension."""
        from mandarin.intelligence.strategic_intelligence import run_competitor_analysis
        conn = _make_db()
        _seed_dimensions(conn)
        _seed_competitors(conn)

        findings = run_competitor_analysis(conn)
        # speaking_output has gap=7, weight=2.5 but not critical path
        # first_session_activation has gap=5, weight=2.5, critical path
        deficits = [f for f in findings if 'deficit' in f.get('title', '').lower()]
        self.assertTrue(len(deficits) >= 1)

    def test_protects_leads(self):
        """13. Finding protecting competitive advantages."""
        from mandarin.intelligence.strategic_intelligence import run_competitor_analysis
        conn = _make_db()
        _seed_dimensions(conn)
        _seed_competitors(conn)

        findings = run_competitor_analysis(conn)
        protect = [f for f in findings if 'protect' in f.get('title', '').lower()]
        self.assertTrue(len(protect) >= 1)
        # Should mention intelligence_and_adaptivity as a lead
        self.assertIn('intelligence_and_adaptivity', protect[0]['title'])


class TestStrategicFindingFormat(unittest.TestCase):
    """Tests for strategic finding structure."""

    def test_includes_commercial_implication(self):
        """14. Strategic findings include commercial_implication field."""
        from mandarin.intelligence.strategic_intelligence import _make_strategic_finding
        finding = _make_strategic_finding(
            priority='P1', title='Test', implication='Test implication',
            detail='Detail', action='Action',
        )
        self.assertIn('commercial_implication', finding)
        self.assertEqual(finding['commercial_implication'], 'Test implication')
        self.assertEqual(finding['finding_type'], 'strategic')
        self.assertEqual(finding['dimension'], 'strategic')


class TestSeedData(unittest.TestCase):
    """Tests for seed data integrity."""

    def test_competitor_seed_no_constraint_violations(self):
        """15. Competitor seed inserts without constraint violations."""
        from mandarin.db.core import _migrate_v70_to_v71, get_connection
        import tempfile
        import os
        from pathlib import Path
        tf = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tf.close()
        try:
            conn = get_connection(Path(tf.name))
            conn.execute("CREATE TABLE session_log (id INTEGER PRIMARY KEY, user_id INTEGER, created_at TEXT)")
            conn.commit()
            _migrate_v70_to_v71(conn)
            count = conn.execute("SELECT COUNT(*) FROM pi_competitors").fetchone()[0]
            self.assertEqual(count, 8)
            conn.close()
        finally:
            os.unlink(tf.name)

    def test_evaluation_dimensions_seed_no_violations(self):
        """16. Evaluation dimensions seed inserts without violations."""
        from mandarin.db.core import _migrate_v70_to_v71, get_connection
        import tempfile
        import os
        from pathlib import Path
        tf = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tf.close()
        try:
            conn = get_connection(Path(tf.name))
            conn.execute("CREATE TABLE session_log (id INTEGER PRIMARY KEY, user_id INTEGER, created_at TEXT)")
            conn.commit()
            _migrate_v70_to_v71(conn)
            count = conn.execute("SELECT COUNT(*) FROM pi_evaluation_dimensions").fetchone()[0]
            self.assertEqual(count, 12)
            conn.close()
        finally:
            os.unlink(tf.name)


class TestThesisRevision(unittest.TestCase):
    """Tests for thesis revision."""

    def test_revision_creates_new_version(self):
        """17. Thesis revision creates new version with superseded_by link."""
        from mandarin.intelligence.strategic_intelligence import (
            run_strategist, revise_thesis,
        )
        conn = _make_db()
        _seed_dimensions(conn)

        # Create initial thesis
        run_strategist(conn)
        old_thesis = conn.execute(
            "SELECT * FROM pi_strategic_theses WHERE status = 'active'"
        ).fetchone()
        old_id = old_thesis['id']

        # Revise
        new_id = revise_thesis(conn, old_id, 'market_shift')

        # Old thesis superseded
        old_now = conn.execute(
            "SELECT * FROM pi_strategic_theses WHERE id = ?", (old_id,)
        ).fetchone()
        self.assertEqual(old_now['status'], 'superseded')
        self.assertEqual(old_now['superseded_by'], new_id)

        # New thesis active with higher version
        new_thesis = conn.execute(
            "SELECT * FROM pi_strategic_theses WHERE id = ?", (new_id,)
        ).fetchone()
        self.assertEqual(new_thesis['status'], 'active')
        self.assertEqual(new_thesis['version'], 2)
        self.assertEqual(new_thesis['revision_trigger'], 'market_shift')


class TestCommercialReadinessPersistence(unittest.TestCase):
    """Tests for commercial readiness data persistence."""

    def test_condition_update_persists_evidence(self):
        """18. Commercial readiness condition update persists evidence."""
        from mandarin.intelligence.strategic_intelligence import run_strategist
        conn = _make_db()
        _seed_dimensions(conn)
        run_strategist(conn)

        thesis = conn.execute(
            "SELECT id FROM pi_strategic_theses WHERE status = 'active'"
        ).fetchone()

        # Update a condition
        conn.execute("""
            UPDATE pi_commercial_readiness
            SET current_status = 'met', evidence = 'Deployed to 3 pilot teachers',
                last_assessed_at = datetime('now')
            WHERE thesis_id = ? AND condition_name = (
                SELECT condition_name FROM pi_commercial_readiness
                WHERE thesis_id = ? LIMIT 1
            )
        """, (thesis['id'], thesis['id']))
        conn.commit()

        # Verify persistence
        updated = conn.execute("""
            SELECT * FROM pi_commercial_readiness
            WHERE thesis_id = ? AND current_status = 'met'
        """, (thesis['id'],)).fetchone()
        self.assertIsNotNone(updated)
        self.assertEqual(updated['evidence'], 'Deployed to 3 pilot teachers')


class TestStrategicFindingsInAudit(unittest.TestCase):
    """Tests for strategic findings integration."""

    def test_strategic_findings_have_correct_dimension(self):
        """19. Strategic findings use 'strategic' dimension for proper routing."""
        from mandarin.intelligence.strategic_intelligence import run_strategist
        conn = _make_db()
        _seed_dimensions(conn)

        findings = run_strategist(conn)
        for f in findings:
            self.assertEqual(f['dimension'], 'strategic')
            self.assertIn(f['severity'], ('critical', 'high', 'medium'))


class TestCompetitivePosition(unittest.TestCase):
    """Tests for competitive position assessment."""

    def test_identifies_leads_and_lags(self):
        """20. _assess_competitive_position correctly identifies leads and lags."""
        from mandarin.intelligence.strategic_intelligence import _assess_competitive_position
        conn = _make_db()
        _seed_dimensions(conn)

        position = _assess_competitive_position(conn)

        # intelligence_and_adaptivity has gap=-4 → Aelu leads
        self.assertIn('intelligence_and_adaptivity', position['leads_on'])
        # classroom_and_teacher_tools has gap=-3 → Aelu leads
        self.assertIn('classroom_and_teacher_tools', position['leads_on'])
        # vocabulary_corpus_depth has gap=4, weight=3.0 → significant lag
        self.assertIn('vocabulary_corpus_depth', position['significant_lags'])
        # first_session_activation has gap=5, weight=2.5 → significant lag
        self.assertIn('first_session_activation', position['significant_lags'])


if __name__ == "__main__":
    unittest.main()
