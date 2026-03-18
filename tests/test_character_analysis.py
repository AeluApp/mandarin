"""Tests for character decomposition and radical/phonetic family analysis."""

import unittest

from mandarin.ai.character_analysis import (
    decompose,
    get_component_family,
    get_phonetic_family,
    get_radical_for_character,
    generate_decomposition_overlay,
    _CHAR_TO_RADICAL,
    _CHAR_TO_PHONETIC,
)


class TestDecompose(unittest.TestCase):
    """Tests for decompose() — single character decomposition."""

    def test_qing_has_radical(self):
        """decompose('清') returns a dict with a radical (water radical)."""
        result = decompose("清")
        self.assertIsNotNone(result)
        self.assertIn("radical", result)
        self.assertEqual(result["radical"], "氵")
        self.assertEqual(result["radical_meaning"], "water")

    def test_qing_has_phonetic(self):
        """decompose('清') returns a dict with phonetic component 青."""
        result = decompose("清")
        self.assertIsNotNone(result)
        self.assertIn("phonetic", result)
        self.assertEqual(result["phonetic"], "青")

    def test_qing_has_family_examples(self):
        """decompose('清') includes family examples from the 青 phonetic group."""
        result = decompose("清")
        self.assertIsNotNone(result)
        self.assertIn("family_examples", result)
        self.assertIsInstance(result["family_examples"], list)
        self.assertTrue(len(result["family_examples"]) > 0)

    def test_character_key_present(self):
        """Returned dict includes the input character."""
        result = decompose("清")
        self.assertIsNotNone(result)
        self.assertEqual(result["character"], "清")

    def test_radical_only_character(self):
        """A character with radical data but no phonetic data still decomposes."""
        # 雪 has rain radical but may not have phonetic family entry
        result = decompose("雪")
        self.assertIsNotNone(result)
        self.assertIn("radical", result)
        self.assertEqual(result["radical"], "雨")
        self.assertEqual(result["radical_meaning"], "rain")

    def test_no_decomposition_returns_none(self):
        """A CJK character with no data in our tables returns None."""
        # Use an uncommon CJK character unlikely to be in our curated data
        result = decompose("鬯")  # archaic character for libation
        self.assertIsNone(result)

    def test_non_cjk_returns_none(self):
        """Non-CJK input (ASCII, latin, etc.) returns None."""
        self.assertIsNone(decompose("A"))
        self.assertIsNone(decompose("1"))
        self.assertIsNone(decompose("!"))

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        self.assertIsNone(decompose(""))

    def test_multi_char_returns_none(self):
        """Multi-character input returns None (single char only)."""
        self.assertIsNone(decompose("你好"))
        self.assertIsNone(decompose("清水"))

    def test_phonetic_hint_present(self):
        """decompose() includes phonetic_hint when phonetic data exists."""
        result = decompose("清")
        self.assertIsNotNone(result)
        self.assertIn("phonetic_hint", result)
        self.assertIsInstance(result["phonetic_hint"], str)
        self.assertTrue(len(result["phonetic_hint"]) > 0)

    def test_radical_pinyin_present(self):
        """decompose() includes radical_pinyin when radical data exists."""
        result = decompose("河")
        self.assertIsNotNone(result)
        self.assertIn("radical_pinyin", result)
        self.assertEqual(result["radical_pinyin"], "shuǐ")


class TestGetComponentFamily(unittest.TestCase):
    """Tests for get_component_family() — characters sharing a radical."""

    def test_water_radical_returns_list(self):
        """Water radical returns a non-empty list of characters."""
        family = get_component_family("氵")
        self.assertIsInstance(family, list)
        self.assertTrue(len(family) > 0)

    def test_water_radical_contains_known_chars(self):
        """Water radical family includes known water-radical characters."""
        family = get_component_family("氵")
        # 河, 湖, 海 are all water-radical characters
        for char in ("河", "湖", "海"):
            self.assertIn(char, family, f"{char} should be in water radical family")

    def test_unknown_radical_returns_empty(self):
        """An unknown radical returns an empty list."""
        family = get_component_family("㐅")  # not in our data
        self.assertEqual(family, [])

    def test_fire_radical(self):
        """Fire radical returns characters like 烧, 烤."""
        family = get_component_family("火")
        self.assertIsInstance(family, list)
        self.assertTrue(len(family) > 0)

    def test_mouth_radical(self):
        """Mouth radical returns characters like 吃, 喝."""
        family = get_component_family("口")
        self.assertIn("吃", family)
        self.assertIn("喝", family)


