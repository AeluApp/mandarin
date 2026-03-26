"""Tone feature extraction, contour families, and diagnostics.

V2 tone classification engine — replaces the thirds-averaging approach
with rich feature vectors scored against contour family templates.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None


# ── Feature vector ────────────────────────────────────────────────

@dataclass
class ToneFeatures:
    """Rich feature vector extracted from a single syllable's F0 contour."""
    onset: float           # avg of first 15% of normed contour
    offset: float          # avg of last 15% of normed contour
    valley: float          # minimum value
    valley_position: float # 0.0=start, 1.0=end
    peak: float            # maximum value
    peak_position: float   # 0.0=start, 1.0=end
    excursion: float       # peak - valley
    slope_first_half: float
    slope_second_half: float
    overall_slope: float
    flatness: float        # 1.0 - scaled std dev
    voiced_ratio: float
    n_voiced_frames: int
    mean_f0_hz: float
    norm_method: str       # "speaker" or "syllable"
    # Voice quality extras (None when librosa unavailable)
    hnr_mean: float | None = None       # harmonics-to-noise ratio (dB)
    intensity_mean: float | None = None # mean intensity (dB)
    intensity_slope: float | None = None # intensity contour slope (stress)
    f1_mean: float | None = None        # mean F1 (vowel openness)
    f2_mean: float | None = None        # mean F2 (vowel frontness)
    jitter: float | None = None         # period perturbation
    shimmer: float | None = None        # amplitude perturbation
    f0_source: str = "yin"                 # "praat" or "yin"


@dataclass
class ToneResult:
    """Rich classification result from the V2 engine."""
    tone: int
    confidence: float
    scores: dict[int, float]         # {1: 0.8, 2: 0.3, ...}
    features: ToneFeatures | None
    ambiguous: bool
    runner_up: int
    margin: float
    diagnostics: list[str]
    surface_tone: int                # what speaker should produce (post-sandhi)
    underlying_tone: int             # citation/dictionary form
    family_matched: str = ""


# ── Feature extraction ────────────────────────────────────────────

def _interpolate_gaps(voiced_flags: np.ndarray, f0: np.ndarray,
                      max_gap: int = 2) -> np.ndarray:
    """Fill short unvoiced gaps (1-2 frames) between voiced regions via linear interp."""
    result = f0.copy()
    n = len(f0)
    i = 0
    while i < n:
        if not voiced_flags[i]:
            # find gap length
            gap_start = i
            while i < n and not voiced_flags[i]:
                i += 1
            gap_end = i
            gap_len = gap_end - gap_start
            if gap_len <= max_gap and gap_start > 0 and gap_end < n:
                # interpolate
                left = result[gap_start - 1]
                right = result[gap_end]
                for j in range(gap_start, gap_end):
                    t = (j - gap_start + 1) / (gap_len + 1)
                    result[j] = left + t * (right - left)
                    voiced_flags[j] = True
        else:
            i += 1
    return result


def _linear_slope(y: np.ndarray) -> float:
    """Compute slope of a linear regression fit, normalized to contour length."""
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    # slope = cov(x,y) / var(x)
    x_mean = x.mean()
    y_mean = y.mean()
    num = np.sum((x - x_mean) * (y - y_mean))
    den = np.sum((x - x_mean) ** 2)
    if den < 1e-12:
        return 0.0
    # Normalize slope by length so it's scale-independent
    return float(num / den) * n


