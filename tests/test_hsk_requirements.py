"""Validation tests for HSK requirements, grammar linking, and data integrity."""

import json
import sqlite3
import tempfile
from pathlib import Path

from mandarin import db
from mandarin.db.core import _migrate
from mandarin.grammar_seed import GRAMMAR_POINTS, SKILLS, seed_grammar_and_skills
from mandarin.grammar_linker import link_grammar_to_content, link_skills_to_content, link_all
from mandarin.diagnostics import HSK_CUMULATIVE


DATA_DIR = Path(__file__).parent.parent / "data"
HSK_REQ_PATH = DATA_DIR / "hsk_requirements.json"


def _make_test_db():
    """Create a fresh test database with schema + migrations + seed profile."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn, path


def _seed_items(conn, n=50):
    """Insert dummy content items across HSK 1-3."""
    test_hanzi = [
        # HSK 1 items with grammar-relevant characters
        ("我是学生", "wǒ shì xuéshēng", "I am a student", 1),
        ("她很高兴", "tā hěn gāoxìng", "She is very happy", 1),
        ("我不喝茶", "wǒ bù hē chá", "I don't drink tea", 1),
        ("他没去", "tā méi qù", "He didn't go", 1),
        ("我的书", "wǒ de shū", "my book", 1),
        ("我吃了饭", "wǒ chī le fàn", "I ate", 1),
        ("你好吗", "nǐ hǎo ma", "How are you?", 1),
        ("你呢", "nǐ ne", "And you?", 1),
        ("一个人", "yī gè rén", "one person", 1),
        ("我在北京", "wǒ zài Běijīng", "I am in Beijing", 1),
        ("你好", "nǐ hǎo", "hello", 1),
        ("老师", "lǎoshī", "teacher", 1),
        ("吃", "chī", "eat", 1),
        ("水", "shuǐ", "water", 1),
        ("谢谢", "xièxie", "thank you", 1),
        # HSK 2 items
        ("我去过中国", "wǒ qù guò Zhōngguó", "I've been to China", 2),
        ("他正在看书", "tā zhèngzài kàn shū", "He is reading", 2),
        ("他比我高", "tā bǐ wǒ gāo", "He is taller than me", 2),
        ("我想去", "wǒ xiǎng qù", "I want to go", 2),
        ("你可以走了", "nǐ kěyǐ zǒu le", "You can go now", 2),
        ("他说得很好", "tā shuō de hěn hǎo", "He speaks well", 2),
        ("从北京到上海", "cóng Běijīng dào Shànghǎi", "From Beijing to Shanghai", 2),
        ("吃饭的时候", "chīfàn de shíhou", "When eating", 2),
        ("买东西", "mǎi dōngxi", "buy things", 2),
        ("多少钱", "duōshao qián", "how much money", 2),
        # HSK 3 items
        ("把门关上", "bǎ mén guānshang", "Close the door", 3),
        ("苹果被吃了", "píngguǒ bèi chī le", "The apple was eaten", 3),
        ("我是坐飞机来的", "wǒ shì zuò fēijī lái de", "I came by plane", 3),
        ("天气越来越冷", "tiānqì yuèláiyuè lěng", "Weather is getting colder", 3),
        ("又便宜又好吃", "yòu piányi yòu hǎochī", "Both cheap and delicious", 3),
        ("找到了", "zhǎodào le", "found it", 3),
        ("走进来", "zǒu jìnlái", "walk in", 3),
        ("除了中文以外", "chúle zhōngwén yǐwài", "besides Chinese", 3),
    ]
    for hanzi, pinyin, english, hsk in test_hanzi:
        conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status)
            VALUES (?, ?, ?, ?, 'drill_ready')
        """, (hanzi, pinyin, english, hsk))
    conn.commit()


# ── Test 1: hsk_requirements.json parses and has levels 1-9 ──

def test_hsk_requirements_parses():
    """hsk_requirements.json parses without error and has levels 1-9."""
    assert HSK_REQ_PATH.exists(), f"Missing {HSK_REQ_PATH}"
    data = json.loads(HSK_REQ_PATH.read_text())
    assert "levels" in data
    assert "source" in data
    for level in range(1, 10):
        assert str(level) in data["levels"], f"Missing level {level}"
        level_data = data["levels"][str(level)]
        assert "vocab_count" in level_data
        assert "grammar" in level_data
        assert "skills" in level_data
        assert "listening" in level_data
        assert "reading" in level_data


# ── Test 2: Every grammar point in grammar_seed.py has an entry in hsk_requirements.json ──

def test_grammar_points_in_requirements():
    """Every grammar point name appears in hsk_requirements.json."""
    data = json.loads(HSK_REQ_PATH.read_text())
    all_req_grammar = set()
    for level_data in data["levels"].values():
        all_req_grammar.update(level_data.get("grammar", []))

    for gp in GRAMMAR_POINTS:
        assert gp["name"] in all_req_grammar, (
            f"Grammar point '{gp['name']}' not found in hsk_requirements.json"
        )


# ── Test 3: Every skill in grammar_seed.py has an entry in hsk_requirements.json ──

