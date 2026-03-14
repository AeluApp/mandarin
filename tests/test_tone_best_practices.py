"""Tests for tone recognition best practices (YIN, transcript-first,
leniency, speaker calibration, coaching feedback)."""

import pytest


# ── YIN F0 extraction ────────────────────────────────────────────

def test_extract_f0_yin_silent():
    """Silent audio should produce all zeros."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")
    from mandarin.tone_grading import extract_f0_yin

    audio = np.zeros(16000, dtype=np.float32)  # 1 second silence
    f0 = extract_f0_yin(audio)
    assert len(f0) > 0
    assert all(v == 0.0 for v in f0), "Silent audio should produce all-zero F0"


def test_extract_f0_yin_sine_wave():
    """A 200 Hz sine wave should extract F0 within 5% of 200 Hz."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")
    from mandarin.tone_grading import extract_f0_yin, SAMPLE_RATE

    sr = SAMPLE_RATE
    duration = 0.5  # seconds
    freq = 200.0
    t = np.arange(int(sr * duration)) / sr
    audio = (0.8 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    f0 = extract_f0_yin(audio, sr)
    voiced = [f for f in f0 if f > 0]
    assert len(voiced) > 0, "Should detect voiced frames in a sine wave"

    mean_f0 = sum(voiced) / len(voiced)
    assert abs(mean_f0 - freq) / freq < 0.05, (
        f"Mean F0 {mean_f0:.1f} Hz should be within 5% of {freq} Hz"
    )


def test_extract_f0_yin_empty():
    """Empty audio should return empty list."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")
    from mandarin.tone_grading import extract_f0_yin

    audio = np.array([], dtype=np.float32)
    f0 = extract_f0_yin(audio)
    assert f0 == []


def test_extract_f0_wrapper_uses_pyin_or_yin():
    """extract_f0() should use librosa pYIN when available, else YIN."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")
    from mandarin.tone_grading import extract_f0, extract_f0_yin, HAS_LIBROSA

    audio = np.zeros(16000, dtype=np.float32)
    result = extract_f0(audio)

    if HAS_LIBROSA:
        # pYIN may produce different frame count than YIN — that's expected.
        # Just verify we get a valid list of floats with all zeros (silence).
        assert len(result) > 0
        assert all(v == 0.0 for v in result)
    else:
        # Without librosa, should fall back to YIN exactly
        assert result == extract_f0_yin(audio)


# ── Transcript-first scoring ─────────────────────────────────────

def test_compute_speaking_score_transcript_match():
    """When content >= 0.9, score should be at least 0.85."""
    from mandarin.drills.speaking import compute_speaking_score

    # Even with poor tone_score, high content should boost to >= 0.85
    score = compute_speaking_score(tone_score=0.3, content_score=0.95)
    assert score >= 0.85


def test_compute_speaking_score_no_transcript():
    """Without transcript, should use tone_score only."""
    from mandarin.drills.speaking import compute_speaking_score

    score = compute_speaking_score(tone_score=0.7, content_score=None)
    assert score == 0.7


def test_compute_speaking_score_partial_match():
    """Partial content match (0.4-0.9) uses 40/60 weighting."""
    from mandarin.drills.speaking import compute_speaking_score

    score = compute_speaking_score(tone_score=0.5, content_score=0.6)
    expected = 0.4 * 0.5 + 0.6 * 0.6  # = 0.56
    assert abs(score - expected) < 0.001


def test_compute_speaking_score_low_content():
    """Low content (< 0.4) uses 60/40 weighting."""
    from mandarin.drills.speaking import compute_speaking_score

    score = compute_speaking_score(tone_score=0.8, content_score=0.2)
    expected = 0.6 * 0.8 + 0.4 * 0.2  # = 0.56
    assert abs(score - expected) < 0.001


def test_compute_speaking_score_perfect():
    """Perfect tone + perfect content → full marks."""
    from mandarin.drills.speaking import compute_speaking_score

    score = compute_speaking_score(tone_score=1.0, content_score=1.0)
    assert score >= 0.99


# ── Proficiency-scaled leniency ──────────────────────────────────

def test_tone_leniency_beginner():
    """Level 1.0 (beginner) should get pass_threshold 0.35."""
    from mandarin.tone_grading import get_tone_leniency

    leniency = get_tone_leniency(1.0)
    assert leniency["pass_threshold"] == 0.35
    assert leniency["close_pair_credit"] == 0.60
    assert leniency["unclassified_credit"] == 0.40
    assert leniency["transcript_floor"] == 0.90


def test_tone_leniency_advanced():
    """Level 5.0 (advanced) should get pass_threshold 0.625 (midpoint 4.0→6.0)."""
    from mandarin.tone_grading import get_tone_leniency

    leniency = get_tone_leniency(5.0)
    assert abs(leniency["pass_threshold"] - 0.625) < 0.01


def test_tone_leniency_interpolation():
    """Level 3.0 (mid-intermediate) should interpolate between bands."""
    from mandarin.tone_grading import get_tone_leniency

    leniency = get_tone_leniency(3.0)
    # Between 2.0 (0.50) and 4.0 (0.60), at midpoint → 0.55
    assert abs(leniency["pass_threshold"] - 0.55) < 0.01


def test_tone_leniency_proficient():
    """Level 7.0 (proficient) clamps to top band."""
    from mandarin.tone_grading import get_tone_leniency

    leniency = get_tone_leniency(7.0)
    assert leniency["pass_threshold"] == 0.65
    assert leniency["close_pair_credit"] == 0.25


