"""Tier gating — free vs paid feature access."""

import sqlite3

# Free tier limits
FREE_HSK_MAX = 2
FREE_SESSIONS_PER_DAY = 3
FREE_DRILL_TYPES = {"mc", "reverse_mc", "ime_type", "tone", "listening_gist"}

# Features gated behind paid tier
PAID_FEATURES = {
    "hsk_3_plus",
    "all_drill_types",
    "unlimited_sessions",
    "reading",
    "media",
    "listening",
    "export",
    "forecast",
}


def get_user_tier(conn: sqlite3.Connection, user_id: int) -> str:
    """Return 'free', 'paid', or 'admin' for a user."""
    row = conn.execute(
        "SELECT subscription_tier FROM user WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        return "free"
    return row["subscription_tier"] or "free"


def check_tier_access(conn: sqlite3.Connection, user_id: int, feature: str) -> bool:
    """Check if a user has access to a feature based on their tier.

    Returns True if access is allowed.
    """
    tier = get_user_tier(conn, user_id)
    if tier in ("paid", "admin"):
        return True
    # Free tier — check if feature requires payment
    return feature not in PAID_FEATURES


def get_daily_session_count(conn: sqlite3.Connection, user_id: int) -> int:
    """Count sessions completed today by this user."""
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM session_log
           WHERE user_id = ? AND date(started_at) = date('now')
             AND items_completed > 0""",
        (user_id,)
    ).fetchone()
    return row["cnt"] if row else 0


def check_session_limit(conn: sqlite3.Connection, user_id: int) -> bool:
    """Check if user can start another session today.

    Returns True if allowed.
    """
    tier = get_user_tier(conn, user_id)
    if tier in ("paid", "admin"):
        return True
    return get_daily_session_count(conn, user_id) < FREE_SESSIONS_PER_DAY


def filter_items_by_tier(items: list, tier: str) -> list:
    """Filter content items by tier HSK level restriction."""
    if tier in ("paid", "admin"):
        return items
    return [i for i in items if (i.get("hsk_level") or 1) <= FREE_HSK_MAX]


def filter_drills_by_tier(drills: list, tier: str) -> list:
    """Filter drill items by tier drill type restriction."""
    if tier in ("paid", "admin"):
        return drills
    return [d for d in drills if d.drill_type in FREE_DRILL_TYPES]
