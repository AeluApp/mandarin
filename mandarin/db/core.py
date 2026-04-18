"""Database core — connection management, schema, migrations."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import json
from pathlib import Path
from datetime import datetime, date, timezone, UTC

logger = logging.getLogger(__name__)


from ..settings import DB_PATH as _SETTINGS_DB_PATH

DB_DIR = _SETTINGS_DB_PATH.parent
DB_PATH = _SETTINGS_DB_PATH
SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema.sql"
PROFILE_JSON_PATH = Path(__file__).parent.parent.parent / "learner_profile.json"


def load_learner_profile_json() -> dict[str, object]:
    """Load learner_profile.json from repo root. Returns empty dict if missing."""
    if PROFILE_JSON_PATH.exists():
        with open(PROFILE_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a database connection with proper settings."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False is safe here: each `with db.connection()` call
    # creates a new connection that is closed on exit. No connection is shared
    # across threads. The flag is needed because Flask's teardown callbacks may
    # run on a different thread than the one that opened the connection.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
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


import threading as _threading

# Thread-local connection pool — reuses connections per-thread instead of
# opening/closing on every request. Gevent greenlets share threads, so
# thread-local storage is greenlet-safe.
_pool = _threading.local()
_pool_stats = {"reused": 0, "created": 0}


class connection:
    """Context manager for DB connections with thread-local pooling.

    Reuses the connection for the current thread/greenlet instead of
    opening and closing on every request. Connections are verified
    before reuse and replaced if stale.

    Usage:
        with db.connection() as conn:
            ...
    """
    def __init__(self):
        self.conn = None
        self._owned = False  # True if we created a new connection

    def __enter__(self) -> sqlite3.Connection:
        # Try to reuse thread-local connection
        cached = getattr(_pool, "conn", None)
        if cached is not None:
            try:
                # Verify connection is still valid
                cached.execute("SELECT 1")
                self.conn = cached
                _pool_stats["reused"] += 1
                return self.conn
            except (sqlite3.Error, sqlite3.ProgrammingError):
                # Connection is stale — discard and create new
                try:
                    cached.close()
                except Exception:
                    pass
                _pool.conn = None

        # Create new connection
        self.conn = ensure_db()
        _pool.conn = self.conn
        self._owned = True
        _pool_stats["created"] += 1
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None and self.conn:
            # On exception, rollback but keep connection in pool
            try:
                self.conn.rollback()
            except Exception:
                pass
        # Don't close — keep in thread-local pool for reuse
        # Connection will be reused by the next `with db.connection()` in this thread
        return False


def get_pool_stats() -> dict:
    """Return connection pool statistics for monitoring."""
    total = _pool_stats["reused"] + _pool_stats["created"]
    return {
        "reused": _pool_stats["reused"],
        "created": _pool_stats["created"],
        "reuse_rate": round(_pool_stats["reused"] / max(total, 1), 4),
        "total": total,
    }


SCHEMA_VERSION = 134  # Increment when adding migrations


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
            DROP TABLE IF EXISTS error_log;
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
            DROP TABLE IF EXISTS grammar_point;
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
            DROP TABLE IF EXISTS learner_profile;
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
            DROP TABLE IF EXISTS progress;
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
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            raise RuntimeError(f"Invalid table name in migration: {table_name!r}")
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

    # Drill-type feature flags (gate experimental drill types)
    for flag_name, desc in [
        ("drill_radical_decomposition", "Radical decomposition drills"),
        ("drill_confusable_pairs", "Confusable character pair drills"),
        ("drill_measure_word", "Measure word drills"),
        ("drill_sentence_building", "Sentence building drills"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO feature_flag (name, enabled, rollout_pct, description) VALUES (?, 1, 100, ?)",
            (flag_name, desc),
        )
    conn.commit()

    # AI feature flags — off by default, gradual rollout via admin UI
    from ..feature_flags import AI_FEATURE_FLAGS
    for _ai_flag, _ai_desc in AI_FEATURE_FLAGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO feature_flag (name, enabled, rollout_pct, description) VALUES (?, 0, 0.0, ?)",
            (_ai_flag, _ai_desc),
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


def _migrate_v20_to_v21(conn: sqlite3.Connection) -> None:
    """V20 -> V21: Teacher/classroom system, LTI user mapping, streak reminders.

    1. Add role column to user table
    2. Create classroom table
    3. Create classroom_student roster table
    4. Create lti_user_mapping table
    5. Add classroom_id to invite_code
    6. Add streak_reminders to learner_profile
    7. Create indexes for classroom hot paths
    """

    # 1. User role column
    user_cols = _col_set(conn, "user")
    if "role" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN role TEXT DEFAULT 'student'")
        conn.commit()

    # 2. Expand subscription_tier CHECK to include 'teacher'
    # SQLite can't ALTER CHECK constraints — recreate only if needed
    user_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='user'"
    ).fetchone()
    if user_sql and "teacher" not in (user_sql[0] or ""):
        # Update existing CHECK constraint to include 'teacher'
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS user_new;
            CREATE TABLE user_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                subscription_tier TEXT NOT NULL DEFAULT 'free'
                    CHECK (subscription_tier IN ('free', 'paid', 'admin', 'teacher')),
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                subscription_expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                onboarding_complete INTEGER DEFAULT 0,
                daily_goal TEXT DEFAULT 'standard',
                is_admin INTEGER DEFAULT 0,
                invited_by TEXT,
                subscription_status TEXT DEFAULT 'active',
                refresh_token_hash TEXT,
                refresh_token_expires TEXT,
                failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                reset_token_hash TEXT,
                reset_token_expires TEXT,
                totp_secret TEXT,
                totp_enabled INTEGER DEFAULT 0,
                totp_backup_codes TEXT,
                email_verified INTEGER DEFAULT 0,
                email_verify_token TEXT,
                email_verify_expires TEXT,
                last_activity TEXT,
                marketing_opt_out INTEGER DEFAULT 0,
                anonymous_mode INTEGER DEFAULT 0,
                role TEXT DEFAULT 'student'
            );
        """)
        # Copy data: get actual columns from old table
        old_cols = [r[1] for r in conn.execute("PRAGMA table_info(user)").fetchall()]
        new_cols = [r[1] for r in conn.execute("PRAGMA table_info(user_new)").fetchall()]
        # Only copy columns that exist in both
        common = [c for c in old_cols if c in new_cols]
        col_csv = ", ".join(common)
        conn.execute(f"DELETE FROM user_new")
        conn.execute(f"INSERT INTO user_new ({col_csv}) SELECT {col_csv} FROM user")
        conn.executescript("""
            DROP TABLE IF EXISTS user;
            ALTER TABLE user_new RENAME TO user;
            PRAGMA foreign_keys = ON;
        """)
        conn.commit()

    # 3. Classroom table
    tables = _table_set(conn)
    if "classroom" not in tables:
        conn.executescript("""
            CREATE TABLE classroom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_user_id INTEGER NOT NULL REFERENCES user(id),
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                invite_code TEXT UNIQUE NOT NULL,
                max_students INTEGER DEFAULT 30,
                billing_type TEXT DEFAULT 'per_student',
                stripe_subscription_id TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX idx_classroom_teacher ON classroom(teacher_user_id);
            CREATE INDEX idx_classroom_invite ON classroom(invite_code);
        """)
        conn.commit()

    # 4. Classroom student roster
    if "classroom_student" not in tables:
        conn.executescript("""
            CREATE TABLE classroom_student (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classroom_id INTEGER NOT NULL REFERENCES classroom(id),
                user_id INTEGER NOT NULL REFERENCES user(id),
                joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT DEFAULT 'active',
                UNIQUE(classroom_id, user_id)
            );
            CREATE INDEX idx_cs_classroom ON classroom_student(classroom_id);
            CREATE INDEX idx_cs_user ON classroom_student(user_id);
        """)
        conn.commit()

    # 5. LTI user mapping
    if "lti_user_mapping" not in tables:
        conn.executescript("""
            CREATE TABLE lti_user_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES user(id),
                issuer TEXT NOT NULL,
                lti_sub TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(issuer, lti_sub)
            );
        """)
        conn.commit()

    # 6. Link invite codes to classrooms
    ic_cols = _col_set(conn, "invite_code")
    if "classroom_id" not in ic_cols and "invite_code" in tables:
        conn.execute("ALTER TABLE invite_code ADD COLUMN classroom_id INTEGER REFERENCES classroom(id)")
        conn.commit()

    # 7. Streak reminder preference on learner_profile
    lp_cols = _col_set(conn, "learner_profile")
    if "streak_reminders" not in lp_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN streak_reminders INTEGER DEFAULT 1")
        conn.commit()


def _migrate_v21_to_v22(conn: sqlite3.Connection) -> None:
    """V21 -> V22: Speaker calibration table for tone grading.

    Stores per-user F0 range (10th/90th percentile) from a calibration phrase.
    Used by classify_tone() to normalize against the speaker's pitch range.
    """
    tables = _table_set(conn)
    if "speaker_calibration" not in tables:
        conn.executescript("""
            CREATE TABLE speaker_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                f0_min REAL NOT NULL,
                f0_max REAL NOT NULL,
                f0_mean REAL NOT NULL,
                calibrated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE INDEX idx_speaker_calibration_user
                ON speaker_calibration(user_id, calibrated_at);
        """)
        conn.commit()


def _migrate_v22_to_v23(conn: sqlite3.Connection) -> None:
    """V22 -> V23: Multi-user isolation fixes.

    1. Recreate error_focus with UNIQUE(user_id, content_item_id, error_type)
       instead of UNIQUE(content_item_id, error_type).
    2. Recreate media_watch with UNIQUE(user_id, media_id)
       instead of UNIQUE(media_id).
    """
    # ── Fix error_focus ──
    cols = _col_set(conn, "error_focus")
    if cols:  # table exists
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS error_focus_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                error_type TEXT NOT NULL,
                first_flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_error_at TEXT NOT NULL DEFAULT (datetime('now')),
                error_count INTEGER NOT NULL DEFAULT 1,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0,
                resolved_at TEXT,
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                UNIQUE(user_id, content_item_id, error_type)
            );
            INSERT OR IGNORE INTO error_focus_new
                (id, user_id, content_item_id, error_type, first_flagged_at,
                 last_error_at, error_count, consecutive_correct, resolved, resolved_at)
                SELECT id, user_id, content_item_id, error_type, first_flagged_at,
                       last_error_at, error_count, consecutive_correct, resolved, resolved_at
                FROM error_focus;
            DROP TABLE IF EXISTS error_focus;
            ALTER TABLE error_focus_new RENAME TO error_focus;
            CREATE INDEX IF NOT EXISTS idx_error_focus_user
                ON error_focus(user_id, content_item_id);
        """)
        conn.commit()

    # ── Fix media_watch ──
    mw_cols = _col_set(conn, "media_watch")
    if mw_cols:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS media_watch_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                media_id TEXT NOT NULL,
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
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, media_id)
            );
            INSERT OR IGNORE INTO media_watch_new
                (id, user_id, media_id, title, hsk_level, media_type,
                 times_presented, times_watched, last_presented_at, last_watched_at,
                 total_questions, total_correct, avg_score, best_score,
                 skipped, liked, status, created_at)
                SELECT id, user_id, media_id, title, hsk_level, media_type,
                       times_presented, times_watched, last_presented_at, last_watched_at,
                       total_questions, total_correct, avg_score, best_score,
                       skipped, liked, status, created_at
                FROM media_watch;
            DROP TABLE IF EXISTS media_watch;
            ALTER TABLE media_watch_new RENAME TO media_watch;
            CREATE INDEX IF NOT EXISTS idx_media_watch_hsk ON media_watch(hsk_level);
            CREATE INDEX IF NOT EXISTS idx_media_watch_status ON media_watch(status);
            CREATE INDEX IF NOT EXISTS idx_media_watch_user ON media_watch(user_id, media_id);
        """)
        conn.commit()


