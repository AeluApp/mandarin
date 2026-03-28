"""Product Intelligence — Vibe audit, marketing intelligence, feature usage, engineering health (Doc 9).

Four analyzer families:
A) Vibe audit — tonal voice standard + visual audit schedule enforcement
B) Marketing intelligence — page quality, conversion funnel, strategy checklist
C) Feature usage tracking — dead/underused feature detection, abandonment rates
D) Engineering health — test coverage, dependency health, schema complexity

For qualitative items (voice, aesthetics), the engine enforces audit schedules
and surfaces findings when overdue. For quantitative items (funnel, usage rates,
coverage), it measures directly.
"""

import logging
import os
import re
import sqlite3

from ._base import _finding, _safe_query_all, _safe_scalar, _safe_query, _f

logger = logging.getLogger(__name__)


# ── Voice Standard ─────────────────────────────────────────────────────────

VOICE_STANDARD = {
    "name": "Civic Sanctuary",
    "principles": [
        "Warmth without condescension",
        "Clarity without oversimplification",
        "Encouragement without inflation",
        "Directness without harshness",
    ],
    "forbidden_patterns": [
        (r"\b(?:Amazing|Awesome|Incredible|Fantastic|Superb)\b[!]", "praise_inflation"),
        (r"\b(?:at risk|falling behind|losing)\b", "anxiety_language"),
        (r"\b(?:you must|you need to|you should)\b", "imperative_pressure"),
        (r"\b(?:Don'?t miss|Act now|Limited time|Hurry)\b", "urgency_marketing"),
        (r"\b(?:easy|simple|just)\b", "false_simplicity"),
    ],
    "max_exclamation_density": 0.05,  # Max 5% of sentences end with !
}

VISUAL_VIBE_CHECKLIST = {
    "color_palette": {
        "description": "Warm stone + teal + terracotta palette consistent across all surfaces",
        "audit_frequency_days": 30,
    },
    "typography": {
        "description": "Cormorant Garamond headings, Source Sans 3 body, Noto Serif SC hanzi",
        "audit_frequency_days": 30,
    },
    "motion": {
        "description": "Upward-drift motion, no jarring transitions",
        "audit_frequency_days": 60,
    },
    "dark_mode": {
        "description": "Warm dark theme via prefers-color-scheme, no cold grays",
        "audit_frequency_days": 30,
    },
    "sound_design": {
        "description": "Web Audio API session start/complete sounds, no streak anxiety",
        "audit_frequency_days": 60,
    },
}

