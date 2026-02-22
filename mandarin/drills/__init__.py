"""Drill type implementations — sub-module package.

Re-exports all public names so that existing imports like
``from mandarin.drills import DrillResult`` continue to work.
"""

# ── base ──────────────────────────────
from .base import (
    DrillResult,
    cause_to_error_type,
    check_confidence_input,
    classify_error_cause,
    elaborate_error,
    format_hanzi,
    format_hanzi_inline,
    format_hanzi_option,
    format_scaffold_hint,
    HANZI_STYLES,
    TONE_DESCRIPTIONS,
)

# ── hints ──────────────────────────────
from .hints import (
    get_hanzi_hint,
)

# ── mc ──────────────────────────────
from .mc import (
    generate_mc_options,
    run_mc_drill,
    run_reverse_mc_drill,
)

# ── pinyin ──────────────────────────────
from .pinyin import (
    run_ime_drill,
    run_english_to_pinyin_drill,
    run_hanzi_to_pinyin_drill,
    run_pinyin_to_hanzi_drill,
    marked_to_numbered,
    strip_tones,
    normalize_pinyin,
    TONE_MARK_TO_NUM,
    TONE_NUM_TO_MARK,
)

# ── tone ──────────────────────────────
from .tone import (
    run_tone_drill,
    TONE_CONTOURS,
)

# ── listening ──────────────────────────────
from .listening import (
    run_listening_gist_drill,
    run_listening_detail_drill,
    run_listening_tone_drill,
    run_listening_dictation_drill,
    run_listening_passage_drill,
    run_dictation_sentence_drill,
    generate_detail_question,
)

# ── production ──────────────────────────────
from .production import (
    run_transfer_drill,
    run_translation_drill,
    run_sentence_build_drill,
    run_word_order_drill,
    char_overlap_score,
)

# ── speaking ──────────────────────────────
from .speaking import (
    run_speaking_drill,
)

# ── advanced ──────────────────────────────
from .advanced import (
    run_intuition_drill,
    run_register_choice_drill,
    run_pragmatic_drill,
    run_slang_exposure_drill,
    run_measure_word_drill,
    run_particle_disc_drill,
    run_homophone_drill,
    run_cloze_context_drill,
    run_synonym_disc_drill,
)

# ── dispatch ──────────────────────────────
from .dispatch import (
    DRILL_REGISTRY,
    DRILL_RUNNERS,
    run_drill,
    ELABORATIVE_PROMPTS,
)
