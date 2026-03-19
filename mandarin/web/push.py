"""Web push notification sender using pywebpush + VAPID.

Sends push notifications to users who have registered web push subscriptions.
Requires VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY environment variables.
"""

import json
import logging
import sqlite3

from ..settings import VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS_EMAIL, BASE_URL

logger = logging.getLogger(__name__)

try:
    from pywebpush import webpush, WebPushException
    _HAS_WEBPUSH = True
except ImportError:
    _HAS_WEBPUSH = False


def send_push(subscription_json: str, title: str, body: str, url: str = "/") -> bool:
    """Send a web push notification to a single subscription.

    Args:
        subscription_json: JSON string of the PushSubscription object.
        title: Notification title.
        body: Notification body text.
        url: URL to open when notification is clicked.

    Returns True if sent successfully.
    """
    if not _HAS_WEBPUSH:
        logger.info("[push dev-mode] title=%s body=%s", title, body)
        return True

    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.info("[push dev-mode] VAPID keys not configured: title=%s body=%s", title, body)
        return True

    try:
        subscription_info = json.loads(subscription_json)
    except (json.JSONDecodeError, TypeError):
        logger.error("Invalid subscription JSON")
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/static/favicon.svg",
    })

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
        )
        logger.info("Push sent: title=%s", title)
        return True
    except WebPushException as e:
        logger.error("Push failed: %s", e)
        return False
    except Exception as e:
        logger.exception("Push error: %s", e)
        return False


def send_push_to_user(conn: sqlite3.Connection, user_id: int,
                      title: str, body: str, url: str = "/") -> int:
    """Send a push notification to all of a user's registered web subscriptions.

    Returns the number of successfully sent notifications.
    """
    rows = conn.execute(
        "SELECT token FROM push_token WHERE user_id = ? AND platform = 'web'",
        (user_id,)
    ).fetchall()

    sent = 0
    for row in rows:
        if send_push(row["token"], title, body, url):
            sent += 1
    return sent


def build_modality_aware_notification(conn, user_id: int) -> tuple[str, str]:
    """Build push notification content that mentions modalities awaiting review.

    Instead of generic "X items ready for review (~Y minutes)", includes
    modality context: "8 items + 1 reading passage ready (~6 minutes)."
    DOCTRINE §6: one notification per day, informational, never guilt.

    Returns (title, body).
    """
    try:
        # Core drill items due
        items_due = conn.execute(
            """SELECT COUNT(*) FROM progress
               WHERE user_id = ? AND next_review <= datetime('now')
               AND mastery_stage NOT IN ('durable')""",
            (user_id,)
        ).fetchone()[0]

        # Reading passages available (check if reading block would be picked)
        reading_available = conn.execute(
            """SELECT COUNT(*) FROM reading_texts
               WHERE hsk_level <= (
                   SELECT COALESCE(level_reading, 1) FROM learner_profile WHERE user_id = ?
               )""",
            (user_id,)
        ).fetchone()[0]

        # Estimate time
        minutes = max(1, round(items_due * 35 / 60))

        parts = []
        if items_due > 0:
            parts.append(f"{items_due} item{'s' if items_due != 1 else ''}")
        if reading_available > 0:
            parts.append("1 reading passage")

        if not parts:
            return ("Review ready", "Your study session is ready when you are.")

        content = " + ".join(parts)
        body = f"{content} ready (~{minutes} min)"

        return ("Study session ready", body)

    except Exception:
        # Fallback to generic
        return ("Review ready", "Items ready for review.")