MARKETING_STRATEGY_CHECKLIST = {
    "positioning": {
        "description": "Clear differentiation from Duolingo/HelloChinese/Anki",
        "review_frequency_days": 90,
    },
    "audience_segments": {
        "description": "Primary and secondary audience segments defined and targeted",
        "review_frequency_days": 60,
    },
    "content_marketing": {
        "description": "Blog posts, social media, or educational content plan",
        "review_frequency_days": 30,
    },
    "seo": {
        "description": "Core keyword targets and ranking progress tracked",
        "review_frequency_days": 30,
    },
    "referral": {
        "description": "Referral program active and conversion tracked",
        "review_frequency_days": 60,
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _days_since_sql(conn, date_val):
    """Compute days since a date string using SQLite julianday. Returns None if date_val is None."""
    if not date_val:
        return None
    row = _safe_query(conn, "SELECT julianday('now') - julianday(?)", (date_val,))
    if row is None:
        return None
    val = row[0]
    return val if val is not None else None


def _score_copy_against_patterns(copy_text):
    """Score a copy string against voice standard patterns. Returns {voice_score, violations}.

    Pure pattern-based — no LLM needed. Scores 0-100 where 100 = perfect.
    """
    violations = []
    score = 100.0

    for pattern, violation_type in VOICE_STANDARD["forbidden_patterns"]:
        matches = re.findall(pattern, copy_text, re.IGNORECASE)
        if matches:
            violations.append({
                "type": violation_type,
                "matches": matches[:3],
                "penalty": 15,
            })
            score -= 15

    # Check exclamation density
    sentences = re.split(r'[.!?]+', copy_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if sentences:
        excl_count = copy_text.count("!")
        excl_density = excl_count / len(sentences)
        if excl_density > VOICE_STANDARD["max_exclamation_density"]:
            violations.append({
                "type": "exclamation_overuse",
                "density": round(excl_density, 3),
                "penalty": 10,
            })
            score -= 10

    return {"voice_score": max(0, score), "violations": violations}


def _audit_copy_against_voice_standard(conn, copy_item):
    """Audit a copy item against voice standard. Uses Qwen if available, falls back to patterns.

    Returns {voice_score, violations}.
    """
    copy_text = copy_item["copy_text"] if isinstance(copy_item, dict) else copy_item[2]

    # Try LLM-based audit first
    try:
        from ..ai.ollama_client import generate, is_ollama_available
        if is_ollama_available():
            prompt = (
                f"Score this UI copy on a 0-100 scale for the 'Civic Sanctuary' voice standard. "
                f"Rules: warm not condescending, clear not oversimplified, encouraging not inflated, "
                f"direct not harsh. No praise inflation (Amazing!, Incredible!), no anxiety language "
                f"(at risk, falling behind), no urgency marketing (Don't miss, Act now).\n\n"
                f"Copy: \"{copy_text}\"\n\n"
                f"Respond with ONLY a JSON object: {{\"score\": <0-100>, \"violations\": [\"...\"]}})"
            )
            resp = generate(prompt, system="You are a copy quality auditor.", temperature=0.1,
                            max_tokens=256, conn=conn, task_type="voice_audit")
            if resp.success:
                import json
                try:
                    data = json.loads(resp.text.strip())
                    return {
                        "voice_score": data.get("score", 50),
                        "violations": [{"type": v, "penalty": 0} for v in data.get("violations", [])],
                    }
                except (json.JSONDecodeError, KeyError):
                    pass
    except ImportError:
        pass

    # Conservative fallback: pattern-based scoring
    return _score_copy_against_patterns(copy_text)


# ── Part A: Vibe Audit ─────────────────────────────────────────────────────

def analyze_tonal_vibe(conn):
    """Check copy registry for voice standard compliance."""
    findings = []

    # Check if copy registry has entries
    total_strings = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_copy_registry", default=0)
    if total_strings == 0:
        findings.append(_finding(
            "tonal_vibe", "medium",
            "No copy strings registered for voice audit",
            f"The pi_copy_registry table is empty. No UI copy is being tracked against the "
            f"'{VOICE_STANDARD['name']}' voice standard.",
            "Register key UI strings in pi_copy_registry so voice audits can run.",
            "Add entries to pi_copy_registry with string_key, copy_text, and surface for all "
            "user-facing copy. Start with onboarding, dashboard, and drill feedback strings.",
            "Ensures voice consistency across the product",
            _f("routes", "dashboard_template"),
        ))
        return findings

    # Check for unaudited strings
    unaudited = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_copy_registry WHERE last_audited_at IS NULL
    """, default=0)
    if unaudited > 0:
        findings.append(_finding(
            "tonal_vibe", "low",
            f"{unaudited} copy strings never audited",
            f"{unaudited} of {total_strings} registered copy strings have never been audited "
            f"against the voice standard.",
            "Run voice audit on unaudited strings.",
            "Query pi_copy_registry WHERE last_audited_at IS NULL and run voice audit on each.",
            "Voice consistency",
            [],
        ))

    # Check for low-scoring strings
    low_score_items = _safe_query_all(conn, """
        SELECT string_key, copy_text, voice_score FROM pi_copy_registry
        WHERE voice_score IS NOT NULL AND voice_score < 50
        ORDER BY voice_score ASC LIMIT 5
    """)
    for item in low_score_items:
        findings.append(_finding(
            "tonal_vibe", "high",
            f"Copy '{item['string_key']}' fails voice standard (score: {item['voice_score']})",
            f"The copy string '{item['copy_text'][:60]}...' scored {item['voice_score']}/100 "
            f"against the {VOICE_STANDARD['name']} voice standard.",
            f"Rewrite this copy to align with voice principles: warm, clear, encouraging, direct.",
            f"Rewrite the copy for string_key='{item['string_key']}' to score above 70 on the "
            f"voice standard. Current text: \"{item['copy_text']}\"",
            "Voice consistency and brand trust",
            _f("routes"),
        ))

    # Check for overdue quarterly full audit
    last_full_audit = _safe_query(conn, """
        SELECT MAX(audit_date) as last_date FROM pi_vibe_audits
        WHERE audit_type = 'full' AND audit_category = 'tonal'
    """)
    last_date = last_full_audit["last_date"] if last_full_audit else None
    days = _days_since_sql(conn, last_date) if last_date else None
    if days is None or days > 90:
        findings.append(_finding(
            "tonal_vibe", "medium",
            "Quarterly tonal voice audit overdue",
            f"Last full tonal audit was {'never' if days is None else f'{int(days)} days ago'}. "
            f"Quarterly cadence (90 days) keeps voice drift in check.",
            "Conduct a full voice audit of all registered copy strings.",
            "Run a full voice audit: query all pi_copy_registry entries, score each against "
            "the Civic Sanctuary voice standard, update voice_score and last_audited_at.",
            "Prevents voice drift over time",
            [],
        ))

    return findings


def analyze_visual_vibe(conn):
    """Check visual audit schedule compliance per VISUAL_VIBE_CHECKLIST."""
    findings = []

    for category, spec in VISUAL_VIBE_CHECKLIST.items():
        last_audit = _safe_query(conn, """
            SELECT MAX(audit_date) as last_date FROM pi_vibe_audits
            WHERE audit_category = ? AND audit_type = 'visual'
        """, (category,))
        last_date = last_audit["last_date"] if last_audit else None
        days = _days_since_sql(conn, last_date) if last_date else None
        freq = spec["audit_frequency_days"]

        if days is None or days > freq:
            findings.append(_finding(
                "visual_vibe", "low",
                f"Visual audit overdue: {category}",
                f"{spec['description']}. Last audit: "
                f"{'never' if days is None else f'{int(days)} days ago'} "
                f"(target: every {freq} days).",
                f"Conduct a visual audit of {category}.",
                f"Take screenshots of the app and review {category}: {spec['description']}. "
                f"Log result via POST /api/admin/intelligence/vibe/audit with "
                f"audit_type='visual', audit_category='{category}'.",
                "Visual consistency",
                _f("style_css", "app_js"),
            ))

    return findings


# ── Part B: Marketing Intelligence ─────────────────────────────────────────

def analyze_marketing_page_quality(conn):
    """Check marketing page registry for quality gaps."""
    findings = []

    total_pages = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_marketing_pages", default=0)
    if total_pages == 0:
        findings.append(_finding(
            "marketing", "medium",
            "No marketing pages registered",
            "The pi_marketing_pages table is empty. Marketing page quality cannot be tracked.",
            "Register marketing pages (landing, pricing, about, etc.) in pi_marketing_pages.",
            "Insert rows into pi_marketing_pages for each marketing page with page_slug, "
            "page_title, page_url, primary_audience, and primary_cta.",
            "Enables marketing quality tracking",
            _f("marketing_routes", "landing_routes"),
        ))
        return findings

    # Stale copy review (>60 days)
    stale = _safe_query_all(conn, """
        SELECT page_slug, page_title, last_copy_review_at FROM pi_marketing_pages
        WHERE last_copy_review_at IS NULL
           OR julianday('now') - julianday(last_copy_review_at) > 60
    """)
    if stale:
        slugs = [r["page_slug"] for r in stale]
        findings.append(_finding(
            "marketing", "medium",
            f"{len(stale)} marketing pages need copy review",
            f"Pages with stale or missing copy reviews: {', '.join(slugs[:5])}.",
            "Review copy on these pages for voice standard compliance and conversion optimization.",
            f"Review marketing copy on pages: {', '.join(slugs[:5])}.",
            "Marketing effectiveness",
            _f("marketing_routes", "landing_routes"),
        ))

    # Missing audience
    no_audience = _safe_query_all(conn, """
        SELECT page_slug FROM pi_marketing_pages
        WHERE primary_audience IS NULL OR primary_audience = ''
    """)
    if no_audience:
        slugs = [r["page_slug"] for r in no_audience]
        findings.append(_finding(
            "marketing", "low",
            f"{len(no_audience)} marketing pages missing primary audience",
            f"Pages without a defined primary audience: {', '.join(slugs[:5])}.",
            "Define the primary audience for each marketing page.",
            f"Set primary_audience on pi_marketing_pages for: {', '.join(slugs[:5])}.",
            "Audience targeting",
            [],
        ))

    # Missing conversion data
    no_conversion = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_marketing_pages
        WHERE conversion_rate IS NULL AND monthly_visitors IS NULL
    """, default=0)
    if no_conversion > 0:
        findings.append(_finding(
            "marketing", "low",
            f"{no_conversion} marketing pages missing analytics data",
            f"{no_conversion} pages have no conversion rate or visitor data.",
            "Connect analytics to track conversion rates and visitor counts.",
            "Update pi_marketing_pages with conversion_rate and monthly_visitors from analytics.",
            "Data-driven marketing decisions",
            [],
        ))

    return findings


def analyze_conversion_funnel(conn):
    """Analyze signup→activation conversion funnel."""
    findings = []

    # Get latest snapshot
    snapshot = _safe_query(conn, """
        SELECT * FROM pi_funnel_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)

    if not snapshot:
        # Check if we have enough funnel events to analyze directly
        signups = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_funnel_events WHERE event_type = 'signup'
        """, default=0)

        if signups < 5:
            return findings  # Not enough data

        findings.append(_finding(
            "marketing", "medium",
            "No funnel snapshots recorded",
            "Funnel events exist but no snapshots have been computed. "
            "Snapshots aggregate weekly metrics for trend analysis.",
            "Create funnel snapshots weekly from pi_funnel_events data.",
            "Compute and insert a pi_funnel_snapshots row with 7-day signup, activation, "
            "and retention metrics.",
            "Funnel visibility",
            [],
        ))
        return findings

    # Check activation rate
    activation_rate = snapshot["conversion_signup_to_activation"]
    if activation_rate is not None and activation_rate < 0.40:
        findings.append(_finding(
            "marketing", "high",
            f"Low signup→activation rate: {activation_rate:.0%}",
            f"Only {activation_rate:.0%} of signups complete their first drill session. "
            f"Target: >60%. This indicates onboarding friction.",
            "Investigate onboarding flow for friction points. Check time-to-first-drill.",
            "Analyze onboarding flow: where do signups drop off before first drill? "
            "Check pi_funnel_events for signup→activation gap patterns.",
            "User activation and retention",
            _f("onboarding_routes", "routes"),
        ))

    # Check D7 retention
    d7 = snapshot["d7_retention_rate"]
    if d7 is not None and d7 < 0.30:
        findings.append(_finding(
            "marketing", "high",
            f"Low D7 retention: {d7:.0%}",
            f"Only {d7:.0%} of activated users return after 7 days. Target: >40%.",
            "Investigate week-1 experience. Are users getting value quickly enough?",
            "Analyze D7 retention drop-off: what do retained vs. churned users do differently?",
            "Long-term retention",
            _f("scheduler", "routes"),
        ))

    # Check funnel data staleness
    days = _days_since_sql(conn, snapshot["snapshot_date"])
    if days is not None and days > 14:
        findings.append(_finding(
            "marketing", "medium",
            f"Funnel data is {int(days)} days stale",
            f"Latest funnel snapshot is {int(days)} days old. Weekly updates recommended.",
            "Compute a fresh funnel snapshot.",
            "Run funnel snapshot computation and insert into pi_funnel_snapshots.",
            "Fresh funnel data",
            [],
        ))

    return findings


def analyze_marketing_strategy(conn):
    """Enforce periodic strategy checklist reviews."""
    findings = []

    for check_name, spec in MARKETING_STRATEGY_CHECKLIST.items():
        last_review = _safe_query(conn, """
            SELECT MAX(audit_date) as last_date FROM pi_vibe_audits
            WHERE audit_type = 'strategy' AND audit_category = ?
        """, (check_name,))
        last_date = last_review["last_date"] if last_review else None
        days = _days_since_sql(conn, last_date) if last_date else None
        freq = spec["review_frequency_days"]

        if days is None or days > freq:
            findings.append(_finding(
                "marketing", "low",
                f"Strategy review overdue: {check_name}",
                f"{spec['description']}. Last review: "
                f"{'never' if days is None else f'{int(days)} days ago'} "
                f"(target: every {freq} days).",
                f"Conduct a {check_name} strategy review.",
                f"Review {check_name} strategy: {spec['description']}. "
                f"Log result via POST /api/admin/intelligence/vibe/audit with "
                f"audit_type='strategy', audit_category='{check_name}'.",
                "Strategic marketing alignment",
                _f("marketing_routes"),
            ))

    return findings


# ── Part C: Feature Usage ──────────────────────────────────────────────────

def analyze_feature_usage(conn):
    """Compute feature usage rates, flag dead/underused features, high abandonment."""
    findings = []

    features = _safe_query_all(conn, """
        SELECT * FROM pi_feature_registry WHERE status = 'active'
    """)
    if not features:
        return findings

    total_active_users = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
    """, default=0)

    if total_active_users == 0:
        return findings

    for feat in features:
        feature_name = feat["feature_name"]
        launched_at = feat["launched_at"]

        # Skip features launched less than 14 days ago
        if launched_at:
            days_since_launch = _days_since_sql(conn, launched_at)
            if days_since_launch is not None and days_since_launch < 14:
                continue

        # Compute 30d usage rate
        users_using = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM pi_feature_events
            WHERE feature_name = ? AND occurred_at >= datetime('now', '-30 days')
        """, (feature_name,), default=0)

        usage_rate = users_using / total_active_users if total_active_users > 0 else 0
        min_rate = feat["minimum_usage_rate_30d"] or 0

        # Update current rate
        try:
            conn.execute("""
                UPDATE pi_feature_registry SET current_usage_rate_30d = ?
                WHERE feature_name = ?
            """, (round(usage_rate, 4), feature_name))
            conn.commit()
        except sqlite3.Error:
            pass

        # Flag zero-usage features
        if users_using == 0:
            findings.append(_finding(
                "feature_usage", "medium",
                f"Dead feature: {feature_name} (0 users in 30d)",
                f"Feature '{feature_name}' has zero usage in the last 30 days. "
                f"{feat['feature_description']}.",
                "Investigate: is the feature discoverable? Consider removing or promoting it.",
                f"Analyze why '{feature_name}' has zero usage. Check: is it discoverable in the UI? "
                f"Is the entry point visible? Consider removing if truly unused.",
                "Feature portfolio health",
                [],
            ))
        elif usage_rate < min_rate:
            findings.append(_finding(
                "feature_usage", "low",
                f"Underused feature: {feature_name} ({usage_rate:.1%} vs target {min_rate:.1%})",
                f"Feature '{feature_name}' usage rate ({usage_rate:.1%}) is below the "
                f"minimum target ({min_rate:.1%}). {users_using}/{total_active_users} active users.",
                "Improve discoverability or reconsider the feature.",
                f"Investigate why '{feature_name}' is underused. Check UI placement and onboarding.",
                "Feature adoption",
                [],
            ))

        # Check abandonment rate (started but not completed)
        starts = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_feature_events
            WHERE feature_name = ? AND event_type = 'start'
              AND occurred_at >= datetime('now', '-30 days')
        """, (feature_name,), default=0)
        completions = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_feature_events
            WHERE feature_name = ? AND event_type = 'complete'
              AND occurred_at >= datetime('now', '-30 days')
        """, (feature_name,), default=0)

        if starts > 5:
            abandonment_rate = 1 - (completions / starts) if starts > 0 else 0
            if abandonment_rate > 0.40:
                findings.append(_finding(
                    "feature_usage", "medium",
                    f"High abandonment: {feature_name} ({abandonment_rate:.0%})",
                    f"{abandonment_rate:.0%} of users who start '{feature_name}' don't complete it. "
                    f"({completions}/{starts} completions in 30d).",
                    "Investigate where users drop off and simplify the flow.",
                    f"Analyze abandonment in '{feature_name}': where do users drop off between "
                    f"start and complete events?",
                    "User experience",
                    [],
                ))

    return findings


