"""Flask app factory for the Aelu web interface."""

import hashlib
import logging
import os
import time

from flask import Flask, jsonify, redirect, render_template, request as flask_request, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from ..settings import (
    SECRET_KEY, IS_PRODUCTION, SENTRY_DSN, PLAUSIBLE_DOMAIN, PLAUSIBLE_SCRIPT_URL,
    GA4_MEASUREMENT_ID, SESSION_TIMEOUT_MINUTES, CANONICAL_URL, PRICING,
    REMEMBER_COOKIE_DURATION_SECONDS, CSRF_TOKEN_LIFETIME_SECONDS,
    SENTRY_TRACES_SAMPLE_RATE, SLOW_REQUEST_THRESHOLD_MS,
)

logger = logging.getLogger(__name__)

_SERVER_START_TIME = str(int(time.time()))


def _compute_build_id(static_folder):
    """Compute a stable build ID from the content hash of core static assets.

    Changes whenever app.js or style.css change — deterministic across restarts.
    Falls back to server start time if files are unreadable.
    """
    import subprocess
    # Try git short SHA first (most precise for deploys)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    # Fallback: hash core static files
    h = hashlib.sha256()
    for fname in sorted(["app.js", "style.css", "sw.js"]):
        path = os.path.join(static_folder, fname)
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()[:12]


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


