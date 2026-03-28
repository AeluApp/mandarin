"""Tests for desirable_difficulty_adjustment() in mandarin/ai/memory_model.py.

Validates all 5 Bjork zones, mastered/well-learned overrides, and edge cases.
Uses pytest + unittest.TestCase pattern with in-memory SQLite (row_factory).
"""

import unittest

from mandarin.ai.memory_model import desirable_difficulty_adjustment


from tests.shared_db import make_test_db as _make_db


class TestBjorkZone1TooEasy(unittest.TestCase):
    """Zone 1: R > 0.95 -- over-practiced, shorten interval."""

    def test_high_retrievability_shortens_interval(self):
        """R=0.97 should yield interval_multiplier=0.75."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.97)
        self.assertAlmostEqual(result["interval_multiplier"], 0.75)

    def test_high_retrievability_forces_production_when_stable(self):
        """R=0.97, stability>7 should force production drill."""
        result = desirable_difficulty_adjustment(stability=10.0, retrievability=0.97)
        self.assertEqual(result["drill_type_override"], "production")

    def test_high_retrievability_no_production_when_unstable(self):
        """R=0.97, stability<=7 should not force production (zone 1 only)."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.97)
        # stability=5 <= 7, so no production override from zone 1
        # But stability > 14 check also fails, so should be None
        self.assertIsNone(result["drill_type_override"])

    def test_zone1_no_context_variation(self):
        """Zone 1 with stability < 30 should not enable context_variation."""
        result = desirable_difficulty_adjustment(stability=10.0, retrievability=0.97)
        self.assertFalse(result["context_variation"])


class TestBjorkZone2Optimal(unittest.TestCase):
    """Zone 2: 0.70 <= R <= 0.85 -- Bjork's sweet spot, no adjustment."""

    def test_optimal_zone_no_multiplier(self):
        """R=0.80 should leave interval_multiplier at 1.0."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.80)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)

    def test_optimal_zone_no_override(self):
        """R=0.80, stability=5 should not override drill type."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.80)
        self.assertIsNone(result["drill_type_override"])

    def test_optimal_zone_lower_bound(self):
        """R=0.70 is included in the optimal zone."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.70)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)

    def test_optimal_zone_upper_bound(self):
        """R=0.85 is included in the optimal zone."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.85)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)


class TestBjorkZone3SlightlyEasy(unittest.TestCase):
    """Zone 3: 0.85 < R < 0.95 -- could be harder, 10% shorter interval."""

    def test_slightly_easy_multiplier(self):
        """R=0.90 should yield interval_multiplier=0.90."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.90)
        self.assertAlmostEqual(result["interval_multiplier"], 0.90)

    def test_zone3_boundary_low(self):
        """R=0.86 is in zone 3 (slightly easy)."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.86)
        self.assertAlmostEqual(result["interval_multiplier"], 0.90)

    def test_zone3_boundary_high(self):
        """R=0.94 is in zone 3 (slightly easy)."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.94)
        self.assertAlmostEqual(result["interval_multiplier"], 0.90)


class TestBjorkZone4HardButProductive(unittest.TestCase):
    """Zone 4: 0.50 <= R < 0.70 -- desirable difficulty, switch to recognition."""

    def test_hard_zone_recognition_override(self):
        """R=0.60 should force recognition drill."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.60)
        self.assertEqual(result["drill_type_override"], "recognition")

    def test_hard_zone_interval_unchanged(self):
        """R=0.60 should keep interval_multiplier at 1.0."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.60)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)

    def test_zone4_lower_bound(self):
        """R=0.50 is in zone 4."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.50)
        self.assertEqual(result["drill_type_override"], "recognition")


class TestBjorkZone5TooHard(unittest.TestCase):
    """Zone 5: R < 0.50 -- retrieval will likely fail, shorten + recognition."""

    def test_too_hard_multiplier(self):
        """R=0.40 should yield interval_multiplier=0.60."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.40)
        self.assertAlmostEqual(result["interval_multiplier"], 0.60)

    def test_too_hard_recognition_override(self):
        """R=0.40 should force recognition drill."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.40)
        self.assertEqual(result["drill_type_override"], "recognition")

    def test_very_low_retrievability(self):
        """R=0.10 is deep in zone 5."""
        result = desirable_difficulty_adjustment(stability=2.0, retrievability=0.10)
        self.assertAlmostEqual(result["interval_multiplier"], 0.60)
        self.assertEqual(result["drill_type_override"], "recognition")


