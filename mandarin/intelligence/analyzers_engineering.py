"""Product Intelligence — engineering analyzers (engineering, security, timing, platform, frustration, pm)."""

from ._base import _f, _FILE_MAP, _finding, _safe_query, _safe_query_all, _safe_scalar


def _analyze_engineering(conn) -> list[dict]:
    findings = []

    crashes_7d = _safe_scalar(conn, """
        SELECT COUNT(*) FROM crash_log
        WHERE timestamp >= datetime('now', '-7 days')
          AND request_path NOT IN ('/unhandled', '/unhandled/')
    """)
    total_requests_7d = _safe_scalar(conn, """
        SELECT COUNT(*) FROM request_timing
        WHERE recorded_at >= datetime('now', '-7 days')
    """)
    if crashes_7d and crashes_7d > 0:
        if total_requests_7d and total_requests_7d >= crashes_7d:
            error_rate = round(crashes_7d / total_requests_7d * 100, 2)
            rate_label = f" (error rate: {error_rate}%)"
        else:
            error_rate = None
            rate_label = ""
        severity = "critical" if crashes_7d > 10 else "high" if crashes_7d > 3 else "medium"
        findings.append(_finding(
            "engineering", severity,
            f"{crashes_7d} server crashes in last 7 days{rate_label}",
            f"{crashes_7d} uncaught exceptions.{' Error rate: ' + str(error_rate) + '%.' if error_rate else ''}",
            "Fix the root causes of server crashes.",
            (
                f"{crashes_7d} server crashes detected.\n\n"
                "Fix server stability:\n"
                "1. Query: SELECT error_type, error_message, COUNT(*) FROM crash_log "
                "WHERE timestamp >= datetime('now', '-7 days') "
                "GROUP BY error_type, error_message ORDER BY COUNT(*) DESC\n"
                "2. Read the top tracebacks from crash_log\n"
                "3. Fix the root causes — check for unhandled exceptions, None access, DB errors\n"
                "4. Add regression tests in tests/\n"
                "5. Run: python -m pytest tests/ -x -q after fixes"
            ),
            "Reliability: crashes directly cause user churn",
            _f("session_routes", "admin_routes"),
        ))

    # Slow endpoints
    slow_endpoints = _safe_query_all(conn, """
        SELECT path as endpoint, COUNT(*) as cnt, ROUND(AVG(duration_ms)) as avg_ms
        FROM request_timing
        WHERE recorded_at >= datetime('now', '-7 days')
          AND duration_ms > 1000
        GROUP BY path
        HAVING cnt >= 3
        ORDER BY avg_ms DESC
        LIMIT 5
    """)
    if slow_endpoints:
        ep_list = ", ".join(f"{r['endpoint']} ({r['avg_ms']}ms)" for r in slow_endpoints)
        findings.append(_finding(
            "engineering", "high" if any(r["avg_ms"] > 2000 for r in slow_endpoints) else "medium",
            f"{len(slow_endpoints)} slow endpoints detected",
            f"Endpoints consistently >1s: {ep_list}.",
            "Profile and optimize slow database queries or add caching.",
            (
                f"Slow endpoints: {ep_list}\n\n"
                "Optimize slow endpoints:\n"
                "1. For each slow endpoint, add EXPLAIN QUERY PLAN to its queries\n"
                f"2. Check {_FILE_MAP['schema']} for missing indexes on WHERE/JOIN columns\n"
                "3. Look for N+1 query patterns in the route handlers\n"
                "4. Consider adding query result caching for read-heavy endpoints"
            ),
            "Satisfaction: slow pages = frustrated users",
            _f("dashboard_routes", "schema"),
        ))

    # Large unindexed tables
    large_tables = _safe_query_all(conn, """
        SELECT name FROM sqlite_master WHERE type='table'
    """)
    for table_row in large_tables:
        table_name = table_row[0] if isinstance(table_row, tuple) else table_row["name"]
        try:
            count = _safe_scalar(conn, f"SELECT COUNT(*) FROM [{table_name}]")
            if count and count > 100000:
                indexes = _safe_query_all(conn, f"PRAGMA index_list([{table_name}])")
                if len(indexes) < 2:
                    findings.append(_finding(
                        "engineering", "medium",
                        f"Large table '{table_name}' ({count:,} rows) with few indexes",
                        f"Table {table_name} has {count:,} rows but only {len(indexes)} indexes.",
                        "Add appropriate indexes to prevent query performance degradation.",
                        (
                            f"Table '{table_name}' has {count:,} rows and {len(indexes)} indexes.\n\n"
                            "Add missing indexes:\n"
                            f"1. Read {_FILE_MAP['schema']} — find the CREATE TABLE for this table\n"
                            "2. Identify columns used in WHERE, JOIN, ORDER BY clauses\n"
                            "3. Add CREATE INDEX IF NOT EXISTS statements"
                        ),
                        "Performance: large unindexed tables cause slow queries",
                        _f("schema"),
                    ))
        except Exception:
            pass

    return findings


