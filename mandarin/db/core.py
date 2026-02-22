"""Database core — connection management, schema, migrations."""

from __future__ import annotations

import logging
import sqlite3
import json
from pathlib import Path
from datetime import datetime, date, timezone

logger = logging.getLogger(__name__)


from ..settings import DB_PATH as _SETTINGS_DB_PATH

DB_DIR = _SETTINGS_DB_PATH.parent
DB_PATH = _SETTINGS_DB_PATH
SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema.sql"
PROFILE_JSON_PATH = Path(__file__).parent.parent.parent / "learner_profile.json"


def load_learner_profile_json() -> dict[str, object]:
    """Load learner_profile.json from repo root. Returns empty dict if missing."""
    if PROFILE_JSON_PATH.exists():
        with open(PROFILE_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a database connection with proper settings."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Initialize the database from schema.sql. Idempotent."""
    conn = get_connection(db_path)
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
    return conn


def ensure_db() -> sqlite3.Connection:
    """Get a connection, initializing if needed."""
    if not DB_PATH.exists():
        return init_db()
    conn = get_connection()
    _migrate(conn)
    return conn


class connection:
    """Context manager for DB connections. Closes on exit.

    Usage:
        with db.connection() as conn:
            ...
    """
    def __init__(self):
        self.conn = None

    def __enter__(self) -> sqlite3.Connection:
        self.conn = ensure_db()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.conn:
            self.conn.close()
        return False


SCHEMA_VERSION = 20  # Increment when adding migrations


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version. Returns 0 if table doesn't exist."""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "schema_version" not in tables:
        return 0
    row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return row[0] if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set schema version, creating table if needed."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def _col_set(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for a table.

    Table name is validated against existing tables to prevent SQL injection
    via PRAGMA (which cannot use parameterized queries).
    """
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        raise ValueError(f"Invalid table name: {table}")
    if table not in _table_set(conn):
        return set()
    return {r[1] for r in conn.execute(
        "PRAGMA table_info(" + table + ")"
    ).fetchall()}


def _table_set(conn: sqlite3.Connection) -> set[str]:
    """Return the set of table names in the database."""
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


# ── Individual migration functions ──────────────────────────────────────────
# Each is idempotent (checks before altering) and self-contained.
# Each commits its own transaction.


def _migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    """V0 -> V1: status column, profile columns, session columns,
    dialogue_scenario, error_focus, error_log CHECK expansion,
    grammar/skill tables, audio metadata, scale_level."""

    # Add status column if missing (V0 -> V0.1 migration)
    cols = _col_set(conn, "content_item")
    if "status" not in cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN status TEXT NOT NULL DEFAULT 'drill_ready'")
        conn.execute("""
            UPDATE content_item SET status = 'raw'
            WHERE (pinyin IS NULL OR pinyin = '') AND (english IS NULL OR english = '')
        """)
        conn.commit()

    # Add preferred_session_length to learner_profile if missing
    profile_cols = _col_set(conn, "learner_profile")
    if "preferred_session_length" not in profile_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN preferred_session_length INTEGER NOT NULL DEFAULT 12")
        conn.commit()

    # audio_enabled on learner_profile
    if "audio_enabled" not in profile_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN audio_enabled INTEGER NOT NULL DEFAULT 1")
        conn.commit()

    # Add session_started_hour to session_log if missing
    session_cols = _col_set(conn, "session_log")
    if "session_started_hour" not in session_cols:
        conn.execute("ALTER TABLE session_log ADD COLUMN session_started_hour INTEGER")
        conn.commit()

    # Add session_day_of_week to session_log
    session_cols = _col_set(conn, "session_log")
    if "session_day_of_week" not in session_cols:
        conn.execute("ALTER TABLE session_log ADD COLUMN session_day_of_week INTEGER")
        conn.commit()

    # Create dialogue_scenario and error_focus tables
    tables = _table_set(conn)

    if "dialogue_scenario" not in tables:
        conn.executescript("""
            CREATE TABLE dialogue_scenario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                title_zh TEXT,
                hsk_level INTEGER NOT NULL DEFAULT 1,
                register TEXT NOT NULL DEFAULT 'neutral',
                scenario_type TEXT NOT NULL DEFAULT 'dialogue',
                tree_json TEXT NOT NULL,
                difficulty REAL NOT NULL DEFAULT 0.5,
                times_presented INTEGER NOT NULL DEFAULT 0,
                avg_score REAL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    if "error_focus" not in tables:
        conn.executescript("""
            CREATE TABLE error_focus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER NOT NULL,
                error_type TEXT NOT NULL,
                first_flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_error_at TEXT NOT NULL DEFAULT (datetime('now')),
                error_count INTEGER NOT NULL DEFAULT 1,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0,
                resolved_at TEXT,
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                UNIQUE(content_item_id, error_type)
            );
        """)
        conn.commit()

    # Expand error_log CHECK constraint to include all 14 error types
    # SQLite can't ALTER CHECK, so recreate the table if needed
    error_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='error_log'"
    ).fetchone()
    if error_sql and "reference_tracking" not in (error_sql[0] or ""):
        # executescript runs as an implicit transaction -- safe for table swap
        conn.executescript("""
            CREATE TABLE error_log_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                session_id INTEGER,
                content_item_id INTEGER NOT NULL,
                modality TEXT NOT NULL,
                error_type TEXT NOT NULL DEFAULT 'other'
                    CHECK (error_type IN (
                        'tone', 'segment', 'ime_confusable', 'grammar', 'vocab', 'other',
                        'register_mismatch', 'particle_misuse', 'function_word_omission',
                        'temporal_sequencing', 'measure_word', 'politeness_softening',
                        'reference_tracking', 'pragmatics_mismatch'
                    )),
                user_answer TEXT,
                expected_answer TEXT,
                drill_type TEXT,
                notes TEXT,
                FOREIGN KEY (session_id) REFERENCES session_log(id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            );
            INSERT INTO error_log_new SELECT * FROM error_log;
            DROP TABLE error_log;
            ALTER TABLE error_log_new RENAME TO error_log;
            CREATE INDEX IF NOT EXISTS idx_error_type ON error_log(error_type);
            CREATE INDEX IF NOT EXISTS idx_error_session ON error_log(session_id);
            CREATE INDEX IF NOT EXISTS idx_error_item ON error_log(content_item_id);
        """)
        conn.commit()

    # Grammar and skill tables
    if "grammar_point" not in tables:
        conn.executescript("""
            CREATE TABLE grammar_point (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                name_zh TEXT,
                hsk_level INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'structure',
                description TEXT,
                examples_json TEXT DEFAULT '[]',
                difficulty REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS skill (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'pragmatic',
                description TEXT,
                hsk_level INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS content_grammar (
                content_item_id INTEGER NOT NULL,
                grammar_point_id INTEGER NOT NULL,
                PRIMARY KEY (content_item_id, grammar_point_id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id)
            );
            CREATE TABLE IF NOT EXISTS content_skill (
                content_item_id INTEGER NOT NULL,
                skill_id INTEGER NOT NULL,
                PRIMARY KEY (content_item_id, skill_id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                FOREIGN KEY (skill_id) REFERENCES skill(id)
            );
        """)
        conn.commit()

    # Audio metadata columns on content_item
    ci_cols = _col_set(conn, "content_item")
    if "audio_available" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN audio_available INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE content_item ADD COLUMN audio_file_path TEXT")
        conn.execute("ALTER TABLE content_item ADD COLUMN clip_start_ms INTEGER")
        conn.execute("ALTER TABLE content_item ADD COLUMN clip_end_ms INTEGER")
        conn.commit()

    # scale_level column on content_item
    ci_cols = _col_set(conn, "content_item")
    if "scale_level" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN scale_level TEXT NOT NULL DEFAULT 'word'")
        # Auto-tag: items with item_type='sentence' get scale_level='sentence'
        conn.execute("UPDATE content_item SET scale_level = 'sentence' WHERE item_type = 'sentence'")
        conn.execute("UPDATE content_item SET scale_level = 'sentence' WHERE item_type = 'phrase'")
        conn.commit()


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """V1 -> V2: context_note on content_item, audio_recording table."""

    # context_note column on content_item
    ci_cols = _col_set(conn, "content_item")
    if "context_note" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN context_note TEXT")
        conn.commit()

    # audio_recording table for voice tone grading
    tables = _table_set(conn)
    if "audio_recording" not in tables:
        conn.executescript("""
            CREATE TABLE audio_recording (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                content_item_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                tone_scores_json TEXT,
                overall_score REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES session_log(id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            );
        """)
        conn.commit()


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """V2 -> V3: Per-direction progress tracking."""

    progress_cols = _col_set(conn, "progress")
    if "drill_direction" not in progress_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN drill_direction TEXT")
        conn.execute("ALTER TABLE progress ADD COLUMN mastery_stage TEXT NOT NULL DEFAULT 'weak'")
        conn.execute("ALTER TABLE progress ADD COLUMN historically_weak INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE progress ADD COLUMN weak_cycle_count INTEGER NOT NULL DEFAULT 0")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progress_direction
            ON progress(content_item_id, modality, drill_direction)
        """)
        # Back-fill mastery_stage for existing data
        conn.execute("""
            UPDATE progress SET mastery_stage = 'improving'
            WHERE streak_correct >= 3 AND streak_correct < 6
        """)
        conn.execute("""
            UPDATE progress SET mastery_stage = 'stable'
            WHERE streak_correct >= 6 AND total_attempts >= 10
        """)
        conn.commit()


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """V3 -> V4: Response time tracking, construction tables, drill type variation."""

    progress_cols = _col_set(conn, "progress")
    if "avg_response_ms" not in progress_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN avg_response_ms REAL")
        conn.execute("ALTER TABLE progress ADD COLUMN drill_types_seen TEXT NOT NULL DEFAULT ''")
        conn.commit()

    tables = _table_set(conn)
    if "construction" not in tables:
        conn.executescript("""
            CREATE TABLE construction (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                pattern_zh TEXT,
                description TEXT,
                hsk_level INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'syntax',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE content_construction (
                content_item_id INTEGER NOT NULL,
                construction_id INTEGER NOT NULL,
                PRIMARY KEY (content_item_id, construction_id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                FOREIGN KEY (construction_id) REFERENCES construction(id)
            );
        """)
        conn.commit()


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """V4 -> V5: Distinct review days for spacing verification."""

    progress_cols = _col_set(conn, "progress")
    if "distinct_review_days" not in progress_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN distinct_review_days INTEGER NOT NULL DEFAULT 0")
        # Back-fill: count distinct last_review_date values is not feasible from
        # current schema, so just set to 1 for any item that's been reviewed
        conn.execute("""
            UPDATE progress SET distinct_review_days = 1
            WHERE total_attempts > 0 AND distinct_review_days = 0
        """)
        conn.commit()


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    """V5 -> V6: Half-life retention model + session metrics table."""

    progress_cols = _col_set(conn, "progress")
    if "half_life_days" not in progress_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN half_life_days REAL DEFAULT 1.0")
        conn.execute("ALTER TABLE progress ADD COLUMN difficulty REAL DEFAULT 0.5")
        conn.execute("ALTER TABLE progress ADD COLUMN last_p_recall REAL")
        # Back-fill half_life from interval_days and ease_factor
        conn.execute("""
            UPDATE progress
            SET half_life_days = MAX(0.5, interval_days * ease_factor / 2.5),
                difficulty = CASE
                    WHEN total_attempts = 0 THEN 0.5
                    WHEN total_correct = 0 THEN 0.9
                    ELSE MAX(0.05, MIN(0.95,
                        1.0 - CAST(total_correct AS REAL) / total_attempts
                    ))
                END
            WHERE total_attempts > 0
        """)
        conn.commit()

    # Session metrics table
    tables = _table_set(conn)
    if "session_metrics" not in tables:
        conn.execute("""
            CREATE TABLE session_metrics (
                session_id INTEGER PRIMARY KEY REFERENCES session_log(id),
                recall_above_threshold INTEGER DEFAULT 0,
                recall_below_threshold INTEGER DEFAULT 0,
                avg_recall REAL,
                avg_difficulty REAL,
                items_strengthened INTEGER DEFAULT 0,
                items_weakened INTEGER DEFAULT 0,
                transfer_events INTEGER DEFAULT 0,
                computed_at TEXT
            )
        """)
        conn.commit()


def _migrate_v6_to_v7(conn: sqlite3.Connection) -> None:
    """V6 -> V7: Six mastery stages + stable tracking columns."""

    progress_cols = _col_set(conn, "progress")
    if "stable_since_date" not in progress_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN stable_since_date TEXT")
        conn.execute("ALTER TABLE progress ADD COLUMN successes_while_stable INTEGER NOT NULL DEFAULT 0")
        # Back-fill mastery stages from 3-state to 6-state
        # 'stable' stays as 'stable', set stable_since_date = last_review_date
        conn.execute("""
            UPDATE progress SET stable_since_date = last_review_date
            WHERE mastery_stage = 'stable'
        """)
        # 'improving' remaps to 'stabilizing'
        conn.execute("""
            UPDATE progress SET mastery_stage = 'stabilizing'
            WHERE mastery_stage = 'improving'
        """)
        # 'weak' with total_attempts > 0 and streak_correct >= 1 -> 'passed_once'
        conn.execute("""
            UPDATE progress SET mastery_stage = 'passed_once'
            WHERE mastery_stage = 'weak' AND total_attempts > 0 AND streak_correct >= 1
        """)
        # 'weak' with total_attempts > 0 and streak_correct = 0 -> 'seen'
        conn.execute("""
            UPDATE progress SET mastery_stage = 'seen'
            WHERE mastery_stage = 'weak' AND total_attempts > 0 AND streak_correct = 0
        """)
        conn.commit()


def _migrate_v7_to_v8(conn: sqlite3.Connection) -> None:
    """V7 -> V8: probe_log table, preferred_domains on learner_profile."""

    # probe_log table for comprehension probe persistence
    tables = _table_set(conn)
    if "probe_log" not in tables:
        conn.executescript("""
            CREATE TABLE probe_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER,
                scenario_id INTEGER,
                probe_type TEXT NOT NULL DEFAULT 'comprehension',
                correct INTEGER NOT NULL DEFAULT 0,
                user_answer TEXT,
                expected_answer TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (scenario_id) REFERENCES dialogue_scenario(id)
            );
            CREATE INDEX IF NOT EXISTS idx_probe_scenario ON probe_log(scenario_id);
        """)
        conn.commit()

    # preferred_domains on learner_profile (for personalization)
    profile_cols = _col_set(conn, "learner_profile")
    if "preferred_domains" not in profile_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN preferred_domains TEXT DEFAULT ''")
        conn.commit()


def _migrate_v8_to_v9(conn: sqlite3.Connection) -> None:
    """V8 -> V9: Expand grammar_point category CHECK to include 'connector'."""

    gp_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='grammar_point'"
    ).fetchone()
    if gp_sql and "connector" not in (gp_sql[0] or ""):
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS grammar_point_new;
            CREATE TABLE grammar_point_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                name_zh TEXT,
                hsk_level INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'structure'
                    CHECK (category IN ('structure', 'particle', 'measure_word',
                                        'complement', 'aspect', 'comparison', 'connector', 'other')),
                description TEXT,
                examples_json TEXT DEFAULT '[]',
                difficulty REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO grammar_point_new SELECT * FROM grammar_point;
            DROP TABLE grammar_point;
            ALTER TABLE grammar_point_new RENAME TO grammar_point;
            CREATE INDEX IF NOT EXISTS idx_grammar_hsk ON grammar_point(hsk_level);
            PRAGMA foreign_keys = ON;
        """)
        conn.commit()


