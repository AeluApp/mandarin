"""Modality adaptation layer — extends core-loop analyzers to non-core features.

93% of aelu's analyzers treat the SRS drill loop as monolithic. This module
runs the same business, UX, engagement, learning science, and anti-Goodhart
analyses PER MODALITY — reading, listening, conversation, grammar, media —
surfacing problems invisible in the aggregate.

No existing analyzers are modified. Findings emit to existing dimensions
(retention, drill_quality, ux, engagement, etc.) with modality-specific
titles so the prescription layer can match on keywords.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)

# Drill types grouped by modality for consistent classification
_MODALITY_BUCKETS = {
    "recognition": ("mc", "reverse_mc"),
    "production": ("ime_type", "hanzi_to_pinyin", "english_to_pinyin"),
    "listening": ("listening_gist", "listening_detail", "listening_tone",
                  "listening_dictation", "listening_passage"),
    "conversation": ("dialogue",),
    "grammar": ("intuition", "complement", "ba_bei", "error_correction",
                "measure_word", "measure_word_cloze", "measure_word_disc"),
    "tone": ("tone", "tone_sandhi", "minimal_pair", "sandhi_contrast"),
    "media": ("media_comprehension",),
}


def _bucket_for_drill_type(dt: str) -> str:
    for bucket, types in _MODALITY_BUCKETS.items():
        if dt in types:
            return bucket
    return "other"


# ═══════════════════════════════════════════════════════════════════════
# TIER 1: CORE BUSINESS IMPACT
# ═══════════════════════════════════════════════════════════════════════


def _analyze_retention_by_modality(conn) -> list[dict]:
    """D7 retention segmented by which modality the user engaged with first."""
    findings = []
    try:
        # Users with first_session_at, eligible for D7 measurement
        users = _safe_query_all(conn, """
            SELECT u.id, u.first_session_at,
                   (SELECT COUNT(*) FROM session_log sl2
                    WHERE sl2.user_id = u.id
                      AND sl2.completed_at >= datetime(u.first_session_at, '+7 days')) as d7_sessions,
                   (SELECT COUNT(*) FROM reading_progress rp
                    WHERE rp.user_id = u.id
                      AND rp.completed_at <= datetime(u.first_session_at, '+3 days')) as early_reading,
                   (SELECT COUNT(*) FROM listening_progress lp
                    WHERE lp.user_id = u.id
                      AND lp.completed_at <= datetime(u.first_session_at, '+3 days')) as early_listening
            FROM user u
            WHERE u.is_admin = 0
              AND u.first_session_at IS NOT NULL
              AND u.first_session_at <= datetime('now', '-8 days')
        """)

        if not users or len(users) < 10:
            return findings

        # Segment by early modality engagement
        segments = {"reading": [], "listening": [], "neither": []}
        for u in users:
            retained = 1 if (u["d7_sessions"] or 0) > 0 else 0
            if (u["early_reading"] or 0) > 0:
                segments["reading"].append(retained)
            if (u["early_listening"] or 0) > 0:
                segments["listening"].append(retained)
            if (u["early_reading"] or 0) == 0 and (u["early_listening"] or 0) == 0:
                segments["neither"].append(retained)

        # Compare retention rates
        rates = {}
        for seg, values in segments.items():
            if len(values) >= 5:
                rates[seg] = sum(values) / len(values) * 100

        if len(rates) >= 2:
            best_seg = max(rates, key=rates.get)
            worst_seg = min(rates, key=rates.get)
            gap = rates[best_seg] - rates[worst_seg]

            if gap > 20:
                findings.append(_finding(
                    "retention", "high",
                    f"Retention gap by modality: {best_seg} {rates[best_seg]:.0f}% vs {worst_seg} {rates[worst_seg]:.0f}% (D7)",
                    f"D7 retention by early modality engagement: "
                    + ", ".join(f"{s}: {r:.0f}% (n={len(segments[s])})" for s, r in rates.items())
                    + f". {gap:.0f}pp gap between best and worst.",
                    f"Investigate why {worst_seg}-first users retain worse. "
                    f"Consider onboarding changes to expose {best_seg} earlier.",
                    f"Compare {worst_seg} vs {best_seg} onboarding flow.",
                    "Modality-first engagement predicts retention.",
                    ["mandarin/web/onboarding_routes.py", "mandarin/scheduler.py"],
                ))
    except Exception as e:
        logger.debug("Retention by modality failed: %s", e)
    return findings


def _analyze_conversion_by_modality(conn) -> list[dict]:
    """Which modalities do paid converters engage with vs churned users?"""
    findings = []
    try:
        paid_users = _safe_query_all(conn, """
            SELECT id FROM user
            WHERE subscription_tier IN ('paid', 'premium') AND is_admin = 0
        """)
        churned_users = _safe_query_all(conn, """
            SELECT DISTINCT user_id as id FROM lifecycle_event
            WHERE event_type = 'cancellation_completed'
        """)

        if not paid_users or len(paid_users) < 3:
            return findings

        def modality_profile(user_ids):
            if not user_ids:
                return {}
            placeholders = ",".join("?" * len(user_ids))
            ids = [u["id"] for u in user_ids]
            profile = {}
            profile["reading"] = _safe_scalar(conn, f"""
                SELECT COUNT(DISTINCT user_id) FROM reading_progress
                WHERE user_id IN ({placeholders})
            """, ids, default=0)
            profile["listening"] = _safe_scalar(conn, f"""
                SELECT COUNT(DISTINCT user_id) FROM listening_progress
                WHERE user_id IN ({placeholders})
            """, ids, default=0)
            profile["conversation"] = _safe_scalar(conn, f"""
                SELECT COUNT(DISTINCT user_id) FROM review_event
                WHERE user_id IN ({placeholders}) AND drill_type = 'dialogue'
            """, ids, default=0)
            return {k: v / len(user_ids) * 100 for k, v in profile.items()}

        paid_profile = modality_profile(paid_users)
        churned_profile = modality_profile(churned_users) if churned_users else {}

        for modality in ["reading", "listening", "conversation"]:
            paid_pct = paid_profile.get(modality, 0)
            churned_pct = churned_profile.get(modality, 0)
            if paid_pct > churned_pct + 30 and paid_pct > 50:
                findings.append(_finding(
                    "profitability", "medium",
                    f"{modality.title()} drives conversion: {paid_pct:.0f}% of paid vs {churned_pct:.0f}% of churned",
                    f"{paid_pct:.0f}% of paid users engaged with {modality} vs "
                    f"{churned_pct:.0f}% of churned users. {modality.title()} engagement "
                    f"strongly correlates with conversion.",
                    f"Prioritize {modality} in onboarding and free-tier access. "
                    f"Ensure {modality} is discoverable early in the learner journey.",
                    f"Increase {modality} visibility in scheduler and onboarding.",
                    f"{modality.title()} engagement predicts paid conversion.",
                    ["mandarin/scheduler.py", "mandarin/tier_gate.py"],
                ))
    except Exception as e:
        logger.debug("Conversion by modality failed: %s", e)
    return findings


def _analyze_drill_quality_by_modality(conn) -> list[dict]:
    """Accuracy and skip rate by modality bucket."""
    findings = []
    try:
        rows = _safe_query_all(conn, """
            SELECT drill_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct_count,
                   SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) as skip_count
            FROM review_event
            WHERE reviewed_at >= datetime('now', '-14 days')
            GROUP BY drill_type
            HAVING total >= 5
        """)
        if not rows:
            return findings

        # Aggregate by modality bucket
        buckets = {}
        for r in rows:
            bucket = _bucket_for_drill_type(r["drill_type"])
            if bucket == "other":
                continue
            if bucket not in buckets:
                buckets[bucket] = {"total": 0, "correct": 0, "skipped": 0}
            buckets[bucket]["total"] += r["total"]
            buckets[bucket]["correct"] += r["correct_count"]
            buckets[bucket]["skipped"] += r["skip_count"]

        if len(buckets) < 2:
            return findings

        overall_total = sum(b["total"] for b in buckets.values())
        overall_accuracy = sum(b["correct"] for b in buckets.values()) / max(1, overall_total)

        for bucket, stats in buckets.items():
            if stats["total"] < 10:
                continue
            accuracy = stats["correct"] / stats["total"]
            skip_rate = stats["skipped"] / stats["total"]

            if accuracy < overall_accuracy - 0.15:
                gap = (overall_accuracy - accuracy) * 100
                findings.append(_finding(
                    "drill_quality", "medium",
                    f"{bucket.title()} accuracy {accuracy*100:.0f}% — {gap:.0f}pp below overall {overall_accuracy*100:.0f}%",
                    f"{bucket.title()} drills: {accuracy*100:.0f}% accuracy "
                    f"({stats['correct']}/{stats['total']}) vs {overall_accuracy*100:.0f}% overall. "
                    f"This modality is significantly harder.",
                    f"Review {bucket} drill difficulty and scaffolding.",
                    f"Check {bucket} drill design and difficulty calibration.",
                    f"{bucket.title()} is a quality outlier.",
                    ["mandarin/drills/", "mandarin/scheduler.py"],
                ))

            if skip_rate > 0.15:
                findings.append(_finding(
                    "drill_quality", "medium",
                    f"{bucket.title()} skip rate {skip_rate*100:.0f}% — learners avoiding this modality",
                    f"{bucket.title()} drills: {skip_rate*100:.0f}% skip rate "
                    f"({stats['skipped']}/{stats['total']}). Learners are voting "
                    f"with their feet.",
                    f"Reduce {bucket} difficulty or improve instructions.",
                    f"Investigate why learners skip {bucket} drills.",
                    f"High skip rate in {bucket} signals usability problem.",
                    ["mandarin/drills/", "mandarin/scheduler.py"],
                ))
    except Exception as e:
        logger.debug("Drill quality by modality failed: %s", e)
    return findings


def _analyze_engagement_by_modality(conn) -> list[dict]:
    """Flag modalities that active users have never tried."""
    findings = []
    try:
        active = _safe_query_all(conn, """
            SELECT u.id FROM user u
            WHERE u.is_admin = 0
              AND (SELECT COUNT(*) FROM session_log sl
                   WHERE sl.user_id = u.id AND sl.items_completed > 0) >= 10
        """)
        if not active or len(active) < 5:
            return findings

        total = len(active)
        ids = [u["id"] for u in active]
        placeholders = ",".join("?" * len(ids))

        checks = [
            ("reading", f"SELECT COUNT(DISTINCT user_id) FROM reading_progress WHERE user_id IN ({placeholders})"),
            ("listening", f"SELECT COUNT(DISTINCT user_id) FROM listening_progress WHERE user_id IN ({placeholders})"),
            ("conversation", f"SELECT COUNT(DISTINCT user_id) FROM review_event WHERE drill_type='dialogue' AND user_id IN ({placeholders})"),
            ("grammar", f"SELECT COUNT(DISTINCT user_id) FROM grammar_progress WHERE user_id IN ({placeholders})"),
        ]

        for modality, sql in checks:
            engaged = _safe_scalar(conn, sql, ids, default=0)
            never_pct = (total - engaged) / total * 100
            if never_pct > 40:
                findings.append(_finding(
                    "engagement", "medium",
                    f"{never_pct:.0f}% of active users have never tried {modality}",
                    f"{total - engaged}/{total} users with 10+ sessions have zero "
                    f"{modality} engagement. DOCTRINE §4 requires modality integration.",
                    f"Surface {modality} in the first 5 sessions. Consider adding "
                    f"a nudge after session 5.",
                    f"Increase {modality} visibility in scheduler and onboarding.",
                    f"{modality.title()} has a discovery problem.",
                    ["mandarin/scheduler.py", "mandarin/nudge_registry.py"],
                ))
    except Exception as e:
        logger.debug("Engagement by modality failed: %s", e)
    return findings


def _analyze_churn_risk_by_modality(conn) -> list[dict]:
    """Do at-risk users tend to be mono-modal?"""
    findings = []
    try:
        # Get users with sessions in last 30 days
        users = _safe_query_all(conn, """
            SELECT u.id,
                   julianday('now') - julianday(MAX(sl.completed_at)) as days_inactive,
                   (SELECT COUNT(DISTINCT drill_type) FROM review_event re
                    WHERE re.user_id = u.id) as drill_type_count,
                   (SELECT COUNT(*) FROM reading_progress rp WHERE rp.user_id = u.id) as reading_count,
                   (SELECT COUNT(*) FROM listening_progress lp WHERE lp.user_id = u.id) as listening_count
            FROM user u
            JOIN session_log sl ON u.id = sl.user_id
            WHERE u.is_admin = 0
            GROUP BY u.id
            HAVING days_inactive IS NOT NULL
        """)
        if not users or len(users) < 10:
            return findings

        at_risk = [u for u in users if (u["days_inactive"] or 0) >= 7]
        retained = [u for u in users if (u["days_inactive"] or 0) < 3]

        if not at_risk or not retained:
            return findings

        def avg_modalities(user_list):
            modality_counts = []
            for u in user_list:
                count = 0
                if (u["reading_count"] or 0) > 0: count += 1
                if (u["listening_count"] or 0) > 0: count += 1
                count += min(3, (u["drill_type_count"] or 0) // 3)  # Rough bucket count
                modality_counts.append(count)
            return sum(modality_counts) / len(modality_counts) if modality_counts else 0

        risk_avg = avg_modalities(at_risk)
        retained_avg = avg_modalities(retained)

        if retained_avg > risk_avg + 0.8:
            findings.append(_finding(
                "retention", "medium",
                f"Mono-modal users churn more: at-risk {risk_avg:.1f} modalities vs retained {retained_avg:.1f}",
                f"At-risk users (inactive 7+ days, n={len(at_risk)}) engage with "
                f"{risk_avg:.1f} modalities on average. Retained users (active in "
                f"last 3 days, n={len(retained)}) engage with {retained_avg:.1f}. "
                f"Broader modality engagement correlates with retention.",
                "Encourage modality exploration. Users stuck in one type of "
                "practice are more likely to churn.",
                "Add modality exploration nudge to reduce mono-modal behavior.",
                "Mono-modal learning predicts churn.",
                ["mandarin/nudge_registry.py", "mandarin/scheduler.py"],
            ))
    except Exception as e:
        logger.debug("Churn risk by modality failed: %s", e)
    return findings


# ═══════════════════════════════════════════════════════════════════════
# TIER 2: UX/FLOW IMPACT
# ═══════════════════════════════════════════════════════════════════════


def _analyze_frustration_by_modality(conn) -> list[dict]:
    """Error streaks by modality — which modality frustrates learners most?"""
    findings = []
    try:
        rows = _safe_query_all(conn, """
            SELECT drill_type, COUNT(*) as errors
            FROM review_event
            WHERE correct = 0
              AND reviewed_at >= datetime('now', '-14 days')
            GROUP BY drill_type
            HAVING errors >= 5
        """)
        if not rows:
            return findings

        total_drills = _safe_scalar(conn, """
            SELECT COUNT(*) FROM review_event
            WHERE reviewed_at >= datetime('now', '-14 days')
        """, default=1)

        buckets = {}
        for r in rows:
            bucket = _bucket_for_drill_type(r["drill_type"])
            if bucket == "other":
                continue
            buckets[bucket] = buckets.get(bucket, 0) + r["errors"]

        bucket_totals = {}
        all_rows = _safe_query_all(conn, """
            SELECT drill_type, COUNT(*) as total
            FROM review_event WHERE reviewed_at >= datetime('now', '-14 days')
            GROUP BY drill_type
        """)
        for r in (all_rows or []):
            b = _bucket_for_drill_type(r["drill_type"])
            if b != "other":
                bucket_totals[b] = bucket_totals.get(b, 0) + r["total"]

        overall_error_rate = sum(buckets.values()) / max(1, total_drills)

        for bucket, errors in buckets.items():
            total = bucket_totals.get(bucket, 1)
            error_rate = errors / total
            if error_rate > overall_error_rate * 2 and total >= 20:
                findings.append(_finding(
                    "frustration", "medium",
                    f"{bucket.title()} error rate {error_rate*100:.0f}% — 2x+ above overall {overall_error_rate*100:.0f}%",
                    f"{bucket.title()} drills have {error_rate*100:.0f}% error rate "
                    f"({errors}/{total}) vs {overall_error_rate*100:.0f}% overall. "
                    f"This modality is a frustration hotspot.",
                    f"Review {bucket} difficulty calibration. Consider adding "
                    f"scaffolding, hints, or near-miss feedback for {bucket} drills.",
                    f"Investigate high error rate in {bucket} drills.",
                    f"{bucket.title()} causes disproportionate learner frustration.",
                    ["mandarin/drills/", "mandarin/scheduler.py"],
                ))
    except Exception as e:
        logger.debug("Frustration by modality failed: %s", e)
    return findings


def _analyze_flow_by_modality(conn) -> list[dict]:
    """Session block completion by type — which blocks get abandoned?"""
    findings = []
    try:
        # Approximate block completion from session_log modality_counts
        sessions = _safe_query_all(conn, """
            SELECT modality_counts, items_completed, items_planned, early_exit
            FROM session_log
            WHERE completed_at >= datetime('now', '-14 days')
              AND items_planned > 0
              AND modality_counts IS NOT NULL
        """)
        if not sessions or len(sessions) < 10:
            return findings

        # Count sessions with/without reading and listening blocks
        has_reading = sum(1 for s in sessions
                         if s["modality_counts"] and "reading" in str(s["modality_counts"]))
        has_listening = sum(1 for s in sessions
                           if s["modality_counts"] and "listening" in str(s["modality_counts"]))
        early_exits = sum(1 for s in sessions if s["early_exit"])

        total = len(sessions)
        if total > 0 and early_exits / total > 0.3:
            # Check if early exits correlate with specific blocks
            early_with_reading = sum(
                1 for s in sessions
                if s["early_exit"] and s["modality_counts"]
                and "reading" in str(s["modality_counts"])
            )
            if has_reading > 0 and early_with_reading / max(1, has_reading) > 0.4:
                findings.append(_finding(
                    "ux", "medium",
                    f"Reading blocks correlate with early exits ({early_with_reading}/{has_reading} = {early_with_reading/has_reading*100:.0f}%)",
                    f"Sessions with reading blocks have {early_with_reading/has_reading*100:.0f}% "
                    f"early exit rate vs {early_exits/total*100:.0f}% overall.",
                    "Reading blocks may be too long or too difficult. Consider "
                    "reducing block time or offering a skip option.",
                    "Check reading block target_seconds in scheduler.py.",
                    "Reading blocks may be causing session abandonment.",
                    ["mandarin/scheduler.py"],
                ))
    except Exception as e:
        logger.debug("Flow by modality failed: %s", e)
    return findings


def _analyze_platform_modality(conn) -> list[dict]:
    """Platform × modality interaction — do iOS/Android/web differ by feature?"""
    findings = []
    try:
        platforms = _safe_query_all(conn, """
            SELECT client_platform, COUNT(DISTINCT user_id) as users
            FROM session_log
            WHERE completed_at >= datetime('now', '-30 days')
              AND client_platform IS NOT NULL
            GROUP BY client_platform
            HAVING users >= 3
        """)
        if not platforms or len(platforms) < 2:
            return findings

        for p in platforms:
            platform = p["client_platform"]
            reading = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT rp.user_id) FROM reading_progress rp
                JOIN session_log sl ON rp.user_id = sl.user_id
                WHERE sl.client_platform = ?
                  AND rp.completed_at >= datetime('now', '-30 days')
            """, (platform,), default=0)
            listening = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT lp.user_id) FROM listening_progress lp
                JOIN session_log sl ON lp.user_id = sl.user_id
                WHERE sl.client_platform = ?
                  AND lp.completed_at >= datetime('now', '-30 days')
            """, (platform,), default=0)

            if p["users"] >= 5 and reading == 0 and listening > 0:
                findings.append(_finding(
                    "platform", "medium",
                    f"{platform}: zero reading engagement but {listening} listening users",
                    f"Platform '{platform}' has {p['users']} active users, "
                    f"{listening} use listening but zero use reading. This may "
                    f"indicate a platform-specific bug or UI issue with reading.",
                    f"Check reading feature on {platform}. Is it accessible? "
                    f"Does the UI render correctly?",
                    f"Test reading feature on {platform} platform.",
                    f"Platform-specific modality gap on {platform}.",
                    ["mandarin/web/static/app.js", "flutter_app/"],
                ))
            elif p["users"] >= 5 and listening == 0 and reading > 0:
                findings.append(_finding(
                    "platform", "medium",
                    f"{platform}: zero listening engagement but {reading} reading users",
                    f"Platform '{platform}' has {p['users']} active users, "
                    f"{reading} use reading but zero use listening.",
                    f"Check listening feature on {platform}.",
                    f"Test listening feature on {platform} platform.",
                    f"Platform-specific modality gap on {platform}.",
                    ["mandarin/web/static/app.js", "flutter_app/"],
                ))
    except Exception as e:
        logger.debug("Platform modality failed: %s", e)
    return findings


def _analyze_timing_by_modality(conn) -> list[dict]:
    """Response time per modality — which modalities take longest?"""
    findings = []
    try:
        rows = _safe_query_all(conn, """
            SELECT drill_type,
                   AVG(response_time_ms) as avg_ms,
                   COUNT(*) as total
            FROM review_event
            WHERE reviewed_at >= datetime('now', '-14 days')
              AND response_time_ms IS NOT NULL
              AND response_time_ms > 0
            GROUP BY drill_type
            HAVING total >= 10
        """)
        if not rows:
            return findings

        buckets = {}
        for r in rows:
            bucket = _bucket_for_drill_type(r["drill_type"])
            if bucket == "other":
                continue
            if bucket not in buckets:
                buckets[bucket] = {"total_ms": 0, "count": 0}
            buckets[bucket]["total_ms"] += (r["avg_ms"] or 0) * r["total"]
            buckets[bucket]["count"] += r["total"]

        if len(buckets) < 2:
            return findings

        overall_avg = sum(b["total_ms"] for b in buckets.values()) / max(1, sum(b["count"] for b in buckets.values()))

        for bucket, stats in buckets.items():
            if stats["count"] < 10:
                continue
            avg = stats["total_ms"] / stats["count"]
            if avg > overall_avg * 2.5 and avg > 10000:  # >2.5x and >10s
                findings.append(_finding(
                    "ux", "low",
                    f"{bucket.title()} response time {avg/1000:.1f}s — 2.5x+ above overall {overall_avg/1000:.1f}s",
                    f"{bucket.title()} drills average {avg/1000:.1f}s response time "
                    f"vs {overall_avg/1000:.1f}s overall. Slow response time may "
                    f"indicate difficulty or confusion, not thoughtfulness.",
                    f"Add scaffolding to {bucket} drills to reduce cognitive load.",
                    f"Review {bucket} drill UX for sources of confusion.",
                    f"{bucket.title()} is slow — may need better scaffolding.",
                    ["mandarin/drills/"],
                ))
    except Exception as e:
        logger.debug("Timing by modality failed: %s", e)
    return findings


# ═══════════════════════════════════════════════════════════════════════
# TIER 3: LEARNING SCIENCE
# ═══════════════════════════════════════════════════════════════════════


def _analyze_srs_funnel_by_modality(conn) -> list[dict]:
    """Mastery stage distribution per modality — where do items get stuck?"""
    findings = []
    try:
        # Group progress by content_item's primary modality
        rows = _safe_query_all(conn, """
            SELECT
                CASE
                    WHEN ci.drill_type IN ('mc', 'reverse_mc') THEN 'recognition'
                    WHEN ci.drill_type LIKE 'listening%' THEN 'listening'
                    WHEN ci.drill_type IN ('ime_type', 'hanzi_to_pinyin') THEN 'production'
                    WHEN ci.drill_type = 'dialogue' THEN 'conversation'
                    ELSE 'other'
                END as modality,
                p.mastery_stage,
                COUNT(*) as cnt
            FROM progress p
            JOIN content_item ci ON p.content_item_id = ci.id
            WHERE p.mastery_stage IS NOT NULL
            GROUP BY modality, p.mastery_stage
        """)
        if not rows:
            return findings

        # Compute stuck rate per modality (% at 'seen' or 'passed_once')
        modality_data = {}
        for r in rows:
            mod = r["modality"]
            if mod == "other":
                continue
            if mod not in modality_data:
                modality_data[mod] = {"total": 0, "stuck": 0}
            modality_data[mod]["total"] += r["cnt"]
            if r["mastery_stage"] in ("seen", "passed_once"):
                modality_data[mod]["stuck"] += r["cnt"]

        for mod, data in modality_data.items():
            if data["total"] < 20:
                continue
            stuck_pct = data["stuck"] / data["total"] * 100
            if stuck_pct > 40:
                findings.append(_finding(
                    "srs_funnel", "medium",
                    f"{mod.title()} items: {stuck_pct:.0f}% stuck at early mastery stages",
                    f"{data['stuck']}/{data['total']} {mod} items are at 'seen' or "
                    f"'passed_once' — never progressing to stabilizing. The SRS "
                    f"may not be activating for this modality.",
                    f"Check if {mod} items are being scheduled for review. They "
                    f"may be drowned out by other modalities.",
                    f"Review SRS scheduling priority for {mod} items.",
                    f"{mod.title()} mastery pipeline is clogged.",
                    ["mandarin/scheduler.py"],
                ))
    except Exception as e:
        logger.debug("SRS funnel by modality failed: %s", e)
    return findings


def _analyze_errors_by_modality(conn) -> list[dict]:
    """Error type distribution per modality."""
    findings = []
    try:
        rows = _safe_query_all(conn, """
            SELECT drill_type, error_type, COUNT(*) as cnt
            FROM review_event
            WHERE correct = 0
              AND error_type IS NOT NULL
              AND reviewed_at >= datetime('now', '-30 days')
            GROUP BY drill_type, error_type
            HAVING cnt >= 3
        """)
        if not rows:
            return findings

        # Aggregate by modality bucket
        mod_errors = {}
        for r in rows:
            bucket = _bucket_for_drill_type(r["drill_type"])
            if bucket == "other":
                continue
            if bucket not in mod_errors:
                mod_errors[bucket] = {}
            mod_errors[bucket][r["error_type"]] = (
                mod_errors[bucket].get(r["error_type"], 0) + r["cnt"]
            )

        # Find dominant error type per modality
        for bucket, errors in mod_errors.items():
            total = sum(errors.values())
            if total < 10:
                continue
            dominant = max(errors, key=errors.get)
            dominant_pct = errors[dominant] / total * 100
            if dominant_pct > 60:
                findings.append(_finding(
                    "drill_quality", "low",
                    f"{bucket.title()} errors dominated by '{dominant}' ({dominant_pct:.0f}%)",
                    f"In {bucket} drills, {dominant_pct:.0f}% of errors are "
                    f"'{dominant}' ({errors[dominant]}/{total}). This concentration "
                    f"suggests a systematic issue, not random mistakes.",
                    f"Target '{dominant}' errors in {bucket} drills with "
                    f"specific scaffolding or near-miss feedback.",
                    f"Add {dominant}-specific feedback to {bucket} drill flow.",
                    f"Concentrated error pattern in {bucket}.",
                    ["mandarin/drills/"],
                ))
    except Exception as e:
        logger.debug("Errors by modality failed: %s", e)
    return findings


def _analyze_hsk_cliff_by_modality(conn) -> list[dict]:
    """HSK level transition difficulty per modality."""
    findings = []
    try:
        rows = _safe_query_all(conn, """
            SELECT ci.hsk_level,
                   CASE
                       WHEN re.drill_type IN ('mc', 'reverse_mc') THEN 'recognition'
                       WHEN re.drill_type LIKE 'listening%' THEN 'listening'
                       WHEN re.drill_type IN ('ime_type', 'hanzi_to_pinyin') THEN 'production'
                       ELSE 'other'
                   END as modality,
                   AVG(CAST(re.correct AS REAL)) as accuracy,
                   COUNT(*) as total
            FROM review_event re
            JOIN content_item ci ON re.content_item_id = ci.id
            WHERE re.reviewed_at >= datetime('now', '-30 days')
              AND ci.hsk_level BETWEEN 1 AND 6
            GROUP BY ci.hsk_level, modality
            HAVING total >= 10
        """)
        if not rows:
            return findings

        # Find steepest cliff per modality
        mod_levels = {}
        for r in rows:
            if r["modality"] == "other":
                continue
            if r["modality"] not in mod_levels:
                mod_levels[r["modality"]] = {}
            mod_levels[r["modality"]][r["hsk_level"]] = r["accuracy"]

        for mod, levels in mod_levels.items():
            sorted_levels = sorted(levels.items())
            for i in range(len(sorted_levels) - 1):
                level_a, acc_a = sorted_levels[i]
                level_b, acc_b = sorted_levels[i + 1]
                drop = (acc_a - acc_b) * 100
                if drop > 20:
                    findings.append(_finding(
                        "curriculum", "medium",
                        f"{mod.title()} HSK cliff: {drop:.0f}pp accuracy drop from HSK {level_a} to {level_b}",
                        f"{mod.title()} accuracy drops {drop:.0f}pp from HSK {level_a} "
                        f"({acc_a*100:.0f}%) to HSK {level_b} ({acc_b*100:.0f}%). "
                        f"This cliff may be steeper than in other modalities.",
                        f"Add bridging content between HSK {level_a} and {level_b} "
                        f"for {mod}. Consider gentler difficulty progression.",
                        f"Review HSK {level_a}→{level_b} transition for {mod}.",
                        f"Steep difficulty cliff in {mod} at HSK {level_a}→{level_b}.",
                        ["mandarin/content_gen/", "mandarin/scheduler.py"],
                    ))
                    break  # One cliff finding per modality
    except Exception as e:
        logger.debug("HSK cliff by modality failed: %s", e)
    return findings


def _analyze_archetype_modality(conn) -> list[dict]:
    """Do learner archetypes differ in modality engagement?"""
    findings = []
    try:
        users = _safe_query_all(conn, """
            SELECT u.id,
                   COUNT(DISTINCT sl.id) as sessions,
                   AVG(CAST(sl.items_correct AS REAL) / NULLIF(sl.items_completed, 0)) as accuracy,
                   julianday('now') - julianday(MAX(sl.completed_at)) as days_inactive,
                   (SELECT COUNT(*) FROM reading_progress rp WHERE rp.user_id = u.id) as reading,
                   (SELECT COUNT(*) FROM listening_progress lp WHERE lp.user_id = u.id) as listening,
                   (SELECT COUNT(*) FROM review_event re WHERE re.user_id = u.id AND re.drill_type = 'dialogue') as conversation
            FROM user u
            JOIN session_log sl ON u.id = sl.user_id
            WHERE u.is_admin = 0
            GROUP BY u.id
            HAVING sessions >= 5
        """)
        if not users or len(users) < 10:
            return findings

        struggling = [u for u in users if (u["accuracy"] or 0) < 0.5]
        active = [u for u in users if (u["days_inactive"] or 99) < 7]

        if struggling and active and len(struggling) >= 3 and len(active) >= 3:
            def avg_modality_count(group):
                counts = []
                for u in group:
                    c = sum(1 for k in ["reading", "listening", "conversation"]
                            if (u[k] or 0) > 0)
                    counts.append(c)
                return sum(counts) / len(counts)

            struggling_avg = avg_modality_count(struggling)
            active_avg = avg_modality_count(active)

            if active_avg > struggling_avg + 0.5:
                findings.append(_finding(
                    "engagement", "low",
                    f"Struggling users engage with {struggling_avg:.1f} modalities vs active {active_avg:.1f}",
                    f"Users with <50% accuracy engage with {struggling_avg:.1f} "
                    f"modalities on average, while active users engage with "
                    f"{active_avg:.1f}. Broader modality engagement correlates "
                    f"with success.",
                    "For struggling users, broaden their modality exposure. "
                    "Mono-modal practice may reinforce the wrong approach.",
                    "Adjust scheduler for struggling users to include more modalities.",
                    "Archetype-modality correlation insight.",
                    ["mandarin/scheduler.py"],
                ))
    except Exception as e:
        logger.debug("Archetype modality failed: %s", e)
    return findings


# ═══════════════════════════════════════════════════════════════════════
# TIER 4: ANTI-GOODHART & AI
# ═══════════════════════════════════════════════════════════════════════


def _analyze_counter_metrics_by_modality(conn) -> list[dict]:
    """Anti-Goodhart: can one modality's accuracy be inflated while another decays?"""
    findings = []
    try:
        # Delayed recall accuracy per modality (items with 7+ day spacing)
        rows = _safe_query_all(conn, """
            SELECT
                CASE
                    WHEN re.drill_type IN ('mc', 'reverse_mc') THEN 'recognition'
                    WHEN re.drill_type LIKE 'listening%' THEN 'listening'
                    WHEN re.drill_type IN ('ime_type', 'hanzi_to_pinyin') THEN 'production'
                    ELSE 'other'
                END as modality,
                AVG(CAST(re.correct AS REAL)) as delayed_accuracy,
                COUNT(*) as total
            FROM review_event re
            JOIN progress p ON re.content_item_id = p.content_item_id
                AND re.user_id = p.user_id
            WHERE re.reviewed_at >= datetime('now', '-30 days')
              AND p.last_reviewed IS NOT NULL
              AND julianday(re.reviewed_at) - julianday(p.last_reviewed) >= 7
            GROUP BY modality
            HAVING total >= 10
        """)
        if not rows or len(rows) < 2:
            return findings

        accuracies = {r["modality"]: r["delayed_accuracy"]
                      for r in rows if r["modality"] != "other"}

        if len(accuracies) < 2:
            return findings

        best = max(accuracies, key=accuracies.get)
        worst = min(accuracies, key=accuracies.get)
        gap = (accuracies[best] - accuracies[worst]) * 100

        if gap > 25:
            findings.append(_finding(
                "retention", "medium",
                f"Anti-Goodhart: {best} delayed-recall {accuracies[best]*100:.0f}% vs {worst} {accuracies[worst]*100:.0f}% ({gap:.0f}pp gap)",
                f"Delayed-recall accuracy (items spaced 7+ days) varies by modality: "
                + ", ".join(f"{m}: {a*100:.0f}%" for m, a in accuracies.items())
                + f". A {gap:.0f}pp gap suggests aggregate accuracy may mask "
                f"decay in {worst}.",
                f"The overall accuracy metric may be Goodharted — {worst} "
                f"is decaying while {best} inflates the average. Monitor "
                f"per-modality delayed-recall separately.",
                f"Add per-modality delayed-recall tracking to counter_metrics.py.",
                f"Aggregate accuracy hides {worst} decay (anti-Goodhart).",
                ["mandarin/counter_metrics.py"],
            ))
    except Exception as e:
        logger.debug("Counter metrics by modality failed: %s", e)
    return findings