def extract_tone_features(f0_contour: list[float],
                          calibration: dict = None) -> ToneFeatures | None:
    """Extract a rich feature vector from an F0 contour.

    Args:
        f0_contour: per-frame F0 values (0.0 = unvoiced)
        calibration: optional dict with f0_min, f0_max for speaker normalization

    Returns ToneFeatures or None if insufficient voiced data.
    """
    if not f0_contour:
        return None

    f0 = np.array(f0_contour, dtype=np.float64)
    voiced_flags = f0 > 0.0
    n_total = len(f0)
    n_voiced = int(voiced_flags.sum())

    if n_voiced < 3:
        return None

    # Interpolate short gaps
    voiced_flags_mut = voiced_flags.copy()
    f0 = _interpolate_gaps(voiced_flags_mut, f0)

    # Extract only voiced frames (post-interpolation)
    voiced = f0[voiced_flags_mut]
    mean_f0_hz = float(voiced.mean())

    # Normalize
    if (calibration and calibration.get("f0_min") is not None
            and calibration.get("f0_max") is not None):
        cal_min = calibration["f0_min"]
        cal_max = calibration["f0_max"]
        cal_range = cal_max - cal_min
        if cal_range < 10:
            cal_range = 10.0
        # 10% padding
        pad = cal_range * 0.1
        norm_min = cal_min - pad
        norm_range = cal_range + 2 * pad
        normed = np.clip((voiced - norm_min) / norm_range, 0.0, 1.0)
        norm_method = "speaker"
    else:
        v_min = voiced.min()
        v_max = voiced.max()
        v_range = v_max - v_min
        if v_range < 1e-6:
            # Truly flat — normalize to midpoint
            normed = np.full_like(voiced, 0.5)
        else:
            normed = (voiced - v_min) / v_range
        norm_method = "syllable"

    n = len(normed)

    # Onset / offset (15% windows)
    win = max(int(n * 0.15), 1)
    onset = float(normed[:win].mean())
    offset = float(normed[-win:].mean())

    # Valley / peak
    valley = float(normed.min())
    valley_pos = int(normed.argmin()) / max(n - 1, 1)
    peak = float(normed.max())
    peak_pos = int(normed.argmax()) / max(n - 1, 1)
    excursion = peak - valley

    # Slopes
    half = n // 2
    slope_first = _linear_slope(normed[:max(half, 2)])
    slope_second = _linear_slope(normed[max(half, 1):])
    overall = _linear_slope(normed)

    # Flatness: 1.0 - std (scaled to [0,1]; std of uniform [0,1] is ~0.289)
    std = float(normed.std())
    flatness = max(0.0, 1.0 - std / 0.289)

    voiced_ratio = n_voiced / n_total if n_total > 0 else 0.0

    return ToneFeatures(
        onset=round(onset, 4),
        offset=round(offset, 4),
        valley=round(valley, 4),
        valley_position=round(valley_pos, 4),
        peak=round(peak, 4),
        peak_position=round(peak_pos, 4),
        excursion=round(excursion, 4),
        slope_first_half=round(slope_first, 4),
        slope_second_half=round(slope_second, 4),
        overall_slope=round(overall, 4),
        flatness=round(flatness, 4),
        voiced_ratio=round(voiced_ratio, 4),
        n_voiced_frames=n_voiced,
        mean_f0_hz=round(mean_f0_hz, 2),
        norm_method=norm_method,
    )


def enrich_with_voice_quality(features: ToneFeatures,
                              extras: dict) -> ToneFeatures:
    """Enrich a ToneFeatures instance with voice quality data.

    Args:
        features: existing ToneFeatures from extract_tone_features()
        extras: dict from tone_grading.extract_voice_quality_extras()

    Returns the same ToneFeatures with extra fields populated.
    """
    if not extras:
        return features

    features.hnr_mean = extras.get("hnr_mean")
    features.jitter = extras.get("jitter")
    features.shimmer = extras.get("shimmer")
    features.f0_source = "pyin"

    # Intensity stats
    intensity = extras.get("intensity", [])
    if intensity:
        valid_int = [v for v in intensity if v > 0]
        if valid_int:
            features.intensity_mean = round(float(np.mean(valid_int)), 2)
            # Intensity slope — proxy for stress pattern
            if len(valid_int) >= 2:
                features.intensity_slope = round(
                    _linear_slope(np.array(valid_int)), 4
                )

    # Formant means (F1, F2 from valid frames)
    formants = extras.get("formants", [])
    if formants:
        f1_vals = [f[0] for f in formants if f[0] > 0]
        f2_vals = [f[1] for f in formants if f[1] > 0]
        if f1_vals:
            features.f1_mean = round(float(np.mean(f1_vals)), 1)
        if f2_vals:
            features.f2_mean = round(float(np.mean(f2_vals)), 1)

    return features


# ── Contour families ──────────────────────────────────────────────

# Each family defines acceptable feature ranges for a tone realization.
# Fields: (feature_name, min_val, max_val) tuples.
# A contour "matches" a family if all constraints are satisfied.
# Score = fraction of constraints satisfied (soft matching).

