"""Content integrity tests -- validates all Phase 1-4 data assets.

Tests verify:
- Reading passages: valid JSON, required fields, HSK levels 1-9
- Grammar examples: all 62 grammar points have 3+ example sentences
- Personalization: all 5 domains have HSK 1 sentences (beginner gap filled)
- Scenario anti-gaming: no cartoonish registers, minimum option lengths,
  at least one scenario per HSK level where shortest option isn't the worst
- HSK canonical data: all 9 files exist with expected item counts
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


# ---- TestReadingPassages ----

PASSAGE_FILE = DATA_DIR / "reading_passages.json"
REQUIRED_FIELDS = {"id", "title", "title_zh", "hsk_level", "text_zh",
                   "text_pinyin", "text_en", "questions"}
QUESTION_FIELDS = {"q_zh", "q_en", "type", "options", "difficulty"}


def test_passage_file_exists():
    assert PASSAGE_FILE.exists()


def test_passage_valid_json():
    data = json.loads(PASSAGE_FILE.read_text(encoding="utf-8"))
    assert "passages" in data


def test_at_least_six_passages():
    data = json.loads(PASSAGE_FILE.read_text(encoding="utf-8"))
    assert len(data["passages"]) >= 6


def test_passage_required_fields_present():
    data = json.loads(PASSAGE_FILE.read_text(encoding="utf-8"))
    for p in data["passages"]:
        for field in REQUIRED_FIELDS:
            assert field in p, f"Passage {p.get('id', '?')} missing '{field}'"
        for q in p["questions"]:
            for field in QUESTION_FIELDS:
                assert field in q, \
                    f"Question in {p['id']} missing '{field}'"


def test_passage_hsk_levels_1_through_9():
    data = json.loads(PASSAGE_FILE.read_text(encoding="utf-8"))
    levels = {p["hsk_level"] for p in data["passages"]}
    for lvl in range(1, 10):
        assert lvl in levels, f"No passage at HSK {lvl}"


def test_each_passage_has_questions():
    data = json.loads(PASSAGE_FILE.read_text(encoding="utf-8"))
    for p in data["passages"]:
        assert len(p["questions"]) > 0, \
            f"Passage {p['id']} has no questions"


# ---- TestGrammarExamples ----

def test_all_grammar_points_have_examples():
    from mandarin.grammar_seed import GRAMMAR_POINTS
    for gp in GRAMMAR_POINTS:
        examples = gp.get("examples", [])
        assert len(examples) >= 3, \
            f"Grammar point '{gp['name']}' has {len(examples)} examples, need 3+"


def test_example_fields():
    from mandarin.grammar_seed import GRAMMAR_POINTS
    for gp in GRAMMAR_POINTS:
        for ex in gp.get("examples", []):
            assert "zh" in ex, f"Example in '{gp['name']}' missing 'zh'"
            assert "en" in ex, f"Example in '{gp['name']}' missing 'en'"
            assert "pinyin" in ex, f"Example in '{gp['name']}' missing 'pinyin'"


def test_grammar_points_minimum():
    from mandarin.grammar_seed import GRAMMAR_POINTS
    assert len(GRAMMAR_POINTS) >= 300, f"Expected >=300 grammar points, got {len(GRAMMAR_POINTS)}"


# ---- TestPersonalizationCoverage ----

CONTEXT_DIR = DATA_DIR / "contexts"


def test_all_domains_have_hsk1():
    for domain_file in sorted(CONTEXT_DIR.glob("*.json")):
        data = json.loads(domain_file.read_text(encoding="utf-8"))
        sentences = data.get("sentences", [])
        hsk1 = [s for s in sentences if s.get("hsk_level") == 1]
        assert len(hsk1) >= 2, \
            f"{domain_file.stem}: only {len(hsk1)} HSK 1 sentences, need 2+"


def test_total_hsk1_at_least_13():
    """After filling, should have 13+ HSK 1 sentences total."""
    total = 0
    for domain_file in sorted(CONTEXT_DIR.glob("*.json")):
        data = json.loads(domain_file.read_text(encoding="utf-8"))
        total += sum(1 for s in data.get("sentences", [])
                    if s.get("hsk_level") == 1)
    assert total >= 13


def test_all_domains_cover_hsk_4_through_9():
    """Every domain should have at least 2 sentences per HSK 4-9 level."""
    for domain_file in sorted(CONTEXT_DIR.glob("*.json")):
        data = json.loads(domain_file.read_text(encoding="utf-8"))
        sentences = data.get("sentences", [])
        for lvl in range(4, 10):
            count = sum(1 for s in sentences if s.get("hsk_level") == lvl)
            assert count >= 2, \
                f"{domain_file.stem}: only {count} HSK {lvl} sentences, need 2+"


def test_sentence_fields():
    required = {"hanzi", "pinyin", "english", "hsk_level"}
    for domain_file in sorted(CONTEXT_DIR.glob("*.json")):
        data = json.loads(domain_file.read_text(encoding="utf-8"))
        for s in data.get("sentences", []):
            for field in required:
                assert field in s, \
                    f"{domain_file.stem} sentence missing '{field}'"


# ---- TestScenarioAntiGaming ----

SCENARIO_DIR = DATA_DIR / "scenarios"


def test_no_cartoonish_registers():
    """No option should have register 'rude' or 'demanding'."""
    banned = {"rude", "demanding"}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for turn in data["tree"]["turns"]:
            if turn.get("speaker") != "player":
                continue
            for opt in turn.get("options", []):
                reg = opt.get("register", "neutral")
                assert reg not in banned, \
                    f"{path.name}: option '{opt['text_zh'][:10]}...' has banned register '{reg}'"


def test_minimum_option_length():
    """All player options should be at least 2 characters."""
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for turn in data["tree"]["turns"]:
            if turn.get("speaker") != "player":
                continue
            for opt in turn.get("options", []):
                assert len(opt["text_zh"]) >= 2, \
                    f"{path.name}: option '{opt['text_zh']}' too short ({len(opt['text_zh'])} chars)"


def test_at_least_one_score_1():
    """Every player turn should have at least one 1.0-scoring option."""
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for i, turn in enumerate(data["tree"]["turns"]):
            if turn.get("speaker") != "player":
                continue
            scores = [opt["score"] for opt in turn.get("options", [])]
            assert 1.0 in scores, \
                f"{path.name} turn {i}: no 1.0-scoring option"


# ---- TestHSKCanonicalData ----

HSK_DIR = DATA_DIR / "hsk"

# Minimum expected items per level
HSK_MIN_COUNTS = {
    1: 500, 2: 700, 3: 900,
    4: 900, 5: 1000, 6: 1000,
    7: 1800, 8: 1800, 9: 1800,
}


def test_all_hsk_files_exist_with_items():
    for level, min_count in HSK_MIN_COUNTS.items():
        path = HSK_DIR / f"hsk{level}.json"
        assert path.exists(), f"Missing {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data.get("items", [])) >= min_count, \
            f"HSK {level} has {len(data.get('items', []))} items, need {min_count}+"


def test_no_duplicate_hanzi_within_level():
    for level in range(1, 10):
        path = HSK_DIR / f"hsk{level}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        hanzi_list = [item["hanzi"] for item in items]
        assert len(hanzi_list) == len(set(hanzi_list)), \
            f"HSK {level} has duplicate hanzi entries"


def test_all_hsk_items_have_required_fields():
    required = {"hanzi", "pinyin", "english"}
    for level in range(1, 10):
        path = HSK_DIR / f"hsk{level}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("items", []):
            for field in required:
                assert field in item, \
                    f"HSK {level} item missing '{field}'"
                assert item[field], \
                    f"HSK {level} item has empty '{field}': {item.get('hanzi', '?')}"
