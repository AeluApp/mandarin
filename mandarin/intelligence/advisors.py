"""Product Intelligence — Multi-agent advisor system with mediator.

4 advisors (Retention, Learning, Growth, Stability) independently evaluate
each finding. A Mediator resolves conflicts and produces a prioritized sprint plan.
All deterministic — zero Claude tokens.
"""

import json
import logging
import sqlite3

from ._base import _SEVERITY_ORDER, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# Effort estimates in developer-hours by change type
EFFORT_ESTIMATES = {
    "schema_migration": 2.0,
    "route_change": 1.0,
    "scheduler_change": 3.0,
    "css_change": 0.5,
    "email_template": 0.5,
    "drill_logic": 2.0,
    "content_addition": 1.0,
    "config_change": 0.5,
    "a_b_experiment": 2.0,
    "investigation": 1.5,
}

# Budget constraints per advisor
ADVISOR_BUDGETS = {
    "retention": {"weekly_hours": 8, "max_learning_loss_pct": 10},
    "learning": {"weekly_hours": 8, "max_retention_loss_pct": 5},
    "growth": {"weekly_hours": 6, "max_learning_loss_pct": 0},
    "stability": {"weekly_hours": 6, "no_feature_regression": True},
}

# Dimension→advisor affinity (which advisor cares most about which dimensions)
_ADVISOR_AFFINITIES = {
    "retention": {
        "retention": 2.0, "ux": 1.8, "flow": 1.5, "engagement": 1.5,
        "frustration": 1.5, "onboarding": 1.3,
    },
    "learning": {
        "drill_quality": 2.0, "content": 1.8, "srs_funnel": 2.0,
        "error_taxonomy": 1.5, "cross_modality": 1.5, "curriculum": 1.8,
        "hsk_cliff": 1.5, "tone_phonology": 1.5, "encounter_loop": 1.5,
        "scheduler_audit": 1.3,
    },
    "growth": {
        "profitability": 2.0, "onboarding": 1.8, "marketing": 2.0,
        "competitive": 1.5, "copy": 1.3,
    },
    "stability": {
        "engineering": 2.0, "security": 2.0, "timing": 1.8,
        "platform": 1.5, "ui": 1.3, "pm": 1.0,
    },
}

_SEVERITY_SCORES = {"critical": 40, "high": 25, "medium": 12, "low": 5}


def _estimate_effort(finding: dict) -> float:
    """Estimate effort in hours based on files involved."""
    files = finding.get("files", [])
    total = 0.0
    for f in files:
        if "schema" in f or "db/" in f:
            total += EFFORT_ESTIMATES["schema_migration"]
        elif "scheduler" in f:
            total += EFFORT_ESTIMATES["scheduler_change"]
        elif "routes" in f:
            total += EFFORT_ESTIMATES["route_change"]
        elif "style" in f or ".css" in f:
            total += EFFORT_ESTIMATES["css_change"]
        elif "email" in f:
            total += EFFORT_ESTIMATES["email_template"]
        elif "drills" in f:
            total += EFFORT_ESTIMATES["drill_logic"]
        elif "scripts/" in f:
            total += EFFORT_ESTIMATES["content_addition"]
        elif "settings" in f:
            total += EFFORT_ESTIMATES["config_change"]
        else:
            total += EFFORT_ESTIMATES["investigation"]
    return max(total, EFFORT_ESTIMATES["investigation"])  # Minimum = investigation


class _BaseAdvisor:
    """Base class for advisors."""
    name = "base"
    affinities = {}

    def evaluate(self, finding: dict, conn=None) -> dict:
        """Score a finding from this advisor's perspective.

        Returns {advisor, recommendation, priority_score, effort_estimate, rationale, tradeoff_notes}.
        """
        dim = finding.get("dimension", "unknown")
        severity = finding.get("severity", "low")

        # Base score from severity
        base_score = _SEVERITY_SCORES.get(severity, 5)

        # Affinity multiplier (how much this advisor cares about this dimension)
        affinity = self.affinities.get(dim, 0.5)

        # Domain-specific multiplier (subclasses override)
        domain_multiplier = self._domain_multiplier(finding, conn)

        priority = round(base_score * affinity * domain_multiplier, 1)
        effort = _estimate_effort(finding)

        return {
            "advisor": self.name,
            "recommendation": self._make_recommendation(finding),
            "priority_score": priority,
            "effort_estimate": effort,
            "rationale": self._rationale(finding, priority, affinity),
            "tradeoff_notes": self._tradeoffs(finding),
        }

    def _domain_multiplier(self, finding, conn=None):
        return 1.0

    def _make_recommendation(self, finding):
        return finding.get("recommendation", "")

    def _rationale(self, finding, score, affinity):
        return (
            f"{self.name} advisor: priority={score} "
            f"(severity={finding.get('severity')}, affinity={affinity})"
        )

    def _tradeoffs(self, finding):
        return ""