def _migrate_v9_to_v10(conn: sqlite3.Connection) -> None:
    """V9 -> V10: media_watch table, behavioral commitment columns on learner_profile."""

    # media_watch table for real-world media recommendations
    tables = _table_set(conn)
    if "media_watch" not in tables:
        conn.executescript("""
            CREATE TABLE media_watch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                hsk_level INTEGER NOT NULL DEFAULT 1,
                media_type TEXT NOT NULL,
                times_presented INTEGER NOT NULL DEFAULT 0,
                times_watched INTEGER NOT NULL DEFAULT 0,
                last_presented_at TEXT,
                last_watched_at TEXT,
                total_questions INTEGER NOT NULL DEFAULT 0,
                total_correct INTEGER NOT NULL DEFAULT 0,
                avg_score REAL,
                best_score REAL,
                skipped INTEGER NOT NULL DEFAULT 0,
                liked INTEGER,
                status TEXT NOT NULL DEFAULT 'available',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_media_watch_hsk ON media_watch(hsk_level);
            CREATE INDEX IF NOT EXISTS idx_media_watch_status ON media_watch(status);
        """)
        conn.commit()

    # Behavioral commitment columns on learner_profile
    profile_cols = _col_set(conn, "learner_profile")
    if "next_session_intention" not in profile_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN next_session_intention TEXT")
        conn.execute("ALTER TABLE learner_profile ADD COLUMN intention_set_at TEXT")
        conn.execute("ALTER TABLE learner_profile ADD COLUMN minimal_days TEXT DEFAULT ''")
        conn.commit()


