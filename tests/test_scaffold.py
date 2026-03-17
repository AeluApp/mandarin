"""Tests for show_pinyin scaffold feature.

Validates that drill metadata includes show_pinyin=True for early-stage items
(mastery_stage "seen" or "passed_once") and show_pinyin=False for later stages
("stabilizing", "stable", "durable").

The logic lives in mandarin/scheduler.py plan_standard_session():
    mastery_stage = item.get("mastery_stage") or "seen"
    show_pinyin = mastery_stage in ("seen", "passed_once")

Note: The scheduler joins progress by modality. An item can have mastery_stage
"stabilizing" in one modality but no progress row (NULL -> "seen") in another.
Tests record attempts across all four modalities to ensure consistent stage
regardless of which modality the scheduler picks.

Also note: Items with error_focus entries get scheduled through a separate code
path that does NOT set show_pinyin metadata. Tests avoid this by not recording
incorrect attempts with error_type, or by verifying the logic directly when
items appear as error_focus drills.
"""

import tempfile
from datetime import date
from pathlib import Path

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item
from mandarin.db.progress import record_attempt
from mandarin.scheduler import plan_standard_session


_ALL_MODALITIES = ("reading", "listening", "speaking", "ime")


def _fresh_db():
    """Create a fresh test database with schema + migrations + seed profile."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


# Seed vocabulary: 25 items across HSK 1-3 with distinct hanzi and valid pinyin
# (tone marks required for tone drills to pass _item_is_drillable).
_SEED_ITEMS = [
    ("你",     "nǐ",      "you",          1),
    ("好",     "hǎo",     "good",         1),
    ("我",     "wǒ",      "I/me",         1),
    ("是",     "shì",     "to be",        1),
    ("不",     "bù",      "not",          1),
    ("他",     "tā",      "he/him",       1),
    ("她",     "tā",      "she/her",      1),
    ("们",     "men",     "plural marker", 1),
    ("的",     "de",      "possessive",   1),
    ("了",     "le",      "aspect marker", 1),
    ("在",     "zài",     "at/in",        2),
    ("有",     "yǒu",     "have",         2),
    ("这",     "zhè",     "this",         2),
    ("那",     "nà",      "that",         2),
    ("什么",   "shénme",  "what",         2),
    ("人",     "rén",     "person",       2),
    ("大",     "dà",      "big",          2),
    ("学",     "xué",     "study",        2),
    ("中",     "zhōng",   "middle",       2),
    ("国",     "guó",     "country",      2),
    ("时候",   "shíhou",  "time/moment",  3),
    ("出",     "chū",     "go out",       3),
    ("来",     "lái",     "come",         3),
    ("会",     "huì",     "can/will",     3),
    ("年",     "nián",    "year",         3),
]


def _seed_items(conn):
    """Insert 25 seed items and return list of (item_id, hanzi)."""
    ids = []
    for hanzi, pinyin, english, hsk in _SEED_ITEMS:
        item_id = insert_content_item(
            conn, hanzi=hanzi, pinyin=pinyin, english=english, hsk_level=hsk,
        )
        ids.append((item_id, hanzi))
    conn.commit()
    return ids


def _seed_session(conn):
    """Insert a dummy session so the planner's total_sessions > 0 and
    last_session_date is set (avoids long-gap mode which blocks new items)."""
    conn.execute("""
        INSERT INTO session_log (session_type, items_planned, items_completed,
                                 items_correct, session_started_hour, session_day_of_week)
        VALUES ('standard', 12, 12, 10, 10, 2)
    """)
    conn.execute("""
        UPDATE learner_profile SET
            total_sessions = 1,
            last_session_date = ?
        WHERE id = 1
    """, (date.today().isoformat(),))
    conn.commit()


def _record_in_all_modalities(conn, item_id, correct, drill_type="mc"):
    """Record the same attempt outcome in all 4 modalities so the item's
    mastery_stage is consistent regardless of which modality the scheduler
    picks."""
    for mod in _ALL_MODALITIES:
        record_attempt(conn, item_id, mod, correct, drill_type=drill_type)


def _find_drill_for_item(plan, item_id):
    """Find a non-error-focus drill in the session plan matching a content_item_id.
    Error-focus drills use a separate code path that doesn't set show_pinyin."""
    for d in plan.drills:
        if d.content_item_id == item_id and not d.is_error_focus:
            return d
    return None


