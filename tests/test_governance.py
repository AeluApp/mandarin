"""Tests for AI governance & compliance (Doc 11)."""

import unittest
from datetime import date, timedelta


from tests.shared_db import make_test_db as _make_db


def _ensure_content_items(conn, *ids):
    """Insert stub content_item rows for FK satisfaction."""
    for cid in ids:
        conn.execute(
            "INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, item_type) "
            "VALUES (?, 'test', 'test', 'test', 'vocab')",
            (cid,),
        )


class TestSeedComponentRegistry(unittest.TestCase):
    """Tests for component registry seeding."""

    def test_inserts_all_components(self):
        """1. seed_component_registry inserts all 6 components."""
        from mandarin.intelligence.governance import seed_component_registry
        conn = _make_db()
        seed_component_registry(conn)
        count = conn.execute("SELECT COUNT(*) FROM ai_component_registry").fetchone()[0]
        self.assertEqual(count, 6)

    def test_idempotent(self):
        """2. seed_component_registry is idempotent."""
        from mandarin.intelligence.governance import seed_component_registry
        conn = _make_db()
        seed_component_registry(conn)
        seed_component_registry(conn)
        count = conn.execute("SELECT COUNT(*) FROM ai_component_registry").fetchone()[0]
        self.assertEqual(count, 6)


class TestFerpaAccess(unittest.TestCase):
    """Tests for FERPA access control."""

    def test_self_access_permitted(self):
        """3. Self-access is permitted."""
        from mandarin.intelligence.governance import check_ferpa_access
        conn = _make_db()
        result = check_ferpa_access(conn, 'user1', 'user1', 'review_event')
        self.assertTrue(result['permitted'])
        self.assertEqual(result['basis'], 'self_access')

    def test_teacher_access_permitted(self):
        """4. Teacher access to own student is permitted."""
        from mandarin.intelligence.governance import check_ferpa_access
        conn = _make_db()
        # Create teacher and student users (teacher_id and user_id are INTEGER FKs)
        conn.execute("INSERT OR IGNORE INTO user (id, email, password_hash, created_at, onboarding_complete) VALUES (100, 'teacher1@test.com', 'hash', datetime('now'), 0)")
        conn.execute("INSERT OR IGNORE INTO user (id, email, password_hash, created_at, onboarding_complete) VALUES (101, 'student1@test.com', 'hash', datetime('now'), 0)")
        conn.execute("INSERT INTO cohorts (id, teacher_id, name) VALUES (1, 100, 'Class A')")
        conn.execute("INSERT INTO cohort_members (cohort_id, user_id, active) VALUES (1, 101, 1)")
        conn.commit()
        result = check_ferpa_access(conn, 100, 101, 'review_event')
        self.assertTrue(result['permitted'])
        self.assertEqual(result['basis'], 'legitimate_educational_interest')

    def test_unrelated_access_denied(self):
        """5. Unrelated user access is denied."""
        from mandarin.intelligence.governance import check_ferpa_access
        conn = _make_db()
        result = check_ferpa_access(conn, 'random_user', 'student1', 'review_event')
        self.assertFalse(result['permitted'])
        self.assertEqual(result['basis'], 'denied_no_basis')

    def test_all_attempts_logged(self):
        """6. All access attempts logged regardless of outcome."""
        from mandarin.intelligence.governance import check_ferpa_access
        conn = _make_db()
        check_ferpa_access(conn, 'user1', 'user1', 'review_event')
        check_ferpa_access(conn, 'random', 'user1', 'review_event')
        logs = conn.execute("SELECT COUNT(*) FROM ferpa_access_audit").fetchone()[0]
        self.assertEqual(logs, 2)


class TestDeletionRequest(unittest.TestCase):
    """Tests for data deletion handling."""

    def test_clears_records(self):
        """7. handle_deletion_request clears records from tables."""
        from mandarin.intelligence.governance import handle_deletion_request
        conn = _make_db()
        _ensure_content_items(conn, 1, 2)
        conn.execute("INSERT INTO review_event (user_id, content_item_id, correct, modality) VALUES (1, 1, 1, 'read')")
        conn.execute("INSERT INTO review_event (user_id, content_item_id, correct, modality) VALUES (1, 2, 0, 'read')")
        conn.execute("INSERT INTO session_log (user_id) VALUES (1)")
        conn.commit()
        result = handle_deletion_request(conn, '1')
        remaining = conn.execute("SELECT COUNT(*) FROM review_event WHERE user_id = 1").fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_returns_counts(self):
        """8. handle_deletion_request returns count of deleted records."""
        from mandarin.intelligence.governance import handle_deletion_request
        conn = _make_db()
        _ensure_content_items(conn, 1, 2)
        conn.execute("INSERT INTO review_event (user_id, content_item_id, correct, modality) VALUES (1, 1, 1, 'read')")
        conn.execute("INSERT INTO review_event (user_id, content_item_id, correct, modality) VALUES (1, 2, 0, 'read')")
        conn.commit()
        result = handle_deletion_request(conn, '1')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['deleted_records'].get('review_event', 0), 2)


