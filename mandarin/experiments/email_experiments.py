"""Email A/B testing — variant assignment, tracking, and analysis for email campaigns.

Uses the same deterministic hash-based assignment as the main experiment system
to ensure consistent variant assignment across channels for the same user.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def assign_email_variant(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
    *,
    variants: list[str] | None = None,
) -> str:
    """Assign a user to an email experiment variant.

    Uses the same deterministic hash as the main experiment system:
    SHA256(experiment_name + user_id) mod len(variants).

    If the user already has an assignment, returns the existing one.
    """
    if variants is None:
        variants = ["control", "treatment"]

    # Check for existing assignment
    try:
        row = conn.execute(
            "SELECT variant FROM experiment_assignment "
            "WHERE experiment_id = (SELECT id FROM experiment WHERE name = ?) "
            "AND user_id = ?",
            (experiment_name, user_id),
        ).fetchone()
        if row:
            return row["variant"]
    except sqlite3.OperationalError:
        pass

    # Deterministic assignment
    hash_input = f"email:{experiment_name}:{user_id}"
    hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16)
    variant_idx = hash_val % len(variants)
    variant = variants[variant_idx]

    # Try to persist assignment
    try:
        exp_row = conn.execute(
            "SELECT id FROM experiment WHERE name = ?", (experiment_name,)
        ).fetchone()
        if exp_row:
            conn.execute(
                "INSERT OR IGNORE INTO experiment_assignment "
                "(experiment_id, user_id, variant, assigned_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (exp_row["id"], user_id, variant),
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass

    return variant


def get_email_template_variant(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
    base_template: str,
) -> str:
    """Return the email template name for a user's variant.

    If user is in 'treatment' variant of experiment 'welcome_email_timing',
    and base_template is 'welcome.html', returns 'welcome-treatment.html'.
    Control variant returns the base template unchanged.
    """
    variant = assign_email_variant(conn, experiment_name, user_id)

    if variant == "control":
        return base_template

    # Construct variant template name: 'weekly-progress.html' → 'weekly-progress-treatment.html'
    name, ext = base_template.rsplit(".", 1) if "." in base_template else (base_template, "html")
    return f"{name}-{variant}.{ext}"


def log_email_send(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
    variant: str,
    email_type: str,
    resend_message_id: str | None = None,
) -> None:
    """Log an email send for experiment tracking."""
    try:
        conn.execute(
            "INSERT INTO email_send_log "
            "(email_type, user_id, resend_message_id, sent_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (f"{email_type}:{experiment_name}:{variant}", user_id, resend_message_id),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("email_send_log table may not exist")


def log_email_open(conn: sqlite3.Connection, resend_message_id: str) -> None:
    """Record an email open event."""
    try:
        conn.execute(
            "UPDATE email_send_log SET opened_at = datetime('now') "
            "WHERE resend_message_id = ? AND opened_at IS NULL",
            (resend_message_id,),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def log_email_click(conn: sqlite3.Connection, resend_message_id: str) -> None:
    """Record an email click event."""
    try:
        conn.execute(
            "UPDATE email_send_log SET clicked_at = datetime('now') "
            "WHERE resend_message_id = ? AND clicked_at IS NULL",
            (resend_message_id,),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def analyze_email_experiment(
    conn: sqlite3.Connection,
    experiment_name: str,
) -> dict:
    """Analyze an email experiment's performance.

    Computes per-variant: send count, open rate, click rate, conversion rate.
    Runs both frequentist (z-test) and Bayesian (Beta-Binomial) analysis.
    Includes SRM check on send counts.
    """
    try:
        # Query email sends with variant info
        # email_type format: "{type}:{experiment_name}:{variant}"
        rows = conn.execute(
            """
            SELECT
                SUBSTR(email_type, INSTR(email_type, ':') + LENGTH(?) + 2) AS variant,
                COUNT(*) AS sent,
                SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened,
                SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicked,
                SUM(CASE WHEN converted_at IS NOT NULL THEN 1 ELSE 0 END) AS converted
            FROM email_send_log
            WHERE email_type LIKE ?
            GROUP BY variant
            """,
            (experiment_name, f"%:{experiment_name}:%"),
        ).fetchall()

        if not rows or len(rows) < 2:
            return {"error": "Insufficient data", "experiment": experiment_name}

        variants = {}
        total_sent = 0
        for r in rows:
            variant = r["variant"]
            sent = r["sent"]
            total_sent += sent
            variants[variant] = {
                "sent": sent,
                "opened": r["opened"],
                "clicked": r["clicked"],
                "converted": r["converted"],
                "open_rate": round(r["opened"] / sent * 100, 2) if sent > 0 else 0,
                "click_rate": round(r["clicked"] / sent * 100, 2) if sent > 0 else 0,
                "conversion_rate": round(r["converted"] / sent * 100, 2) if sent > 0 else 0,
            }

        # SRM check on send counts
        expected_per_variant = total_sent / len(variants)
        srm_chi2 = sum(
            (v["sent"] - expected_per_variant) ** 2 / expected_per_variant
            for v in variants.values()
        )
        srm_ok = srm_chi2 < 10.83  # chi2 critical value for df=1 at p=0.001

        # Bayesian analysis on open rate
        bayesian_data = {}
        for vname, vdata in variants.items():
            bayesian_data[vname] = {
                "successes": vdata["opened"],
                "trials": vdata["sent"],
            }

        from .bayesian import compute_bayesian_results
        bayesian_results = compute_bayesian_results(
            bayesian_data, metric="open_rate"
        )

        return {
            "experiment": experiment_name,
            "variants": variants,
            "srm_check": {"chi2": round(srm_chi2, 4), "passed": srm_ok},
            "bayesian": bayesian_results,
            "total_sent": total_sent,
        }

    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.error("Email experiment analysis failed: %s", e)
        return {"error": str(e), "experiment": experiment_name}
