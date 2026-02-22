"""Anti-gaming tests — MC distractor length invariants, tier tracking, DrillResult fields.

Tests for:
- English length bounds on MC distractors (short word, long phrase)
- Hanzi length bounds on MC distractors
- Distractor tier tracking (return type, value range)
- DrillResult.distractor_tier field existence and settability
"""

import tempfile
from pathlib import Path

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.drills import generate_mc_options, DrillResult


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


# Seed data: 25 items across HSK 1-3 with varying English/hanzi/pinyin lengths.
_SEED_ITEMS = [
    # HSK 1 — short words
    ("吃", "chī", "eat", 1),
    ("喝", "hē", "drink", 1),
    ("看", "kàn", "look", 1),
    ("走", "zǒu", "walk", 1),
    ("跑", "pǎo", "run", 1),
    ("大", "dà", "big", 1),
    ("小", "xiǎo", "small", 1),
    ("好", "hǎo", "good", 1),
    ("坏", "huài", "bad", 1),
    ("来", "lái", "come", 1),
    # HSK 1 — medium words
    ("你好", "nǐ hǎo", "hello", 1),
    ("谢谢", "xiè xie", "thank you", 1),
    ("朋友", "péng yǒu", "friend", 1),
    # HSK 2 — medium phrases
    ("已经", "yǐ jīng", "already", 2),
    ("准备", "zhǔn bèi", "prepare", 2),
    ("非常", "fēi cháng", "very much", 2),
    ("一起", "yì qǐ", "together", 2),
    ("希望", "xī wàng", "hope for something", 2),
    ("可能", "kě néng", "possibly or maybe", 2),
    ("知道", "zhī dào", "to know about something", 2),
    # HSK 3 — longer phrases
    ("天气越来越冷了", "tiān qì yuè lái yuè lěng le", "the weather is getting colder", 3),
    ("我们应该早点出发", "wǒ men yīng gāi zǎo diǎn chū fā", "we should leave earlier", 3),
    ("这个周末你有空吗", "zhè ge zhōu mò nǐ yǒu kòng ma", "are you free this weekend", 3),
    ("请帮我把这个翻译成中文", "qǐng bāng wǒ bǎ zhè ge fān yì chéng zhōng wén", "please help me translate this into Chinese", 3),
    ("他的中文说得非常流利", "tā de zhōng wén shuō de fēi cháng liú lì", "his Chinese is spoken very fluently", 3),
]


