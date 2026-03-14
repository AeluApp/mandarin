"""Tests for mandarin.intelligence.analyzers_domain — 8 domain-specific analyzers.

Each analyzer accepts a SQLite connection and returns a list of finding dicts.
Tests use an in-memory SQLite database to avoid touching the real DB.
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

from mandarin.intelligence.analyzers_domain import (
    analyze_srs_funnel,
    analyze_error_taxonomy,
    analyze_cross_modality_transfer,
    analyze_curriculum_coverage,
    analyze_hsk_cliff,
    analyze_tone_phonology,
    analyze_scheduler_decisions,
    analyze_encounter_feedback_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn():
    """Create a minimal in-memory SQLite connection with row_factory set."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _ago(days: int) -> str:
    """Return ISO datetime string for N days ago (UTC)."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _assert_finding_shape(finding: dict) -> None:
    """All findings must carry the standard keys."""
    for key in ("dimension", "severity", "title", "analysis", "recommendation",
                "claude_prompt", "impact", "files"):
        assert key in finding, f"Finding missing key '{key}': {finding}"


# ---------------------------------------------------------------------------
# 1. analyze_srs_funnel
# ---------------------------------------------------------------------------

@pytest.fixture
def srs_conn():
    conn = _make_conn()
    conn.execute("""
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER,
            user_id INTEGER DEFAULT 1,
            modality TEXT DEFAULT 'reading',
            mastery_stage TEXT DEFAULT 'seen',
            updated_at TEXT,
            weak_cycle_count INTEGER DEFAULT 0,
            historically_weak INTEGER DEFAULT 0,
            repetitions INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            interval_days REAL DEFAULT 1.0
        )
    """)
    conn.commit()
    return conn


def test_srs_funnel_empty_returns_no_findings(srs_conn):
    """With no progress rows the analyzer returns nothing (no stages to evaluate)."""
    findings = analyze_srs_funnel(srs_conn)
    assert findings == []


def test_srs_funnel_stuck_stabilizing_triggers_high(srs_conn):
    """Majority of items stuck at stabilizing >14 days triggers high finding."""
    # Insert 8 items stuck at stabilizing for 20 days, 2 at other stages
    for i in range(8):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at) VALUES (?,?,?)",
            (i + 1, "stabilizing", _ago(20)),
        )
    for i in range(2):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at) VALUES (?,?,?)",
            (100 + i, "stable", _ago(1)),
        )
    srs_conn.commit()

    findings = analyze_srs_funnel(srs_conn)
    titles = [f["title"] for f in findings]
    assert any("stuck" in t.lower() or "stabilizing" in t.lower() for t in titles), (
        f"Expected a stuck-stabilizing finding; got: {titles}"
    )
    stuck = [f for f in findings if "stabilizing" in f["title"]]
    assert stuck[0]["severity"] == "high"
    for f in findings:
        _assert_finding_shape(f)


def test_srs_funnel_stuck_stabilizing_below_threshold_no_finding(srs_conn):
    """Fewer than 50% stuck at stabilizing should not trigger the finding."""
    # 3 stuck, 7 at stable — 30% < 50% threshold
    for i in range(3):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at) VALUES (?,?,?)",
            (i + 1, "stabilizing", _ago(20)),
        )
    for i in range(7):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at) VALUES (?,?,?)",
            (100 + i, "stable", _ago(1)),
        )
    srs_conn.commit()

    findings = analyze_srs_funnel(srs_conn)
    stuck = [f for f in findings if "stabilizing" in f.get("title", "")]
    assert stuck == [], f"Should not fire when <50% stuck; got: {stuck}"


def test_srs_funnel_regressions_trigger_medium(srs_conn):
    """Items with weak_cycle_count > 0, early stage, and many reps trigger medium finding."""
    # 6 regressed items (> threshold of 5)
    for i in range(6):
        srs_conn.execute("""
            INSERT INTO progress
                (content_item_id, mastery_stage, updated_at, weak_cycle_count, repetitions)
            VALUES (?,?,?,?,?)
        """, (i + 1, "learning", _ago(1), 2, 15))
    srs_conn.commit()

    findings = analyze_srs_funnel(srs_conn)
    reg = [f for f in findings if "regressed" in f["title"].lower()]
    assert reg, "Expected a regression finding"
    assert reg[0]["severity"] == "medium"
    for f in findings:
        _assert_finding_shape(f)


def test_srs_funnel_regressions_at_threshold_no_finding(srs_conn):
    """Exactly 5 or fewer regressions should not trigger."""
    for i in range(5):
        srs_conn.execute("""
            INSERT INTO progress
                (content_item_id, mastery_stage, updated_at, weak_cycle_count, repetitions)
            VALUES (?,?,?,?,?)
        """, (i + 1, "learning", _ago(1), 1, 12))
    srs_conn.commit()

    findings = analyze_srs_funnel(srs_conn)
    reg = [f for f in findings if "regressed" in f["title"].lower()]
    assert reg == []


def test_srs_funnel_historically_weak_triggers_medium(srs_conn):
    """More than 20% historically_weak items triggers a medium finding."""
    # 3 weak, 9 normal — 25% > 20% threshold
    for i in range(3):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at, historically_weak) VALUES (?,?,?,?)",
            (i + 1, "learning", _ago(1), 1),
        )
    for i in range(9):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at, historically_weak) VALUES (?,?,?,?)",
            (100 + i, "stable", _ago(1), 0),
        )
    srs_conn.commit()

    findings = analyze_srs_funnel(srs_conn)
    weak = [f for f in findings if "historically_weak" in f["title"].lower()]
    assert weak, "Expected a historically_weak finding"
    assert weak[0]["severity"] == "medium"


def test_srs_funnel_historically_weak_below_threshold_no_finding(srs_conn):
    """10% historically_weak should not trigger."""
    for i in range(1):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at, historically_weak) VALUES (?,?,?,?)",
            (i + 1, "learning", _ago(1), 1),
        )
    for i in range(9):
        srs_conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at, historically_weak) VALUES (?,?,?,?)",
            (100 + i, "stable", _ago(1), 0),
        )
    srs_conn.commit()

    findings = analyze_srs_funnel(srs_conn)
    weak = [f for f in findings if "historically_weak" in f["title"].lower()]
    assert weak == []


# ---------------------------------------------------------------------------
# 2. analyze_error_taxonomy
# ---------------------------------------------------------------------------

@pytest.fixture
def error_conn():
    conn = _make_conn()
    conn.execute("""
        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY,
            error_type TEXT,
            created_at TEXT,
            content_item_id INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


