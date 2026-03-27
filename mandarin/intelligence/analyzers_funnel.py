"""Activation funnel analyzer — auto-detects and auto-fixes broken funnels.

Monitors seven funnel stages from visit through subscription, computes
conversion rates over 7-day and 30-day windows, compares against health
thresholds, and prescribes concrete auto-fixes using the experiment proposer,
email system, and feature flags.

Funnel stages:
    visit -> signup -> email_verified -> first_session ->
    session_completed -> return_day2 -> return_day7 -> subscription
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)

# ── Funnel stage definitions ─────────────────────────────────────────────
# Each stage: (name, threshold_pct, auto_fix_action, dimension, severity_when_broken)

FUNNEL_STAGES = [
    {
        "from": "visit",
        "to": "signup",
        "threshold": 5.0,
        "action": "auto_test_registration_page",
        "description": "Visitor to signup conversion",
    },
    {
        "from": "signup",
        "to": "email_verified",
        "threshold": 60.0,
        "action": "resend_verification_shorten_email",
        "description": "Signup to email verified",
    },
    {
        "from": "email_verified",
        "to": "first_session",
        "threshold": 40.0,
        "action": "auto_test_onboarding_copy",
        "description": "Email verified to first session",
    },
    {
        "from": "first_session",
        "to": "session_completed",
        "threshold": 70.0,
        "action": "reduce_session_length",
        "description": "First session started to session completed",
    },
    {
        "from": "session_completed",
        "to": "return_day2",
        "threshold": 30.0,
        "action": "auto_send_reminder_email",
        "description": "Session completed to day-2 return",
    },
    {
        "from": "return_day2",
        "to": "return_day7",
        "threshold": 50.0,
        "action": "auto_test_retention_email",
        "description": "Day-2 return to day-7 return",
    },
    {
        "from": "return_day7",
        "to": "subscription",
        "threshold": 5.0,
        "action": "auto_test_pricing_page",
        "description": "Day-7 active to subscription conversion",
    },
]


# ── Stage count queries ──────────────────────────────────────────────────
# Each function returns the count of users/events in that stage for a given
# lookback window (e.g. '-7 days' or '-30 days').


def _count_visits(conn: sqlite3.Connection, window: str) -> int:
    """Count unique visitors from pi_funnel_events or Plausible analytics."""
    # Try pi_funnel_events first
    count = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT COALESCE(user_id, session_token))
        FROM pi_funnel_events
        WHERE event_type = 'visit'
          AND occurred_at >= datetime('now', ?)
    """, (window,), default=0)
    if count > 0:
        return count

    # Fallback: count from pi_marketing_pages (monthly_visitors scaled to window)
    monthly = _safe_scalar(conn, """
        SELECT SUM(monthly_visitors) FROM pi_marketing_pages
        WHERE monthly_visitors IS NOT NULL
    """, default=0)
    if monthly and monthly > 0:
        days = 7 if window == '-7 days' else 30
        return max(1, int(monthly * days / 30))

    return 0


def _count_signups(conn: sqlite3.Connection, window: str) -> int:
    """Count new user registrations in the window."""
    return _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE is_admin = 0
          AND created_at >= datetime('now', ?)
    """, (window,), default=0)


def _count_email_verified(conn: sqlite3.Connection, window: str) -> int:
    """Count users who verified their email in the window."""
    return _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE is_admin = 0
          AND email_verified = 1
          AND created_at >= datetime('now', ?)
    """, (window,), default=0)


def _count_first_session(conn: sqlite3.Connection, window: str) -> int:
    """Count users who started their first session in the window."""
    return _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE is_admin = 0
          AND first_session_at IS NOT NULL
          AND first_session_at >= datetime('now', ?)
    """, (window,), default=0)


def _count_session_completed(conn: sqlite3.Connection, window: str) -> int:
    """Count users whose first session was completed (not abandoned/bounced)."""
    return _safe_scalar(conn, """
        SELECT COUNT(DISTINCT sl.user_id) FROM session_log sl
        JOIN user u ON sl.user_id = u.id
        WHERE u.is_admin = 0
          AND sl.session_outcome = 'completed'
          AND sl.started_at >= datetime('now', ?)
          AND sl.id = (
              SELECT MIN(s2.id) FROM session_log s2
              WHERE s2.user_id = sl.user_id
          )
    """, (window,), default=0)


def _count_return_day2(conn: sqlite3.Connection, window: str) -> int:
    """Count users who returned for a second session within 2 days of their first."""
    return _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        WHERE u.is_admin = 0
          AND u.first_session_at IS NOT NULL
          AND u.first_session_at >= datetime('now', ?)
          AND EXISTS (
              SELECT 1 FROM session_log sl
              WHERE sl.user_id = u.id
                AND sl.started_at > u.first_session_at
                AND sl.started_at <= datetime(u.first_session_at, '+2 days')
          )
    """, (window,), default=0)