def create_app(testing=False):
    """Create and configure the Flask app."""
    app = Flask(__name__, static_folder="static", template_folder="templates")
    if testing:
        app.config["TESTING"] = True

    # ── Secret key ────────────────────────────────────────
    app.config["SECRET_KEY"] = SECRET_KEY

    # ── Production config validation (categorized by severity) ──
    if IS_PRODUCTION:
        from ..settings import validate_production_config
        issues = validate_production_config()

        # CRITICAL — prevent startup entirely
        if issues["critical"]:
            msg = "FATAL: production startup blocked by missing critical config:\n"
            msg += "\n".join(f"  - {m}" for m in issues["critical"])
            logger.critical(msg)
            raise RuntimeError(msg)

        # IMPORTANT — log as ERROR, allow startup
        for message in issues["important"]:
            logger.error("Production config: %s", message)

        # OPTIONAL — log as WARNING, allow startup
        for message in issues["optional"]:
            logger.warning("Production config: %s", message)

    # ── Cookie security ───────────────────────────────────
    app.config["REMEMBER_COOKIE_DURATION"] = REMEMBER_COOKIE_DURATION_SECONDS
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = IS_PRODUCTION
    app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION

    # ── Request size limit ────────────────────────────────
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max request size

    # ── Logging ───────────────────────────────────────────
    # Only configure logging if not in test mode (tests set their own config).
    if not app.config.get("TESTING"):
        from ..log_config import configure_logging
        configure_logging(mode="web")

    # ── Request/response performance logging ──────────────
    from flask import g

    @app.before_request
    def _record_request_start():
        g._request_start = time.monotonic()

    @app.after_request
    def _log_request(response):
        # Skip static file requests
        if flask_request.path.startswith("/static/"):
            return response
        start = getattr(g, "_request_start", None)
        if start is None:
            return response
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            log_level, "%s %s %s %.1fms",
            flask_request.method, flask_request.path,
            response.status_code, latency_ms,
            extra={
                "request_method": flask_request.method,
                "request_path": flask_request.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        if latency_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning("Slow request: %s %s took %.0fms",
                           flask_request.method, flask_request.path, latency_ms)
        return response

    # Security response headers are set in routes.py set_security_headers()
    # which includes CSP, Permissions-Policy, and Cache-Control.

    # ── Sentry (error monitoring) ─────────────────────────
    if SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration

            sentry_sdk.init(
                dsn=SENTRY_DSN,
                integrations=[FlaskIntegration()],
                traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
                before_send=_sentry_filter,
            )
        except ImportError:
            logging.getLogger(__name__).info("sentry-sdk not installed, skipping Sentry init")

    # ── ProxyFix (production behind reverse proxy) ────────
    if IS_PRODUCTION:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── V1 API prefix rewrite (after ProxyFix) ────────────
    app.wsgi_app = V1PrefixMiddleware(app.wsgi_app)

    # ── CSRF protection ───────────────────────────────────
    # Extend CSRF token lifetime to 24 hours (default is 1 hour).
    # The macOS/web app can stay open for long periods without interaction,
    # causing "Bad Request — The CSRF token has expired" on stale forms.
    app.config["WTF_CSRF_TIME_LIMIT"] = CSRF_TOKEN_LIFETIME_SECONDS
    csrf = CSRFProtect(app)

    # ── Request timing middleware ───────
    from .timing_middleware import init_timing
    init_timing(app)

    # ── Rate limiting (persistent SQLite storage) ───────
    from .rate_limit_store import SQLiteStorage
    _sqlite_storage = SQLiteStorage("sqlite://")
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per hour"],
        storage_uri="memory://",
    )
    # Replace the default in-memory backend with our SQLite storage.
    # We cannot pass SQLiteStorage directly to Limiter() because it
    # expects a URI string, not a Storage instance. Setting the internal
    # _storage attribute is the supported extension point.
    limiter._storage = _sqlite_storage

    # ── Flask-Login ───────────────────────────────────────
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    login_manager.init_app(app)

    from .auth_routes import load_user, User, _is_native_request
    login_manager.user_loader(load_user)

    # ── Idle session timeout (Item 22) ────────────────────
    # Registered AFTER Flask-Login init so current_user is loaded before this runs.
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
            if _is_native_request():
                return render_template("login.html", email="")
            return redirect(url_for("auth.login"))
        _session["last_activity"] = now
        return None

    @login_manager.unauthorized_handler
    def _unauthorized():
        """Native iOS (Capacitor) can't follow 302 redirects — render login directly."""
        if _is_native_request():
            return render_template("login.html", email="")
        if flask_request.is_json or flask_request.path.startswith("/api/"):
            return {"error": "Authentication required"}, 401
        return redirect(url_for("auth.login"))

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

    # ── Static hash cache busting + build ID ────────────────
    _hashes = _build_static_hashes(app.static_folder)
    _build_id = _compute_build_id(app.static_folder)
    logger.info("Build ID: %s", _build_id)

    @app.context_processor
    def inject_static_hash():
        from flask import g
        def static_hash(filename):
            return _hashes.get(filename, "0") + "." + _SERVER_START_TIME
        # Pricing subset for client-side display (no secrets)
        # Respect user's A/B price variant if assigned
        _psrc = PRICING
        try:
            from flask_login import current_user as _cu
            if hasattr(_cu, 'is_authenticated') and _cu.is_authenticated:
                _pv = getattr(_cu, 'price_variant', None)
                if _pv:
                    from ..settings import get_variant_pricing
                    _psrc = get_variant_pricing(_pv)
        except Exception:
            pass
        _pricing_display = {
            "monthly": _psrc.get("monthly_display", PRICING["monthly_display"]),
            "annual": _psrc.get("annual_display", PRICING["annual_display"]),
            "annual_monthly": _psrc.get("annual_monthly_equiv", PRICING["annual_monthly_equiv"]),
            "annual_savings": _psrc.get("annual_savings", PRICING["annual_savings"]),
        }
        return {
            "static_hash": static_hash,
            "build_id": _build_id,
            "plausible_domain": PLAUSIBLE_DOMAIN,
            "plausible_script_url": PLAUSIBLE_SCRIPT_URL,
            "ga4_id": GA4_MEASUREMENT_ID,
            "csp_nonce": getattr(g, "csp_nonce", ""),
            "is_production": IS_PRODUCTION,
            "canonical_url": CANONICAL_URL,
            "pricing_display": _pricing_display,
        }

    # ── SW kill-switch endpoint ────────────────────────────
    @app.route("/api/sw-status")
    def sw_status():
        """Returns SW status. Set SW_KILL=1 env var to force-unregister all SWs."""
        from ..settings import SW_KILL
        return jsonify({"active": not SW_KILL, "build_id": _build_id})

    # ── Register blueprints ───────────────────────────────
    from .auth_routes import auth_bp
    app.register_blueprint(auth_bp)

    # Rate limits on auth routes
    limiter.limit("10/minute")(app.view_functions["auth.login"])
    limiter.limit("5/hour")(app.view_functions["auth.register"])
    limiter.limit("3/hour")(app.view_functions["auth.forgot_password"])

    from .routes import register_routes
    register_routes(app)

    # Exempt health check endpoints from rate limiting — Fly.io probes
    # every 15s (240/hour) which exceeds the default 200/hour limit.
    # Also exempt the full /api/health endpoint.
    for ep in ("api_health_live", "api_health_ready", "api_health"):
        if ep in app.view_functions:
            limiter.exempt(app.view_functions[ep])

    # Belt-and-suspenders: also raise limit on health paths via decorator
    # in case exempt() doesn't stick with custom storage backends.
    for ep in ("api_health_live", "api_health_ready", "api_health"):
        if ep in app.view_functions:
            limiter.limit("2000/hour")(app.view_functions[ep])

    from .session_routes import register_session_routes
    register_session_routes(app)

    from .dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from .settings_routes import settings_bp
    app.register_blueprint(settings_bp)

    from .exposure_routes import exposure_bp
    app.register_blueprint(exposure_bp)

    from .grammar_routes import grammar_bp
    app.register_blueprint(grammar_bp)

    from .export_routes import export_bp
    app.register_blueprint(export_bp)

    # Rate limit on error-report (20/hour per IP)
    if "api_error_report" in app.view_functions:
        limiter.limit("20/hour")(app.view_functions["api_error_report"])
    if "api_stats_public" in app.view_functions:
        limiter.limit("30/minute")(app.view_functions["api_stats_public"])

    from .landing_routes import landing_bp
    app.register_blueprint(landing_bp)

    from .seo_routes import seo_bp
    app.register_blueprint(seo_bp)

    from .marketing_routes import register_marketing_routes
    register_marketing_routes(app)

    # Rate limits on unauthenticated marketing endpoints
    if "api_feedback" in app.view_functions:
        limiter.limit("5/hour")(app.view_functions["api_feedback"])
    if "api_referral_signup" in app.view_functions:
        limiter.limit("20/hour")(app.view_functions["api_referral_signup"])

    from .payment_routes import payment_bp
    csrf.exempt(payment_bp)
    app.register_blueprint(payment_bp)

    from .onboarding_routes import onboarding_bp
    app.register_blueprint(onboarding_bp)

    from .admin_routes import admin_bp
    app.register_blueprint(admin_bp)

    # ── NIST AI RMF: Admin MFA enforcement middleware (defense-in-depth) ──
    # Enforces MFA on all /api/admin/* routes at the middleware level,
    # independent of per-route decorators. Production returns 403;
    # development logs a warning but allows access.
    @app.before_request
    def _enforce_admin_mfa():
        if not flask_request.path.startswith("/api/admin/") and not flask_request.path.startswith("/admin/"):
            return None
        from flask_login import current_user as _cu
        if not _cu.is_authenticated:
            return None  # Auth check handled elsewhere
        try:
            from .. import db as _db
            with _db.connection() as _conn:
                _row = _conn.execute(
                    "SELECT is_admin, totp_enabled FROM user WHERE id = ?",
                    (_cu.id,),
                ).fetchone()
                if not _row or not _row["is_admin"]:
                    return None  # Non-admin — access denied handled by decorator
                if not _row["totp_enabled"]:
                    if IS_PRODUCTION:
                        logger.warning(
                            "NIST-AI: admin MFA not enabled for user %s on %s",
                            _cu.id, flask_request.path,
                        )
                        return jsonify({"error": "MFA required for admin access."}), 403
                    else:
                        logger.warning(
                            "NIST-AI [dev]: admin MFA not enabled for user %s on %s (allowing in dev)",
                            _cu.id, flask_request.path,
                        )
        except Exception:
            logger.debug("admin MFA check failed", exc_info=True)
        return None

    from .vibe_admin_routes import vibe_admin_bp
    app.register_blueprint(vibe_admin_bp)

    from .strategy_admin_routes import strategy_admin_bp
    app.register_blueprint(strategy_admin_bp)

    from .governance_admin_routes import governance_admin_bp
    app.register_blueprint(governance_admin_bp)

    from .genai_admin_routes import genai_admin_bp
    app.register_blueprint(genai_admin_bp)

    from .intelligence_admin_routes import intelligence_admin_bp
    app.register_blueprint(intelligence_admin_bp)

    from .nps_routes import nps_bp
    app.register_blueprint(nps_bp)

    # ── MFA routes (CSRF exempt for JSON API) ─────────────
    from .mfa_routes import mfa_bp
    app.register_blueprint(mfa_bp)
    limiter.limit("10/minute")(app.view_functions["mfa.mfa_verify_setup"])
    limiter.limit("5/hour")(app.view_functions["mfa.mfa_disable"])
    limiter.limit("10/hour")(app.view_functions["mfa.mfa_setup"])

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

    # ── Classroom routes ─────────────────────────────
    from .classroom_routes import classroom_bp
    app.register_blueprint(classroom_bp)

    from .tutor_routes import tutor_bp
    app.register_blueprint(tutor_bp)

    # ── Learner intelligence routes ─────────────────────
    from .intelligence_routes import intelligence_bp
    app.register_blueprint(intelligence_bp)

    # ── LTI 1.3 routes (Item 14) ─────────────────────
    try:
        from .lti_routes import lti_bp
        csrf.exempt(lti_bp)
        app.register_blueprint(lti_bp)
    except ImportError:
        pass

    # ── OpenClaw API routes (n8n integration) ─────────
    from .openclaw_routes import openclaw_bp
    csrf.exempt(openclaw_bp)
    app.register_blueprint(openclaw_bp)

    # ── Conversation drill routes ──────────────────────
    from .conversation_routes import conversation_bp
    app.register_blueprint(conversation_bp)

    # ── Content management routes ──────────────────────
    from .content_routes import content_bp
    app.register_blueprint(content_bp)

    # ── SRS / analytics / content import routes ──────────
    from .srs_analytics_routes import srs_analytics_bp
    app.register_blueprint(srs_analytics_bp)

    # ── Gap features (OCR, widget, study lists) ──────────
    from .gap_routes import gap_bp
    csrf.exempt(gap_bp)
    app.register_blueprint(gap_bp)

    # ── Self-healing webhook routes (Sentry, UptimeRobot) ──────────
    from .webhook_routes import webhook_bp
    csrf.exempt(webhook_bp)
    app.register_blueprint(webhook_bp)

    # CSRF protection for JSON API routes: require X-Requested-With header
    # instead of CSRF tokens. This header triggers CORS preflight, preventing
    # cross-origin POST attacks from simple forms. (Zero Trust: verify every request)
    @app.before_request
    def _verify_api_csrf():
        if (flask_request.method in ("POST", "PUT", "DELETE", "PATCH")
                and flask_request.path.startswith("/api/")
                and not flask_request.path.startswith("/api/webhook/")
                and not flask_request.path.startswith("/api/auth/token")
                and not flask_request.path.startswith("/api/error-report")
                and not flask_request.path.startswith("/api/client-events")
                and not flask_request.path.startswith("/api/openclaw/")):
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
                    logger.warning("CSRF security event logging failed", exc_info=True)
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
            logger.warning("rate limit event logging failed", exc_info=True)
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
            logger.debug("retry-after parsing failed", exc_info=True)
        resp = jsonify({"error": "Rate limit exceeded. Try again later."})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    # ── 500 error handler — log crashes to DB ─────────────
    @app.errorhandler(500)
    def _handle_500(e):
        original = getattr(e, "original_exception", e)
        _log_crash(original)
        if flask_request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("500.html"), 500

    # Exempt all /api/ POST routes from Flask-WTF CSRF (we use custom header above)
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/") and "POST" in (rule.methods or set()):
            view_fn = app.view_functions.get(rule.endpoint)
            if view_fn:
                csrf.exempt(view_fn)

    # ── Background schedulers (all with DB-backed multi-instance locks) ──
    if not app.config.get("TESTING"):
        from . import scheduler_health
        from . import (
            stale_session_scheduler,
            retention_scheduler,
            email_scheduler,
            security_scan_scheduler,
            quality_scheduler,
            ai_feedback_scheduler,
            crawl_scheduler,
            interference_scheduler,
            experiment_daemon,
            openclaw_scheduler,
            counter_metrics_scheduler,
            marketing_scheduler,
            nightly_intelligence_scheduler,
            signal_scheduler,
        )

        _scheduler_modules = [
            ("stale-session-cleanup", stale_session_scheduler),
            ("retention-purge", retention_scheduler),
            ("email-scheduler", email_scheduler),
            ("security-scan", security_scan_scheduler),
            ("quality-scheduler", quality_scheduler),
            ("ai-feedback", ai_feedback_scheduler),
            ("crawl-scheduler", crawl_scheduler),
            ("interference-scheduler", interference_scheduler),
            ("experiment-daemon", experiment_daemon),
            ("openclaw-scheduler", openclaw_scheduler),
            ("counter-metrics", counter_metrics_scheduler),
            ("marketing-scheduler", marketing_scheduler),
            ("nightly-intelligence", nightly_intelligence_scheduler),
            ("signal-bot", signal_scheduler),
        ]

        for _name, _module in _scheduler_modules:
            try:
                _module.start()
                _thread = getattr(_module, "_thread", None)
                if _thread is not None:
                    scheduler_health.register(_name, _thread, _module.start)
            except Exception:
                logger.exception("Failed to start scheduler '%s'", _name)

        # Start the scheduler health monitor (checks every 5 minutes)
        scheduler_health.start_monitor()

        # Log LLM health at startup
        try:
            from ..ai.ollama_client import is_llm_available
            from ..settings import LITELLM_MODEL, IS_CLOUD_MODEL, MODEL_SIZE_B
            if is_llm_available():
                logger.info("LLM ready: %s (cloud=%s, %.0fb)", LITELLM_MODEL, IS_CLOUD_MODEL, MODEL_SIZE_B)
            else:
                logger.warning("LLM unavailable at startup — check API keys and Ollama")
        except Exception:
            pass

    # ── Ensure ADMIN_EMAIL user has is_admin flag ──────────
    try:
        from ..settings import ADMIN_EMAIL
        if ADMIN_EMAIL:
            with db.connection() as _conn:
                _conn.execute(
                    "UPDATE user SET is_admin = 1 WHERE email = ? AND (is_admin IS NULL OR is_admin = 0)",
                    (ADMIN_EMAIL,),
                )
                _conn.commit()
    except Exception:
        pass

    return app


