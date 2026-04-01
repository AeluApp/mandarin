"""Matrix messaging client for Beeper/iMessage integration.

Sends notifications via the Matrix Client-Server API using plain HTTP
requests — no SDK dependency. All methods gracefully no-op when
MATRIX_ACCESS_TOKEN is not configured, so callers never need to check.

Matrix API endpoints used:
  POST /_matrix/client/v3/createRoom          (create DM room)
  PUT  /_matrix/client/v3/rooms/{roomId}/send  (send message)
  POST /_matrix/client/v3/sync                (poll for replies)
  GET  /_matrix/client/v3/joined_rooms        (list rooms)

Beeper routes messages through iMessage when the recipient is a Beeper
user with an iMessage bridge configured.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from html import escape as _esc

import requests

from ..settings import MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_USER_ID, MATRIX_ROOM_ID

logger = logging.getLogger(__name__)

# Module-level cache: once we find/create a DM room, reuse it.
_dm_room_id: str | None = None

# Timeout for Matrix HTTP requests (seconds).
_HTTP_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {MATRIX_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _api(path: str) -> str:
    """Build a full Matrix API URL."""
    base = MATRIX_HOMESERVER.rstrip("/")
    return f"{base}{path}"


def _is_configured() -> bool:
    """Return True only when Matrix credentials are present."""
    return bool(MATRIX_ACCESS_TOKEN and MATRIX_HOMESERVER and MATRIX_USER_ID)


def _txn_id() -> str:
    """Generate a unique transaction ID for idempotent Matrix sends."""
    return f"aelu_{int(time.time())}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Room management
# ---------------------------------------------------------------------------

def _find_existing_dm_room() -> str | None:
    """Check joined rooms for an existing DM with the configured user.

    Looks at the m.direct account data to find a room already tagged as
    a direct message with MATRIX_USER_ID.
    """
    try:
        resp = requests.get(
            _api("/_matrix/client/v3/user/{user}/account_data/m.direct".format(
                user=requests.utils.quote(MATRIX_USER_ID, safe=""),
            )),
            headers=_headers(),
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            rooms = data.get(MATRIX_USER_ID, [])
            if rooms:
                return rooms[0]
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.debug("Matrix: could not look up existing DM room: %s", exc)

    return None


def _create_dm_room() -> str | None:
    """Create a new direct-message room with the configured Matrix user."""
    try:
        resp = requests.post(
            _api("/_matrix/client/v3/createRoom"),
            headers=_headers(),
            json={
                "invite": [MATRIX_USER_ID],
                "is_direct": True,
                "preset": "trusted_private_chat",
                "name": "Aelu Notifications",
            },
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            room_id = resp.json().get("room_id")
            logger.info("Matrix: created DM room %s with %s", room_id, MATRIX_USER_ID)
            return room_id
        else:
            logger.error(
                "Matrix: createRoom failed %s: %s", resp.status_code, resp.text
            )
    except (requests.RequestException, ValueError) as exc:
        logger.error("Matrix: createRoom request error: %s", exc)

    return None


def _get_dm_room() -> str | None:
    """Get (or create) the DM room ID. Cached after first call."""
    global _dm_room_id
    if _dm_room_id:
        return _dm_room_id

    # Try to find an existing DM first.
    room_id = _find_existing_dm_room()
    if room_id:
        _dm_room_id = room_id
        return _dm_room_id

    # Create a new DM room.
    room_id = _create_dm_room()
    if room_id:
        _dm_room_id = room_id

    return _dm_room_id


# ---------------------------------------------------------------------------
# Core send
# ---------------------------------------------------------------------------

def send_message(
    room_id_or_user: str,
    message: str,
    html_message: str | None = None,
) -> bool:
    """Send a text (or HTML) message to a Matrix room or user.

    Args:
        room_id_or_user: A room ID (starting with ``!``) or a Matrix user
            ID (starting with ``@``). When a user ID is given, the message
            is sent to the DM room with that user.
        message: Plain-text message body.
        html_message: Optional HTML-formatted body. When provided the
            message is sent as ``org.matrix.custom.html``.

    Returns:
        True on success, False on failure. Always returns True (no-op)
        when Matrix is not configured.
    """
    if not _is_configured():
        logger.debug("Matrix: not configured, skipping send_message")
        return True

    # Resolve target room.
    if room_id_or_user.startswith("!"):
        room_id = room_id_or_user
    elif room_id_or_user.startswith("@"):
        room_id = _get_dm_room()
        if not room_id:
            logger.error("Matrix: cannot resolve DM room for %s", room_id_or_user)
            return False
    else:
        # Assume it's a room ID or alias.
        room_id = room_id_or_user

    txn = _txn_id()
    body: dict = {
        "msgtype": "m.text",
        "body": message,
    }
    if html_message:
        body["format"] = "org.matrix.custom.html"
        body["formatted_body"] = html_message

    try:
        url = _api(
            f"/_matrix/client/v3/rooms/{requests.utils.quote(room_id, safe='')}"
            f"/send/m.room.message/{txn}"
        )
        resp = requests.put(
            url,
            headers=_headers(),
            json=body,
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            logger.info("Matrix: message sent to %s", room_id)
            return True
        else:
            logger.error(
                "Matrix: send failed %s: %s", resp.status_code, resp.text
            )
            return False
    except (requests.RequestException, ValueError) as exc:
        logger.error("Matrix: send request error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# High-level notification methods
# ---------------------------------------------------------------------------

def send_notification(message: str, html_message: str | None = None) -> bool:
    """Send a notification to the configured room or DM.

    Uses MATRIX_ROOM_ID directly when set (avoids DM-with-self lookup issues).
    Falls back to MATRIX_USER_ID DM resolution when no room ID is configured.
    """
    if not _is_configured():
        logger.debug("Matrix: not configured, skipping notification")
        return True
    target = MATRIX_ROOM_ID if MATRIX_ROOM_ID else MATRIX_USER_ID
    return send_message(target, message, html_message)


def send_approval_request(post: dict) -> bool:
    """Send a formatted approval request for a marketing post.

    Args:
        post: Dict with keys ``id``, ``subreddit``, ``title``, ``body``,
            and optionally ``platform``.

    The message includes the post content and instructions to reply
    ``approve`` or ``reject`` directly in the chat.
    """
    if not _is_configured():
        return True

    post_id = post.get("id", "?")
    subreddit = post.get("subreddit", "")
    title = post.get("title", "")
    body = post.get("body", "")
    platform = post.get("platform", "reddit")

    plain = (
        f"--- Post Approval Request ---\n"
        f"Platform: {platform}\n"
        f"Subreddit: r/{subreddit}\n"
        f"Title: {title}\n"
        f"---\n"
        f"{body}\n"
        f"---\n"
        f"Reply \"approve {post_id}\" or \"reject {post_id}\" to act on this post."
    )

    html = (
        f"<h3>Post Approval Request</h3>"
        f"<table>"
        f"<tr><td><strong>Platform</strong></td><td>{_esc(platform)}</td></tr>"
        f"<tr><td><strong>Subreddit</strong></td>"
        f"<td><code>r/{_esc(subreddit)}</code></td></tr>"
        f"<tr><td><strong>Title</strong></td><td>{_esc(title)}</td></tr>"
        f"</table>"
        f"<blockquote>{_esc(body)}</blockquote>"
        f"<p>Reply <code>approve {_esc(str(post_id))}</code> or "
        f"<code>reject {_esc(str(post_id))}</code> to act on this post.</p>"
    )

    return send_notification(plain, html)


def send_alert(subject: str, details: str) -> bool:
    """Send a critical alert (downtime, cost limits, etc.).

    Args:
        subject: Short summary line (e.g. "Monitors Down").
        details: Longer explanation text.
    """
    if not _is_configured():
        return True

    plain = f"ALERT: {subject}\n\n{details}"
    html = (
        f"<h3>Alert: {_esc(subject)}</h3>"
        f"<pre>{_esc(details)}</pre>"
    )
    return send_notification(plain, html)


def send_daily_digest(stats: dict) -> bool:
    """Send a compact daily digest of what happened today.

    Args:
        stats: Dict with keys like ``posts_queued``, ``posts_approved``,
            ``posts_rejected``, ``uptime_pct``, ``errors_count``,
            ``self_healing_actions``, ``active_users``, etc.
            All are optional — missing keys are omitted from output.
    """
    if not _is_configured():
        return True

    lines = ["--- Aelu Daily Digest ---"]
    html_rows = ""

    stat_labels = {
        "posts_queued": "Posts Queued",
        "posts_approved": "Posts Approved",
        "posts_rejected": "Posts Rejected",
        "uptime_pct": "Uptime",
        "errors_count": "Errors",
        "self_healing_actions": "Self-Healing Actions",
        "active_users": "Active Users",
        "llm_cost_today": "LLM Cost Today",
    }

    for key, label in stat_labels.items():
        value = stats.get(key)
        if value is not None:
            display = f"{value}%" if key == "uptime_pct" else str(value)
            if key == "llm_cost_today" and isinstance(value, (int, float)):
                display = f"${value:.2f}"
            lines.append(f"  {label}: {display}")
            html_rows += (
                f"<tr><td><strong>{_esc(label)}</strong></td>"
                f"<td>{_esc(display)}</td></tr>"
            )

    plain = "\n".join(lines)
    html = f"<h3>Aelu Daily Digest</h3><table>{html_rows}</table>"

    return send_notification(plain, html)


# ---------------------------------------------------------------------------
# Reply polling (for two-way approval flow)
# ---------------------------------------------------------------------------

# Sync token persisted in memory (resets on app restart — acceptable for
# a lightweight polling setup).
_sync_token: str | None = None


def poll_replies() -> list[dict]:
    """Poll the DM room for new messages and return parsed commands.

    Returns a list of dicts like:
        [{"action": "approve", "post_id": 42}, ...]

    Only ``approve <id>`` and ``reject <id>`` messages are recognized.
    All other messages are ignored.
    """
    global _sync_token

    if not _is_configured():
        return []

    room_id = _get_dm_room()
    if not room_id:
        return []

    # Build sync filter: only the DM room, only m.room.message events.
    sync_filter = json.dumps({
        "room": {
            "rooms": [room_id],
            "timeline": {"types": ["m.room.message"], "limit": 50},
            "state": {"types": []},
            "ephemeral": {"types": []},
        },
        "presence": {"types": []},
        "account_data": {"types": []},
    })

    params: dict = {
        "filter": sync_filter,
        "timeout": "5000",  # 5 second long-poll (short to avoid blocking)
    }
    if _sync_token:
        params["since"] = _sync_token

    try:
        resp = requests.get(
            _api("/_matrix/client/v3/sync"),
            headers=_headers(),
            params=params,
            timeout=_HTTP_TIMEOUT + 10,  # slightly more than long-poll
        )
        if resp.status_code != 200:
            logger.warning("Matrix sync: %s %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()
        _sync_token = data.get("next_batch", _sync_token)

        commands = []
        rooms = data.get("rooms", {}).get("join", {})
        room_data = rooms.get(room_id, {})
        events = room_data.get("timeline", {}).get("events", [])

        for event in events:
            # Skip our own messages.
            sender = event.get("sender", "")
            if sender != MATRIX_USER_ID:
                continue

            content = event.get("content", {})
            body = (content.get("body") or "").strip().lower()

            # Parse "approve <id>" or "reject <id>"
            for action in ("approve", "reject"):
                if body.startswith(action):
                    rest = body[len(action):].strip()
                    try:
                        post_id = int(rest)
                        commands.append({"action": action, "post_id": post_id})
                    except (ValueError, TypeError):
                        pass

        return commands

    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Matrix sync error: %s", exc)
        return []


def process_approval_commands(commands: list[dict]) -> list[str]:
    """Process parsed approval/reject commands from Matrix replies.

    Applies each command to the marketing_post_queue and returns a list
    of human-readable result strings (also sent back to the DM as
    confirmation).

    Args:
        commands: List from poll_replies().

    Returns:
        List of result description strings.
    """
    if not commands:
        return []

    results = []
    try:
        from .. import db
    except ImportError:
        logger.error("Matrix: cannot import db module for approval processing")
        return []

    for cmd in commands:
        action = cmd["action"]
        post_id = cmd["post_id"]

        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT id, status, title, subreddit FROM marketing_post_queue WHERE id = ?",
                    (post_id,),
                ).fetchone()

                if not row:
                    msg = f"Post #{post_id} not found."
                    results.append(msg)
                    send_notification(msg)
                    continue

                current_status = row["status"]

                if action == "approve":
                    if current_status not in ("pending", "ready_to_post"):
                        msg = f"Post #{post_id} is '{current_status}', cannot approve."
                        results.append(msg)
                        send_notification(msg)
                        continue
                    conn.execute(
                        "UPDATE marketing_post_queue SET status = 'approved', reviewed_at = datetime('now') WHERE id = ?",
                        (post_id,),
                    )
                    conn.commit()
                    msg = f"Post #{post_id} (r/{row['subreddit']}: {row['title']}) approved."
                    results.append(msg)
                    send_notification(msg)

                elif action == "reject":
                    if current_status not in ("pending", "ready_to_post"):
                        msg = f"Post #{post_id} is '{current_status}', cannot reject."
                        results.append(msg)
                        send_notification(msg)
                        continue
                    conn.execute(
                        "UPDATE marketing_post_queue SET status = 'rejected', reviewed_at = datetime('now'), reject_reason = 'Rejected via Matrix' WHERE id = ?",
                        (post_id,),
                    )
                    conn.commit()
                    msg = f"Post #{post_id} (r/{row['subreddit']}: {row['title']}) rejected."
                    results.append(msg)
                    send_notification(msg)

        except Exception as exc:
            msg = f"Error processing {action} for post #{post_id}: {exc}"
            logger.exception(msg)
            results.append(msg)

    return results
