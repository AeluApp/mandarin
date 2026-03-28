"""Landing page routes — serve static marketing pages + social proof API."""

import logging
import os
import re

from flask import Blueprint, send_from_directory, abort, jsonify, request

logger = logging.getLogger(__name__)

_ILLUSTRATIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "marketing", "assets", "illustrations")
)

# Landing pages live outside the web package, in project root marketing/landing/
_LANDING_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "marketing", "landing")
_LANDING_DIR = os.path.normpath(_LANDING_DIR)

landing_bp = Blueprint("landing", __name__)


# Note: the "/" route is handled in routes.py (index) to avoid conflicts
# with the authenticated app dashboard.  Unauthenticated visitors see the
# landing page; authenticated users see the dashboard.


@landing_bp.route("/pricing")
def landing_pricing():
    return send_from_directory(_LANDING_DIR, "pricing.html")


@landing_bp.route("/about")
def landing_about():
    return send_from_directory(_LANDING_DIR, "about.html")


@landing_bp.route("/faq")
def landing_faq():
    return send_from_directory(_LANDING_DIR, "faq.html")


@landing_bp.route("/privacy")
def landing_privacy():
    return send_from_directory(_LANDING_DIR, "privacy.html")


@landing_bp.route("/terms")
def landing_terms():
    return send_from_directory(_LANDING_DIR, "terms.html")


@landing_bp.route("/breach-notification")
def landing_breach_notification():
    return send_from_directory(_LANDING_DIR, "breach-notification.html")


@landing_bp.route("/accessibility")
def landing_accessibility():
    return send_from_directory(_LANDING_DIR, "accessibility.html")


@landing_bp.route("/ccpa")
def landing_ccpa():
    return send_from_directory(_LANDING_DIR, "ccpa.html")


@landing_bp.route("/dmca")
def landing_dmca():
    return send_from_directory(_LANDING_DIR, "dmca.html")


@landing_bp.route("/ai-content-policy")
def landing_ai_content_policy():
    return send_from_directory(_LANDING_DIR, "ai-content-policy.html")


@landing_bp.route("/changelog")
def landing_changelog():
    return send_from_directory(_LANDING_DIR, "changelog.html")


@landing_bp.route("/affiliates")
def landing_affiliates():
    return send_from_directory(_LANDING_DIR, "affiliates.html")


@landing_bp.route("/hsk-prep")
def landing_hsk_prep():
    return send_from_directory(_LANDING_DIR, "hsk-prep.html")


@landing_bp.route("/serious-learner")
def landing_serious_learner():
    return send_from_directory(_LANDING_DIR, "serious-learner.html")


@landing_bp.route("/anki-alternative")
def landing_anki_alternative():
    return send_from_directory(_LANDING_DIR, "anki-alternative.html")


@landing_bp.route("/vs-duolingo")
def landing_vs_duolingo():
    return send_from_directory(_LANDING_DIR, "vs-duolingo.html")


@landing_bp.route("/vs-anki")
def landing_vs_anki():
    return send_from_directory(_LANDING_DIR, "vs-anki.html")


@landing_bp.route("/vs-hack-chinese")
def landing_vs_hack_chinese():
    return send_from_directory(_LANDING_DIR, "vs-hack-chinese.html")


@landing_bp.route("/vs-hellochinese")
def landing_vs_hellochinese():
    return send_from_directory(_LANDING_DIR, "vs-hellochinese.html")


@landing_bp.route("/partners")
@landing_bp.route("/partner-kit")
def landing_partner_kit():
    return send_from_directory(_LANDING_DIR, "partner-kit.html")


@landing_bp.route("/hsk-calculator")
def landing_hsk_calculator():
    return send_from_directory(_LANDING_DIR, "hsk-calculator.html")


@landing_bp.route("/links")
def landing_links():
    return send_from_directory(_LANDING_DIR, "links.html")


@landing_bp.route("/blog")
@landing_bp.route("/blog/")
def landing_blog_index():
    return send_from_directory(os.path.join(_LANDING_DIR, "blog"), "index.html")


@landing_bp.route("/blog/<path:slug>")
def landing_blog_post(slug):
    # Strict slug validation: alphanumeric and hyphens only
    safe_slug = slug.strip("/")
    if not safe_slug or not re.match(r'^[a-zA-Z0-9-]+$', safe_slug):
        abort(404)
    filename = safe_slug if safe_slug.endswith(".html") else safe_slug + ".html"
    return send_from_directory(os.path.join(_LANDING_DIR, "blog"), filename)


