"""Product Intelligence — domain-specific analyzers for Mandarin learning.

8 analyzers that understand the SRS, phonology, curriculum, and pedagogy domains.
"""

import json
import logging

from ._base import (
    _f, _FILE_MAP, _ARCHETYPE_RULES, _finding,
    _safe_query, _safe_query_all, _safe_scalar,
)

logger = logging.getLogger(__name__)


def analyze_srs_funnel(conn) -> list[dict]:
    """Mastery stage pipeline health — blockages, regressions, weak cycles."""
    findings = []

    # Stage distribution
    stages = _safe_query_all(conn, """
        SELECT mastery_stage, COUNT(*) as cnt
        FROM progress
        GROUP BY mastery_stage
    """)
    if not stages:
        return findings

    stage_counts = {r["mastery_stage"]: r["cnt"] for r in stages}
    total = sum(stage_counts.values())

    # Items stuck at stabilizing for >14 days
    stuck_stabilizing = _safe_scalar(conn, """
        SELECT COUNT(*) FROM progress
        WHERE mastery_stage = 'stabilizing'
          AND last_review_date <= datetime('now', '-14 days')
    """)
    if stuck_stabilizing and total > 0:
        stuck_pct = round(stuck_stabilizing / total * 100, 1)
        if stuck_pct > 50:
            findings.append(_finding(
                "srs_funnel", "high",
                f"{stuck_pct}% of items stuck at 'stabilizing' for >14 days",
                f"{stuck_stabilizing} of {total} progress records are stuck at stabilizing. "
                "Items should transition to stable within 2 weeks with normal review cadence.",
                "Investigate scheduler interval settings — items may not be scheduled frequently enough.",
                (
                    f"{stuck_stabilizing}/{total} items stuck at stabilizing.\n\n"
                    f"1. Check {_FILE_MAP['scheduler']} — interval calculation for stabilizing stage\n"
                    "2. Query: SELECT content_item_id, ease_factor, interval_days, last_review_date "
                    "FROM progress WHERE mastery_stage = 'stabilizing' AND "
                    "last_review_date <= datetime('now', '-14 days') ORDER BY last_review_date ASC LIMIT 20"
                ),
                "Learning: stuck items mean the SRS isn't working",
                _f("scheduler"),
            ))

    # Regression: items that moved backward
    regressions = _safe_scalar(conn, """
        SELECT COUNT(*) FROM progress
        WHERE weak_cycle_count > 0
          AND mastery_stage IN ('seen', 'learning')
          AND repetitions > 10
    """)
    if regressions and regressions > 5:
        findings.append(_finding(
            "srs_funnel", "medium",
            f"{regressions} items regressed after 10+ reps",
            "Items with many repetitions are still in early stages, suggesting regression.",
            "Review items that cycle between mastery stages — they may need scaffolding.",
            (
                f"{regressions} regressed items.\n\n"
                "1. Query: SELECT p.content_item_id, c.hanzi, c.english, p.mastery_stage, "
                "p.weak_cycle_count, p.repetitions FROM progress p "
                "JOIN content_item c ON p.content_item_id = c.id "
                "WHERE p.weak_cycle_count > 0 AND p.repetitions > 10 "
                "ORDER BY p.weak_cycle_count DESC LIMIT 20"
            ),
            "Learning: regression cycles waste learner time",
            _f("scheduler"),
        ))

    # Historically weak population
    historically_weak = _safe_scalar(conn, """
        SELECT COUNT(*) FROM progress WHERE historically_weak = 1
    """)
    if historically_weak and total > 0:
        weak_pct = round(historically_weak / total * 100, 1)
        if weak_pct > 20:
            findings.append(_finding(
                "srs_funnel", "medium",
                f"{weak_pct}% of items flagged historically_weak",
                f"{historically_weak} items are marked as historically weak. "
                "This is a large fraction that may indicate systemic difficulty issues.",
                "Review the historically_weak threshold and whether additional scaffolding is needed.",
                (
                    f"{historically_weak}/{total} items historically weak ({weak_pct}%).\n\n"
                    f"1. Check {_FILE_MAP['scheduler']} — historically_weak handling\n"
                    "2. These items may benefit from different drill types or context notes"
                ),
                "Learning: too many weak items = learner overwhelm",
                _f("scheduler"),
            ))

    return findings


