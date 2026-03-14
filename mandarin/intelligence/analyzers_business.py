"""Product Intelligence — business analyzers (profitability, retention, marketing, onboarding, competitive)."""

from ._base import _f, _FILE_MAP, _finding, _safe_query, _safe_query_all, _safe_scalar


def _analyze_profitability(conn) -> list[dict]:
    findings = []

    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user")
    if total_users == 0:
        findings.append(_finding(
            "profitability", "medium", "No users yet",
            "The user table is empty. No profitability analysis is possible.",
            "Focus on acquiring first users before optimizing monetization.",
            "No data-driven prompt available yet. Focus on user acquisition first.",
            "N/A until users exist",
            [],
        ))
        return findings

    # Tier distribution
    paid_users = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM user WHERE subscription_tier = 'paid'",
    )
    free_users = total_users - paid_users
    conversion_rate = round(paid_users / total_users * 100, 1) if total_users > 0 else 0

    if conversion_rate < 2:
        severity = "critical"
    elif conversion_rate < 5:
        severity = "high"
    elif conversion_rate < 10:
        severity = "medium"
    else:
        severity = None

    if severity:
        findings.append(_finding(
            "profitability", severity,
            f"Low conversion rate: {conversion_rate}% free-to-paid",
            f"{paid_users} of {total_users} users are paid ({conversion_rate}%). "
            f"Industry benchmark for language apps is 5-10%.",
            "Investigate paywall placement, trial experience, and value proposition clarity. "
            "Consider offering a longer free trial or highlighting paid-only features earlier.",
            (
                f"Conversion rate is {conversion_rate}% ({paid_users}/{total_users} users).\n\n"
                "Improve free-to-paid conversion:\n"
                f"1. Read {_FILE_MAP['pricing_template']} — check if value props are clear\n"
                f"2. Read {_FILE_MAP['payment_routes']} — check paywall triggers and trial flow\n"
                "3. Check if free users hit a compelling 'aha moment' before the paywall\n"
                f"4. Consider adding a 'preview paid features' section to the dashboard\n"
                f"5. Review {_FILE_MAP['email']} for trial expiration and upgrade nudge emails"
            ),
            f"Revenue: converting even 2% more users = {max(1, int(free_users * 0.02))} new paid users",
            _f("pricing_template", "payment_routes", "email"),
        ))

    # Churn indicators
    churned = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON s.user_id = u.id
        WHERE u.id NOT IN (
            SELECT DISTINCT user_id FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
        )
        AND u.is_active = 1
    """)
    if churned and total_users > 0:
        churn_pct = round(churned / total_users * 100, 1)
        if churn_pct > 50:
            findings.append(_finding(
                "profitability", "critical",
                f"High churn: {churn_pct}% of users inactive >14 days",
                f"{churned} users had sessions previously but none in the last 14 days.",
                "Implement win-back campaigns and investigate why users leave.",
                (
                    f"{churned} users ({churn_pct}%) are inactive >14 days.\n\n"
                    "Reduce churn:\n"
                    f"1. Read {_FILE_MAP['email']} — check win-back / re-engagement emails\n"
                    "2. Query session_log for the last session of churned users to find patterns\n"
                    "3. Check if churn correlates with specific session types or drill difficulty\n"
                    f"4. Review {_FILE_MAP['scheduler']} — are sessions too hard or too easy?\n"
                    "5. Add a 'welcome back' flow for returning users"
                ),
                f"Retention: recovering {int(churned * 0.1)} users = meaningful LTV increase",
                _f("email", "scheduler", "dashboard_routes"),
            ))

    # Revenue per user
    try:
        from ..settings import PRICING
        monthly_price = float(PRICING["monthly_display"])
        revenue_per_user = round(paid_users * monthly_price / total_users, 2) if total_users > 0 else 0
        if revenue_per_user < 1.0 and total_users >= 10:
            findings.append(_finding(
                "profitability", "high",
                f"Low ARPU: ${revenue_per_user}/user/month",
                f"Average revenue per user is ${revenue_per_user}. With {paid_users} paid users "
                f"at ${monthly_price}/mo across {total_users} total users.",
                "Increase ARPU through better conversion, upselling annual plans, or premium features.",
                (
                    f"ARPU is ${revenue_per_user}/user/month.\n\n"
                    "Improve revenue per user:\n"
                    f"1. Read {_FILE_MAP['settings']} PRICING — evaluate if pricing is competitive\n"
                    f"2. Check {_FILE_MAP['pricing_template']} — annual plan prominence\n"
                    "3. Consider adding premium tiers (classroom, family plans)\n"
                    "4. Review if annual plan discount is compelling enough"
                ),
                f"Revenue: each $0.50 ARPU increase = ${round(total_users * 0.5, 0)}/month",
                _f("settings", "pricing_template"),
            ))
    except (ImportError, KeyError, TypeError):
        pass

    # LTV cohort analysis
    ltv_data = _safe_query(conn, """
        SELECT
            AVG(julianday('now') - julianday(created_at)) as avg_account_days,
            AVG(CASE WHEN subscription_expires_at IS NOT NULL
                THEN julianday(subscription_expires_at) - julianday('now') END) as avg_remaining
        FROM user WHERE subscription_tier = 'paid' AND is_active = 1
    """)
    if ltv_data and ltv_data[0] is not None:
        avg_account_days = ltv_data[0]
        churned_recently = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier = 'paid' AND subscription_status = 'canceled'
              AND updated_at >= datetime('now', '-30 days')
        """)
        if avg_account_days < 30 and paid_users >= 3 and (churned_recently or 0) > 0:
            findings.append(_finding(
                "profitability", "high",
                f"Short average paid account age: {round(avg_account_days, 0)} days with active churn",
                f"Paid user accounts average {round(avg_account_days, 0)} days old and {churned_recently} "
                "recently canceled. Note: this measures account age, not subscription length — "
                "consider adding a subscription_started_at column for accurate LTV tracking.",
                "Investigate what causes paid users to cancel. Improve post-conversion experience.",
                (
                    f"Average paid account age: {round(avg_account_days, 0)} days, {churned_recently} recent cancellations.\n\n"
                    "Improve paid retention:\n"
                    f"1. Read {_FILE_MAP['scheduler']} — is the experience better for paid users?\n"
                    "2. Check what paid-only features are unlocked and how visible they are\n"
                    "3. Review cancellation flow for win-back opportunities\n"
                    "4. Consider adding subscription_started_at column to user table for accurate LTV"
                ),
                "Revenue: each month of extended tenure = significant LTV increase",
                _f("scheduler", "payment_routes"),
            ))

    # Trial-to-paid timing
    trial_conversion = _safe_query(conn, """
        SELECT AVG(julianday(u.updated_at) - julianday(u.created_at)) as avg_days,
               COUNT(*) as sample_size
        FROM user u WHERE u.subscription_tier = 'paid'
          AND u.created_at >= datetime('now', '-90 days')
    """)
    if trial_conversion and trial_conversion[0] is not None:
        avg_days = trial_conversion[0]
        sample_size = trial_conversion[1] or 0
        if avg_days > 14 and sample_size >= 3:
            findings.append(_finding(
                "profitability", "medium",
                f"Slow trial-to-paid conversion: ~{round(avg_days, 0)} days (estimated, n={sample_size})",
                f"Users take approximately {round(avg_days, 0)} days to convert (based on updated_at proxy, "
                f"sample={sample_size}). This is directional — updated_at may reflect non-conversion changes.",
                "Accelerate the path to paid by showcasing value earlier. "
                "Consider adding a subscription_started_at column for accurate measurement.",
                (
                    f"Trial-to-paid estimated at ~{round(avg_days, 0)} days (n={sample_size}).\n\n"
                    "Accelerate conversion:\n"
                    "1. Show paid feature previews earlier in the free experience\n"
                    "2. Add a compelling trial offer after session 3\n"
                    f"3. Review {_FILE_MAP['payment_routes']} for trial timing logic\n"
                    "4. Add subscription_started_at column for accurate conversion tracking"
                ),
                "Revenue: faster conversion = higher conversion rate",
                _f("payment_routes", "pricing_template"),
            ))

    # Churn revenue impact
    if paid_users > 0:
        churned_paid = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier = 'paid'
              AND subscription_status = 'canceled'
              AND updated_at >= datetime('now', '-30 days')
        """)
        if churned_paid and churned_paid > 0:
            try:
                from ..settings import PRICING
                monthly_price = float(PRICING["monthly_display"])
                lost_mrr = round(churned_paid * monthly_price, 2)
                findings.append(_finding(
                    "profitability", "high",
                    f"{churned_paid} paid users churned in last 30 days (${lost_mrr} MRR lost)",
                    f"{churned_paid} paid cancellations = ${lost_mrr}/mo in lost revenue.",
                    "Review cancellation reasons and implement win-back flow.",
                    (
                        f"{churned_paid} paid users canceled recently = ${lost_mrr}/mo lost.\n\n"
                        "Reduce paid churn:\n"
                        "1. Add cancellation survey to capture reasons\n"
                        "2. Implement pause-instead-of-cancel option\n"
                        f"3. Review {_FILE_MAP['email']} for win-back emails"
                    ),
                    f"Revenue: recovering {churned_paid} users = ${lost_mrr}/mo",
                    _f("payment_routes", "email"),
                ))
            except (ImportError, KeyError, TypeError):
                pass

    return findings


def _analyze_retention(conn) -> list[dict]:
    findings = []

    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user")
    if total_users == 0:
        return findings

    # Day 1 retention
    d1_eligible = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE created_at <= datetime('now', '-1 day')
    """)
    d1_retained = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON s.user_id = u.id
        WHERE u.created_at <= datetime('now', '-1 day')
          AND s.started_at >= datetime(u.created_at, '+1 day')
    """)
    if d1_eligible and d1_eligible >= 5:
        d1_rate = round(d1_retained / d1_eligible * 100, 1)
        if d1_rate < 40:
            findings.append(_finding(
                "retention", "critical" if d1_rate < 20 else "high",
                f"D1 retention: {d1_rate}% ({d1_retained}/{d1_eligible})",
                f"Only {d1_rate}% of users return after their first day. "
                f"Benchmark for language apps is 40-60%.",
                "Improve first-session experience and add day-1 engagement hooks.",
                (
                    f"D1 retention is {d1_rate}%.\n\n"
                    "Improve day-1 return rate:\n"
                    f"1. Read {_FILE_MAP['dashboard_template']} — is there a clear next-step CTA?\n"
                    f"2. Check {_FILE_MAP['email']} — is there a day-1 follow-up email?\n"
                    f"3. Review {_FILE_MAP['scheduler']} — is the first session too hard/long?\n"
                    "4. Consider adding a 'streak started' celebration after session 1\n"
                    "5. Add push notification for day-1 reminder"
                ),
                "Retention: +10% D1 retention compounds to major LTV improvement",
                _f("dashboard_template", "email", "scheduler"),
            ))

    # Day 7 retention
    d7_eligible = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE created_at <= datetime('now', '-7 days')
    """)
    d7_retained = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT u.id) FROM user u
        JOIN session_log s ON s.user_id = u.id
        WHERE u.created_at <= datetime('now', '-7 days')
          AND s.started_at >= datetime(u.created_at, '+7 days')
    """)
    if d7_eligible and d7_eligible >= 5:
        d7_rate = round(d7_retained / d7_eligible * 100, 1)
        if d7_rate < 30:
            findings.append(_finding(
                "retention", "critical" if d7_rate < 15 else "high",
                f"D7 retention: {d7_rate}% ({d7_retained}/{d7_eligible})",
                f"Only {d7_rate}% of users are active after 7 days. "
                f"Benchmark is 30-40%.",
                "Build a compelling first-week experience with progressive difficulty.",
                (
                    f"D7 retention is {d7_rate}%.\n\n"
                    "Improve week-1 retention:\n"
                    f"1. Read {_FILE_MAP['scheduler']} — check first-week session planning\n"
                    f"2. Review {_FILE_MAP['email']} — week-1 drip email sequence\n"
                    "3. Check if users hit the 'magic moment' (first lookup drilled) within 7 days\n"
                    "4. Consider a 7-day guided onboarding path"
                ),
                "Retention: D7 is the strongest predictor of long-term retention",
                _f("scheduler", "email"),
            ))

    # Weekly active rate
    streak_users = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
    """)
    if streak_users and total_users >= 5:
        streak_pct = round(streak_users / total_users * 100, 1)
        if streak_pct < 20:
            findings.append(_finding(
                "retention", "medium",
                f"Low weekly active rate: {streak_pct}%",
                f"Only {streak_users} of {total_users} users had sessions in the last 7 days.",
                "Investigate re-engagement mechanisms and session reminders.",
                (
                    f"Only {streak_pct}% of users are active this week.\n\n"
                    "Improve weekly engagement:\n"
                    f"1. Check {_FILE_MAP['email']} — weekly digest / reminder emails\n"
                    "2. Check streak freeze mechanics — are they helping retain users?\n"
                    "3. Consider adding 'minimal session' (2-3 min) for low-motivation days"
                ),
                "Retention: weekly active users are the core health metric",
                _f("email", "dashboard_routes"),
            ))

    return findings


