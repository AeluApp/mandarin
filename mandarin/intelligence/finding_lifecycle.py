"""Product Intelligence — Finding Lifecycle with state machine.

State machine:
    INVESTIGATING → DIAGNOSED → RECOMMENDED → IMPLEMENTED → VERIFIED → RESOLVED
                                                           ↘ (regression) → INVESTIGATING
    Any state → REJECTED

Provides deduplication, hypothesis management, root cause tagging,
meta-analysis (engine accuracy), stale detection, and regression detection.
"""

import json
import logging
import math
import re
import sqlite3
from difflib import SequenceMatcher
from datetime import datetime, timezone, UTC

from ._base import (
    _SEVERITY_ORDER, _CORRELATED_DIMENSIONS,
    _safe_query, _safe_query_all, _safe_scalar,
)
from .feedback_loops import get_model_confidence

logger = logging.getLogger(__name__)

# Valid state transitions
_VALID_TRANSITIONS = {
    "investigating": {"diagnosed", "rejected"},
    "diagnosed": {"recommended", "rejected"},
    "recommended": {"implemented", "rejected"},
    "implemented": {"verified", "rejected"},
    "verified": {"resolved", "investigating"},  # investigating = regression
    "resolved": {"investigating"},  # regression
    "rejected": set(),  # terminal
}


def _canonical_title(title: str) -> str:
    """Normalize a finding title for fuzzy matching.

    Strips specific numbers/percentages to a placeholder so
    "D1 retention: 20%" and "D1 retention: 18%" become the same canonical form.
    """
    # Replace percentages like "20%" or "18.5%" with "X%"
    result = re.sub(r'\d+\.?\d*%', 'X%', title)
    # Replace standalone numbers like "20" or "3.5" with "N"
    result = re.sub(r'\b\d+\.?\d*\b', 'N', result)
    return result.strip()


def _fuzzy_match(title_a: str, title_b: str, threshold: float = 0.8) -> bool:
    """Check if two finding titles are fuzzy matches.

    Uses canonical form comparison first, then sentence transformer semantic
    similarity (if available), then SequenceMatcher as final fallback.
    """
    # Canonical match (exact after normalization)
    if _canonical_title(title_a) == _canonical_title(title_b):
        return True
    # Semantic similarity via sentence transformer (if installed)
    try:
        from ..ml.fuzzy_dedup import compute_similarity, is_available
        if is_available():
            sim = compute_similarity(title_a, title_b)
            if sim >= 0.82:
                return True
    except (ImportError, Exception):
        pass
    # SequenceMatcher fallback
    return SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio() >= threshold