def analyze_error_taxonomy(conn) -> list[dict]:
    """14-type error trend analysis — growth detection, cross-reference."""
    findings = []

    # Current week vs prior 4-week avg per error_type
    current_week = _safe_query_all(conn, """
        SELECT error_type, COUNT(*) as cnt
        FROM error_log
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY error_type
    """)
    prior_avg = _safe_query_all(conn, """
        SELECT error_type, COUNT(*) / 4.0 as avg_cnt
        FROM error_log
        WHERE created_at >= datetime('now', '-35 days')
          AND created_at < datetime('now', '-7 days')
        GROUP BY error_type
    """)
    if not current_week:
        return findings

    current_map = {r["error_type"]: r["cnt"] for r in current_week}
    prior_map = {r["error_type"]: r["avg_cnt"] for r in (prior_avg or [])}

    growing_types = []
    for etype, cnt in current_map.items():
        prior = prior_map.get(etype, 0)
        if prior > 0 and cnt > prior * 1.3:
            growth_pct = round((cnt - prior) / prior * 100, 1)
            growing_types.append((etype, cnt, prior, growth_pct))

    if growing_types:
        growing_types.sort(key=lambda x: -x[3])
        examples = ", ".join(f"{t[0]} (+{t[3]}%)" for t in growing_types[:5])
        findings.append(_finding(
            "error_taxonomy", "high" if any(t[3] > 50 for t in growing_types) else "medium",
            f"{len(growing_types)} error types growing >30% week-over-week",
            f"Growing error types: {examples}. "
            "Rapidly increasing error types may indicate new difficulty cliffs or content issues.",
            "Investigate the fastest-growing error types for root causes.",
            (
                f"Growing error types: {examples}\n\n"
                "1. Query: SELECT error_type, content_item_id, COUNT(*) FROM error_log "
                "WHERE created_at >= datetime('now', '-7 days') AND error_type IN "
                f"({','.join(repr(t[0]) for t in growing_types[:3])}) "
                "GROUP BY error_type, content_item_id ORDER BY COUNT(*) DESC LIMIT 20"
            ),
            "Learning: growing error types signal emerging difficulty",
            _f("drills", "scheduler"),
        ))

    # Error type transitions (week-over-week)
    transitions = _safe_query_all(conn, """
        SELECT e1.error_type as from_type, e2.error_type as to_type, COUNT(*) as cnt
        FROM error_log e1
        JOIN error_log e2 ON e1.user_id = e2.user_id
            AND e1.error_type != e2.error_type
            AND e1.created_at >= datetime('now', '-14 days')
            AND e1.created_at < datetime('now', '-7 days')
            AND e2.created_at >= datetime('now', '-7 days')
        GROUP BY e1.error_type, e2.error_type
        HAVING cnt >= 3
        ORDER BY cnt DESC
        LIMIT 10
    """)
    if transitions and len(transitions) >= 2:
        # Classify transitions
        positive_transitions = {"vocabulary": {"grammar", "register_mismatch", "pragmatic"}}
        concerning = []
        positive = []
        for t in transitions:
            ft, tt = t["from_type"], t["to_type"]
            if ft in positive_transitions and tt in positive_transitions.get(ft, set()):
                positive.append(f"{ft}→{tt} ({t['cnt']}x)")
            else:
                concerning.append(f"{ft}→{tt} ({t['cnt']}x)")
        if concerning:
            findings.append(_finding(
                "error_taxonomy", "medium",
                f"{len(concerning)} concerning error type transitions detected",
                f"Concerning transitions: {', '.join(concerning[:5])}. "
                "Users are shifting between error types in ways that may indicate confusion.",
                "Investigate whether content progression is causing error type shifts.",
                f"Error transitions: {', '.join(concerning[:5])}",
                "Learning: error type shifts reveal progression patterns",
                _f("drills", "scheduler"),
            ))

    # Register mismatch cross-reference
    register_errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM error_log
        WHERE error_type = 'register_mismatch'
          AND created_at >= datetime('now', '-30 days')
    """)
    if register_errors and register_errors > 5:
        findings.append(_finding(
            "error_taxonomy", "medium",
            f"{register_errors} register mismatch errors in 30 days",
            "Learners are producing wrong register (formal/informal/professional). "
            "This is a specific error type that benefits from targeted drill design.",
            "Add register-awareness to drill prompts for professional vocabulary.",
            (
                f"{register_errors} register mismatches.\n\n"
                "1. Query error_log for register_mismatch + content_item details\n"
                f"2. Check {_FILE_MAP['drills']} for register-specific drill logic"
            ),
            "Learning: register errors indicate pragmatic competence gaps",
            _f("drills"),
        ))

    return findings


def analyze_cross_modality_transfer(conn) -> list[dict]:
    """Per-item modality mastery comparison — find gaps between reading/listening/etc."""
    findings = []

    # Find items where one modality is >=2 stages ahead of another
    # mastery_stage order: unseen=0, seen=1, learning=2, stabilizing=3, stable=4
    modality_gaps = _safe_query_all(conn, """
        SELECT p1.user_id, p1.content_item_id, p1.modality as mod1, p1.mastery_stage as stage1,
               p2.modality as mod2, p2.mastery_stage as stage2
        FROM progress p1
        JOIN progress p2 ON p1.user_id = p2.user_id
            AND p1.content_item_id = p2.content_item_id
            AND p1.modality != p2.modality
        WHERE p1.mastery_stage IN ('stable', 'stabilizing')
          AND p2.mastery_stage IN ('unseen', 'seen')
        LIMIT 50
    """)

    if modality_gaps and len(modality_gaps) >= 5:
        # Count unique content items with gaps
        gap_items = set()
        for r in modality_gaps:
            gap_items.add(r["content_item_id"])

        # Summarize modality pairs
        pair_counts = {}
        for r in modality_gaps:
            pair = f"{r['mod1']}→{r['mod2']}"
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
        top_pairs = sorted(pair_counts.items(), key=lambda x: -x[1])[:3]
        pair_info = ", ".join(f"{p} ({c}x)" for p, c in top_pairs)

        findings.append(_finding(
            "cross_modality", "high" if len(gap_items) > 20 else "medium",
            f"{len(gap_items)} items with modality mastery gaps",
            f"Items are mastered in one modality but not another. "
            f"Common gaps: {pair_info}. "
            "This means learners can read but not listen (or vice versa).",
            "Schedule cross-modality drills for items with gaps.",
            (
                f"{len(gap_items)} items with modality gaps: {pair_info}\n\n"
                f"1. Check {_FILE_MAP['scheduler']} — cross-modality scheduling logic\n"
                "2. Query: SELECT content_item_id, modality, mastery_stage FROM progress "
                "WHERE content_item_id IN (SELECT content_item_id FROM progress "
                "WHERE mastery_stage IN ('stable','stabilizing') GROUP BY content_item_id "
                "HAVING COUNT(DISTINCT modality) < (SELECT COUNT(DISTINCT modality) FROM progress)) "
                "ORDER BY content_item_id, modality"
            ),
            "Learning: modality gaps mean incomplete mastery",
            _f("scheduler"),
        ))

    return findings


def analyze_curriculum_coverage(conn) -> list[dict]:
    """Grammar, skills, constructions — coverage gaps."""
    findings = []

    # Need active learners to assess curriculum coverage meaningfully
    active_users = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
    """)
    if not active_users or active_users < 3:
        return findings

    # Grammar point coverage
    total_grammar = _safe_scalar(conn, "SELECT COUNT(*) FROM grammar_point")
    drilled_grammar = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT grammar_point_id) FROM grammar_progress
    """)
    if total_grammar and total_grammar > 0:
        coverage = round((drilled_grammar or 0) / total_grammar * 100, 1)
        if coverage < 50:
            findings.append(_finding(
                "curriculum", "high" if coverage < 25 else "medium",
                f"Grammar coverage: {coverage}% ({drilled_grammar}/{total_grammar} points drilled)",
                f"Only {coverage}% of grammar points have been practiced. "
                "Learners may have gaps in grammatical knowledge.",
                "Ensure grammar points are systematically introduced in sessions.",
                (
                    f"Grammar coverage is {coverage}%.\n\n"
                    "1. Query: SELECT gp.id, gp.name, gp.category FROM grammar_point gp "
                    "WHERE gp.id NOT IN (SELECT grammar_point_id FROM grammar_progress) "
                    "ORDER BY gp.category, gp.id\n"
                    f"2. Check {_FILE_MAP['scheduler']} — grammar introduction logic"
                ),
                "Learning: uncovered grammar = blind spots",
                _f("scheduler"),
            ))

    # Grammar category balance
    category_coverage = _safe_query_all(conn, """
        SELECT gp.category, COUNT(DISTINCT gp.id) as total,
               COUNT(DISTINCT gpr.grammar_point_id) as drilled
        FROM grammar_point gp
        LEFT JOIN grammar_progress gpr ON gp.id = gpr.grammar_point_id
        GROUP BY gp.category
    """)
    if category_coverage:
        weak_cats = [r for r in category_coverage if (r["drilled"] or 0) < 2]
        if weak_cats:
            cat_info = ", ".join(f"{r['category']} ({r['drilled'] or 0}/{r['total']})" for r in weak_cats)
            findings.append(_finding(
                "curriculum", "medium",
                f"{len(weak_cats)} grammar categories with <2 points drilled",
                f"Underdrilled categories: {cat_info}.",
                "Balance grammar category exposure in scheduling.",
                (
                    f"Weak grammar categories: {cat_info}\n\n"
                    f"1. Check {_FILE_MAP['scheduler']} — grammar category balancing"
                ),
                "Learning: category gaps leave learners unprepared",
                _f("scheduler"),
            ))

    # Skills with zero linked items
    orphan_skills = _safe_query_all(conn, """
        SELECT s.id, s.name FROM skill s
        LEFT JOIN content_skill cs ON s.id = cs.skill_id
        WHERE cs.id IS NULL
    """)
    if orphan_skills:
        skill_names = ", ".join(r["name"] for r in orphan_skills[:5])
        findings.append(_finding(
            "curriculum", "medium",
            f"{len(orphan_skills)} skills with zero linked content items",
            f"Skills without content: {skill_names}{'...' if len(orphan_skills) > 5 else ''}. "
            "These skills exist in the curriculum but have no drillable content.",
            "Link content items to these skills or create content for them.",
            (
                f"Orphan skills: {skill_names}\n\n"
                "1. Query: SELECT s.id, s.name FROM skill s LEFT JOIN content_skill cs "
                "ON s.id = cs.skill_id WHERE cs.id IS NULL"
            ),
            "Learning: skills without content can't be learned",
            [],
        ))

    return findings


def analyze_hsk_cliff(conn) -> list[dict]:
    """Difficulty cliff detection at HSK boundaries."""
    findings = []

    # Error rate per HSK level
    hsk_error_rates = _safe_query_all(conn, """
        SELECT c.hsk_level,
               COUNT(*) as total,
               SUM(CASE WHEN r.correct = 0 THEN 1 ELSE 0 END) as errors
        FROM review_event r
        JOIN content_item c ON r.content_item_id = c.id
        WHERE r.created_at >= datetime('now', '-30 days')
          AND c.hsk_level IS NOT NULL
        GROUP BY c.hsk_level
        HAVING total >= 10
        ORDER BY c.hsk_level
    """)
    if not hsk_error_rates or len(hsk_error_rates) < 2:
        return findings

    # Check adjacent level error rate jumps
    for i in range(len(hsk_error_rates) - 1):
        curr = hsk_error_rates[i]
        nxt = hsk_error_rates[i + 1]
        curr_rate = (curr["errors"] or 0) / curr["total"] * 100 if curr["total"] > 0 else 0
        nxt_rate = (nxt["errors"] or 0) / nxt["total"] * 100 if nxt["total"] > 0 else 0
        jump = nxt_rate - curr_rate

        if jump > 20:
            findings.append(_finding(
                "hsk_cliff", "high" if jump > 30 else "medium",
                f"HSK cliff: {round(jump, 1)}pp error rate jump at HSK {curr['hsk_level']}→{nxt['hsk_level']}",
                f"Error rate jumps from {round(curr_rate, 1)}% (HSK {curr['hsk_level']}, n={curr['total']}) "
                f"to {round(nxt_rate, 1)}% (HSK {nxt['hsk_level']}, n={nxt['total']}). "
                "This is a difficulty cliff that may cause learner frustration.",
                "Add bridge content between these HSK levels. "
                "Consider introducing HSK N+1 vocabulary more gradually.",
                (
                    f"Error rate cliff: HSK {curr['hsk_level']} ({round(curr_rate, 1)}%) → "
                    f"HSK {nxt['hsk_level']} ({round(nxt_rate, 1)}%), jump={round(jump, 1)}pp.\n\n"
                    "1. Query: SELECT c.hanzi, c.english, c.hsk_level, "
                    "AVG(CASE WHEN r.correct=0 THEN 1.0 ELSE 0.0 END) as err_rate, COUNT(*) as n "
                    "FROM review_event r JOIN content_item c ON r.content_item_id=c.id "
                    f"WHERE c.hsk_level={nxt['hsk_level']} AND r.created_at>=datetime('now','-30 days') "
                    "GROUP BY c.id HAVING n>=5 ORDER BY err_rate DESC LIMIT 10\n"
                    "2. Add scaffolding content for the hardest HSK N+1 items"
                ),
                f"Learning: HSK cliffs are the #1 cause of level-transition churn",
                _f("scheduler"),
            ))

    return findings


def analyze_tone_phonology(conn) -> list[dict]:
    """Parselmouth tone data analysis — per-tone accuracy, confusion pairs, fatigue."""
    findings = []

    # Check if audio recordings exist with tone data
    recordings = _safe_scalar(conn, """
        SELECT COUNT(*) FROM audio_recording
        WHERE tone_scores_json IS NOT NULL
    """)
    if not recordings or recordings < 10:
        return findings

    # Per-tone accuracy from tone_scores_json
    # Parse aggregated tone data
    tone_data = _safe_query_all(conn, """
        SELECT tone_scores_json, created_at FROM audio_recording
        WHERE tone_scores_json IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 500
    """)

    tone_correct = {1: 0, 2: 0, 3: 0, 4: 0}
    tone_total = {1: 0, 2: 0, 3: 0, 4: 0}
    confusion_pairs = {}  # (expected, detected) -> count
    malformed_count = 0
    total_records = 0

    for row in (tone_data or []):
        total_records += 1
        try:
            scores = json.loads(row["tone_scores_json"])
            if not isinstance(scores, list):
                malformed_count += 1
                continue
            for syllable in scores:
                expected = syllable.get("expected_tone")
                detected = syllable.get("detected_tone")
                correct = syllable.get("correct", False)
                if expected in tone_total:
                    tone_total[expected] += 1
                    if correct:
                        tone_correct[expected] += 1
                    elif detected and detected != expected:
                        pair = (expected, detected)
                        confusion_pairs[pair] = confusion_pairs.get(pair, 0) + 1
        except (json.JSONDecodeError, TypeError, KeyError):
            malformed_count += 1
            continue

    # Data quality check
    if total_records > 0 and malformed_count / total_records > 0.1:
        malformed_pct = round(malformed_count / total_records * 100, 1)
        findings.append(_finding(
            "tone_phonology", "high" if malformed_pct > 25 else "medium",
            f"{malformed_pct}% of tone recordings have malformed data",
            f"{malformed_count} of {total_records} tone_scores_json records are malformed. "
            "This degrades tone analysis accuracy.",
            "Fix the tone scoring pipeline to ensure valid JSON output.",
            f"{malformed_count}/{total_records} malformed tone records.",
            "Data quality: malformed data undermines tone analysis",
            ["mandarin/tone_grading.py"],
        ))

    # Per-tone accuracy
    weak_tones = []
    for tone in [1, 2, 3, 4]:
        if tone_total[tone] >= 10:
            acc = round(tone_correct[tone] / tone_total[tone] * 100, 1)
            if acc < 70:
                weak_tones.append((tone, acc, tone_total[tone]))

    if weak_tones:
        tone_info = ", ".join(f"Tone {t[0]}: {t[1]}% (n={t[2]})" for t in weak_tones)
        findings.append(_finding(
            "tone_phonology", "high" if any(t[1] < 50 for t in weak_tones) else "medium",
            f"Weak tone accuracy: {tone_info}",
            f"Tones with <70% accuracy: {tone_info}. "
            "Systematic tone weakness needs targeted practice.",
            "Add tone-focused drills for weak tones. Consider minimal pair exercises.",
            (
                f"Weak tones: {tone_info}\n\n"
                f"1. Check {_FILE_MAP['drills']} — tone drill type availability\n"
                "2. Consider adding tone-pair discrimination drills\n"
                "3. Review tone grading sensitivity in mandarin/tone_grading.py"
            ),
            "Learning: tone accuracy is critical for Mandarin intelligibility",
            _f("drills", "scheduler"),
        ))

    # Confusion pairs
    if confusion_pairs:
        top_confusion = sorted(confusion_pairs.items(), key=lambda x: -x[1])[:3]
        if top_confusion[0][1] >= 5:
            pair_info = ", ".join(
                f"T{p[0]}→T{p[1]} ({c}x)" for (p, c) in top_confusion
            )
            findings.append(_finding(
                "tone_phonology", "medium",
                f"Systematic tone confusion: {pair_info}",
                f"Common confusion pairs: {pair_info}. "
                "These confusions are systematic and benefit from targeted practice.",
                "Create minimal pair drills targeting these specific confusions.",
                (
                    f"Tone confusion pairs: {pair_info}\n\n"
                    "1. Design minimal pair drills for the top confusion pair\n"
                    "2. The classic T2↔T3 confusion is especially common for English speakers"
                ),
                "Learning: systematic confusions need targeted intervention",
                _f("drills"),
            ))

    return findings


def analyze_scheduler_decisions(conn) -> list[dict]:
    """Scheduler self-audit — day profiles, WIP, bounces, Thompson Sampling."""
    findings = []

    # Day profile mode distribution
    sessions = _safe_query_all(conn, """
        SELECT plan_snapshot FROM session_log
        WHERE plan_snapshot IS NOT NULL
          AND started_at >= datetime('now', '-30 days')
        ORDER BY started_at DESC
        LIMIT 200
    """)
    if sessions:
        mode_counts = {}
        wip_exceeded_count = 0
        for row in sessions:
            try:
                plan = json.loads(row["plan_snapshot"]) if isinstance(row["plan_snapshot"], str) else row["plan_snapshot"]
                mode = plan.get("day_mode") or plan.get("profile_mode", "unknown")
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
                if plan.get("wip_exceeded"):
                    wip_exceeded_count += 1
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        total_parsed = sum(mode_counts.values())
        if total_parsed > 0:
            gentle_pct = round(
                (mode_counts.get("gentle", 0) + mode_counts.get("consolidation", 0))
                / total_parsed * 100, 1
            )
            if gentle_pct > 40:
                findings.append(_finding(
                    "scheduler_audit", "medium",
                    f"{gentle_pct}% of sessions are gentle/consolidation mode",
                    f"Day profile distribution: {dict(mode_counts)}. "
                    "High gentle/consolidation usage suggests the learner is struggling or uncommitted.",
                    "Review gentle mode trigger conditions — are they too sensitive?",
                    (
                        f"Day profile modes: {dict(mode_counts)} ({gentle_pct}% gentle/consolidation).\n\n"
                        f"1. Check {_FILE_MAP['scheduler']} — day_mode selection logic\n"
                        "2. Are sessions being made too easy too often?"
                    ),
                    "Learning: too much gentleness may slow progression",
                    _f("scheduler"),
                ))

        # WIP exceeded
        if wip_exceeded_count > 5:
            findings.append(_finding(
                "scheduler_audit", "medium",
                f"WIP limit exceeded in {wip_exceeded_count} sessions",
                "Multiple sessions show WIP limit violations.",
                "Review WIP limit settings — they may be too low or the learner too ambitious.",
                (
                    f"{wip_exceeded_count} WIP violations.\n\n"
                    f"1. Check {_FILE_MAP['scheduler']} — WIP limit enforcement"
                ),
                "Methodology: WIP violations indicate planning issues",
                _f("scheduler"),
            ))

    # Thompson Sampling convergence check
    drill_dist = _safe_query_all(conn, """
        SELECT drill_type, COUNT(*) as cnt
        FROM review_event
        WHERE created_at >= datetime('now', '-14 days')
        GROUP BY drill_type
        ORDER BY cnt DESC
    """)
    if drill_dist and len(drill_dist) >= 3:
        total = sum(r["cnt"] for r in drill_dist)
        top = drill_dist[0]
        if total > 0:
            top_pct = round(top["cnt"] / total * 100, 1)
            if top_pct > 70:
                findings.append(_finding(
                    "scheduler_audit", "medium",
                    f"Thompson Sampling may have converged: '{top['drill_type']}' = {top_pct}%",
                    f"One drill type dominates 2-week sampling at {top_pct}%. "
                    "The bandit may have converged prematurely — exploration has stopped.",
                    "Add exploration bonus or reset priors for undersampled arms.",
                    (
                        f"'{top['drill_type']}' at {top_pct}% of 2-week drills.\n\n"
                        f"1. Check {_FILE_MAP['scheduler']} — Thompson Sampling exploration rate\n"
                        "2. Consider adding epsilon-greedy exploration fallback"
                    ),
                    "Methodology: premature convergence limits learning variety",
                    _f("scheduler"),
                ))

    # Planned vs completed ratio
    plan_stats = _safe_query(conn, """
        SELECT AVG(CAST(items_completed AS REAL) / NULLIF(items_planned, 0)) as avg_ratio,
               COUNT(*) as n
        FROM session_log
        WHERE items_planned > 0
          AND started_at >= datetime('now', '-30 days')
    """)
    if plan_stats and plan_stats["avg_ratio"] is not None and plan_stats["n"] >= 10:
        ratio = round(plan_stats["avg_ratio"] * 100, 1)
        if ratio < 60:
            findings.append(_finding(
                "scheduler_audit", "high",
                f"Sessions complete only {ratio}% of planned items on average",
                f"Avg planned-to-completed ratio is {ratio}% over {plan_stats['n']} sessions. "
                "Sessions are consistently over-planned.",
                "Reduce session plan size or make plans adaptive.",
                (
                    f"Completion ratio: {ratio}%.\n\n"
                    f"1. Check {_FILE_MAP['scheduler']} — session planning size\n"
                    "2. Consider reducing plan to 80% of current size"
                ),
                "Learning: over-planned sessions lead to frustration and abandonment",
                _f("scheduler"),
            ))

    return findings


def analyze_encounter_feedback_loop(conn) -> list[dict]:
    """vocab_encounter → drill effectiveness — are encounters producing learning?"""
    findings = []

    # Total encounters
    total_encounters = _safe_scalar(conn, """
        SELECT COUNT(*) FROM vocab_encounter WHERE looked_up = 1
    """)
    if not total_encounters or total_encounters < 10:
        return findings

    # Encounters that were subsequently drilled
    drilled_encounters = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT ve.content_item_id) FROM vocab_encounter ve
        JOIN review_event re ON ve.content_item_id = re.content_item_id
        WHERE ve.looked_up = 1
          AND re.created_at > ve.created_at
    """)
    encounter_to_drill_rate = round((drilled_encounters or 0) / total_encounters * 100, 1)

    if encounter_to_drill_rate < 30:
        findings.append(_finding(
            "encounter_loop", "high" if encounter_to_drill_rate < 10 else "medium",
            f"Only {encounter_to_drill_rate}% of looked-up words get drilled",
            f"{drilled_encounters} of {total_encounters} encountered words were subsequently drilled. "
            "The encounter→drill pipeline is leaking.",
            "Ensure the scheduler prioritizes recently-encountered vocabulary.",
            (
                f"Encounter→drill rate: {encounter_to_drill_rate}%.\n\n"
                f"1. Check {_FILE_MAP['scheduler']} — encounter boost logic\n"
                "2. Query: SELECT ve.hanzi, ve.created_at, "
                "(SELECT MIN(re.created_at) FROM review_event re "
                "WHERE re.content_item_id = ve.content_item_id AND re.created_at > ve.created_at) as first_drill "
                "FROM vocab_encounter ve WHERE ve.looked_up = 1 ORDER BY ve.created_at DESC LIMIT 20"
            ),
            "Learning: encounters without follow-up drills don't consolidate",
            _f("scheduler"),
        ))

    # Encounter→first_drill latency
    latency = _safe_query(conn, """
        SELECT AVG(julianday(re_min.min_drill) - julianday(ve.created_at)) as avg_days
        FROM vocab_encounter ve
        JOIN (
            SELECT content_item_id, MIN(created_at) as min_drill
            FROM review_event
            GROUP BY content_item_id
        ) re_min ON ve.content_item_id = re_min.content_item_id
        WHERE ve.looked_up = 1
          AND re_min.min_drill > ve.created_at
    """)
    if latency and latency["avg_days"] is not None:
        avg_days = round(latency["avg_days"], 1)
        if avg_days > 7:
            findings.append(_finding(
                "encounter_loop", "medium",
                f"Median encounter→first drill latency: {avg_days} days",
                f"On average, it takes {avg_days} days from encountering a word to first drilling it. "
                "Research suggests optimal consolidation within 24-48 hours.",
                "Boost encounter scheduling priority to drill within 1-2 days.",
                (
                    f"Encounter→drill latency: {avg_days} days.\n\n"
                    f"1. Check {_FILE_MAP['scheduler']} — encounter boost scheduling window\n"
                    "2. Consider adding same-day encounter review"
                ),
                "Learning: delayed drilling wastes the encounter memory trace",
                _f("scheduler"),
            ))

    return findings