def _analyze_marketing(conn) -> list[dict]:
    findings = []

    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user")
    if total_users == 0:
        return findings

    # UTM tracking
    users_with_utm = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE utm_source IS NOT NULL
    """)
    if total_users >= 10 and (users_with_utm or 0) < total_users * 0.3:
        findings.append(_finding(
            "marketing", "medium",
            f"Only {users_with_utm or 0}/{total_users} users have UTM tracking",
            "Most users don't have acquisition channel attribution.",
            "Add UTM tracking to all marketing links and referral sources.",
            (
                f"Only {round((users_with_utm or 0) / total_users * 100, 1)}% of users have UTM attribution.\n\n"
                "Improve attribution tracking:\n"
                f"1. Read {_FILE_MAP['auth_routes']} — registration flow\n"
                "2. Ensure UTM params are captured at signup\n"
                "3. Add UTM params to all marketing links, emails, and social posts"
            ),
            "Marketing: can't optimize what you can't measure",
            _f("auth_routes"),
        ))

    # Referrals
    referrals = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE invited_by IS NOT NULL
    """)
    if total_users >= 20 and (referrals or 0) == 0:
        findings.append(_finding(
            "marketing", "medium",
            "No referral-driven signups",
            "No users have been referred by existing users.",
            "Implement or promote a referral program.",
            (
                "Zero referral signups detected.\n\n"
                "Build referral program:\n"
                f"1. Check if referral system exists in {_FILE_MAP['auth_routes']}\n"
                "2. Add 'Invite a friend' button to the dashboard\n"
                "3. Consider offering incentives (free month, streak freezes)"
            ),
            "Marketing: referrals are the cheapest acquisition channel",
            _f("auth_routes", "dashboard_template"),
        ))

    # Referral conversion rate
    if referrals and referrals > 0 and total_users >= 20:
        referral_pct = round(referrals / total_users * 100, 1)
        if referral_pct < 5:
            findings.append(_finding(
                "marketing", "low",
                f"Low referral rate: {referral_pct}%",
                f"Only {referrals} of {total_users} users came from referrals ({referral_pct}%).",
                "Increase referral visibility and incentives.",
                (
                    f"Referral rate is {referral_pct}%.\n\n"
                    "Boost referrals:\n"
                    "1. Add referral prompt after session completion\n"
                    "2. Show referral stats on dashboard"
                ),
                "Marketing: viral growth requires active referral program",
                _f("dashboard_routes", "dashboard_template"),
            ))

    # Email open/click rates
    email_sent = _safe_scalar(conn, """
        SELECT COUNT(*) FROM lifecycle_event
        WHERE event_type = 'email_sent'
          AND created_at >= datetime('now', '-30 days')
    """)
    email_opened = _safe_scalar(conn, """
        SELECT COUNT(*) FROM lifecycle_event
        WHERE event_type = 'email_opened'
          AND created_at >= datetime('now', '-30 days')
    """)
    if email_sent and email_sent >= 20:
        open_rate = round((email_opened or 0) / email_sent * 100, 1)
        if open_rate < 20:
            findings.append(_finding(
                "marketing", "medium",
                f"Low email open rate: {open_rate}%",
                f"{email_opened or 0} of {email_sent} emails opened ({open_rate}%). Industry benchmark is 20-30%.",
                "Improve email subject lines and sending times.",
                (
                    f"Email open rate is {open_rate}%.\n\n"
                    f"1. Review {_FILE_MAP['email']} — subject line quality\n"
                    "2. Test different send times\n"
                    "3. Segment emails by user engagement level"
                ),
                "Marketing: emails that aren't opened can't convert",
                _f("email"),
            ))

    # UTM attribution analysis
    utm_sources = _safe_query_all(conn, """
        SELECT utm_source, COUNT(*) as cnt,
               COUNT(CASE WHEN first_session_at IS NOT NULL THEN 1 END) as activated
        FROM user
        WHERE utm_source IS NOT NULL
        GROUP BY utm_source
        HAVING cnt >= 5
        ORDER BY cnt DESC LIMIT 5
    """)
    for src in utm_sources:
        source = src["utm_source"]
        cnt = src["cnt"]
        activated = src["activated"] or 0
        activation_rate = round(activated / cnt * 100, 1) if cnt > 0 else 0
        if activation_rate < 30:
            findings.append(_finding(
                "marketing", "medium",
                f"Low activation from '{source}': {activation_rate}% ({activated}/{cnt})",
                f"Users from {source} have low activation. Channel may attract wrong audience.",
                "Review targeting and messaging for this channel.",
                (
                    f"UTM source '{source}': {activation_rate}% activation rate.\n\n"
                    "1. Review landing page copy for this source\n"
                    "2. Check if expectations set in ads match the product\n"
                    "3. Consider adjusting targeting or messaging"
                ),
                f"Marketing: low activation from {source} wastes acquisition spend",
                _f("landing_routes", "marketing_routes"),
            ))

    return findings


