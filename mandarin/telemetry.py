"""Canonical client event definitions and ingestion helpers.

Single source of truth for all client-side telemetry event categories
and names. Used by the /api/client-events ingestion endpoint for schema
validation and by any future analytics queries.
"""

# Valid (category, event) pairs. If a category maps to None, any event
# name is accepted (open-ended). If it maps to a set, only those event
# names are accepted.
VALID_EVENTS = {
    "paywall": {"shown", "click", "checkout_started", "dismiss", "rage_bounce"},
    "nav": {"transition"},
    "session": {"start", "early_exit", "complete"},
    "ws": {"open", "close", "error", "server_error"},
    "audio": {"unavailable", "permission_error"},
    "view": {"reading", "grammar", "media", "listening"},
    "grammar": {"open_point", "mark_studied"},
    "nps": {"submitted", "share"},
    "report": {"opened", "sent", "downloaded"},
    "adoption": None,  # open-ended — feature names vary
    "error": {"unhandled", "promise"},
    "activation": {"first_lookup", "first_encounter_drilled", "first_session",
                    "first_week", "first_streak"},
    "drill_timing": {"response", "gap", "first_drill_latency"},
    "ux": {"rage_click", "dead_click", "nav_depth"},
    "onboarding": {"step_view", "step_complete", "step_skip"},
}

# Canonical lifecycle event types for the activation funnel
ACTIVATION_EVENTS = {
    "signup",
    "first_session",
    "first_lookup",            # First word looked up during reading
    "encounter_drilled",       # A looked-up word appeared in a drill session
    "first_encounter_drilled", # First time the lookup→drill loop completes for a user
    "session_complete",
    "activation",              # User hits activation criteria (3 sessions in 14 days)
    "milestone_reached",
}

# Max events per install_id per hour (server-side rate limit)
RATE_LIMIT_PER_HOUR = 500


def is_valid_event(category: str, event: str) -> bool:
    """Check if a (category, event) pair is in the canonical schema."""
    if category not in VALID_EVENTS:
        return False
    allowed = VALID_EVENTS[category]
    if allowed is None:
        return True  # open-ended category
    return event in allowed