def deduplicate_findings(conn, new_findings: list[dict]) -> list[dict]:
    """Match new findings to open pi_finding rows using fuzzy matching.

    Uses _fuzzy_match() to detect near-duplicate titles (e.g. different percentages).
    If match: increment times_seen, update last_seen_audit_id.
    If no match: insert new pi_finding row.
    Returns only genuinely new findings (no prior match).
    """
    genuinely_new = []

    # Get the most recent audit_id
    audit_row = _safe_query(conn, "SELECT MAX(id) FROM product_audit")
    audit_id = audit_row[0] if audit_row and audit_row[0] else None

    # Pre-load all open findings for fuzzy matching
    open_findings = _safe_query_all(conn, """
        SELECT id, dimension, title, times_seen FROM pi_finding
        WHERE status NOT IN ('resolved', 'rejected')
    """) or []

    for finding in new_findings:
        dim = finding.get("dimension", "")
        title = finding.get("title", "")
        severity = finding.get("severity", "low")

        # Fuzzy match against open findings in same dimension
        matched = None
        for of in open_findings:
            if of["dimension"] == dim and _fuzzy_match(title, of["title"]):
                matched = of
                break

        if matched:
            # Update existing finding
            try:
                conn.execute("""
                    UPDATE pi_finding
                    SET times_seen = times_seen + 1,
                        last_seen_audit_id = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (audit_id, matched["id"]))
            except (sqlite3.OperationalError, sqlite3.Error) as e:
                logger.debug("Failed to update pi_finding: %s", e)
        else:
            # Insert new finding
            try:
                conn.execute("""
                    INSERT INTO pi_finding
                        (audit_id, dimension, severity, title, analysis,
                         recommendation, status, metric_name, last_seen_audit_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'investigating', ?, ?)
                """, (
                    audit_id, dim, severity, title,
                    finding.get("analysis", ""),
                    finding.get("recommendation", ""),
                    finding.get("dimension", ""),  # metric_name defaults to dimension
                    audit_id,
                ))
                genuinely_new.append(finding)
            except (sqlite3.OperationalError, sqlite3.Error) as e:
                logger.debug("Failed to insert pi_finding: %s", e)

    # Confidence-based finding labeling (Self-Correction Layer)
    for finding in new_findings:
        dim = finding.get("dimension", "")
        try:
            conf_info = get_model_confidence(conn, dim)
            confidence = conf_info.get("confidence", 0.5)
            scored = conf_info.get("scored_count", 0)

            # Models with <5 scored outcomes always render as "medium"
            if scored < 5:
                finding["confidence_label"] = "medium"
            elif confidence >= 0.70:
                finding["confidence_label"] = "high"
            elif confidence >= 0.40:
                finding["confidence_label"] = "medium"
                finding["title"] = f"[CALIBRATING] {finding['title']}"
            else:
                finding["confidence_label"] = "low"
                finding["title"] = f"[LOW CONFIDENCE — REVIEW BEFORE ACTING] {finding['title']}"
                finding["requires_approval"] = True
                # Cap escalation to alert for low-confidence findings
                if finding.get("severity") in ("critical", "high"):
                    finding["severity"] = "high"
        except Exception:
            finding["confidence_label"] = "medium"

    try:
        conn.commit()
    except sqlite3.Error:
        pass

    return genuinely_new


def transition_finding(conn, finding_id: int, new_status: str, notes: str = "") -> bool:
    """Validate and execute a state transition.

    Returns True if transition was valid and executed.
    """
    current = _safe_query(conn, "SELECT status FROM pi_finding WHERE id = ?", (finding_id,))
    if not current:
        return False

    current_status = current["status"]
    valid_next = _VALID_TRANSITIONS.get(current_status, set())

    if new_status not in valid_next:
        logger.warning(
            "Invalid transition: %s → %s for finding %d",
            current_status, new_status, finding_id
        )
        return False

    # Enforcement gate: cannot mark implemented without a prediction record
    if new_status == "implemented":
        pred = _safe_query(conn, """
            SELECT id FROM pi_prediction_ledger WHERE finding_id = ?
        """, (finding_id,))
        if not pred:
            logger.warning(
                "Cannot mark finding %d as implemented — no prediction record. "
                "Call emit_prediction() first.", finding_id
            )
            return False

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            UPDATE pi_finding
            SET status = ?, updated_at = ?,
                resolved_at = CASE WHEN ? = 'resolved' THEN ? ELSE resolved_at END,
                resolution_notes = CASE WHEN ? != '' THEN ? ELSE resolution_notes END
            WHERE id = ?
        """, (new_status, now, new_status, now, notes, notes, finding_id))
        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to transition finding %d: %s", finding_id, e)
        return False


def attach_hypothesis(conn, finding_id: int, hypothesis: str, falsification: str) -> bool:
    """Set hypothesis and falsification criteria on a finding."""
    try:
        conn.execute("""
            UPDATE pi_finding
            SET hypothesis = ?, falsification = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (hypothesis, falsification, finding_id))
        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error):
        return False


def tag_root_cause(conn, finding_id: int, is_root: bool, linked_finding_id: int = None) -> bool:
    """Mark root_cause_tag as 'root_cause' or 'symptom'. If symptom, link to root cause."""
    tag = "root_cause" if is_root else "symptom"
    try:
        conn.execute("""
            UPDATE pi_finding
            SET root_cause_tag = ?,
                linked_finding_id = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (tag, linked_finding_id if not is_root else None, finding_id))
        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error):
        return False