def test_error_taxonomy_empty_returns_no_findings(error_conn):
    findings = analyze_error_taxonomy(error_conn)
    assert findings == []


def test_error_taxonomy_growing_error_type_triggers_finding(error_conn):
    """An error type that grew >30% week-over-week should trigger a finding."""
    # Prior 4 weeks (5–35 days ago): 4 total → avg 1/week
    for day in [10, 15, 20, 25]:
        error_conn.execute(
            "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
            ("tone", _ago(day)),
        )
    # Current week: 5 — that's +400% above prior avg of 1
    for _ in range(5):
        error_conn.execute(
            "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
            ("tone", _ago(2)),
        )
    error_conn.commit()

    findings = analyze_error_taxonomy(error_conn)
    assert findings, "Expected at least one finding for growing error type"
    assert any("growing" in f["title"].lower() for f in findings)
    for f in findings:
        _assert_finding_shape(f)


def test_error_taxonomy_high_severity_when_growth_over_50pct(error_conn):
    """Growth >50% should yield severity=high."""
    # Prior 4 weeks: 1 per week (4 total)
    for day in [10, 15, 20, 25]:
        error_conn.execute(
            "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
            ("stroke_order", _ago(day)),
        )
    # Current week: 10 events — 900% growth
    for _ in range(10):
        error_conn.execute(
            "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
            ("stroke_order", _ago(3)),
        )
    error_conn.commit()

    findings = analyze_error_taxonomy(error_conn)
    growing = [f for f in findings if "growing" in f["title"].lower()]
    assert growing
    assert growing[0]["severity"] == "high"


def test_error_taxonomy_no_growth_no_finding(error_conn):
    """Stable error counts should not trigger a growth finding."""
    # 4 per week for 5 weeks — flat
    for day in range(5, 36, 7):
        for _ in range(4):
            error_conn.execute(
                "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
                ("tone", _ago(day)),
            )
    error_conn.commit()

    findings = analyze_error_taxonomy(error_conn)
    growing = [f for f in findings if "growing" in f["title"].lower()]
    assert growing == []


def test_error_taxonomy_register_mismatch_triggers_medium(error_conn):
    """More than 5 register_mismatch errors in 30 days triggers a medium finding."""
    for _ in range(6):
        error_conn.execute(
            "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
            ("register_mismatch", _ago(5)),
        )
    error_conn.commit()

    findings = analyze_error_taxonomy(error_conn)
    reg = [f for f in findings if "register" in f["title"].lower()]
    assert reg, "Expected a register_mismatch finding"
    assert reg[0]["severity"] == "medium"


def test_error_taxonomy_register_mismatch_at_threshold_no_finding(error_conn):
    """Exactly 5 register_mismatch errors should not trigger."""
    for _ in range(5):
        error_conn.execute(
            "INSERT INTO error_log (error_type, created_at) VALUES (?,?)",
            ("register_mismatch", _ago(5)),
        )
    error_conn.commit()

    findings = analyze_error_taxonomy(error_conn)
    reg = [f for f in findings if "register" in f["title"].lower()]
    assert reg == []


# ---------------------------------------------------------------------------
# 3. analyze_cross_modality_transfer
# ---------------------------------------------------------------------------

@pytest.fixture
def modality_conn():
    conn = _make_conn()
    conn.execute("""
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY,
            user_id INTEGER DEFAULT 1,
            content_item_id INTEGER,
            modality TEXT,
            mastery_stage TEXT,
            updated_at TEXT DEFAULT '2024-01-01'
        )
    """)
    conn.commit()
    return conn


