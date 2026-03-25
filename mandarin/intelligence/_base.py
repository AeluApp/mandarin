"""Product Intelligence Engine — shared constants, helpers, scoring.

All constants and utility functions used across the intelligence package.
"""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

# Severity ordering for sort
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Severity penalty for dimension scoring — nonlinear (see _dimension_score)
_SEVERITY_PENALTY = {"critical": 25, "high": 15, "medium": 8, "low": 3}

# Grade thresholds
_GRADE_THRESHOLDS = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]

# Dimensions weighted 1.5x for overall score (growth drivers)
_WEIGHTED_DIMENSIONS = {"retention", "ux", "onboarding"}

# Minimum data thresholds for confident analysis
_MIN_DATA_THRESHOLDS = {
    "users": 5,
    "sessions": 10,
    "reviews": 50,
    "client_events": 20,
    "requests": 30,
}

# Confidence levels based on data volume
_CONFIDENCE_LEVELS = {
    "high": "sufficient data for reliable analysis",
    "medium": "limited data — findings are directional, not definitive",
    "low": "insufficient data — cannot draw conclusions",
    "none": "no data available",
}

# Verification windows: dimension → days before measuring outcome
_VERIFICATION_WINDOWS = {
    "ux": 3,
    "retention": 30,
    "engagement": 14,
    "onboarding": 7,
    "profitability": 30,
    "engineering": 7,
    "security": 7,
    "frustration": 7,
    "drill_quality": 14,
    "flow": 7,
    "content": 14,
    "srs_funnel": 14,
    "tone_phonology": 14,
    "scheduler_audit": 7,
    "encounter_loop": 14,
    "output_production": 14,
    "tutor_integration": 14,
    "tone_quality": 14,
    "pm": 14,
    "timing": 7,
    "platform": 7,
    "ui": 7,
    "competitive": 30,
    "marketing": 30,
    "copy": 14,
    "tonal_vibe": 14,
    "visual_vibe": 30,
    "feature_usage": 14,
    "engineering_health": 7,
    "strategic": 30,
    "governance": 7,
    "data_quality": 7,
    "genai_governance": 7,
    "memory_model": 14,
    "learner_model": 14,
    "genai": 7,
    "rag": 14,
    "native_speaker_validation": 14,
    "curriculum": 14,
    "input_layer": 14,
    "accountability": 7,
    "commercial": 30,
    "agentic": 7,
    "cross_platform": 14,
    "behavioral_econ": 14,
    "growth_accounting": 30,
    "journey": 14,
    "brand_health": 30,
    "learning_science": 14,
    "copy_drift": 7,
    "runtime_health": 3,
}

# Correlated dimension pairs for RCA graph edges
_CORRELATED_DIMENSIONS = {
    ("retention", "ux"),
    ("retention", "frustration"),
    ("retention", "onboarding"),
    ("ux", "flow"),
    ("ux", "frustration"),
    ("drill_quality", "srs_funnel"),
    ("drill_quality", "error_taxonomy"),
    ("content", "curriculum"),
    ("content", "hsk_cliff"),
    ("engineering", "timing"),
    ("engineering", "platform"),
    ("tone_phonology", "drill_quality"),
    ("scheduler_audit", "srs_funnel"),
    ("encounter_loop", "content"),
    ("tone_phonology", "output_production"),
    ("tutor_integration", "content"),
    ("output_production", "drill_quality"),
    ("tonal_vibe", "copy"),
    ("visual_vibe", "ui"),
    ("feature_usage", "engagement"),
    ("engineering_health", "engineering"),
    ("strategic", "competitive"),
    ("strategic", "marketing"),
    ("strategic", "profitability"),
    ("governance", "security"),
    ("data_quality", "engineering"),
    ("platform", "cross_platform"),
    ("behavioral_econ", "retention"),
    ("behavioral_econ", "onboarding"),
    ("behavioral_econ", "ux"),
    ("growth_accounting", "profitability"),
    ("growth_accounting", "retention"),
    ("journey", "onboarding"),
    ("journey", "retention"),
    ("brand_health", "marketing"),
    ("brand_health", "retention"),
    ("learning_science", "drill_quality"),
    ("learning_science", "curriculum"),
    ("learning_science", "retention"),
    ("copy_drift", "marketing"),
    ("copy_drift", "copy"),
    ("runtime_health", "engineering"),
    ("runtime_health", "security"),
}