def _migrate_v10_to_v11(conn: sqlite3.Connection) -> None:
    """V10 -> V11: session_outcome for funnel metrics."""

    session_cols = _col_set(conn, "session_log")
    if "session_outcome" not in session_cols:
        conn.execute("ALTER TABLE session_log ADD COLUMN session_outcome TEXT DEFAULT 'started'")
        # Back-fill: sessions with ended_at are completed, with early_exit are abandoned
        conn.execute("""
            UPDATE session_log SET session_outcome = 'completed'
            WHERE ended_at IS NOT NULL AND early_exit = 0
        """)
        conn.execute("""
            UPDATE session_log SET session_outcome = 'abandoned'
            WHERE ended_at IS NOT NULL AND early_exit = 1 AND items_completed > 0
        """)
        conn.execute("""
            UPDATE session_log SET session_outcome = 'bounced'
            WHERE ended_at IS NOT NULL AND early_exit = 1 AND items_completed = 0
        """)
        # Sessions that were never ended (crashed/interrupted)
        conn.execute("""
            UPDATE session_log SET session_outcome = 'bounced'
            WHERE ended_at IS NULL AND session_outcome = 'started'
        """)
        conn.commit()


def _migrate_v11_to_v12(conn: sqlite3.Connection) -> None:
    """V11 -> V12: mapping_groups_used on session_log (cross-session interleaving)."""

    session_cols = _col_set(conn, "session_log")
    if "mapping_groups_used" not in session_cols:
        conn.execute("ALTER TABLE session_log ADD COLUMN mapping_groups_used TEXT")
        conn.commit()