class TestGetPhoneticFamily(unittest.TestCase):
    """Tests for get_phonetic_family() — characters sharing a phonetic component."""

    def test_qing_phonetic_returns_dict(self):
        """Phonetic 青 returns a dict mapping pinyin -> characters."""
        family = get_phonetic_family("青")
        self.assertIsInstance(family, dict)
        self.assertTrue(len(family) > 0)

    def test_qing_phonetic_contains_qing(self):
        """Phonetic 青 family includes qīng -> 清."""
        family = get_phonetic_family("青")
        self.assertIn("qīng", family)
        self.assertIn("清", family["qīng"])

    def test_qing_phonetic_contains_qing_variants(self):
        """Phonetic 青 family includes multiple tone variants."""
        family = get_phonetic_family("青")
        # 请 (qǐng), 情/晴 (qíng), 精 (jīng) should be present
        self.assertIn("qǐng", family)
        self.assertIn("qíng", family)

    def test_unknown_phonetic_returns_empty(self):
        """Unknown phonetic component returns empty dict."""
        family = get_phonetic_family("㐅")
        self.assertEqual(family, {})

    def test_bao_phonetic(self):
        """Phonetic 包 returns expected characters."""
        family = get_phonetic_family("包")
        self.assertIsInstance(family, dict)
        self.assertTrue(len(family) > 0)
        # 跑袍 should be under páo
        self.assertIn("páo", family)

    def test_returns_copy_not_reference(self):
        """get_phonetic_family returns a new dict, not the internal reference."""
        family1 = get_phonetic_family("青")
        family2 = get_phonetic_family("青")
        self.assertEqual(family1, family2)
        # Mutating one should not affect the other
        family1["test_key"] = "test"
        family2_again = get_phonetic_family("青")
        self.assertNotIn("test_key", family2_again)


class TestGetRadicalForCharacter(unittest.TestCase):
    """Tests for get_radical_for_character()."""

    def test_known_character(self):
        """Known character returns (radical, meaning, pinyin) tuple."""
        result = get_radical_for_character("河")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        radical, meaning, pinyin = result
        self.assertEqual(radical, "氵")
        self.assertEqual(meaning, "water")

    def test_unknown_character(self):
        """Unknown character returns None."""
        result = get_radical_for_character("鬯")
        self.assertIsNone(result)


class TestGenerateDecompositionOverlay(unittest.TestCase):
    """Tests for generate_decomposition_overlay()."""

    def test_known_character_returns_overlay(self):
        """Known character returns overlay dict with expected keys."""
        overlay = generate_decomposition_overlay("清")
        self.assertIsNotNone(overlay)
        for key in ("character", "radical", "radical_meaning"):
            self.assertIn(key, overlay)

    def test_overlay_family_limited(self):
        """Family examples in overlay are limited to 4."""
        overlay = generate_decomposition_overlay("清")
        self.assertIsNotNone(overlay)
        examples = overlay.get("family_examples", [])
        self.assertLessEqual(len(examples), 4)

    def test_unknown_character_returns_none(self):
        """Character with no data returns None."""
        overlay = generate_decomposition_overlay("鬯")
        self.assertIsNone(overlay)

    def test_non_cjk_returns_none(self):
        """Non-CJK input returns None."""
        self.assertIsNone(generate_decomposition_overlay("X"))


class TestEdgeCases(unittest.TestCase):
    """Miscellaneous edge-case tests."""

    def test_reverse_indices_populated(self):
        """Module-level reverse indices are non-empty after import."""
        self.assertTrue(len(_CHAR_TO_RADICAL) > 0)
        self.assertTrue(len(_CHAR_TO_PHONETIC) > 0)

    def test_decompose_character_with_both_radical_and_phonetic(self):
        """Character with both radical and phonetic has all fields."""
        # 请 has speech radical 讠 and phonetic 青
        result = decompose("请")
        self.assertIsNotNone(result)
        self.assertIn("radical", result)
        self.assertIn("phonetic", result)
        self.assertEqual(result["radical"], "讠")
        self.assertEqual(result["phonetic"], "青")

    def test_decompose_character_radical_only(self):
        """Character with only radical data (no phonetic) still decomposes."""
        # Find a character in _CHAR_TO_RADICAL but not _CHAR_TO_PHONETIC
        for char in _CHAR_TO_RADICAL:
            if char not in _CHAR_TO_PHONETIC:
                result = decompose(char)
                self.assertIsNotNone(result)
                self.assertIn("radical", result)
                self.assertNotIn("phonetic", result)
                break


if __name__ == "__main__":
    unittest.main()
