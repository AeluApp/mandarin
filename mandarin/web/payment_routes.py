"""Payment routes — Stripe checkout, billing portal, webhooks, subscription status."""

import logging

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..payment import create_checkout_session, create_billing_portal_session, handle_webhook

logger = logging.getLogger(__name__)

payment_bp = Blueprint("payment", __name__)


@payment_bp.route("/api/checkout", methods=["POST"])
@login_required
def checkout():
    """Create a Stripe Checkout session and return the URL."""
    try:
        url = create_checkout_session(current_user.id, current_user.email)
        return jsonify({"url": url})
    except Exception as e:
        logger.error("Checkout error: %s", e)
        return jsonify({"error": "Could not create checkout session"}), 500


@payment_bp.route("/api/billing-portal", methods=["POST"])
@login_required
def billing_portal():
    """Create a Stripe Billing Portal session and return the URL."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT stripe_customer_id FROM user WHERE id = ?",
                (current_user.id,)
            ).fetchone()
            if not row or not row["stripe_customer_id"]:
                return jsonify({"error": "No active subscription found"}), 400
            url = create_billing_portal_session(row["stripe_customer_id"])
            return jsonify({"url": url})
    except Exception as e:
        logger.error("Billing portal error: %s", e)
        return jsonify({"error": "Could not create billing portal session"}), 500


@payment_bp.route("/api/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Stripe webhook endpoint — verifies signature, processes events."""
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        with db.connection() as conn:
            handle_webhook(payload, sig_header, conn)
            return jsonify({"received": True})
    except ValueError as e:
        logger.warning("Webhook signature failed: %s", e)
        return jsonify({"error": "Invalid request"}), 400
    except Exception as e:
        logger.error("Webhook processing error: %s", e)
        return jsonify({"error": "Webhook processing failed"}), 500


@payment_bp.route("/api/subscription/status")
@login_required
def subscription_status():
    """Return current user's subscription status."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                """SELECT subscription_tier, subscription_status, subscription_expires_at,
                          stripe_customer_id FROM user WHERE id = ?""",
                (current_user.id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "User not found"}), 404
            return jsonify({
                "tier": row["subscription_tier"] or "free",
                "status": row["subscription_status"] or "active",
                "expires_at": row["subscription_expires_at"],
                "has_stripe": bool(row["stripe_customer_id"]),
            })
    except Exception as e:
        logger.error("Subscription status error: %s", e)
        return jsonify({"error": "Could not fetch subscription status"}), 500