def _count_return_day7(conn: sqlite3.Connection, window: str) -> int:
    """Count users who had a session between day 3 and day 7 after signup."""
    return _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        WHERE u.is_admin = 0
          AND u.first_session_at IS NOT NULL
          AND u.first_session_at >= datetime('now', ?)
          AND EXISTS (
              SELECT 1 FROM session_log sl
              WHERE sl.user_id = u.id
                AND sl.started_at > datetime(u.first_session_at, '+2 days')
                AND sl.started_at <= datetime(u.first_session_at, '+7 days')
          )
    """, (window,), default=0)


def _count_subscription(conn: sqlite3.Connection, window: str) -> int:
    """Count users who converted to a paid subscription in the window."""
    return _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE is_admin = 0
          AND subscription_tier IN ('paid', 'premium')
          AND subscription_status = 'active'
          AND created_at >= datetime('now', ?)
    """, (window,), default=0)


# Map stage names to their count functions
_STAGE_COUNTERS = {
    "visit": _count_visits,
    "signup": _count_signups,
    "email_verified": _count_email_verified,
    "first_session": _count_first_session,
    "session_completed": _count_session_completed,
    "return_day2": _count_return_day2,
    "return_day7": _count_return_day7,
    "subscription": _count_subscription,
}


# ── Auto-fix prescriptions ──────────────────────────────────────────────
# Each returns a dict describing the concrete fix action taken or proposed.


