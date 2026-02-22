"""Tests for listening drill types: detail question heuristic, tone drill, dictation drill.

Covers:
- generate_detail_question keyword heuristic (number, time, person, location, default)
- run_listening_tone_drill (correct and wrong MC answers)
- run_listening_dictation_drill (correct and wrong free-form answers)
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.drills import (
    generate_detail_question,
    run_listening_tone_drill,
    run_listening_dictation_drill,
    DrillResult,
)


# ── Test DB helpers ──────────────────────────────

def _make_test_db():
    """Create a fresh test database with schema + migrations + seed profile."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


def _seed_toned_items(conn, n=12):
    """Seed items with toned pinyin for tone/dictation drills."""
    items = [
        ("你好", "nǐ hǎo", "hello", 1, "vocab"),
        ("谢谢", "xiè xie", "thank you", 1, "vocab"),
        ("再见", "zài jiàn", "goodbye", 1, "vocab"),
        ("学生", "xué shēng", "student", 1, "vocab"),
        ("老师", "lǎo shī", "teacher", 1, "vocab"),
        ("中国", "zhōng guó", "China", 1, "vocab"),
        ("朋友", "péng yǒu", "friend", 1, "vocab"),
        ("工作", "gōng zuò", "work", 2, "vocab"),
        ("学校", "xué xiào", "school", 2, "vocab"),
        ("医院", "yī yuàn", "hospital", 2, "vocab"),
        ("明天", "míng tiān", "tomorrow", 1, "vocab"),
        ("今天", "jīn tiān", "today", 1, "vocab"),
    ]
    # Pad to n if needed
    for i in range(len(items), n):
        items.append((f"字{i}", f"zì{i}", f"word{i}", 1, "vocab"))
    ids = []
    for hanzi, pinyin, english, hsk, itype in items[:n]:
        cur = conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status, item_type)
            VALUES (?, ?, ?, ?, 'drill_ready', ?)
        """, (hanzi, pinyin, english, hsk, itype))
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def _make_item_dict(conn, item_id):
    """Fetch an item as a dict from the DB."""
    row = conn.execute("SELECT * FROM content_item WHERE id = ?", (item_id,)).fetchone()
    return dict(row)


# ── Detail question heuristic tests ──────────────────────────────

def test_detail_question_number():
    """English containing a number word should produce 'How many?' question."""
    q = generate_detail_question("I have three books")
    assert "How many" in q, f"expected 'How many' in: {q}"


def test_detail_question_time():
    """English containing a time word should produce 'When?' question."""
    q = generate_detail_question("I go running in the morning")
    assert "When" in q, f"expected 'When' in: {q}"


def test_detail_question_person():
    """English containing a person reference should produce 'Who?' question."""
    q = generate_detail_question("The teacher is very kind")
    assert "Who" in q, f"expected 'Who' in: {q}"


def test_detail_question_location():
    """English containing a location word should produce 'Where?' question."""
    q = generate_detail_question("We arrived at school on time")
    assert "Where" in q, f"expected 'Where' in: {q}"


def test_detail_question_default():
    """English without any keyword should produce the default question."""
    q = generate_detail_question("It is very interesting")
    assert q == "What is being described?", f"expected default question, got: {q}"


# ── Listening tone drill tests ──────────────────────────────

def test_listening_tone_correct():
    """Correct pinyin selection in tone drill should return correct=True."""
    conn, path = _make_test_db()
    ids = _seed_toned_items(conn)
    item = _make_item_dict(conn, ids[0])  # 你好 / nǐ hǎo
    correct_pinyin = item["pinyin"]

    output = []
    def show_fn(text, end="\n"):
        output.append(text)

    # The drill shows numbered options; we need to find which number is correct.
    # Strategy: capture options from show_fn, then find the correct one.
    call_count = [0]
    captured_options = []

    def show_fn_capture(text, end="\n"):
        output.append(text)
        # Options are lines like "  1. nǐ hǎo"
        stripped = text.strip()
        if stripped and stripped[0].isdigit() and ". " in stripped:
            captured_options.append(stripped)

    # We need a two-phase approach: first call to discover option order,
    # then provide the right answer. Use a closure that figures out the answer.
    answer_given = [False]
    def input_fn(prompt):
        # Find which option matches the correct pinyin
        for opt in captured_options:
            num, _, text = opt.partition(". ")
            if text.strip() == correct_pinyin:
                return num.strip()
        return "1"  # fallback

    try:
        result = run_listening_tone_drill(item, conn, show_fn_capture, input_fn,
                                          audio_enabled=False)
        assert isinstance(result, DrillResult)
        assert result.correct is True, f"expected correct=True, got {result.correct}"
        assert result.drill_type == "listening_tone"
        assert result.expected_answer == correct_pinyin
    finally:
        conn.close()
        os.unlink(str(path))


def test_listening_tone_wrong():
    """Wrong pinyin selection in tone drill should return correct=False."""
    conn, path = _make_test_db()
    ids = _seed_toned_items(conn)
    item = _make_item_dict(conn, ids[0])  # 你好 / nǐ hǎo
    correct_pinyin = item["pinyin"]

    captured_options = []
    def show_fn(text, end="\n"):
        stripped = text.strip()
        if stripped and stripped[0].isdigit() and ". " in stripped:
            captured_options.append(stripped)

    def input_fn(prompt):
        # Pick the option that is NOT the correct pinyin
        for opt in captured_options:
            num, _, text = opt.partition(". ")
            if text.strip() != correct_pinyin:
                return num.strip()
        return "1"  # fallback (shouldn't happen with 4 options)

    try:
        result = run_listening_tone_drill(item, conn, show_fn, input_fn,
                                          audio_enabled=False)
        assert isinstance(result, DrillResult)
        assert result.correct is False, f"expected correct=False, got {result.correct}"
        assert result.drill_type == "listening_tone"
        assert result.error_type.startswith("tone"), f"expected tone error, got {result.error_type}"
    finally:
        conn.close()
        os.unlink(str(path))


# ── Listening dictation drill tests ──────────────────────────────

def test_listening_dictation_correct():
    """Exact hanzi match in dictation drill should return correct=True."""
    conn, path = _make_test_db()
    ids = _seed_toned_items(conn)
    item = _make_item_dict(conn, ids[0])  # 你好

    output = []
    def show_fn(text, end="\n"):
        output.append(text)

    def input_fn(prompt):
        return item["hanzi"]  # exact match

    try:
        result = run_listening_dictation_drill(item, conn, show_fn, input_fn,
                                               audio_enabled=False)
        assert isinstance(result, DrillResult)
        assert result.correct is True, f"expected correct=True, got {result.correct}"
        assert result.drill_type == "listening_dictation"
        assert result.expected_answer == item["hanzi"]
        assert result.user_answer == item["hanzi"]
    finally:
        conn.close()
        os.unlink(str(path))


def test_listening_dictation_wrong():
    """Wrong hanzi in dictation drill should return correct=False."""
    conn, path = _make_test_db()
    ids = _seed_toned_items(conn)
    item = _make_item_dict(conn, ids[0])  # 你好

    output = []
    def show_fn(text, end="\n"):
        output.append(text)

    def input_fn(prompt):
        return "你坏"  # wrong hanzi

    try:
        result = run_listening_dictation_drill(item, conn, show_fn, input_fn,
                                               audio_enabled=False)
        assert isinstance(result, DrillResult)
        assert result.correct is False, f"expected correct=False, got {result.correct}"
        assert result.drill_type == "listening_dictation"
        assert result.user_answer == "你坏"
        assert result.expected_answer == item["hanzi"]
        assert result.error_type == "vocab"
    finally:
        conn.close()
        os.unlink(str(path))