def analyze_learner_archetypes(conn) -> list[dict]:
    """Classify users into archetypes and generate findings for at-risk groups."""
    findings = []

    user_stats = _safe_query_all(conn, """
        SELECT u.id,
               COUNT(DISTINCT s.id) * 1.0 /
                   MAX(1, (julianday('now') - julianday(MIN(s.started_at))) / 7.0) as sessions_per_week,
               AVG(CASE WHEN r.correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy,
               SUM(CASE WHEN strftime('%%w', s.started_at) IN ('0', '6') THEN 1 ELSE 0 END) * 1.0 /
                   MAX(1, COUNT(DISTINCT s.id)) as weekend_pct,
               julianday('now') - julianday(MAX(s.started_at)) as days_since_last
        FROM user u
        LEFT JOIN session_log s ON u.id = s.user_id
        LEFT JOIN review_event r ON u.id = r.user_id
        WHERE u.created_at <= datetime('now', '-7 days')
        GROUP BY u.id
        HAVING COUNT(DISTINCT s.id) > 0
    """)

    if not user_stats or len(user_stats) < 5:
        return findings

    archetypes = {"sprint": [], "steady": [], "weekend_warrior": [],
                  "struggling": [], "lapsed": []}

    for user in user_stats:
        spw = user["sessions_per_week"] or 0
        acc = user["accuracy"] or 0
        wpct = user["weekend_pct"] or 0
        dsl = user["days_since_last"] or 0

        rules = _ARCHETYPE_RULES
        if dsl >= rules["lapsed"]["days_since_last_min"]:
            archetypes["lapsed"].append(user["id"])
        elif acc <= rules["struggling"]["accuracy_max"] and spw >= rules["struggling"]["sessions_per_week_min"]:
            archetypes["struggling"].append(user["id"])
        elif wpct >= rules["weekend_warrior"]["weekend_pct_min"] and spw >= rules["weekend_warrior"]["sessions_per_week_min"]:
            archetypes["weekend_warrior"].append(user["id"])
        elif spw >= rules["sprint"]["sessions_per_week_min"] and acc >= rules["sprint"]["accuracy_min"]:
            archetypes["sprint"].append(user["id"])
        elif spw >= rules["steady"]["sessions_per_week_min"] and acc >= rules["steady"]["accuracy_min"]:
            archetypes["steady"].append(user["id"])

    total_users = len(user_stats)

    if archetypes["struggling"]:
        n = len(archetypes["struggling"])
        pct = round(n / total_users * 100, 1)
        findings.append(_finding(
            "engagement", "high" if pct > 20 else "medium",
            f"{n} struggling users ({pct}%) — active but <50% accuracy",
            f"{n} users are actively learning but scoring below 50% accuracy. "
            "They need scaffolding or easier content to build confidence.",
            "Add scaffolding for struggling users: reduce item count, add hints, lower difficulty.",
            f"{n} struggling users.\n\n1. Check scheduler difficulty settings\n2. Add adaptive difficulty",
            "Retention: struggling users churn 3x faster than steady learners",
            _f("scheduler"),
        ))

    if archetypes["lapsed"]:
        n = len(archetypes["lapsed"])
        pct = round(n / total_users * 100, 1)
        findings.append(_finding(
            "retention", "high" if pct > 30 else "medium",
            f"{n} lapsed users ({pct}%) — no activity for 14+ days",
            f"{n} users haven't opened a session in 14+ days.",
            "Send re-engagement communications. Consider a 'welcome back' session design.",
            f"{n} lapsed users.\n\n1. Check re-engagement email triggers\n2. Design welcome-back flow",
            "Retention: lapsed users rarely return without intervention",
            _f("scheduler"),
        ))

    return findings


