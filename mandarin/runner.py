"""Session runner — executes a SessionPlan through the CLI."""

import logging
import random
import sqlite3
import time
from dataclasses import dataclass, field, replace
from datetime import date
from statistics import mean
from typing import Callable, List, Optional

from . import db, display

logger = logging.getLogger(__name__)
from .scheduler import SessionPlan, DrillItem
from .drills import run_drill, DrillResult, DRILL_REGISTRY
from .conversation import run_dialogue_drill
from .scenario_loader import get_scenario_by_id, record_scenario_attempt
from .media import get_media_entry, run_media_comprehension
from .milestones import get_growth_summary

_STAGE_LABELS = display.STAGE_LABELS

_DRILL_DESCRIPTIONS = {
    "mc": "What does this mean?",
    "mc_reading": "What does this mean?",
    "reverse_mc": "Which character matches?",
    "mc_listening": "Listen and identify",
    "ime_type": "Write the pinyin",
    "ime": "Write the pinyin",
    "tone": "Identify the tones",
    "pinyin_recall": "What's the pronunciation?",
    "english_to_pinyin": "What's the pronunciation?",
    "pinyin_reading": "Read and write the pinyin",
    "hanzi_to_pinyin": "Read and write the pinyin",
    "pinyin_to_hanzi": "Write the character from pinyin",
    "listening_gist": "Listen for the meaning",
    "listening_detail": "Listen and answer",
    "listening_tone": "Identify the tone you hear",
    "listening_dictation": "Write what you hear",
    "intuition": "Which sounds natural?",
    "dialogue": "Choose your response",
    "register_choice": "Pick the right register",
    "pragmatic": "What's the appropriate response?",
    "slang_exposure": "Colloquial usage",
    "speaking": "Speak the phrase aloud",
    "transfer": "Apply in a new context",
    "measure_word": "Which measure word?",
    "word_order": "Arrange the words",
    "sentence_build": "Build the sentence",
    "particle_disc": "Which particle?",
    "homophone": "Distinguish similar sounds",
    "translation": "Write the translation",
    "media_comprehension": "Real-world media",
    "cloze_context": "Fill in the blank",
    "synonym_disc": "Which synonym fits?",
    "listening_passage": "Listen to the passage",
    "dictation_sentence": "Write the full sentence",
}


@dataclass
class SessionState:
    """Mutable state for a running session."""
    session_id: int
    plan: SessionPlan
    results: List[DrillResult] = field(default_factory=list)
    current_index: int = 0
    boredom_flags: int = 0
    early_exit: bool = False

    @property
    def items_completed(self) -> int:
        return len(self.results)

    @property
    def items_correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def is_done(self) -> bool:
        return self.current_index >= len(self.plan.drills) or self.early_exit

    @property
    def modality_counts(self) -> dict:
        counts = {}
        for r in self.results:
            counts[r.modality] = counts.get(r.modality, 0) + 1
        return counts


