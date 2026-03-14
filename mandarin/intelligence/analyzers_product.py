"""Product Intelligence — product analyzers (ux, ui, flow, engagement, drill_quality, content, copy)."""

from ._base import _f, _FILE_MAP, _finding, _safe_query, _safe_query_all, _safe_scalar


def _analyze_ux(conn) -> list[dict]:
    findings = []

    total_sessions = _safe_scalar(conn, "SELECT COUNT(*) FROM session_log")
    if total_sessions == 0:
        return findings

    # Session completion rate
    completed = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE items_completed > 0 AND items_completed >= items_planned * 0.8
    """)
    completion_rate = round(completed / total_sessions * 100, 1) if total_sessions > 0 else 0
    if completion_rate < 70 and total_sessions >= 10:
        findings.append(_finding(
            "ux", "high",
            f"Session completion rate: {completion_rate}%",
            f"Only {completion_rate}% of sessions have >= 80% items completed. "
            f"({completed}/{total_sessions} sessions).",
            "Investigate why users abandon sessions. Check difficulty, length, and engagement.",
            (
                f"Session completion rate is {completion_rate}%.\n\n"
                "Improve session completion:\n"
                f"1. Read {_FILE_MAP['scheduler']} — are sessions too long?\n"
                "2. Check session_log for early_exit patterns (query WHERE early_exit = 1)\n"
                f"3. Review drill difficulty in {_FILE_MAP['drills']} — too hard = frustration quit\n"
                "4. Check if boredom_flags correlate with exits\n"
                "5. Consider adaptive session length based on user engagement"
            ),
            "Satisfaction: completing sessions is key to learning outcomes",
            _f("scheduler"),
        ))

    # Bounce rate
    bounced = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log WHERE items_completed = 0
    """)
    bounce_rate = round(bounced / total_sessions * 100, 1) if total_sessions > 0 else 0
    if bounce_rate > 15 and total_sessions >= 10:
        findings.append(_finding(
            "ux", "high",
            f"High bounce rate: {bounce_rate}%",
            f"{bounced} of {total_sessions} sessions had zero items completed.",
            "Users are starting sessions but immediately leaving. Check loading, first drill UX.",
            (
                f"Bounce rate is {bounce_rate}% ({bounced}/{total_sessions}).\n\n"
                "Reduce session bounce rate:\n"
                "1. Check session_log for bounced sessions — what session_type? what time of day?\n"
                f"2. Read {_FILE_MAP['app_js']} — is the session start flow smooth?\n"
                "3. Check for JS errors during session initialization (client_error_log)\n"
                "4. Consider pre-loading first drill before showing session screen"
            ),
            "Retention: users who bounce once are unlikely to return",
            _f("app_js", "session_routes"),
        ))

    # Early exit patterns
    early_exits = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log WHERE early_exit = 1
    """)
    if early_exits and total_sessions >= 10:
        early_pct = round(early_exits / total_sessions * 100, 1)
        if early_pct > 25:
            findings.append(_finding(
                "ux", "medium",
                f"High early exit rate: {early_pct}%",
                f"{early_exits} of {total_sessions} sessions ended early ({early_pct}%).",
                "Sessions are too long, too hard, or not engaging enough.",
                (
                    f"Early exit rate is {early_pct}%.\n\n"
                    "Reduce early exits:\n"
                    "1. Query session_log: SELECT items_planned, items_completed, duration_seconds "
                    "FROM session_log WHERE early_exit = 1 ORDER BY started_at DESC LIMIT 20\n"
                    "2. Check if exits cluster at specific item counts\n"
                    f"3. Review {_FILE_MAP['scheduler']} session length calculation"
                ),
                "Satisfaction: early exits signal frustration or boredom",
                _f("scheduler"),
            ))

    # Slow response rate
    slow_responses = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event WHERE response_ms > 30000
    """)
    total_reviews = _safe_scalar(conn, "SELECT COUNT(*) FROM review_event")
    if total_reviews and total_reviews >= 50:
        slow_pct = round(slow_responses / total_reviews * 100, 1)
        if slow_pct > 10:
            findings.append(_finding(
                "ux", "medium",
                f"Slow response rate: {slow_pct}% of reviews >30s",
                f"{slow_responses} of {total_reviews} drill responses took >30 seconds.",
                "Users are stuck on drills. Check difficulty calibration.",
                (
                    f"{slow_pct}% of drill responses take >30 seconds.\n\n"
                    "Investigate slow responses:\n"
                    "1. Query: SELECT drill_type, AVG(response_ms), COUNT(*) FROM review_event "
                    "GROUP BY drill_type ORDER BY AVG(response_ms) DESC\n"
                    f"2. Check if specific drill types are consistently slow\n"
                    f"3. Review {_FILE_MAP['scheduler']} difficulty selection"
                ),
                "Satisfaction: long response times indicate struggling",
                _f("scheduler", "drills"),
            ))

    return findings