def _seed_items(conn):
    """Insert the full set of seed items into the database."""
    for hanzi, pinyin, english, hsk in _SEED_ITEMS:
        conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status)
            VALUES (?, ?, ?, ?, 'drill_ready')
        """, (hanzi, pinyin, english, hsk))
    conn.commit()


def _get_item_by_english(conn, english_val):
    """Fetch a content_item row as a dict by its English value."""
    row = conn.execute(
        "SELECT * FROM content_item WHERE english = ?", (english_val,)
    ).fetchone()
    assert row is not None, f"Seed item with english={english_val!r} not found"
    return dict(row)


def _get_item_by_hanzi(conn, hanzi_val):
    """Fetch a content_item row as a dict by its hanzi value."""
    row = conn.execute(
        "SELECT * FROM content_item WHERE hanzi = ?", (hanzi_val,)
    ).fetchone()
    assert row is not None, f"Seed item with hanzi={hanzi_val!r} not found"
    return dict(row)


# ── 1. English length invariants in MC options ──────────────────────────────

def test_english_length_short_word():
    """correct='eat' (3 chars). Distractors between 3 and max(18, 5)=18 chars."""
    conn, path = _make_test_db()
    _seed_items(conn)
    item = _get_item_by_english(conn, "eat")

    options, tier = generate_mc_options(conn, item, field="english", n_options=4)

    # Correct value must be in options
    assert "eat" in options, f"Correct value 'eat' missing from options: {options}"

    # Length bounds for correct_len=3: min=max(3, 1)=3, max=max(18, 5)=18
    min_len = 3
    max_len = 18
    for opt in options:
        if opt == "eat":
            continue  # skip correct answer itself
        assert min_len <= len(opt) <= max_len, (
            f"Distractor {opt!r} (len={len(opt)}) outside bounds [{min_len}, {max_len}]"
        )
    conn.close()


def test_english_length_long_phrase():
    """correct='the weather is getting colder' (30 chars).
    Distractors between max(3,12)=12 and max(45,54)=54 chars."""
    conn, path = _make_test_db()
    _seed_items(conn)
    item = _get_item_by_english(conn, "the weather is getting colder")

    options, tier = generate_mc_options(conn, item, field="english", n_options=4)

    correct_val = "the weather is getting colder"
    assert correct_val in options, f"Correct value missing from options: {options}"

    correct_len = len(correct_val)  # 30
    min_len = max(3, int(correct_len * 0.4))   # max(3, 12) = 12
    max_len = max(correct_len + 15, int(correct_len * 1.8))  # max(45, 54) = 54

    for opt in options:
        if opt == correct_val:
            continue
        # Tier-3 fallback distractors may bypass length bounds, but verify
        # the function at least returned the correct answer
        if tier < 3:
            assert min_len <= len(opt) <= max_len, (
                f"Distractor {opt!r} (len={len(opt)}) outside bounds [{min_len}, {max_len}]"
            )
    conn.close()


def test_hanzi_length_bounds():
    """correct='你好' (2 chars). Field='hanzi'.
    min=max(1, 1)=1, max=int(2*1.5)+1=4. Verify distractors within bounds."""
    conn, path = _make_test_db()
    _seed_items(conn)
    item = _get_item_by_hanzi(conn, "你好")

    options, tier = generate_mc_options(conn, item, field="hanzi", n_options=4)

    assert "你好" in options, f"Correct value '你好' missing from options: {options}"

    correct_len = len("你好")  # 2
    min_len = max(1, int(correct_len * 0.5))   # max(1, 1) = 1
    max_len = int(correct_len * 1.5) + 1       # 3 + 1 = 4

    for opt in options:
        if opt == "你好":
            continue
        if tier < 3:
            assert min_len <= len(opt) <= max_len, (
                f"Distractor {opt!r} (len={len(opt)}) outside bounds [{min_len}, {max_len}]"
            )
    conn.close()


# ── 2. Distractor tier tracking ──────────────────────────────

def test_distractor_tier_returned():
    """generate_mc_options returns a tuple of (list, int)."""
    conn, path = _make_test_db()
    _seed_items(conn)
    item = _get_item_by_english(conn, "eat")

    result = generate_mc_options(conn, item, field="english", n_options=4)

    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2, f"Expected 2-tuple, got length {len(result)}"

    options, tier = result
    assert isinstance(options, list), f"options should be list, got {type(options)}"
    assert isinstance(tier, int), f"tier should be int, got {type(tier)}"
    conn.close()


def test_distractor_tier_value_range():
    """max_tier_used should be between 0 and 3."""
    conn, path = _make_test_db()
    _seed_items(conn)

    # Test across multiple items to get a range of tiers
    for english_val in ["eat", "already", "the weather is getting colder"]:
        item = _get_item_by_english(conn, english_val)
        _options, tier = generate_mc_options(conn, item, field="english", n_options=4)
        assert 0 <= tier <= 3, (
            f"Tier {tier} out of range [0, 3] for item {english_val!r}"
        )
    conn.close()


# ── 3. DrillResult has distractor_tier field ──────────────────────────────

def test_drill_result_has_distractor_tier():
    """DrillResult defaults distractor_tier to None."""
    result = DrillResult(
        content_item_id=1,
        modality="reading",
        drill_type="mc",
        correct=True,
    )
    assert hasattr(result, "distractor_tier"), "DrillResult missing distractor_tier field"
    assert result.distractor_tier is None, (
        f"Expected distractor_tier=None, got {result.distractor_tier}"
    )


def test_drill_result_distractor_tier_settable():
    """DrillResult(distractor_tier=2) should store the value."""
    result = DrillResult(
        content_item_id=1,
        modality="reading",
        drill_type="mc",
        correct=True,
        distractor_tier=2,
    )
    assert result.distractor_tier == 2, (
        f"Expected distractor_tier=2, got {result.distractor_tier}"
    )


