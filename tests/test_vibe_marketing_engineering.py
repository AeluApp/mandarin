"""Tests for vibe audit, marketing intelligence, feature usage, engineering health (Doc 9)."""

import unittest
from unittest.mock import patch
from datetime import datetime, timedelta


from tests.shared_db import make_test_db as _make_db


class TestTonalVibe(unittest.TestCase):
    """Tests for tonal voice standard analysis."""

    def test_empty_copy_registry_medium_finding(self):
        """1. Empty copy registry produces medium finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_tonal_vibe
        conn = _make_db()
        conn.execute("DELETE FROM pi_copy_registry")
        conn.commit()
        results = analyze_tonal_vibe(conn)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["severity"], "medium")
        self.assertIn("no copy strings", results[0]["title"].lower())

    def test_low_voice_score_high_finding(self):
        """2. Copy with voice_score < 50 generates high finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_tonal_vibe
        conn = _make_db()
        conn.execute("""
            INSERT INTO pi_copy_registry (id, string_key, copy_text, voice_score, last_audited_at)
            VALUES ('1', 'bad_copy', 'Amazing! You are incredible! Act now!', 30, datetime('now'))
        """)
        conn.commit()
        results = analyze_tonal_vibe(conn)
        high_findings = [f for f in results if f["severity"] == "high"]
        self.assertTrue(len(high_findings) >= 1)

    def test_audit_conservative_default_no_llm(self):
        """3. _audit_copy_against_voice_standard returns conservative fallback when Qwen unavailable."""
        from mandarin.intelligence.vibe_marketing_eng import _audit_copy_against_voice_standard
        conn = _make_db()
        # With no Ollama available, should fall back to pattern matching
        with patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False):
            result = _audit_copy_against_voice_standard(conn, {
                "copy_text": "Keep practicing every day.",
            })
        self.assertIn("voice_score", result)
        self.assertIsInstance(result["voice_score"], (int, float))
        self.assertIn("violations", result)


