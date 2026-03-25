"""OpenClaw Discord bot — async bot with slash commands + natural language.

Uses discord.py v2+. Owner-only: checks OPENCLAW_DISCORD_OWNER_ID.
Runs as a separate process: ./run discord

Setup:
1. Create a Discord application at discord.com/developers
2. Add a bot, copy token to OPENCLAW_DISCORD_TOKEN
3. Enable Message Content Intent in Bot settings
4. Invite bot to your server with messages.read + messages.send scopes
5. Get your Discord user ID: Settings > Advanced > Developer Mode, right-click yourself
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import discord
    from discord.ext import commands as discord_commands
    _HAS_DISCORD = True
except ImportError:
    _HAS_DISCORD = False
    logger.debug("discord.py not installed — Discord bot disabled")

from . import commands, llm_handler, security


def _get_config():
    """Read config at call time."""
    return {
        "token": os.environ.get("OPENCLAW_DISCORD_TOKEN", ""),
        "owner_id": int(os.environ.get("OPENCLAW_DISCORD_OWNER_ID", "0")),
    }


def is_configured() -> bool:
    """Check if Discord credentials are set."""
    cfg = _get_config()
    return bool(cfg["token"]) and _HAS_DISCORD


def _check_owner(user_id: int) -> bool:
    """Check if the Discord user is the owner."""
    cfg = _get_config()
    if cfg["owner_id"] == 0:
        logger.warning("OPENCLAW_DISCORD_OWNER_ID not set — rejecting all messages")
        return False
    return user_id == cfg["owner_id"]


def _get_conn():
    """Get a DB connection."""
    try:
        from .. import db
        return db.connection()
    except Exception:
        return None


def _execute_intent(intent_result, conn) -> str:
    """Execute intent — same dispatch as other bots."""
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
            "Commands: `!status`, `!review`, `!audit`, `!briefing`, `!errors`\n"
            "Or just type naturally in DMs."
        ),
    }

    handler = dispatch.get(intent)
    if handler:
        try:
            return handler()
        except Exception as e:
            logger.error("Discord command %s failed: %s", intent, e, exc_info=True)
            return f"Error running {intent}."

    if intent_result.reply:
        return intent_result.reply
    return llm_handler.generate_chat_response("", conn=conn)


async def _handle_command(message, cmd_name: str, arg_text: str = "") -> None:
    """Handle a !command message."""
    if not _check_owner(message.author.id):
        await message.reply("Unauthorized.")
        return

    conn = _get_conn()
    try:
        dispatch = {
            "status": lambda: commands.cmd_status(),
            "review": lambda: commands.cmd_review(),
            "audit": lambda: commands.cmd_audit(),
            "briefing": lambda: commands.cmd_briefing(focus=arg_text or "general"),
            "errors": lambda: commands.cmd_error_patterns(),
            "approve": lambda: commands.cmd_approve(item_id=int(arg_text)) if arg_text.isdigit() else "Usage: !approve <id>",
            "reject": lambda: commands.cmd_reject(item_id=int(arg_text.split()[0]), reason=" ".join(arg_text.split()[1:])) if arg_text else "Usage: !reject <id> [reason]",
            "help": lambda: (
                "**Aelu OpenClaw**\n"
                "`!status` — learning status + due items\n"
                "`!review` — content review queue\n"
                "`!audit` — latest audit results\n"
                "`!briefing` — learner/tutor prep\n"
                "`!errors` — error patterns\n"
                "`!help` — this message\n\n"
                "Or DM me naturally."
            ),
        }

        handler = dispatch.get(cmd_name)
        if handler:
            try:
                result = handler()
            except Exception as e:
                result = f"Error: {str(e)[:100]}"
        else:
            result = f"Unknown command: !{cmd_name}. Try !help."

        if conn:
            security.log_message(
                conn, direction="inbound", channel="discord",
                message_text=f"!{cmd_name} {arg_text}".strip(),
                user_identifier=str(message.author.id),
                intent=cmd_name, tool_called=f"cmd_{cmd_name}",
                tool_result=result[:500],
            )

        # Discord message limit is 2000 chars
        safe = security.sanitize_output(result)
        for chunk in _chunk_message(safe, 2000):
            await message.reply(chunk)

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


async def _handle_natural_language(message) -> None:
    """Handle free-text DM via LLM intent classification."""
    if not _check_owner(message.author.id):
        return

    text = message.content
    conn = _get_conn()

    try:
        clean_text = security.sanitize_input(text)

        is_safe, detail = security.check_prompt_injection(clean_text)
        if not is_safe:
            if conn:
                security.log_message(
                    conn, direction="inbound", channel="discord",
                    message_text=clean_text, user_identifier=str(message.author.id),
                    injection_detected=True, injection_detail=detail or "",
                )
            await message.reply("I couldn't process that. Try `!help`.")
            return

        discord_user_id = str(message.author.id)[:20]
        intent_result = llm_handler.classify_intent(clean_text, conn=conn, user_id=discord_user_id)
        response = _execute_intent(intent_result, conn)

        if conn:
            security.log_message(
                conn, direction="inbound", channel="discord",
                message_text=clean_text, user_identifier=str(message.author.id),
                intent=intent_result.intent,
                tool_called=f"cmd_{intent_result.intent}" if intent_result.intent != "chat" else "",
                tool_result=response[:500],
            )

        # Store conversation turn in memory
        try:
            from ..ai.memory import add_memory
            add_memory(discord_user_id, clean_text, response, channel="discord")
        except (ImportError, Exception):
            pass

        safe = security.sanitize_output(response)
        for chunk in _chunk_message(safe or "Try `!help`.", 2000):
            await message.reply(chunk)

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _chunk_message(text: str, limit: int) -> list[str]:
    """Split a message into chunks respecting the character limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def create_bot() -> object | None:
    """Create the Discord bot client.

    Returns None if discord.py is not installed or token is missing.
    """
    if not _HAS_DISCORD:
        logger.info("discord.py not available — skipping Discord bot")
        return None

    cfg = _get_config()
    if not cfg["token"]:
        logger.info("OPENCLAW_DISCORD_TOKEN not set — skipping Discord bot")
        return None

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Discord bot connected as %s", client.user)

    @client.event
    async def on_message(message):
        # Ignore own messages
        if message.author == client.user:
            return

        content = message.content.strip()

        # Handle !commands
        if content.startswith("!"):
            parts = content[1:].split(maxsplit=1)
            cmd_name = parts[0].lower()
            arg_text = parts[1] if len(parts) > 1 else ""
            await _handle_command(message, cmd_name, arg_text)
            return

        # Handle DMs (natural language)
        if isinstance(message.channel, discord.DMChannel):
            await _handle_natural_language(message)
            return

        # In guild channels, only respond if mentioned
        if client.user in message.mentions:
            # Strip the mention and process
            clean = content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
            if clean:
                message.content = clean
                await _handle_natural_language(message)

    return client


async def send_to_owner(text: str) -> bool:
    """Send a DM to the owner. Requires an active bot client.

    This is intended to be called from n8n workflows via the notify endpoint.
    """
    # This would need a reference to the running client,
    # which is only available during run_bot(). For webhook-triggered
    # notifications, use the Flask /api/openclaw/notify endpoint instead.
    logger.debug("Discord send_to_owner called but requires running bot context")
    return False


def run_bot() -> None:
    """Start the Discord bot (blocking)."""
    client = create_bot()
    if client is None:
        logger.error("Cannot start Discord bot — missing deps or token")
        return

    cfg = _get_config()
    logger.info("Starting OpenClaw Discord bot...")
    client.run(cfg["token"], log_handler=None)
