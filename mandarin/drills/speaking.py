"""Speaking drill implementation (voice tone grading + content verification)."""

from .base import DrillResult, format_hanzi
from .production import char_overlap_score


# ── Content accuracy grading ──────────────────────────────

def grade_speaking_content(transcript: str, expected_hanzi: str) -> float:
    """Grade whether the spoken transcript matches expected content.

    Uses char_overlap_score (Jaccard similarity on character sets).
    Returns 0.0-1.0 content accuracy score.
    """
    if not transcript or not expected_hanzi:
        return 0.0
    # Normalize: strip whitespace and punctuation
    import re
    clean_transcript = re.sub(r'[\s\u3000-\u303f\uff00-\uffef.,!?;:]+', '', transcript)
    clean_expected = re.sub(r'[\s\u3000-\u303f\uff00-\uffef.,!?;:]+', '', expected_hanzi)
    if not clean_transcript or not clean_expected:
        return 0.0
    # Exact match
    if clean_transcript == clean_expected:
        return 1.0
    return char_overlap_score(clean_expected, clean_transcript)


# ── Speaking drill (voice tone grading + content) ──────────────────────────────

def run_speaking_drill(item, conn, show_fn, input_fn, prominent=True,
                       audio_enabled=False) -> DrillResult:
    """Record the learner speaking and grade tone accuracy + content."""
    from ..tone_grading import (is_recording_available, record_audio,
                               save_recording, grade_tones, pinyin_to_tones)
    from ..audio import speak_and_wait

    hanzi = item.get("hanzi", "")
    pinyin = item.get("pinyin", "")
    english = item.get("english", "")
    item_id = item.get("id", 0)

    if not is_recording_available():
        show_fn("  (Microphone not available — skipping speaking drill)")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="speaking", correct=False, skipped=True,
        )

    expected_tones = pinyin_to_tones(pinyin)
    if not expected_tones:
        show_fn("  (No tones detected in pinyin — skipping)")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="speaking", correct=False, skipped=True,
        )

    # Show what to say
    show_fn(format_hanzi(hanzi, prominent))
    show_fn(f"  {pinyin} — {english}")

    # Play reference audio if available
    if audio_enabled:
        show_fn("  Listen:")
        speak_and_wait(hanzi)

    # Prompt to record
    show_fn(f"  Say it aloud. Tones: {' '.join(str(t) for t in expected_tones)}")
    start = input_fn("  Press Enter to start recording (Q=quit, S=skip) ")

    if start.strip().upper() == "Q":
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="speaking", correct=False,
            skipped=True, user_answer="Q",
        )
    if start.strip().upper() == "S":
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="speaking", correct=False, skipped=True,
        )

    show_fn("  Recording (3 seconds)...")
    audio, transcript = record_audio(duration=3.0)

    if audio is None:
        show_fn("  Recording failed.")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="speaking", correct=False, skipped=True,
        )

    show_fn("  Analyzing...")

    # Grade tones
    result = grade_tones(audio, expected_tones)
    tone_score = result["overall_score"]
    feedback = result["feedback"]

    # Grade content (if transcript available from SpeechRecognition)
    content_score = grade_speaking_content(transcript, hanzi) if transcript else None

    # Combined score: 60% tone + 40% content when transcript available
    if content_score is not None:
        score = 0.6 * tone_score + 0.4 * content_score
    else:
        score = tone_score

    correct = score >= 0.5

    # Save recording
    session_id = None  # Will be set by runner if available
    file_path = save_recording(audio, item_id, session_id or 0)

    # Store in DB
    import json as _json
    conn.execute("""
        INSERT INTO audio_recording (content_item_id, file_path,
                                     tone_scores_json, overall_score)
        VALUES (?, ?, ?, ?)
    """, (item_id, str(file_path),
          _json.dumps(result["syllable_scores"]), score))
    conn.commit()

    # Build feedback
    fb = f"  Tone score: {tone_score:.0%}"
    if content_score is not None:
        fb += f"  Content: {content_score:.0%}"
        fb += f"  Combined: {score:.0%}"
    if feedback:
        fb += f"\n  {feedback}"
    if transcript:
        fb += f"\n  Heard: {transcript}"

    return DrillResult(
        content_item_id=item_id, modality="speaking",
        drill_type="speaking", correct=correct,
        user_answer=f"score={score:.2f}",
        expected_answer=f"tones={''.join(str(t) for t in expected_tones)}",
        feedback=fb,
        score=score,
        error_type="tone" if not correct else None,
    )


# ── Audio replay wrapper ──────────────────────────────

def _make_replay_input(input_fn, show_fn, item: dict, audio_enabled: bool):
    """Wrap input_fn to handle R key for audio replay.

    When audio_enabled and user types R, replays the hanzi audio and re-prompts.
    Returns a wrapped input function.

    Captures the hanzi string at closure time (not the dict reference)
    to prevent stale data if the dict were ever mutated.
    """
    if not audio_enabled:
        return input_fn

    # Capture value at closure time — not the dict reference
    hanzi = item.get("hanzi", "")

    def replay_input(prompt):
        while True:
            answer = input_fn(prompt)
            if answer.strip().upper() == "R":
                from ..audio import cancel_audio, speak_and_wait
                cancel_audio()
                show_fn("  (replaying...)")
                speak_and_wait(hanzi)
                continue
            return answer
    return replay_input