class TestVisualVibe(unittest.TestCase):
    """Tests for visual audit schedule."""

    def test_overdue_visual_audit_low_finding(self):
        """4. Each overdue visual audit category generates a low finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_visual_vibe, VISUAL_VIBE_CHECKLIST
        conn = _make_db()
        results = analyze_visual_vibe(conn)
        # All categories should be overdue (no audits logged)
        self.assertEqual(len(results), len(VISUAL_VIBE_CHECKLIST))
        for f in results:
            self.assertEqual(f["severity"], "low")
            self.assertEqual(f["dimension"], "visual_vibe")


class TestMarketingPageQuality(unittest.TestCase):
    """Tests for marketing page quality analysis."""

    def test_empty_pages_medium_finding(self):
        """5. Empty marketing pages table produces medium finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_marketing_page_quality
        conn = _make_db()
        conn.execute("DELETE FROM pi_marketing_pages")
        conn.commit()
        results = analyze_marketing_page_quality(conn)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["severity"], "medium")
        self.assertIn("no marketing pages", results[0]["title"].lower())

    def test_missing_audience_finding(self):
        """6. Pages missing primary_audience generate a finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_marketing_page_quality
        conn = _make_db()
        conn.execute("DELETE FROM pi_marketing_pages")
        conn.execute("""
            INSERT INTO pi_marketing_pages (id, page_slug, page_title, last_copy_review_at)
            VALUES ('1', 'landing', 'Landing Page', datetime('now'))
        """)
        conn.commit()
        results = analyze_marketing_page_quality(conn)
        audience_findings = [f for f in results if "audience" in f["title"].lower()]
        self.assertTrue(len(audience_findings) >= 1)


class TestConversionFunnel(unittest.TestCase):
    """Tests for conversion funnel analysis."""

    def test_low_activation_rate_high_finding(self):
        """7. Activation rate < 40% generates high finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_conversion_funnel
        conn = _make_db()
        conn.execute("""
            INSERT INTO pi_funnel_snapshots
            (id, snapshot_date, signups_7d, activations_7d,
             conversion_signup_to_activation, d7_retention_rate)
            VALUES ('1', date('now'), 100, 30, 0.30, 0.50)
        """)
        conn.commit()
        results = analyze_conversion_funnel(conn)
        high_findings = [f for f in results if f["severity"] == "high"]
        self.assertTrue(len(high_findings) >= 1)
        self.assertIn("activation", high_findings[0]["title"].lower())

    def test_few_signups_no_findings(self):
        """8. With < 5 signups and no snapshot, no findings."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_conversion_funnel
        conn = _make_db()
        # Insert 3 signup events (below threshold of 5)
        for i in range(3):
            conn.execute("""
                INSERT INTO pi_funnel_events (id, user_id, event_type)
                VALUES (?, ?, 'signup')
            """, (str(i), str(i)))
        conn.commit()
        results = analyze_conversion_funnel(conn)
        self.assertEqual(len(results), 0)


class TestMarketingStrategy(unittest.TestCase):
    """Tests for marketing strategy checklist."""

    def test_overdue_strategy_reviews(self):
        """9. All strategy items overdue when no reviews logged."""
        from mandarin.intelligence.vibe_marketing_eng import (
            analyze_marketing_strategy, MARKETING_STRATEGY_CHECKLIST
        )
        conn = _make_db()
        results = analyze_marketing_strategy(conn)
        self.assertEqual(len(results), len(MARKETING_STRATEGY_CHECKLIST))
        for f in results:
            self.assertEqual(f["severity"], "low")
            self.assertEqual(f["dimension"], "marketing")


class TestFeatureUsage(unittest.TestCase):
    """Tests for feature usage analysis."""

    def _seed_active_users(self, conn, count=10):
        """Insert active users with recent sessions."""
        for i in range(count):
            conn.execute("""
                INSERT INTO session_log (user_id, started_at)
                VALUES (?, datetime('now', '-1 day'))
            """, (i + 1,))
        conn.commit()

    def test_zero_usage_flags_dead_feature(self):
        """10. Zero-usage feature launched 15+ days ago flagged as dead."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_feature_usage
        conn = _make_db()
        self._seed_active_users(conn, 10)
        conn.execute("""
            INSERT INTO pi_feature_registry
            (id, feature_name, feature_description, launched_at, minimum_usage_rate_30d, status)
            VALUES ('1', 'dead_feature', 'A dead feature', datetime('now', '-30 days'), 0.10, 'active')
        """)
        conn.commit()
        results = analyze_feature_usage(conn)
        dead = [f for f in results if "dead" in f["title"].lower()]
        self.assertTrue(len(dead) >= 1)

    def test_new_feature_not_flagged(self):
        """11. Feature launched < 14 days ago is not flagged."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_feature_usage
        conn = _make_db()
        self._seed_active_users(conn, 10)
        conn.execute("""
            INSERT OR REPLACE INTO pi_feature_registry
            (id, feature_name, feature_description, launched_at, minimum_usage_rate_30d, status)
            VALUES ('1', 'new_feature', 'A new feature', datetime('now', '-5 days'), 0.10, 'active')
        """)
        conn.commit()
        results = analyze_feature_usage(conn)
        new_findings = [f for f in results if "new_feature" in f.get("title", "").lower()]
        self.assertEqual(len(new_findings), 0)

    def test_high_abandonment_medium_finding(self):
        """12. High abandonment rate (>40%) generates medium finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_feature_usage
        conn = _make_db()
        self._seed_active_users(conn, 10)
        conn.execute("""
            INSERT INTO pi_feature_registry
            (id, feature_name, feature_description, launched_at, minimum_usage_rate_30d, status)
            VALUES ('1', 'leaky_feature', 'A leaky feature', datetime('now', '-30 days'), 0.01, 'active')
        """)
        # 10 starts, 3 completions = 70% abandonment
        for i in range(10):
            conn.execute("""
                INSERT INTO pi_feature_events (id, user_id, feature_name, event_type, occurred_at)
                VALUES (?, ?, 'leaky_feature', 'start', datetime('now', '-1 day'))
            """, (f"s{i}", str(i + 1)))
        for i in range(3):
            conn.execute("""
                INSERT INTO pi_feature_events (id, user_id, feature_name, event_type, occurred_at)
                VALUES (?, ?, 'leaky_feature', 'complete', datetime('now', '-1 day'))
            """, (f"c{i}", str(i + 1)))
        conn.commit()
        results = analyze_feature_usage(conn)
        abandon = [f for f in results if "abandonment" in f["title"].lower()]
        self.assertTrue(len(abandon) >= 1)
        self.assertEqual(abandon[0]["severity"], "medium")


