"""Stripe payment integration — checkout, billing portal, webhooks."""

import logging
import sqlite3
from datetime import datetime, timezone, UTC
from typing import Optional

import stripe

from .email import send_subscription_confirmed, send_subscription_cancelled
from .settings import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_TAX_ENABLED, BASE_URL, PRICING

logger = logging.getLogger(__name__)

stripe.api_key = STRIPE_SECRET_KEY

# ── Commission structure ──
# Standard partner rate (pilot — escalate to 0.30 after 6-month review if metrics hit)
COMMISSION_RATE_STANDARD = 0.25
# All partner tiers use the same rate
COMMISSION_RATE_UPGRADE = 0.25
# Maximum months a partner earns commission per referred user
COMMISSION_CAP_MONTHS = 24
# Optional partner discount (opt-in, not standard)
PARTNER_DISCOUNT_PERCENT = 15  # 15% off first 3 months
PARTNER_DISCOUNT_MONTHS = 3

# ── Student upgrade (classroom students upgrading to premium) ──
TEACHER_STUDENT_UPGRADE_RATE = 0.25  # Teacher earns 25% of student upgrades


def calculate_commission(conn: sqlite3.Connection, partner_code: str,
                         user_id: int, payment_amount: float) -> dict | None:
    """Calculate affiliate commission for a payment, respecting the 24-month cap.

    Returns a dict with commission details, or None if the commission window
    has expired or the user was not referred by a partner.
    """
    if not partner_code:
        return None

    # Check if this user's commission window has expired
    row = conn.execute(
        """SELECT MIN(payment_date) as first_payment
           FROM affiliate_commission
           WHERE partner_code = ? AND user_id = ?""",
        (partner_code, user_id)
    ).fetchone()

    now = datetime.now(UTC)

    if row and row[0]:
        first_payment = datetime.fromisoformat(row[0]).replace(tzinfo=UTC)
        months_elapsed = (now.year - first_payment.year) * 12 + (now.month - first_payment.month)
        if months_elapsed >= COMMISSION_CAP_MONTHS:
            logger.info("Commission cap reached for partner %s / user %s (%d months)",
                        partner_code, user_id, months_elapsed)
            return None

    # Determine commission rate from partner tier
    partner_row = conn.execute(
        """SELECT tier, commission_rate FROM affiliate_partner
           WHERE partner_code = ?""",
        (partner_code,)
    ).fetchone()

    if not partner_row:
        logger.warning("Partner code %s not found in affiliate_partner", partner_code)
        return None

    # Use partner's stored rate, or default based on tier
    if partner_row["tier"] in ("upgrade", "teacher"):
        rate = COMMISSION_RATE_UPGRADE
    else:
        rate = partner_row["commission_rate"] or COMMISSION_RATE_STANDARD

    commission = round(payment_amount * rate, 2)

    # Find referral_id for this user+partner (needed for existing schema FK)
    ref_row = conn.execute(
        """SELECT id FROM referral_tracking
           WHERE partner_code = ? AND signed_up = 1
           ORDER BY signup_at DESC LIMIT 1""",
        (partner_code,)
    ).fetchone()
    referral_id = ref_row["id"] if ref_row else 0

    return {
        "partner_code": partner_code,
        "referral_id": referral_id,
        "user_id": user_id,
        "amount": commission,
        "commission_rate": rate,
        "payment_amount": payment_amount,
        "payment_date": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def record_commission(conn: sqlite3.Connection, commission: dict) -> None:
    """Record a commission in the affiliate_commission table."""
    first_payment_date = conn.execute(
        """SELECT MIN(payment_date) FROM affiliate_commission
           WHERE partner_code = ? AND user_id = ?""",
        (commission["partner_code"], commission["user_id"])
    ).fetchone()[0] or commission["payment_date"]

    conn.execute(
        """INSERT INTO affiliate_commission
           (partner_code, referral_id, user_id, amount, commission_rate,
            payment_date, first_payment_date, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (commission["partner_code"], commission["referral_id"],
         commission["user_id"], commission["amount"],
         commission["commission_rate"], commission["payment_date"],
         first_payment_date)
    )
    conn.commit()
    logger.info("Commission recorded: $%.2f for partner %s (user %s, rate %.0f%%)",
                commission["amount"], commission["partner_code"],
                commission["user_id"], commission["commission_rate"] * 100)


def _calculate_teacher_student_commission(conn: sqlite3.Connection,
                                          teacher_user_id: int,
                                          student_user_id: int,
                                          payment_amount: float) -> dict | None:
    """Calculate teacher commission from a student's premium upgrade payment.

    Teachers earn 25% of student upgrade payments for up to 24 months.
    Uses the affiliate_commission table with a synthetic partner_code
    of 'teacher_{teacher_user_id}'.
    """
    partner_code = f"teacher_{teacher_user_id}"
    now = datetime.now(UTC)

    # Check commission window
    row = conn.execute(
        """SELECT MIN(payment_date) as first_payment
           FROM affiliate_commission
           WHERE partner_code = ? AND user_id = ?""",
        (partner_code, student_user_id)
    ).fetchone()

    if row and row[0]:
        first_payment = datetime.fromisoformat(row[0]).replace(tzinfo=UTC)
        months_elapsed = (now.year - first_payment.year) * 12 + (now.month - first_payment.month)
        if months_elapsed >= COMMISSION_CAP_MONTHS:
            logger.info("Teacher commission cap reached: teacher %s / student %s (%d months)",
                        teacher_user_id, student_user_id, months_elapsed)
            return None

    commission = round(payment_amount * TEACHER_STUDENT_UPGRADE_RATE, 2)

    return {
        "partner_code": partner_code,
        "referral_id": 0,
        "user_id": student_user_id,
        "amount": commission,
        "commission_rate": TEACHER_STUDENT_UPGRADE_RATE,
        "payment_amount": payment_amount,
        "payment_date": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def create_checkout_session(user_id: int, email: str, plan: str = "monthly",
                            price_variant: str = None) -> str:
    """Create a Stripe Checkout session. Returns the checkout URL.

    Args:
        plan: "monthly" or "annual".
        price_variant: experiment variant name (e.g. "lower_9.99") to use
            variant-specific pricing. Falls back to default PRICING if None.
    """
    from .settings import get_variant_pricing
    pricing = get_variant_pricing(price_variant)

    if plan == "annual":
        unit_amount = pricing["annual_cents"]
        interval = "year"
        product_name = "Aelu — Full Access (Annual)"
    else:
        unit_amount = pricing["monthly_cents"]
        interval = "month"
        product_name = "Aelu — Full Access"

    checkout_kwargs = dict(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": product_name},
                "unit_amount": unit_amount,
                "recurring": {"interval": interval},
            },
            "quantity": 1,
        }],
        mode="subscription",
        success_url=BASE_URL + "/?payment=success",
        cancel_url=BASE_URL + "/?payment=cancelled",
        metadata={
            "user_id": str(user_id),
            "price_variant": price_variant or "default",
        },
    )
    if STRIPE_TAX_ENABLED:
        checkout_kwargs["automatic_tax"] = {"enabled": True}
    session = stripe.checkout.Session.create(**checkout_kwargs)
    return session.url


def create_classroom_checkout(teacher_user_id: int, email: str,
                              student_count: int, billing: str = "per_student") -> str:
    """Create a Stripe Checkout session for classroom pricing.

    Args:
        billing: "per_student" ($8/student/mo, min 5) or "semester" ($200 flat, up to 30).
    """
    tax_kwargs = {"automatic_tax": {"enabled": True}} if STRIPE_TAX_ENABLED else {}
    if billing == "semester":
        session = stripe.checkout.Session.create(
            customer_email=email,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Aelu — Classroom (Semester)"},
                    "unit_amount": PRICING["classroom_semester_cents"],
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=BASE_URL + "/?payment=classroom_success",
            cancel_url=BASE_URL + "/?payment=cancelled",
            metadata={
                "user_id": str(teacher_user_id),
                "checkout_type": "classroom",
                "billing": "semester",
                "student_count": str(min(student_count, PRICING["classroom_max_students_semester"])),
            },
            **tax_kwargs,
        )
    else:
        # Per-student pricing, minimum students enforced
        qty = max(PRICING["classroom_min_students"], student_count)
        session = stripe.checkout.Session.create(
            customer_email=email,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Aelu — Classroom (Per Student)"},
                    "unit_amount": PRICING["classroom_per_student_cents"],
                    "recurring": {"interval": "month"},
                },
                "quantity": qty,
            }],
            mode="subscription",
            success_url=BASE_URL + "/?payment=classroom_success",
            cancel_url=BASE_URL + "/?payment=cancelled",
            metadata={
                "user_id": str(teacher_user_id),
                "checkout_type": "classroom",
                "billing": "per_student",
                "student_count": str(qty),
            },
            **tax_kwargs,
        )
    return session.url


def create_student_upgrade_checkout(student_user_id: int, email: str,
                                    teacher_user_id: int) -> str:
    """Create a Stripe Checkout session for a classroom student upgrading to Premium.

    The student pays $4.99/month. The teacher who referred them via classroom
    earns 25% commission for up to 24 months.
    """
    upgrade_kwargs = dict(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Aelu — Premium (Student Upgrade)"},
                "unit_amount": PRICING["student_upgrade_cents"],
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }],
        mode="subscription",
        success_url=BASE_URL + "/?payment=premium_success",
        cancel_url=BASE_URL + "/?payment=cancelled",
        metadata={
            "user_id": str(student_user_id),
            "checkout_type": "student_upgrade",
            "teacher_user_id": str(teacher_user_id),
        },
    )
    if STRIPE_TAX_ENABLED:
        upgrade_kwargs["automatic_tax"] = {"enabled": True}
    session = stripe.checkout.Session.create(**upgrade_kwargs)
    return session.url


# ── Stripe Connect: Partner Onboarding & Payouts ──


def create_partner_connect_account(conn: sqlite3.Connection, partner_code: str,
                                    email: str) -> str:
    """Create a Stripe Connect Express account for a partner and return the onboarding URL.

    The partner clicks the URL, enters their bank details on Stripe's hosted form,
    and Stripe handles identity verification and compliance. No sensitive data touches our servers.
    """
    account = stripe.Account.create(
        type="express",
        email=email,
        metadata={"partner_code": partner_code},
        capabilities={
            "transfers": {"requested": True},
        },
    )

    # Store the Connect account ID
    conn.execute(
        "UPDATE affiliate_partner SET stripe_connect_id = ?, updated_at = datetime('now') WHERE partner_code = ?",
        (account.id, partner_code),
    )
    conn.commit()
    logger.info("Connect account %s created for partner %s", account.id, partner_code)

    # Generate onboarding link
    link = stripe.AccountLink.create(
        account=account.id,
        refresh_url=BASE_URL + "/partners/onboarding?refresh=1",
        return_url=BASE_URL + "/partners/onboarding?complete=1",
        type="account_onboarding",
    )
    return link.url


def get_partner_connect_status(conn: sqlite3.Connection, partner_code: str) -> dict:
    """Check if a partner's Connect account is fully set up for payouts."""
    row = conn.execute(
        "SELECT stripe_connect_id FROM affiliate_partner WHERE partner_code = ?",
        (partner_code,),
    ).fetchone()

    if not row or not row["stripe_connect_id"]:
        return {"status": "not_started", "payouts_enabled": False}

    try:
        account = stripe.Account.retrieve(row["stripe_connect_id"])
        return {
            "status": "complete" if account.details_submitted else "incomplete",
            "payouts_enabled": account.payouts_enabled,
            "charges_enabled": account.charges_enabled,
            "connect_id": account.id,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def pay_out_partner(conn: sqlite3.Connection, partner_code: str,
                    amount_cents: int, description: str = "Aelu affiliate commission") -> dict:
    """Transfer pending commission to a partner's Connect account.

    Call this from the admin payout flow or a scheduled job.
    """
    row = conn.execute(
        "SELECT stripe_connect_id FROM affiliate_partner WHERE partner_code = ?",
        (partner_code,),
    ).fetchone()

    if not row or not row["stripe_connect_id"]:
        return {"error": "Partner has no Connect account"}

    try:
        transfer = stripe.Transfer.create(
            amount=amount_cents,
            currency="usd",
            destination=row["stripe_connect_id"],
            description=description,
            metadata={"partner_code": partner_code},
        )

        # Mark commissions as paid
        conn.execute(
            """UPDATE affiliate_commission SET status = 'paid', paid_out_at = datetime('now')
               WHERE partner_code = ? AND status = 'pending'""",
            (partner_code,),
        )
        conn.commit()

        logger.info("Paid $%.2f to partner %s (transfer %s)",
                     amount_cents / 100, partner_code, transfer.id)
        return {"status": "paid", "transfer_id": transfer.id, "amount": amount_cents / 100}
    except Exception as e:
        logger.error("Payout failed for partner %s: %s", partner_code, e)
        return {"error": str(e)}


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
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured — cannot verify webhook")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid webhook signature")

    event_type = event["type"]
    event_id = event.get("id", "")
    data = event["data"]["object"]
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Idempotency: skip already-processed events
    if event_id:
        try:
            already = conn.execute(
                "SELECT 1 FROM webhook_event WHERE event_id = ?", (event_id,)
            ).fetchone()
            if already:
                logger.info("Webhook event %s already processed, skipping", event_id)
                return {"event_type": event_type, "status": "duplicate", "event_id": event_id}
            conn.execute(
                "INSERT INTO webhook_event (event_id, event_type, processed_at) VALUES (?, ?, ?)",
                (event_id, event_type, now),
            )
        except sqlite3.OperationalError:
            # Table may not exist yet — proceed without idempotency
            logger.warning("webhook_event table not found, skipping idempotency check")

    if event_type == "checkout.session.completed":
        raw_user_id = data.get("metadata", {}).get("user_id")
        customer_id = data.get("customer")
        checkout_type = data.get("metadata", {}).get("checkout_type", "")
        # Validate user_id is a valid integer
        try:
            user_id = str(int(raw_user_id)) if raw_user_id else None
        except (ValueError, TypeError):
            logger.error("Invalid user_id in webhook metadata: %r", raw_user_id)
            return {"event_type": event_type, "status": "error", "reason": "invalid user_id"}

        if checkout_type == "classroom" and user_id:
            # Classroom checkout: set teacher tier
            sub_id = data.get("subscription") or ""
            conn.execute(
                """UPDATE user SET stripe_customer_id = ?, subscription_tier = 'teacher',
                   subscription_status = 'active', role = 'teacher', updated_at = ? WHERE id = ?""",
                (customer_id, now, int(user_id))
            )
            # Store stripe_subscription_id on the teacher's most recent classroom
            if sub_id:
                conn.execute(
                    """UPDATE classroom SET stripe_subscription_id = ?, updated_at = ?
                       WHERE teacher_user_id = ? AND stripe_subscription_id IS NULL
                       ORDER BY created_at DESC LIMIT 1""",
                    (sub_id, now, int(user_id))
                )
            conn.commit()
            logger.info("Classroom checkout completed: user %s upgraded to teacher", user_id)
            row = conn.execute(
                "SELECT email, display_name FROM user WHERE id = ?",
                (int(user_id),)
            ).fetchone()
            if row:
                send_subscription_confirmed(row[0], row[1] or "")

        elif checkout_type == "student_upgrade" and user_id:
            # Student upgrading to premium tier
            teacher_id = data.get("metadata", {}).get("teacher_user_id")
            conn.execute(
                """UPDATE user SET stripe_customer_id = ?, subscription_tier = 'premium',
                   subscription_status = 'active', updated_at = ?
                   WHERE id = ?""",
                (customer_id, now, int(user_id))
            )
            # Store teacher reference if column exists (added in later migration)
            if teacher_id:
                try:
                    conn.execute(
                        "UPDATE user SET referred_by_teacher = ? WHERE id = ?",
                        (teacher_id, int(user_id))
                    )
                except sqlite3.OperationalError:
                    logger.debug("referred_by_teacher column not yet available")
            conn.commit()
            logger.info("Student upgrade completed: user %s upgraded to premium (teacher %s)",
                        user_id, teacher_id)
            row = conn.execute(
                "SELECT email, display_name FROM user WHERE id = ?",
                (int(user_id),)
            ).fetchone()
            if row:
                send_subscription_confirmed(row[0], row[1] or "")

        elif user_id and customer_id:
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

            # ── Affiliate commission handling ──
            # Check if this user was referred by a partner
            user_row = conn.execute(
                """SELECT id, referred_by_partner, subscription_tier FROM user
                   WHERE stripe_customer_id = ?""",
                (customer_id,)
            ).fetchone()

            if user_row and user_row["referred_by_partner"]:
                # Get the invoice amount (in cents from Stripe)
                amount_paid = data.get("amount_paid", 0) / 100.0  # Convert cents to dollars
                if amount_paid > 0:
                    commission = calculate_commission(
                        conn,
                        partner_code=user_row["referred_by_partner"],
                        user_id=user_row["id"],
                        payment_amount=amount_paid,
                    )
                    if commission:
                        record_commission(conn, commission)

            # ── Teacher commission from student premium upgrades ──
            if user_row and user_row["subscription_tier"] == "premium":
                try:
                    teacher_row = conn.execute(
                        "SELECT referred_by_teacher FROM user WHERE id = ?",
                        (user_row["id"],)
                    ).fetchone()
                    teacher_id = teacher_row["referred_by_teacher"] if teacher_row else None
                except (sqlite3.OperationalError, KeyError):
                    teacher_id = None

                if teacher_id:
                    amount_paid = data.get("amount_paid", 0) / 100.0
                    if amount_paid > 0:
                        teacher_commission = _calculate_teacher_student_commission(
                            conn,
                            teacher_user_id=int(teacher_id),
                            student_user_id=user_row["id"],
                            payment_amount=amount_paid,
                        )
                        if teacher_commission:
                            record_commission(conn, teacher_commission)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            # Check if this is a classroom subscription
            teacher_row = conn.execute(
                "SELECT id, subscription_tier FROM user WHERE stripe_customer_id = ?",
                (customer_id,)
            ).fetchone()

            conn.execute(
                """UPDATE user SET subscription_tier = 'free', subscription_status = 'cancelled',
                   updated_at = ? WHERE stripe_customer_id = ?""",
                (now, customer_id)
            )

            # If teacher, revert classroom students to free tier
            if teacher_row and teacher_row["subscription_tier"] == "teacher":
                classrooms = conn.execute(
                    "SELECT id FROM classroom WHERE teacher_user_id = ?",
                    (teacher_row["id"],)
                ).fetchall()
                for cls in classrooms:
                    conn.execute(
                        """UPDATE user SET subscription_tier = 'free', updated_at = ?
                           WHERE id IN (
                               SELECT user_id FROM classroom_student
                               WHERE classroom_id = ? AND status = 'active'
                           )""",
                        (now, cls["id"])
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
                    access_until = datetime.fromtimestamp(period_end, tz=UTC).strftime("%B %d, %Y")
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