class TestAccessRequest(unittest.TestCase):
    """Tests for data access requests."""

    def test_returns_data(self):
        """10. handle_access_request returns data from core tables."""
        from mandarin.intelligence.governance import handle_access_request
        conn = _make_db()
        _ensure_content_items(conn, 1)
        conn.execute("INSERT INTO review_event (user_id, content_item_id, correct, modality) VALUES (1, 1, 1, 'read')")
        conn.execute("INSERT INTO session_log (user_id) VALUES (1)")
        conn.commit()
        result = handle_access_request(conn, '1')
        self.assertEqual(result['status'], 'completed')
        self.assertIn('review_event', result['data'])
        self.assertEqual(len(result['data']['review_event']), 1)


class TestTransparency(unittest.TestCase):
    """Tests for learner transparency."""

    def test_report_sections(self):
        """11. get_transparency_report returns all three main sections."""
        from mandarin.intelligence.governance import get_transparency_report
        conn = _make_db()
        report = get_transparency_report(conn, 'user1')
        self.assertIn('what_ai_does_in_aelu', report)
        self.assertIn('your_data', report)
        self.assertIn('your_rights', report)

    def test_explain_new_item(self):
        """12. explain_item_scheduling returns 'new item' for unseen items."""
        from mandarin.intelligence.governance import explain_item_scheduling
        conn = _make_db()
        result = explain_item_scheduling(conn, '999', 'user1')
        self.assertIn('new item', result['scheduling_reason'].lower())

    def test_explain_reviewed_item(self):
        """13. explain_item_scheduling returns days-since for reviewed items."""
        from mandarin.intelligence.governance import explain_item_scheduling
        conn = _make_db()
        _ensure_content_items(conn, 42)
        conn.execute("""
            INSERT INTO review_event (user_id, content_item_id, correct, modality, created_at)
            VALUES (1, 42, 1, 'read', datetime('now', '-3 days'))
        """)
        conn.commit()
        result = explain_item_scheduling(conn, '42', '1')
        self.assertIn('3 day', result['scheduling_reason'])


class TestDataQuality(unittest.TestCase):
    """Tests for data quality checks."""

    def test_orphaned_sessions(self):
        """14. Orphaned sessions generate high finding."""
        from mandarin.intelligence.governance import check_data_quality
        conn = _make_db()
        conn.execute("INSERT INTO session_log (user_id, started_at) VALUES (1, datetime('now'))")
        conn.commit()
        findings = check_data_quality(conn)
        orphan = [f for f in findings if 'no review events' in f['title'].lower()]
        self.assertTrue(len(orphan) >= 1)
        self.assertEqual(orphan[0]['severity'], 'high')

    def test_future_timestamps(self):
        """15. Future timestamps generate medium finding."""
        from mandarin.intelligence.governance import check_data_quality
        conn = _make_db()
        _ensure_content_items(conn, 1)
        conn.execute("""
            INSERT INTO review_event (user_id, content_item_id, correct, modality, created_at)
            VALUES (1, 1, 1, 'read', datetime('now', '+2 days'))
        """)
        conn.commit()
        findings = check_data_quality(conn)
        future = [f for f in findings if 'future' in f['title'].lower()]
        self.assertTrue(len(future) >= 1)
        self.assertEqual(future[0]['severity'], 'medium')


class TestGovernanceCompliance(unittest.TestCase):
    """Tests for governance compliance analyzer."""

    def test_critical_for_overdue_data_requests(self):
        """16. Critical finding for overdue data subject requests."""
        from mandarin.intelligence.governance import analyze_governance_compliance
        conn = _make_db()
        conn.execute("""
            INSERT INTO data_subject_requests (id, user_id, request_type, status, response_due_date)
            VALUES ('r1', 'u1', 'deletion', 'pending', date('now', '-5 days'))
        """)
        conn.commit()
        findings = analyze_governance_compliance(conn)
        critical = [f for f in findings if f['severity'] == 'critical'
                     and 'data subject' in f['title'].lower()]
        self.assertTrue(len(critical) >= 1)

    def test_critical_for_open_incidents(self):
        """17. Critical finding for open P0/P1 incidents."""
        from mandarin.intelligence.governance import analyze_governance_compliance
        conn = _make_db()
        conn.execute("""
            INSERT INTO ai_incident_log (id, severity, incident_type, description)
            VALUES ('i1', 'P0', 'data_breach', 'Test breach')
        """)
        conn.commit()
        findings = analyze_governance_compliance(conn)
        critical = [f for f in findings if f['severity'] == 'critical'
                     and 'incident' in f['title'].lower()]
        self.assertTrue(len(critical) >= 1)

    def test_critical_for_coppa_no_consent(self):
        """18. Critical finding for COPPA subjects without consent."""
        from mandarin.intelligence.governance import analyze_governance_compliance
        conn = _make_db()
        conn.execute("""
            INSERT INTO user_age_classification (user_id, is_coppa_subject, parental_consent_obtained)
            VALUES ('child1', 1, 0)
        """)
        conn.commit()
        findings = analyze_governance_compliance(conn)
        coppa = [f for f in findings if f['severity'] == 'critical'
                  and 'under 13' in f['title'].lower()]
        self.assertTrue(len(coppa) >= 1)

    def test_high_for_overdue_validation(self):
        """19. High finding for overdue component validation."""
        from mandarin.intelligence.governance import analyze_governance_compliance
        conn = _make_db()
        conn.execute("""
            INSERT INTO ai_component_registry
            (id, component_name, component_description, ai_type, decision_type,
             risk_tier, risk_tier_rationale, failure_mode, failure_impact,
             known_limitations, next_validation_due)
            VALUES ('c1', 'test_model', 'Test', 'ml_model', 'scheduling',
                    'tier_2_medium', 'Test', 'Test', 'Test', 'Test',
                    date('now', '-10 days'))
        """)
        conn.commit()
        findings = analyze_governance_compliance(conn)
        overdue = [f for f in findings if f['severity'] == 'high'
                    and 'overdue' in f['title'].lower()]
        self.assertTrue(len(overdue) >= 1)


