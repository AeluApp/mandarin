"""Behavioral economics analyzers for non-core learning modalities.

Extends behavioral econ coverage (nudges, choice architecture, progress
framing) to reading, listening, conversation, grammar, and media —
features where the core behavioral econ analyzers have zero coverage.
"""

from __future__ import annotations

import os
import re
import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query_all

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_MANDARIN_PKG = os.path.join(_PROJECT_ROOT, "mandarin")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _all_source() -> str:
    """Read key source files for pattern detection."""
    parts = []
    for f in ["runner.py", "scheduler.py", "web/dashboard_routes.py",
              "web/session_routes.py", "web/static/app.js"]:
        parts.append(_read(os.path.join(_MANDARIN_PKG, f)))
    return "\n".join(parts)


# ── 1. Modality-specific progress framing ────────────────────────────


def _analyze_modality_progress_framing(conn) -> list[dict]:
    """Check for capability-framed progress messages per modality.

    DOCTRINE §6: 'Show what the learner can do.' Current capability messages
    only reference vocabulary counts ('You can now recognize 100 words').
    No messages for reading ('You've read 5 passages this month'), listening
    ('You can follow a 2-minute conversation'), or grammar mastery.
    """
    findings = []
    source = _all_source()

    modality_messages = {
        "reading": (
            r"(?:passage|reading|read\s+\d|comprehension\s+(?:score|improved))",
            "No reading progress framing (e.g., 'You've read X passages this month')",
        ),
        "listening": (
            r"(?:listening\s+(?:score|improved|comprehension)|follow\s+a\s+\d-minute|"
            r"ear\s+(?:trained|improving))",
            "No listening progress framing (e.g., 'You can now follow a 2-minute conversation')",
        ),
        "conversation": (
            r"(?:conversation|dialogue|spoken|speaking\s+(?:improved|progress))",
            "No conversation progress framing",
        ),
        "grammar": (
            r"(?:grammar\s+(?:mastered|understood|pattern)|sentence\s+structure)",
            "No grammar mastery framing",
        ),
    }

    missing = []
    for modality, (pattern, _msg) in modality_messages.items():
        if not re.search(pattern, source, re.IGNORECASE):
            missing.append(modality)

    if missing:
        findings.append(_finding(
            "behavioral_econ", "medium",
            f"No capability-framed progress for: {', '.join(missing)}",
            f"DOCTRINE §6 requires progress framed as capability. Current "
            f"messages only cover vocabulary counts. Missing modality-specific "
            f"progress framing for: {', '.join(missing)}. Learners in these "
            f"modalities cannot see their improvement.",
            "Add capability messages per modality. Examples: "
            "'You've read 5 passages this month — up from 2 last month.' "
            "'Your listening comprehension improved 15% this week.'",
            "Add modality-specific milestones to dashboard_routes.py _compute_milestones().",
            "Missing modality progress framing leaves learners without feedback.",
            ["mandarin/web/dashboard_routes.py", "mandarin/runner.py"],
        ))

    return findings


# ── 2. Modality exploration nudge ────────────────────────────────────