# Rule-based learner archetype definitions
# Each rule: (name, condition_description, {criteria})
_ARCHETYPE_RULES = {
    "sprint": {
        "sessions_per_week_min": 5,
        "accuracy_min": 0.7,
        "description": "High-frequency learner, sessions most days",
    },
    "steady": {
        "sessions_per_week_min": 2,
        "sessions_per_week_max": 4,
        "accuracy_min": 0.6,
        "description": "Consistent moderate-frequency learner",
    },
    "weekend_warrior": {
        "weekend_pct_min": 0.6,
        "sessions_per_week_min": 1,
        "description": "Primarily learns on weekends",
    },
    "struggling": {
        "accuracy_max": 0.5,
        "sessions_per_week_min": 1,
        "description": "Active but low accuracy — needs support",
    },
    "lapsed": {
        "days_since_last_min": 14,
        "description": "No activity for 14+ days",
    },
}

# ── File map: logical areas → actual file paths ──────────────────────────
_FILE_MAP = {
    "routes": "mandarin/web/routes.py",
    "dashboard_routes": "mandarin/web/dashboard_routes.py",
    "session_routes": "mandarin/web/session_routes.py",
    "payment_routes": "mandarin/web/payment_routes.py",
    "auth_routes": "mandarin/web/auth_routes.py",
    "admin_routes": "mandarin/web/admin_routes.py",
    "onboarding_routes": "mandarin/web/onboarding_routes.py",
    "marketing_routes": "mandarin/web/marketing_routes.py",
    "landing_routes": "mandarin/web/landing_routes.py",
    "exposure_routes": "mandarin/web/exposure_routes.py",
    "settings_routes": "mandarin/web/settings_routes.py",
    "scheduler": "mandarin/scheduler.py",
    "email": "mandarin/email.py",
    "settings": "mandarin/settings.py",
    "security": "mandarin/security.py",
    "middleware": "mandarin/web/middleware.py",
    "app_js": "mandarin/web/static/app.js",
    "style_css": "mandarin/web/static/style.css",
    "bridge": "mandarin/web/bridge.py",
    "drills": "mandarin/drills/",
    "schema": "schema.sql",
    "pricing_template": "mandarin/web/templates/pricing.html",
    "dashboard_template": "mandarin/web/templates/dashboard.html",
    "admin_template": "mandarin/web/templates/admin.html",
    "marketing_landing": "marketing/landing/",
    "email_templates": "marketing/email-templates/",
}


def _f(*keys):
    """Resolve file keys to actual paths."""
    return [_FILE_MAP.get(k, k) for k in keys]


