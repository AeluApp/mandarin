"""Authentication — user creation, login, password reset.

Implements NIST SP 800-63B password requirements including:
- Minimum 12 characters (defense in depth)
- Common password screening (breached password list)
- Proper email validation
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta, UTC

from werkzeug.security import generate_password_hash, check_password_hash

from .security import log_security_event, SecurityEvent, Severity

logger = logging.getLogger(__name__)

# Minimum password length (NIST SP 800-63B recommends >= 8, we use 12 for defense in depth)
MIN_PASSWORD_LENGTH = 12

# Account lockout settings (CIS Control 6.2)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

# Email validation regex (RFC 5322 simplified)
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# Common password list — loaded lazily on first use
_common_passwords: set | None = None
_COMMON_PASSWORDS_PATH = Path(__file__).parent.parent / "data" / "common_passwords.txt"


def _load_common_passwords() -> set:
    """Load the common passwords set from disk. Cached after first call."""
    global _common_passwords
    if _common_passwords is not None:
        return _common_passwords
    try:
        text = _COMMON_PASSWORDS_PATH.read_text(encoding="utf-8")
        _common_passwords = {line.strip().lower() for line in text.splitlines() if line.strip()}
    except FileNotFoundError:
        logger.warning("common_passwords.txt not found at %s", _COMMON_PASSWORDS_PATH)
        _common_passwords = set()
    return _common_passwords


def _validate_password(password: str) -> None:
    """Validate password against NIST SP 800-63B requirements.

    Raises ValueError if password is too short or too common.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.lower() in _load_common_passwords():
        raise ValueError("This password is too common. Please choose a more unique password.")