TONE_FAMILIES = {
    1: [
        {
            "name": "high_flat",
            "constraints": {
                "excursion": (None, 0.2),
                "onset": (0.5, None),
                "flatness": (0.7, None),
            },
            "weight": 1.0,
        },
        {
            "name": "mid_flat",
            "constraints": {
                "excursion": (None, 0.2),
                "onset": (0.3, None),
                "flatness": (0.6, None),
            },
            "weight": 0.8,
        },
    ],
    2: [
        {
            "name": "mid_rising",
            "constraints": {
                "overall_slope": (0.05, None),
                "offset": (None, None),  # no constraint, but offset > onset checked below
                "_offset_gt_onset": True,
            },
            "weight": 1.0,
        },
        {
            "name": "low_rising",
            "constraints": {
                "onset": (None, 0.4),
                "offset": (0.4, None),
                "overall_slope": (0.03, None),
            },
            "weight": 0.9,
        },
    ],
    3: [
        {
            "name": "full_dip",
            "constraints": {
                "valley_position": (0.2, 0.8),
                "valley": (None, 0.35),
                "excursion": (0.2, None),
            },
            "weight": 1.0,
        },
        {
            "name": "half_third",
            "constraints": {
                "onset": (None, 0.5),
                "offset": (None, 0.4),
                "slope_first_half": (None, -0.03),
                "valley": (None, 0.35),
            },
            "weight": 1.0,
        },
        {
            "name": "low_flat",
            "constraints": {
                "onset": (None, 0.35),
                "offset": (None, 0.35),
                "excursion": (None, 0.2),
            },
            "weight": 0.85,
        },
    ],
    4: [
        {
            "name": "high_falling",
            "constraints": {
                "onset": (0.5, None),
                "overall_slope": (None, -0.08),
            },
            "weight": 1.0,
        },
        {
            "name": "mid_falling",
            "constraints": {
                "onset": (0.3, None),
                "overall_slope": (None, -0.04),
                "offset": (None, 0.5),
            },
            "weight": 0.85,
        },
    ],
}


def _check_constraint(features: ToneFeatures, feat_name: str,
                      bounds: tuple) -> float:
    """Check a single constraint. Returns 1.0 if met, partial credit for near-miss."""
    if feat_name.startswith("_"):
        # Special constraints
        if feat_name == "_offset_gt_onset":
            return 1.0 if features.offset > features.onset else 0.0
        return 1.0

    val = getattr(features, feat_name, None)
    if val is None:
        return 0.0

    lo, hi = bounds
    if lo is not None and hi is not None:
        # Range constraint
        if lo <= val <= hi:
            return 1.0
        # Partial credit for near-miss (within 50% of range width)
        width = hi - lo
        margin = width * 0.5
        if val < lo:
            dist = lo - val
            return max(0.0, 1.0 - dist / max(margin, 0.01))
        else:
            dist = val - hi
            return max(0.0, 1.0 - dist / max(margin, 0.01))
    elif lo is not None:
        # Lower bound only
        if val >= lo:
            return 1.0
        dist = lo - val
        return max(0.0, 1.0 - dist / max(abs(lo) * 0.5 + 0.05, 0.05))
    elif hi is not None:
        # Upper bound only
        if val <= hi:
            return 1.0
        dist = val - hi
        return max(0.0, 1.0 - dist / max(abs(hi) * 0.5 + 0.05, 0.05))
    else:
        return 1.0  # No constraint


def score_against_families(features: ToneFeatures,
                           mode: str = "connected") -> dict[int, tuple[float, str]]:
    """Score features against all tone families.

    Returns {tone: (best_score, family_name)} for tones 1-4.
    """
    results = {}
    for tone, families in TONE_FAMILIES.items():
        best_score = 0.0
        best_family = ""
        for fam in families:
            constraints = fam["constraints"]
            weight = fam["weight"]
            name = fam["name"]

            # Mode adjustments
            if mode == "isolated" and name == "half_third":
                weight *= 0.5
            elif mode == "isolated" and name == "low_flat":
                weight *= 0.5

            n_constraints = len(constraints)
            if n_constraints == 0:
                score = weight
            else:
                total = 0.0
                for feat_name, bounds in constraints.items():
                    if feat_name.startswith("_"):
                        total += _check_constraint(features, feat_name, bounds)
                    else:
                        total += _check_constraint(features, feat_name, bounds)
                score = (total / n_constraints) * weight

            if score > best_score:
                best_score = score
                best_family = name

        results[tone] = (round(best_score, 4), best_family)
    return results


# ── Syllable segmentation ─────────────────────────────────────────

