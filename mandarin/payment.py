"""Stripe payment integration — checkout, billing portal, webhooks."""

import logging
import sqlite3
from datetime import datetime, timezone

import stripe

from .email import send_subscription_confirmed, send_subscription_cancelled
from .settings import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, BASE_URL

logger = logging.getLogger(__name__)

stripe.api_key = STRIPE_SECRET_KEY


def create_checkout_session(user_id: int, email: str) -> str:
    """Create a Stripe Checkout session. Returns the checkout URL."""
    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Mandarin — Full Access"},
                "unit_amount": 990,  # $9.90/mo
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }],
        mode="subscription",
        success_url=BASE_URL + "/?payment=success",
        cancel_url=BASE_URL + "/?payment=cancelled",
        metadata={"user_id": str(user_id)},
    )
    return session.url


def create_billing_portal_session(stripe_customer_id: str) -> str:
    """Create a Stripe Billing Portal session. Returns the portal URL."""
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=BASE_URL + "/",
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str, conn: sqlite3.Connection) -> dict:
    """Verify and process a Stripe webhook event.

    Returns a dict with event type and processing result.
    Raises ValueError on signature verification failure.
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if event_type == "checkout.session.completed":
        user_id = data.get("metadata", {}).get("user_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            conn.execute(
                """UPDATE user SET stripe_customer_id = ?, subscription_tier = 'paid',
                   subscription_status = 'active', updated_at = ? WHERE id = ?""",
                (customer_id, now, int(user_id))
            )
            conn.commit()
            logger.info("Checkout completed: user %s upgraded to paid", user_id)
            # Send subscription confirmation email
            row = conn.execute(
                "SELECT email, display_name FROM user WHERE id = ?",
                (int(user_id),)
            ).fetchone()
            if row:
                send_subscription_confirmed(row[0], row[1] or "")

    elif event_type == "invoice.paid":
        customer_id = data.get("customer")
        if customer_id:
            conn.execute(
                """UPDATE user SET subscription_status = 'active', updated_at = ?
                   WHERE stripe_customer_id = ?""",
                (now, customer_id)
            )
            conn.commit()
            logger.info("Invoice paid: customer %s subscription renewed", customer_id)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            conn.execute(
                """UPDATE user SET subscription_tier = 'free', subscription_status = 'cancelled',
                   updated_at = ? WHERE stripe_customer_id = ?""",
                (now, customer_id)
            )
            conn.commit()
            logger.info("Subscription cancelled for customer %s", customer_id)
            # Send cancellation email
            row = conn.execute(
                "SELECT email, display_name FROM user WHERE stripe_customer_id = ?",
                (customer_id,)
            ).fetchone()
            if row:
                # current_period_end from the Stripe subscription object
                period_end = data.get("current_period_end")
                if period_end:
                    access_until = datetime.fromtimestamp(period_end, tz=timezone.utc).strftime("%B %d, %Y")
                else:
                    access_until = "the end of your billing period"
                send_subscription_cancelled(row[0], row[1] or "", access_until)

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        if customer_id:
            conn.execute(
                """UPDATE user SET subscription_status = 'past_due', updated_at = ?
                   WHERE stripe_customer_id = ?""",
                (now, customer_id)
            )
            conn.commit()
            logger.warning("Payment failed for customer %s", customer_id)

    return {"event_type": event_type, "processed": True}
