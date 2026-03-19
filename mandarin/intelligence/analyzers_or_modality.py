"""Operations Research analyzers for non-core learning modalities.

Applies OR models (SPC control charts, queueing theory, process capability)
to reading passages, listening comprehension, conversation, grammar, and
media — features that the core OR analyzers treat as a single aggregate.
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)

# Modality groups: drill_types that belong to each modality
_MODALITY_DRILL_TYPES = {
    "reading": ("mc", "reverse_mc", "reading_comp"),
    "listening": ("listening_gist", "listening_detail", "listening_tone",
                  "listening_dictation", "listening_passage"),
    "conversation": ("dialogue",),
    "grammar": ("intuition", "complement", "ba_bei", "error_correction",
                "measure_word", "measure_word_cloze", "measure_word_disc"),
    "media": ("media_comprehension",),
}


# ── 1. Modality-specific SPC ────────────────────────────────────────


def _analyze_modality_spc(conn) -> list[dict]:
    """SPC control charts per modality — detect quality shifts invisible to system-wide SPC."""
    findings = []

    try:
        from ..quality.spc import compute_control_limits, detect_out_of_control
    except ImportError:
        return findings

    for modality, drill_types in _MODALITY_DRILL_TYPES.items():
        try:
            placeholders = ",".join("?" * len(drill_types))
            rows = _safe_query_all(conn, f"""
                SELECT date(reviewed_at) as day,
                       AVG(CAST(correct AS REAL)) as daily_accuracy,
                       COUNT(*) as n
                FROM review_event
                WHERE drill_type IN ({placeholders})
                  AND reviewed_at >= datetime('now', '-30 days')
                GROUP BY day
                HAVING n >= 3
                ORDER BY day
            """, list(drill_types))

            if not rows or len(rows) < 14:
                continue  # Not enough data for SPC

            data = [r["daily_accuracy"] for r in rows]
            limits = compute_control_limits(data)
            violations = detect_out_of_control(data, limits)

            if violations:
                rule1 = [v for v in violations if v.get("rule") == 1]
                if rule1:
                    findings.append(_finding(
                        "drill_quality", "high",
                        f"{modality.title()} accuracy: SPC 3σ breach detected",
                        f"{modality.title()} drill accuracy has {len(rule1)} "
                        f"out-of-control point(s) (Rule 1: beyond 3σ). "
                        f"Control limits: UCL={limits['ucl']:.3f}, "
                        f"CL={limits['cl']:.3f}, LCL={limits['lcl']:.3f}. "
                        f"This may be invisible in system-wide SPC.",
                        f"Investigate {modality} drill quality. Check if content "
                        f"difficulty changed, new drill types were added, or "
                        f"user mix shifted.",
                        f"Run modality-specific SPC for {modality} drills.",
                        f"Modality-level quality issue hidden in aggregate data.",
                        ["mandarin/drills/", "mandarin/scheduler.py"],
                    ))
        except Exception as e:
            logger.debug("Modality SPC for %s failed: %s", modality, e)

    return findings


# ── 2. Cross-modality queue balance ─────────────────────────────────


def _analyze_modality_queue_balance(conn) -> list[dict]:
    """Detect imbalanced review queues across modalities."""
    findings = []

    try:
        # Get queue depth per modality from progress table
        rows = _safe_query_all(conn, """
            SELECT
                CASE
                    WHEN ci.drill_type IN ('mc', 'reverse_mc') THEN 'vocabulary'
                    WHEN ci.drill_type LIKE 'listening%' THEN 'listening'
                    WHEN ci.drill_type = 'dialogue' THEN 'conversation'
                    WHEN ci.drill_type IN ('intuition', 'complement', 'ba_bei',
                         'error_correction', 'measure_word') THEN 'grammar'
                    WHEN ci.drill_type = 'media_comprehension' THEN 'media'
                    ELSE 'other'
                END as modality_group,
                COUNT(*) as queue_depth
            FROM progress p
            JOIN content_item ci ON p.content_item_id = ci.id
            WHERE p.next_review <= datetime('now')
              AND p.mastery_stage NOT IN ('durable')
            GROUP BY modality_group
            HAVING queue_depth > 0
        """)

        if not rows or len(rows) < 2:
            return findings

        queues = {r["modality_group"]: r["queue_depth"] for r in rows}
        max_q = max(queues.values())
        min_q = min(queues.values())

        if max_q > 0 and min_q > 0 and max_q / min_q > 3:
            heavy = max(queues, key=queues.get)
            light = min(queues, key=queues.get)
            findings.append(_finding(
                "scheduler_audit", "medium",
                f"Queue imbalance: {heavy} ({max_q}) vs {light} ({min_q}) — {max_q/min_q:.1f}x ratio",
                f"Review queue depths by modality: {queues}. A {max_q/min_q:.1f}x "
                f"imbalance suggests the scheduler is over-weighting {heavy} "
                f"at the expense of {light}.",
                f"Review scheduler modality weights. Consider capping {heavy} "
                f"queue or boosting {light} scheduling priority.",
                f"Check _pick_modality_distribution() in scheduler.py.",
                "Queue imbalance causes uneven skill development across modalities.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Queue balance analyzer failed: %s", e)

    return findings


# ── 3. Reading difficulty calibration ────────────────────────────────


def _analyze_reading_difficulty_calibration(conn) -> list[dict]:
    """Check if reading passage difficulty matches learner level (Nation vocab profile)."""
    findings = []

    try:
        stats = _safe_query(conn, """
            SELECT COUNT(*) as total,
                   AVG(CAST(questions_correct AS REAL) / NULLIF(questions_total, 0)) as avg_score,
                   AVG(words_looked_up) as avg_lookups
            FROM reading_progress
            WHERE completed_at >= datetime('now', '-30 days')
              AND questions_total > 0
        """)

        if not stats or not stats["total"] or stats["total"] < 5:
            return findings

        avg_score = stats["avg_score"] or 0
        avg_lookups = stats["avg_lookups"] or 0

        # Nation (2006): optimal comprehension at 95-98% known vocabulary
        # Score < 50% = too hard; lookups > 10 = vocabulary gap
        if avg_score < 0.5:
            findings.append(_finding(
                "drill_quality", "medium",
                f"Reading too hard: avg comprehension {avg_score*100:.0f}% (target: 70%+)",
                f"Average reading comprehension across {stats['total']} sessions is "
                f"{avg_score*100:.0f}%, with {avg_lookups:.1f} lookups per passage. "
                f"Nation (2006): comprehension below 50% signals vocabulary coverage "
                f"below the 85% intensive reading threshold.",
                "Reduce reading passage difficulty or ensure passages match "
                "the learner's current HSK level more tightly.",
                "Check _pick_reading_block() vocabulary coverage thresholds.",
                "Passages too hard for current level reduce reading engagement.",
                ["mandarin/scheduler.py"],
            ))

        if avg_lookups > 10:
            findings.append(_finding(
                "drill_quality", "low",
                f"High reading lookup rate: {avg_lookups:.1f} lookups/passage",
                f"Learners look up {avg_lookups:.1f} words per passage on average. "
                f"More than 10 lookups suggests vocabulary coverage is below "
                f"the 85% threshold for comfortable reading.",
                "Consider filtering passages to higher coverage (90%+) or "
                "pre-teaching key vocabulary before the passage.",
                "Review vocabulary coverage computation in scheduler reading selection.",
                "High lookup rate signals poor vocabulary-passage match.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Reading calibration analyzer failed: %s", e)

    return findings


# ── 4. Listening process capability ──────────────────────────────────


def _analyze_listening_process_capability(conn) -> list[dict]:
    """Cpk for listening comprehension — is the process capable?"""
    findings = []

    try:
        rows = _safe_query_all(conn, """
            SELECT comprehension_score, replays, playback_speed
            FROM listening_progress
            WHERE completed_at >= datetime('now', '-30 days')
              AND comprehension_score IS NOT NULL
        """)

        if not rows or len(rows) < 10:
            return findings

        scores = [r["comprehension_score"] for r in rows if r["comprehension_score"] is not None]
        replays = [r["replays"] or 0 for r in rows]

        if not scores:
            return findings

        import statistics
        mean_score = statistics.mean(scores)
        std_score = statistics.stdev(scores) if len(scores) > 1 else 0.1

        # Cpk: target = 0.7, USL = 1.0, LSL = 0.4
        target = 0.7
        usl, lsl = 1.0, 0.4
        cpu = (usl - mean_score) / (3 * max(std_score, 0.01))
        cpl = (mean_score - lsl) / (3 * max(std_score, 0.01))
        cpk = min(cpu, cpl)

        avg_replays = statistics.mean(replays)

        if cpk < 1.0:
            findings.append(_finding(
                "drill_quality", "medium",
                f"Listening Cpk={cpk:.2f} (target: 1.0+), avg replays: {avg_replays:.1f}",
                f"Listening comprehension process capability index Cpk={cpk:.2f}. "
                f"Mean score: {mean_score:.2f}, std: {std_score:.2f}. "
                f"Average replays per session: {avg_replays:.1f}. "
                f"Cpk < 1.0 means the process cannot reliably produce "
                f"acceptable comprehension outcomes.",
                "Reduce listening difficulty: slower default playback, "
                "simpler passages, or more vocabulary pre-teaching.",
                "Review listening passage selection and playback_speed defaults.",
                "Low Cpk means listening is unreliably difficult.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Listening Cpk analyzer failed: %s", e)

    return findings


# ── 5. Conversation throughput ───────────────────────────────────────


def _analyze_conversation_throughput(conn) -> list[dict]:
    """Service channel analysis for conversation drills."""
    findings = []

    try:
        stats = _safe_query(conn, """
            SELECT COUNT(*) as attempts,
                   SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as completions,
                   AVG(score) as avg_score,
                   SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) as abandoned
            FROM review_event
            WHERE drill_type = 'dialogue'
              AND reviewed_at >= datetime('now', '-30 days')
        """)

        if not stats or not stats["attempts"] or stats["attempts"] < 5:
            return findings

        attempts = stats["attempts"]
        abandoned = stats["abandoned"] or 0
        abandonment_rate = abandoned / attempts * 100
        avg_score = stats["avg_score"]

        if abandonment_rate > 40:
            findings.append(_finding(
                "ux", "high",
                f"Conversation abandonment: {abandonment_rate:.0f}% ({abandoned}/{attempts})",
                f"Conversation drills have a {abandonment_rate:.0f}% abandonment rate. "
                f"Average score on completed: {avg_score:.2f}. "
                f"In service channel terms, this is an unacceptable "
                f"service failure rate.",
                "Investigate why learners abandon conversations. Common causes: "
                "too difficult, unclear prompts, or anxiety about production.",
                "Review conversation difficulty and prompt clarity.",
                "High abandonment signals a broken conversation experience.",
                ["mandarin/conversation.py", "mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Conversation throughput analyzer failed: %s", e)

    return findings


# ── 6. Grammar mastery velocity ──────────────────────────────────────


def _analyze_grammar_mastery_velocity(conn) -> list[dict]:
    """Compare grammar mastery velocity to vocabulary mastery velocity."""
    findings = []

    try:
        # Grammar: average attempts to reach mastery_score >= 0.7
        grammar_stats = _safe_query(conn, """
            SELECT AVG(drill_attempts) as avg_attempts,
                   COUNT(*) as total_points,
                   SUM(CASE WHEN mastery_score >= 0.7 THEN 1 ELSE 0 END) as mastered
            FROM grammar_progress
            WHERE drill_attempts > 0
        """)

        # Vocabulary: average attempts to reach stable mastery
        vocab_stats = _safe_query(conn, """
            SELECT AVG(total_attempts) as avg_attempts,
                   COUNT(*) as total_items,
                   SUM(CASE WHEN mastery_stage IN ('stable', 'durable') THEN 1 ELSE 0 END) as mastered
            FROM progress
            WHERE total_attempts > 0
        """)

        if (not grammar_stats or not grammar_stats["total_points"]
                or grammar_stats["total_points"] < 5):
            return findings
        if (not vocab_stats or not vocab_stats["total_items"]
                or vocab_stats["total_items"] < 10):
            return findings

        grammar_attempts = grammar_stats["avg_attempts"] or 0
        vocab_attempts = vocab_stats["avg_attempts"] or 0

        if vocab_attempts > 0 and grammar_attempts > vocab_attempts * 2:
            grammar_mastery_pct = (
                (grammar_stats["mastered"] or 0) / grammar_stats["total_points"] * 100
            )
            findings.append(_finding(
                "curriculum", "medium",
                f"Grammar mastery 2x+ slower than vocabulary ({grammar_attempts:.0f} vs {vocab_attempts:.0f} attempts)",
                f"Grammar points require {grammar_attempts:.0f} drill attempts "
                f"on average vs {vocab_attempts:.0f} for vocabulary items. "
                f"Grammar mastery rate: {grammar_mastery_pct:.0f}%. "
                f"This suggests grammar integration (DOCTRINE §1: Focus on "
                f"Form) may not be working — grammar drills may be too "
                f"isolated from context.",
                "Review grammar drill integration. DOCTRINE §1 requires "
                "grammar introduced through encountered sentences, not "
                "in isolation. Consider more context-embedded grammar practice.",
                "Check grammar scheduling and context integration in scheduler.py.",
                "Slow grammar mastery signals weak context integration.",
                ["mandarin/scheduler.py", "mandarin/drills/"],
            ))

    except Exception as e:
        logger.debug("Grammar velocity analyzer failed: %s", e)

    return findings


ANALYZERS = [
    _analyze_modality_spc,
    _analyze_modality_queue_balance,
    _analyze_reading_difficulty_calibration,
    _analyze_listening_process_capability,
    _analyze_conversation_throughput,
    _analyze_grammar_mastery_velocity,
]
