"""Tests for Doc 23 B-04: Teacher Communication Drafts."""

import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.teacher_comms import (
    draft_teacher_outreach,
    draft_pilot_invitation,
    get_pending_drafts,
    approve_draft,
    reject_draft,
    edit_draft,
    mark_sent,
)


from tests.shared_db import make_test_db as _make_db


def _seed_teacher_lead(conn):
    """Insert a teacher lead for tests that need one."""
    conn.execute(
        "INSERT OR IGNORE INTO teacher_lead (id, name, platform, status) "
        "VALUES (1, 'Test Teacher', 'italki', 'qualified')"
    )
    conn.commit()


class TestDraftTeacherOutreach(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        _seed_teacher_lead(self.conn)

    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False)
    def test_template_draft_without_llm(self, mock_avail):
        draft_id = draft_teacher_outreach(self.conn, 1, "pilot_invitation")
        self.assertIsNotNone(draft_id)

        draft = self.conn.execute(
            "SELECT * FROM email_draft WHERE id = ?", (draft_id,)
        ).fetchone()
        self.assertEqual(draft["status"], "draft")
        self.assertIn("Test Teacher", draft["body_text"])
        self.assertEqual(draft["purpose"], "pilot_invitation")

    def test_nonexistent_lead(self):
        result = draft_teacher_outreach(self.conn, 9999, "test")
        self.assertIsNone(result)


class TestDraftPilotInvitation(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        _seed_teacher_lead(self.conn)

    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False)
    def test_creates_invitation(self, mock_avail):
        draft_id = draft_pilot_invitation(self.conn, 1)
        self.assertIsNotNone(draft_id)


class TestGetPendingDrafts(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        _seed_teacher_lead(self.conn)

    def test_empty_queue(self):
        drafts = get_pending_drafts(self.conn)
        self.assertEqual(drafts, [])

    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False)
    def test_pending_drafts(self, mock_avail):
        draft_teacher_outreach(self.conn, 1, "test")
        drafts = get_pending_drafts(self.conn)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["recipient_name"], "Test Teacher")


class TestApproveRejectDraft(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        self.conn.execute("""
            INSERT INTO email_draft
            (recipient_type, recipient_id, subject, body_text, purpose, status)
            VALUES ('teacher_lead', 1, 'Test', 'Body', 'test', 'draft')
        """)
        self.draft_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.commit()

    def test_approve(self):
        success = approve_draft(self.conn, self.draft_id, approved_by=1)
        self.assertTrue(success)

        draft = self.conn.execute(
            "SELECT * FROM email_draft WHERE id = ?", (self.draft_id,)
        ).fetchone()
        self.assertEqual(draft["status"], "approved")
        self.assertEqual(draft["approved_by"], 1)
        self.assertIsNotNone(draft["approved_at"])

    def test_reject(self):
        success = reject_draft(self.conn, self.draft_id, reason="not good")
        self.assertTrue(success)

        draft = self.conn.execute(
            "SELECT * FROM email_draft WHERE id = ?", (self.draft_id,)
        ).fetchone()
        self.assertEqual(draft["status"], "rejected")

    def test_approve_nonexistent(self):
        success = approve_draft(self.conn, 9999, approved_by=1)
        self.assertFalse(success)


class TestEditDraft(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        self.conn.execute("""
            INSERT INTO email_draft
            (recipient_type, recipient_id, subject, body_text, status)
            VALUES ('teacher_lead', 1, 'Original', 'Original body', 'draft')
        """)
        self.draft_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.commit()

    def test_edit_subject(self):
        success = edit_draft(self.conn, self.draft_id, subject="New Subject")
        self.assertTrue(success)

        draft = self.conn.execute(
            "SELECT * FROM email_draft WHERE id = ?", (self.draft_id,)
        ).fetchone()
        self.assertEqual(draft["subject"], "New Subject")
        self.assertEqual(draft["body_text"], "Original body")

    def test_edit_body(self):
        success = edit_draft(self.conn, self.draft_id, body_text="New body")
        self.assertTrue(success)

    def test_edit_nonexistent(self):
        success = edit_draft(self.conn, 9999, subject="test")
        self.assertFalse(success)


class TestMarkSent(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        self.conn.execute("""
            INSERT INTO email_draft
            (recipient_type, recipient_id, subject, body_text, status)
            VALUES ('teacher_lead', 1, 'Test', 'Body', 'approved')
        """)
        self.draft_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.commit()

    def test_mark_sent(self):
        success = mark_sent(self.conn, self.draft_id)
        self.assertTrue(success)

        draft = self.conn.execute(
            "SELECT * FROM email_draft WHERE id = ?", (self.draft_id,)
        ).fetchone()
        self.assertEqual(draft["status"], "sent")
        self.assertIsNotNone(draft["sent_at"])

    def test_cannot_send_draft(self):
        # Change status back to draft
        self.conn.execute(
            "UPDATE email_draft SET status = 'draft' WHERE id = ?",
            (self.draft_id,),
        )
        self.conn.commit()
        success = mark_sent(self.conn, self.draft_id)
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