def _analyze_security(conn) -> list[dict]:
    findings = []

    # Failed login attempts
    failed_logins = _safe_scalar(conn, """
        SELECT COUNT(*) FROM security_audit_log
        WHERE event_type = 'LOGIN_FAILURE'
          AND timestamp >= datetime('now', '-7 days')
    """)
    if failed_logins and failed_logins > 50:
        findings.append(_finding(
            "security", "critical" if failed_logins > 200 else "high",
            f"{failed_logins} failed login attempts in 7 days",
            "Elevated failed login attempts may indicate brute force attempts.",
            "Review rate limiting and consider IP-based blocking.",
            (
                f"{failed_logins} failed login attempts detected.\n\n"
                "Strengthen authentication defenses:\n"
                f"1. Read {_FILE_MAP['middleware']} — check rate limiting on /api/auth/login\n"
                f"2. Read {_FILE_MAP['security']} — verify account lockout after N failures\n"
                "3. Query: SELECT ip_address, COUNT(*) FROM security_audit_log "
                "WHERE event_type = 'LOGIN_FAILURE' GROUP BY ip_address ORDER BY COUNT(*) DESC\n"
                "4. Consider adding CAPTCHA after 3 failures"
            ),
            "Security: brute force attacks can compromise accounts",
            _f("middleware", "security"),
        ))

    # Admins without MFA
    admins_no_mfa = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE is_admin = 1 AND totp_enabled = 0
    """)
    if admins_no_mfa and admins_no_mfa > 0:
        findings.append(_finding(
            "security", "critical",
            f"{admins_no_mfa} admin account(s) without MFA",
            "Admin accounts without MFA are a significant security risk.",
            "Require MFA for all admin accounts.",
            (
                f"{admins_no_mfa} admin accounts lack MFA.\n\n"
                "Enforce admin MFA:\n"
                f"1. Read {_FILE_MAP['admin_routes']} admin_required decorator\n"
                "2. Verify it blocks admin access without MFA\n"
                "3. Query: SELECT id, email FROM user WHERE is_admin = 1 AND totp_enabled = 0"
            ),
            "Security: admin compromise = full data breach",
            _f("admin_routes"),
        ))

    # High severity security events
    high_severity_events = _safe_scalar(conn, """
        SELECT COUNT(*) FROM security_audit_log
        WHERE severity IN ('CRITICAL', 'HIGH')
          AND timestamp >= datetime('now', '-7 days')
    """)
    if high_severity_events and high_severity_events > 0:
        findings.append(_finding(
            "security", "high",
            f"{high_severity_events} high-severity security events this week",
            "Critical or high-severity security events need immediate review.",
            "Review security audit log and investigate each event.",
            (
                f"{high_severity_events} high-severity security events.\n\n"
                "Investigate security events:\n"
                "1. Query: SELECT event_type, details, ip_address, timestamp "
                "FROM security_audit_log WHERE severity IN ('CRITICAL', 'HIGH') "
                "AND timestamp >= datetime('now', '-7 days') ORDER BY timestamp DESC\n"
                f"2. Check CSRF protection in {_FILE_MAP['middleware']}"
            ),
            "Security: high-severity events may indicate active attacks",
            _f("security", "middleware"),
        ))

    # Session token rotation check
    reused_tokens = _safe_scalar(conn, """
        SELECT COUNT(*) FROM security_audit_log
        WHERE event_type = 'TOKEN_REUSE'
          AND timestamp >= datetime('now', '-7 days')
    """)
    if reused_tokens and reused_tokens > 0:
        findings.append(_finding(
            "security", "high",
            f"{reused_tokens} session token reuse events detected",
            "Session tokens are being reused across authentication events, indicating tokens aren't rotated.",
            "Ensure session tokens are regenerated on login and privilege changes.",
            (
                f"{reused_tokens} token reuse events.\n\n"
                f"1. Check {_FILE_MAP['auth_routes']} — token rotation on login\n"
                "2. Verify session regeneration on privilege escalation\n"
                f"3. Check {_FILE_MAP['middleware']} for session lifecycle management"
            ),
            "Security: token reuse enables session fixation attacks",
            _f("auth_routes", "middleware"),
        ))

    # CORS audit
    cors_events = _safe_scalar(conn, """
        SELECT COUNT(*) FROM security_audit_log
        WHERE event_type LIKE '%CORS%'
          AND timestamp >= datetime('now', '-7 days')
    """)
    if cors_events and cors_events > 0:
        findings.append(_finding(
            "security", "high",
            f"{cors_events} CORS-related security events",
            "CORS misconfiguration can allow cross-origin attacks.",
            "Review CORS configuration.",
            (
                f"{cors_events} CORS events detected.\n\n"
                f"1. Read {_FILE_MAP['middleware']} — review CORS headers\n"
                "2. Ensure only trusted origins are allowed"
            ),
            "Security: CORS issues enable cross-site attacks",
            _f("middleware"),
        ))

    # Rate limit effectiveness
    rate_limited = _safe_scalar(conn, """
        SELECT COUNT(*) FROM security_audit_log
        WHERE event_type = 'RATE_LIMITED'
          AND timestamp >= datetime('now', '-7 days')
    """)
    if rate_limited and rate_limited > 100:
        findings.append(_finding(
            "security", "medium",
            f"{rate_limited} rate-limited requests in 7 days",
            "High rate limiting volume may indicate ongoing attack or misconfigured limits.",
            "Review rate limit thresholds and attacker IPs.",
            (
                f"{rate_limited} rate-limited requests.\n\n"
                f"1. Check {_FILE_MAP['middleware']} rate limit configuration\n"
                "2. Query for top IPs being rate limited\n"
                "3. Consider IP-level blocking for repeat offenders"
            ),
            "Security: rate limiting is working but volume is high",
            _f("middleware"),
        ))

    # API key exposure scan
    api_key_errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_error_log
        WHERE timestamp >= datetime('now', '-7 days')
          AND (error_message LIKE '%api_key=%'
               OR error_message LIKE '%secret_key%'
               OR error_message LIKE '%sk_live_%'
               OR error_message LIKE '%sk_test_%'
               OR error_message LIKE '%password=%'
               OR error_message LIKE '%Authorization: Bearer%')
    """)
    if api_key_errors and api_key_errors > 0:
        findings.append(_finding(
            "security", "critical",
            f"Possible credential exposure in {api_key_errors} client errors",
            "Client error logs contain patterns consistent with actual credential values (API keys, passwords, bearer tokens).",
            "Review client errors for credential leakage immediately.",
            (
                f"{api_key_errors} errors may contain credentials.\n\n"
                "1. Query: SELECT error_message FROM client_error_log WHERE timestamp >= datetime('now', '-7 days') "
                "AND (error_message LIKE '%api_key=%' OR error_message LIKE '%sk_live_%' "
                "OR error_message LIKE '%sk_test_%' OR error_message LIKE '%password=%') LIMIT 10\n"
                "2. Rotate any exposed credentials immediately\n"
                f"3. Check {_FILE_MAP['app_js']} for hardcoded secrets"
            ),
            "Security: exposed credentials = immediate breach risk",
            _f("app_js", "settings"),
        ))

    return findings


