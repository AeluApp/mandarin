"""Product Intelligence — behavioral economics analyzer suite.

8 DOCTRINE-aware analyzers that evaluate aelu's behavioral economics
implementation across nudges, choice architecture, commitment devices,
progress framing, peak-end design, social proof, fresh starts, and
nudge registry health.

Replaces the single regex-only analyzer that recommended anti-DOCTRINE
patterns. All recommendations here are DOCTRINE-compliant.
"""

from __future__ import annotations

import os
import re
import sqlite3

from ._base import _f, _finding, _safe_scalar, _safe_query_all

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_MANDARIN_PKG = os.path.join(_PROJECT_ROOT, "mandarin")
_TEMPLATE_DIR = os.path.join(_MANDARIN_PKG, "web", "templates")
_STATIC_DIR = os.path.join(_MANDARIN_PKG, "web", "static")
_EMAIL_DIR = os.path.join(_PROJECT_ROOT, "marketing", "email-templates")


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IOError):
        return ""


def _scan_content() -> str:
    """Aggregate all user-facing content for scanning."""
    parts = []
    # Templates
    for name in os.listdir(_TEMPLATE_DIR) if os.path.isdir(_TEMPLATE_DIR) else []:
        parts.append(_read(os.path.join(_TEMPLATE_DIR, name)))
    # JS
    parts.append(_read(os.path.join(_STATIC_DIR, "app.js")))
    # Email templates
    if os.path.isdir(_EMAIL_DIR):
        for name in os.listdir(_EMAIL_DIR):
            parts.append(_read(os.path.join(_EMAIL_DIR, name)))
    return "\n".join(parts)


def _scan_routes() -> str:
    """Aggregate route files for server-side behavioral patterns."""
    routes = ["dashboard_routes.py", "session_routes.py", "onboarding_routes.py",
              "payment_routes.py", "landing_routes.py", "settings_routes.py"]
    parts = []
    for r in routes:
        parts.append(_read(os.path.join(_MANDARIN_PKG, "web", r)))
    parts.append(_read(os.path.join(_MANDARIN_PKG, "scheduler.py")))
    parts.append(_read(os.path.join(_MANDARIN_PKG, "runner.py")))
    parts.append(_read(os.path.join(_MANDARIN_PKG, "marketing_hooks.py")))
    return "\n".join(parts)


# ── 1. DOCTRINE Violation Detection ─────────────────────────────────


def _analyze_doctrine_violations(conn) -> list[dict]:
    """Scan for anti-DOCTRINE behavioral patterns (critical severity).

    Detects: guilt, streak anxiety, manufactured urgency, normative pressure.
    Any such language is a DOCTRINE violation — critical severity.
    """
    findings = []
    content = _scan_content()
    routes = _scan_routes()
    all_text = content + "\n" + routes

    if not all_text.strip():
        return findings

    checks = [
        (
            r"\b(?:you\s+haven'?t|we\s+miss|falling\s+behind|you'?re\s+letting|"
            r"don'?t\s+give\s+up|disappointed\s+(?:in|with))\b",
            "guilt language", "behavioral_econ", "critical",
            "DOCTRINE §6 violation: guilt language. Replace with factual, "
            "autonomy-respecting alternatives.",
        ),
        (
            r"\b(?:streak\s+(?:is\s+)?at\s+risk|lose\s+your\s+streak|"
            r"streak\s+(?:about\s+to|will)\s+(?:break|be\s+lost|reset)|"
            r"keep\s+(?:your\s+)?streak\s+alive)\b",
            "streak anxiety", "behavioral_econ", "critical",
            "DOCTRINE §6 violation: streak is a trailing indicator, not a "
            "goal. Remove all streak-loss pressure.",
        ),
        (
            r"\b(?:hurry|limited\s+time|only\s+\d+\s+left|expires?\s+soon|"
            r"last\s+chance|act\s+now|running\s+out)\b",
            "manufactured urgency", "behavioral_econ", "critical",
            "DOCTRINE §6 violation: never manufacture urgency. Replace with "
            "factual, time-neutral information.",
        ),
        (
            r"\b(?:others?\s+are\s+(?:already|ahead)|your\s+friends?\s+(?:are|have)|"
            r"everyone\s+(?:is|else)|don'?t\s+(?:miss|fall)\b)",
            "normative social pressure", "behavioral_econ", "high",
            "DOCTRINE §8 violation: informational social proof is fine; "
            "normative pressure (comparison to others) is not.",
        ),
    ]

    for pattern, label, dim, severity, recommendation in checks:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        if matches:
            findings.append(_finding(
                dim, severity,
                f"DOCTRINE violation: {label} ({len(matches)} instance{'s' if len(matches) != 1 else ''})",
                f"Found {label}: {matches[:3]}. This violates DOCTRINE "
                f"sections 6 and 8.",
                recommendation,
                f"Search all user-facing content for {label} patterns and remove or replace.",
                f"{label.title()} violates DOCTRINE and erodes learner trust.",
                _f("app_js") + ["marketing/email-templates/"],
            ))

    return findings


