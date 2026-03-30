"""Kanban health analyzers — monitor WIP limits, flow, aging, SLA compliance, and pull system health."""

import logging
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# Service class SLA targets: max cycle time in hours
SERVICE_CLASS_TARGETS = {
    "expedite": 48,
    "fixed_date": 168,
    "standard": 336,
    "intangible": 672,
}


# ── Check 1: WIP limit violations ────────────────────────────────────

def check_wip_violations(conn):
    """Flag service classes where in-progress count exceeds the configured WIP limit."""
    findings = []
    try:
        # Get WIP counts by service class
        wip_counts = _safe_query_all(conn,
            "SELECT service_class, COUNT(*) AS cnt "
            "FROM work_item WHERE status = 'in_progress' "
            "GROUP BY service_class")

        if not wip_counts:
            return findings

        for row in wip_counts:
            svc = row["service_class"] if isinstance(row, dict) else row[0]
            cnt = row["cnt"] if isinstance(row, dict) else row[1]

            # Look up WIP limit from kanban_config
            limit = _safe_scalar(conn,
                "SELECT wip_limit FROM kanban_config "
                "WHERE service_class = ?", (svc,), default=None)

            if limit is None:
                continue  # No configured limit for this class

            if cnt > limit:
                findings.append(_finding(
                    "kanban", "high",
                    f"WIP limit violated for '{svc}' ({cnt}/{limit})",
                    f"Service class '{svc}' has {cnt} items in progress, "
                    f"exceeding the WIP limit of {limit}. WIP violations "
                    f"degrade flow predictability and increase cycle times.",
                    f"Stop starting new '{svc}' work until in-progress count "
                    f"drops to or below {limit}. Swarm on existing items to "
                    f"finish them.",
                    f"Query work_item WHERE status='in_progress' AND "
                    f"service_class='{svc}'. Identify the oldest items and "
                    f"help unblock or complete them.",
                    "Flow efficiency and cycle time predictability",
                    ["mandarin/intelligence/analyzers_kanban_health.py"],
                ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 2: Expedite dilution ───────────────────────────────────────

def check_expedite_dilution(conn):
    """Flag if expedite items exceed 20% of completed work in the last 90 days."""
    findings = []
    try:
        total = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE status = 'done' "
            "AND completed_at > datetime('now', '-90 days')",
            default=0)

        if total < 5:
            return findings  # Not enough data

        expedite = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE status = 'done' "
            "AND service_class = 'expedite' "
            "AND completed_at > datetime('now', '-90 days')",
            default=0)

        ratio = expedite / total if total > 0 else 0

        if ratio > 0.20:
            findings.append(_finding(
                "kanban", "medium",
                f"Expedite dilution: {ratio*100:.0f}% of completed work is expedite",
                f"{expedite} of {total} items completed in the last 90 days were "
                f"expedite class ({ratio*100:.1f}%). When everything is urgent, "
                f"nothing is. Expedite items should be <20% to preserve the "
                f"priority signal.",
                "Tighten expedite criteria. Review recent expedite requests and "
                "reclassify items that could have been standard or fixed_date.",
                "Query work_item WHERE service_class='expedite' AND "
                "completed_at > datetime('now', '-90 days'). Review each item "
                "and propose reclassification criteria.",
                "Priority signal integrity",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: Aging items ─────────────────────────────────────────────

def check_aging_items(conn):
    """Flag items that are aging beyond thresholds for their service class."""
    findings = []
    try:
        # In-progress items with age
        in_progress = _safe_query_all(conn,
            "SELECT id, title, service_class, started_at, due_date, "
            "julianday('now') - julianday(started_at) AS age_days "
            "FROM work_item "
            "WHERE status = 'in_progress' AND started_at IS NOT NULL")

        blocked = _safe_query_all(conn,
            "SELECT id, title, service_class, blocked_at, due_date, "
            "julianday('now') - julianday(blocked_at) AS age_days "
            "FROM work_item "
            "WHERE status = 'blocked' AND blocked_at IS NOT NULL")

        all_items = (in_progress or []) + (blocked or [])

        critical_items = []
        warning_items = []

        for row in all_items:
            if isinstance(row, dict):
                svc = row.get("service_class", "standard")
                age = row.get("age_days", 0)
                title = row.get("title", f"item {row.get('id', '?')}")
                due_date = row.get("due_date")
                started_at = row.get("started_at")
            else:
                svc = row[2] if len(row) > 2 else "standard"
                age = row[5] if len(row) > 5 else 0
                title = row[1] if len(row) > 1 else f"item {row[0]}"
                due_date = row[4] if len(row) > 4 else None
                started_at = row[3] if len(row) > 3 else None

            if age is None:
                continue

            if svc == "expedite":
                if age > 5:
                    critical_items.append((title, svc, age))
                elif age > 2:
                    warning_items.append((title, svc, age))
            elif svc == "fixed_date" and due_date and started_at:
                # Compute fraction of time elapsed
                total_span = _safe_scalar(conn,
                    "SELECT julianday(?) - julianday(?)",
                    (due_date, started_at), default=0)
                if total_span and total_span > 0:
                    fraction = age / total_span
                    if fraction > 0.80:
                        critical_items.append((title, svc, age))
                    elif fraction > 0.50:
                        warning_items.append((title, svc, age))
            else:  # standard, intangible, unknown
                if age > 21:
                    critical_items.append((title, svc, age))
                elif age > 14:
                    warning_items.append((title, svc, age))

        if critical_items:
            names = ", ".join(f"'{t[0]}' ({t[1]}, {t[2]:.0f}d)" for t in critical_items[:5])
            findings.append(_finding(
                "kanban", "high",
                f"{len(critical_items)} item(s) critically aged",
                f"These items have exceeded critical aging thresholds: {names}. "
                f"Expedite >5d, standard >21d, or fixed_date >80% of time budget.",
                "Immediately swarm on critically aged items. Consider splitting, "
                "re-scoping, or escalating blockers.",
                "Query work_item WHERE status IN ('in_progress','blocked') and "
                "check age against service class thresholds. Propose unblocking "
                "actions for each.",
                "Flow health and delivery predictability",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))

        if warning_items:
            names = ", ".join(f"'{t[0]}' ({t[1]}, {t[2]:.0f}d)" for t in warning_items[:5])
            findings.append(_finding(
                "kanban", "medium",
                f"{len(warning_items)} item(s) approaching aging thresholds",
                f"These items are aging but not yet critical: {names}. "
                f"Expedite >2d, standard >14d, or fixed_date >50% of time budget.",
                "Review aging items in the next standup. Identify blockers early "
                "before they become critical.",
                "Query work_item for items approaching aging thresholds. "
                "Check for blockers and propose mitigation.",
                "Early warning for flow problems",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: Blocked stagnation ──────────────────────────────────────

def check_blocked_stagnation(conn):
    """Flag items blocked for more than 7 days."""
    findings = []
    try:
        stagnant = _safe_query_all(conn,
            "SELECT id, title, service_class, blocked_at, "
            "julianday('now') - julianday(blocked_at) AS blocked_days "
            "FROM work_item "
            "WHERE status = 'blocked' AND blocked_at IS NOT NULL "
            "AND julianday('now') - julianday(blocked_at) > 7 "
            "ORDER BY blocked_days DESC LIMIT 10")

        if not stagnant:
            return findings

        items = []
        for row in stagnant:
            if isinstance(row, dict):
                title = row.get("title", f"item {row.get('id', '?')}")
                days = row.get("blocked_days", 0)
            else:
                title = row[1] if len(row) > 1 else f"item {row[0]}"
                days = row[4] if len(row) > 4 else 0
            items.append((title, days))

        names = ", ".join(f"'{t}' ({d:.0f}d)" for t, d in items[:5])
        findings.append(_finding(
            "kanban", "high",
            f"{len(items)} item(s) blocked for 7+ days",
            f"These items have been blocked for over a week: {names}. "
            f"Stagnant blockers indicate systemic dependency or coordination "
            f"failures.",
            "Escalate blocked items. Identify the root cause of each blocker "
            "and create explicit unblocking actions. Consider policy changes "
            "to prevent recurring blockers.",
            "Query work_item WHERE status='blocked' AND blocked_at < "
            "datetime('now', '-7 days'). For each, identify the blocker "
            "reason and propose resolution.",
            "Flow throughput and blocker resolution",
            ["mandarin/intelligence/analyzers_kanban_health.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 5: Queue utilization too high ──────────────────────────────

def check_queue_instability(conn):
    """Flag when system utilization exceeds 85% of total WIP capacity."""
    findings = []
    try:
        in_progress = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item WHERE status = 'in_progress'",
            default=0)

        # Sum all WIP limits from kanban_config
        total_limit = _safe_scalar(conn,
            "SELECT SUM(wip_limit) FROM kanban_config",
            default=None)

        if total_limit is None or total_limit == 0:
            return findings  # No WIP limits configured

        utilization = in_progress / total_limit

        if utilization > 0.85:
            findings.append(_finding(
                "kanban", "high",
                f"System utilization at {utilization*100:.0f}% "
                f"({in_progress}/{total_limit} WIP)",
                f"In-progress count ({in_progress}) is {utilization*100:.0f}% "
                f"of total WIP capacity ({total_limit}). Queueing theory shows "
                f"that above ~85% utilization, wait times grow exponentially. "
                f"Flow becomes unpredictable.",
                "Reduce WIP by finishing existing work before pulling new items. "
                "Consider increasing WIP limits only if the team has grown.",
                "Check work_item WHERE status='in_progress' count against "
                "kanban_config total WIP. Identify items that can be deferred "
                "or completed quickly.",
                "System-level flow predictability",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 6: CFD expansion (flow stalling) ───────────────────────────

def check_cfd_expansion(conn):
    """Detect expanding in-progress band while done count is flat or declining."""
    findings = []
    try:
        # Current counts
        now_in_progress = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item WHERE status = 'in_progress'",
            default=0)
        now_done = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE status = 'done' "
            "AND completed_at > datetime('now', '-14 days')",
            default=0)

        # 14 days ago counts (approximate via items that were in progress then)
        prev_in_progress = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE started_at <= datetime('now', '-14 days') "
            "AND (completed_at IS NULL OR completed_at > datetime('now', '-14 days')) "
            "AND (blocked_at IS NULL OR blocked_at > datetime('now', '-14 days'))",
            default=0)
        prev_done = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE status = 'done' "
            "AND completed_at > datetime('now', '-28 days') "
            "AND completed_at <= datetime('now', '-14 days')",
            default=0)

        if prev_in_progress == 0 and now_in_progress == 0:
            return findings  # No data

        ip_grew = now_in_progress > prev_in_progress
        done_flat_or_declined = now_done <= prev_done

        if ip_grew and done_flat_or_declined and now_in_progress >= 3:
            findings.append(_finding(
                "kanban", "medium",
                "CFD expansion: in-progress growing while throughput stalls",
                f"In-progress items grew from {prev_in_progress} to "
                f"{now_in_progress} over 14 days, while completed items went "
                f"from {prev_done} to {now_done}. This expanding CFD band "
                f"indicates flow is stalling — work is entering faster than "
                f"it exits.",
                "Stop starting new work. Focus on finishing in-progress items. "
                "Investigate why throughput is declining (blockers, context "
                "switching, unclear requirements).",
                "Compare work_item counts by status over the last 14 days. "
                "Identify bottlenecks causing the in-progress expansion.",
                "Cumulative flow health",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 7: Pull system unused ──────────────────────────────────────

def check_pull_system_unused(conn):
    """Flag when ready items wait 3+ days with no pulls to in-progress."""
    findings = []
    try:
        # Items in 'ready' status for >3 days
        stale_ready = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE status = 'ready' "
            "AND created_at IS NOT NULL "
            "AND julianday('now') - julianday(created_at) > 3",
            default=0)

        if stale_ready == 0:
            return findings

        # Were any items moved to in_progress in the last 3 days?
        recent_pulls = _safe_scalar(conn,
            "SELECT COUNT(*) FROM work_item "
            "WHERE status = 'in_progress' "
            "AND started_at > datetime('now', '-3 days')",
            default=0)

        if recent_pulls == 0 and stale_ready > 0:
            findings.append(_finding(
                "kanban", "low",
                f"{stale_ready} ready item(s) waiting 3+ days with no pulls",
                f"{stale_ready} item(s) in 'ready' status have been waiting "
                f"over 3 days and no items were pulled into in-progress during "
                f"that period. The pull system may not be functioning — work "
                f"should flow from ready to in-progress continuously.",
                "Review the ready queue in the next standup. Pull the highest "
                "priority item immediately if WIP limits allow.",
                "Query work_item WHERE status='ready' ORDER BY priority. "
                "Check if WIP limits prevent pulling. If not, identify why "
                "the team is not pulling work.",
                "Pull system discipline",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 8: Cycle time regression ───────────────────────────────────

def check_cycle_time_regression(conn):
    """Flag if P85 cycle time regressed >30% vs the prior 30-day window."""
    findings = []
    try:
        # Recent 30-day cycle times (in days)
        recent_rows = _safe_query_all(conn,
            "SELECT julianday(completed_at) - julianday(started_at) AS ct "
            "FROM work_item "
            "WHERE status = 'done' "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND completed_at > datetime('now', '-30 days') "
            "ORDER BY ct")

        # Prior 30-day cycle times
        prev_rows = _safe_query_all(conn,
            "SELECT julianday(completed_at) - julianday(started_at) AS ct "
            "FROM work_item "
            "WHERE status = 'done' "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND completed_at > datetime('now', '-60 days') "
            "AND completed_at <= datetime('now', '-30 days') "
            "ORDER BY ct")

        if not recent_rows or len(recent_rows) < 5 or not prev_rows or len(prev_rows) < 5:
            return findings  # Not enough data

        def p85(rows):
            values = []
            for r in rows:
                v = r["ct"] if isinstance(r, dict) else r[0]
                if v is not None and v >= 0:
                    values.append(v)
            if not values:
                return 0
            values.sort()
            idx = int(len(values) * 0.85)
            idx = min(idx, len(values) - 1)
            return values[idx]

        recent_p85 = p85(recent_rows)
        prev_p85 = p85(prev_rows)

        if prev_p85 > 0 and recent_p85 > prev_p85 * 1.30:
            pct_increase = ((recent_p85 - prev_p85) / prev_p85) * 100
            findings.append(_finding(
                "kanban", "medium",
                f"P85 cycle time regressed {pct_increase:.0f}% "
                f"({prev_p85:.1f}d → {recent_p85:.1f}d)",
                f"The 85th-percentile cycle time increased from "
                f"{prev_p85:.1f} days to {recent_p85:.1f} days compared to "
                f"the prior 30-day window. This {pct_increase:.0f}% regression "
                f"indicates flow is slowing down.",
                "Investigate root causes: increased WIP, more blockers, scope "
                "creep, or context switching. Review completed items for "
                "outliers dragging up the P85.",
                "Compare cycle times across the last two 30-day windows. "
                "Identify outlier items and common blocker patterns.",
                "Delivery predictability (cycle time stability)",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 9: SLA compliance ──────────────────────────────────────────

def check_sla_compliance(conn):
    """Flag if overall SLA compliance drops below 80%."""
    findings = []
    try:
        total_compliant = 0
        total_items = 0
        per_class = []

        for svc, max_hours in SERVICE_CLASS_TARGETS.items():
            rows = _safe_query_all(conn,
                "SELECT "
                "(julianday(completed_at) - julianday(started_at)) * 24 AS cycle_hours "
                "FROM work_item "
                "WHERE status = 'done' "
                "AND service_class = ? "
                "AND started_at IS NOT NULL AND completed_at IS NOT NULL",
                (svc,))

            if not rows:
                continue

            count = 0
            compliant = 0
            for row in rows:
                hours = row["cycle_hours"] if isinstance(row, dict) else row[0]
                if hours is None:
                    continue
                count += 1
                if hours <= max_hours:
                    compliant += 1

            if count > 0:
                rate = compliant / count
                per_class.append((svc, compliant, count, rate))
                total_compliant += compliant
                total_items += count

        if total_items < 5:
            return findings  # Not enough data

        overall_rate = total_compliant / total_items

        if overall_rate < 0.80:
            class_details = ", ".join(
                f"{svc}: {rate*100:.0f}% ({c}/{n})"
                for svc, c, n, rate in per_class
            )
            findings.append(_finding(
                "kanban", "high",
                f"SLA compliance at {overall_rate*100:.0f}% (target: 80%+)",
                f"Overall SLA compliance is {overall_rate*100:.0f}% "
                f"({total_compliant}/{total_items} items within target). "
                f"By class: {class_details}. Targets: expedite ≤48h, "
                f"fixed_date ≤168h, standard ≤336h, intangible ≤672h.",
                "Identify which service classes are missing SLA most often. "
                "Reduce WIP, improve blocker resolution, or adjust SLA "
                "targets if they are unrealistic.",
                "Query work_item by service_class with cycle time computation. "
                "Identify items that missed SLA and their common root causes.",
                "Service level predictability",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 10: Blocked time ratio ─────────────────────────────────────

def check_blocked_time_ratio(conn):
    """Flag if average blocked-to-cycle-time ratio exceeds 25%."""
    findings = []
    try:
        rows = _safe_query_all(conn,
            "SELECT total_blocked_hours, "
            "(julianday(completed_at) - julianday(started_at)) * 24 AS cycle_hours "
            "FROM work_item "
            "WHERE status = 'done' "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND total_blocked_hours IS NOT NULL "
            "AND total_blocked_hours > 0")

        if not rows or len(rows) < 3:
            return findings  # Not enough data

        ratios = []
        for row in rows:
            if isinstance(row, dict):
                blocked = row.get("total_blocked_hours", 0)
                cycle = row.get("cycle_hours", 0)
            else:
                blocked = row[0] if row[0] is not None else 0
                cycle = row[1] if len(row) > 1 and row[1] is not None else 0

            if cycle > 0:
                ratios.append(blocked / cycle)

        if not ratios:
            return findings

        avg_ratio = sum(ratios) / len(ratios)

        if avg_ratio > 0.25:
            findings.append(_finding(
                "kanban", "medium",
                f"Blocked time ratio at {avg_ratio*100:.0f}% of cycle time "
                f"(target: <25%)",
                f"Completed items spend an average of {avg_ratio*100:.0f}% of "
                f"their cycle time in a blocked state (based on "
                f"{len(ratios)} items with blocked time). More than a quarter "
                f"of lead time is waste from waiting on dependencies or "
                f"external input.",
                "Analyze the most common blocker reasons. Establish policies "
                "for faster dependency resolution, pre-work dependency "
                "checks, and blocker escalation timers.",
                "Query work_item WHERE total_blocked_hours > 0 AND "
                "status='done'. Compute blocked_hours / cycle_hours for each. "
                "Identify items with highest ratios and their blocker reasons.",
                "Flow efficiency (value-add vs wait time)",
                ["mandarin/intelligence/analyzers_kanban_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ────────────────────────────────────────────────

ANALYZERS = [
    check_wip_violations,
    check_expedite_dilution,
    check_aging_items,
    check_blocked_stagnation,
    check_queue_instability,
    check_cfd_expansion,
    check_pull_system_unused,
    check_cycle_time_regression,
    check_sla_compliance,
    check_blocked_time_ratio,
]
