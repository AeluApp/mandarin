"""Speaking drill implementation (voice tone grading + content verification)."""

from .base import DrillResult, format_hanzi
from .production import char_overlap_score


# ── Transcript-first scoring ──────────────────────────────

def compute_speaking_score(tone_score: float, content_score: float = None) -> float:
    """Compute combined speaking score using transcript-first weighting.

    When transcript is available, the browser SpeechRecognition result is the
    stronger signal: if it understood the speaker, tones were likely fine.

    Paths:
      - content >= 0.9: max(0.85, 0.3*tone + 0.7*content)  — recognised → tones OK
      - 0.4 <= content < 0.9: 0.4*tone + 0.6*content        — partial match
      - content < 0.4: 0.6*tone + 0.4*content                — recogniser confused
      - no transcript: tone_score only                        — CLI fallback
    """
    if content_score is None:
        return tone_score

    if content_score >= 0.9:
        return max(0.85, 0.3 * tone_score + 0.7 * content_score)
    elif content_score >= 0.4:
        return 0.4 * tone_score + 0.6 * content_score
    else:
        return 0.6 * tone_score + 0.4 * content_score


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
                       audio_enabled=False, english_level="full",
                       speaking_level: float = 1.0) -> DrillResult:
    """Record the learner speaking and grade tone accuracy + content."""
    from ..tone_grading import (is_recording_available, record_audio,
                               save_recording, grade_tones, pinyin_to_tones,
                               get_tone_leniency, get_speaker_calibration,
                               run_tone_calibration, save_speaker_calibration,
                               generate_tone_coaching, CONTOUR_ARROWS)
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

    # Load speaker calibration (or offer first-use prompt)
    calibration = get_speaker_calibration(conn)
    from ..tone_grading import _web_recording
    is_web = bool(getattr(_web_recording, "callback", None))

    if calibration is None and not is_web:
        offer = input_fn("  No voice calibration found. Calibrate now? "
                         "(say māmámǎmà) [Y/n/skip] ")
        if offer.strip().upper() not in ("N", "S", "SKIP"):
            show_fn("  Recording calibration phrase (3 seconds)...")
            cal_audio, _ = record_audio(duration=3.0)
            if cal_audio is not None:
                cal_result = run_tone_calibration(cal_audio)
                if cal_result:
                    save_speaker_calibration(conn, cal_result)
                    calibration = cal_result
                    show_fn(f"  Calibrated: {cal_result['f0_min']:.0f}"
                            f"-{cal_result['f0_max']:.0f} Hz "
                            f"(mean {cal_result['f0_mean']:.0f} Hz)")
                else:
                    show_fn("  Not enough audio to calibrate \u2014 no worries, we\u2019ll try again next time.")
            else:
                show_fn("  Couldn\u2019t capture that \u2014 calibration can happen anytime.")

    # Show what to say
    show_fn(format_hanzi(hanzi, prominent))
    if english_level != "full":
        show_fn(f"  {pinyin}")
    else:
        show_fn(f"  {pinyin} — {english}")

    # Play reference audio if available
    if audio_enabled:
        speak_and_wait(hanzi)
        show_fn("  Listen:")

    # Prompt to record
    tone_display = ', '.join('·' if t == 0 else str(t) for t in expected_tones)
    show_fn(f"  Say it aloud. Tones: {tone_display}")

    if not is_web:
        # CLI: prompt for Enter/Q/S before recording
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
    else:
        # Web: recording panel provides start/stop/skip controls
        audio, transcript = record_audio(duration=30.0)

    if audio is None:
        show_fn("  Couldn\u2019t capture audio \u2014 moving on." if not is_web else "")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="speaking", correct=False, skipped=True,
        )

    if not is_web:
        show_fn("  Analyzing...")

    # Grade tones with proficiency-scaled leniency and speaker calibration
    leniency = get_tone_leniency(speaking_level)
    result = grade_tones(audio, expected_tones, leniency=leniency,
                         calibration=calibration)
    tone_score = result["overall_score"]
    feedback = result["feedback"]

    # Grade content (if transcript available from SpeechRecognition)
    content_score = grade_speaking_content(transcript, hanzi) if transcript else None

    # Transcript-first scoring: weight browser recognition over F0 analysis
    score = compute_speaking_score(tone_score, content_score)

    correct = score >= leniency["pass_threshold"]

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

    # Generate coaching tips (informational — does not affect pass/fail)
    coaching_tips = generate_tone_coaching(result["syllable_scores"])

    # Build contour shapes for metadata (future web UI visualization)
    contour_shapes = []
    for s in result["syllable_scores"]:
        contour_shapes.append({
            "expected": s["expected"],
            "detected": s["detected"],
            "expected_arrow": CONTOUR_ARROWS.get(s["expected"], "?"),
            "detected_arrow": CONTOUR_ARROWS.get(s.get("detected", 0), "?"),
        })

    # Build feedback
    fb = f"  Tone score: {tone_score:.0%}"
    if content_score is not None:
        fb += f"  Content: {content_score:.0%}"
        fb += f"  Combined: {score:.0%}"
    if feedback:
        fb += f"\n  {feedback}"
    if transcript:
        fb += f"\n  Heard: {transcript}"

    # Append coaching tips
    if coaching_tips:
        fb += "\n"
        for tip in coaching_tips:
            fb += (f"\n  Syllable {tip['syllable']}: "
                   f"expected {tip['expected_arrow']} tone {tip['expected']}, "
                   f"heard {tip['detected_arrow']} tone {tip['detected']}")
            fb += f"\n    {tip['tip']}"

    return DrillResult(
        content_item_id=item_id, modality="speaking",
        drill_type="speaking", correct=correct,
        user_answer=f"score={score:.2f}",
        expected_answer=f"tones={''.join(str(t) for t in expected_tones)}",
        feedback=fb,
        score=score,
        error_type="tone" if not correct else None,
        error_cause="tone_grading" if not correct else None,
        metadata={"contour_shapes": contour_shapes,
                  "coaching_tips": coaching_tips},
    )