def segment_syllable_nuclei(audio: np.ndarray, n_syllables: int,
                            sr: int = 16000) -> list[tuple[int, int]]:
    """Segment audio into syllable regions using short-time energy.

    Returns list of (start_sample, end_sample) tuples.
    Falls back to even-split if energy peaks aren't cleanly separable.
    """
    if n_syllables <= 0:
        return []
    if n_syllables == 1:
        return [(0, len(audio))]

    # Short-time energy: 20ms frames, 5ms hop
    frame_len = int(sr * 0.020)
    hop_len = int(sr * 0.005)

    if len(audio) < frame_len:
        # Too short — even split
        return _even_split(len(audio), n_syllables)

    # Compute energy per frame
    n_frames = (len(audio) - frame_len) // hop_len + 1
    energy = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_len
        frame = audio[start:start + frame_len]
        energy[i] = np.sum(frame ** 2)

    # Smooth with 50ms moving average
    smooth_width = max(int(0.050 / 0.005), 1)  # 10 frames
    if len(energy) >= smooth_width:
        kernel = np.ones(smooth_width) / smooth_width
        energy_smooth = np.convolve(energy, kernel, mode='same')
    else:
        energy_smooth = energy

    # Find peaks (syllable centers)
    peaks = _find_energy_peaks(energy_smooth, n_syllables)

    if len(peaks) != n_syllables:
        return _even_split(len(audio), n_syllables)

    # Convert frame indices to sample boundaries
    segments = []
    for i, peak in enumerate(peaks):
        if i == 0:
            start_frame = 0
        else:
            # Boundary = valley between this peak and previous
            prev_peak = peaks[i - 1]
            valley_region = energy_smooth[prev_peak:peak]
            if len(valley_region) > 0:
                start_frame = prev_peak + int(np.argmin(valley_region))
            else:
                start_frame = (prev_peak + peak) // 2

        if i == len(peaks) - 1:
            end_frame = n_frames - 1
        else:
            next_peak = peaks[i + 1]
            valley_region = energy_smooth[peak:next_peak]
            if len(valley_region) > 0:
                end_frame = peak + int(np.argmin(valley_region))
            else:
                end_frame = (peak + next_peak) // 2

        start_sample = start_frame * hop_len
        end_sample = min(end_frame * hop_len + frame_len, len(audio))
        segments.append((start_sample, end_sample))

    return segments


def _find_energy_peaks(energy: np.ndarray, n_expected: int) -> list[int]:
    """Find n_expected peaks in energy contour."""
    if len(energy) < n_expected:
        return []

    # Simple approach: find all local maxima, keep top n_expected
    peaks = []
    for i in range(1, len(energy) - 1):
        if energy[i] > energy[i - 1] and energy[i] >= energy[i + 1]:
            peaks.append((i, energy[i]))

    if not peaks:
        # No local maxima — use evenly spaced points
        return [int(i * len(energy) / n_expected + len(energy) / (2 * n_expected))
                for i in range(n_expected)]

    # Sort by energy, keep top n_expected
    peaks.sort(key=lambda x: x[1], reverse=True)
    selected = sorted([p[0] for p in peaks[:n_expected]])

    # Merge peaks that are too close (within 20% of expected spacing)
    min_spacing = len(energy) / (n_expected * 3)
    merged = [selected[0]]
    for p in selected[1:]:
        if p - merged[-1] > min_spacing:
            merged.append(p)
        else:
            # Keep the higher-energy one
            if energy[p] > energy[merged[-1]]:
                merged[-1] = p

    return merged if len(merged) == n_expected else []


def _even_split(total_len: int, n: int) -> list[tuple[int, int]]:
    """Even-split fallback."""
    seg_len = total_len // n if n > 0 else total_len
    segments = []
    for i in range(n):
        start = i * seg_len
        end = start + seg_len if i < n - 1 else total_len
        segments.append((start, end))
    return segments


# ── Diagnostics ───────────────────────────────────────────────────

# Keyed by (expected_tone, condition_fn) → diagnostic label
# condition_fn takes ToneFeatures, returns bool

DIAGNOSTIC_RULES: list[tuple[int, str, object, str]] = [
    # (expected_tone, feature_name, condition_fn, label)
    (1, "overall_slope", lambda f: f.overall_slope > 0.05, "pitch_drifted_up"),
    (1, "overall_slope", lambda f: f.overall_slope < -0.05, "pitch_drifted_down"),
    (2, "overall_slope", lambda f: f.overall_slope < 0.03, "rise_too_small"),
    (2, "offset", lambda f: f.offset < 0.5, "didnt_reach_high_enough"),
    (3, "valley", lambda f: f.valley > 0.35, "didnt_go_low_enough"),
    (3, "valley_position", lambda f: f.valley_position < 0.2, "dipped_too_early"),
    (4, "overall_slope", lambda f: f.overall_slope > -0.03, "fall_too_small"),
    (4, "onset", lambda f: f.onset < 0.5, "didnt_start_high_enough"),
]

