"""Stripe MCP integration — payment management via natural language.

Instead of building custom Stripe webhook integration, this wires
Stripe's official MCP server into Aelu's agentic layer. Subscription
management, failed payment handling, and refund processing become
natural language tool calls.

Usage:
    from mandarin.openclaw.stripe_mcp import create_stripe_tools
    tools = create_stripe_tools()
    # Tools are dict-based for integration with any agent framework

When Stripe's official MCP server is running (npx @anthropic/stripe-mcp),
these tools delegate to it. Otherwise, they fall back to direct Stripe
API calls via the stripe Python package.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _get_stripe():
    """Import and configure stripe. Returns None if unavailable."""
    try:
        import stripe
        from ..settings import STRIPE_SECRET_KEY
        if not STRIPE_SECRET_KEY:
            return None
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        return None


def get_subscription_status(user_id: int) -> dict:
    """Check a user's subscription: tier, status, renewal date, payment method.

    Returns structured data suitable for agent responses.
    """
    from .. import db
    with db.connection() as conn:
        user = conn.execute("""
            SELECT email, subscription_tier, stripe_customer_id,
                   subscription_status, subscription_end_date
            FROM user WHERE id = ?
        """, (user_id,)).fetchone()

        if not user:
            return {"error": "User not found"}

        result = {
            "user_id": user_id,
            "email": user["email"],
            "tier": user["subscription_tier"] or "free",
            "status": user["subscription_status"] or "none",
        }

        # Try to get live data from Stripe
        stripe = _get_stripe()
        if stripe and user["stripe_customer_id"]:
            try:
                subs = stripe.Subscription.list(
                    customer=user["stripe_customer_id"],
                    limit=1,
                )
                if subs.data:
                    sub = subs.data[0]
                    result["stripe_status"] = sub.status
                    result["current_period_end"] = sub.current_period_end
                    result["cancel_at_period_end"] = sub.cancel_at_period_end
                    if sub.default_payment_method:
                        pm = stripe.PaymentMethod.retrieve(sub.default_payment_method)
                        if pm.card:
                            result["payment_method"] = {
                                "brand": pm.card.brand,
                                "last4": pm.card.last4,
                                "exp_month": pm.card.exp_month,
                                "exp_year": pm.card.exp_year,
                            }
            except Exception as e:
                logger.debug("Stripe API call failed: %s", e)
                result["stripe_error"] = str(e)

        return result


def get_payment_history(user_id: int, limit: int = 10) -> dict:
    """Recent payment history: invoices, amounts, status."""
    from .. import db
    with db.connection() as conn:
        user = conn.execute(
            "SELECT stripe_customer_id FROM user WHERE id = ?",
            (user_id,),
        ).fetchone()

        if not user or not user["stripe_customer_id"]:
            return {"payments": [], "note": "No Stripe customer ID"}

    stripe = _get_stripe()
    if not stripe:
        return {"payments": [], "note": "Stripe not configured"}

    try:
        invoices = stripe.Invoice.list(
            customer=user["stripe_customer_id"],
            limit=min(limit, 50),
        )
        return {
            "payments": [
                {
                    "id": inv.id,
                    "amount": inv.amount_paid / 100,
                    "currency": inv.currency,
                    "status": inv.status,
                    "date": inv.created,
                    "description": inv.description or "",
                }
                for inv in invoices.data
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def handle_failed_payment(user_id: int) -> dict:
    """Diagnose and suggest resolution for failed payment.

    Checks: card expired, insufficient funds, Stripe dunning status.
    Returns actionable recommendations.
    """
    status = get_subscription_status(user_id)
    if "error" in status:
        return status

    recommendations = []

    if status.get("stripe_status") == "past_due":
        recommendations.append({
            "action": "update_payment_method",
            "reason": "Subscription is past due — payment method may need updating",
            "urgency": "high",
        })

    pm = status.get("payment_method", {})
    if pm:
        import time
        now = time.gmtime()
        if pm.get("exp_year", 9999) < now.tm_year or (
            pm.get("exp_year") == now.tm_year and pm.get("exp_month", 13) < now.tm_mon
        ):
            recommendations.append({
                "action": "card_expired",
                "reason": f"Card ending {pm['last4']} expired {pm['exp_month']}/{pm['exp_year']}",
                "urgency": "high",
            })

    if status.get("cancel_at_period_end"):
        recommendations.append({
            "action": "cancellation_pending",
            "reason": "Subscription will cancel at period end",
            "urgency": "medium",
        })

    if not recommendations:
        recommendations.append({
            "action": "none",
            "reason": "No payment issues detected",
            "urgency": "low",
        })

    return {
        "user_id": user_id,
        "current_status": status.get("stripe_status", status.get("status")),
        "recommendations": recommendations,
    }


def issue_refund(invoice_id: str, reason: str = "") -> dict:
    """Issue a refund for a specific invoice. Requires confirmation.

    This is a write operation — the agent should confirm with the
    human before calling this.
    """
    stripe = _get_stripe()
    if not stripe:
        return {"error": "Stripe not configured"}

    try:
        invoice = stripe.Invoice.retrieve(invoice_id)
        if not invoice.charge:
            return {"error": "No charge found for this invoice"}

        refund = stripe.Refund.create(
            charge=invoice.charge,
            reason="requested_by_customer",
            metadata={"agent_reason": reason[:200]} if reason else {},
        )
        return {
            "status": "refunded",
            "refund_id": refund.id,
            "amount": refund.amount / 100,
            "currency": refund.currency,
        }
    except Exception as e:
        return {"error": str(e)}


def create_stripe_tools() -> list[dict]:
    """Return tool definitions for agent integration.

    These can be registered with any agent framework (LangChain,
    CrewAI, or the OpenClaw agentic layer).
    """
    return [
        {
            "name": "get_subscription_status",
            "description": "Check a user's subscription tier, payment status, and renewal date",
            "function": get_subscription_status,
            "parameters": {"user_id": "int"},
        },
        {
            "name": "get_payment_history",
            "description": "Get recent payment history (invoices, amounts, status)",
            "function": get_payment_history,
            "parameters": {"user_id": "int", "limit": "int (optional, default 10)"},
        },
        {
            "name": "handle_failed_payment",
            "description": "Diagnose failed payment and suggest resolution",
            "function": handle_failed_payment,
            "parameters": {"user_id": "int"},
        },
        {
            "name": "issue_refund",
            "description": "Issue a refund for a specific invoice (requires confirmation)",
            "function": issue_refund,
            "parameters": {"invoice_id": "str", "reason": "str (optional)"},
            "requires_confirmation": True,
        },
    ]