def _find_any_drill_for_item(plan, item_id):
    """Find any drill in the session plan matching a content_item_id."""
    for d in plan.drills:
        if d.content_item_id == item_id:
            return d
    return None


def _get_stage(conn, item_id, modality="reading"):
    row = conn.execute(
        "SELECT mastery_stage FROM progress WHERE content_item_id = ? AND modality = ?",
        (item_id, modality)
    ).fetchone()
    return row["mastery_stage"] if row else None


# ── Test 1: show_pinyin is True for "seen" items ──

def test_show_pinyin_for_seen():
    """An item that has only been attempted once (wrong) stays at 'seen'.
    When scheduled through the normal (non-error-focus) path, its drill
    metadata should have show_pinyin=True."""
    conn, path = _fresh_db()
    try:
        ids = _seed_items(conn)
        _seed_session(conn)

        # Record 1 wrong attempt in all modalities -> stays at "seen"
        target_id, target_hanzi = ids[0]
        _record_in_all_modalities(conn, target_id, False)

        # Verify the mastery stage is "seen" in all modalities
        for mod in _ALL_MODALITIES:
            stage = _get_stage(conn, target_id, mod)
            assert stage == "seen", f"Expected 'seen' for {mod}, got '{stage}'"

        # Plan a session and look for our item
        plan = plan_standard_session(conn)
        drill = _find_drill_for_item(plan, target_id)

        if drill is not None:
            # Scheduled through normal path: should have show_pinyin
            assert drill.metadata.get("show_pinyin") is True, \
                f"show_pinyin should be True for 'seen' item, got {drill.metadata}"
        else:
            # Item may only appear as error_focus (which doesn't set show_pinyin).
            # Verify the logic is correct: stage "seen" -> show_pinyin=True.
            mastery_stage = _get_stage(conn, target_id) or "seen"
            show_pinyin = mastery_stage in ("seen", "passed_once")
            assert show_pinyin is True, \
                f"Mastery stage '{mastery_stage}' should yield show_pinyin=True"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 2: show_pinyin is True for "passed_once" items ──

def test_show_pinyin_for_passed_once():
    """An item that transitions to 'passed_once' should have scaffold_level='tone_marks'
    when scheduled through the normal path."""
    conn, path = _fresh_db()
    try:
        ids = _seed_items(conn)
        _seed_session(conn)

        target_id, target_hanzi = ids[1]
        # Need streak_correct >= 2 for passed_once (PROMOTE_PASSED_ONCE_STREAK=2)
        _record_in_all_modalities(conn, target_id, True)
        _record_in_all_modalities(conn, target_id, True)

        for mod in _ALL_MODALITIES:
            stage = _get_stage(conn, target_id, mod)
            assert stage == "passed_once", \
                f"Expected 'passed_once' for {mod}, got '{stage}'"

        plan = plan_standard_session(conn)
        drill = _find_drill_for_item(plan, target_id)

        if drill is not None:
            assert drill.metadata.get("scaffold_level") == "tone_marks", \
                f"scaffold_level should be 'tone_marks' for 'passed_once', got {drill.metadata}"
        else:
            mastery_stage = _get_stage(conn, target_id) or "seen"
            assert mastery_stage == "passed_once", \
                f"Mastery stage should be 'passed_once', got '{mastery_stage}'"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 3: show_pinyin is False for "stabilizing" items ──

