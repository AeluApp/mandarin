"""Product Intelligence — Human-in-the-Loop decision support.

Classifies decisions by type, computes escalation levels, builds contextual
frames, surfaces findings for different roles, and manages human overrides.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# Escalation levels in order of urgency
_ESCALATION_ORDER = {
    "quiet": 0, "nudge": 1, "alert": 2, "escalate": 3, "emergency": 4,
}

# Industry benchmarks with source and last_verified date
_BENCHMARKS = {
    "retention": {"label": "Language app D7 retention", "range": "30-40%",
                  "source": "Duolingo SEC filings, Sensor Tower", "last_verified": "2025-06"},
    "ux": {"label": "Session completion rate", "range": "70-85%",
           "source": "Mobile app UX benchmarks (Amplitude)", "last_verified": "2025-06"},
    "profitability": {"label": "Freemium conversion", "range": "5-10%",
                      "source": "SaaS benchmarks (OpenView)", "last_verified": "2025-09"},
    "onboarding": {"label": "Signup-to-activation", "range": "40-60%",
                   "source": "ProductLed benchmarks", "last_verified": "2025-06"},
    "engagement": {"label": "Weekly active rate", "range": "30-50%",
                   "source": "Mixpanel mobile benchmarks", "last_verified": "2025-06"},
    "engineering": {"label": "Error rate", "range": "<0.1%",
                    "source": "Google SRE handbook", "last_verified": "2025-03"},
    "security": {"label": "Failed login rate", "range": "<5/day",
                 "source": "OWASP monitoring guidelines", "last_verified": "2025-03"},
}


def classify_decision(finding: dict, advisor_opinions: dict = None) -> str:
    """Classify what kind of human decision this finding requires.

    Returns: 'auto_fix', 'informed_fix', 'judgment_call', 'values_decision', 'investigation'
    """
    severity = finding.get("severity", "low")
    dim = finding.get("dimension", "")
    files = finding.get("files", [])

    # Check for advisor conflict
    opinions = advisor_opinions.get(finding.get("title", ""), []) if advisor_opinions else []
    has_conflict = False
    if len(opinions) >= 2:
        scores = [op.get("priority_score", 0) for op in opinions]
        has_conflict = (max(scores) - min(scores)) > 30

    # visual_vibe: aesthetic design quality findings
    if dim == "visual_vibe":
        analysis_lower = (finding.get("analysis", "") + " " + finding.get("title", "")).lower()
        # Token mismatches, missing dark mode, missing reduced-motion → auto-fix
        if any(kw in analysis_lower for kw in ("token mismatch", "missing dark mode",
                                                 "missing reduced-motion", "dark-mode",
                                                 "reduced motion")):
            return "auto_fix"
        # Typography weight changes or new animation patterns → informed fix
        if any(kw in analysis_lower for kw in ("font weight", "typography weight",
                                                 "animation pattern", "new animation",
                                                 "keyframe")):
            return "informed_fix"
        # Color shifts, spacing changes, motion timing → judgment call (A/B test)
        if any(kw in analysis_lower for kw in ("color shift", "spacing", "motion timing",
                                                 "palette", "transition speed",
                                                 "accent color", "shadow depth")):
            return "judgment_call"
        # Fundamental design language, new fonts, asset generation → values decision
        if any(kw in analysis_lower for kw in ("design language", "new font", "typeface",
                                                 "asset generation", "brand identity",
                                                 "illustration style")):
            return "values_decision"
        # Default for visual_vibe: judgment_call (routes to A/B test)
        return "judgment_call"

    # copy_drift: marketing/legal/email content accuracy findings
    if dim == "copy_drift":
        title_lower = (finding.get("title", "") + " " + finding.get("analysis", "")).lower()
        # Number mismatches (price, drill count) — straightforward swap → auto_fix
        if any(kw in title_lower for kw in ("drill count", "drill type count",
                                              "pricing mismatch", "stale price",
                                              "annual price mismatch")):
            return "auto_fix"
        # Removed feature still claimed, brand name mismatch → informed_fix
        if any(kw in title_lower for kw in ("offline", "overclaim", "old brand",
                                              "broken image", "brand name")):
            return "informed_fix"
        # Complex accuracy claims, LLM-identified issues → judgment_call
        if any(kw in title_lower for kw in ("[llm]", "misleading", "potential issue",
                                              "undisclosed")):
            return "judgment_call"
        # Legal text changes (privacy policy, terms of service) → values_decision
        if any(kw in title_lower for kw in ("privacy", "terms", "legal", "gdpr",
                                              "ccpa", "disclosure", "cookie")):
            return "values_decision"
        # Default for copy_drift number mismatches: auto_fix
        if severity == "low":
            return "auto_fix"
        if severity == "medium":
            return "informed_fix"
        return "judgment_call"

    # auto_fix: low severity, single file, all advisors agree
    if severity == "low" and len(files) <= 1 and not has_conflict:
        return "auto_fix"

    # investigation: data confidence is low (dimension contains signals of novelty)
    # Novel = first time seeing this finding
    analysis = finding.get("analysis", "").lower()
    if "insufficient data" in analysis or "no data" in analysis:
        return "investigation"

    # values_decision: involves retention vs learning tradeoff, or aesthetic
    learning_dims = {"drill_quality", "content", "srs_funnel", "error_taxonomy",
                     "cross_modality", "curriculum", "hsk_cliff", "tone_phonology"}

    if has_conflict:
        conflict_advisors = set()
        for op in opinions:
            if op.get("priority_score", 0) > 20:
                conflict_advisors.add(op["advisor"])
        if "learning" in conflict_advisors and "retention" in conflict_advisors:
            return "values_decision"

    if dim in ("copy",) or "aesthetic" in analysis or "tone" in analysis.lower():
        return "values_decision"

    # judgment_call: high severity, advisor conflict, or pedagogy
    if severity in ("high", "critical") and (has_conflict or dim in learning_dims):
        return "judgment_call"

    # informed_fix: medium severity, multiple approaches
    if severity == "medium" and len(files) >= 2:
        return "informed_fix"

    # Default for medium with single approach
    if severity == "medium":
        return "auto_fix"

    # High severity without conflict
    return "informed_fix"


def compute_escalation(conn, finding: dict, history: list = None) -> str:
    """Compute escalation level based on finding characteristics and history.

    Returns: 'quiet', 'nudge', 'alert', 'escalate', 'emergency'
    """
    severity = finding.get("severity", "low")
    dim = finding.get("dimension", "")
    title = finding.get("title", "")

    # Check how many audit cycles this finding has been open
    times_seen = 1
    pi_row = _safe_query(conn, """
        SELECT id, times_seen, status, created_at,
               julianday('now') - julianday(created_at) as age_days
        FROM pi_finding
        WHERE dimension = ? AND title = ?
          AND status NOT IN ('resolved', 'rejected')
        ORDER BY created_at DESC LIMIT 1
    """, (dim, title))

    if pi_row:
        times_seen = pi_row["times_seen"] or 1
        pi_row["age_days"] or 0
    else:
        pass

    # Check if a prior recommendation was implemented but didn't help
    prior_ineffective = False
    if pi_row:
        ineffective = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_recommendation_outcome
            WHERE finding_id = ? AND effective = -1
        """, (pi_row["id"],))
        prior_ineffective = (ineffective or 0) > 0

    # emergency: critical severity with high confidence, or metric >2 SD from mean
    if severity == "critical":
        return "emergency"

    # escalate: open 3+ cycles AND worsening, OR prior fix didn't work
    if times_seen >= 3 and prior_ineffective:
        return "escalate"
    if times_seen >= 3 and severity in ("high", "critical"):
        return "escalate"

    # alert: open 2+ cycles, or metric breached threshold
    if times_seen >= 2:
        return "alert"

    # nudge: first occurrence with medium severity
    if severity == "medium":
        return "nudge"

    # quiet: first occurrence, low severity
    return "quiet"