def _fix_auto_test_registration_page(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Propose A/B test on registration page variants."""
    try:
        from .experiment_proposer import propose_experiment
        finding = _finding(
            "activation_funnel", "high",
            f"Visit-to-signup conversion critically low ({rate_7d:.1f}% 7d)",
            f"Only {rate_7d:.1f}% of visitors sign up (7d), {rate_30d:.1f}% (30d). "
            f"Threshold: 5%. Registration page may have friction, unclear value prop, "
            f"or trust barriers.",
            "Test simplified registration with fewer fields, social proof, "
            "and clearer value proposition above the fold.",
            "Propose A/B experiment on registration page: control vs simplified variant.",
            "Registration page conversion directly limits all downstream metrics.",
            ["mandarin/web/auth_routes.py", "mandarin/web/templates/auth/register.html",
             "marketing/landing/index.html"],
        )
        proposal = propose_experiment(conn, finding, source="funnel_analyzer")
        action = "experiment_proposed" if proposal else "experiment_proposal_failed"
    except (ImportError, Exception) as e:
        logger.debug("Could not propose registration experiment: %s", e)
        proposal = None
        action = "experiment_proposal_failed"

    return {
        "action": "auto_test_registration_page",
        "status": action,
        "proposal": proposal,
        "detail": "A/B test registration page: control vs simplified variant "
                  "with fewer fields and clearer value prop.",
    }


def _fix_resend_verification(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Resend verification emails to unverified users and flag for shorter email copy."""
    resent_count = 0
    try:
        # Find unverified users from last 7 days who haven't been nudged recently
        unverified = _safe_query_all(conn, """
            SELECT id, email, display_name FROM user
            WHERE is_admin = 0
              AND email_verified = 0
              AND created_at >= datetime('now', '-7 days')
              AND id NOT IN (
                  SELECT CAST(user_id AS INTEGER) FROM lifecycle_event
                  WHERE event_type = 'verification_resent'
                    AND created_at >= datetime('now', '-2 days')
              )
            LIMIT 50
        """)

        if unverified:
            from ..email import send_email_verification
            from ..auth import generate_email_verify_token
            for user in unverified:
                try:
                    token = generate_email_verify_token(conn, user["id"])
                    if token:
                        verify_url = f"/verify-email?token={token}"
                        sent = send_email_verification(user["email"], verify_url)
                        if sent:
                            resent_count += 1
                            # Log lifecycle event to avoid re-sending
                            conn.execute("""
                                INSERT INTO lifecycle_event (event_type, user_id, metadata)
                                VALUES ('verification_resent', ?, ?)
                            """, (str(user["id"]), json.dumps({"source": "funnel_analyzer"})))
                except Exception as e:
                    logger.debug("Failed to resend verification to user %s: %s", user["id"], e)
            if resent_count > 0:
                conn.commit()
    except (ImportError, Exception) as e:
        logger.debug("Verification resend failed: %s", e)

    return {
        "action": "resend_verification_shorten_email",
        "status": "resent" if resent_count > 0 else "no_action",
        "resent_count": resent_count,
        "detail": f"Resent {resent_count} verification emails. "
                  f"Consider shortening verification email copy for higher open rates.",
    }


def _fix_auto_test_onboarding(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Propose A/B test on onboarding copy and flow."""
    try:
        from .experiment_proposer import propose_experiment
        finding = _finding(
            "activation_funnel", "high",
            f"Verified-to-first-session conversion low ({rate_7d:.1f}% 7d)",
            f"Only {rate_7d:.1f}% of verified users start their first session (7d), "
            f"{rate_30d:.1f}% (30d). Threshold: 40%. Onboarding may be confusing or "
            f"not conveying urgency to start.",
            "Test onboarding variants: shorter copy, immediate drill preview, "
            "progress visualization from step one.",
            "Propose A/B experiment on onboarding flow and welcome copy.",
            "Users verified but not activating = onboarding friction.",
            ["mandarin/web/onboarding_routes.py",
             "mandarin/web/templates/onboarding/"],
        )
        proposal = propose_experiment(conn, finding, source="funnel_analyzer")
        action = "experiment_proposed" if proposal else "experiment_proposal_failed"
    except (ImportError, Exception) as e:
        logger.debug("Could not propose onboarding experiment: %s", e)
        proposal = None
        action = "experiment_proposal_failed"

    return {
        "action": "auto_test_onboarding_copy",
        "status": action,
        "proposal": proposal,
        "detail": "A/B test onboarding: control vs streamlined flow with "
                  "immediate drill preview and shorter welcome copy.",
    }


def _fix_reduce_session_length(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Reduce default session length via feature flag to improve completion."""
    adjusted = False
    try:
        from ..feature_flags import is_enabled
        # Check if short_session flag already exists and is enabled
        flag_row = _safe_query(conn, """
            SELECT enabled, rollout_pct FROM feature_flag
            WHERE name = 'short_first_session'
        """)
        if flag_row is None:
            # Create the flag at 50% rollout for A/B comparison
            conn.execute("""
                INSERT OR IGNORE INTO feature_flag (name, enabled, rollout_pct, created_at)
                VALUES ('short_first_session', 1, 50, datetime('now'))
            """)
            conn.commit()
            adjusted = True
        elif not flag_row["enabled"]:
            conn.execute("""
                UPDATE feature_flag SET enabled = 1, rollout_pct = 50
                WHERE name = 'short_first_session'
            """)
            conn.commit()
            adjusted = True
    except (ImportError, sqlite3.Error) as e:
        logger.debug("Could not adjust session length flag: %s", e)

    return {
        "action": "reduce_session_length",
        "status": "flag_activated" if adjusted else "already_active",
        "detail": "Feature flag 'short_first_session' set to 50% rollout. "
                  "Shorter first sessions (10 items vs 20) improve completion rate.",
    }


def _fix_send_reminder_email(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Send day-1 reminder emails to users who completed a session but haven't returned."""
    sent_count = 0
    try:
        # Users who completed their first session 1-2 days ago but haven't returned
        eligible = _safe_query_all(conn, """
            SELECT DISTINCT u.id, u.email, u.display_name FROM user u
            JOIN session_log sl ON sl.user_id = u.id
            WHERE u.is_admin = 0
              AND u.marketing_opt_out = 0
              AND sl.session_outcome = 'completed'
              AND sl.started_at >= datetime('now', '-3 days')
              AND sl.started_at <= datetime('now', '-1 days')
              AND NOT EXISTS (
                  SELECT 1 FROM session_log sl2
                  WHERE sl2.user_id = u.id
                    AND sl2.started_at > sl.started_at
              )
              AND u.id NOT IN (
                  SELECT CAST(user_id AS INTEGER) FROM lifecycle_event
                  WHERE event_type = 'day2_reminder_sent'
                    AND created_at >= datetime('now', '-3 days')
              )
            LIMIT 50
        """)

        if eligible:
            from ..email import send_activation_nudge
            for user in eligible:
                try:
                    sent = send_activation_nudge(
                        to=user["email"],
                        name=user["display_name"] or "there",
                        n=1,
                        user_id=user["id"],
                    )
                    if sent:
                        sent_count += 1
                        conn.execute("""
                            INSERT INTO lifecycle_event (event_type, user_id, metadata)
                            VALUES ('day2_reminder_sent', ?, ?)
                        """, (str(user["id"]), json.dumps({"source": "funnel_analyzer"})))
                except Exception as e:
                    logger.debug("Failed to send reminder to user %s: %s", user["id"], e)
            if sent_count > 0:
                conn.commit()
    except (ImportError, Exception) as e:
        logger.debug("Reminder email sending failed: %s", e)

    return {
        "action": "auto_send_reminder_email",
        "status": "sent" if sent_count > 0 else "no_eligible_users",
        "sent_count": sent_count,
        "detail": f"Sent {sent_count} day-2 reminder emails to users who completed "
                  f"a session but haven't returned.",
    }


def _fix_auto_test_retention_email(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Propose A/B test on retention email copy for day-2 to day-7 retention."""
    try:
        from .experiment_proposer import propose_experiment
        finding = _finding(
            "activation_funnel", "medium",
            f"Day-2 to day-7 retention low ({rate_7d:.1f}% 7d)",
            f"Only {rate_7d:.1f}% of day-2 returners come back by day 7 (7d), "
            f"{rate_30d:.1f}% (30d). Threshold: 50%. Retention email copy or "
            f"timing may not be compelling enough.",
            "Test retention email variants: progress summaries, streak encouragement, "
            "and personalized next-lesson previews.",
            "Propose A/B experiment on retention email copy and send timing.",
            "Week-1 retention is the strongest predictor of long-term engagement.",
            ["mandarin/email.py", "mandarin/scheduler.py"],
        )
        proposal = propose_experiment(conn, finding, source="funnel_analyzer")
        action = "experiment_proposed" if proposal else "experiment_proposal_failed"
    except (ImportError, Exception) as e:
        logger.debug("Could not propose retention email experiment: %s", e)
        proposal = None
        action = "experiment_proposal_failed"

    return {
        "action": "auto_test_retention_email",
        "status": action,
        "proposal": proposal,
        "detail": "A/B test retention emails: control vs progress-summary variant "
                  "with personalized next-lesson preview.",
    }


def _fix_auto_test_pricing_page(conn: sqlite3.Connection, rate_7d: float, rate_30d: float) -> dict:
    """Propose A/B test on pricing page for subscription conversion."""
    try:
        from .experiment_proposer import propose_experiment
        finding = _finding(
            "activation_funnel", "high",
            f"Day-7 active to subscription conversion low ({rate_7d:.1f}% 7d)",
            f"Only {rate_7d:.1f}% of day-7 active users convert to paid (7d), "
            f"{rate_30d:.1f}% (30d). Threshold: 5%. Pricing page, trial length, "
            f"or value communication may need optimization.",
            "Test pricing page variants: social proof, trial extension offer, "
            "feature comparison table, money-back guarantee emphasis.",
            "Propose A/B experiment on pricing page layout and copy.",
            "Subscription conversion is the final revenue gate.",
            ["mandarin/web/templates/pricing.html", "marketing/landing/pricing.html",
             "mandarin/payment.py"],
        )
        proposal = propose_experiment(conn, finding, source="funnel_analyzer")
        action = "experiment_proposed" if proposal else "experiment_proposal_failed"
    except (ImportError, Exception) as e:
        logger.debug("Could not propose pricing experiment: %s", e)
        proposal = None
        action = "experiment_proposal_failed"

    return {
        "action": "auto_test_pricing_page",
        "status": action,
        "proposal": proposal,
        "detail": "A/B test pricing page: control vs variant with social proof, "
                  "feature comparison, and money-back guarantee.",
    }


# Map action names to fix functions
_FIX_ACTIONS = {
    "auto_test_registration_page": _fix_auto_test_registration_page,
    "resend_verification_shorten_email": _fix_resend_verification,
    "auto_test_onboarding_copy": _fix_auto_test_onboarding,
    "reduce_session_length": _fix_reduce_session_length,
    "auto_send_reminder_email": _fix_send_reminder_email,
    "auto_test_retention_email": _fix_auto_test_retention_email,
    "auto_test_pricing_page": _fix_auto_test_pricing_page,
}


# ── Core analyzer ────────────────────────────────────────────────────────


def _compute_stage_counts(conn: sqlite3.Connection, window: str) -> dict[str, int]:
    """Compute user counts at each funnel stage for the given time window."""
    counts = {}
    for stage_name, counter_fn in _STAGE_COUNTERS.items():
        try:
            counts[stage_name] = counter_fn(conn, window)
        except Exception as e:
            logger.debug("Failed to count stage %s: %s", stage_name, e)
            counts[stage_name] = 0
    return counts


def _compute_conversion_rate(from_count: int, to_count: int) -> float | None:
    """Compute conversion rate as percentage. Returns None if denominator is zero."""
    if from_count <= 0:
        return None
    return round(to_count / from_count * 100, 2)


def _severity_for_gap(rate: float | None, threshold: float) -> str:
    """Determine finding severity based on how far below threshold the rate is."""
    if rate is None:
        return "low"
    gap = threshold - rate
    if gap <= 0:
        return "low"  # Above threshold — healthy
    if rate == 0:
        return "critical"
    if gap > threshold * 0.5:
        return "critical"  # More than 50% below threshold
    if gap > threshold * 0.25:
        return "high"  # More than 25% below threshold
    return "medium"


def analyze_activation_funnel(conn: sqlite3.Connection) -> list[dict]:
    """Analyze the activation funnel and generate findings with auto-fix prescriptions.

    For each funnel stage transition:
    1. Query DB to calculate actual conversion rate (7d and 30d windows)
    2. Compare against threshold
    3. If below threshold, generate finding with severity and auto-fix prescription
    4. Execute auto-fix using existing systems (experiment proposer, email, feature flags)

    Returns a list of finding dicts compatible with the intelligence engine.
    """
    findings = []

    # Compute counts for both windows
    counts_7d = _compute_stage_counts(conn, '-7 days')
    counts_30d = _compute_stage_counts(conn, '-30 days')

    # Check if we have enough data to analyze
    total_signups_30d = counts_30d.get("signup", 0)
    total_visits_30d = counts_30d.get("visit", 0)

    if total_signups_30d == 0 and total_visits_30d == 0:
        findings.append(_finding(
            "activation_funnel", "low",
            "Activation funnel: no data yet",
            "No signups or tracked visits in the last 30 days. The funnel "
            "analyzer is ready and will activate when traffic and signups arrive. "
            "Ensure visit tracking (pi_funnel_events) and user registration are "
            "instrumented.",
            "Instrument visit tracking via pi_funnel_events or Plausible analytics. "
            "The funnel analyzer will produce actionable findings once data flows.",
            "Verify that visit events are being recorded in pi_funnel_events and "
            "that user registration populates the user table.",
            "Funnel analysis requires upstream data.",
            ["mandarin/web/landing_routes.py", "mandarin/web/auth_routes.py"],
        ))
        return findings

    # Analyze each stage transition
    auto_fix_results = []

    for stage in FUNNEL_STAGES:
        from_stage = stage["from"]
        to_stage = stage["to"]
        threshold = stage["threshold"]
        action_name = stage["action"]
        description = stage["description"]

        from_count_7d = counts_7d.get(from_stage, 0)
        to_count_7d = counts_7d.get(to_stage, 0)
        from_count_30d = counts_30d.get(from_stage, 0)
        to_count_30d = counts_30d.get(to_stage, 0)

        rate_7d = _compute_conversion_rate(from_count_7d, to_count_7d)
        rate_30d = _compute_conversion_rate(from_count_30d, to_count_30d)

        # Use 30d rate as primary (more stable), 7d as trend signal
        primary_rate = rate_30d if rate_30d is not None else rate_7d

        if primary_rate is None:
            # Not enough data for this stage
            continue

        if primary_rate >= threshold:
            # Healthy — no finding needed
            continue

        # Below threshold — generate finding and attempt auto-fix
        severity = _severity_for_gap(primary_rate, threshold)

        rate_7d_str = f"{rate_7d:.1f}%" if rate_7d is not None else "N/A"
        rate_30d_str = f"{rate_30d:.1f}%" if rate_30d is not None else "N/A"

        analysis = (
            f"{description}: {rate_7d_str} (7d), {rate_30d_str} (30d). "
            f"Threshold: {threshold}%. "
            f"Counts 7d: {from_stage}={from_count_7d}, {to_stage}={to_count_7d}. "
            f"Counts 30d: {from_stage}={from_count_30d}, {to_stage}={to_count_30d}."
        )

        # Execute auto-fix
        fix_fn = _FIX_ACTIONS.get(action_name)
        fix_result = None
        if fix_fn:
            try:
                fix_result = fix_fn(conn, rate_7d or 0.0, rate_30d or 0.0)
                auto_fix_results.append({
                    "stage": f"{from_stage}_to_{to_stage}",
                    **fix_result,
                })
            except Exception as e:
                logger.warning("Auto-fix %s failed: %s", action_name, e)
                fix_result = {"action": action_name, "status": "error", "detail": str(e)}

        fix_detail = ""
        if fix_result:
            fix_detail = f" Auto-fix: {fix_result.get('detail', action_name)}"

        recommendation = (
            f"Conversion from {from_stage} to {to_stage} is below the "
            f"{threshold}% threshold.{fix_detail}"
        )

        findings.append(_finding(
            "activation_funnel", severity,
            f"Funnel break: {description} at {rate_30d_str} (threshold {threshold}%)",
            analysis,
            recommendation,
            f"Analyze {from_stage}-to-{to_stage} conversion and apply fix: {action_name}.",
            f"Broken funnel stage limits all downstream conversion.",
            _files_for_stage(from_stage, to_stage),
        ))

    # Store funnel snapshot for trending
    _save_funnel_snapshot(conn, counts_7d, counts_30d)

    return findings


def _files_for_stage(from_stage: str, to_stage: str) -> list[str]:
    """Return relevant file paths for a funnel stage transition."""
    stage_files = {
        "visit": ["mandarin/web/landing_routes.py", "marketing/landing/index.html"],
        "signup": ["mandarin/web/auth_routes.py", "mandarin/web/templates/auth/register.html"],
        "email_verified": ["mandarin/email.py", "mandarin/auth.py"],
        "first_session": ["mandarin/web/onboarding_routes.py", "mandarin/web/templates/onboarding/"],
        "session_completed": ["mandarin/web/session_routes.py", "mandarin/db/session.py"],
        "return_day2": ["mandarin/email.py", "mandarin/scheduler.py"],
        "return_day7": ["mandarin/email.py", "mandarin/scheduler.py"],
        "subscription": ["mandarin/payment.py", "mandarin/web/templates/pricing.html"],
    }
    files = set()
    files.update(stage_files.get(from_stage, []))
    files.update(stage_files.get(to_stage, []))
    return sorted(files)


def _save_funnel_snapshot(
    conn: sqlite3.Connection,
    counts_7d: dict[str, int],
    counts_30d: dict[str, int],
) -> None:
    """Save a funnel snapshot for historical trending."""
    try:
        import uuid
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Calculate key conversion rates for the snapshot table
        visit_to_signup = _compute_conversion_rate(
            counts_7d.get("visit", 0), counts_7d.get("signup", 0)
        )
        signup_to_activation = _compute_conversion_rate(
            counts_7d.get("signup", 0), counts_7d.get("first_session", 0)
        )

        # Use REPLACE to update today's snapshot if it already exists
        conn.execute("""
            INSERT OR REPLACE INTO pi_funnel_snapshots
            (id, snapshot_date, signups_7d, activations_7d,
             conversion_visitor_to_signup, conversion_signup_to_activation,
             notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            today,
            counts_7d.get("signup", 0),
            counts_7d.get("first_session", 0),
            visit_to_signup,
            signup_to_activation,
            json.dumps({
                "counts_7d": counts_7d,
                "counts_30d": counts_30d,
                "source": "funnel_analyzer",
            }),
        ))
        conn.commit()
    except Exception as e:
        logger.debug("Failed to save funnel snapshot: %s", e)


# ── Funnel summary (for admin API) ──────────────────────────────────────


def get_funnel_summary(conn: sqlite3.Connection) -> dict:
    """Compute a full funnel summary for the admin API.

    Returns stage counts, conversion rates, health status, and auto-fix
    prescriptions for both 7-day and 30-day windows.
    """
    counts_7d = _compute_stage_counts(conn, '-7 days')
    counts_30d = _compute_stage_counts(conn, '-30 days')

    stages = []
    for stage_def in FUNNEL_STAGES:
        from_stage = stage_def["from"]
        to_stage = stage_def["to"]
        threshold = stage_def["threshold"]

        from_7d = counts_7d.get(from_stage, 0)
        to_7d = counts_7d.get(to_stage, 0)
        from_30d = counts_30d.get(from_stage, 0)
        to_30d = counts_30d.get(to_stage, 0)

        rate_7d = _compute_conversion_rate(from_7d, to_7d)
        rate_30d = _compute_conversion_rate(from_30d, to_30d)
        primary_rate = rate_30d if rate_30d is not None else rate_7d

        healthy = primary_rate is not None and primary_rate >= threshold

        stages.append({
            "from": from_stage,
            "to": to_stage,
            "description": stage_def["description"],
            "threshold_pct": threshold,
            "rate_7d_pct": rate_7d,
            "rate_30d_pct": rate_30d,
            "from_count_7d": from_7d,
            "to_count_7d": to_7d,
            "from_count_30d": from_30d,
            "to_count_30d": to_30d,
            "healthy": healthy,
            "severity": _severity_for_gap(primary_rate, threshold) if not healthy else None,
            "prescribed_action": stage_def["action"] if not healthy else None,
        })

    # Overall funnel health: count of broken stages
    broken_count = sum(1 for s in stages if not s["healthy"])
    total_stages = len(stages)
    health_score = round((total_stages - broken_count) / max(1, total_stages) * 100)

    # Historical snapshots for trending
    snapshots = _safe_query_all(conn, """
        SELECT snapshot_date, signups_7d, activations_7d,
               conversion_visitor_to_signup, conversion_signup_to_activation, notes
        FROM pi_funnel_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 14
    """)

    return {
        "stages": stages,
        "counts_7d": counts_7d,
        "counts_30d": counts_30d,
        "broken_stages": broken_count,
        "total_stages": total_stages,
        "health_score": health_score,
        "snapshots": [dict(s) for s in snapshots] if snapshots else [],
    }


# ── Standalone stats function (for admin dashboard) ─────────────────────


def fetch_funnel_stats(conn: sqlite3.Connection) -> dict:
    """Standalone funnel stats for the admin dashboard API.

    Returns stage counts, conversion rates, health status, and historical
    snapshots for both 7-day and 30-day windows.  Lighter than
    get_funnel_summary — no auto-fix prescriptions, no experiment proposals.
    """
    counts_7d = _compute_stage_counts(conn, '-7 days')
    counts_30d = _compute_stage_counts(conn, '-30 days')

    stages = []
    for stage_def in FUNNEL_STAGES:
        from_stage = stage_def["from"]
        to_stage = stage_def["to"]
        threshold = stage_def["threshold"]

        from_7d = counts_7d.get(from_stage, 0)
        to_7d = counts_7d.get(to_stage, 0)
        from_30d = counts_30d.get(from_stage, 0)
        to_30d = counts_30d.get(to_stage, 0)

        rate_7d = _compute_conversion_rate(from_7d, to_7d)
        rate_30d = _compute_conversion_rate(from_30d, to_30d)
        primary_rate = rate_30d if rate_30d is not None else rate_7d
        healthy = primary_rate is not None and primary_rate >= threshold

        stages.append({
            "from": from_stage,
            "to": to_stage,
            "description": stage_def["description"],
            "threshold_pct": threshold,
            "rate_7d_pct": rate_7d,
            "rate_30d_pct": rate_30d,
            "from_count_7d": from_7d,
            "to_count_7d": to_7d,
            "from_count_30d": from_30d,
            "to_count_30d": to_30d,
            "healthy": healthy,
            "severity": _severity_for_gap(primary_rate, threshold) if not healthy else None,
        })

    broken_count = sum(1 for s in stages if not s["healthy"])
    total_stages = len(stages)
    health_score = round((total_stages - broken_count) / max(1, total_stages) * 100)

    snapshots = _safe_query_all(conn, """
        SELECT snapshot_date, signups_7d, activations_7d,
               conversion_visitor_to_signup, conversion_signup_to_activation, notes
        FROM pi_funnel_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 14
    """)

    return {
        "stages": stages,
        "counts_7d": counts_7d,
        "counts_30d": counts_30d,
        "broken_stages": broken_count,
        "total_stages": total_stages,
        "health_score": health_score,
        "snapshots": [dict(s) for s in snapshots] if snapshots else [],
    }


# ── Analyzer registration ───────────────────────────────────────────────

ANALYZERS = [
    analyze_activation_funnel,
]