def _analyze_onboarding(conn) -> list[dict]:
    findings = []

    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user")
    if total_users < 5:
        return findings

    # Signup to first session
    users_with_session = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE first_session_at IS NOT NULL
    """)
    if total_users > 0:
        first_session_rate = round((users_with_session or 0) / total_users * 100, 1)
        if first_session_rate < 60:
            findings.append(_finding(
                "onboarding", "critical" if first_session_rate < 30 else "high",
                f"Only {first_session_rate}% of signups start a session",
                f"{users_with_session or 0} of {total_users} users have completed their first session.",
                "The gap between signup and first session is too large. Simplify onboarding.",
                (
                    f"Signup-to-first-session rate: {first_session_rate}%\n\n"
                    "Improve onboarding completion:\n"
                    f"1. Read {_FILE_MAP['onboarding_routes']} — onboarding flow after registration\n"
                    "2. Reduce steps between registration and first drill\n"
                    "3. Consider auto-starting a mini session after signup\n"
                    f"4. Check {_FILE_MAP['email']} — is there an immediate welcome email with CTA?"
                ),
                "Retention: users who never start a session never come back",
                _f("onboarding_routes", "email"),
            ))

    # Activation rate
    activated = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user WHERE activation_at IS NOT NULL
    """)
    if users_with_session and users_with_session > 0:
        activation_rate = round((activated or 0) / users_with_session * 100, 1)
        if activation_rate < 50 and users_with_session >= 5:
            findings.append(_finding(
                "onboarding", "high",
                f"Activation rate: {activation_rate}% (session -> activated)",
                f"Only {activated or 0} of {users_with_session} users who started a session "
                f"reached the activation milestone.",
                "The activation moment isn't compelling enough.",
                (
                    f"Activation rate is {activation_rate}%.\n\n"
                    "Improve activation:\n"
                    "1. Grep codebase for 'activation_at' to find the trigger condition\n"
                    "2. Make the activation moment feel rewarding (celebration UI)\n"
                    "3. Ensure the path to activation is clear and achievable in session 1"
                ),
                "Retention: activated users are 3-5x more likely to retain",
                _f("onboarding_routes", "scheduler"),
            ))

    # First session completion vs subsequent
    first_sessions = _safe_query(conn, """
        SELECT AVG(CASE WHEN items_completed > 0 THEN
            CAST(items_completed AS REAL) / NULLIF(items_planned, 0) * 100
        END) as avg_completion
        FROM session_log s
        JOIN user u ON s.user_id = u.id
        WHERE s.started_at = u.first_session_at
    """)
    subsequent = _safe_query(conn, """
        SELECT AVG(CASE WHEN items_completed > 0 THEN
            CAST(items_completed AS REAL) / NULLIF(items_planned, 0) * 100
        END) as avg_completion
        FROM session_log s
        JOIN user u ON s.user_id = u.id
        WHERE s.started_at != u.first_session_at
    """)
    if first_sessions and subsequent:
        first_comp = first_sessions["avg_completion"]
        subseq_comp = subsequent["avg_completion"]
        if first_comp is not None and subseq_comp is not None and first_comp < subseq_comp - 15:
            findings.append(_finding(
                "onboarding", "medium",
                f"First sessions complete at {round(first_comp, 1)}% vs {round(subseq_comp, 1)}% subsequent",
                "First sessions have notably lower completion than later sessions.",
                "Make first sessions shorter or easier to build early confidence.",
                (
                    f"First session completion: {round(first_comp, 1)}% vs subsequent: {round(subseq_comp, 1)}%\n\n"
                    "Improve first session experience:\n"
                    f"1. Read {_FILE_MAP['scheduler']} — special handling for first session?\n"
                    "2. Consider reducing first session to 5-6 items (vs normal 8-12)\n"
                    "3. Use easier items for first session (HSK 1 only)"
                ),
                "Retention: first session completion predicts long-term retention",
                _f("scheduler"),
            ))

    return findings