def test_skills_in_requirements():
    """Every skill name appears in hsk_requirements.json."""
    data = json.loads(HSK_REQ_PATH.read_text())
    all_req_skills = set()
    for level_data in data["levels"].values():
        all_req_skills.update(level_data.get("skills", []))

    for sk in SKILLS:
        # Phonetic skills (tone pair discrimination, third tone sandhi) may not be
        # in the requirements if they're training-internal
        if sk["category"] == "phonetic":
            continue
        assert sk["name"] in all_req_skills, (
            f"Skill '{sk['name']}' not found in hsk_requirements.json"
        )


# ── Test 4: After linking, content_grammar has rows ──

def test_grammar_linking_produces_rows():
    """After running link_grammar_to_content(), content_grammar has > 0 rows."""
    conn, path = _make_test_db()
    try:
        _seed_items(conn)
        seed_grammar_and_skills(conn)
        links = link_grammar_to_content(conn)
        count = conn.execute("SELECT COUNT(*) FROM content_grammar").fetchone()[0]
        assert count > 0, f"Expected content_grammar rows, got {count}"
        assert links > 0, f"Expected links created, got {links}"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 5: After linking, content_skill has rows ──

def test_skill_linking_produces_rows():
    """After running link_skills_to_content(), content_skill has > 0 rows."""
    conn, path = _make_test_db()
    try:
        _seed_items(conn)
        seed_grammar_and_skills(conn)
        links = link_skills_to_content(conn)
        count = conn.execute("SELECT COUNT(*) FROM content_skill").fetchone()[0]
        assert count > 0, f"Expected content_skill rows, got {count}"
        assert links > 0, f"Expected links created, got {links}"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 6: HSK vocab counts match HSK_CUMULATIVE ──

def test_vocab_counts_match():
    """HSK vocab counts in hsk_requirements.json match HSK_CUMULATIVE in diagnostics.py."""
    data = json.loads(HSK_REQ_PATH.read_text())
    for level_str, level_data in data["levels"].items():
        level = int(level_str)
        if level in HSK_CUMULATIVE:
            assert level_data["vocab_count"] == HSK_CUMULATIVE[level], (
                f"HSK {level}: requirements says {level_data['vocab_count']}, "
                f"HSK_CUMULATIVE says {HSK_CUMULATIVE[level]}"
            )


# ── Test 7: link_all runs without error ──

def test_link_all():
    """link_all() runs without error and creates both grammar and skill links."""
    conn, path = _make_test_db()
    try:
        _seed_items(conn)
        seed_grammar_and_skills(conn)
        g_links, s_links = link_all(conn)
        assert g_links > 0, "No grammar links created"
        assert s_links > 0, "No skill links created"
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 8: format_confidence produces readable output ──

def test_format_confidence():
    """format_confidence returns descriptive strings at various levels."""
    from mandarin.diagnostics import format_confidence
    assert "no data" in format_confidence(0.0, 0)
    assert "very low" in format_confidence(0.1, 10)
    assert "low" in format_confidence(0.2, 30)
    assert "moderate" in format_confidence(0.4, 80)
    assert "%" in format_confidence(0.6, 120)


# ── Test 9: estimate_levels_lite works on empty DB ──

def test_estimate_levels_lite_empty():
    """estimate_levels_lite returns defaults on a DB with no progress."""
    from mandarin.diagnostics import estimate_levels_lite
    conn, path = _make_test_db()
    try:
        _seed_items(conn)
        levels = estimate_levels_lite(conn)
        assert "reading" in levels
        assert "listening" in levels
        assert levels["reading"]["level"] == 1.0
        assert levels["reading"]["confidence"] == 0.0
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 10: get_mastery_by_hsk returns seen/not_seen ──

def test_mastery_includes_seen():
    """get_mastery_by_hsk returns seen and not_seen counts."""
    conn, path = _make_test_db()
    try:
        _seed_items(conn)
        mastery = db.get_mastery_by_hsk(conn)
        for level, m in mastery.items():
            assert "seen" in m, f"Missing 'seen' for HSK {level}"
            assert "not_seen" in m, f"Missing 'not_seen' for HSK {level}"
            assert m["seen"] + m["not_seen"] == m["total"]
    finally:
        conn.close()
        path.unlink(missing_ok=True)


# ── Test 11: Diagnostics loads HSK registry ──

def test_diagnostics_uses_registry():
    """diagnostics.get_hsk_requirements loads data and returns accuracy targets."""
    from mandarin.diagnostics import get_hsk_requirements
    reqs = get_hsk_requirements(2)
    assert reqs is not None, "get_hsk_requirements(2) returned None"
    assert "listening" in reqs, "Missing 'listening' in HSK 2 requirements"
    assert "reading" in reqs, "Missing 'reading' in HSK 2 requirements"
    assert "accuracy_target" in reqs["listening"]
    assert "accuracy_target" in reqs["reading"]
    assert 0 < reqs["listening"]["accuracy_target"] <= 1.0
    assert 0 < reqs["reading"]["accuracy_target"] <= 1.0


# ── Test 12: Registry values used in projections ──

def test_registry_thresholds_per_level():
    """Different HSK levels have different accuracy targets in the registry."""
    from mandarin.diagnostics import get_hsk_requirements
    reqs_1 = get_hsk_requirements(1)
    reqs_6 = get_hsk_requirements(6)
    assert reqs_1 is not None and reqs_6 is not None
    # Higher levels should have equal or higher targets
    assert reqs_6["listening"]["accuracy_target"] >= reqs_1["listening"]["accuracy_target"]

