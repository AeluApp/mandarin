"""Tests for Doc 16: Learner Model and Personalization Engine."""

import sqlite3
import pytest

from mandarin.ai.learner_model import (
    update_pattern_state_from_review,
    _upsert_pattern_state,
    _compute_pattern_status,
    update_pattern_avg_stability,
    estimate_proficiency_zones,
    _estimate_vocab_zone,
    _estimate_grammar_zone,
    _estimate_listening_zone,
    _compute_composite_hsk,
    get_learner_model_context,
    get_student_insight_for_teacher,
    _generate_teaching_priorities,
    analyze_learner_model,
)


def _make_db():
    """Create an in-memory DB with Doc 16 schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT);
        INSERT INTO user (id, username) VALUES (1, 'test');

        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            item_type TEXT DEFAULT 'vocab',
            hsk_level INTEGER,
            content_lens TEXT,
            status TEXT DEFAULT 'drill_ready',
            difficulty REAL DEFAULT 0.5,
            times_shown INTEGER DEFAULT 0,
            times_correct INTEGER DEFAULT 0,
            is_mined_out INTEGER DEFAULT 0
        );

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

        CREATE TABLE content_grammar (
            content_item_id INTEGER NOT NULL,
            grammar_point_id INTEGER NOT NULL,
            PRIMARY KEY (content_item_id, grammar_point_id)
        );

        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE review_event (
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
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE memory_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            content_item_id INTEGER NOT NULL,
            stability REAL NOT NULL DEFAULT 1.0,
            retrievability REAL NOT NULL DEFAULT 0.0,
            difficulty REAL NOT NULL DEFAULT 0.5,
            state TEXT NOT NULL DEFAULT 'new',
            last_reviewed_at TEXT,
            next_review_due TEXT NOT NULL DEFAULT (datetime('now')),
            scheduled_days INTEGER NOT NULL DEFAULT 1,
            reps INTEGER NOT NULL DEFAULT 0,
            lapses INTEGER NOT NULL DEFAULT 0,
            encoding_quality TEXT DEFAULT 'unknown',
            UNIQUE(user_id, content_item_id)
        );

        CREATE TABLE learner_pattern_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            grammar_point_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'untouched',
            encounters INTEGER NOT NULL DEFAULT 0,
            correct_streak INTEGER NOT NULL DEFAULT 0,
            error_count_30d INTEGER NOT NULL DEFAULT 0,
            avg_stability REAL,
            first_encountered_at TEXT,
            last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, grammar_point_id)
        );

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
            reading_confidence TEXT DEFAULT 'insufficient_data',
            listening_hsk_estimate REAL,
            listening_confidence TEXT DEFAULT 'insufficient_data',
            production_hsk_estimate REAL,
            production_confidence TEXT DEFAULT 'insufficient_data',
            composite_hsk_estimate REAL,
            computed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE learner_model_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            snapshot TEXT NOT NULL,
            generated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    return conn


def _seed_items_and_grammar(conn):
    """Seed content items and grammar points with linkage."""
    # Grammar points
    conn.execute(
        "INSERT INTO grammar_point (id, name, hsk_level, category) VALUES (1, 'le_completion', 2, 'aspect')"
    )
    conn.execute(
        "INSERT INTO grammar_point (id, name, hsk_level, category) VALUES (2, 'ba_disposal', 3, 'structure')"
    )
    conn.execute(
        "INSERT INTO grammar_point (id, name, hsk_level, category) VALUES (3, 'de_structural', 1, 'particle')"
    )

    # Content items
    for i in range(1, 11):
        hsk = 1 if i <= 4 else (2 if i <= 7 else 3)
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?,?,?,?)",
            (f"字{i}", f"zi{i}", f"word{i}", hsk),
        )

    # Link items to grammar points
    conn.execute("INSERT INTO content_grammar VALUES (1, 1)")  # item 1 → le_completion
    conn.execute("INSERT INTO content_grammar VALUES (2, 1)")  # item 2 → le_completion
    conn.execute("INSERT INTO content_grammar VALUES (3, 2)")  # item 3 → ba_disposal
    conn.execute("INSERT INTO content_grammar VALUES (4, 3)")  # item 4 → de_structural

    conn.commit()


# ─────────────────────────────────────────────
# PATTERN STATE TESTS
# ─────────────────────────────────────────────


class TestPatternState:
    def test_first_encounter_creates_state(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        _upsert_pattern_state(conn, 1, 1, True)
        row = conn.execute(
            "SELECT * FROM learner_pattern_states WHERE grammar_point_id=1"
        ).fetchone()
        assert row is not None
        assert row["status"] == "introduced"
        assert row["encounters"] == 1
        assert row["correct_streak"] == 1

    def test_correct_increments_streak(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        _upsert_pattern_state(conn, 1, 1, True)
        _upsert_pattern_state(conn, 1, 1, True)
        row = conn.execute(
            "SELECT * FROM learner_pattern_states WHERE grammar_point_id=1"
        ).fetchone()
        assert row["correct_streak"] == 2
        assert row["encounters"] == 2

    def test_error_resets_streak(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        _upsert_pattern_state(conn, 1, 1, True)
        _upsert_pattern_state(conn, 1, 1, True)
        _upsert_pattern_state(conn, 1, 1, False)
        row = conn.execute(
            "SELECT * FROM learner_pattern_states WHERE grammar_point_id=1"
        ).fetchone()
        assert row["correct_streak"] == 0
        assert row["encounters"] == 3

    def test_review_links_through_content_grammar(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        # Review item 1, which is linked to grammar_point 1 (le_completion)
        update_pattern_state_from_review(conn, 1, 1, True)
        row = conn.execute(
            "SELECT * FROM learner_pattern_states WHERE grammar_point_id=1"
        ).fetchone()
        assert row is not None
        assert row["encounters"] == 1

    def test_no_grammar_link_is_noop(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        # Item 5 has no grammar link
        update_pattern_state_from_review(conn, 1, 5, True)
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM learner_pattern_states"
        ).fetchone()["cnt"]
        assert count == 0


# ─────────────────────────────────────────────
# PATTERN STATUS COMPUTATION
# ─────────────────────────────────────────────


class TestPatternStatusComputation:
    def test_introduced_under_3_encounters(self):
        assert _compute_pattern_status("introduced", 2, 2, 0) == "introduced"

    def test_acquiring_on_high_errors(self):
        assert _compute_pattern_status("introduced", 1, 10, 5) == "acquiring"

    def test_consolidating(self):
        assert _compute_pattern_status("acquiring", 3, 10, 1) == "consolidating"

    def test_mastered(self):
        assert _compute_pattern_status("consolidating", 5, 20, 0) == "mastered"

    def test_mastered_requires_20_encounters(self):
        # 5 streak, 0 errors, but only 10 encounters — not mastered
        assert _compute_pattern_status("consolidating", 5, 10, 0) == "consolidating"

    def test_status_transitions_full_path(self):
        """untouched → introduced → acquiring → consolidating → mastered"""
        s = "introduced"
        s = _compute_pattern_status(s, 1, 5, 4)
        assert s == "acquiring"
        s = _compute_pattern_status(s, 3, 10, 1)
        assert s == "consolidating"
        s = _compute_pattern_status(s, 5, 20, 0)
        assert s == "mastered"


# ─────────────────────────────────────────────
# PROFICIENCY ZONE TESTS
# ─────────────────────────────────────────────


class TestProficiencyZones:
    def test_no_data_returns_zero(self):
        conn = _make_db()
        result = estimate_proficiency_zones(conn, user_id=1)
        assert result["composite_hsk"] == 0.0
        assert result["vocab"]["hsk_estimate"] == 0.0

    def test_vocab_zone_with_mastered_items(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        # Master all HSK 1 items (items 1-4)
        for i in range(1, 5):
            conn.execute("""
                INSERT INTO memory_states
                (user_id, content_item_id, state, stability, reps)
                VALUES (1, ?, 'review', 25.0, 10)
            """, (i,))
        conn.commit()

        vocab = _estimate_vocab_zone(conn, 1)
        assert vocab["items_mastered"] == 4
        assert vocab["hsk_estimate"] >= 1.0

    def test_grammar_zone_with_mastered_patterns(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        # Master the HSK 1 grammar point
        conn.execute("""
            INSERT INTO learner_pattern_states
            (user_id, grammar_point_id, status, encounters)
            VALUES (1, 3, 'mastered', 25)
        """)
        conn.commit()

        grammar = _estimate_grammar_zone(conn, 1)
        assert grammar["patterns_mastered"] == 1

    def test_listening_zone_insufficient_data(self):
        conn = _make_db()
        result = _estimate_listening_zone(conn, 1)
        assert result["confidence"] == "insufficient_data"

    def test_composite_weights(self):
        vocab = {"hsk_estimate": 2.0}
        grammar = {"hsk_estimate": 1.0}
        listening = {"hsk_estimate": None}

        composite = _compute_composite_hsk(vocab, grammar, listening)
        # vocab=2.0*0.5 + grammar=1.0*0.35 = 1.35 / 0.85 ≈ 1.6
        expected = round((2.0 * 0.5 + 1.0 * 0.35) / (0.5 + 0.35), 1)
        assert composite == expected

    def test_estimate_persists_to_db(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        estimate_proficiency_zones(conn, user_id=1)
        row = conn.execute(
            "SELECT * FROM learner_proficiency_zones WHERE user_id=1"
        ).fetchone()
        assert row is not None

    def test_estimate_updates_existing(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        estimate_proficiency_zones(conn, user_id=1)
        estimate_proficiency_zones(conn, user_id=1)  # Second call should update
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM learner_proficiency_zones WHERE user_id=1"
        ).fetchone()["cnt"]
        assert count == 1


# ─────────────────────────────────────────────
# LEARNER MODEL CONTEXT
# ─────────────────────────────────────────────


class TestLearnerModelContext:
    def test_returns_required_keys(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        context = get_learner_model_context(conn, user_id=1)
        assert "composite_hsk" in context
        assert "vocab_hsk" in context
        assert "grammar_hsk" in context
        assert "mastered_patterns" in context
        assert "active_patterns" in context

    def test_caches_snapshot(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        get_learner_model_context(conn, user_id=1)
        row = conn.execute(
            "SELECT * FROM learner_model_snapshots WHERE user_id=1"
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────
# TEACHER INSIGHT
# ─────────────────────────────────────────────


class TestTeacherInsight:
    def test_returns_teaching_priorities(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        result = get_student_insight_for_teacher(conn, student_user_id=1)
        assert "teaching_priorities" in result
        assert isinstance(result["teaching_priorities"], list)

    def test_priorities_from_struggles(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        conn.execute("""
            INSERT INTO learner_pattern_states
            (user_id, grammar_point_id, status, encounters, error_count_30d, correct_streak)
            VALUES (1, 1, 'acquiring', 10, 5, 0)
        """)
        conn.commit()

        result = get_student_insight_for_teacher(conn, student_user_id=1)
        assert len(result["grammar_struggles"]) == 1
        assert result["grammar_struggles"][0]["pattern"] == "le_completion"
        assert len(result["teaching_priorities"]) >= 1

    def test_vocabulary_struggles_use_lapse_rate(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        conn.execute("""
            INSERT INTO memory_states
            (user_id, content_item_id, state, reps, lapses, stability)
            VALUES (1, 1, 'review', 10, 5, 2.0)
        """)
        conn.commit()

        result = get_student_insight_for_teacher(conn, student_user_id=1)
        assert len(result["vocabulary_struggles"]) == 1
        assert result["vocabulary_struggles"][0]["lapse_rate"] == 50


# ─────────────────────────────────────────────
# GENERATE TEACHING PRIORITIES
# ─────────────────────────────────────────────


class TestTeachingPriorities:
    def test_generates_from_struggles(self):
        struggles = [
            {"name": "le_completion", "category": "aspect",
             "error_count_30d": 5, "encounters": 10},
        ]
        priorities = _generate_teaching_priorities(struggles)
        assert len(priorities) == 1
        assert "le_completion" in priorities[0]

    def test_empty_with_no_struggles(self):
        assert _generate_teaching_priorities([]) == []


# ─────────────────────────────────────────────
# AVG STABILITY UPDATE
# ─────────────────────────────────────────────


class TestAvgStability:
    def test_computes_from_linked_items(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        # Create pattern state and memory states for linked items
        conn.execute("""
            INSERT INTO learner_pattern_states
            (user_id, grammar_point_id, status, encounters)
            VALUES (1, 1, 'acquiring', 5)
        """)
        # Items 1 and 2 are linked to grammar_point 1
        conn.execute("""
            INSERT INTO memory_states
            (user_id, content_item_id, stability, reps, state)
            VALUES (1, 1, 10.0, 5, 'review')
        """)
        conn.execute("""
            INSERT INTO memory_states
            (user_id, content_item_id, stability, reps, state)
            VALUES (1, 2, 20.0, 5, 'review')
        """)
        conn.commit()

        update_pattern_avg_stability(conn, 1, 1)
        row = conn.execute(
            "SELECT avg_stability FROM learner_pattern_states WHERE grammar_point_id=1"
        ).fetchone()
        assert row["avg_stability"] == 15.0  # (10+20)/2


# ─────────────────────────────────────────────
# ANALYZER TESTS
# ─────────────────────────────────────────────


class TestAnalyzer:
    def test_stale_pattern_finding(self):
        conn = _make_db()
        _seed_items_and_grammar(conn)
        conn.execute("""
            INSERT INTO learner_pattern_states
            (user_id, grammar_point_id, status, encounters, last_updated_at)
            VALUES (1, 1, 'acquiring', 5, datetime('now', '-10 days'))
        """)
        conn.commit()

        findings = analyze_learner_model(conn)
        stale = [f for f in findings if "stale" in f["title"].lower()]
        assert len(stale) == 1

    def test_untagged_grammar_finding(self):
        conn = _make_db()
        # Grammar point with no content_grammar links
        conn.execute(
            "INSERT INTO grammar_point (name, hsk_level, category) VALUES ('orphan_pattern', 2, 'aspect')"
        )
        conn.commit()

        findings = analyze_learner_model(conn)
        untagged = [f for f in findings if "no items tagged" in f["title"].lower()]
        assert len(untagged) == 1

    def test_no_findings_when_healthy(self):
        conn = _make_db()
        findings = analyze_learner_model(conn)
        assert findings == []


# ─────────────────────────────────────────────
# SCHEMA MIGRATION TEST
# ─────────────────────────────────────────────


class TestSchemaMigration:
    def test_migration_creates_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE content_item (id INTEGER PRIMARY KEY);
            CREATE TABLE grammar_point (id INTEGER PRIMARY KEY);
            CREATE TABLE session_log (id INTEGER PRIMARY KEY);
            CREATE TABLE user (id INTEGER PRIMARY KEY);
        """)

        from mandarin.db.core import _migrate_v74_to_v75
        _migrate_v74_to_v75(conn)

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "learner_pattern_states" in tables
        assert "learner_proficiency_zones" in tables
        assert "learner_model_snapshots" in tables

    def test_migration_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE content_item (id INTEGER PRIMARY KEY);
            CREATE TABLE grammar_point (id INTEGER PRIMARY KEY);
            CREATE TABLE session_log (id INTEGER PRIMARY KEY);
            CREATE TABLE user (id INTEGER PRIMARY KEY);
        """)

        from mandarin.db.core import _migrate_v74_to_v75
        _migrate_v74_to_v75(conn)
        _migrate_v74_to_v75(conn)  # Should not error