# ── 2. Social Proof Presence ────────────────────────────────────────


def _analyze_social_proof_presence(conn) -> list[dict]:
    """Check for factual (informational) social proof on landing page."""
    findings = []
    content = _scan_content()
    routes = _scan_routes()

    # Look for factual social proof patterns
    has_user_count = bool(re.search(
        r"\b(?:trusted\s+by|used\s+by)\s+\d+\s+\w*learner", content, re.IGNORECASE
    ))
    has_outcome_stat = bool(re.search(
        r"(?:average|typical)\s+learner\s+\w+\s+\d+", content, re.IGNORECASE
    ))
    has_rating = bool(re.search(r"rated\s+\d+\.?\d*", content, re.IGNORECASE))
    has_api = bool(re.search(r"social[_-]proof", routes, re.IGNORECASE))

    if not (has_user_count or has_outcome_stat or has_rating or has_api):
        findings.append(_finding(
            "behavioral_econ", "low",
            "No informational social proof on landing page",
            "No factual social proof found (user counts, outcome stats, "
            "ratings). Informational social proof (Cialdini 1984) reduces "
            "signup uncertainty. DOCTRINE §8 permits factual claims.",
            "Add factual social proof: user count (if >100), outcome stat, "
            "app rating. Must be auto-computed from real data.",
            "Add /api/social-proof endpoint and surface on landing page.",
            "Missing social proof increases visitor-to-signup friction.",
            _f("landing_routes") + ["mandarin/web/templates/index.html"],
        ))

    return findings


# ── 3. Choice Architecture ─────────────────────────────────────────


def _analyze_choice_architecture(conn) -> list[dict]:
    """Check for smart defaults and meaningful learner choices."""
    findings = []
    routes = _scan_routes()

    # Check for session focus choice
    has_session_choice = bool(re.search(
        r"(?:session[_\s]?(?:focus|preference|type)|plan_session_with_preference)",
        routes, re.IGNORECASE,
    ))
    if not has_session_choice:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No session choice architecture",
            "Learners cannot choose session focus (review vs new material). "
            "Choice architecture (Thaler & Sunstein) increases autonomy. "
            "DOCTRINE §7: 'Adapt what matters.'",
            "Offer session focus selector: Review, New Words, Mixed (default).",
            "Add plan_session_with_preference() and pre-session selector UI.",
            "Lack of choice reduces learner autonomy.",
            _f("scheduler", "session_routes"),
        ))

    return findings


# ── 4. Commitment Devices ──────────────────────────────────────────


def _analyze_commitment_devices(conn) -> list[dict]:
    """Check for implementation intentions and goal-setting mechanisms."""
    findings = []
    routes = _scan_routes()

    # Check for implementation intentions (study time preference)
    has_study_time = bool(re.search(
        r"preferred_study_time|study.time|implementation.intention",
        routes, re.IGNORECASE,
    ))
    if not has_study_time:
        findings.append(_finding(
            "behavioral_econ", "medium",
            "No implementation intentions mechanism",
            "No study-time preference found. Gollwitzer: 'when X, I will Y' "
            "is 2-3x more effective than goals alone.",
            "Ask 'When do you usually have 5 free minutes?' after onboarding.",
            "Add preferred_study_time to profile and notification timing.",
            "Habit formation relies on willpower alone without this.",
            _f("onboarding_routes", "settings_routes"),
        ))

    # Check for goal-setting
    has_goals = bool(re.search(
        r"(?:daily[_\s]goal|target[_\s]sessions|set[_\s]goal|goal[_\s]setting)",
        routes, re.IGNORECASE,
    ))
    if not has_goals:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No goal-setting mechanism",
            "No daily goal or target sessions found. Commitment devices "
            "(DOCTRINE-compatible) leverage consistency bias.",
            "Add goal-setting in onboarding and settings.",
            "Add daily goal selector and target_sessions_per_week.",
            "Without goals, learners lack self-imposed accountability.",
            _f("onboarding_routes", "settings_routes"),
        ))

    return findings


