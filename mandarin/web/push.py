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