def _analyze_competitive(conn) -> list[dict]:
    findings = []

    # HSK level content coverage
    hsk_coverage = _safe_query_all(conn, """
        SELECT hsk_level, COUNT(*) as cnt
        FROM content_item
        WHERE hsk_level IS NOT NULL
        GROUP BY hsk_level
        ORDER BY hsk_level
    """)
    if hsk_coverage:
        total_content = sum(r["cnt"] for r in hsk_coverage)
        thin_levels = [r for r in hsk_coverage if r["cnt"] < 20]
        covered_levels = {r["hsk_level"] for r in hsk_coverage}
        missing_levels = [l for l in range(1, 7) if l not in covered_levels]

        if missing_levels:
            findings.append(_finding(
                "competitive", "high",
                f"No content for HSK levels: {missing_levels}",
                f"HSK levels {missing_levels} have zero content items.",
                "Add seed content for missing HSK levels.",
                (
                    f"Missing content for HSK levels: {missing_levels}\n\n"
                    "Add content:\n"
                    "1. Read scripts/ for content seeding patterns\n"
                    "2. Add at least 50 items per missing HSK level"
                ),
                "Competitive: incomplete HSK coverage loses users to competitors",
                ["scripts/"],
            ))

        if thin_levels:
            thin_info = ", ".join(f"HSK {r['hsk_level']}: {r['cnt']}" for r in thin_levels)
            findings.append(_finding(
                "competitive", "medium",
                "Thin content at some HSK levels",
                f"Low item counts: {thin_info}. Total content: {total_content}.",
                "Expand content library for underserved HSK levels.",
                (
                    f"Thin content: {thin_info}\n\n"
                    "Expand content:\n"
                    "1. Prioritize levels with < 50 items\n"
                    "2. Focus on high-frequency vocabulary for each level"
                ),
                "Competitive: content depth determines learning effectiveness",
                ["scripts/"],
            ))

    # Drill type imbalance
    drill_dist = _safe_query_all(conn, """
        SELECT drill_type, COUNT(*) as cnt
        FROM review_event
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY drill_type
        ORDER BY cnt DESC
    """)
    if drill_dist and len(drill_dist) >= 2:
        total_drills_30d = sum(r["cnt"] for r in drill_dist)
        top_drill = drill_dist[0]
        if total_drills_30d > 0:
            top_pct = round(top_drill["cnt"] / total_drills_30d * 100, 1)
            if top_pct > 60:
                findings.append(_finding(
                    "competitive", "medium",
                    f"Drill type imbalance: '{top_drill['drill_type']}' = {top_pct}% of all drills",
                    f"One drill type dominates usage, limiting skill breadth.",
                    "Rebalance drill type scheduling for more varied practice.",
                    (
                        f"'{top_drill['drill_type']}' accounts for {top_pct}% of drills.\n\n"
                        f"1. Read {_FILE_MAP['scheduler']} — drill type selection logic\n"
                        "2. Ensure interleaving enforcement is working"
                    ),
                    "Learning: varied practice improves outcomes",
                    _f("scheduler"),
                ))

    return findings


ANALYZERS = [
    _analyze_profitability,
    _analyze_retention,
    _analyze_marketing,
    _analyze_onboarding,
    _analyze_competitive,
]