# ── 5. Progress Framing ────────────────────────────────────────────


def _analyze_progress_framing(conn) -> list[dict]:
    """Check for capability framing, endowed progress, goal gradient."""
    findings = []
    content = _scan_content()
    routes = _scan_routes()
    all_text = content + "\n" + routes

    # Capability framing (DOCTRINE §6)
    has_capability = bool(re.search(
        r"you\s+can\s+now|you(?:'ve|'ve)\s+learned\s+to",
        all_text, re.IGNORECASE,
    ))
    if not has_capability:
        findings.append(_finding(
            "behavioral_econ", "medium",
            "No capability-framed progress",
            "No 'You can now...' framing found. DOCTRINE §6 mandates "
            "progress visibility framed as capability.",
            "Add capability messages to milestones and session summaries.",
            "Add _CAPABILITY_MESSAGES to milestone computation.",
            "Learners lack functional context for their progress.",
            _f("dashboard_routes", "session_routes"),
        ))

    # Endowed progress (Nunes & Dreze 2006)
    has_endowed = bool(re.search(
        r"endowed_progress|already\s+know\s+approximately|journey.*complete",
        all_text, re.IGNORECASE,
    ))
    if not has_endowed:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No endowed progress at signup",
            "After placement, existing knowledge is not framed as progress. "
            "Nunes & Dreze 2006: endowed progress increases completion.",
            "Show placement results as progress toward conversational fluency.",
            "Compute endowed_progress in placement_submit().",
            "Learners start from zero — lower motivation.",
            _f("onboarding_routes"),
        ))

    # Goal gradient (Kivetz 2006)
    has_gradient = bool(re.search(
        r"upcoming_milestone|goal_gradient|remaining.*word",
        all_text, re.IGNORECASE,
    ))
    if not has_gradient:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No goal gradient near milestones",
            "Learners near milestones don't see their proximity. "
            "Kivetz 2006: effort accelerates as goals approach.",
            "Show 'You're X words from [milestone]' when within 10%.",
            "Add _compute_upcoming_milestones() to dashboard.",
            "Missing acceleration potential near milestones.",
            _f("dashboard_routes"),
        ))

    return findings


# ── 6. Peak-End Session Design ─────────────────────────────────────


def _analyze_peak_end_design(conn) -> list[dict]:
    """Check for peak-end rule in session ordering and summary."""
    findings = []
    scheduler = _read(os.path.join(_MANDARIN_PKG, "scheduler.py"))
    runner = _read(os.path.join(_MANDARIN_PKG, "runner.py"))

    has_peak_end = bool(re.search(
        r"peak[_\s]end|_apply_peak_end|high[_\s]confidence.*end",
        scheduler + runner, re.IGNORECASE,
    ))
    if not has_peak_end:
        findings.append(_finding(
            "behavioral_econ", "medium",
            "No peak-end session design",
            "Sessions don't apply Kahneman's peak-end rule. Memory of an "
            "experience is dominated by peak and ending.",
            "Reorder last 2 drills to high-confidence items.",
            "Add _apply_peak_end_ordering() to scheduler pipeline.",
            "Random session endings miss positive memory formation.",
            ["mandarin/scheduler.py", "mandarin/runner.py"],
        ))

    has_peak_display = bool(re.search(
        r"peak.moment|best.moment|_show_peak",
        runner, re.IGNORECASE,
    ))
    if not has_peak_display:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No peak moment in session summary",
            "Session summary doesn't highlight the best moment.",
            "Show 'Best moment: recalled [word] correctly' in summary.",
            "Add _show_peak_moment() to _finalize().",
            "Missed opportunity to reinforce positive experience.",
            ["mandarin/runner.py"],
        ))

    return findings


# ── 7. Fresh-Start Triggers ────────────────────────────────────────