def _score_to_grade(score: float) -> str:
    """Convert a 0-100 score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _dimension_score(findings: list[dict], dimension: str, confidence: str = "high") -> tuple[float, str]:
    """Calculate score (0-100) and grade for a dimension based on its findings.

    Nonlinear scoring rules:
    - One critical finding caps the dimension at C (max 65)
    - Two+ critical findings cap at D (max 45)
    - One critical + one high caps at D (max 45)
    - "no data" confidence caps at B (max 80) — can't get an A without evidence
    """
    dim_findings = [f for f in findings if f.get("dimension") == dimension]
    score = 100.0
    for f in dim_findings:
        penalty = _SEVERITY_PENALTY.get(f.get("severity", "low"), 3)
        score -= penalty
    score = max(0.0, min(100.0, score))

    # Nonlinear caps
    critical_count = sum(1 for f in dim_findings if f.get("severity") == "critical")
    high_count = sum(1 for f in dim_findings if f.get("severity") == "high")

    if critical_count >= 2 or (critical_count >= 1 and high_count >= 1):
        score = min(score, 45.0)  # Capped at D
    elif critical_count >= 1:
        score = min(score, 65.0)  # Capped at C

    # No data = can't claim A — cap at B
    if confidence in ("none", "low"):
        score = min(score, 80.0)

    return round(score, 1), _score_to_grade(score)


def _overall_score(dimension_scores: dict) -> tuple[float, str]:
    """Weighted average across dimensions. Growth drivers weighted 1.5x.

    Nonlinear: any dimension with F grade caps overall at D.
    Any dimension with D grade caps overall at C.
    """
    if not dimension_scores:
        return 80.0, "B"  # No data = B at best, not A
    total_weight = 0.0
    weighted_sum = 0.0
    for dim, info in dimension_scores.items():
        weight = 1.5 if dim in _WEIGHTED_DIMENSIONS else 1.0
        weighted_sum += info["score"] * weight
        total_weight += weight
    score = round(weighted_sum / total_weight, 1) if total_weight > 0 else 80.0

    # Nonlinear caps: worst dimensions drag the overall down
    grades = [info["grade"] for info in dimension_scores.values()]
    if "F" in grades:
        score = min(score, 45.0)
    elif "D" in grades:
        score = min(score, 65.0)

    return score, _score_to_grade(score)


def _safe_query(conn, sql, params=(), default=None):
    """Execute a query, returning default on any error."""
    try:
        return conn.execute(sql, params).fetchone()
    except (sqlite3.OperationalError, sqlite3.Error):
        return default


def _safe_query_all(conn, sql, params=(), default=None):
    """Execute a query returning all rows, with fallback."""
    try:
        return conn.execute(sql, params).fetchall()
    except (sqlite3.OperationalError, sqlite3.Error):
        return default or []


def _safe_scalar(conn, sql, params=(), default=0):
    """Execute a query and return the first column of the first row."""
    row = _safe_query(conn, sql, params)
    if row is None:
        return default
    try:
        return row[0] if row[0] is not None else default
    except (IndexError, KeyError):
        return default


def _finding(dimension, severity, title, analysis, recommendation, claude_prompt, impact, files):
    """Create a standardized finding dict."""
    return {
        "dimension": dimension,
        "severity": severity,
        "title": title,
        "analysis": analysis,
        "recommendation": recommendation,
        "claude_prompt": claude_prompt,
        "impact": impact,
        "files": files,
    }


def _count_by(findings, key):
    counts = {}
    for f in findings:
        v = f.get(key, "unknown")
        counts[v] = counts.get(v, 0) + 1
    return counts


# ── Product lifecycle phases & real-user filtering ─────────────────────
#
# Scoring adapts to three lifecycle phases:
#
#   PRE_LAUNCH  (0 real users)
#     Solo-dev / admin-only.  User-behavior dimensions suppressed entirely.
#     Process-maturity (methodology) and commercial-readiness (strategic)
#     suppressed.  GenAI governance downgraded.  Only code/infra findings
#     (engineering, security, etc.) score at full weight.
#
#   EARLY       (1–29 real users)
#     Public but not yet statistically significant.  User-behavior and
#     strategic findings are kept but downgraded.  Methodology starts
#     contributing at reduced severity.  GenAI governance scored normally.
#
#   ESTABLISHED (30+ real users)
#     Full scoring — no suppression, all dimensions at full weight.
#

_REAL_USER_WHERE = "is_admin = 0 AND first_session_at IS NOT NULL"

_PHASE_THRESHOLDS = {
    "early": 1,        # first real user → early
    "established": 30,  # statistical significance → full scoring
}

# Dimensions whose signal depends on real user behavior — suppressed
# pre-launch (admin-only data pollutes metrics), downgraded early.
_USER_BEHAVIOR_DIMENSIONS = {
    "profitability",    # conversion rates meaningless with admin-only
    "retention",        # retention needs real cohorts
    "onboarding",       # completion rates polluted by admin testing
    "ux",               # bounce/completion rates reflect admin debugging, not UX
    "flow",             # session flow metrics need real users
    "engagement",       # engagement metrics need real users
    "drill_quality",    # drill accuracy/completion rates from admin testing
    "frustration",      # frustration signals from admin debugging
    # "platform" moved to _CODE_ASSESSABLE_DOWNGRADE_DIMENSIONS (code-inspectable)
    "encounter_loop",   # lookup-to-drill funnel needs real learner behavior
    "scheduler_audit",  # session completion % polluted by admin bouncing on bugs
    "srs_funnel",       # SRS progression metrics need real learners
    "error_taxonomy",   # error pattern distribution needs real usage
    "hsk_cliff",        # level transition analysis needs real progression data
}

# Dimensions assessable from code, content, and data — always scored.
# Findings are valid pre-launch (they examine the codebase/corpus, not
# user behavior), but severity is downgraded since they're aspirational.
_CODE_DATA_DIMENSIONS = {
    "content",          # content gaps (review queue, comprehension coverage)
    "cross_modality",   # modality mastery gaps in corpus data
    "curriculum",       # grammar pattern coverage gaps
    "marketing",        # page quality, analytics setup, strategy reviews
    "tone_phonology",   # tone drill volume, phonology content gaps
}

# System/infra/process dimensions — always at full weight
_SYSTEM_DIMENSIONS = {
    "engineering", "security", "methodology", "agentic",
    "governance", "data_quality", "genai_governance", "runtime_health",
}

# Dimensions that are assessable from code/infra but whose findings are
# aspirational pre-launch (solo-dev can't have Six Sigma DPMO or monetization
# metrics).  Downgraded to low pre-launch, medium early, full established.
_CODE_ASSESSABLE_DOWNGRADE_DIMENSIONS = {
    "methodology",       # process-maturity coverage is real but not critical pre-launch
    "strategic",         # content/competitive gaps are real insights, not emergencies
    "genai_governance",  # "unreviewed" findings are schema artifacts pre-launch
    "platform",          # code-inspectable (Flutter parity, config health) even pre-launch
}


def _real_user_count(conn) -> int:
    """Count non-admin users who have started at least one session."""
    return _safe_scalar(conn, f"SELECT COUNT(*) FROM user WHERE {_REAL_USER_WHERE}", default=0)


def _real_user_session_count(conn) -> int:
    """Count sessions from real (non-admin) users."""
    return _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM session_log
        WHERE user_id IN (SELECT id FROM user WHERE {_REAL_USER_WHERE})
    """, default=0)