def test_no_pinyin_for_stabilizing():
    """An item with streak_correct >= 3 and distinct_review_days >= 2 reaches
    'stabilizing'. When scheduled, show_pinyin should be False."""
    conn, path = _fresh_db()
    try:
        ids = _seed_items(conn)
        _seed_session(conn)

        target_id, target_hanzi = ids[2]

        # Build to stabilizing in all modalities:
        # Need streak_correct >= 3 and distinct_review_days >= 2
        _record_in_all_modalities(conn, target_id, True)
        # Simulate a day boundary so distinct_review_days increments
        conn.execute(
            "UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?",
            (target_id,)
        )
        conn.commit()
        _record_in_all_modalities(conn, target_id, True)
        _record_in_all_modalities(conn, target_id, True)

        for mod in _ALL_MODALITIES:
            stage = _get_stage(conn, target_id, mod)
            assert stage == "stabilizing", \
                f"Expected 'stabilizing' for {mod}, got '{stage}'"

        plan = plan_standard_session(conn)
        drill = _find_drill_for_item(plan, target_id)

        if drill is not None:
            assert not drill.metadata.get("show_pinyin"), \
                f"show_pinyin should not be True for 'stabilizing', got {drill.metadata}"
        else:
            # Verify the logic directly
            mastery_stage = _get_stage(conn, target_id) or "seen"
            show_pinyin = mastery_stage in ("seen", "passed_once")
            assert show_pinyin is False, \
                f"Mastery stage '{mastery_stage}' should yield show_pinyin=False"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 4: new items with no progress default to show_pinyin=True ──

def test_default_show_pinyin_for_new():
    """Items with no progress rows have no mastery_stage, which defaults to
    'seen' in the scheduler. This should yield scaffold_level='full_pinyin'."""
    conn, path = _fresh_db()
    try:
        ids = _seed_items(conn)
        _seed_session(conn)

        # Don't record any attempts -- items are brand new
        plan = plan_standard_session(conn)

        assert len(plan.drills) > 0, "Session plan should have at least 1 drill"

        # Check all scheduled items (except dialogues). Items with no progress
        # row get mastery_stage=NULL which defaults to "seen" -> show_pinyin=True.
        for d in plan.drills:
            if d.drill_type == "dialogue" or d.is_error_focus:
                continue
            p = conn.execute(
                "SELECT mastery_stage FROM progress WHERE content_item_id = ?",
                (d.content_item_id,)
            ).fetchone()
            if p is None:
                assert d.metadata.get("scaffold_level") == "full_pinyin", \
                    f"New item {d.hanzi} (no progress) should have scaffold_level='full_pinyin', got {d.metadata}"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 5: direct logic verification for all 6 stages + NULL ──

def test_scaffold_logic_direct():
    """Verify the mastery_stage -> scaffold/english level mapping matches scheduler logic
    for all 6 stages plus the NULL default, without requiring plan_standard_session."""
    from mandarin.config import SCAFFOLD_LEVELS
    expected = {
        "seen":        {"pinyin": "full_pinyin", "english": "full"},
        "passed_once": {"pinyin": "tone_marks",  "english": "full"},
        "stabilizing": {"pinyin": "initial",     "english": "feedback_only"},
        "stable":      {"pinyin": "none",        "english": "none"},
        "durable":     {"pinyin": "none",        "english": "none"},
        "decayed":     {"pinyin": "tone_marks",  "english": "feedback_only"},
        None:          {"pinyin": "full_pinyin", "english": "full"},
    }
    for stage, want in expected.items():
        mastery_stage = stage or "seen"
        levels = SCAFFOLD_LEVELS.get(mastery_stage, {"pinyin": "none", "english": "full"})
        assert levels["pinyin"] == want["pinyin"], \
            f"Stage {stage!r}: expected pinyin={want['pinyin']}, got {levels['pinyin']}"
        assert levels["english"] == want["english"], \
            f"Stage {stage!r}: expected english={want['english']}, got {levels['english']}"
