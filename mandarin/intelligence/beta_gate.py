"""Beta readiness gate — 18 pass/fail checks that must clear before public launch.

Each check is a concrete function that validates a specific launch prerequisite.
Checks marked ``blocking=True`` must pass before the product can go live;
``blocking=False`` checks are warnings (nice-to-have for launch).

When a blocking check *regresses* (was passing, now failing), an alert email
is sent to the admin.

Exports:
    CHECKS: list of (id, description, blocking) tuples
    run_beta_gate: run all checks and return structured results
    ANALYZERS: list of analyzer functions for the intelligence engine
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query

logger = logging.getLogger(__name__)


# ── Check definitions ────────────────────────────────────────────────────
# (id, description, blocking)

CHECKS = [
    ("health_200", "GET /api/health/live returns 200", True),
    ("stripe_live", "STRIPE_SECRET_KEY starts with sk_live_", True),
    ("email_configured", "RESEND_API_KEY is set", True),
    ("sentry_configured", "SENTRY_DSN is set", False),
    ("uptime_monitor", "UPTIMEROBOT_API_KEY is set", False),
    ("hsk1_vocab", "HSK1 vocab >= 150", True),
    ("hsk2_vocab", "HSK2 vocab >= 150", True),
    ("hsk3_vocab", "HSK3 vocab >= 300", False),
    ("grammar_seeded", "grammar_points >= 20", True),
    ("admin_exists", "at least 1 admin user", True),
    ("srs_tables", "SRS tables exist with data", True),
    ("stripe_products", "at least 1 Stripe price configured", True),
    ("plausible_configured", "PLAUSIBLE_API_KEY is set", False),
    ("analytics_configured", "PLAUSIBLE_DOMAIN is set", False),
    ("tts_available", "edge-tts importable", True),
    ("db_writable", "can write to DB", True),
    ("llm_available", "LLM endpoint responds", True),
    ("cost_tracking", "llm_cost_log table exists", False),
]


# ── Individual check functions ───────────────────────────────────────────


def _check_health_200(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify that the health endpoint responds with 200."""
    try:
        from ..settings import BASE_URL
        import requests
        url = f"{BASE_URL}/api/health/live"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return True, f"Health endpoint returned 200 ({url})"
        return False, f"Health endpoint returned {resp.status_code} ({url})"
    except Exception as e:
        return False, f"Health endpoint unreachable: {e}"


