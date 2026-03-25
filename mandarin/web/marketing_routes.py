"""Marketing routes — affiliate tracking, referrals, discounts, subscription lifecycle."""

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta, UTC

from flask import jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..marketing_hooks import log_lifecycle_event
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)


def register_marketing_routes(app):
    """Register all marketing-related routes on the Flask app."""

    # ── Landing Page Experiment ───────────────────────────────────────────

    @app.route("/api/experiment/landing-variant")
    @api_error_handler("LandingVariant")
    def api_landing_variant():
        """Server-side A/B assignment for landing page headline.

        Uses aelu_vid cookie (set by client JS) hashed with experiment name
        for deterministic, stable variant assignment. Logs exposure.
        """
        variants = ["control", "patient_path"]

        visitor_id = request.cookies.get("aelu_vid", "")
        if not visitor_id:
            # No cookie yet — return control
            return jsonify({"variant": "control", "variant_index": 0})

        # Deterministic assignment via SHA256(experiment_name + visitor_id)
        assign_key = f"landing_headline:{visitor_id}"
        variant_index = int(hashlib.sha256(assign_key.encode()).hexdigest()[:8], 16) % len(variants)
        variant = variants[variant_index]

        # Log exposure to experiment system if available
        try:
            with db.connection() as conn:
                from .. import experiments
                # Use visitor_id hash as a pseudo user_id for anonymous visitors
                pseudo_user_id = int(hashlib.sha256(visitor_id.encode()).hexdigest()[:8], 16) % 1000000
                experiments.log_exposure(conn, "landing_headline", pseudo_user_id, context="landing_page")
        except Exception as e:
            logger.debug("Landing experiment exposure logging skipped: %s", e)

        return jsonify({
            "variant": variant,
            "variant_index": variant_index,
        })

    # ── Price Display Experiment ────────────────────────────────────────

    @app.route("/api/experiment/price-variant")
    @api_error_handler("PriceVariant")
    def api_price_variant():
        """Return active price_display_test variant for the visitor.

        Checks for a running experiment named 'price_display_test' and assigns
        the visitor to a variant using the same cookie-hash approach as the
        landing headline test.  Falls back to default pricing if no experiment
        is active.
        """
        from ..settings import PRICING

        default_price = f"${PRICING['monthly_display']}/mo"

        try:
            with db.connection() as conn:
                # Check for running price experiment
                exp = conn.execute(
                    "SELECT id, name, variants FROM experiment WHERE name = 'price_display_test' AND status = 'running'"
                ).fetchone()

                if not exp:
                    return jsonify({"price_display": default_price, "variant": "default"})

                visitor_id = request.cookies.get("aelu_vid", "")
                if not visitor_id:
                    return jsonify({"price_display": default_price, "variant": "default"})

                # Deterministic assignment
                from ..web.experiment_daemon import _MARKETING_EXPERIMENT_TEMPLATES
                template = _MARKETING_EXPERIMENT_TEMPLATES.get("price_display_test", {})

                assign_key = f"price_display_test:{visitor_id}"
                variant_index = int(hashlib.sha256(assign_key.encode()).hexdigest()[:8], 16) % 2

                if variant_index == 0:
                    price_display = template.get("variant_a_config", {}).get("price_display", default_price)
                    variant_name = template.get("variant_a_name", "control")
                else:
                    price_display = template.get("variant_b_config", {}).get("price_display", default_price)
                    variant_name = template.get("variant_b_name", "treatment")

                # Log exposure
                try:
                    from .. import experiments
                    pseudo_user_id = int(hashlib.sha256(visitor_id.encode()).hexdigest()[:8], 16) % 1000000
                    experiments.log_exposure(conn, "price_display_test", pseudo_user_id, context="landing_pricing")
                except Exception:
                    pass

                return jsonify({
                    "price_display": price_display,
                    "variant": variant_name,
                })
        except Exception as e:
            logger.debug("Price variant lookup failed: %s", e)
            return jsonify({"price_display": default_price, "variant": "default"})

    # ── Referral Tracking ─────────────────────────────────────────────────

    @app.route("/api/referral/track")
    @api_error_handler("ReferralTrack")
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

                # Record the referral visit (with optional A/B variant)
                variant = request.args.get("variant", "")
                conn.execute(
                    """INSERT INTO referral_tracking
                       (visitor_id, partner_code, landing_page, utm_source, utm_medium, utm_campaign)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        visitor_id,
                        partner_code,
                        request.args.get("page", "") + (f"|variant={variant}" if variant else ""),
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
    @api_error_handler("ReferralSignup")
    def api_referral_signup():
        """Link a referral tracking record to a new signup.

        Body: {visitor_id: str, partner_code: str}
        """
        try:
            data = request.get_json(silent=True) or {}
            visitor_id = (data.get("visitor_id") or "").strip()
            partner_code = (data.get("partner_code") or "").strip()

            if not visitor_id or not partner_code:
                return jsonify({"error": "visitor_id and partner_code are required"}), 400

            now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

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
    @api_error_handler("DiscountValidate")
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
    @api_error_handler("DiscountApply")
    def api_discount_apply():
        """Apply a discount code to the authenticated user.

        Body: {code: str}
        Returns: {applied, discount_percent, valid_months}
        """
        try:
            data = request.get_json(silent=True) or {}
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
    @api_error_handler("SubscriptionCancel")
    def api_subscription_cancel():
        """Cancel a subscription and log the reason.

        Body: {reason: str, details: str (optional)}
        Returns: {cancelled, access_until, free_tier_active}
        """
        try:
            data = request.get_json(silent=True) or {}
            reason = (data.get("reason") or "").strip()
            details = (data.get("details") or "").strip()
            user_id = str(current_user.id)

            if not reason:
                return jsonify({"error": "reason is required"}), 400

            if reason not in CANCELLATION_REASONS:
                return jsonify({"error": "Invalid cancellation reason", "valid_reasons": sorted(CANCELLATION_REASONS)}), 400

            now_utc = datetime.now(UTC)
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
    @api_error_handler("SubscriptionPause")
    def api_subscription_pause():
        """Pause a subscription for 1-3 months.

        Body: {duration_months: 1|2|3}
        Returns: {paused, resume_date, reminder_date}
        """
        try:
            data = request.get_json(silent=True) or {}
            duration_months = data.get("duration_months")
            user_id = str(current_user.id)

            if duration_months not in (1, 2, 3):
                return jsonify({"error": "duration_months must be 1, 2, or 3"}), 400

            now_utc = datetime.now(UTC)
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
    @api_error_handler("ReferralLink")
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
    @api_error_handler("ReferralStats")
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

    # ── Account Referral (Flutter compat) ─────────────────────────────

    @app.route("/api/account/referral")
    @login_required
    @api_error_handler("AccountReferral")
    def api_account_referral():
        """Combined referral link + stats for Flutter app."""
        try:
            with db.connection() as conn:
                profile = db.get_profile(conn)
                seed = "mandarin-ref-" + str(profile.get("created_at", "")) + "-" + str(profile.get("total_sessions", 0))
                ref_code = hashlib.sha256(seed.encode()).hexdigest()[:10]
                base_url = request.host_url.rstrip("/")
                link = base_url + "/?ref=" + ref_code

                try:
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM referral_tracking WHERE partner_code = ? AND signed_up = 1",
                        (ref_code,)
                    ).fetchone()
                    count = row["cnt"] if row else 0
                except sqlite3.OperationalError:
                    count = 0

                return jsonify({"link": link, "count": count})
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("account referral error: %s", e)
            return jsonify({"error": "Could not get referral info"}), 500

    # ── NPS Interview Opt-In ──────────────────────────────────────────

    @app.route("/api/nps/interview-opt-in", methods=["POST"])
    @login_required
    @api_error_handler("NPSInterviewOptIn")
    def api_nps_interview_opt_in():
        """Record that a promoter (NPS 9-10) volunteered for an interview."""
        try:
            data = request.get_json(silent=True) or {}
            user_id = str(current_user.id)
            score = data.get("score", 10)

            with db.connection() as conn:
                log_lifecycle_event(
                    "interview_volunteered",
                    user_id=user_id,
                    conn=conn,
                    score=score,
                )

            return jsonify({"recorded": True})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("nps interview opt-in error: %s", e)
            return jsonify({"error": "Interview opt-in failed"}), 500

    # ── Feedback / NPS ────────────────────────────────────────────────

    @app.route("/api/feedback", methods=["POST"])
    @api_error_handler("Feedback")
    def api_feedback():
        """Accept user feedback (NPS, bug report, feature request).

        Body: {rating: 1-10, comment: string, type: "nps"|"bug"|"feature"}
        Stores in user_feedback table (auto-created if missing).
        """
        try:
            data = request.get_json(silent=True) or {}
            rating = data.get("rating")
            comment = (data.get("comment") or "").strip()
            feedback_type = (data.get("type") or "nps").strip()

            if rating is None or not isinstance(rating, (int, float)) or rating < 1 or rating > 10:
                return jsonify({"error": "rating must be between 1 and 10"}), 400

            if feedback_type not in ("nps", "bug", "feature"):
                return jsonify({"error": "type must be nps, bug, or feature"}), 400

            rating = int(rating)
            now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

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
    @api_error_handler("SubscriptionResume")
    def api_subscription_resume():
        """Resume a paused subscription.

        Returns: {resumed, next_billing_date}
        """
        try:
            user_id = str(current_user.id)

            now_utc = datetime.now(UTC)
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

    # ── NPS Survey ─────────────────────────────────────────────────────

    @app.route("/api/nps/check")
    @login_required
    @api_error_handler("NPSCheck")
    def api_nps_check():
        """Check if the current user should see the NPS survey.

        Eligible: 28-45 days after signup, not already prompted (via lifecycle_event).
        Returns: {show: bool, days_since_signup: int}
        """
        try:
            user_id = str(current_user.id)
            with db.connection() as conn:
                # Days since signup
                signup_row = conn.execute(
                    "SELECT created_at FROM user WHERE id = ?",
                    (int(user_id),)
                ).fetchone()
                if not signup_row or not signup_row["created_at"]:
                    return jsonify({"show": False})

                days_row = conn.execute(
                    "SELECT CAST(julianday('now') - julianday(?) AS INTEGER) as days",
                    (signup_row["created_at"],)
                ).fetchone()
                days_since = (days_row["days"] or 0) if days_row else 0

                if days_since < 28 or days_since > 45:
                    return jsonify({"show": False, "days_since_signup": days_since})

                # Check if already prompted
                already = conn.execute(
                    """SELECT id FROM lifecycle_event
                       WHERE event_type = 'nps_prompted'
                         AND user_id = ?
                       LIMIT 1""",
                    (user_id,)
                ).fetchone()
                if already:
                    return jsonify({"show": False, "days_since_signup": days_since})

                return jsonify({"show": True, "days_since_signup": days_since})
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("nps check error: %s", e)
            return jsonify({"show": False})

    @app.route("/api/nps/prompted", methods=["POST"])
    @login_required
    @api_error_handler("NPSPrompted")
    def api_nps_prompted():
        """Record that the NPS survey was shown and optionally the score.

        Body: {score: 0-10 (optional), comment: str (optional)}
        """
        try:
            data = request.get_json(silent=True) or {}
            user_id = str(current_user.id)
            score = data.get("score")
            comment = (data.get("comment") or "").strip()

            with db.connection() as conn:
                log_lifecycle_event(
                    "nps_prompted",
                    user_id=user_id,
                    score=score,
                    comment=comment,
                    conn=conn,
                )

                # Also store in user_feedback if score provided
                if score is not None and isinstance(score, (int, float)):
                    score = max(0, min(10, int(score)))
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_feedback (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            rating INTEGER NOT NULL,
                            comment TEXT DEFAULT '',
                            feedback_type TEXT NOT NULL DEFAULT 'nps',
                            created_at TEXT NOT NULL DEFAULT (datetime('now'))
                        )
                    """)
                    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        "INSERT INTO user_feedback (rating, comment, feedback_type, created_at) VALUES (?, ?, 'nps', ?)",
                        (score, comment, now_utc)
                    )
                    conn.commit()

            return jsonify({"recorded": True})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("nps prompted error: %s", e)
            return jsonify({"error": "NPS recording failed"}), 500
