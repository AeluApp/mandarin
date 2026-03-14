"""Shared middleware helpers for route files."""

import logging
from datetime import date as dt_date, datetime, timedelta, timezone

from flask import abort, request
from flask_login import current_user

logger = logging.getLogger(__name__)


def paginate_params(default_per_page=50, max_per_page=100):
    """Extract page/per_page/offset from query string.

    Returns (page, per_page, offset, user_id).
    """
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(max_per_page, max(1, request.args.get("per_page", default_per_page, type=int)))
    user_id = request.args.get("user_id", type=int)
    offset = (page - 1) * per_page
    return page, per_page, offset, user_id


def _get_user_id():
    """Return current_user.id or abort 401."""
    if current_user.is_authenticated:
        return current_user.id
    abort(401)


def _sanitize_error(e: Exception) -> str:
    """Convert an exception to a user-friendly message.

    Never expose stack traces or internal details to the browser.
    """
    msg = str(e)
    if "no such table" in msg:
        return "Database needs setup. Run: ./run add-hsk 1"
    if "database is locked" in msg:
        return "Database is busy. Try again in a moment."
    if "no drills" in msg.lower() or "no items" in msg.lower():
        return "No items available for drilling. Import some content first."
    logger.error("session error (sanitized): %s", msg)
    return "Something went wrong. Reload to try again."


def _compute_streak(conn, user_id: int = 1) -> int:
    """Compute current consecutive-day study streak."""
    rows = conn.execute(
        """SELECT DISTINCT date(started_at) as d
           FROM session_log
           WHERE user_id = ? AND items_completed > 0
             AND started_at >= date('now', '-90 days')
           ORDER BY d DESC""",
        (user_id,)
    ).fetchall()
    if not rows:
        return 0
    dates = []
    for r in rows:
        try:
            dates.append(dt_date.fromisoformat(r["d"]))
        except (ValueError, TypeError):
            pass
    if not dates:
        return 0
    # Use UTC date to match SQLite's date() which operates in UTC
    today = datetime.now(timezone.utc).date()
    if dates[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak
