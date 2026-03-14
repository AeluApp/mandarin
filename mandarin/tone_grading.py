"""Tone grading — record voice and grade Mandarin tone accuracy.

Primary F0 backend: librosa pYIN (probabilistic YIN pitch tracker, ISC license).
Fallback: YIN algorithm (pure numpy, no external deps).

Web mode: set_web_recording_callback() enables browser-based recording via
getUserMedia, bridged through WebSocket.
"""

import json
import logging
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import numpy as np
    import sounddevice as sd
    HAS_AUDIO_INPUT = True
except ImportError:
    logger.info("numpy/sounddevice not available; audio input disabled")
    HAS_AUDIO_INPUT = False

try:
    import librosa
    HAS_LIBROSA = True
    logger.info("librosa available — using pYIN pitch tracker")
except ImportError:
    HAS_LIBROSA = False
    logger.info("librosa not available — using YIN fallback")

from . import db
from .tone_features import (
    ToneResult, classify_tone_v2, enrich_with_voice_quality,
    extract_tone_features, generate_diagnostics, score_against_families,
    segment_syllable_nuclei, DIAGNOSTIC_TIPS,
)


SAMPLE_RATE = 16000  # 16kHz mono — sufficient for voice
MAX_RECORD_SECONDS = 5
RECORDINGS_DIR = Path(__file__).parent.parent / "data" / "recordings"


def validate_audio_sanity(audio_data, sample_rate=16000):
    """Reject adversarial or invalid audio before tone grading.

    NIST AI RMF (AI-003): pre-grading validation to detect silence,
    clipping, and out-of-range duration that could exploit the tone
    grading pipeline.

    Returns (is_valid, reason) tuple.
    """
    import numpy as np

    if audio_data is None or len(audio_data) == 0:
        return False, "empty_audio"

    # RMS check: reject silence (< -40dB)
    rms = np.sqrt(np.mean(np.array(audio_data, dtype=float) ** 2))
    if rms < 0.001:
        return False, "silence"

    # Clipping check: reject if >5% samples at +/-0.95
    arr = np.array(audio_data, dtype=float)
    if len(arr) > 0:
        clip_ratio = np.sum(np.abs(arr) > 0.95) / len(arr)
        if clip_ratio > 0.05:
            return False, "clipping"

    # Duration check: reject if < 0.2s or > 10s
    duration = len(audio_data) / sample_rate
    if duration < 0.2:
        return False, "too_short"
    if duration > 10:
        return False, "too_long"

    return True, "ok"

# Thread-local web recording callback — when set, recording uses browser mic
_web_recording = threading.local()


def set_web_recording_callback(callback, has_mic=True):
    """Set callback for web recording: callback(duration) returns numpy array or None."""
    _web_recording.callback = callback
    _web_recording.has_mic = has_mic


def clear_web_recording_callback():
    """Clear the web recording callback (return to local recording)."""
    _web_recording.callback = None


def is_recording_available() -> bool:
    """Check if voice recording is possible."""
    # Web mode — browser has mic access
    callback = getattr(_web_recording, "callback", None)
    if callback:
        return getattr(_web_recording, "has_mic", True)
    if not HAS_AUDIO_INPUT:
        return False
    try:
        devices = sd.query_devices()
        # Check for at least one input device
        for d in devices if isinstance(devices, list) else [devices]:
            if isinstance(d, dict) and d.get("max_input_channels", 0) > 0:
                return True
        return False
    except OSError:
        logger.debug("Audio device query failed", exc_info=True)
        return False


def record_audio(duration: float = MAX_RECORD_SECONDS):
    """Record audio from the microphone. Returns (numpy_array, transcript) or (None, None).

    In web mode, transcript is the browser SpeechRecognition result (zh-CN).
    In CLI mode, transcript is always None.
    """
    # Web mode — delegate to browser
    callback = getattr(_web_recording, "callback", None)
    if callback:
        try:
            result = callback(duration)
            # Web callback returns (audio, transcript) tuple
            if isinstance(result, tuple):
                return result
            # Backwards compat: raw numpy array
            return (result, None)
        except (TypeError, OSError, ConnectionError) as e:
            logger.warning("Web recording callback failed: %s", e)
            return (None, None)
    if not HAS_AUDIO_INPUT:
        return (None, None)
    try:
        audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                       channels=1, dtype="float32")
        sd.wait()
        return (audio.flatten(), None)
    except OSError:
        logger.warning("Local audio recording failed", exc_info=True)
        return (None, None)