def _insert_progress(conn, item_id, modality, stage, user_id=1):
    conn.execute(
        "INSERT INTO progress (user_id, content_item_id, modality, mastery_stage) VALUES (?,?,?,?)",
        (user_id, item_id, modality, stage),
    )


def test_cross_modality_empty_returns_no_findings(modality_conn):
    findings = analyze_cross_modality_transfer(modality_conn)
    assert findings == []


def test_cross_modality_gap_triggers_finding(modality_conn):
    """5+ items where reading is stable but listening is unseen triggers a finding."""
    for item_id in range(1, 11):
        _insert_progress(modality_conn, item_id, "reading", "stable")
        _insert_progress(modality_conn, item_id, "listening", "unseen")
    modality_conn.commit()

    findings = analyze_cross_modality_transfer(modality_conn)
    assert findings, "Expected a cross-modality finding"
    assert any("modality" in f["title"].lower() or "gap" in f["title"].lower() for f in findings)
    for f in findings:
        _assert_finding_shape(f)


def test_cross_modality_high_severity_for_many_gaps(modality_conn):
    """More than 20 items with gaps triggers severity=high."""
    for item_id in range(1, 26):
        _insert_progress(modality_conn, item_id, "reading", "stable")
        _insert_progress(modality_conn, item_id, "listening", "seen")
    modality_conn.commit()

    findings = analyze_cross_modality_transfer(modality_conn)
    assert findings
    assert findings[0]["severity"] == "high"


def test_cross_modality_no_gap_no_finding(modality_conn):
    """Items mastered in all modalities should not trigger a finding."""
    for item_id in range(1, 6):
        _insert_progress(modality_conn, item_id, "reading", "stable")
        _insert_progress(modality_conn, item_id, "listening", "stable")
    modality_conn.commit()

    findings = analyze_cross_modality_transfer(modality_conn)
    assert findings == []


def test_cross_modality_fewer_than_5_gaps_no_finding(modality_conn):
    """Fewer than 5 gap rows should not trigger (threshold is 5)."""
    for item_id in range(1, 5):
        _insert_progress(modality_conn, item_id, "reading", "stable")
        _insert_progress(modality_conn, item_id, "listening", "unseen")
    modality_conn.commit()

    findings = analyze_cross_modality_transfer(modality_conn)
    assert findings == []


# ---------------------------------------------------------------------------
# 4. analyze_curriculum_coverage
# ---------------------------------------------------------------------------