def _analyze_ui_visual(conn) -> list[dict]:
    findings = []

    # Need meaningful traffic to avoid noise on fresh/dev databases
    total_sessions_7d = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
    """)
    if not total_sessions_7d or total_sessions_7d < 5:
        return findings

    css_js_errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_error_log
        WHERE (error_message LIKE '%CSS%' OR error_message LIKE '%style%'
               OR error_message LIKE '%font%' OR error_message LIKE '%script%'
               OR error_message LIKE '%Failed to load%' OR error_message LIKE '%ERR_NAME%')
          AND timestamp >= datetime('now', '-7 days')
    """)
    if css_js_errors and css_js_errors >= 3:
        findings.append(_finding(
            "ui", "high",
            f"{css_js_errors} resource loading errors in last 7 days",
            "CSS, JS, or font files are failing to load for some users.",
            "Check CDN configuration, CSP headers, and static file serving.",
            (
                f"{css_js_errors} resource loading errors detected.\n\n"
                "Fix resource loading:\n"
                "1. Query: SELECT error_message, page_url, COUNT(*) FROM client_error_log "
                "WHERE timestamp >= datetime('now', '-7 days') AND "
                "(error_message LIKE '%CSS%' OR error_message LIKE '%font%') "
                "GROUP BY error_message ORDER BY COUNT(*) DESC\n"
                f"2. Check {_FILE_MAP['middleware']} CSP headers\n"
                f"3. Verify static files in {_FILE_MAP['style_css']}"
            ),
            "Satisfaction: broken CSS/JS = broken product",
            _f("middleware", "style_css"),
        ))

    # Mobile client errors
    mobile_errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_error_log
        WHERE timestamp >= datetime('now', '-7 days')
          AND (page_url LIKE '%capacitor%' OR page_url LIKE '%ionic%'
               OR error_message LIKE '%viewport%' OR error_message LIKE '%touch%')
    """)
    if mobile_errors and mobile_errors > 3:
        findings.append(_finding(
            "ui", "high",
            f"{mobile_errors} mobile-specific errors in last 7 days",
            "Mobile users are experiencing errors, possibly viewport or touch-related.",
            "Test on iOS simulator and fix mobile-specific issues.",
            (
                f"{mobile_errors} mobile errors detected.\n\n"
                "Fix mobile UX:\n"
                "1. Query client_error_log for mobile-specific errors\n"
                "2. Test on iOS simulator: xcrun simctl boot 'iPhone 16e'\n"
                f"3. Check {_FILE_MAP['style_css']} for responsive breakpoints\n"
                "4. Verify Capacitor config in ios/App/"
            ),
            "Satisfaction: mobile users are likely a large segment",
            _f("style_css", "app_js"),
        ))

    # Total client errors
    total_client_errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_error_log
        WHERE timestamp >= datetime('now', '-7 days')
    """)
    if total_client_errors and total_client_errors > 20:
        findings.append(_finding(
            "ui", "medium",
            f"{total_client_errors} total client errors this week",
            "Elevated client-side error rate may indicate UI/JS issues.",
            "Review client error log for patterns and fix the most common errors.",
            (
                f"{total_client_errors} client errors in 7 days.\n\n"
                "Triage client errors:\n"
                "1. Query: SELECT error_type, error_message, COUNT(*) as cnt "
                "FROM client_error_log WHERE timestamp >= datetime('now', '-7 days') "
                "GROUP BY error_type, error_message ORDER BY cnt DESC LIMIT 10\n"
                f"2. Fix the top 3 most frequent errors\n"
                f"3. Check {_FILE_MAP['app_js']} error handling"
            ),
            "Satisfaction: JS errors degrade user experience silently",
            _f("app_js"),
        ))

    return findings