# ── Part D: Engineering Health ─────────────────────────────────────────────

def analyze_test_coverage(conn):
    """Check last engineering snapshot for test coverage / failure data.

    Uses cached snapshot data rather than running pytest/coverage live,
    which can take minutes and block the audit UI.
    """
    findings = []

    last_snap = _safe_query(conn, """
        SELECT test_coverage_pct, tests_passing, tests_failing
        FROM pi_engineering_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    if not last_snap:
        return findings

    coverage_pct = last_snap[0]
    tests_passing = last_snap[1]
    tests_failing = last_snap[2]

    if coverage_pct is not None and coverage_pct < 60:
        findings.append(_finding(
            "engineering_health", "high",
            f"Test coverage below 60%: {coverage_pct:.1f}%",
            f"Test coverage is {coverage_pct:.1f}%. Minimum target: 60%. "
            f"Low coverage increases regression risk.",
            "Add tests for uncovered modules, prioritizing critical paths.",
            "Run `coverage report --show-missing` to identify uncovered modules. "
            "Add tests for the least-covered critical-path modules first.",
            "Regression prevention",
            ["tests/"],
        ))

    if tests_failing is not None and tests_failing > 0:
        findings.append(_finding(
            "engineering_health", "high",
            f"{tests_failing} tests failing",
            f"{tests_failing} test(s) are currently failing out of "
            f"{(tests_passing or 0) + tests_failing} total.",
            "Fix failing tests immediately — they may indicate regressions.",
            f"Run `pytest -x` to find and fix the {tests_failing} failing test(s).",
            "Code correctness",
            ["tests/"],
        ))

    return findings


def analyze_dependency_health(conn):
    """Check last engineering snapshot for outdated dependency data.

    Uses cached snapshot data rather than running pip live.
    """
    findings = []

    last_snap = _safe_query(conn, """
        SELECT outdated_dependencies FROM pi_engineering_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    if last_snap and last_snap[0] is not None and last_snap[0] > 10:
        findings.append(_finding(
            "engineering_health", "medium",
            f"{last_snap[0]} packages outdated",
            f"{last_snap[0]} pip packages are outdated (from last snapshot).",
            "Update critical dependencies to get security patches and bug fixes.",
            "Run `pip list --outdated` to see details, then update critical packages.",
            "Security and stability",
            ["requirements.txt"],
        ))

    return findings


def analyze_schema_health(conn):
    """Check schema complexity — table count, DB file size."""
    findings = []

    table_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM sqlite_master WHERE type='table'
    """, default=0)

    if table_count > 80:
        findings.append(_finding(
            "engineering_health", "low",
            f"Schema has {table_count} tables",
            f"The database has {table_count} tables. High table count increases "
            f"migration complexity and cognitive overhead.",
            "Consider consolidating related tables or archiving unused ones.",
            "Review sqlite_master for tables that can be consolidated or removed.",
            "Schema maintainability",
            _f("schema"),
        ))

    # DB file size
    try:
        db_path = str(conn.execute("PRAGMA database_list").fetchone()[2])
        if os.path.exists(db_path):
            db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
            if db_size_mb > 500:
                findings.append(_finding(
                    "engineering_health", "medium",
                    f"Database file is {db_size_mb:.0f} MB",
                    f"The database file is {db_size_mb:.0f} MB. Consider archiving old data.",
                    "Archive old session logs, review events, and audit data.",
                    "Identify tables consuming the most space with "
                    "`SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC`.",
                    "Storage efficiency",
                    _f("schema"),
                ))
    except (sqlite3.Error, OSError):
        pass

    return findings


# ── Analyzer Registry ──────────────────────────────────────────────────────

ANALYZERS = [
    analyze_tonal_vibe,
    analyze_visual_vibe,
    analyze_marketing_page_quality,
    analyze_conversion_funnel,
    analyze_marketing_strategy,
    analyze_feature_usage,
    analyze_test_coverage,
    analyze_dependency_health,
    analyze_schema_health,
]