@pytest.fixture
def curriculum_conn():
    conn = _make_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_log (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            started_at TEXT DEFAULT (datetime('now')),
            items_planned INTEGER DEFAULT 10, items_completed INTEGER DEFAULT 8,
            duration_seconds INTEGER DEFAULT 300, early_exit INTEGER DEFAULT 0,
            boredom_flags INTEGER DEFAULT 0, client_platform TEXT
        );
        CREATE TABLE grammar_point (
            id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT DEFAULT 'basic'
        );
        CREATE TABLE grammar_progress (
            id INTEGER PRIMARY KEY,
            grammar_point_id INTEGER
        );
        CREATE TABLE skill (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE content_skill (
            id INTEGER PRIMARY KEY,
            skill_id INTEGER,
            content_item_id INTEGER
        );
    """)
    # Seed 3 active users with recent sessions (minimum for curriculum analysis)
    for uid in range(1, 4):
        conn.execute(
            "INSERT INTO session_log (user_id, started_at) VALUES (?, datetime('now', '-1 day'))",
            (uid,),
        )
    conn.commit()
    return conn


def test_curriculum_empty_tables_returns_no_findings(curriculum_conn):
    """No grammar points or skills means nothing to report coverage on."""
    findings = analyze_curriculum_coverage(curriculum_conn)
    assert findings == []


def test_curriculum_low_grammar_coverage_triggers_high(curriculum_conn):
    """Coverage below 25% triggers a high finding."""
    for i in range(20):
        curriculum_conn.execute("INSERT INTO grammar_point (name, category) VALUES (?,?)",
                                (f"point_{i}", "basic"))
    # Only drill 2 out of 20 = 10% coverage
    curriculum_conn.execute("INSERT INTO grammar_progress (grammar_point_id) VALUES (1)")
    curriculum_conn.execute("INSERT INTO grammar_progress (grammar_point_id) VALUES (2)")
    curriculum_conn.commit()

    findings = analyze_curriculum_coverage(curriculum_conn)
    grammar_findings = [f for f in findings if "grammar coverage" in f["title"].lower()]
    assert grammar_findings, "Expected a low grammar coverage finding"
    assert grammar_findings[0]["severity"] == "high"
    for f in findings:
        _assert_finding_shape(f)


def test_curriculum_medium_grammar_coverage(curriculum_conn):
    """Coverage between 25–50% triggers a medium finding."""
    for i in range(10):
        curriculum_conn.execute("INSERT INTO grammar_point (name, category) VALUES (?,?)",
                                (f"point_{i}", "basic"))
    # Drill 4 out of 10 = 40%
    for i in range(1, 5):
        curriculum_conn.execute("INSERT INTO grammar_progress (grammar_point_id) VALUES (?)", (i,))
    curriculum_conn.commit()

    findings = analyze_curriculum_coverage(curriculum_conn)
    grammar_findings = [f for f in findings if "grammar coverage" in f["title"].lower()]
    assert grammar_findings
    assert grammar_findings[0]["severity"] == "medium"


def test_curriculum_sufficient_coverage_no_grammar_finding(curriculum_conn):
    """Coverage at or above 50% should not trigger the grammar coverage finding."""
    for i in range(10):
        curriculum_conn.execute("INSERT INTO grammar_point (name, category) VALUES (?,?)",
                                (f"point_{i}", "basic"))
    # Drill 6 out of 10 = 60%
    for i in range(1, 7):
        curriculum_conn.execute("INSERT INTO grammar_progress (grammar_point_id) VALUES (?)", (i,))
    curriculum_conn.commit()

    findings = analyze_curriculum_coverage(curriculum_conn)
    grammar_findings = [f for f in findings if "grammar coverage" in f["title"].lower()]
    assert grammar_findings == []


def test_curriculum_weak_category_triggers_medium(curriculum_conn):
    """A grammar category with fewer than 2 drilled points triggers a medium finding."""
    # Category A: 5 points, 0 drilled
    for i in range(5):
        curriculum_conn.execute("INSERT INTO grammar_point (name, category) VALUES (?,?)",
                                (f"cat_a_{i}", "particles"))
    curriculum_conn.commit()

    findings = analyze_curriculum_coverage(curriculum_conn)
    cat_findings = [f for f in findings if "categories" in f["title"].lower()]
    assert cat_findings, "Expected a weak-category finding"
    assert cat_findings[0]["severity"] == "medium"


def test_curriculum_orphan_skills_trigger_finding(curriculum_conn):
    """Skills with no linked content items trigger a finding."""
    curriculum_conn.execute("INSERT INTO skill (name) VALUES ('Greetings')")
    curriculum_conn.execute("INSERT INTO skill (name) VALUES ('Numbers')")
    curriculum_conn.commit()

    findings = analyze_curriculum_coverage(curriculum_conn)
    orphan_findings = [f for f in findings if "orphan" in f["title"].lower() or "zero linked" in f["title"].lower()]
    assert orphan_findings, "Expected an orphan skills finding"
    for f in findings:
        _assert_finding_shape(f)


def test_curriculum_linked_skills_no_orphan_finding(curriculum_conn):
    """Skills that have linked content items should not trigger the orphan finding."""
    curriculum_conn.execute("INSERT INTO skill (id, name) VALUES (1, 'Greetings')")
    curriculum_conn.execute("INSERT INTO content_skill (skill_id, content_item_id) VALUES (1, 42)")
    curriculum_conn.commit()

    findings = analyze_curriculum_coverage(curriculum_conn)
    orphan_findings = [f for f in findings if "orphan" in f["title"].lower() or "zero linked" in f["title"].lower()]
    assert orphan_findings == []


# ---------------------------------------------------------------------------
# 5. analyze_hsk_cliff
# ---------------------------------------------------------------------------

@pytest.fixture
def hsk_conn():
    conn = _make_conn()
    conn.executescript("""
        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER,
            correct INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY,
            hsk_level INTEGER
        );
    """)
    conn.commit()
    return conn


def _insert_reviews(conn, item_id, hsk_level, total, errors, days_ago=5):
    """Insert a content_item and matching review_events."""
    conn.execute("INSERT OR IGNORE INTO content_item (id, hsk_level) VALUES (?,?)",
                 (item_id, hsk_level))
    ts = _ago(days_ago)
    for i in range(total):
        correct = 0 if i < errors else 1
        conn.execute(
            "INSERT INTO review_event (content_item_id, correct, created_at) VALUES (?,?,?)",
            (item_id, correct, ts),
        )


def test_hsk_cliff_empty_returns_no_findings(hsk_conn):
    findings = analyze_hsk_cliff(hsk_conn)
    assert findings == []


def test_hsk_cliff_insufficient_levels_no_finding(hsk_conn):
    """Only one HSK level with data cannot form a cliff comparison."""
    _insert_reviews(hsk_conn, 1, 2, 20, 2)
    hsk_conn.commit()

    findings = analyze_hsk_cliff(hsk_conn)
    assert findings == []


def test_hsk_cliff_triggers_high_on_large_jump(hsk_conn):
    """A >30pp error rate jump between adjacent HSK levels triggers high severity."""
    # HSK 2: 20 reviews, 2 errors = 10% error rate
    _insert_reviews(hsk_conn, 1, 2, 20, 2)
    # HSK 3: 20 reviews, 9 errors = 45% error rate → +35pp jump
    _insert_reviews(hsk_conn, 2, 3, 20, 9)
    hsk_conn.commit()

    findings = analyze_hsk_cliff(hsk_conn)
    assert findings, "Expected an HSK cliff finding"
    cliff = [f for f in findings if "cliff" in f["title"].lower()]
    assert cliff
    assert cliff[0]["severity"] == "high"
    for f in findings:
        _assert_finding_shape(f)


def test_hsk_cliff_triggers_medium_on_moderate_jump(hsk_conn):
    """A 20–30pp jump triggers severity=medium."""
    # HSK 1: 20 reviews, 2 errors = 10% error rate
    _insert_reviews(hsk_conn, 1, 1, 20, 2)
    # HSK 2: 20 reviews, 7 errors = 35% error rate → +25pp jump
    _insert_reviews(hsk_conn, 2, 2, 20, 7)
    hsk_conn.commit()

    findings = analyze_hsk_cliff(hsk_conn)
    cliff = [f for f in findings if "cliff" in f["title"].lower()]
    assert cliff
    assert cliff[0]["severity"] == "medium"


def test_hsk_cliff_small_jump_no_finding(hsk_conn):
    """A jump of <=20pp should not trigger a cliff finding."""
    # HSK 1: 20 reviews, 2 errors = 10%
    _insert_reviews(hsk_conn, 1, 1, 20, 2)
    # HSK 2: 20 reviews, 5 errors = 25% → +15pp — under threshold
    _insert_reviews(hsk_conn, 2, 2, 20, 5)
    hsk_conn.commit()

    findings = analyze_hsk_cliff(hsk_conn)
    cliff = [f for f in findings if "cliff" in f["title"].lower()]
    assert cliff == []


def test_hsk_cliff_respects_minimum_10_reviews(hsk_conn):
    """HSK levels with fewer than 10 reviews are excluded from cliff detection."""
    # HSK 1: only 5 reviews — below minimum
    _insert_reviews(hsk_conn, 1, 1, 5, 1)
    # HSK 2: 20 reviews, 10 errors = 50%
    _insert_reviews(hsk_conn, 2, 2, 20, 10)
    hsk_conn.commit()

    # Only one level passes the HAVING threshold — no comparison possible
    findings = analyze_hsk_cliff(hsk_conn)
    assert findings == []


# ---------------------------------------------------------------------------
# 6. analyze_tone_phonology
# ---------------------------------------------------------------------------

@pytest.fixture
def tone_conn():
    conn = _make_conn()
    conn.execute("""
        CREATE TABLE audio_recording (
            id INTEGER PRIMARY KEY,
            tone_scores_json TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


def _insert_recording(conn, syllables: list, days_ago: int = 1):
    conn.execute(
        "INSERT INTO audio_recording (tone_scores_json, created_at) VALUES (?,?)",
        (json.dumps(syllables), _ago(days_ago)),
    )


def test_tone_phonology_no_data_returns_empty(tone_conn):
    """Fewer than 10 recordings returns no findings."""
    findings = analyze_tone_phonology(tone_conn)
    assert findings == []


def test_tone_phonology_weak_tone_triggers_finding(tone_conn):
    """A tone with <70% accuracy (n>=10) triggers a finding."""
    # Tone 2 with only 40% accuracy — 4 correct, 6 wrong (×12 recordings)
    for _ in range(12):
        _insert_recording(tone_conn, [
            {"expected_tone": 2, "detected_tone": 3, "correct": False},
            {"expected_tone": 2, "detected_tone": 3, "correct": False},
            {"expected_tone": 2, "detected_tone": 2, "correct": True},
            {"expected_tone": 2, "detected_tone": 2, "correct": True},
        ])
    tone_conn.commit()

    findings = analyze_tone_phonology(tone_conn)
    assert findings, "Expected a weak tone finding"
    tone_findings = [f for f in findings if "tone" in f["title"].lower()]
    assert tone_findings
    for f in findings:
        _assert_finding_shape(f)


def test_tone_phonology_very_low_accuracy_triggers_high(tone_conn):
    """A tone with <50% accuracy triggers severity=high."""
    # Tone 3 with 30% accuracy
    for _ in range(12):
        _insert_recording(tone_conn, [
            {"expected_tone": 3, "detected_tone": 2, "correct": False},
            {"expected_tone": 3, "detected_tone": 2, "correct": False},
            {"expected_tone": 3, "detected_tone": 2, "correct": False},
            {"expected_tone": 3, "detected_tone": 3, "correct": True},
        ])
    tone_conn.commit()

    findings = analyze_tone_phonology(tone_conn)
    tone_findings = [f for f in findings if "weak tone" in f["title"].lower()]
    assert tone_findings
    assert tone_findings[0]["severity"] == "high"


def test_tone_phonology_good_accuracy_no_weak_tone_finding(tone_conn):
    """Tones with >=70% accuracy should not trigger a weak-tone finding."""
    for _ in range(12):
        _insert_recording(tone_conn, [
            {"expected_tone": 1, "detected_tone": 1, "correct": True},
            {"expected_tone": 2, "detected_tone": 2, "correct": True},
            {"expected_tone": 3, "detected_tone": 3, "correct": True},
        ])
    tone_conn.commit()

    findings = analyze_tone_phonology(tone_conn)
    weak = [f for f in findings if "weak tone" in f["title"].lower()]
    assert weak == []


def test_tone_phonology_confusion_pairs_trigger_finding(tone_conn):
    """5+ instances of the same confusion pair triggers a confusion finding."""
    # T2→T3 confusion (5 per recording × 2 recordings = 10 — but test uses single recording approach)
    for _ in range(12):
        syllables = [
            {"expected_tone": 2, "detected_tone": 3, "correct": False},
            {"expected_tone": 2, "detected_tone": 2, "correct": True},
        ]
        _insert_recording(tone_conn, syllables)
    tone_conn.commit()

    findings = analyze_tone_phonology(tone_conn)
    confusion = [f for f in findings if "confusion" in f["title"].lower()]
    assert confusion, "Expected a tone confusion finding"
    assert confusion[0]["severity"] == "medium"


def test_tone_phonology_insufficient_recordings_no_finding(tone_conn):
    """Fewer than 10 recordings with tone_scores_json should return no findings."""
    for _ in range(5):
        _insert_recording(tone_conn, [
            {"expected_tone": 1, "detected_tone": 2, "correct": False},
        ])
    tone_conn.commit()

    findings = analyze_tone_phonology(tone_conn)
    assert findings == []


def test_tone_phonology_malformed_json_handled_gracefully(tone_conn):
    """Malformed tone_scores_json should not raise — findings may be empty."""
    for _ in range(12):
        tone_conn.execute(
            "INSERT INTO audio_recording (tone_scores_json, created_at) VALUES (?,?)",
            ("not-valid-json", _ago(1)),
        )
    tone_conn.commit()

    # Should not raise
    findings = analyze_tone_phonology(tone_conn)
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# 7. analyze_scheduler_decisions
# ---------------------------------------------------------------------------

@pytest.fixture
def scheduler_conn():
    conn = _make_conn()
    conn.executescript("""
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY,
            plan_snapshot TEXT,
            started_at TEXT,
            items_planned INTEGER DEFAULT 10,
            items_completed INTEGER DEFAULT 8
        );
        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY,
            drill_type TEXT,
            created_at TEXT
        );
    """)
    conn.commit()
    return conn


def test_scheduler_decisions_empty_returns_no_findings(scheduler_conn):
    findings = analyze_scheduler_decisions(scheduler_conn)
    assert findings == []


def test_scheduler_decisions_gentle_mode_dominance_triggers_medium(scheduler_conn):
    """More than 40% gentle/consolidation sessions triggers a medium finding."""
    for i in range(5):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at) VALUES (?,?)",
            (json.dumps({"day_mode": "gentle"}), _ago(2)),
        )
    for i in range(3):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at) VALUES (?,?)",
            (json.dumps({"day_mode": "standard"}), _ago(2)),
        )
    scheduler_conn.commit()

    findings = analyze_scheduler_decisions(scheduler_conn)
    gentle = [f for f in findings if "gentle" in f["title"].lower()]
    assert gentle, "Expected a gentle-mode finding"
    assert gentle[0]["severity"] == "medium"
    for f in findings:
        _assert_finding_shape(f)