def _analyze_flow(conn) -> list[dict]:
    findings = []

    # Onboarding funnel from lifecycle_event
    funnel_steps = _safe_query_all(conn, """
        SELECT event_type, COUNT(DISTINCT user_id) as users
        FROM lifecycle_event
        WHERE event_type IN ('signup', 'first_session', 'first_lookup',
                             'encounter_drilled', 'activation', 'session_complete')
        GROUP BY event_type
    """)
    if funnel_steps and len(funnel_steps) >= 2:
        step_counts = {r["event_type"]: r["users"] for r in funnel_steps}
        ordered = ["signup", "first_session", "first_lookup", "encounter_drilled", "activation"]
        for i in range(len(ordered) - 1):
            prev_step = ordered[i]
            next_step = ordered[i + 1]
            prev_count = step_counts.get(prev_step, 0)
            next_count = step_counts.get(next_step, 0)
            if prev_count >= 5 and next_count > 0:
                dropoff = round((1 - next_count / prev_count) * 100, 1)
                if dropoff > 30:
                    findings.append(_finding(
                        "flow", "high" if dropoff > 50 else "medium",
                        f"Funnel dropoff: {prev_step} → {next_step}: {dropoff}% lost",
                        f"{prev_count} users at '{prev_step}' but only {next_count} at '{next_step}' ({dropoff}% drop).",
                        f"Investigate why users don't progress from {prev_step} to {next_step}.",
                        (
                            f"Funnel: {prev_step} ({prev_count}) → {next_step} ({next_count}), {dropoff}% dropoff.\n\n"
                            "Fix funnel dropoff:\n"
                            "1. Check the UX between these steps — is the path clear?\n"
                            "2. Look at session_log for users who completed the first but not the second\n"
                            f"3. Review {_FILE_MAP['onboarding_routes']} and {_FILE_MAP['scheduler']}"
                        ),
                        f"Growth: fixing this step = {int(prev_count * dropoff / 100)} more users progressing",
                        _f("onboarding_routes", "scheduler"),
                    ))

    # Post-session behavior: users who complete a session but never return
    one_time_users = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM (
            SELECT user_id, COUNT(*) as cnt
            FROM session_log
            WHERE items_completed > 0
            GROUP BY user_id
            HAVING cnt = 1
        )
    """)
    total_session_users = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log WHERE items_completed > 0
    """)
    if total_session_users and total_session_users >= 10:
        one_time_pct = round(one_time_users / total_session_users * 100, 1)
        if one_time_pct > 40:
            findings.append(_finding(
                "flow", "high",
                f"{one_time_pct}% of users complete exactly one session then leave",
                f"{one_time_users} of {total_session_users} users who completed a session never returned.",
                "The first session doesn't create enough pull for a second.",
                (
                    f"{one_time_pct}% one-and-done users.\n\n"
                    "Improve post-session engagement:\n"
                    "1. Add a clear 'come back tomorrow' CTA with preview of what's next\n"
                    f"2. Check {_FILE_MAP['email']} for day-1 follow-up email\n"
                    "3. Show progress hooks (items learned, next milestone)"
                ),
                "Retention: the first-to-second session gap is the biggest churn cliff",
                _f("dashboard_routes", "email"),
            ))

    return findings


