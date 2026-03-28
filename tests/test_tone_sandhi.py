"""Tests for tone sandhi classification, DB lookup, and drill generation."""

import sqlite3
import unittest

from mandarin.ai.tone_sandhi import (
    classify_sandhi_context,
    generate_sandhi_drill,
    get_sandhi_pairs,
    _extract_tone_number,
    _split_pinyin_syllables,
    _get_tone_sequence,
    SANDHI_RULES,
)


from tests.shared_db import make_test_db as _make_db


class TestClassifySandhiContext(unittest.TestCase):
    """Tests for classify_sandhi_context()."""

    def test_third_third_rule(self):
        """ni3hao3 triggers 3rd+3rd -> 2nd+3rd rule."""
        results = classify_sandhi_context("你好", "nǐhǎo")
        rule_names = [r["rule_name"] for r in results]
        self.assertIn("third_third", rule_names)
        third = next(r for r in results if r["rule_name"] == "third_third")
        self.assertEqual(third["position"], 0)

    def test_bu_fourth_rule(self):
        """bu4shi4 triggers bu-before-fourth rule."""
        results = classify_sandhi_context("不是", "bùshì")
        rule_names = [r["rule_name"] for r in results]
        self.assertIn("bu_fourth", rule_names)

    def test_yi_tone_change_rule(self):
        """yi1ge4 triggers yi-tone-change rule."""
        results = classify_sandhi_context("一个", "yīgè")
        rule_names = [r["rule_name"] for r in results]
        self.assertIn("yi_tone_change", rule_names)

    def test_yi_before_non_fourth(self):
        """yi1tian1 triggers yi -> yi4 before 1st tone."""
        results = classify_sandhi_context("一天", "yītiān")
        rule_names = [r["rule_name"] for r in results]
        self.assertIn("yi_tone_change", rule_names)

    def test_half_third_rule(self):
        """3rd tone before non-3rd triggers half-third."""
        results = classify_sandhi_context("你们", "nǐmen")
        rule_names = [r["rule_name"] for r in results]
        self.assertIn("half_third", rule_names)

    def test_empty_string(self):
        """Empty hanzi returns empty list."""
        results = classify_sandhi_context("", "")
        self.assertEqual(results, [])

    def test_single_char_no_sandhi(self):
        """A single character cannot trigger sandhi (needs at least two)."""
        results = classify_sandhi_context("好", "hǎo")
        # Single char -> no consecutive-tone rules fire
        self.assertEqual(results, [])

    def test_no_sandhi_applicable(self):
        """Two first-tone characters: no sandhi rule should fire."""
        results = classify_sandhi_context("天天", "tiāntiān")
        # No rule should match (1st+1st is not a sandhi trigger)
        substantive = [
            r for r in results
            if r["rule_name"] in ("third_third", "bu_fourth", "yi_tone_change")
        ]
        self.assertEqual(substantive, [])

    def test_result_dict_keys(self):
        """Each result dict has the required keys."""
        results = classify_sandhi_context("你好", "nǐhǎo")
        self.assertTrue(len(results) > 0)
        for r in results:
            for key in ("rule_name", "position", "original_pinyin",
                        "actual_pinyin", "explanation"):
                self.assertIn(key, r, f"Missing key: {key}")


class TestPinyinHelpers(unittest.TestCase):
    """Tests for internal pinyin helpers."""

    def test_extract_tone_third(self):
        self.assertEqual(_extract_tone_number("nǐ"), 3)

    def test_extract_tone_fourth(self):
        self.assertEqual(_extract_tone_number("shì"), 4)

    def test_extract_tone_first(self):
        self.assertEqual(_extract_tone_number("yī"), 1)

    def test_extract_tone_neutral(self):
        self.assertEqual(_extract_tone_number("de"), 0)

    def test_extract_tone_digit_notation(self):
        self.assertEqual(_extract_tone_number("ni3"), 3)

    def test_split_space_separated(self):
        parts = _split_pinyin_syllables("nǐ hǎo")
        self.assertEqual(len(parts), 2)

    def test_split_run_together(self):
        parts = _split_pinyin_syllables("nǐhǎo")
        self.assertEqual(len(parts), 2)

    def test_split_empty(self):
        self.assertEqual(_split_pinyin_syllables(""), [])

    def test_tone_sequence(self):
        tones = _get_tone_sequence("你好", "nǐhǎo")
        self.assertEqual(tones, [3, 3])