def test_scheduler_decisions_standard_mode_no_finding(scheduler_conn):
    """Mostly standard sessions should not trigger the gentle-mode finding."""
    for i in range(8):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at) VALUES (?,?)",
            (json.dumps({"day_mode": "standard"}), _ago(2)),
        )
    for i in range(2):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at) VALUES (?,?)",
            (json.dumps({"day_mode": "gentle"}), _ago(2)),
        )
    scheduler_conn.commit()

    findings = analyze_scheduler_decisions(scheduler_conn)
    gentle = [f for f in findings if "gentle" in f["title"].lower()]
    assert gentle == []


def test_scheduler_decisions_wip_exceeded_triggers_medium(scheduler_conn):
    """More than 5 sessions with wip_exceeded=True triggers a medium finding."""
    for i in range(6):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at) VALUES (?,?)",
            (json.dumps({"day_mode": "standard", "wip_exceeded": True}), _ago(2)),
        )
    scheduler_conn.commit()

    findings = analyze_scheduler_decisions(scheduler_conn)
    wip = [f for f in findings if "wip" in f["title"].lower()]
    assert wip, "Expected a WIP exceeded finding"
    assert wip[0]["severity"] == "medium"


def test_scheduler_decisions_thompson_convergence_triggers_medium(scheduler_conn):
    """One drill type comprising >70% of 2-week reviews triggers a Thompson Sampling finding."""
    for _ in range(75):
        scheduler_conn.execute(
            "INSERT INTO review_event (drill_type, created_at) VALUES (?,?)",
            ("mc", _ago(5)),
        )
    for _ in range(25):
        scheduler_conn.execute(
            "INSERT INTO review_event (drill_type, created_at) VALUES (?,?)",
            ("reverse_mc", _ago(5)),
        )
    # Add a third type to satisfy the len >= 3 condition
    scheduler_conn.execute(
        "INSERT INTO review_event (drill_type, created_at) VALUES (?,?)",
        ("tone", _ago(5)),
    )
    scheduler_conn.commit()

    findings = analyze_scheduler_decisions(scheduler_conn)
    ts = [f for f in findings if "thompson" in f["title"].lower() or "converged" in f["title"].lower()]
    assert ts, "Expected a Thompson Sampling convergence finding"
    assert ts[0]["severity"] == "medium"


