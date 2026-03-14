"""Payment routes — Stripe checkout, billing portal, webhooks, subscription status."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..payment import create_checkout_session, create_billing_portal_session, handle_webhook, create_classroom_checkout
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

payment_bp = Blueprint("payment", __name__)


@payment_bp.route("/api/checkout", methods=["POST"])
@login_required
@api_error_handler("Checkout")
def checkout():
    """Create a Stripe Checkout session and return the URL."""
    try:
        data = request.get_json(silent=True) or {}
        plan = data.get("plan", "monthly")
        if plan not in ("monthly", "annual"):
            return jsonify({"error": "Invalid plan. Use 'monthly' or 'annual'."}), 400
        url = create_checkout_session(current_user.id, current_user.email, plan=plan)
        return jsonify({"url": url})
    except (sqlite3.Error, KeyError, ValueError, OSError) as e:
        logger.error("Checkout error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create checkout session"}), 500


@payment_bp.route("/api/checkout/classroom", methods=["POST"])
@login_required
@api_error_handler("Classroom checkout")
def classroom_checkout():
    """Create a Stripe Checkout session for classroom pricing."""
    try:
        data = request.get_json(silent=True) or {}
        student_count = data.get("student_count", 5)
        billing = data.get("billing", "per_student")
        if billing not in ("per_student", "semester"):
            return jsonify({"error": "Invalid billing type"}), 400
        if not isinstance(student_count, int) or student_count < 1:
            return jsonify({"error": "Invalid student count"}), 400
        url = create_classroom_checkout(
            current_user.id, current_user.email, student_count, billing
        )
        return jsonify({"url": url})
    except (sqlite3.Error, KeyError, ValueError, OSError) as e:
        logger.error("Classroom checkout error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create classroom checkout session"}), 500


@payment_bp.route("/api/billing-portal", methods=["POST"])
@login_required
@api_error_handler("Billing portal")
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
    except (sqlite3.Error, KeyError, ValueError, OSError) as e:
        logger.error("Billing portal error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not create billing portal session"}), 500


@payment_bp.route("/api/webhook/stripe", methods=["POST"])
@api_error_handler("Webhook")
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
    except (sqlite3.Error, KeyError, TypeError, OSError) as e:
        logger.error("Webhook processing error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Webhook processing failed"}), 500


@payment_bp.route("/api/subscription/status")
@login_required
@api_error_handler("Subscription status")
def subscription_status():
    """Return current user's subscription status."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                """SELECT subscription_tier, subscription_status, subscription_expires_at,
                          stripe_customer_id, is_admin FROM user WHERE id = ?""",
                (current_user.id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "User not found"}), 404
            # Admins always have full access regardless of subscription state
            tier = row["subscription_tier"] or "free"
            if row["is_admin"]:
                tier = "full"
            return jsonify({
                "tier": tier,
                "status": row["subscription_status"] or "active",
                "expires_at": row["subscription_expires_at"],
                "has_stripe": bool(row["stripe_customer_id"]),
            })
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Subscription status error (%s): %s", type(e).__name__, e)
        return jsonify({"error": "Could not fetch subscription status"}), 500
