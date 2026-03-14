"""Tier gating — free vs paid feature access."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Free tier limits
FREE_HSK_MAX = 2
FREE_SESSIONS_PER_DAY = 3
FREE_DRILL_TYPES = {"mc", "reverse_mc", "ime_type", "tone", "listening_gist"}
FREE_READING_HSK_MAX = 1  # HSK 1 reading passages available on free tier
FREE_LISTENING_HSK_MAX = 2  # HSK 1-2 listening passages available on free tier
FREE_MEDIA_HSK_MAX = 1  # HSK 1 media available on free tier

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

# Premium-only features (student upgrade on top of classroom access)
# Premium inherits all paid features plus these extras.
PREMIUM_FEATURES = {
    "priority_scheduling",   # Encounter-boost items processed first
    "export_csv",            # CSV progress downloads
    "export_json",           # JSON progress downloads
    "advanced_analytics",    # Forecast, detailed diagnostics, error trend graphs
}


def get_user_tier(conn: sqlite3.Connection, user_id: int) -> str:
    """Return 'free', 'paid', or 'admin' for a user."""
    row = conn.execute(
        "SELECT subscription_tier, is_admin FROM user WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        return "free"
    if row["is_admin"]:
        return "admin"
    return row["subscription_tier"] or "free"


def check_tier_access(conn: sqlite3.Connection, user_id: int, feature: str) -> bool:
    """Check if a user has access to a feature based on their tier.

    Returns True if access is allowed.
    """
    tier = get_user_tier(conn, user_id)
    if tier in ("paid", "admin", "teacher", "premium"):
        return True
    # Free tier — check if feature requires payment
    allowed = feature not in PAID_FEATURES
    if not allowed:
        logger.info("Tier gate denied: user_id=%d (tier=%s) feature=%r", user_id, tier, feature)
    return allowed


def check_premium_access(conn: sqlite3.Connection, user_id: int, feature: str) -> bool:
    """Check if a user has access to a premium-only feature.

    Premium features are available to 'premium', 'admin', and 'paid' tiers.
    Classroom students (teacher-enrolled, no individual subscription) do NOT
    get premium features — they must upgrade individually.
    """
    tier = get_user_tier(conn, user_id)
    if tier in ("premium", "admin", "paid"):
        return True
    if feature in PREMIUM_FEATURES:
        logger.info("Premium gate denied: user_id=%d (tier=%s) feature=%r", user_id, tier, feature)
        return False
    # Non-premium features fall through to standard tier check
    return check_tier_access(conn, user_id, feature)


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
    if tier in ("paid", "admin", "teacher", "premium"):
        return True
    return get_daily_session_count(conn, user_id) < FREE_SESSIONS_PER_DAY


def filter_items_by_tier(items: list, tier: str) -> list:
    """Filter content items by tier HSK level restriction."""
    if tier in ("paid", "admin", "teacher", "premium"):
        return items
    return [i for i in items if (i.get("hsk_level") or 1) <= FREE_HSK_MAX]


def filter_drills_by_tier(drills: list, tier: str) -> list:
    """Filter drill items by tier drill type restriction."""
    if tier in ("paid", "admin", "teacher", "premium"):
        return drills
    return [d for d in drills if d.drill_type in FREE_DRILL_TYPES]