def build_context_frame(conn, finding: dict) -> dict:
    """Build rich context for human decision-making.

    Returns benchmarks, cohort breakdowns, why-now, correlations, options.
    """
    dim = finding.get("dimension", "")
    title = finding.get("title", "")

    frame = {
        "benchmarks": [],
        "cohort_breakdowns": [],
        "why_now": "",
        "correlations": [],
        "options": [],
    }

    # Benchmarks with staleness detection
    if dim in _BENCHMARKS:
        bm = _BENCHMARKS[dim]
        last_verified = bm.get("last_verified", "")
        stale = False
        if last_verified:
            try:
                from datetime import datetime as _dt
                verified_date = _dt.strptime(last_verified, "%Y-%m")
                stale = (_dt.now() - verified_date).days > 180
            except (ValueError, TypeError):
                pass
        frame["benchmarks"].append({
            "label": bm["label"],
            "value": bm["range"],
            "source": bm.get("source", "industry benchmarks"),
            "last_verified": last_verified,
            "stale": stale,
        })

    # Historical values from product_audit
    history = _safe_query_all(conn, """
        SELECT overall_score, dimension_scores, run_at
        FROM product_audit
        ORDER BY run_at DESC LIMIT 5
    """)
    if history:
        hist_values = []
        for h in history:
            try:
                ds = json.loads(h["dimension_scores"])
                if dim in ds:
                    hist_values.append({"run_at": h["run_at"], "score": ds[dim].get("score")})
            except (json.JSONDecodeError, TypeError):
                pass
        if hist_values:
            frame["benchmarks"].append({
                "label": "Your historical scores",
                "value": [h["score"] for h in hist_values],
                "source": "product_audit",
            })

    # Calibrated threshold
    cal = _safe_query(conn, """
        SELECT threshold_value, false_positive_rate FROM pi_threshold_calibration
        WHERE metric_name = ?
    """, (dim,))
    if cal:
        frame["benchmarks"].append({
            "label": "Calibrated threshold",
            "value": cal["threshold_value"],
            "source": "pi_threshold_calibration",
        })

    # Why now
    pi_row = _safe_query(conn, """
        SELECT times_seen, created_at, status
        FROM pi_finding
        WHERE dimension = ? AND title = ?
        ORDER BY created_at DESC LIMIT 1
    """, (dim, title))
    if pi_row:
        times = pi_row["times_seen"] or 1
        if times == 1:
            frame["why_now"] = "First time detected"
        elif times <= 3:
            frame["why_now"] = f"Seen {times} times — becoming persistent"
        else:
            frame["why_now"] = f"Seen {times} times — chronic issue requiring intervention"

        # Check if it was previously resolved
        was_resolved = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_finding
            WHERE dimension = ? AND title LIKE ? || '%'
              AND status = 'resolved'
        """, (dim, title[:30]))
        if was_resolved and was_resolved > 0:
            frame["why_now"] = "Regression from previously resolved state"
    else:
        frame["why_now"] = "New finding"

    # Cohort breakdowns: new/established/veteran users
    cohort_data = _safe_query_all(conn, """
        SELECT
            CASE
                WHEN julianday('now') - julianday(u.created_at) < 7 THEN 'new'
                WHEN julianday('now') - julianday(u.created_at) < 30 THEN 'established'
                ELSE 'veteran'
            END as cohort,
            COUNT(DISTINCT u.id) as user_count,
            AVG(CASE WHEN r.correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy,
            COUNT(DISTINCT s.id) * 1.0 / MAX(1, COUNT(DISTINCT u.id)) as sessions_per_user
        FROM user u
        LEFT JOIN session_log s ON u.id = s.user_id
        LEFT JOIN review_event r ON u.id = r.user_id
        GROUP BY cohort
    """)
    for row in (cohort_data or []):
        frame["cohort_breakdowns"].append({
            "cohort": row["cohort"],
            "users": row["user_count"] or 0,
            "accuracy": round((row["accuracy"] or 0) * 100, 1),
            "sessions_per_user": round(row["sessions_per_user"] or 0, 1),
        })

    # Populate options based on dimension type
    retention_dims = {"retention", "ux", "flow", "engagement", "frustration"}
    learning_dims = {"drill_quality", "content", "srs_funnel", "error_taxonomy",
                     "cross_modality", "curriculum", "hsk_cliff", "tone_phonology"}
    engineering_dims = {"engineering", "security", "timing", "platform"}

    if dim in retention_dims:
        frame["options"] = [
            {"action": "Adjust session length/difficulty", "impact": "Quick win for struggling users"},
            {"action": "Add scaffolding for at-risk cohort", "impact": "Targeted intervention"},
            {"action": "A/B test UX variant", "impact": "Data-driven decision, slower"},
        ]
    elif dim in learning_dims:
        frame["options"] = [
            {"action": "Add new drill types for weak areas", "impact": "Addresses root cause"},
            {"action": "Tune SRS intervals", "impact": "Systemic improvement"},
            {"action": "Add content for coverage gaps", "impact": "Expands curriculum"},
        ]
    elif dim in engineering_dims:
        frame["options"] = [
            {"action": "Fix root cause in hot path", "impact": "Eliminates error class"},
            {"action": "Add monitoring/alerting", "impact": "Earlier detection"},
            {"action": "Add error handling/graceful degradation", "impact": "Reduces user impact"},
        ]

    # Correlations — co-occurring findings in same audit
    co_findings = _safe_query_all(conn, """
        SELECT DISTINCT pf2.dimension, pf2.title
        FROM pi_finding pf1
        JOIN pi_finding pf2 ON pf1.audit_id = pf2.audit_id
            AND pf1.id != pf2.id
        WHERE pf1.dimension = ? AND pf1.title = ?
          AND pf2.status NOT IN ('resolved', 'rejected')
        LIMIT 5
    """, (dim, title))
    for cf in (co_findings or []):
        frame["correlations"].append(
            f"Co-occurs with: {cf['title']} ({cf['dimension']})"
        )

    return frame


def surface_for_role(finding: dict, context: dict, role: str) -> dict:
    """Adapt finding presentation for different roles.

    Roles: 'solo' (unified dev+product+admin), 'developer', 'product_owner', 'teacher'
    The 'solo' role is the default — it shows everything a solo founder needs:
    technical details, product impact, learning context, and actionable prompts.
    """
    base = {
        "title": finding.get("title"),
        "severity": finding.get("severity"),
        "dimension": finding.get("dimension"),
        "why_now": context.get("why_now", ""),
        "benchmarks": context.get("benchmarks", []),
    }

    if role == "solo":
        # Unified view: everything the solo dev/product owner/admin needs
        base["claude_prompt"] = finding.get("claude_prompt", "")
        base["files"] = finding.get("files", [])
        base["analysis"] = finding.get("analysis", "")
        base["impact"] = finding.get("impact", "")
        base["recommendation"] = finding.get("recommendation", "")
        base["correlations"] = context.get("correlations", [])
        base["options"] = context.get("options", [])
        base["cohort_breakdowns"] = context.get("cohort_breakdowns", [])

    elif role == "developer":
        base["claude_prompt"] = finding.get("claude_prompt", "")
        base["files"] = finding.get("files", [])
        base["analysis"] = finding.get("analysis", "")
        base["options"] = context.get("options", [])

    elif role == "product_owner":
        base["impact"] = finding.get("impact", "")
        base["recommendation"] = finding.get("recommendation", "")
        base["correlations"] = context.get("correlations", [])

    elif role == "teacher":
        # Pedagogical framing
        base["learning_impact"] = finding.get("analysis", "")
        base["recommendation"] = finding.get("recommendation", "")
        base["cohort_breakdowns"] = context.get("cohort_breakdowns", [])

    return base


def record_override(
    conn, finding_id: int, threshold_name: str, new_threshold: float,
    reason: str, expires_in_days: int = 90,
) -> bool:
    """Record a human override: 'stop flagging X.'"""
    try:
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, presented_to,
                 decision, decision_reason, override_expires_at)
            VALUES (?, 'auto_fix', 'quiet', 'solo',
                    ?, ?, datetime('now', ? || ' days'))
        """, (
            finding_id,
            f"Override: suppress {threshold_name} (new threshold: {new_threshold})",
            reason,
            f"+{expires_in_days}",
        ))

        # Also update the threshold
        conn.execute("""
            INSERT INTO pi_threshold_calibration
                (metric_name, threshold_value, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(metric_name) DO UPDATE SET
                threshold_value = excluded.threshold_value,
                calibrated_at = datetime('now'),
                prior_threshold = pi_threshold_calibration.threshold_value,
                notes = excluded.notes
        """, (threshold_name, new_threshold, f"Human override: {reason}"))

        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to record override: %s", e)
        return False


