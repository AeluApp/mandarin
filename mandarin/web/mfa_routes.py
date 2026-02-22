"""MFA routes — TOTP setup, verification, disable."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..mfa import (
    generate_totp_secret,
    get_provisioning_uri,
    verify_totp,
    generate_backup_codes,
    hash_backup_codes,
    verify_backup_code,
)
from ..security import log_security_event, SecurityEvent, Severity

logger = logging.getLogger(__name__)

mfa_bp = Blueprint("mfa", __name__, url_prefix="/api/mfa")


@mfa_bp.before_request
@login_required
def require_auth():
    pass


@mfa_bp.route("/status")
def mfa_status():
    """Return whether MFA is enabled for the current user."""
    with db.connection() as conn:
        row = conn.execute(
            "SELECT totp_enabled FROM user WHERE id = ?", (current_user.id,)
        ).fetchone()
        enabled = bool(row["totp_enabled"]) if row and row["totp_enabled"] else False
    return jsonify({"enabled": enabled})


@mfa_bp.route("/setup", methods=["POST"])
def mfa_setup():
    """Generate a TOTP secret and backup codes for MFA enrollment.

    The user must call /verify-setup with a valid TOTP code before MFA is activated.
    """
    with db.connection() as conn:
        # Check if already enabled
        row = conn.execute(
            "SELECT totp_enabled FROM user WHERE id = ?", (current_user.id,)
        ).fetchone()
        if row and row["totp_enabled"]:
            return jsonify({"error": "MFA is already enabled"}), 400

        secret = generate_totp_secret()
        uri = get_provisioning_uri(secret, current_user.email)
        backup_codes = generate_backup_codes()
        hashed = hash_backup_codes(backup_codes)

        # Store secret and backup codes (not yet enabled)
        conn.execute(
            "UPDATE user SET totp_secret = ?, totp_backup_codes = ? WHERE id = ?",
            (secret, hashed, current_user.id),
        )
        conn.commit()

    return jsonify({
        "secret": secret,
        "provisioning_uri": uri,
        "backup_codes": backup_codes,
    })


@mfa_bp.route("/verify-setup", methods=["POST"])
def mfa_verify_setup():
    """Verify a TOTP code to activate MFA on the account."""
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "TOTP code is required"}), 400

    with db.connection() as conn:
        row = conn.execute(
            "SELECT totp_secret, totp_enabled FROM user WHERE id = ?",
            (current_user.id,),
        ).fetchone()

        if not row or not row["totp_secret"]:
            return jsonify({"error": "Call /api/mfa/setup first"}), 400
        if row["totp_enabled"]:
            return jsonify({"error": "MFA is already enabled"}), 400

        if not verify_totp(row["totp_secret"], code):
            log_security_event(
                conn, SecurityEvent.MFA_FAILED, user_id=current_user.id,
                details="verify-setup failed", severity=Severity.WARNING,
            )
            return jsonify({"error": "Invalid TOTP code"}), 400

        conn.execute(
            "UPDATE user SET totp_enabled = 1 WHERE id = ?", (current_user.id,)
        )
        conn.commit()
        log_security_event(
            conn, SecurityEvent.MFA_ENABLED, user_id=current_user.id,
        )

    return jsonify({"enabled": True})


@mfa_bp.route("/disable", methods=["POST"])
def mfa_disable():
    """Disable MFA after verifying a TOTP code."""
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "TOTP code is required"}), 400

    with db.connection() as conn:
        row = conn.execute(
            "SELECT totp_secret, totp_enabled FROM user WHERE id = ?",
            (current_user.id,),
        ).fetchone()

        if not row or not row["totp_enabled"]:
            return jsonify({"error": "MFA is not enabled"}), 400

        if not verify_totp(row["totp_secret"], code):
            log_security_event(
                conn, SecurityEvent.MFA_FAILED, user_id=current_user.id,
                details="disable attempt failed", severity=Severity.WARNING,
            )
            return jsonify({"error": "Invalid TOTP code"}), 400

        conn.execute(
            """UPDATE user SET totp_enabled = 0, totp_secret = NULL,
               totp_backup_codes = NULL WHERE id = ?""",
            (current_user.id,),
        )
        conn.commit()
        log_security_event(
            conn, SecurityEvent.MFA_DISABLED, user_id=current_user.id,
        )

    return jsonify({"enabled": False})