def _analyze_ai_quality_by_modality(conn) -> list[dict]:
    """AI generation quality per task type mapped to modality."""
    findings = []
    try:
        rows = _safe_query_all(conn, """
            SELECT task_type,
                   AVG(quality_score) as avg_quality,
                   COUNT(*) as total
            FROM prompt_trace
            WHERE created_at >= datetime('now', '-30 days')
              AND quality_score IS NOT NULL
            GROUP BY task_type
            HAVING total >= 5
        """)
        if not rows or len(rows) < 2:
            return findings

        # Map task_types to modalities
        task_modality = {
            "reading_generation": "reading",
            "drill_generation": "core_drills",
            "conversation_eval": "conversation",
            "error_explanation": "feedback",
            "research_synthesis": "content",
        }

        mapped = {}
        for r in rows:
            mod = task_modality.get(r["task_type"])
            if mod:
                mapped[mod] = r["avg_quality"]

        if len(mapped) < 2:
            return findings

        overall = sum(mapped.values()) / len(mapped)
        for mod, quality in mapped.items():
            if quality < overall - 0.15 and quality < 0.7:
                findings.append(_finding(
                    "genai", "medium",
                    f"{mod.title()} AI quality {quality:.2f} — below average {overall:.2f}",
                    f"AI generation quality for {mod}: {quality:.2f} vs "
                    f"overall average {overall:.2f}. Lower quality AI output "
                    f"may degrade the learner experience in this modality.",
                    f"Review AI prompts for {mod} generation. Consider task-specific "
                    f"model selection or prompt refinement.",
                    f"Improve AI prompt quality for {mod} task type.",
                    f"{mod.title()} AI generation needs quality improvement.",
                    ["mandarin/ai/ollama_client.py"],
                ))
    except Exception as e:
        logger.debug("AI quality by modality failed: %s", e)
    return findings


ANALYZERS = [
    # Tier 1: Core Business
    _analyze_retention_by_modality,
    _analyze_conversion_by_modality,
    _analyze_drill_quality_by_modality,
    _analyze_engagement_by_modality,
    _analyze_churn_risk_by_modality,
    # Tier 2: UX/Flow
    _analyze_frustration_by_modality,
    _analyze_flow_by_modality,
    _analyze_platform_modality,
    _analyze_timing_by_modality,
    # Tier 3: Learning Science
    _analyze_srs_funnel_by_modality,
    _analyze_errors_by_modality,
    _analyze_hsk_cliff_by_modality,
    _analyze_archetype_modality,
    # Tier 4: Anti-Goodhart & AI
    _analyze_counter_metrics_by_modality,
    _analyze_ai_quality_by_modality,
]
