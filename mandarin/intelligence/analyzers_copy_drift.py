"""Copy / content truth-drift analyzers — detect when marketing pages,
legal text, email templates, or about-page claims diverge from the
actual codebase, configuration, or data.

Each checker reads the source-of-truth (settings.py, drills/dispatch.py,
requirements.txt, etc.) and compares it against claims found in HTML files.
Mismatches produce findings with dimension="copy_drift".

Auto-fix helpers live at the bottom of this module.
"""

import json
import logging
import os
import re
from typing import Optional

from ._base import _finding

logger = logging.getLogger(__name__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Paths to monitor ────────────────────────────────────────────────
_MARKETING_DIR = os.path.join(_PROJECT_ROOT, "marketing", "landing")
_EMAIL_DIR = os.path.join(_PROJECT_ROOT, "marketing", "email-templates")

_MARKETING_FILES = {
    "index": os.path.join(_MARKETING_DIR, "index.html"),
    "about": os.path.join(_MARKETING_DIR, "about.html"),
    "pricing": os.path.join(_MARKETING_DIR, "pricing.html"),
    "privacy": os.path.join(_MARKETING_DIR, "privacy.html"),
    "terms": os.path.join(_MARKETING_DIR, "terms.html"),
    "affiliates": os.path.join(_MARKETING_DIR, "affiliates.html"),
    "partner_kit": os.path.join(_MARKETING_DIR, "partner-kit.html"),
}


# ── Helpers ──────────────────────────────────────────────────────────

def _read_file(rel_path: str) -> str:
    """Read a file relative to the project root. Returns '' on error."""
    try:
        with open(os.path.join(_PROJECT_ROOT, rel_path), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _read_abs(path: str) -> str:
    """Read a file by absolute path. Returns '' on error."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Rough strip of HTML tags for plain-text comparison."""
    return re.sub(r"<[^>]+>", " ", html)


def _extract_dollar_amounts(text: str) -> list[str]:
    """Return list of numeric strings for dollar amounts in text.

    Handles: $14.99, $149, $0.50, $8/student, $200/semester, etc.
    Returns the numeric part only (e.g. "14.99", "149").
    """
    return re.findall(r'\$(\d+(?:\.\d+)?)', text)


def _find_line_number(content: str, substring: str) -> int:
    """Find the approximate line number of a substring in content."""
    idx = content.find(substring)
    if idx == -1:
        return 0
    return content[:idx].count("\n") + 1


def _get_pricing() -> dict:
    """Import PRICING from settings without circular imports."""
    try:
        from ..settings import PRICING
        return PRICING
    except Exception:
        return {}


def _get_drill_count() -> int:
    """Count registered drill types from dispatch.py."""
    try:
        from ..drills.dispatch import DRILL_REGISTRY
        return len(DRILL_REGISTRY)
    except Exception:
        return 0


def _get_email_templates() -> dict[str, str]:
    """Read all email templates. Returns {name: content}."""
    templates = {}
    if not os.path.isdir(_EMAIL_DIR):
        return templates
    for fname in os.listdir(_EMAIL_DIR):
        if fname.endswith(".html"):
            path = os.path.join(_EMAIL_DIR, fname)
            content = _read_abs(path)
            if content:
                templates[fname] = content
    return templates


# ══════════════════════════════════════════════════════════════════════
# ANALYZERS
# ══════════════════════════════════════════════════════════════════════

def _check_pricing_drift(conn) -> list[dict]:
    """Compare dollar amounts in marketing/pricing pages against PRICING in settings.py."""
    findings = []
    pricing = _get_pricing()
    if not pricing:
        return findings

    # Build set of canonical dollar amounts (display strings)
    canonical = {
        pricing.get("monthly_display", "14.99"),
        pricing.get("annual_display", "149"),
        pricing.get("annual_monthly_equiv", "12.42"),
        pricing.get("annual_savings", "30"),
        str(pricing.get("classroom_per_student_cents", 800) // 100),  # "$8"
        str(pricing.get("classroom_semester_cents", 20000) // 100),   # "$200"
        "{:.2f}".format(pricing.get("student_upgrade_cents", 499) / 100),  # "$4.99"
    }

    # Also accept integer forms (e.g. "149" and "149.00")
    canonical_ints = set()
    for c in canonical:
        canonical_ints.add(c)
        try:
            if "." not in c:
                canonical_ints.add(f"{c}.00")
            elif c.endswith(".00"):
                canonical_ints.add(c.replace(".00", ""))
        except Exception:
            pass

    # Check pricing-sensitive pages
    price_pages = ["pricing", "terms", "index", "affiliates", "partner_kit"]
    for page_key in price_pages:
        path = _MARKETING_FILES.get(page_key)
        if not path:
            continue
        content = _read_abs(path)
        if not content:
            continue

        amounts = _extract_dollar_amounts(content)
        for amount in amounts:
            # Skip well-known non-pricing amounts (comparison table, etc.)
            if amount in ("0", "0.00", "0.50"):
                continue
            # Skip amounts that appear in comparison tables (other product prices)
            # by checking if this amount is in our canonical set
            if amount not in canonical_ints and amount not in canonical:
                # This dollar amount is not in our pricing — could be a competitor
                # price in a comparison table, or could be stale. Check context.
                # Look for amounts that are close to our prices but wrong
                monthly = pricing.get("monthly_display", "14.99")
                annual = pricing.get("annual_display", "149")
                try:
                    val = float(amount)
                    monthly_val = float(monthly)
                    annual_val = float(annual)
                    # Flag if the amount is suspiciously close to our actual price
                    # (within 30%) but not matching — likely a stale price
                    if (abs(val - monthly_val) / monthly_val < 0.3 and val != monthly_val):
                        line = _find_line_number(content, f"${amount}")
                        findings.append(_finding(
                            "copy_drift", "high",
                            f"Pricing mismatch in {os.path.basename(path)}: ${amount} vs ${monthly}/mo",
                            f"Page claims ${amount} but settings.py PRICING['monthly_display'] = "
                            f"'{monthly}'. This could mislead customers or cause billing disputes.",
                            f"Update the dollar amount in {os.path.basename(path)} to match "
                            f"PRICING['monthly_display'] = ${monthly}.",
                            f"In {os.path.basename(path)} around line {line}, replace '${amount}' "
                            f"with '${monthly}'. Verify all other price references on the page.",
                            "Revenue accuracy — price mismatches erode trust",
                            [path],
                        ))
                    elif (abs(val - annual_val) / annual_val < 0.3 and val != annual_val):
                        line = _find_line_number(content, f"${amount}")
                        findings.append(_finding(
                            "copy_drift", "high",
                            f"Annual price mismatch in {os.path.basename(path)}: ${amount} vs ${annual}/yr",
                            f"Page claims ${amount} but settings.py PRICING['annual_display'] = "
                            f"'{annual}'. Annual pricing is inconsistent.",
                            f"Update the dollar amount in {os.path.basename(path)} to match "
                            f"PRICING['annual_display'] = ${annual}.",
                            f"In {os.path.basename(path)} around line {line}, replace '${amount}' "
                            f"with '${annual}'. Verify all annual price references.",
                            "Revenue accuracy — price mismatches erode trust",
                            [path],
                        ))
                except (ValueError, ZeroDivisionError):
                    pass

    return findings


def _check_feature_claims(conn) -> list[dict]:
    """Verify feature claims in marketing copy against actual code."""
    findings = []
    drill_count = _get_drill_count()

    # ── Drill type count claims ──
    for page_key, path in _MARKETING_FILES.items():
        content = _read_abs(path)
        if not content:
            continue
        plain = _strip_html(content)

        # Find claims like "44 drill types" or "27 drill types"
        drill_claims = re.findall(r'(\d+)\s+drill\s+type', plain, re.IGNORECASE)
        for claimed in drill_claims:
            claimed_int = int(claimed)
            if claimed_int != drill_count:
                line = _find_line_number(content, f"{claimed} drill type")
                findings.append(_finding(
                    "copy_drift", "medium",
                    f"Drill type count mismatch in {os.path.basename(path)}: "
                    f"claims {claimed_int}, actual {drill_count}",
                    f"Marketing copy says '{claimed} drill types' but DRILL_REGISTRY "
                    f"contains {drill_count} entries. {'The count is too high — features may have been removed.' if claimed_int > drill_count else 'The count is too low — new drill types have been added.'}",
                    f"Update '{claimed} drill types' to '{drill_count} drill types' in "
                    f"{os.path.basename(path)}.",
                    f"In {os.path.basename(path)} around line {line}, replace "
                    f"'{claimed} drill type' with '{drill_count} drill type'. "
                    f"Search the entire file for other occurrences of '{claimed}'.",
                    "Feature accuracy — wrong numbers undermine credibility",
                    [path],
                ))

    # ── HSK level coverage claims ──
    # Check for "HSK 1-9" claims and verify data exists
    for page_key, path in _MARKETING_FILES.items():
        content = _read_abs(path)
        if not content:
            continue
        plain = _strip_html(content)

        hsk_claims = re.findall(r'HSK\s+(\d+)\s*[-–]\s*(\d+)', plain)
        for low, high in hsk_claims:
            _low_int, high_int = int(low), int(high)
            # Verify HSK levels exist in the database
            if conn is not None:
                try:
                    max_level = conn.execute(
                        "SELECT MAX(hsk_level) FROM content_item WHERE hsk_level IS NOT NULL"
                    ).fetchone()
                    if max_level and max_level[0] is not None:
                        actual_max = max_level[0]
                        if high_int > actual_max:
                            line = _find_line_number(content, f"HSK {low}")
                            findings.append(_finding(
                                "copy_drift", "medium",
                                f"HSK range overclaim in {os.path.basename(path)}: "
                                f"claims HSK {low}-{high}, data only covers up to HSK {actual_max}",
                                f"Page says 'HSK {low}-{high}' but the content_item table "
                                f"only has data up to HSK level {actual_max}. Learners expecting "
                                f"HSK {actual_max + 1}+ content will be disappointed.",
                                f"Either add HSK {actual_max + 1}-{high} content or update "
                                f"the claim to 'HSK {low}-{actual_max}'.",
                                f"In {os.path.basename(path)} around line {line}, verify "
                                f"HSK level claim matches actual content coverage. "
                                f"Current max HSK level in data: {actual_max}.",
                                "Feature accuracy — overclaiming content coverage",
                                [path],
                            ))
                except Exception:
                    pass

    # ── "works offline" claims ──
    for page_key, path in _MARKETING_FILES.items():
        content = _read_abs(path)
        if not content:
            continue
        plain = _strip_html(content).lower()

        if "works offline" in plain or "offline mode" in plain or "without internet" in plain:
            # Check if service worker or offline support actually exists
            sw_path = os.path.join(_PROJECT_ROOT, "mandarin", "web", "static", "sw.js")
            manifest_path = os.path.join(_PROJECT_ROOT, "mandarin", "web", "static", "manifest.json")
            has_sw = os.path.isfile(sw_path)
            _has_manifest = os.path.isfile(manifest_path)
            if not has_sw:
                line = _find_line_number(content.lower(), "offline")
                findings.append(_finding(
                    "copy_drift", "high",
                    f"'Works offline' claim in {os.path.basename(path)} but no service worker found",
                    "Marketing copy claims offline support but no service worker "
                    "(sw.js) exists. This is a false promise to users.",
                    "Either implement offline support or remove the claim.",
                    f"In {os.path.basename(path)} around line {line}, remove or qualify "
                    "the offline claim. If offline is planned, change to 'offline support coming soon'.",
                    "Feature accuracy — false offline claim",
                    [path],
                ))

    return findings


def _check_privacy_claims(conn) -> list[dict]:
    """Verify privacy.html claims match actual integrations."""
    findings = []
    privacy_content = _read_abs(_MARKETING_FILES.get("privacy", ""))
    if not privacy_content:
        return findings

    plain = _strip_html(privacy_content).lower()

    # ── Third-party services claimed in privacy page ──
    claimed_services = set()
    service_names = [
        "stripe", "plausible", "sentry", "formspree", "resend",
        "firebase", "google analytics", "mixpanel", "amplitude",
        "hotjar", "fullstory", "segment", "intercom",
    ]
    for svc in service_names:
        if svc in plain:
            claimed_services.add(svc)

    # ── Check for services in code that are NOT mentioned in privacy ──
    # GA4 configured in settings
    try:
        from ..settings import GA4_MEASUREMENT_ID, PLAUSIBLE_DOMAIN
        if GA4_MEASUREMENT_ID and "google analytics" not in plain and "ga4" not in plain:
            findings.append(_finding(
                "copy_drift", "high",
                "Google Analytics (GA4) configured but not disclosed in privacy policy",
                f"settings.py has GA4_MEASUREMENT_ID = '{GA4_MEASUREMENT_ID[:8]}...' but the "
                "privacy page does not mention Google Analytics. This may violate GDPR/CCPA "
                "disclosure requirements.",
                "Add Google Analytics to the third-party services section of privacy.html, "
                "or remove GA4_MEASUREMENT_ID from settings.py if not in use.",
                "Add a Google Analytics entry to the 'Third Parties' section of privacy.html "
                "similar to the existing Plausible entry. Include a link to Google's privacy policy.",
                "Legal compliance — undisclosed analytics tracking",
                [_MARKETING_FILES["privacy"], "mandarin/settings.py"],
            ))
    except Exception:
        pass

    # ── Check for cookie claims ──
    if "do not use" in plain and "cookie" in plain:
        # Claim about no cookies — but we use session cookies
        # This is OK if they say "no third-party cookies"
        # Check if the claim is overly broad
        no_cookie_match = re.search(r'(do not use|does not use|no)\s+cookie', plain)
        if no_cookie_match and "first-party" not in plain and "third-party" not in plain:
            findings.append(_finding(
                "copy_drift", "medium",
                "Overly broad 'no cookies' claim in privacy policy",
                "Privacy policy appears to claim no cookies are used, but the app "
                "uses session cookies and potentially referral tracking cookies. "
                "The claim should specify 'no third-party tracking cookies' if that is accurate.",
                "Qualify the cookie claim to specify which types of cookies are and are not used.",
                "In privacy.html, update the cookie section to clearly distinguish "
                "between first-party (session, preferences) and third-party cookies.",
                "Legal accuracy — cookie disclosure",
                [_MARKETING_FILES["privacy"]],
            ))

    # ── Check requirements.txt for services not in privacy ──
    req_content = _read_file("requirements.txt")
    if req_content:
        # Check for analytics/tracking packages
        tracking_packages = {
            "google-analytics": "Google Analytics",
            "mixpanel": "Mixpanel",
            "amplitude": "Amplitude",
            "segment": "Segment",
            "hotjar": "Hotjar",
            "intercom": "Intercom",
        }
        for pkg, name in tracking_packages.items():
            if pkg in req_content.lower() and name.lower() not in plain:
                findings.append(_finding(
                    "copy_drift", "medium",
                    f"{name} in requirements.txt but not disclosed in privacy policy",
                    f"requirements.txt includes {pkg} but the privacy policy does not "
                    f"mention {name}. If this service processes user data, it must be disclosed.",
                    f"Add {name} to the third-party services section of privacy.html, "
                    f"or remove the package if not in use.",
                    f"Add a {name} entry to the 'Third Parties' section of privacy.html.",
                    "Legal compliance — undisclosed third-party service",
                    [_MARKETING_FILES["privacy"], "requirements.txt"],
                ))

    return findings


def _check_terms_accuracy(conn) -> list[dict]:
    """Check terms.html for pricing and policy accuracy."""
    findings = []
    terms_content = _read_abs(_MARKETING_FILES.get("terms", ""))
    if not terms_content:
        return findings

    pricing = _get_pricing()
    if not pricing:
        return findings

    plain = _strip_html(terms_content)

    # ── Pricing in terms ──
    dollar_amounts = _extract_dollar_amounts(plain)
    monthly = pricing.get("monthly_display", "14.99")
    annual = pricing.get("annual_display", "149")
    classroom_per_student = str(pricing.get("classroom_per_student_cents", 800) // 100)
    classroom_semester = str(pricing.get("classroom_semester_cents", 20000) // 100)

    known_prices = {monthly, annual, classroom_per_student, classroom_semester, "0"}

    for amount in dollar_amounts:
        if amount in known_prices:
            continue
        # Check if it's close to a known price (possible stale value)
        try:
            val = float(amount)
            for kp in known_prices:
                kp_val = float(kp)
                if kp_val > 0 and abs(val - kp_val) / kp_val < 0.3 and val != kp_val:
                    line = _find_line_number(terms_content, f"${amount}")
                    findings.append(_finding(
                        "copy_drift", "high",
                        f"Stale price in terms.html: ${amount} (expected ${kp})",
                        f"Terms of service mentions ${amount} but the closest canonical "
                        f"price is ${kp}. Legal documents must reflect actual pricing.",
                        f"Update ${amount} to ${kp} in terms.html.",
                        f"In terms.html around line {line}, replace '${amount}' with '${kp}'.",
                        "Legal accuracy — terms must match actual pricing",
                        [_MARKETING_FILES["terms"]],
                    ))
                    break
        except (ValueError, ZeroDivisionError):
            pass

    # ── Drill type counts in terms ──
    drill_count = _get_drill_count()
    drill_claims = re.findall(r'(\d+)\s+drill\s+type', plain, re.IGNORECASE)
    for claimed in drill_claims:
        claimed_int = int(claimed)
        if claimed_int != drill_count:
            line = _find_line_number(terms_content, f"{claimed} drill type")
            findings.append(_finding(
                "copy_drift", "medium",
                f"Drill count in terms.html: claims {claimed_int}, actual {drill_count}",
                f"Terms of service says '{claimed} drill types' but code has {drill_count}.",
                f"Update '{claimed} drill types' to '{drill_count} drill types' in terms.html.",
                f"In terms.html around line {line}, replace '{claimed}' with '{drill_count}'.",
                "Legal accuracy — terms must match actual features",
                [_MARKETING_FILES["terms"]],
            ))

    return findings


def _check_email_accuracy(conn) -> list[dict]:
    """Verify email templates for pricing, feature claims, and asset references."""
    findings = []
    templates = _get_email_templates()
    if not templates:
        return findings

    pricing = _get_pricing()
    drill_count = _get_drill_count()
    monthly = pricing.get("monthly_display", "14.99") if pricing else "14.99"

    for fname, content in templates.items():
        plain = _strip_html(content)
        rel_path = f"marketing/email-templates/{fname}"

        # ── Drill type count claims ──
        drill_claims = re.findall(r'(\d+)\s+drill\s+type', plain, re.IGNORECASE)
        for claimed in drill_claims:
            claimed_int = int(claimed)
            if claimed_int != drill_count:
                line = _find_line_number(content, f"{claimed} drill type")
                findings.append(_finding(
                    "copy_drift", "medium",
                    f"Drill count in {fname}: claims {claimed_int}, actual {drill_count}",
                    f"Email template says '{claimed} drill types' but DRILL_REGISTRY "
                    f"has {drill_count}. Subscribers receive inaccurate information.",
                    f"Update '{claimed} drill types' to '{drill_count} drill types' in {fname}.",
                    f"In {rel_path} around line {line}, replace "
                    f"'{claimed} drill type' with '{drill_count} drill type'.",
                    "Brand consistency — emails must match reality",
                    [rel_path],
                ))

        # ── Pricing references ──
        if pricing:
            dollar_amounts = _extract_dollar_amounts(plain)
            for amount in dollar_amounts:
                if amount in ("0", "0.00"):
                    continue
                try:
                    val = float(amount)
                    monthly_val = float(monthly)
                    if abs(val - monthly_val) / monthly_val < 0.3 and val != monthly_val:
                        line = _find_line_number(content, f"${amount}")
                        findings.append(_finding(
                            "copy_drift", "medium",
                            f"Stale price in {fname}: ${amount} (expected ${monthly})",
                            f"Email template has ${amount} but settings.py price is ${monthly}/mo.",
                            f"Update ${amount} to ${monthly} in {fname}.",
                            f"In {rel_path} around line {line}, replace '${amount}' with '${monthly}'.",
                            "Revenue accuracy — email prices must match billing",
                            [rel_path],
                        ))
                except (ValueError, ZeroDivisionError):
                    pass

        # ── Brand name consistency ──
        # Check for old/wrong brand names
        _brand_names = re.findall(r'\b(aelu|Aelu|AELU)\b', content)
        # Check for "Mandarin" used as the product name (old name)
        if re.search(r'(?<!\w)Mandarin(?:\s+app|\s+learning\s+app)', content):
            line = _find_line_number(content, "Mandarin")
            findings.append(_finding(
                "copy_drift", "low",
                f"Old brand name 'Mandarin' used in {fname}",
                "Email template uses 'Mandarin' as a product name instead of 'Aelu'.",
                f"Replace 'Mandarin app' or 'Mandarin learning app' with 'Aelu' in {fname}.",
                f"In {rel_path} around line {line}, replace references to 'Mandarin' "
                "as a product name with 'Aelu'.",
                "Brand consistency",
                [rel_path],
            ))

        # ── Broken image/asset references ──
        img_refs = re.findall(r'(?:src|href)=["\']([^"\']+\.(?:png|jpg|jpeg|gif|svg|webp))', content)
        for img_ref in img_refs:
            if img_ref.startswith("http"):
                continue  # External URL — can't verify from code
            # Resolve relative to static directory
            if img_ref.startswith("/static/"):
                abs_path = os.path.join(_PROJECT_ROOT, "mandarin", "web", img_ref.lstrip("/"))
            elif img_ref.startswith("/"):
                abs_path = os.path.join(_PROJECT_ROOT, "mandarin", "web", img_ref.lstrip("/"))
            else:
                abs_path = os.path.join(_PROJECT_ROOT, img_ref)

            if not os.path.isfile(abs_path):
                line = _find_line_number(content, img_ref)
                findings.append(_finding(
                    "copy_drift", "medium",
                    f"Broken image reference in {fname}: {img_ref}",
                    f"Email template references {img_ref} but the file does not exist "
                    f"at {abs_path}. This will show a broken image in sent emails.",
                    f"Either add the missing image or update the reference in {fname}.",
                    f"In {rel_path} around line {line}, fix the broken image reference "
                    f"'{img_ref}'. Either create the image or update the src attribute.",
                    "Email quality — broken images reduce open/click rates",
                    [rel_path],
                ))

    return findings


def _check_about_page_numbers(conn) -> list[dict]:
    """Verify numerical claims on the about page."""
    findings = []
    about_content = _read_abs(_MARKETING_FILES.get("about", ""))
    if not about_content:
        return findings

    plain = _strip_html(about_content)
    drill_count = _get_drill_count()

    # ── Drill type count ──
    drill_claims = re.findall(r'(\d+)\s+drill\s+type', plain, re.IGNORECASE)
    for claimed in drill_claims:
        claimed_int = int(claimed)
        if claimed_int != drill_count:
            line = _find_line_number(about_content, f"{claimed} drill type")
            findings.append(_finding(
                "copy_drift", "medium",
                f"About page drill count: claims {claimed_int}, actual {drill_count}",
                f"About page says '{claimed} drill types' but DRILL_REGISTRY has {drill_count}.",
                f"Update '{claimed} drill types' to '{drill_count} drill types' in about.html.",
                f"In about.html around line {line}, replace '{claimed}' with '{drill_count}'. "
                f"Also search for 'Forty-four', 'forty-four', 'Forty four' etc.",
                "Credibility — about page numbers must match reality",
                [_MARKETING_FILES["about"]],
            ))

    # Also check for spelled-out numbers like "Forty-four"
    spelled_claims = re.findall(
        r'((?:Twenty|Thirty|Forty|Fifty|Sixty|Seventy|Eighty|Ninety)'
        r'(?:\s*-?\s*(?:one|two|three|four|five|six|seven|eight|nine))?)\s+drill\s+type',
        plain, re.IGNORECASE,
    )
    # Simple spelled-number-to-int conversion for common values
    _SPELLED_TENS = {
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    _SPELLED_ONES = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9,
    }
    for spelled in spelled_claims:
        parts = re.split(r'[\s-]+', spelled.lower())
        val = _SPELLED_TENS.get(parts[0], 0)
        if len(parts) > 1:
            val += _SPELLED_ONES.get(parts[1], 0)
        if val > 0 and val != drill_count:
            line = _find_line_number(about_content, spelled)
            findings.append(_finding(
                "copy_drift", "medium",
                f"About page drill count (spelled): claims {val}, actual {drill_count}",
                f"About page says '{spelled} drill types' but DRILL_REGISTRY has {drill_count}.",
                f"Update '{spelled}' to match the actual count of {drill_count}.",
                f"In about.html around line {line}, update the spelled-out drill count.",
                "Credibility — about page numbers must match reality",
                [_MARKETING_FILES["about"]],
            ))

    # ── HSK level range on about page ──
    hsk_claims = re.findall(r'HSK\s+(\d+)\s*[-–]\s*(\d+)', plain)
    if conn is not None:
        for low, high in hsk_claims:
            high_int = int(high)
            try:
                max_level = conn.execute(
                    "SELECT MAX(hsk_level) FROM content_item WHERE hsk_level IS NOT NULL"
                ).fetchone()
                if max_level and max_level[0] is not None and high_int > max_level[0]:
                    line = _find_line_number(about_content, f"HSK {low}")
                    findings.append(_finding(
                        "copy_drift", "medium",
                        f"About page HSK overclaim: HSK {low}-{high}, data covers up to HSK {max_level[0]}",
                        f"About page claims HSK coverage up to {high} but data only goes to {max_level[0]}.",
                        f"Update HSK range to reflect actual content or add missing content.",
                        f"In about.html around line {line}, verify HSK level claim.",
                        "Feature accuracy",
                        [_MARKETING_FILES["about"]],
                    ))
            except Exception:
                pass

    return findings


def _check_ollama_deep_review(conn) -> list[dict]:
    """Use Ollama/LLM to do a deep review of copy accuracy when available."""
    findings = []

    try:
        from ..ai.ollama_client import is_ollama_available, generate, is_model_capable
    except ImportError:
        return findings

    if not is_ollama_available():
        return findings

    if not is_model_capable("copy_drift_review"):
        return findings

    # Build a summary of actual app capabilities
    pricing = _get_pricing()
    drill_count = _get_drill_count()

    capabilities_summary = f"""
App: Aelu — adaptive Chinese learning platform
Drill types: {drill_count} registered in DRILL_REGISTRY
Pricing: monthly ${pricing.get('monthly_display', '?')}, annual ${pricing.get('annual_display', '?')}
Classroom: ${pricing.get('classroom_per_student_cents', 0) // 100}/student/mo, ${pricing.get('classroom_semester_cents', 0) // 100}/semester
Student upgrade: ${pricing.get('student_upgrade_cents', 0) / 100:.2f}/mo
HSK coverage: 1-9 claimed
Analytics: Plausible (privacy-focused), Sentry (error monitoring), GA4 (if configured)
Third parties: Stripe (payments), Resend (email), Firebase Cloud Messaging (push notifications), Formspree (contact form)
Tech: Flask web app, SQLite, local Ollama LLM for content generation (not user-facing AI)
""".strip()

    # Review each marketing page
    pages_to_review = ["index", "about", "pricing", "privacy", "terms"]
    for page_key in pages_to_review:
        path = _MARKETING_FILES.get(page_key)
        if not path:
            continue
        content = _read_abs(path)
        if not content:
            continue

        plain = _strip_html(content)
        # Truncate to avoid overloading context
        if len(plain) > 6000:
            plain = plain[:6000] + "\n...[truncated]"

        prompt = f"""Analyze this marketing page for accuracy issues. Compare claims against actual capabilities.

ACTUAL APP CAPABILITIES:
{capabilities_summary}

PAGE CONTENT ({os.path.basename(path)}):
{plain}

List any claims that are:
1. Factually wrong (wrong numbers, prices, feature claims)
2. Misleading (implies capabilities that don't exist)
3. Outdated (references removed features)
4. Legally risky (privacy/data claims that don't match reality)

For each issue found, respond in this exact JSON format:
{{"issues": [
  {{"claim": "the exact claim text", "problem": "why it's wrong", "severity": "high|medium|low", "suggestion": "how to fix"}}
]}}

If no issues found, respond: {{"issues": []}}
"""

        result = generate(
            prompt=prompt,
            system="You are a copy accuracy auditor. Be precise and conservative. "
                   "Only flag clear inaccuracies, not style preferences. "
                   "Respond with valid JSON only.",
            temperature=0.3,
            max_tokens=1024,
            use_cache=True,
            conn=conn,
            task_type="copy_drift_review",
        )

        if not result.success:
            continue

        # Parse LLM output
        try:
            # Extract JSON from response (may be wrapped in markdown code blocks)
            text = result.text.strip()
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                issues = data.get("issues", [])
                for issue in issues:
                    if not isinstance(issue, dict):
                        continue
                    claim = issue.get("claim", "")
                    problem = issue.get("problem", "")
                    severity = issue.get("severity", "low")
                    suggestion = issue.get("suggestion", "")

                    if severity not in ("high", "medium", "low"):
                        severity = "low"

                    findings.append(_finding(
                        "copy_drift", severity,
                        f"[LLM] Potential issue in {os.path.basename(path)}: {problem[:80]}",
                        f"Claim: '{claim}'. Problem: {problem}. "
                        f"(Identified by LLM review — verify manually before acting.)",
                        suggestion,
                        f"Review {os.path.basename(path)} for the claim '{claim[:60]}'. "
                        f"{suggestion}. This was flagged by LLM analysis — confirm manually.",
                        "Copy accuracy (LLM-assisted review)",
                        [path],
                    ))
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.debug("LLM copy review for %s returned unparseable output", page_key)

    return findings


# ══════════════════════════════════════════════════════════════════════
# AUTO-FIX
# ══════════════════════════════════════════════════════════════════════

def auto_fix_copy_drift(conn, finding: dict) -> bool:
    """Attempt to auto-fix a copy drift finding.

    For straightforward fixes (wrong number, wrong price), swap the value
    directly. Returns True if the fix was applied, False otherwise.
    """
    title = finding.get("title", "")
    files = finding.get("files", [])
    if not files:
        return False

    # ── Drill type count fixes ──
    drill_count_match = re.search(
        r'claims (\d+), actual (\d+)', title
    )
    if drill_count_match and "drill" in title.lower():
        old_count = drill_count_match.group(1)
        new_count = drill_count_match.group(2)
        return _swap_number_in_files(files, old_count, new_count, "drill type")

    # ── Pricing fixes ──
    price_match = re.search(r'\$(\d+\.?\d*)\s+(?:vs|.*expected)\s+\$(\d+\.?\d*)', title)
    if price_match:
        old_price = price_match.group(1)
        new_price = price_match.group(2)
        return _swap_dollar_amount_in_files(files, old_price, new_price)

    # ── Stale price in terms/emails ──
    stale_match = re.search(r'Stale price.*\$(\d+\.?\d*)\s+\(expected \$(\d+\.?\d*)\)', title)
    if stale_match:
        old_price = stale_match.group(1)
        new_price = stale_match.group(2)
        return _swap_dollar_amount_in_files(files, old_price, new_price)

    return False


def _swap_number_in_files(
    files: list[str], old_val: str, new_val: str, context_word: str,
) -> bool:
    """Replace a number near a context word in one or more files."""
    any_changed = False
    for file_path in files:
        abs_path = file_path
        if not os.path.isabs(file_path):
            abs_path = os.path.join(_PROJECT_ROOT, file_path)
        try:
            content = _read_abs(abs_path)
            if not content:
                continue
            # Replace "44 drill type" → "45 drill type" (preserving case and context)
            pattern = re.compile(
                rf'(\b){re.escape(old_val)}(\s+{re.escape(context_word)})',
                re.IGNORECASE,
            )
            new_content = pattern.sub(rf'\g<1>{new_val}\2', content)
            if new_content != content:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                any_changed = True
                logger.info("Auto-fixed: %s → %s in %s", old_val, new_val, abs_path)
        except Exception as e:
            logger.warning("Auto-fix failed for %s: %s", abs_path, e)
    return any_changed


def _swap_dollar_amount_in_files(
    files: list[str], old_amount: str, new_amount: str,
) -> bool:
    """Replace $old_amount with $new_amount in one or more files."""
    any_changed = False
    for file_path in files:
        abs_path = file_path
        if not os.path.isabs(file_path):
            abs_path = os.path.join(_PROJECT_ROOT, file_path)
        try:
            content = _read_abs(abs_path)
            if not content:
                continue
            # Only replace exact matches like $14.99, "$14.99", price: "14.99"
            patterns = [
                (rf'\${re.escape(old_amount)}', f"${new_amount}"),
                (rf'"price":\s*"{re.escape(old_amount)}"', f'"price": "{new_amount}"'),
            ]
            new_content = content
            for pat, repl in patterns:
                new_content = re.sub(pat, repl, new_content)
            if new_content != content:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                any_changed = True
                logger.info("Auto-fixed price: $%s → $%s in %s", old_amount, new_amount, abs_path)
        except Exception as e:
            logger.warning("Auto-fix price failed for %s: %s", abs_path, e)
    return any_changed


# ══════════════════════════════════════════════════════════════════════
# EXPORTS
# ══════════════════════════════════════════════════════════════════════

ANALYZERS = [
    _check_pricing_drift,
    _check_feature_claims,
    _check_privacy_claims,
    _check_terms_accuracy,
    _check_email_accuracy,
    _check_about_page_numbers,
    _check_ollama_deep_review,
]
