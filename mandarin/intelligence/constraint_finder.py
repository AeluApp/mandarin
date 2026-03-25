"""Product Intelligence — Cross-Domain Constraint Finder.

Priority-ordered constraint detection across pedagogical safety, learning,
engagement, content quality, AI health, product-market, and methodology.
Falls back to the existing ToC dimension-score analysis when no cross-domain
constraint is detected.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, UTC
from uuid import uuid4

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


def identify_cross_domain_constraint(conn, dimension_scores=None) -> dict:
    """Find the highest-priority cross-domain constraint.

    Checks domains in priority order:
        0: Pedagogical safety (rejected accuracy errors)
        1: Learning bottleneck (existing ToC)
        2: Engagement (session frequency)
        3: Content quality (review rejection rate)
        4: AI component health (portfolio verdict)
        5: Product-market (only when non-solo users)
        6: Methodology (framework grade gaps)

    Returns dict with:
        constraint, domain, severity, description, all_constraints
    """
    all_constraints = []

    checks = [
        ("pedagogical_safety", _check_pedagogical_safety),
        ("learning", _get_current_learning_bottleneck),
        ("engagement", _get_engagement_health),
        ("content_quality", _get_content_quality_constraint),
        ("ai_health", _get_ai_portfolio_verdict),
        ("methodology", _get_methodology_gaps),
    ]

    for domain, check_fn in checks:
        try:
            result = check_fn(conn) if domain != "learning" else check_fn(conn, dimension_scores)
            if result:
                all_constraints.append(result)
        except Exception as e:
            logger.debug("Constraint check %s failed: %s", domain, e)

    # Pick highest priority (first found)
    primary = all_constraints[0] if all_constraints else {
        "constraint": "none_detected",
        "domain": "none",
        "severity": "low",
        "description": "No cross-domain constraints detected. System is healthy.",
    }

    result = {
        **primary,
        "all_constraints": all_constraints,
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Persist if a real constraint was found
    if primary.get("constraint") != "none_detected":
        try:
            _persist_constraint(conn, primary)
        except Exception as e:
            logger.debug("Failed to persist constraint: %s", e)

    return result


def _check_pedagogical_safety(conn) -> dict | None:
    """Check for rejected accuracy errors in review queue.

    Pedagogical safety is Priority 0 — a wrong answer marked correct
    (or vice versa) is the most damaging possible issue.
    """
    # Count accuracy-related rejections in last 30 days
    rejected = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision = 'rejected'
        AND category = 'accuracy'
        AND created_at >= datetime('now', '-30 days')
    """, default=0)

    if rejected and rejected > 0:
        return {
            "constraint": "pedagogical_accuracy_errors",
            "domain": "pedagogical_safety",
            "severity": "critical" if rejected >= 3 else "high",
            "description": f"{rejected} accuracy error(s) rejected in review queue in last 30 days. "
                          "Learners may have been exposed to incorrect content.",
            "metric_value": rejected,
        }
    return None


def _get_current_learning_bottleneck(conn, dimension_scores=None) -> dict | None:
    """Use existing ToC to find learning bottleneck dimension."""
    if not dimension_scores:
        # Try to load from latest audit
        latest = _safe_query(conn, """
            SELECT dimension_scores FROM product_audit ORDER BY run_at DESC LIMIT 1
        """)
        if latest and latest[0]:
            try:
                dimension_scores = json.loads(latest[0])
            except (json.JSONDecodeError, TypeError):
                return None
        else:
            return None

    try:
        from ._synthesis import identify_system_constraint
        toc = identify_system_constraint(conn, dimension_scores)
        constraint_dim = toc.get("constraint")
        if constraint_dim:
            score = dimension_scores.get(constraint_dim, {})
            dim_score = score.get("score", 0) if isinstance(score, dict) else 0
            if dim_score < 75:  # Only flag if actually below B
                return {
                    "constraint": f"learning_bottleneck_{constraint_dim}",
                    "domain": "learning",
                    "severity": "high" if dim_score < 60 else "medium",
                    "description": f"ToC analysis: '{constraint_dim}' dimension (score {dim_score}) "
                                  f"is the system constraint. Marginal improvement: {toc.get('marginal_improvement', '?')} points.",
                    "metric_value": dim_score,
                    "toc_detail": toc,
                }
    except Exception as e:
        logger.debug("Learning bottleneck check failed: %s", e)
    return None