def _migrate_v12_to_v13(conn: sqlite3.Connection) -> None:
    """V12 -> V13: vocab_encounter table for reading/listening lookup tracking."""

    tables = _table_set(conn)
    if "vocab_encounter" not in tables:
        conn.executescript("""
            CREATE TABLE vocab_encounter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER,
                hanzi TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT,
                looked_up INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            );
            CREATE INDEX idx_encounter_hanzi ON vocab_encounter(hanzi);
            CREATE INDEX idx_encounter_source ON vocab_encounter(source_type, source_id);
        """)
        conn.commit()


def _migrate_v13_to_v14(conn: sqlite3.Connection) -> None:
    """V13 -> V14: Affiliate tracking, referral, commission, discount, lifecycle event tables."""

    tables = _table_set(conn)

    # Affiliate/partner tracking
    if "affiliate_partner" not in tables:
        conn.executescript("""
            CREATE TABLE affiliate_partner (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_code TEXT UNIQUE NOT NULL,
                partner_name TEXT NOT NULL,
                partner_email TEXT,
                commission_rate REAL NOT NULL DEFAULT 0.30,
                tier TEXT NOT NULL DEFAULT 'standard',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                CHECK (tier IN ('standard', 'upgrade')),
                CHECK (status IN ('active', 'inactive'))
            );
        """)
        conn.commit()

    # Referral tracking
    if "referral_tracking" not in tables:
        conn.executescript("""
            CREATE TABLE referral_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                partner_code TEXT NOT NULL,
                landing_page TEXT,
                utm_source TEXT,
                utm_medium TEXT,
                utm_campaign TEXT,
                cookie_set_at TEXT NOT NULL DEFAULT (datetime('now')),
                signed_up INTEGER NOT NULL DEFAULT 0,
                signup_at TEXT,
                converted_to_paid INTEGER NOT NULL DEFAULT 0,
                converted_at TEXT,
                FOREIGN KEY (partner_code) REFERENCES affiliate_partner(partner_code)
            );
            CREATE INDEX IF NOT EXISTS idx_referral_partner ON referral_tracking(partner_code);
            CREATE INDEX IF NOT EXISTS idx_referral_visitor ON referral_tracking(visitor_id);
        """)
        conn.commit()

    # Commission tracking
    if "affiliate_commission" not in tables:
        conn.executescript("""
            CREATE TABLE affiliate_commission (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_code TEXT NOT NULL,
                referral_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                confirmed_at TEXT,
                paid_out_at TEXT,
                CHECK (status IN ('pending', 'confirmed', 'paid', 'reversed')),
                FOREIGN KEY (partner_code) REFERENCES affiliate_partner(partner_code),
                FOREIGN KEY (referral_id) REFERENCES referral_tracking(id)
            );
            CREATE INDEX IF NOT EXISTS idx_commission_partner ON affiliate_commission(partner_code);
            CREATE INDEX IF NOT EXISTS idx_commission_status ON affiliate_commission(status);
        """)
        conn.commit()

    # Discount codes
    if "discount_code" not in tables:
        conn.executescript("""
            CREATE TABLE discount_code (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                partner_code TEXT,
                discount_percent INTEGER NOT NULL DEFAULT 20,
                valid_months INTEGER NOT NULL DEFAULT 3,
                max_uses INTEGER,
                current_uses INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (partner_code) REFERENCES affiliate_partner(partner_code)
            );
        """)
        conn.commit()

    # Lifecycle event logging
    if "lifecycle_event" not in tables:
        conn.executescript("""
            CREATE TABLE lifecycle_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_lifecycle_event_type ON lifecycle_event(event_type);
            CREATE INDEX IF NOT EXISTS idx_lifecycle_user ON lifecycle_event(user_id);
            CREATE INDEX IF NOT EXISTS idx_lifecycle_created ON lifecycle_event(created_at);
        """)
        conn.commit()