def save_recording(audio: "np.ndarray", content_item_id: int,
                   session_id: int) -> Optional[Path]:
    """Save recording as WAV file. Returns path."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_item{content_item_id}.wav"
    path = RECORDINGS_DIR / filename

    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())

    return path


# ── Pitch extraction ──────────────────────────────

def extract_f0_pyin(audio: "np.ndarray", sr: int = SAMPLE_RATE,
                    hop_ms: int = 10,
                    fmin: float = 75.0, fmax: float = 500.0) -> List[float]:
    """Extract F0 using librosa's pYIN (probabilistic YIN) pitch tracker.

    pYIN adds a hidden Markov model on top of YIN for smoother, more
    accurate pitch tracking with better voicing decisions than raw YIN.

    Returns list of F0 values (Hz) per frame. 0.0 = unvoiced.
    """
    if not HAS_LIBROSA or len(audio) == 0:
        return []

    try:
        hop_length = int(sr * hop_ms / 1000)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            audio.astype(np.float64),
            fmin=fmin,
            fmax=fmax,
            sr=sr,
            hop_length=hop_length,
        )

        # pyin returns NaN for unvoiced frames — convert to 0.0
        return [round(float(v), 2) if not np.isnan(v) else 0.0 for v in f0]

    except Exception as e:
        logger.warning("librosa pYIN F0 extraction failed: %s", e)
        return []


def extract_voice_quality_extras(audio: "np.ndarray", sr: int = SAMPLE_RATE,
                                  fmin: float = 75.0, fmax: float = 500.0) -> dict:
    """Extract voice quality features using librosa and numpy.

    Returns dict with:
        - hnr_mean: harmonics-to-noise ratio estimate (dB)
        - formants: list of (F1, F2, F3) tuples per frame via LPC
        - intensity: list of RMS intensity values (dB) per frame
        - jitter: local jitter (period perturbation) from F0
        - shimmer: local shimmer (amplitude perturbation) from RMS
    Returns empty dict if librosa unavailable or extraction fails.
    """
    if not HAS_LIBROSA or len(audio) == 0:
        return {}

    try:
        audio_f64 = audio.astype(np.float64)
        extras = {}
        hop_length = int(sr * 0.010)   # 10ms
        frame_length = int(sr * 0.025)  # 25ms

        # --- F0 via pYIN (needed for jitter) ---
        f0, voiced_flag, _ = librosa.pyin(
            audio_f64, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop_length,
        )
        voiced_f0 = [float(v) for v in f0 if not np.isnan(v) and v > 0]

        # --- HNR estimate via autocorrelation ---
        min_lag = int(sr / fmax)
        max_lag = int(sr / fmin)
        corr = np.correlate(audio_f64, audio_f64, mode='full')
        mid = len(audio_f64) - 1
        corr_pos = corr[mid:]  # positive lags only
        if corr_pos[0] > 0 and max_lag < len(corr_pos):
            corr_norm = corr_pos / corr_pos[0]
            peak = float(np.max(corr_norm[min_lag:max_lag + 1]))
            peak = min(peak, 0.9999)
            extras["hnr_mean"] = round(10 * np.log10(peak / (1 - peak)), 2) if peak > 0 else 0.0
        else:
            extras["hnr_mean"] = 0.0

        # --- Formants via LPC per frame ---
        lpc_order = 2 + int(sr / 1000)  # ~18 for 16kHz
        formant_frames = []
        for start in range(0, len(audio_f64) - frame_length, hop_length):
            frame = audio_f64[start:start + frame_length]
            # Pre-emphasis + windowing
            frame_pre = np.append(frame[0], frame[1:] - 0.97 * frame[:-1])
            frame_win = frame_pre * np.hamming(len(frame_pre))
            try:
                a = librosa.lpc(frame_win, order=lpc_order)
                roots = np.roots(a)
                roots = roots[np.imag(roots) > 0]
                freqs = np.abs(np.arctan2(np.imag(roots), np.real(roots))) * sr / (2 * np.pi)
                freqs = np.sort(freqs[(freqs > 90) & (freqs < 5500)])
                f1 = round(float(freqs[0]), 1) if len(freqs) > 0 else 0.0
                f2 = round(float(freqs[1]), 1) if len(freqs) > 1 else 0.0
                f3 = round(float(freqs[2]), 1) if len(freqs) > 2 else 0.0
                formant_frames.append((f1, f2, f3))
            except Exception:
                formant_frames.append((0.0, 0.0, 0.0))
        extras["formants"] = formant_frames

        # --- Intensity (RMS → dB) per frame ---
        rms = librosa.feature.rms(
            y=audio_f64, frame_length=frame_length, hop_length=hop_length
        )[0]
        extras["intensity"] = [
            round(float(20 * np.log10(max(v, 1e-10))), 2) for v in rms
        ]

        # --- Jitter from F0 periods ---
        if len(voiced_f0) >= 2:
            periods = [1.0 / f for f in voiced_f0]
            diffs = [abs(periods[i + 1] - periods[i]) for i in range(len(periods) - 1)]
            extras["jitter"] = round(float(np.mean(diffs) / np.mean(periods)), 6)
        else:
            extras["jitter"] = 0.0

        # --- Shimmer from per-frame RMS at voiced frames ---
        if len(voiced_f0) >= 2 and len(rms) > 0:
            voiced_rms = [float(rms[i]) for i, v in enumerate(voiced_flag)
                          if v and i < len(rms) and rms[i] > 0]
            if len(voiced_rms) >= 2:
                amp_diffs = [abs(voiced_rms[i + 1] - voiced_rms[i])
                             for i in range(len(voiced_rms) - 1)]
                mean_amp = float(np.mean(voiced_rms))
                extras["shimmer"] = round(float(np.mean(amp_diffs) / mean_amp), 6) if mean_amp > 0 else 0.0
            else:
                extras["shimmer"] = 0.0
        else:
            extras["shimmer"] = 0.0

        return extras

    except Exception as e:
        logger.warning("voice quality extraction failed: %s", e)
        return {}


def _extract_f0_autocorr(audio: "np.ndarray", sr: int = SAMPLE_RATE,
                         frame_ms: int = 30, hop_ms: int = 10,
                         fmin: float = 75.0, fmax: float = 500.0) -> List[float]:
    """Extract F0 using autocorrelation (legacy, kept as reference).

    Returns list of F0 values (Hz) per frame. 0.0 = unvoiced.
    """
    frame_len = int(sr * frame_ms / 1000)
    hop_len = int(sr * hop_ms / 1000)
    min_lag = int(sr / fmax)
    max_lag = int(sr / fmin)

    f0_values = []
    for start in range(0, len(audio) - frame_len, hop_len):
        frame = audio[start:start + frame_len]

        # Apply Hanning window
        frame = frame * np.hanning(frame_len)

        # Autocorrelation
        corr = np.correlate(frame, frame, mode="full")
        corr = corr[frame_len - 1:]  # Keep positive lags only

        # Normalize
        if corr[0] == 0:
            f0_values.append(0.0)
            continue
        corr = corr / corr[0]

        # Find peak in valid lag range
        search_start = min(min_lag, len(corr) - 1)
        search_end = min(max_lag + 1, len(corr))

        if search_start >= search_end:
            f0_values.append(0.0)
            continue

        region = corr[search_start:search_end]
        peak_idx = np.argmax(region)
        peak_val = region[peak_idx]

        # Voicing threshold
        if peak_val < 0.4:
            f0_values.append(0.0)
        else:
            lag = search_start + peak_idx
            half_lag = lag // 2
            if half_lag >= min_lag and half_lag < len(corr):
                if corr[half_lag] > 0.7 * corr[lag]:
                    lag = half_lag
            f0_values.append(sr / lag if lag > 0 else 0.0)

    return f0_values


def extract_f0_yin(audio: "np.ndarray", sr: int = SAMPLE_RATE,
                   frame_ms: int = 30, hop_ms: int = 10,
                   fmin: float = 75.0, fmax: float = 500.0,
                   threshold: float = 0.15) -> List[float]:
    """Extract F0 using the YIN algorithm.

    YIN: a fundamental frequency estimator for speech and music
    (de Cheveigné & Kawahara, 2002). Uses cumulative mean normalized
    difference function with absolute threshold and parabolic interpolation.

    Returns list of F0 values (Hz) per frame. 0.0 = unvoiced.
    """
    frame_len = int(sr * frame_ms / 1000)
    hop_len = int(sr * hop_ms / 1000)
    min_lag = int(sr / fmax)
    max_lag = int(sr / fmin)

    f0_values = []
    for start in range(0, len(audio) - frame_len, hop_len):
        frame = audio[start:start + frame_len]

        # Step 1: Difference function d(tau)
        # d(tau) = sum_j (x[j] - x[j+tau])^2
        half_len = frame_len // 2
        if half_len < max_lag + 1:
            f0_values.append(0.0)
            continue

        d = np.zeros(half_len)
        for tau in range(1, half_len):
            diff = frame[:half_len] - frame[tau:tau + half_len]
            d[tau] = np.sum(diff * diff)

        # Step 2: Cumulative mean normalized difference function d'(tau)
        # d'(0) = 1; d'(tau) = d(tau) / ((1/tau) * sum_{j=1}^{tau} d(j))
        d_prime = np.ones(half_len)
        running_sum = 0.0
        for tau in range(1, half_len):
            running_sum += d[tau]
            if running_sum == 0:
                d_prime[tau] = 1.0
            else:
                d_prime[tau] = d[tau] * tau / running_sum

        # Step 3: Absolute threshold — find first tau in [min_lag, max_lag]
        # where d'(tau) < threshold, then pick the local minimum from there
        search_end = min(max_lag + 1, half_len)
        best_tau = 0

        for tau in range(min_lag, search_end):
            if d_prime[tau] < threshold:
                # Walk forward to find the local minimum
                while tau + 1 < search_end and d_prime[tau + 1] < d_prime[tau]:
                    tau += 1
                best_tau = tau
                break

        if best_tau == 0:
            # No dip below threshold — pick global minimum as fallback
            if min_lag < search_end:
                region = d_prime[min_lag:search_end]
                min_idx = np.argmin(region)
                min_val = region[min_idx]
                # Only accept if reasonably periodic (lenient fallback)
                if min_val < 0.5:
                    best_tau = min_lag + min_idx
                else:
                    f0_values.append(0.0)
                    continue
            else:
                f0_values.append(0.0)
                continue

        # Step 4: Parabolic interpolation for sub-sample accuracy
        if 0 < best_tau < half_len - 1:
            alpha = d_prime[best_tau - 1]
            beta = d_prime[best_tau]
            gamma = d_prime[best_tau + 1]
            denom = alpha - 2.0 * beta + gamma
            if abs(denom) > 1e-10:
                adjustment = 0.5 * (alpha - gamma) / denom
                refined_tau = best_tau + adjustment
            else:
                refined_tau = float(best_tau)
        else:
            refined_tau = float(best_tau)

        if refined_tau > 0:
            f0_values.append(sr / refined_tau)
        else:
            f0_values.append(0.0)

    return f0_values


def extract_f0(audio: "np.ndarray", sr: int = SAMPLE_RATE,
               frame_ms: int = 30, hop_ms: int = 10,
               fmin: float = 75.0, fmax: float = 500.0) -> List[float]:
    """Extract fundamental frequency contour.

    Tries librosa pYIN first for HMM-smoothed accuracy,
    falls back to YIN if librosa is unavailable or fails.

    Returns list of F0 values (Hz) per frame. 0.0 = unvoiced.
    """
    if HAS_LIBROSA:
        result = extract_f0_pyin(audio, sr, hop_ms=hop_ms,
                                 fmin=fmin, fmax=fmax)
        if result:
            return result
        logger.debug("pYIN returned empty — falling back to YIN")

    return extract_f0_yin(audio, sr, frame_ms, hop_ms, fmin, fmax)


# ── Tone classification ──────────────────────────────

# Mandarin tones as pitch contour shapes
# Each tone maps to a characteristic F0 trajectory pattern
TONE_PATTERNS = {
    1: "flat",      # High flat
    2: "rising",    # Mid rising
    3: "dipping",   # Low dipping (fall-rise)
    4: "falling",   # High falling
}


def classify_tone(f0_contour: List[float],
                  calibration: dict = None) -> Tuple[int, float]:
    """Classify a single-syllable F0 contour into Mandarin tone 1-4.

    Args:
        f0_contour: per-frame F0 values (0.0 = unvoiced)
        calibration: optional dict with f0_min, f0_max from speaker calibration.
            When provided, normalizes against the speaker's known pitch range
            instead of the per-syllable min/max (preserves inter-syllable info).

    Returns (tone_number, confidence) where confidence is 0.0-1.0.
    Backward-compatible wrapper around the V2 engine.
    """
    # Filter out unvoiced frames for the flat-pitch fast path
    voiced = [f for f in f0_contour if f > 0]
    if len(voiced) < 3:
        return (0, 0.0)

    # Per-syllable flat pitch fast path (preserves exact V1 behavior for tests)
    if not (calibration and calibration.get("f0_min") and calibration.get("f0_max")):
        min_f = min(voiced)
        max_f = max(voiced)
        spread = max_f - min_f
        if spread < 5:
            return (1, 0.7)

    result = classify_tone_v2(f0_contour, calibration=calibration)
    return (result.tone, result.confidence)


# ── Speaker calibration ──────────────────────────────

def run_tone_calibration(audio: "np.ndarray", sr: int = SAMPLE_RATE) -> Optional[dict]:
    """Extract speaker's F0 range from a calibration phrase (e.g. māmámǎmà).

    Returns dict with f0_min, f0_max, f0_mean (10th/90th percentile)
    or None if insufficient voiced data.
    """
    f0 = extract_f0(audio, sr)
    voiced = [f for f in f0 if f > 0]
    if len(voiced) < 10:
        return None

    arr = np.array(voiced)
    return {
        "f0_min": round(float(np.percentile(arr, 10)), 1),
        "f0_max": round(float(np.percentile(arr, 90)), 1),
        "f0_mean": round(float(np.mean(arr)), 1),
    }


def save_speaker_calibration(conn, calibration: dict, user_id: int = 1) -> None:
    """Store speaker calibration in the database."""
    conn.execute("""
        INSERT INTO speaker_calibration (user_id, f0_min, f0_max, f0_mean)
        VALUES (?, ?, ?, ?)
    """, (user_id, calibration["f0_min"], calibration["f0_max"],
          calibration["f0_mean"]))
    conn.commit()


def get_speaker_calibration(conn, user_id: int = 1) -> Optional[dict]:
    """Load the most recent speaker calibration from the database.

    Returns dict with f0_min, f0_max, f0_mean or None if not calibrated.
    """
    row = conn.execute("""
        SELECT f0_min, f0_max, f0_mean, calibrated_at
        FROM speaker_calibration
        WHERE user_id = ?
        ORDER BY calibrated_at DESC
        LIMIT 1
    """, (user_id,)).fetchone()
    if row is None:
        return None
    return {
        "f0_min": row["f0_min"],
        "f0_max": row["f0_max"],
        "f0_mean": row["f0_mean"],
        "calibrated_at": row["calibrated_at"],
    }


def _apply_sandhi_rules(tones: List[int]) -> Tuple[List[int], List[int], List[bool]]:
    """Apply Mandarin tone sandhi rules to expected tones.

    Rules applied:
    1. Third-tone sandhi: tone 3 before tone 3 becomes tone 2
       e.g., 你好 nǐ hǎo → ní hǎo (expected [3,3] → [2,3])
    2. Sequential third tones: in chains of 3+, all but last become tone 2
       e.g., 我也好 wǒ yě hǎo → wó yé hǎo
    3. Tone 3 before non-tone-3 → half-third expected (internal marker)

    Note: 一 and 不 sandhi are handled at the pinyin level (pinyin_to_tones
    already extracts the surface tone from tone-marked pinyin).

    Returns:
        (surface_tones, underlying_tones, half_third_markers)
        - surface_tones: what the speaker should produce
        - underlying_tones: citation/dictionary form (unchanged input)
        - half_third_markers: True where half-third realization is acceptable
    """
    underlying = list(tones)
    surface = list(tones)
    half_third = [False] * len(tones)

    if len(tones) < 2:
        return (surface, underlying, half_third)

    # Third-tone sandhi: consecutive T3 runs → all but last become T2
    i = 0
    while i < len(surface):
        if surface[i] == 3:
            run_end = i + 1
            while run_end < len(surface) and surface[run_end] == 3:
                run_end += 1
            for j in range(i, run_end - 1):
                surface[j] = 2
            i = run_end
        else:
            i += 1

    # Mark T3 before non-T3 as half-third expected
    for i in range(len(underlying)):
        if underlying[i] == 3 and i < len(underlying) - 1 and underlying[i + 1] != 3:
            half_third[i] = True

    return (surface, underlying, half_third)


def get_tone_leniency(speaking_level: float) -> dict:
    """Return proficiency-scaled leniency parameters for tone grading.

    Beginners get generous partial credit; advanced learners are held to
    higher standards.  Linear interpolation within each band.

    Bands:
      1.0-2.0 (beginner)     → pass 0.35, close_pair 0.6, unclassified 0.4, floor 0.90
      2.0-4.0 (intermediate) → pass 0.50, close_pair 0.5, unclassified 0.3, floor 0.85
      4.0-6.0 (advanced)     → pass 0.60, close_pair 0.35, unclassified 0.2, floor 0.80
      6.0+    (proficient)   → pass 0.65, close_pair 0.25, unclassified 0.15, floor 0.75
    """
    bands = [
        (1.0, {"pass_threshold": 0.35, "close_pair_credit": 0.60,
                "unclassified_credit": 0.40, "transcript_floor": 0.90}),
        (2.0, {"pass_threshold": 0.50, "close_pair_credit": 0.50,
                "unclassified_credit": 0.30, "transcript_floor": 0.85}),
        (4.0, {"pass_threshold": 0.60, "close_pair_credit": 0.35,
                "unclassified_credit": 0.20, "transcript_floor": 0.80}),
        (6.0, {"pass_threshold": 0.65, "close_pair_credit": 0.25,
                "unclassified_credit": 0.15, "transcript_floor": 0.75}),
    ]
    level = max(1.0, speaking_level)

    # Clamp to top band
    if level >= bands[-1][0]:
        return dict(bands[-1][1])

    # Find surrounding bands and interpolate
    for i in range(len(bands) - 1):
        lo_level, lo_vals = bands[i]
        hi_level, hi_vals = bands[i + 1]
        if level <= hi_level:
            t = (level - lo_level) / (hi_level - lo_level)
            return {
                k: round(lo_vals[k] + t * (hi_vals[k] - lo_vals[k]), 3)
                for k in lo_vals
            }

    return dict(bands[-1][1])


def grade_tones(audio: "np.ndarray", expected_tones: List[int],
                sr: int = SAMPLE_RATE, leniency: dict = None,
                calibration: dict = None) -> dict:
    """Grade pronunciation against expected tone sequence.

    Args:
        audio: recorded audio array
        expected_tones: list of expected tone numbers (1-4)
        leniency: optional dict from get_tone_leniency() with credit overrides
        calibration: optional dict from get_speaker_calibration() for F0 normalization

    Returns dict with:
        - syllable_scores: list of {expected, detected, correct, confidence, ...}
        - overall_score: 0.0-1.0
        - feedback: human-readable feedback string
    """
    # NIST AI RMF (AI-003): validate audio before processing
    is_valid, reason = validate_audio_sanity(audio, sr)
    if not is_valid:
        logger.warning("Audio sanity check failed: %s", reason)
        return {
            "syllable_scores": [],
            "overall_score": 0.0,
            "feedback": f"Audio rejected: {reason}. Please try recording again.",
            "audio_validation": reason,
        }

    f0 = extract_f0(audio, sr)

    if not f0 or not expected_tones:
        return {
            "syllable_scores": [],
            "overall_score": 0.0,
            "feedback": "Could not detect speech. Try speaking closer to the mic.",
        }

    # Extract voice quality extras (non-blocking — empty dict on failure)
    vq_extras = extract_voice_quality_extras(audio, sr) if HAS_LIBROSA else {}

    # Apply tone sandhi rules — returns (surface, underlying, half_third markers)
    surface_tones, underlying_tones, half_third_markers = _apply_sandhi_rules(expected_tones)

    # Auto-detect mode
    mode = "isolated" if len(expected_tones) == 1 else "connected"

    # Syllable segmentation — try energy-based, fall back to even split
    n_syllables = len(surface_tones)
    if HAS_AUDIO_INPUT and n_syllables > 1:
        segments = segment_syllable_nuclei(audio, n_syllables, sr)
    else:
        seg_len = len(f0) // n_syllables if n_syllables > 0 else len(f0)
        segments = []
        for i in range(n_syllables):
            start = i * seg_len
            end = start + seg_len if i < n_syllables - 1 else len(f0)
            segments.append((start, end))

    # Convert audio segments to F0 frame segments
    # F0 frames: hop_ms=10, so frame i corresponds to audio sample i * hop_samples
    hop_samples = int(sr * 10 / 1000)  # 10ms hop
    f0_segments = []
    for start_sample, end_sample in segments:
        f0_start = start_sample // hop_samples
        f0_end = end_sample // hop_samples
        f0_start = max(0, min(f0_start, len(f0)))
        f0_end = max(f0_start, min(f0_end, len(f0)))
        if f0_end <= f0_start:
            f0_end = min(f0_start + 1, len(f0))
        f0_segments.append((f0_start, f0_end))

    # Tone pairs that are acoustically close — award partial credit
    _CLOSE_TONE_PAIRS = {(2, 3), (3, 2), (1, 4), (4, 1)}

    # Leniency-scaled credit values
    close_pair_credit = (leniency or {}).get("close_pair_credit", 0.5)
    unclassified_credit = (leniency or {}).get("unclassified_credit", 0.3)

    syllable_scores = []
    for i, expected in enumerate(surface_tones):
        if i < len(f0_segments):
            f0_start, f0_end = f0_segments[i]
            segment = f0[f0_start:f0_end]
        else:
            segment = []

        # Neutral tone (0) — accept any pronunciation
        if expected == 0:
            detected, confidence = classify_tone(segment, calibration=calibration)
            syllable_scores.append({
                "expected": expected,
                "detected": detected,
                "correct": True,
                "confidence": round(confidence, 2),
                "credit": 1.0,
            })
            continue

        # Use V2 engine for rich classification
        result = classify_tone_v2(
            segment, calibration=calibration, mode=mode,
            expected_tone=expected,
            half_third_expected=half_third_markers[i] if i < len(half_third_markers) else False,
        )

        # Enrich features with voice quality data
        if result.features and vq_extras:
            enrich_with_voice_quality(result.features, vq_extras)

        detected = result.tone
        confidence = result.confidence
        correct = detected == expected

        # Ambiguity-aware credit
        if correct:
            credit = 1.0
        elif result.ambiguous and result.runner_up == expected:
            # Ambiguous detection where the runner-up matches expected
            credit = 0.7
        elif detected == 0:
            credit = unclassified_credit
        elif (expected, detected) in _CLOSE_TONE_PAIRS:
            credit = close_pair_credit
        elif confidence < 0.45:
            credit = 0.25
        else:
            credit = 0.0

        score_entry = {
            "expected": expected,
            "detected": detected,
            "correct": correct,
            "confidence": round(confidence, 2),
            "credit": round(credit, 2),
            # V2 additions (additive, non-breaking)
            "ambiguous": result.ambiguous,
            "runner_up": result.runner_up,
            "diagnostics": result.diagnostics,
            "family_matched": result.family_matched,
            "surface_expected": expected,
            "underlying_expected": underlying_tones[i] if i < len(underlying_tones) else expected,
        }
        # Voice quality extras (additive, non-breaking)
        if result.features:
            if result.features.hnr_mean is not None:
                score_entry["hnr"] = result.features.hnr_mean
            if result.features.f0_source:
                score_entry["f0_source"] = result.features.f0_source
        syllable_scores.append(score_entry)

    # Overall score — weighted by per-syllable credit
    total_credit = sum(s["credit"] for s in syllable_scores)
    overall = total_credit / len(syllable_scores) if syllable_scores else 0.0

    # Feedback
    feedback_parts = []
    for i, s in enumerate(syllable_scores):
        if not s["correct"] and s["detected"] > 0:
            feedback_parts.append(
                f"Syllable {i + 1}: expected tone {s['expected']}, "
                f"heard tone {s['detected']}"
            )

    if not feedback_parts:
        if overall == 1.0:
            feedback = "All tones correct."
        else:
            feedback = "Couldn't clearly detect some syllables. Try speaking more slowly."
    else:
        feedback = "; ".join(feedback_parts)

    result_dict = {
        "syllable_scores": syllable_scores,
        "overall_score": round(overall, 2),
        "feedback": feedback,
        "f0_source": "pyin" if HAS_LIBROSA else "yin",
    }

    # Add voice quality summary if available
    if vq_extras:
        result_dict["voice_quality"] = {
            "hnr_mean": vq_extras.get("hnr_mean", 0.0),
            "jitter": vq_extras.get("jitter", 0.0),
            "shimmer": vq_extras.get("shimmer", 0.0),
        }

    return result_dict


# ── Coaching feedback ──────────────────────────────

# Contour shape arrows for display
CONTOUR_ARROWS = {
    1: "\u2192",      # → flat
    2: "\u2197",      # ↗ rising
    3: "\u2198\u2197", # ↘↗ dipping
    4: "\u2198",      # ↘ falling
}

# Per-tone coaching tips when the wrong contour is detected
_TONE_COACHING = {
    1: "Tone 1 should be high and flat \u2192. Hold pitch steady at the top of your range.",
    2: "Tone 2 should rise like a question \u2197. Start mid and go up. Think: 'What?!'",
    3: "Tone 3 dips low then rises \u2198\u2197. Let your voice drop, then come back up.",
    4: "Tone 4 falls sharply \u2198. Start high and drop fast. Think: a firm 'No!'",
}

# What the detected shape suggests the speaker actually did
_DETECTED_DESCRIPTIONS = {
    1: "Your pitch stayed flat.",
    2: "Your pitch rose.",
    3: "Your pitch dipped.",
    4: "Your pitch fell.",
    0: "Couldn't detect a clear pitch contour.",
}


def generate_tone_coaching(syllable_scores: List[dict]) -> List[dict]:
    """Generate actionable coaching tips for each syllable with incorrect tone.

    Returns a list of coaching dicts (one per incorrect syllable):
      - syllable: 1-based syllable index
      - expected: expected tone number
      - detected: detected tone number
      - expected_arrow: contour arrow for expected tone
      - detected_arrow: contour arrow for detected tone
      - tip: actionable coaching string
      - error_kind: "category" (wrong tone) or "quality" (right tone, poor execution)

    Returns empty list when all tones are correct.
    """
    tips = []
    for i, s in enumerate(syllable_scores):
        if s.get("correct"):
            continue
        expected = s.get("expected", 0)
        detected = s.get("detected", 0)
        if expected < 1 or expected > 4:
            continue

        expected_arrow = CONTOUR_ARROWS.get(expected, "?")
        detected_arrow = CONTOUR_ARROWS.get(detected, "?")

        # V2 path: use diagnostic tips if available
        diagnostics = s.get("diagnostics", [])
        if diagnostics:
            diag_tips = [DIAGNOSTIC_TIPS[d] for d in diagnostics if d in DIAGNOSTIC_TIPS]
            if diag_tips:
                tip = " ".join(diag_tips)
                error_kind = "quality"
            else:
                # Fall back to static tips
                detected_desc = _DETECTED_DESCRIPTIONS.get(detected, "")
                tone_tip = _TONE_COACHING.get(expected, "")
                tip = f"{detected_desc} {tone_tip}".strip()
                error_kind = "category"
        else:
            # Legacy path: static tips
            detected_desc = _DETECTED_DESCRIPTIONS.get(detected, "")
            tone_tip = _TONE_COACHING.get(expected, "")
            tip = f"{detected_desc} {tone_tip}".strip()
            error_kind = "category"

        tips.append({
            "syllable": i + 1,
            "expected": expected,
            "detected": detected,
            "expected_arrow": expected_arrow,
            "detected_arrow": detected_arrow,
            "tip": tip,
            "error_kind": error_kind,
        })

    return tips


# ── Pinyin → tone number extraction ──────────────────────────────

_TONE_MAP = {
    "ā": 1, "á": 2, "ǎ": 3, "à": 4,
    "ē": 1, "é": 2, "ě": 3, "è": 4,
    "ī": 1, "í": 2, "ǐ": 3, "ì": 4,
    "ō": 1, "ó": 2, "ǒ": 3, "ò": 4,
    "ū": 1, "ú": 2, "ǔ": 3, "ù": 4,
    "ǖ": 1, "ǘ": 2, "ǚ": 3, "ǜ": 4,
}


def get_tone_accuracy(conn, days: int = 30, user_id: int = 1) -> dict:
    """Aggregate tone accuracy from audio_recording over the last N days.

    Returns dict with:
        - overall_accuracy: float 0.0-1.0 (% of syllable tones correct)
        - per_tone: {1: 0.92, 2: 0.71, ...} accuracy by expected tone
        - confused_pairs: [(expected, detected, count), ...] most common confusions
        - total_recordings: int sample size
    """
    rows = conn.execute("""
        SELECT tone_scores_json FROM audio_recording
        WHERE created_at >= datetime('now', ? || ' days')
          AND tone_scores_json IS NOT NULL
          AND user_id = ?
    """, (f"-{days}", user_id)).fetchall()

    result = {
        "overall_accuracy": 0.0,
        "per_tone": {},
        "confused_pairs": [],
        "total_recordings": len(rows),
    }

    if not rows:
        return result

    # Aggregate syllable-level scores
    tone_correct = {}   # {tone: correct_count}
    tone_total = {}     # {tone: total_count}
    confusions = {}     # {(expected, detected): count}
    total_correct = 0
    total_syllables = 0

    for row in rows:
        try:
            scores = json.loads(dict(row).get("tone_scores_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            logger.debug("Skipping unparseable tone_scores_json row")
            continue
        for s in scores:
            expected = s.get("expected", 0)
            detected = s.get("detected", 0)
            if expected < 1 or expected > 4:
                continue
            tone_total[expected] = tone_total.get(expected, 0) + 1
            total_syllables += 1
            if s.get("correct"):
                tone_correct[expected] = tone_correct.get(expected, 0) + 1
                total_correct += 1
            elif detected >= 1:
                pair = (expected, detected)
                confusions[pair] = confusions.get(pair, 0) + 1

    if total_syllables > 0:
        result["overall_accuracy"] = round(total_correct / total_syllables, 3)

    # Per-tone accuracy
    for tone in sorted(tone_total.keys()):
        correct = tone_correct.get(tone, 0)
        total = tone_total[tone]
        result["per_tone"][tone] = round(correct / total, 3) if total > 0 else 0.0

    # Top confused pairs sorted by count descending
    result["confused_pairs"] = sorted(
        [(exp, det, cnt) for (exp, det), cnt in confusions.items()],
        key=lambda x: x[2], reverse=True
    )[:10]

    return result


_PINYIN_VOWELS = set("aeiouüAEIOUÜ")

def pinyin_to_tones(pinyin: str) -> List[int]:
    """Extract tone numbers from pinyin string, including neutral tones (0).

    'nǐ hǎo' → [3, 3]
    'zhōngguó' → [1, 2]
    'xièxie' → [4, 0]  (neutral tone = 0)
    'bú kèqi' → [2, 4, 0]
    """
    tones = []
    syllable_tone = 0
    in_syllable = False
    had_vowel = False  # tracks if current syllable has seen a vowel

    for ch in pinyin:
        if ch in _TONE_MAP:
            # Toned vowel — if we already had a tone, push previous syllable
            if syllable_tone:
                tones.append(syllable_tone)
            syllable_tone = _TONE_MAP[ch]
            in_syllable = True
            had_vowel = True
        elif ch == " " or ch == "'":
            # Explicit syllable boundary
            if syllable_tone:
                tones.append(syllable_tone)
                syllable_tone = 0
            elif in_syllable:
                tones.append(0)  # neutral tone
            in_syllable = False
            had_vowel = False
        elif ch.isalpha():
            is_vowel = ch in _PINYIN_VOWELS
            # Consonant after a vowel in the same syllable = new syllable boundary
            # (except 'n', 'g', 'r' which can be finals: -n, -ng, -r)
            if had_vowel and not is_vowel and ch.lower() not in ('n', 'g', 'r'):
                # Flush current syllable
                if syllable_tone:
                    tones.append(syllable_tone)
                    syllable_tone = 0
                elif in_syllable:
                    tones.append(0)
                had_vowel = False
                in_syllable = True
            elif is_vowel:
                had_vowel = True
                in_syllable = True
            else:
                in_syllable = True

    # Last syllable
    if syllable_tone:
        tones.append(syllable_tone)
    elif in_syllable:
        tones.append(0)  # trailing neutral tone

    return tones
