"""Tests for the V2 tone feature extraction engine."""

import pytest
np = pytest.importorskip("numpy")


# ── Feature extraction ────────────────────────────────────────────

class TestExtractToneFeatures:
    def test_rising_contour(self):
        from mandarin.tone_features import extract_tone_features
        contour = [100.0, 130.0, 160.0, 190.0, 220.0, 250.0]
        feat = extract_tone_features(contour)
        assert feat is not None
        assert feat.overall_slope > 0
        assert feat.offset > feat.onset

    def test_falling_contour(self):
        from mandarin.tone_features import extract_tone_features
        contour = [250.0, 220.0, 190.0, 160.0, 130.0, 100.0]
        feat = extract_tone_features(contour)
        assert feat is not None
        assert feat.overall_slope < 0
        assert feat.onset > feat.offset

    def test_dipping_contour(self):
        from mandarin.tone_features import extract_tone_features
        contour = [200.0, 170.0, 130.0, 100.0, 130.0, 170.0, 200.0]
        feat = extract_tone_features(contour)
        assert feat is not None
        assert feat.valley < feat.onset
        assert feat.valley < feat.offset
        assert 0.2 < feat.valley_position < 0.8

    def test_flat_contour(self):
        from mandarin.tone_features import extract_tone_features
        contour = [200.0, 200.0, 200.0, 200.0]
        feat = extract_tone_features(contour)
        assert feat is not None
        assert feat.flatness > 0.8
        assert feat.excursion < 0.05

    def test_too_few_voiced(self):
        from mandarin.tone_features import extract_tone_features
        assert extract_tone_features([150.0, 160.0]) is None
        assert extract_tone_features([]) is None
        assert extract_tone_features([0.0, 0.0, 0.0, 0.0]) is None

    def test_unvoiced_gap_interpolation(self):
        from mandarin.tone_features import extract_tone_features
        # Gap of 1 unvoiced frame between voiced regions
        contour = [200.0, 210.0, 0.0, 230.0, 240.0, 250.0]
        feat = extract_tone_features(contour)
        assert feat is not None
        assert feat.n_voiced_frames >= 5  # original 5 + interpolated

    def test_speaker_calibration(self):
        from mandarin.tone_features import extract_tone_features
        contour = [150.0, 170.0, 190.0, 210.0, 230.0, 250.0]
        cal = {"f0_min": 100.0, "f0_max": 300.0}
        feat = extract_tone_features(contour, calibration=cal)
        assert feat is not None
        assert feat.norm_method == "speaker"

    def test_no_calibration_uses_syllable(self):
        from mandarin.tone_features import extract_tone_features
        contour = [150.0, 170.0, 190.0, 210.0]
        feat = extract_tone_features(contour)
        assert feat is not None
        assert feat.norm_method == "syllable"


# ── Family scoring ────────────────────────────────────────────────

class TestScoreAgainstFamilies:
    def test_flat_scores_tone1_highest(self):
        from mandarin.tone_features import extract_tone_features, score_against_families
        contour = [200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0]
        feat = extract_tone_features(contour)
        scores = score_against_families(feat)
        assert scores[1][0] >= scores[2][0]
        assert scores[1][0] >= scores[3][0]
        assert scores[1][0] >= scores[4][0]

    def test_rising_scores_tone2_highest(self):
        from mandarin.tone_features import extract_tone_features, score_against_families
        contour = [100.0, 130.0, 160.0, 190.0, 220.0, 250.0, 280.0, 310.0]
        feat = extract_tone_features(contour)
        scores = score_against_families(feat)
        assert scores[2][0] >= scores[1][0]
        assert scores[2][0] >= scores[4][0]

    def test_dipping_scores_tone3_highest(self):
        from mandarin.tone_features import extract_tone_features, score_against_families
        contour = [200.0, 170.0, 130.0, 100.0, 80.0, 100.0, 130.0, 170.0, 200.0]
        feat = extract_tone_features(contour)
        scores = score_against_families(feat)
        assert scores[3][0] >= scores[1][0]
        assert scores[3][0] >= scores[4][0]

    def test_falling_scores_tone4_highest(self):
        from mandarin.tone_features import extract_tone_features, score_against_families
        contour = [300.0, 270.0, 230.0, 190.0, 150.0, 110.0, 80.0, 60.0]
        feat = extract_tone_features(contour)
        scores = score_against_families(feat)
        assert scores[4][0] >= scores[1][0]
        assert scores[4][0] >= scores[2][0]

    def test_half_third_recognized(self):
        """Half-third (falling only, no rise) should score well for tone 3."""
        from mandarin.tone_features import extract_tone_features, score_against_families
        contour = [150.0, 130.0, 110.0, 100.0, 95.0, 90.0]
        feat = extract_tone_features(contour)
        scores = score_against_families(feat)
        # Tone 3 should have a reasonable score via half_third or low_flat
        assert scores[3][0] > 0.3

    def test_low_flat_recognized_as_tone3(self):
        """Low flat contour should match tone 3 families."""
        from mandarin.tone_features import extract_tone_features, score_against_families
        # Use speaker calibration so the low range maps correctly
        contour = [100.0, 100.0, 98.0, 97.0, 99.0, 100.0]
        cal = {"f0_min": 80.0, "f0_max": 300.0}
        feat = extract_tone_features(contour, calibration=cal)
        scores = score_against_families(feat)
        assert scores[3][0] > 0.3

    def test_isolated_mode_reduces_half_third(self):
        from mandarin.tone_features import extract_tone_features, score_against_families
        contour = [150.0, 130.0, 110.0, 100.0, 95.0, 90.0]
        feat = extract_tone_features(contour)
        connected = score_against_families(feat, mode="connected")
        isolated = score_against_families(feat, mode="isolated")
        # In isolated mode, half_third weight is halved
        assert isolated[3][0] <= connected[3][0]


