"""Conversation drills — dialogue scenarios with multi-turn NPC interaction."""

import json
import logging
import random
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

from .drills import DrillResult


def _show_best_option(options: list, chosen: dict, show_fn,
                      support_level: str = "full_support"):
    """Show the best-scoring option if it differs from what was chosen."""
    best = max(options, key=lambda o: o.get("score", 0))
    if best != chosen:
        best_parts = [best.get('text_zh', '')]
        if support_level != "hanzi_only" and best.get("text_pinyin"):
            best_parts.append(f"({best['text_pinyin']})")
        if support_level == "full_support" and best.get("text_en"):
            best_parts.append(f"— {best['text_en']}")
        show_fn(f"  Better: {' '.join(best_parts)}")


def run_dialogue_drill(scenario: dict, show_fn, input_fn,
                       support_level: str = "full_support",
                       conn=None) -> DrillResult:
    """Run a multi-turn dialogue scenario.

    scenario dict must have 'tree_json' (str or already parsed dict) and 'id'.
    support_level: "full_support" (hanzi+pinyin+english) or "hanzi_only".
    conn: optional DB connection for probe persistence.
    Returns DrillResult with score 0.0-1.0.
    """
    tree = scenario.get("tree_json", "{}")
    if isinstance(tree, str):
        try:
            tree = json.loads(tree)
        except (json.JSONDecodeError, TypeError):
            return DrillResult(
                content_item_id=0, modality="reading", drill_type="dialogue",
                correct=False, skipped=True, feedback="  (Scenario data corrupted, skipping)",
            )

    # The tree might be the full scenario dict or just the tree portion
    setup = tree.get("setup", "")
    setup_zh = tree.get("setup_zh", "")
    turns = tree.get("turns", [])
    cultural_note = tree.get("cultural_note", "")

    if not turns:
        return DrillResult(
            content_item_id=0, modality="reading", drill_type="dialogue",
            correct=False, skipped=True, feedback="  (No turns in scenario)",
        )

    # Show setup
    show_fn(f"\n  ── Dialogue: {scenario.get('title', '')} ──")
    if setup:
        show_fn(f"  {setup}")
    if setup_zh:
        show_fn(f"  {setup_zh}")

    if support_level == "hanzi_only":
        show_fn("  (Hanzi only for this scenario)")
    elif support_level == "pinyin_support":
        show_fn("  (English removed for this scenario)")
    if support_level != "full_support":
        show_fn("  [dim](quick check after each choice)[/dim]")
    show_fn("")

    turn_scores = []
    all_feedback = []

    for turn in turns:
        speaker = turn.get("speaker", "npc")

        if speaker == "npc":
            # NPC line — display based on support level
            text_zh = turn.get("text_zh", "")
            text_pinyin = turn.get("text_pinyin", "")
            text_en = turn.get("text_en", "")
            speaker_name = turn.get("speaker_name", "NPC")
            show_fn(f"  {speaker_name}: {text_zh}")
            if support_level != "hanzi_only" and text_pinyin:
                show_fn(f"       ({text_pinyin})")
            if support_level == "full_support" and text_en:
                show_fn(f"       \"{text_en}\"")
            show_fn("")

        elif speaker == "player":
            # Player choice
            prompt_en = turn.get("prompt_en", "What do you say?")
            options = turn.get("options", [])

            if not options:
                show_fn("  (no response options for this turn)")
                continue

            # Shuffle options to prevent position-gaming
            display_order = list(range(len(options)))
            random.shuffle(display_order)

            show_fn(f"  → {prompt_en}")
            if support_level == "hanzi_only":
                show_fn("  (P = show pinyin)")
            show_fn("")
            for display_num, orig_idx in enumerate(display_order, 1):
                opt = options[orig_idx]
                if support_level == "full_support":
                    # Max-two-of-three: hanzi + pinyin, or hanzi + english
                    pinyin = opt.get("text_pinyin", "")
                    en = opt.get("text_en", "")
                    parts = [opt.get('text_zh', '')]
                    if pinyin:
                        parts.append(f"({pinyin})")
                    elif en:
                        parts.append(f"— {en}")
                    show_fn(f"  {display_num}. {' '.join(parts)}")
                elif support_level == "pinyin_support":
                    # hanzi + pinyin only (no english)
                    pinyin = opt.get("text_pinyin", "")
                    parts = [opt.get('text_zh', '')]
                    if pinyin:
                        parts.append(f"({pinyin})")
                    show_fn(f"  {display_num}. {' '.join(parts)}")
                else:
                    # hanzi_only — just show the Chinese text
                    show_fn(f"  {display_num}. {opt.get('text_zh', '')}")

            # Input loop with invalid-input re-prompting (max 2 retries)
            # and pinyin assist toggle
            assist_used = False
            chosen = None
            for attempt in range(3):
                answer = input_fn("\n  > ").strip()

                if answer.upper() in ("Q", "B"):
                    return DrillResult(
                        content_item_id=0, modality="reading", drill_type="dialogue",
                        correct=False, skipped=True, user_answer=answer,
                    )

                # Pinyin assist: P key reveals pinyin under hanzi_only options
                if answer.upper() == "P" and support_level == "hanzi_only":
                    assist_used = True
                    show_fn("")
                    for display_num, orig_idx in enumerate(display_order, 1):
                        opt = options[orig_idx]
                        pinyin = opt.get("text_pinyin", "")
                        show_fn(f"  {display_num}. {opt.get('text_zh', '')}  ({pinyin})")
                    continue

                try:
                    choice_idx = int(answer) - 1
                    if 0 <= choice_idx < len(display_order):
                        chosen = options[display_order[choice_idx]]
                        break
                    else:
                        raise ValueError("out of range")
                except (ValueError, IndexError):
                    if attempt < 2:
                        show_fn(f"  (enter 1-{len(options)})")
                    else:
                        chosen = max(options, key=lambda o: o.get("score", 0))
                        show_fn(f"  (invalid — selecting best option)")

            if chosen is None:
                chosen = max(options, key=lambda o: o.get("score", 0))

            turn_score = chosen.get("score", 0.0)
            turn_scores.append(turn_score)

            register = chosen.get("register", "")
            feedback = chosen.get("feedback", "")

            # Post-answer reveal — max two of three (hanzi + pinyin + english)
            pinyin = chosen.get("text_pinyin", "")
            en = chosen.get("text_en", "")
            reveal_parts = [chosen.get('text_zh', '')]
            if pinyin:
                # Hanzi + pinyin → omit English (max-2 rule)
                reveal_parts.append(f"({pinyin})")
            elif en:
                # No pinyin available → show hanzi + English
                reveal_parts.append(f"— {en}")
            reveal_str = " ".join(reveal_parts)

            if turn_score >= 0.8:
                show_fn(f"  Your answer: {reveal_str}")
                show_fn(f"  ✓ {feedback}")
            elif turn_score >= 0.5:
                show_fn(f"  Your answer: {reveal_str}")
                show_fn(f"  ~ {feedback}")
                _show_best_option(options, chosen, show_fn, support_level)
            else:
                show_fn(f"  Your answer: {reveal_str}")
                show_fn(f"  → {feedback}")
                _show_best_option(options, chosen, show_fn, support_level)

            if register:
                show_fn(f"    (register: {register})")

            # Comprehension probe — verify understanding, not just option picking
            probe_correct = None
            if turn_score >= 0.5 and support_level != "full_support":
                probe_correct = _run_comprehension_probe(
                    chosen, options, show_fn, input_fn
                )

            # Track probe and assist in metadata
            if probe_correct is not None:
                all_feedback.append(("probe", probe_correct))
                # Persist probe result if DB available
                if conn is not None:
                    probe_type = "comprehension"
                    try:
                        record_probe_result(
                            conn,
                            content_item_id=0,
                            scenario_id=scenario.get("id"),
                            probe_type=probe_type,
                            correct=probe_correct,
                            user_answer="",
                            expected_answer="",
                        )
                        # Soft difficulty penalty on probe failure
                        if not probe_correct:
                            _apply_probe_penalty(conn, scenario.get("id"))
                    except sqlite3.Error as e:
                        logger.debug("probe persistence failed: %s", e)
            if assist_used:
                all_feedback.append(("assist", True))

            show_fn("")

    # Calculate overall score
    if turn_scores:
        avg_score = sum(turn_scores) / len(turn_scores)
    else:
        avg_score = 0.0

    # Cultural note at end
    if cultural_note:
        show_fn(f"  💡 {cultural_note}")
        show_fn("")

    # Summary
    correct = avg_score >= 0.7
    pct = int(avg_score * 100)
    marker = "\u2713" if correct else "\u2717"
    show_fn(f"  {marker} Dialogue score: {pct}%")

    # Build feedback metadata
    probe_results = [x[1] for x in all_feedback if x[0] == "probe"]
    assist_count = sum(1 for x in all_feedback if x[0] == "assist")
    feedback_parts = []
    if probe_results:
        sum(1 for p in probe_results if p) / len(probe_results)
        feedback_parts.append(f"probes: {sum(1 for p in probe_results if p)}/{len(probe_results)}")
    if assist_count:
        feedback_parts.append(f"assist used: {assist_count}x")
    feedback_str = "  " + " · ".join(feedback_parts) if feedback_parts else ""

    return DrillResult(
        content_item_id=0,
        modality="reading",
        drill_type="dialogue",
        correct=correct,
        user_answer=f"score={avg_score:.2f}",
        expected_answer="",
        score=avg_score,
        feedback=feedback_str,
    )