class TestModelValidation(unittest.TestCase):
    """Tests for model validation."""

    def test_validated_for_healthy_component(self):
        """20. 'validated' verdict for healthy Tier 2 component."""
        from mandarin.intelligence.governance import _validate_component
        conn = _make_db()
        # Mock component row
        component = {
            'component_name': 'test_model',
            'known_limitations': 'Has limitations',
            'human_override_available': 1,
            'risk_tier': 'tier_2_medium',
        }
        result = _validate_component(conn, component)
        self.assertEqual(result['verdict'], 'validated')
        self.assertEqual(result['conceptual_soundness'], 'sound')

    def test_validation_failed_for_critical(self):
        """21. 'validation_failed' for critical-status component."""
        from mandarin.intelligence.governance import _validate_component
        conn = _make_db()
        # Insert a critical finding for this component
        conn.execute("""
            INSERT INTO pi_finding (dimension, severity, title, status)
            VALUES ('engagement', 'critical', 'Test critical', 'investigating')
        """)
        conn.commit()
        component = {
            'component_name': 'abandonment_risk_heuristic',
            'known_limitations': 'Has limitations',
            'human_override_available': 1,
            'risk_tier': 'tier_2_medium',
        }
        result = _validate_component(conn, component)
        self.assertEqual(result['verdict'], 'validation_failed')

    def test_needs_review_missing_limitations(self):
        """22. 'needs_review' when limitations not acknowledged."""
        from mandarin.intelligence.governance import _validate_component
        conn = _make_db()
        component = {
            'component_name': 'test_model',
            'known_limitations': '',  # empty = not acknowledged
            'human_override_available': 0,
            'risk_tier': 'tier_2_medium',
        }
        result = _validate_component(conn, component)
        self.assertEqual(result['verdict'], 'needs_review')
        self.assertEqual(result['conceptual_soundness'], 'needs_review')

    def test_validation_updates_next_due(self):
        """23. run_model_validation updates next_validation_due."""
        from mandarin.intelligence.governance import run_model_validation, seed_component_registry
        conn = _make_db()
        seed_component_registry(conn)

        # Set all next_validation_due to past
        conn.execute("UPDATE ai_component_registry SET next_validation_due = date('now', '-1 day')")
        conn.commit()

        records = run_model_validation(conn)
        self.assertTrue(len(records) >= 1)

        # Check next_validation_due was updated
        updated = conn.execute("""
            SELECT next_validation_due FROM ai_component_registry
            WHERE risk_tier = 'tier_2_medium' LIMIT 1
        """).fetchone()
        self.assertIsNotNone(updated['next_validation_due'])
        self.assertGreater(updated['next_validation_due'], date.today().isoformat())


class TestPolicyDocuments(unittest.TestCase):
    """Tests for policy document seeding."""

    def test_seeds_all_documents(self):
        """24. seed_policy_documents inserts all 4 documents."""
        from mandarin.intelligence.governance import seed_policy_documents
        conn = _make_db()
        seed_policy_documents(conn)
        count = conn.execute("SELECT COUNT(*) FROM ai_policy_documents").fetchone()[0]
        self.assertEqual(count, 4)

    def test_idempotent(self):
        """25. seed_policy_documents is idempotent."""
        from mandarin.intelligence.governance import seed_policy_documents
        conn = _make_db()
        seed_policy_documents(conn)
        seed_policy_documents(conn)
        count = conn.execute("SELECT COUNT(*) FROM ai_policy_documents").fetchone()[0]
        self.assertEqual(count, 4)


if __name__ == "__main__":
    unittest.main()
