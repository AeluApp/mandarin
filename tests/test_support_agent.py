"""Tests for mandarin.openclaw.support_agent — FAQ matching, escalation, ticket management."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone, UTC
from unittest.mock import MagicMock, patch

from tests.shared_db import make_test_db
from mandarin.openclaw.support_agent import (
    SupportAgent,
    SupportContext,
    SupportKnowledge,
    SupportResponse,
)


def _make_conn():
    """Create an in-memory SQLite DB with the tables support_agent expects."""
    conn = make_test_db()
    conn.execute("PRAGMA foreign_keys=OFF")
    # Add columns that support_agent code references but are not yet in schema.sql
    try:
        conn.execute("ALTER TABLE user ADD COLUMN streak_days INTEGER DEFAULT 0")
    except Exception:
        pass  # Column may already exist
    conn.commit()
    return conn


def _seed_user(conn, user_id=1, email="test@aelu.app", tier="free",
               streak=0, days_ago=10):
    created = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO user (id, email, password_hash, subscription_tier, subscription_status, streak_days, created_at) "
        "VALUES (?, ?, 'test_hash', ?, 'active', ?, ?)",
        (user_id, email, tier, streak, created),
    )
    conn.commit()


class TestSupportContextDefaults(unittest.TestCase):
    """SupportContext dataclass construction and defaults."""

    def test_minimal_construction(self):
        ctx = SupportContext(user_id=1)
        self.assertEqual(ctx.user_id, 1)
        self.assertEqual(ctx.user_email, "")
        self.assertEqual(ctx.subscription_tier, "free")
        self.assertEqual(ctx.account_age_days, 0)
        self.assertEqual(ctx.total_sessions, 0)
        self.assertEqual(ctx.recent_crashes, 0)

    def test_full_construction(self):
        ctx = SupportContext(
            user_id=5, user_email="u@example.com", subscription_tier="paid",
            account_age_days=30, total_sessions=12, last_session_date="2026-03-01",
            streak_days=7, platform="ios", recent_crashes=1, recent_client_errors=2,
        )
        self.assertEqual(ctx.user_email, "u@example.com")
        self.assertEqual(ctx.platform, "ios")


class TestSupportContextFromUser(unittest.TestCase):
    """SupportContext.from_user DB population."""

    def test_missing_user_returns_minimal(self):
        conn = _make_conn()
        ctx = SupportContext.from_user(conn, user_id=999)
        self.assertEqual(ctx.user_id, 999)
        self.assertEqual(ctx.user_email, "")

    def test_basic_user(self):
        conn = _make_conn()
        _seed_user(conn, user_id=1, email="a@b.com", tier="paid", streak=5, days_ago=20)
        ctx = SupportContext.from_user(conn, 1)
        self.assertEqual(ctx.user_email, "a@b.com")
        self.assertEqual(ctx.subscription_tier, "paid")
        self.assertGreaterEqual(ctx.account_age_days, 19)  # allow clock drift
        self.assertEqual(ctx.streak_days, 5)

    def test_session_count(self):
        conn = _make_conn()
        _seed_user(conn, 1)
        now_str = datetime.now(UTC).isoformat()
        for _ in range(3):
            conn.execute("INSERT INTO session_log (user_id, started_at) VALUES (1, ?)", (now_str,))
        conn.commit()
        ctx = SupportContext.from_user(conn, 1)
        self.assertEqual(ctx.total_sessions, 3)

    def test_last_session_date(self):
        conn = _make_conn()
        _seed_user(conn, 1)
        conn.execute("INSERT INTO session_log (user_id, started_at) VALUES (1, '2026-03-10 12:00:00')")
        conn.commit()
        ctx = SupportContext.from_user(conn, 1)
        self.assertEqual(ctx.last_session_date, "2026-03-10 12:00:00")

    def test_crash_count(self):
        conn = _make_conn()
        _seed_user(conn, 1)
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO crash_log (timestamp, error_type) VALUES (?, 'TestError')", (now_str,))
        conn.execute("INSERT INTO crash_log (timestamp, error_type) VALUES (?, 'TestError')", (now_str,))
        conn.commit()
        ctx = SupportContext.from_user(conn, 1)
        self.assertEqual(ctx.recent_crashes, 2)


class TestSupportResponseDefaults(unittest.TestCase):
    def test_defaults(self):
        r = SupportResponse(answer="ok", confidence=0.9, category="billing")
        self.assertFalse(r.escalate)
        self.assertIsNone(r.context)
        self.assertEqual(r.suggested_actions, [])


class TestSupportKnowledge(unittest.TestCase):
    """FAQ knowledge base matching."""

    def setUp(self):
        self.kb = SupportKnowledge()

    def test_categories_include_all_five(self):
        cats = self.kb.get_categories()
        for c in ("account", "billing", "learning", "privacy", "technical"):
            self.assertIn(c, cats)

    def test_entries_by_category(self):
        account_entries = self.kb.get_entries_by_category("account")
        self.assertGreater(len(account_entries), 0)
        for e in account_entries:
            self.assertEqual(e["category"], "account")

    def test_password_reset_match(self):
        match, conf = self.kb.find_match("How do I reset my password?")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "account")
        self.assertGreaterEqual(conf, 0.7)

    def test_billing_pricing_match(self):
        match, conf = self.kb.find_match("What are the subscription plans and pricing?")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "billing")

    def test_learning_spaced_repetition_match(self):
        match, conf = self.kb.find_match("This word came back again, why am I reviewing it?")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "learning")

    def test_technical_crash_match(self):
        match, conf = self.kb.find_match("The app keeps crashing on my phone")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "technical")

    def test_privacy_gdpr_match(self):
        match, conf = self.kb.find_match("Are you GDPR compliant?")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "privacy")

    def test_keyword_fallback_low_confidence(self):
        match, conf = self.kb.find_match("something about my account")
        # Should match via keyword fallback with lower confidence
        if match:
            self.assertLessEqual(conf, 0.75)

    def test_no_match_gibberish(self):
        match, conf = self.kb.find_match("asdfghjkl qwertyuiop")
        self.assertIsNone(match)
        self.assertEqual(conf, 0.0)

    def test_delete_account_match(self):
        match, _ = self.kb.find_match("I want to delete my account")
        self.assertIsNotNone(match)
        self.assertIn("delete", match["answer"].lower())

    def test_2fa_match(self):
        match, _ = self.kb.find_match("How do I enable 2FA?")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "account")

    def test_refund_match(self):
        match, _ = self.kb.find_match("I want a refund for my payment")
        self.assertIsNotNone(match)
        self.assertEqual(match["category"], "billing")
        self.assertTrue(match["requires_db"])


class TestSupportAgentHandleRequest(unittest.TestCase):
    """SupportAgent.handle_request covering match, personalization, escalation."""

    def setUp(self):
        self.agent = SupportAgent()

    def test_matched_request_no_escalation(self):
        resp = self.agent.handle_request("How do I reset my password?")
        self.assertFalse(resp.escalate)
        self.assertEqual(resp.category, "account")
        self.assertGreaterEqual(resp.confidence, 0.7)

    def test_unmatched_request_escalates(self):
        resp = self.agent.handle_request("zzzz nothing matches zzzzz")
        self.assertTrue(resp.escalate)
        self.assertEqual(resp.category, "unknown")

    def test_personalization_free_tier_mention(self):
        conn = _make_conn()
        _seed_user(conn, 1, tier="free")
        # The billing answer about "Pro" should get free-tier appendix
        resp = self.agent.handle_request("What is the cost of subscription plans?", user_id=1, conn=conn)
        self.assertIn("free tier", resp.answer.lower())

    def test_no_personalization_without_context(self):
        resp = self.agent.handle_request("What are the subscription plans?")
        # Without context, the answer should NOT have the appended "You're currently on the free tier." line
        self.assertNotIn("You're currently on the free tier", resp.answer)

    def test_billing_dispute_escalates(self):
        resp = self.agent.handle_request("This is an unauthorized charge, possible fraud")
        self.assertTrue(resp.escalate)

    def test_angry_language_escalates(self):
        resp = self.agent.handle_request("This is unacceptable, worst app ever, I'll sue you")
        self.assertTrue(resp.escalate)

    def test_paid_user_technical_issue_escalates(self):
        conn = _make_conn()
        _seed_user(conn, 1, tier="paid")
        resp = self.agent.handle_request("Audio is not working in the app", user_id=1, conn=conn)
        self.assertTrue(resp.escalate)

    def test_crash_with_many_recent_crashes_escalates(self):
        conn = _make_conn()
        _seed_user(conn, 1)
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        for _ in range(5):
            conn.execute("INSERT INTO crash_log (timestamp, error_type) VALUES (?, 'TestError')", (now_str,))
        conn.commit()
        resp = self.agent.handle_request("This bug is crashing the app", user_id=1, conn=conn)
        self.assertTrue(resp.escalate)


class TestSuggestedActions(unittest.TestCase):
    def test_technical_with_crashes(self):
        agent = SupportAgent()
        conn = _make_conn()
        _seed_user(conn, 1)
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO crash_log (timestamp, error_type) VALUES (?, 'TestError')", (now_str,))
        conn.commit()
        resp = agent.handle_request("The app keeps crashing", user_id=1, conn=conn)
        self.assertTrue(any("crash" in a.lower() for a in resp.suggested_actions))

    def test_billing_paid_user_stripe_action(self):
        agent = SupportAgent()
        conn = _make_conn()
        _seed_user(conn, 1, tier="paid")
        resp = agent.handle_request("My payment failed on my card", user_id=1, conn=conn)
        self.assertTrue(any("stripe" in a.lower() for a in resp.suggested_actions))

    def test_learning_zero_sessions_onboarding_action(self):
        agent = SupportAgent()
        conn = _make_conn()
        _seed_user(conn, 1)
        resp = agent.handle_request("I want to learn about session types", user_id=1, conn=conn)
        self.assertTrue(any("onboarding" in a.lower() for a in resp.suggested_actions))


class TestTicketManagement(unittest.TestCase):
    """SupportAgent static ticket methods."""

    def test_create_ticket(self):
        conn = _make_conn()
        resp = SupportResponse(answer="test", confidence=0.5, category="billing", escalate=True)
        ticket_id = SupportAgent.create_ticket(conn, 1, "help me", resp)
        self.assertIsInstance(ticket_id, int)
        self.assertGreater(ticket_id, 0)

    def test_get_open_tickets(self):
        conn = _make_conn()
        resp = SupportResponse(answer="a", confidence=0.9, category="account")
        SupportAgent.create_ticket(conn, 1, "msg1", resp)
        SupportAgent.create_ticket(conn, 2, "msg2", resp)
        tickets = SupportAgent.get_open_tickets(conn)
        self.assertEqual(len(tickets), 2)

    def test_resolve_ticket(self):
        conn = _make_conn()
        resp = SupportResponse(answer="a", confidence=0.9, category="account")
        tid = SupportAgent.create_ticket(conn, 1, "msg", resp)
        ok = SupportAgent.resolve_ticket(conn, tid, "Fixed")
        self.assertTrue(ok)
        remaining = SupportAgent.get_open_tickets(conn)
        self.assertEqual(len(remaining), 0)

    def test_resolve_nonexistent_ticket(self):
        conn = _make_conn()
        # Create table first via a ticket
        resp = SupportResponse(answer="a", confidence=0.9, category="account")
        SupportAgent.create_ticket(conn, 1, "msg", resp)
        ok = SupportAgent.resolve_ticket(conn, 9999, "nope")
        self.assertFalse(ok)

    def test_get_open_tickets_no_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        tickets = SupportAgent.get_open_tickets(conn)
        self.assertEqual(tickets, [])

    def test_resolve_ticket_already_resolved(self):
        conn = _make_conn()
        resp = SupportResponse(answer="a", confidence=0.9, category="account")
        tid = SupportAgent.create_ticket(conn, 1, "msg", resp)
        SupportAgent.resolve_ticket(conn, tid, "Done")
        ok = SupportAgent.resolve_ticket(conn, tid, "Again")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
