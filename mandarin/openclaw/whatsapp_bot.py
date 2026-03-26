"""OpenClaw WhatsApp bot — Meta Cloud API integration.

Webhook-based: Flask receives inbound messages from Meta,
processes via commands/llm_handler, replies via Cloud API.
No long-running process needed — runs inside the Flask app.

Setup:
1. Create a Meta Business App at developers.facebook.com
2. Add WhatsApp product, get phone number ID and access token
3. Set webhook URL to https://your-domain/api/openclaw/webhook/whatsapp
4. Set verify token to match OPENCLAW_WHATSAPP_VERIFY_TOKEN
"""

import logging
import os
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

from . import commands, llm_handler, security

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v21.0"


def _get_config():
    """Read config at call time for testability."""
    return {
        "token": os.environ.get("OPENCLAW_WHATSAPP_TOKEN", ""),
        "phone_id": os.environ.get("OPENCLAW_WHATSAPP_PHONE_ID", ""),
        "verify_token": os.environ.get("OPENCLAW_WHATSAPP_VERIFY_TOKEN", ""),
        "owner_number": os.environ.get("OPENCLAW_WHATSAPP_OWNER_NUMBER", ""),
    }


def is_configured() -> bool:
    """Check if WhatsApp credentials are set."""
    cfg = _get_config()
    return bool(cfg["token"] and cfg["phone_id"])


def verify_webhook(mode: str, token: str, challenge: str) -> str | None:
    """Verify Meta webhook subscription.

    Returns the challenge string if valid, None if not.
    """
    cfg = _get_config()
    if mode == "subscribe" and token == cfg["verify_token"] and cfg["verify_token"]:
        return challenge
    return None


def handle_webhook(payload: dict) -> None:
    """Process an inbound WhatsApp webhook payload.

    Meta sends a nested structure:
    {object, entry: [{changes: [{value: {messages: [...]}}]}]}
    """
    cfg = _get_config()
    if not cfg["token"]:
        return

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                _process_message(msg, cfg)


def _process_message(msg: dict, cfg: dict) -> None:
    """Process a single inbound WhatsApp message."""
    sender = msg.get("from", "")
    msg_type = msg.get("type", "")

    # Owner-only check
    if cfg["owner_number"] and sender != cfg["owner_number"]:
        logger.warning("WhatsApp message from unauthorized number: %s", sender[:6] + "...")
        return

    # Only handle text messages for now
    if msg_type != "text":
        send_message(sender, "I can only process text messages right now.", cfg)
        return

    text = msg.get("text", {}).get("body", "")
    if not text:
        return

    # Get DB connection for logging
    conn = None
    try:
        from .. import db
        conn = db.connection().__enter__()
    except Exception:
        pass

    try:
        # Sanitize
        clean_text = security.sanitize_input(text)

        # Injection check
        is_safe, detail = security.check_prompt_injection(clean_text)
        if not is_safe:
            if conn:
                security.log_message(
                    conn, direction="inbound", channel="whatsapp",
                    message_text=clean_text, user_identifier=sender[:6],
                    injection_detected=True, injection_detail=detail or "",
                )
            send_message(sender, "I couldn't process that. Try /status or /review.", cfg)
            return

        # Classify and execute
        wa_user_id = sender[:20]
        intent_result = llm_handler.classify_intent(clean_text, conn=conn, user_id=wa_user_id)
        response = _execute_intent(intent_result, conn)

        # Log
        if conn:
            security.log_message(
                conn, direction="inbound", channel="whatsapp",
                message_text=clean_text, user_identifier=sender[:6],
                intent=intent_result.intent,
                tool_called=f"cmd_{intent_result.intent}" if intent_result.intent != "chat" else "",
                tool_result=response[:500],
            )

        # Store conversation turn in memory
        try:
            from ..ai.memory import add_memory
            add_memory(wa_user_id, clean_text, response, channel="whatsapp")
        except (ImportError, Exception):
            pass

        # Send response
        safe_response = security.sanitize_output(response)
        send_message(sender, safe_response or "Try /help for available commands.", cfg)

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _execute_intent(intent_result, conn) -> str:
    """Execute intent — same dispatch as telegram_bot."""
    intent = intent_result.intent
    args = intent_result.args

    dispatch = {
        "status": lambda: commands.cmd_status(),
        "review": lambda: commands.cmd_review(),
        "audit": lambda: commands.cmd_audit(),
        "briefing": lambda: commands.cmd_briefing(focus=args.get("focus", "general")),
        "errors": lambda: commands.cmd_error_patterns(),
        "approve": lambda: commands.cmd_approve(item_id=args.get("item_id", 0)),
        "reject": lambda: commands.cmd_reject(
            item_id=args.get("item_id", 0), reason=args.get("reason", ""),
        ),
        "session": lambda: "Open the Aelu app or web interface to start a session.",
        "help": lambda: (
            "Commands: /status, /review, /audit, /briefing, /errors\n"
            "Or just type naturally."
        ),
    }

    handler = dispatch.get(intent)
    if handler:
        try:
            return handler()
        except Exception as e:
            logger.error("WhatsApp command %s failed: %s", intent, e, exc_info=True)
            return f"Error running {intent}."

    if intent_result.reply:
        return intent_result.reply
    return llm_handler.generate_chat_response("", conn=conn)


def send_message(to: str, text: str, cfg: dict = None) -> bool:
    """Send a WhatsApp message via the Cloud API.

    Returns True if sent successfully.
    """
    if cfg is None:
        cfg = _get_config()

    if not cfg["token"] or not cfg["phone_id"]:
        logger.debug("WhatsApp not configured — skipping send")
        return False

    url = f"{WHATSAPP_API_URL}/{cfg['phone_id']}/messages"
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},  # WhatsApp limit
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            return True
        logger.warning("WhatsApp send failed: %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        logger.error("WhatsApp send error: %s", e)
        return False


def send_to_owner(text: str) -> bool:
    """Send a message to the owner's WhatsApp number."""
    cfg = _get_config()
    if not cfg["owner_number"]:
        return False
    return send_message(cfg["owner_number"], text, cfg)