def check_override_sunsets(conn) -> list[dict]:
    """Find expired overrides and generate findings to re-evaluate."""
    from ._base import _finding

    expired = _safe_query_all(conn, """
        SELECT dl.id, dl.finding_id, dl.decision, dl.decision_reason,
               dl.override_expires_at, pf.dimension, pf.title
        FROM pi_decision_log dl
        JOIN pi_finding pf ON dl.finding_id = pf.id
        WHERE dl.override_expires_at IS NOT NULL
          AND dl.override_expires_at <= datetime('now')
          AND dl.outcome_notes IS NULL
    """)

    findings = []
    for row in (expired or []):
        findings.append(_finding(
            row["dimension"], "low",
            f"Override expired: '{row['title']}'",
            f"A human override on this finding expired. "
            f"Original reason: {row['decision_reason']}. "
            "The product has changed since then — please re-evaluate.",
            "Review whether this finding is still suppressed or needs attention.",
            f"Expired override on finding #{row['finding_id']}: {row['title']}",
            "Process: expired overrides should be re-evaluated",
            [],
        ))

        # Mark the override as handled
        try:
            conn.execute("""
                UPDATE pi_decision_log SET outcome_notes = 'Expired, regenerated finding'
                WHERE id = ?
            """, (row["id"],))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

    return findings