def _migrate_v14_to_v15(conn: sqlite3.Connection) -> None:
    """V14 -> V15: Multi-user support — user table, user_id on all per-learner tables.

    1. Create user table
    2. Insert bootstrap user (id=1) for existing single-user data
    3. Recreate learner_profile without CHECK(id=1), add user_id FK
    4. Recreate progress with user_id in UNIQUE constraint
    5. Add user_id column to remaining per-learner tables
    6. Create composite indexes for multi-user hot paths
    """

    tables = _table_set(conn)

    # 1. Create user table
    if "user" not in tables:
        conn.execute("""
            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                subscription_tier TEXT NOT NULL DEFAULT 'free'
                    CHECK (subscription_tier IN ('free', 'paid', 'admin')),
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                subscription_expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()

    # 2. Bootstrap user for existing single-user data
    if not conn.execute("SELECT 1 FROM user WHERE id = 1").fetchone():
        conn.execute("""
            INSERT INTO user (id, email, password_hash, display_name, subscription_tier)
            VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
        """)
        conn.commit()

    # 3. Recreate learner_profile: remove CHECK(id=1), add user_id with FK
    if "user_id" not in _col_set(conn, "learner_profile"):
        old_cols = [r[1] for r in conn.execute(
            "PRAGMA table_info(learner_profile)"
        ).fetchall()]
        col_csv = ", ".join(old_cols)

        conn.executescript(f"""
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS learner_profile_new;
            CREATE TABLE learner_profile_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                level_reading REAL NOT NULL DEFAULT 1.0,
                level_listening REAL NOT NULL DEFAULT 1.0,
                level_speaking REAL NOT NULL DEFAULT 1.0,
                level_ime REAL NOT NULL DEFAULT 1.0,
                level_chunks REAL NOT NULL DEFAULT 1.0,
                confidence_reading REAL NOT NULL DEFAULT 0.0,
                confidence_listening REAL NOT NULL DEFAULT 0.0,
                confidence_speaking REAL NOT NULL DEFAULT 0.0,
                confidence_ime REAL NOT NULL DEFAULT 0.0,
                confidence_chunks REAL NOT NULL DEFAULT 0.0,
                target_sessions_per_week INTEGER NOT NULL DEFAULT 4,
                preferred_session_length INTEGER NOT NULL DEFAULT 12,
                total_sessions INTEGER NOT NULL DEFAULT 0,
                last_session_date TEXT,
                lens_quiet_observation REAL NOT NULL DEFAULT 0.7,
                lens_institutions REAL NOT NULL DEFAULT 0.7,
                lens_urban_texture REAL NOT NULL DEFAULT 0.7,
                lens_humane_mystery REAL NOT NULL DEFAULT 0.7,
                lens_identity REAL NOT NULL DEFAULT 0.7,
                lens_comedy REAL NOT NULL DEFAULT 0.7,
                lens_food REAL NOT NULL DEFAULT 0.5,
                lens_travel REAL NOT NULL DEFAULT 0.5,
                lens_explainers REAL NOT NULL DEFAULT 0.5,
                audio_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_domains TEXT DEFAULT '',
                next_session_intention TEXT,
                intention_set_at TEXT,
                minimal_days TEXT DEFAULT '',
                UNIQUE(user_id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            INSERT INTO learner_profile_new ({col_csv}, user_id)
                SELECT {col_csv}, 1 FROM learner_profile;
            DROP TABLE learner_profile;
            ALTER TABLE learner_profile_new RENAME TO learner_profile;
            PRAGMA foreign_keys = ON;
        """)
        conn.commit()

    # 4. Recreate progress: add user_id, change UNIQUE to (user_id, item, modality)
    if "user_id" not in _col_set(conn, "progress"):
        old_cols = [r[1] for r in conn.execute(
            "PRAGMA table_info(progress)"
        ).fetchall()]
        col_csv = ", ".join(old_cols)

        conn.executescript(f"""
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS progress_new;
            CREATE TABLE progress_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                modality TEXT NOT NULL
                    CHECK (modality IN ('reading', 'listening', 'speaking', 'ime')),
                ease_factor REAL NOT NULL DEFAULT 2.5,
                interval_days REAL NOT NULL DEFAULT 0.0,
                repetitions INTEGER NOT NULL DEFAULT 0,
                next_review_date TEXT,
                last_review_date TEXT,
                total_attempts INTEGER NOT NULL DEFAULT 0,
                total_correct INTEGER NOT NULL DEFAULT 0,
                streak_correct INTEGER NOT NULL DEFAULT 0,
                streak_incorrect INTEGER NOT NULL DEFAULT 0,
                intuition_attempts INTEGER NOT NULL DEFAULT 0,
                intuition_correct INTEGER NOT NULL DEFAULT 0,
                drill_direction TEXT,
                mastery_stage TEXT NOT NULL DEFAULT 'seen',
                historically_weak INTEGER NOT NULL DEFAULT 0,
                weak_cycle_count INTEGER NOT NULL DEFAULT 0,
                avg_response_ms REAL,
                drill_types_seen TEXT NOT NULL DEFAULT '',
                distinct_review_days INTEGER NOT NULL DEFAULT 0,
                half_life_days REAL DEFAULT 1.0,
                difficulty REAL DEFAULT 0.5,
                last_p_recall REAL,
                stable_since_date TEXT,
                successes_while_stable INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, content_item_id, modality),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            INSERT INTO progress_new ({col_csv}, user_id)
                SELECT {col_csv}, 1 FROM progress;
            DROP TABLE progress;
            ALTER TABLE progress_new RENAME TO progress;
            CREATE INDEX IF NOT EXISTS idx_progress_review ON progress(next_review_date);
            CREATE INDEX IF NOT EXISTS idx_progress_modality ON progress(modality);
            CREATE INDEX IF NOT EXISTS idx_progress_direction
                ON progress(content_item_id, modality, drill_direction);
            CREATE INDEX IF NOT EXISTS idx_progress_item ON progress(content_item_id);
            CREATE INDEX IF NOT EXISTS idx_progress_mastery ON progress(mastery_stage);
            PRAGMA foreign_keys = ON;
        """)
        conn.commit()

    # 5. Add user_id to remaining per-learner tables (simple ALTER TABLE)
    alter_tables = [
        "session_log", "error_log", "error_focus", "audio_recording",
        "probe_log", "session_metrics", "vocab_encounter",
        "improvement_log", "media_watch",
    ]
    for table_name in alter_tables:
        # SECURITY: table_name comes from the hardcoded list above, not user input.
        # Assertion ensures no injection if the list is ever refactored.
        import re as _re
        assert _re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name), f"Invalid table name: {table_name}"
        if table_name in _table_set(conn):
            if "user_id" not in _col_set(conn, table_name):
                conn.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER DEFAULT 1"
                )
                conn.execute(
                    f"UPDATE {table_name} SET user_id = 1 WHERE user_id IS NULL"
                )
                conn.commit()

    # 6. Composite indexes for multi-user hot paths
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_progress_user_item
            ON progress(user_id, content_item_id, modality);
        CREATE INDEX IF NOT EXISTS idx_session_log_user
            ON session_log(user_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_error_log_user_session
            ON error_log(user_id, session_id);
        CREATE INDEX IF NOT EXISTS idx_error_focus_user
            ON error_focus(user_id, content_item_id);
        CREATE INDEX IF NOT EXISTS idx_vocab_encounter_user
            ON vocab_encounter(user_id, hanzi);
        CREATE INDEX IF NOT EXISTS idx_media_watch_user
            ON media_watch(user_id, media_id);
        CREATE INDEX IF NOT EXISTS idx_improvement_log_user
            ON improvement_log(user_id);
    """)
    conn.commit()


