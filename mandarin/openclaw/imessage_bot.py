"""OpenClaw iMessage bot — macOS-native Messages.app integration.

Uses AppleScript to send messages and reads ~/Library/Messages/chat.db
(SQLite) to poll for inbound messages. Zero external dependencies.

macOS only. Requires Full Disk Access for chat.db reading
(System Settings > Privacy & Security > Full Disk Access > Terminal).

Setup:
1. Set OPENCLAW_IMESSAGE_OWNER_ID to your phone number or Apple ID email
2. Grant Full Disk Access to your terminal app
3. Run: ./run imessage
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import commands, llm_handler, security

logger = logging.getLogger(__name__)

CHAT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"
POLL_INTERVAL = 5  # seconds


def _get_config():
    """Read config at call time."""
    from ..settings import OPENCLAW_IMESSAGE_OWNER_ID
    return {
        "owner_id": OPENCLAW_IMESSAGE_OWNER_ID,
    }


def is_configured() -> bool:
    """Check if iMessage is available and configured."""
    cfg = _get_config()
    return bool(cfg["owner_id"]) and _is_macos() and CHAT_DB_PATH.exists()


def _is_macos() -> bool:
    """Check if running on macOS."""
    import platform
    return platform.system() == "Darwin"


def send_message(to: str, text: str) -> bool:
    """Send an iMessage via AppleScript.

    Args:
        to: Phone number (+1234567890) or Apple ID email
        text: Message body
    """
    if not _is_macos():
        logger.debug("Not macOS — iMessage unavailable")
        return False

    # Escape for AppleScript
    escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
    escaped_to = to.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "Messages"
        set targetBuddy to buddy "{escaped_to}" of service 1
        send "{escaped_text}" to targetBuddy
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True
        logger.warning("iMessage send failed: %s", result.stderr[:200])
        return False
    except subprocess.TimeoutExpired:
        logger.warning("iMessage send timed out")
        return False
    except Exception as e:
        logger.error("iMessage send error: %s", e)
        return False


def send_to_owner(text: str) -> bool:
    """Send a message to the configured owner."""
    cfg = _get_config()
    if not cfg["owner_id"]:
        return False
    return send_message(cfg["owner_id"], text)


def _get_recent_messages(since_rowid: int, owner_id: str) -> list[dict]:
    """Read recent inbound messages from chat.db.

    Returns messages newer than since_rowid from the owner.
    """
    if not CHAT_DB_PATH.exists():
        return []

    try:
        conn = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Find the chat handle for the owner
        rows = conn.execute("""
            SELECT m.ROWID, m.text, m.date, m.is_from_me,
                   h.id as handle_id
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.ROWID > ?
              AND m.is_from_me = 0
              AND m.text IS NOT NULL
              AND m.text != ''
              AND h.id = ?
            ORDER BY m.ROWID ASC
            LIMIT 10
        """, (since_rowid, owner_id)).fetchall()

        messages = []
        for r in rows:
            messages.append({
                "rowid": r["ROWID"],
                "text": r["text"],
                "handle": r["handle_id"],
            })
        conn.close()
        return messages

    except Exception as e:
        logger.debug("Failed to read chat.db: %s", e)
        return []


def _get_latest_rowid() -> int:
    """Get the current max ROWID from chat.db."""
    if not CHAT_DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True)
        row = conn.execute("SELECT MAX(ROWID) FROM message").fetchone()
        conn.close()
        return row[0] or 0
    except Exception:
        return 0


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
        "session": lambda: "Open the Aelu app to start a session.",
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
            logger.error("iMessage command %s failed: %s", intent, e, exc_info=True)
            return f"Error running {intent}."

    if intent_result.reply:
        return intent_result.reply
    return llm_handler.generate_chat_response("", conn=conn)


def _process_message(text: str, owner_id: str) -> str:
    """Process a single inbound message and return the response."""
    conn = None
    try:
        from .. import db
        conn = db.connection().__enter__()
    except Exception:
        pass

    try:
        clean_text = security.sanitize_input(text)

        is_safe, detail = security.check_prompt_injection(clean_text)
        if not is_safe:
            if conn:
                security.log_message(
                    conn, direction="inbound", channel="imessage",
                    message_text=clean_text, user_identifier=owner_id[:6],
                    injection_detected=True, injection_detail=detail or "",
                )
            return "I couldn't process that. Try /status or /review."

        user_id_short = owner_id[:20]
        intent_result = llm_handler.classify_intent(clean_text, conn=conn, user_id=user_id_short)
        response = _execute_intent(intent_result, conn)

        if conn:
            security.log_message(
                conn, direction="inbound", channel="imessage",
                message_text=clean_text, user_identifier=owner_id[:6],
                intent=intent_result.intent,
                tool_called=f"cmd_{intent_result.intent}" if intent_result.intent != "chat" else "",
                tool_result=response[:500],
            )

        # Store conversation turn in memory
        try:
            from ..ai.memory import add_memory
            add_memory(user_id_short, clean_text, response, channel="imessage")
        except (ImportError, Exception):
            pass

        return security.sanitize_output(response) or "Try /help."

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def run_bot() -> None:
    """Start the iMessage polling loop (blocking).

    Polls chat.db for new messages from the owner, processes them,
    and sends replies via AppleScript.
    """
    cfg = _get_config()
    if not cfg["owner_id"]:
        logger.error("OPENCLAW_IMESSAGE_OWNER_ID not set")
        return

    if not _is_macos():
        logger.error("iMessage bot requires macOS")
        return

    if not CHAT_DB_PATH.exists():
        logger.error("Messages database not found at %s", CHAT_DB_PATH)
        logger.error("Grant Full Disk Access: System Settings > Privacy & Security > Full Disk Access")
        return

    logger.info("Starting OpenClaw iMessage bot (polling %s)...", cfg["owner_id"])
    logger.info("Tip: Grant Full Disk Access to Terminal for chat.db reading")

    # Start from current position (don't replay history)
    last_rowid = _get_latest_rowid()
    logger.info("Starting from message ROWID %d", last_rowid)

    # Send startup message
    send_message(cfg["owner_id"], "Aelu OpenClaw active via iMessage. Type /help for commands.")

    try:
        while True:
            messages = _get_recent_messages(last_rowid, cfg["owner_id"])
            for msg in messages:
                last_rowid = msg["rowid"]
                text = msg["text"]
                logger.info("iMessage from %s: %s", cfg["owner_id"][:6], text[:50])

                response = _process_message(text, cfg["owner_id"])
                send_message(cfg["owner_id"], response)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("iMessage bot stopped")
    except Exception as e:
        logger.error("iMessage bot error: %s", e, exc_info=True)
