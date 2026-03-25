"""Auth routes — login, register, logout, password reset, MFA challenge."""

import logging

from urllib.parse import urlparse

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
)
from flask_login import login_user, logout_user, login_required, current_user

from werkzeug.security import generate_password_hash

from .. import db
from ..auth import create_user, authenticate, get_user_by_id, create_reset_token, reset_password, verify_email, _validate_password, _check_password_reuse, _save_password_history
from ..email import send_welcome, send_password_reset, send_email_verification
from ..mfa import verify_totp, verify_backup_code
from ..security import log_security_event, SecurityEvent, Severity
# IS_PRODUCTION no longer needed — invite code enforcement uses feature_flag table

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _is_native_request():
    """Detect Capacitor/native iOS requests that can't handle 302 redirects."""
    # Check for native=1 query param, Capacitor user-agent, or referer from capacitor
    if request.args.get("native") == "1":
        return True
    ua = (request.headers.get("User-Agent") or "").lower()
    if "capacitor" in ua:
        return True
    referer = request.headers.get("Referer") or ""
    if "capacitor://" in referer:
        return True
    return False


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
    def role(self):
        return self._data.get("role", "student")

    @property
    def price_variant(self):
        return self._data.get("price_variant")

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
        if _is_native_request():
            return render_template("index.html")
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
                        if _is_native_request():
                            return render_template("mfa_verify.html")
                        return redirect(url_for("auth.mfa_verify"))

                    # Session fixation protection: clear session before login
                    session.clear()
                    login_user(User(user_dict), remember=True)
                    # Lifecycle: user_returned (if last login was 24+ hours ago)
                    try:
                        last_login = user_dict.get("last_login_at")
                        if last_login:
                            from datetime import datetime, timezone, timedelta
                            last_dt = datetime.strptime(last_login, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                            if datetime.now(timezone.utc) - last_dt > timedelta(hours=24):
                                from ..marketing_hooks import log_lifecycle_event
                                log_lifecycle_event("user_returned", user_id=str(user_dict["id"]), conn=conn,
                                                    days_away=round((datetime.now(timezone.utc) - last_dt).total_seconds() / 86400, 1))
                    except Exception:
                        pass
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
                    if _is_native_request():
                        return render_template("index.html")
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
        if _is_native_request():
            return render_template("index.html")
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        display_name = (request.form.get("display_name") or "").strip()[:255]
        invite_code = (request.form.get("invite_code") or "").strip()
        promo_code = (request.form.get("promo_code") or "").strip()

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

        # Check feature flag for invite code requirement
        invite_required = False
        try:
            with db.connection() as conn:
                flag_row = conn.execute(
                    "SELECT enabled FROM feature_flag WHERE name = 'require_invite_code'"
                ).fetchone()
                if flag_row and flag_row["enabled"]:
                    invite_required = True
        except (OSError, TypeError):
            pass

        if invite_required and not invite_code:
            flash("An invite code is required.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

        # Teacher registration via ?role=teacher
        role = request.args.get("role", "student")
        if role not in ("student", "teacher"):
            role = "student"

        try:
            with db.connection() as conn:
                user_dict = create_user(conn, email, password, display_name,
                                        invite_code=invite_code if invite_code else None,
                                        role=role)
                # Promo code: 加油 grants full paid access
                if promo_code == "加油":
                    try:
                        conn.execute(
                            "UPDATE user SET subscription_tier = 'paid' WHERE id = ?",
                            (user_dict["id"],)
                        )
                        conn.commit()
                        logger.info("Promo code applied: user %s upgraded to paid via 加油", user_dict["id"])
                    except Exception:
                        logger.exception("Failed to apply promo code for user %s", user_dict["id"])
                # Session fixation protection: clear session before login
                session.clear()
                login_user(User(user_dict), remember=True)
                # Send verification email (Item 16)
                verify_token = user_dict.pop("_verify_token", None)
                if verify_token:
                    verify_url = request.host_url.rstrip('/') + url_for('auth.verify_email_view', token=verify_token)
                    send_email_verification(email, verify_url)
                send_welcome(email, display_name)
                # Capture UTM parameters for attribution
                try:
                    utm_source = request.args.get("utm_source") or request.form.get("utm_source") or ""
                    utm_medium = request.args.get("utm_medium") or request.form.get("utm_medium") or ""
                    utm_campaign = request.args.get("utm_campaign") or request.form.get("utm_campaign") or ""
                    if utm_source or utm_medium or utm_campaign:
                        conn.execute(
                            "UPDATE user SET utm_source=?, utm_medium=?, utm_campaign=? WHERE id=?",
                            (utm_source or None, utm_medium or None, utm_campaign or None, user_dict["id"])
                        )
                        conn.commit()
                except Exception:
                    pass
                # Persist A/B price variant from visitor cookie (if active experiment)
                try:
                    import hashlib as _hl
                    visitor_id = request.cookies.get("aelu_vid", "")
                    if visitor_id:
                        from ..web.experiment_daemon import _MARKETING_EXPERIMENT_TEMPLATES
                        template = _MARKETING_EXPERIMENT_TEMPLATES.get("price_display_test", {})
                        assign_key = f"price_display_test:{visitor_id}"
                        vidx = int(_hl.sha256(assign_key.encode()).hexdigest()[:8], 16) % 2
                        vname = template.get("variant_a_name" if vidx == 0 else "variant_b_name", "")
                        if vname:
                            conn.execute("UPDATE user SET price_variant = ? WHERE id = ?",
                                         (vname, user_dict["id"]))
                            conn.commit()
                except Exception:
                    pass
                # Lifecycle: signup
                try:
                    from ..marketing_hooks import log_lifecycle_event
                    log_lifecycle_event("signup", user_id=str(user_dict["id"]), conn=conn)
                except Exception:
                    pass
                if _is_native_request():
                    return render_template("index.html")
                return redirect(url_for("index"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)
        except (OSError, TypeError) as e:
            logger.error("Register error: %s", e)
            flash("An error occurred. Please try again.", "error")
            return render_template("register.html", email=email, display_name=display_name, invite_code=invite_code)

    role = request.args.get("role", "student")
    return render_template("register.html", email="", display_name="", invite_code="",
                           teacher_mode=(role == "teacher"))


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
                        # Save redirect URL before clearing session
                        next_page = session.get("pending_mfa_next")
                        # Session fixation protection: clear session before login
                        session.clear()
                        login_user(User(user_dict), remember=True)
                        log_security_event(conn, SecurityEvent.MFA_VERIFIED,
                                           user_id=pending_user_id)
                        if next_page:
                            parsed = urlparse(next_page)
                            if parsed.netloc or parsed.scheme:
                                next_page = None
                        if _is_native_request():
                            return render_template("index.html")
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
    except (OSError, TypeError) as e:
        logger.warning("Failed to log LOGOUT security event for user_id=%s: %s", user_id, e)
    logout_user()
    if _is_native_request():
        return render_template("login.html", email="")
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


@auth_bp.route("/api/account/change-password", methods=["POST"])
@login_required
def change_password():
    """Change password while logged in. Requires old password verification."""
    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        return jsonify({"error": "Old password and new password are required."}), 400

    try:
        with db.connection() as conn:
            # Verify old password
            user_dict = authenticate(conn, current_user.email, old_password)
            if not user_dict:
                log_security_event(conn, SecurityEvent.PASSWORD_RESET_FAILED,
                                   user_id=current_user.id,
                                   details="change-password: wrong old password",
                                   severity=Severity.WARNING)
                return jsonify({"error": "Current password is incorrect."}), 403

            # Validate new password
            _validate_password(new_password)

            # Password reuse prevention — check last 5 passwords
            if _check_password_reuse(conn, current_user.id, new_password):
                return jsonify({"error": "Please choose a password you haven't used recently."}), 400

            # Fetch old hash before overwriting
            old_row = conn.execute(
                "SELECT password_hash FROM user WHERE id = ?",
                (current_user.id,),
            ).fetchone()
            old_hash = old_row["password_hash"] if old_row else None

            # Update hash and revoke all refresh tokens (force re-login)
            password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
            conn.execute(
                """UPDATE user SET password_hash = ?, updated_at = datetime('now'),
                   refresh_token_hash = NULL, refresh_token_expires = NULL
                   WHERE id = ?""",
                (password_hash, current_user.id),
            )
            # Save old hash to password history
            if old_hash:
                _save_password_history(conn, current_user.id, old_hash)
            conn.commit()
            log_security_event(conn, SecurityEvent.PASSWORD_CHANGED, user_id=current_user.id)

            return jsonify({"changed": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (OSError, TypeError) as e:
        logger.error("Change password error: %s", e)
        return jsonify({"error": "An error occurred. Please try again."}), 500
