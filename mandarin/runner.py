"""Session runner — executes a SessionPlan through the CLI."""

import logging
import random
import sqlite3
import time
import traceback
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone, UTC
from pathlib import Path
from statistics import mean
from typing import List, Optional
from collections.abc import Callable

from . import db, display

logger = logging.getLogger(__name__)
from .scheduler import SessionPlan, DrillItem
from .drills import run_drill, DrillResult, DRILL_REGISTRY
from .drills.base import detect_near_miss, format_near_miss_feedback
from .conversation import run_dialogue_drill
from .scenario_loader import get_scenario_by_id, record_scenario_attempt
from .media import get_media_entry, run_media_comprehension
from .milestones import get_growth_summary

_STAGE_LABELS = display.STAGE_LABELS

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DRILL_LOG = _DATA_DIR / "drill_errors.log"
_SESSION_TRACE = _DATA_DIR / "session_trace.jsonl"

# Dedicated rotating loggers for drill errors and session trace.
# propagate=False keeps them out of the root logger (no duplicates).
_drill_error_logger = logging.getLogger("mandarin.drill_errors")
_drill_error_logger.propagate = False

_trace_logger = logging.getLogger("mandarin.session_trace")
_trace_logger.propagate = False

_rotating_loggers_initialized = False


def _ensure_rotating_loggers():
    """Lazily attach rotating handlers (avoids import-time file creation)."""
    global _rotating_loggers_initialized
    if _rotating_loggers_initialized:
        return
    from .log_config import get_rotating_handler
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    # These loggers format their own content (human-readable text / raw JSONL),
    # so use a message-only formatter instead of JSONFormatter to avoid
    # double-wrapping.
    raw_fmt = logging.Formatter("%(message)s")

    _drill_error_logger.setLevel(logging.DEBUG)
    _drill_error_logger.addHandler(get_rotating_handler(_DRILL_LOG, formatter=raw_fmt))

    _trace_logger.setLevel(logging.DEBUG)
    _trace_logger.addHandler(get_rotating_handler(_SESSION_TRACE, formatter=raw_fmt))

    _rotating_loggers_initialized = True


def _log_drill_error(drill_type: str, item_id, exc: Exception, context: dict = None):
    """Append a drill-level error to drill_errors.log with full reproduction context.

    context should include everything needed to reproduce: item data, drill
    metadata, scaffold level, session state counts, etc.
    """
    import json
    from .log_config import utc_now_iso
    _ensure_rotating_loggers()
    tb = traceback.format_exc()
    ctx_str = ""
    if context:
        ctx_str = "\n--- context ---\n" + json.dumps(
            context, ensure_ascii=False, indent=2, default=str)
    _drill_error_logger.error(
        "\n%s\n%s  drill_type=%s  item_id=%s\n%s%s",
        "=" * 60, utc_now_iso(), drill_type, item_id, tb, ctx_str,
    )
    logger.error("drill %s (item %s) crashed: %s", drill_type, item_id, exc)


def _trace(session_id: int, event: str, **kwargs):
    """Append a structured event to session_trace.jsonl — flight recorder for debugging."""
    import json
    from .log_config import utc_now_iso
    _ensure_rotating_loggers()
    entry = {
        "ts": utc_now_iso(),
        "session": session_id,
        "event": event,
    }
    entry.update(kwargs)
    _trace_logger.info("%s", json.dumps(entry, ensure_ascii=False))


_DRILL_DESCRIPTIONS = {
    "mc": "What does this mean?",
    "mc_reading": "What does this mean?",
    "reverse_mc": "Which character matches?",
    "mc_listening": "Listen and identify",
    "ime_type": "Write the pinyin",
    "ime": "Write the pinyin",
    "tone": "Pick the correct tones from 4 options",
    "pinyin_recall": "What's the pronunciation?",
    "english_to_pinyin": "What's the pronunciation?",
    "pinyin_reading": "Read and write the pinyin",
    "hanzi_to_pinyin": "Read and write the pinyin",
    "pinyin_to_hanzi": "Write the character from pinyin",
    "listening_gist": "Listen for the meaning",
    "listening_detail": "Listen and answer",
    "listening_tone": "Pick the correct tones from 4 options",
    "listening_dictation": "Write what you hear",
    "intuition": "Which sounds natural?",
    "dialogue": "Choose your response",
    "register_choice": "Pick the right register",
    "pragmatic": "What's the appropriate response?",
    "slang_exposure": "Colloquial usage",
    "speaking": "Speak the phrase aloud",
    "transfer": "Apply in a new context",
    "measure_word": "Which measure word?",
    "measure_word_cloze": "Fill in the measure word",
    "measure_word_production": "Type the measure word",
    "measure_word_disc": "Which noun uses this MW?",
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
    "number_system": "Express this in Chinese",
    "tone_sandhi": "How is this pronounced?",
    "complement": "Fill in the complement",
    "ba_bei": "把 or 被?",
    "collocation": "Which verb fits?",
    "radical": "Identify the radical",
    "error_correction": "Find the error",
    "chengyu": "Four-character idiom",
}