def test_scheduler_decisions_low_completion_ratio_triggers_high(scheduler_conn):
    """Sessions completing <60% of planned items trigger a high finding."""
    # 15 sessions each completing 5 out of 15 planned = 33%
    for i in range(15):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at, items_planned, items_completed) VALUES (?,?,?,?)",
            (None, _ago(5), 15, 5),
        )
    scheduler_conn.commit()

    findings = analyze_scheduler_decisions(scheduler_conn)
    completion = [f for f in findings if "planned" in f["title"].lower() or "complete" in f["title"].lower()]
    assert completion, "Expected a low completion ratio finding"
    assert completion[0]["severity"] == "high"


def test_scheduler_decisions_good_completion_no_finding(scheduler_conn):
    """Sessions completing >=60% of planned items should not trigger."""
    for i in range(15):
        scheduler_conn.execute(
            "INSERT INTO session_log (plan_snapshot, started_at, items_planned, items_completed) VALUES (?,?,?,?)",
            (None, _ago(5), 10, 8),
        )
    scheduler_conn.commit()

    findings = analyze_scheduler_decisions(scheduler_conn)
    completion = [f for f in findings if "planned" in f["title"].lower() or "complete" in f["title"].lower()]
    assert completion == []


# ---------------------------------------------------------------------------
# 8. analyze_encounter_feedback_loop
# ---------------------------------------------------------------------------