def auto_tag_root_causes(conn, findings: list[dict]) -> None:
    """Directed RCA graph: build adjacency list from file overlap + severity gap
    and correlated dimensions. Nodes with in-degree 0 that have outgoing edges
    are root causes; their downstream nodes are symptoms."""
    if len(findings) < 2:
        return

    # Build adjacency list: i→j means i is a potential root cause of j
    n = len(findings)
    edges = set()  # (root_idx, symptom_idx)

    # Get files per finding
    finding_files = [set(f.get("files", [])) for f in findings]
    finding_dims = [f.get("dimension", "") for f in findings]
    finding_sevs = [_SEVERITY_ORDER.get(f.get("severity", "low"), 9) for f in findings]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            sev_gap = finding_sevs[j] - finding_sevs[i]  # positive means i is more severe
            if sev_gap < 2:
                continue

            # Criterion (a): file overlap + severity gap ≥ 2
            if finding_files[i] & finding_files[j]:
                edges.add((i, j))
                continue

            # Criterion (b): correlated dimensions + severity gap
            pair = tuple(sorted([finding_dims[i], finding_dims[j]]))
            if pair in _CORRELATED_DIMENSIONS:
                edges.add((i, j))

    if not edges:
        return

    # Compute in-degree
    in_degree = [0] * n
    out_degree = [0] * n
    for src, dst in edges:
        in_degree[dst] += 1
        out_degree[src] += 1

    # Root causes: in-degree 0 with outgoing edges
    roots = {i for i in range(n) if in_degree[i] == 0 and out_degree[i] > 0}
    symptoms = {j for _, j in edges if j not in roots}

    tagged = set()
    for root_idx in roots:
        f_root = findings[root_idx]
        root_row = _safe_query(conn, """
            SELECT id FROM pi_finding
            WHERE dimension = ? AND title = ?
              AND status NOT IN ('resolved', 'rejected')
            ORDER BY created_at DESC LIMIT 1
        """, (f_root.get("dimension"), f_root.get("title")))
        if root_row:
            tag_root_cause(conn, root_row["id"], True)

    for symptom_idx in symptoms:
        if symptom_idx in tagged:
            continue
        # Find the root that points to this symptom
        root_idx = next((src for src, dst in edges if dst == symptom_idx and src in roots), None)
        if root_idx is None:
            continue
        f_symptom = findings[symptom_idx]
        f_root = findings[root_idx]
        symptom_row = _safe_query(conn, """
            SELECT id FROM pi_finding
            WHERE dimension = ? AND title = ?
              AND status NOT IN ('resolved', 'rejected')
            ORDER BY created_at DESC LIMIT 1
        """, (f_symptom.get("dimension"), f_symptom.get("title")))
        root_row = _safe_query(conn, """
            SELECT id FROM pi_finding
            WHERE dimension = ? AND title = ?
              AND status NOT IN ('resolved', 'rejected')
            ORDER BY created_at DESC LIMIT 1
        """, (f_root.get("dimension"), f_root.get("title")))
        if symptom_row and root_row:
            tag_root_cause(conn, symptom_row["id"], False, root_row["id"])
            tagged.add(symptom_idx)