def _analyze_engagement_patterns(conn) -> list[dict]:
    findings = []

    # Users with <=1 session/week
    low_freq = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM (
            SELECT user_id, COUNT(*) as cnt
            FROM session_log
            WHERE started_at >= datetime('now', '-28 days')
            GROUP BY user_id
            HAVING cnt <= 4
        )
    """)
    active_users = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-28 days')
    """)
    if active_users and active_users >= 5:
        low_pct = round(low_freq / active_users * 100, 1)
        if low_pct > 40:
            findings.append(_finding(
                "engagement", "medium",
                f"{low_pct}% of active users do ≤1 session/week",
                f"{low_freq} of {active_users} 28-day active users average ≤1 session per week.",
                "Increase engagement through reminders, shorter sessions, and habit hooks.",
                (
                    f"{low_pct}% of users are low-frequency.\n\n"
                    "Boost session frequency:\n"
                    f"1. Check {_FILE_MAP['email']} — daily/weekly reminder emails\n"
                    "2. Add 'quick review' (2 min) option for low-motivation days\n"
                    "3. Review streak mechanics — do they motivate or guilt?"
                ),
                "Retention: frequency predicts long-term retention",
                _f("email", "scheduler"),
            ))

    # Declining session frequency (churning pattern)
    week_counts = _safe_query_all(conn, """
        SELECT
            CASE WHEN started_at >= datetime('now', '-7 days') THEN 'w1'
                 WHEN started_at >= datetime('now', '-14 days') THEN 'w2'
                 WHEN started_at >= datetime('now', '-21 days') THEN 'w3'
                 WHEN started_at >= datetime('now', '-28 days') THEN 'w4'
            END as week,
            COUNT(*) as cnt
        FROM session_log
        WHERE started_at >= datetime('now', '-28 days')
        GROUP BY week
        ORDER BY week
    """)
    if week_counts and len(week_counts) >= 3:
        weekly = {r["week"]: r["cnt"] for r in week_counts if r["week"]}
        w4 = weekly.get("w4", 0)
        w3 = weekly.get("w3", 0)
        w2 = weekly.get("w2", 0)
        w1 = weekly.get("w1", 0)
        # Check for 3-week declining trend
        if w4 > 0 and w3 > 0 and w2 > 0 and w1 > 0:
            if w1 < w2 < w3 < w4:
                decline_pct = round((1 - w1 / w4) * 100, 1)
                findings.append(_finding(
                    "engagement", "high",
                    f"Session volume declining: {decline_pct}% drop over 4 weeks",
                    f"Week-over-week decline: {w4} → {w3} → {w2} → {w1} sessions.",
                    "Overall engagement is decreasing. Investigate root cause.",
                    (
                        f"4-week decline: {w4}→{w3}→{w2}→{w1} sessions ({decline_pct}% drop).\n\n"
                        "Address declining engagement:\n"
                        "1. Check for recent UX changes that may have hurt engagement\n"
                        "2. Review crash_log and client_error_log for new issues\n"
                        "3. Check if content staleness is a factor"
                    ),
                    "Retention: sustained decline = approaching critical mass loss",
                    _f("scheduler", "email"),
                ))

    return findings


