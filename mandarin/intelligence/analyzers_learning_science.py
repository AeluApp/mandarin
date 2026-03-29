"""Learning science analyzers for non-core modalities.

Applies academic research findings to reading, listening, conversation,
grammar, and media features. Each analyzer references specific research
and checks whether aelu's implementation follows the evidence.

References:
  - Krashen (2004): Extensive reading, narrow listening, comprehensible input
  - Nation (2006): Vocabulary coverage thresholds for reading
  - Swain (1985, 2005): Pushed output / comprehensible output hypothesis
  - Long (1991): Focus on Form — grammar through meaning-focused interaction
  - Rohrer & Taylor (2007): Interleaving across categories for retention
  - Bjork (1994): Desirable difficulties for long-term learning
  - Gilmore (2007): Authentic materials for pragmatic competence
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)


# ── 1. Extensive Reading (Krashen 2004, Nation 2006) ─────────────────


def _analyze_extensive_reading(conn) -> list[dict]:
    """Check if reading passages meet extensive reading standards.

    Krashen (2004): Extensive reading requires high vocabulary coverage
    (98%+ known words) so learners read for pleasure and meaning, not
    decoding. Nation (2006): 98% coverage = extensive, 85-95% = intensive.

    The scheduler's current i+1 targets 85-95% coverage — this is
    intensive reading, which is fine for learning but insufficient for
    developing reading fluency. Both modes should be available.
    """
    findings = []

    try:
        # Check reading passage difficulty distribution
        stats = _safe_query(conn, """
            SELECT COUNT(*) as total,
                   AVG(words_looked_up) as avg_lookups,
                   AVG(CAST(questions_correct AS REAL) / NULLIF(questions_total, 0)) as avg_score
            FROM reading_progress
            WHERE completed_at >= datetime('now', '-30 days')
              AND questions_total > 0
        """)

        if not stats or not stats["total"] or stats["total"] < 3:
            return findings

        avg_lookups = stats["avg_lookups"] or 0

        # If average lookups > 5, passages are in intensive range (too hard for extensive)
        # Extensive reading: learners should know 98%+ of words = near-zero lookups
        if avg_lookups > 5:
            findings.append(_finding(
                "learning_science", "medium",
                f"All reading is intensive — no extensive reading mode (avg {avg_lookups:.1f} lookups)",
                f"Average {avg_lookups:.1f} word lookups per passage indicates "
                f"all passages are in the intensive reading range (85-95% "
                f"coverage). Krashen (2004): extensive reading (98%+ coverage, "
                f"near-zero lookups) develops reading fluency and vocabulary "
                f"acquisition through pleasure reading. Nation (2006) confirms "
                f"the 98% threshold. Currently aelu only offers intensive reading.",
                "Add an extensive reading mode: passages where the learner "
                "knows 98%+ of vocabulary. These should be easy, fast, and "
                "pleasurable — building reading fluency, not testing comprehension.",
                "Add extensive reading passage selection with 98%+ coverage threshold.",
                "Without extensive reading, learners practice decoding but not fluency.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Extensive reading analyzer failed: %s", e)

    return findings


# ── 2. Narrow Listening (Krashen) ────────────────────────────────────


def _analyze_narrow_listening(conn) -> list[dict]:
    """Check if listening follows Krashen's narrow listening principle.

    Krashen: narrow listening (repeated exposure to same topic/speaker)
    builds comprehension faster than varied listening. Topical grouping
    provides contextual scaffolding that makes comprehension easier.
    """
    findings = []

    try:
        # Check if listening passages show topical grouping
        # If consecutive listening sessions use very different passages,
        # there's no narrow listening effect
        sessions = _safe_query_all(conn, """
            SELECT passage_id, completed_at
            FROM listening_progress
            WHERE completed_at >= datetime('now', '-30 days')
            ORDER BY completed_at
        """)

        if not sessions or len(sessions) < 5:
            return findings

        # Check for repeated passage_ids (narrow listening = some repetition)
        passage_ids = [s["passage_id"] for s in sessions]
        unique_passages = len(set(passage_ids))
        total_sessions = len(passage_ids)

        # If every session uses a different passage, there's no narrow listening
        if unique_passages == total_sessions:
            findings.append(_finding(
                "learning_science", "low",
                "No narrow listening: every session uses a unique passage",
                f"{total_sessions} listening sessions used {unique_passages} "
                f"unique passages — zero repetition. Krashen's narrow "
                f"listening research shows repeated exposure to the same "
                f"topic/speaker builds comprehension faster than varied "
                f"listening. Some passage revisiting or topical clustering "
                f"would improve listening skill acquisition.",
                "Group listening passages by topic. Allow re-listening to "
                "previously heard passages at higher speed. Consider a "
                "'listening series' feature with connected episodes.",
                "Add topical grouping or passage revisiting to listening selection.",
                "Varied-only listening misses the narrow listening benefit.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Narrow listening analyzer failed: %s", e)

    return findings


# ── 3. Pushed Output (Swain 1985, 2005) ──────────────────────────────


def _analyze_pushed_output(conn) -> list[dict]:
    """Check if conversation drills push learners to produce novel language.

    Swain's comprehensible output hypothesis: learners must produce
    language (not just comprehend it) to develop fluency. Production
    should be challenging — high success rates (>85%) may indicate
    learners are selecting from options rather than generating output.
    """
    findings = []

    try:
        conv_stats = _safe_query(conn, """
            SELECT AVG(score) as avg_score,
                   COUNT(*) as attempts,
                   SUM(CASE WHEN score >= 0.9 THEN 1 ELSE 0 END) as high_score_count
            FROM review_event
            WHERE drill_type = 'dialogue'
              AND reviewed_at >= datetime('now', '-30 days')
              AND score IS NOT NULL
        """)

        if not conv_stats or not conv_stats["attempts"] or conv_stats["attempts"] < 10:
            return findings

        avg_score = conv_stats["avg_score"] or 0
        high_pct = (conv_stats["high_score_count"] or 0) / conv_stats["attempts"] * 100

        # Swain: production should be challenging. 0.6-0.8 success rate
        # is the sweet spot for pushed output.
        if avg_score > 0.85:
            findings.append(_finding(
                "learning_science", "low",
                f"Conversation may not push output enough (avg score {avg_score:.2f}, {high_pct:.0f}% score ≥0.9)",
                f"Average conversation score is {avg_score:.2f} with "
                f"{high_pct:.0f}% of attempts scoring ≥0.9. Swain (1985, "
                f"2005): pushed output theory suggests production should be "
                f"challenging — a 0.6-0.8 success rate maximizes learning. "
                f"Scores above 0.85 may indicate learners are selecting "
                f"from easy options rather than generating novel output.",
                "Increase conversation difficulty: require more open-ended "
                "responses, reduce option-based answers, or scaffold toward "
                "free production at higher mastery levels.",
                "Review conversation drill format for production vs. selection balance.",
                "Too-easy conversations don't develop productive fluency.",
                ["mandarin/conversation.py"],
            ))

    except Exception as e:
        logger.debug("Pushed output analyzer failed: %s", e)

    return findings


# ── 4. Focus on Form Enforcement (Long 1991) ────────────────────────


def _analyze_focus_on_form(conn) -> list[dict]:
    """Check if grammar is introduced through context, not isolation.

    Long (1991): Focus on Form draws attention to form when it arises
    naturally in meaning-focused input. DOCTRINE §1 explicitly requires
    this: 'Every grammar point is introduced through a sentence the
    learner has already encountered.'

    Check if grammar_progress entries are preceded by contextual exposure
    (reading/review events containing the same grammar pattern).
    """
    findings = []

    try:
        # Check if content_grammar linking table exists and is populated
        grammar_items = _safe_scalar(conn, """
            SELECT COUNT(*) FROM content_grammar
        """, default=0)

        if grammar_items == 0:
            findings.append(_finding(
                "learning_science", "medium",
                "No content-grammar linkage for Focus on Form",
                "The content_grammar table is empty — grammar points are "
                "not linked to the content items where they naturally appear. "
                "Long (1991) Focus on Form requires grammar to arise from "
                "meaning-focused input, not isolation. DOCTRINE §1 mandates "
                "this. Without linkage, the system cannot enforce contextual "
                "grammar introduction.",
                "Populate content_grammar with links between content items "
                "and their grammar patterns. This enables Focus on Form "
                "enforcement in the scheduler.",
                "Populate content_grammar table to enable Focus on Form.",
                "Without content-grammar links, grammar may be taught in isolation.",
                ["mandarin/db/", "mandarin/scheduler.py"],
            ))
            return findings

        # Check grammar progress for items drilled without prior contextual exposure
        isolated = _safe_scalar(conn, """
            SELECT COUNT(*) FROM grammar_progress gp
            WHERE gp.drill_attempts > 0
              AND NOT EXISTS (
                  SELECT 1 FROM review_event re
                  JOIN content_grammar cg ON re.content_item_id = cg.content_item_id
                  WHERE cg.grammar_point_id = gp.grammar_point_id
                    AND re.reviewed_at < gp.studied_at
                    AND re.user_id = gp.user_id
              )
        """, default=0)

        total_grammar = _safe_scalar(conn, """
            SELECT COUNT(*) FROM grammar_progress WHERE drill_attempts > 0
        """, default=0)

        if total_grammar > 0 and isolated > 0:
            isolation_pct = isolated / total_grammar * 100
            if isolation_pct > 30:
                findings.append(_finding(
                    "learning_science", "high",
                    f"Focus on Form violation: {isolation_pct:.0f}% of grammar drilled in isolation",
                    f"{isolated}/{total_grammar} grammar points were drilled "
                    f"before the learner encountered them in context (reading "
                    f"or review). Long (1991): grammar should emerge from "
                    f"meaning-focused input. DOCTRINE §1: 'Explanation follows "
                    f"noticing, not the reverse.' {isolation_pct:.0f}% isolation "
                    f"rate is a significant DOCTRINE violation.",
                    "Gate grammar drills on prior contextual exposure: only "
                    "schedule a grammar drill after the learner has encountered "
                    "the pattern in 2+ reading/review contexts.",
                    "Add contextual exposure check to grammar drill scheduling.",
                    "Isolated grammar teaching contradicts DOCTRINE §1 and SLA research.",
                    ["mandarin/scheduler.py"],
                ))

    except Exception as e:
        logger.debug("Focus on Form analyzer failed: %s", e)

    return findings


# ── 5. Cross-Modality Interleaving (Rohrer & Taylor 2007) ────────────


def _analyze_cross_modality_interleaving(conn) -> list[dict]:
    """Check if vocabulary items appear across multiple modalities.

    Rohrer & Taylor (2007): interleaving similar-but-different tasks
    improves long-term retention. DOCTRINE §4: 'A word learned through
    reading should appear in a listening drill within 3 sessions.'
    """
    findings = []

    try:
        # For items with 5+ review events, check how many modalities they appear in
        items = _safe_query_all(conn, """
            SELECT content_item_id,
                   COUNT(DISTINCT
                       CASE
                           WHEN drill_type IN ('mc', 'reverse_mc') THEN 'recognition'
                           WHEN drill_type LIKE 'listening%' THEN 'listening'
                           WHEN drill_type IN ('ime_type', 'hanzi_to_pinyin',
                                'english_to_pinyin') THEN 'production'
                           WHEN drill_type = 'dialogue' THEN 'conversation'
                           WHEN drill_type = 'tone' THEN 'tone'
                           ELSE 'other'
                       END
                   ) as modality_count,
                   COUNT(*) as total_reviews
            FROM review_event
            WHERE reviewed_at >= datetime('now', '-60 days')
            GROUP BY content_item_id
            HAVING total_reviews >= 5
        """)

        if not items or len(items) < 10:
            return findings

        total_items = len(items)
        multi_modal = sum(1 for i in items if i["modality_count"] >= 2)
        mono_modal = total_items - multi_modal
        multi_pct = multi_modal / total_items * 100

        if multi_pct < 50:
            findings.append(_finding(
                "learning_science", "medium",
                f"Low cross-modality interleaving: {multi_pct:.0f}% of items appear in 2+ modalities",
                f"Of {total_items} items with 5+ reviews, only {multi_modal} "
                f"({multi_pct:.0f}%) appear in 2+ modality groups. {mono_modal} "
                f"items are stuck in one modality. Rohrer & Taylor (2007): "
                f"interleaving across categories improves retention. DOCTRINE "
                f"§4: 'A word learned through reading should appear in a "
                f"listening drill within 3 sessions.'",
                "Boost cross-modality scheduling: when an item has been "
                "reviewed 5+ times in one modality, prioritize it for a "
                "different modality in the next session.",
                "Add cross-modality rotation to scheduler priority computation.",
                "Mono-modal drilling limits long-term retention and skill transfer.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Cross-modality interleaving analyzer failed: %s", e)

    return findings


# ── 6. Desirable Difficulty for Listening (Bjork 1994) ───────────────


def _analyze_listening_desirable_difficulty(conn) -> list[dict]:
    """Check if listening difficulty progresses over time (Bjork 1994).

    Bjork's desirable difficulty: slightly harder conditions improve
    long-term retention. For listening, this means gradually reducing
    playback speed assistance and increasing passage complexity.
    """
    findings = []

    try:
        # Check listening progression over time
        rows = _safe_query_all(conn, """
            SELECT comprehension_score, playback_speed, replays,
                   ROW_NUMBER() OVER (ORDER BY completed_at) as session_num
            FROM listening_progress
            WHERE completed_at >= datetime('now', '-60 days')
              AND comprehension_score IS NOT NULL
            ORDER BY completed_at
        """)

        if not rows or len(rows) < 10:
            return findings

        # Split into first half and second half
        mid = len(rows) // 2
        first_half = rows[:mid]
        second_half = rows[mid:]

        from statistics import mean

        first_speed = mean([r["playback_speed"] or 1.0 for r in first_half])
        second_speed = mean([r["playback_speed"] or 1.0 for r in second_half])

        first_replays = mean([r["replays"] or 0 for r in first_half])
        second_replays = mean([r["replays"] or 0 for r in second_half])

        first_score = mean([r["comprehension_score"] for r in first_half])
        second_score = mean([r["comprehension_score"] for r in second_half])

        # Desirable difficulty: speed should increase (or stay same),
        # replays should decrease, scores should stay stable or improve
        speed_flat = abs(second_speed - first_speed) < 0.05
        replays_flat = abs(second_replays - first_replays) < 0.5
        score_flat = abs(second_score - first_score) < 0.05

        if speed_flat and replays_flat and score_flat:
            findings.append(_finding(
                "learning_science", "low",
                "Listening difficulty not progressing (Bjork desirable difficulty)",
                f"Listening metrics are flat across {len(rows)} sessions: "
                f"speed {first_speed:.2f}→{second_speed:.2f}x, "
                f"replays {first_replays:.1f}→{second_replays:.1f}, "
                f"score {first_score:.2f}→{second_score:.2f}. "
                f"Bjork (1994): desirable difficulty — slightly harder "
                f"conditions improve long-term retention. Listening should "
                f"gradually increase in challenge as comprehension improves.",
                "Implement adaptive listening difficulty: as comprehension "
                "scores stabilize, increase playback speed or reduce "
                "replay allowance. Small steps: 1.0x → 1.1x → 1.25x.",
                "Add adaptive speed progression to listening block selection.",
                "Flat difficulty plateaus learning — Bjork's desirable difficulty shows slight challenge drives retention.",
                ["mandarin/scheduler.py"],
            ))

    except Exception as e:
        logger.debug("Listening desirable difficulty analyzer failed: %s", e)

    return findings


# ── 7. Authentic Media (Gilmore 2007) ────────────────────────────────


def _analyze_media_authenticity(conn) -> list[dict]:
    """Check if media comprehension features use authentic materials.

    Gilmore (2007): authentic materials develop pragmatic competence
    that textbook-style materials cannot. Real-world media exposure
    is essential for advanced comprehension.
    """
    findings = []

    try:
        media_engagement = _safe_scalar(conn, """
            SELECT COUNT(*) FROM review_event
            WHERE drill_type = 'media_comprehension'
              AND reviewed_at >= datetime('now', '-60 days')
        """, default=0)

        # Check if media entries exist at all
        media_entries = _safe_scalar(conn, """
            SELECT COUNT(*) FROM media_entry
        """, default=-1)  # -1 if table doesn't exist

        if media_entries == -1:
            # Table doesn't exist — media feature not fully built
            findings.append(_finding(
                "learning_science", "low",
                "Media shelf not available — no authentic input channel",
                "Gilmore (2007): authentic materials (real-world video, audio, "
                "text) develop pragmatic competence that textbook drills "
                "cannot. The media shelf feature is not yet available. "
                "This is acceptable pre-launch but should be prioritized "
                "for intermediate learners (HSK 3+).",
                "Build media shelf with authentic Chinese content: news "
                "clips, interviews, vlogs with comprehension questions.",
                "Implement media_entry table and media comprehension drills.",
                "Without authentic input, pragmatic competence development is limited.",
                ["mandarin/media.py"],
            ))
        elif media_entries == 0:
            findings.append(_finding(
                "learning_science", "low",
                "Media shelf empty — no authentic content available",
                f"The media shelf exists but has zero entries. "
                f"Gilmore (2007): authentic materials are essential for "
                f"developing pragmatic competence beyond textbook patterns.",
                "Populate the media shelf with authentic Chinese content.",
                "Add media entries via content ingestion pipeline.",
                "Empty media shelf means zero authentic input exposure.",
                ["mandarin/media.py"],
            ))
        elif media_engagement == 0 and media_entries > 0:
            findings.append(_finding(
                "learning_science", "medium",
                f"Media shelf has {media_entries} entries but zero engagement in 60 days",
                f"The media shelf contains {media_entries} entries but no "
                f"learner has engaged with media comprehension in the last "
                f"60 days. Gilmore (2007): authentic materials develop "
                f"competence textbook drills cannot. Zero engagement means "
                f"this research-backed feature is not reaching learners.",
                "Investigate media discoverability. Is media behind a "
                "paywall? Is it surfaced in the scheduler? Consider adding "
                "a media block to standard sessions for HSK 3+ learners.",
                "Check media visibility in scheduler and tier_gate.",
                "Authentic media feature exists but zero learners use it.",
                ["mandarin/scheduler.py", "mandarin/tier_gate.py"],
            ))

    except Exception as e:
        logger.debug("Media authenticity analyzer failed: %s", e)

    return findings


def _analyze_fsrs_calibration(conn):
    """Check if FSRS per-learner calibration is fresh for active learners."""
    findings = []
    try:
        # Count active users with 50+ reviews but no recent FSRS calibration
        stale = _safe_scalar(
            conn,
            """SELECT COUNT(DISTINCT re.user_id) FROM review_event re
               WHERE re.user_id NOT IN (
                   SELECT user_id FROM learner_fsrs_params
                   WHERE calibrated_at >= datetime('now', '-30 days')
               )
               GROUP BY re.user_id HAVING COUNT(*) >= 50""",
        )
        if stale and stale > 0:
            findings.append(_finding(
                dimension="learning_science",
                severity="low",
                title="FSRS calibration stale for active learners",
                analysis=f"{stale} active learner(s) with 50+ reviews lack recent FSRS calibration.",
                recommendation="Run FSRS calibration nightly via quality scheduler.",
                claude_prompt="Check mandarin/fsrs_calibration.py calibrate_all_eligible()",
                files=["mandarin/fsrs_calibration.py"],
            ))
    except Exception:
        pass
    return findings


def _analyze_grammar_linkage_coverage(conn):
    """Check what % of content items have grammar links."""
    findings = []
    try:
        total = _safe_scalar(conn, "SELECT COUNT(*) FROM content_item") or 0
        linked = _safe_scalar(
            conn,
            "SELECT COUNT(DISTINCT content_item_id) FROM content_grammar",
        ) or 0
        if total > 0:
            coverage = linked / total
            if coverage < 0.3:
                findings.append(_finding(
                    dimension="learning_science",
                    severity="high",
                    title=f"Grammar linkage coverage only {coverage:.0%}",
                    analysis=f"Only {linked}/{total} content items have grammar links. "
                             f"Focus on Form (Long 1991) cannot be enforced without linkage.",
                    recommendation="Run auto_link_grammar() to populate content_grammar table.",
                    claude_prompt="Run mandarin/grammar_linker.py auto_link_grammar(conn)",
                    files=["mandarin/grammar_linker.py"],
                ))
    except Exception:
        pass
    return findings


def _analyze_prerequisite_coverage(conn):
    """Check what % of multi-character items have prerequisites defined."""
    findings = []
    try:
        multi_char = _safe_scalar(
            conn,
            "SELECT COUNT(*) FROM content_item WHERE LENGTH(hanzi) > 1",
        ) or 0
        with_prereqs = _safe_scalar(
            conn,
            "SELECT COUNT(DISTINCT item_id) FROM prerequisite_edge",
        ) or 0
        if multi_char > 0:
            coverage = with_prereqs / multi_char
            if coverage < 0.2:
                findings.append(_finding(
                    dimension="learning_science",
                    severity="medium",
                    title=f"Prerequisite coverage only {coverage:.0%}",
                    analysis=f"Only {with_prereqs}/{multi_char} multi-character items have prerequisites.",
                    recommendation="Run build_prerequisite_graph() to detect character component dependencies.",
                    claude_prompt="Run mandarin/prerequisites.py build_prerequisite_graph(conn)",
                    files=["mandarin/prerequisites.py"],
                ))
    except Exception:
        pass
    return findings


def _analyze_calibration_gap(conn):
    """Check if learners are systematically overconfident or underconfident."""
    findings = []
    try:
        rows = _safe_query(
            conn,
            """SELECT confidence_level, AVG(predicted_rate) as avg_pred,
                      AVG(actual_rate) as avg_actual, SUM(n_items) as total
               FROM calibration_snapshot
               WHERE snapshot_at >= datetime('now', '-30 days')
               GROUP BY confidence_level""",
        )
        if rows:
            for r in rows:
                gap = abs((r.get("avg_pred") or 0) - (r.get("avg_actual") or 0))
                if gap > 0.15 and (r.get("total") or 0) >= 20:
                    direction = "overconfident" if (r.get("avg_pred") or 0) > (r.get("avg_actual") or 0) else "underconfident"
                    findings.append(_finding(
                        dimension="learning_science",
                        severity="medium",
                        title=f"Learners are {direction} at '{r['confidence_level']}' level",
                        analysis=f"Predicted {r['avg_pred']:.0%} but actual {r['avg_actual']:.0%} ({gap:.0%} gap).",
                        recommendation="Increase calibration feedback frequency or adjust confidence prompts.",
                        claude_prompt="Check mandarin/metacognition.py calibration feedback thresholds",
                        files=["mandarin/metacognition.py"],
                    ))
    except Exception:
        pass
    return findings


def _analyze_interference_scheduling(conn):
    """Check if confusable pairs are being appropriately managed."""
    findings = []
    try:
        total_pairs = _safe_scalar(conn, "SELECT COUNT(*) FROM confusable_pair") or 0
        if total_pairs == 0:
            findings.append(_finding(
                dimension="learning_science",
                severity="low",
                title="No confusable pairs detected yet",
                analysis="Interference-aware scheduling requires confusable pair data.",
                recommendation="Run detect_confusables() to populate confusable_pair table.",
                claude_prompt="Run mandarin/interference.py detect_confusables(conn)",
                files=["mandarin/interference.py"],
            ))
    except Exception:
        pass
    return findings


ANALYZERS = [
    _analyze_extensive_reading,
    _analyze_narrow_listening,
    _analyze_pushed_output,
    _analyze_focus_on_form,
    _analyze_cross_modality_interleaving,
    _analyze_listening_desirable_difficulty,
    _analyze_media_authenticity,
    _analyze_fsrs_calibration,
    _analyze_grammar_linkage_coverage,
    _analyze_prerequisite_coverage,
    _analyze_calibration_gap,
    _analyze_interference_scheduling,
]