# ── Shadowing drill ──────────────────────────────

def run_shadowing_drill(item, conn, show_fn, input_fn, prominent=True,
                        audio_enabled=False, english_level="full",
                        speaking_level: float = 1.0) -> DrillResult:
    """Shadowing: listen to model audio, repeat immediately, grade tone + content + timing.

    Scoring:
      - 0.4 * tone_score + 0.4 * content_score + 0.2 * timing_score
      - timing_score = 1.0 if user duration within 30% of expected, else linearly decays
    """
    from ..tone_grading import (is_recording_available, record_audio,
                               save_recording, grade_tones, pinyin_to_tones,
                               get_tone_leniency, get_speaker_calibration,
                               generate_tone_coaching, CONTOUR_ARROWS)
    from ..audio import speak_and_wait, generate_audio_file
    import time as _time

    hanzi = item.get("hanzi", "")
    pinyin = item.get("pinyin", "")
    english = item.get("english", "")
    item_id = item.get("id", 0)

    if not is_recording_available():
        show_fn("  (Microphone not available — skipping shadowing drill)")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="shadowing", correct=False, skipped=True,
        )

    expected_tones = pinyin_to_tones(pinyin)
    if not expected_tones:
        show_fn("  (No tones detected in pinyin — skipping)")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="shadowing", correct=False, skipped=True,
        )

    calibration = get_speaker_calibration(conn)
    from ..tone_grading import _web_recording
    is_web = bool(getattr(_web_recording, "callback", None))

    # Show context
    show_fn(format_hanzi(hanzi, prominent))
    if english_level == "full":
        show_fn(f"  {pinyin} — {english}")
    else:
        show_fn(f"  {pinyin}")

    show_fn("  Shadowing: listen, then repeat immediately.")

    # Play model audio and measure playback duration
    model_start = _time.monotonic()
    if audio_enabled:
        speak_and_wait(hanzi)
    else:
        # Estimate model duration: ~0.4s per syllable at normal speed
        _time.sleep(0.3 * len(expected_tones))
    model_duration = _time.monotonic() - model_start

    show_fn("  Now repeat!")

    if not is_web:
        start = input_fn("  Press Enter to record (Q=quit, S=skip) ")
        if start.strip().upper() == "Q":
            return DrillResult(
                content_item_id=item_id, modality="speaking",
                drill_type="shadowing", correct=False,
                skipped=True, user_answer="Q",
            )
        if start.strip().upper() == "S":
            return DrillResult(
                content_item_id=item_id, modality="speaking",
                drill_type="shadowing", correct=False, skipped=True,
            )
        show_fn("  Recording (3 seconds)...")
        rec_start = _time.monotonic()
        audio, transcript = record_audio(duration=3.0)
        rec_duration = _time.monotonic() - rec_start
    else:
        rec_start = _time.monotonic()
        audio, transcript = record_audio(duration=30.0)
        rec_duration = _time.monotonic() - rec_start

    if audio is None:
        show_fn("  Couldn\u2019t capture audio \u2014 moving on." if not is_web else "")
        return DrillResult(
            content_item_id=item_id, modality="speaking",
            drill_type="shadowing", correct=False, skipped=True,
        )

    if not is_web:
        show_fn("  Analyzing...")

    # Grade tones
    leniency = get_tone_leniency(speaking_level)
    result = grade_tones(audio, expected_tones, leniency=leniency,
                         calibration=calibration)
    tone_score = result["overall_score"]

    # Grade content
    content_score = grade_speaking_content(transcript, hanzi) if transcript else tone_score * 0.8

    # Grade timing: within 30% of model duration is perfect
    if model_duration > 0.5:
        ratio = rec_duration / model_duration
        if 0.7 <= ratio <= 1.3:
            timing_score = 1.0
        elif ratio < 0.7:
            timing_score = max(0.0, ratio / 0.7)
        else:
            timing_score = max(0.0, 1.0 - (ratio - 1.3) / 1.0)
    else:
        timing_score = 0.8  # Can't measure model, give benefit of doubt

    # Combined score
    score = 0.4 * tone_score + 0.4 * content_score + 0.2 * timing_score
    correct = score >= leniency["pass_threshold"]

    # Save recording
    file_path = save_recording(audio, item_id, 0)

    import json as _json
    conn.execute("""
        INSERT INTO audio_recording (content_item_id, file_path,
                                     tone_scores_json, overall_score)
        VALUES (?, ?, ?, ?)
    """, (item_id, str(file_path),
          _json.dumps(result["syllable_scores"]), score))
    conn.commit()

    coaching_tips = generate_tone_coaching(result["syllable_scores"])

    contour_shapes = []
    for s in result["syllable_scores"]:
        contour_shapes.append({
            "expected": s["expected"],
            "detected": s["detected"],
            "expected_arrow": CONTOUR_ARROWS.get(s["expected"], "?"),
            "detected_arrow": CONTOUR_ARROWS.get(s.get("detected", 0), "?"),
        })

    fb = f"  Tone: {tone_score:.0%}  Content: {content_score:.0%}  Timing: {timing_score:.0%}"
    fb += f"\n  Combined: {score:.0%}"
    if result.get("feedback"):
        fb += f"\n  {result['feedback']}"
    if transcript:
        fb += f"\n  Heard: {transcript}"
    if coaching_tips:
        fb += "\n"
        for tip in coaching_tips:
            fb += (f"\n  Syllable {tip['syllable']}: "
                   f"expected {tip['expected_arrow']} tone {tip['expected']}, "
                   f"heard {tip['detected_arrow']} tone {tip['detected']}")
            fb += f"\n    {tip['tip']}"

    return DrillResult(
        content_item_id=item_id, modality="speaking",
        drill_type="shadowing", correct=correct,
        user_answer=f"score={score:.2f}",
        expected_answer=f"tones={''.join(str(t) for t in expected_tones)}",
        feedback=fb,
        score=score,
        error_type="tone" if not correct else None,
        error_cause="tone_grading" if not correct else None,
        metadata={"contour_shapes": contour_shapes,
                  "coaching_tips": coaching_tips,
                  "timing_score": timing_score},
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