def _analyze_drill_quality(conn) -> list[dict]:
    findings = []

    # Drills with high response time AND low accuracy (confusing, not hard)
    confusing_drills = _safe_query_all(conn, """
        SELECT drill_type, content_item_id,
               AVG(response_ms) as avg_ms,
               AVG(CASE WHEN correct = 0 THEN 1.0 ELSE 0.0 END) as error_rate,
               COUNT(*) as cnt
        FROM review_event
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY drill_type, content_item_id
        HAVING cnt >= 5 AND avg_ms > 15000 AND error_rate > 0.5
        ORDER BY error_rate DESC
        LIMIT 10
    """)
    if confusing_drills:
        examples = ", ".join(
            f"{r['drill_type']}:{r['content_item_id']} ({round(r['error_rate'] * 100)}% errors, {round(r['avg_ms'] / 1000, 1)}s)"
            for r in confusing_drills[:5]
        )
        findings.append(_finding(
            "drill_quality", "high",
            f"{len(confusing_drills)} confusing drill+item combinations",
            f"These drills have both high response time and high error rate — they're confusing, not challenging: {examples}",
            "Review the content items and drill presentations. Fix unclear prompts.",
            (
                f"Confusing drills: {examples}\n\n"
                "Fix confusing drills:\n"
                "1. Query each content_item_id to see the item text\n"
                "2. Check if the drill type is appropriate for that item\n"
                f"3. Review drill logic in {_FILE_MAP['drills']}"
            ),
            "Learning: confusing drills frustrate users and don't teach",
            _f("drills", "scheduler"),
        ))

    # Drill types with high skip rates
    skip_rates = _safe_query_all(conn, """
        SELECT drill_type,
               COUNT(*) as total,
               SUM(CASE WHEN response_ms < 1000 AND correct = 0 THEN 1 ELSE 0 END) as likely_skips
        FROM review_event
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY drill_type
        HAVING total >= 20
    """)
    for row in skip_rates:
        total = row["total"]
        skips = row["likely_skips"] or 0
        if total > 0 and skips / total > 0.15:
            skip_pct = round(skips / total * 100, 1)
            findings.append(_finding(
                "drill_quality", "medium",
                f"High skip rate for '{row['drill_type']}': {skip_pct}%",
                f"{skips} of {total} responses were fast-wrong (likely skipped).",
                "Users may be frustrated or bored with this drill type.",
                (
                    f"'{row['drill_type']}' skip rate: {skip_pct}%.\n\n"
                    f"1. Review drill presentation in {_FILE_MAP['drills']}\n"
                    "2. Check if the drill type is too hard or unclear"
                ),
                "Learning: skipped drills don't contribute to retention",
                _f("drills"),
            ))

    return findings


def _analyze_content_staleness(conn) -> list[dict]:
    findings = []

    # Items where learners consistently struggle
    struggling_items = _safe_scalar(conn, """
        SELECT COUNT(*) FROM progress p
        WHERE p.repetitions > 15 AND p.ease_factor < 1.8
          AND EXISTS (
              SELECT 1 FROM review_event r
              WHERE r.content_item_id = p.content_item_id
                AND r.user_id = p.user_id
                AND r.created_at >= datetime('now', '-30 days')
                AND r.correct = 0
          )
    """)
    if struggling_items and struggling_items > 10:
        findings.append(_finding(
            "content", "medium",
            f"{struggling_items} items where learners persistently struggle despite many reps",
            "These items have been reviewed 15+ times, still have low ease factor, "
            "AND learners are still getting them wrong recently. This goes beyond normal difficulty — "
            "the content or drill presentation may be confusing or poorly scaffolded.",
            "Review the worst offenders: add better context notes, mnemonics, or try different drill types.",
            (
                f"{struggling_items} persistently-struggling items.\n\n"
                "Investigate struggling items:\n"
                "1. Query: SELECT p.content_item_id, c.hanzi, c.english, p.repetitions, p.ease_factor,\n"
                "   (SELECT COUNT(*) FROM review_event r WHERE r.content_item_id = p.content_item_id\n"
                "    AND r.correct = 0 AND r.created_at >= datetime('now', '-30 days')) as recent_errors\n"
                "   FROM progress p JOIN content_item c ON p.content_item_id = c.id\n"
                "   WHERE p.repetitions > 15 AND p.ease_factor < 1.8 ORDER BY p.repetitions DESC LIMIT 20\n"
                "2. For each: check if context_note exists, add mnemonics, try different drill types"
            ),
            "Learning: persistently-struggling items frustrate learners and don't teach",
            _f("scheduler"),
        ))

    # Drill types without recent content additions
    latest_items = _safe_query(conn, """
        SELECT MAX(created_at) as latest FROM content_item
    """)
    if latest_items and latest_items[0]:
        recent_content = _safe_scalar(conn, """
            SELECT COUNT(*) FROM content_item
            WHERE created_at >= datetime('now', '-30 days')
        """)
        total_content = _safe_scalar(conn, "SELECT COUNT(*) FROM content_item")
        if recent_content == 0 and total_content > 0:
            findings.append(_finding(
                "content", "low",
                "No new content added in 30 days",
                "The content library hasn't grown recently. Fresh content keeps users engaged.",
                "Add new content items, reading passages, or media.",
                (
                    "No new content in 30 days.\n\n"
                    "1. Run scripts/expand_content.py to add new items\n"
                    "2. Add new reading passages via exposure_routes\n"
                    "3. Consider adding user-submitted content via /api/content/analyze"
                ),
                "Engagement: fresh content drives return visits",
                ["scripts/"],
            ))

    return findings


