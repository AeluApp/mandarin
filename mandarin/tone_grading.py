"""Tone grading — record voice and grade Mandarin tone accuracy.

Uses sounddevice for recording and numpy autocorrelation for F0 extraction.
No external audio analysis libraries required.

Web mode: set_web_recording_callback() enables browser-based recording via
getUserMedia, bridged through WebSocket.
"""

import json
import logging
import threading
import wave
from datetime import datetime
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

from . import db


SAMPLE_RATE = 16000  # 16kHz mono — sufficient for voice
MAX_RECORD_SECONDS = 5
RECORDINGS_DIR = Path(__file__).parent.parent / "data" / "recordings"

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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_item{content_item_id}.wav"
    path = RECORDINGS_DIR / filename

    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())

    return path


# ── Pitch extraction (autocorrelation) ──────────────────────────────

def extract_f0(audio: "np.ndarray", sr: int = SAMPLE_RATE,
               frame_ms: int = 30, hop_ms: int = 10,
               fmin: float = 75.0, fmax: float = 500.0) -> List[float]:
    """Extract fundamental frequency contour using autocorrelation.

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
        if peak_val < 0.5:
            f0_values.append(0.0)
        else:
            lag = search_start + peak_idx
            # Octave correction: check if a strong peak exists at lag/2
            # (indicating detected lag is a subharmonic, not the fundamental).
            # If corr[lag/2] > 0.7 * corr[lag], prefer the higher frequency.
            half_lag = lag // 2
            if half_lag >= min_lag and half_lag < len(corr):
                if corr[half_lag] > 0.7 * corr[lag]:
                    lag = half_lag
            f0_values.append(sr / lag if lag > 0 else 0.0)

    return f0_values


# ── Tone classification ──────────────────────────────

# Mandarin tones as pitch contour shapes
# Each tone maps to a characteristic F0 trajectory pattern
TONE_PATTERNS = {
    1: "flat",      # High flat
    2: "rising",    # Mid rising
    3: "dipping",   # Low dipping (fall-rise)
    4: "falling",   # High falling
}


def classify_tone(f0_contour: List[float]) -> Tuple[int, float]:
    """Classify a single-syllable F0 contour into Mandarin tone 1-4.

    Returns (tone_number, confidence) where confidence is 0.0-1.0.
    """
    # Filter out unvoiced frames
    voiced = [f for f in f0_contour if f > 0]
    if len(voiced) < 3:
        return (0, 0.0)  # Not enough data

    # Normalize to 0-1 range
    min_f = min(voiced)
    max_f = max(voiced)
    spread = max_f - min_f
    if spread < 5:  # Nearly flat in Hz
        return (1, 0.7)  # Tone 1 (flat)

    normed = [(f - min_f) / spread for f in voiced]

    # Divide into thirds for trajectory analysis
    n = len(normed)
    third = max(n // 3, 1)
    first = sum(normed[:third]) / third
    middle = sum(normed[third:2 * third]) / max(len(normed[third:2 * third]), 1)
    last = sum(normed[2 * third:]) / max(len(normed[2 * third:]), 1)

    # Score each tone
    scores = {}

    # Tone 1: flat high — all thirds close together
    flatness = 1.0 - (max(first, middle, last) - min(first, middle, last))
    scores[1] = flatness * 0.8 + (first + middle + last) / 3 * 0.2

    # Tone 2: rising — last > first, middle in between
    if last > first:
        rise = (last - first)
        scores[2] = rise * 0.7 + (0.3 if middle < last else 0.0)
    else:
        scores[2] = 0.0

    # Tone 3: dipping — middle < first and middle < last
    if middle < first and middle < last:
        dip = ((first - middle) + (last - middle)) / 2
        scores[3] = dip * 0.8
    else:
        scores[3] = 0.0

    # Tone 4: falling — first > last, steep descent
    if first > last:
        fall = (first - last)
        scores[4] = fall * 0.7 + (0.3 if middle > last else 0.0)
    else:
        scores[4] = 0.0

    # Pick best
    best_tone = max(scores, key=scores.get)
    best_score = scores[best_tone]

    # Normalize confidence
    total = sum(scores.values())
    confidence = best_score / total if total > 0 else 0.0

    return (best_tone, min(confidence, 1.0))


def _apply_sandhi_rules(tones: List[int]) -> List[int]:
    """Apply Mandarin tone sandhi rules to expected tones.

    Rules applied:
    1. Third-tone sandhi: tone 3 before tone 3 becomes tone 2
       e.g., 你好 nǐ hǎo → ní hǎo (expected [3,3] → [2,3])
    2. Sequential third tones: in chains of 3+, all but last become tone 2
       e.g., 我也好 wǒ yě hǎo → wó yé hǎo

    Note: 一 and 不 sandhi are handled at the pinyin level (pinyin_to_tones
    already extracts the surface tone from tone-marked pinyin).
    """
    if len(tones) < 2:
        return tones

    result = list(tones)
    # Third-tone sandhi: in a consecutive run of tone-3 syllables,
    # all but the last become tone 2. E.g., 3-3-3 → 2-2-3
    i = 0
    while i < len(result):
        if result[i] == 3:
            # Find the end of this consecutive tone-3 run
            run_end = i + 1
            while run_end < len(result) and result[run_end] == 3:
                run_end += 1
            # Change all but the last in the run to tone 2
            for j in range(i, run_end - 1):
                result[j] = 2
            i = run_end
        else:
            i += 1

    return result


def grade_tones(audio: "np.ndarray", expected_tones: List[int],
                sr: int = SAMPLE_RATE) -> dict:
    """Grade pronunciation against expected tone sequence.

    Args:
        audio: recorded audio array
        expected_tones: list of expected tone numbers (1-4)

    Returns dict with:
        - syllable_scores: list of {expected, detected, correct, confidence}
        - overall_score: 0.0-1.0
        - feedback: human-readable feedback string
    """
    f0 = extract_f0(audio, sr)

    if not f0 or not expected_tones:
        return {
            "syllable_scores": [],
            "overall_score": 0.0,
            "feedback": "Could not detect speech. Try speaking closer to the mic.",
        }

    # Apply tone sandhi rules so correct pronunciation isn't penalized
    expected_tones = _apply_sandhi_rules(expected_tones)

    # Split F0 contour into syllable segments (evenly divided)
    n_syllables = len(expected_tones)
    segment_len = len(f0) // n_syllables if n_syllables > 0 else len(f0)

    syllable_scores = []
    for i, expected in enumerate(expected_tones):
        start = i * segment_len
        end = start + segment_len if i < n_syllables - 1 else len(f0)
        segment = f0[start:end]

        detected, confidence = classify_tone(segment)
        correct = detected == expected

        syllable_scores.append({
            "expected": expected,
            "detected": detected,
            "correct": correct,
            "confidence": round(confidence, 2),
        })

    # Overall score
    correct_count = sum(1 for s in syllable_scores if s["correct"])
    overall = correct_count / len(syllable_scores) if syllable_scores else 0.0

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

    return {
        "syllable_scores": syllable_scores,
        "overall_score": round(overall, 2),
        "feedback": feedback,
    }


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
            scores = json.loads(row["tone_scores_json"])
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


def pinyin_to_tones(pinyin: str) -> List[int]:
    """Extract tone numbers from pinyin string.

    'nǐ hǎo' → [3, 3]
    'zhōngguó' → [1, 2]
    'xièxie' → [4]  (neutral tones omitted)
    """
    tones = []
    syllable_tone = 0
    for ch in pinyin:
        if ch in _TONE_MAP:
            # If we already found a tone for this syllable, push it first
            if syllable_tone:
                tones.append(syllable_tone)
            syllable_tone = _TONE_MAP[ch]
        elif ch == " " or ch == "'":
            if syllable_tone:
                tones.append(syllable_tone)
                syllable_tone = 0

    # Last syllable
    if syllable_tone:
        tones.append(syllable_tone)

    return tones
