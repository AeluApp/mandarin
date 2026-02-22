"""Security audit logging — centralized security event tracking.

Implements CIS Control 8 (Audit Log Management), NIST DE.AE (Anomalies and Events),
and ISO 27001 A.8.15 (Logging). All authentication and authorization events are
recorded to the security_audit_log table for forensic analysis and compliance.

Zero Trust principle: log every access decision, successful or not.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from enum import Enum

from flask import request as flask_request

logger = logging.getLogger(__name__)


class SecurityEvent(str, Enum):
    """Security event types for audit logging."""

    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_LOCKED = "login_locked"
    LOGOUT = "logout"
    REGISTER = "register"

    # Password events
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    PASSWORD_RESET_FAILED = "password_reset_failed"

    # Token events
    TOKEN_ISSUED = "token_issued"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REVOKED = "token_revoked"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"

    # Authorization events
    ACCESS_DENIED = "access_denied"
    ADMIN_ACCESS = "admin_access"
    SESSION_RESUMED = "session_resumed"
    SESSION_RESUME_REJECTED = "session_resume_rejected"

    # MFA events
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    MFA_VERIFIED = "mfa_verified"
    MFA_FAILED = "mfa_failed"

    # Account events
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    ACCOUNT_DEACTIVATED = "account_deactivated"
    DATA_EXPORT_REQUESTED = "data_export_requested"
    DATA_DELETION_REQUESTED = "data_deletion_requested"
    DATA_DELETION_COMPLETED = "data_deletion_completed"

    # Security anomalies
    CSRF_VIOLATION = "csrf_violation"
    RATE_LIMIT_HIT = "rate_limit_hit"
    OPEN_REDIRECT_BLOCKED = "open_redirect_blocked"


class Severity(str, Enum):
    """Log severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _send_critical_alert(event_type: str, user_id: int | None, details: str | None) -> None:
    """Send critical security alert via webhook and email (Item 9)."""
    import os
    alert_msg = f"CRITICAL: {event_type} user={user_id} details={details}"

    # POST to webhook if configured
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook_url:
        try:
            import requests
            requests.post(webhook_url, json={
                "text": alert_msg,
                "severity": "CRITICAL",
                "event_type": event_type,
                "user_id": user_id,
            }, timeout=5)
        except Exception as e:
            logger.error("Alert webhook failed: %s", e)

    # Send admin email
    admin_email = os.environ.get("ADMIN_EMAIL")
    if admin_email:
        try:
            from .email import send_alert
            send_alert(admin_email, f"[CRITICAL] {event_type}", alert_msg)
        except Exception as e:
            logger.error("Alert email failed: %s", e)


def _redact_pii(text: str) -> str:
    """Redact PII from log details for structured log output.

    - Email: j***@example.com
    - IP: last octet masked (192.168.1.xxx)
    """
    import re
    if not text:
        return text
    # Redact emails
    text = re.sub(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        lambda m: m.group(0)[0] + '***@' + m.group(0).split('@')[1],
        text,
    )
    # Redact IP addresses (mask last octet)
    text = re.sub(
        r'\b(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\b',
        r'\1.xxx',
        text,
    )
    return text


def log_security_event(
    conn: sqlite3.Connection,
    event_type: SecurityEvent | str,
    user_id: int | None = None,
    details: str | None = None,
    severity: Severity | str = Severity.INFO,
) -> None:
    """Record a security event to the audit log.

    Captures IP address and user agent from the current Flask request context.
    Falls back gracefully if called outside a request context.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Get request context safely
    ip_address = None
    user_agent = None
    request_path = None
    try:
        ip_address = flask_request.remote_addr
        user_agent = (flask_request.headers.get("User-Agent") or "")[:512]
        request_path = f"{flask_request.method} {flask_request.path}"
    except RuntimeError:
        pass  # Outside request context

    # Append request path to details for forensic completeness
    if request_path and details:
        details = f"{details} [{request_path}]"
    elif request_path:
        details = request_path

    event_str = event_type.value if isinstance(event_type, SecurityEvent) else str(event_type)
    severity_str = severity.value if isinstance(severity, Severity) else str(severity)

    try:
        conn.execute(
            """INSERT INTO security_audit_log
               (timestamp, event_type, user_id, ip_address, user_agent, details, severity)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now, event_str, user_id, ip_address, user_agent, details, severity_str),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # Table might not exist yet (pre-migration) — log to stderr
        logger.warning("security_audit_log table not available, event: %s user=%s", event_str, user_id)

    # Also emit structured log for SIEM integration (PII-redacted for log output)
    redacted_details = _redact_pii(details) if details else details
    redacted_ip = _redact_pii(ip_address) if ip_address else ip_address
    logger.info(
        "SECURITY_EVENT type=%s user_id=%s ip=%s severity=%s details=%s",
        event_str, user_id, redacted_ip, severity_str, redacted_details,
    )

    # Item 9: Critical event alerting
    if severity_str == "CRITICAL":
        _send_critical_alert(event_str, user_id, details)