def _analyze_modality_exploration_nudge(conn) -> list[dict]:
    """Check if the app nudges learners to try underused modalities.

    Behavioral economics: people stick to defaults. Without a nudge,
    learners who start with drills may never discover reading or listening.
    """
    findings = []

    try:
        # Find users with 10+ sessions who've never tried reading or listening
        unexplored = _safe_query_all(conn, """
            SELECT u.id,
                   (SELECT COUNT(*) FROM reading_progress rp WHERE rp.user_id = u.id) as reading_count,
                   (SELECT COUNT(*) FROM listening_progress lp WHERE lp.user_id = u.id) as listening_count,
                   (SELECT COUNT(*) FROM session_log sl WHERE sl.user_id = u.id AND sl.items_completed > 0) as sessions
            FROM user u
            WHERE u.is_admin = 0
              AND (SELECT COUNT(*) FROM session_log sl WHERE sl.user_id = u.id AND sl.items_completed > 0) >= 10
        """)

        if not unexplored:
            return findings

        total_eligible = len(unexplored)
        no_reading = sum(1 for u in unexplored if (u["reading_count"] or 0) == 0)
        no_listening = sum(1 for u in unexplored if (u["listening_count"] or 0) == 0)

        gaps = []
        if total_eligible > 0:
            if no_reading / total_eligible > 0.3:
                gaps.append(f"reading ({no_reading}/{total_eligible} = {no_reading/total_eligible*100:.0f}%)")
            if no_listening / total_eligible > 0.3:
                gaps.append(f"listening ({no_listening}/{total_eligible} = {no_listening/total_eligible*100:.0f}%)")

        if gaps:
            # Check if any nudge exists for modality exploration
            source = _all_source()
            has_nudge = bool(re.search(
                r"(?:try\s+reading|try\s+listening|explore.*modali|"
                r"modality.*nudge|ready\s+to\s+try)",
                source, re.IGNORECASE,
            ))

            if not has_nudge:
                findings.append(_finding(
                    "behavioral_econ", "medium",
                    f"No exploration nudge for underused modalities: {', '.join(gaps)}",
                    f"Among users with 10+ sessions: {', '.join(gaps)} have "
                    f"never engaged. No nudge exists to encourage exploration. "
                    f"Default bias keeps learners in the core drill loop.",
                    "Add a one-time nudge after session 10: 'You've been "
                    "building vocabulary — ready to try reading a short "
                    "passage?' Register via nudge_registry with DOCTRINE "
                    "ethics check.",
                    "Register a modality exploration nudge in nudge_registry.py.",
                    "Default bias without nudges means most users miss non-core features.",
                    ["mandarin/nudge_registry.py", "mandarin/runner.py"],
                ))

    except Exception as e:
        logger.debug("Modality exploration nudge analyzer failed: %s", e)

    return findings


# ── 3. Listening speed choice architecture ───────────────────────────


def _analyze_listening_choice_architecture(conn) -> list[dict]:
    """Check if listening offers speed/difficulty choices (Thaler & Sunstein)."""
    findings = []

    source = _all_source()
    scheduler = _read(os.path.join(_MANDARIN_PKG, "scheduler.py"))

    # Check for hardcoded playback speed
    has_speed_choice = bool(re.search(
        r"preferred_playback_speed|playback_speed_pref|speed_selector|"
        r"listening_speed_choice",
        source + scheduler, re.IGNORECASE,
    ))

    has_hardcoded_speed = bool(re.search(
        r"playback_speed\s*=\s*1\.0", scheduler,
    ))

    if has_hardcoded_speed and not has_speed_choice:
        findings.append(_finding(
            "behavioral_econ", "low",
            "Listening playback speed hardcoded at 1.0x — no choice architecture",
            "Listening blocks default to 1.0x speed with no learner choice. "
            "Thaler & Sunstein: offering a default with alternatives "
            "increases autonomy and satisfaction. DOCTRINE §7: 'Adapt what "
            "matters.' Listening speed matters.",
            "Add a preferred_playback_speed to learner_profile. Default 1.0x "
            "but offer 0.75x/1.0x/1.25x at listening block start.",
            "Add playback speed choice to listening UI and learner_profile.",
            "Hardcoded speed ignores learner difficulty variation.",
            ["mandarin/scheduler.py"],
        ))

    return findings


# ── 4. Reading depth choice ──────────────────────────────────────────


def _analyze_reading_choice_architecture(conn) -> list[dict]:
    """Check if reading offers depth choices (skim vs detailed)."""
    findings = []

    source = _all_source()

    has_reading_choice = bool(re.search(
        r"(?:reading_mode|skim|detailed|quick_read|deep_read|reading_depth|"
        r"reading.*preference)",
        source, re.IGNORECASE,
    ))

    if not has_reading_choice:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No reading depth choice architecture",
            "All reading passages are presented identically. Choice "
            "architecture would let learners pick 'quick read' (questions "
            "only) vs 'deep read' (vocabulary lookup + questions + re-read). "
            "DOCTRINE §7: 'Adapt what matters.'",
            "Consider offering a reading mode selector. This is lower "
            "priority than listening speed choice.",
            "Add reading mode choice to session flow.",
            "One-size-fits-all reading ignores learner goals.",
            ["mandarin/scheduler.py", "mandarin/web/session_routes.py"],
        ))

    return findings


