"""UX health analyzers — detect usability problems from behavioral data.

Feeds findings into the auto-execution pipeline so the LLM can propose
specific CSS/JS/config fixes via _design_fix_via_llm.
"""

import logging
from ._base import _finding

logger = logging.getLogger(__name__)


def _analyze_session_abandonment(conn) -> list[dict]:
    """If >20% sessions incomplete in last 14 days, emit finding."""
    findings = []
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) as abandoned
            FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
        """).fetchone()
        total = row["total"] if row else 0
        if total >= 10:
            abandoned = row["abandoned"] or 0
            rate = abandoned / total * 100
            if rate > 20:
                findings.append(_finding(
                    "ux", "high" if rate > 40 else "medium",
                    f"Session abandonment rate: {rate:.0f}% ({abandoned}/{total} sessions incomplete)",
                    f"{rate:.1f}% of sessions in the last 14 days were not completed. "
                    f"Users may find sessions too long, too hard, or not engaging enough.",
                    "Reduce session length or difficulty. Check if specific block types cause abandonment.",
                    "Investigate session abandonment: check session_length_minutes, new_item_ceiling, and block time budgets. Reduce session length if >10 minutes average.",
                    "Session completion UX",
                    ["mandarin/scheduler.py", "mandarin/settings.py"],
                ))
    except Exception:
        pass
    return findings


def _analyze_drill_skip_rate(conn) -> list[dict]:
    """If skip rate >15% for any drill type, emit finding."""
    findings = []
    try:
        rows = conn.execute("""
            SELECT drill_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN rating = 0 OR user_answer = '__skip__' THEN 1 ELSE 0 END) as skipped
            FROM review_event
            WHERE reviewed_at >= datetime('now', '-14 days')
            GROUP BY drill_type
            HAVING total >= 20
        """).fetchall()
        for row in (rows or []):
            skip_rate = (row["skipped"] or 0) / row["total"] * 100
            if skip_rate > 15:
                findings.append(_finding(
                    "ux", "medium",
                    f"High skip rate for '{row['drill_type']}' drills: {skip_rate:.0f}%",
                    f"Users skip {skip_rate:.0f}% of {row['drill_type']} drills. "
                    f"This drill type may be too difficult, confusing, or not engaging.",
                    f"Review {row['drill_type']} drill UX. Consider adding hints, simplifying instructions, or adjusting difficulty.",
                    f"Investigate why users skip {row['drill_type']} drills and improve the UX or reduce difficulty.",
                    "Drill type UX quality",
                    ["mandarin/drills/", "mandarin/web/static/app.js"],
                ))
    except Exception:
        pass
    return findings


def _analyze_repeated_errors(conn) -> list[dict]:
    """If users make the same error 3+ times on same item, feedback isn't helping."""
    findings = []
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT content_item_id) as stuck_items
            FROM (
                SELECT content_item_id, COUNT(*) as error_count
                FROM review_event
                WHERE rating <= 2
                AND reviewed_at >= datetime('now', '-14 days')
                GROUP BY user_id, content_item_id
                HAVING error_count >= 3
            )
        """).fetchone()
        stuck = row["stuck_items"] if row else 0
        if stuck >= 5:
            findings.append(_finding(
                "ux", "medium",
                f"{stuck} items have 3+ repeated errors — error feedback may be insufficient",
                f"Users are making the same mistake 3+ times on {stuck} items. "
                f"The current error feedback (showing correct answer) isn't helping them learn.",
                "Improve error explanations: show WHY the answer was wrong, not just WHAT is correct. Add targeted practice for stuck items.",
                "Enhance error feedback in drills: add error_type-specific explanations and consider forcing remedial practice for repeatedly-wrong items.",
                "Error recovery UX",
                ["mandarin/web/static/app.js", "mandarin/runner.py"],
            ))
    except Exception:
        pass
    return findings


def _analyze_onboarding_completion(conn) -> list[dict]:
    """If >30% users never complete a session after signup, onboarding failed."""
    findings = []
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total_users,
                   SUM(CASE WHEN session_count = 0 THEN 1 ELSE 0 END) as never_started
            FROM (
                SELECT u.id, COUNT(sl.id) as session_count
                FROM user u
                LEFT JOIN session_log sl ON u.id = sl.user_id AND sl.completed = 1
                WHERE u.created_at >= datetime('now', '-30 days')
                GROUP BY u.id
            )
        """).fetchone()
        total = row["total_users"] if row else 0
        if total >= 5:
            never = row["never_started"] or 0
            rate = never / total * 100
            if rate > 30:
                findings.append(_finding(
                    "onboarding", "high" if rate > 50 else "medium",
                    f"Onboarding dropout: {rate:.0f}% of new users never completed a session",
                    f"{never} of {total} users who signed up in the last 30 days never completed a session. "
                    f"The onboarding flow may be too long, confusing, or not compelling enough.",
                    "Simplify onboarding: reduce steps, add a quick-win first drill, or improve the value proposition shown during signup.",
                    "Improve onboarding: shorten the intro flow, add an immediate interactive demo drill, and ensure the first session starts within 30 seconds of signup.",
                    "First-time user experience",
                    ["mandarin/web/static/app.js", "mandarin/web/templates/index.html"],
                ))
    except Exception:
        pass
    return findings


def _analyze_session_duration(conn) -> list[dict]:
    """If sessions consistently exceed target length, blocks are too long."""
    findings = []
    try:
        row = conn.execute("""
            SELECT AVG(duration_seconds) as avg_duration,
                   COUNT(*) as total
            FROM session_log
            WHERE completed = 1
            AND started_at >= datetime('now', '-14 days')
            AND duration_seconds IS NOT NULL
        """).fetchone()
        if row and row["total"] and row["total"] >= 10:
            avg = row["avg_duration"] or 0
            # Standard session target is 600s (10 min)
            if avg > 720:  # 12+ minutes = too long
                findings.append(_finding(
                    "ux", "medium",
                    f"Sessions averaging {avg/60:.1f} minutes (target: 10 min)",
                    f"Completed sessions average {avg/60:.1f} minutes, exceeding the 10-minute target by {(avg-600)/60:.1f} minutes. "
                    f"Longer sessions increase abandonment risk and fatigue.",
                    "Reduce block time budgets or drill count per session.",
                    "Reduce session duration: decrease reading/listening block target_seconds or reduce drill count in scheduler.py.",
                    "Session length UX",
                    ["mandarin/scheduler.py"],
                ))
    except Exception:
        pass
    return findings


ANALYZERS = [
    _analyze_session_abandonment,
    _analyze_drill_skip_rate,
    _analyze_repeated_errors,
    _analyze_onboarding_completion,
    _analyze_session_duration,
]