def _analyze_fresh_start_triggers(conn) -> list[dict]:
    """Check for temporal landmark campaigns (Dai, Milkman & Riis 2014)."""
    findings = []
    hooks = _read(os.path.join(_MANDARIN_PKG, "marketing_hooks.py"))

    has_fresh_start = bool(re.search(
        r"fresh[_\s]start|temporal[_\s]landmark|new[_\s]month|new[_\s]year",
        hooks, re.IGNORECASE,
    ))
    if not has_fresh_start:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No fresh-start campaign triggers",
            "No temporal landmark campaigns (new month, New Year, HSK "
            "completion). Dai et al. 2014: fresh starts motivate goal pursuit.",
            "Add fresh-start triggers to marketing_hooks.py for new month, "
            "HSK completion, and cultural events.",
            "Add check_fresh_start_triggers() to marketing hooks.",
            "Missing re-engagement opportunity at natural transition points.",
            ["mandarin/marketing_hooks.py"],
        ))

    return findings


# ── 8. Nudge Registry Health ───────────────────────────────────────


def _analyze_nudge_health(conn) -> list[dict]:
    """Check nudge registry for coverage, ethics scores, conversion rates."""
    findings = []

    # Check if nudge_registry table exists and has data
    try:
        total = conn.execute("SELECT COUNT(*) FROM nudge_registry").fetchone()[0]
    except (sqlite3.OperationalError, TypeError):
        findings.append(_finding(
            "behavioral_econ", "medium",
            "No nudge registry table",
            "The nudge_registry table does not exist. Without centralized "
            "tracking, nudge effectiveness and DOCTRINE compliance cannot "
            "be measured.",
            "Run migration to create nudge_registry tables and register "
            "existing nudges.",
            "Create nudge_registry, nudge_exposure, nudge_outcome tables.",
            "Nudge effectiveness is unmeasurable without a registry.",
            ["mandarin/nudge_registry.py"],
        ))
        return findings

    if total == 0:
        findings.append(_finding(
            "behavioral_econ", "medium",
            "Nudge registry is empty",
            f"The nudge_registry table exists but has 0 registered nudges. "
            f"Existing nudges (upgrade prompts, emails, milestones) should "
            f"be registered for tracking.",
            "Register all existing nudges via nudge_registry.register_nudge().",
            "Audit user-facing nudges and register each one.",
            "Unregistered nudges can't be measured or ethics-evaluated.",
            ["mandarin/nudge_registry.py"],
        ))
        return findings

    # Check for nudges with low doctrine scores
    try:
        low_score = conn.execute(
            "SELECT COUNT(*) FROM nudge_registry WHERE doctrine_score < 0.7 AND status = 'active'"
        ).fetchone()[0]
        if low_score > 0:
            findings.append(_finding(
                "behavioral_econ", "high",
                f"{low_score} active nudge(s) below DOCTRINE threshold",
                f"{low_score} active nudges have doctrine_score < 0.7. "
                f"These may contain guilt, urgency, or pressure patterns.",
                "Review and revise nudges with low DOCTRINE scores. "
                "Pause any nudge scoring below 0.5.",
                "Query nudge_registry for low-scoring nudges and revise copy.",
                "Low-scoring nudges risk DOCTRINE violations.",
                ["mandarin/nudge_registry.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # Check for nudges with zero conversions (ineffective)
    try:
        total_active = conn.execute(
            "SELECT COUNT(*) FROM nudge_registry WHERE status = 'active'"
        ).fetchone()[0]
        with_exposure = conn.execute(
            """SELECT COUNT(DISTINCT nr.id) FROM nudge_registry nr
               JOIN nudge_exposure ne ON nr.id = ne.nudge_id
               WHERE nr.status = 'active'"""
        ).fetchone()[0]
        if total_active > 3 and with_exposure < total_active * 0.5:
            findings.append(_finding(
                "behavioral_econ", "low",
                f"{total_active - with_exposure} active nudge(s) with zero exposure",
                f"Several active nudges have never been shown to a user. "
                f"This may indicate broken delivery or stale registration.",
                "Audit nudge delivery paths and remove stale registrations.",
                "Check nudge delivery integration for unexposed nudges.",
                "Nudges without exposure waste registry space.",
                ["mandarin/nudge_registry.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings


ANALYZERS = [
    _analyze_doctrine_violations,
    _analyze_social_proof_presence,
    _analyze_choice_architecture,
    _analyze_commitment_devices,
    _analyze_progress_framing,
    _analyze_peak_end_design,
    _analyze_fresh_start_triggers,
    _analyze_nudge_health,
]