# ── 5. Conversation encouragement ────────────────────────────────────


def _analyze_conversation_encouragement(conn) -> list[dict]:
    """Check for DOCTRINE-compliant encouragement in conversation drills.

    Conversations are production tasks — inherently harder than recognition.
    DOCTRINE §3: 'Normalize error.' Conversation drills should include
    language like 'Conversations are the hardest part — every attempt builds
    fluency.' Without this, learners may feel conversation failure is personal.
    """
    findings = []

    source = _all_source()
    conv_file = _read(os.path.join(_MANDARIN_PKG, "conversation.py"))

    has_encouragement = bool(re.search(
        r"(?:conversation.*hard|speaking.*challenge|production.*difficult|"
        r"every\s+attempt|normal.*(?:to|for)\s+(?:struggle|find)|"
        r"most\s+learners\s+find\s+conversation)",
        source + conv_file, re.IGNORECASE,
    ))

    if not has_encouragement:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No difficulty-normalizing language for conversation drills",
            "Conversation drills are production tasks — inherently harder "
            "than recognition drills. DOCTRINE §3: 'Normalize error.' No "
            "language found that normalizes conversation difficulty (e.g., "
            "'Conversations are the hardest part — every attempt builds "
            "fluency.').",
            "Add encouraging framing before or after conversation drills. "
            "Keep it DOCTRINE-compliant: factual, not saccharine.",
            "Add difficulty-normalizing copy to conversation drill flow.",
            "Without normalization, learners may blame themselves for conversation difficulty.",
            ["mandarin/conversation.py", "mandarin/runner.py"],
        ))

    return findings


# ── 6. Grammar insight nudge ─────────────────────────────────────────


def _analyze_grammar_insight_nudge(conn) -> list[dict]:
    """Check if grammar explanations follow DOCTRINE §1: 'Explanation follows noticing.'

    The behavioral economics principle: show the grammar rule after the
    learner has encountered the pattern 3+ times. If grammar is explained
    before encountering it in context, DOCTRINE §1 is violated.
    """
    findings = []

    source = _all_source()

    # Check if there's a mechanism that gates grammar explanation on prior encounters
    has_encounter_gate = bool(re.search(
        r"(?:encounter.*count|seen.*(?:3|three)\+?\s*times|"
        r"grammar.*after.*noticing|explain.*after.*encounter|"
        r"focus[_\s]on[_\s]form.*gate)",
        source, re.IGNORECASE,
    ))

    if not has_encounter_gate:
        findings.append(_finding(
            "behavioral_econ", "medium",
            "Grammar explanation not gated on prior encounters (DOCTRINE §1)",
            "DOCTRINE §1: 'Explanation follows noticing, not the reverse.' "
            "No code found that gates grammar explanation on the learner "
            "having encountered the pattern 3+ times in context. Grammar "
            "may be presented in isolation, violating Focus on Form (Long, "
            "1991).",
            "Gate grammar drills on prior contextual encounters: only "
            "show grammar explanation after the learner has seen the "
            "pattern in 3+ reading/listening contexts.",
            "Add encounter count check before grammar drill scheduling.",
            "Premature grammar explanation undermines implicit acquisition.",
            ["mandarin/scheduler.py", "mandarin/drills/"],
        ))

    return findings


ANALYZERS = [
    _analyze_modality_progress_framing,
    _analyze_modality_exploration_nudge,
    _analyze_listening_choice_architecture,
    _analyze_reading_choice_architecture,
    _analyze_conversation_encouragement,
    _analyze_grammar_insight_nudge,
]
