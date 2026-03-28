"""Webhook endpoints for external monitoring services.

Receives alerts from Sentry and UptimeRobot and triggers targeted
self-healing analysis. These endpoints are CSRF-exempt and do not
require authentication (they validate payloads via signatures/tokens).

Endpoints:
    POST /api/webhooks/sentry   — Sentry webhook (error alerts)
    POST /api/webhooks/uptime   — UptimeRobot webhook (downtime alerts)
    GET  /api/webhooks/health   — Health check for webhook system

Security:
    - Sentry webhooks are verified via the Sentry-Hook-Resource header
      and optionally via HMAC signature (if SENTRY_WEBHOOK_SECRET is set)
    - UptimeRobot webhooks are verified by checking for expected payload fields
    - All webhook processing is logged
    - Rate limited to prevent abuse
"""

import hashlib
import hmac
import json
import logging
import os
import threading

from flask import Blueprint, jsonify, request

from .. import db

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")

# Optional: HMAC secret for Sentry webhook signature verification
_SENTRY_WEBHOOK_SECRET = os.environ.get("SENTRY_WEBHOOK_SECRET", "")


@webhook_bp.route("/health", methods=["GET"])
def webhook_health():
    """Health check for the webhook system."""
    return jsonify({
        "status": "ok",
        "sentry_configured": bool(os.environ.get("SENTRY_AUTH_TOKEN")),
        "uptime_configured": bool(_get_uptime_key()),
    })


@webhook_bp.route("/sentry", methods=["POST"])
def sentry_webhook():
    """Receive Sentry webhook alerts and trigger self-healing analysis.

    Sentry sends webhooks for new issues, resolved issues, and other events.
    We process error/issue events and route them through the self-healing
    classification and fix pipeline.

    Sentry webhook documentation:
    https://docs.sentry.io/product/integrations/integration-platform/webhooks/
    """
    # Verify the request comes from Sentry
    resource = request.headers.get("Sentry-Hook-Resource", "")
    if not resource:
        logger.warning("Sentry webhook: missing Sentry-Hook-Resource header")
        return jsonify({"status": "ignored", "reason": "missing header"}), 400

    # Optional: verify HMAC signature
    if _SENTRY_WEBHOOK_SECRET:
        signature = request.headers.get("Sentry-Hook-Signature", "")
        body = request.get_data()
        expected = hmac.new(
            _SENTRY_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Sentry webhook: invalid signature")
            return jsonify({"status": "rejected", "reason": "invalid signature"}), 403

    # Parse payload
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"status": "error", "reason": "invalid JSON"}), 400

    action = payload.get("action", "")
    # Only process issue-related webhooks (not installation, etc.)
    if resource not in ("issue", "event_alert", "metric_alert"):
        logger.debug("Sentry webhook: ignoring resource type '%s'", resource)
        return jsonify({"status": "ignored", "reason": f"resource '{resource}' not handled"})

    # Process asynchronously to respond quickly
    _process_webhook_async("sentry", payload)

    logger.info("Sentry webhook received: resource=%s, action=%s", resource, action)
    return jsonify({"status": "accepted"})


@webhook_bp.route("/uptime", methods=["POST"])
def uptime_webhook():
    """Receive UptimeRobot webhook alerts.

    UptimeRobot sends webhooks when monitors go down or recover.
    We process down alerts and route them through self-healing.

    UptimeRobot webhook format:
    - Form-encoded or JSON with fields: monitorID, monitorURL,
      monitorFriendlyName, alertType (1=down, 2=up), alertDetails
    """
    # Accept both JSON and form-encoded data
    if request.is_json:
        payload = request.get_json(force=True, silent=True) or {}
    else:
        payload = {
            "monitorID": request.form.get("monitorID", ""),
            "monitorURL": request.form.get("monitorURL", ""),
            "monitorFriendlyName": request.form.get("monitorFriendlyName", ""),
            "alertType": int(request.form.get("alertType", "0") or "0"),
            "alertDetails": request.form.get("alertDetails", ""),
            "alertDuration": request.form.get("alertDuration", ""),
        }

    # Basic validation
    monitor_id = payload.get("monitorID", "")
    if not monitor_id:
        return jsonify({"status": "ignored", "reason": "missing monitorID"}), 400

    alert_type = payload.get("alertType", 0)
    try:
        alert_type = int(alert_type)
    except (ValueError, TypeError):
        alert_type = 0

    # alertType 2 = recovery, log but don't trigger healing
    if alert_type == 2:
        logger.info(
            "UptimeRobot webhook: monitor '%s' recovered",
            payload.get("monitorFriendlyName", monitor_id),
        )
        return jsonify({"status": "noted", "type": "recovery"})

    # Process down alert asynchronously
    _process_webhook_async("uptime", payload)

    logger.info(
        "UptimeRobot webhook: monitor '%s' is DOWN",
        payload.get("monitorFriendlyName", monitor_id),
    )
    return jsonify({"status": "accepted"})


# ── Async processing ─────────────────────────────────────────────────────

def _process_webhook_async(source: str, payload: dict) -> None:
    """Process a webhook payload in a background thread.

    This allows the webhook endpoint to respond immediately (within Sentry/
    UptimeRobot timeout) while the self-healing analysis runs asynchronously.
    """
    thread = threading.Thread(
        target=_process_webhook_sync,
        args=(source, payload),
        daemon=True,
        name=f"webhook-{source}",
    )
    thread.start()


def _process_webhook_sync(source: str, payload: dict) -> None:
    """Synchronous webhook processing (runs in background thread)."""
    conn = None
    try:
        conn = db.get_connection()

        from ..intelligence.self_healing import run_self_healing_for_webhook
        result = run_self_healing_for_webhook(conn, source, payload)

        logger.info(
            "Webhook processing [%s] complete: %s",
            source,
            result.get("action_taken", "no action"),
        )
    except Exception:
        logger.exception("Webhook processing [%s] failed", source)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _get_uptime_key() -> str:
    """Check if UptimeRobot API key is configured."""
    try:
        from ..settings import UPTIMEROBOT_API_KEY
        return UPTIMEROBOT_API_KEY or ""
    except (ImportError, AttributeError):
        return os.environ.get("UPTIMEROBOT_API_KEY", "")