def test_tone_leniency_below_minimum():
    """Level below 1.0 clamps to beginner."""
    from mandarin.tone_grading import get_tone_leniency

    leniency = get_tone_leniency(0.5)
    assert leniency["pass_threshold"] == 0.35


# ── Speaker calibration ──────────────────────────────────────────

def test_speaker_calibration_roundtrip(test_db):
    """Store and retrieve speaker calibration."""
    conn, _ = test_db

    from mandarin.tone_grading import save_speaker_calibration, get_speaker_calibration

    cal = {"f0_min": 100.0, "f0_max": 300.0, "f0_mean": 180.0}
    save_speaker_calibration(conn, cal, user_id=1)

    loaded = get_speaker_calibration(conn, user_id=1)
    assert loaded is not None
    assert loaded["f0_min"] == 100.0
    assert loaded["f0_max"] == 300.0
    assert loaded["f0_mean"] == 180.0
    assert "calibrated_at" in loaded


def test_speaker_calibration_none_when_empty(test_db):
    """get_speaker_calibration returns None when no calibration exists."""
    conn, _ = test_db
    from mandarin.tone_grading import get_speaker_calibration

    assert get_speaker_calibration(conn, user_id=1) is None


def test_run_tone_calibration_with_sine():
    """Calibration with a sine wave should extract reasonable F0 range."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")
    from mandarin.tone_grading import run_tone_calibration, SAMPLE_RATE

    sr = SAMPLE_RATE
    t = np.arange(int(sr * 1.0)) / sr
    audio = (0.8 * np.sin(2 * np.pi * 200.0 * t)).astype(np.float32)

    cal = run_tone_calibration(audio, sr)
    assert cal is not None
    assert 150 < cal["f0_min"] < 250
    assert 150 < cal["f0_max"] < 250
    assert 150 < cal["f0_mean"] < 250


def test_run_tone_calibration_silent():
    """Calibration with silence returns None."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")
    from mandarin.tone_grading import run_tone_calibration

    audio = np.zeros(16000, dtype=np.float32)
    assert run_tone_calibration(audio) is None


def test_classify_tone_with_calibration():
    """classify_tone with calibration uses speaker range for normalization."""
    from mandarin.tone_grading import classify_tone

    # Rising contour in absolute Hz
    contour = [150.0, 170.0, 190.0, 210.0, 230.0, 250.0]

    # Without calibration — per-syllable normalization
    tone_no_cal, _ = classify_tone(contour)

    # With calibration — speaker range 100-300 Hz
    cal = {"f0_min": 100.0, "f0_max": 300.0}
    tone_with_cal, _ = classify_tone(contour, calibration=cal)

    # Both should produce a valid tone
    assert tone_no_cal in [1, 2, 3, 4]
    assert tone_with_cal in [1, 2, 3, 4]


# ── Coaching feedback ────────────────────────────────────────────

def test_coaching_correct_tones():
    """No coaching tips when all tones are correct."""
    from mandarin.tone_grading import generate_tone_coaching

    syllable_scores = [
        {"expected": 1, "detected": 1, "correct": True, "confidence": 0.9, "credit": 1.0},
        {"expected": 2, "detected": 2, "correct": True, "confidence": 0.8, "credit": 1.0},
    ]
    tips = generate_tone_coaching(syllable_scores)
    assert tips == []


def test_coaching_wrong_tone():
    """Wrong tone generates an actionable tip."""
    from mandarin.tone_grading import generate_tone_coaching

    syllable_scores = [
        {"expected": 2, "detected": 4, "correct": False, "confidence": 0.7, "credit": 0.0},
    ]
    tips = generate_tone_coaching(syllable_scores)
    assert len(tips) == 1
    tip = tips[0]
    assert tip["syllable"] == 1
    assert tip["expected"] == 2
    assert tip["detected"] == 4
    assert "rise" in tip["tip"].lower() or "question" in tip["tip"].lower()
    assert tip["expected_arrow"] == "\u2197"  # ↗


def test_coaching_unclassified_tone():
    """Unclassified detected tone (0) generates coaching with expected tip."""
    from mandarin.tone_grading import generate_tone_coaching

    syllable_scores = [
        {"expected": 3, "detected": 0, "correct": False, "confidence": 0.0, "credit": 0.3},
    ]
    tips = generate_tone_coaching(syllable_scores)
    assert len(tips) == 1
    assert "dip" in tips[0]["tip"].lower()


def test_coaching_multiple_syllables():
    """Coaching generates tips for each incorrect syllable."""
    from mandarin.tone_grading import generate_tone_coaching

    syllable_scores = [
        {"expected": 1, "detected": 1, "correct": True, "confidence": 0.9, "credit": 1.0},
        {"expected": 2, "detected": 4, "correct": False, "confidence": 0.7, "credit": 0.0},
        {"expected": 3, "detected": 1, "correct": False, "confidence": 0.6, "credit": 0.0},
    ]
    tips = generate_tone_coaching(syllable_scores)
    assert len(tips) == 2
    assert tips[0]["syllable"] == 2
    assert tips[1]["syllable"] == 3


def test_contour_arrows_complete():
    """CONTOUR_ARROWS has entries for all four tones."""
    from mandarin.tone_grading import CONTOUR_ARROWS

    assert 1 in CONTOUR_ARROWS
    assert 2 in CONTOUR_ARROWS
    assert 3 in CONTOUR_ARROWS
    assert 4 in CONTOUR_ARROWS