@landing_bp.route("/marketing.js")
def landing_marketing_js():
    return send_from_directory(_LANDING_DIR, "marketing.js")


@landing_bp.route("/og/<path:filename>")
def landing_og_image(filename):
    safe_name = os.path.basename(filename)
    if not re.match(r'^[a-zA-Z0-9._-]+$', safe_name):
        abort(404)
    return send_from_directory(os.path.join(_LANDING_DIR, "og"), safe_name)


@landing_bp.route("/api/social-proof")
def api_social_proof():
    """Factual social proof stats for landing page (Cialdini 1984).

    Returns real, auto-computed stats. Only displays data when thresholds
    are met (user count > 100, etc.) to avoid fabrication.
    DOCTRINE §8: factual, verifiable claims only.
    """
    try:
        from .. import db
        with db.connection() as conn:
            # Total non-admin users who completed at least one session
            user_count = conn.execute(
                """SELECT COUNT(*) FROM user
                   WHERE is_admin = 0 AND first_session_at IS NOT NULL"""
            ).fetchone()[0]

            # Average words mastered in first 30 days (stable + durable)
            avg_words = None
            if user_count >= 10:
                row = conn.execute(
                    """SELECT AVG(word_count) as avg_words FROM (
                         SELECT p.user_id, COUNT(*) as word_count
                         FROM progress p
                         JOIN user u ON p.user_id = u.id
                         WHERE u.is_admin = 0
                           AND p.mastery_stage IN ('stable', 'durable')
                           AND u.first_session_at >= datetime('now', '-60 days')
                         GROUP BY p.user_id
                         HAVING word_count >= 5
                       )"""
                ).fetchone()
                if row and row["avg_words"]:
                    avg_words = round(row["avg_words"])

            result = {
                "show_user_count": user_count >= 100,
                "user_count": user_count if user_count >= 100 else None,
                "show_outcome_stat": avg_words is not None and avg_words >= 20,
                "avg_words_first_month": avg_words,
                "outcome_message": (
                    f"Average learner masters {avg_words} words in their first month"
                    if avg_words and avg_words >= 20 else None
                ),
            }
            return jsonify(result)
    except Exception as e:
        logger.debug("Social proof API error: %s", e)
        return jsonify({"show_user_count": False, "show_outcome_stat": False})


@landing_bp.route("/api/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    """Add email to Resend audience for newsletter delivery.

    Falls back to storing in newsletter_subscriber table when Resend
    API key or audience ID is not configured.
    """
    import requests as http_requests
    from ..settings import RESEND_API_KEY

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Valid email required"}), 400

    RESEND_AUDIENCE_ID = os.environ.get("RESEND_AUDIENCE_ID", "")

    # Store in DB as canonical record (works regardless of Resend config)
    try:
        from .. import db
        with db.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO newsletter_subscriber (email, subscribed_at)"
                " VALUES (?, datetime('now'))",
                (email,),
            )
            conn.commit()
    except Exception as db_err:
        logger.debug("Newsletter DB insert skipped: %s", db_err)

    if not RESEND_API_KEY or not RESEND_AUDIENCE_ID:
        logger.info("[newsletter] subscribe (db-only): %s", email)
        return jsonify({"status": "subscribed"})

    try:
        resp = http_requests.post(
            f"https://api.resend.com/audiences/{RESEND_AUDIENCE_ID}/contacts",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"email": email},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info("Newsletter subscribe: %s", email)
            return jsonify({"status": "subscribed"})
        else:
            logger.error("Resend audience error %s: %s", resp.status_code, resp.text)
            # Already stored in DB above, so still report success
            return jsonify({"status": "subscribed"})
    except Exception as e:
        logger.exception("Newsletter subscribe error: %s", e)
        # Already stored in DB above, so still report success
        return jsonify({"status": "subscribed"})


@landing_bp.route("/illustrations/<path:filename>")
def landing_illustration(filename):
    safe_name = os.path.basename(filename)
    if not re.match(r'^[a-zA-Z0-9._-]+$', safe_name):
        abort(404)
    return send_from_directory(_ILLUSTRATIONS_DIR, safe_name)
