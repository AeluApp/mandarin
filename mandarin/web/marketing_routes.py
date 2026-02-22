"""Marketing routes — affiliate tracking, referrals, discounts, subscription lifecycle."""

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

from flask import jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..marketing_hooks import log_lifecycle_event

logger = logging.getLogger(__name__)


def register_marketing_routes(app):
    """Register all marketing-related routes on the Flask app."""

    # ── Referral Tracking ─────────────────────────────────────────────────

    @app.route("/api/referral/track")
    def api_referral_track():
        """Record a referral visit and return partner info for the landing page.

        Query params:
            ref: partner code (required)
            page: landing page URL
            utm_source, utm_medium, utm_campaign: UTM parameters
        """
        partner_code = request.args.get("ref", "").strip()
        if not partner_code:
            return jsonify({"error": "Missing ref parameter"}), 400

        try:
            with db.connection() as conn:
                # Look up the partner
                partner = conn.execute(
                    "SELECT partner_code, partner_name, tier, status FROM affiliate_partner WHERE partner_code = ?",
                    (partner_code,)
                ).fetchone()

                if not partner:
                    return jsonify({"error": "Unknown partner code"}), 404

                if partner["status"] != "active":
                    return jsonify({"error": "Partner is inactive"}), 403

                # Generate a visitor ID for this referral visit
                visitor_id = str(uuid.uuid4())

                # Record the referral visit
                conn.execute(
                    """INSERT INTO referral_tracking
                       (visitor_id, partner_code, landing_page, utm_source, utm_medium, utm_campaign)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        visitor_id,
                        partner_code,
                        request.args.get("page", ""),
                        request.args.get("utm_source", ""),
                        request.args.get("utm_medium", ""),
                        request.args.get("utm_campaign", ""),
                    )
                )
                conn.commit()

                return jsonify({
                    "visitor_id": visitor_id,
                    "partner_code": partner["partner_code"],
                    "partner_name": partner["partner_name"],
                    "tier": partner["tier"],
                })
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("referral track error: %s", e)
            return jsonify({"error": "Referral tracking failed"}), 500

    @app.route("/api/referral/signup", methods=["POST"])
    def api_referral_signup():
        """Link a referral tracking record to a new signup.

        Body: {visitor_id: str, partner_code: str}
        """
        try:
            data = request.get_json(force=True)
            visitor_id = (data.get("visitor_id") or "").strip()
            partner_code = (data.get("partner_code") or "").strip()

            if not visitor_id or not partner_code:
                return jsonify({"error": "visitor_id and partner_code are required"}), 400

            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            with db.connection() as conn:
                # Verify the referral record exists
                referral = conn.execute(
                    "SELECT id, signed_up FROM referral_tracking WHERE visitor_id = ? AND partner_code = ?",
                    (visitor_id, partner_code)
                ).fetchone()

                if not referral:
                    return jsonify({"error": "Referral record not found"}), 404

                if referral["signed_up"]:
                    return jsonify({"error": "Referral already linked to a signup"}), 409

                # Mark the referral as signed up
                conn.execute(
                    "UPDATE referral_tracking SET signed_up = 1, signup_at = ? WHERE id = ?",
                    (now_utc, referral["id"])
                )
                conn.commit()

                # Log lifecycle event
                log_lifecycle_event(
                    "signup",
                    user_id=visitor_id,
                    partner_code=partner_code,
                    referral_id=referral["id"],
                    conn=conn,
                )

                return jsonify({
                    "linked": True,
                    "referral_id": referral["id"],
                    "partner_code": partner_code,
                })
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("referral signup error: %s", e)
            return jsonify({"error": "Referral signup linking failed"}), 500

    # ── Discount Code Validation & Application ────────────────────────────

    @app.route("/api/discount/validate")
    def api_discount_validate():
        """Validate a discount code.

        Query params:
            code: discount code (required)

        Returns: {valid, discount_percent, valid_months, partner_name}
        """
        code = (request.args.get("code") or "").strip().upper()
        if not code:
            return jsonify({"error": "Missing code parameter"}), 400

        try:
            with db.connection() as conn:
                row = conn.execute(
                    """SELECT dc.code, dc.discount_percent, dc.valid_months,
                              dc.max_uses, dc.current_uses, dc.active,
                              ap.partner_name
                       FROM discount_code dc
                       LEFT JOIN affiliate_partner ap ON dc.partner_code = ap.partner_code
                       WHERE dc.code = ?""",
                    (code,)
                ).fetchone()

                if not row:
                    return jsonify({"valid": False, "reason": "Code not found"}), 200

                if not row["active"]:
                    return jsonify({"valid": False, "reason": "Code is no longer active"}), 200

                max_uses = row["max_uses"]
                if max_uses is not None and row["current_uses"] >= max_uses:
                    return jsonify({"valid": False, "reason": "Code has reached its usage limit"}), 200

                return jsonify({
                    "valid": True,
                    "discount_percent": row["discount_percent"],
                    "valid_months": row["valid_months"],
                    "partner_name": row["partner_name"] or "",
                })
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("discount validate error: %s", e)
            return jsonify({"error": "Discount validation failed"}), 500

    @app.route("/api/discount/apply", methods=["POST"])
    @login_required
    def api_discount_apply():
        """Apply a discount code to the authenticated user.

        Body: {code: str}
        Returns: {applied, discount_percent, valid_months}
        """
        try:
            data = request.get_json(force=True)
            code = (data.get("code") or "").strip().upper()
            user_id = str(current_user.id)

            if not code:
                return jsonify({"error": "code is required"}), 400

            with db.connection() as conn:
                row = conn.execute(
                    """SELECT id, discount_percent, valid_months, max_uses, current_uses, active, partner_code
                       FROM discount_code WHERE code = ?""",
                    (code,)
                ).fetchone()

                if not row:
                    return jsonify({"applied": False, "reason": "Code not found"}), 200

                if not row["active"]:
                    return jsonify({"applied": False, "reason": "Code is no longer active"}), 200

                max_uses = row["max_uses"]
                if max_uses is not None and row["current_uses"] >= max_uses:
                    return jsonify({"applied": False, "reason": "Code has reached its usage limit"}), 200

                # Increment usage count
                conn.execute(
                    "UPDATE discount_code SET current_uses = current_uses + 1 WHERE id = ?",
                    (row["id"],)
                )
                conn.commit()

                # Log lifecycle event
                log_lifecycle_event(
                    "discount_applied",
                    user_id=user_id,
                    code=code,
                    discount_percent=row["discount_percent"],
                    valid_months=row["valid_months"],
                    partner_code=row["partner_code"] or "",
                    conn=conn,
                )

                return jsonify({
                    "applied": True,
                    "discount_percent": row["discount_percent"],
                    "valid_months": row["valid_months"],
                })
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("discount apply error: %s", e)
            return jsonify({"error": "Discount application failed"}), 500

    # ── Subscription Lifecycle ────────────────────────────────────────────

    CANCELLATION_REASONS = {
        "too_expensive", "not_using", "found_better",
        "content_gap", "taking_break", "achieved_goal", "other",
    }

    @app.route("/api/subscription/cancel", methods=["POST"])
    @login_required
    def api_subscription_cancel():
        """Cancel a subscription and log the reason.

        Body: {reason: str, details: str (optional)}
        Returns: {cancelled, access_until, free_tier_active}
        """
        try:
            data = request.get_json(force=True)
            reason = (data.get("reason") or "").strip()
            details = (data.get("details") or "").strip()
            user_id = str(current_user.id)

            if not reason:
                return jsonify({"error": "reason is required"}), 400

            if reason not in CANCELLATION_REASONS:
                return jsonify({"error": "Invalid cancellation reason", "valid_reasons": sorted(CANCELLATION_REASONS)}), 400

            now_utc = datetime.now(timezone.utc)
            # Access until end of current billing period (approximate: 30 days from now)
            access_until = (now_utc + timedelta(days=30)).strftime("%Y-%m-%d")

            with db.connection() as conn:
                # Log the cancellation initiation
                log_lifecycle_event(
                    "cancellation_initiated",
                    user_id=user_id,
                    reason=reason,
                    details=details,
                    conn=conn,
                )

                # Log the reason separately for analytics
                log_lifecycle_event(
                    "cancellation_reason",
                    user_id=user_id,
                    reason=reason,
                    details=details,
                    conn=conn,
                )

                # Log the completion
                log_lifecycle_event(
                    "cancellation_completed",
                    user_id=user_id,
                    access_until=access_until,
                    conn=conn,
                )

            return jsonify({
                "cancelled": True,
                "access_until": access_until,
                "free_tier_active": True,
            })
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("subscription cancel error: %s", e)
            return jsonify({"error": "Cancellation failed"}), 500

    @app.route("/api/subscription/pause", methods=["POST"])
    @login_required
    def api_subscription_pause():
        """Pause a subscription for 1-3 months.

        Body: {duration_months: 1|2|3}
        Returns: {paused, resume_date, reminder_date}
        """
        try:
            data = request.get_json(force=True)
            duration_months = data.get("duration_months")
            user_id = str(current_user.id)

            if duration_months not in (1, 2, 3):
                return jsonify({"error": "duration_months must be 1, 2, or 3"}), 400

            now_utc = datetime.now(timezone.utc)
            resume_date = (now_utc + timedelta(days=30 * duration_months)).strftime("%Y-%m-%d")
            reminder_date = (now_utc + timedelta(days=30 * duration_months - 7)).strftime("%Y-%m-%d")

            with db.connection() as conn:
                log_lifecycle_event(
                    "pause_started",
                    user_id=user_id,
                    duration_months=duration_months,
                    resume_date=resume_date,
                    reminder_date=reminder_date,
                    conn=conn,
                )

            return jsonify({
                "paused": True,
                "resume_date": resume_date,
                "reminder_date": reminder_date,
            })
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("subscription pause error: %s", e)
            return jsonify({"error": "Pause failed"}), 500

    # ── In-App Referral ────────────────────────────────────────────────

    @app.route("/api/referral/link")
    def api_referral_link():
        """Generate/return a referral link for the current user.

        Uses a deterministic hash of the learner profile so the link is stable.
        Returns: {link, ref_code}
        """
        try:
            with db.connection() as conn:
                profile = db.get_profile(conn)
                # Deterministic referral code from profile creation date + total sessions
                seed = "mandarin-ref-" + str(profile.get("created_at", "")) + "-" + str(profile.get("total_sessions", 0))
                ref_code = hashlib.sha256(seed.encode()).hexdigest()[:10]
                # Build the link relative to current host
                base_url = request.host_url.rstrip("/")
                link = base_url + "/?ref=" + ref_code
                return jsonify({"link": link, "ref_code": ref_code})
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("referral link error: %s", e)
            return jsonify({"error": "Could not generate referral link"}), 500

    @app.route("/api/referral/stats")
    def api_referral_stats():
        """Return referral count for this user.

        Returns: {referral_count, ref_code}
        """
        try:
            with db.connection() as conn:
                profile = db.get_profile(conn)
                seed = "mandarin-ref-" + str(profile.get("created_at", "")) + "-" + str(profile.get("total_sessions", 0))
                ref_code = hashlib.sha256(seed.encode()).hexdigest()[:10]

                # Count signups through this ref code
                try:
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM referral_tracking WHERE partner_code = ? AND signed_up = 1",
                        (ref_code,)
                    ).fetchone()
                    count = row["cnt"] if row else 0
                except sqlite3.OperationalError:
                    # Table may not exist yet
                    count = 0

                return jsonify({"referral_count": count, "ref_code": ref_code})
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("referral stats error: %s", e)
            return jsonify({"error": "Could not retrieve referral stats"}), 500

    # ── Feedback / NPS ────────────────────────────────────────────────

    @app.route("/api/feedback", methods=["POST"])
    def api_feedback():
        """Accept user feedback (NPS, bug report, feature request).

        Body: {rating: 1-10, comment: string, type: "nps"|"bug"|"feature"}
        Stores in user_feedback table (auto-created if missing).
        """
        try:
            data = request.get_json(force=True)
            rating = data.get("rating")
            comment = (data.get("comment") or "").strip()
            feedback_type = (data.get("type") or "nps").strip()

            if rating is None or not isinstance(rating, (int, float)) or rating < 1 or rating > 10:
                return jsonify({"error": "rating must be between 1 and 10"}), 400

            if feedback_type not in ("nps", "bug", "feature"):
                return jsonify({"error": "type must be nps, bug, or feature"}), 400

            rating = int(rating)
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            with db.connection() as conn:
                # Ensure user_feedback table exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rating INTEGER NOT NULL,
                        comment TEXT DEFAULT '',
                        feedback_type TEXT NOT NULL DEFAULT 'nps',
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                conn.execute(
                    "INSERT INTO user_feedback (rating, comment, feedback_type, created_at) VALUES (?, ?, ?, ?)",
                    (rating, comment, feedback_type, now_utc)
                )
                conn.commit()

            return jsonify({"submitted": True})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("feedback submit error: %s", e)
            return jsonify({"error": "Feedback submission failed"}), 500

    @app.route("/api/subscription/resume", methods=["POST"])
    @login_required
    def api_subscription_resume():
        """Resume a paused subscription.

        Returns: {resumed, next_billing_date}
        """
        try:
            user_id = str(current_user.id)

            now_utc = datetime.now(timezone.utc)
            next_billing_date = (now_utc + timedelta(days=30)).strftime("%Y-%m-%d")

            with db.connection() as conn:
                log_lifecycle_event(
                    "pause_ended",
                    user_id=user_id,
                    conn=conn,
                )

                log_lifecycle_event(
                    "reactivation",
                    user_id=user_id,
                    next_billing_date=next_billing_date,
                    conn=conn,
                )

            return jsonify({
                "resumed": True,
                "next_billing_date": next_billing_date,
            })
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("subscription resume error: %s", e)
            return jsonify({"error": "Resume failed"}), 500
