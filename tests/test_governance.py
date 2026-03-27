"""Tests for AI governance & compliance (Doc 11)."""

import sqlite3
import unittest
from datetime import date, timedelta


def _make_db():
    """Create in-memory DB with Doc 11 tables + dependencies."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Core tables
    conn.execute("""
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            content_item_id INTEGER,
            session_id INTEGER,
            is_correct INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT, pinyin TEXT, english TEXT,
            status TEXT DEFAULT 'drill_ready'
        )
    """)

    # Cohort tables for FERPA
    conn.execute("""
        CREATE TABLE cohorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id TEXT NOT NULL,
            name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE cohort_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cohort_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Doc 11 tables
    conn.execute("""
        CREATE TABLE ai_component_registry (
            id TEXT PRIMARY KEY,
            component_name TEXT NOT NULL UNIQUE,
            component_description TEXT NOT NULL,
            ai_type TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            risk_tier TEXT NOT NULL,
            risk_tier_rationale TEXT NOT NULL,
            failure_mode TEXT NOT NULL,
            failure_impact TEXT NOT NULL,
            failure_detectability TEXT,
            human_override_available INTEGER NOT NULL DEFAULT 1,
            human_override_mechanism TEXT,
            monitoring_function TEXT,
            known_limitations TEXT NOT NULL,
            performance_benchmarks TEXT,
            component_owner TEXT NOT NULL DEFAULT 'jason_yee',
            last_validated_at TEXT,
            next_validation_due TEXT,
            registered_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE ai_validation_log (
            id TEXT PRIMARY KEY,
            component_name TEXT NOT NULL,
            validated_at TEXT NOT NULL DEFAULT (datetime('now')),
            verdict TEXT NOT NULL,
            prediction_accuracy_90d REAL,
            monitoring_status TEXT,
            conceptual_soundness TEXT,
            limitations_acknowledged INTEGER NOT NULL DEFAULT 0,
            override_available INTEGER NOT NULL DEFAULT 0,
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ai_incident_log (
            id TEXT PRIMARY KEY,
            detected_at TEXT NOT NULL DEFAULT (datetime('now')),
            severity TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            affected_component TEXT,
            affected_user_ids TEXT,
            description TEXT NOT NULL,
            immediate_actions_taken TEXT,
            root_cause TEXT,
            resolution TEXT,
            resolved_at TEXT,
            user_notification_sent INTEGER NOT NULL DEFAULT 0,
            post_incident_review_notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE user_consent_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            consent_type TEXT NOT NULL,
            consented INTEGER NOT NULL,
            consent_version TEXT NOT NULL,
            consented_at TEXT NOT NULL DEFAULT (datetime('now')),
            withdrawn_at TEXT,
            UNIQUE(user_id, consent_type)
        )
    """)
    conn.execute("""
        CREATE TABLE data_subject_requests (
            id TEXT PRIMARY KEY,
            requested_at TEXT NOT NULL DEFAULT (datetime('now')),
            user_id TEXT NOT NULL,
            request_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            response_due_date TEXT NOT NULL DEFAULT (date('now', '+30 days')),
            completed_at TEXT,
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE user_age_classification (
            user_id TEXT PRIMARY KEY,
            is_minor INTEGER NOT NULL DEFAULT 0,
            is_coppa_subject INTEGER NOT NULL DEFAULT 0,
            parental_consent_obtained INTEGER NOT NULL DEFAULT 0,
            parental_consent_at TEXT,
            data_collection_restricted INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE ferpa_access_audit (
            id TEXT PRIMARY KEY,
            accessed_at TEXT NOT NULL DEFAULT (datetime('now')),
            requesting_user_id TEXT NOT NULL,
            target_user_id TEXT NOT NULL,
            data_table TEXT NOT NULL,
            access_permitted INTEGER NOT NULL,
            access_basis TEXT NOT NULL,
            request_context TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ai_policy_documents (
            id TEXT PRIMARY KEY,
            document_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            content TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'draft',
            user_facing INTEGER NOT NULL DEFAULT 0,
            last_reviewed_at TEXT,
            next_review_due TEXT,
            owner TEXT NOT NULL DEFAULT 'jason_yee'
        )
    """)
    # Prediction ledger (dependency for validation)
    conn.execute("""
        CREATE TABLE pi_predictions (
            id TEXT PRIMARY KEY,
            prediction_domain TEXT,
            prediction_made_at TEXT,
            outcome_confirmed INTEGER,
            outcome_observed_at TEXT
        )
    """)
    # pi_findings for monitoring status
    conn.execute("""
        CREATE TABLE pi_findings (
            id TEXT PRIMARY KEY,
            dimension TEXT,
            severity TEXT,
            title TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


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
        conn.execute("INSERT INTO cohorts (id, teacher_id, name) VALUES (1, 'teacher1', 'Class A')")
        conn.execute("INSERT INTO cohort_members (cohort_id, user_id, active) VALUES (1, 'student1', 1)")
        conn.commit()
        result = check_ferpa_access(conn, 'teacher1', 'student1', 'review_event')
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
        conn.execute("INSERT INTO review_event (user_id, content_item_id, is_correct) VALUES (1, 1, 1)")
        conn.execute("INSERT INTO review_event (user_id, content_item_id, is_correct) VALUES (1, 2, 0)")
        conn.execute("INSERT INTO session_log (user_id) VALUES (1)")
        conn.commit()
        handle_deletion_request(conn, '1')
        remaining = conn.execute("SELECT COUNT(*) FROM review_event WHERE user_id = 1").fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_returns_counts(self):
        """8. handle_deletion_request returns count of deleted records."""
        from mandarin.intelligence.governance import handle_deletion_request
        conn = _make_db()
        conn.execute("INSERT INTO review_event (user_id, content_item_id, is_correct) VALUES (1, 1, 1)")
        conn.execute("INSERT INTO review_event (user_id, content_item_id, is_correct) VALUES (1, 2, 0)")
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
        conn.execute("INSERT INTO review_event (user_id, content_item_id, is_correct) VALUES (1, 1, 1)")
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
        conn.execute("""
            INSERT INTO review_event (user_id, content_item_id, is_correct, created_at)
            VALUES (1, 42, 1, datetime('now', '-3 days'))
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
        conn.execute("INSERT INTO session_log (user_id, created_at) VALUES (1, datetime('now'))")
        conn.commit()
        findings = check_data_quality(conn)
        orphan = [f for f in findings if 'no review events' in f['title'].lower()]
        self.assertTrue(len(orphan) >= 1)
        self.assertEqual(orphan[0]['severity'], 'high')

    def test_future_timestamps(self):
        """15. Future timestamps generate medium finding."""
        from mandarin.intelligence.governance import check_data_quality
        conn = _make_db()
        conn.execute("""
            INSERT INTO review_event (user_id, content_item_id, is_correct, created_at)
            VALUES (1, 1, 1, datetime('now', '+2 days'))
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
            INSERT INTO pi_findings (id, dimension, severity, title)
            VALUES ('f1', 'engagement', 'critical', 'Test critical')
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
