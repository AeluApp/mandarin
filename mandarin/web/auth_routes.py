"""Auth routes — login, register, logout, password reset, MFA challenge."""

import logging

from urllib.parse import urlparse

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
)
from flask_login import login_user, logout_user, login_required, current_user

from .. import db
from ..auth import create_user, authenticate, get_user_by_id, create_reset_token, reset_password, verify_email
from ..email import send_welcome, send_password_reset, send_email_verification
from ..mfa import verify_totp, verify_backup_code
from ..security import log_security_event, SecurityEvent, Severity
from ..settings import IS_PRODUCTION

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


class User:
    """Flask-Login user wrapper."""

    def __init__(self, user_dict):
        self._data = user_dict

    @property
    def id(self):
        return self._data["id"]

    @property
    def email(self):
        return self._data["email"]

    @property
    def display_name(self):
        return self._data["display_name"]

    @property
    def subscription_tier(self):
        return self._data["subscription_tier"]

    @property
    def is_admin(self):
        return self._data.get("is_admin", False)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self._data["id"])


def load_user(user_id):
    """Flask-Login user_loader callback."""
    try:
        with db.connection() as conn:
            user_dict = get_user_by_id(conn, int(user_id))
            if user_dict:
                return User(user_dict)
    except (ValueError, TypeError, OSError):
        pass
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html", email=email)

        try:
            with db.connection() as conn:
                user_dict = authenticate(conn, email, password)
                if user_dict:
                    # Check if MFA is enabled
                    mfa_row = conn.execute(
                        "SELECT totp_enabled FROM user WHERE id = ?",
                        (user_dict["id"],),
                    ).fetchone()
                    if mfa_row and mfa_row["totp_enabled"]:
                        # Store pending MFA user in session, don't login yet
                        session["pending_mfa_user_id"] = user_dict["id"]
                        session["pending_mfa_next"] = request.args.get("next")
                        return redirect(url_for("auth.mfa_verify"))

                    login_user(User(user_dict), remember=True)
                    next_page = request.args.get("next")
                    # Prevent open redirect — only allow relative URLs
                    if next_page:
                        parsed = urlparse(next_page)
                        if parsed.netloc or parsed.scheme:
                            next_page = None
                            log_security_event(conn, SecurityEvent.OPEN_REDIRECT_BLOCKED,
                                               user_id=user_dict["id"],
                                               details=f"blocked redirect to {request.args.get('next')}",
                                               severity=Severity.WARNING)
                    return redirect(next_page or url_for("index"))
                else:
                    flash("Invalid email or password.", "error")
                    return render_template("login.html", email=email)
        except (OSError, TypeError) as e:
            logger.error("Login error: %s", e)
            flash("An error occurred. Please try again.", "error")
            return render_template("login.html", email=email)

    return render_template("login.html", email="")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        display_name = (request.form.get("display_name") or "").strip()
        invite_code = (request.form.get("invite_code") or "").strip()

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

        if IS_PRODUCTION and not invite_code:
            flash("An invite code is required.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

        try:
            with db.connection() as conn:
                user_dict = create_user(conn, email, password, display_name, invite_code=invite_code if invite_code else None)
                login_user(User(user_dict), remember=True)
                # Send verification email (Item 16)
                verify_token = user_dict.pop("_verify_token", None)
                if verify_token:
                    verify_url = request.host_url.rstrip('/') + url_for('auth.verify_email_view', token=verify_token)
                    send_email_verification(email, verify_url)
                send_welcome(email, display_name)
                return redirect(url_for("index"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)
        except (OSError, TypeError) as e:
            logger.error("Register error: %s", e)
            flash("An error occurred. Please try again.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

    return render_template("register.html", email="", display_name="", invite_code="")


@auth_bp.route("/mfa-verify", methods=["GET", "POST"])
def mfa_verify():
    """MFA challenge page — verify TOTP or backup code to complete login."""
    pending_user_id = session.get("pending_mfa_user_id")
    if not pending_user_id:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if not code:
            flash("Please enter your authentication code.", "error")
            return render_template("mfa_verify.html")

        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT totp_secret, totp_backup_codes FROM user WHERE id = ?",
                    (pending_user_id,),
                ).fetchone()
                if not row or not row["totp_secret"]:
                    session.pop("pending_mfa_user_id", None)
                    return redirect(url_for("auth.login"))

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
                            (remaining, pending_user_id),
                        )
                        conn.commit()

                if verified:
                    user_dict = get_user_by_id(conn, pending_user_id)
                    if user_dict:
                        login_user(User(user_dict), remember=True)
                        log_security_event(conn, SecurityEvent.MFA_VERIFIED,
                                           user_id=pending_user_id)
                        next_page = session.pop("pending_mfa_next", None)
                        session.pop("pending_mfa_user_id", None)
                        if next_page:
                            parsed = urlparse(next_page)
                            if parsed.netloc or parsed.scheme:
                                next_page = None
                        return redirect(next_page or url_for("index"))

                log_security_event(conn, SecurityEvent.MFA_FAILED,
                                   user_id=pending_user_id,
                                   details="invalid code at login",
                                   severity=Severity.WARNING)
                flash("Invalid authentication code.", "error")
                return render_template("mfa_verify.html")
        except (OSError, TypeError) as e:
            logger.error("MFA verify error: %s", e)
            flash("An error occurred. Please try again.", "error")
            return render_template("mfa_verify.html")

    return render_template("mfa_verify.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    user_id = current_user.id
    try:
        with db.connection() as conn:
            log_security_event(conn, SecurityEvent.LOGOUT, user_id=user_id)
    except (OSError, TypeError):
        pass
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        if not email:
            flash("Email is required.", "error")
            return render_template("forgot_password.html", email="")

        try:
            with db.connection() as conn:
                token = create_reset_token(conn, email)
                if token:
                    reset_url = request.host_url.rstrip('/') + url_for('auth.reset_password_view', token=token)
                    send_password_reset(email, reset_url)
                # Always show same message regardless of whether email exists
                flash("If that email exists, a reset link has been sent.", "info")
        except (OSError, TypeError) as e:
            logger.error("Forgot password error: %s", e)
            flash("An error occurred. Please try again.", "error")

        return render_template("forgot_password.html", email=email)

    return render_template("forgot_password.html", email="")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_view(token):
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)

        try:
            with db.connection() as conn:
                if reset_password(conn, token, password):
                    flash("Password has been reset. Please log in.", "info")
                    return redirect(url_for("auth.login"))
                else:
                    flash("Reset link is invalid or expired.", "error")
                    return render_template("reset_password.html", token=token)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("reset_password.html", token=token)
        except (OSError, TypeError) as e:
            logger.error("Reset password error: %s", e)
            flash("An error occurred. Please try again.", "error")
            return render_template("reset_password.html", token=token)

    return render_template("reset_password.html", token=token)


@auth_bp.route("/verify-email")
def verify_email_view():
    """Verify email address via token link (Item 16)."""
    token = request.args.get("token", "")
    if not token:
        flash("Invalid verification link.", "error")
        return redirect(url_for("auth.login"))

    try:
        with db.connection() as conn:
            if verify_email(conn, token):
                flash("Email verified successfully.", "info")
            else:
                flash("Verification link is invalid or expired.", "error")
    except (OSError, TypeError) as e:
        logger.error("Email verify error: %s", e)
        flash("An error occurred. Please try again.", "error")

    return redirect(url_for("auth.login"))


@auth_bp.route("/unsubscribe")
def unsubscribe():
    """Marketing email unsubscribe via HMAC-signed link (Item 27)."""
    import hmac as _hmac
    import hashlib as _hashlib
    from ..settings import SECRET_KEY as _sk

    token = request.args.get("token", "")
    user_id_str = request.args.get("uid", "")
    if not token or not user_id_str:
        flash("Invalid unsubscribe link.", "error")
        return redirect(url_for("auth.login"))

    expected = _hmac.new(
        _sk.encode(), user_id_str.encode(), _hashlib.sha256
    ).hexdigest()[:32]
    if not _hmac.compare_digest(token, expected):
        flash("Invalid unsubscribe link.", "error")
        return redirect(url_for("auth.login"))

    try:
        with db.connection() as conn:
            conn.execute(
                "UPDATE user SET marketing_opt_out = 1 WHERE id = ?",
                (int(user_id_str),),
            )
            conn.commit()
            flash("You have been unsubscribed from marketing emails.", "info")
    except (OSError, TypeError, ValueError) as e:
        logger.error("Unsubscribe error: %s", e)
        flash("An error occurred.", "error")

    return redirect(url_for("auth.login"))
