"""OpenClaw Signal bot — two-way messaging via Beeper/Matrix bridge.

Signal messages arrive as Matrix room events via Beeper's cloud bridge.
The bot polls the bridged room, classifies intent, dispatches commands,
and replies through Matrix → Beeper → Signal.

Works from Fly.io (Linux) — no Mac or local Signal client needed.
"""

import json
import logging
import re
import time
import uuid

import requests

from ..settings import (
    MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_USER_ID,
    OPENCLAW_SIGNAL_NUMBER,
)
from . import commands, llm_handler, security

logger = logging.getLogger(__name__)

# Polling state — separate from matrix_client.py's _sync_token
_sync_token: str | None = None

# Signal room cache
_signal_room_id: str | None = None

_HTTP_TIMEOUT = 15


def is_configured() -> bool:
    """Return True if Signal bot can run."""
    return bool(MATRIX_ACCESS_TOKEN and MATRIX_HOMESERVER and OPENCLAW_SIGNAL_NUMBER)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {MATRIX_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _api(path: str) -> str:
    return f"{MATRIX_HOMESERVER.rstrip('/')}{path}"


# ── Room discovery ───────────────────────────────────────────


def _find_signal_room() -> str | None:
    """Find the Matrix room bridged from Signal for the owner's number.

    Beeper bridges Signal contacts into Matrix rooms. The room typically
    has a member whose Matrix ID contains the phone number.
    """
    global _signal_room_id
    if _signal_room_id:
        return _signal_room_id

    # Normalize phone number: strip +, spaces, dashes
    phone_digits = re.sub(r"[^0-9]", "", OPENCLAW_SIGNAL_NUMBER)

    try:
        resp = requests.get(
            _api("/_matrix/client/v3/joined_rooms"),
            headers=_headers(),
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return None

        for room_id in resp.json().get("joined_rooms", []):
            # Check room members for a Signal-bridged identity
            try:
                members_resp = requests.get(
                    _api(f"/_matrix/client/v3/rooms/{requests.utils.quote(room_id, safe='')}/members"),
                    headers=_headers(),
                    params={"membership": "join"},
                    timeout=_HTTP_TIMEOUT,
                )
                if members_resp.status_code != 200:
                    continue

                for event in members_resp.json().get("chunk", []):
                    sender = event.get("sender", "")
                    # Beeper Signal bridge creates IDs like @signal_16789239236:beeper.com
                    if "signal" in sender.lower() and phone_digits in sender:
                        _signal_room_id = room_id
                        logger.info("Signal bot: found bridged room %s (member %s)",
                                    room_id, sender)
                        return room_id
            except requests.RequestException:
                continue

    except (requests.RequestException, ValueError) as exc:
        logger.debug("Signal bot: room discovery failed: %s", exc)

    # Fallback: check for "Aelu Notifications" room
    try:
        from ..notifications.matrix_client import _find_dm_room_via_joined
        room = _find_dm_room_via_joined()
        if room:
            _signal_room_id = room
            return room
    except Exception:
        pass

    return None


def _validate_signal_sender(sender_mxid: str) -> bool:
    """Check if a Matrix user ID belongs to the Signal owner."""
    if sender_mxid == MATRIX_USER_ID:
        return True  # Owner's own Beeper account
    phone_digits = re.sub(r"[^0-9]", "", OPENCLAW_SIGNAL_NUMBER)
    return "signal" in sender_mxid.lower() and phone_digits in sender_mxid


# ── Message handling ─────────────────────────────────────────


def _send_reply(room_id: str, message: str) -> bool:
    """Send a reply to the Signal room via Matrix."""
    txn = f"aelu_signal_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    try:
        url = _api(
            f"/_matrix/client/v3/rooms/{requests.utils.quote(room_id, safe='')}"
            f"/send/m.room.message/{txn}"
        )
        resp = requests.put(
            url, headers=_headers(),
            json={"msgtype": "m.text", "body": message},
            timeout=_HTTP_TIMEOUT,
        )
        return resp.status_code in (200, 201)
    except requests.RequestException:
        return False


def handle_message(sender: str, text: str, room_id: str) -> None:
    """Process an inbound Signal message through the OpenClaw pipeline."""
    from .. import db

    # Owner check
    if not _validate_signal_sender(sender):
        logger.debug("Signal bot: ignoring message from non-owner %s", sender)
        return

    # Rate limit
    if not security.check_rate_limit("signal"):
        _send_reply(room_id, "Rate limit reached. Try again in a minute.")
        return

    # Sanitize
    clean_text = security.sanitize_input(text)
    if not clean_text:
        return

    # Injection check
    is_safe, detail = security.check_prompt_injection(clean_text)
    if not is_safe:
        logger.warning("Signal bot: injection attempt from %s: %s", sender, detail)
        with db.connection() as conn:
            security.log_message(
                conn, direction="inbound", channel="signal",
                message_text=clean_text, user_identifier=sender,
                injection_detected=True, injection_detail=detail or "",
            )
        _send_reply(room_id, "Message blocked by security filter.")
        return

    # Classify intent
    with db.connection() as conn:
        security.log_message(
            conn, direction="inbound", channel="signal",
            message_text=clean_text, user_identifier=sender,
        )

        intent_result = llm_handler.classify_intent(clean_text, conn=conn)
        response = commands.dispatch_intent(intent_result, conn)
        response = security.sanitize_output(response)

        # Log outbound
        security.log_message(
            conn, direction="outbound", channel="signal",
            message_text=response, intent=intent_result.intent,
        )

    _send_reply(room_id, response)


# ── Polling ──────────────────────────────────────────────────


def poll_once() -> int:
    """Poll the Signal room for new messages. Returns count of messages processed."""
    global _sync_token

    room_id = _find_signal_room()
    if not room_id:
        return 0

    sync_filter = json.dumps({
        "room": {
            "rooms": [room_id],
            "timeline": {"types": ["m.room.message"], "limit": 20},
            "state": {"types": []},
            "ephemeral": {"types": []},
        },
        "presence": {"types": []},
        "account_data": {"types": []},
    })

    params: dict = {
        "filter": sync_filter,
        "timeout": "5000",
    }
    if _sync_token:
        params["since"] = _sync_token

    try:
        resp = requests.get(
            _api("/_matrix/client/v3/sync"),
            headers=_headers(),
            params=params,
            timeout=_HTTP_TIMEOUT + 10,
        )
        if resp.status_code != 200:
            logger.warning("Signal bot sync: %s", resp.status_code)
            return 0

        data = resp.json()
        _sync_token = data.get("next_batch", _sync_token)

        processed = 0
        rooms = data.get("rooms", {}).get("join", {})
        room_data = rooms.get(room_id, {})
        events = room_data.get("timeline", {}).get("events", [])

        for event in events:
            sender = event.get("sender", "")
            # Skip our own messages (sent by the bot itself)
            if sender == MATRIX_USER_ID:
                continue

            content = event.get("content", {})
            msgtype = content.get("msgtype", "")
            body = (content.get("body") or "").strip()

            if msgtype == "m.text" and body:
                handle_message(sender, body, room_id)
                processed += 1

        return processed

    except (requests.RequestException, ValueError) as exc:
        logger.warning("Signal bot poll error: %s", exc)
        return 0