@pytest.fixture
def encounter_conn():
    conn = _make_conn()
    conn.executescript("""
        CREATE TABLE vocab_encounter (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER,
            looked_up INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER,
            created_at TEXT
        );
    """)
    conn.commit()
    return conn


def test_encounter_feedback_loop_no_data_returns_empty(encounter_conn):
    """Fewer than 10 looked-up encounters returns no findings."""
    findings = analyze_encounter_feedback_loop(encounter_conn)
    assert findings == []


def test_encounter_feedback_loop_low_drill_rate_triggers_high(encounter_conn):
    """Very few encounters drilled (<10%) triggers a high finding."""
    # 20 looked-up encounters — none of them ever drilled
    for i in range(20):
        encounter_conn.execute(
            "INSERT INTO vocab_encounter (content_item_id, looked_up, created_at) VALUES (?,?,?)",
            (i + 1, 1, _ago(10)),
        )
    encounter_conn.commit()

    findings = analyze_encounter_feedback_loop(encounter_conn)
    loop_findings = [f for f in findings if "drilled" in f["title"].lower() or "looked-up" in f["title"].lower()]
    assert loop_findings, "Expected an encounter feedback loop finding"
    assert loop_findings[0]["severity"] == "high"
    for f in findings:
        _assert_finding_shape(f)


def test_encounter_feedback_loop_medium_severity_between_10_and_30_pct(encounter_conn):
    """10–30% drill rate triggers severity=medium."""
    # 20 encounters, 3 drilled = 15%
    for i in range(20):
        encounter_conn.execute(
            "INSERT INTO vocab_encounter (content_item_id, looked_up, created_at) VALUES (?,?,?)",
            (i + 1, 1, _ago(10)),
        )
    for i in range(3):
        encounter_conn.execute(
            "INSERT INTO review_event (content_item_id, created_at) VALUES (?,?)",
            (i + 1, _ago(5)),
        )
    encounter_conn.commit()

    findings = analyze_encounter_feedback_loop(encounter_conn)
    loop_findings = [f for f in findings if "drilled" in f["title"].lower() or "looked-up" in f["title"].lower()]
    assert loop_findings
    assert loop_findings[0]["severity"] == "medium"


def test_encounter_feedback_loop_good_rate_no_rate_finding(encounter_conn):
    """>=30% drill rate should not trigger the low-drill-rate finding."""
    for i in range(20):
        encounter_conn.execute(
            "INSERT INTO vocab_encounter (content_item_id, looked_up, created_at) VALUES (?,?,?)",
            (i + 1, 1, _ago(10)),
        )
    # Drill 10 of the 20 = 50%
    for i in range(10):
        encounter_conn.execute(
            "INSERT INTO review_event (content_item_id, created_at) VALUES (?,?)",
            (i + 1, _ago(5)),
        )
    encounter_conn.commit()

    findings = analyze_encounter_feedback_loop(encounter_conn)
    loop_findings = [f for f in findings if "drilled" in f["title"].lower() or "looked-up" in f["title"].lower()]
    assert loop_findings == []