def _analyze_timing_friction(conn) -> list[dict]:
    findings = []

    # p95 latency per endpoint
    endpoints_with_volume = _safe_query_all(conn, """
        SELECT path, COUNT(*) as cnt
        FROM request_timing
        WHERE recorded_at >= datetime('now', '-7 days')
        GROUP BY path
        HAVING cnt >= 10
    """)
    for ep in (endpoints_with_volume or []):
        path = ep["path"]
        cnt = ep["cnt"]
        offset_95 = max(0, int(cnt * 0.05))
        p95_row = _safe_query(conn, """
            SELECT duration_ms FROM request_timing
            WHERE recorded_at >= datetime('now', '-7 days') AND path = ?
            ORDER BY duration_ms DESC
            LIMIT 1 OFFSET ?
        """, (path, offset_95))
        if p95_row:
            p95_ms = p95_row[0]
            if p95_ms > 500:
                median_row = _safe_query(conn, """
                    SELECT duration_ms FROM request_timing
                    WHERE recorded_at >= datetime('now', '-7 days') AND path = ?
                    ORDER BY duration_ms ASC
                    LIMIT 1 OFFSET ?
                """, (path, cnt // 2))
                median_ms = median_row[0] if median_row else 0
                findings.append(_finding(
                    "timing", "high" if p95_ms > 1000 else "medium",
                    f"Slow endpoint: {path} p95={p95_ms}ms (median={median_ms}ms, n={cnt})",
                    f"{path} p95 latency is {p95_ms}ms across {cnt} requests (median {median_ms}ms). "
                    f"{'Tail latency issue — most requests are fast but some are very slow.' if median_ms < p95_ms * 0.3 else 'Consistently slow endpoint.'}",
                    "Optimize this endpoint's queries or add caching.",
                    (
                        f"{path}: p95={p95_ms}ms, median={median_ms}ms, n={cnt}.\n\n"
                        "1. Profile the endpoint's database queries with EXPLAIN QUERY PLAN\n"
                        f"2. Check {_FILE_MAP['schema']} for missing indexes\n"
                        "3. If tail latency: look for lock contention or GC pauses"
                    ),
                    "Satisfaction: slow endpoints frustrate users",
                    _f("dashboard_routes", "schema"),
                ))

    # Sessions with very slow inter-drill gaps
    slow_gap_sessions = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_event
        WHERE category = 'drill_timing' AND event = 'response'
          AND json_extract(detail, '$.gap_ms') > 5000
          AND created_at >= datetime('now', '-7 days')
    """)
    if slow_gap_sessions and slow_gap_sessions > 5:
        findings.append(_finding(
            "timing", "medium",
            f"{slow_gap_sessions} drill transitions with >5s gap",
            "Some drills take >5 seconds between prompts — something may be slow or broken.",
            "Check server-side drill generation and WebSocket delivery.",
            (
                f"{slow_gap_sessions} slow drill gaps detected.\n\n"
                f"1. Check {_FILE_MAP['bridge']} WS message delivery\n"
                f"2. Profile {_FILE_MAP['scheduler']} drill selection"
            ),
            "Satisfaction: slow transitions break flow",
            _f("bridge", "scheduler"),
        ))

    # First-drill latency
    slow_first_drill = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_event
        WHERE category = 'drill_timing' AND event = 'first_drill_latency'
          AND json_extract(detail, '$.ms') > 3000
          AND created_at >= datetime('now', '-7 days')
    """)
    if slow_first_drill and slow_first_drill > 3:
        findings.append(_finding(
            "timing", "high",
            f"{slow_first_drill} sessions with >3s first-drill latency",
            "Sessions take too long to show the first drill — feels sluggish.",
            "Optimize session initialization and drill planning.",
            (
                f"{slow_first_drill} slow session starts.\n\n"
                f"1. Profile {_FILE_MAP['session_routes']} session initialization\n"
                f"2. Check {_FILE_MAP['scheduler']} for startup queries"
            ),
            "Satisfaction: slow start = user leaves before engaging",
            _f("session_routes", "scheduler"),
        ))

    return findings


def _analyze_platform_cohort(conn) -> list[dict]:
    findings = []

    platform_stats = _safe_query_all(conn, """
        SELECT client_platform,
               COUNT(*) as sessions,
               AVG(CASE WHEN items_completed > 0 THEN
                   CAST(items_completed AS REAL) / NULLIF(items_planned, 0) * 100 END) as completion,
               AVG(duration_seconds) as avg_duration
        FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
          AND client_platform IS NOT NULL
        GROUP BY client_platform
        HAVING sessions >= 5
    """)
    if platform_stats and len(platform_stats) >= 2:
        overall_completion = sum((r["completion"] or 0) * r["sessions"] for r in platform_stats)
        total_sessions = sum(r["sessions"] for r in platform_stats)
        if total_sessions > 0:
            avg_completion = overall_completion / total_sessions
            for row in platform_stats:
                pf = row["client_platform"]
                comp = row["completion"] or 0
                if comp < avg_completion - 15:
                    findings.append(_finding(
                        "platform", "high",
                        f"Platform '{pf}' has {round(comp, 1)}% completion (avg {round(avg_completion, 1)}%)",
                        f"{pf} users complete sessions at {round(comp, 1)}% vs overall {round(avg_completion, 1)}%.",
                        f"Investigate {pf}-specific issues.",
                        (
                            f"Platform '{pf}' underperforms by {round(avg_completion - comp, 1)}pp.\n\n"
                            "1. Check client_error_log filtered by platform\n"
                            f"2. Test the app on {pf}\n"
                            "3. Look for platform-specific JS errors"
                        ),
                        f"Satisfaction: {pf} users are having a degraded experience",
                        _f("app_js", "style_css"),
                    ))

    # Platform-specific error spikes
    platform_errors = _safe_query_all(conn, """
        SELECT
            CASE WHEN page_url LIKE '%capacitor%' THEN 'ios'
                 WHEN page_url LIKE '%localhost%' THEN 'web_local'
                 ELSE 'web' END as platform,
            COUNT(*) as cnt
        FROM client_error_log
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY platform
    """)
    for row in platform_errors:
        if row["cnt"] > 20:
            findings.append(_finding(
                "platform", "medium",
                f"{row['cnt']} client errors on '{row['platform']}' in 7 days",
                f"Elevated error rate on {row['platform']}.",
                f"Investigate {row['platform']}-specific error patterns.",
                (
                    f"{row['cnt']} errors on {row['platform']}.\n\n"
                    "1. Query: SELECT error_type, error_message, COUNT(*) FROM client_error_log "
                    f"WHERE timestamp >= datetime('now', '-7 days') "
                    f"GROUP BY error_type ORDER BY COUNT(*) DESC LIMIT 10"
                ),
                f"Satisfaction: {row['platform']} users impacted",
                _f("app_js"),
            ))

    return findings


def _analyze_frustration(conn) -> list[dict]:
    findings = []

    total_sessions_7d = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
    """)
    rage_clicks = _safe_scalar(conn, """
        SELECT COUNT(*)
        FROM client_event
        WHERE category = 'ux' AND event = 'rage_click'
          AND created_at >= datetime('now', '-7 days')
    """)
    if total_sessions_7d and total_sessions_7d >= 10:
        rage_rate = round((rage_clicks or 0) / total_sessions_7d * 100, 1) if total_sessions_7d > 0 else 0
        if rage_rate > 5:
            findings.append(_finding(
                "frustration", "high",
                f"Rage click rate: {rage_rate}% of sessions",
                f"{rage_clicks} sessions had rage clicks in the last 7 days.",
                "Users are clicking repeatedly in frustration. Check for unresponsive UI elements.",
                (
                    f"Rage click rate is {rage_rate}%.\n\n"
                    "Fix rage click targets:\n"
                    "1. Query: SELECT json_extract(detail, '$.target') as target, COUNT(*) "
                    "FROM client_event WHERE category = 'ux' AND event = 'rage_click' "
                    "GROUP BY target ORDER BY COUNT(*) DESC\n"
                    "2. For each target: add click feedback, fix latency, or improve affordance"
                ),
                "Satisfaction: rage clicks = frustrated users",
                _f("app_js"),
            ))

    # Dead clicks (only flag with meaningful session volume)
    dead_clicks = _safe_query_all(conn, """
        SELECT json_extract(detail, '$.target') as target, COUNT(*) as cnt
        FROM client_event
        WHERE category = 'ux' AND event = 'dead_click'
          AND created_at >= datetime('now', '-7 days')
        GROUP BY target
        HAVING cnt >= 5
        ORDER BY cnt DESC
        LIMIT 5
    """)
    if dead_clicks and total_sessions_7d and total_sessions_7d >= 10:
        targets = ", ".join(f"{r['target']} ({r['cnt']}x)" for r in dead_clicks)
        findings.append(_finding(
            "frustration", "medium",
            f"Dead clicks detected on {len(dead_clicks)} elements",
            f"Users are clicking on non-interactive elements: {targets}",
            "Make these elements interactive or change their visual affordance.",
            (
                f"Dead click targets: {targets}\n\n"
                "Fix dead clicks:\n"
                "1. For each target: either make it clickable or style it clearly as non-interactive\n"
                f"2. Check {_FILE_MAP['style_css']} for cursor styles\n"
                f"3. Update {_FILE_MAP['app_js']} to add click handlers where appropriate"
            ),
            "Satisfaction: dead clicks = confusing UI",
            _f("app_js", "style_css"),
        ))

    # Frustration spiral: 3+ errors in a row
    error_streaks = _safe_scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT user_id, session_id,
                   SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) as errors,
                   COUNT(*) as total
            FROM review_event
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY user_id, session_id
            HAVING errors >= 3 AND errors > total * 0.6
        )
    """)
    if error_streaks and error_streaks > 5:
        findings.append(_finding(
            "frustration", "medium",
            f"{error_streaks} sessions with frustration spiral (>60% errors)",
            "Multiple sessions have high error rates, indicating material is too hard.",
            "Review difficulty calibration — these users need easier content.",
            (
                f"{error_streaks} frustration spiral sessions.\n\n"
                f"1. Review {_FILE_MAP['scheduler']} difficulty selection\n"
                "2. Check if specific users consistently get hard items\n"
                "3. Consider adding difficulty adjustment after 3 consecutive errors"
            ),
            "Satisfaction: frustration spirals cause churn",
            _f("scheduler"),
        ))

    # Frustrated abandonments
    frustrated_exits = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE early_exit = 1 AND boredom_flags > 0
          AND started_at >= datetime('now', '-7 days')
    """)
    if frustrated_exits and frustrated_exits > 3:
        findings.append(_finding(
            "frustration", "medium",
            f"{frustrated_exits} frustrated abandonments in 7 days",
            "Sessions ended early with boredom flags — users are leaving frustrated.",
            "Review what triggers boredom flags and whether sessions are engaging enough.",
            (
                f"{frustrated_exits} frustrated exits.\n\n"
                f"1. Check {_FILE_MAP['scheduler']} boredom detection logic\n"
                "2. Review drill variety and difficulty in affected sessions"
            ),
            "Satisfaction: frustrated exits predict churn",
            _f("scheduler"),
        ))

    return findings


def _analyze_pm_product(conn) -> list[dict]:
    findings = []

    # Feature adoption (drill types)
    drill_usage = _safe_query_all(conn, """
        SELECT drill_type, COUNT(*) as cnt
        FROM review_event
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY drill_type
        ORDER BY cnt DESC
    """)
    if drill_usage and len(drill_usage) >= 3:
        total_drills = sum(r["cnt"] for r in drill_usage)
        underused = [r for r in drill_usage if r["cnt"] < total_drills * 0.02]
        if underused:
            underused_names = ", ".join(r["drill_type"] or "unknown" for r in underused)
            findings.append(_finding(
                "pm", "medium",
                f"{len(underused)} drill types used <2% of the time",
                f"Underused drill types: {underused_names}.",
                "Either improve underused drill types or remove them to simplify.",
                (
                    f"Underused drill types: {underused_names}\n\n"
                    "Address underused features:\n"
                    f"1. Read {_FILE_MAP['drills']} — understand each drill type's purpose\n"
                    f"2. Check {_FILE_MAP['scheduler']} — are underused drills being scheduled?\n"
                    "3. For each underused type, decide: improve, promote, or remove"
                ),
                "Product: unused features add complexity without value",
                _f("drills", "scheduler"),
            ))

    # Stale backlog
    stale_items = _safe_scalar(conn, """
        SELECT COUNT(*) FROM work_item
        WHERE status NOT IN ('done', 'archived')
          AND updated_at <= datetime('now', '-30 days')
    """)
    if stale_items and stale_items > 3:
        findings.append(_finding(
            "pm", "medium",
            f"{stale_items} stale backlog items (>30 days untouched)",
            "Work items that haven't been updated in 30+ days may be abandoned.",
            "Review and either complete, descope, or archive stale items.",
            (
                f"{stale_items} stale work items.\n\n"
                "Clean up backlog:\n"
                "1. Query: SELECT id, title, status, created_at, updated_at FROM work_item "
                "WHERE status NOT IN ('done', 'archived') AND updated_at <= datetime('now', '-30 days') "
                "ORDER BY updated_at ASC"
            ),
            "PM: stale backlogs signal prioritization problems",
            [],
        ))

    # A/B tests (only nag when there's enough traffic to run experiments)
    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user")
    active_experiments = _safe_scalar(conn, """
        SELECT COUNT(*) FROM experiment WHERE status = 'running'
    """)
    if active_experiments == 0 and total_users and total_users >= 20:
        findings.append(_finding(
            "pm", "medium",
            "No A/B tests currently running",
            "There are no active experiments. Data-driven decisions require experiments.",
            "Design and launch at least one experiment.",
            (
                "No active experiments.\n\n"
                f"1. Read {_FILE_MAP['admin_routes']} — experiment endpoints\n"
                "2. Identify a hypothesis to test\n"
                "3. Create experiment via POST /api/admin/experiments"
            ),
            "Product: no experiments = guessing, not learning",
            _f("admin_routes"),
        ))

    # NPS detractors
    detractors = _safe_query_all(conn, """
        SELECT comment FROM user_feedback
        WHERE feedback_type = 'nps' AND rating <= 6
          AND comment IS NOT NULL AND comment != ''
          AND created_at >= datetime('now', '-30 days')
        ORDER BY created_at DESC LIMIT 10
    """)
    if detractors and len(detractors) >= 3:
        comments = "; ".join((r["comment"] or "")[:80] for r in detractors[:5])
        findings.append(_finding(
            "pm", "high",
            f"{len(detractors)} NPS detractors with comments (last 30 days)",
            f"Recent detractor feedback: {comments}",
            "Analyze feedback themes and address the most common complaints.",
            (
                f"NPS detractor feedback (last 30d):\n"
                + "\n".join(f"- {r['comment'][:120]}" for r in detractors)
                + "\n\nAddress detractor feedback:\n"
                "1. Group complaints by theme (difficulty, UX, content, bugs)\n"
                "2. For each theme, identify the relevant code and fix"
            ),
            "Satisfaction: detractors actively discourage others from using the product",
            [],
        ))

    return findings


ANALYZERS = [
    _analyze_engineering,
    _analyze_security,
    _analyze_timing_friction,
    _analyze_platform_cohort,
    _analyze_frustration,
    _analyze_pm_product,
]
