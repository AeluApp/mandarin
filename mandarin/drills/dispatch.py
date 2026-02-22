"""Drill dispatcher: registry, validation, and run_drill entry point."""

import sys
from typing import Optional

from .base import DrillResult, format_scaffold_hint
from .mc import run_mc_drill, run_reverse_mc_drill
from .pinyin import (
    run_ime_drill, run_english_to_pinyin_drill,
    run_hanzi_to_pinyin_drill, run_pinyin_to_hanzi_drill,
)
from .tone import run_tone_drill, TONE_CONTOURS
from .listening import (
    run_listening_gist_drill, run_listening_detail_drill,
    run_listening_tone_drill, run_listening_dictation_drill,
    run_listening_passage_drill, run_dictation_sentence_drill,
)
from .production import (
    run_transfer_drill, run_translation_drill,
    run_sentence_build_drill, run_word_order_drill,
)
from .speaking import run_speaking_drill, _make_replay_input
from .advanced import (
    run_intuition_drill, run_register_choice_drill, run_pragmatic_drill,
    run_slang_exposure_drill, run_measure_word_drill,
    run_particle_disc_drill, run_homophone_drill,
    run_cloze_context_drill, run_synonym_disc_drill,
)


# ── Elaborative interrogation prompts (generation effect) ──────────────

ELABORATIVE_PROMPTS = {
    "mc": "Why does {english} map to this character?",
    "reverse_mc": "What's the radical in {hanzi}? How does it relate to meaning?",
    "tone": "What tone pattern is {pinyin}? Picture the pitch.",
    "ime_type": "What component distinguishes {hanzi} from similar characters?",
    "listening_gist": "What word was the clue to the meaning?",
    "hanzi_to_pinyin": "Which part of {hanzi} hints at the pronunciation?",
    "intuition": "Why does this word order feel natural in Chinese?",
    "measure_word": "What quality of {english} determines its measure word?",
    "translation": "What's the sentence structure pattern here?",
}


# ── Debug validation ──────────────────────────────

def _validate_drill_inputs(item: dict, drill_type: str):
    """Log a warning to stderr if a drill is about to render with suspect data.

    Creates a paper trail for integrity issues without blocking the session.
    """
    hanzi = (item.get("hanzi") or "").strip()
    pinyin = (item.get("pinyin") or "").strip()
    english = (item.get("english") or "").strip()
    item_id = item.get("id", "?")

    warnings = []
    if not hanzi:
        warnings.append("empty hanzi")
    if not pinyin and drill_type in ("ime_type", "tone", "english_to_pinyin", "hanzi_to_pinyin",
                                     "pinyin_to_hanzi", "listening_tone", "listening_dictation"):
        warnings.append(f"empty pinyin (needed for {drill_type})")
    if not english and drill_type in ("mc", "reverse_mc", "listening_gist", "listening_detail",
                                      "english_to_pinyin", "pinyin_to_hanzi"):
        warnings.append(f"empty english (needed for {drill_type})")

    if warnings:
        msg = f"[drill-integrity] item={item_id} type={drill_type}: {', '.join(warnings)}"
        print(msg, file=sys.stderr)


# ── Drill dispatcher ──────────────────────────────

DRILL_REGISTRY = {
    "mc": {"runner": run_mc_drill, "label": "Reading", "requires": {"hanzi", "english"}},
    "reverse_mc": {"runner": run_reverse_mc_drill, "label": "Recognition", "requires": {"hanzi", "english"}},
    "ime_type": {"runner": run_ime_drill, "label": "IME", "requires": {"hanzi", "pinyin"}},
    "tone": {"runner": run_tone_drill, "label": "Tone", "requires": {"hanzi", "pinyin"}},
    "listening_gist": {"runner": run_listening_gist_drill, "label": "Listening", "requires": {"hanzi", "english"}},
    "listening_detail": {"runner": run_listening_detail_drill, "label": "Listening (detail)", "requires": {"hanzi", "english"}},
    "listening_tone": {"runner": run_listening_tone_drill, "label": "Tone ID", "requires": {"hanzi", "pinyin"}},
    "listening_dictation": {"runner": run_listening_dictation_drill, "label": "Dictation", "requires": {"hanzi", "pinyin"}},
    "intuition": {"runner": run_intuition_drill, "label": "Intuition", "requires": {"hanzi", "english"}},
    "english_to_pinyin": {"runner": run_english_to_pinyin_drill, "label": "Pinyin recall", "requires": {"hanzi", "pinyin", "english"}},
    "hanzi_to_pinyin": {"runner": run_hanzi_to_pinyin_drill, "label": "Pinyin reading", "requires": {"hanzi", "pinyin"}},
    "pinyin_to_hanzi": {"runner": run_pinyin_to_hanzi_drill, "label": "Hanzi recall", "requires": {"hanzi", "pinyin", "english"}},
    "register_choice": {"runner": run_register_choice_drill, "label": "Register", "requires": {"hanzi"}},
    "pragmatic": {"runner": run_pragmatic_drill, "label": "Pragmatic", "requires": {"hanzi"}},
    "slang_exposure": {"runner": run_slang_exposure_drill, "label": "Slang", "requires": {"hanzi"}},
    "speaking": {"runner": run_speaking_drill, "label": "Speaking", "requires": {"hanzi", "pinyin"}},
    "transfer": {"runner": run_transfer_drill, "label": "Transfer", "requires": {"hanzi", "english"}},
    "measure_word": {"runner": run_measure_word_drill, "label": "Measure word", "requires": {"hanzi", "english"}},
    "word_order": {"runner": run_word_order_drill, "label": "Word order", "requires": {"hanzi", "english"}},
    "sentence_build": {"runner": run_sentence_build_drill, "label": "Sentence build", "requires": {"hanzi", "english"}},
    "particle_disc": {"runner": run_particle_disc_drill, "label": "Particle", "requires": {"hanzi"}},
    "homophone": {"runner": run_homophone_drill, "label": "Homophone", "requires": {"hanzi"}},
    "translation": {"runner": run_translation_drill, "label": "Translation", "requires": {"hanzi", "english"}},
    "cloze_context": {"runner": run_cloze_context_drill, "label": "Cloze", "requires": {"hanzi"}},
    "synonym_disc": {"runner": run_synonym_disc_drill, "label": "Synonym", "requires": {"hanzi"}},
    "listening_passage": {"runner": run_listening_passage_drill, "label": "Passage", "requires": {"hanzi"}},
    "dictation_sentence": {"runner": run_dictation_sentence_drill, "label": "Sentence dictation", "requires": {"hanzi", "pinyin"}},
}