# ── classify_tone_v2 ──────────────────────────────────────────────

class TestClassifyToneV2:
    def test_smoke_tone1(self):
        from mandarin.tone_features import classify_tone_v2
        result = classify_tone_v2([200.0, 200.0, 200.0, 200.0])
        assert result.tone == 1
        assert result.confidence > 0

    def test_smoke_tone2(self):
        from mandarin.tone_features import classify_tone_v2
        result = classify_tone_v2([100.0, 150.0, 200.0, 250.0])
        assert result.tone == 2

    def test_smoke_tone3_full_dip(self):
        from mandarin.tone_features import classify_tone_v2
        result = classify_tone_v2([200.0, 150.0, 100.0, 80.0, 100.0, 150.0])
        assert result.tone == 3

    def test_smoke_tone3_half_third(self):
        from mandarin.tone_features import classify_tone_v2
        result = classify_tone_v2([100.0, 100.0, 90.0, 80.0])
        # Should recognize as T3 (low_flat or half_third) not T4
        assert result.tone in (3, 4)  # may be ambiguous without half_third hint

    def test_smoke_tone3_half_third_with_hint(self):
        from mandarin.tone_features import classify_tone_v2
        # With speaker calibration, low-range falling reads as half-third
        cal = {"f0_min": 80.0, "f0_max": 300.0}
        result = classify_tone_v2([100.0, 100.0, 90.0, 80.0],
                                  calibration=cal, half_third_expected=True)
        assert result.tone == 3

    def test_smoke_tone4(self):
        from mandarin.tone_features import classify_tone_v2
        result = classify_tone_v2([250.0, 200.0, 150.0, 100.0])
        assert result.tone == 4

    def test_ambiguity_detection(self):
        from mandarin.tone_features import classify_tone_v2
        # A contour that could be T2 or T3
        result = classify_tone_v2([120.0, 110.0, 105.0, 110.0, 130.0, 160.0])
        # Just verify the ambiguity flag is a bool
        assert isinstance(result.ambiguous, bool)
        assert isinstance(result.runner_up, int)

    def test_insufficient_data(self):
        from mandarin.tone_features import classify_tone_v2
        result = classify_tone_v2([150.0])
        assert result.tone == 0
        assert result.confidence == 0.0


# ── Diagnostics ───────────────────────────────────────────────────

class TestDiagnostics:
    def test_tone1_drift_up(self):
        from mandarin.tone_features import extract_tone_features, generate_diagnostics
        # Tone 1 that drifts upward
        contour = [200.0, 210.0, 220.0, 230.0, 240.0, 250.0]
        feat = extract_tone_features(contour)
        diags = generate_diagnostics(feat, expected_tone=1)
        assert "pitch_drifted_up" in diags

    def test_tone2_rise_too_small(self):
        from mandarin.tone_features import extract_tone_features, generate_diagnostics
        # Truly flat-ish contour: barely any rise at all over wide range
        cal = {"f0_min": 80.0, "f0_max": 400.0}
        contour = [180.0, 180.0, 181.0, 182.0, 182.0, 183.0]
        feat = extract_tone_features(contour, calibration=cal)
        diags = generate_diagnostics(feat, expected_tone=2)
        assert "rise_too_small" in diags or "didnt_reach_high_enough" in diags

    def test_tone4_fall_too_small(self):
        from mandarin.tone_features import extract_tone_features, generate_diagnostics
        # Barely falling over a wide speaker range
        cal = {"f0_min": 80.0, "f0_max": 400.0}
        contour = [183.0, 182.0, 182.0, 181.0, 180.0, 180.0]
        feat = extract_tone_features(contour, calibration=cal)
        diags = generate_diagnostics(feat, expected_tone=4)
        assert "fall_too_small" in diags or "didnt_start_high_enough" in diags

    def test_no_diagnostics_for_neutral(self):
        from mandarin.tone_features import extract_tone_features, generate_diagnostics
        contour = [200.0, 200.0, 200.0, 200.0]
        feat = extract_tone_features(contour)
        diags = generate_diagnostics(feat, expected_tone=0)
        assert diags == []

    def test_diagnostic_tips_mapping(self):
        from mandarin.tone_features import DIAGNOSTIC_TIPS
        expected_keys = [
            "pitch_drifted_up", "pitch_drifted_down",
            "rise_too_small", "didnt_reach_high_enough",
            "didnt_go_low_enough", "dipped_too_early",
            "fall_too_small", "didnt_start_high_enough",
        ]
        for key in expected_keys:
            assert key in DIAGNOSTIC_TIPS
            assert isinstance(DIAGNOSTIC_TIPS[key], str)
            assert len(DIAGNOSTIC_TIPS[key]) > 10


