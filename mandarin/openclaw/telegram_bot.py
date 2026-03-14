"""OpenClaw Telegram bot — owner-only messaging interface for Aelu admin.

Uses python-telegram-bot v21+ (async). Owner-only: rejects all messages
from non-owner chat IDs. Full audit trail via security.log_message().
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, MessageHandler, filters,
        ContextTypes,
    )
    _HAS_TELEGRAM = True
except ImportError:
    _HAS_TELEGRAM = False
    Update = None  # type: ignore
    BotCommand = None  # type: ignore
    Application = None  # type: ignore
    CommandHandler = MessageHandler = filters = ContextTypes = None  # type: ignore
    logger.debug("python-telegram-bot not installed — Telegram bot disabled")

try:
    from ..settings import OPENCLAW_TELEGRAM_TOKEN
except (ImportError, AttributeError):
    OPENCLAW_TELEGRAM_TOKEN = os.environ.get("OPENCLAW_TELEGRAM_TOKEN", "")

from . import commands, security, llm_handler


# ── Owner-only middleware ─────────────────────────────────

async def _check_owner(update: Update) -> bool:
    """Reject non-owner messages. Returns True if authorized."""
    if update.effective_chat is None:
        return False
    chat_id = update.effective_chat.id
    if not security.validate_owner(chat_id):
        logger.warning("Unauthorized Telegram message from chat_id=%s", chat_id)
        if update.message:
            await update.message.reply_text("⛔ Unauthorized.")
        return False
    return True


def _get_conn():
    """Get a DB connection for audit logging."""
    try:
        from .. import db
        return db.connection()
    except Exception:
        return None


# ── Command handlers ──────────────────────────────────────

async def cmd_start(update: Update, context: Any) -> None:
    """Handle /start command."""
    if not await _check_owner(update):
        return
    await update.message.reply_text(
        "Aelu OpenClaw active.\n\n"
        "Commands:\n"
        "/status — learning status + due items\n"
        "/review — content review queue\n"
        "/audit — latest audit results\n"
        "/briefing — learner/tutor prep\n"
        "/errors — error patterns + interference\n"
        "/help — this message\n\n"
        "Or just type naturally — I'll figure out what you need."
    )


async def cmd_status(update: Update, context: Any) -> None:
    """Handle /status command."""
    if not await _check_owner(update):
        return
    conn = _get_conn()
    try:
        result = commands.cmd_status()
        security.log_message(
            conn, direction="inbound", channel="telegram",
            message_text="/status", intent="status", tool_called="cmd_status",
            tool_result=result[:500],
        ) if conn else None
        await update.message.reply_text(result)
    finally:
        if conn:
            conn.close()


async def cmd_review(update: Update, context: Any) -> None:
    """Handle /review command."""
    if not await _check_owner(update):
        return
    conn = _get_conn()
    try:
        result = commands.cmd_review()
        security.log_message(
            conn, direction="inbound", channel="telegram",
            message_text="/review", intent="review", tool_called="cmd_review",
            tool_result=result[:500],
        ) if conn else None
        await update.message.reply_text(result)
    finally:
        if conn:
            conn.close()


async def cmd_audit(update: Update, context: Any) -> None:
    """Handle /audit command."""
    if not await _check_owner(update):
        return
    conn = _get_conn()
    try:
        result = commands.cmd_audit()
        security.log_message(
            conn, direction="inbound", channel="telegram",
            message_text="/audit", intent="audit", tool_called="cmd_audit",
            tool_result=result[:500],
        ) if conn else None
        await update.message.reply_text(result)
    finally:
        if conn:
            conn.close()


async def cmd_briefing(update: Update, context: Any) -> None:
    """Handle /briefing command."""
    if not await _check_owner(update):
        return
    conn = _get_conn()
    try:
        focus = " ".join(context.args) if context.args else "general"
        result = commands.cmd_briefing(focus=focus)
        security.log_message(
            conn, direction="inbound", channel="telegram",
            message_text=f"/briefing {focus}", intent="briefing",
            tool_called="cmd_briefing", tool_result=result[:500],
        ) if conn else None
        await update.message.reply_text(result)
    finally:
        if conn:
            conn.close()


async def cmd_errors(update: Update, context: Any) -> None:
    """Handle /errors command."""
    if not await _check_owner(update):
        return
    conn = _get_conn()
    try:
        result = commands.cmd_error_patterns()
        security.log_message(
            conn, direction="inbound", channel="telegram",
            message_text="/errors", intent="errors",
            tool_called="cmd_error_patterns", tool_result=result[:500],
        ) if conn else None
        await update.message.reply_text(result)
    finally:
        if conn:
            conn.close()


async def cmd_help(update: Update, context: Any) -> None:
    """Handle /help command."""
    if not await _check_owner(update):
        return
    await cmd_start(update, context)


# ── Natural language handler ──────────────────────────────

async def handle_message(update: Update, context: Any) -> None:
    """Handle free-text messages via LLM intent classification."""
    if not await _check_owner(update):
        return

    text = update.message.text or ""
    conn = _get_conn()

    try:
        # Sanitize input
        clean_text = security.sanitize_input(text)

        # Check for prompt injection
        is_safe, detail = security.check_prompt_injection(clean_text)
        if not is_safe:
            security.log_message(
                conn, direction="inbound", channel="telegram",
                message_text=clean_text, injection_detected=True,
                injection_detail=detail or "",
            ) if conn else None
            await update.message.reply_text(
                "I couldn't process that message. Try a command like /status or /review."
            )
            return

        # Classify intent
        intent_result = llm_handler.classify_intent(clean_text, conn=conn)

        # Route to appropriate command
        response = _execute_intent(intent_result, conn)

        # Log
        security.log_message(
            conn, direction="inbound", channel="telegram",
            message_text=clean_text, intent=intent_result.intent,
            tool_called=f"cmd_{intent_result.intent}" if intent_result.intent != "chat" else "",
            tool_result=response[:500],
        ) if conn else None

        # Sanitize and send
        safe_response = security.sanitize_output(response)
        await update.message.reply_text(safe_response or "I'm not sure how to help with that. Try /help.")

    finally:
        if conn:
            conn.close()


async def handle_voice(update: Update, context: Any) -> None:
    """Handle voice messages — transcribe and process as text.

    If Pipecat is available and running, forwards to voice pipeline.
    Otherwise, uses edge-tts for basic voice interaction.
    """
    if not await _check_owner(update):
        return
    await update.message.reply_text(
        "Voice messages received. Voice conversation mode coming soon — "
        "for now, please type your message."
    )


def _execute_intent(intent_result: llm_handler.IntentResult, conn) -> str:
    """Execute a classified intent and return the response text."""
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
            item_id=args.get("item_id", 0),
            reason=args.get("reason", ""),
        ),
        "session": lambda: (
            f"Ready to study? Open the app or visit {__import__('mandarin.settings', fromlist=['BASE_URL']).BASE_URL} "
            "to start a session."
        ),
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
            logger.error("Command %s failed: %s", intent, e, exc_info=True)
            return f"Error running {intent}: {str(e)[:100]}"

    # Chat / unknown — generate conversational response
    if intent_result.reply:
        return intent_result.reply
    return llm_handler.generate_chat_response(
        intent_result.args.get("original_text", ""), conn=conn,
    )


# ── Bot factory ───────────────────────────────────────────

def create_bot() -> Optional["Application"]:
    """Create and configure the Telegram bot application.

    Returns None if python-telegram-bot is not installed or token is missing.
    """
    if not _HAS_TELEGRAM:
        logger.info("python-telegram-bot not available — skipping Telegram bot")
        return None

    token = OPENCLAW_TELEGRAM_TOKEN
    if not token:
        logger.info("OPENCLAW_TELEGRAM_TOKEN not set — skipping Telegram bot")
        return None

    app = Application.builder().token(token).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("errors", cmd_errors))
    app.add_handler(CommandHandler("help", cmd_help))

    # Natural language handler (catches all text messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Voice message handler
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    return app


async def set_bot_commands(app: "Application") -> None:
    """Register command menu with Telegram."""
    await app.bot.set_my_commands([
        BotCommand("status", "Learning status + due items"),
        BotCommand("review", "Content review queue"),
        BotCommand("audit", "Latest audit results"),
        BotCommand("briefing", "Learner/tutor prep briefing"),
        BotCommand("errors", "Error patterns + interference"),
        BotCommand("help", "Show available commands"),
    ])


def run_bot() -> None:
    """Start the Telegram bot (blocking). Call from CLI or startup."""
    app = create_bot()
    if app is None:
        logger.error("Cannot start Telegram bot — missing deps or token")
        return

    logger.info("Starting OpenClaw Telegram bot...")
    app.run_polling(drop_pending_updates=True)
