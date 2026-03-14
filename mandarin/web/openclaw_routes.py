"""Flask blueprint for OpenClaw n8n integration endpoints.

These endpoints are called by n8n workflows to:
- Poll for review queue status
- Receive notifications about audit results
- Trigger Telegram notifications
- Health check
- Webhook receiver for n8n workflow events

All endpoints require the OPENCLAW_API_KEY header for authentication.
"""

import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, request

from ..settings import OPENCLAW_TELEGRAM_TOKEN
from ..openclaw import commands, security
from ..openclaw import whatsapp_bot

logger = logging.getLogger(__name__)

openclaw_bp = Blueprint("openclaw", __name__, url_prefix="/api/openclaw")


def _get_api_key():
    """Read API key at request time (not import time) for testability."""
    import os
    return os.environ.get("OPENCLAW_API_KEY", "")


def _require_api_key(f):
    """Decorator: require OPENCLAW_API_KEY header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = _get_api_key()
        if not api_key:
            return jsonify({"error": "OPENCLAW_API_KEY not configured"}), 503
        provided = request.headers.get("X-OpenClaw-Key", "")
        if provided != api_key:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@openclaw_bp.route("/health", methods=["GET"])
def health():
    """Health check for n8n."""
    return jsonify({
        "status": "ok",
        "telegram_configured": bool(OPENCLAW_TELEGRAM_TOKEN),
        "api_key_configured": bool(_get_api_key()),
    })


@openclaw_bp.route("/review-queue", methods=["GET"])
@_require_api_key
def review_queue():
    """Review queue summary for n8n polling."""
    try:
        result = commands.cmd_review()
        items = commands.cmd_review_items(limit=10)
        return jsonify({
            "summary": result,
            "items": items,
        })
    except Exception as e:
        logger.error("review-queue endpoint failed: %s", e)
        return jsonify({"error": str(e)}), 500


@openclaw_bp.route("/status", methods=["GET"])
@_require_api_key
def status():
    """Learner status for n8n study nudge workflow."""
    try:
        result = commands.cmd_status()
        return jsonify({"status": result})
    except Exception as e:
        logger.error("status endpoint failed: %s", e)
        return jsonify({"error": str(e)}), 500


@openclaw_bp.route("/audit", methods=["GET"])
@_require_api_key
def audit():
    """Latest audit for n8n audit briefing workflow."""
    try:
        result = commands.cmd_audit()
        return jsonify({"audit": result})
    except Exception as e:
        logger.error("audit endpoint failed: %s", e)
        return jsonify({"error": str(e)}), 500


@openclaw_bp.route("/errors", methods=["GET"])
@_require_api_key
def errors():
    """Error pattern analysis for n8n."""
    try:
        result = commands.cmd_error_patterns()
        return jsonify({"errors": result})
    except Exception as e:
        logger.error("errors endpoint failed: %s", e)
        return jsonify({"error": str(e)}), 500


@openclaw_bp.route("/notify", methods=["POST"])
@_require_api_key
def notify():
    """Send a notification to the owner via configured channels.

    Body: {"message": "text", "channel": "telegram|whatsapp|imessage|all" (default: "all")}
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "message required"}), 400

    safe_message = security.sanitize_output(message)
    channel = data.get("channel", "all")
    sent_via = []

    # WhatsApp
    if channel in ("whatsapp", "all"):
        try:
            if whatsapp_bot.send_to_owner(safe_message):
                sent_via.append("whatsapp")
        except Exception as e:
            logger.debug("WhatsApp notify failed: %s", e)

    # iMessage
    if channel in ("imessage", "all"):
        try:
            from ..openclaw.imessage_bot import send_to_owner as imessage_send
            if imessage_send(safe_message):
                sent_via.append("imessage")
        except Exception as e:
            logger.debug("iMessage notify failed: %s", e)

    # Telegram
    if channel in ("telegram", "all"):
        try:
            import asyncio

            async def _send_telegram():
                from telegram import Bot
                if not OPENCLAW_TELEGRAM_TOKEN:
                    return False
                bot = Bot(token=OPENCLAW_TELEGRAM_TOKEN)
                owner_id = security.OWNER_CHAT_ID
                if not owner_id:
                    return False
                await bot.send_message(chat_id=owner_id, text=safe_message)
                return True

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        ok = pool.submit(lambda: asyncio.run(_send_telegram())).result(timeout=10)
                else:
                    ok = loop.run_until_complete(_send_telegram())
            except RuntimeError:
                ok = asyncio.run(_send_telegram())

            if ok:
                sent_via.append("telegram")
        except (ImportError, Exception) as e:
            logger.debug("Telegram notify failed: %s", e)

    if sent_via:
        return jsonify({"status": "sent", "channels": sent_via})
    return jsonify({"error": "no channels available or configured"}), 503