def _migrate_v23_to_v24(conn: sqlite3.Connection) -> None:
    """V23 -> V24: Observability tables for beta — crash_log + client_error_log."""
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "crash_log" not in tables:
        conn.execute("""
            CREATE TABLE crash_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                error_type TEXT NOT NULL,
                error_message TEXT,
                traceback TEXT,
                request_method TEXT,
                request_path TEXT,
                request_body TEXT,
                ip_address TEXT,
                user_agent TEXT,
                severity TEXT NOT NULL DEFAULT 'ERROR',
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crash_log_ts ON crash_log(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crash_log_user_ts ON crash_log(user_id, timestamp)")
        conn.commit()

    if "client_error_log" not in tables:
        conn.execute("""
            CREATE TABLE client_error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                error_type TEXT NOT NULL,
                error_message TEXT,
                source_file TEXT,
                line_number INTEGER,
                col_number INTEGER,
                stack_trace TEXT,
                page_url TEXT,
                user_agent TEXT,
                event_snapshot TEXT,
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_client_error_ts ON client_error_log(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_client_error_user_ts ON client_error_log(user_id, timestamp)")
        conn.commit()

    # Register 90-day retention policies
    for tbl, days, desc in [
        ("crash_log", 90, "Server crash logs retained 90 days"),
        ("client_error_log", 90, "Client error logs retained 90 days"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description) VALUES (?, ?, ?)",
            (tbl, days, desc),
        )
    conn.commit()


def _migrate_v24_to_v25(conn: sqlite3.Connection) -> None:
    """V24 -> V25: mfa_challenge table — move MFA tokens from in-memory dict to DB."""
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "mfa_challenge" not in tables:
        conn.execute("""
            CREATE TABLE mfa_challenge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES user(id),
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mfa_challenge_user_expires ON mfa_challenge(user_id, expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mfa_challenge_token ON mfa_challenge(token_hash)")
        conn.commit()


def _migrate_v25_to_v26(conn: sqlite3.Connection) -> None:
    """V25 -> V26: tone confusion columns on error_log, grade_appeal table, last_activity_at on session_log."""

    # a) Add tone_user / tone_expected to error_log
    error_cols = _col_set(conn, "error_log")
    if "tone_user" not in error_cols:
        conn.execute("ALTER TABLE error_log ADD COLUMN tone_user INTEGER")
        conn.execute("ALTER TABLE error_log ADD COLUMN tone_expected INTEGER")
        conn.commit()

    # b) Create grade_appeal table
    tables = _table_set(conn)
    if "grade_appeal" not in tables:
        conn.execute("""
            CREATE TABLE grade_appeal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id INTEGER,
                drill_number INTEGER,
                content_item_id INTEGER,
                user_answer TEXT,
                expected_answer TEXT,
                appeal_text TEXT,
                error_type TEXT,
                status TEXT DEFAULT 'pending',
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.commit()

    # c) Add last_activity_at to session_log
    session_cols = _col_set(conn, "session_log")
    if "last_activity_at" not in session_cols:
        conn.execute("ALTER TABLE session_log ADD COLUMN last_activity_at TEXT")
        conn.commit()

    # d) Register 90-day retention for grade_appeal
    conn.execute(
        "INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description) VALUES (?, ?, ?)",
        ("grade_appeal", 90, "Grade appeals retained 90 days"),
    )
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
        CREATE INDEX IF NOT EXISTS idx_content_review_status ON content_item(review_status);
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
        -- Observability indexes (v24)
        CREATE INDEX IF NOT EXISTS idx_crash_log_ts ON crash_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_crash_log_user_ts ON crash_log(user_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_client_error_ts ON client_error_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_client_error_user_ts ON client_error_log(user_id, timestamp);
        -- content_item
        CREATE INDEX IF NOT EXISTS idx_content_type ON content_item(item_type);
        CREATE INDEX IF NOT EXISTS idx_content_lens ON content_item(content_lens);
        -- progress
        CREATE INDEX IF NOT EXISTS idx_progress_direction ON progress(content_item_id, modality, drill_direction);
        CREATE INDEX IF NOT EXISTS idx_progress_user_item ON progress(user_id, content_item_id, modality);
        CREATE INDEX IF NOT EXISTS idx_progress_user_modality_due ON progress(user_id, modality, next_review_date);
        -- session_log
        CREATE INDEX IF NOT EXISTS idx_session_log_user ON session_log(user_id, started_at);
        -- review_event
        CREATE INDEX IF NOT EXISTS idx_review_event_user ON review_event(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_review_event_item ON review_event(content_item_id);
        -- error_log / error_focus
        CREATE INDEX IF NOT EXISTS idx_error_log_user_session ON error_log(user_id, session_id);
        CREATE INDEX IF NOT EXISTS idx_error_focus_user ON error_focus(user_id, content_item_id);
        -- grammar / skill
        CREATE INDEX IF NOT EXISTS idx_grammar_hsk ON grammar_point(hsk_level);
        CREATE INDEX IF NOT EXISTS idx_skill_category ON skill(category);
        -- probe_log
        CREATE INDEX IF NOT EXISTS idx_probe_scenario ON probe_log(scenario_id);
        -- vocab_encounter
        CREATE INDEX IF NOT EXISTS idx_encounter_hanzi ON vocab_encounter(hanzi);
        CREATE INDEX IF NOT EXISTS idx_encounter_source ON vocab_encounter(source_type, source_id);
        CREATE INDEX IF NOT EXISTS idx_vocab_encounter_user ON vocab_encounter(user_id, hanzi);
        -- reading_progress
        CREATE INDEX IF NOT EXISTS idx_reading_progress_user ON reading_progress(user_id, passage_id);
        -- improvement_log
        CREATE INDEX IF NOT EXISTS idx_improvement_log_user ON improvement_log(user_id);
        -- media_watch
        CREATE INDEX IF NOT EXISTS idx_media_watch_hsk ON media_watch(hsk_level);
        CREATE INDEX IF NOT EXISTS idx_media_watch_status ON media_watch(status);
        CREATE INDEX IF NOT EXISTS idx_media_watch_user ON media_watch(user_id, media_id);
        -- referral_tracking / affiliate_commission
        CREATE INDEX IF NOT EXISTS idx_referral_partner ON referral_tracking(partner_code);
        CREATE INDEX IF NOT EXISTS idx_referral_visitor ON referral_tracking(visitor_id);
        CREATE INDEX IF NOT EXISTS idx_commission_partner ON affiliate_commission(partner_code);
        CREATE INDEX IF NOT EXISTS idx_commission_status ON affiliate_commission(status);
        -- lifecycle_event
        CREATE INDEX IF NOT EXISTS idx_lifecycle_event_type ON lifecycle_event(event_type);
        CREATE INDEX IF NOT EXISTS idx_lifecycle_user ON lifecycle_event(user_id);
        CREATE INDEX IF NOT EXISTS idx_lifecycle_created ON lifecycle_event(created_at);
        -- security_audit_log
        CREATE INDEX IF NOT EXISTS idx_security_audit_timestamp ON security_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_security_audit_event ON security_audit_log(event_type);
        CREATE INDEX IF NOT EXISTS idx_security_audit_severity ON security_audit_log(severity);
        -- security_scan_finding
        CREATE INDEX IF NOT EXISTS idx_scan_finding_scan ON security_scan_finding(scan_id);
        CREATE INDEX IF NOT EXISTS idx_scan_finding_severity ON security_scan_finding(severity);
        -- speaker_calibration
        CREATE INDEX IF NOT EXISTS idx_speaker_calibration_user ON speaker_calibration(user_id, calibrated_at);
        -- client_event
        CREATE INDEX IF NOT EXISTS idx_client_event_ts ON client_event(created_at);
        CREATE INDEX IF NOT EXISTS idx_client_event_user_cat ON client_event(user_id, category);
        -- mfa_challenge
        CREATE INDEX IF NOT EXISTS idx_mfa_challenge_user_expires ON mfa_challenge(user_id, expires_at);
        CREATE INDEX IF NOT EXISTS idx_mfa_challenge_token ON mfa_challenge(token_hash);
        -- classroom
        CREATE INDEX IF NOT EXISTS idx_classroom_teacher ON classroom(teacher_user_id);
        CREATE INDEX IF NOT EXISTS idx_classroom_invite ON classroom(invite_code);
        CREATE INDEX IF NOT EXISTS idx_cs_classroom ON classroom_student(classroom_id);
        CREATE INDEX IF NOT EXISTS idx_cs_user ON classroom_student(user_id);
        -- quality / SPC
        CREATE INDEX IF NOT EXISTS idx_quality_metric_type ON quality_metric(metric_type, measured_at);
        CREATE INDEX IF NOT EXISTS idx_spc_observation_type ON spc_observation(chart_type, observed_at);
        -- risk / work items
        CREATE INDEX IF NOT EXISTS idx_risk_item_status ON risk_item(status);
        CREATE INDEX IF NOT EXISTS idx_work_item_status ON work_item(status);
        -- request_timing
        CREATE INDEX IF NOT EXISTS idx_request_timing_path ON request_timing(path, recorded_at);
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

def _migrate_v26_to_v27(conn: sqlite3.Connection) -> None:
    """V26 -> V27: client_event table for client-side event tracking."""
    tables = _table_set(conn)
    if "client_event" not in tables:
        conn.execute("""
            CREATE TABLE client_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                install_id TEXT,
                category TEXT NOT NULL,
                event TEXT NOT NULL,
                detail TEXT,
                user_agent TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_client_event_ts ON client_event(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_client_event_user_cat ON client_event(user_id, category)")
        conn.commit()

    # Register 30-day retention
    conn.execute(
        "INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description) VALUES (?, ?, ?)",
        ("client_event", 30, "Client-side events retained 30 days"),
    )
    conn.commit()


def _migrate_v27_to_v28(conn: sqlite3.Connection) -> None:
    """V27 -> V28: Activation tracking columns on user table."""
    cols = _col_set(conn, "user")

    for col, defn in [
        ("first_session_at", "TEXT"),
        ("activation_at", "TEXT"),
        ("utm_source", "TEXT"),
        ("utm_medium", "TEXT"),
        ("utm_campaign", "TEXT"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE user ADD COLUMN {col} {defn}")

    conn.commit()

    # Backfill first_session_at from session_log for existing users
    conn.execute("""
        UPDATE user SET first_session_at = (
            SELECT MIN(started_at) FROM session_log WHERE session_log.user_id = user.id
        ) WHERE first_session_at IS NULL
    """)

    # Backfill activation_at: users with 3+ sessions within 14 days of signup
    conn.execute("""
        UPDATE user SET activation_at = (
            SELECT s.started_at FROM session_log s
            WHERE s.user_id = user.id
            ORDER BY s.started_at
            LIMIT 1 OFFSET 2
        ) WHERE activation_at IS NULL AND (
            SELECT COUNT(*) FROM session_log sl
            WHERE sl.user_id = user.id
              AND sl.started_at <= datetime(user.created_at, '+14 days')
        ) >= 3
    """)
    conn.commit()


def _migrate_v28_to_v29(conn: sqlite3.Connection) -> None:
    """V28 -> V29: Reading display preferences on learner_profile."""
    cols = _col_set(conn, "learner_profile")
    if "reading_show_pinyin" not in cols:
        conn.execute(
            "ALTER TABLE learner_profile ADD COLUMN reading_show_pinyin INTEGER NOT NULL DEFAULT 0"
        )
    if "reading_show_translation" not in cols:
        conn.execute(
            "ALTER TABLE learner_profile ADD COLUMN reading_show_translation INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def _migrate_v29_to_v30(conn: sqlite3.Connection) -> None:
    """V29 -> V30: TTS voice preference on learner_profile."""
    cols = _col_set(conn, "learner_profile")
    if "preferred_voice" not in cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN preferred_voice TEXT DEFAULT 'female'")
    conn.commit()


def _migrate_v30_to_v31(conn: sqlite3.Connection) -> None:
    """V30 -> V31: Grammar mastery tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grammar_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            grammar_point_id INTEGER NOT NULL,
            studied_at TEXT NOT NULL DEFAULT (datetime('now')),
            drill_attempts INTEGER NOT NULL DEFAULT 0,
            drill_correct INTEGER NOT NULL DEFAULT 0,
            mastery_score REAL NOT NULL DEFAULT 0.0,
            UNIQUE(user_id, grammar_point_id),
            FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id)
        )
    """)
    conn.commit()


def _migrate_v31_to_v32(conn: sqlite3.Connection) -> None:
    """V31 -> V32: Reading progress tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reading_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            passage_id TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            words_looked_up INTEGER NOT NULL DEFAULT 0,
            questions_correct INTEGER NOT NULL DEFAULT 0,
            questions_total INTEGER NOT NULL DEFAULT 0,
            reading_time_seconds INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reading_progress_user ON reading_progress(user_id, passage_id)")
    conn.commit()


def _migrate_v32_to_v33(conn: sqlite3.Connection) -> None:
    """V32 -> V33: MBB commission structure — 24-month cap, teacher tier, updated rates."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(affiliate_partner)").fetchall()}
    # Add 'teacher' to partner tier (need to recreate table for CHECK constraint)
    # Instead, just add new columns and handle tier validation in application code
    if "commission_cap_months" not in cols:
        conn.execute("ALTER TABLE affiliate_partner ADD COLUMN commission_cap_months INTEGER NOT NULL DEFAULT 24")
    conn.commit()

    # Update default commission rate from 0.30 to 0.25 for existing standard partners
    conn.execute("""
        UPDATE affiliate_partner SET commission_rate = 0.25
        WHERE tier = 'standard' AND commission_rate = 0.30
    """)
    conn.commit()

    # Add columns to affiliate_commission for the cap and rate tracking
    comm_cols = {r[1] for r in conn.execute("PRAGMA table_info(affiliate_commission)").fetchall()}
    if "user_id" not in comm_cols:
        conn.execute("ALTER TABLE affiliate_commission ADD COLUMN user_id INTEGER")
    if "commission_rate" not in comm_cols:
        conn.execute("ALTER TABLE affiliate_commission ADD COLUMN commission_rate REAL NOT NULL DEFAULT 0.25")
    if "first_payment_date" not in comm_cols:
        conn.execute("ALTER TABLE affiliate_commission ADD COLUMN first_payment_date TEXT")
    conn.commit()

    # Add referred_by_partner to user table
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(user)").fetchall()}
    if "referred_by_partner" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN referred_by_partner TEXT")
    conn.commit()

    # Update discount_code default from 20% to 15%
    conn.execute("""
        UPDATE discount_code SET discount_percent = 15
        WHERE discount_percent = 20 AND current_uses = 0
    """)
    conn.commit()


def _migrate_v33_to_v34(conn: sqlite3.Connection) -> None:
    """V33 -> V34: Telemetry dedup + scheduler lock table."""
    # Event ID dedup column
    cols = {r[1] for r in conn.execute("PRAGMA table_info(client_event)").fetchall()}
    if "event_id" not in cols:
        conn.execute("ALTER TABLE client_event ADD COLUMN event_id TEXT")
    conn.commit()
    # Unique index for dedup (NULLs are allowed — legacy events without IDs)
    try:
        conn.execute("CREATE UNIQUE INDEX idx_client_event_id ON client_event(event_id)")
    except sqlite3.OperationalError:
        pass  # Index already exists

    # Scheduler lock table for multi-instance safety
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_lock (
            name TEXT PRIMARY KEY,
            locked_by TEXT NOT NULL,
            locked_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _migrate_v34_to_v35(conn: sqlite3.Connection) -> None:
    """V34 -> V35: Listening progress tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listening_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            passage_id TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            comprehension_score REAL DEFAULT 0.0,
            questions_correct INTEGER DEFAULT 0,
            questions_total INTEGER DEFAULT 0,
            words_looked_up INTEGER DEFAULT 0,
            hsk_level INTEGER DEFAULT 1
        )
    """)
    conn.commit()


def _migrate_v35_to_v36(conn: sqlite3.Connection) -> None:
    """V35 -> V36: Add referred_by_teacher to user table for student upgrade commissions."""
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(user)").fetchall()}
    if "referred_by_teacher" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN referred_by_teacher INTEGER")
    conn.commit()


def _migrate_v36_to_v37(conn: sqlite3.Connection) -> None:
    """V36 -> V37: Add 'number' to error_log error_type CHECK constraint.

    SQLite can't ALTER CHECK constraints, so we recreate the table.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(error_log)").fetchall()}
    if not cols:
        return  # Table doesn't exist yet
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS error_log_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            session_id INTEGER,
            content_item_id INTEGER NOT NULL,
            modality TEXT NOT NULL,
            error_type TEXT NOT NULL DEFAULT 'other'
                CHECK (error_type IN (
                    'tone', 'segment', 'ime_confusable', 'grammar', 'vocab', 'other',
                    'register_mismatch', 'particle_misuse', 'function_word_omission',
                    'temporal_sequencing', 'measure_word', 'politeness_softening',
                    'reference_tracking', 'pragmatics_mismatch', 'number'
                )),
            user_answer TEXT,
            expected_answer TEXT,
            drill_type TEXT,
            notes TEXT,
            tone_user INTEGER,
            tone_expected INTEGER,
            FOREIGN KEY (session_id) REFERENCES session_log(id),
            FOREIGN KEY (content_item_id) REFERENCES content_item(id)
        );
        INSERT OR IGNORE INTO error_log_new
            (id, user_id, created_at, session_id, content_item_id, modality,
             error_type, user_answer, expected_answer, drill_type, notes,
             tone_user, tone_expected)
            SELECT id, user_id, created_at, session_id, content_item_id, modality,
                   error_type, user_answer, expected_answer, drill_type, notes,
                   tone_user, tone_expected
            FROM error_log;
        DROP TABLE IF EXISTS error_log;
        ALTER TABLE error_log_new RENAME TO error_log;
        CREATE INDEX IF NOT EXISTS idx_error_type ON error_log(error_type);
        CREATE INDEX IF NOT EXISTS idx_error_session ON error_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_error_item ON error_log(content_item_id);
    """)
    conn.commit()


def _migrate_v37_to_v38(conn: sqlite3.Connection) -> None:
    """V37 -> V38: Add personality content lens columns to learner_profile."""
    cols = _col_set(conn, "learner_profile")
    for col in (
        "lens_wit", "lens_ensemble_comedy", "lens_sharp_observation",
        "lens_satire", "lens_moral_texture",
    ):
        if col not in cols:
            conn.execute(
                f"ALTER TABLE learner_profile ADD COLUMN {col} REAL NOT NULL DEFAULT 0.7"
            )
    conn.commit()


def _migrate_v38_to_v39(conn: sqlite3.Connection) -> None:
    """V38 -> V39: Tech debt remediation — missing columns, lifecycle_event type fix, indexes, retention seeds."""
    # C-1: Add missing columns to user table
    user_cols = _col_set(conn, "user")
    for col, default in (
        ("totp_secret", "TEXT"),
        ("totp_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("totp_backup_codes", "TEXT"),
        ("email_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("email_verify_token", "TEXT"),
        ("email_verify_expires", "TEXT"),
        ("marketing_opt_out", "INTEGER NOT NULL DEFAULT 0"),
        ("anonymous_mode", "INTEGER NOT NULL DEFAULT 0"),
        ("role", "TEXT NOT NULL DEFAULT 'student'"),
        ("push_token", "TEXT"),
    ):
        if col not in user_cols:
            conn.execute(f"ALTER TABLE user ADD COLUMN {col} {default}")

    # C-1: Add missing columns to learner_profile
    lp_cols = _col_set(conn, "learner_profile")
    if "streak_reminders" not in lp_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN streak_reminders INTEGER NOT NULL DEFAULT 1")
    if "preferred_voice" not in lp_cols:
        conn.execute("ALTER TABLE learner_profile ADD COLUMN preferred_voice TEXT")

    # C-1: Add event_id to client_event
    ce_cols = _col_set(conn, "client_event")
    if "event_id" not in ce_cols:
        conn.execute("ALTER TABLE client_event ADD COLUMN event_id TEXT")

    # M-4: Recreate lifecycle_event with user_id INTEGER
    if "lifecycle_event" in _table_set(conn):
        le_cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(lifecycle_event)").fetchall()}
        if le_cols.get("user_id", "").upper() == "TEXT":
            conn.execute("""CREATE TABLE IF NOT EXISTS lifecycle_event_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
            conn.execute("""INSERT INTO lifecycle_event_new (id, event_type, user_id, metadata, created_at)
                SELECT id, event_type, CAST(user_id AS INTEGER), metadata, created_at
                FROM lifecycle_event""")
            conn.execute("DROP TABLE IF EXISTS lifecycle_event")
            conn.execute("ALTER TABLE lifecycle_event_new RENAME TO lifecycle_event")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_event_type ON lifecycle_event(event_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_user ON lifecycle_event(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_created ON lifecycle_event(created_at)")

    # M-5: Fix bootstrap user tier from 'admin' to 'free'
    conn.execute("UPDATE user SET subscription_tier = 'free' WHERE id = 1 AND subscription_tier = 'admin'")

    # M-10: Add index on security_audit_log.severity
    conn.execute("CREATE INDEX IF NOT EXISTS idx_security_audit_severity ON security_audit_log(severity)")

    # L-3: Seed retention policies
    conn.execute("""INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description)
        VALUES ('crash_log', 90, 'Server crash logs — 90 day retention')""")
    conn.execute("""INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description)
        VALUES ('client_error_log', 30, 'Client error reports — 30 day retention')""")
    conn.execute("""INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description)
        VALUES ('security_audit_log', 365, 'Security audit events — 1 year retention')""")

    conn.commit()


def _migrate_v39_to_v40(conn: sqlite3.Connection) -> None:
    """V39 -> V40: Per-item tone mastery, review_event table."""
    prog_cols = _col_set(conn, "progress")
    if "tone_attempts" not in prog_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN tone_attempts INTEGER NOT NULL DEFAULT 0")
    if "tone_correct" not in prog_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN tone_correct INTEGER NOT NULL DEFAULT 0")

    # Review event log (Doctrine §12: per-review instrumentation)
    if "review_event" not in _table_set(conn):
        conn.execute("""CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            session_id INTEGER,
            content_item_id INTEGER NOT NULL,
            modality TEXT NOT NULL,
            drill_type TEXT,
            correct INTEGER NOT NULL,
            confidence TEXT DEFAULT 'full',
            response_ms INTEGER,
            error_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (content_item_id) REFERENCES content_item(id),
            FOREIGN KEY (session_id) REFERENCES session_log(id),
            FOREIGN KEY (user_id) REFERENCES user(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_event_user ON review_event(user_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_event_item ON review_event(content_item_id)")
    conn.commit()


def _migrate_v40_to_v41(conn: sqlite3.Connection) -> None:
    """V40 -> V41: Security scan tables for automated SAST + dependency scanning."""
    tables = _table_set(conn)
    if "security_scan" not in tables:
        conn.execute("""CREATE TABLE security_scan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_type TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            summary TEXT,
            error_message TEXT,
            duration_seconds INTEGER
        )""")
    if "security_scan_finding" not in tables:
        conn.execute("""CREATE TABLE security_scan_finding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            file_path TEXT,
            line_number INTEGER,
            package_name TEXT,
            installed_version TEXT,
            fixed_version TEXT,
            FOREIGN KEY (scan_id) REFERENCES security_scan(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_finding_scan ON security_scan_finding(scan_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_finding_severity ON security_scan_finding(severity)")
    conn.commit()


def _migrate_v41_to_v42(conn: sqlite3.Connection) -> None:
    """V42: Quality metrics, SPC, risk register, work items, request timing."""
    logger.info("Migration v41→v42: quality infrastructure tables")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_metric (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_type TEXT NOT NULL,
            value REAL NOT NULL,
            details TEXT,
            measured_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_metric_type ON quality_metric(metric_type, measured_at)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS spc_observation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chart_type TEXT NOT NULL,
            value REAL NOT NULL,
            subgroup_size INTEGER DEFAULT 1,
            observed_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spc_observation_type ON spc_observation(chart_type, observed_at)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            probability INTEGER NOT NULL DEFAULT 3,
            impact INTEGER NOT NULL DEFAULT 3,
            mitigation TEXT,
            contingency TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            owner TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_item_status ON risk_item(status)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS work_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            item_type TEXT NOT NULL DEFAULT 'standard',
            status TEXT NOT NULL DEFAULT 'backlog',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            ready_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            blocked_at TEXT,
            unblocked_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_item_status ON work_item(status)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS request_timing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            method TEXT NOT NULL DEFAULT 'GET',
            status_code INTEGER,
            duration_ms REAL NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_request_timing_path ON request_timing(path, recorded_at)")

    # Performance index for session planning (get_items_due queries by user+modality+date)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_progress_user_modality_due ON progress(user_id, modality, next_review_date)")


def _migrate_v42_to_v43(conn: sqlite3.Connection) -> None:
    """V43: Streak freeze support for streak recovery mechanism."""
    logger.info("Migration v42→v43: streak_freezes_available column on user")
    try:
        conn.execute("ALTER TABLE user ADD COLUMN streak_freezes_available INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_v43_to_v44(conn: sqlite3.Connection) -> None:
    """v43→v44: Add service_class and review_at to work_item for Kanban service classes."""
    logger.info("Migration v43→v44: service_class and review_at on work_item")
    for col, col_def in [
        ("service_class", "TEXT DEFAULT 'standard'"),
        ("review_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE work_item ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def _migrate_v44_to_v45(conn: sqlite3.Connection) -> None:
    """v44→v45: Add client_platform to session_log for platform analytics."""
    logger.info("Migration v44→v45: client_platform on session_log")
    try:
        conn.execute("ALTER TABLE session_log ADD COLUMN client_platform TEXT DEFAULT 'web'")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_v45_to_v46(conn: sqlite3.Connection) -> None:
    """v45→v46: Sprint table for Scrum methodology + session_retrospective column."""
    logger.info("Migration v45→v46: sprint table, session_retrospective, risk_event table")
    tables = _table_set(conn)

    # Sprint table for Scrum sprint tracking
    if "sprint" not in tables:
        conn.execute("""
            CREATE TABLE sprint (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sprint_number INTEGER NOT NULL,
                goal TEXT,
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT,
                planned_items INTEGER,
                completed_items INTEGER,
                planned_points INTEGER,
                completed_points INTEGER,
                velocity REAL,
                accuracy_trend REAL,
                status TEXT DEFAULT 'active',
                retrospective TEXT,
                UNIQUE(user_id, sprint_number)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sprint_user_status ON sprint(user_id, status)")
        conn.commit()

    # Session retrospective column for Agile mini-retros
    session_cols = _col_set(conn, "session_log")
    if "retrospective_json" not in session_cols:
        try:
            conn.execute("ALTER TABLE session_log ADD COLUMN retrospective_json TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Risk event table for Spiral risk tracking
    if "risk_event" not in tables:
        conn.execute("""
            CREATE TABLE risk_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                risk_category TEXT NOT NULL,
                risk_type TEXT NOT NULL,
                severity TEXT DEFAULT 'medium',
                description TEXT NOT NULL,
                source TEXT,
                data_json TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_event_status ON risk_event(status)")
        conn.commit()


def _migrate_v46_to_v47(conn: sqlite3.Connection) -> None:
    """v46→v47: Experiment registry, assignment, exposure tables + session_log experiment_variant column."""
    logger.info("Migration v46→v47: experiment infrastructure tables")
    tables = _table_set(conn)

    if "experiment" not in tables:
        conn.execute("""
            CREATE TABLE experiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                status TEXT DEFAULT 'draft',
                variants TEXT NOT NULL,
                traffic_pct REAL DEFAULT 100.0,
                guardrail_metrics TEXT,
                min_sample_size INTEGER DEFAULT 100,
                created_at TEXT DEFAULT (datetime('now')),
                started_at TEXT,
                concluded_at TEXT,
                conclusion TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_experiment_status ON experiment(status)")
        conn.commit()

    if "experiment_assignment" not in tables:
        conn.execute("""
            CREATE TABLE experiment_assignment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                variant TEXT NOT NULL,
                assigned_at TEXT DEFAULT (datetime('now')),
                UNIQUE(experiment_id, user_id),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_experiment_assignment_exp ON experiment_assignment(experiment_id, user_id)")
        conn.commit()

    if "experiment_exposure" not in tables:
        conn.execute("""
            CREATE TABLE experiment_exposure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                variant TEXT NOT NULL,
                context TEXT,
                exposed_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_experiment_exposure_exp ON experiment_exposure(experiment_id, user_id)")
        conn.commit()

    # Add experiment_variant column to session_log
    session_cols = _col_set(conn, "session_log")
    if "experiment_variant" not in session_cols:
        try:
            conn.execute("ALTER TABLE session_log ADD COLUMN experiment_variant TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _migrate_v47_to_v48(conn: sqlite3.Connection) -> None:
    """v47→v48: Passage comments, classroom assignments, study buddy opt-in, reading speed tracking."""
    logger.info("Migration v47→v48: passage_comment, classroom_assignment, find_study_partner")
    tables = _table_set(conn)

    # Passage comment table for community discussion
    if "passage_comment" not in tables:
        conn.execute("""
            CREATE TABLE passage_comment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                passage_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_passage_comment_passage ON passage_comment(passage_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_passage_comment_user ON passage_comment(user_id)")
        conn.commit()

    # Classroom assignment table for teacher-assigned drills
    if "classroom_assignment" not in tables:
        conn.execute("""
            CREATE TABLE classroom_assignment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classroom_id INTEGER NOT NULL,
                teacher_user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                hsk_level INTEGER,
                content_item_ids TEXT,
                drill_types TEXT,
                due_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (classroom_id) REFERENCES classroom(id),
                FOREIGN KEY (teacher_user_id) REFERENCES user(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_classroom_assignment_class ON classroom_assignment(classroom_id)")
        conn.commit()

    # Add find_study_partner to user table for buddy matching
    user_cols = _col_set(conn, "user")
    if "find_study_partner" not in user_cols:
        try:
            conn.execute("ALTER TABLE user ADD COLUMN find_study_partner INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists


def _migrate_v48_to_v49(conn: sqlite3.Connection) -> None:
    """v48→v49: Product audit history table for product intelligence trending."""
    logger.info("Migration v48→v49: product_audit table")
    tables = _table_set(conn)
    if "product_audit" not in tables:
        conn.execute("""
            CREATE TABLE product_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL DEFAULT (datetime('now')),
                overall_grade TEXT NOT NULL,
                overall_score REAL NOT NULL,
                dimension_scores TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                findings_count INTEGER NOT NULL,
                critical_count INTEGER NOT NULL DEFAULT 0,
                high_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_product_audit_run_at ON product_audit(run_at)")
    conn.commit()


def _migrate_v49_to_v50(conn: sqlite3.Connection) -> None:
    """v49→v50: pi_finding — finding lifecycle with state machine."""
    logger.info("Migration v49→v50: pi_finding table")
    tables = _table_set(conn)
    if "pi_finding" not in tables:
        conn.execute("""
            CREATE TABLE pi_finding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id INTEGER REFERENCES product_audit(id),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                dimension TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                analysis TEXT,
                status TEXT NOT NULL DEFAULT 'investigating'
                    CHECK(status IN ('investigating','diagnosed','recommended',
                                     'implemented','verified','resolved','rejected')),
                hypothesis TEXT,
                falsification TEXT,
                root_cause_tag TEXT,
                linked_finding_id INTEGER REFERENCES pi_finding(id),
                metric_name TEXT,
                metric_value_at_detection REAL,
                times_seen INTEGER NOT NULL DEFAULT 1,
                last_seen_audit_id INTEGER,
                resolved_at TEXT,
                resolution_notes TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_finding_status ON pi_finding(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_finding_dimension ON pi_finding(dimension)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_finding_audit ON pi_finding(audit_id)")
    conn.commit()


def _migrate_v50_to_v51(conn: sqlite3.Connection) -> None:
    """v50→v51: pi_recommendation_outcome — feedback loop closure."""
    logger.info("Migration v50→v51: pi_recommendation_outcome table")
    tables = _table_set(conn)
    if "pi_recommendation_outcome" not in tables:
        conn.execute("""
            CREATE TABLE pi_recommendation_outcome (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                action_type TEXT NOT NULL
                    CHECK(action_type IN ('code_change','config_change','content_change','experiment')),
                action_description TEXT,
                files_changed TEXT,
                commit_hash TEXT,
                metric_before TEXT,
                metric_after TEXT,
                verified_at TEXT,
                delta_pct REAL,
                effective INTEGER CHECK(effective IN (-1, 0, 1))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_rec_outcome_finding ON pi_recommendation_outcome(finding_id)")
    conn.commit()


def _migrate_v51_to_v52(conn: sqlite3.Connection) -> None:
    """v51→v52: pi_decision_log — human decisions."""
    logger.info("Migration v51→v52: pi_decision_log table")
    tables = _table_set(conn)
    if "pi_decision_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                decision_class TEXT NOT NULL
                    CHECK(decision_class IN ('auto_fix','informed_fix','judgment_call',
                                             'values_decision','investigation')),
                escalation_level TEXT NOT NULL
                    CHECK(escalation_level IN ('quiet','nudge','alert','escalate','emergency')),
                presented_to TEXT
                    CHECK(presented_to IN ('solo','developer','product_owner','teacher')),
                context_json TEXT,
                decision TEXT,
                decision_reason TEXT,
                override_expires_at TEXT,
                outcome_notes TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_decision_finding ON pi_decision_log(finding_id)")
    conn.commit()


def _migrate_v52_to_v53(conn: sqlite3.Connection) -> None:
    """v52→v53: pi_advisor_opinion — per-finding advisor evaluations."""
    logger.info("Migration v52→v53: pi_advisor_opinion table")
    tables = _table_set(conn)
    if "pi_advisor_opinion" not in tables:
        conn.execute("""
            CREATE TABLE pi_advisor_opinion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
                advisor TEXT NOT NULL
                    CHECK(advisor IN ('retention','learning','growth','stability')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                recommendation TEXT,
                priority_score REAL NOT NULL DEFAULT 0,
                effort_estimate REAL,
                rationale TEXT,
                tradeoff_notes TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_advisor_finding ON pi_advisor_opinion(finding_id)")
    conn.commit()


def _migrate_v53_to_v54(conn: sqlite3.Connection) -> None:
    """v53→v54: pi_advisor_resolution — mediator conflict resolution."""
    logger.info("Migration v53→v54: pi_advisor_resolution table")
    tables = _table_set(conn)
    if "pi_advisor_resolution" not in tables:
        conn.execute("""
            CREATE TABLE pi_advisor_resolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                winning_advisor TEXT,
                resolution_rationale TEXT,
                tradeoff_summary TEXT,
                weekly_effort_budget REAL,
                constraint_notes TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_resolution_finding ON pi_advisor_resolution(finding_id)")
    conn.commit()


def _migrate_v54_to_v55(conn: sqlite3.Connection) -> None:
    """v54→v55: pi_threshold_calibration — self-calibrating thresholds."""
    logger.info("Migration v54→v55: pi_threshold_calibration table")
    tables = _table_set(conn)
    if "pi_threshold_calibration" not in tables:
        conn.execute("""
            CREATE TABLE pi_threshold_calibration (
                metric_name TEXT PRIMARY KEY,
                threshold_value REAL NOT NULL,
                calibrated_at TEXT NOT NULL DEFAULT (datetime('now')),
                sample_size INTEGER,
                false_positive_rate REAL,
                false_negative_rate REAL,
                prior_threshold REAL,
                notes TEXT
            )
        """)
    conn.commit()


def _migrate_v55_to_v56(conn: sqlite3.Connection) -> None:
    """v55→v56: Intelligence engine A+ — false negative signals, DMAIC log, extra columns."""
    logger.info("Migration v55→v56: intelligence engine A+ tables")
    tables = _table_set(conn)

    if "pi_false_negative_signal" not in tables:
        conn.execute("""
            CREATE TABLE pi_false_negative_signal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_source TEXT NOT NULL,
                signal_id TEXT,
                dimension TEXT,
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                had_finding INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_fns_source ON pi_false_negative_signal(signal_source)")

    if "pi_dmaic_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_dmaic_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dimension TEXT NOT NULL,
                define_json TEXT,
                measure_json TEXT,
                analyze_json TEXT,
                improve_json TEXT,
                control_json TEXT,
                run_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_dmaic_dim ON pi_dmaic_log(dimension)")

    # Add gate_blocked and gate_reason to pi_dmaic_log (Six Sigma tollgates)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pi_dmaic_log)").fetchall()}
    if "gate_blocked" not in cols:
        conn.execute("ALTER TABLE pi_dmaic_log ADD COLUMN gate_blocked TEXT")
    if "gate_reason" not in cols:
        conn.execute("ALTER TABLE pi_dmaic_log ADD COLUMN gate_reason TEXT")

    # Add verification_window_days to pi_threshold_calibration
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pi_threshold_calibration)").fetchall()}
    if "verification_window_days" not in cols:
        conn.execute("ALTER TABLE pi_threshold_calibration ADD COLUMN verification_window_days INTEGER")

    # Add requires_approval and approved_at to pi_decision_log
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pi_decision_log)").fetchall()}
    if "requires_approval" not in cols:
        conn.execute("ALTER TABLE pi_decision_log ADD COLUMN requires_approval INTEGER NOT NULL DEFAULT 0")
    if "approved_at" not in cols:
        conn.execute("ALTER TABLE pi_decision_log ADD COLUMN approved_at TEXT")

    conn.commit()


def _migrate_v56_to_v57(conn: sqlite3.Connection) -> None:
    """v56→v57: Self-correction layer — prediction ledger, outcomes, model confidence, self-audit."""
    logger.info("Migration v56→v57: self-correction layer tables")
    tables = _table_set(conn)

    if "pi_prediction_ledger" not in tables:
        conn.execute("""
            CREATE TABLE pi_prediction_ledger (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                finding_id INTEGER NOT NULL,
                model_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                claim_type TEXT NOT NULL CHECK (claim_type IN (
                    'metric_will_improve', 'metric_will_worsen',
                    'no_change', 'threshold_will_be_breached'
                )),
                metric_name TEXT NOT NULL,
                metric_baseline REAL NOT NULL,
                predicted_delta REAL NOT NULL,
                predicted_delta_confidence REAL NOT NULL CHECK (
                    predicted_delta_confidence BETWEEN 0 AND 1
                ),
                verification_window_days INTEGER NOT NULL,
                verification_due_at TEXT NOT NULL,
                outcome_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                    'pending', 'verified', 'expired', 'invalidated'
                ))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_pred_finding ON pi_prediction_ledger(finding_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_pred_status ON pi_prediction_ledger(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_pred_due ON pi_prediction_ledger(verification_due_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_pred_model ON pi_prediction_ledger(model_id)")

    if "pi_prediction_outcomes" not in tables:
        conn.execute("""
            CREATE TABLE pi_prediction_outcomes (
                id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                metric_actual REAL NOT NULL,
                actual_delta REAL NOT NULL,
                direction_correct INTEGER NOT NULL,
                magnitude_error REAL NOT NULL,
                outcome_class TEXT NOT NULL CHECK (outcome_class IN (
                    'correct', 'directionally_correct', 'wrong', 'insufficient_data'
                ))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_pred_out_pred ON pi_prediction_outcomes(prediction_id)")

    if "pi_model_confidence" not in tables:
        conn.execute("""
            CREATE TABLE pi_model_confidence (
                model_id TEXT PRIMARY KEY,
                dimension TEXT NOT NULL,
                correct_count INTEGER NOT NULL DEFAULT 0,
                directionally_correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                insufficient_data_count INTEGER NOT NULL DEFAULT 0,
                measurement_failure_count INTEGER NOT NULL DEFAULT 0,
                current_confidence REAL NOT NULL DEFAULT 0.5,
                last_updated TEXT
            )
        """)

    if "pi_self_audit_report" not in tables:
        conn.execute("""
            CREATE TABLE pi_self_audit_report (
                id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                lookback_days INTEGER NOT NULL,
                total_predictions INTEGER,
                correct_count INTEGER,
                directionally_correct_count INTEGER,
                wrong_count INTEGER,
                expired_count INTEGER,
                invalidated_count INTEGER,
                insufficient_data_count INTEGER,
                worst_models_json TEXT,
                best_models_json TEXT,
                current_constraint TEXT,
                constraint_confidence REAL,
                human_override_accuracy REAL,
                engine_accuracy REAL,
                override_domains_json TEXT,
                report_json TEXT
            )
        """)

    conn.commit()


def _migrate_v57_to_v58(conn: sqlite3.Connection) -> None:
    """v57→v58: Prescription layer — pi_work_order table."""
    logger.info("Migration v57→v58: prescription layer work order table")
    tables = _table_set(conn)

    if "pi_work_order" not in tables:
        conn.execute("""
            CREATE TABLE pi_work_order (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_cycle_id INTEGER NOT NULL,
                finding_id INTEGER NOT NULL,
                prediction_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                constraint_dimension TEXT NOT NULL,
                constraint_score REAL NOT NULL,
                marginal_improvement REAL NOT NULL,
                instruction TEXT NOT NULL,
                target_file TEXT,
                target_parameter TEXT,
                direction TEXT,
                success_metric TEXT NOT NULL,
                success_baseline REAL NOT NULL,
                success_threshold REAL NOT NULL,
                verification_window_days INTEGER NOT NULL,
                verification_due_at TEXT,
                subordinated_count INTEGER NOT NULL DEFAULT 0,
                subordinated_finding_ids TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN (
                        'pending', 'verifying', 'succeeded',
                        'failed', 'stale', 'superseded'
                    )),
                implemented_at TEXT,
                verified_at TEXT,
                outcome_notes TEXT,
                confidence_label TEXT,
                confidence_score REAL,
                instruction_source TEXT DEFAULT 'legacy_lookup'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_status ON pi_work_order(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_finding ON pi_work_order(finding_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_audit ON pi_work_order(audit_cycle_id)")

    conn.commit()


def _migrate_v58_to_v59(conn: sqlite3.Connection) -> None:
    """v58→v59: Parameter Graph — registry, history, influence edges."""
    logger.info("Migration v58→v59: parameter graph tables")
    tables = _table_set(conn)

    if "pi_parameter_registry" not in tables:
        conn.execute("""
            CREATE TABLE pi_parameter_registry (
                id TEXT PRIMARY KEY,
                parameter_name TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL,
                current_value REAL,
                current_value_str TEXT,
                value_type TEXT NOT NULL CHECK (
                    value_type IN ('float', 'int', 'ratio', 'bool', 'enum')
                ),
                min_valid REAL,
                max_valid REAL,
                soft_min REAL,
                soft_max REAL,
                primary_dimension TEXT NOT NULL,
                secondary_dimensions TEXT,
                change_direction TEXT CHECK (
                    change_direction IN ('increase', 'decrease', 'either', 'unknown')
                ),
                last_changed_at TEXT,
                last_changed_by TEXT,
                change_count INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                registered_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "pi_parameter_history" not in tables:
        conn.execute("""
            CREATE TABLE pi_parameter_history (
                id TEXT PRIMARY KEY,
                parameter_id TEXT NOT NULL REFERENCES pi_parameter_registry(id),
                changed_at TEXT NOT NULL DEFAULT (datetime('now')),
                old_value REAL,
                new_value REAL,
                changed_by TEXT NOT NULL,
                work_order_id INTEGER REFERENCES pi_work_order(id),
                metric_before REAL,
                metric_after REAL,
                metric_name TEXT,
                delta_achieved REAL,
                outcome_class TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_param ON pi_parameter_history(parameter_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_wo ON pi_parameter_history(work_order_id)")

    if "pi_influence_edges" not in tables:
        conn.execute("""
            CREATE TABLE pi_influence_edges (
                id TEXT PRIMARY KEY,
                parameter_id TEXT NOT NULL REFERENCES pi_parameter_registry(id),
                metric_name TEXT NOT NULL,
                dimension TEXT NOT NULL,
                observation_count INTEGER NOT NULL DEFAULT 0,
                positive_effect_count INTEGER NOT NULL DEFAULT 0,
                negative_effect_count INTEGER NOT NULL DEFAULT 0,
                null_effect_count INTEGER NOT NULL DEFAULT 0,
                mean_delta_achieved REAL,
                weight REAL NOT NULL DEFAULT 0.5,
                weight_confidence REAL NOT NULL DEFAULT 0.1,
                last_updated TEXT,
                learned_direction TEXT CHECK (
                    learned_direction IN ('increase', 'decrease', 'nonlinear', 'unknown')
                ) DEFAULT 'unknown'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ie_param ON pi_influence_edges(parameter_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ie_dim ON pi_influence_edges(dimension)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ie_param_metric "
            "ON pi_influence_edges(parameter_id, metric_name)"
        )

    # Add instruction_source column to pi_work_order if missing
    wo_cols = _col_set(conn, "pi_work_order")
    if "instruction_source" not in wo_cols:
        conn.execute(
            "ALTER TABLE pi_work_order ADD COLUMN instruction_source TEXT DEFAULT 'legacy_lookup'"
        )

    conn.commit()


def _migrate_v59_to_v60(conn: sqlite3.Connection) -> None:
    """v59→v60: Collaborator Model — interaction log, model, domain trust."""
    logger.info("Migration v59→v60: collaborator model tables")
    tables = _table_set(conn)

    if "pi_interaction_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_interaction_log (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                interaction_type TEXT NOT NULL CHECK (interaction_type IN (
                    'work_order_viewed',
                    'work_order_implemented',
                    'work_order_delayed',
                    'work_order_overridden',
                    'finding_approved',
                    'finding_dismissed',
                    'subordination_overridden',
                    'self_audit_viewed',
                    'parameter_graph_viewed',
                    'override_reason_provided',
                    'correction'
                )),
                work_order_id INTEGER REFERENCES pi_work_order(id),
                finding_id INTEGER,
                dimension TEXT,
                day_of_week INTEGER,
                hour_of_day INTEGER,
                days_since_work_order_issued INTEGER,
                model_confidence_at_time REAL,
                severity_at_time TEXT,
                was_constraint_dimension INTEGER,
                subsequent_outcome_class TEXT,
                notes TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_il_type ON pi_interaction_log(interaction_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_il_occurred ON pi_interaction_log(occurred_at)"
        )

    if "pi_collaborator_model" not in tables:
        conn.execute("""
            CREATE TABLE pi_collaborator_model (
                id TEXT PRIMARY KEY DEFAULT 'singleton',
                generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_updated TEXT NOT NULL DEFAULT (datetime('now')),
                observation_count INTEGER NOT NULL DEFAULT 0,
                median_implementation_days REAL,
                fastest_dimension TEXT,
                slowest_dimension TEXT,
                preferred_day_of_week INTEGER,
                preferred_hour_of_day INTEGER,
                timing_confidence REAL DEFAULT 0.1,
                override_rate_overall REAL,
                override_accuracy_overall REAL,
                domains_where_human_leads TEXT,
                domains_where_engine_leads TEXT,
                override_confidence REAL DEFAULT 0.1,
                reads_self_audit INTEGER DEFAULT 0,
                reads_parameter_graph INTEGER DEFAULT 0,
                provides_override_reasons INTEGER DEFAULT 0,
                responds_to_specific_parameters INTEGER DEFAULT 0,
                responds_to_rationale INTEGER DEFAULT 0,
                responds_to_confidence_labels INTEGER DEFAULT 0,
                presentation_confidence REAL DEFAULT 0.1,
                data_quality TEXT DEFAULT 'insufficient',
                model_notes TEXT,
                adaptations_disabled INTEGER DEFAULT 0
            )
        """)

    if "pi_collaborator_model_history" not in tables:
        conn.execute("""
            CREATE TABLE pi_collaborator_model_history (
                id TEXT PRIMARY KEY,
                snapshot_at TEXT NOT NULL DEFAULT (datetime('now')),
                model_json TEXT NOT NULL,
                observation_count_at_snapshot INTEGER,
                significant_change TEXT
            )
        """)

    if "pi_domain_trust" not in tables:
        conn.execute("""
            CREATE TABLE pi_domain_trust (
                dimension TEXT PRIMARY KEY,
                engine_confidence REAL NOT NULL DEFAULT 0.5,
                engine_scored_predictions INTEGER NOT NULL DEFAULT 0,
                human_override_count INTEGER NOT NULL DEFAULT 0,
                human_correct_count INTEGER NOT NULL DEFAULT 0,
                human_wrong_count INTEGER NOT NULL DEFAULT 0,
                human_confidence REAL NOT NULL DEFAULT 0.5,
                trust_leader TEXT CHECK (
                    trust_leader IN ('engine', 'human', 'tied', 'insufficient_data')
                ) DEFAULT 'insufficient_data',
                trust_margin REAL,
                override_requires_reason INTEGER NOT NULL DEFAULT 0,
                escalation_persistence TEXT NOT NULL DEFAULT 'normal'
                    CHECK (escalation_persistence IN ('low', 'normal', 'high')),
                last_updated TEXT
            )
        """)

    conn.commit()


def _migrate_v60_to_v61(conn: sqlite3.Connection) -> None:
    """v60→v61: External Grounding — pedagogical knowledge, benchmarks, goal coherence."""
    logger.info("Migration v60→v61: external grounding tables")
    tables = _table_set(conn)

    if "pi_pedagogical_knowledge" not in tables:
        conn.execute("""
            CREATE TABLE pi_pedagogical_knowledge (
                id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                finding_text TEXT NOT NULL,
                source_author TEXT NOT NULL,
                source_year INTEGER NOT NULL,
                source_title TEXT NOT NULL,
                evidence_quality TEXT NOT NULL CHECK (evidence_quality IN (
                    'meta_analysis', 'rct', 'longitudinal',
                    'cross_sectional', 'expert_consensus', 'theoretical'
                )),
                applicable_metric TEXT,
                applicable_dimension TEXT,
                implied_threshold_low REAL,
                implied_threshold_high REAL,
                implied_direction TEXT CHECK (
                    implied_direction IN ('higher_is_better', 'lower_is_better',
                                          'range_optimal', 'context_dependent', 'unknown')
                ),
                applicability_notes TEXT,
                applicability_confidence REAL,
                encoded_at TEXT NOT NULL DEFAULT (datetime('now')),
                encoded_by TEXT NOT NULL DEFAULT 'human',
                last_reviewed TEXT,
                superseded_by TEXT REFERENCES pi_pedagogical_knowledge(id),
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pk_domain ON pi_pedagogical_knowledge(domain)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pk_active ON pi_pedagogical_knowledge(active)"
        )

    if "pi_knowledge_conflicts" not in tables:
        conn.execute("""
            CREATE TABLE pi_knowledge_conflicts (
                id TEXT PRIMARY KEY,
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                knowledge_id TEXT NOT NULL REFERENCES pi_pedagogical_knowledge(id),
                dimension TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                engine_threshold REAL,
                engine_direction TEXT,
                engine_confidence REAL,
                literature_threshold_low REAL,
                literature_threshold_high REAL,
                literature_direction TEXT,
                evidence_quality TEXT,
                conflict_severity TEXT CHECK (
                    conflict_severity IN ('minor', 'moderate', 'significant', 'critical')
                ),
                resolution TEXT CHECK (
                    resolution IN (
                        'engine_defers_to_literature',
                        'literature_noted_engine_proceeds',
                        'human_review_required',
                        'unresolved'
                    )
                ),
                resolution_rationale TEXT,
                resolved_at TEXT,
                resolved_by TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kc_status ON pi_knowledge_conflicts(resolution)"
        )

    if "pi_benchmark_registry" not in tables:
        conn.execute("""
            CREATE TABLE pi_benchmark_registry (
                id TEXT PRIMARY KEY,
                benchmark_name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applicable_hsk_range_low INTEGER,
                applicable_hsk_range_high INTEGER,
                applicable_study_hours_min INTEGER,
                applicable_study_hours_max INTEGER,
                learner_profile TEXT,
                population_median REAL,
                population_p25 REAL,
                population_p75 REAL,
                population_n INTEGER,
                aelu_metric_name TEXT,
                aelu_dimension TEXT,
                source TEXT NOT NULL,
                source_year INTEGER,
                evidence_quality TEXT NOT NULL,
                encoded_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_reviewed TEXT,
                review_interval_days INTEGER DEFAULT 365,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)

    if "pi_benchmark_comparisons" not in tables:
        conn.execute("""
            CREATE TABLE pi_benchmark_comparisons (
                id TEXT PRIMARY KEY,
                compared_at TEXT NOT NULL DEFAULT (datetime('now')),
                benchmark_id TEXT NOT NULL REFERENCES pi_benchmark_registry(id),
                your_value REAL NOT NULL,
                population_median REAL NOT NULL,
                your_percentile REAL,
                interpretation TEXT NOT NULL,
                finding_warranted INTEGER NOT NULL,
                finding_id TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bc_benchmark ON pi_benchmark_comparisons(benchmark_id)"
        )

    if "pi_goal_coherence_check" not in tables:
        conn.execute("""
            CREATE TABLE pi_goal_coherence_check (
                id TEXT PRIMARY KEY,
                checked_at TEXT NOT NULL DEFAULT (datetime('now')),
                estimated_hsk_level INTEGER NOT NULL,
                stage_range_low INTEGER NOT NULL,
                stage_range_high INTEGER NOT NULL,
                coherent INTEGER NOT NULL,
                issues_json TEXT,
                message TEXT NOT NULL,
                finding_id INTEGER
            )
        """)

    conn.commit()


def _migrate_v61_to_v62(conn: sqlite3.Connection) -> None:
    """v61→v62: Product Experience — feedback, interaction events, release log."""
    logger.info("Migration v61→v62: product experience tables")
    tables = _table_set(conn)

    if "pi_ux_feedback" not in tables:
        conn.execute("""
            CREATE TABLE pi_ux_feedback (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                feedback_type TEXT NOT NULL CHECK (feedback_type IN (
                    'session_frustration',
                    'item_difficulty',
                    'interface_confusion',
                    'feature_missing',
                    'session_completion'
                )),
                response_value INTEGER NOT NULL,
                screen_name TEXT,
                item_id TEXT,
                triggered_by TEXT,
                primary_dimension TEXT NOT NULL DEFAULT 'frustration',
                secondary_dimension TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uf_type ON pi_ux_feedback(feedback_type, occurred_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uf_session ON pi_ux_feedback(session_id)"
        )

    if "pi_feedback_prompts" not in tables:
        conn.execute("""
            CREATE TABLE pi_feedback_prompts (
                id TEXT PRIMARY KEY,
                prompt_type TEXT NOT NULL,
                prompt_text TEXT,
                trigger_condition TEXT NOT NULL,
                frequency_limit TEXT NOT NULL,
                suppress_if_streak_below INTEGER DEFAULT 3,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)

    if "pi_interaction_events" not in tables:
        conn.execute("""
            CREATE TABLE pi_interaction_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                event_type TEXT NOT NULL,
                screen_name TEXT,
                element_id TEXT,
                item_id TEXT,
                time_on_screen_ms INTEGER,
                time_to_action_ms INTEGER,
                was_correct INTEGER,
                error_code TEXT,
                day_bucket TEXT,
                hour_bucket INTEGER,
                app_version TEXT NOT NULL DEFAULT 'unknown'
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ie_session ON pi_interaction_events(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ie_type ON pi_interaction_events(event_type, occurred_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ie_screen ON pi_interaction_events(screen_name, occurred_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ie_version ON pi_interaction_events(app_version, occurred_at)"
        )

    if "pi_release_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_release_log (
                id TEXT PRIMARY KEY,
                app_version TEXT NOT NULL UNIQUE,
                released_at TEXT NOT NULL DEFAULT (datetime('now')),
                release_notes TEXT,
                changed_ux INTEGER DEFAULT 0,
                changed_srs INTEGER DEFAULT 0,
                changed_content INTEGER DEFAULT 0,
                changed_auth INTEGER DEFAULT 0,
                changed_api INTEGER DEFAULT 0,
                analysis_run_at TEXT,
                analysis_status TEXT CHECK (
                    analysis_status IN ('pending', 'clean', 'regression_detected', 'insufficient_data')
                ) DEFAULT 'pending',
                generated_finding_ids TEXT
            )
        """)

    if "pi_release_metric_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE pi_release_metric_snapshots (
                id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL REFERENCES pi_release_log(id),
                snapshot_type TEXT NOT NULL CHECK (
                    snapshot_type IN ('pre_release', 'post_release_48h', 'post_release_7d')
                ),
                snapshotted_at TEXT NOT NULL DEFAULT (datetime('now')),
                metrics_json TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rms_release ON pi_release_metric_snapshots(release_id)"
        )

    conn.commit()


def _migrate_v62_to_v63(conn: sqlite3.Connection) -> None:
    """v62→v63: Methodology Coverage — framework component registry + grading tables."""
    logger.info("Migration v62→v63: methodology coverage grading tables")
    tables = _table_set(conn)

    if "pi_framework_components" not in tables:
        conn.execute("""
            CREATE TABLE pi_framework_components (
                id TEXT PRIMARY KEY,
                framework TEXT NOT NULL,
                component_name TEXT NOT NULL,
                component_description TEXT NOT NULL,
                solo_dev_applicable TEXT NOT NULL
                    CHECK(solo_dev_applicable IN ('yes','no','partial','when_scaled')),
                applicability_rationale TEXT NOT NULL,
                detection_function TEXT,
                weight REAL NOT NULL DEFAULT 1.0,
                UNIQUE(framework, component_name)
            )
        """)

    if "pi_framework_grades" not in tables:
        conn.execute("""
            CREATE TABLE pi_framework_grades (
                id TEXT PRIMARY KEY,
                graded_at TEXT NOT NULL DEFAULT (datetime('now')),
                audit_cycle_id TEXT,
                framework TEXT NOT NULL,
                component_name TEXT NOT NULL,
                raw_score REAL NOT NULL,
                weighted_score REAL NOT NULL,
                grade_label TEXT NOT NULL,
                evidence TEXT NOT NULL,
                gap_description TEXT,
                recommendation TEXT,
                solo_dev_applicable TEXT NOT NULL,
                was_overridden INTEGER DEFAULT 0,
                override_reason TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fgr_framework ON pi_framework_grades(framework, graded_at)"
        )

    if "pi_framework_summary_grades" not in tables:
        conn.execute("""
            CREATE TABLE pi_framework_summary_grades (
                id TEXT PRIMARY KEY,
                graded_at TEXT NOT NULL DEFAULT (datetime('now')),
                audit_cycle_id TEXT,
                framework TEXT NOT NULL,
                overall_score REAL NOT NULL,
                overall_grade TEXT NOT NULL,
                applicable_component_count INTEGER NOT NULL,
                na_component_count INTEGER NOT NULL,
                gap_count INTEGER NOT NULL,
                prior_grade TEXT,
                trend TEXT CHECK(trend IN ('improving','stable','declining')),
                summary_text TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fsg_framework ON pi_framework_summary_grades(framework, graded_at)"
        )

    # Seed framework components
    _seed_framework_components(conn)

    conn.commit()


def _seed_framework_components(conn: sqlite3.Connection) -> None:
    """Seed the pi_framework_components table with all 9 framework registries."""
    import uuid as _uuid

    components = [
        # ── Six Sigma ──
        ("six_sigma", "DPMO tracking", "Defects Per Million Opportunities measurement for quality quantification", "yes", "Core quality metric applicable at any scale", "check_dpmo_implementation", 1.5),
        ("six_sigma", "Statistical Process Control", "Control charts monitoring process stability over time", "yes", "Essential for detecting out-of-control processes", "check_spc_implementation", 1.5),
        ("six_sigma", "Process capability (Cpk)", "Capability indices measuring process performance vs specifications", "yes", "Measures how well process meets requirements", "check_cpk_implementation", 1.0),
        ("six_sigma", "DMAIC cycle", "Define-Measure-Analyze-Improve-Control improvement methodology", "yes", "Structured problem-solving applicable to solo dev", "check_dmaic_implementation", 1.5),
        ("six_sigma", "Cost of Poor Quality", "Financial quantification of quality failures", "partial", "Useful but financial impact harder to measure for solo dev", "check_copq_implementation", 0.8),
        ("six_sigma", "False negative detection", "Signals for defects the engine missed", "yes", "Critical for engine self-improvement", "check_false_negative_detection", 1.2),
        ("six_sigma", "Bidirectional calibration", "Threshold tuning in both tightening and loosening directions", "yes", "Prevents both over- and under-detection", "check_bidirectional_calibration", 1.0),
        ("six_sigma", "Western Electric rules", "Pattern detection rules for SPC charts", "yes", "Standard SPC pattern recognition", "check_western_electric_rules", 1.0),
        # ── Lean ──
        ("lean", "Value Stream Mapping", "End-to-end flow visualization from input to output", "yes", "Flow analysis applicable at any scale", "check_vsm_implementation", 1.5),
        ("lean", "Waste identification", "Detection and classification of process waste (muda)", "yes", "Core lean principle for efficiency", "check_waste_identification", 1.5),
        ("lean", "Cycle time measurement", "Tracking time from start to completion of work items", "yes", "Essential flow metric", "check_cycle_time_measurement", 1.2),
        ("lean", "Flow metrics", "Throughput and lead time tracking", "yes", "Key lean performance indicators", "check_flow_metrics", 1.2),
        ("lean", "Pull system", "Work pulled based on capacity, not pushed by schedule", "partial", "Partial applicability for solo dev — no team queue", "check_pull_system", 0.8),
        ("lean", "Audit frequency", "Regular cadence of quality audits", "yes", "Ensures continuous monitoring", "check_audit_frequency", 1.0),
        # ── Kanban ──
        ("kanban", "WIP limits", "Work-in-progress limits per workflow stage", "yes", "Prevents overload even for solo dev", "check_wip_limits", 1.5),
        ("kanban", "Service classes", "Priority tiers for different work types", "yes", "Enables expedite vs standard distinction", "check_service_classes", 1.0),
        ("kanban", "Aging alerts", "Detection of stale or blocked work items", "yes", "Prevents items from languishing", "check_aging_alerts", 1.2),
        ("kanban", "Flow metrics", "Throughput and cycle time measurement", "yes", "Core kanban performance tracking", "check_kanban_flow_metrics", 1.2),
        ("kanban", "Explicit policies", "Documented definitions of done and decision rules", "yes", "Clarity even for solo developer", "check_explicit_policies", 1.0),
        ("kanban", "CFD implementation", "Cumulative Flow Diagram data tracking", "partial", "Useful but less critical for solo dev", "check_cfd_implementation", 0.8),
        ("kanban", "Blocker tracking", "Recording and resolving blocked work items", "yes", "Essential for flow management", "check_blocker_tracking", 1.0),
        # ── Operations Research ──
        ("operations_research", "Thompson Sampling", "Multi-armed bandit for experiment assignment", "yes", "Efficient exploration-exploitation balance", "check_thompson_sampling", 1.5),
        ("operations_research", "Knapsack optimization", "Resource allocation under budget constraints", "yes", "Advisor budget allocation", "check_knapsack_implementation", 1.0),
        ("operations_research", "Queuing theory", "Queue depth and saturation modeling", "yes", "Prevents work queue overload", "check_queuing_theory", 1.2),
        ("operations_research", "Queue stability alert", "Alerts when queue approaches instability", "yes", "Early warning for capacity issues", "check_queue_stability_alert", 1.0),
        ("operations_research", "Power analysis", "Sample size determination for experiments", "yes", "Ensures valid experimental conclusions", "check_power_analysis", 1.2),
        ("operations_research", "Batch sizing", "Adaptive session sizing based on context", "partial", "Applicable but limited scope for solo dev", "check_batch_sizing", 0.8),
        # ── Theory of Constraints ──
        ("theory_of_constraints", "Constraint identification", "Finding the system bottleneck dimension", "yes", "Core ToC principle", "check_constraint_identification", 1.5),
        ("theory_of_constraints", "Exploitation strategy", "Maximizing throughput at the constraint", "yes", "Focused improvement on bottleneck", "check_exploitation_strategy", 1.2),
        ("theory_of_constraints", "Subordination enforcer", "Subordinating non-constraints to the constraint", "yes", "Prevents local optimization", "check_subordination_enforcer", 1.0),
        ("theory_of_constraints", "Elevation strategy", "Investing to lift the constraint", "yes", "Long-term capacity improvement", "check_elevation_strategy", 1.0),
        ("theory_of_constraints", "Constraint history", "Tracking constraint shifts over time", "yes", "Ensures constraints are actually moving", "check_constraint_history", 1.0),
        # ── SPC ──
        ("spc", "Control charts", "Multiple chart types with sufficient data", "yes", "Foundation of SPC", "check_control_charts", 1.5),
        ("spc", "OOC detection", "Out-of-control signal detection and response", "yes", "Core SPC capability", "check_ooc_detection", 1.5),
        ("spc", "Cause distinction", "Separating common cause from special cause variation", "yes", "Essential for correct response", "check_cause_distinction", 1.2),
        ("spc", "SPC closure", "Resolving SPC-triggered findings", "yes", "Closing the loop on SPC signals", "check_spc_closure", 1.0),
        ("spc", "Western Electric rules", "Pattern detection on control charts", "yes", "Standard SPC pattern recognition", "check_western_electric", 1.0),
        # ── DoE ──
        ("doe", "A/B framework", "Experiment creation and assignment tracking", "yes", "Core experimentation capability", "check_ab_framework", 1.5),
        ("doe", "Power analysis", "Sample size computation before experiments", "yes", "Ensures valid experiments", "check_power_analysis_doe", 1.2),
        ("doe", "Significance testing", "Statistical conclusion of experiments", "yes", "Required for valid inference", "check_significance_testing", 1.2),
        ("doe", "Effect size", "Practical significance measurement", "yes", "Beyond just p-values", "check_effect_size", 1.0),
        ("doe", "Experiment health", "Guardrails and SRM checks", "yes", "Prevents invalid experiments", "check_experiment_health", 1.0),
        # ── Spiral (placeholder — not applicable to solo dev) ──
        ("spiral", "Risk-driven iterations", "Iterative development driven by risk analysis", "no", "Spiral model designed for large multi-team projects", None, 0.0),
        # ── Scrum (placeholder — not applicable to solo dev) ──
        ("scrum", "Sprint ceremonies", "Sprint planning, review, retrospective ceremonies", "no", "Scrum ceremonies require a team", None, 0.0),
    ]

    for fw, name, desc, applicable, rationale, detect_fn, weight in components:
        cid = str(_uuid.uuid4())
        conn.execute(
            """INSERT OR IGNORE INTO pi_framework_components
               (id, framework, component_name, component_description,
                solo_dev_applicable, applicability_rationale, detection_function, weight)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, fw, name, desc, applicable, rationale, detect_fn, weight),
        )


def _migrate_v63_to_v64(conn: sqlite3.Connection) -> None:
    """v63→v64: Local LLM (Ollama) — generation cache, log, review queue + vocab_encounter columns."""
    logger.info("Migration v63→v64: local LLM tables")
    tables = _table_set(conn)

    if "pi_ai_generation_cache" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_generation_cache (
                id TEXT PRIMARY KEY,
                prompt_hash TEXT NOT NULL UNIQUE,
                prompt_text TEXT NOT NULL,
                system_text TEXT,
                model_used TEXT NOT NULL,
                response_text TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                hit_count INTEGER NOT NULL DEFAULT 0,
                last_hit_at TEXT
            )
        """)

    if "pi_ai_generation_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_generation_log (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                task_type TEXT NOT NULL,
                model_used TEXT NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                generation_time_ms INTEGER,
                from_cache INTEGER NOT NULL,
                success INTEGER NOT NULL,
                error TEXT,
                finding_id TEXT,
                item_id TEXT
            )
        """)

    if "pi_ai_review_queue" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_review_queue (
                id TEXT PRIMARY KEY,
                queued_at TEXT NOT NULL DEFAULT (datetime('now')),
                content_type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                validation_issues TEXT,
                encounter_id TEXT,
                reviewed_at TEXT,
                reviewed_by TEXT DEFAULT 'human',
                review_decision TEXT CHECK (
                    review_decision IN ('approved', 'rejected', 'edited')
                ),
                edited_content_json TEXT,
                review_notes TEXT,
                provenance_checked INTEGER DEFAULT 0
            )
        """)

    # ALTER vocab_encounter — 4 new columns
    enc_cols = _col_set(conn, "vocab_encounter")
    if "drill_generation_status" not in enc_cols:
        conn.execute("ALTER TABLE vocab_encounter ADD COLUMN drill_generation_status TEXT DEFAULT 'pending'")
    if "generated_item_id" not in enc_cols:
        conn.execute("ALTER TABLE vocab_encounter ADD COLUMN generated_item_id TEXT")
    if "generation_attempted_at" not in enc_cols:
        conn.execute("ALTER TABLE vocab_encounter ADD COLUMN generation_attempted_at TEXT")
    if "generation_error" not in enc_cols:
        conn.execute("ALTER TABLE vocab_encounter ADD COLUMN generation_error TEXT")

    conn.commit()


def _migrate_v64_to_v65(conn: sqlite3.Connection) -> None:
    """v64→v65: Traditional ML — difficulty predictions, finding embeddings, model versions, pipeline runs."""
    logger.info("Migration v64→v65: traditional ML tables")
    tables = _table_set(conn)

    if "pi_difficulty_predictions" not in tables:
        conn.execute("""
            CREATE TABLE pi_difficulty_predictions (
                id TEXT PRIMARY KEY,
                review_event_id INTEGER,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                session_id INTEGER,
                predicted_accuracy REAL NOT NULL,
                difficulty_class TEXT NOT NULL,
                prediction_confidence REAL NOT NULL,
                model_available INTEGER NOT NULL DEFAULT 1,
                actual_correct INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (review_event_id) REFERENCES review_event(id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pi_dp_review ON pi_difficulty_predictions(review_event_id)"
        )

    if "pi_finding_embeddings" not in tables:
        conn.execute("""
            CREATE TABLE pi_finding_embeddings (
                finding_id INTEGER PRIMARY KEY REFERENCES pi_finding(id),
                title_at_embedding TEXT NOT NULL,
                embedding_bytes BLOB NOT NULL,
                embedded_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "pi_ml_model_versions" not in tables:
        conn.execute("""
            CREATE TABLE pi_ml_model_versions (
                id TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                trained_at TEXT NOT NULL DEFAULT (datetime('now')),
                model_path TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                val_accuracy REAL,
                baseline_accuracy REAL,
                improvement REAL,
                active INTEGER NOT NULL DEFAULT 1,
                retired_at TEXT
            )
        """)

    if "pi_ml_pipeline_runs" not in tables:
        conn.execute("""
            CREATE TABLE pi_ml_pipeline_runs (
                id TEXT PRIMARY KEY,
                run_at TEXT NOT NULL DEFAULT (datetime('now')),
                results_json TEXT NOT NULL
            )
        """)

    conn.commit()


def _migrate_v65_to_v66(conn: sqlite3.Connection) -> None:
    """v65→v66: AI Outcome Measurement — measurements, experiments, portfolio, review outcomes, dedup outcomes, latency, security."""
    logger.info("Migration v65→v66: AI outcome measurement tables")
    tables = _table_set(conn)

    if "pi_ai_outcome_measurements" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_outcome_measurements (
                id TEXT PRIMARY KEY,
                measured_at TEXT NOT NULL DEFAULT (datetime('now')),
                audit_cycle_id TEXT,
                component TEXT NOT NULL,
                dimension TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                metric_unit TEXT,
                threshold_low REAL,
                threshold_high REAL,
                status TEXT NOT NULL CHECK (
                    status IN ('healthy', 'degraded', 'critical', 'insufficient_data', 'not_applicable')
                ),
                evidence TEXT NOT NULL,
                sample_size INTEGER,
                confidence REAL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pi_aiom_component ON pi_ai_outcome_measurements(component, dimension)"
        )

    if "pi_ai_component_experiments" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_component_experiments (
                id TEXT PRIMARY KEY,
                component TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                deactivated_at TEXT,
                pre_activation_baseline_json TEXT,
                post_activation_snapshot_json TEXT,
                net_delta_json TEXT,
                verdict TEXT CHECK (
                    verdict IN ('net_positive', 'net_neutral', 'net_negative', 'insufficient_data')
                ),
                verdict_computed_at TEXT,
                notes TEXT
            )
        """)

    if "pi_ai_portfolio_assessments" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_portfolio_assessments (
                id TEXT PRIMARY KEY,
                assessed_at TEXT NOT NULL DEFAULT (datetime('now')),
                audit_cycle_id TEXT,
                net_verdict TEXT NOT NULL CHECK (
                    net_verdict IN ('net_positive', 'net_neutral', 'net_negative', 'mixed', 'insufficient_data')
                ),
                component_verdicts_json TEXT NOT NULL,
                dimension_scores_json TEXT NOT NULL,
                top_ai_win TEXT,
                top_ai_risk TEXT,
                maintenance_burden_estimate_hrs_week REAL,
                recommendation TEXT NOT NULL,
                prior_verdict TEXT,
                trend TEXT CHECK (trend IN ('improving', 'stable', 'declining'))
            )
        """)

    if "pi_ai_review_outcomes" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_review_outcomes (
                id TEXT PRIMARY KEY,
                review_queue_id TEXT NOT NULL,
                component TEXT NOT NULL,
                decision TEXT NOT NULL,
                rejection_reason TEXT,
                rejection_category TEXT CHECK (
                    rejection_category IN (
                        'accuracy_error', 'tone_error', 'formatting_error',
                        'difficulty_mismatch', 'awkward_chinese', 'distractor_quality',
                        'content_policy', 'other'
                    )
                ),
                latency_improvement INTEGER,
                reviewed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "pi_dedup_outcomes" not in tables:
        conn.execute("""
            CREATE TABLE pi_dedup_outcomes (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                finding_a_id TEXT NOT NULL,
                finding_b_id TEXT NOT NULL,
                similarity_score REAL NOT NULL,
                engine_decision TEXT NOT NULL CHECK (
                    engine_decision IN ('merged', 'distinct')
                ),
                human_override TEXT CHECK (
                    human_override IN ('was_wrong_merged', 'was_wrong_distinct', 'confirmed')
                ),
                override_at TEXT,
                override_reason TEXT
            )
        """)

    if "pi_ai_latency_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_latency_log (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                component TEXT NOT NULL,
                operation TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                succeeded INTEGER NOT NULL,
                used_fallback INTEGER NOT NULL DEFAULT 0,
                user_facing INTEGER NOT NULL DEFAULT 0,
                session_id TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pi_ai_lat_comp ON pi_ai_latency_log(component, occurred_at)"
        )

    if "pi_ai_security_events" not in tables:
        conn.execute("""
            CREATE TABLE pi_ai_security_events (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                component TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
                detail TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0,
                resolution_notes TEXT
            )
        """)

    # Add explanation_shown to review_event for error explanation tracking
    re_cols = _col_set(conn, "review_event")
    if "explanation_shown" not in re_cols:
        conn.execute("ALTER TABLE review_event ADD COLUMN explanation_shown INTEGER DEFAULT 0")

    # Add suspended flag to feature_flag if not present (for component suspension)
    # We'll use feature_flag table entries like 'ai_component_<name>' for suspension

    conn.commit()


def _migrate_v66_to_v67(conn: sqlite3.Connection) -> None:
    """v66→v67: Coverage Audit + Cross-Domain Constraint History."""
    logger.info("Migration v66→v67: coverage audit + constraint history tables")
    tables = _table_set(conn)

    if "pi_coverage_audit_log" not in tables:
        conn.execute("""
            CREATE TABLE pi_coverage_audit_log (
                id TEXT PRIMARY KEY,
                logged_at TEXT NOT NULL DEFAULT (datetime('now')),
                component TEXT NOT NULL,
                domain TEXT NOT NULL,
                coverage_status TEXT NOT NULL,
                covering_document TEXT,
                notes TEXT
            )
        """)

    if "pi_system_constraint_history" not in tables:
        conn.execute("""
            CREATE TABLE pi_system_constraint_history (
                id TEXT PRIMARY KEY,
                identified_at TEXT NOT NULL DEFAULT (datetime('now')),
                constraint_type TEXT NOT NULL,
                domain TEXT NOT NULL,
                severity TEXT NOT NULL,
                description TEXT NOT NULL,
                resolved_at TEXT,
                resolution TEXT
            )
        """)

    conn.commit()


def _migrate_v67_to_v68(conn: sqlite3.Connection) -> None:
    """v67→v68: Engagement snapshots, events, cohort snapshots, teacher interventions (Doc 7)."""
    logger.info("Migration v67→v68: engagement + cohort + intervention tables")
    tables = _table_set(conn)

    if "pi_engagement_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE pi_engagement_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                snapshot_date TEXT NOT NULL,
                sessions_7d INTEGER DEFAULT 0,
                sessions_14d INTEGER DEFAULT 0,
                avg_accuracy_7d REAL,
                avg_duration_7d REAL,
                early_exits_7d INTEGER DEFAULT 0,
                boredom_flags_7d INTEGER DEFAULT 0,
                avg_response_ms_7d REAL,
                items_reviewed_7d INTEGER DEFAULT 0,
                encounters_7d INTEGER DEFAULT 0,
                abandonment_risk REAL DEFAULT 0.0,
                risk_level TEXT DEFAULT 'low',
                risk_factors TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, snapshot_date)
            )
        """)
        conn.execute("CREATE INDEX idx_eng_snap_user ON pi_engagement_snapshots(user_id, snapshot_date)")

    if "pi_engagement_events" not in tables:
        conn.execute("""
            CREATE TABLE pi_engagement_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_eng_event_user ON pi_engagement_events(user_id, created_at)")

    if "pi_cohort_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE pi_cohort_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classroom_id INTEGER NOT NULL,
                snapshot_date TEXT NOT NULL,
                total_students INTEGER DEFAULT 0,
                active_students_7d INTEGER DEFAULT 0,
                avg_accuracy REAL,
                avg_sessions_per_student REAL,
                at_risk_count INTEGER DEFAULT 0,
                high_risk_count INTEGER DEFAULT 0,
                avg_abandonment_risk REAL,
                engagement_trend TEXT DEFAULT 'stable',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(classroom_id, snapshot_date)
            )
        """)
        conn.execute("CREATE INDEX idx_cohort_snap_class ON pi_cohort_snapshots(classroom_id, snapshot_date)")

    if "pi_teacher_interventions" not in tables:
        conn.execute("""
            CREATE TABLE pi_teacher_interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_user_id INTEGER NOT NULL,
                student_user_id INTEGER NOT NULL,
                classroom_id INTEGER,
                intervention_type TEXT NOT NULL,
                notes TEXT,
                risk_at_intervention REAL,
                risk_after_7d REAL,
                effective INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_intervention_student ON pi_teacher_interventions(student_user_id)")

    conn.commit()


def _migrate_v68_to_v69(conn: sqlite3.Connection) -> None:
    """v68→v69: Output drill responses, tutor sessions/corrections/flags, speaking practice (Doc 8)."""
    logger.info("Migration v68→v69: output production, tutor integration, speaking practice tables")
    tables = _table_set(conn)

    if "output_drill_responses" not in tables:
        conn.execute("""
            CREATE TABLE output_drill_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                session_id INTEGER,
                prompt_type TEXT NOT NULL,
                user_response TEXT NOT NULL,
                expected_response TEXT NOT NULL,
                is_correct INTEGER,
                similarity_score REAL,
                grading_method TEXT,
                feedback TEXT,
                response_time_ms INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_odr_user_created ON output_drill_responses(user_id, created_at)")

    if "tutor_sessions" not in tables:
        conn.execute("""
            CREATE TABLE tutor_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                tutor_name TEXT,
                platform TEXT,
                session_date TEXT NOT NULL,
                duration_minutes INTEGER,
                session_type TEXT,
                self_assessment INTEGER,
                topics_covered TEXT,
                tutor_notes TEXT,
                processed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_tutor_sess_user ON tutor_sessions(user_id, session_date)")

    if "tutor_corrections" not in tables:
        conn.execute("""
            CREATE TABLE tutor_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tutor_session_id INTEGER NOT NULL,
                correction_type TEXT NOT NULL DEFAULT 'grammar',
                wrong_form TEXT NOT NULL,
                correct_form TEXT NOT NULL,
                explanation TEXT,
                linked_content_item_id INTEGER,
                added_to_srs INTEGER DEFAULT 0,
                srs_priority_boost INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_tutor_corr_session ON tutor_corrections(tutor_session_id)")
        conn.execute("CREATE INDEX idx_tutor_corr_item ON tutor_corrections(linked_content_item_id)")

    if "tutor_vocabulary_flags" not in tables:
        conn.execute("""
            CREATE TABLE tutor_vocabulary_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tutor_session_id INTEGER NOT NULL,
                hanzi TEXT NOT NULL,
                pinyin TEXT,
                meaning TEXT,
                flag_reason TEXT DEFAULT 'tutor_introduced',
                linked_content_item_id INTEGER,
                added_to_srs INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_tutor_vocab_session ON tutor_vocabulary_flags(tutor_session_id)")
        conn.execute("CREATE INDEX idx_tutor_vocab_item ON tutor_vocabulary_flags(linked_content_item_id)")

    if "speaking_practice_sessions" not in tables:
        conn.execute("""
            CREATE TABLE speaking_practice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                session_id INTEGER,
                prompt_type TEXT NOT NULL,
                target_zh TEXT NOT NULL,
                expected_zh TEXT NOT NULL,
                whisper_transcription TEXT,
                tone_accuracy REAL,
                character_accuracy REAL,
                overall_score REAL,
                error_types TEXT,
                audio_duration_seconds REAL,
                whisper_confidence REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    # ALTER TABLE content_item — add tutor columns
    cols = {r[1] for r in conn.execute("PRAGMA table_info(content_item)").fetchall()}
    if "tutor_corrected" not in cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN tutor_corrected INTEGER NOT NULL DEFAULT 0")
    if "tutor_correction_count" not in cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN tutor_correction_count INTEGER NOT NULL DEFAULT 0")
    if "tutor_flagged" not in cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN tutor_flagged INTEGER NOT NULL DEFAULT 0")

    conn.commit()


def _migrate_v69_to_v70(conn: sqlite3.Connection) -> None:
    """v69→v70: Vibe audit, marketing intelligence, feature usage, engineering health (Doc 9)."""
    logger.info("Migration v69→v70: vibe/marketing/feature/engineering intelligence tables")
    tables = _table_set(conn)

    if "pi_copy_registry" not in tables:
        conn.execute("""
            CREATE TABLE pi_copy_registry (
                id TEXT PRIMARY KEY,
                string_key TEXT NOT NULL UNIQUE,
                copy_text TEXT NOT NULL,
                copy_context TEXT,
                surface TEXT NOT NULL DEFAULT 'product_ui',
                page_id TEXT,
                last_audited_at TEXT,
                voice_score REAL,
                clarity_score REAL,
                last_updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_pi_copy_surface ON pi_copy_registry(surface)")

    if "pi_marketing_pages" not in tables:
        conn.execute("""
            CREATE TABLE pi_marketing_pages (
                id TEXT PRIMARY KEY,
                page_slug TEXT NOT NULL UNIQUE,
                page_title TEXT NOT NULL,
                page_url TEXT,
                primary_audience TEXT,
                primary_cta TEXT,
                last_copy_review_at TEXT,
                copy_score REAL,
                conversion_rate REAL,
                monthly_visitors INTEGER,
                last_analytics_update TEXT,
                notes TEXT
            )
        """)

    if "pi_funnel_events" not in tables:
        conn.execute("""
            CREATE TABLE pi_funnel_events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                session_token TEXT,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                event_type TEXT NOT NULL,
                source TEXT,
                landing_page TEXT,
                device_type TEXT
            )
        """)
        conn.execute("CREATE INDEX idx_pi_funnel_user_event ON pi_funnel_events(user_id, event_type)")

    if "pi_funnel_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE pi_funnel_snapshots (
                id TEXT PRIMARY KEY,
                snapshot_date TEXT NOT NULL UNIQUE,
                signups_7d INTEGER,
                activations_7d INTEGER,
                d7_retention_rate REAL,
                d30_retention_rate REAL,
                teacher_signups_7d INTEGER,
                conversion_visitor_to_signup REAL,
                conversion_signup_to_activation REAL,
                avg_time_to_first_drill_minutes REAL,
                notes TEXT
            )
        """)

    if "pi_feature_registry" not in tables:
        conn.execute("""
            CREATE TABLE pi_feature_registry (
                id TEXT PRIMARY KEY,
                feature_name TEXT NOT NULL UNIQUE,
                feature_description TEXT NOT NULL,
                launched_at TEXT,
                expected_usage_frequency TEXT,
                minimum_usage_rate_30d REAL,
                current_usage_rate_30d REAL,
                status TEXT DEFAULT 'new',
                notes TEXT
            )
        """)

    if "pi_feature_events" not in tables:
        conn.execute("""
            CREATE TABLE pi_feature_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
                feature_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                session_id TEXT,
                metadata_json TEXT
            )
        """)
        conn.execute("CREATE INDEX idx_pi_feature_name_at ON pi_feature_events(feature_name, occurred_at)")

    if "pi_engineering_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE pi_engineering_snapshots (
                id TEXT PRIMARY KEY,
                snapshot_date TEXT NOT NULL UNIQUE,
                test_coverage_pct REAL,
                tests_passing INTEGER,
                tests_failing INTEGER,
                table_count INTEGER,
                db_size_mb REAL,
                outdated_dependencies INTEGER,
                notes TEXT
            )
        """)

    if "pi_vibe_audits" not in tables:
        conn.execute("""
            CREATE TABLE pi_vibe_audits (
                id TEXT PRIMARY KEY,
                audit_date TEXT NOT NULL,
                audit_type TEXT NOT NULL,
                audit_category TEXT NOT NULL,
                overall_pass INTEGER NOT NULL DEFAULT 1,
                findings_text TEXT,
                auditor TEXT DEFAULT 'self',
                notes TEXT
            )
        """)

    # Seed feature registry with core features
    existing = conn.execute("SELECT COUNT(*) FROM pi_feature_registry").fetchone()[0]
    if existing == 0:
        import uuid as _uuid
        _seed_features = [
            ("graded_reader", "Graded reading passages with vocab lookup", "daily", 0.10),
            ("extensive_listening", "Browser TTS extensive listening practice", "weekly", 0.05),
            ("media_shelf", "Video content shelf with HSK-tagged media", "weekly", 0.05),
            ("speaking_drill", "Tone-graded speaking practice drill", "daily", 0.10),
            ("context_notes", "Per-item context notes for SRS cards", "weekly", 0.05),
            ("dark_mode", "Dark mode UI toggle", "weekly", 0.10),
            ("export_data", "GDPR data export and download", "monthly", 0.01),
            ("streak_freeze", "Streak freeze earning and usage", "monthly", 0.02),
            ("tutor_corrections", "Manual tutor correction logging", "weekly", 0.03),
            ("classroom_mode", "Teacher classroom management", "daily", 0.05),
        ]
        for name, desc, freq, min_rate in _seed_features:
            conn.execute(
                """INSERT INTO pi_feature_registry
                   (id, feature_name, feature_description, expected_usage_frequency,
                    minimum_usage_rate_30d, status)
                   VALUES (?, ?, ?, ?, ?, 'active')""",
                (str(_uuid.uuid4()), name, desc, freq, min_rate),
            )

    conn.commit()


def _migrate_v70_to_v71(conn: sqlite3.Connection) -> None:
    """v70→v71: Strategic intelligence — competitors, theses, editorial, commercial readiness (Doc 10)."""
    logger.info("Migration v70→v71: strategic intelligence tables")
    tables = _table_set(conn)

    if "pi_competitors" not in tables:
        conn.execute("""
            CREATE TABLE pi_competitors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL CHECK (category IN (
                    'srs_focused', 'gamified_mass_market', 'audio_first',
                    'content_platform', 'human_instruction', 'authentic_content',
                    'enterprise_training'
                )),
                primary_url TEXT,
                pricing_model TEXT,
                price_point_usd_monthly REAL,
                target_user TEXT,
                strategic_position TEXT NOT NULL,
                primary_strength TEXT NOT NULL,
                primary_weakness TEXT NOT NULL,
                ceiling TEXT NOT NULL,
                aelu_overlap_degree TEXT CHECK (aelu_overlap_degree IN (
                    'direct', 'partial', 'indirect', 'none'
                )),
                last_assessed_at TEXT,
                notes TEXT
            )
        """)

    if "pi_competitor_dimensions" not in tables:
        conn.execute("""
            CREATE TABLE pi_competitor_dimensions (
                id TEXT PRIMARY KEY,
                competitor_id TEXT NOT NULL REFERENCES pi_competitors(id),
                dimension TEXT NOT NULL,
                score INTEGER CHECK (score BETWEEN 1 AND 10),
                evidence TEXT NOT NULL,
                assessed_at TEXT NOT NULL,
                UNIQUE(competitor_id, dimension)
            )
        """)

    if "pi_competitive_signals" not in tables:
        conn.execute("""
            CREATE TABLE pi_competitive_signals (
                id TEXT PRIMARY KEY,
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                competitor_id TEXT REFERENCES pi_competitors(id),
                signal_type TEXT NOT NULL CHECK (signal_type IN (
                    'new_feature', 'pricing_change', 'new_market_entry',
                    'partnership', 'funding', 'user_review_pattern',
                    'content_expansion', 'strategic_pivot'
                )),
                signal_description TEXT NOT NULL,
                strategic_implication TEXT,
                requires_aelu_response INTEGER DEFAULT 0,
                response_logged_at TEXT,
                response_description TEXT
            )
        """)

    if "pi_evaluation_dimensions" not in tables:
        conn.execute("""
            CREATE TABLE pi_evaluation_dimensions (
                id TEXT PRIMARY KEY,
                dimension_name TEXT NOT NULL UNIQUE,
                dimension_description TEXT NOT NULL,
                weight REAL NOT NULL,
                aelu_current_score INTEGER,
                aelu_target_score INTEGER,
                best_in_class_competitor TEXT,
                best_in_class_score INTEGER,
                gap INTEGER,
                gap_closeable INTEGER DEFAULT 1,
                closing_cost TEXT CHECK (closing_cost IN (
                    'low', 'medium', 'high', 'prohibitive'
                )),
                on_critical_path INTEGER DEFAULT 0,
                last_assessed_at TEXT
            )
        """)

    if "pi_strategic_theses" not in tables:
        conn.execute("""
            CREATE TABLE pi_strategic_theses (
                id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT NOT NULL CHECK (status IN (
                    'active', 'superseded', 'rejected'
                )),
                target_user TEXT NOT NULL,
                value_proposition TEXT NOT NULL,
                revenue_model TEXT NOT NULL CHECK (revenue_model IN (
                    'b2c_subscription', 'b2b2c_teachers', 'enterprise',
                    'hybrid_b2c_b2b2c', 'undetermined'
                )),
                price_point_rationale TEXT NOT NULL,
                primary_moat TEXT NOT NULL,
                key_assumptions TEXT NOT NULL,
                disconfirming_conditions TEXT NOT NULL,
                confirming_conditions TEXT NOT NULL,
                monetization_blockers TEXT,
                estimated_months_to_monetization INTEGER,
                confidence_score REAL,
                confidence_rationale TEXT,
                superseded_by TEXT REFERENCES pi_strategic_theses(id),
                revision_trigger TEXT,
                notes TEXT
            )
        """)

    if "pi_strategic_hypotheses" not in tables:
        conn.execute("""
            CREATE TABLE pi_strategic_hypotheses (
                id TEXT PRIMARY KEY,
                thesis_id TEXT NOT NULL REFERENCES pi_strategic_theses(id),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                hypothesis TEXT NOT NULL,
                hypothesis_type TEXT NOT NULL CHECK (hypothesis_type IN (
                    'market', 'product', 'commercial', 'competitive'
                )),
                test_design TEXT NOT NULL,
                test_metric TEXT NOT NULL,
                test_threshold TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'untested' CHECK (status IN (
                    'untested', 'confirmed', 'disconfirmed', 'inconclusive'
                )),
                evidence TEXT,
                resolved_at TEXT
            )
        """)

    if "pi_commercial_readiness" not in tables:
        conn.execute("""
            CREATE TABLE pi_commercial_readiness (
                id TEXT PRIMARY KEY,
                thesis_id TEXT NOT NULL REFERENCES pi_strategic_theses(id),
                revenue_model TEXT NOT NULL,
                condition_name TEXT NOT NULL,
                condition_description TEXT NOT NULL,
                condition_type TEXT CHECK (condition_type IN (
                    'product', 'content', 'ux', 'market', 'operational'
                )),
                current_status TEXT NOT NULL CHECK (current_status IN (
                    'met', 'partial', 'not_met', 'not_assessed'
                )),
                evidence TEXT,
                priority TEXT CHECK (priority IN ('blocking', 'important', 'nice_to_have')),
                last_assessed_at TEXT,
                UNIQUE(thesis_id, revenue_model, condition_name)
            )
        """)

    # Seed competitor knowledge base
    existing_competitors = conn.execute("SELECT COUNT(*) FROM pi_competitors").fetchone()[0]
    if existing_competitors == 0:
        import uuid as _uuid
        _competitor_seed = [
            {
                'name': 'Anki', 'category': 'srs_focused',
                'pricing_model': 'freemium', 'price_point_usd_monthly': 0,
                'target_user': 'self-directed learners willing to build or source decks',
                'strategic_position': 'The most powerful and flexible SRS in existence, with no opinions about content.',
                'primary_strength': 'Unmatched SRS algorithm depth and community deck ecosystem. Free on all platforms.',
                'primary_weakness': 'Zero pedagogical structure. No onboarding. UX is 2005-era. No analytics beyond basic counts.',
                'ceiling': 'Can never be a structured learning product without abandoning its identity.',
                'aelu_overlap_degree': 'direct',
            },
            {
                'name': 'Hack Chinese', 'category': 'srs_focused',
                'pricing_model': 'freemium', 'price_point_usd_monthly': 9,
                'target_user': 'serious Mandarin learners who want HSK-structured SRS',
                'strategic_position': 'The best purpose-built Mandarin SRS with curated HSK vocabulary.',
                'primary_strength': 'Clean UX, HSK-aligned 10,000+ words, good SRS, Mandarin-specific features. Proven PMF.',
                'primary_weakness': 'Vocabulary SRS only — no grammar, reading, listening, or output production. No AI.',
                'ceiling': 'Structurally limited to vocabulary acquisition. Cannot become a full learning system.',
                'aelu_overlap_degree': 'direct',
            },
            {
                'name': 'HelloChinese', 'category': 'gamified_mass_market',
                'pricing_model': 'freemium', 'price_point_usd_monthly': 10,
                'target_user': 'beginners wanting structured HSK 1-4 progression',
                'strategic_position': 'The best-designed entry-level Mandarin learning app.',
                'primary_strength': 'Exceptional onboarding, best-in-class first-session activation, clean HSK 1-4 curriculum.',
                'primary_weakness': 'Content thin above HSK 4. Gamification without acquisition at higher levels.',
                'ceiling': 'Cannot serve serious learners above HSK 4 without abandoning the gamification model.',
                'aelu_overlap_degree': 'partial',
            },
            {
                'name': 'Duolingo', 'category': 'gamified_mass_market',
                'pricing_model': 'freemium', 'price_point_usd_monthly': 7,
                'target_user': 'casual learners, beginners, streak maintainers',
                'strategic_position': 'The world\'s largest language learning platform by users.',
                'primary_strength': 'Brand dominance, massive content library, best-in-class gamification, free tier.',
                'primary_weakness': 'Mandarin is one of Duolingo\'s weakest courses. No serious learner uses it past HSK 2.',
                'ceiling': 'Optimized for DAU, not fluency. Structurally in tension at advanced levels.',
                'aelu_overlap_degree': 'indirect',
            },
            {
                'name': 'Pimsleur', 'category': 'audio_first',
                'pricing_model': 'subscription', 'price_point_usd_monthly': 20,
                'target_user': 'adult professionals wanting spoken Mandarin',
                'strategic_position': 'The gold standard for audio-based spoken language acquisition.',
                'primary_strength': 'Proven methodology, 60+ years of research. Speaking-first, no screen required.',
                'primary_weakness': 'No character instruction, reading, or writing. Expensive. No SRS. Content dated.',
                'ceiling': 'Cannot teach reading or writing without abandoning audio-first identity.',
                'aelu_overlap_degree': 'partial',
            },
            {
                'name': "Chairman's Bao", 'category': 'authentic_content',
                'pricing_model': 'subscription', 'price_point_usd_monthly': 12,
                'target_user': 'intermediate-to-advanced learners wanting authentic reading content',
                'strategic_position': 'The best graded authentic Chinese reading content platform.',
                'primary_strength': 'Real Chinese news at HSK 1-6. Genuinely interesting. Strong reputation.',
                'primary_weakness': 'No SRS integration. No grammar, speaking, or listening. Passive consumption only.',
                'ceiling': 'Content platform, not a learning system. Can never close the loop to acquisition.',
                'aelu_overlap_degree': 'direct',
            },
            {
                'name': 'Mandarin Corner', 'category': 'content_platform',
                'pricing_model': 'freemium', 'price_point_usd_monthly': 15,
                'target_user': 'intermediate learners wanting authentic video content with transcripts',
                'strategic_position': 'The best video content platform for intermediate Mandarin learners.',
                'primary_strength': 'High-quality authentic video with full transcripts. Culturally grounded.',
                'primary_weakness': 'No SRS, no structured curriculum, no output production. Content-only.',
                'ceiling': 'YouTube-native. Cannot become a structured learning system.',
                'aelu_overlap_degree': 'partial',
            },
            {
                'name': 'italki', 'category': 'human_instruction',
                'pricing_model': 'marketplace', 'price_point_usd_monthly': 60,
                'target_user': 'learners wanting human tutors at any level',
                'strategic_position': 'The dominant marketplace for language tutors.',
                'primary_strength': 'Human instruction is irreplaceable. Massive tutor supply. Flexible.',
                'primary_weakness': 'Quality variance enormous. No curriculum. Expensive at professional rates.',
                'ceiling': 'Marketplace, not a product. Cannot standardize quality.',
                'aelu_overlap_degree': 'indirect',
            },
        ]
        for c in _competitor_seed:
            conn.execute("""
                INSERT INTO pi_competitors
                (id, name, category, pricing_model, price_point_usd_monthly,
                 target_user, strategic_position, primary_strength, primary_weakness,
                 ceiling, aelu_overlap_degree, last_assessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
            """, (str(_uuid.uuid4()), c['name'], c['category'], c['pricing_model'],
                  c['price_point_usd_monthly'], c['target_user'], c['strategic_position'],
                  c['primary_strength'], c['primary_weakness'], c['ceiling'],
                  c['aelu_overlap_degree']))

    # Seed evaluation dimensions
    existing_dims = conn.execute("SELECT COUNT(*) FROM pi_evaluation_dimensions").fetchone()[0]
    if existing_dims == 0:
        import uuid as _uuid
        _dim_seed = [
            ('srs_sophistication', 'Quality of spaced repetition algorithm and scheduling', 3.0,
             9, 9, 'Anki', 8, -1, 1, 'low', 0),
            ('vocabulary_corpus_depth', 'Breadth and quality of vocabulary items across HSK levels', 3.0,
             4, 8, 'Hack Chinese', 8, 4, 1, 'high', 1),
            ('first_session_activation', 'Quality of onboarding and time-to-first-success', 2.5,
             4, 8, 'HelloChinese', 9, 5, 1, 'medium', 1),
            ('content_interest', 'Whether content is genuinely interesting to adult learners', 2.5,
             5, 9, "Chairman's Bao", 8, 3, 1, 'medium', 1),
            ('grammar_instruction_quality', 'Depth and clarity of grammar explanations', 2.0,
             5, 8, 'None — market gap', 6, 1, 1, 'medium', 0),
            ('speaking_output', 'Speaking practice with feedback and pronunciation assessment', 2.5,
             1, 7, 'Pimsleur', 8, 7, 1, 'high', 0),
            ('cultural_depth', 'Whether content connects language to Chinese culture and context', 2.0,
             7, 9, 'Mandarin Corner', 8, 1, 1, 'low', 0),
            ('intelligence_and_adaptivity', 'How well the system adapts to each individual learner', 3.0,
             8, 9, 'None — Aelu leads', 4, -4, 1, 'low', 0),
            ('classroom_and_teacher_tools', 'Teacher dashboard, classroom management, progress visibility', 2.0,
             6, 9, 'None — no competitor has this', 3, -3, 1, 'medium', 1),
            ('ux_polish', 'Visual design quality, interaction smoothness, perceived professionalism', 2.0,
             5, 8, 'HelloChinese', 9, 4, 1, 'medium', 1),
            ('pricing_and_value_clarity', 'Whether pricing is clear, justified, and positioned', 1.5,
             1, 8, "Chairman's Bao", 7, 7, 1, 'low', 1),
            ('advanced_learner_ceiling', 'Whether the product can take a learner to HSK 7-9', 2.5,
             6, 9, 'None — no product does this', 3, -3, 1, 'high', 0),
        ]
        for (name, desc, weight, cur, target, bic, bic_score, gap,
             closeable, cost, critical) in _dim_seed:
            conn.execute("""
                INSERT INTO pi_evaluation_dimensions
                (id, dimension_name, dimension_description, weight,
                 aelu_current_score, aelu_target_score, best_in_class_competitor,
                 best_in_class_score, gap, gap_closeable, closing_cost,
                 on_critical_path, last_assessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
            """, (str(_uuid.uuid4()), name, desc, weight, cur, target,
                  bic, bic_score, gap, closeable, cost, critical))

    conn.commit()


def _migrate_v71_to_v72(conn: sqlite3.Connection) -> None:
    """v71→v72: AI governance — component registry, validation, incidents, consent, FERPA (Doc 11)."""
    logger.info("Migration v71→v72: AI governance and compliance tables")
    tables = _table_set(conn)

    if "ai_component_registry" not in tables:
        conn.execute("""
            CREATE TABLE ai_component_registry (
                id TEXT PRIMARY KEY,
                component_name TEXT NOT NULL UNIQUE,
                component_description TEXT NOT NULL,
                ai_type TEXT NOT NULL CHECK (ai_type IN (
                    'ml_model', 'generative_ai', 'rule_based', 'hybrid'
                )),
                decision_type TEXT NOT NULL CHECK (decision_type IN (
                    'scheduling', 'generation', 'assessment',
                    'recommendation', 'classification'
                )),
                risk_tier TEXT NOT NULL CHECK (risk_tier IN (
                    'tier_1_high', 'tier_2_medium', 'tier_3_low'
                )),
                risk_tier_rationale TEXT NOT NULL,
                failure_mode TEXT NOT NULL,
                failure_impact TEXT NOT NULL,
                failure_detectability TEXT CHECK (failure_detectability IN (
                    'immediate', 'delayed', 'latent'
                )),
                human_override_available INTEGER NOT NULL DEFAULT 1,
                human_override_mechanism TEXT,
                monitoring_function TEXT,
                known_limitations TEXT NOT NULL,
                performance_benchmarks TEXT,
                component_owner TEXT NOT NULL DEFAULT 'jason_yee',
                last_validated_at TEXT,
                next_validation_due TEXT,
                registered_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "ai_validation_log" not in tables:
        conn.execute("""
            CREATE TABLE ai_validation_log (
                id TEXT PRIMARY KEY,
                component_name TEXT NOT NULL,
                validated_at TEXT NOT NULL DEFAULT (datetime('now')),
                verdict TEXT NOT NULL CHECK (verdict IN (
                    'validated', 'needs_review', 'validation_failed'
                )),
                prediction_accuracy_90d REAL,
                monitoring_status TEXT,
                conceptual_soundness TEXT CHECK (conceptual_soundness IN (
                    'sound', 'needs_review'
                )),
                limitations_acknowledged INTEGER NOT NULL DEFAULT 0,
                override_available INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            )
        """)

    if "ai_incident_log" not in tables:
        conn.execute("""
            CREATE TABLE ai_incident_log (
                id TEXT PRIMARY KEY,
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                severity TEXT NOT NULL CHECK (severity IN ('P0','P1','P2','P3')),
                incident_type TEXT NOT NULL CHECK (incident_type IN (
                    'content_bypass', 'data_breach', 'model_failure',
                    'data_quality', 'access_violation', 'other'
                )),
                affected_component TEXT,
                affected_user_ids TEXT,
                description TEXT NOT NULL,
                immediate_actions_taken TEXT,
                root_cause TEXT,
                resolution TEXT,
                resolved_at TEXT,
                user_notification_sent INTEGER NOT NULL DEFAULT 0,
                post_incident_review_notes TEXT
            )
        """)

    if "user_consent_records" not in tables:
        conn.execute("""
            CREATE TABLE user_consent_records (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                consent_type TEXT NOT NULL CHECK (consent_type IN (
                    'terms_of_service', 'privacy_policy', 'ai_content_generation',
                    'teacher_data_access', 'research_participation'
                )),
                consented INTEGER NOT NULL,
                consent_version TEXT NOT NULL,
                consented_at TEXT NOT NULL DEFAULT (datetime('now')),
                withdrawn_at TEXT,
                UNIQUE(user_id, consent_type)
            )
        """)

    if "data_subject_requests" not in tables:
        conn.execute("""
            CREATE TABLE data_subject_requests (
                id TEXT PRIMARY KEY,
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                user_id TEXT NOT NULL,
                request_type TEXT NOT NULL CHECK (request_type IN (
                    'access', 'deletion', 'correction', 'portability', 'restriction'
                )),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                    'pending', 'in_progress', 'completed', 'denied'
                )),
                response_due_date TEXT NOT NULL DEFAULT (date('now', '+30 days')),
                completed_at TEXT,
                notes TEXT
            )
        """)

    if "user_age_classification" not in tables:
        conn.execute("""
            CREATE TABLE user_age_classification (
                user_id TEXT PRIMARY KEY,
                is_minor INTEGER NOT NULL DEFAULT 0,
                is_coppa_subject INTEGER NOT NULL DEFAULT 0,
                parental_consent_obtained INTEGER NOT NULL DEFAULT 0,
                parental_consent_at TEXT,
                data_collection_restricted INTEGER NOT NULL DEFAULT 0
            )
        """)

    if "ferpa_access_audit" not in tables:
        conn.execute("""
            CREATE TABLE ferpa_access_audit (
                id TEXT PRIMARY KEY,
                accessed_at TEXT NOT NULL DEFAULT (datetime('now')),
                requesting_user_id TEXT NOT NULL,
                target_user_id TEXT NOT NULL,
                data_table TEXT NOT NULL,
                access_permitted INTEGER NOT NULL,
                access_basis TEXT NOT NULL CHECK (access_basis IN (
                    'self_access', 'legitimate_educational_interest', 'denied_no_basis'
                )),
                request_context TEXT
            )
        """)

    if "ai_policy_documents" not in tables:
        conn.execute("""
            CREATE TABLE ai_policy_documents (
                id TEXT PRIMARY KEY,
                document_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                content TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
                    'draft', 'active', 'superseded'
                )),
                user_facing INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at TEXT,
                next_review_due TEXT,
                owner TEXT NOT NULL DEFAULT 'jason_yee'
            )
        """)

    conn.commit()


def _migrate_v72_to_v73(conn: sqlite3.Connection) -> None:
    """v72→v73: GenAI layer tables, usage_map column, json_parse_failure, T6 rename (Doc 12)."""
    logger.info("Migration v72→v73: GenAI layer + A+ quick wins")
    tables = _table_set(conn)
    ci_cols = _col_set(conn, "content_item")

    # 1. usage_map column on content_item
    if "usage_map" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN usage_map TEXT")

    # 2. genai_prompt_registry — prompt versioning
    if "genai_prompt_registry" not in tables:
        conn.execute("""
            CREATE TABLE genai_prompt_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_key TEXT NOT NULL UNIQUE,
                prompt_text TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'general',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    # 3. genai_session_analysis — session intelligence results
    if "genai_session_analysis" not in tables:
        conn.execute("""
            CREATE TABLE genai_session_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 1,
                analysis_type TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    # 4. genai_item_embeddings — multilingual embeddings for content items
    if "genai_item_embeddings" not in tables:
        conn.execute("""
            CREATE TABLE genai_item_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER NOT NULL UNIQUE,
                embedding BLOB NOT NULL,
                model_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            )
        """)

    # 5. G6: json_parse_failure column on pi_ai_generation_log
    if "pi_ai_generation_log" in tables:
        log_cols = _col_set(conn, "pi_ai_generation_log")
        if "json_parse_failure" not in log_cols:
            conn.execute(
                "ALTER TABLE pi_ai_generation_log ADD COLUMN json_parse_failure INTEGER DEFAULT 0"
            )

    # 6. T6: rename abandonment_risk_model → abandonment_risk_heuristic
    if "ai_component_registry" in tables:
        conn.execute("""
            UPDATE ai_component_registry
            SET component_name = 'abandonment_risk_heuristic'
            WHERE component_name = 'abandonment_risk_model'
        """)

    conn.commit()


def _migrate_v73_to_v74(conn: sqlite3.Connection) -> None:
    """v73→v74: Memory science tables — FSRS memory model, interference, load tracking (Doc 13)."""
    logger.info("Migration v73→v74: Memory science + FSRS scheduler")
    tables = _table_set(conn)

    # 1. memory_states — FSRS-compatible memory state per user per item
    if "memory_states" not in tables:
        conn.execute("""
            CREATE TABLE memory_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                stability REAL NOT NULL DEFAULT 1.0,
                retrievability REAL NOT NULL DEFAULT 0.0,
                difficulty REAL NOT NULL DEFAULT 0.5,
                state TEXT NOT NULL DEFAULT 'new'
                    CHECK (state IN ('new', 'learning', 'review', 'relearning')),
                last_reviewed_at TEXT,
                next_review_due TEXT NOT NULL DEFAULT (datetime('now')),
                scheduled_days INTEGER NOT NULL DEFAULT 1,
                reps INTEGER NOT NULL DEFAULT 0,
                lapses INTEGER NOT NULL DEFAULT 0,
                encoding_quality TEXT DEFAULT 'unknown'
                    CHECK (encoding_quality IN ('strong', 'weak', 'interference', 'unknown')),
                UNIQUE(user_id, content_item_id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_states_due ON memory_states(user_id, next_review_due)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_states_item ON memory_states(content_item_id)")

    # 2. interference_pairs — items with documented interference risk
    if "interference_pairs" not in tables:
        conn.execute("""
            CREATE TABLE interference_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id_a INTEGER NOT NULL,
                item_id_b INTEGER NOT NULL,
                interference_type TEXT NOT NULL
                    CHECK (interference_type IN (
                        'near_synonym', 'near_homophone', 'visual_similarity',
                        'antonym', 'semantic_field'
                    )),
                interference_strength TEXT NOT NULL
                    CHECK (interference_strength IN ('high', 'medium', 'low')),
                detected_by TEXT NOT NULL
                    CHECK (detected_by IN (
                        'embedding_similarity', 'qwen_analysis',
                        'human_flagged', 'error_pattern'
                    )),
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(item_id_a, item_id_b),
                FOREIGN KEY (item_id_a) REFERENCES content_item(id),
                FOREIGN KEY (item_id_b) REFERENCES content_item(id)
            )
        """)

    # 3. session_load_log — cognitive load tracking per session
    if "session_load_log" not in tables:
        conn.execute("""
            CREATE TABLE session_load_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 1,
                new_items_introduced INTEGER NOT NULL DEFAULT 0,
                active_learning_count INTEGER NOT NULL DEFAULT 0,
                total_reviews INTEGER NOT NULL DEFAULT 0,
                load_exceeded INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES session_log(id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    # 4. learner_dd_config — desirable difficulty config per learner
    if "learner_dd_config" not in tables:
        conn.execute("""
            CREATE TABLE learner_dd_config (
                user_id INTEGER PRIMARY KEY,
                cued_recall_ratio REAL NOT NULL DEFAULT 0.40,
                context_variation_enabled INTEGER NOT NULL DEFAULT 1,
                interleaving_strength TEXT NOT NULL DEFAULT 'moderate'
                    CHECK (interleaving_strength IN ('light', 'moderate', 'strong')),
                new_item_ceiling INTEGER NOT NULL DEFAULT 5,
                spacing_communication INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    # 5. learner_fsrs_params — calibrated FSRS parameters per learner
    if "learner_fsrs_params" not in tables:
        conn.execute("""
            CREATE TABLE learner_fsrs_params (
                user_id INTEGER PRIMARY KEY,
                w TEXT NOT NULL,
                calibrated_at TEXT NOT NULL DEFAULT (datetime('now')),
                review_count_at_calibration INTEGER NOT NULL,
                rmse REAL,
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    conn.commit()


def _migrate_v74_to_v75(conn: sqlite3.Connection) -> None:
    """v74→v75: Learner model tables — pattern states, proficiency zones, snapshots (Doc 16)."""
    logger.info("Migration v74→v75: Learner model + personalization engine")
    tables = _table_set(conn)

    # 1. learner_pattern_states — per-learner per-grammar-point mastery state
    if "learner_pattern_states" not in tables:
        conn.execute("""
            CREATE TABLE learner_pattern_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                grammar_point_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'untouched'
                    CHECK (status IN (
                        'untouched', 'introduced', 'acquiring',
                        'consolidating', 'mastered'
                    )),
                encounters INTEGER NOT NULL DEFAULT 0,
                correct_streak INTEGER NOT NULL DEFAULT 0,
                error_count_30d INTEGER NOT NULL DEFAULT 0,
                avg_stability REAL,
                first_encountered_at TEXT,
                last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, grammar_point_id),
                FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lps_user ON learner_pattern_states(user_id, status)"
        )

    # 2. learner_proficiency_zones — proficiency zone estimates per skill domain
    if "learner_proficiency_zones" not in tables:
        conn.execute("""
            CREATE TABLE learner_proficiency_zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                vocab_hsk_estimate REAL,
                vocab_items_mastered INTEGER,
                vocab_coverage_pct REAL,
                grammar_hsk_estimate REAL,
                grammar_patterns_mastered INTEGER,
                grammar_coverage_pct REAL,
                reading_hsk_estimate REAL,
                reading_confidence TEXT DEFAULT 'insufficient_data'
                    CHECK (reading_confidence IN (
                        'high', 'medium', 'low', 'insufficient_data'
                    )),
                listening_hsk_estimate REAL,
                listening_confidence TEXT DEFAULT 'insufficient_data',
                production_hsk_estimate REAL,
                production_confidence TEXT DEFAULT 'insufficient_data',
                composite_hsk_estimate REAL,
                computed_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    # 3. learner_model_snapshots — cached learner model context for Qwen prompts
    if "learner_model_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE learner_model_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                snapshot TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lms_user ON learner_model_snapshots(user_id, generated_at)"
        )

    conn.commit()


def _migrate_v75_to_v76(conn: sqlite3.Connection) -> None:
    """v75→v76: RAG layer, G6 failure logging, prompt regression (Doc 21)."""
    logger.info("Migration v75→v76: RAG layer + GenAI hardening (G1, G3, G6)")
    tables = _table_set(conn)

    # 1. rag_knowledge_base — one entry per vocabulary item
    if "rag_knowledge_base" not in tables:
        conn.execute("""
            CREATE TABLE rag_knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hanzi TEXT NOT NULL UNIQUE,
                pinyin TEXT NOT NULL,
                cc_cedict_definitions TEXT NOT NULL,
                part_of_speech TEXT,
                usage_notes TEXT,
                traditional_form TEXT,
                hsk_level INTEGER,
                frequency_rank INTEGER,
                example_sentences TEXT,
                common_collocations TEXT,
                learner_errors TEXT,
                near_synonyms TEXT,
                drift_risk TEXT DEFAULT 'low'
                    CHECK (drift_risk IN ('high', 'medium', 'low')),
                cc_cedict_version TEXT,
                last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                manually_reviewed INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_kb_hanzi ON rag_knowledge_base(hanzi)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_kb_hsk ON rag_knowledge_base(hsk_level)")

    # 2. rag_retrieval_log — track retrieval hits/misses
    if "rag_retrieval_log" not in tables:
        conn.execute("""
            CREATE TABLE rag_retrieval_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queried_at TEXT NOT NULL DEFAULT (datetime('now')),
                hanzi TEXT NOT NULL,
                retrieved INTEGER NOT NULL DEFAULT 1,
                num_examples_retrieved INTEGER NOT NULL DEFAULT 0,
                generation_prompt_key TEXT,
                generation_succeeded INTEGER,
                quality_signal REAL
            )
        """)

    # 3. json_generation_failures — G6 failure logging
    if "json_generation_failures" not in tables:
        conn.execute("""
            CREATE TABLE json_generation_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                failed_at TEXT NOT NULL DEFAULT (datetime('now')),
                prompt_key TEXT NOT NULL,
                failure_type TEXT NOT NULL
                    CHECK (failure_type IN (
                        'invalid_json', 'empty_response', 'exception',
                        'timeout', 'schema_mismatch'
                    )),
                prompt_length INTEGER,
                response_length INTEGER,
                response_sample TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jgf_key ON json_generation_failures(prompt_key)")

    # 4. drift_risk_flags — flag high-risk generation requests
    if "drift_risk_flags" not in tables:
        conn.execute("""
            CREATE TABLE drift_risk_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
                hanzi_list TEXT NOT NULL,
                prompt_key TEXT NOT NULL,
                reviewed INTEGER NOT NULL DEFAULT 0
            )
        """)

    # 5. prompt_regression_log — regression suite results
    if "prompt_regression_log" not in tables:
        conn.execute("""
            CREATE TABLE prompt_regression_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL DEFAULT (datetime('now')),
                passed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                findings_json TEXT
            )
        """)

    conn.commit()


def _migrate_v76_to_v77(conn: sqlite3.Connection) -> None:
    """v76→v77: Native speaker validation queue, validators, sessions (Doc 22)."""
    logger.info("Migration v76→v77: Native speaker validation protocol")
    tables = _table_set(conn)
    ci_cols = _col_set(conn, "content_item")

    # 1. native_speaker_validation_queue
    if "native_speaker_validation_queue" not in tables:
        conn.execute("""
            CREATE TABLE native_speaker_validation_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queued_at TEXT NOT NULL DEFAULT (datetime('now')),
                content_item_id INTEGER,
                content_hanzi TEXT NOT NULL,
                content_type TEXT NOT NULL
                    CHECK (content_type IN (
                        'drill_sentence', 'example_sentence', 'passage',
                        'dialogue', 'rag_example', 'error_explanation'
                    )),
                queue_reason TEXT NOT NULL
                    CHECK (queue_reason IN (
                        'drift_risk_flagged', 'hsk_high_level', 'register_mismatch',
                        'systematic_review', 'human_flagged', 'new_content_type'
                    )),
                hsk_level INTEGER,
                content_lens TEXT,
                target_vocabulary TEXT,
                intended_register TEXT,
                validated_at TEXT,
                validated_by TEXT,
                naturalness_score INTEGER CHECK (naturalness_score BETWEEN 1 AND 5),
                register_correct INTEGER,
                usage_current INTEGER,
                verdict TEXT
                    CHECK (verdict IN (
                        'approved', 'approved_with_note', 'needs_revision', 'reject'
                    )),
                validator_note TEXT,
                revised_content TEXT,
                action_taken TEXT DEFAULT 'pending'
                    CHECK (action_taken IN (
                        'approved_to_srs', 'revised_and_approved', 'rejected',
                        'queued_for_revision', 'pending'
                    )),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nsv_pending ON "
            "native_speaker_validation_queue(validated_at, queue_reason)"
        )

    # 2. native_speaker_validators
    if "native_speaker_validators" not in tables:
        conn.execute("""
            CREATE TABLE native_speaker_validators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT,
                native_dialect TEXT DEFAULT 'mandarin_standard',
                active INTEGER NOT NULL DEFAULT 1,
                sessions_completed INTEGER NOT NULL DEFAULT 0,
                avg_items_per_session REAL,
                first_session_at TEXT,
                last_session_at TEXT
            )
        """)

    # 3. validation_sessions
    if "validation_sessions" not in tables:
        conn.execute("""
            CREATE TABLE validation_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                validator_id INTEGER,
                tutor_session_id INTEGER,
                items_reviewed INTEGER NOT NULL DEFAULT 0,
                items_approved INTEGER NOT NULL DEFAULT 0,
                items_rejected INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY (validator_id) REFERENCES native_speaker_validators(id)
            )
        """)

    # 4. Add validation columns to content_item
    if "native_speaker_validated" not in ci_cols:
        conn.execute(
            "ALTER TABLE content_item ADD COLUMN native_speaker_validated INTEGER DEFAULT 0"
        )
    if "native_speaker_note" not in ci_cols:
        conn.execute(
            "ALTER TABLE content_item ADD COLUMN native_speaker_note TEXT"
        )
    if "suspended_for_revision" not in ci_cols:
        conn.execute(
            "ALTER TABLE content_item ADD COLUMN suspended_for_revision INTEGER DEFAULT 0"
        )
    if "rejected_native_speaker" not in ci_cols:
        conn.execute(
            "ALTER TABLE content_item ADD COLUMN rejected_native_speaker INTEGER DEFAULT 0"
        )

    conn.commit()


def _migrate_v77_to_v78(conn: sqlite3.Connection) -> None:
    """v77→v78: Curriculum architecture — add prerequisite_patterns to grammar_point (Doc 14)."""
    logger.info("Migration v77→v78: Curriculum architecture (Doc 14)")
    gp_cols = _col_set(conn, "grammar_point")
    if "prerequisite_patterns" not in gp_cols:
        conn.execute(
            "ALTER TABLE grammar_point ADD COLUMN prerequisite_patterns TEXT"
        )
    conn.commit()


def _migrate_v78_to_v79(conn: sqlite3.Connection) -> None:
    """v78→v79: Input acquisition layer — reading texts, events, listening, SRS queue (Doc 15)."""
    logger.info("Migration v78→v79: Input acquisition layer (Doc 15)")
    tables = _table_set(conn)

    if "reading_texts" not in tables:
        conn.execute("""
            CREATE TABLE reading_texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content_hanzi TEXT NOT NULL,
                content_pinyin TEXT,
                word_count INTEGER NOT NULL DEFAULT 0,
                hsk_ceiling INTEGER NOT NULL DEFAULT 1,
                above_ceiling_words TEXT,
                content_lens TEXT,
                source TEXT NOT NULL DEFAULT 'generated',
                approved INTEGER NOT NULL DEFAULT 0,
                approved_at TEXT,
                difficulty_score REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "reading_events" not in tables:
        conn.execute("""
            CREATE TABLE reading_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                text_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                completion_pct REAL NOT NULL DEFAULT 0.0,
                lookups TEXT,
                comprehension_score REAL,
                time_on_text_seconds INTEGER,
                FOREIGN KEY (text_id) REFERENCES reading_texts(id)
            )
        """)

    if "listening_texts" not in tables:
        conn.execute("""
            CREATE TABLE listening_texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                transcript_hanzi TEXT NOT NULL,
                audio_path TEXT,
                duration_seconds INTEGER,
                hsk_ceiling INTEGER NOT NULL DEFAULT 1,
                speech_rate TEXT DEFAULT 'normal',
                accent TEXT DEFAULT 'standard_beijing',
                source TEXT NOT NULL DEFAULT 'generated',
                approved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "listening_events" not in tables:
        conn.execute("""
            CREATE TABLE listening_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                text_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                completion_pct REAL NOT NULL DEFAULT 0.0,
                comprehension_score REAL,
                FOREIGN KEY (text_id) REFERENCES listening_texts(id)
            )
        """)

    if "pending_srs_additions" not in tables:
        conn.execute("""
            CREATE TABLE pending_srs_additions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                encounter_source TEXT NOT NULL DEFAULT 'reading_lookup',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, content_item_id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            )
        """)

    conn.commit()


def _migrate_v79_to_v80(conn: sqlite3.Connection) -> None:
    """v79→v80: Onboarding, placement, and activation (Doc 17)."""
    logger.info("Migration v79→v80: Onboarding + placement (Doc 17)")
    tables = _table_set(conn)

    if "onboarding_sessions" not in tables:
        conn.execute("""
            CREATE TABLE onboarding_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                self_reported_level TEXT,
                prior_study_years REAL,
                study_context TEXT,
                primary_goal TEXT,
                placement_hsk_estimate REAL,
                placement_confidence TEXT,
                activation_completed INTEGER NOT NULL DEFAULT 0,
                activation_session_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    if "placement_probe_responses" not in tables:
        conn.execute("""
            CREATE TABLE placement_probe_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                onboarding_id INTEGER NOT NULL,
                content_item_id INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                response_ms INTEGER,
                hsk_level_of_item INTEGER,
                responded_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (onboarding_id) REFERENCES onboarding_sessions(id),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            )
        """)

    conn.commit()


def _migrate_v80_to_v81(conn: sqlite3.Connection) -> None:
    """v80→v81: Social, accountability, and habit architecture (Doc 18)."""
    logger.info("Migration v80→v81: Accountability + study partners (Doc 18)")
    tables = _table_set(conn)

    if "study_commitments" not in tables:
        conn.execute("""
            CREATE TABLE study_commitments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                week_start TEXT NOT NULL,
                target_sessions INTEGER NOT NULL DEFAULT 4,
                target_new_items INTEGER NOT NULL DEFAULT 10,
                completed_sessions INTEGER NOT NULL DEFAULT 0,
                completed_new_items INTEGER NOT NULL DEFAULT 0,
                commitment_met INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, week_start),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    if "study_partners" not in tables:
        conn.execute("""
            CREATE TABLE study_partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id_a INTEGER NOT NULL,
                user_id_b INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                paired_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id_a, user_id_b),
                FOREIGN KEY (user_id_a) REFERENCES user(id),
                FOREIGN KEY (user_id_b) REFERENCES user(id)
            )
        """)

    if "partner_check_ins" not in tables:
        conn.execute("""
            CREATE TABLE partner_check_ins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partnership_id INTEGER NOT NULL,
                checking_in_user_id INTEGER NOT NULL,
                week_start TEXT NOT NULL,
                sessions_this_week INTEGER NOT NULL DEFAULT 0,
                commitment_met INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                checked_in_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (partnership_id) REFERENCES study_partners(id)
            )
        """)

    conn.commit()


def _migrate_v81_to_v82(conn: sqlite3.Connection) -> None:
    """v81→v82: Commercial intelligence — cohorts, readiness tracking (Doc 19)."""
    logger.info("Migration v81→v82: Commercial intelligence (Doc 19)")
    tables = _table_set(conn)

    if "cohorts" not in tables:
        conn.execute("""
            CREATE TABLE cohorts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                teacher_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (teacher_id) REFERENCES user(id)
            )
        """)

    if "cohort_members" not in tables:
        conn.execute("""
            CREATE TABLE cohort_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cohort_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(cohort_id, user_id),
                FOREIGN KEY (cohort_id) REFERENCES cohorts(id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

    if "pi_commercial_readiness" not in tables:
        conn.execute("""
            CREATE TABLE pi_commercial_readiness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                condition_name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'confirmed', 'blocked')),
                confirmed_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    conn.commit()


def _migrate_v82_to_v83(conn: sqlite3.Connection) -> None:
    """v82→v83: Personal HSK 9 study system — milestones (Doc 20)."""
    logger.info("Migration v82→v83: Personal study system (Doc 20)")
    tables = _table_set(conn)

    if "personal_milestones" not in tables:
        conn.execute("""
            CREATE TABLE personal_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase TEXT NOT NULL,
                milestone_text TEXT NOT NULL,
                target_date TEXT,
                achieved_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    conn.commit()


def _migrate_v83_to_v84(conn: sqlite3.Connection) -> None:
    """v83→v84: Agentic technology layer — signals, execution log, content queue (Doc 23)."""
    logger.info("Migration v83→v84: Agentic technology layer (Doc 23)")
    tables = _table_set(conn)

    if "competitor_signals" not in tables:
        conn.execute("""
            CREATE TABLE competitor_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                source_url TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "research_signals" not in tables:
        conn.execute("""
            CREATE TABLE research_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                finding TEXT,
                applicability_score REAL,
                doi TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "prescription_execution_log" not in tables:
        conn.execute("""
            CREATE TABLE prescription_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result_data TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "content_generation_queue" not in tables:
        conn.execute("""
            CREATE TABLE content_generation_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gap_type TEXT NOT NULL,
                gap_data TEXT,
                generation_brief TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'generating', 'approved', 'rejected', 'error')),
                generated_content TEXT,
                reviewer_note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at TEXT
            )
        """)

    if "agent_task_log" not in tables:
        conn.execute("""
            CREATE TABLE agent_task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                task_data TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    conn.commit()


def _migrate_v84_to_v85(conn: sqlite3.Connection) -> None:
    """v84→v85: Doc 23 Tiers 2-3 + OpenClaw — 14 new tables."""
    logger.info("Migration v84→v85: Doc 23 agentic layer expansion (Tiers 2-3 + OpenClaw)")
    tables = _table_set(conn)

    if "crawl_source" not in tables:
        conn.execute("""
            CREATE TABLE crawl_source (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK (source_type IN ('competitor', 'research', 'news')),
                crawl_interval_hours INTEGER NOT NULL DEFAULT 24,
                last_crawl_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "crawl_run" not in tables:
        conn.execute("""
            CREATE TABLE crawl_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES crawl_source(id),
                status TEXT NOT NULL DEFAULT 'running',
                items_found INTEGER DEFAULT 0,
                items_new INTEGER DEFAULT 0,
                error_detail TEXT,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT
            )
        """)

    if "rag_faiss_index" not in tables:
        conn.execute("""
            CREATE TABLE rag_faiss_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_name TEXT NOT NULL UNIQUE,
                dimension INTEGER NOT NULL,
                num_vectors INTEGER NOT NULL DEFAULT 0,
                built_at TEXT NOT NULL DEFAULT (datetime('now')),
                index_path TEXT NOT NULL
            )
        """)

    if "rag_evaluation_log" not in tables:
        conn.execute("""
            CREATE TABLE rag_evaluation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                retrieved_count INTEGER NOT NULL DEFAULT 0,
                faithfulness_score REAL,
                relevance_score REAL,
                context_precision_score REAL,
                generation_prompt_key TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "research_paper" not in tables:
        conn.execute("""
            CREATE TABLE research_paper (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                authors TEXT,
                abstract TEXT,
                doi TEXT,
                published_date TEXT,
                relevance_score REAL,
                applicability_analysis TEXT,
                methodology_tags TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "research_application" not in tables:
        conn.execute("""
            CREATE TABLE research_application (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id INTEGER NOT NULL REFERENCES research_paper(id),
                aelu_component TEXT NOT NULL,
                proposed_change TEXT NOT NULL,
                impact_estimate TEXT,
                status TEXT NOT NULL DEFAULT 'proposed'
                    CHECK (status IN ('proposed', 'approved', 'rejected', 'implemented')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "teacher_lead" not in tables:
        conn.execute("""
            CREATE TABLE teacher_lead (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                profile_url TEXT,
                language_pair TEXT,
                teaching_style_tags TEXT,
                platform_rating REAL,
                estimated_students INTEGER,
                qualification_score REAL,
                qualification_notes TEXT,
                source_crawl_id INTEGER,
                status TEXT NOT NULL DEFAULT 'discovered'
                    CHECK (status IN ('discovered', 'qualified', 'disqualified', 'contacted')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "email_draft" not in tables:
        conn.execute("""
            CREATE TABLE email_draft (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_type TEXT NOT NULL
                    CHECK (recipient_type IN ('teacher_lead', 'teacher', 'learner')),
                recipient_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                body_text TEXT NOT NULL,
                body_html TEXT,
                purpose TEXT,
                tone_directive TEXT,
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'sent', 'rejected')),
                approved_by INTEGER,
                approved_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "adversarial_debate" not in tables:
        conn.execute("""
            CREATE TABLE adversarial_debate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                content_id INTEGER,
                content_data TEXT NOT NULL,
                critic_output TEXT,
                defender_output TEXT,
                judge_verdict TEXT,
                judge_score REAL,
                dimensions_tested TEXT,
                passed INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "prompt_trace" not in tables:
        conn.execute("""
            CREATE TABLE prompt_trace (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_key TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                model_used TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                error_type TEXT,
                output_quality_score REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_trace_key ON prompt_trace(prompt_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_trace_created ON prompt_trace(created_at)")

    if "prompt_regression_run" not in tables:
        conn.execute("""
            CREATE TABLE prompt_regression_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_key TEXT NOT NULL,
                baseline_hash TEXT,
                current_hash TEXT,
                metric TEXT NOT NULL,
                baseline_value REAL,
                current_value REAL,
                drift_detected INTEGER NOT NULL DEFAULT 0,
                run_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "workflow_execution" not in tables:
        conn.execute("""
            CREATE TABLE workflow_execution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_type TEXT NOT NULL,
                workflow_data TEXT,
                status TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'paused', 'completed', 'failed', 'retrying')),
                current_step TEXT,
                max_retries INTEGER NOT NULL DEFAULT 3,
                retry_count INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                error_detail TEXT
            )
        """)

    if "workflow_step" not in tables:
        conn.execute("""
            CREATE TABLE workflow_step (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id INTEGER NOT NULL REFERENCES workflow_execution(id),
                step_name TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
                input_data TEXT,
                output_data TEXT,
                started_at TEXT,
                completed_at TEXT,
                error_detail TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_step_exec ON workflow_step(execution_id)")

    if "audio_coherence_check" not in tables:
        conn.execute("""
            CREATE TABLE audio_coherence_check (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER NOT NULL,
                tts_engine TEXT NOT NULL DEFAULT 'edge-tts',
                expected_pinyin TEXT,
                transcribed_text TEXT,
                transcribed_pinyin TEXT,
                similarity_score REAL,
                passed INTEGER,
                checked_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_coherence_item ON audio_coherence_check(content_item_id)")

    conn.commit()


def _migrate_v85_to_v86(conn: sqlite3.Connection) -> None:
    """v85→v86: Add review_status column to content_item.

    AI-generated content must pass review before being served to users.
    Existing items default to 'approved' (they were manually seeded).
    """
    logger.info("Migration v85→v86: content_item.review_status column")
    cols = _col_set(conn, "content_item")
    if "review_status" not in cols:
        conn.execute(
            "ALTER TABLE content_item ADD COLUMN review_status TEXT NOT NULL DEFAULT 'approved'"
        )
        conn.commit()


def _migrate_v86_to_v87(conn: sqlite3.Connection) -> None:
    """v86->v87: Add provenance_checked column to pi_ai_review_queue.

    Human reviewers must verify AI-generated content does not appear to be
    from a published source before approving.
    """
    logger.info("Migration v86->v87: pi_ai_review_queue.provenance_checked column")
    if "pi_ai_review_queue" in _table_set(conn):
        cols = _col_set(conn, "pi_ai_review_queue")
        if "provenance_checked" not in cols:
            conn.execute(
                "ALTER TABLE pi_ai_review_queue ADD COLUMN provenance_checked INTEGER DEFAULT 0"
            )
            conn.commit()


def _migrate_v87_to_v88(conn: sqlite3.Connection) -> None:
    """v87->v88: Add error_cause column to error_log for detailed cause tracking."""
    logger.info("Migration v87->v88: error_log.error_cause + error_shape_summary table")
    cols = _col_set(conn, "error_log")
    if "error_cause" not in cols:
        conn.execute("ALTER TABLE error_log ADD COLUMN error_cause TEXT")
        conn.commit()

    # Persistent error shape summary — aggregates detailed causes across sessions
    if "error_shape_summary" not in _table_set(conn):
        conn.execute("""
            CREATE TABLE error_shape_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                error_shape TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0,
                resolved_at TEXT,
                UNIQUE(user_id, content_item_id, error_shape),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_error_shape_user "
            "ON error_shape_summary(user_id, resolved)"
        )
        conn.commit()


def _migrate_v88_to_v89(conn: sqlite3.Connection) -> None:
    """v88->v89: Add cross-session tracking columns to interference_pairs."""
    logger.info("Migration v88->v89: interference_pairs session tracking")
    if "interference_pairs" in _table_set(conn):
        cols = _col_set(conn, "interference_pairs")
        if "last_item_a_drilled" not in cols:
            conn.execute(
                "ALTER TABLE interference_pairs ADD COLUMN last_item_a_drilled TEXT"
            )
        if "last_item_b_drilled" not in cols:
            conn.execute(
                "ALTER TABLE interference_pairs ADD COLUMN last_item_b_drilled TEXT"
            )
        if "error_co_occurrence" not in cols:
            conn.execute(
                "ALTER TABLE interference_pairs ADD COLUMN error_co_occurrence INTEGER DEFAULT 0"
            )
        conn.commit()


def _migrate_v89_to_v90(conn: sqlite3.Connection) -> None:
    """v89->v90: Add interference_density to progress for LECTOR-style spacing."""
    logger.info("Migration v89->v90: progress.interference_density")
    cols = _col_set(conn, "progress")
    if "interference_density" not in cols:
        conn.execute(
            "ALTER TABLE progress ADD COLUMN interference_density REAL DEFAULT 0.0"
        )
        conn.commit()


def _migrate_v90_to_v91(conn: sqlite3.Connection) -> None:
    """v90->v91: Seed interference_pairs from confusable_pairs.json."""
    logger.info("Migration v90->v91: seed interference_pairs from confusable_pairs.json")
    import json as _json
    pairs_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "confusable_pairs.json")
    pairs_path = os.path.normpath(pairs_path)
    if not os.path.exists(pairs_path):
        logger.warning("confusable_pairs.json not found at %s, skipping seed", pairs_path)
        return

    if "interference_pairs" not in _table_set(conn):
        return

    with open(pairs_path, encoding="utf-8") as f:
        pairs = _json.load(f)

    type_map = {"visual": "visual_similarity", "phonetic": "near_homophone"}
    seeded = 0
    for p in pairs:
        pair = p.get("pair", [])
        if len(pair) != 2:
            continue
        hanzi_a, hanzi_b = pair
        # Look up content_item IDs
        row_a = conn.execute(
            "SELECT id FROM content_item WHERE hanzi = ? LIMIT 1", (hanzi_a,)
        ).fetchone()
        row_b = conn.execute(
            "SELECT id FROM content_item WHERE hanzi = ? LIMIT 1", (hanzi_b,)
        ).fetchone()
        if not row_a or not row_b:
            continue
        item_a, item_b = row_a["id"], row_b["id"]
        # Canonical ordering
        if item_a > item_b:
            item_a, item_b = item_b, item_a
        i_type = type_map.get(p.get("type", ""), "visual_similarity")
        try:
            conn.execute("""
                INSERT OR IGNORE INTO interference_pairs
                    (item_id_a, item_id_b, interference_type, interference_strength, detected_by)
                VALUES (?, ?, ?, 'high', 'human_flagged')
            """, (item_a, item_b, i_type))
            seeded += 1
        except Exception:
            pass
    conn.commit()
    logger.info("Seeded %d interference pairs from confusable_pairs.json", seeded)


def _migrate_v91_to_v92(conn):
    """Add openclaw_message_log table for audit trail."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS openclaw_message_log (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            direction TEXT NOT NULL,
            channel TEXT NOT NULL,
            user_identifier TEXT DEFAULT '',
            message_text TEXT DEFAULT '',
            intent TEXT DEFAULT '',
            tool_called TEXT DEFAULT '',
            tool_result TEXT DEFAULT '',
            injection_detected INTEGER DEFAULT 0,
            injection_detail TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_openclaw_msg_created
        ON openclaw_message_log(created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_openclaw_msg_channel
        ON openclaw_message_log(channel)
    """)
    conn.commit()


def _migrate_v92_to_v93(conn):
    """Add expires_at and created_by to invite_code for beta invite flow."""
    cols = _col_set(conn, "invite_code")
    if "expires_at" not in cols:
        conn.execute("ALTER TABLE invite_code ADD COLUMN expires_at TEXT")
    if "created_by" not in cols:
        conn.execute("ALTER TABLE invite_code ADD COLUMN created_by INTEGER REFERENCES user(id)")
    if "label" not in cols:
        conn.execute("ALTER TABLE invite_code ADD COLUMN label TEXT DEFAULT ''")
    conn.commit()


def _migrate_v93_to_v94(conn):
    """Add methodology A+ gap columns: estimate, implementation_type, blocked_reason on work_item."""
    cols = _col_set(conn, "work_item")
    if "estimate" not in cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN estimate TEXT")  # S/M/L/XL
    if "implementation_type" not in cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN implementation_type TEXT")  # prototype/full/NULL
    if "blocked_reason" not in cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN blocked_reason TEXT")
    conn.commit()


def _migrate_v94_to_v95(conn):
    """Add assignment, assignment_submission, curriculum_path, dictionary_entry tables."""
    tables = _table_set(conn)

    # Full assignment table (extends basic classroom_assignment)
    if "assignment" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assignment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classroom_id INTEGER REFERENCES classroom(id),
                title TEXT NOT NULL,
                description TEXT,
                assignment_type TEXT CHECK (assignment_type IN ('drill', 'reading', 'grammar', 'mixed')),
                content_ids TEXT,
                due_date TEXT,
                created_by INTEGER REFERENCES user(id),
                status TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assignment_classroom ON assignment(classroom_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assignment_status ON assignment(status)")

    if "assignment_submission" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assignment_submission (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER REFERENCES assignment(id),
                user_id INTEGER REFERENCES user(id),
                completed_at TEXT,
                score REAL,
                items_completed INTEGER DEFAULT 0,
                items_correct INTEGER DEFAULT 0,
                time_spent_seconds INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'late')),
                UNIQUE(assignment_id, user_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submission_assignment ON assignment_submission(assignment_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submission_user ON assignment_submission(user_id)")

    if "curriculum_path" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS curriculum_path (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classroom_id INTEGER REFERENCES classroom(id),
                name TEXT NOT NULL,
                description TEXT,
                sequence_json TEXT NOT NULL,
                created_by INTEGER REFERENCES user(id),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_curriculum_path_classroom ON curriculum_path(classroom_id)")

    if "dictionary_entry" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dictionary_entry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                traditional TEXT NOT NULL,
                simplified TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                english TEXT NOT NULL,
                frequency_rank INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dict_simplified ON dictionary_entry(simplified)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dict_traditional ON dictionary_entry(traditional)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dict_pinyin ON dictionary_entry(pinyin)")

    conn.commit()


def _migrate_v95_to_v96(conn):
    """Add sprint enhancements, retrospective, root_cause_analysis, risk_review tables; WSJF fields on work_item."""
    tables = _table_set(conn)

    # 1. Sprint table enhancements: add retro/review columns
    sprint_cols = _col_set(conn, "sprint")
    if "review_notes" not in sprint_cols:
        conn.execute("ALTER TABLE sprint ADD COLUMN review_notes TEXT")
    if "retro_went_well" not in sprint_cols:
        conn.execute("ALTER TABLE sprint ADD COLUMN retro_went_well TEXT")
    if "retro_improve" not in sprint_cols:
        conn.execute("ALTER TABLE sprint ADD COLUMN retro_improve TEXT")
    if "retro_action_items" not in sprint_cols:
        conn.execute("ALTER TABLE sprint ADD COLUMN retro_action_items TEXT")

    # 2. Add sprint_id to work_item
    wi_cols = _col_set(conn, "work_item")
    if "sprint_id" not in wi_cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN sprint_id INTEGER REFERENCES sprint(id)")

    # 3. WSJF fields on work_item
    if "business_value" not in wi_cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN business_value INTEGER DEFAULT 5")
    if "time_criticality" not in wi_cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN time_criticality INTEGER DEFAULT 5")
    if "risk_reduction" not in wi_cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN risk_reduction INTEGER DEFAULT 5")
    if "job_size" not in wi_cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN job_size INTEGER DEFAULT 5")

    # 4. Standalone retrospective table
    if "retrospective" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retrospective (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT,
                went_well TEXT,
                improve TEXT,
                action_items TEXT,
                sprint_id INTEGER REFERENCES sprint(id),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

    # 5. Root cause analysis table (5 Whys + Ishikawa)
    if "root_cause_analysis" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS root_cause_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_item_id INTEGER REFERENCES work_item(id),
                improvement_id INTEGER,
                why_1 TEXT,
                why_2 TEXT,
                why_3 TEXT,
                why_4 TEXT,
                why_5 TEXT,
                root_cause TEXT,
                category TEXT CHECK (category IN ('method', 'measurement', 'material', 'machine', 'man', 'environment')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rca_work_item ON root_cause_analysis(work_item_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rca_category ON root_cause_analysis(category)")

    # 6. Risk review table (Spiral risk burndown)
    if "risk_review" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_review (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                risk_item_id INTEGER REFERENCES risk_item(id),
                previous_score REAL,
                new_score REAL,
                notes TEXT,
                reviewed_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_review_item ON risk_review(risk_item_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_review_date ON risk_review(reviewed_at)")

    conn.commit()


def _migrate_v96_to_v97(conn):
    """Add target_retention_rate to learner_profile, suspended_until to progress."""
    lp_cols = _col_set(conn, "learner_profile")
    if "target_retention_rate" not in lp_cols:
        conn.execute(
            "ALTER TABLE learner_profile ADD COLUMN target_retention_rate REAL DEFAULT 0.85"
        )

    p_cols = _col_set(conn, "progress")
    if "suspended_until" not in p_cols:
        conn.execute(
            "ALTER TABLE progress ADD COLUMN suspended_until TEXT"  # ISO date or NULL
        )

    conn.commit()


def _migrate_v97_to_v98(conn):
    """Add image_url to content_item, study_list table for community features."""
    ci_cols = _col_set(conn, "content_item")
    if "image_url" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN image_url TEXT")

    tables = _table_set(conn)
    if "study_list" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS study_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES user(id),
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                item_ids TEXT NOT NULL DEFAULT '[]',
                public INTEGER NOT NULL DEFAULT 0,
                share_code TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_study_list_user ON study_list(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_study_list_share ON study_list(share_code)")

    conn.commit()


def _migrate_v98_to_v99(conn):
    """NIST AI RMF: content provenance tracking columns on content_item.

    Adds is_ai_generated, generated_by_prompt, human_reviewed_at,
    human_reviewer_id for AI content provenance and human review gate.
    CHECK: if is_ai_generated=1, generated_by_prompt must be NOT NULL.
    """
    ci_cols = _col_set(conn, "content_item")
    if "is_ai_generated" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN is_ai_generated INTEGER NOT NULL DEFAULT 0")
    if "generated_by_prompt" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN generated_by_prompt TEXT")
    if "human_reviewed_at" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN human_reviewed_at TEXT")
    if "human_reviewer_id" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN human_reviewer_id INTEGER")

    # Add a trigger to enforce: when is_ai_generated=1, generated_by_prompt must be NOT NULL.
    # SQLite can't ALTER CHECK constraints, so we use a trigger instead.
    conn.execute("DROP TRIGGER IF EXISTS trg_ai_provenance_check_insert")
    conn.execute("""
        CREATE TRIGGER trg_ai_provenance_check_insert
        BEFORE INSERT ON content_item
        WHEN NEW.is_ai_generated = 1 AND NEW.generated_by_prompt IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'AI-generated content must have generated_by_prompt set');
        END
    """)
    conn.execute("DROP TRIGGER IF EXISTS trg_ai_provenance_check_update")
    conn.execute("""
        CREATE TRIGGER trg_ai_provenance_check_update
        BEFORE UPDATE ON content_item
        WHEN NEW.is_ai_generated = 1 AND NEW.generated_by_prompt IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'AI-generated content must have generated_by_prompt set');
        END
    """)

    conn.commit()


def _migrate_v99_to_v100(conn):
    """Autonomous A/B testing: experiment proposals and graduated rollouts."""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "experiment_proposal" not in tables:
        conn.execute("""
            CREATE TABLE experiment_proposal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                hypothesis TEXT NOT NULL,
                source TEXT NOT NULL,
                source_detail TEXT,
                variants TEXT NOT NULL,
                traffic_pct REAL DEFAULT 50.0,
                guardrail_metrics TEXT,
                min_sample_size INTEGER DEFAULT 100,
                priority INTEGER DEFAULT 0,
                scope TEXT DEFAULT 'parameter',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                reviewed_at TEXT,
                started_experiment_id INTEGER,
                FOREIGN KEY (started_experiment_id) REFERENCES experiment(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_experiment_proposal_status "
            "ON experiment_proposal(status)"
        )
    else:
        # Migration: add scope column if missing
        cols = {r[1] for r in conn.execute("PRAGMA table_info(experiment_proposal)").fetchall()}
        if "scope" not in cols:
            conn.execute("ALTER TABLE experiment_proposal ADD COLUMN scope TEXT DEFAULT 'parameter'")

    if "experiment_rollout" not in tables:
        conn.execute("""
            CREATE TABLE experiment_rollout (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                winner_variant TEXT NOT NULL,
                rollout_stage TEXT DEFAULT 'pending',
                current_pct INTEGER DEFAULT 0,
                stage_started_at TEXT,
                next_stage_at TEXT,
                feature_flag_name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_experiment_rollout_stage "
            "ON experiment_rollout(rollout_stage)"
        )

    conn.commit()


def _migrate_v100_to_v101(conn):
    """Add example_sentence columns to content_item for AI-generated drills."""
    ci_cols = _col_set(conn, "content_item")
    if "example_sentence_hanzi" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN example_sentence_hanzi TEXT")
    if "example_sentence_pinyin" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN example_sentence_pinyin TEXT")
    if "example_sentence_english" not in ci_cols:
        conn.execute("ALTER TABLE content_item ADD COLUMN example_sentence_english TEXT")
    conn.commit()


def _migrate_v101_to_v102(conn):
    """Add password_history table for password reuse prevention."""
    tables = _table_set(conn)
    if "password_history" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS password_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_password_history_user ON password_history(user_id);
        """)
        conn.commit()



def _migrate_v102_to_v103(conn):
    """Add anti-Goodhart counter-metric tables: snapshot storage + holdout probes."""
    tables = _table_set(conn)
    if "counter_metric_snapshot" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS counter_metric_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                computed_at TEXT NOT NULL,
                overall_health TEXT NOT NULL DEFAULT 'unknown',
                alert_count INTEGER NOT NULL DEFAULT 0,
                critical_count INTEGER NOT NULL DEFAULT 0,
                integrity_json TEXT,
                cost_json TEXT,
                distortion_json TEXT,
                outcome_json TEXT,
                alerts_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cm_snapshot_user_date
                ON counter_metric_snapshot(user_id, computed_at);
        """)
    if "counter_metric_holdout" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS counter_metric_holdout (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                modality TEXT NOT NULL DEFAULT 'reading',
                drill_type TEXT,
                correct INTEGER NOT NULL DEFAULT 0,
                response_ms INTEGER,
                administered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                session_id INTEGER,
                holdout_set TEXT NOT NULL DEFAULT 'standard'
            );
            CREATE INDEX IF NOT EXISTS idx_cm_holdout_user_date
                ON counter_metric_holdout(user_id, administered_at);
            CREATE INDEX IF NOT EXISTS idx_cm_holdout_item
                ON counter_metric_holdout(content_item_id);
        """)
    if "counter_metric_action_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS counter_metric_action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
        """)
    conn.commit()


def _migrate_v103_to_v104(conn):
    """Add delayed recall validation table for counter-metric integrity checks."""
    tables = _table_set(conn)
    if "counter_metric_delayed_validation" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS counter_metric_delayed_validation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                content_item_id INTEGER NOT NULL,
                modality TEXT NOT NULL DEFAULT 'reading',
                scheduled_at TEXT NOT NULL,
                delay_days INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                administered_at TEXT,
                correct INTEGER,
                response_ms INTEGER,
                session_id INTEGER,
                drill_type TEXT,
                mastery_at_schedule TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_cm_dv_user_status
                ON counter_metric_delayed_validation(user_id, status, scheduled_at);
            CREATE INDEX IF NOT EXISTS idx_cm_dv_item
                ON counter_metric_delayed_validation(content_item_id);
        """)
    conn.commit()


def _migrate_v104_to_v105(conn):
    """Add content_reaudit_log table for post-approval quality monitoring."""
    tables = _table_set(conn)
    if "content_reaudit_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS content_reaudit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER NOT NULL,
                audited_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                audit_type TEXT NOT NULL DEFAULT 'scheduled',
                passed INTEGER NOT NULL DEFAULT 1,
                issues_found TEXT,
                learner_accuracy REAL,
                attempt_count INTEGER,
                action_taken TEXT,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_reaudit_item
                ON content_reaudit_log(content_item_id);
            CREATE INDEX IF NOT EXISTS idx_reaudit_passed
                ON content_reaudit_log(passed, audited_at);
        """)

    # Add created_at to pi_ai_review_queue if missing (needed for latency calculation)
    cols = _col_set(conn, "pi_ai_review_queue")
    if "created_at" not in cols and "queued_at" not in cols:
        try:
            conn.execute("""
                ALTER TABLE pi_ai_review_queue
                ADD COLUMN created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            """)
        except sqlite3.OperationalError:
            pass  # Column may already exist under different name

    conn.commit()


def _migrate_v105_to_v106(conn):
    """Add platform_status to work orders + ensure prescription_execution_log exists."""
    # Add platform_status column for cross-platform change tracking
    cols = _col_set(conn, "pi_work_order")
    if "platform_status" not in cols:
        try:
            conn.execute("""
                ALTER TABLE pi_work_order
                ADD COLUMN platform_status TEXT DEFAULT '{}'
            """)
        except sqlite3.OperationalError:
            pass

    # Ensure prescription_execution_log has all needed columns
    tables = _table_set(conn)
    if "prescription_execution_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prescription_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                result_data TEXT,
                pre_audit_score REAL,
                post_audit_score REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_pel_status
                ON prescription_execution_log(status);
            CREATE INDEX IF NOT EXISTS idx_pel_wo
                ON prescription_execution_log(work_order_id);
        """)
    else:
        # Add columns if table already exists but lacks them
        cols = _col_set(conn, "prescription_execution_log")
        for col, default in [
            ("pre_audit_score", "NULL"),
            ("post_audit_score", "NULL"),
            ("completed_at", "NULL"),
        ]:
            if col not in cols:
                try:
                    conn.execute(
                        f"ALTER TABLE prescription_execution_log ADD COLUMN {col} REAL DEFAULT {default}"
                        if "score" in col else
                        f"ALTER TABLE prescription_execution_log ADD COLUMN {col} TEXT DEFAULT {default}"
                    )
                except sqlite3.OperationalError:
                    pass

    conn.commit()


def _migrate_v106_to_v107(conn):
    """Add pi_model_registry for agentic model selection."""
    tables = _table_set(conn)
    if "pi_model_registry" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pi_model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                model_name TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'ollama',
                quality_score REAL,
                latency_p50_ms INTEGER,
                latency_p95_ms INTEGER,
                cost_per_1k_tokens REAL,
                sample_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                benchmarked_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(task_type, model_name)
            );
            CREATE INDEX IF NOT EXISTS idx_model_reg_task
                ON pi_model_registry(task_type, is_active);
        """)
    conn.commit()


def _migrate_v107_to_v108(conn):
    """v107->v108: Add pattern, explanation, examples columns to grammar_point.

    These columns are referenced by grammar_tutor.py, grammar_routes.py, and
    exposure_routes.py but were never added to the schema.  This caused 500
    errors on /api/grammar/ask, /api/grammar/point/<id>/teach, and related
    grammar endpoints.
    """
    gp_cols = _col_set(conn, "grammar_point")
    if "pattern" not in gp_cols:
        conn.execute("ALTER TABLE grammar_point ADD COLUMN pattern TEXT")
    if "explanation" not in gp_cols:
        conn.execute("ALTER TABLE grammar_point ADD COLUMN explanation TEXT")
    if "examples" not in gp_cols:
        conn.execute("ALTER TABLE grammar_point ADD COLUMN examples TEXT")
    conn.commit()


def _migrate_v108_to_v109(conn):
    """v108->v109: Add listening block columns to listening_progress.

    The ListeningBlock feature needs listening_time_seconds, playback_speed,
    and replays columns for tracking in-session listening comprehension.
    Also adds an index on (user_id, completed_at) for efficient lookups.
    """
    tables = _table_set(conn)
    if "listening_progress" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS listening_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                passage_id TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                comprehension_score REAL DEFAULT 0.0,
                questions_correct INTEGER DEFAULT 0,
                questions_total INTEGER DEFAULT 0,
                words_looked_up INTEGER DEFAULT 0,
                hsk_level INTEGER DEFAULT 1,
                listening_time_seconds INTEGER DEFAULT 0,
                playback_speed REAL DEFAULT 1.0,
                replays INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_listening_progress_user
                ON listening_progress(user_id, completed_at);
        """)
    else:
        lp_cols = _col_set(conn, "listening_progress")
        if "listening_time_seconds" not in lp_cols:
            conn.execute(
                "ALTER TABLE listening_progress ADD COLUMN listening_time_seconds INTEGER DEFAULT 0"
            )
        if "playback_speed" not in lp_cols:
            conn.execute(
                "ALTER TABLE listening_progress ADD COLUMN playback_speed REAL DEFAULT 1.0"
            )
        if "replays" not in lp_cols:
            conn.execute(
                "ALTER TABLE listening_progress ADD COLUMN replays INTEGER DEFAULT 0"
            )
        # Add index if missing
        idx_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_listening_progress_user'"
        ).fetchall()
        if not idx_rows:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_listening_progress_user "
                "ON listening_progress(user_id, completed_at)"
            )
    conn.commit()


def _find_grammar_id(points: dict, pattern: str) -> int | None:
    """Fuzzy-match a grammar point by name/pattern key.

    Tries exact match, then substring, then prefix match.
    """
    key = pattern.lower().strip()
    if key in points:
        return points[key]
    # Substring match
    for k, v in points.items():
        if key in k or k in key:
            return v
    return None


def _seed_grammar_prerequisites(conn):
    """Seed core grammar prerequisite relationships based on Pienemann's Processability Theory.

    Hierarchy (each level requires mastery of the previous):
      1. Lemma access: 是, 有, 在, 不
      2. Category procedure: 的 modification, adjective predicates, measure words
      3. Phrasal procedure: SVO order, 在+location, time expressions
      4. S-procedure: 了 completion, 过 experience, 把 construction
      5. Subordinate clause: 因为...所以, 虽然...但是, 如果...就
    """
    points = {}
    for row in conn.execute("SELECT id, name FROM grammar_point").fetchall():
        key = (row["name"] or "").lower().strip()
        if key:
            points[key] = row["id"]

    if not points:
        return

    # (grammar_name_fragment, prerequisite_name_fragment, relationship)
    prerequisites = [
        # ── Level 2 (category procedure) requires Level 1 (lemma access) ──
        ("的 possession", "是", "requires"),
        ("很 + adjective", "是", "requires"),
        ("measure words", "有", "requires"),
        ("不 negation", "是", "requires"),
        ("没 negation", "有", "requires"),

        # ── Level 3 (phrasal) requires Level 2 (category) ──
        ("svo basic", "是", "requires"),
        ("svo basic", "不 negation", "requires"),
        ("在 location", "是", "requires"),
        ("time word placement", "svo basic", "requires"),
        ("number + measure", "measure words", "requires"),
        ("adjective predicate", "很 + adjective", "requires"),

        # ── Question forms require basic sentence structure ──
        ("吗 yes/no", "svo basic", "requires"),
        ("呢 follow-up", "吗 yes/no", "requires"),
        ("question words", "svo basic", "requires"),
        ("几/多少", "question words", "requires"),
        ("是不是", "是", "requires"),
        ("v不v", "不 negation", "requires"),

        # ── Desire/ability verbs require SVO ──
        ("想/要 expressing", "svo basic", "requires"),
        ("会 can", "svo basic", "requires"),
        ("可以/能", "会 can", "requires"),

        # ── Level 4 (S-procedure) requires Level 3 (phrasal) ──
        ("了 completed", "svo basic", "requires"),
        ("了 completed", "不 negation", "requires"),
        ("了 perfective", "了 completed", "extends"),
        ("过 experience", "了 completed", "requires"),
        ("正在 ongoing", "在 location", "requires"),
        ("在+v progressive", "正在 ongoing", "extends"),
        ("着 continuous", "正在 ongoing", "requires"),

        # ── Comparison requires adjective predicates ──
        ("比 comparison", "adjective predicate", "requires"),
        ("比 comparison", "很 + adjective", "requires"),
        ("最 superlative", "比 comparison", "requires"),
        ("更 even more", "比 comparison", "requires"),
        ("比+adj+一点", "比 comparison", "extends"),

        # ── Complement constructions require basic verbs + 了 ──
        ("得 complement", "了 completed", "requires"),
        ("duration complement", "了 completed", "requires"),
        ("v+到 result", "了 completed", "requires"),
        ("v+完 result", "了 completed", "requires"),
        ("v+见 result", "了 completed", "requires"),
        ("v+懂 result", "了 completed", "requires"),

        # ── Causative/passive require transitive sentence mastery ──
        ("让/叫 causative", "svo basic", "requires"),
        ("让/叫 causative", "了 completed", "recommended"),
        ("给 for/give", "svo basic", "requires"),
        ("double object", "给 for/give", "requires"),

        # ── Level 5 (subordinate clause) requires Level 4 ──
        ("虽然", "了 completed", "requires"),
        ("所以", "了 completed", "requires"),
        ("要是", "了 completed", "requires"),
        ("...的话", "了 completed", "requires"),

        # ── Adverb ordering ──
        ("就 then", "svo basic", "requires"),
        ("就 then", "time word placement", "requires"),
        ("才 only then", "就 then", "requires"),
        ("先...再", "就 then", "requires"),
        ("已经...了", "了 completed", "requires"),
        ("又 again", "了 completed", "requires"),
        ("再 again", "不 negation", "requires"),
        ("一直", "在+v progressive", "recommended"),

        # ── Direction/location requires 在 ──
        ("从...到", "在 location", "requires"),
        ("从 from", "在 location", "requires"),
        ("向/往", "从 from", "requires"),
        ("到 arrive", "在 location", "requires"),
        ("location words", "在 location", "requires"),
        ("到...去", "到 arrive", "extends"),

        # ── Other common patterns ──
        ("也 also", "svo basic", "requires"),
        ("都 all", "也 also", "requires"),
        ("还是 or", "吗 yes/no", "requires"),
        ("verb reduplication", "svo basic", "requires"),
        ("一下 briefly", "verb reduplication", "requires"),
        ("快要...了", "了 completed", "requires"),
        ("太...了", "很 + adjective", "requires"),
        ("有点儿", "很 + adjective", "requires"),
        ("一点儿", "比 comparison", "recommended"),
        ("别 don't", "不 negation", "requires"),
    ]

    inserted = 0
    for point_pattern, prereq_pattern, rel in prerequisites:
        point_id = _find_grammar_id(points, point_pattern)
        prereq_id = _find_grammar_id(points, prereq_pattern)
        if point_id and prereq_id and point_id != prereq_id:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO grammar_prerequisites
                    (grammar_point_id, prerequisite_id, relationship)
                    VALUES (?, ?, ?)
                """, (point_id, prereq_id, rel))
                inserted += 1
            except Exception:
                pass
    conn.commit()
    logger.info("Seeded %d grammar prerequisite relationships", inserted)


def _migrate_v109_to_v110(conn):
    """v109->v110: Add grammar_prerequisites table for Pienemann's Processability Theory DAG.

    Creates the prerequisite graph table and seeds ~50 core relationships
    encoding the natural acquisition order for Mandarin grammar points.
    """
    tables = _table_set(conn)
    if "grammar_prerequisites" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS grammar_prerequisites (
                grammar_point_id INTEGER NOT NULL,
                prerequisite_id INTEGER NOT NULL,
                relationship TEXT DEFAULT 'requires',
                PRIMARY KEY (grammar_point_id, prerequisite_id),
                FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id),
                FOREIGN KEY (prerequisite_id) REFERENCES grammar_point(id)
            );
            CREATE INDEX IF NOT EXISTS idx_grammar_prereq_point
                ON grammar_prerequisites(grammar_point_id);
            CREATE INDEX IF NOT EXISTS idx_grammar_prereq_prereq
                ON grammar_prerequisites(prerequisite_id);
        """)
    conn.commit()

    # Seed prerequisite relationships (idempotent via INSERT OR IGNORE)
    _seed_grammar_prerequisites(conn)


def _migrate_v110_to_v111(conn):
    """v110->v111: Metacognitive prompts (Dunlosky 2013) and SDT motivation (Ryan & Deci 2000).

    Creates tables for confidence calibration, error reflection, and
    session self-assessment. Adds user_choice column to session_log for
    SDT autonomy support.
    """
    tables = _table_set(conn)

    if "confidence_calibration" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS confidence_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id TEXT,
                item_id INTEGER,
                confidence TEXT NOT NULL,
                was_correct INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "error_reflection" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_reflection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER,
                reflection_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "session_self_assessment" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_self_assessment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id TEXT,
                difficulty_rating TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    # Add user_choice column to session_log for SDT autonomy
    session_cols = _col_set(conn, "session_log")
    if "user_choice" not in session_cols:
        conn.execute("ALTER TABLE session_log ADD COLUMN user_choice TEXT")
        conn.commit()


def _migrate_v111_to_v112(conn):
    """v111->v112: drill_type_posterior table for per-item Thompson Sampling (Beta-Bernoulli bandit).

    Each (user, item, drill_type) triple maintains a Beta(alpha, beta) posterior
    updated after each drill attempt. Used by _thompson_sample_drill_type in scheduler.
    """
    tables = _table_set(conn)

    if "drill_type_posterior" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drill_type_posterior (
                user_id INTEGER NOT NULL,
                content_item_id INTEGER NOT NULL,
                drill_type TEXT NOT NULL,
                alpha REAL NOT NULL DEFAULT 1.0,
                beta REAL NOT NULL DEFAULT 1.0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, content_item_id, drill_type)
            )
        """)
        conn.commit()


def _migrate_v112_to_v113(conn):
    """v112->v113: LLM cost metering and referral tracking tables.

    llm_cost_log tracks per-call LLM spend for cost analytics.
    referral_log tracks user-to-user referrals for viral coefficient.
    """
    tables = _table_set(conn)

    if "llm_cost_log" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cost_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_cost_log_day ON llm_cost_log(date(created_at))
        """)
        conn.commit()

    if "referral_log" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                channel TEXT DEFAULT 'link',
                referral_code TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referral_log_referrer ON referral_log(referrer_id)
        """)
        conn.commit()


def _migrate_v113_to_v114(conn):
    """v113->v114: Design for Six Sigma (DFSS) tables.

    pi_voc_capture — Voice of Customer signals from learner feedback.
    pi_design_spec — CTQ design specifications for new features.
    pi_dmadv_log — DMADV cycle audit log (Define-Measure-Analyze-Design-Verify).
    """
    tables = _table_set(conn)

    if "pi_voc_capture" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_voc_capture (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_need TEXT NOT NULL,
                ctq_metric TEXT,
                source TEXT DEFAULT 'auto',
                source_detail TEXT,
                priority INTEGER DEFAULT 0,
                captured_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_voc_capture_need ON pi_voc_capture(customer_need)
        """)
        conn.commit()

    if "pi_design_spec" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_design_spec (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT NOT NULL,
                spec_description TEXT NOT NULL,
                target_value TEXT,
                verification_method TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'draft',
                verified_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(feature_name, spec_description)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_design_spec_feature ON pi_design_spec(feature_name)
        """)
        conn.commit()

    if "pi_dmadv_log" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_dmadv_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT NOT NULL,
                define_json TEXT,
                measure_json TEXT,
                analyze_json TEXT,
                design_json TEXT,
                verify_json TEXT,
                gate_blocked TEXT,
                gate_reason TEXT,
                design_fmea_max_rpn INTEGER DEFAULT 0,
                approved INTEGER DEFAULT 0,
                run_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dmadv_log_feature ON pi_dmadv_log(feature_name)
        """)
        conn.commit()


def _migrate_v114_to_v115(conn):
    """v114->v115: Nudge registry for behavioral economics tracking.

    nudge_registry — central catalog of all nudges with DOCTRINE ethics scores.
    nudge_exposure — tracks when a user sees a nudge.
    nudge_outcome — tracks what the user did after seeing a nudge.
    """
    tables = _table_set(conn)

    if "nudge_registry" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nudge_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nudge_key TEXT NOT NULL UNIQUE,
                nudge_type TEXT NOT NULL DEFAULT 'informational',
                copy_template TEXT NOT NULL,
                doctrine_score REAL,
                doctrine_evaluation TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                platforms TEXT DEFAULT 'web,ios,android,macos',
                experiment_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nudge_registry_key
            ON nudge_registry(nudge_key)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nudge_registry_status
            ON nudge_registry(status)
        """)
        conn.commit()

    if "nudge_exposure" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nudge_exposure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nudge_id INTEGER NOT NULL REFERENCES nudge_registry(id),
                user_id INTEGER NOT NULL,
                context TEXT DEFAULT '',
                variant TEXT DEFAULT 'control',
                exposed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nudge_exposure_nudge
            ON nudge_exposure(nudge_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nudge_exposure_user
            ON nudge_exposure(user_id)
        """)
        conn.commit()

    if "nudge_outcome" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nudge_outcome (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nudge_exposure_id INTEGER NOT NULL REFERENCES nudge_exposure(id),
                outcome_type TEXT NOT NULL,
                outcome_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nudge_outcome_exposure
            ON nudge_outcome(nudge_exposure_id)
        """)
        conn.commit()

    # Add preferred_study_time to learner_profile (implementation intentions)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(learner_profile)").fetchall()}
        if "preferred_study_time" not in cols:
            conn.execute(
                "ALTER TABLE learner_profile ADD COLUMN preferred_study_time TEXT DEFAULT 'varies'"
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass


def _migrate_v115_to_v116(conn):
    """v115->v116: Management consulting frameworks — BSC, waterfall, journey,
    Kano, JTBD, OKR, flywheel snapshots, acquisition cost, decision log enhancements.
    """
    tables = _table_set(conn)

    if "pi_balanced_scorecard" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_balanced_scorecard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                perspective TEXT NOT NULL,
                metric_key TEXT NOT NULL UNIQUE,
                metric_name TEXT NOT NULL,
                indicator_type TEXT NOT NULL,
                current_value REAL,
                target_value REAL,
                status TEXT,
                linked_lead_metric TEXT,
                data_source_sql TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bsc_perspective ON pi_balanced_scorecard(perspective)")
        conn.commit()

    if "pi_revenue_waterfall" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_revenue_waterfall (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                new_mrr REAL NOT NULL DEFAULT 0,
                expansion_mrr REAL NOT NULL DEFAULT 0,
                reactivation_mrr REAL NOT NULL DEFAULT 0,
                contraction_mrr REAL NOT NULL DEFAULT 0,
                churn_mrr REAL NOT NULL DEFAULT 0,
                net_new_mrr REAL NOT NULL DEFAULT 0,
                ending_mrr REAL NOT NULL DEFAULT 0,
                computed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "pi_journey_touchpoints" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_journey_touchpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage TEXT NOT NULL,
                touchpoint TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'web',
                emotion_proxy TEXT,
                drop_off_rate REAL,
                avg_time_in_stage_hours REAL,
                computed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journey_stage ON pi_journey_touchpoints(stage)")
        conn.commit()

    if "pi_kano_classification" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_kano_classification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_key TEXT NOT NULL UNIQUE,
                feature_name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'indifferent',
                evidence_type TEXT DEFAULT 'behavioral',
                satisfaction_if_present REAL,
                dissatisfaction_if_absent REAL,
                usage_rate REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "pi_jtbd_map" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_jtbd_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_statement TEXT NOT NULL,
                job_category TEXT NOT NULL DEFAULT 'functional',
                user_segment TEXT,
                feature_mapping TEXT,
                evidence_source TEXT DEFAULT 'behavioral',
                evidence_strength TEXT DEFAULT 'weak',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "pi_okr_objective" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_okr_objective (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                quarter TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'on_track',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "pi_okr_key_result" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_okr_key_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                objective_id INTEGER NOT NULL REFERENCES pi_okr_objective(id),
                description TEXT NOT NULL,
                metric_key TEXT,
                baseline REAL NOT NULL DEFAULT 0,
                target REAL NOT NULL,
                current_value REAL NOT NULL DEFAULT 0,
                unit TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_okr_kr_obj ON pi_okr_key_result(objective_id)")
        conn.commit()

    if "pi_flywheel_snapshot" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_flywheel_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL UNIQUE,
                content_velocity REAL,
                engagement_multiplier REAL,
                referral_multiplier REAL,
                growth_multiplier REAL,
                total_velocity REAL,
                bottleneck_node TEXT,
                computed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    if "acquisition_cost" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS acquisition_cost (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                month TEXT NOT NULL,
                spend_cents INTEGER NOT NULL DEFAULT 0,
                users_acquired INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(channel, month)
            )
        """)
        conn.commit()

    # Enhance pi_decision_log with outcome tracking columns
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(pi_decision_log)").fetchall()}
        for col, definition in [
            ("alternatives_considered", "TEXT"),
            ("expected_outcome", "TEXT"),
            ("actual_outcome", "TEXT"),
            ("outcome_measured_at", "TEXT"),
            ("decision_scope", "TEXT DEFAULT 'finding'"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE pi_decision_log ADD COLUMN {col} {definition}")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Enhance pi_strategic_hypotheses with priority and experiment linkage
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(pi_strategic_hypotheses)").fetchall()}
        for col, definition in [
            ("priority", "TEXT DEFAULT 'p1'"),
            ("predicted_outcome", "TEXT"),
            ("effort_estimate", "TEXT"),
            ("experiment_id", "INTEGER"),
            ("conclusion", "TEXT"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE pi_strategic_hypotheses ADD COLUMN {col} {definition}")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _migrate_v116_to_v117(conn):
    """v116->v117: Listening playback speed + classroom assignment type for non-core features."""
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(learner_profile)").fetchall()}
        if "preferred_playback_speed" not in cols:
            conn.execute(
                "ALTER TABLE learner_profile ADD COLUMN preferred_playback_speed REAL DEFAULT 1.0"
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add assignment_type to classroom_assignment for non-core feature assignments
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(classroom_assignment)").fetchall()}
        if "assignment_type" not in cols:
            conn.execute(
                "ALTER TABLE classroom_assignment ADD COLUMN assignment_type TEXT DEFAULT 'drill'"
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass


def _migrate_v117_to_v118(conn):
    """v117->v118: Experiment assignment architecture — eligibility, stratification,
    balance monitoring, audit logging, governance, holdout groups."""
    tables = _table_set(conn)

    # Extend experiment table with governance/stratification columns
    exp_cols = _col_set(conn, "experiment") if "experiment" in tables else set()
    new_exp_cols = {
        "salt": "TEXT",
        "hypothesis": "TEXT",
        "primary_metric": "TEXT",
        "secondary_metrics": "TEXT",
        "outcome_window_days": "INTEGER DEFAULT 7",
        "outcome_horizon": "TEXT DEFAULT 'short'",
        "mde": "REAL",
        "eligibility_rules": "TEXT",
        "stratification_config": "TEXT",
        "predeclared_subgroups": "TEXT",
        "goodhart_risks": "TEXT",
        "contamination_risks": "TEXT",
        "pre_registration": "TEXT",
        "config_frozen_at": "TEXT",
        "randomization_unit": "TEXT DEFAULT 'user'",
    }
    for col, typedef in new_exp_cols.items():
        if col not in exp_cols:
            try:
                conn.execute(f"ALTER TABLE experiment ADD COLUMN {col} {typedef}")
            except Exception:
                pass

    # Extend experiment_assignment table
    assign_cols = _col_set(conn, "experiment_assignment") if "experiment_assignment" in tables else set()
    for col, typedef in {"stratum": "TEXT", "hash_value": "TEXT",
                         "eligibility_version": "TEXT", "pre_period_data": "TEXT"}.items():
        if col not in assign_cols:
            try:
                conn.execute(f"ALTER TABLE experiment_assignment ADD COLUMN {col} {typedef}")
            except Exception:
                pass

    if "experiment_audit_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            );
            CREATE INDEX IF NOT EXISTS idx_exp_audit_experiment ON experiment_audit_log(experiment_id);
        """)

    if "experiment_balance_check" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_balance_check (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                check_type TEXT NOT NULL,
                passed INTEGER NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            );
            CREATE INDEX IF NOT EXISTS idx_exp_balance_experiment ON experiment_balance_check(experiment_id);
        """)

    if "experiment_eligibility_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_eligibility_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                eligible INTEGER NOT NULL,
                reasons TEXT,
                checked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            );
            CREATE INDEX IF NOT EXISTS idx_exp_eligibility_experiment ON experiment_eligibility_log(experiment_id);
        """)

    if "experiment_holdout" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_holdout (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                assigned_at TEXT DEFAULT (datetime('now')),
                holdout_group TEXT DEFAULT 'global'
            );
            CREATE INDEX IF NOT EXISTS idx_exp_holdout_user ON experiment_holdout(user_id);
        """)

    conn.commit()


def _migrate_v118_to_v119(conn):
    """v118->v119: Add price_variant column to user table for A/B pricing experiments."""
    user_cols = _col_set(conn, "user")
    if "price_variant" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN price_variant TEXT")
        conn.commit()


def _migrate_v119_to_v120(conn):
    """v119->v120: Marketing automation tables — content bank, variants, approval, posting, metrics."""
    conn.executescript("""
        -- Content bank registry (parsed from markdown source files)
        CREATE TABLE IF NOT EXISTS marketing_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            content_type TEXT NOT NULL,
            original_text TEXT NOT NULL,
            source_file TEXT,
            requires_personalization INTEGER DEFAULT 0,
            identity_passed INTEGER,
            voice_score REAL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );

        -- A/B variant storage
        CREATE TABLE IF NOT EXISTS marketing_content_variant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            variant_id TEXT NOT NULL,
            variant_text TEXT NOT NULL,
            generation_model TEXT,
            voice_score REAL,
            identity_passed INTEGER DEFAULT 0,
            copy_drift_passed INTEGER DEFAULT 0,
            experiment_id INTEGER,
            status TEXT DEFAULT 'draft'
                CHECK(status IN ('draft', 'approved', 'rejected', 'posted', 'winner')),
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (experiment_id) REFERENCES experiment(id)
        );
        CREATE INDEX IF NOT EXISTS idx_mcv_content ON marketing_content_variant(content_id);
        CREATE INDEX IF NOT EXISTS idx_mcv_status ON marketing_content_variant(status);

        -- Approval queue for high-risk posts (Reddit, personalized content)
        CREATE TABLE IF NOT EXISTS marketing_approval_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            variant_id TEXT,
            platform TEXT NOT NULL,
            content_text TEXT NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending', 'approved', 'rejected', 'expired')),
            submitted_at TEXT DEFAULT (datetime('now')),
            reviewed_at TEXT,
            reviewer_note TEXT
        );

        -- Post execution log (dedup + audit trail)
        CREATE TABLE IF NOT EXISTS marketing_post_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            variant_id TEXT,
            platform TEXT NOT NULL,
            platform_post_id TEXT,
            posted_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'posted'
                CHECK(status IN ('posted', 'failed', 'deleted')),
            error TEXT,
            utm_campaign TEXT,
            utm_source TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mpl_content ON marketing_post_log(content_id);
        CREATE INDEX IF NOT EXISTS idx_mpl_platform ON marketing_post_log(platform, posted_at);

        -- Performance metrics (pulled from platform APIs)
        CREATE TABLE IF NOT EXISTS marketing_content_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_log_id INTEGER NOT NULL,
            metric_type TEXT NOT NULL,
            metric_value REAL NOT NULL,
            measured_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (post_log_id) REFERENCES marketing_post_log(id)
        );
        CREATE INDEX IF NOT EXISTS idx_mcm_post ON marketing_content_metrics(post_log_id);

        -- Calendar execution state (dedup)
        CREATE TABLE IF NOT EXISTS marketing_calendar_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calendar_week INTEGER NOT NULL,
            calendar_day INTEGER NOT NULL,
            action_hash TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending', 'queued', 'posted', 'skipped', 'manual')),
            executed_at TEXT,
            notes TEXT
        );

        -- Newsletter subscribers (fallback when Resend audience not configured)
        CREATE TABLE IF NOT EXISTS newsletter_subscriber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            subscribed_at TEXT DEFAULT (datetime('now')),
            unsubscribed_at TEXT
        );

        -- Weekly optimization cycle log
        CREATE TABLE IF NOT EXISTS marketing_optimizer_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            top_performers TEXT,
            patterns_extracted TEXT,
            variants_generated INTEGER DEFAULT 0,
            variants_approved INTEGER DEFAULT 0,
            experiments_proposed INTEGER DEFAULT 0,
            model_used TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()


def _migrate_v120_to_v121(conn):
    """v120->v121: Add experiment_approval_queue for governance of AI-proposed experiments."""
    tables = _table_set(conn)
    if "experiment_approval_queue" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_approval_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                experiment_name TEXT NOT NULL,
                proposed_by TEXT NOT NULL DEFAULT 'daemon',
                proposal_data TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_approval_queue_status
                ON experiment_approval_queue(status);
        """)
    conn.commit()


def _migrate_v121_to_v122(conn):
    """v121->v122: Seed intelligence registry tables (copy, marketing pages, vibe audits, strategy reviews)."""
    import uuid as _uuid

    now = datetime.now(UTC).strftime("%Y-%m-%d")

    # ── 1. pi_copy_registry — register key UI strings for voice audit ──
    copy_entries = [
        ("start_session", "Begin your session", "dashboard CTA", "product_ui"),
        ("empty_state_no_items", "Nothing to review yet. Start a session to begin learning.", "empty review queue", "product_ui"),
        ("placement_intro", "Let's find your level. Answer a few questions and we'll build your study plan.", "placement test intro", "product_ui"),
        ("feedback_prompt", "How did that session feel?", "post-session feedback", "product_ui"),
        ("streak_neutral", "You've studied 3 days this week.", "streak display (no praise inflation)", "product_ui"),
    ]
    for string_key, copy_text, copy_context, surface in copy_entries:
        conn.execute(
            """INSERT OR IGNORE INTO pi_copy_registry
               (id, string_key, copy_text, copy_context, surface, last_updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (str(_uuid.uuid4()), string_key, copy_text, copy_context, surface),
        )

    # ── 2. pi_marketing_pages — register landing pages ──
    marketing_pages = [
        ("landing", "Home", "/", "general learner", "Start learning"),
        ("pricing", "Pricing", "/pricing", "converting visitor", "Choose a plan"),
        ("faq", "FAQ", "/faq", "evaluating visitor", "Start learning"),
        ("hsk-prep", "HSK Prep", "/hsk-prep", "exam-focused learner", "Start HSK prep"),
        ("serious-learner", "For Serious Learners", "/serious-learner", "committed learner", "Start learning"),
        ("vs-duolingo", "Aelu vs Duolingo", "/vs-duolingo", "Duolingo user", "Try Aelu free"),
        ("vs-anki", "Aelu vs Anki", "/vs-anki", "Anki user", "Try Aelu free"),
    ]
    for slug, title, url, audience, cta in marketing_pages:
        conn.execute(
            """INSERT OR IGNORE INTO pi_marketing_pages
               (id, page_slug, page_title, page_url, primary_audience, primary_cta)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(_uuid.uuid4()), slug, title, url, audience, cta),
        )

    # ── 3. pi_vibe_audits — seed recent audit dates to clear "overdue" alerts ──
    audit_categories = [
        "color_palette",
        "typography",
        "motion",
        "dark_mode",
        "sound_design",
    ]
    for category in audit_categories:
        conn.execute(
            """INSERT OR IGNORE INTO pi_vibe_audits
               (id, audit_date, audit_type, audit_category, overall_pass,
                findings_text, auditor)
               VALUES (?, ?, 'scheduled', ?, 1, 'Baseline audit — no issues found.', 'migration_seed')""",
            (str(_uuid.uuid4()), now, category),
        )

    # ── 4. pi_marketing_strategy_reviews — create table + seed strategy review dates ──
    tables = _table_set(conn)
    if "pi_marketing_strategy_reviews" not in tables:
        conn.execute("""
            CREATE TABLE pi_marketing_strategy_reviews (
                id TEXT PRIMARY KEY,
                review_date TEXT NOT NULL,
                strategy_area TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                summary TEXT,
                action_items TEXT,
                reviewer TEXT DEFAULT 'migration_seed',
                next_review_date TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pi_msr_area ON pi_marketing_strategy_reviews(strategy_area)"
        )

    strategy_areas = [
        ("positioning", "Brand positioning and differentiation review"),
        ("audience_segments", "Target audience segments validation"),
        ("content_marketing", "Content marketing pipeline review"),
        ("seo", "SEO strategy and keyword performance review"),
        ("referral", "Referral and word-of-mouth strategy review"),
    ]
    for area, summary in strategy_areas:
        conn.execute(
            """INSERT OR IGNORE INTO pi_marketing_strategy_reviews
               (id, review_date, strategy_area, status, summary, reviewer)
               VALUES (?, ?, ?, 'completed', ?, 'migration_seed')""",
            (str(_uuid.uuid4()), now, area, summary),
        )

    conn.commit()


def _migrate_v122_to_v123(conn):
    """v122->v123: Add content_grammar_link table for Focus on Form linkage.

    Links content items to grammar points by text name with level and example,
    enabling contextual grammar teaching (Focus on Form methodology).
    """
    tables = _table_set(conn)
    if "content_grammar_link" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS content_grammar_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER NOT NULL REFERENCES content_item(id),
                grammar_point TEXT NOT NULL,
                grammar_level INTEGER DEFAULT 1,
                example_sentence TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_cgl_content
                ON content_grammar_link(content_item_id);
            CREATE INDEX IF NOT EXISTS idx_cgl_grammar
                ON content_grammar_link(grammar_point);
        """)
    conn.commit()


def _migrate_v123_to_v124(conn):
    """v123->v124: Add media_shelf table for authentic input channel.

    Stores curated authentic Chinese content (articles, audio, video, podcasts)
    tagged by HSK level for comprehensible input.
    """
    tables = _table_set(conn)
    if "media_shelf" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS media_shelf (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_url TEXT,
                content_type TEXT NOT NULL
                    CHECK (content_type IN ('article', 'audio', 'video', 'podcast')),
                hsk_level INTEGER NOT NULL DEFAULT 3,
                topic TEXT,
                summary TEXT,
                full_text TEXT,
                duration_seconds INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                curated_by TEXT DEFAULT 'system'
            );
            CREATE INDEX IF NOT EXISTS idx_media_shelf_hsk
                ON media_shelf(hsk_level);
            CREATE INDEX IF NOT EXISTS idx_media_shelf_type
                ON media_shelf(content_type);
        """)
    conn.commit()


def _migrate_v124_to_v125(conn):
    """v124->v125: Add free trial and referral columns to user table.

    - trial_ends_at: when the 7-day free trial expires
    - referral_code: unique 8-char code for sharing
    - referred_by: user ID of the referrer
    """
    user_cols = _col_set(conn, "user")
    if "trial_ends_at" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN trial_ends_at TEXT")
    if "referral_code" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN referral_code TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_referral_code ON user(referral_code)")
    if "referred_by" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN referred_by INTEGER REFERENCES user(id)")
    # Backfill referral codes for existing users that don't have one
    import secrets as _secrets
    rows = conn.execute("SELECT id FROM user WHERE referral_code IS NULL").fetchall()
    for row in rows:
        code = _secrets.token_urlsafe(6)[:8]
        try:
            conn.execute("UPDATE user SET referral_code = ? WHERE id = ?", (code, row["id"]))
        except Exception:
            # Collision — retry with a different code
            code = _secrets.token_urlsafe(6)[:8]
            try:
                conn.execute("UPDATE user SET referral_code = ? WHERE id = ?", (code, row["id"]))
            except Exception:
                pass
    conn.commit()


def _migrate_v125_to_v126(conn):
    """v125->v126: Add modality_history JSON column to progress table.

    Tracks when each modality was last drilled for an item, enabling
    cross-modal transfer scheduling (FMEA: items stuck in single modality).
    Format: JSON object mapping drill_type -> ISO date of last practice.
    e.g. {"mc": "2026-03-20", "ime_type": "2026-03-22", "listening_gist": "2026-03-25"}
    """
    progress_cols = _col_set(conn, "progress")
    if "modality_history" not in progress_cols:
        conn.execute("ALTER TABLE progress ADD COLUMN modality_history TEXT DEFAULT '{}'")
        conn.commit()


def _migrate_v126_to_v127(conn):
    """v126->v127: Promote project owner to admin.

    Ensures the primary developer account has admin access when MFA is enabled.
    """
    conn.execute(
        "UPDATE user SET is_admin = 1 WHERE email = 'jason.gerson@gmail.com'"
    )
    conn.commit()


def _migrate_v127_to_v128(conn):
    """v127->v128: Lean Six Sigma A+ tables — NPS, Andon, tollgate, email quality, LLM quality."""
    tables = _table_set(conn)
    if "nps_response" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS nps_response (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                score INTEGER CHECK (score BETWEEN 0 AND 10),
                feedback TEXT,
                responded_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE INDEX IF NOT EXISTS idx_nps_user ON nps_response(user_id);
            CREATE INDEX IF NOT EXISTS idx_nps_date ON nps_response(responded_at);
        """)
    if "andon_event" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS andon_event (
                id INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
                summary TEXT NOT NULL,
                details TEXT,
                fired_at TEXT DEFAULT (datetime('now')),
                acknowledged_at TEXT,
                acknowledged_by INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_andon_date ON andon_event(fired_at);
        """)
    if "pi_tollgate_review" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pi_tollgate_review (
                id INTEGER PRIMARY KEY,
                dmaic_id INTEGER,
                phase TEXT CHECK (phase IN ('define', 'measure', 'analyze', 'improve', 'control')),
                decision TEXT CHECK (decision IN ('go', 'conditional_go', 'no_go')),
                reviewed_at TEXT DEFAULT (datetime('now')),
                notes TEXT,
                FOREIGN KEY (dmaic_id) REFERENCES pi_dmaic_log(id)
            );
        """)
    if "email_send_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_send_log (
                id INTEGER PRIMARY KEY,
                email_type TEXT,
                user_id INTEGER,
                resend_message_id TEXT,
                sent_at TEXT DEFAULT (datetime('now')),
                delivered_at TEXT,
                opened_at TEXT,
                clicked_at TEXT,
                converted_at TEXT,
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE INDEX IF NOT EXISTS idx_email_log_type ON email_send_log(email_type);
        """)
    if "llm_output_quality" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS llm_output_quality (
                id INTEGER PRIMARY KEY,
                content_item_id INTEGER,
                llm_model TEXT,
                metric_type TEXT CHECK (metric_type IN ('authenticity', 'grammatical_correctness', 'pedagogical_fit')),
                score REAL,
                evaluated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (content_item_id) REFERENCES content_item(id)
            );
            CREATE INDEX IF NOT EXISTS idx_llm_quality_item ON llm_output_quality(content_item_id);
        """)
    conn.commit()


def _migrate_v128_to_v129(conn):
    """v128->v129: Kanban A+ — per-class WIP config, due dates, blocked time, notifications."""
    tables = _table_set(conn)
    cols = _col_set(conn, "work_item") if "work_item" in tables else set()

    # Add due_date to work_item
    if "due_date" not in cols:
        conn.execute("ALTER TABLE work_item ADD COLUMN due_date TEXT")

    # Add total_blocked_hours to work_item
    if "total_blocked_hours" not in cols:
        conn.execute(
            "ALTER TABLE work_item ADD COLUMN total_blocked_hours REAL DEFAULT 0"
        )

    # Kanban config table with per-service-class WIP limits
    if "kanban_config" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kanban_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_class TEXT NOT NULL UNIQUE,
                wip_limit INTEGER NOT NULL DEFAULT 3,
                target_cycle_hours REAL,
                max_cycle_hours REAL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT OR IGNORE INTO kanban_config (service_class, wip_limit, target_cycle_hours, max_cycle_hours)
            VALUES
                ('expedite', 1, 24, 48),
                ('fixed_date', 2, 72, 168),
                ('standard', 3, 168, 336),
                ('intangible', 2, 336, 672);
        """)

    # Kanban notification table
    if "kanban_notification" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kanban_notification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_item_id INTEGER,
                notification_type TEXT NOT NULL,
                message TEXT NOT NULL,
                read_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (work_item_id) REFERENCES work_item(id)
            );
            CREATE INDEX IF NOT EXISTS idx_kanban_notif_unread
                ON kanban_notification(read_at) WHERE read_at IS NULL;
        """)
    conn.commit()


def _migrate_v129_to_v130(conn):
    """v129->v130: A/B testing A+ — subgroup results, causal DAGs, metric hierarchy."""
    tables = _table_set(conn)

    # Experiment subgroup results (heterogeneous treatment effects)
    if "experiment_subgroup_result" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_subgroup_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                subgroup_variable TEXT NOT NULL,
                subgroup_level TEXT NOT NULL,
                effect_size REAL,
                ci_lower REAL,
                ci_upper REAL,
                p_value REAL,
                n_treatment INTEGER,
                n_control INTEGER,
                analyzed_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            );
            CREATE INDEX IF NOT EXISTS idx_subgroup_exp
                ON experiment_subgroup_result(experiment_id);
        """)

    # Causal DAG documentation
    if "experiment_causal_dag" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_causal_dag (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER,
                dag_json TEXT NOT NULL,
                confounders TEXT,
                documented_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (experiment_id) REFERENCES experiment(id)
            );
        """)

    # Add metric_hierarchy to experiment table
    if "experiment" in tables:
        cols = _col_set(conn, "experiment")
        if "metric_hierarchy" not in cols:
            conn.execute(
                "ALTER TABLE experiment ADD COLUMN metric_hierarchy TEXT"
            )

    conn.commit()


def _migrate_v130_to_v131(conn):
    """v130->v131: Learning science A+ — FSRS columns, confusables, prerequisites, metacognition."""
    tables = _table_set(conn)

    # FSRS columns on progress table
    if "progress" in tables:
        cols = _col_set(conn, "progress")
        if "fsrs_stability" not in cols:
            conn.execute("ALTER TABLE progress ADD COLUMN fsrs_stability REAL")
        if "fsrs_difficulty" not in cols:
            conn.execute("ALTER TABLE progress ADD COLUMN fsrs_difficulty REAL")

    # Confusable pairs table
    if "confusable_pair" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS confusable_pair (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_a_id INTEGER NOT NULL,
                item_b_id INTEGER NOT NULL,
                confusable_type TEXT NOT NULL,
                similarity_score REAL DEFAULT 0.5,
                detected_at TEXT DEFAULT (datetime('now')),
                UNIQUE(item_a_id, item_b_id, confusable_type)
            );
            CREATE INDEX IF NOT EXISTS idx_confusable_a ON confusable_pair(item_a_id);
            CREATE INDEX IF NOT EXISTS idx_confusable_b ON confusable_pair(item_b_id);
        """)

    # Prerequisite edges table
    if "prerequisite_edge" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prerequisite_edge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                prerequisite_id INTEGER NOT NULL,
                edge_type TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(item_id, prerequisite_id, edge_type)
            );
            CREATE INDEX IF NOT EXISTS idx_prereq_item ON prerequisite_edge(item_id);
            CREATE INDEX IF NOT EXISTS idx_prereq_dep ON prerequisite_edge(prerequisite_id);
        """)

    # Calibration snapshot table
    if "calibration_snapshot" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS calibration_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                confidence_level TEXT NOT NULL,
                predicted_rate REAL,
                actual_rate REAL,
                n_items INTEGER,
                brier_score REAL,
                snapshot_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE INDEX IF NOT EXISTS idx_calibration_user ON calibration_snapshot(user_id);
        """)

    # Reflection log table
    if "reflection_log" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reflection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id INTEGER,
                prompt TEXT NOT NULL,
                response TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
        """)

    # Adaptive listening columns on user table
    if "user" in tables:
        cols = _col_set(conn, "user")
        if "listening_speed" not in cols:
            conn.execute(
                "ALTER TABLE user ADD COLUMN listening_speed REAL DEFAULT 1.0"
            )
        if "max_replays" not in cols:
            conn.execute(
                "ALTER TABLE user ADD COLUMN max_replays INTEGER DEFAULT 5"
            )

    conn.commit()


def _migrate_v131_to_v132(conn):
    """v131->v132: Goodhart A+ — alert outcomes, pending actions, session distortion, validation flag."""
    tables = _table_set(conn)

    # Alert outcome tracking (counter-metric self-validation)
    if "counter_metric_alert_outcome" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS counter_metric_alert_outcome (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                alert_severity TEXT,
                action_taken TEXT,
                metric_before REAL,
                metric_after REAL,
                improved INTEGER,
                evaluated_at TEXT DEFAULT (datetime('now')),
                action_log_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_alert_outcome_metric
                ON counter_metric_alert_outcome(metric_name);
        """)

    # Pending actions requiring admin approval
    if "counter_metric_pending_action" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS counter_metric_pending_action (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_details TEXT,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
                created_at TEXT DEFAULT (datetime('now')),
                decided_at TEXT,
                decided_by INTEGER
            );
        """)

    # Session distortion flags
    if "session_log" in tables:
        cols = _col_set(conn, "session_log")
        if "distortion_flags" not in cols:
            conn.execute(
                "ALTER TABLE session_log ADD COLUMN distortion_flags TEXT"
            )

    # Validation failed flag on progress
    if "progress" in tables:
        cols = _col_set(conn, "progress")
        if "validation_failed" not in cols:
            conn.execute(
                "ALTER TABLE progress ADD COLUMN validation_failed INTEGER DEFAULT 0"
            )

    conn.commit()


def _migrate_v132_to_v133(conn):
    """v132->v133: Statistics A+ — IRT columns, learner segmentation."""
    tables = _table_set(conn)

    # IRT columns on content_item
    if "content_item" in tables:
        cols = _col_set(conn, "content_item")
        if "irt_difficulty" not in cols:
            conn.execute("ALTER TABLE content_item ADD COLUMN irt_difficulty REAL")
        if "irt_discrimination" not in cols:
            conn.execute("ALTER TABLE content_item ADD COLUMN irt_discrimination REAL")
        if "irt_fit_infit" not in cols:
            conn.execute("ALTER TABLE content_item ADD COLUMN irt_fit_infit REAL")
        if "irt_fit_outfit" not in cols:
            conn.execute("ALTER TABLE content_item ADD COLUMN irt_fit_outfit REAL")

    # IRT ability on user
    if "user" in tables:
        cols = _col_set(conn, "user")
        if "irt_ability" not in cols:
            conn.execute("ALTER TABLE user ADD COLUMN irt_ability REAL")
        if "irt_ability_se" not in cols:
            conn.execute("ALTER TABLE user ADD COLUMN irt_ability_se REAL")
        if "learner_segment" not in cols:
            conn.execute("ALTER TABLE user ADD COLUMN learner_segment TEXT")

    conn.commit()


def _migrate_v133_to_v134(conn: sqlite3.Connection) -> None:
    """v133->v134: Fix NULL NOT-NULL lens columns from ALTER TABLE ADD COLUMN migrations.

    SQLite 3.37+ integrity_check flags NOT NULL violations in physical storage for
    columns added via ALTER TABLE ADD COLUMN on existing rows. The bootstrap learner
    profile row may have NULL stored for these lens columns even though the schema
    records a DEFAULT. This migration back-fills them to their intended defaults.
    """
    cols = _col_set(conn, "learner_profile")
    lens_defaults = {
        "lens_quiet_observation": 0.7,
        "lens_institutions": 0.7,
        "lens_urban_texture": 0.7,
        "lens_humane_mystery": 0.7,
        "lens_identity": 0.7,
        "lens_comedy": 0.7,
        "lens_food": 0.5,
        "lens_travel": 0.5,
        "lens_explainers": 0.5,
        "lens_wit": 0.7,
        "lens_ensemble_comedy": 0.7,
        "lens_sharp_observation": 0.7,
        "lens_satire": 0.7,
        "lens_moral_texture": 0.7,
    }
    # Use unconditional COALESCE rather than WHERE col IS NULL.
    # Columns added via ALTER TABLE ADD COLUMN have no physical storage for
    # existing rows; SQLite returns the DEFAULT for reads, so "IS NULL" never
    # matches them — but PRAGMA integrity_check still flags the absent bytes as
    # a NOT NULL violation.  COALESCE forces a physical write while preserving
    # any real user-set values.
    for col, default in lens_defaults.items():
        if col in cols:
            conn.execute(
                f"UPDATE learner_profile SET {col} = COALESCE({col}, ?)",
                (default,),
            )
    conn.commit()


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
    20: _migrate_v20_to_v21,
    21: _migrate_v21_to_v22,
    22: _migrate_v22_to_v23,
    23: _migrate_v23_to_v24,
    24: _migrate_v24_to_v25,
    25: _migrate_v25_to_v26,
    26: _migrate_v26_to_v27,
    27: _migrate_v27_to_v28,
    28: _migrate_v28_to_v29,
    29: _migrate_v29_to_v30,
    30: _migrate_v30_to_v31,
    31: _migrate_v31_to_v32,
    32: _migrate_v32_to_v33,
    33: _migrate_v33_to_v34,
    34: _migrate_v34_to_v35,
    35: _migrate_v35_to_v36,
    36: _migrate_v36_to_v37,
    37: _migrate_v37_to_v38,
    38: _migrate_v38_to_v39,
    39: _migrate_v39_to_v40,
    40: _migrate_v40_to_v41,
    41: _migrate_v41_to_v42,
    42: _migrate_v42_to_v43,
    43: _migrate_v43_to_v44,
    44: _migrate_v44_to_v45,
    45: _migrate_v45_to_v46,
    46: _migrate_v46_to_v47,
    47: _migrate_v47_to_v48,
    48: _migrate_v48_to_v49,
    49: _migrate_v49_to_v50,
    50: _migrate_v50_to_v51,
    51: _migrate_v51_to_v52,
    52: _migrate_v52_to_v53,
    53: _migrate_v53_to_v54,
    54: _migrate_v54_to_v55,
    55: _migrate_v55_to_v56,
    56: _migrate_v56_to_v57,
    57: _migrate_v57_to_v58,
    58: _migrate_v58_to_v59,
    59: _migrate_v59_to_v60,
    60: _migrate_v60_to_v61,
    61: _migrate_v61_to_v62,
    62: _migrate_v62_to_v63,
    63: _migrate_v63_to_v64,
    64: _migrate_v64_to_v65,
    65: _migrate_v65_to_v66,
    66: _migrate_v66_to_v67,
    67: _migrate_v67_to_v68,
    68: _migrate_v68_to_v69,
    69: _migrate_v69_to_v70,
    70: _migrate_v70_to_v71,
    71: _migrate_v71_to_v72,
    72: _migrate_v72_to_v73,
    73: _migrate_v73_to_v74,
    74: _migrate_v74_to_v75,
    75: _migrate_v75_to_v76,
    76: _migrate_v76_to_v77,
    77: _migrate_v77_to_v78,
    78: _migrate_v78_to_v79,
    79: _migrate_v79_to_v80,
    80: _migrate_v80_to_v81,
    81: _migrate_v81_to_v82,
    82: _migrate_v82_to_v83,
    83: _migrate_v83_to_v84,
    84: _migrate_v84_to_v85,
    85: _migrate_v85_to_v86,
    86: _migrate_v86_to_v87,
    87: _migrate_v87_to_v88,
    88: _migrate_v88_to_v89,
    89: _migrate_v89_to_v90,
    90: _migrate_v90_to_v91,
    91: _migrate_v91_to_v92,
    92: _migrate_v92_to_v93,
    93: _migrate_v93_to_v94,
    94: _migrate_v94_to_v95,
    95: _migrate_v95_to_v96,
    96: _migrate_v96_to_v97,
    97: _migrate_v97_to_v98,
    98: _migrate_v98_to_v99,
    99: _migrate_v99_to_v100,
    100: _migrate_v100_to_v101,
    101: _migrate_v101_to_v102,
    102: _migrate_v102_to_v103,
    103: _migrate_v103_to_v104,
    104: _migrate_v104_to_v105,
    105: _migrate_v105_to_v106,
    106: _migrate_v106_to_v107,
    107: _migrate_v107_to_v108,
    108: _migrate_v108_to_v109,
    109: _migrate_v109_to_v110,
    110: _migrate_v110_to_v111,
    111: _migrate_v111_to_v112,
    112: _migrate_v112_to_v113,
    113: _migrate_v113_to_v114,
    114: _migrate_v114_to_v115,
    115: _migrate_v115_to_v116,
    116: _migrate_v116_to_v117,
    117: _migrate_v117_to_v118,
    118: _migrate_v118_to_v119,
    119: _migrate_v119_to_v120,
    120: _migrate_v120_to_v121,
    121: _migrate_v121_to_v122,
    122: _migrate_v122_to_v123,
    123: _migrate_v123_to_v124,
    124: _migrate_v124_to_v125,
    125: _migrate_v125_to_v126,
    126: _migrate_v126_to_v127,
    127: _migrate_v127_to_v128,
    128: _migrate_v128_to_v129,
    129: _migrate_v129_to_v130,
    130: _migrate_v130_to_v131,
    131: _migrate_v131_to_v132,
    132: _migrate_v132_to_v133,
    133: _migrate_v133_to_v134,
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