def _sentry_filter(event, hint):
    """Filter out 401/404 errors from Sentry."""
    if "exc_info" in hint:
        exc = hint["exc_info"][1]
        from werkzeug.exceptions import NotFound, Unauthorized
        if isinstance(exc, (NotFound, Unauthorized)):
            return None
    return event


def _log_crash(exception):
    """Log an unhandled server exception to the crash_log table.

    Falls back to logger.critical if the DB insert itself fails
    (e.g. the database is the crash source).
    """
    import traceback as _tb

    error_type = type(exception).__name__
    error_message = str(exception)[:2048]
    tb_text = _tb.format_exc()

    # Request context (may not be available outside request)
    method = path = body = ip = ua = None
    try:
        method = flask_request.method
        path = flask_request.path
        try:
            body = (flask_request.get_data(as_text=True) or "")[:2048]
        except Exception:
            body = ""
        ip = flask_request.remote_addr
        ua = (flask_request.headers.get("User-Agent") or "")[:512]
    except RuntimeError:
        pass  # Outside request context

    user_id = None
    try:
        from flask_login import current_user as _cu
        if _cu.is_authenticated:
            user_id = _cu.id
    except Exception:
        pass

    try:
        from .. import db as _db
        with _db.connection() as conn:
            conn.execute(
                """INSERT INTO crash_log
                   (user_id, error_type, error_message, traceback,
                    request_method, request_path, request_body,
                    ip_address, user_agent, severity)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ERROR')""",
                (user_id, error_type, error_message, tb_text,
                 method, path, body, ip, ua),
            )
            conn.commit()
    except Exception:
        logger.critical(
            "crash_log DB insert failed; original error: %s: %s\n%s",
            error_type, error_message, tb_text,
        )
