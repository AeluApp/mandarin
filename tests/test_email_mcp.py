"""Tests for Email MCP integration module (teacher communication)."""

import json
import unittest
from unittest.mock import patch, MagicMock

from tests.shared_db import make_test_db


def _make_db():
    conn = make_test_db()
    conn.executescript("""
        -- Seed users for email tests
        UPDATE user SET email='student@aelu.app', display_name='Alice' WHERE id=1;
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name)
        VALUES (2, 'teacher@aelu.app', 'test_hash', 'Ms. Chen');
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name)
        VALUES (3, 'student2@aelu.app', 'test_hash', 'Bob');
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name)
        VALUES (4, 'inactive@aelu.app', 'test_hash', NULL);

        INSERT INTO session_log (user_id, started_at, session_outcome, items_completed, items_correct, duration_seconds)
        VALUES (1, datetime('now', '-1 day'), 'completed', 20, 16, 900);
        INSERT INTO session_log (user_id, started_at, session_outcome, items_completed, items_correct, duration_seconds)
        VALUES (1, datetime('now', '-3 days'), 'completed', 15, 10, 600);
        INSERT INTO session_log (user_id, started_at, session_outcome, items_completed, items_correct, duration_seconds)
        VALUES (3, datetime('now', '-2 days'), 'completed', 10, 3, 300);

        INSERT INTO grammar_point (id, name, hsk_level) VALUES (1, 'Subject-Verb-Object', 1);
        INSERT INTO grammar_point (id, name, hsk_level) VALUES (2, 'Aspect particle 了', 2);

        INSERT INTO grammar_progress (user_id, grammar_point_id, mastery_score)
        VALUES (1, 1, 0.85);
        INSERT INTO grammar_progress (user_id, grammar_point_id, mastery_score)
        VALUES (1, 2, 0.45);

        INSERT INTO classroom (id, teacher_user_id, name, invite_code) VALUES (1, 2, 'HSK 1 Morning', 'TEST001');
        INSERT INTO classroom_student (classroom_id, user_id) VALUES (1, 1);
        INSERT INTO classroom_student (classroom_id, user_id) VALUES (1, 3);
        INSERT INTO classroom_student (classroom_id, user_id) VALUES (1, 4);
    """)
    return conn


class TestEmailMCPImport(unittest.TestCase):

    def test_module_imports(self):
        from mandarin.openclaw import email_mcp
        self.assertTrue(hasattr(email_mcp, 'draft_weekly_summary'))
        self.assertTrue(hasattr(email_mcp, 'draft_class_report'))
        self.assertTrue(hasattr(email_mcp, 'send_email'))
        self.assertTrue(hasattr(email_mcp, 'create_email_tools'))

    def test_create_email_tools_structure(self):
        from mandarin.openclaw.email_mcp import create_email_tools
        tools = create_email_tools()
        self.assertIsInstance(tools, list)
        self.assertEqual(len(tools), 3)
        names = {t["name"] for t in tools}
        self.assertIn("draft_weekly_summary", names)
        self.assertIn("draft_class_report", names)
        self.assertIn("send_email", names)

    def test_send_email_requires_confirmation(self):
        from mandarin.openclaw.email_mcp import create_email_tools
        tools = create_email_tools()
        send_tool = next(t for t in tools if t["name"] == "send_email")
        self.assertTrue(send_tool.get("requires_confirmation"))