class TestGetSandhiPairs(unittest.TestCase):
    """Tests for get_sandhi_pairs() with seeded DB data."""

    def setUp(self):
        self.conn = _make_db()
        # Seed content_item rows that should trigger sandhi rules
        self.conn.executemany(
            """INSERT INTO content_item (hanzi, pinyin, english, hsk_level,
               status, review_status) VALUES (?, ?, ?, ?, 'drill_ready', 'approved')""",
            [
                ("你好", "nǐ hǎo", "hello", 1),           # third_third
                ("不是", "bù shì", "is not", 1),           # bu_fourth
                ("一个", "yī gè", "one (measure word)", 1), # yi_tone_change
                ("天天", "tiān tiān", "every day", 1),      # no sandhi
                ("好", "hǎo", "good", 1),                   # single char, filtered by LENGTH >= 2
            ],
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_returns_sandhi_items(self):
        """get_sandhi_pairs returns items that trigger substantive sandhi rules."""
        pairs = get_sandhi_pairs(self.conn, hsk_level=9)
        self.assertTrue(len(pairs) >= 3, f"Expected >= 3 sandhi pairs, got {len(pairs)}")

    def test_excludes_no_sandhi(self):
        """Items with no substantive sandhi rule are excluded."""
        pairs = get_sandhi_pairs(self.conn, hsk_level=9)
        hanzi_list = [p["hanzi"] for p in pairs]
        self.assertNotIn("天天", hanzi_list)

    def test_excludes_single_char(self):
        """Single character items are excluded (LENGTH >= 2 filter)."""
        pairs = get_sandhi_pairs(self.conn, hsk_level=9)
        hanzi_list = [p["hanzi"] for p in pairs]
        self.assertNotIn("好", hanzi_list)

    def test_pair_dict_keys(self):
        """Each pair dict has required keys."""
        pairs = get_sandhi_pairs(self.conn, hsk_level=9)
        self.assertTrue(len(pairs) > 0)
        for p in pairs:
            for key in ("item_id", "hanzi", "pinyin", "sandhi_rule",
                        "original_pronunciation", "actual_pronunciation"):
                self.assertIn(key, p, f"Missing key: {key}")

    def test_hsk_level_filter(self):
        """Items above requested HSK level are excluded."""
        self.conn.execute(
            """INSERT INTO content_item (hanzi, pinyin, english, hsk_level,
               status, review_status) VALUES (?, ?, ?, ?, 'drill_ready', 'approved')""",
            ("不对", "bù duì", "incorrect", 6),
        )
        self.conn.commit()
        pairs = get_sandhi_pairs(self.conn, hsk_level=2)
        hanzi_list = [p["hanzi"] for p in pairs]
        self.assertNotIn("不对", hanzi_list)

    def test_empty_table(self):
        """Empty content_item table returns empty list."""
        empty_conn = _make_db()
        pairs = get_sandhi_pairs(empty_conn, hsk_level=9)
        self.assertEqual(pairs, [])
        empty_conn.close()

    def test_missing_table_returns_empty(self):
        """Missing content_item table returns empty list (OperationalError caught)."""
        bare_conn = sqlite3.connect(":memory:")
        bare_conn.row_factory = sqlite3.Row
        pairs = get_sandhi_pairs(bare_conn)
        self.assertEqual(pairs, [])
        bare_conn.close()


class TestGenerateSandhiDrill(unittest.TestCase):
    """Tests for generate_sandhi_drill()."""

    def setUp(self):
        self.conn = _make_db()

    def tearDown(self):
        self.conn.close()

    def test_drill_required_keys(self):
        """Returned drill dict has all required keys."""
        item = {"hanzi": "你好", "pinyin": "nǐ hǎo", "sandhi_rule": "third_third"}
        drill = generate_sandhi_drill(self.conn, item)
        for key in ("type", "hanzi", "correct_answer", "distractor"):
            self.assertIn(key, drill, f"Missing key: {key}")

    def test_drill_type_value(self):
        """Drill type is 'sandhi_contrast'."""
        item = {"hanzi": "不是", "pinyin": "bù shì", "sandhi_rule": "bu_fourth"}
        drill = generate_sandhi_drill(self.conn, item)
        self.assertEqual(drill["type"], "sandhi_contrast")

    def test_drill_correct_differs_from_distractor(self):
        """Correct answer and distractor should differ."""
        item = {"hanzi": "你好", "pinyin": "nǐ hǎo", "sandhi_rule": "third_third"}
        drill = generate_sandhi_drill(self.conn, item)
        self.assertNotEqual(drill["correct_answer"], drill["distractor"])

    def test_drill_hanzi_matches(self):
        """Drill hanzi matches input item."""
        item = {"hanzi": "一个", "pinyin": "yī gè", "sandhi_rule": "yi_tone_change"}
        drill = generate_sandhi_drill(self.conn, item)
        self.assertEqual(drill["hanzi"], "一个")

    def test_drill_explanation_present(self):
        """Drill has a non-empty explanation."""
        item = {"hanzi": "你好", "pinyin": "nǐ hǎo", "sandhi_rule": "third_third"}
        drill = generate_sandhi_drill(self.conn, item)
        self.assertIn("explanation", drill)
        self.assertTrue(len(drill["explanation"]) > 0)

    def test_drill_rule_name_present(self):
        """Drill has a rule_name field."""
        item = {"hanzi": "不是", "pinyin": "bù shì", "sandhi_rule": "bu_fourth"}
        drill = generate_sandhi_drill(self.conn, item)
        self.assertIn("rule_name", drill)
        self.assertEqual(drill["rule_name"], "bu_fourth")

    def test_fallback_no_sandhi(self):
        """Item with no sandhi context still returns a valid drill dict."""
        item = {"hanzi": "天天", "pinyin": "tiān tiān", "sandhi_rule": ""}
        drill = generate_sandhi_drill(self.conn, item)
        self.assertIn("type", drill)
        self.assertEqual(drill["type"], "sandhi_contrast")


if __name__ == "__main__":
    unittest.main()