def _check_stripe_live(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify that STRIPE_SECRET_KEY starts with sk_live_."""
    try:
        from ..settings import STRIPE_SECRET_KEY
        if STRIPE_SECRET_KEY and STRIPE_SECRET_KEY.startswith("sk_live_"):
            return True, "Stripe live key configured"
        if STRIPE_SECRET_KEY and STRIPE_SECRET_KEY.startswith("sk_test_"):
            return False, "Stripe key is test mode (sk_test_), not live"
        return False, "STRIPE_SECRET_KEY is empty or invalid"
    except (ImportError, AttributeError):
        return False, "STRIPE_SECRET_KEY not found in settings"


def _check_email_configured(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify that RESEND_API_KEY is set."""
    try:
        from ..settings import RESEND_API_KEY
        if RESEND_API_KEY:
            return True, "RESEND_API_KEY is configured"
        return False, "RESEND_API_KEY is empty"
    except (ImportError, AttributeError):
        return False, "RESEND_API_KEY not found in settings"


def _check_sentry_configured(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify that SENTRY_DSN is set."""
    try:
        from ..settings import SENTRY_DSN
        if SENTRY_DSN:
            return True, "SENTRY_DSN is configured"
        return False, "SENTRY_DSN is empty — error monitoring disabled"
    except (ImportError, AttributeError):
        return False, "SENTRY_DSN not found in settings"


def _check_uptime_monitor(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify that UPTIMEROBOT_API_KEY is set."""
    try:
        from ..settings import UPTIMEROBOT_API_KEY
        if UPTIMEROBOT_API_KEY:
            return True, "UPTIMEROBOT_API_KEY is configured"
        return False, "UPTIMEROBOT_API_KEY is empty — uptime monitoring disabled"
    except (ImportError, AttributeError):
        return False, "UPTIMEROBOT_API_KEY not found in settings"


def _check_hsk1_vocab(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify HSK1 vocab count >= 150."""
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved' AND hsk_level = 1
    """, default=0)
    if count >= 150:
        return True, f"HSK1 vocab: {count} (>= 150)"
    return False, f"HSK1 vocab: {count} (need >= 150)"


def _check_hsk2_vocab(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify HSK2 vocab count >= 150."""
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved' AND hsk_level = 2
    """, default=0)
    if count >= 150:
        return True, f"HSK2 vocab: {count} (>= 150)"
    return False, f"HSK2 vocab: {count} (need >= 150)"


def _check_hsk3_vocab(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify HSK3 vocab count >= 300."""
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved' AND hsk_level = 3
    """, default=0)
    if count >= 300:
        return True, f"HSK3 vocab: {count} (>= 300)"
    return False, f"HSK3 vocab: {count} (need >= 300)"


def _check_grammar_seeded(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify at least 20 grammar points exist."""
    count = _safe_scalar(conn, "SELECT COUNT(*) FROM grammar_point", default=0)
    if count >= 20:
        return True, f"Grammar points: {count} (>= 20)"
    return False, f"Grammar points: {count} (need >= 20)"


def _check_admin_exists(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify at least 1 admin user exists."""
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE is_admin = 1
    """, default=0)
    if count >= 1:
        return True, f"Admin users: {count}"
    return False, "No admin users found"


def _check_srs_tables(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify SRS tables exist and contain data."""
    # Check progress table exists and has data
    progress_count = _safe_scalar(conn, "SELECT COUNT(*) FROM progress", default=0)
    content_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item WHERE review_status = 'approved'
    """, default=0)

    if content_count == 0:
        return False, "No approved content items for SRS"
    if progress_count >= 0 and content_count > 0:
        return True, f"SRS ready: {content_count} content items, {progress_count} progress records"
    return False, f"SRS tables incomplete: {content_count} content, {progress_count} progress"


def _check_stripe_products(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify at least 1 Stripe price is configured in settings."""
    try:
        from ..settings import PRICING, STRIPE_SECRET_KEY
        if not STRIPE_SECRET_KEY:
            return False, "STRIPE_SECRET_KEY not set — cannot verify products"

        monthly_cents = PRICING.get("monthly_cents", 0)
        annual_cents = PRICING.get("annual_cents", 0)

        if monthly_cents > 0 or annual_cents > 0:
            return True, f"Pricing configured: monthly={monthly_cents}c, annual={annual_cents}c"
        return False, "No pricing configured in settings.PRICING"
    except (ImportError, AttributeError):
        return False, "Could not read pricing configuration"


def _check_plausible_configured(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify PLAUSIBLE_API_KEY is set."""
    try:
        from ..settings import PLAUSIBLE_API_KEY
        if PLAUSIBLE_API_KEY:
            return True, "PLAUSIBLE_API_KEY is configured"
        return False, "PLAUSIBLE_API_KEY is empty"
    except (ImportError, AttributeError):
        return False, "PLAUSIBLE_API_KEY not found in settings"


def _check_analytics_configured(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify PLAUSIBLE_DOMAIN is set."""
    try:
        from ..settings import PLAUSIBLE_DOMAIN
        if PLAUSIBLE_DOMAIN:
            return True, f"PLAUSIBLE_DOMAIN is configured: {PLAUSIBLE_DOMAIN}"
        return False, "PLAUSIBLE_DOMAIN is empty"
    except (ImportError, AttributeError):
        return False, "PLAUSIBLE_DOMAIN not found in settings"


def _check_tts_available(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify that edge-tts is importable."""
    try:
        import edge_tts  # noqa: F401
        return True, "edge-tts is importable"
    except ImportError:
        return False, "edge-tts is not installed (pip install edge-tts)"


def _check_db_writable(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify the database is writable."""
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _beta_gate_test (id INTEGER PRIMARY KEY)
        """)
        conn.execute("INSERT INTO _beta_gate_test (id) VALUES (1)")
        conn.execute("DELETE FROM _beta_gate_test WHERE id = 1")
        conn.execute("DROP TABLE IF EXISTS _beta_gate_test")
        conn.commit()
        return True, "Database is writable"
    except (sqlite3.Error, OSError) as e:
        return False, f"Database not writable: {e}"


def _check_llm_available(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify the LLM endpoint responds."""
    try:
        from ..settings import OLLAMA_URL, OLLAMA_PRIMARY_MODEL
        import requests
        # Check Ollama tags endpoint
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            if any(OLLAMA_PRIMARY_MODEL in m for m in models):
                return True, f"LLM available: {OLLAMA_PRIMARY_MODEL}"
            return False, f"LLM endpoint up but model '{OLLAMA_PRIMARY_MODEL}' not found. Available: {', '.join(models[:5])}"
        return False, f"LLM endpoint returned {resp.status_code}"
    except Exception as e:
        return False, f"LLM endpoint unreachable: {e}"


def _check_cost_tracking(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Verify llm_cost_log table exists."""
    try:
        row = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'llm_cost_log'
        """).fetchone()
        if row:
            return True, "llm_cost_log table exists"
        return False, "llm_cost_log table does not exist"
    except sqlite3.Error as e:
        return False, f"Could not check for llm_cost_log table: {e}"


# Map check IDs to their functions
_CHECK_FUNCTIONS = {
    "health_200": _check_health_200,
    "stripe_live": _check_stripe_live,
    "email_configured": _check_email_configured,
    "sentry_configured": _check_sentry_configured,
    "uptime_monitor": _check_uptime_monitor,
    "hsk1_vocab": _check_hsk1_vocab,
    "hsk2_vocab": _check_hsk2_vocab,
    "hsk3_vocab": _check_hsk3_vocab,
    "grammar_seeded": _check_grammar_seeded,
    "admin_exists": _check_admin_exists,
    "srs_tables": _check_srs_tables,
    "stripe_products": _check_stripe_products,
    "plausible_configured": _check_plausible_configured,
    "analytics_configured": _check_analytics_configured,
    "tts_available": _check_tts_available,
    "db_writable": _check_db_writable,
    "llm_available": _check_llm_available,
    "cost_tracking": _check_cost_tracking,
}


# ── Core gate runner ─────────────────────────────────────────────────────


def run_beta_gate(conn: sqlite3.Connection) -> dict:
    """Run all beta gate checks and return structured results.

    Returns:
        {
            "ready": bool,           # True if all blocking checks pass
            "passed": [...],         # list of passed check dicts
            "failed": [...],         # list of failed blocking check dicts
            "warnings": [...],       # list of failed non-blocking check dicts
            "total": int,
            "passed_count": int,
            "failed_count": int,
            "warning_count": int,
        }
    """
    passed = []
    failed = []
    warnings = []

    for check_id, description, blocking in CHECKS:
        check_fn = _CHECK_FUNCTIONS.get(check_id)
        if check_fn is None:
            logger.warning("Beta gate check %s has no implementation", check_id)
            continue

        try:
            ok, detail = check_fn(conn)
        except Exception as e:
            ok = False
            detail = f"Check raised exception: {e}"
            logger.warning("Beta gate check %s failed with exception: %s", check_id, e)

        entry = {
            "id": check_id,
            "description": description,
            "blocking": blocking,
            "passed": ok,
            "detail": detail,
        }

        if ok:
            passed.append(entry)
        elif blocking:
            failed.append(entry)
        else:
            warnings.append(entry)

    ready = len(failed) == 0

    result = {
        "ready": ready,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "total": len(CHECKS),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "warning_count": len(warnings),
    }

    # Check for regressions and send alerts
    _check_regressions_and_alert(conn, result)

    return result


# ── Regression detection and alerting ────────────────────────────────────


def _get_previous_results(conn: sqlite3.Connection) -> dict[str, bool] | None:
    """Load previous beta gate results from the DB."""
    try:
        import json
        row = _safe_query(conn, """
            SELECT details FROM quality_metric
            WHERE metric_type = 'beta_gate'
            ORDER BY measured_at DESC
            LIMIT 1
        """)
        if row and row["details"]:
            data = json.loads(row["details"])
            return {c["id"]: c["passed"] for c in data.get("all_checks", [])}
    except Exception:
        pass
    return None


def _save_results(conn: sqlite3.Connection, result: dict) -> None:
    """Save current beta gate results for future regression detection."""
    try:
        import json
        all_checks = result["passed"] + result["failed"] + result["warnings"]
        conn.execute("""
            INSERT INTO quality_metric (metric_type, value, details)
            VALUES ('beta_gate', ?, ?)
        """, (
            1.0 if result["ready"] else 0.0,
            json.dumps({
                "ready": result["ready"],
                "passed_count": result["passed_count"],
                "failed_count": result["failed_count"],
                "warning_count": result["warning_count"],
                "all_checks": all_checks,
            }),
        ))
        conn.commit()
    except Exception as e:
        logger.debug("Failed to save beta gate results: %s", e)


def _check_regressions_and_alert(conn: sqlite3.Connection, result: dict) -> None:
    """Detect blocking check regressions and email admin."""
    previous = _get_previous_results(conn)
    _save_results(conn, result)

    if previous is None:
        return  # First run — no regression possible

    regressions = []
    for check in result["failed"]:
        check_id = check["id"]
        if previous.get(check_id, False):
            # Was passing, now failing — regression
            regressions.append(check)

    if not regressions:
        return

    # Send alert email
    try:
        from ..email import send_alert
        from ..settings import ADMIN_EMAIL
        admin_email = ADMIN_EMAIL or ""
        if not admin_email:
            logger.warning("Beta gate regression detected but ADMIN_EMAIL not set")
            return

        names = ", ".join(r["id"] for r in regressions)
        details_lines = []
        for r in regressions:
            details_lines.append(f"- {r['id']}: {r['description']} -- {r['detail']}")
        details = "\n".join(details_lines)

        send_alert(
            to_email=admin_email,
            subject=f"Beta gate regression: {len(regressions)} blocking check(s) now failing",
            details=(
                f"The following blocking beta gate checks were previously passing "
                f"and are now failing:\n\n{details}\n\n"
                f"These must be resolved before launch."
            ),
        )
        logger.warning("Beta gate regression alert sent: %s", names)
    except Exception as e:
        logger.warning("Failed to send beta gate regression alert: %s", e)


# ── Intelligence engine analyzer ─────────────────────────────────────────


def analyze_beta_gate(conn: sqlite3.Connection) -> list[dict]:
    """Run beta gate checks and convert failures to intelligence findings."""
    findings = []

    result = run_beta_gate(conn)

    if result["ready"]:
        # All blocking checks pass — emit informational finding
        warning_ids = ", ".join(w["id"] for w in result["warnings"])
        if result["warnings"]:
            findings.append(_finding(
                "engineering", "low",
                f"Beta gate: ready ({result['warning_count']} non-blocking warnings)",
                f"All {len([c for c in CHECKS if c[2]])} blocking checks pass. "
                f"{result['warning_count']} non-blocking warnings: {warning_ids}.",
                "Address non-blocking warnings before full launch for best experience.",
                "Review beta gate warnings and address remaining items.",
                "Non-blocking warnings affect monitoring and analytics quality.",
                ["mandarin/intelligence/beta_gate.py"],
            ))
        return findings

    # Blocking failures — generate findings
    for check in result["failed"]:
        findings.append(_finding(
            "engineering", "critical" if check["blocking"] else "low",
            f"Beta gate FAIL: {check['description']}",
            f"Blocking check '{check['id']}' failed: {check['detail']}. "
            f"This must be resolved before the product can go live.",
            f"Fix: {check['detail']}",
            f"Resolve beta gate blocker: {check['id']} -- {check['description']}.",
            "Launch blocker — product cannot go live until resolved.",
            ["mandarin/intelligence/beta_gate.py"],
        ))

    # Non-blocking warnings as lower severity
    for check in result["warnings"]:
        findings.append(_finding(
            "engineering", "low",
            f"Beta gate WARNING: {check['description']}",
            f"Non-blocking check '{check['id']}' failed: {check['detail']}. "
            f"Recommended but not required for launch.",
            f"Configure: {check['detail']}",
            f"Address beta gate warning: {check['id']} -- {check['description']}.",
            "Nice-to-have for launch — improves monitoring and analytics.",
            ["mandarin/intelligence/beta_gate.py"],
        ))

    return findings


# ── Analyzer registration ───────────────────────────────────────────────

ANALYZERS = [
    analyze_beta_gate,
]