def analyze_learner_value_stream(conn) -> list[dict]:
    """Lean Value Stream Mapping: measure the learner acquisition funnel.

    signup → first_session → activated (3+ sessions) → d7_retained → d30_retained.
    Identifies the biggest drop-off point.
    """
    findings = []

    total_signups = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE created_at <= datetime('now', '-30 days')
    """)
    if not total_signups or total_signups < 5:
        return findings

    first_session = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON u.id = s.user_id
        WHERE u.created_at <= datetime('now', '-30 days')
    """)
    activated = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON u.id = s.user_id
        WHERE u.created_at <= datetime('now', '-30 days')
        GROUP BY u.id HAVING COUNT(DISTINCT s.id) >= 3
    """)
    # activated is a count from a subquery — need different approach
    activated = _safe_scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT u.id FROM user u
            JOIN session_log s ON u.id = s.user_id
            WHERE u.created_at <= datetime('now', '-30 days')
            GROUP BY u.id HAVING COUNT(DISTINCT s.id) >= 3
        )
    """)
    d7_retained = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON u.id = s.user_id
        WHERE u.created_at <= datetime('now', '-30 days')
          AND s.started_at >= datetime(u.created_at, '+7 days')
    """)
    d30_retained = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON u.id = s.user_id
        WHERE u.created_at <= datetime('now', '-60 days')
          AND s.started_at >= datetime(u.created_at, '+30 days')
    """)

    funnel = [
        ("signup", total_signups or 0),
        ("first_session", first_session or 0),
        ("activated_3_sessions", activated or 0),
        ("d7_retained", d7_retained or 0),
        ("d30_retained", d30_retained or 0),
    ]

    # Find biggest drop-off
    biggest_drop_stage = None
    biggest_drop_pct = 0
    for i in range(len(funnel) - 1):
        stage_name, stage_count = funnel[i]
        next_name, next_count = funnel[i + 1]
        if stage_count > 0:
            drop_pct = round((1 - next_count / stage_count) * 100, 1)
            if drop_pct > biggest_drop_pct:
                biggest_drop_pct = drop_pct
                biggest_drop_stage = f"{stage_name} → {next_name}"

    if biggest_drop_stage and biggest_drop_pct > 30:
        funnel_str = " → ".join(f"{name}:{count}" for name, count in funnel)
        findings.append(_finding(
            "onboarding", "high" if biggest_drop_pct > 60 else "medium",
            f"Funnel bottleneck: {biggest_drop_pct}% drop at {biggest_drop_stage}",
            f"Learner funnel: {funnel_str}. "
            f"The biggest drop-off ({biggest_drop_pct}%) occurs at {biggest_drop_stage}.",
            f"Focus improvement efforts on the {biggest_drop_stage} transition.",
            f"VSM funnel: {funnel_str}\nBottleneck: {biggest_drop_stage} ({biggest_drop_pct}% drop)",
            "Lean: VSM identifies where value is lost in the learner journey",
            _f("onboarding_routes", "scheduler"),
        ))

    return findings