class TestMasteredItems(unittest.TestCase):
    """Mastered items: stability > 30 triggers production + context_variation."""

    def test_mastered_item_production_and_context(self):
        """stability=35, R=0.80 should force production and context_variation."""
        result = desirable_difficulty_adjustment(stability=35.0, retrievability=0.80)
        self.assertEqual(result["drill_type_override"], "production")
        self.assertTrue(result["context_variation"])

    def test_mastered_overrides_zone_recognition(self):
        """Even if zone says recognition, stability>30 overrides to production."""
        # R=0.60 is zone 4 (recognition), but stability=35 is mastered
        result = desirable_difficulty_adjustment(stability=35.0, retrievability=0.60)
        self.assertEqual(result["drill_type_override"], "production")
        self.assertTrue(result["context_variation"])

    def test_mastered_overrides_zone5(self):
        """stability>30 with R<0.50 still gets production + context_variation."""
        result = desirable_difficulty_adjustment(stability=35.0, retrievability=0.40)
        self.assertEqual(result["drill_type_override"], "production")
        self.assertTrue(result["context_variation"])


class TestWellLearnedItems(unittest.TestCase):
    """Well-learned items: stability > 14 forces production when no other override."""

    def test_well_learned_production(self):
        """stability=20, R=0.80 (optimal zone, no override) -> production."""
        result = desirable_difficulty_adjustment(stability=20.0, retrievability=0.80)
        self.assertEqual(result["drill_type_override"], "production")

    def test_well_learned_does_not_override_existing(self):
        """stability=20, R=0.60 (zone 4 recognition) -> zone 4 wins,
        but then stability>14 check only fires when drill_type_override is None.
        Here zone 4 already set recognition, so the well-learned check skips."""
        # Actually, zone 4 sets recognition, then stability>14 check:
        #   `elif stability > 14 and result["drill_type_override"] is None:`
        # Since override is "recognition" (not None), the elif is skipped.
        result = desirable_difficulty_adjustment(stability=20.0, retrievability=0.60)
        self.assertEqual(result["drill_type_override"], "recognition")

    def test_well_learned_no_context_variation(self):
        """stability=20 (< 30) should not enable context_variation."""
        result = desirable_difficulty_adjustment(stability=20.0, retrievability=0.80)
        self.assertFalse(result["context_variation"])


class TestEdgeCasesAndInvalidInputs(unittest.TestCase):
    """Edge cases: None, negative values, boundary values."""

    def test_none_retrievability_graceful(self):
        """None retrievability should return defaults (caught by TypeError)."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=None)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)
        self.assertIsNone(result["drill_type_override"])
        self.assertFalse(result["context_variation"])

    def test_none_stability_graceful(self):
        """None stability should return defaults (caught by TypeError)."""
        result = desirable_difficulty_adjustment(stability=None, retrievability=0.80)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)
        self.assertIsNone(result["drill_type_override"])
        self.assertFalse(result["context_variation"])

    def test_negative_retrievability_graceful(self):
        """Negative R falls into zone 5 (R < 0.50)."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=-0.5)
        self.assertAlmostEqual(result["interval_multiplier"], 0.60)
        self.assertEqual(result["drill_type_override"], "recognition")

    def test_negative_stability_graceful(self):
        """Negative stability should not crash."""
        result = desirable_difficulty_adjustment(stability=-1.0, retrievability=0.80)
        # stability < 0 won't trigger mastered/well-learned overrides
        self.assertIsNotNone(result)
        self.assertIn("interval_multiplier", result)

    def test_zero_retrievability(self):
        """R=0.0 falls into zone 5."""
        result = desirable_difficulty_adjustment(stability=5.0, retrievability=0.0)
        self.assertAlmostEqual(result["interval_multiplier"], 0.60)

    def test_retrievability_exactly_one(self):
        """R=1.0 falls into zone 1 (> 0.95)."""
        result = desirable_difficulty_adjustment(stability=10.0, retrievability=1.0)
        self.assertAlmostEqual(result["interval_multiplier"], 0.75)

    def test_both_none_graceful(self):
        """Both None should return defaults."""
        result = desirable_difficulty_adjustment(stability=None, retrievability=None)
        self.assertAlmostEqual(result["interval_multiplier"], 1.0)
        self.assertIsNone(result["drill_type_override"])
        self.assertFalse(result["context_variation"])

    def test_result_always_has_required_keys(self):
        """Every call must return all three keys."""
        for s, r in [(5.0, 0.80), (0.0, 0.0), (100.0, 1.0), (None, None)]:
            result = desirable_difficulty_adjustment(stability=s, retrievability=r)
            self.assertIn("interval_multiplier", result)
            self.assertIn("drill_type_override", result)
            self.assertIn("context_variation", result)


if __name__ == "__main__":
    unittest.main()