DIAGNOSTIC_TIPS = {
    "pitch_drifted_up": "Tone 1 should stay flat. Your pitch crept upward.",
    "pitch_drifted_down": "Tone 1 should stay flat. Your pitch drifted downward.",
    "rise_too_small": "Your pitch rose but not enough \u2014 try exaggerating the upward sweep.",
    "didnt_reach_high_enough": "The rise didn\u2019t reach high enough. Push your pitch up more at the end.",
    "didnt_go_low_enough": "The dip wasn\u2019t deep enough. Really let your voice drop.",
    "dipped_too_early": "You dipped too early in the syllable. The low point should come around the middle.",
    "fall_too_small": "Your pitch fell but not enough \u2014 try a sharper, more decisive drop.",
    "didnt_start_high_enough": "Tone 4 starts high. Begin at the top of your range before dropping.",
}


def generate_diagnostics(features: ToneFeatures,
                         expected_tone: int) -> list[str]:
    """Generate diagnostic labels for a syllable based on features vs expected tone."""
    if features is None or expected_tone < 1 or expected_tone > 4:
        return []

    labels = []
    for tone, _feat, condition_fn, label in DIAGNOSTIC_RULES:
        if tone == expected_tone:
            try:
                if condition_fn(features):
                    labels.append(label)
            except (AttributeError, TypeError):
                pass
    return labels


def classify_tone_v2(f0_contour: list[float],
                     calibration: dict = None,
                     mode: str = "connected",
                     expected_tone: int = 0,
                     half_third_expected: bool = False) -> ToneResult:
    """Full V2 tone classification with rich output.

    Args:
        f0_contour: per-frame F0 values
        calibration: speaker calibration dict
        mode: "isolated" or "connected"
        expected_tone: if known, used for diagnostics
        half_third_expected: if True, boost half_third/low_flat families

    Returns ToneResult with tone, confidence, scores, features, diagnostics.
    """
    features = extract_tone_features(f0_contour, calibration)

    if features is None:
        return ToneResult(
            tone=0, confidence=0.0, scores={}, features=None,
            ambiguous=False, runner_up=0, margin=0.0,
            diagnostics=[], surface_tone=0, underlying_tone=0,
        )

    # Score against families
    family_scores = score_against_families(features, mode=mode)

    # If half-third expected (T3 before non-T3), boost T3 half_third/low_flat
    if half_third_expected:
        t3_score, t3_family = family_scores[3]
        # Give T3 a boost since half-third is the expected realization
        if t3_family in ("half_third", "low_flat"):
            family_scores[3] = (min(t3_score * 1.3, 1.0), t3_family)
        elif t3_score < 0.5:
            # Re-check specifically for half_third pattern
            for fam in TONE_FAMILIES[3]:
                if fam["name"] in ("half_third", "low_flat"):
                    n_c = len(fam["constraints"])
                    total = 0.0
                    for fn, bounds in fam["constraints"].items():
                        total += _check_constraint(features, fn, bounds)
                    score = (total / n_c) * fam["weight"] * 1.2
                    if score > t3_score:
                        family_scores[3] = (min(round(score, 4), 1.0), fam["name"])
                        break

    # Find best and runner-up
    sorted_tones = sorted(family_scores.items(), key=lambda x: x[1][0], reverse=True)

    best_tone = sorted_tones[0][0]
    best_score = sorted_tones[0][1][0]
    best_family = sorted_tones[0][1][1]

    runner_up_tone = sorted_tones[1][0] if len(sorted_tones) > 1 else 0
    runner_up_score = sorted_tones[1][1][0] if len(sorted_tones) > 1 else 0.0

    margin = best_score - runner_up_score
    ambiguous = margin < 0.15 and best_score > 0.0

    # Confidence: normalize best score relative to total
    total_score = sum(s for s, _ in family_scores.values())
    confidence = best_score / total_score if total_score > 0 else 0.0

    # Diagnostics
    diagnostics = generate_diagnostics(features, expected_tone) if expected_tone > 0 else []

    scores_dict = {t: s for t, (s, _) in family_scores.items()}

    return ToneResult(
        tone=best_tone,
        confidence=round(min(confidence, 1.0), 4),
        scores=scores_dict,
        features=features,
        ambiguous=ambiguous,
        runner_up=runner_up_tone,
        margin=round(margin, 4),
        diagnostics=diagnostics,
        surface_tone=expected_tone,
        underlying_tone=expected_tone,
        family_matched=best_family,
    )
