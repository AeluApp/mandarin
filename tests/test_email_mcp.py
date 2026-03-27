"""Tests for Email MCP integration module (teacher communication)."""

import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, email TEXT, display_name TEXT,
            streak_days INTEGER DEFAULT 0
        );
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            started_at TEXT DEFAULT (datetime('now')),
            session_outcome TEXT DEFAULT 'completed',
            items_completed INTEGER DEFAULT 0,
            items_correct INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0
        );
        CREATE TABLE grammar_point (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );
        CREATE TABLE grammar_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, grammar_point_id INTEGER,
            mastery_score REAL DEFAULT 0,
            studied_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE classroom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            teacher_id INTEGER
        );
        CREATE TABLE classroom_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER, user_id INTEGER,
            role TEXT DEFAULT 'student'
        );

        -- Seed data
        INSERT INTO user (id, email, display_name, streak_days)
        VALUES (1, 'student@aelu.app', 'Alice', 12);
        INSERT INTO user (id, email, display_name, streak_days)
        VALUES (2, 'teacher@aelu.app', 'Ms. Chen', 0);
        INSERT INTO user (id, email, display_name)
        VALUES (3, 'student2@aelu.app', 'Bob');
        INSERT INTO user (id, email, display_name)
        VALUES (4, 'inactive@aelu.app', NULL);

        INSERT INTO session_log (user_id, started_at, session_outcome, items_completed, items_correct, duration_seconds)
        VALUES (1, datetime('now', '-1 day'), 'completed', 20, 16, 900);
        INSERT INTO session_log (user_id, started_at, session_outcome, items_completed, items_correct, duration_seconds)
        VALUES (1, datetime('now', '-3 days'), 'completed', 15, 10, 600);
        INSERT INTO session_log (user_id, started_at, session_outcome, items_completed, items_correct, duration_seconds)
        VALUES (3, datetime('now', '-2 days'), 'completed', 10, 3, 300);

        INSERT INTO grammar_point (id, name) VALUES (1, 'Subject-Verb-Object');
        INSERT INTO grammar_point (id, name) VALUES (2, 'Aspect particle 了');

        INSERT INTO grammar_progress (user_id, grammar_point_id, mastery_score)
        VALUES (1, 1, 0.85);
        INSERT INTO grammar_progress (user_id, grammar_point_id, mastery_score)
        VALUES (1, 2, 0.45);

        INSERT INTO classroom (id, name, teacher_id) VALUES (1, 'HSK 1 Morning', 2);
        INSERT INTO classroom_member (classroom_id, user_id, role) VALUES (1, 1, 'student');
        INSERT INTO classroom_member (classroom_id, user_id, role) VALUES (1, 3, 'student');
        INSERT INTO classroom_member (classroom_id, user_id, role) VALUES (1, 4, 'student');
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
        self.assertEqual(result["metadata"]["streak"], 12)
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

    @patch("mandarin.settings.SMTP_USER", "")
    @patch("mandarin.settings.SMTP_HOST", "")
    def test_no_smtp_configured(self):
        from mandarin.openclaw.email_mcp import send_email
        result = send_email("test@example.com", "Test", "Body")
        self.assertEqual(result["status"], "not_sent")
        self.assertIn("SMTP not configured", result["reason"])

    @patch("mandarin.settings.SMTP_HOST", "")
    @patch("mandarin.settings.SMTP_USER", "")
    def test_empty_smtp_config(self):
        from mandarin.openclaw.email_mcp import send_email
        result = send_email("test@example.com", "Test", "Body")
        self.assertEqual(result["status"], "not_sent")

    @patch("smtplib.SMTP")
    @patch("mandarin.settings.SMTP_FROM", "noreply@aelu.app")
    @patch("mandarin.settings.SMTP_PASSWORD", "pass123")
    @patch("mandarin.settings.SMTP_USER", "user@test.com")
    @patch("mandarin.settings.SMTP_PORT", 587)
    @patch("mandarin.settings.SMTP_HOST", "smtp.test.com")
    def test_successful_send(self, mock_smtp_class):
        from mandarin.openclaw.email_mcp import send_email
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = send_email("student@example.com", "Weekly Progress", "Your stats...")
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["to"], "student@example.com")

    @patch("smtplib.SMTP")
    @patch("mandarin.settings.SMTP_FROM", "")
    @patch("mandarin.settings.SMTP_PASSWORD", "pass123")
    @patch("mandarin.settings.SMTP_USER", "user@test.com")
    @patch("mandarin.settings.SMTP_PORT", 587)
    @patch("mandarin.settings.SMTP_HOST", "smtp.test.com")
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
    @patch("mandarin.settings.SMTP_FROM", "")
    @patch("mandarin.settings.SMTP_PASSWORD", "pass123")
    @patch("mandarin.settings.SMTP_USER", "user@test.com")
    @patch("mandarin.settings.SMTP_PORT", 587)
    @patch("mandarin.settings.SMTP_HOST", "smtp.test.com")
    def test_send_failure(self, mock_smtp_class):
        from mandarin.openclaw.email_mcp import send_email
        mock_smtp_class.side_effect = Exception("Connection refused")

        result = send_email("student@example.com", "Test", "Body")
        self.assertEqual(result["status"], "error")
        self.assertIn("Connection refused", result["error"])

    @patch("mandarin.settings.SMTP_FROM", "")
    @patch("mandarin.settings.SMTP_PASSWORD", "pass123")
    @patch("mandarin.settings.SMTP_USER", "user@test.com")
    @patch("mandarin.settings.SMTP_PORT", 587)
    @patch("mandarin.settings.SMTP_HOST", "smtp.test.com")
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
