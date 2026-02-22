"""Database package — re-exports all public API for backward compatibility.

All existing code using `from . import db` or `from .. import db`
continues to work via `db.function_name()` unchanged.
"""

# Core: connection, schema, migrations
from .core import (
    DB_DIR, DB_PATH, SCHEMA_PATH, PROFILE_JSON_PATH,
    load_learner_profile_json,
    get_connection, init_db, ensure_db, connection,
    SCHEMA_VERSION,
)

# Content: content_item CRUD
from .content import (
    insert_content_item, seed_context_notes, seed_constructions,
    get_items_due, get_new_items, content_count,
)

# Progress: SRS, attempts, mastery, error focus
from .progress import (
    DRILL_DIRECTION_MAP,
    record_attempt, update_error_focus,
    get_error_focus_items, get_resolved_this_session,
    get_mastery_by_hsk,
    get_stage_transitions, get_items_due_count, get_new_items_available,
)

# Session: lifecycle, history
from .session import (
    start_session, end_session, update_session_progress,
    get_session_history, get_days_since_last_session,
    get_error_summary, get_session_funnel,
)

# Profile
from .profile import get_profile

# Curriculum: grammar, skills, HSK
from .curriculum import (
    get_grammar_points, get_skills,
    link_content_grammar, link_content_skill,
    get_core_lexicon_coverage, get_core_catchup_items,
    get_skill_coverage, should_suggest_next_hsk,
)