def analyze_learning_waste(conn) -> list[dict]:
    """Lean 7 wastes mapped to learning context.

    1. Overproduction: drilling mastered items (accuracy>95% for 3+ sessions)
    2. Inventory: items in learning state >60 days without mastery
    3. Over-processing: items reviewed far more than SRS schedule requires
    4. Defects: error rate by drill type
    5. Motion: user corrections/retries per drill
    6. Waiting: gap between sessions vs ideal spacing
    7. Transport: (not measurable from data)
    """
    findings = []
    wastes = []

    # 1. Overproduction — drilling already-mastered items
    overproduced = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT p.content_item_id)
        FROM progress p
        JOIN review_event r ON p.content_item_id = r.content_item_id
            AND p.user_id = r.user_id
        WHERE p.mastery_stage = 'stable'
          AND r.created_at >= datetime('now', '-14 days')
          AND r.correct = 1
        GROUP BY p.content_item_id, p.user_id
        HAVING COUNT(*) >= 3 AND AVG(CASE WHEN r.correct=1 THEN 1.0 ELSE 0.0 END) > 0.95
    """)
    # Use subquery for proper count
    overproduced = _safe_scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT p.content_item_id
            FROM progress p
            JOIN review_event r ON p.content_item_id = r.content_item_id
                AND p.user_id = r.user_id
            WHERE p.mastery_stage = 'stable'
              AND r.created_at >= datetime('now', '-14 days')
            GROUP BY p.content_item_id, p.user_id
            HAVING COUNT(*) >= 3 AND AVG(CASE WHEN r.correct=1 THEN 1.0 ELSE 0.0 END) > 0.95
        )
    """)
    if overproduced and overproduced > 5:
        wastes.append(("overproduction", overproduced,
                       f"{overproduced} mastered items still being drilled at >95% accuracy"))

    # 2. Inventory — items stuck in learning >60 days
    stuck_inventory = _safe_scalar(conn, """
        SELECT COUNT(*) FROM progress
        WHERE mastery_stage IN ('learning', 'stabilizing')
          AND last_review_date <= datetime('now', '-60 days')
    """)
    if stuck_inventory and stuck_inventory > 10:
        wastes.append(("inventory", stuck_inventory,
                       f"{stuck_inventory} items stuck in learning for >60 days"))

    # 3. Over-processing — items with far more reviews than needed
    over_reviewed = _safe_scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT p.content_item_id, p.repetitions, p.interval_days
            FROM progress p
            WHERE p.mastery_stage = 'stable'
              AND p.repetitions > p.interval_days * 2
        )
    """)
    if over_reviewed and over_reviewed > 10:
        wastes.append(("over_processing", over_reviewed,
                       f"{over_reviewed} stable items with excessive review count"))

    # 4. Defects — error rate by drill type
    drill_errors = _safe_query_all(conn, """
        SELECT drill_type,
               COUNT(*) as total,
               SUM(CASE WHEN correct=0 THEN 1 ELSE 0 END) as errors
        FROM review_event
        WHERE created_at >= datetime('now', '-14 days')
        GROUP BY drill_type
        HAVING total >= 10
        ORDER BY errors * 1.0 / total DESC
        LIMIT 3
    """)
    high_error_drills = [d for d in (drill_errors or [])
                         if d["total"] > 0 and (d["errors"] or 0) / d["total"] > 0.4]
    if high_error_drills:
        wastes.append(("defects", len(high_error_drills),
                       f"{len(high_error_drills)} drill types with >40% error rate"))

    # Sort by magnitude and report top 3
    wastes.sort(key=lambda w: -w[1])
    if wastes:
        top = wastes[:3]
        waste_summary = "; ".join(f"{w[0]}: {w[2]}" for w in top)
        findings.append(_finding(
            "scheduler_audit", "high" if top[0][1] > 20 else "medium",
            f"Learning waste detected: {', '.join(w[0] for w in top)}",
            f"Lean waste analysis: {waste_summary}.",
            "Address top waste sources to improve learning efficiency.",
            f"Learning waste: {waste_summary}\n\n"
            f"1. Check {_FILE_MAP['scheduler']} — SRS interval logic\n"
            "2. Remove mastered items from active review queue",
            "Lean: waste elimination improves throughput without adding resources",
            _f("scheduler"),
        ))

    return findings


def analyze_session_queue(conn) -> list[dict]:
    """Operations Research: model review queue as M/M/1 system using Little's Law.

    λ = arrival rate (new items entering review per day)
    μ = service rate (items reviewed per session × sessions per day)
    ρ = λ/μ (utilization). If ρ ≥ 1.0, queue is unstable.
    L = λW (Little's Law: items in queue = arrival rate × avg wait time).
    """
    findings = []

    # λ: new items entering review per day (last 14 days)
    new_items = _safe_query(conn, """
        SELECT COUNT(*) as cnt,
               (julianday('now') - julianday(MIN(created_at))) as days_span
        FROM progress
        WHERE created_at >= datetime('now', '-14 days')
          AND mastery_stage != 'unseen'
    """)
    if not new_items or not new_items["days_span"] or new_items["days_span"] < 1:
        return findings

    lambda_rate = (new_items["cnt"] or 0) / max(1, new_items["days_span"])

    # μ: items reviewed per day (last 14 days)
    reviews = _safe_query(conn, """
        SELECT COUNT(*) as cnt,
               (julianday('now') - julianday(MIN(created_at))) as days_span
        FROM review_event
        WHERE created_at >= datetime('now', '-14 days')
    """)
    if not reviews or not reviews["days_span"] or reviews["days_span"] < 1:
        return findings

    mu_rate = (reviews["cnt"] or 0) / max(1, reviews["days_span"])

    if mu_rate == 0:
        return findings

    rho = lambda_rate / mu_rate  # utilization

    # Current queue depth
    queue_depth = _safe_scalar(conn, """
        SELECT COUNT(*) FROM progress
        WHERE mastery_stage IN ('learning', 'stabilizing')
          AND next_review_date <= datetime('now')
    """)

    # Little's Law: L = λW → W = L/λ (avg wait time per item)
    avg_wait = round(queue_depth / lambda_rate, 1) if lambda_rate > 0 and queue_depth else 0

    # Optimal batch size (newsvendor: balance under- vs over-review)
    # Simple heuristic: items per session = μ / sessions_per_day
    sessions_per_day = _safe_scalar(conn, """
        SELECT COUNT(*) * 1.0 / MAX(1, julianday('now') - julianday(MIN(started_at)))
        FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
    """)
    optimal_batch = round(mu_rate / max(0.1, sessions_per_day or 1), 0)

    if rho >= 1.0:
        findings.append(_finding(
            "scheduler_audit", "critical" if rho > 1.5 else "high",
            f"Review queue unstable: ρ={round(rho, 2)} (arrival > service rate)",
            f"Queue utilization ρ = {round(rho, 2)} (λ={round(lambda_rate, 1)}/day, "
            f"μ={round(mu_rate, 1)}/day). Queue will grow unbounded. "
            f"Current backlog: {queue_depth or 0} items, avg wait: {avg_wait} days.",
            "Either reduce new item introduction rate or increase review throughput.",
            (
                f"Queue model: λ={round(lambda_rate, 1)}, μ={round(mu_rate, 1)}, ρ={round(rho, 2)}\n"
                f"Backlog: {queue_depth or 0}, Wait: {avg_wait}d\n\n"
                f"1. Check {_FILE_MAP['scheduler']} — new item introduction rate\n"
                "2. Consider increasing session length or frequency"
            ),
            "Operations Research: unstable queues cause exponential backlog growth",
            _f("scheduler"),
        ))
    elif rho > 0.8:
        findings.append(_finding(
            "scheduler_audit", "medium",
            f"Review queue nearing capacity: ρ={round(rho, 2)}",
            f"Queue utilization at {round(rho * 100, 1)}%. "
            f"Sustainable but buffer is thin. Optimal batch size: {int(optimal_batch)} items/session.",
            "Monitor queue depth and reduce new introductions if ρ exceeds 0.9.",
            f"Queue utilization: {round(rho * 100, 1)}%",
            "Operations Research: high utilization increases wait times nonlinearly",
            _f("scheduler"),
        ))

    return findings


ANALYZERS = [
    analyze_srs_funnel,
    analyze_error_taxonomy,
    analyze_cross_modality_transfer,
    analyze_curriculum_coverage,
    analyze_hsk_cliff,
    analyze_tone_phonology,
    analyze_scheduler_decisions,
    analyze_encounter_feedback_loop,
    analyze_learner_archetypes,
    analyze_learner_value_stream,
    analyze_learning_waste,
    analyze_session_queue,
]
