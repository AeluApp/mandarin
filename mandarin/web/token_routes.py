"""Token-based auth routes — JWT access + refresh tokens for mobile clients."""

from __future__ import annotations

import hashlib
import logging

from flask import Blueprint, request, jsonify
from flask_login import current_user

from .. import db
from ..auth import authenticate, get_user_by_id
from ..jwt_auth import (
    create_access_token,
    create_refresh_token,
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
)
from ..mfa import verify_totp, verify_backup_code
from ..security import log_security_event, SecurityEvent, Severity
from ..settings import JWT_ACCESS_EXPIRY_HOURS
from .api_errors import (
    api_error,
    api_error_handler,
    AUTH_CREDENTIALS_INVALID,
    AUTH_REFRESH_INVALID,
    AUTH_REQUIRED,
    VALIDATION_ERROR,
)

logger = logging.getLogger(__name__)

token_bp = Blueprint("token", __name__, url_prefix="/api/auth")


def _hash_token(token: str) -> str:
    """Return SHA-256 hex digest of a token string."""
    return hashlib.sha256(token.encode()).hexdigest()


@token_bp.route("/token", methods=["POST"])
@api_error_handler("Token obtain")
def obtain_token():
    """Exchange email + password for access + refresh tokens.

    POST /api/auth/token
    Body: {"email": "...", "password": "..."}
    Returns: {"access_token": "...", "refresh_token": "...", "expires_in": N, "user": {...}}
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not email or not password:
        return api_error(VALIDATION_ERROR, "Email and password are required.")

    try:
        with db.connection() as conn:
            user_dict = authenticate(conn, email, password)
            if not user_dict:
                return api_error(AUTH_CREDENTIALS_INVALID, "Invalid email or password.", 401)

            user_id = user_dict["id"]

            # Check if MFA is enabled
            mfa_row = conn.execute(
                "SELECT totp_enabled FROM user WHERE id = ?", (user_id,)
            ).fetchone()
            if mfa_row and mfa_row["totp_enabled"]:
                # Issue short-lived MFA token instead of full access
                import secrets
                mfa_token = secrets.token_urlsafe(32)
                token_hash = _hash_token(mfa_token)
                conn.execute(
                    "INSERT INTO mfa_challenge (user_id, token_hash, expires_at) VALUES (?, ?, datetime('now', '+5 minutes'))",
                    (user_id, token_hash),
                )
                # Clean expired challenges
                conn.execute("DELETE FROM mfa_challenge WHERE expires_at < datetime('now')")
                conn.commit()
                return jsonify({"mfa_required": True, "mfa_token": mfa_token})

            access_token = create_access_token(user_id)
            raw_refresh, refresh_hash = create_refresh_token()
            store_refresh_token(conn, user_id, refresh_hash)
            log_security_event(conn, SecurityEvent.TOKEN_ISSUED, user_id=user_id)

            return jsonify({
                "access_token": access_token,
                "refresh_token": raw_refresh,
                "expires_in": JWT_ACCESS_EXPIRY_HOURS * 3600,
                "user": {
                    "id": user_id,
                    "email": user_dict["email"],
                    "display_name": user_dict.get("display_name", ""),
                    "subscription_tier": user_dict.get("subscription_tier", "free"),
                },
            })
    except (ValueError, TypeError, OSError) as e:
        logger.error("token obtain error: %s", e)
        return api_error(AUTH_CREDENTIALS_INVALID, "Invalid email or password.", 401)


@token_bp.route("/token/mfa", methods=["POST"])
@api_error_handler("Token MFA verify")
def mfa_token():
    """Complete MFA challenge for JWT flow.

    POST /api/auth/token/mfa
    Body: {"mfa_token": "...", "code": "..."}
    Returns: full access + refresh tokens on success.
    """
    data = request.get_json(silent=True) or {}
    mfa_token_str = data.get("mfa_token") or ""
    code = (data.get("code") or "").strip()

    if not mfa_token_str or not code:
        return api_error(VALIDATION_ERROR, "mfa_token and code are required.")

    try:
        with db.connection() as conn:
            token_hash = _hash_token(mfa_token_str)
            entry = conn.execute(
                "SELECT user_id, expires_at FROM mfa_challenge WHERE token_hash = ? AND expires_at > datetime('now')",
                (token_hash,),
            ).fetchone()
            if not entry:
                # Clean up expired row if it existed
                conn.execute("DELETE FROM mfa_challenge WHERE token_hash = ?", (token_hash,))
                conn.commit()
                return api_error(AUTH_CREDENTIALS_INVALID, "MFA token expired or invalid.", 401)

            user_id = entry["user_id"]
            row = conn.execute(
                "SELECT totp_secret, totp_backup_codes FROM user WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row or not row["totp_secret"]:
                return api_error(AUTH_CREDENTIALS_INVALID, "MFA not configured.", 401)

            # Try TOTP first, then backup code
            if verify_totp(row["totp_secret"], code):
                verified = True
            else:
                verified, remaining = verify_backup_code(
                    row["totp_backup_codes"] or "[]", code
                )
                if verified:
                    conn.execute(
                        "UPDATE user SET totp_backup_codes = ? WHERE id = ?",
                        (remaining, user_id),
                    )
                    conn.commit()

            if not verified:
                log_security_event(conn, SecurityEvent.MFA_FAILED, user_id=user_id,
                                   details="JWT MFA verification failed",
                                   severity=Severity.WARNING)
                return api_error(AUTH_CREDENTIALS_INVALID, "Invalid MFA code.", 401)

            # MFA passed — consume the challenge token
            conn.execute("DELETE FROM mfa_challenge WHERE token_hash = ?", (token_hash,))
            access_token = create_access_token(user_id)
            raw_refresh, refresh_hash = create_refresh_token()
            store_refresh_token(conn, user_id, refresh_hash)

            user_dict = get_user_by_id(conn, user_id) or {}
            log_security_event(conn, SecurityEvent.MFA_VERIFIED, user_id=user_id)
            log_security_event(conn, SecurityEvent.TOKEN_ISSUED, user_id=user_id)

            return jsonify({
                "access_token": access_token,
                "refresh_token": raw_refresh,
                "expires_in": JWT_ACCESS_EXPIRY_HOURS * 3600,
                "user": {
                    "id": user_id,
                    "email": user_dict.get("email", ""),
                    "display_name": user_dict.get("display_name", ""),
                    "subscription_tier": user_dict.get("subscription_tier", "free"),
                },
            })
    except (ValueError, TypeError, OSError) as e:
        logger.error("MFA token verify error: %s", e)
        return api_error(AUTH_CREDENTIALS_INVALID, "MFA verification failed.", 401)


@token_bp.route("/token/refresh", methods=["POST"])
@api_error_handler("Token refresh")
def refresh_token():
    """Exchange a refresh token for a new access token.

    POST /api/auth/token/refresh
    Body: {"refresh_token": "..."}
    Returns: {"access_token": "...", "expires_in": N}
    """
    data = request.get_json(silent=True) or {}
    raw_token = data.get("refresh_token") or ""

    if not raw_token:
        return api_error(VALIDATION_ERROR, "refresh_token is required.")

    try:
        with db.connection() as conn:
            user_id = validate_refresh_token(conn, raw_token)
            if user_id is None:
                return api_error(AUTH_REFRESH_INVALID, "Invalid or expired refresh token.", 401)

            access_token = create_access_token(user_id)
            log_security_event(conn, SecurityEvent.TOKEN_REFRESHED, user_id=user_id)
            return jsonify({
                "access_token": access_token,
                "expires_in": JWT_ACCESS_EXPIRY_HOURS * 3600,
            })
    except (ValueError, TypeError, OSError) as e:
        logger.error("token refresh error: %s", e)
        return api_error(AUTH_REFRESH_INVALID, "Token refresh failed.", 401)


@token_bp.route("/token/revoke", methods=["POST"])
@api_error_handler("Token revoke")
def revoke_token():
    """Revoke the current user's refresh token (logout).

    POST /api/auth/token/revoke
    Requires: Bearer token in Authorization header
    """
    if not current_user.is_authenticated:
        return api_error(AUTH_REQUIRED, "Authentication required.", 401)

    try:
        with db.connection() as conn:
            revoke_refresh_token(conn, current_user.id)
            log_security_event(conn, SecurityEvent.LOGOUT, user_id=current_user.id)
            log_security_event(conn, SecurityEvent.TOKEN_REVOKED, user_id=current_user.id)
            return jsonify({"status": "ok"})
    except (ValueError, TypeError, OSError) as e:
        logger.error("token revoke error: %s", e)
        return api_error(AUTH_REQUIRED, "Revoke failed.", 500)