def _get_engagement_health(conn) -> dict | None:
    """Check session frequency from session_log over last 14 days."""
    session_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
    """, default=0)

    # For a solo learner, fewer than 3 sessions in 14 days is concerning
    user_count = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
    """, default=0)

    if user_count and user_count > 0 and session_count is not None:
        sessions_per_user = session_count / user_count
        if sessions_per_user < 2:
            return {
                "constraint": "low_engagement",
                "domain": "engagement",
                "severity": "high" if sessions_per_user < 1 else "medium",
                "description": f"Only {session_count} sessions across {user_count} user(s) "
                              f"in last 14 days ({sessions_per_user:.1f}/user). "
                              "Engagement is below healthy threshold.",
                "metric_value": sessions_per_user,
            }
    return None


def _get_content_quality_constraint(conn) -> dict | None:
    """Check accuracy rejection rate from review outcomes."""
    total_reviews = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision IS NOT NULL
        AND created_at >= datetime('now', '-30 days')
    """, default=0)

    rejected = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision = 'rejected'
        AND created_at >= datetime('now', '-30 days')
    """, default=0)

    if total_reviews and total_reviews >= 5:
        rejection_rate = rejected / total_reviews
        if rejection_rate > 0.15:
            return {
                "constraint": "high_content_rejection_rate",
                "domain": "content_quality",
                "severity": "high" if rejection_rate > 0.3 else "medium",
                "description": f"Content rejection rate is {rejection_rate:.0%} "
                              f"({rejected}/{total_reviews} reviews) in last 30 days. "
                              "Content pipeline may need quality improvements.",
                "metric_value": round(rejection_rate * 100, 1),
            }
    return None


def _get_ai_portfolio_verdict(conn) -> dict | None:
    """Check latest AI portfolio assessment for degraded/critical status."""
    latest = _safe_query(conn, """
        SELECT overall_verdict, assessed_at, component_count, healthy_count
        FROM pi_ai_portfolio_assessments
        ORDER BY assessed_at DESC LIMIT 1
    """)

    if latest:
        verdict = latest["overall_verdict"] if latest["overall_verdict"] else None
        if verdict in ("degraded", "critical"):
            healthy = latest["healthy_count"] or 0
            total = latest["component_count"] or 0
            return {
                "constraint": f"ai_portfolio_{verdict}",
                "domain": "ai_health",
                "severity": "critical" if verdict == "critical" else "high",
                "description": f"AI portfolio verdict is '{verdict}'. "
                              f"Only {healthy}/{total} components healthy.",
                "metric_value": healthy,
            }
    return None


def _get_methodology_gaps(conn) -> dict | None:
    """Check for failing framework grades."""
    failing = _safe_query_all(conn, """
        SELECT framework, grade, score
        FROM pi_framework_grades
        WHERE grade IN ('D', 'F')
        ORDER BY score ASC
        LIMIT 3
    """)

    if failing and len(failing) > 0:
        worst = failing[0]
        names = [f["framework"] for f in failing]
        return {
            "constraint": "methodology_gaps",
            "domain": "methodology",
            "severity": "medium",
            "description": f"{len(failing)} methodology framework(s) graded D or F: "
                          f"{', '.join(names)}. Worst: {worst['framework']} ({worst['grade']}, score {worst['score']}).",
            "metric_value": worst["score"] if worst["score"] is not None else 0,
        }
    return None


def _persist_constraint(conn, constraint: dict) -> None:
    """Insert a constraint into pi_system_constraint_history."""
    try:
        conn.execute("""
            INSERT INTO pi_system_constraint_history
                (id, identified_at, constraint_type, domain, severity, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(uuid4()),
            datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            constraint.get("constraint", "unknown"),
            constraint.get("domain", "unknown"),
            constraint.get("severity", "medium"),
            constraint.get("description", ""),
        ))
        conn.commit()
    except Exception as e:
        logger.debug("Failed to persist constraint: %s", e)