def compute_engine_accuracy(conn, lookback_days: int = 90) -> dict:
    """Meta-analysis: engine accuracy over time.

    Returns:
        total_findings, true_positives, false_positives, fpr,
        avg_time_per_state, per_dimension_accuracy
    """
    result = {
        "total_findings": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_positive_rate": 0.0,
        "avg_resolution_days": None,
        "per_dimension": {},
    }

    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_finding
        WHERE created_at >= datetime('now', ? || ' days')
    """, (f"-{lookback_days}",))
    result["total_findings"] = total or 0

    verified = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_finding
        WHERE status IN ('verified', 'resolved')
          AND created_at >= datetime('now', ? || ' days')
    """, (f"-{lookback_days}",))
    result["true_positives"] = verified or 0

    rejected = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_finding
        WHERE status = 'rejected'
          AND created_at >= datetime('now', ? || ' days')
    """, (f"-{lookback_days}",))
    result["false_positives"] = rejected or 0

    if total and total > 0:
        result["false_positive_rate"] = round((rejected or 0) / total * 100, 1)

    # Average resolution time
    avg_res = _safe_query(conn, """
        SELECT AVG(julianday(resolved_at) - julianday(created_at)) as avg_days
        FROM pi_finding
        WHERE resolved_at IS NOT NULL
          AND created_at >= datetime('now', ? || ' days')
    """, (f"-{lookback_days}",))
    if avg_res and avg_res["avg_days"] is not None:
        result["avg_resolution_days"] = round(avg_res["avg_days"], 1)

    # Per-dimension breakdown
    dim_stats = _safe_query_all(conn, """
        SELECT dimension,
               COUNT(*) as total,
               SUM(CASE WHEN status IN ('verified','resolved') THEN 1 ELSE 0 END) as verified,
               SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
        FROM pi_finding
        WHERE created_at >= datetime('now', ? || ' days')
        GROUP BY dimension
    """, (f"-{lookback_days}",))
    for row in (dim_stats or []):
        dim_total = row["total"] or 0
        dim_rejected = row["rejected"] or 0
        result["per_dimension"][row["dimension"]] = {
            "total": dim_total,
            "verified": row["verified"] or 0,
            "rejected": dim_rejected,
            "fpr": round(dim_rejected / dim_total * 100, 1) if dim_total > 0 else 0.0,
        }

    return result


def compute_counterfactual(conn, finding: dict) -> dict:
    """Compare affected vs unaffected cohorts for multiple dimensions.

    Covers retention, ux, flow, drill_quality. Includes 95% CI via
    normal approximation for difference in proportions.
    Returns {affected_metric, control_metric, delta, sample_sizes, significant, ci_95}.
    """
    dim = finding.get("dimension", "")
    result = {"available": False}

    # Define cohort queries per dimension
    cohort_queries = {
        "retention": {
            "affected": """
                SELECT COUNT(DISTINCT u.id) as total,
                       COUNT(DISTINCT CASE WHEN EXISTS (
                           SELECT 1 FROM session_log s2 WHERE s2.user_id = u.id
                             AND s2.started_at >= datetime(u.created_at, '+7 days')
                       ) THEN u.id END) as positive
                FROM user u
                JOIN session_log s ON s.user_id = u.id AND s.early_exit = 1
                WHERE u.created_at <= datetime('now', '-7 days')
            """,
            "control": """
                SELECT COUNT(DISTINCT u.id) as total,
                       COUNT(DISTINCT CASE WHEN EXISTS (
                           SELECT 1 FROM session_log s2 WHERE s2.user_id = u.id
                             AND s2.started_at >= datetime(u.created_at, '+7 days')
                       ) THEN u.id END) as positive
                FROM user u
                WHERE u.created_at <= datetime('now', '-7 days')
                  AND u.id NOT IN (SELECT DISTINCT user_id FROM session_log WHERE early_exit = 1)
            """,
        },
        "ux": {
            "affected": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN items_completed >= items_planned * 0.8 THEN 1 ELSE 0 END) as positive
                FROM session_log WHERE items_planned > 0 AND early_exit = 1
                  AND started_at >= datetime('now', '-30 days')
            """,
            "control": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN items_completed >= items_planned * 0.8 THEN 1 ELSE 0 END) as positive
                FROM session_log WHERE items_planned > 0 AND early_exit = 0
                  AND started_at >= datetime('now', '-30 days')
            """,
        },
        "flow": {
            "affected": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN items_completed >= items_planned * 0.8 THEN 1 ELSE 0 END) as positive
                FROM session_log WHERE items_planned > 0 AND early_exit = 1
                  AND started_at >= datetime('now', '-30 days')
            """,
            "control": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN items_completed >= items_planned * 0.8 THEN 1 ELSE 0 END) as positive
                FROM session_log WHERE items_planned > 0 AND early_exit = 0
                  AND started_at >= datetime('now', '-30 days')
            """,
        },
        "drill_quality": {
            "affected": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as positive
                FROM review_event WHERE drill_type IN (
                    SELECT drill_type FROM review_event
                    WHERE created_at >= datetime('now', '-14 days')
                    GROUP BY drill_type
                    HAVING AVG(CASE WHEN correct=1 THEN 1.0 ELSE 0.0 END) < 0.5
                )
                AND created_at >= datetime('now', '-14 days')
            """,
            "control": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as positive
                FROM review_event WHERE drill_type NOT IN (
                    SELECT drill_type FROM review_event
                    WHERE created_at >= datetime('now', '-14 days')
                    GROUP BY drill_type
                    HAVING AVG(CASE WHEN correct=1 THEN 1.0 ELSE 0.0 END) < 0.5
                )
                AND created_at >= datetime('now', '-14 days')
            """,
        },
    }

    if dim not in cohort_queries:
        return result

    queries = cohort_queries[dim]
    affected = _safe_query(conn, queries["affected"])
    control = _safe_query(conn, queries["control"])

    if not affected or not control:
        return result
    aff_total = affected["total"] or 0
    ctrl_total = control["total"] or 0
    if aff_total == 0 or ctrl_total == 0:
        return result

    aff_pos = affected["positive"] or 0
    ctrl_pos = control["positive"] or 0
    aff_rate = aff_pos / aff_total
    ctrl_rate = ctrl_pos / ctrl_total
    delta = ctrl_rate - aff_rate

    # 95% CI for difference in proportions (normal approximation)
    se = math.sqrt(
        aff_rate * (1 - aff_rate) / aff_total +
        ctrl_rate * (1 - ctrl_rate) / ctrl_total
    ) if aff_total > 0 and ctrl_total > 0 else 0
    z = 1.96
    ci_low = round((delta - z * se) * 100, 1)
    ci_high = round((delta + z * se) * 100, 1)
    significant = (ci_low > 0) or (ci_high < 0)  # CI doesn't include 0

    result = {
        "available": True,
        "affected_rate": round(aff_rate * 100, 1),
        "control_rate": round(ctrl_rate * 100, 1),
        "delta_pp": round(delta * 100, 1),
        "affected_n": aff_total,
        "control_n": ctrl_total,
        "significant": significant,
        "ci_95": [ci_low, ci_high],
    }

    return result


def check_stale_findings(conn) -> list[dict]:
    """Findings in INVESTIGATING or DIAGNOSED for >14 days → generate meta-finding."""
    from ._base import _finding

    stale = _safe_query_all(conn, """
        SELECT id, dimension, title, status,
               julianday('now') - julianday(updated_at) as days_stale
        FROM pi_finding
        WHERE status IN ('investigating', 'diagnosed')
          AND updated_at <= datetime('now', '-14 days')
    """)

    findings = []
    for row in (stale or []):
        findings.append(_finding(
            "pm", "medium",
            f"Stale finding: '{row['title']}' ({row['status']} for {round(row['days_stale'])}d)",
            f"Finding #{row['id']} in dimension '{row['dimension']}' has been in "
            f"'{row['status']}' state for {round(row['days_stale'])} days without progress.",
            "Either investigate further, advance to next state, or reject if no longer relevant.",
            (
                f"Stale finding #{row['id']}: {row['title']}\n\n"
                "1. Review the finding analysis and decide: advance, investigate, or reject\n"
                f"2. POST /api/admin/intelligence/findings/{row['id']}/transition"
            ),
            "Process: stale findings indicate investigation bottlenecks",
            [],
        ))

    return findings


def check_regression(conn) -> list[dict]:
    """Findings that were RESOLVED but whose metric has worsened → reopen."""
    from ._base import _finding

    resolved = _safe_query_all(conn, """
        SELECT pf.id, pf.dimension, pf.title, pf.metric_name,
               pf.metric_value_at_detection, pf.resolved_at
        FROM pi_finding pf
        WHERE pf.status = 'resolved'
          AND pf.resolved_at >= datetime('now', '-90 days')
          AND pf.metric_name IS NOT NULL
    """)

    findings = []
    for row in (resolved or []):
        # Check if the metric has regressed by looking at recent findings with same dimension+title pattern
        recent_match = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_finding
            WHERE dimension = ? AND title LIKE ? || '%'
              AND status = 'investigating'
              AND created_at > ?
        """, (row["dimension"], row["title"][:30], row["resolved_at"]))

        if recent_match and recent_match > 0:
            # Auto-reopen the resolved finding
            try:
                conn.execute("""
                    UPDATE pi_finding SET status = 'investigating',
                        resolution_notes = COALESCE(resolution_notes, '') || ' [Regression detected]',
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (row["id"],))
                conn.commit()
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

            findings.append(_finding(
                row["dimension"], "high",
                f"Regression: '{row['title']}' reopened after resolution",
                f"Finding #{row['id']} was resolved on {row['resolved_at']} but "
                "the same issue has reappeared. The fix may have been incomplete.",
                "Investigate why the previous fix didn't hold. Check for root cause vs symptom.",
                (
                    f"Regression on finding #{row['id']}: {row['title']}\n\n"
                    "1. Review the original resolution notes\n"
                    "2. Check if the fix addressed root cause or just symptoms\n"
                    "3. Look for environmental changes since resolution"
                ),
                "Process: regressions indicate incomplete fixes",
                [],
            ))

    return findings


def estimate_false_negatives(conn, lookback_days: int = 30) -> dict:
    """Cross-reference external signals against existing findings to estimate FNR.

    Checks SPC violations, crash spikes, client errors, and concluded experiments
    against pi_finding rows. Unmatched signals suggest missed findings (Six Sigma).
    Returns {total_signals, unmatched, fnr_estimate, details}.
    """
    result = {"total_signals": 0, "unmatched": 0, "fnr_estimate": 0.0, "details": []}
    lookback = f"-{lookback_days}"

    signal_sources = [
        ("spc_violation", """
            SELECT id, chart_type as signal_id, 'engineering' as dimension
            FROM spc_observation
            WHERE observed_at >= datetime('now', ? || ' days')
        """),
        ("crash_spike", """
            SELECT MIN(id) as id, traceback_hash as signal_id, 'engineering' as dimension
            FROM crash_log
            WHERE created_at >= datetime('now', ? || ' days')
            GROUP BY traceback_hash
            HAVING COUNT(*) >= 3
        """),
        ("client_error_spike", """
            SELECT MIN(id) as id, error_message as signal_id, 'ux' as dimension
            FROM client_error_log
            WHERE created_at >= datetime('now', ? || ' days')
            GROUP BY error_message
            HAVING COUNT(*) >= 5
        """),
        ("experiment_concluded", """
            SELECT id, name as signal_id, 'pm' as dimension
            FROM experiment
            WHERE status = 'concluded'
              AND concluded_at >= datetime('now', ? || ' days')
        """),
    ]

    for source_name, sql in signal_sources:
        signals = _safe_query_all(conn, sql, (lookback,))
        for sig in (signals or []):
            result["total_signals"] += 1
            sig_dim = sig["dimension"] if sig["dimension"] else "unknown"
            sig_id_val = str(sig["signal_id"] or "") if sig["signal_id"] else ""

            # Check if there's a corresponding finding
            had_finding = _safe_scalar(conn, """
                SELECT COUNT(*) FROM pi_finding
                WHERE dimension = ?
                  AND created_at >= datetime('now', ? || ' days')
                  AND status != 'rejected'
            """, (sig_dim, lookback))

            is_matched = (had_finding or 0) > 0
            if not is_matched:
                result["unmatched"] += 1
                result["details"].append({
                    "source": source_name,
                    "signal_id": sig_id_val,
                    "dimension": sig_dim,
                })

            # Persist to pi_false_negative_signal
            try:
                conn.execute("""
                    INSERT INTO pi_false_negative_signal
                        (signal_source, signal_id, dimension, had_finding)
                    VALUES (?, ?, ?, ?)
                """, (source_name, sig_id_val, sig_dim, 1 if is_matched else 0))
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    try:
        conn.commit()
    except sqlite3.Error:
        pass

    total = result["total_signals"]
    if total > 0:
        result["fnr_estimate"] = round(result["unmatched"] / total * 100, 1)

    return result
