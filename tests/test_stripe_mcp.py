"""Tests for Stripe MCP integration module."""

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
            subscription_tier TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            subscription_status TEXT,
            subscription_end_date TEXT
        );
        INSERT INTO user (id, email, display_name, subscription_tier, stripe_customer_id, subscription_status)
        VALUES (1, 'test@aelu.app', 'Test User', 'pro', 'cus_test123', 'active');
        INSERT INTO user (id, email, display_name, subscription_tier)
        VALUES (2, 'free@aelu.app', 'Free User', 'free');
    """)
    return conn


class TestStripeMCPImport(unittest.TestCase):

    def test_module_imports(self):
        from mandarin.openclaw import stripe_mcp
        self.assertTrue(hasattr(stripe_mcp, 'create_stripe_tools'))
        self.assertTrue(hasattr(stripe_mcp, 'get_subscription_status'))
        self.assertTrue(hasattr(stripe_mcp, 'get_payment_history'))
        self.assertTrue(hasattr(stripe_mcp, 'handle_failed_payment'))
        self.assertTrue(hasattr(stripe_mcp, 'issue_refund'))

    def test_create_stripe_tools_structure(self):
        from mandarin.openclaw.stripe_mcp import create_stripe_tools
        tools = create_stripe_tools()
        self.assertIsInstance(tools, list)
        self.assertEqual(len(tools), 4)

        names = {t["name"] for t in tools}
        self.assertIn("get_subscription_status", names)
        self.assertIn("get_payment_history", names)
        self.assertIn("handle_failed_payment", names)
        self.assertIn("issue_refund", names)

    def test_refund_requires_confirmation(self):
        from mandarin.openclaw.stripe_mcp import create_stripe_tools
        tools = create_stripe_tools()
        refund_tool = next(t for t in tools if t["name"] == "issue_refund")
        self.assertTrue(refund_tool.get("requires_confirmation"))

    def test_tools_have_functions(self):
        from mandarin.openclaw.stripe_mcp import create_stripe_tools
        tools = create_stripe_tools()
        for tool in tools:
            self.assertTrue(callable(tool["function"]))
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)


class TestGetStripe(unittest.TestCase):

    @patch("mandarin.settings.STRIPE_SECRET_KEY", "")
    def test_returns_none_without_key(self):
        from mandarin.openclaw.stripe_mcp import _get_stripe
        _get_stripe()
        # Returns None if no STRIPE_SECRET_KEY set
        # (may or may not have stripe package)

    @patch("mandarin.settings.STRIPE_SECRET_KEY", "")
    def test_returns_none_with_empty_key(self):
        from mandarin.openclaw.stripe_mcp import _get_stripe
        result = _get_stripe()
        self.assertIsNone(result)


class TestSubscriptionStatus(unittest.TestCase):

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_subscription_status_no_stripe(self, mock_stripe):
        from mandarin.openclaw.stripe_mcp import get_subscription_status
        # Mock db.connection to return our test db
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            result = get_subscription_status(1)
            self.assertEqual(result["user_id"], 1)
            self.assertEqual(result["tier"], "pro")
            self.assertEqual(result["status"], "active")
            self.assertEqual(result["email"], "test@aelu.app")

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_subscription_status_user_not_found(self, mock_stripe):
        from mandarin.openclaw.stripe_mcp import get_subscription_status
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            result = get_subscription_status(999)
            self.assertIn("error", result)

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_subscription_free_user(self, mock_stripe):
        from mandarin.openclaw.stripe_mcp import get_subscription_status
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            result = get_subscription_status(2)
            self.assertEqual(result["tier"], "free")
            self.assertEqual(result["status"], "none")


class TestPaymentHistory(unittest.TestCase):

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_payment_history_no_stripe(self, mock_stripe):
        from mandarin.openclaw.stripe_mcp import get_payment_history
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            result = get_payment_history(1)
            self.assertEqual(result["payments"], [])
            self.assertIn("note", result)

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_payment_history_no_customer_id(self, mock_stripe):
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            from mandarin.openclaw.stripe_mcp import get_payment_history
            result = get_payment_history(2)
            self.assertEqual(result["payments"], [])


class TestHandleFailedPayment(unittest.TestCase):

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_no_issues_detected(self, mock_stripe):
        from mandarin.openclaw.stripe_mcp import handle_failed_payment
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            result = handle_failed_payment(1)
            self.assertIn("recommendations", result)
            self.assertEqual(result["recommendations"][0]["action"], "none")

    @patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None)
    def test_user_not_found(self, mock_stripe):
        from mandarin.openclaw.stripe_mcp import handle_failed_payment
        conn = _make_db()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("mandarin.db.connection", return_value=mock_conn):
            result = handle_failed_payment(999)
            self.assertIn("error", result)


class TestIssueRefund(unittest.TestCase):

    def test_refund_no_stripe(self):
        from mandarin.openclaw.stripe_mcp import issue_refund
        with patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=None):
            result = issue_refund("inv_test123")
            self.assertEqual(result["error"], "Stripe not configured")

    def test_refund_with_mock_stripe(self):
        from mandarin.openclaw.stripe_mcp import issue_refund
        mock_stripe = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.charge = "ch_test123"
        mock_stripe.Invoice.retrieve.return_value = mock_invoice

        mock_refund = MagicMock()
        mock_refund.id = "re_test123"
        mock_refund.amount = 999
        mock_refund.currency = "usd"
        mock_stripe.Refund.create.return_value = mock_refund

        with patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=mock_stripe):
            result = issue_refund("inv_test123", reason="test refund")
            self.assertEqual(result["status"], "refunded")
            self.assertEqual(result["refund_id"], "re_test123")
            self.assertAlmostEqual(result["amount"], 9.99)

    def test_refund_no_charge(self):
        from mandarin.openclaw.stripe_mcp import issue_refund
        mock_stripe = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.charge = None
        mock_stripe.Invoice.retrieve.return_value = mock_invoice

        with patch("mandarin.openclaw.stripe_mcp._get_stripe", return_value=mock_stripe):
            result = issue_refund("inv_test123")
            self.assertEqual(result["error"], "No charge found for this invoice")


if __name__ == "__main__":
    unittest.main()