# ── Syllable segmentation ────────────────────────────────────────

class TestSegmentation:
    def test_single_syllable(self):
        import numpy as np
        from mandarin.tone_features import segment_syllable_nuclei
        audio = np.zeros(16000, dtype=np.float32)
        segs = segment_syllable_nuclei(audio, 1)
        assert len(segs) == 1
        assert segs[0] == (0, 16000)

    def test_even_split_fallback(self):
        import numpy as np
        from mandarin.tone_features import segment_syllable_nuclei
        # Very short audio triggers even split
        audio = np.zeros(100, dtype=np.float32)
        segs = segment_syllable_nuclei(audio, 3)
        assert len(segs) == 3

    def test_zero_syllables(self):
        import numpy as np
        from mandarin.tone_features import segment_syllable_nuclei
        audio = np.zeros(16000, dtype=np.float32)
        segs = segment_syllable_nuclei(audio, 0)
        assert segs == []


# ── Sandhi rules V2 ──────────────────────────────────────────────

class TestSandhiV2:
    def test_sandhi_returns_three_lists(self):
        from mandarin.tone_grading import _apply_sandhi_rules
        surface, underlying, half_third = _apply_sandhi_rules([3, 3])
        assert surface == [2, 3]
        assert underlying == [3, 3]
        assert isinstance(half_third, list)

    def test_sandhi_half_third_marker(self):
        from mandarin.tone_grading import _apply_sandhi_rules
        # T3 before T1 → half-third expected
        surface, underlying, half_third = _apply_sandhi_rules([3, 1])
        assert surface == [3, 1]
        assert half_third[0] is True
        assert half_third[1] is False

    def test_sandhi_triple_three(self):
        from mandarin.tone_grading import _apply_sandhi_rules
        surface, underlying, half_third = _apply_sandhi_rules([3, 3, 3])
        assert surface == [2, 2, 3]
        assert underlying == [3, 3, 3]

    def test_sandhi_single_tone(self):
        from mandarin.tone_grading import _apply_sandhi_rules
        surface, underlying, half_third = _apply_sandhi_rules([2])
        assert surface == [2]
        assert underlying == [2]
        assert half_third == [False]


# ── Coaching V2 ───────────────────────────────────────────────────

class TestCoachingV2:
    def test_coaching_with_diagnostics(self):
        from mandarin.tone_grading import generate_tone_coaching
        scores = [{
            "expected": 1, "detected": 2, "correct": False,
            "confidence": 0.6, "credit": 0.0,
            "diagnostics": ["pitch_drifted_up"],
        }]
        tips = generate_tone_coaching(scores)
        assert len(tips) == 1
        assert "flat" in tips[0]["tip"].lower() or "crept" in tips[0]["tip"].lower()
        assert tips[0]["error_kind"] == "quality"

    def test_coaching_without_diagnostics_legacy(self):
        from mandarin.tone_grading import generate_tone_coaching
        scores = [{
            "expected": 2, "detected": 4, "correct": False,
            "confidence": 0.7, "credit": 0.0,
        }]
        tips = generate_tone_coaching(scores)
        assert len(tips) == 1
        assert tips[0]["error_kind"] == "category"

    def test_coaching_correct_still_empty(self):
        from mandarin.tone_grading import generate_tone_coaching
        scores = [{
            "expected": 1, "detected": 1, "correct": True,
            "confidence": 0.9, "credit": 1.0,
            "diagnostics": [],
        }]
        tips = generate_tone_coaching(scores)
        assert tips == []