# ── WhatsApp webhook ──────────────────────────────────────

@openclaw_bp.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_verify():
    """WhatsApp webhook verification (Meta subscription handshake)."""
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")

    result = whatsapp_bot.verify_webhook(mode, token, challenge)
    if result is not None:
        return result, 200
    return "Forbidden", 403


@openclaw_bp.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Receive inbound WhatsApp messages from Meta Cloud API."""
    payload = request.get_json(silent=True) or {}

    # Meta sends a verification ping we should acknowledge
    if payload.get("object") != "whatsapp_business_account":
        return "ok", 200

    try:
        whatsapp_bot.handle_webhook(payload)
    except Exception as e:
        logger.error("WhatsApp webhook error: %s", e, exc_info=True)

    # Always return 200 to Meta (they retry on non-200)
    return "ok", 200


@openclaw_bp.route("/webhook/n8n", methods=["POST"])
@_require_api_key
def n8n_webhook():
    """Receive events from n8n workflows.

    Body: {"event": "event_type", "data": {...}}

    Event types:
    - study_nudge_due: Time for a study reminder
    - review_queue_alert: Items pending in review queue
    - audit_complete: Weekly audit finished
    - custom: Arbitrary workflow event
    """
    data = request.get_json(silent=True) or {}
    event = data.get("event", "")
    payload = data.get("data", {})

    if not event:
        return jsonify({"error": "event required"}), 400

    # Log the webhook event
    try:
        from .. import db
        with db.connection() as conn:
            security.log_message(
                conn, direction="inbound", channel="n8n",
                message_text=json.dumps(data)[:2000],
                intent=event,
            )
    except Exception:
        pass

    # Route to handler
    handlers = {
        "study_nudge_due": _handle_study_nudge,
        "review_queue_alert": _handle_review_alert,
        "audit_complete": _handle_audit_complete,
    }

    handler = handlers.get(event)
    if handler:
        try:
            result = handler(payload)
            return jsonify({"status": "processed", "result": result})
        except Exception as e:
            logger.error("n8n webhook handler %s failed: %s", event, e)
            return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ignored", "reason": f"unknown event: {event}"})


def _handle_study_nudge(payload: dict) -> str:
    """Handle study nudge event from n8n."""
    status = commands.cmd_status()
    # The n8n workflow should call /notify separately to push to Telegram
    return status


def _handle_review_alert(payload: dict) -> str:
    """Handle review queue alert from n8n."""
    return commands.cmd_review()


def _handle_audit_complete(payload: dict) -> str:
    """Handle audit completion event from n8n."""
    return commands.cmd_audit()


@openclaw_bp.route("/approve/<int:item_id>", methods=["POST"])
@_require_api_key
def approve_item(item_id: int):
    """Approve a review item via API (for n8n or external tools)."""
    try:
        result = commands.cmd_approve(item_id)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@openclaw_bp.route("/reject/<int:item_id>", methods=["POST"])
@_require_api_key
def reject_item(item_id: int):
    """Reject a review item via API."""
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    try:
        result = commands.cmd_reject(item_id, reason=reason)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