# Backwards-compatible alias -- keyed to runner functions
DRILL_RUNNERS = {k: v["runner"] for k, v in DRILL_REGISTRY.items()}


def _get_requirement_ref(item: dict, conn, drill_type: str) -> Optional[dict]:
    """Build provenance ref for a drill item."""
    # Supplementary drills without HSK mapping
    if drill_type in ("register_choice", "pragmatic", "slang_exposure"):
        if not item.get("hsk_level"):
            return None

    # Check for linked grammar point
    gp_row = conn.execute("""
        SELECT gp.name, gp.hsk_level FROM content_grammar cg
        JOIN grammar_point gp ON gp.id = cg.grammar_point_id
        WHERE cg.content_item_id = ?
        LIMIT 1
    """, (item["id"],)).fetchone()
    if gp_row:
        return {
            "type": "grammar",
            "name": gp_row["name"],
            "hsk_level": gp_row["hsk_level"],
            "source": "HSK 3.0 Standards",
        }

    # Check for linked skill
    sk_row = conn.execute("""
        SELECT s.name, s.hsk_level FROM content_skill cs
        JOIN skill s ON s.id = cs.skill_id
        WHERE cs.content_item_id = ?
        LIMIT 1
    """, (item["id"],)).fetchone()
    if sk_row:
        return {
            "type": "skill",
            "name": sk_row["name"],
            "hsk_level": sk_row["hsk_level"],
            "source": "HSK 3.0 Standards",
        }

    # Default: vocab provenance
    hsk = item.get("hsk_level")
    if hsk:
        return {
            "type": "vocab",
            "hsk_level": hsk,
            "source": "HSK 3.0 vocabulary list",
        }
    return None


def run_drill(drill_type: str, item: dict, conn, show_fn, input_fn,
              prominent: bool = True, audio_enabled: bool = False,
              show_pinyin: bool = False,
              scaffold_level: str = "none") -> DrillResult:
    """Dispatch to the appropriate drill runner."""
    _validate_drill_inputs(item, drill_type)
    runner = DRILL_RUNNERS.get(drill_type)
    if not runner:
        raise ValueError(f"Unknown drill type: {drill_type}")
    # Wrap input_fn with R-key audio replay for all drills
    wrapped_input = _make_replay_input(input_fn, show_fn, item, audio_enabled)
    if audio_enabled:
        show_fn("  [dim](R to replay audio)[/dim]")

    # Gradient scaffold: compute effective show_pinyin from scaffold_level
    effective_show_pinyin = show_pinyin
    if scaffold_level and scaffold_level != "none":
        hint = format_scaffold_hint(item.get("pinyin", ""), scaffold_level)
        if hint:
            effective_show_pinyin = True
            # Wrap show_fn to inject scaffold hint for MC-type drills
            original_show = show_fn
            _hint_shown = [False]
            def scaffold_show_fn(text, **kwargs):
                original_show(text, **kwargs)
                if not _hint_shown[0] and "hanzi" in text.lower() or "bright_magenta" in text:
                    original_show(f"  [dim]{hint}[/dim]")
                    _hint_shown[0] = True
            # Only use scaffold_show for drills that show hanzi
            if drill_type in ("mc", "reverse_mc", "hanzi_to_pinyin", "translation"):
                show_fn = scaffold_show_fn

    # Pass audio_enabled to drills that support it
    if drill_type in ("listening_gist", "listening_detail", "listening_tone",
                      "listening_dictation", "listening_passage",
                      "dictation_sentence", "tone", "speaking"):
        result = runner(item, conn, show_fn, wrapped_input, prominent=prominent,
                       audio_enabled=audio_enabled)
    elif drill_type in ("mc", "reverse_mc", "hanzi_to_pinyin"):
        result = runner(item, conn, show_fn, wrapped_input, prominent=prominent,
                       show_pinyin=effective_show_pinyin)
    else:
        result = runner(item, conn, show_fn, wrapped_input, prominent=prominent)
    # Attach provenance
    result.requirement_ref = _get_requirement_ref(item, conn, drill_type)
    return result