def test_encounter_feedback_loop_high_latency_triggers_medium(encounter_conn):
    """Average encounter→drill latency >7 days triggers a medium finding."""
    # 20 encounters 20 days ago, all drilled 10 days later (latency = 10 days)
    for i in range(20):
        encounter_conn.execute(
            "INSERT INTO vocab_encounter (content_item_id, looked_up, created_at) VALUES (?,?,?)",
            (i + 1, 1, _ago(20)),
        )
        encounter_conn.execute(
            "INSERT INTO review_event (content_item_id, created_at) VALUES (?,?)",
            (i + 1, _ago(10)),
        )
    encounter_conn.commit()

    findings = analyze_encounter_feedback_loop(encounter_conn)
    latency_findings = [f for f in findings if "latency" in f["title"].lower()]
    assert latency_findings, "Expected a latency finding"
    assert latency_findings[0]["severity"] == "medium"


def test_encounter_feedback_loop_low_latency_no_latency_finding(encounter_conn):
    """Encounters drilled within 1 day should not trigger the latency finding."""
    for i in range(20):
        encounter_conn.execute(
            "INSERT INTO vocab_encounter (content_item_id, looked_up, created_at) VALUES (?,?,?)",
            (i + 1, 1, _ago(10)),
        )
        # Drill same-ish day (1 day later) — within acceptable window
        encounter_conn.execute(
            "INSERT INTO review_event (content_item_id, created_at) VALUES (?,?)",
            (i + 1, _ago(9)),
        )
    encounter_conn.commit()

    findings = analyze_encounter_feedback_loop(encounter_conn)
    latency_findings = [f for f in findings if "latency" in f["title"].lower()]
    assert latency_findings == []


def test_encounter_feedback_loop_only_looked_up_counted(encounter_conn):
    """Encounters with looked_up=0 should not count toward the total threshold."""
    # 15 rows but looked_up=0 — should not reach the threshold of 10
    for i in range(15):
        encounter_conn.execute(
            "INSERT INTO vocab_encounter (content_item_id, looked_up, created_at) VALUES (?,?,?)",
            (i + 1, 0, _ago(5)),
        )
    encounter_conn.commit()

    findings = analyze_encounter_feedback_loop(encounter_conn)
    assert findings == []


# ---------------------------------------------------------------------------
# Finding shape contract — all analyzers must produce well-formed findings
# ---------------------------------------------------------------------------

def test_all_findings_have_required_keys():
    """Any finding produced by any domain analyzer must have all required keys."""
    conn = _make_conn()
    conn.executescript("""
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY, content_item_id INTEGER, user_id INTEGER DEFAULT 1,
            modality TEXT DEFAULT 'reading', mastery_stage TEXT DEFAULT 'stabilizing',
            updated_at TEXT, weak_cycle_count INTEGER DEFAULT 2,
            historically_weak INTEGER DEFAULT 0, repetitions INTEGER DEFAULT 15,
            ease_factor REAL DEFAULT 2.5, interval_days REAL DEFAULT 1.0
        );
        CREATE TABLE error_log (id INTEGER PRIMARY KEY, error_type TEXT, created_at TEXT, content_item_id INTEGER DEFAULT 1);
        CREATE TABLE grammar_point (id INTEGER PRIMARY KEY, name TEXT, category TEXT DEFAULT 'basic');
        CREATE TABLE grammar_progress (id INTEGER PRIMARY KEY, grammar_point_id INTEGER);
        CREATE TABLE skill (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE content_skill (id INTEGER PRIMARY KEY, skill_id INTEGER, content_item_id INTEGER);
        CREATE TABLE review_event (id INTEGER PRIMARY KEY, content_item_id INTEGER, correct INTEGER DEFAULT 1, created_at TEXT, drill_type TEXT DEFAULT 'mc');
        CREATE TABLE content_item (id INTEGER PRIMARY KEY, hsk_level INTEGER);
        CREATE TABLE audio_recording (id INTEGER PRIMARY KEY, tone_scores_json TEXT, created_at TEXT);
        CREATE TABLE session_log (id INTEGER PRIMARY KEY, plan_snapshot TEXT, started_at TEXT, items_planned INTEGER DEFAULT 10, items_completed INTEGER DEFAULT 5);
        CREATE TABLE vocab_encounter (id INTEGER PRIMARY KEY, content_item_id INTEGER, looked_up INTEGER DEFAULT 1, created_at TEXT);
    """)

    # Seed enough data to trigger at least some findings across all analyzers
    ts = _ago(20)
    for i in range(10):
        conn.execute(
            "INSERT INTO progress (content_item_id, mastery_stage, updated_at, weak_cycle_count, repetitions) VALUES (?,?,?,?,?)",
            (i + 1, "stabilizing", ts, 1, 12),
        )
    conn.commit()

    analyzers = [
        analyze_srs_funnel,
        analyze_error_taxonomy,
        analyze_cross_modality_transfer,
        analyze_curriculum_coverage,
        analyze_hsk_cliff,
        analyze_tone_phonology,
        analyze_scheduler_decisions,
        analyze_encounter_feedback_loop,
    ]
    for analyzer in analyzers:
        findings = analyzer(conn)
        assert isinstance(findings, list), f"{analyzer.__name__} must return a list"
        for f in findings:
            _assert_finding_shape(f)

    conn.close()