@dataclass
class SessionState:
    """Mutable state for a running session."""
    session_id: int
    plan: SessionPlan
    results: list[DrillResult] = field(default_factory=list)
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
                user_id: int = 1,
                progress_fn: Callable | None = None,
                drill_meta_fn: Callable | None = None,
                client_platform: str = "cli") -> SessionState:
    """Run a complete session from a plan.

    show_fn(text): display text to user
    input_fn(prompt) -> str: get user input
    progress_fn(session_id, drill_index, drill_total, correct, completed, session_type):
        optional callback after each drill for progress checkpointing

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
        client_platform=client_platform,
        experiment_variant=getattr(plan, 'experiment_variant', None),
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

    _trace(session_id, "session_start",
           n_drills=len(plan.drills),
           session_type=plan.session_type,
           micro_plan=plan.micro_plan,
           drill_types=[d.drill_type for d in plan.drills])

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

    # Speaking level for tone leniency scaling
    speaking_level = profile.get("level_speaking", 1.0) or 1.0

    # Audio: default ON on macOS; profile setting overrides only if explicitly 0
    from .audio import is_audio_available, get_tts_rate, set_default_rate
    audio_enabled = profile.get("audio_enabled", 1) != 0 and is_audio_available()
    if audio_enabled:
        listening_level = profile.get("level_listening", 1.0) or 1.0
        # Adaptive TTS: slower for beginners, natural speed for advanced
        base_rate = get_tts_rate("sample", listening_level)
        set_default_rate(base_rate)

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
        try:
            _finalize(conn, state, show_fn, input_fn=input_fn, pre_milestones=pre_milestones, user_id=user_id)
        except Exception as exc:
            _log_drill_error("_finalize", state.session_id, exc, context={
                "items_completed": state.items_completed,
                "phase": "early_quit",
            })
            show_fn(f"\n  Session saved: {state.items_correct}/{state.items_completed}")
            show_fn(f"  (summary error logged to data/drill_errors.log)")
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

    # Per-item miss count for failure escalation (Doctrine §3: tiered feedback)
    _item_miss_count = {}  # content_item_id -> int

    # Phase 10: Within-session difficulty adaptation
    scaffold_adjusted = False
    seen_drill_types = set()  # Session-scoped for first-encounter hints
    pending_insertions = []  # (offset_from_i, drill) pairs queued during the loop
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
                    show_fn("\n  ── Halfway through. ──")

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
                show_fn("  Moving on\u2026")
                i += 1
                continue
            scenario = get_scenario_by_id(conn, scenario_id)
            if not scenario:
                show_fn("  Moving on\u2026")
                i += 1
                continue
            support_level = drill.metadata.get("support_level", "full_support")
            try:
                result = run_dialogue_drill(scenario, show_fn, input_fn, support_level=support_level, conn=conn)
            except Exception as exc:
                _log_drill_error("dialogue", scenario_id, exc, context={
                    "scenario_id": scenario_id,
                    "scenario_title": scenario.get("title", "?"),
                    "support_level": support_level,
                    "n_turns": len(scenario.get("tree", {}).get("turns", [])),
                    "metadata": drill.metadata,
                    "session_index": i,
                })
                show_fn("  Moving on\u2026")
                i += 1
                continue
            if result.score is not None:
                record_scenario_attempt(conn, scenario_id, result.score)

            if result.skipped and result.user_answer.upper() == "Q":
                state.early_exit = True
                state.results.append(result)
                _trace(session_id, "drill_quit", index=i, drill_type="dialogue")
                break
            if result.skipped and result.user_answer.upper() == "B":
                state.boredom_flags += 1
                show_fn("  (Noted)")
                _trace(session_id, "drill_skip", index=i, drill_type="dialogue")
                i += 1
                continue

            state.results.append(result)
            _trace(session_id, "drill_done", index=i, drill_type="dialogue",
                   correct=result.correct, score=result.score,
                   user_answer=result.user_answer[:80])
            # Dialogue already shows "Dialogue score: N%" — no need for a separate ✓
            i += 1
            continue

        # Handle media comprehension drills
        if drill.drill_type == "media_comprehension":
            mid = drill.metadata.get("media_id")
            if not mid:
                show_fn("  Moving on\u2026")
                i += 1
                continue
            entry = get_media_entry(mid)
            if not entry:
                show_fn("  Moving on\u2026")
                i += 1
                continue
            try:
                result = run_media_comprehension(entry, show_fn, input_fn, conn=conn)
            except Exception as exc:
                _log_drill_error("media_comprehension", mid, exc, context={
                    "media_id": mid,
                    "entry": dict(entry) if entry else None,
                    "metadata": drill.metadata,
                    "session_index": i,
                })
                show_fn("  Moving on\u2026")
                i += 1
                continue

            if result.skipped and result.user_answer.upper() == "Q":
                state.early_exit = True
                state.results.append(result)
                _trace(session_id, "drill_quit", index=i, drill_type="media_comprehension")
                break
            if result.skipped and result.user_answer.upper() == "B":
                state.boredom_flags += 1
                show_fn("  (Noted)")
                _trace(session_id, "drill_skip", index=i, drill_type="media_comprehension")
                i += 1
                continue

            state.results.append(result)
            _trace(session_id, "drill_done", index=i, drill_type="media_comprehension",
                   correct=result.correct, score=result.score,
                   user_answer=result.user_answer[:80])
            if result.correct:
                show_fn("  ✓")
            i += 1
            continue

        # Handle minimal pair drills (side-by-side interference contrast)
        if drill.drill_type == "minimal_pair":
            item_a = drill.metadata.get("item_a", {})
            item_b = drill.metadata.get("item_b", {})
            interference_type = drill.metadata.get("interference_type", "")
            if not item_a or not item_b:
                show_fn("  Moving on\u2026")
                i += 1
                continue
            # Present the minimal pair via show_fn/input_fn
            type_label = (
                "These sound similar" if interference_type == "near_homophone"
                else "These look similar" if interference_type == "visual_similarity"
                else "Easy to confuse"
            )
            show_fn(f"\n  {type_label}")
            show_fn(f"  Which one means '{item_a['english']}'?")
            show_fn(f"    a) {item_a['hanzi']}  {item_a['pinyin']}")
            show_fn(f"    b) {item_b['hanzi']}  {item_b['pinyin']}")
            answer = input_fn("  > ").strip().lower()
            correct = answer == "a"
            from .drills.base import DrillResult as _DR
            result = _DR(
                content_item_id=drill.content_item_id,
                modality="reading",
                drill_type="minimal_pair",
                correct=correct,
                user_answer=answer,
                expected_answer="a",
                error_type=None if correct else "vocab",
            )
            if result.skipped and answer.upper() == "Q":
                state.early_exit = True
                state.results.append(result)
                _trace(session_id, "drill_quit", index=i, drill_type="minimal_pair")
                break
            state.results.append(result)
            # Record both items in the pair to progress
            try:
                db.record_attempt(
                    conn,
                    content_item_id=item_a["id"],
                    modality="reading",
                    correct=correct,
                    session_id=session_id,
                    error_type=None if correct else "vocab",
                    drill_type="minimal_pair",
                    user_id=user_id,
                )
                db.record_attempt(
                    conn,
                    content_item_id=item_b["id"],
                    modality="reading",
                    correct=not correct,  # if user chose 'a' correctly, 'b' was the wrong choice
                    session_id=session_id,
                    error_type=None if not correct else "vocab",
                    drill_type="minimal_pair",
                    user_id=user_id,
                )
            except Exception:
                pass
            _trace(session_id, "drill_done", index=i, drill_type="minimal_pair",
                   correct=correct, hanzi=item_a.get("hanzi", ""))
            i += 1
            continue

        # Get the content item from DB for full data
        item = conn.execute(
            "SELECT * FROM content_item WHERE id = ?",
            (drill.content_item_id,)
        ).fetchone()

        if not item:
            show_fn("  Moving on\u2026")
            i += 1
            continue

        item = dict(item)

        # Inject drill metadata into item dict for drills that need it
        if drill.drill_type == "contrastive" and "contrastive_partner_id" in drill.metadata:
            item["contrastive_partner_id"] = drill.metadata["contrastive_partner_id"]

        # Run the drill with timing and gradient scaffold
        drill_start = time.monotonic()
        scaffold_level = drill.metadata.get("scaffold_level", "none")
        english_level = drill.metadata.get("english_level", "full")
        show_pinyin = scaffold_level == "full_pinyin"

        # Phase 10: Within-session difficulty adaptation
        if not scaffold_adjusted and state.items_completed >= 4:
            non_skipped = [r for r in state.results if not r.skipped]
            if non_skipped:
                running_acc = sum(1 for r in non_skipped if r.correct) / len(non_skipped)
                from .config import SCAFFOLD_ORDER, ENGLISH_ORDER
                if running_acc < 0.5 and len(non_skipped) >= 4:
                    # Upgrade scaffold: more support
                    idx = SCAFFOLD_ORDER.index(scaffold_level) if scaffold_level in SCAFFOLD_ORDER else 0
                    if idx < len(SCAFFOLD_ORDER) - 1:
                        scaffold_level = SCAFFOLD_ORDER[idx + 1]
                        show_pinyin = scaffold_level == "full_pinyin"
                    # Upgrade english: more support
                    eng_idx = ENGLISH_ORDER.index(english_level) if english_level in ENGLISH_ORDER else 0
                    if eng_idx < len(ENGLISH_ORDER) - 1:
                        english_level = ENGLISH_ORDER[eng_idx + 1]
                    scaffold_adjusted = True
                    logger.debug("scaffold upgraded mid-session, accuracy=%.0f%%", running_acc * 100)
                elif running_acc > 0.9 and len(non_skipped) >= 6:
                    # Downgrade scaffold: desirable difficulty
                    idx = SCAFFOLD_ORDER.index(scaffold_level) if scaffold_level in SCAFFOLD_ORDER else 0
                    if idx > 0:
                        scaffold_level = SCAFFOLD_ORDER[idx - 1]
                        show_pinyin = scaffold_level == "full_pinyin"
                    # Downgrade english: less support
                    eng_idx = ENGLISH_ORDER.index(english_level) if english_level in ENGLISH_ORDER else 0
                    if eng_idx > 0:
                        english_level = ENGLISH_ORDER[eng_idx - 1]
                    scaffold_adjusted = True
                    logger.debug("scaffold downgraded mid-session, accuracy=%.0f%%", running_acc * 100)

        # Mid-session struggle detection: pivot to confidence wins if accuracy < 40% after 5+ items
        if not getattr(state, '_struggle_pivoted', False) and state.items_completed >= 5:
            non_skipped = [r for r in state.results if not r.skipped]
            if non_skipped and len(non_skipped) >= 5:
                running_acc = sum(1 for r in non_skipped if r.correct) / len(non_skipped)
                if running_acc < 0.4:
                    state._struggle_pivoted = True
                    show_fn("\n  ── A few familiar faces next. ──")
                    # Replace remaining drills with confidence wins (high-streak items)
                    remaining_count = len(plan.drills) - i
                    if remaining_count > 3:
                        # Keep only 3 more drills, preferring confidence wins
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
                        else:
                            # No confidence wins available — keep next 3 original drills
                            plan.drills[i:] = plan.drills[i:i + 3]
                    _trace(session_id, "struggle_pivot", index=i,
                           accuracy=round(running_acc, 2),
                           remaining_after=len(plan.drills) - i)
                    logger.debug("struggle pivot at item %d, accuracy=%.0f%%", i, running_acc * 100)

        try:
            result = run_drill(drill.drill_type, item, conn, show_fn, input_fn,
                              prominent=prominent, audio_enabled=audio_enabled,
                              show_pinyin=show_pinyin, scaffold_level=scaffold_level,
                              english_level=english_level,
                              speaking_level=speaking_level,
                              user_id=user_id)
        except Exception as exc:
            _log_drill_error(drill.drill_type, drill.content_item_id, exc, context={
                "item": item,
                "drill_type": drill.drill_type,
                "modality": drill.modality,
                "hanzi": drill.hanzi,
                "metadata": drill.metadata,
                "scaffold_level": scaffold_level,
                "english_level": english_level,
                "show_pinyin": show_pinyin,
                "audio_enabled": audio_enabled,
                "session_index": i,
                "items_completed": state.items_completed,
                "items_correct": state.items_correct,
            })
            show_fn("  Moving on\u2026")
            _trace(session_id, "drill_crash", index=i,
                   drill_type=drill.drill_type, item_id=drill.content_item_id,
                   hanzi=drill.hanzi, error=str(exc)[:200])
            i += 1
            continue
        drill_ms = int((time.monotonic() - drill_start) * 1000)

        # Check for special commands
        if result.skipped and result.user_answer.upper() == "Q":
            state.early_exit = True
            state.results.append(result)
            _trace(session_id, "drill_quit", index=i,
                   drill_type=drill.drill_type, hanzi=drill.hanzi)
            break

        if result.skipped and result.user_answer.upper() == "B":
            state.boredom_flags += 1
            show_fn("  (Noted)")
            _trace(session_id, "drill_skip", index=i,
                   drill_type=drill.drill_type, hanzi=drill.hanzi)
            i += 1
            continue

        # Record to DB — fix modality for listening drills without audio
        record_modality = drill.modality
        if record_modality == "listening" and not audio_enabled:
            record_modality = "reading"  # text-only listening drills are really reading

        # Holdout probes go to counter_metric_holdout, NOT to SRS progress
        if drill.metadata.get("is_holdout"):
            try:
                from .holdout_probes import record_holdout_result
                record_holdout_result(
                    conn,
                    user_id=user_id,
                    content_item_id=drill.content_item_id,
                    modality=record_modality,
                    drill_type=drill.drill_type,
                    correct=result.correct,
                    response_ms=drill_ms,
                    session_id=session_id,
                    holdout_set=drill.metadata.get("holdout_set", "standard"),
                )
            except Exception:
                logger.debug("holdout result recording failed", exc_info=True)
        elif drill.metadata.get("is_delayed_validation"):
            try:
                from .delayed_validation import record_validation_result
                record_validation_result(
                    conn,
                    validation_id=drill.metadata["validation_id"],
                    correct=result.correct,
                    response_ms=drill_ms,
                    session_id=session_id,
                    drill_type=drill.drill_type,
                )
            except Exception:
                logger.debug("delayed validation result recording failed", exc_info=True)
        else:
            db.record_attempt(
                conn,
                content_item_id=drill.content_item_id,
                modality=record_modality,
                correct=result.correct,
                session_id=session_id,
                error_type=result.error_type,
                error_cause=getattr(result, "error_cause", None),
                user_answer=result.user_answer,
                expected_answer=result.expected_answer,
                drill_type=drill.drill_type,
                confidence=result.confidence,
                response_ms=drill_ms,
                user_id=user_id,
                metadata=result.metadata,
            )

        state.results.append(result)

        # Near-miss detection (behavioral economics: targeted feedback)
        near_miss_info = None
        if not result.correct and not result.skipped:
            try:
                nm = detect_near_miss(
                    user_answer=result.user_answer,
                    expected_answer=result.expected_answer,
                    drill_type=drill.drill_type,
                    error_type=result.error_type,
                )
                if nm:
                    result.near_miss_type = nm[0].value
                    near_miss_info = {
                        "type": nm[0].value,
                        "feedback": format_near_miss_feedback(nm),
                    }
            except Exception:
                logger.debug("near-miss detection failed", exc_info=True)

        # Send drill metadata to web UI for override support
        if drill_meta_fn:
            try:
                drill_meta_fn(
                    content_item_id=drill.content_item_id,
                    modality=record_modality,
                    correct=result.correct,
                    hanzi=drill.hanzi or "",
                    error_type=result.error_type or "",
                    requirement_ref=result.requirement_ref,
                    near_miss=near_miss_info,
                )
            except Exception:
                logger.debug("drill_meta_fn callback failed", exc_info=True)

        _trace(session_id, "drill_done", index=i,
               drill_type=drill.drill_type, hanzi=drill.hanzi,
               item_id=drill.content_item_id,
               correct=result.correct, confidence=result.confidence,
               user_answer=result.user_answer[:80],
               expected=result.expected_answer[:80],
               error_type=result.error_type,
               ms=drill_ms)

        # Incremental save — persist progress after each drill
        db.update_session_progress(conn, session_id,
                                   state.items_completed, state.items_correct)

        # Notify client for checkpoint persistence
        if progress_fn:
            try:
                progress_fn(session_id, i + 1, len(plan.drills),
                            state.items_correct, state.items_completed,
                            plan.session_type)
            except Exception:
                logger.debug("progress_fn callback failed", exc_info=True)

        # Within-session re-insertion: re-present failed items after a short delay
        # (Landauer & Bjork 1978 expanding retrieval practice)
        # Queued for insertion after index advances to avoid mid-loop mutation.
        if (not result.correct and not result.skipped
                and result.confidence == "full"
                and not drill.metadata.get("retry")
                and retry_insertions < MAX_RETRY_INSERTIONS):
            retry_drill = replace(drill, metadata={**drill.metadata, "retry": True})
            pending_insertions.append((4, retry_drill))
            retry_insertions += 1
            logger.debug("queued retry for %s (%d/%d retries)",
                         drill.hanzi, retry_insertions, MAX_RETRY_INSERTIONS)

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
                        pending_insertions.append((2, builder))
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

            # Phase 3a: Elaborative interrogation (generation effect)
            # Doctrine §1: new items get reflective prompts to build deeper encoding
            # Higher rate for new items (seen/passed_once: 40%), lower for established (5%)
            _elab_row = conn.execute(
                "SELECT mastery_stage FROM progress WHERE content_item_id = ? AND modality = ? AND user_id = ?",
                (drill.content_item_id, drill.modality, user_id),
            ).fetchone()
            _elab_stage = (_elab_row["mastery_stage"] if _elab_row else "seen") or "seen"
            _elab_rate = 0.40 if _elab_stage in ("seen", "passed_once") else 0.05
            if (not result.skipped
                    and not drill.metadata.get("confidence_builder")
                    and random.random() < _elab_rate):
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
                        logger.debug("elaborative prompt format failed", exc_info=True)
        else:
            # Track per-item miss count for escalation
            _item_miss_count[drill.content_item_id] = _item_miss_count.get(drill.content_item_id, 0) + 1
            miss_n = _item_miss_count[drill.content_item_id]

            if result.feedback:
                show_fn(f"  → {result.feedback}")
            else:
                # Fallback: show correction + distinction (doctrine §3: never just the answer)
                hanzi = item.get("hanzi", "")
                pinyin = item.get("pinyin", "")
                expected = result.expected_answer or hanzi
                user_ans = result.user_answer or ""
                if user_ans and user_ans != expected:
                    show_fn(f"  → {hanzi} ({pinyin}) = {expected}. You chose: {user_ans}")
                else:
                    show_fn(f"  → {hanzi} ({pinyin}) = {expected}")

            # Failure escalation tiers (Doctrine §3)
            # Tier 2: 2nd miss — show context note if available
            if miss_n >= 2:
                ctx_note = item.get("context_note")
                if not ctx_note:
                    from .context_notes import CONTEXT_NOTES
                    ctx_note = CONTEXT_NOTES.get(item.get("hanzi", ""))
                if ctx_note:
                    show_fn(display.dim_italic(f"  Context: {ctx_note}"))
            # Tier 3: 3rd+ miss — show full breakdown (hanzi + pinyin + english)
            if miss_n >= 3:
                show_fn(display.dim(f"  Full: {item.get('hanzi','')} [{item.get('pinyin','')}] = {item.get('english','')}"))

        # Mastery stage indicator — show after each non-skipped drill
        if not result.skipped:
            _show_mastery_stage(conn, drill.content_item_id, drill.modality, show_fn, user_id=user_id)

        # AI error explanation for persistent mistakes
        if not result.correct and not result.skipped:
            try:
                from .ai.error_explanation import generate_error_explanation
                # Count how many times this item has been wrong
                times_wrong_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM error_log WHERE content_item_id = ?",
                    (drill.content_item_id,),
                ).fetchone()
                times_wrong = (times_wrong_row["cnt"] if times_wrong_row else 0) or 0
                explanation = generate_error_explanation(
                    conn,
                    item_id=str(drill.content_item_id),
                    correct_answer=result.expected_answer,
                    wrong_answer=result.user_answer,
                    item_content=dict(item),
                    error_type=result.error_type or "",
                    times_wrong=times_wrong,
                    learner_hsk_level=max(int(profile.get("level_reading", 1) or 1), 1),
                )
                if explanation:
                    result.feedback = f"{result.feedback}\n\n{explanation}" if result.feedback else explanation
                    # Mark the most recent review event for this item as explanation-shown
                    try:
                        conn.execute("""
                            UPDATE review_event SET explanation_shown = 1
                            WHERE id = (
                                SELECT id FROM review_event
                                WHERE content_item_id = ? AND user_id = ?
                                ORDER BY created_at DESC LIMIT 1
                            )
                        """, (drill.content_item_id, user_id))
                        conn.commit()
                    except Exception:
                        pass
            except Exception:
                pass  # Never block drill flow for AI

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

        # Apply queued insertions now that this drill is done
        # Sort by offset descending so later inserts don't shift earlier ones
        for offset, queued_drill in sorted(pending_insertions, key=lambda x: -x[0]):
            insert_at = min(i + offset, len(plan.drills))
            plan.drills.insert(insert_at, queued_drill)
        pending_insertions.clear()

        i += 1

    # ── In-session error retry: revisit missed items ──
    missed = [
        (r, plan.drills[i] if i < len(plan.drills) else None)
        for i, r in enumerate(state.results)
        if not r.correct and not r.skipped and r.confidence == "full"
    ]
    if missed and not state.early_exit:
        show_fn("\n  ── One more look ──\n")
        retry_count = 0
        for _orig_result, drill in missed:
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
            try:
                result = run_drill(drill.drill_type, item, conn, show_fn, input_fn,
                                  prominent=prominent, audio_enabled=audio_enabled,
                                  user_id=user_id)
            except Exception as exc:
                _log_drill_error(drill.drill_type, drill.content_item_id, exc, context={
                    "item": item,
                    "drill_type": drill.drill_type,
                    "modality": drill.modality,
                    "hanzi": drill.hanzi,
                    "phase": "retry",
                })
                show_fn("  Moving on\u2026")
                continue
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
                metadata=result.metadata,
            )

            state.results.append(result)
            if result.correct:
                show_fn("  ✓  (solid)")
            elif result.feedback:
                show_fn(f"  → {result.feedback}")

            retry_count += 1

    try:
        _finalize(conn, state, show_fn, input_fn=input_fn, pre_milestones=pre_milestones, user_id=user_id)
    except Exception as exc:
        _log_drill_error("_finalize", state.session_id, exc, context={
            "items_completed": state.items_completed,
            "items_correct": state.items_correct,
            "early_exit": state.early_exit,
            "n_results": len(state.results),
            "drill_types_seen": list({r.drill_type for r in state.results}),
        })
        total = state.items_completed
        correct = state.items_correct
        show_fn(f"\n  Session saved: {correct}/{total}")
        show_fn(f"  (summary error logged to data/drill_errors.log)")

    elapsed_s = time.monotonic() - session_start
    _trace(session_id, "session_end",
           completed=state.items_completed,
           correct=state.items_correct,
           planned=len(plan.drills),
           early_exit=state.early_exit,
           boredom_flags=state.boredom_flags,
           elapsed_s=round(elapsed_s, 1))

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

    # ── Update interference pair drill timestamps for cross-session spacing ──
    try:
        drilled_ids = [r.content_item_id for r in state.results]
        if drilled_ids:
            _update_interference_drill_times(conn, drilled_ids)
    except Exception:
        logger.debug("interference pair timestamp update failed", exc_info=True)

    # ── Post-session anomaly summary ──
    _show_anomaly_summary(state, plan, elapsed_s, session_id, show_fn)

    return state


def _update_interference_drill_times(conn, drilled_item_ids: list) -> None:
    """Update interference_pairs timestamps after a session for cross-session spacing."""
    if not drilled_item_ids:
        return
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" * len(drilled_item_ids))
    try:
        conn.execute("""
            UPDATE interference_pairs SET last_item_a_drilled = ?
            WHERE item_id_a IN ({})
        """.format(placeholders), [now] + drilled_item_ids)
        conn.execute("""
            UPDATE interference_pairs SET last_item_b_drilled = ?
            WHERE item_id_b IN ({})
        """.format(placeholders), [now] + drilled_item_ids)
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Columns not yet migrated


def _get_cadence(conn, user_id: int = 1) -> int | None:
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
                      seen_types: set | None = None) -> None:
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


def _show_anomaly_summary(state: SessionState, plan: SessionPlan,
                          elapsed_s: float, session_id: int,
                          show_fn: Callable) -> None:
    """Print a visible debug summary if anything unusual happened during the session."""
    anomalies = []

    # Check for drill crashes (logged to drill_errors.log)
    try:
        if _DRILL_LOG.exists():
            import json as _json
            # Check session_trace for crash events from this session
            if _SESSION_TRACE.exists():
                with open(_SESSION_TRACE) as f:
                    crashes = [
                        _json.loads(line) for line in f
                        if line.strip()
                        and _json.loads(line).get("session") == session_id
                        and _json.loads(line).get("event") == "drill_crash"
                    ]
                if crashes:
                    anomalies.append(f"{len(crashes)} drill(s) crashed — see data/drill_errors.log")
    except (OSError, ValueError):
        pass

    # Skips
    skipped = sum(1 for r in state.results if r.skipped)
    if skipped:
        anomalies.append(f"{skipped} drill(s) skipped")

    # Struggle pivot
    if getattr(state, '_struggle_pivoted', False):
        anomalies.append("struggle pivot triggered (accuracy < 40%)")

    # Session shorter than planned
    planned = len(plan.drills)
    completed = state.items_completed
    if planned > 0 and completed < planned * 0.7 and not state.early_exit:
        anomalies.append(f"only {completed}/{planned} drills completed")

    # Unusually long session
    if elapsed_s > 900:  # 15+ minutes
        anomalies.append(f"session took {int(elapsed_s // 60)} minutes")

    if anomalies:
        show_fn(display.dim(f"\n  [debug] {' · '.join(anomalies)}"))


def _show_peak_moment(conn: sqlite3.Connection, state: SessionState,
                      show_fn: Callable, user_id: int = 1) -> None:
    """Show the peak moment of the session (Kahneman peak-end rule).

    Finds items that were previously errored but answered correctly this
    session — the most satisfying moment. Shows the best one.
    """
    if not state.results or state.items_correct == 0:
        return

    # Find items answered correctly this session
    correct_ids = [
        r.content_item_id for r in state.results
        if hasattr(r, "correct") and r.correct and hasattr(r, "content_item_id")
    ]
    if not correct_ids:
        return

    # Find which of these had recent errors (last 14 days)
    placeholders = ",".join("?" * len(correct_ids))
    try:
        rows = conn.execute(
            """SELECT re.content_item_id, ci.hanzi, ci.pinyin, ci.english,
                       MAX(re.reviewed_at) as last_error
                FROM review_event re
                JOIN content_item ci ON re.content_item_id = ci.id
                WHERE re.user_id = ?
                  AND re.content_item_id IN ({})
                  AND re.correct = 0
                  AND re.reviewed_at >= datetime('now', '-14 days')
                GROUP BY re.content_item_id
                ORDER BY last_error DESC
                LIMIT 1""".format(placeholders),
            [user_id] + correct_ids,
        ).fetchone()

        if rows:
            hanzi = rows["hanzi"]
            english = rows["english"]
            show_fn(display.dim(f"  Best moment: recalled {hanzi} ({english}) correctly"))
    except Exception:
        pass


def _show_next_session_preview(conn: sqlite3.Connection, show_fn: Callable,
                                user_id: int = 1) -> None:
    """Preview upcoming items for next session (Zeigarnik effect).

    Showing what's coming next creates anticipation and a natural bridge
    to the next session. DOCTRINE §5: "the learner exits with something."
    """
    try:
        from .scheduler import preview_next_session
        preview = preview_next_session(conn, user_id, n=3)
        if preview:
            review_count = sum(1 for p in preview if not p["is_new"])
            new_count = sum(1 for p in preview if p["is_new"])
            words = " · ".join(p["hanzi"] for p in preview)
            parts = []
            if review_count:
                parts.append(f"{review_count} review")
            if new_count:
                parts.append(f"{new_count} new")
            show_fn(display.dim(f"  Coming up: {words} ({', '.join(parts)})"))
    except Exception:
        pass


def _finalize(conn: sqlite3.Connection, state: SessionState,
              show_fn: Callable, input_fn: Callable = None,
              pre_milestones: set = None,
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
        show_fn(f"  Practicing ~{cadence}x/week")

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
        # Lifecycle: drill_abandonment
        try:
            from .marketing_hooks import log_lifecycle_event
            last_type = state.results[-1].get("drill_type", "unknown") if state.results else "unknown"
            log_lifecycle_event("drill_abandonment", user_id=str(user_id), conn=conn,
                                last_drill_type=last_type,
                                completed=state.items_completed,
                                planned=len(state.plan.drills) if state.plan else 0)
        except Exception:
            pass

    # ── HSK progression prompt — actionable, show immediately ──
    next_hsk = db.should_suggest_next_hsk(conn)
    if next_hsk:
        mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
        if mastery:
            max_level = max(mastery.keys())
            pct = mastery[max_level]["pct"]
            show_fn(f"\n  HSK 1-{max_level}: {pct:.0f}% progress.")
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

    # ── Peak moment (Kahneman peak-end rule) ──
    # Find the most notable correct answer this session — an item that
    # was previously difficult but answered correctly today.
    try:
        _show_peak_moment(conn, state, show_fn, user_id)
    except Exception:
        pass

    # ── Stage transitions — top 3 in main flow ──
    transitions = db.get_stage_transitions(conn, state.session_id, user_id=user_id)
    if transitions:
        parts = []
        for t in transitions[:3]:
            from_l = _STAGE_LABELS.get(t["from"], t["from"])
            to_l = _STAGE_LABELS.get(t["to"], t["to"])
            parts.append(f"{t['hanzi']} ({from_l} → {to_l})")
        show_fn(display.dim(f"Strengthened: {', '.join(parts)}"))

    # ── Session details — show automatically ──
    detail_lines = _build_detail_lines(conn, state, cadence, user_id=user_id)
    if detail_lines:
        show_fn("")
        for line in detail_lines:
            show_fn(line)

    # ── Monthly snapshot (every 30 sessions) ──
    if total_sessions > 0 and total_sessions % 30 == 0:
        _show_monthly_snapshot(conn, show_fn, total_sessions, user_id=user_id)

    # ── Real-world task surfacing (relatedness grounding) ──
    if total > 0:
        _show_real_world_task(conn, state, show_fn)

    # ── Zeigarnik preview — show upcoming items to create return anticipation ──
    if total > 0 and not state.early_exit:
        try:
            _show_next_session_preview(conn, show_fn, user_id)
        except Exception:
            pass

    # ── Post-session behavioral nudges (skip on early exit — user wants to stop) ──
    if input_fn and total > 0 and not state.early_exit:
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


def _build_detail_lines(conn, state: SessionState, cadence, user_id: int = 1) -> list[str]:
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

    # Stage transitions — already shown in main _finalize flow (line ~1166),
    # so omit here to avoid duplicate "Strengthened:" lines.

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
    from datetime import datetime

    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions", 0) or 0

    # ── Implementation intention: "When's your next session?" ──
    try:
        resp = input_fn("\n  When's your next session? (e.g. 'tomorrow morning') ").strip()
        if resp and resp.upper() not in ("", "Q", "N"):
            now = datetime.now(UTC).isoformat()
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