def _analyze_copy_quality(conn) -> list[dict]:
    findings = []

    # Error messages with technical jargon
    jargon_errors = _safe_query_all(conn, """
        SELECT error_message, COUNT(*) as cnt
        FROM client_error_log
        WHERE timestamp >= datetime('now', '-7 days')
          AND (error_message LIKE '%WebSocket%'
               OR error_message LIKE '%timeout%'
               OR error_message LIKE '%500%'
               OR error_message LIKE '%Internal Server%'
               OR error_message LIKE '%undefined%'
               OR error_message LIKE '%null%'
               OR error_message LIKE '%TypeError%')
        GROUP BY error_message
        HAVING cnt >= 3
        ORDER BY cnt DESC
        LIMIT 5
    """)
    if jargon_errors:
        examples = "; ".join(f'"{r["error_message"][:60]}" ({r["cnt"]}x)' for r in jargon_errors[:3])
        findings.append(_finding(
            "copy", "medium",
            f"Technical jargon in {len(jargon_errors)} user-visible error messages",
            f"Error messages contain technical terms: {examples}",
            "Replace technical error messages with human-readable text.",
            (
                f"Jargon in errors: {examples}\n\n"
                "Fix error messages:\n"
                f"1. Search {_FILE_MAP['app_js']} for these error messages\n"
                f"2. Search {_FILE_MAP['session_routes']} for error responses\n"
                "3. Replace with user-friendly alternatives"
            ),
            "Satisfaction: technical errors confuse and alarm users",
            _f("app_js", "session_routes"),
        ))

    # Unhelpful error messages
    vague_errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_error_log
        WHERE timestamp >= datetime('now', '-7 days')
          AND (error_message LIKE '%Something went wrong%'
               OR error_message LIKE '%Unknown error%'
               OR error_message LIKE '%Error occurred%'
               OR error_message LIKE '%Please try again%')
    """)
    if vague_errors and vague_errors > 5:
        findings.append(_finding(
            "copy", "medium",
            f"{vague_errors} vague error messages shown to users",
            "Users see unhelpful messages like 'Something went wrong' with no guidance.",
            "Add specific recovery actions to error messages.",
            (
                f"{vague_errors} vague errors.\n\n"
                "Improve error messages:\n"
                "1. For each vague message, add what the user should do (reload, log in again, etc.)\n"
                f"2. Search {_FILE_MAP['app_js']} for 'Something went wrong' strings"
            ),
            "Satisfaction: unhelpful errors leave users stranded",
            _f("app_js"),
        ))

    # Onboarding steps with high skip rates
    onboarding_skips = _safe_query_all(conn, """
        SELECT json_extract(detail, '$.step_name') as step_name, COUNT(*) as cnt
        FROM client_event
        WHERE category = 'onboarding' AND event = 'step_skip'
          AND created_at >= datetime('now', '-30 days')
        GROUP BY step_name
        HAVING cnt >= 3
        ORDER BY cnt DESC
    """)
    if onboarding_skips:
        skip_info = ", ".join(f"{r['step_name']} ({r['cnt']}x)" for r in onboarding_skips)
        findings.append(_finding(
            "copy", "medium",
            f"Onboarding steps with high skip rates: {skip_info}",
            "Users frequently skip these onboarding steps — the copy may not be compelling.",
            "Shorten or improve the skipped steps.",
            (
                f"Skipped onboarding steps: {skip_info}\n\n"
                f"1. Review onboarding copy in {_FILE_MAP['app_js']}\n"
                "2. Consider condensing or removing frequently-skipped steps"
            ),
            "Onboarding: skipped steps = missed context",
            _f("app_js", "onboarding_routes"),
        ))

    return findings


ANALYZERS = [
    _analyze_ux,
    _analyze_ui_visual,
    _analyze_flow,
    _analyze_engagement_patterns,
    _analyze_drill_quality,
    _analyze_content_staleness,
    _analyze_copy_quality,
]
