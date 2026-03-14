"""Structured API error responses for mobile/v1 endpoints."""

from __future__ import annotations

import functools
import logging
import sqlite3

from flask import jsonify

logger = logging.getLogger(__name__)


# ── Error code constants ─────────────────────────────────────────────────────

AUTH_TOKEN_EXPIRED = "auth/token_expired"
AUTH_TOKEN_INVALID = "auth/token_invalid"
AUTH_CREDENTIALS_INVALID = "auth/credentials_invalid"
AUTH_REQUIRED = "auth/required"
AUTH_REFRESH_INVALID = "auth/refresh_invalid"

TIER_UPGRADE_REQUIRED = "tier/upgrade_required"

RATE_LIMIT_EXCEEDED = "rate/limit_exceeded"

CSRF_MISSING = "security/csrf_missing"

VALIDATION_ERROR = "validation/error"
NOT_FOUND = "resource/not_found"
SERVER_ERROR = "server/error"


# ── Response builder ─────────────────────────────────────────────────────────

def api_error(code: str, message: str, status: int = 400, **extra):
    """Build a structured JSON error response.

    Returns a (response, status_code) tuple suitable for Flask route returns.

    Shape: {"error": {"code": "...", "message": "...", "status": N, ...extra}}
    """
    body = {"code": code, "message": message, "status": status}
    body.update(extra)
    return jsonify({"error": body}), status


# ── Error handler decorator ──────────────────────────────────────────────────

# Exceptions that indicate server-side problems (500)
_SERVER_EXCEPTIONS = (sqlite3.Error, OSError, ImportError)
# Exceptions that indicate bad input or missing data (more contextual)
_CLIENT_EXCEPTIONS = (KeyError, TypeError, ValueError)


def api_error_handler(label: str, status: int = 500):
    """Decorator that wraps a Flask route in standardized error handling.

    Usage:
        @app.route("/api/foo")
        @api_error_handler("Foo")
        def api_foo():
            ...

    On exception, logs the error and returns:
        {"error": "Foo unavailable"}, 500
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (*_SERVER_EXCEPTIONS, *_CLIENT_EXCEPTIONS) as e:
                logger.error("%s API error: %s", label, e, exc_info=True)
                return jsonify({"error": f"{label} unavailable"}), status
            except Exception as e:
                logger.error("%s API error (unexpected): %s", label, e, exc_info=True)
                try:
                    from mandarin.web import _log_crash
                    _log_crash(e)
                except Exception:
                    pass
                return jsonify({"error": f"{label} unavailable"}), status
        return wrapper
    return decorator
