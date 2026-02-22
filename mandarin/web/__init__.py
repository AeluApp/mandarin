"""Flask app factory for the Mandarin web interface."""

import hashlib
import json
import logging
import os
import sys
import time

from flask import Flask, jsonify, request as flask_request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from ..settings import SECRET_KEY, IS_PRODUCTION, SENTRY_DSN, PLAUSIBLE_DOMAIN, PLAUSIBLE_SCRIPT_URL

_SERVER_START_TIME = str(int(time.time()))


class V1PrefixMiddleware:
    """WSGI middleware that rewrites /api/v1/* → /api/*.

    Lets mobile clients use versioned URLs while existing routes stay unchanged.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith("/api/v1/"):
            environ["PATH_INFO"] = "/api/" + path[8:]
        return self.app(environ, start_response)


def _build_static_hashes(static_folder):
    """Compute SHA-256 content hashes for CSS and JS files in the static folder."""
    hashes = {}
    for fname in os.listdir(static_folder):
        if fname.endswith((".css", ".js")):
            path = os.path.join(static_folder, fname)
            try:
                with open(path, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()[:8]
                hashes[fname] = digest
            except OSError:
                hashes[fname] = "0"
    return hashes


def create_app():
    """Create and configure the Flask app."""
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # ── Secret key ────────────────────────────────────────
    app.config["SECRET_KEY"] = SECRET_KEY
    if IS_PRODUCTION and SECRET_KEY == "mandarin-local-only":
        raise RuntimeError("SECRET_KEY must be set in production (not the default)")

    # Validate JWT_SECRET in production (Zero Trust: explicit credential verification)
    from ..settings import JWT_SECRET
    if IS_PRODUCTION and JWT_SECRET == "mandarin-local-only":
        raise RuntimeError("JWT_SECRET must be set in production (not the default)")

    # ── Cookie security ───────────────────────────────────
    app.config["REMEMBER_COOKIE_DURATION"] = 30 * 24 * 3600  # 30 days
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = IS_PRODUCTION
    app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION

    # ── Logging ───────────────────────────────────────────
    if IS_PRODUCTION:
        # JSON log lines for structured log aggregation
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "ts": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                })
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logging.root.handlers = [handler]
        logging.root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    # ── Sentry (error monitoring) ─────────────────────────
    if SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration

            sentry_sdk.init(
                dsn=SENTRY_DSN,
                integrations=[FlaskIntegration()],
                traces_sample_rate=0.1,
                before_send=_sentry_filter,
            )
        except ImportError:
            logging.getLogger(__name__).warning("sentry-sdk not installed, skipping Sentry init")

    # ── ProxyFix (production behind reverse proxy) ────────
    if IS_PRODUCTION:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── V1 API prefix rewrite (after ProxyFix) ────────────
    app.wsgi_app = V1PrefixMiddleware(app.wsgi_app)

    # ── CSRF protection ───────────────────────────────────
    csrf = CSRFProtect(app)

    # ── Rate limiting (persistent SQLite storage) ───────
    from .rate_limit_store import SQLiteStorage
    _sqlite_storage = SQLiteStorage("sqlite://")
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per hour"],
        storage_uri="memory://",
    )
    try:
        limiter._storage = _sqlite_storage
    except Exception:
        pass  # Falls back to memory://

    # ── Idle session timeout (Item 22) ────────────────────
    SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))

    @app.before_request
    def _check_idle_timeout():
        from flask_login import current_user as _cu
        from flask import session as _session
        if not _cu.is_authenticated:
            return None
        now = time.time()
        last = _session.get("last_activity")
        if last and (now - last) > SESSION_TIMEOUT_MINUTES * 60:
            from flask_login import logout_user as _logout
            _logout()
            _session.clear()
            if flask_request.is_json or flask_request.path.startswith("/api/"):
                return {"error": "Session expired due to inactivity"}, 401
            from flask import redirect, url_for, flash
            flash("Session expired due to inactivity. Please log in again.", "info")
            return redirect(url_for("auth.login"))
        _session["last_activity"] = now
        return None

    # ── Flask-Login ───────────────────────────────────────
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    login_manager.init_app(app)

    from .auth_routes import load_user, User
    login_manager.user_loader(load_user)

    # ── JWT Bearer token request loader ───────────────────
    # Checks Authorization: Bearer <token> header and ?token= query param
    # (for WebSocket). Makes current_user transparent for all routes.
    @app.before_request
    def _load_jwt_user():
        from flask_login import current_user as _cu
        if _cu.is_authenticated:
            return  # Already authenticated via session cookie

        token = None
        auth_header = flask_request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        # Note: ?token= query param intentionally NOT supported here.
        # JWT tokens in URLs leak via server logs, referrer headers, and browser history.
        # WebSocket auth uses protocol-level message instead (Zero Trust: no credential leakage).

        if token:
            from ..jwt_auth import decode_access_token
            user_id = decode_access_token(token)
            if user_id:
                from ..auth import get_user_by_id
                from .. import db
                try:
                    with db.connection() as conn:
                        user_dict = get_user_by_id(conn, user_id)
                        if user_dict:
                            from flask_login import login_user as _login_user
                            _login_user(User(user_dict), remember=False)
                except (ValueError, TypeError, OSError):
                    pass

    # ── Static hash cache busting ─────────────────────────
    _hashes = _build_static_hashes(app.static_folder)

    @app.context_processor
    def inject_static_hash():
        from flask import g
        def static_hash(filename):
            return _hashes.get(filename, "0") + "." + _SERVER_START_TIME
        return {
            "static_hash": static_hash,
            "plausible_domain": PLAUSIBLE_DOMAIN,
            "plausible_script_url": PLAUSIBLE_SCRIPT_URL,
            "csp_nonce": getattr(g, "csp_nonce", ""),
        }

    # ── Register blueprints ───────────────────────────────
    from .auth_routes import auth_bp
    app.register_blueprint(auth_bp)

    # Rate limits on auth routes
    limiter.limit("10/minute")(app.view_functions["auth.login"])
    limiter.limit("5/hour")(app.view_functions["auth.register"])
    limiter.limit("3/hour")(app.view_functions["auth.forgot_password"])

    from .routes import register_routes
    register_routes(app)

    from .landing_routes import landing_bp
    app.register_blueprint(landing_bp)

    from .marketing_routes import register_marketing_routes
    register_marketing_routes(app)

    from .payment_routes import payment_bp
    csrf.exempt(payment_bp)
    app.register_blueprint(payment_bp)

    from .onboarding_routes import onboarding_bp
    app.register_blueprint(onboarding_bp)

    from .admin_routes import admin_bp
    app.register_blueprint(admin_bp)

    # ── MFA routes (CSRF exempt for JSON API) ─────────────
    from .mfa_routes import mfa_bp
    app.register_blueprint(mfa_bp)
    limiter.limit("10/minute")(app.view_functions["mfa.mfa_verify_setup"])

    # ── Token routes (CSRF exempt, rate limited) ──────────
    from .token_routes import token_bp
    csrf.exempt(token_bp)
    app.register_blueprint(token_bp)
    limiter.limit("10/minute")(app.view_functions["token.obtain_token"])
    limiter.limit("10/minute")(app.view_functions["token.mfa_token"])
    limiter.limit("30/minute")(app.view_functions["token.refresh_token"])

    # ── Sync routes (CSRF exempt) ─────────────────────────
    from .sync_routes import sync_bp
    csrf.exempt(sync_bp)
    app.register_blueprint(sync_bp)

    # ── GDPR routes (data export/deletion) ─────────────
    from .gdpr_routes import gdpr_bp
    csrf.exempt(gdpr_bp)
    app.register_blueprint(gdpr_bp)

    # ── LTI 1.3 routes (Item 14) ─────────────────────
    try:
        from .lti_routes import lti_bp
        csrf.exempt(lti_bp)
        app.register_blueprint(lti_bp)
    except ImportError:
        pass

    # CSRF protection for JSON API routes: require X-Requested-With header
    # instead of CSRF tokens. This header triggers CORS preflight, preventing
    # cross-origin POST attacks from simple forms. (Zero Trust: verify every request)
    @app.before_request
    def _verify_api_csrf():
        if (flask_request.method in ("POST", "PUT", "DELETE", "PATCH")
                and flask_request.path.startswith("/api/")
                and not flask_request.path.startswith("/api/webhook/")
                and not flask_request.path.startswith("/api/auth/token")):
            # JWT-authenticated requests (Bearer token) are inherently CSRF-safe
            auth_header = flask_request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return None
            # Cookie-authenticated requests must include custom header
            if not flask_request.headers.get("X-Requested-With"):
                from .api_errors import api_error, CSRF_MISSING
                from ..security import log_security_event, SecurityEvent, Severity
                try:
                    from .. import db as _db
                    with _db.connection() as _conn:
                        log_security_event(
                            _conn, SecurityEvent.CSRF_VIOLATION,
                            details=f"{flask_request.method} {flask_request.path}",
                            severity=Severity.WARNING,
                        )
                except Exception:
                    pass
                return api_error(CSRF_MISSING, "X-Requested-With header required for API requests.", 403)
        return None

    # ── Rate limit exceeded handler ─────────────────────
    @app.errorhandler(429)
    def _rate_limit_exceeded(e):
        from ..security import log_security_event, SecurityEvent, Severity
        try:
            from .. import db as _db
            with _db.connection() as _conn:
                from flask_login import current_user as _cu
                uid = _cu.id if _cu.is_authenticated else None
                log_security_event(
                    _conn, SecurityEvent.RATE_LIMIT_HIT,
                    user_id=uid,
                    details=f"{flask_request.method} {flask_request.path}",
                    severity=Severity.WARNING,
                )
        except Exception:
            pass
        # Item 21: Include Retry-After header
        retry_after = 60  # Default 60s
        try:
            desc = str(e.description) if hasattr(e, 'description') else ""
            # Extract retry window from limiter description (e.g. "10 per 1 minute")
            import re as _rate_re
            m = _rate_re.search(r'(\d+)\s*(second|minute|hour)', desc)
            if m:
                val = int(m.group(1))
                unit = m.group(2)
                if unit == "minute":
                    retry_after = val * 60
                elif unit == "hour":
                    retry_after = val * 3600
                else:
                    retry_after = val
        except Exception:
            pass
        resp = jsonify({"error": "Rate limit exceeded. Try again later."})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    # Exempt all /api/ POST routes from Flask-WTF CSRF (we use custom header above)
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/") and "POST" in (rule.methods or set()):
            view_fn = app.view_functions.get(rule.endpoint)
            if view_fn:
                csrf.exempt(view_fn)

    return app


def _sentry_filter(event, hint):
    """Filter out 401/404 errors from Sentry."""
    if "exc_info" in hint:
        exc = hint["exc_info"][1]
        from werkzeug.exceptions import NotFound, Unauthorized
        if isinstance(exc, (NotFound, Unauthorized)):
            return None
    return event