def _lifecycle_phase(conn) -> str:
    """Determine the current product lifecycle phase."""
    real_users = _real_user_count(conn)
    if real_users >= _PHASE_THRESHOLDS["established"]:
        return "established"
    if real_users >= _PHASE_THRESHOLDS["early"]:
        return "early"
    return "pre_launch"


def _check_phase_transition(conn) -> list[dict]:
    """Emit a finding when the product lifecycle phase changes."""
    current_phase = _lifecycle_phase(conn)
    try:
        last_row = conn.execute(
            "SELECT dimension_scores FROM product_audit ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        if last_row and last_row[0]:
            import json as _json
            scores = _json.loads(last_row[0])
            last_phase = scores.get("_lifecycle_phase")
            if last_phase and last_phase != current_phase:
                return [_finding(
                    "pm", "low",
                    f"Lifecycle phase transition: {last_phase} → {current_phase}",
                    f"Product transitioned from {last_phase} to {current_phase}. "
                    f"Scoring weights have been adjusted automatically. "
                    f"Previously suppressed user-behavior dimensions are now active.",
                    "Review dimension scores — previously suppressed dimensions are now active.",
                    "Run product audit and review all dimensions that were previously suppressed.",
                    "Product lifecycle",
                    [],
                )]
    except Exception:
        pass
    return []


def suppress_low_sample_findings(conn, findings: list[dict]) -> list[dict]:
    """Adapt finding severity and visibility to the product lifecycle phase.

    PRE_LAUNCH (0 real users):
      - User-behavior dimensions: suppressed (no signal possible)
      - Code-assessable dimensions (methodology, strategic, genai_governance):
        downgraded to low — the gaps are real but not emergencies for solo-dev
      - Other system/infra (engineering, security): full weight

    EARLY (1–29 real users):
      - User-behavior dimensions: downgraded, tagged [EARLY]
      - Code-assessable dimensions: downgraded to medium (10+) or low (<10)
      - Other system/infra: full weight

    ESTABLISHED (30+ real users):
      - No suppression — full scoring
    """
    phase = _lifecycle_phase(conn)
    real_users = _real_user_count(conn)

    if phase == "established":
        return findings

    filtered = []
    for f in findings:
        dim = f.get("dimension", "")

        # ── Code-assessable dimensions: always keep, downgrade severity ──
        if dim in _CODE_ASSESSABLE_DOWNGRADE_DIMENSIONS:
            f = dict(f)
            if phase == "pre_launch":
                if f.get("severity") in ("critical", "high", "medium"):
                    f["severity"] = "low"
                tag = "[PRE-LAUNCH]"
            else:  # early
                if f.get("severity") in ("critical", "high"):
                    f["severity"] = "medium" if real_users >= 10 else "low"
                elif f.get("severity") == "medium" and real_users < 10:
                    f["severity"] = "low"
                tag = "[EARLY]"
            if not f.get("title", "").startswith(tag):
                f["title"] = f"{tag} {f['title']}"
            filtered.append(f)
            continue

        # ── User-behavior dimensions: suppress pre-launch, downgrade early ──
        if dim in _USER_BEHAVIOR_DIMENSIONS:
            if phase == "pre_launch":
                # No real users → no signal → suppress entirely
                continue

            # Early: downgrade + annotate
            f = dict(f)
            if f.get("severity") in ("critical", "high"):
                f["severity"] = "medium" if real_users >= 10 else "low"
            elif f.get("severity") == "medium" and real_users < 10:
                f["severity"] = "low"
            tag = "[EARLY]"
            if not f.get("title", "").startswith(tag):
                f["title"] = f"{tag} {f['title']}"
            f["analysis"] = (
                f"Early phase: {real_users} real user(s) — findings are "
                f"directional, not yet statistically significant. "
                f"{f.get('analysis', '')}"
            )
            filtered.append(f)
            continue

        # ── Everything else (system/infra, unknown dimensions): full weight ──
        filtered.append(f)

    return filtered