_STOP_WORDS = {"the", "a", "is", "to", "in", "on", "of", "it", "i", "you",
               "my", "your", "do", "was", "were", "be", "am", "an", "are"}


def _run_comprehension_probe(chosen: dict, options: list,
                              show_fn, input_fn) -> bool | None:
    """Run a follow-up meaning probe after a dialogue selection.

    Always runs a brief MC meaning probe: "Which character is in your answer?"
    Deterministic — no random skip. Predictable for the learner.
    Returns True if correct, False if wrong, None if insufficient data.
    """
    text_zh = chosen.get("text_zh", "")

    if not text_zh or len(text_zh) < 2:
        return None

    # Pick a CJK character from the chosen answer
    chosen_chars = [c for c in text_zh if '\u4e00' <= c <= '\u9fff']
    if not chosen_chars:
        return None

    target = random.choice(chosen_chars)

    # Build distractors from other options' characters
    other_chars = set()
    for opt in options:
        if opt is not chosen:
            for c in opt.get("text_zh", ""):
                if '\u4e00' <= c <= '\u9fff' and c not in chosen_chars:
                    other_chars.add(c)

    distractors = list(other_chars)
    if len(distractors) < 2:
        return None  # Not enough distractors

    random.shuffle(distractors)
    distractors = distractors[:2]

    # Build 3-option MC
    mc_options = [target] + distractors
    random.shuffle(mc_options)
    correct_idx = mc_options.index(target) + 1

    show_fn(f"\n  Quick check: which character is in your answer?")
    for i, ch in enumerate(mc_options, 1):
        show_fn(f"  {i}. {ch}")

    answer = input_fn("  > ").strip()
    try:
        if int(answer) == correct_idx:
            show_fn(f"  ✓ {target} is in: {text_zh}")
            return True
        else:
            show_fn(f"  → {target} is in: {text_zh}")
            return False
    except (ValueError, IndexError):
        show_fn(f"  → {target} is in: {text_zh}")
        return False


def record_probe_result(conn, content_item_id: int, scenario_id: int,
                        probe_type: str, correct: bool,
                        user_answer: str = "", expected_answer: str = ""):
    """Record a comprehension probe result to the probe_log table."""
    conn.execute("""
        INSERT INTO probe_log
            (content_item_id, scenario_id, probe_type, correct,
             user_answer, expected_answer)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (content_item_id, scenario_id, probe_type, 1 if correct else 0,
          user_answer, expected_answer))
    conn.commit()


def _apply_probe_penalty(conn, scenario_id: int):
    """Apply soft difficulty penalty (+0.02 to reading modality) on probe failure.

    Targets items from the scenario's HSK level.
    """
    if not scenario_id:
        return
    row = conn.execute(
        "SELECT hsk_level FROM dialogue_scenario WHERE id = ?",
        (scenario_id,)
    ).fetchone()
    if not row:
        return
    hsk_level = row["hsk_level"]
    conn.execute("""
        UPDATE progress SET difficulty = MIN(0.95, difficulty + 0.02)
        WHERE modality = 'reading'
          AND content_item_id IN (
              SELECT id FROM content_item WHERE hsk_level = ?
          )
          AND total_attempts > 0
    """, (hsk_level,))
    conn.commit()