class TestDraftWeeklySummary(unittest.TestCase):

    def test_basic_summary(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        result = draft_weekly_summary(conn, 1)
        self.assertEqual(result["status"], "drafted")
        self.assertEqual(result["to"], "student@aelu.app")
        self.assertIn("Alice", result["subject"])
        self.assertIn("Alice", result["text_body"])

    def test_summary_stats(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        result = draft_weekly_summary(conn, 1)
        self.assertEqual(result["metadata"]["user_id"], 1)
        self.assertEqual(result["metadata"]["session_count"], 2)
        self.assertEqual(result["metadata"]["streak"], 1)
        # Accuracy: (16+10)/(20+15) = 26/35 = 74%
        self.assertEqual(result["metadata"]["accuracy"], 74)

    def test_summary_has_html_body(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        result = draft_weekly_summary(conn, 1)
        self.assertIn("<div", result["html_body"])
        self.assertIn("Cormorant Garamond", result["html_body"])

    def test_summary_includes_grammar(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        result = draft_weekly_summary(conn, 1)
        self.assertIn("Grammar progress", result["text_body"])
        self.assertIn("Subject-Verb-Object", result["text_body"])

    def test_summary_user_not_found(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        result = draft_weekly_summary(conn, 999)
        self.assertIn("error", result)

    def test_summary_no_sessions(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        # User 4 has no sessions
        result = draft_weekly_summary(conn, 4)
        self.assertEqual(result["status"], "drafted")
        self.assertEqual(result["metadata"]["session_count"], 0)
        self.assertEqual(result["metadata"]["accuracy"], 0)

    def test_summary_display_name_fallback(self):
        from mandarin.openclaw.email_mcp import draft_weekly_summary
        conn = _make_db()
        # User 4 has no display_name, should fallback to email prefix
        result = draft_weekly_summary(conn, 4)
        self.assertIn("inactive", result["text_body"])


class TestDraftClassReport(unittest.TestCase):

    def test_basic_report(self):
        from mandarin.openclaw.email_mcp import draft_class_report
        conn = _make_db()
        result = draft_class_report(conn, 1)
        self.assertEqual(result["status"], "drafted")
        self.assertEqual(result["to"], "teacher@aelu.app")
        self.assertIn("HSK 1 Morning", result["subject"])

    def test_report_student_count(self):
        from mandarin.openclaw.email_mcp import draft_class_report
        conn = _make_db()
        result = draft_class_report(conn, 1)
        self.assertEqual(result["metadata"]["student_count"], 3)

    def test_report_identifies_struggling(self):
        from mandarin.openclaw.email_mcp import draft_class_report
        conn = _make_db()
        result = draft_class_report(conn, 1)
        # Student 3 (Bob) has 30% accuracy, Student 4 has 0 sessions
        self.assertGreater(result["metadata"]["struggling_count"], 0)

    def test_report_text_has_student_names(self):
        from mandarin.openclaw.email_mcp import draft_class_report
        conn = _make_db()
        result = draft_class_report(conn, 1)
        self.assertIn("Alice", result["text_body"])
        self.assertIn("Bob", result["text_body"])

    def test_report_class_not_found(self):
        from mandarin.openclaw.email_mcp import draft_class_report
        conn = _make_db()
        result = draft_class_report(conn, 999)
        self.assertIn("error", result)

    def test_report_struggling_detail(self):
        from mandarin.openclaw.email_mcp import draft_class_report
        conn = _make_db()
        result = draft_class_report(conn, 1)
        # Should mention "Needs attention" section
        self.assertIn("Needs attention", result["text_body"])


class TestSendEmail(unittest.TestCase):

    def test_no_smtp_configured(self):
        from mandarin.openclaw.email_mcp import send_email
        with patch.dict("os.environ", {}, clear=True):
            result = send_email("test@example.com", "Test", "Body")
            self.assertEqual(result["status"], "not_sent")
            self.assertIn("SMTP not configured", result["reason"])

    @patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_USER": ""})
    def test_empty_smtp_config(self):
        from mandarin.openclaw.email_mcp import send_email
        result = send_email("test@example.com", "Test", "Body")
        self.assertEqual(result["status"], "not_sent")

    @patch("smtplib.SMTP")
    @patch.dict("os.environ", {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "user@test.com",
        "SMTP_PASSWORD": "pass123",
        "SMTP_FROM": "noreply@aelu.app",
    })
    def test_successful_send(self, mock_smtp_class):
        from mandarin.openclaw.email_mcp import send_email
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = send_email("student@example.com", "Weekly Progress", "Your stats...")
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["to"], "student@example.com")

    @patch("smtplib.SMTP")
    @patch.dict("os.environ", {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_USER": "user@test.com",
        "SMTP_PASSWORD": "pass123",
    })
    def test_send_with_html(self, mock_smtp_class):
        from mandarin.openclaw.email_mcp import send_email
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = send_email(
            "student@example.com", "Test",
            "Plain text", "<h1>HTML</h1>"
        )
        self.assertEqual(result["status"], "sent")

    @patch("smtplib.SMTP")
    @patch.dict("os.environ", {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_USER": "user@test.com",
        "SMTP_PASSWORD": "pass123",
    })
    def test_send_failure(self, mock_smtp_class):
        from mandarin.openclaw.email_mcp import send_email
        mock_smtp_class.side_effect = Exception("Connection refused")

        result = send_email("student@example.com", "Test", "Body")
        self.assertEqual(result["status"], "error")
        self.assertIn("Connection refused", result["error"])

    @patch.dict("os.environ", {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_USER": "user@test.com",
        "SMTP_PASSWORD": "pass123",
    })
    def test_from_defaults_to_smtp_user(self):
        from mandarin.openclaw.email_mcp import send_email
        # The from_addr should default to SMTP_USER when SMTP_FROM is not set
        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

            send_email("to@test.com", "Test", "Body")
            # sendmail should have been called
            call_args = mock_server.sendmail.call_args
            self.assertEqual(call_args[0][0], "user@test.com")


if __name__ == "__main__":
    unittest.main()