def apply_overrides(findings: list[dict], conn) -> list[dict]:
    """Filter out findings that match active, non-expired overrides."""
    # Get active overrides
    overrides = _safe_query_all(conn, """
        SELECT pf.dimension, pf.title
        FROM pi_decision_log dl
        JOIN pi_finding pf ON dl.finding_id = pf.id
        WHERE dl.override_expires_at IS NOT NULL
          AND dl.override_expires_at > datetime('now')
          AND dl.outcome_notes IS NULL
          AND dl.decision LIKE 'Override:%'
    """)

    if not overrides:
        return findings

    suppressed = {(r["dimension"], r["title"]) for r in overrides}

    return [f for f in findings if (f.get("dimension"), f.get("title")) not in suppressed]


def classify_and_escalate_all(
    conn, findings: list[dict], advisor_opinions: dict = None,
) -> list[dict]:
    """Classify and compute escalation for all findings.

    Returns sorted decision queue (highest escalation first).
    """
    queue = []

    for finding in findings:
        decision_class = classify_decision(finding, advisor_opinions)
        escalation = compute_escalation(conn, finding)
        context = build_context_frame(conn, finding)

        # Approval workflow: only auto_fix + severity=low doesn't require approval
        requires_approval = not (decision_class == "auto_fix" and finding.get("severity") == "low")

        queue.append({
            "title": finding.get("title"),
            "dimension": finding.get("dimension"),
            "severity": finding.get("severity"),
            "decision_class": decision_class,
            "escalation_level": escalation,
            "escalation_order": _ESCALATION_ORDER.get(escalation, 0),
            "requires_approval": requires_approval,
            "context": context,
            "finding": finding,
        })

        # Persist alert+ items to pi_decision_log for notification system
        if _ESCALATION_ORDER.get(escalation, 0) >= _ESCALATION_ORDER.get("alert", 2):
            try:
                # Look up finding ID
                pi_row = _safe_query(conn, """
                    SELECT id FROM pi_finding
                    WHERE dimension = ? AND title = ?
                      AND status NOT IN ('resolved', 'rejected')
                    ORDER BY created_at DESC LIMIT 1
                """, (finding.get("dimension"), finding.get("title")))
                if pi_row:
                    conn.execute("""
                        INSERT INTO pi_decision_log
                            (finding_id, decision_class, escalation_level,
                             presented_to, requires_approval)
                        VALUES (?, ?, ?, 'solo', ?)
                    """, (
                        pi_row["id"], decision_class, escalation,
                        1 if requires_approval else 0,
                    ))
            except (sqlite3.OperationalError, sqlite3.Error):
                pass
    try:
        conn.commit()
    except sqlite3.Error:
        pass

    # Sort by escalation level descending, then severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    queue.sort(key=lambda x: (
        -x["escalation_order"],
        severity_order.get(x["severity"], 9),
    ))

    return queue