class TestEngineeringHealth(unittest.TestCase):
    """Tests for engineering health analyzers.

    These analyzers now use cached snapshot data from pi_engineering_snapshots
    rather than running subprocess commands live.
    """

    def test_low_coverage_high_finding(self):
        """13. Coverage < 60% generates high finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_test_coverage
        conn = _make_db()

        # Insert a snapshot with low coverage
        conn.execute("""
            INSERT INTO pi_engineering_snapshots
            (id, snapshot_date, test_coverage_pct, tests_passing, tests_failing)
            VALUES ('1', date('now'), 45.2, 2, 0)
        """)
        conn.commit()

        results = analyze_test_coverage(conn)
        coverage_findings = [f for f in results if "coverage" in f["title"].lower()]
        self.assertTrue(len(coverage_findings) >= 1)
        self.assertEqual(coverage_findings[0]["severity"], "high")

    def test_failing_tests_high_finding(self):
        """14. Failing tests generate high finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_test_coverage
        conn = _make_db()

        # Insert a snapshot with failing tests
        conn.execute("""
            INSERT INTO pi_engineering_snapshots
            (id, snapshot_date, test_coverage_pct, tests_passing, tests_failing)
            VALUES ('1', date('now'), 80.0, 18, 3)
        """)
        conn.commit()

        results = analyze_test_coverage(conn)
        fail_findings = [f for f in results if "failing" in f["title"].lower()]
        self.assertTrue(len(fail_findings) >= 1)
        self.assertEqual(fail_findings[0]["severity"], "high")

    def test_outdated_deps_flagged(self):
        """15. Many outdated packages flagged."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_dependency_health
        conn = _make_db()

        # Insert a snapshot with many outdated dependencies
        conn.execute("""
            INSERT INTO pi_engineering_snapshots
            (id, snapshot_date, outdated_dependencies)
            VALUES ('1', date('now'), 15)
        """)
        conn.commit()

        results = analyze_dependency_health(conn)
        self.assertTrue(len(results) >= 1)
        self.assertIn("outdated", results[0]["title"].lower())

    def test_schema_high_table_count(self):
        """16. Table count > 80 generates low finding."""
        from mandarin.intelligence.vibe_marketing_eng import analyze_schema_health
        conn = _make_db()
        # Create 81+ tables
        for i in range(85):
            conn.execute(f"CREATE TABLE dummy_table_{i} (id INTEGER PRIMARY KEY)")
        conn.commit()
        results = analyze_schema_health(conn)
        table_findings = [f for f in results if "table" in f["title"].lower()]
        self.assertTrue(len(table_findings) >= 1)
        self.assertEqual(table_findings[0]["severity"], "low")


class TestVoiceStandardPatterns(unittest.TestCase):
    """Tests for pattern-based voice scoring."""

    def test_praise_inflation_low_score(self):
        """17. String with 'Amazing!' triggers praise_inflation violation."""
        from mandarin.intelligence.vibe_marketing_eng import _score_copy_against_patterns
        # Trigger multiple violation types: praise_inflation + urgency + false_simplicity
        result = _score_copy_against_patterns(
            "Amazing! Don't miss this! It's just so easy! You must try it! "
            "Your streak is at risk!"
        )
        self.assertLess(result["voice_score"], 60)
        violation_types = [v["type"] for v in result["violations"]]
        self.assertIn("praise_inflation", violation_types)

    def test_urgency_detected(self):
        """18. String with 'at risk' detected as anxiety language."""
        from mandarin.intelligence.vibe_marketing_eng import _score_copy_against_patterns
        result = _score_copy_against_patterns("Your streak is at risk of being lost.")
        violation_types = [v["type"] for v in result["violations"]]
        self.assertIn("anxiety_language", violation_types)


class TestFunnelEventPersistence(unittest.TestCase):
    """Tests for funnel event data operations."""

    def test_funnel_event_insert_and_query(self):
        """19. Funnel event insert + query by event_type returns correct counts."""
        conn = _make_db()
        conn.execute("""
            INSERT INTO pi_funnel_events (id, user_id, event_type)
            VALUES ('e1', 'u1', 'signup')
        """)
        conn.execute("""
            INSERT INTO pi_funnel_events (id, user_id, event_type)
            VALUES ('e2', 'u2', 'signup')
        """)
        conn.execute("""
            INSERT INTO pi_funnel_events (id, user_id, event_type)
            VALUES ('e3', 'u1', 'activation')
        """)
        conn.commit()

        signups = conn.execute(
            "SELECT COUNT(*) FROM pi_funnel_events WHERE event_type = 'signup'"
        ).fetchone()[0]
        activations = conn.execute(
            "SELECT COUNT(*) FROM pi_funnel_events WHERE event_type = 'activation'"
        ).fetchone()[0]
        self.assertEqual(signups, 2)
        self.assertEqual(activations, 1)


class TestVibeAuditPersistence(unittest.TestCase):
    """Tests for vibe audit data operations."""

    def test_audit_log_queryable_by_category(self):
        """20. Vibe audit log persists and is queryable by audit_category."""
        conn = _make_db()
        conn.execute("""
            INSERT INTO pi_vibe_audits
            (id, audit_date, audit_type, audit_category, overall_pass, findings_text)
            VALUES ('a1', datetime('now'), 'visual', 'color_palette', 1, 'Looks good')
        """)
        conn.execute("""
            INSERT INTO pi_vibe_audits
            (id, audit_date, audit_type, audit_category, overall_pass, findings_text)
            VALUES ('a2', datetime('now'), 'visual', 'typography', 0, 'Wrong font on mobile')
        """)
        conn.commit()

        color_audits = conn.execute(
            "SELECT * FROM pi_vibe_audits WHERE audit_category = 'color_palette' AND id = 'a1'"
        ).fetchall()
        typo_audits = conn.execute(
            "SELECT * FROM pi_vibe_audits WHERE audit_category = 'typography' AND id = 'a2'"
        ).fetchall()
        self.assertEqual(len(color_audits), 1)
        self.assertEqual(len(typo_audits), 1)
        self.assertEqual(color_audits[0]["overall_pass"], 1)
        self.assertEqual(typo_audits[0]["overall_pass"], 0)


if __name__ == "__main__":
    unittest.main()