def run_session(conn, plan: SessionPlan,
                show_fn: Callable, input_fn: Callable,
                user_id: int = 1) -> SessionState:
    """Run a complete session from a plan.

    show_fn(text): display text to user
    input_fn(prompt) -> str: get user input

    Returns the final SessionState with all results.
    """
    # Get profile early — needed for plan_snapshot and hanzi prominence
    profile = db.get_profile(conn, user_id=user_id)

    # Start session in DB
    session_id = db.start_session(
        conn,
        session_type=plan.session_type,
        items_planned=len(plan.drills),
        user_id=user_id,
        plan_snapshot={
            "type": plan.session_type,
            "n_drills": len(plan.drills),
            "micro_plan": plan.micro_plan,
            "seed": f"{date.today().isoformat()}:{profile.get('total_sessions', 0)}",
            "drills": [
                {
                    "item_id": d.content_item_id,
                    "hanzi": d.hanzi,
                    "type": d.drill_type,
                    "modality": d.modality,
                    "reason": "new" if d.is_new else
                              "error_focus" if d.is_error_focus else
                              "confidence_win" if d.is_confidence_win else
                              d.metadata.get("reason", "scheduled"),
                }
                for d in plan.drills
            ],
        }
    )

    state = SessionState(session_id=session_id, plan=plan)

    # Cross-session interleaving: store mapping groups used
    if hasattr(plan, '_mapping_groups_used') and plan._mapping_groups_used:
        try:
            conn.execute(
                "UPDATE session_log SET mapping_groups_used = ? WHERE id = ?",
                (plan._mapping_groups_used, session_id)
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.debug("could not store mapping groups: %s", e)

    # Within-session re-insertion counter (Landauer & Bjork expanding retrieval)
    retry_insertions = 0
    MAX_RETRY_INSERTIONS = 3

    # Determine hanzi prominence based on average profile level
    level_keys = ["level_reading", "level_listening", "level_speaking", "level_ime"]
    avg_level = mean(profile.get(k, 1.0) or 1.0 for k in level_keys)
    prominent = avg_level < 6.0

    # Audio: default ON on macOS; profile setting overrides only if explicitly 0
    from .audio import is_audio_available
    audio_enabled = profile.get("audio_enabled", 1) != 0 and is_audio_available()

    # ── Session opening: the mark, then context ──
    show_fn("\n  [dim]漫[/dim]")
    total_sessions = profile.get("total_sessions", 0) or 0
    if plan.gap_message:
        show_fn(f"\n  {plan.gap_message}")
        # Retention-aware gap context
        try:
            from .retention import compute_retention_stats
            ret = compute_retention_stats(conn, user_id=user_id)
            if ret["total_items"] >= 5 and ret["retention_pct"] < 85:
                show_fn(f"  Memory estimate: {ret['retention_pct']:.0f}% of items above recall threshold.")
        except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
            logger.warning("retention stats unavailable at session open: %s", e)
            show_fn(display.hint("memory estimate unavailable"))
        show_fn("")
    elif total_sessions == 0:
        show_fn("\n  Session 1.\n")
    elif total_sessions < 5:
        show_fn(f"\n  Session {total_sessions + 1}. Continuing.\n")

    # Show micro-plan
    show_fn(f"  {plan.micro_plan}")
    show_fn(f"  ({len(plan.drills)} items, ~{plan.estimated_seconds // 60} min)\n")

    # Track pre-session milestones for comparison at end
    pre_milestones = {m["key"] for m in get_growth_summary(conn).get("unlocked", [])}

    # Wait for user to begin
    start_input = input_fn("  Press Enter to begin (M=mini, Q=quit) ").strip().upper()

    if start_input == "Q":
        state.early_exit = True
        _finalize(conn, state, show_fn, input_fn=input_fn, pre_milestones=pre_milestones, user_id=user_id)
        return state

    if start_input == "M":
        # Switch to minimal session
        from .scheduler import plan_minimal_session
        mini_plan = plan_minimal_session(conn, user_id=user_id)
        state.plan = mini_plan
        plan = mini_plan
        show_fn(f"\n  Switching to mini: {plan.micro_plan}\n")

    # Run drills
    session_start = time.monotonic()
    mid_shown = False
    last_modality = None
    streak_run = 0  # consecutive correct for momentum signal

    # Phase 2: Frustration detection
    consecutive_wrong = 0
    confidence_builders_used = 0
    MAX_CONFIDENCE_BUILDERS = 2

    # Phase 10: Within-session difficulty adaptation
    scaffold_adjusted = False
    seen_drill_types = set()  # Session-scoped for first-encounter hints
    i = 0
    while i < len(plan.drills):
        drill = plan.drills[i]
        state.current_index = i

        # Mid-session pulse — brief, non-intrusive
        if not mid_shown and len(plan.drills) >= 6 and i == len(plan.drills) // 2:
            mid_shown = True
            completed_so_far = [r for r in state.results if not r.skipped]
            if completed_so_far:
                mid_correct = sum(1 for r in completed_so_far if r.correct)
                mid_pct = mid_correct / len(completed_so_far)
                if mid_pct >= 0.8:
                    show_fn("\n  ── Halfway through. ──")
                elif mid_pct < 0.5:
                    show_fn("\n  ── Difficult stretch. ──")

        # Modality transition — subtle visual break on mode switch
        if last_modality and drill.modality != last_modality:
            show_fn(display.modality_break())
        last_modality = drill.modality

        # Progress indicator with time remaining
        remaining = len(plan.drills) - i
        if i > 0:
            avg_per = (time.monotonic() - session_start) / i
            est_left = int(remaining * avg_per)
        else:
            est_left = remaining * 35
        if est_left >= 90:
            time_hint = f" ~{est_left // 60}min"
        elif est_left >= 30:
            time_hint = " <1min"
        else:
            time_hint = ""
        show_fn(f"\n  [{i + 1}/{len(plan.drills)}{time_hint}]  ", end="")
        _show_drill_label(drill, show_fn, seen_drill_types)

        # Handle dialogue drills specially (they use scenarios, not content items)
        if drill.drill_type == "dialogue":
            scenario_id = drill.metadata.get("scenario_id")
            if not scenario_id:
                show_fn("  (scenario unavailable, skipping)")
                i += 1
                continue
            scenario = get_scenario_by_id(conn, scenario_id)
            if not scenario:
                show_fn("  (scenario not found, skipping)")
                i += 1
                continue
            support_level = drill.metadata.get("support_level", "full_support")
            result = run_dialogue_drill(scenario, show_fn, input_fn, support_level=support_level, conn=conn)
            if result.score is not None:
                record_scenario_attempt(conn, scenario_id, result.score)

            if result.skipped and result.user_answer.upper() == "Q":
                state.early_exit = True
                state.results.append(result)
                break
            if result.skipped and result.user_answer.upper() == "B":
                state.boredom_flags += 1
                show_fn("  (Noted)")
                i += 1
                continue

            state.results.append(result)
            if result.correct:
                show_fn("  ✓")
            i += 1
            continue

        # Handle media comprehension drills
        if drill.drill_type == "media_comprehension":
            mid = drill.metadata.get("media_id")
            if not mid:
                show_fn("  (media entry unavailable, skipping)")
                i += 1
                continue
            entry = get_media_entry(mid)
            if not entry:
                show_fn("  (media entry not found, skipping)")
                i += 1
                continue
            result = run_media_comprehension(entry, show_fn, input_fn, conn=conn)

            if result.skipped and result.user_answer.upper() == "Q":
                state.early_exit = True
                state.results.append(result)
                break
            if result.skipped and result.user_answer.upper() == "B":
                state.boredom_flags += 1
                show_fn("  (Noted)")
                i += 1
                continue

            state.results.append(result)
            if result.correct:
                show_fn("  ✓")
            i += 1
            continue

        # Get the content item from DB for full data
        item = conn.execute(
            "SELECT * FROM content_item WHERE id = ?",
            (drill.content_item_id,)
        ).fetchone()

        if not item:
            show_fn("  (item unavailable, skipping)")
            i += 1
            continue

        item = dict(item)

        # Run the drill with timing and gradient scaffold
        drill_start = time.monotonic()
        scaffold_level = drill.metadata.get("scaffold_level", "none")
        show_pinyin = scaffold_level == "full_pinyin"

        # Phase 10: Within-session difficulty adaptation
        if not scaffold_adjusted and state.items_completed >= 4:
            non_skipped = [r for r in state.results if not r.skipped]
            if non_skipped:
                running_acc = sum(1 for r in non_skipped if r.correct) / len(non_skipped)
                from .config import SCAFFOLD_ORDER
                if running_acc < 0.5 and len(non_skipped) >= 4:
                    # Upgrade scaffold: more support
                    idx = SCAFFOLD_ORDER.index(scaffold_level) if scaffold_level in SCAFFOLD_ORDER else 0
                    if idx < len(SCAFFOLD_ORDER) - 1:
                        scaffold_level = SCAFFOLD_ORDER[idx + 1]
                        show_pinyin = scaffold_level == "full_pinyin"
                    scaffold_adjusted = True
                    logger.debug("scaffold upgraded mid-session, accuracy=%.0f%%", running_acc * 100)
                elif running_acc > 0.9 and len(non_skipped) >= 6:
                    # Downgrade scaffold: desirable difficulty
                    idx = SCAFFOLD_ORDER.index(scaffold_level) if scaffold_level in SCAFFOLD_ORDER else 0
                    if idx > 0:
                        scaffold_level = SCAFFOLD_ORDER[idx - 1]
                        show_pinyin = scaffold_level == "full_pinyin"
                    scaffold_adjusted = True
                    logger.debug("scaffold downgraded mid-session, accuracy=%.0f%%", running_acc * 100)

        # Mid-session struggle detection: pivot to confidence wins if accuracy < 40% after 5+ items
        if not getattr(state, '_struggle_pivoted', False) and state.items_completed >= 5:
            non_skipped = [r for r in state.results if not r.skipped]
            if non_skipped and len(non_skipped) >= 5:
                running_acc = sum(1 for r in non_skipped if r.correct) / len(non_skipped)
                if running_acc < 0.4:
                    state._struggle_pivoted = True
                    show_fn("\n  ── Shifting to review. ──")
                    # Replace remaining drills with confidence wins (high-streak items)
                    remaining_count = len(plan.drills) - i
                    if remaining_count > 3:
                        # Keep only 3 more drills, all confidence wins
                        conf_drills = [d for d in plan.drills[i:] if d.is_confidence_win]
                        if len(conf_drills) < 3:
                            # Also include items the learner got right this session
                            correct_ids = {r.content_item_id for r in state.results if r.correct}
                            for d in plan.drills[i:]:
                                if d.content_item_id in correct_ids and d not in conf_drills:
                                    conf_drills.append(d)
                                    if len(conf_drills) >= 3:
                                        break
                        if conf_drills:
                            plan.drills[i:] = conf_drills[:3]
                    logger.debug("struggle pivot at item %d, accuracy=%.0f%%", i, running_acc * 100)

        result = run_drill(drill.drill_type, item, conn, show_fn, input_fn,
                          prominent=prominent, audio_enabled=audio_enabled,
                          show_pinyin=show_pinyin, scaffold_level=scaffold_level)
        drill_ms = int((time.monotonic() - drill_start) * 1000)

        # Check for special commands
        if result.skipped and result.user_answer.upper() == "Q":
            state.early_exit = True
            state.results.append(result)
            break

        if result.skipped and result.user_answer.upper() == "B":
            state.boredom_flags += 1
            show_fn("  (Noted)")
            i += 1
            continue

        # Record to DB — fix modality for listening drills without audio
        record_modality = drill.modality
        if record_modality == "listening" and not audio_enabled:
            record_modality = "reading"  # text-only listening drills are really reading

        db.record_attempt(
            conn,
            content_item_id=drill.content_item_id,
            modality=record_modality,
            correct=result.correct,
            session_id=session_id,
            error_type=result.error_type,
            user_answer=result.user_answer,
            expected_answer=result.expected_answer,
            drill_type=drill.drill_type,
            confidence=result.confidence,
            response_ms=drill_ms,
            user_id=user_id,
        )

        state.results.append(result)

        # Incremental save — persist progress after each drill
        db.update_session_progress(conn, session_id,
                                   state.items_completed, state.items_correct)

        # Within-session re-insertion: re-present failed items after a short delay
        # (Landauer & Bjork 1978 expanding retrieval practice)
        if (not result.correct and not result.skipped
                and result.confidence == "full"
                and not drill.metadata.get("retry")
                and retry_insertions < MAX_RETRY_INSERTIONS):
            retry_drill = replace(drill, metadata={**drill.metadata, "retry": True})
            insert_pos = min(i + 4, len(plan.drills))
            plan.drills.insert(insert_pos, retry_drill)
            retry_insertions += 1
            logger.debug("re-inserted %s at position %d (%d/%d retries)",
                         drill.hanzi, insert_pos, retry_insertions, MAX_RETRY_INSERTIONS)

        # Phase 2: Frustration detection
        if not result.skipped:
            if not result.correct and result.confidence == "full":
                consecutive_wrong += 1
            else:
                consecutive_wrong = 0

            # Inject confidence builder after 3 consecutive wrong
            if (consecutive_wrong >= 3
                    and confidence_builders_used < MAX_CONFIDENCE_BUILDERS):
                # Find highest-streak correct item from this session
                correct_results = [
                    (r, plan.drills[j] if j < len(plan.drills) else None)
                    for j, r in enumerate(state.results)
                    if r.correct and not r.skipped
                    and not (plan.drills[j].metadata.get("confidence_builder") if j < len(plan.drills) else False)
                ]
                if correct_results:
                    best_r, best_drill = max(correct_results,
                                             key=lambda x: x[0].content_item_id)
                    if best_drill:
                        builder = replace(best_drill, metadata={
                            **best_drill.metadata,
                            "confidence_builder": True,
                        })
                        insert_at = min(i + 2, len(plan.drills))
                        plan.drills.insert(insert_at, builder)
                        show_fn(display.dim("Quick checkpoint —"))
                        confidence_builders_used += 1
                        consecutive_wrong = 0

        # Immediate feedback — use rich feedback from drill if available
        if result.confidence in ("half", "unknown", "narrowed", "narrowed_wrong"):
            # Confidence states: show feedback without ✓/→ markers
            if result.feedback:
                show_fn(result.feedback)
        elif result.correct:
            show_fn("  ✓")
            if result.feedback:
                show_fn(result.feedback)

            # Phase 3a: Elaborative interrogation (~15% of correct, non-skipped)
            if (not result.skipped
                    and not drill.metadata.get("confidence_builder")
                    and random.random() < 0.15):
                from .drills import ELABORATIVE_PROMPTS
                prompt_template = ELABORATIVE_PROMPTS.get(drill.drill_type)
                if prompt_template:
                    try:
                        prompt = prompt_template.format(
                            hanzi=item.get("hanzi", ""),
                            pinyin=item.get("pinyin", ""),
                            english=item.get("english", ""),
                        )
                        show_fn(display.elaborative_prompt(prompt))
                    except (KeyError, IndexError):
                        pass
        else:
            if result.feedback:
                show_fn(f"  → {result.feedback}")
            else:
                # Fallback: always show something useful on miss
                fallback = result.expected_answer or item.get("hanzi", "")
                show_fn(f"  → {item.get('hanzi', '')} = {fallback}")

        # Mastery stage indicator — show after each non-skipped drill
        if not result.skipped:
            _show_mastery_stage(conn, drill.content_item_id, drill.modality, show_fn, user_id=user_id)

        # Audio: speak correct answer after miss
        if audio_enabled and not result.correct and not result.skipped:
            from .audio import speak_chinese
            speak_chinese(item.get("hanzi", ""))

        # Context note: check both DB field and CONTEXT_NOTES dict
        context_note = item.get("context_note")
        if not context_note:
            from .context_notes import CONTEXT_NOTES
            context_note = CONTEXT_NOTES.get(item.get("hanzi", ""))
        if context_note:
            show_note = (not result.correct) or random.random() < 0.3
            if show_note and not result.skipped:
                show_fn(display.dim_italic(context_note))

        # Personalized domain context: 20% chance on correct, non-skipped
        if result.correct and not result.skipped:
            if random.random() < 0.2:
                try:
                    pref_domains = (profile.get("preferred_domains") or "").strip()
                    if pref_domains:
                        from .personalization import get_personalized_sentences
                        domain = pref_domains.split(",")[0].strip()
                        max_hsk = max(int(profile.get("level_reading", 1) or 1), 1) + 1
                        sents = get_personalized_sentences(max_hsk, domain, n=1)
                        if sents:
                            show_fn(display.context_note(sents[0]['hanzi'], sents[0]['english']))
                except (ImportError, KeyError, TypeError, ValueError) as e:
                    logger.debug("personalization display skipped: %s", e)

        # Momentum micro-signal — acknowledge streaks without praise inflation
        if result.correct and not result.skipped:
            streak_run += 1
            if streak_run in (3, 5, 7):
                _streak_labels = {3: "3 in a row", 5: "5 in a row", 7: "7 — strong"}
                show_fn(display.streak_label(_streak_labels[streak_run]))
        elif not result.skipped:
            streak_run = 0

        # Time cap — auto-finish to prevent hyperfocus
        from .config import SESSION_TIME_CAP_SECONDS
        elapsed_s = time.monotonic() - session_start
        if elapsed_s >= SESSION_TIME_CAP_SECONDS and i < len(plan.drills) - 1:
            show_fn(f"\n  ── {int(elapsed_s // 60)} min — good stopping point. ──")
            state.early_exit = True
            break

        i += 1

    # ── In-session error retry: revisit missed items ──
    missed = [
        (r, plan.drills[i] if i < len(plan.drills) else None)
        for i, r in enumerate(state.results)
        if not r.correct and not r.skipped and r.confidence == "full"
    ]
    if missed and not state.early_exit:
        show_fn("\n  ─────────────────────────")
        show_fn("  Revisiting missed items.\n")
        retry_count = 0
        for orig_result, drill in missed:
            if retry_count >= 3:
                break
            if drill is None:
                continue
            item = conn.execute(
                "SELECT * FROM content_item WHERE id = ?",
                (drill.content_item_id,)
            ).fetchone()
            if not item:
                continue
            item = dict(item)

            show_fn(f"\n  [retry]  ", end="")
            _show_drill_label(drill, show_fn, seen_drill_types)

            retry_start = time.monotonic()
            result = run_drill(drill.drill_type, item, conn, show_fn, input_fn,
                              prominent=prominent, audio_enabled=audio_enabled)
            retry_ms = int((time.monotonic() - retry_start) * 1000)

            if result.skipped:
                break

            db.record_attempt(
                conn,
                content_item_id=drill.content_item_id,
                modality=drill.modality,
                correct=result.correct,
                session_id=session_id,
                error_type=result.error_type,
                user_answer=result.user_answer,
                expected_answer=result.expected_answer,
                drill_type=drill.drill_type,
                confidence=result.confidence,
                response_ms=retry_ms,
                user_id=user_id,
            )

            state.results.append(result)
            if result.correct:
                show_fn("  ✓  (got it this time)")
            elif result.feedback:
                show_fn(f"  → {result.feedback}")

            retry_count += 1

    _finalize(conn, state, show_fn, input_fn=input_fn, pre_milestones=pre_milestones, user_id=user_id)

    # ── Session metrics (observability) ──
    try:
        from .retention import compute_session_metrics, save_session_metrics
        metrics = compute_session_metrics(conn, state.session_id, user_id=user_id)
        save_session_metrics(conn, state.session_id, metrics)
        # Surface transfer events
        if metrics.get("transfer_events", 0) > 0:
            show_fn(f"  Transfer: {metrics['transfer_events']} item(s) succeeded in a new modality")
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.warning("session metrics failed for session %d: %s", state.session_id, e)
        show_fn(display.hint("session metrics unavailable"))

    return state


def _get_cadence(conn, user_id: int = 1) -> Optional[int]:
    """Sessions per week over the last 14 days, rounded to nearest int.

    Returns None if fewer than 2 sessions in the window.
    """
    from datetime import date as dt_date, timedelta
    cutoff = (dt_date.today() - timedelta(days=14)).isoformat()
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM session_log
        WHERE items_completed > 0 AND date(started_at) >= ?
          AND user_id = ?
    """, (cutoff, user_id)).fetchone()
    count = row["cnt"] if row else 0
    if count < 2:
        return None
    return round(count / 2)  # sessions per week (14 days = 2 weeks)


_SUPPLEMENTARY_DRILLS = {"register_choice", "pragmatic", "slang_exposure"}

_STAGE_DISPLAY = {
    "seen": "seen",
    "passed_once": "passed once",
    "stabilizing": "stabilizing",
    "stable": "stable",
    "durable": "durable",
    "decayed": "needs review",
}


def _show_confidence_calibration(state: SessionState, show_fn: Callable) -> None:
    """Show confidence calibration feedback after session.

    Compares accuracy of full-confidence answers vs lower-confidence answers.
    Helps learner calibrate when to use ? (50/50) vs committing to an answer.
    Requires at least 3 full-confidence and 2 lower-confidence attempts.
    """
    full_results = [r for r in state.results
                    if not r.skipped and r.confidence in ("full", None)]
    low_results = [r for r in state.results
                   if not r.skipped and r.confidence in ("half", "narrowed", "unknown")]

    if len(full_results) < 3 or len(low_results) < 2:
        return  # Not enough data for meaningful comparison

    full_acc = sum(1 for r in full_results if r.correct) / len(full_results)
    low_acc = sum(1 for r in low_results if r.correct) / len(low_results)

    # Only surface if there's a meaningful signal
    if full_acc > low_acc + 0.15:
        show_fn(display.dim(f"  Calibration: confident answers more reliable ({full_acc:.0%} vs {low_acc:.0%})."))
    elif low_acc > full_acc + 0.1:
        show_fn(display.dim(f"  Calibration: half-confidence answers outperformed ({low_acc:.0%} vs {full_acc:.0%}). Trust initial instincts."))


def _show_mastery_stage(conn, content_item_id: int, modality: str,
                        show_fn: Callable, user_id: int = 1) -> None:
    """Show a brief mastery stage indicator after a drill answer."""
    row = conn.execute("""
        SELECT mastery_stage, streak_correct
        FROM progress
        WHERE content_item_id = ? AND modality = ?
          AND user_id = ?
    """, (content_item_id, modality, user_id)).fetchone()
    if not row:
        return
    stage = row["mastery_stage"] or "seen"
    streak = row["streak_correct"] or 0
    label = _STAGE_DISPLAY.get(stage, stage)
    # Only show for non-trivial stages or when streak is building
    if stage == "seen" and streak == 0:
        return
    if stage in ("stabilizing",):
        show_fn(display.mastery_stage(label, streak))
    elif stage in ("stable", "durable"):
        show_fn(display.mastery_stage(label))
    elif streak > 0:
        show_fn(display.mastery_stage(label, streak))


def _show_drill_label(drill: DrillItem, show_fn: Callable,
                      seen_types: Optional[set] = None) -> None:
    """Show a brief label for what kind of drill this is.

    Labels are derived from DRILL_REGISTRY — single source of truth.
    Pass a session-scoped `seen_types` set to get first-encounter hints.
    """
    reg = DRILL_REGISTRY.get(drill.drill_type)
    label = reg["label"] if reg else drill.drill_type
    if drill.drill_type == "dialogue":
        label = "Dialogue"
    if drill.drill_type in _SUPPLEMENTARY_DRILLS:
        label += " [supplementary]"
    if drill.is_new:
        label += " (new)"
    if drill.is_confidence_win:
        label += " ★"
    if drill.is_error_focus:
        label += " ↻"
    if drill.metadata.get("retry"):
        label += " (retry)"
    show_fn(label)

    # First-encounter hint: briefly explain drill type
    desc = _DRILL_DESCRIPTIONS.get(drill.drill_type)
    if desc and seen_types is not None and drill.drill_type not in seen_types:
        seen_types.add(drill.drill_type)
        show_fn(display.hint(desc))


def _finalize(conn, state: SessionState, show_fn: Callable,
              input_fn: Callable = None, pre_milestones: set = None,
              user_id: int = 1) -> None:
    """End the session and show summary.

    Core summary (3 lines) always shown. Secondary details behind [d] prompt
    to avoid overwhelming post-session attention.
    """
    db.end_session(
        conn,
        session_id=state.session_id,
        items_completed=state.items_completed,
        items_correct=state.items_correct,
        modality_counts=state.modality_counts,
        early_exit=state.early_exit,
        boredom_flags=state.boredom_flags,
        user_id=user_id,
    )

    show_fn("\n  ─────────────────────────")

    if state.early_exit and state.items_completed == 0:
        show_fn("  Session saved. Continuing.")
        return

    total = state.items_completed
    correct = state.items_correct
    accuracy = (correct / total * 100) if total > 0 else 0

    # ── Core line 1: Accuracy vs historical ──
    recent = db.get_session_history(conn, limit=8, user_id=user_id)
    past_sessions = [s for s in recent if s["id"] != state.session_id
                     and (s.get("items_completed") or 0) > 0][:7]
    if past_sessions:
        past_correct = sum(s["items_correct"] or 0 for s in past_sessions)
        past_total = sum(s["items_completed"] or 0 for s in past_sessions)
        past_avg = (past_correct / past_total * 100) if past_total > 0 else 0
        window = len(past_sessions)
        if accuracy > past_avg + 5:
            show_fn(f"  {correct}/{total} correct ({accuracy:.0f}%) — above {window}-session avg of {past_avg:.0f}%")
        elif accuracy < past_avg - 5:
            show_fn(f"  {correct}/{total} correct ({accuracy:.0f}%) — harder set today (avg: {past_avg:.0f}%)")
        else:
            show_fn(f"  {correct}/{total} correct ({accuracy:.0f}%) — steady with average")
    else:
        show_fn(f"  {correct}/{total} correct ({accuracy:.0f}%) — first sessions are the hardest")

    # ── Core line 2: Mini sparkline ──
    spark_sessions = db.get_session_history(conn, limit=10, user_id=user_id)
    spark_completed = [s for s in spark_sessions if (s.get("items_completed") or 0) > 0]
    if len(spark_completed) >= 3:
        from .cli import _sparkline, _session_accuracy_pct
        acc_values = [_session_accuracy_pct(s) for s in reversed(spark_completed)]
        spark = _sparkline(acc_values)
        show_fn(display.sparkline("Recent:", spark))

    # ── Core line 3: Cadence ──
    cadence = _get_cadence(conn, user_id=user_id)
    if cadence is not None and cadence > 0:
        cadence_display = "7+" if cadence > 7 else str(cadence)
        show_fn(f"  Practicing ~{cadence_display}x/week")

    # ── Confidence calibration — metacognitive feedback ──
    _show_confidence_calibration(state, show_fn)

    # ── Milestones — rare and exciting, prominent in main flow ──
    if pre_milestones is not None:
        post_summary = get_growth_summary(conn)
        post_keys = {m["key"] for m in post_summary.get("unlocked", [])}
        new_keys = post_keys - pre_milestones
        if new_keys:
            from .milestones import MILESTONES
            show_fn("")
            show_fn("  ─── New Milestone ───")
            for m in MILESTONES:
                if m["key"] in new_keys:
                    show_fn(f"  ✦ {m['label']}")
            show_fn("  ──────────────────────")

    # ── Early exit message ──
    if state.early_exit:
        show_fn(f"\n  Short session — {correct}/{total} saved.")

    # ── HSK progression prompt — actionable, show immediately ──
    next_hsk = db.should_suggest_next_hsk(conn)
    if next_hsk:
        mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
        max_level = max(mastery.keys())
        pct = mastery[max_level]["pct"]
        show_fn(f"\n  HSK 1-{max_level}: {pct:.0f}% mastered.")
        show_fn(f"  Load HSK {next_hsk}: mandarin add-hsk {next_hsk}")

    # ── Calibration prompt (sessions 3-5, and periodically if uncalibrated) ──
    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions", 0) or 0
    confidence_sum = sum(
        float(profile.get(f"confidence_{m}", 0) or 0)
        for m in ("reading", "listening", "ime")
    )
    show_calibrate = (
        confidence_sum < 0.3
        and total_sessions in (3, 4, 5, 10, 20, 50)
    )
    if show_calibrate:
        show_fn(f"\n{display.dim('Calibrate: ./run calibrate')}")
        show_fn(display.dim("Estimates current level across modalities."))

    # ── Stage transitions — top 3 in main flow ──
    transitions = db.get_stage_transitions(conn, state.session_id, user_id=user_id)
    if transitions:
        parts = []
        for t in transitions[:3]:
            from_l = _STAGE_LABELS.get(t["from"], t["from"])
            to_l = _STAGE_LABELS.get(t["to"], t["to"])
            parts.append(f"{t['hanzi']} ({from_l} → {to_l})")
        show_fn(display.dim(f"Strengthened: {', '.join(parts)}"))

    # ── Collapsible details — secondary signals behind [d] prompt ──
    detail_lines = _build_detail_lines(conn, state, cadence, user_id=user_id)
    if detail_lines and input_fn:
        show_fn("")
        try:
            d_input = input_fn("  Enter to finish, d for details: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            d_input = ""
        if d_input == "d":
            for line in detail_lines:
                show_fn(line)

    # ── Monthly snapshot (every 30 sessions) ──
    if total_sessions > 0 and total_sessions % 30 == 0:
        _show_monthly_snapshot(conn, show_fn, total_sessions, user_id=user_id)

    # ── Real-world task surfacing (relatedness grounding) ──
    if total > 0:
        _show_real_world_task(conn, state, show_fn)

    # ── Post-session behavioral nudges ──
    if input_fn and total > 0:
        _post_session_nudges(conn, show_fn, input_fn, user_id=user_id)

    show_fn("")


def _show_real_world_task(conn, state: SessionState, show_fn: Callable) -> None:
    """Show a contextual real-world task matching items practiced this session."""
    import json
    from pathlib import Path

    tasks_path = Path(__file__).parent.parent / "data" / "real_world_tasks.json"
    try:
        with open(tasks_path) as f:
            data = json.load(f)
        tasks = data.get("tasks", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return

    if not tasks:
        return

    # Collect hanzi from this session's drills
    session_hanzi = set()
    for r in state.results:
        if r.expected_answer:
            session_hanzi.update(r.expected_answer)

    # Get max HSK level from session drills
    session_hsk = set()
    for d in state.plan.drills:
        hsk = d.metadata.get("hsk_level", 0)
        if hsk:
            session_hsk.add(hsk)
    max_hsk = max(session_hsk) if session_hsk else 1

    # Score tasks by vocab overlap with session items
    best_task = None
    best_overlap = 0
    for task in tasks:
        if task.get("hsk_level", 99) > max_hsk + 1:
            continue
        key_vocab = task.get("key_vocab", [])
        overlap = sum(1 for v in key_vocab if any(c in session_hanzi for c in v))
        if overlap > best_overlap:
            best_overlap = overlap
            best_task = task

    if best_task and best_overlap > 0:
        show_fn(f"\n{display.dim('Real-world practice: ' + best_task['task'])}")
    elif tasks:
        # Fall back to a task matching the HSK level
        level_tasks = [t for t in tasks if t.get("hsk_level", 99) <= max_hsk]
        if level_tasks:
            task = random.choice(level_tasks)
            show_fn(f"\n{display.dim('Real-world practice: ' + task['task'])}")


def _build_detail_lines(conn, state: SessionState, cadence, user_id: int = 1) -> List[str]:
    """Build secondary summary lines (shown only on [d] request)."""
    lines = []
    total = state.items_completed
    accuracy = (state.items_correct / total * 100) if total > 0 else 0

    # Usefulness
    new_count = sum(1 for d in state.plan.drills if d.is_new)
    error_count = sum(1 for r in state.results if not r.correct and not r.skipped)
    usefulness_parts = []
    if new_count > 0:
        usefulness_parts.append(f"{new_count} new introduced")
    if error_count > 0 and accuracy >= 50:
        usefulness_parts.append(f"{error_count} errors to learn from")
    if usefulness_parts:
        lines.append(f"  {', '.join(usefulness_parts)}.")

    # Speed
    speed_row = conn.execute("""
        SELECT AVG(p.avg_response_ms) as avg_ms, COUNT(*) as cnt
        FROM progress p
        WHERE p.avg_response_ms IS NOT NULL AND p.last_review_date = ?
          AND p.user_id = ?
    """, (date.today().isoformat(), user_id)).fetchone()
    if speed_row and speed_row["avg_ms"] and speed_row["cnt"] >= 3:
        avg_s = speed_row["avg_ms"] / 1000
        if avg_s < 4:
            lines.append(f"  Speed: {avg_s:.1f}s avg — responses feel automatic")
        elif avg_s < 7:
            lines.append(f"  Speed: {avg_s:.1f}s avg — getting faster")
        else:
            lines.append(f"  Speed: {avg_s:.1f}s avg — still processing (this improves with repetition)")

    # Errors
    error_results = [r for r in state.results if not r.correct and not r.skipped
                     and r.confidence == "full"]
    if error_results:
        error_types = {}
        for e in error_results:
            if e.error_type:
                error_types[e.error_type] = error_types.get(e.error_type, 0) + 1
        if error_types:
            parts = [f"{etype} ({cnt})" for etype, cnt in
                     sorted(error_types.items(), key=lambda x: -x[1])]
            lines.append(f"  Misses: {', '.join(parts)}")

    # Resolved
    resolved = db.get_resolved_this_session(conn, state.session_id, user_id=user_id)
    if resolved:
        resolved_parts = [r['hanzi'] for r in resolved]
        lines.append(f"  Resolved: {', '.join(resolved_parts)}")

    # Stage transitions
    transitions = db.get_stage_transitions(conn, state.session_id, user_id=user_id)
    if transitions:
        parts = []
        for t in transitions[:5]:
            from_l = _STAGE_LABELS.get(t["from"], t["from"])
            to_l = _STAGE_LABELS.get(t["to"], t["to"])
            parts.append(f"{t['hanzi']} ({from_l} → {to_l})")
        lines.append(f"  Strengthened: {', '.join(parts)}")

    # Consistency messaging
    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions", 0) or 0
    days_gap = db.get_days_since_last_session(conn)
    if cadence is not None and cadence >= 5 and total_sessions < 14:
        lines.append("  Consistency matters more than intensity. 3x/week for months beats daily for weeks.")
    elif days_gap is not None and days_gap >= 7 and cadence is not None and cadence >= 4:
        lines.append("  Continuing.")

    # Retention
    try:
        from .retention import compute_retention_stats, RECALL_THRESHOLD
        ret = compute_retention_stats(conn, user_id=user_id)
        if ret["total_items"] >= 5:
            threshold_pct = int(RECALL_THRESHOLD * 100)
            lines.append(f"  Memory: {ret['retention_pct']:.0f}% of items above {threshold_pct}% recall")
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("retention stats unavailable for summary: %s", e)

    # What's next
    if not state.early_exit and total > 0:
        due = db.get_items_due_count(conn, user_id=user_id)
        new_avail = db.get_new_items_available(conn, user_id=user_id)
        parts = []
        if due > 0:
            parts.append(f"{due} items due for review")
        if new_avail > 0:
            parts.append(f"{new_avail} new available")
        if parts:
            lines.append(f"  Next session: {', '.join(parts)}.")

        from .diagnostics import compute_readiness
        readiness = compute_readiness(conn, user_id=user_id)
        lines.append(f"  Focus: {readiness['focus']}")

    return lines


def _show_monthly_snapshot(conn, show_fn, total_sessions: int, user_id: int = 1):
    """Show a 'Month in Review' summary every 30 sessions."""
    from .milestones import get_stage_counts, get_growth_summary

    stages = get_stage_counts(conn)
    growth = get_growth_summary(conn)
    solid = stages["stable"] + stages["durable"]
    stabilizing = stages["stabilizing"]

    show_fn("\n  ═══════════════════════════")
    show_fn(f"  Month in Review — Session {total_sessions}")
    show_fn("  ═══════════════════════════")

    show_fn(f"  {solid} items mastered · {stabilizing} stabilizing")
    show_fn(f"  {growth['phase_label']}")

    # Mastery by HSK
    mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
    active = {k: v for k, v in mastery.items() if v.get("seen", 0) > 0} if mastery else {}
    if active:
        parts = []
        for level in sorted(active.keys()):
            m = active[level]
            lvl_solid = m.get("stable", 0) + m.get("durable", 0)
            parts.append(f"HSK {level}: {lvl_solid}/{m['total']}")
        show_fn(f"  {' · '.join(parts)}")

    # Milestones earned
    if growth["unlocked"]:
        recent = growth["unlocked"][-3:]
        show_fn(f"  Recent milestones: {', '.join(m['label'] for m in recent)}")

    if growth["next"]:
        show_fn(f"  Next: {growth['next']['label']}")

    show_fn("  ═══════════════════════════\n")


# ── Relatedness nudges (SDT) — rotate by session count ──
_RELATEDNESS_NUDGES = [
    "Try using 3 words from today's session in a real conversation this week.",
    "Consider a language exchange — apps like Tandem or HelloTalk connect you with native speakers.",
    "Next time you're at a Chinese restaurant, try ordering in Mandarin.",
    "Find a Chinese-speaking conversation partner for weekly 20-minute chats.",
    "Watch a recommended media clip with someone — explaining what you hear builds fluency.",
]


def _post_session_nudges(conn, show_fn, input_fn, user_id: int = 1):
    """Post-session behavioral nudges: intention, pre-commitment, relatedness."""
    from datetime import datetime, timezone

    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions", 0) or 0

    # ── Implementation intention: "When's your next session?" ──
    try:
        resp = input_fn("\n  When's your next session? (e.g. 'tomorrow morning') ").strip()
        if resp and resp.upper() not in ("", "Q", "N"):
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE learner_profile SET next_session_intention = ?, intention_set_at = ? WHERE user_id = ?",
                (resp, now, user_id)
            )
            conn.commit()
    except (EOFError, KeyboardInterrupt):
        pass

    # ── Pre-commitment for weak days ──
    # Detect if there's a day-of-week the learner consistently skips
    minimal_days = (profile.get("minimal_days") or "").strip()
    if not minimal_days and total_sessions >= 10:
        try:
            _offer_precommitment(conn, show_fn, input_fn, user_id=user_id)
        except (EOFError, KeyboardInterrupt):
            pass

    # ── Relatedness nudge (~every 10 sessions) ──
    if total_sessions > 0 and total_sessions % 10 == 0:
        idx = (total_sessions // 10 - 1) % len(_RELATEDNESS_NUDGES)
        show_fn(f"\n{display.dim(_RELATEDNESS_NUDGES[idx])}")


_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _offer_precommitment(conn, show_fn, input_fn, user_id: int = 1):
    """Detect consistently skipped days and offer to set them as minimal-session days."""
    rows = conn.execute("""
        SELECT session_day_of_week, COUNT(*) as cnt
        FROM session_log
        WHERE started_at >= date('now', '-28 days')
          AND items_completed > 0
          AND session_day_of_week IS NOT NULL
          AND user_id = ?
        GROUP BY session_day_of_week
    """, (user_id,)).fetchall()

    if not rows:
        return

    dow_counts = {r["session_day_of_week"]: r["cnt"] for r in rows}
    avg_count = sum(dow_counts.values()) / 7
    if avg_count < 0.5:
        return  # Not enough data

    # Find days with 0 sessions (consistently skipped)
    weak_days = [d for d in range(7) if dow_counts.get(d, 0) == 0]
    if not weak_days:
        return

    day_names = [_DOW_NAMES[d] for d in weak_days[:2]]
    show_fn(f"\n{display.dim('You tend to skip ' + ', '.join(day_names) + '.')}")
    resp = input_fn(f"  Switch to 90-second sessions on those days? (y/n) ").strip().lower()
    if resp == "y":
        conn.execute(
            "UPDATE learner_profile SET minimal_days = ? WHERE user_id = ?",
            (",".join(str(d) for d in weak_days), user_id)
        )
        conn.commit()
        show_fn(display.dim(f"Done — {', '.join(day_names)} set to mini sessions."))