class RetentionAdvisor(_BaseAdvisor):
    """Prioritizes by churn risk impact."""
    name = "retention"
    affinities = _ADVISOR_AFFINITIES["retention"]

    def _domain_multiplier(self, finding, conn=None):
        if not conn:
            return 1.0
        dim = finding.get("dimension", "")
        if dim in ("retention", "ux", "frustration"):
            # Continuous: 1.0 + churn_risk * 0.5
            declining = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT user_id) FROM (
                    SELECT user_id,
                           COUNT(CASE WHEN started_at >= datetime('now', '-7 days') THEN 1 END) as recent,
                           COUNT(CASE WHEN started_at >= datetime('now', '-14 days')
                                       AND started_at < datetime('now', '-7 days') THEN 1 END) as prior
                    FROM session_log
                    GROUP BY user_id
                    HAVING prior > 0 AND recent < prior * 0.5
                )
            """)
            total = _safe_scalar(conn, "SELECT COUNT(*) FROM user") or 1
            churn_risk = min((declining or 0) / total, 1.0)
            return 1.0 + churn_risk * 0.5
        return 1.0

    def _tradeoffs(self, finding):
        dim = finding.get("dimension", "")
        if dim in ("drill_quality", "content", "srs_funnel"):
            return "Fixing this may temporarily disrupt learning sequences for active users."
        return ""


class LearningAdvisor(_BaseAdvisor):
    """Prioritizes by learning outcome impact."""
    name = "learning"
    affinities = _ADVISOR_AFFINITIES["learning"]

    def _domain_multiplier(self, finding, conn=None):
        dim = finding.get("dimension", "")
        if dim in ("srs_funnel", "drill_quality", "error_taxonomy", "cross_modality"):
            # Continuous: 1.0 + min(affected/100, 1.0) * 0.5
            if conn:
                affected = _safe_scalar(conn, """
                    SELECT COUNT(DISTINCT content_item_id) FROM progress
                    WHERE mastery_stage IN ('learning', 'stabilizing')
                      AND weak_cycle_count > 0
                """)
                return 1.0 + min((affected or 0) / 100.0, 1.0) * 0.5
            return 1.5
        return 1.0

    def _tradeoffs(self, finding):
        dim = finding.get("dimension", "")
        if dim in ("retention", "ux"):
            return "Learning improvements may increase difficulty, potentially hurting short-term retention."
        return ""


class GrowthAdvisor(_BaseAdvisor):
    """Prioritizes by conversion/activation impact."""
    name = "growth"
    affinities = _ADVISOR_AFFINITIES["growth"]

    def _domain_multiplier(self, finding, conn=None):
        dim = finding.get("dimension", "")
        if dim in ("profitability", "onboarding", "marketing"):
            return 1.5
        return 1.0

    def _tradeoffs(self, finding):
        dim = finding.get("dimension", "")
        if dim in ("drill_quality", "content"):
            return "Prioritizing growth over learning quality risks attracting users who churn quickly."
        return ""


class StabilityAdvisor(_BaseAdvisor):
    """Prioritizes by system reliability impact."""
    name = "stability"
    affinities = _ADVISOR_AFFINITIES["stability"]

    def _domain_multiplier(self, finding, conn=None):
        severity = finding.get("severity", "low")
        if severity == "critical":
            return 2.0
        dim = finding.get("dimension", "")
        if dim in ("engineering", "security"):
            # Continuous: 1.0 + min(crash_count/50, 1.0)
            if conn:
                crashes = _safe_scalar(conn, """
                    SELECT COUNT(*) FROM crash_log
                    WHERE created_at >= datetime('now', '-7 days')
                """)
                return 1.0 + min((crashes or 0) / 50.0, 1.0)
            return 1.5
        return 1.0

    def _tradeoffs(self, finding):
        dim = finding.get("dimension", "")
        if dim in ("profitability", "marketing", "onboarding"):
            return "Stability work delays new features and growth experiments."
        return ""


_ADVISORS = [
    RetentionAdvisor(),
    LearningAdvisor(),
    GrowthAdvisor(),
    StabilityAdvisor(),
]

# Advisor voting weights for conflict resolution
_ADVISOR_WEIGHTS = {
    "retention": 1.5,
    "learning": 1.5,
    "growth": 1.0,
    "stability": 1.0,
}


class Mediator:
    """Resolves conflicts between advisors and produces prioritized work plans."""

    def evaluate_all(self, conn, findings: list[dict]) -> dict:
        """Run all advisors on all findings. Returns {finding_title: [opinions]}."""
        all_opinions = {}

        for finding in findings:
            title = finding.get("title", "unknown")
            opinions = []
            for advisor in _ADVISORS:
                try:
                    opinion = advisor.evaluate(finding, conn)
                    opinions.append(opinion)
                    # Persist to DB
                    self._save_opinion(conn, finding, opinion)
                except Exception as e:
                    logger.debug("Advisor %s failed on '%s': %s", advisor.name, title, e)
            all_opinions[title] = opinions

        return all_opinions

    def _save_opinion(self, conn, finding: dict, opinion: dict):
        """Persist advisor opinion to pi_advisor_opinion table."""
        # Look up finding ID
        row = _safe_query(conn, """
            SELECT id FROM pi_finding
            WHERE dimension = ? AND title = ?
              AND status NOT IN ('resolved', 'rejected')
            ORDER BY created_at DESC LIMIT 1
        """, (finding.get("dimension"), finding.get("title")))

        if not row:
            return

        try:
            conn.execute("""
                INSERT INTO pi_advisor_opinion
                    (finding_id, advisor, recommendation, priority_score,
                     effort_estimate, rationale, tradeoff_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row["id"], opinion["advisor"], opinion["recommendation"],
                opinion["priority_score"], opinion["effort_estimate"],
                opinion["rationale"], opinion["tradeoff_notes"],
            ))
        except (sqlite3.OperationalError, sqlite3.Error):
            pass  # Table might not exist yet

    def _get_dynamic_weights(self, conn) -> dict:
        """Query latest product_audit scores to dynamically adjust advisor weights."""
        weights = dict(_ADVISOR_WEIGHTS)
        try:
            row = _safe_query(conn, """
                SELECT dimension_scores FROM product_audit
                ORDER BY run_at DESC LIMIT 1
            """)
            if row and row["dimension_scores"]:
                import json
                ds = json.loads(row["dimension_scores"])
                retention_score = ds.get("retention", {}).get("score", 80)
                engineering_score = ds.get("engineering", {}).get("score", 80)
                if retention_score < 60:
                    weights["retention"] = 2.0
                if engineering_score < 50:
                    weights["stability"] = 2.0
        except Exception:
            pass
        return weights

    def resolve(self, conn, finding: dict, opinions: list[dict]) -> dict:
        """Resolve conflict between advisors for a single finding.

        Uses dynamic weights based on current dimension scores.
        Returns {winning_advisor, resolution_rationale, tradeoff_summary, priority, tradeoff_options}.
        """
        if not opinions:
            return {"winning_advisor": None, "resolution_rationale": "No opinions",
                    "priority": 0, "tradeoff_options": []}

        dynamic_weights = self._get_dynamic_weights(conn)

        scores = {op["advisor"]: op["priority_score"] for op in opinions}
        max_score = max(scores.values())
        min_score = min(scores.values())

        # Detect conflict: spread > 30 points
        is_conflict = (max_score - min_score) > 30

        # Pareto frontier: all advisor options with tradeoff costs
        tradeoff_options = []
        for op in opinions:
            tradeoff_options.append({
                "advisor": op.get("advisor", ""),
                "recommendation": (op.get("recommendation") or "")[:200],
                "priority": op.get("priority_score", 0),
                "effort": op.get("effort_estimate", 0),
                "tradeoff": op.get("tradeoff_notes", ""),
            })

        if not is_conflict:
            avg_scores = {}
            for op in opinions:
                weight = dynamic_weights.get(op["advisor"], 1.0)
                avg_scores[op["advisor"]] = op["priority_score"] * weight

            winner = max(avg_scores, key=avg_scores.get)
            winning_opinion = next(op for op in opinions if op["advisor"] == winner)

            return {
                "winning_advisor": winner,
                "resolution_rationale": f"Consensus: {winner} has highest weighted score ({round(avg_scores[winner], 1)})",
                "tradeoff_summary": winning_opinion.get("tradeoff_notes", ""),
                "priority": round(avg_scores[winner], 1),
                "tradeoff_options": tradeoff_options,
            }
        else:
            weighted_votes = {}
            for op in opinions:
                weight = dynamic_weights.get(op["advisor"], 1.0)
                weighted_votes[op["advisor"]] = op["priority_score"] * weight

            winner = max(weighted_votes, key=weighted_votes.get)
            losing = [a for a in weighted_votes if a != winner]
            winning_opinion = next(op for op in opinions if op["advisor"] == winner)

            tradeoffs = [op["tradeoff_notes"] for op in opinions
                         if op["advisor"] != winner and op.get("tradeoff_notes")]
            tradeoff_summary = "; ".join(tradeoffs) if tradeoffs else ""

            resolution = {
                "winning_advisor": winner,
                "resolution_rationale": (
                    f"Conflict resolved by weighted vote: {winner} "
                    f"({round(weighted_votes[winner], 1)}) vs "
                    f"{', '.join(f'{a} ({round(weighted_votes[a], 1)})' for a in losing)}"
                ),
                "tradeoff_summary": tradeoff_summary,
                "priority": round(weighted_votes[winner], 1),
                "tradeoff_options": tradeoff_options,
            }

            self._save_resolution(conn, finding, resolution)
            return resolution

    def _save_resolution(self, conn, finding: dict, resolution: dict):
        """Persist mediator resolution to pi_advisor_resolution table."""
        row = _safe_query(conn, """
            SELECT id FROM pi_finding
            WHERE dimension = ? AND title = ?
              AND status NOT IN ('resolved', 'rejected')
            ORDER BY created_at DESC LIMIT 1
        """, (finding.get("dimension"), finding.get("title")))

        if not row:
            return

        try:
            conn.execute("""
                INSERT INTO pi_advisor_resolution
                    (finding_id, winning_advisor, resolution_rationale,
                     tradeoff_summary)
                VALUES (?, ?, ?, ?)
            """, (
                row["id"], resolution["winning_advisor"],
                resolution["resolution_rationale"],
                resolution["tradeoff_summary"],
            ))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

    def plan_sprint(self, conn, findings: list[dict], weekly_budget_hours: float = 20.0) -> dict:
        """Produce an ordered work plan within budget.

        1. Score all findings via all advisors
        2. Resolve conflicts for each finding
        3. Principled sort: (-priority, -times_seen, +effort_hours)
        4. Greedy knapsack with per-advisor budget enforcement
        """
        items = []

        for finding in findings:
            title = finding.get("title", "unknown")
            opinions = []
            for advisor in _ADVISORS:
                try:
                    opinions.append(advisor.evaluate(finding, conn))
                except Exception:
                    pass

            resolution = self.resolve(conn, finding, opinions)
            effort = _estimate_effort(finding)

            # Look up times_seen for tie-breaking
            times_seen = 1
            pi_row = _safe_query(conn, """
                SELECT times_seen FROM pi_finding
                WHERE dimension = ? AND title = ?
                  AND status NOT IN ('resolved', 'rejected')
                ORDER BY created_at DESC LIMIT 1
            """, (finding.get("dimension"), title))
            if pi_row:
                times_seen = pi_row["times_seen"] or 1

            items.append({
                "title": title,
                "dimension": finding.get("dimension"),
                "severity": finding.get("severity"),
                "priority": resolution.get("priority", 0),
                "effort_hours": effort,
                "winning_advisor": resolution.get("winning_advisor"),
                "tradeoff_summary": resolution.get("tradeoff_summary", ""),
                "files": finding.get("files", []),
                "times_seen": times_seen,
            })

        # Principled multi-key sort: (-priority, -times_seen, +effort_hours)
        items.sort(key=lambda x: (-x["priority"], -x["times_seen"], x["effort_hours"]))

        # Per-advisor budget tracking
        advisor_hours_used = {name: 0.0 for name in ADVISOR_BUDGETS}

        # Greedy knapsack with per-advisor budget enforcement
        plan = []
        remaining_hours = weekly_budget_hours
        deferred = []
        for item in items:
            advisor = item["winning_advisor"]
            advisor_budget = ADVISOR_BUDGETS.get(advisor, {}).get("weekly_hours", weekly_budget_hours)

            # Check per-advisor budget
            if advisor and advisor_hours_used.get(advisor, 0) + item["effort_hours"] > advisor_budget:
                deferred.append(item)
                continue

            if item["effort_hours"] <= remaining_hours:
                plan.append(item)
                remaining_hours -= item["effort_hours"]
                if advisor:
                    advisor_hours_used[advisor] = advisor_hours_used.get(advisor, 0) + item["effort_hours"]
            else:
                deferred.append(item)

        # Add dependency hints (shared files)
        file_owners = {}
        for i, item in enumerate(plan):
            for f in item["files"]:
                if f in file_owners:
                    if "depends_on" not in plan[i]:
                        plan[i]["depends_on"] = []
                    plan[i]["depends_on"].append(plan[file_owners[f]]["title"])
                else:
                    file_owners[f] = i

        return {
            "plan": plan,
            "total_hours": round(weekly_budget_hours - remaining_hours, 1),
            "budget_hours": weekly_budget_hours,
            "remaining_hours": round(remaining_hours, 1),
            "deferred_count": len(deferred),
            "advisor_hours_used": {k: round(v, 1) for k, v in advisor_hours_used.items() if v > 0},
        }