def _migrate_v15_to_v16(conn: sqlite3.Connection) -> None:
    """V15 -> V16: Production readiness — user columns, invite codes.

    Adds: onboarding_complete, daily_goal, is_admin, invited_by,
          subscription_status on user table.
    Creates: invite_code table.
    """

    user_cols = _col_set(conn, "user")

    # New columns on user table
    if "onboarding_complete" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN onboarding_complete INTEGER DEFAULT 0")
        conn.commit()

    if "daily_goal" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN daily_goal TEXT DEFAULT 'standard'")
        conn.commit()

    if "is_admin" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN is_admin INTEGER DEFAULT 0")
        # Make bootstrap user (id=1) an admin
        conn.execute("UPDATE user SET is_admin = 1 WHERE id = 1")
        conn.commit()

    if "invited_by" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN invited_by TEXT")
        conn.commit()

    if "subscription_status" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN subscription_status TEXT DEFAULT 'active'")
        conn.commit()

    # Mark existing users as onboarding complete (they're already using the system)
    conn.execute("UPDATE user SET onboarding_complete = 1 WHERE onboarding_complete = 0 OR onboarding_complete IS NULL")
    conn.commit()

    # Invite code table
    tables = _table_set(conn)
    if "invite_code" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS invite_code (
                code TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                used_by INTEGER REFERENCES user(id),
                used_at TEXT,
                max_uses INTEGER DEFAULT 1,
                use_count INTEGER DEFAULT 0
            );
        """)
        conn.commit()


def _migrate_v16_to_v17(conn: sqlite3.Connection) -> None:
    """V16 -> V17: JWT refresh tokens on user, push_token table for mobile."""

    # JWT refresh token columns on user
    user_cols = _col_set(conn, "user")
    if "refresh_token_hash" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN refresh_token_hash TEXT")
        conn.execute("ALTER TABLE user ADD COLUMN refresh_token_expires TEXT")
        conn.commit()

    # Push notification token table
    tables = _table_set(conn)
    if "push_token" not in tables:
        conn.executescript("""
            CREATE TABLE push_token (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES user(id),
                platform TEXT NOT NULL,
                token TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX idx_push_token_user_platform
                ON push_token(user_id, platform);
        """)
        conn.commit()


def _migrate_v17_to_v18(conn: sqlite3.Connection) -> None:
    """V17 -> V18: Security hardening — account lockout, audit log, GDPR deletion support."""

    # Account lockout + password reset columns on user
    user_cols = _col_set(conn, "user")
    if "failed_login_attempts" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
    if "locked_until" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN locked_until TEXT")
    if "reset_token_hash" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN reset_token_hash TEXT")
    if "reset_token_expires" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN reset_token_expires TEXT")
    if "is_admin" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "subscription_status" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN subscription_status TEXT DEFAULT 'active'")
    conn.commit()

    # Deactivate bootstrap user in production (L-4)
    conn.execute("UPDATE user SET is_active = 0 WHERE id = 1 AND email = 'local@localhost'")
    conn.commit()

    # Security audit log table (CIS Control 8, NIST DE.AE, ISO A.8.15)
    tables = _table_set(conn)
    if "security_audit_log" not in tables:
        conn.executescript("""
            CREATE TABLE security_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                event_type TEXT NOT NULL,
                user_id INTEGER,
                ip_address TEXT,
                user_agent TEXT,
                details TEXT,
                severity TEXT NOT NULL DEFAULT 'INFO',
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE INDEX idx_security_audit_timestamp ON security_audit_log(timestamp);
            CREATE INDEX idx_security_audit_user ON security_audit_log(user_id);
            CREATE INDEX idx_security_audit_event ON security_audit_log(event_type);
        """)
        conn.commit()

    # Data deletion request table (GDPR Article 17)
    if "data_deletion_request" not in tables:
        conn.executescript("""
            CREATE TABLE data_deletion_request (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES user(id),
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
            );
        """)
        conn.commit()


def _migrate_v18_to_v19(conn: sqlite3.Connection) -> None:
    """V18 -> V19: TOTP MFA columns on user table."""

    user_cols = _col_set(conn, "user")
    if "totp_secret" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN totp_secret TEXT")
    if "totp_enabled" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN totp_enabled INTEGER DEFAULT 0")
    if "totp_backup_codes" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN totp_backup_codes TEXT")
    conn.commit()


def _migrate_v19_to_v20(conn: sqlite3.Connection) -> None:
    """V19 -> V20: Framework gap closure — email verification, idle timeout,
    marketing opt-out, anonymous mode, feature flags, persistent rate limiter,
    retention policies, LTI platforms."""

    user_cols = _col_set(conn, "user")

    # Item 16: Email verification columns
    if "email_verified" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN email_verified INTEGER DEFAULT 0")
    if "email_verify_token" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN email_verify_token TEXT")
    if "email_verify_expires" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN email_verify_expires TEXT")

    # Item 22: Idle session timeout tracking
    if "last_activity" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN last_activity TEXT")

    # Item 27: Marketing email opt-out
    if "marketing_opt_out" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN marketing_opt_out INTEGER DEFAULT 0")

    # Item 28: Anonymous learning mode
    if "anonymous_mode" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN anonymous_mode INTEGER DEFAULT 0")

    conn.commit()

    tables = _table_set(conn)

    # Item 29: Feature flags
    if "feature_flag" not in tables:
        conn.execute("""
            CREATE TABLE feature_flag (
                name TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                rollout_pct INTEGER DEFAULT 100,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        # Seed default flags
        for flag_name, desc in [
            ("anonymous_mode", "Allow users to enable anonymous learning mode"),
            ("email_verification", "Require email verification on registration"),
            ("xapi_export", "Enable xAPI statement export"),
            ("lti_enabled", "Enable LTI 1.3 launch integration"),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO feature_flag (name, enabled, description) VALUES (?, 0, ?)",
                (flag_name, desc),
            )
        conn.commit()

    # Item 8: Persistent rate limiter
    if "rate_limit" not in tables:
        conn.executescript("""
            CREATE TABLE rate_limit (
                key TEXT NOT NULL,
                hits INTEGER DEFAULT 1,
                window_start TEXT DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                PRIMARY KEY (key, window_start)
            );
        """)
        conn.commit()

    # Items 2/18: Data retention policy
    if "retention_policy" not in tables:
        conn.execute("""
            CREATE TABLE retention_policy (
                table_name TEXT PRIMARY KEY,
                retention_days INTEGER NOT NULL,
                last_purged TEXT,
                description TEXT
            )
        """)
        conn.commit()
        # Seed default policies
        for tbl, days, desc in [
            ("error_log", 90, "Error logs retained 90 days"),
            ("security_audit_log", 365, "Audit log retained 1 year (legal basis)"),
            ("rate_limit", 1, "Rate limit windows purged daily"),
            ("drill_response", -1, "Drill responses retained indefinitely"),
            ("vocab_encounter", -1, "Vocab encounters retained indefinitely"),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description) VALUES (?, ?, ?)",
                (tbl, days, desc),
            )
        conn.commit()

    # Item 14: LTI platforms
    if "lti_platform" not in tables:
        conn.execute("""
            CREATE TABLE lti_platform (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issuer TEXT NOT NULL,
                client_id TEXT NOT NULL,
                deployment_id TEXT,
                auth_url TEXT NOT NULL,
                token_url TEXT NOT NULL,
                jwks_url TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    """Ensure indexes on hot query paths. Idempotent."""
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_session_started ON session_log(started_at);
        CREATE INDEX IF NOT EXISTS idx_progress_item ON progress(content_item_id);
        CREATE INDEX IF NOT EXISTS idx_progress_review ON progress(next_review_date);
        CREATE INDEX IF NOT EXISTS idx_progress_modality ON progress(modality);
        CREATE INDEX IF NOT EXISTS idx_error_type ON error_log(error_type);
        CREATE INDEX IF NOT EXISTS idx_error_session ON error_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_error_item ON error_log(content_item_id);
        CREATE INDEX IF NOT EXISTS idx_content_hsk ON content_item(hsk_level);
        CREATE INDEX IF NOT EXISTS idx_content_status ON content_item(status);
        CREATE INDEX IF NOT EXISTS idx_progress_mastery ON progress(mastery_stage);
        -- Item 11: Performance indexes for multi-user hot paths
        CREATE INDEX IF NOT EXISTS idx_srs_user_next ON progress(user_id, next_review_date);
        CREATE INDEX IF NOT EXISTS idx_srs_user_item ON progress(user_id, content_item_id);
        CREATE INDEX IF NOT EXISTS idx_session_user_date ON session_log(user_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_response_session ON error_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_encounter_user_item ON vocab_encounter(content_item_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_user_time ON security_audit_log(user_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_error_user_time ON error_log(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_rate_limit_expires ON rate_limit(expires_at);
    """)


def _ensure_views(conn: sqlite3.Connection) -> None:
    """Create useful views for diagnostic queries. Idempotent."""
    conn.executescript("""
        CREATE VIEW IF NOT EXISTS v_mastery_by_hsk AS
        SELECT ci.hsk_level,
               p.mastery_stage,
               COUNT(*) as cnt
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id
        WHERE ci.status = 'drill_ready'
        GROUP BY ci.hsk_level, p.mastery_stage;

        CREATE VIEW IF NOT EXISTS v_review_due AS
        SELECT ci.id, ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
               p.mastery_stage, p.next_review_date, p.half_life_days,
               p.last_p_recall, p.streak_correct
        FROM content_item ci
        JOIN progress p ON ci.id = p.content_item_id
        WHERE p.next_review_date <= date('now')
          AND ci.status = 'drill_ready';

        CREATE VIEW IF NOT EXISTS v_error_summary AS
        SELECT ci.hanzi, ci.hsk_level,
               el.error_type,
               COUNT(*) as error_count,
               MAX(el.created_at) as last_error
        FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        GROUP BY ci.id, el.error_type
        ORDER BY error_count DESC;
    """)


# ── Migration registry ──────────────────────────────────────────────────────
# Maps (from_version) -> migration function that upgrades to (from_version + 1).

MIGRATIONS = {
    0: _migrate_v0_to_v1,
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
    5: _migrate_v5_to_v6,
    6: _migrate_v6_to_v7,
    7: _migrate_v7_to_v8,
    8: _migrate_v8_to_v9,
    9: _migrate_v9_to_v10,
    10: _migrate_v10_to_v11,
    11: _migrate_v11_to_v12,
    12: _migrate_v12_to_v13,
    13: _migrate_v13_to_v14,
    14: _migrate_v14_to_v15,
    15: _migrate_v15_to_v16,
    16: _migrate_v16_to_v17,
    17: _migrate_v17_to_v18,
    18: _migrate_v18_to_v19,
    19: _migrate_v19_to_v20,
}


def _migrate(conn: sqlite3.Connection) -> None:
    """Run any needed migrations on an existing database.

    Each migration is idempotent (checks before altering) and runs in
    its own transaction.  The schema version is stamped after each
    migration completes so that a crash mid-sequence resumes correctly.
    """
    current = _get_schema_version(conn)

    if current < SCHEMA_VERSION:
        logger.info("Database migration needed: v%d -> v%d", current, SCHEMA_VERSION)

    for version in range(current, SCHEMA_VERSION):
        migration_fn = MIGRATIONS.get(version)
        if migration_fn is None:
            raise RuntimeError(
                "No migration function registered for version %d -> %d"
                % (version, version + 1)
            )
        logger.info("Running migration v%d -> v%d", version, version + 1)
        migration_fn(conn)
        _set_schema_version(conn, version + 1)
        logger.info("Migration v%d -> v%d complete", version, version + 1)

    # Always ensure indexes and views (idempotent, no version gate needed)
    _ensure_indexes(conn)
    _ensure_views(conn)
