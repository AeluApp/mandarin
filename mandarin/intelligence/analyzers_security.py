"""Security posture analyzers — MFA adoption, scan freshness, audit log anomalies."""

import logging
import sqlite3

from ._base import _finding, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Check 1: MFA adoption for admin users ───────────────────────────

def check_mfa_adoption(conn):
    """Flag admin users who have not enabled TOTP multi-factor authentication."""
    findings = []
    try:
        admins_without_mfa = _safe_query_all(conn,
            "SELECT id, email FROM user "
            "WHERE is_admin = 1 AND (totp_enabled = 0 OR totp_enabled IS NULL)")

        if not admins_without_mfa:
            return findings  # All admins have MFA — nothing to report

        count = len(admins_without_mfa)
        emails = ", ".join(
            (row["email"] if isinstance(row, dict) else row[1])
            for row in admins_without_mfa[:5]
        )
        findings.append(_finding(
            "security", "critical",
            f"{count} admin user(s) without MFA enabled",
            f"Admin accounts without TOTP multi-factor authentication: "
            f"{emails}. Admin accounts are high-value targets — a "
            f"compromised admin credential without MFA gives full system "
            f"access.",
            "Enable TOTP MFA for all admin accounts immediately. Consider "
            "enforcing MFA as a requirement for admin role assignment.",
            "Query user WHERE is_admin=1 AND totp_enabled=0. For each, "
            "generate a TOTP enrollment prompt and notify the admin.",
            "Admin account security posture",
            ["mandarin/security.py", "mandarin/auth.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 2: Security scan freshness ────────────────────────────────

def check_security_scan_freshness(conn):
    """Flag when the most recent security scan is older than 7 days or missing."""
    findings = []
    try:
        latest = _safe_scalar(conn,
            "SELECT MAX(julianday('now') - julianday(created_at)) "
            "FROM security_scan_finding",
            default=None)

        if latest is None:
            findings.append(_finding(
                "security", "high",
                "No security scan results found",
                "The security_scan_finding table contains no entries. "
                "Either scans have never run or results have been purged. "
                "Without regular scanning, vulnerabilities accumulate "
                "undetected.",
                "Configure and run a security scan immediately. Ensure "
                "scans are scheduled at least weekly.",
                "Check security_scan_finding table. If empty, trigger a "
                "scan and verify the scan pipeline is healthy.",
                "Vulnerability detection coverage",
                ["mandarin/security.py"],
            ))
        elif latest > 7:
            findings.append(_finding(
                "security", "high",
                f"Security scan is {latest:.0f} days stale (threshold: 7 days)",
                f"The most recent security scan finding is {latest:.0f} days "
                f"old. Scans should run at least weekly to catch new "
                f"vulnerabilities promptly.",
                "Run a security scan now and investigate why scheduled "
                "scans have not executed recently.",
                "Query security_scan_finding ORDER BY created_at DESC "
                "LIMIT 1. Check scan scheduler health.",
                "Vulnerability detection timeliness",
                ["mandarin/security.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: Unresolved security findings ───────────────────────────

def check_unresolved_security_findings(conn):
    """Count high/critical security scan findings that remain unresolved."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_scan_finding "
            "WHERE status != 'resolved' "
            "AND severity IN ('high', 'critical')",
            default=0)

        if count > 0:
            findings.append(_finding(
                "security", "high",
                f"{count} unresolved high/critical security finding(s)",
                f"There are {count} security scan findings with severity "
                f"'high' or 'critical' that have not been resolved. "
                f"Unresolved findings represent known attack surface that "
                f"adversaries can exploit.",
                "Triage and remediate all high/critical findings. Assign "
                "owners and set resolution deadlines (critical: 48h, "
                "high: 7 days).",
                "Query security_scan_finding WHERE status != 'resolved' "
                "AND severity IN ('high', 'critical'). Prioritize by "
                "severity and age. Propose fix for each.",
                "Known vulnerability remediation",
                ["mandarin/security.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: Rate limit violations ──────────────────────────────────

def check_rate_limit_violations(conn):
    """Flag excessive rate limit hits in the last 24 hours (possible brute force)."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_audit_log "
            "WHERE event_type = 'rate_limit_hit' "
            "AND created_at > datetime('now', '-1 day')",
            default=0)

        if count > 20:
            findings.append(_finding(
                "security", "medium",
                f"{count} rate limit violations in the last 24 hours",
                f"There were {count} rate limit hits in the past 24 hours "
                f"(threshold: 20). A high volume of rate limit violations "
                f"may indicate brute-force attacks, credential stuffing, "
                f"or automated scanning.",
                "Review the source IPs and targeted endpoints. Block "
                "repeat offenders at the WAF/firewall level. Consider "
                "implementing progressive delays or CAPTCHA.",
                "Query security_audit_log WHERE event_type='rate_limit_hit' "
                "AND created_at > datetime('now', '-1 day'). Group by IP "
                "and endpoint to identify attack patterns.",
                "Brute-force and abuse detection",
                ["mandarin/security.py", "mandarin/web/middleware.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 5: CSRF violations ────────────────────────────────────────

def check_csrf_violations(conn):
    """Flag any CSRF violations in the last 7 days."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_audit_log "
            "WHERE event_type = 'csrf_violation' "
            "AND created_at > datetime('now', '-7 days')",
            default=0)

        if count > 0:
            findings.append(_finding(
                "security", "high",
                f"{count} CSRF violation(s) in the last 7 days",
                f"Detected {count} CSRF token validation failures in the "
                f"past 7 days. CSRF violations indicate either a "
                f"misconfigured form (missing token), a client-side bug, "
                f"or an active cross-site request forgery attack.",
                "Audit all forms for proper CSRF token inclusion. Review "
                "the targeted endpoints and source referrers. If attacks "
                "are confirmed, strengthen SameSite cookie policy.",
                "Query security_audit_log WHERE event_type='csrf_violation' "
                "AND created_at > datetime('now', '-7 days'). Identify "
                "affected endpoints and determine root cause.",
                "Cross-site request forgery protection",
                ["mandarin/security.py", "mandarin/web/middleware.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 6: Failed login spike ─────────────────────────────────────

def check_failed_login_spike(conn):
    """Flag spikes in failed login attempts (possible credential attack)."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_audit_log "
            "WHERE event_type = 'login_failed' "
            "AND created_at > datetime('now', '-1 day')",
            default=0)

        if count > 50:
            findings.append(_finding(
                "security", "high",
                f"{count} failed logins in the last 24 hours (threshold: 50)",
                f"There were {count} failed login attempts in the past "
                f"24 hours. This volume strongly suggests an automated "
                f"credential stuffing or brute-force attack in progress.",
                "Immediately review source IPs and targeted accounts. "
                "Enable temporary IP blocking for repeat offenders. "
                "Notify affected users to change passwords.",
                "Query security_audit_log WHERE event_type='login_failed' "
                "AND created_at > datetime('now', '-1 day'). Group by IP "
                "and user_id to identify attack vectors.",
                "Credential attack detection",
                ["mandarin/security.py", "mandarin/auth.py"],
            ))
        elif count > 20:
            findings.append(_finding(
                "security", "medium",
                f"{count} failed logins in the last 24 hours (threshold: 20)",
                f"There were {count} failed login attempts in the past "
                f"24 hours. This elevated rate warrants monitoring — it "
                f"could indicate low-volume credential probing or users "
                f"struggling with passwords.",
                "Monitor the trend over the next 24 hours. Review whether "
                "failures are concentrated on specific accounts or IPs. "
                "Consider proactive password reset prompts for targeted "
                "accounts.",
                "Query security_audit_log WHERE event_type='login_failed' "
                "AND created_at > datetime('now', '-1 day'). Group by "
                "user_id to distinguish attacks from forgotten passwords.",
                "Credential attack early warning",
                ["mandarin/security.py", "mandarin/auth.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 7: Account lockouts ───────────────────────────────────────

def check_account_lockouts(conn):
    """Track account lockouts in the last 24 hours (informational)."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_audit_log "
            "WHERE event_type = 'account_locked' "
            "AND created_at > datetime('now', '-1 day')",
            default=0)

        if count > 0:
            findings.append(_finding(
                "security", "medium",
                f"{count} account lockout(s) in the last 24 hours",
                f"There were {count} account lockouts triggered in the "
                f"past 24 hours. Lockouts protect against brute-force "
                f"attacks but also impact legitimate users who forget "
                f"their passwords.",
                "Review locked accounts to distinguish legitimate lockouts "
                "from attack-triggered ones. Consider sending proactive "
                "password reset emails to affected users.",
                "Query security_audit_log WHERE event_type='account_locked' "
                "AND created_at > datetime('now', '-1 day'). Cross-reference "
                "with login_failed events for the same user_ids.",
                "Account lockout monitoring",
                ["mandarin/security.py", "mandarin/auth.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 8: Open redirect attempts ─────────────────────────────────

def check_open_redirect_attempts(conn):
    """Flag open redirect attempts blocked in the last 7 days."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_audit_log "
            "WHERE event_type = 'open_redirect_blocked' "
            "AND created_at > datetime('now', '-7 days')",
            default=0)

        if count > 0:
            findings.append(_finding(
                "security", "medium",
                f"{count} open redirect attempt(s) blocked in the last 7 days",
                f"Detected {count} blocked open redirect attempts in the "
                f"past 7 days. Open redirect attacks are used in phishing "
                f"campaigns to make malicious URLs appear to originate "
                f"from a trusted domain.",
                "Review the blocked redirect targets to assess threat "
                "level. Audit all redirect endpoints for proper URL "
                "validation. Consider restricting redirects to a "
                "domain allowlist.",
                "Query security_audit_log WHERE "
                "event_type='open_redirect_blocked' AND "
                "created_at > datetime('now', '-7 days'). Extract target "
                "URLs and assess phishing risk.",
                "Open redirect protection",
                ["mandarin/security.py", "mandarin/web/middleware.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 9: Admin access patterns ──────────────────────────────────

def check_admin_access_patterns(conn):
    """Flag unusual admin access patterns (high path diversity)."""
    findings = []
    try:
        distinct_paths = _safe_scalar(conn,
            "SELECT COUNT(DISTINCT details) FROM security_audit_log "
            "WHERE event_type = 'admin_access' "
            "AND created_at > datetime('now', '-1 day')",
            default=0)

        if distinct_paths > 10:
            findings.append(_finding(
                "security", "low",
                f"Admin access from {distinct_paths} distinct paths in "
                f"the last 24 hours",
                f"Admin endpoints were accessed via {distinct_paths} "
                f"distinct paths in the past 24 hours. High path "
                f"diversity may indicate automated enumeration or "
                f"reconnaissance of admin functionality.",
                "Review admin access logs to verify these are legitimate "
                "admin activities. Ensure admin routes are not publicly "
                "discoverable.",
                "Query security_audit_log WHERE event_type='admin_access' "
                "AND created_at > datetime('now', '-1 day'). Group by "
                "details and user_id to identify unusual patterns.",
                "Admin access monitoring",
                ["mandarin/security.py", "mandarin/web/admin_routes.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 10: Password reset spike ──────────────────────────────────

def check_password_reset_spike(conn):
    """Flag spikes in password reset requests (possible account takeover campaign)."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_audit_log "
            "WHERE event_type = 'password_reset_requested' "
            "AND created_at > datetime('now', '-1 day')",
            default=0)

        if count > 10:
            findings.append(_finding(
                "security", "medium",
                f"{count} password reset requests in the last 24 hours "
                f"(threshold: 10)",
                f"There were {count} password reset requests in the past "
                f"24 hours. An unusually high volume may indicate an "
                f"account takeover campaign — attackers trigger resets to "
                f"intercept tokens via email compromise or social "
                f"engineering.",
                "Review reset requests for concentration on specific "
                "accounts or from specific IPs. Verify that reset tokens "
                "expire quickly and are single-use. Consider adding "
                "rate limiting per email address.",
                "Query security_audit_log WHERE "
                "event_type='password_reset_requested' AND "
                "created_at > datetime('now', '-1 day'). Group by "
                "user_id and IP to detect targeting patterns.",
                "Account takeover detection",
                ["mandarin/security.py", "mandarin/auth.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ───────────────────────────────────────────────

ANALYZERS = [
    check_mfa_adoption,
    check_security_scan_freshness,
    check_unresolved_security_findings,
    check_rate_limit_violations,
    check_csrf_violations,
    check_failed_login_spike,
    check_account_lockouts,
    check_open_redirect_attempts,
    check_admin_access_patterns,
    check_password_reset_spike,
]