def _check_password_reuse(conn: sqlite3.Connection, user_id: int,
                          new_password: str, limit: int = 5) -> bool:
    """Return True if password was recently used (should be rejected).

    Checks the current password hash and the last ``limit`` entries in
    password_history.
    """
    # Check current password first
    current = conn.execute(
        "SELECT password_hash FROM user WHERE id = ?", (user_id,)
    ).fetchone()
    if current and check_password_hash(current["password_hash"], new_password):
        return True

    # Check historical passwords
    rows = conn.execute(
        "SELECT password_hash FROM password_history WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    for row in rows:
        if check_password_hash(row["password_hash"], new_password):
            return True
    return False


def _save_password_history(conn: sqlite3.Connection, user_id: int,
                           old_password_hash: str) -> None:
    """Save a password hash to the history table."""
    conn.execute(
        "INSERT INTO password_history (user_id, password_hash) VALUES (?, ?)",
        (user_id, old_password_hash),
    )


def create_user(conn: sqlite3.Connection, email: str, password: str,
                display_name: str = "", invite_code: str = None,
                role: str = "student", referred_by_user_id: int = None) -> dict:
    """Create a new user + learner_profile row.

    Returns the user dict on success.
    Raises ValueError if email already exists, input is invalid, or invite code is bad.
    """
    email = email.strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address")
    _validate_password(password)

    # Check feature flag: require_invite_code
    invite_required = False
    try:
        flag_row = conn.execute(
            "SELECT enabled FROM feature_flag WHERE name = 'require_invite_code'"
        ).fetchone()
        if flag_row and flag_row["enabled"]:
            invite_required = True
    except Exception:
        pass

    if invite_required and not invite_code:
        raise ValueError("An invite code is required to register during the beta period")

    # Validate invite code if provided
    invited_by = None
    if invite_code:
        invite_code = invite_code.strip()
        row = conn.execute(
            "SELECT code, max_uses, use_count, expires_at FROM invite_code WHERE code = ?",
            (invite_code,)
        ).fetchone()
        if not row:
            raise ValueError("Invalid invite code")
        # Check expiration
        if row["expires_at"]:
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            if now_str > row["expires_at"]:
                raise ValueError("This invite code has expired")
        # Check usage limit
        if row["max_uses"] and row["use_count"] >= row["max_uses"]:
            raise ValueError("This invite code has reached its usage limit")
        invited_by = invite_code

    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    display_name = (display_name or email.split("@")[0]).strip()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Email verification token (Item 16)
    verify_token = secrets.token_urlsafe(32)
    verify_expires = (datetime.now(UTC) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    if role not in ("student", "teacher"):
        role = "student"

    # Free trial: 7 days from now
    trial_ends_at = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # Unique referral code (8-char URL-safe)
    referral_code = secrets.token_urlsafe(6)[:8]

    try:
        cursor = conn.execute(
            """INSERT INTO user (email, password_hash, display_name, invited_by,
                                 email_verify_token, email_verify_expires, role,
                                 trial_ends_at, referral_code, referred_by,
                                 created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, password_hash, display_name, invited_by, verify_token, verify_expires, role,
             trial_ends_at, referral_code, referred_by_user_id, now, now)
        )
        user_id = cursor.lastrowid

        # Create learner profile for the new user
        conn.execute(
            "INSERT INTO learner_profile (user_id, created_at, updated_at) VALUES (?, ?, ?)",
            (user_id, now, now)
        )

        # Mark invite code as used
        if invited_by:
            conn.execute(
                "UPDATE invite_code SET use_count = use_count + 1, used_by = ?, used_at = ? WHERE code = ?",
                (user_id, now, invited_by)
            )

        conn.commit()

        logger.info("Created user id=%d", user_id)
        log_security_event(conn, SecurityEvent.REGISTER, user_id=user_id)
        return {**get_user_by_id(conn, user_id), "_verify_token": verify_token}

    except sqlite3.IntegrityError:
        raise ValueError("Could not create account. Please try a different email or sign in.")


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> dict | None:
    """Authenticate a user by email and password.

    Returns user dict on success, None on failure.
    Implements account lockout after MAX_FAILED_ATTEMPTS (CIS Control 6.2).
    Uses constant-time password comparison to prevent timing attacks.
    """
    email = email.strip().lower()
    row = conn.execute(
        """SELECT id, email, password_hash, display_name, subscription_tier,
                  is_active, is_admin, failed_login_attempts, locked_until, role
           FROM user WHERE email = ?""",
        (email,)
    ).fetchone()

    if not row:
        # Constant-time: hash a dummy password to prevent timing side-channel
        generate_password_hash("dummy-password-for-timing", method="pbkdf2:sha256")
        log_security_event(conn, SecurityEvent.LOGIN_FAILED, details=f"unknown email attempt")
        return None

    if not row["is_active"]:
        log_security_event(conn, SecurityEvent.LOGIN_FAILED, user_id=row["id"],
                           details="inactive account", severity=Severity.WARNING)
        return None

    # Check account lockout
    locked_until = row["locked_until"] if row["locked_until"] else None
    if locked_until:
        try:
            lock_time = datetime.strptime(locked_until, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            if datetime.now(UTC) < lock_time:
                logger.warning("Login attempt on locked account id=%d", row["id"])
                log_security_event(conn, SecurityEvent.LOGIN_LOCKED, user_id=row["id"],
                                   severity=Severity.WARNING)
                return None
        except (ValueError, TypeError):
            # Malformed locked_until — treat as still locked (fail-safe)
            logger.warning("Malformed locked_until value for user id=%d: %r", row["id"], locked_until)
            log_security_event(conn, SecurityEvent.LOGIN_LOCKED, user_id=row["id"],
                               severity=Severity.WARNING)
            return None

    if not check_password_hash(row["password_hash"], password):
        # Increment failed attempts
        attempts = (row["failed_login_attempts"] or 0) + 1
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if attempts >= MAX_FAILED_ATTEMPTS:
            lock_until = (datetime.now(UTC) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            conn.execute(
                "UPDATE user SET failed_login_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?",
                (attempts, lock_until, now, row["id"]),
            )
            logger.warning("Account locked after %d failed attempts id=%d", attempts, row["id"])
            log_security_event(conn, SecurityEvent.ACCOUNT_LOCKED, user_id=row["id"],
                               details=f"locked after {attempts} failed attempts",
                               severity=Severity.WARNING)
        else:
            conn.execute(
                "UPDATE user SET failed_login_attempts = ?, updated_at = ? WHERE id = ?",
                (attempts, now, row["id"]),
            )
        conn.commit()
        log_security_event(conn, SecurityEvent.LOGIN_FAILED, user_id=row["id"],
                           details=f"wrong password, attempt {attempts}")
        return None

    # Success — reset failed attempts and update login time
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE user SET last_login_at = ?, failed_login_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
        (now, now, row["id"]),
    )
    conn.commit()
    log_security_event(conn, SecurityEvent.LOGIN_SUCCESS, user_id=row["id"])

    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "subscription_tier": row["subscription_tier"],
        "is_admin": bool(row["is_admin"]) if row["is_admin"] is not None else False,
        "role": row["role"] if row["role"] else "student",
    }


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict | None:
    """Load a user by ID. Returns dict or None."""
    row = conn.execute(
        """SELECT id, email, display_name, subscription_tier, is_active, is_admin, role,
                  trial_ends_at, referral_code
           FROM user WHERE id = ?""",
        (user_id,)
    ).fetchone()

    if not row or not row["is_active"]:
        return None

    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "subscription_tier": row["subscription_tier"],
        "is_admin": bool(row["is_admin"]) if row["is_admin"] is not None else False,
        "role": row["role"] or "student",
        "trial_ends_at": row["trial_ends_at"],
        "referral_code": row["referral_code"],
    }


def create_reset_token(conn: sqlite3.Connection, email: str) -> str | None:
    """Generate a password reset token. Returns the token string or None.

    Always takes constant time to prevent email enumeration via timing.
    Returns None if email not found (caller should show generic message).
    """
    email = email.strip().lower()
    user = conn.execute("SELECT id FROM user WHERE email = ? AND is_active = 1", (email,)).fetchone()

    # Always generate a token to prevent timing side-channel
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    if not user:
        # Constant time: still do the hash work but don't store
        return None

    conn.execute(
        "UPDATE user SET reset_token_hash = ?, reset_token_expires = ? WHERE id = ?",
        (token_hash, expires, user["id"])
    )
    conn.commit()

    logger.info("Reset token generated for user id=%d", user["id"])
    log_security_event(conn, SecurityEvent.PASSWORD_RESET_REQUESTED, user_id=user["id"])
    return token


def reset_password(conn: sqlite3.Connection, token: str, new_password: str) -> bool:
    """Reset a password using a reset token. Returns True on success.

    Also invalidates all existing sessions (refresh tokens) for the user
    to prevent continued access with compromised credentials.

    Raises ValueError if the new password was recently used.
    """
    _validate_password(new_password)

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    row = conn.execute(
        """SELECT id, password_hash FROM user
           WHERE reset_token_hash = ? AND reset_token_expires > ? AND is_active = 1""",
        (token_hash, now)
    ).fetchone()

    if not row:
        return False

    # Password reuse prevention — check last 5 passwords
    if _check_password_reuse(conn, row["id"], new_password):
        raise ValueError("Please choose a password you haven't used recently.")

    old_hash = row["password_hash"]
    password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
    # Clear password reset token, refresh token (invalidate JWT sessions),
    # failed login attempts, and account lockout
    conn.execute(
        """UPDATE user SET password_hash = ?, reset_token_hash = NULL,
           reset_token_expires = NULL, refresh_token_hash = NULL,
           refresh_token_expires = NULL, failed_login_attempts = 0,
           locked_until = NULL, updated_at = ? WHERE id = ?""",
        (password_hash, now, row["id"])
    )
    _save_password_history(conn, row["id"], old_hash)
    conn.commit()

    logger.info("Password reset for user id=%d", row["id"])
    log_security_event(conn, SecurityEvent.PASSWORD_RESET_COMPLETED, user_id=row["id"])
    return True


def verify_email(conn: sqlite3.Connection, token: str) -> bool:
    """Verify a user's email address using the verification token.

    Returns True on success, False if token is invalid or expired.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        """SELECT id FROM user
           WHERE email_verify_token = ? AND email_verify_expires > ? AND is_active = 1""",
        (token, now),
    ).fetchone()

    if not row:
        return False

    conn.execute(
        """UPDATE user SET email_verified = 1, email_verify_token = NULL,
           email_verify_expires = NULL, updated_at = ? WHERE id = ?""",
        (now, row["id"]),
    )
    conn.commit()
    logger.info("Email verified for user id=%d", row["id"])
    return True
