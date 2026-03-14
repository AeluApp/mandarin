"""Landing page routes — serve static marketing pages."""

import os
import re

from flask import Blueprint, send_from_directory, abort

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


@landing_bp.route("/illustrations/<path:filename>")
def landing_illustration(filename):
    safe_name = os.path.basename(filename)
    if not re.match(r'^[a-zA-Z0-9._-]+$', safe_name):
        abort(404)
    return send_from_directory(_ILLUSTRATIONS_DIR, safe_name)
