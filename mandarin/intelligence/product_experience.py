"""Product Intelligence — Product Experience Layer.

User feedback, interaction events, and release-correlated anomaly detection.
Gives the engine UX-level signal it cannot otherwise see.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone, UTC
from uuid import uuid4

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# Valid interaction event types
EVENT_TYPES = {
    "screen_view", "screen_exit", "session_start", "session_abandon",
    "item_answer", "item_skip", "item_replay", "item_hint",
    "rage_click", "long_pause", "rapid_exit", "error_encounter",
    "back_navigate", "repeated_back",
}

# Initial feedback prompts
INITIAL_PROMPTS = [
    {
        "prompt_type": "session_frustration",
        "prompt_text": "Did anything frustrate you in this session?",
        "trigger_condition": "session_end",
        "frequency_limit": "once_per_session",
        "suppress_if_streak_below": 5,
    },
    {
        "prompt_type": "session_completion",
        "prompt_text": "Did you finish what you came to do?",
        "trigger_condition": "session_end",
        "frequency_limit": "once_per_session",
        "suppress_if_streak_below": 3,
    },
    {
        "prompt_type": "item_difficulty",
        "prompt_text": None,
        "trigger_condition": "item_complete",
        "frequency_limit": "always",
        "suppress_if_streak_below": 0,
    },
]

# Dimensions where lower values are worse
_WORSE_IF_LOWER = {
    "retention", "ux", "drill_quality", "engagement",
    "onboarding", "srs_funnel", "flow", "curriculum",
}


# ── Seed Functions ───────────────────────────────────────────────────────────

def seed_feedback_prompts(conn) -> int:
    """Seed initial feedback prompts. Idempotent."""
    count = 0
    for p in INITIAL_PROMPTS:
        existing = _safe_query(conn, """
            SELECT id FROM pi_feedback_prompts WHERE prompt_type = ?
        """, (p["prompt_type"],))
        if existing:
            continue
        try:
            conn.execute("""
                INSERT INTO pi_feedback_prompts
                    (id, prompt_type, prompt_text, trigger_condition,
                     frequency_limit, suppress_if_streak_below)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(uuid4()), p["prompt_type"], p["prompt_text"],
                p["trigger_condition"], p["frequency_limit"],
                p["suppress_if_streak_below"],
            ))
            count += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to seed prompt %s: %s", p["prompt_type"], e)

    if count:
        conn.commit()
    return count


# ── Event Ingestion ──────────────────────────────────────────────────────────

def ingest_events(conn, events: list) -> int:
    """Ingest a batch of interaction events. Max 50 per call.

    Returns count of events accepted. Never raises — best-effort.
    """
    inserted = 0
    for event in events[:50]:
        event_type = event.get("event_type")
        if event_type not in EVENT_TYPES:
            continue

        occurred_at = event.get("occurred_at", datetime.now(UTC).isoformat())

        try:
            conn.execute("""
                INSERT INTO pi_interaction_events
                    (id, user_id, session_id, occurred_at, event_type,
                     screen_name, element_id, item_id, time_on_screen_ms,
                     time_to_action_ms, was_correct, error_code,
                     app_version, day_bucket, hour_bucket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATE(?),
                        CAST(strftime('%H', ?) AS INTEGER))
            """, (
                str(uuid4()),
                event.get("user_id", "unknown"),
                event.get("session_id", "unknown"),
                occurred_at, event_type,
                event.get("screen_name"),
                event.get("element_id"),
                event.get("item_id"),
                event.get("time_on_screen_ms"),
                event.get("time_to_action_ms"),
                event.get("was_correct"),
                event.get("error_code"),
                event.get("app_version", "unknown"),
                occurred_at, occurred_at,
            ))
            inserted += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to insert event: %s", e)

    if inserted:
        try:
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            pass
    return inserted


# ── UX Feedback Analyzer ────────────────────────────────────────────────────

def analyze_ux_feedback(conn) -> list:
    """Analyze UX feedback signals for findings."""
    findings = []
    cutoff = (datetime.now(UTC) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    # Session frustration trend
    frustration = _safe_query_all(conn, """
        SELECT DATE(occurred_at) as day,
               AVG(response_value) as avg_frustration,
               COUNT(*) as response_count
        FROM pi_ux_feedback
        WHERE feedback_type = 'session_frustration'
          AND occurred_at >= ?
          AND response_value IS NOT NULL
        GROUP BY DATE(occurred_at)
        ORDER BY day
    """, (cutoff,))

    if frustration and len(frustration) >= 5:
        recent_avg = sum(r["avg_frustration"] for r in frustration[-5:]) / 5
        baseline_avg = sum(r["avg_frustration"] for r in frustration[:5]) / 5

        if baseline_avg > 0 and recent_avg > baseline_avg * 1.3 and recent_avg > 0.4:
            total_responses = sum(r["response_count"] for r in frustration[-5:])
            sev = "high" if recent_avg > 0.7 else "medium"
            findings.append(_finding(
                "frustration", sev,
                f"Session frustration rising: {recent_avg:.2f} avg (up from {baseline_avg:.2f})",
                (f"Average session frustration score has increased "
                 f"{((recent_avg / baseline_avg) - 1) * 100:.0f}% over the last 5 days. "
                 f"Based on {total_responses} responses."),
                "Review recent releases and interaction events for UX regressions.",
                "Investigate session frustration increase.",
                f"Frustration: {recent_avg:.2f} avg",
                ["mandarin/web/"],
            ))

    # Item difficulty distribution
    difficulty = _safe_query_all(conn, """
        SELECT response_value, COUNT(*) as cnt
        FROM pi_ux_feedback
        WHERE feedback_type = 'item_difficulty'
          AND occurred_at >= ?
          AND response_value IS NOT NULL
        GROUP BY response_value
    """, (cutoff,))

    if difficulty:
        dist = {r["response_value"]: r["cnt"] for r in difficulty}
        total = sum(dist.values())
        too_hard_pct = dist.get(1, 0) / total if total > 0 else 0
        too_easy_pct = dist.get(-1, 0) / total if total > 0 else 0

        if too_hard_pct > 0.40:
            findings.append(_finding(
                "drill_quality", "high",
                f"Item difficulty skewing hard: {too_hard_pct:.0%} rated too hard",
                (f"{too_hard_pct:.0%} of {total} rated items were flagged as too hard. "
                 f"Target range: 15-30% too hard (desirable difficulty zone)."),
                "Decrease DIFFICULTY_TARGET_ACCURACY or review item selection logic.",
                "Adjust item difficulty parameters.",
                f"{too_hard_pct:.0%} too hard",
                ["mandarin/config.py", "mandarin/scheduler.py"],
            ))

        if too_easy_pct > 0.50:
            findings.append(_finding(
                "drill_quality", "medium",
                f"Item difficulty skewing easy: {too_easy_pct:.0%} rated too easy",
                (f"{too_easy_pct:.0%} of rated items flagged as too easy. "
                 f"Under-challenge reduces long-term retention."),
                "Increase DIFFICULTY_TARGET_ACCURACY or review mastery threshold.",
                "Adjust difficulty for more challenge.",
                f"{too_easy_pct:.0%} too easy",
                ["mandarin/config.py", "mandarin/scheduler.py"],
            ))

    # Screen-specific confusion signals
    confusion = _safe_query_all(conn, """
        SELECT screen_name, COUNT(*) as confusion_count
        FROM pi_ux_feedback
        WHERE feedback_type = 'interface_confusion'
          AND occurred_at >= ?
        GROUP BY screen_name
        ORDER BY confusion_count DESC
        LIMIT 5
    """, (cutoff,))

    for screen in (confusion or []):
        if screen["confusion_count"] >= 5:
            findings.append(_finding(
                "ux", "medium",
                f"Interface confusion on {screen['screen_name']}: {screen['confusion_count']} events",
                (f"{screen['confusion_count']} rage clicks or extended pauses detected "
                 f"on {screen['screen_name']} in last 14 days."),
                f"Review {screen['screen_name']} layout, tap targets, and information hierarchy.",
                f"Fix UX issues on {screen['screen_name']}.",
                f"{screen['confusion_count']} confusion events",
                ["mandarin/web/"],
            ))

    # Session completion rate
    completion = _safe_query(conn, """
        SELECT AVG(CASE WHEN response_value = 1 THEN 1.0 ELSE 0.0 END) as completion_rate,
               COUNT(*) as total
        FROM pi_ux_feedback
        WHERE feedback_type = 'session_completion'
          AND occurred_at >= ?
    """, (cutoff,))

    if completion and (completion["total"] or 0) >= 10:
        rate = completion["completion_rate"] or 0
        if rate < 0.65:
            findings.append(_finding(
                "ux", "high",
                f"Session completion rate low: {rate:.0%}",
                (f"Only {rate:.0%} of users report completing "
                 f"what they came to do. Based on {completion['total']} responses."),
                "Investigate session length, item count, and flow interruptions.",
                "Improve session completion rate.",
                f"{rate:.0%} completion",
                ["mandarin/scheduler.py", "mandarin/web/"],
            ))

    return findings


# ── Interaction Event Analyzer ──────────────────────────────────────────────

def analyze_interaction_events(conn) -> list:
    """Analyze interaction events for UX/engineering findings."""
    findings = []
    cutoff = (datetime.now(UTC) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    # Rage click hotspots
    rage_clicks = _safe_query_all(conn, """
        SELECT screen_name, element_id, COUNT(*) as cnt
        FROM pi_interaction_events
        WHERE event_type = 'rage_click'
          AND occurred_at >= ?
        GROUP BY screen_name, element_id
        HAVING cnt >= 3
        ORDER BY cnt DESC
        LIMIT 10
    """, (cutoff,))

    for rc in (rage_clicks or []):
        sev = "high" if rc["cnt"] >= 10 else "medium"
        elem = rc["element_id"] or "unknown element"
        screen = rc["screen_name"] or "unknown screen"
        findings.append(_finding(
            "ux", sev,
            f"Rage click hotspot: {screen} / {elem} ({rc['cnt']} events)",
            (f"{rc['cnt']} rage click events on this element in last 14 days. "
             f"Indicates element is unresponsive, confusing, or broken."),
            f"Inspect {screen}: check tap target size, responsiveness.",
            f"Fix rage click issue on {screen}.",
            f"{rc['cnt']} rage clicks",
            ["mandarin/web/"],
        ))

    # Session abandonment rate by screen
    total_sessions = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT session_id) FROM pi_interaction_events
        WHERE event_type = 'session_start' AND occurred_at >= ?
    """, (cutoff,), default=0)

    if total_sessions > 0:
        abandons = _safe_query_all(conn, """
            SELECT screen_name, COUNT(*) as abandon_count
            FROM pi_interaction_events
            WHERE event_type = 'session_abandon' AND occurred_at >= ?
            GROUP BY screen_name
            ORDER BY abandon_count DESC
            LIMIT 5
        """, (cutoff,))

        for ab in (abandons or []):
            abandon_rate = ab["abandon_count"] / total_sessions
            if abandon_rate >= 0.10:
                screen = ab["screen_name"] or "unknown"
                sev = "high" if abandon_rate >= 0.20 else "medium"
                findings.append(_finding(
                    "ux", sev,
                    f"Session abandonment at {screen}: {abandon_rate:.0%} of sessions",
                    (f"{ab['abandon_count']} sessions abandoned at {screen} "
                     f"({abandon_rate:.0%} of all sessions)."),
                    f"Review {screen} for confusing navigation or bugs.",
                    f"Fix session abandonment on {screen}.",
                    f"{abandon_rate:.0%} abandon rate",
                    ["mandarin/web/"],
                ))

    # Error encounter rate
    errors = _safe_query_all(conn, """
        SELECT error_code, COUNT(*) as cnt, COUNT(DISTINCT user_id) as users
        FROM pi_interaction_events
        WHERE event_type = 'error_encounter' AND occurred_at >= ?
        GROUP BY error_code
        ORDER BY cnt DESC
        LIMIT 10
    """, (cutoff,))

    for err in (errors or []):
        if err["cnt"] >= 5:
            sev = "critical" if (err["users"] or 0) >= 3 else "high"
            findings.append(_finding(
                "engineering", sev,
                f"Recurring error: {err['error_code']} ({err['cnt']} occurrences, {err['users']} users)",
                (f"Error {err['error_code']} encountered {err['cnt']} times "
                 f"by {err['users']} users in last 14 days."),
                f"Investigate and fix error {err['error_code']}.",
                f"Fix error {err['error_code']}.",
                f"{err['cnt']} errors",
                ["mandarin/"],
            ))

    # Screen time anomalies
    screen_times = _safe_query_all(conn, """
        SELECT screen_name, AVG(time_on_screen_ms) as avg_time, COUNT(*) as visits
        FROM pi_interaction_events
        WHERE event_type = 'screen_exit'
          AND time_on_screen_ms IS NOT NULL
          AND occurred_at >= ?
        GROUP BY screen_name
        HAVING visits >= 10
    """, (cutoff,))

    if screen_times and len(screen_times) > 1:
        overall_avg = sum(s["avg_time"] for s in screen_times) / len(screen_times)
        for screen in screen_times:
            if overall_avg > 0 and screen["avg_time"] > overall_avg * 2.5:
                ratio = screen["avg_time"] / overall_avg
                findings.append(_finding(
                    "ux", "medium",
                    (f"Excessive time on {screen['screen_name']}: "
                     f"{screen['avg_time'] / 1000:.1f}s avg ({ratio:.1f}x overall avg)"),
                    (f"Users spend {screen['avg_time'] / 1000:.1f}s on average on "
                     f"{screen['screen_name']}, {ratio:.1f}x longer than overall."),
                    f"Review {screen['screen_name']} for information overload or slow loading.",
                    f"Investigate slow screen {screen['screen_name']}.",
                    f"{ratio:.1f}x avg time",
                    ["mandarin/web/"],
                ))

    return findings


# ── Release Registration & Regression Detection ─────────────────────────────

def _snapshot_all_metrics(conn) -> dict:
    """Snapshot all measurable metrics. Returns {dimension: value}."""
    from .feedback_loops import _measure_current_metric
    from ._base import _VERIFICATION_WINDOWS

    metrics = {}
    for dim in _VERIFICATION_WINDOWS:
        val = _measure_current_metric(conn, dim, dim)
        if val is not None:
            metrics[dim] = val
    return metrics


def register_release(conn, app_version: str, release_notes=None,
                     changed_ux=False, changed_srs=False,
                     changed_content=False, changed_auth=False,
                     changed_api=False) -> str:
    """Register a new release and take a pre-release metric snapshot.

    Returns the release id.
    """
    release_id = str(uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    metrics = _snapshot_all_metrics(conn)

    try:
        conn.execute("""
            INSERT INTO pi_release_log
                (id, app_version, released_at, release_notes,
                 changed_ux, changed_srs, changed_content,
                 changed_auth, changed_api)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            release_id, app_version, now, release_notes,
            int(changed_ux), int(changed_srs), int(changed_content),
            int(changed_auth), int(changed_api),
        ))

        conn.execute("""
            INSERT INTO pi_release_metric_snapshots
                (id, release_id, snapshot_type, snapshotted_at, metrics_json)
            VALUES (?, ?, 'pre_release', ?, ?)
        """, (str(uuid4()), release_id, now, json.dumps(metrics)))

        conn.commit()
        return release_id
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to register release: %s", e)
        return None


def analyze_release_regressions(conn) -> list:
    """Analyze releases older than 48 hours for metric regressions.

    Returns list of finding dicts for any regressions detected.
    """
    findings = []
    pending = _safe_query_all(conn, """
        SELECT * FROM pi_release_log
        WHERE analysis_status = 'pending'
          AND released_at <= datetime('now', '-48 hours')
    """)

    if not pending:
        return findings

    for release in pending:
        # Take post-release snapshot
        post_metrics = _snapshot_all_metrics(conn)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn.execute("""
                INSERT INTO pi_release_metric_snapshots
                    (id, release_id, snapshot_type, snapshotted_at, metrics_json)
                VALUES (?, ?, 'post_release_48h', ?, ?)
            """, (str(uuid4()), release["id"], now, json.dumps(post_metrics)))
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

        # Get pre-release snapshot
        pre = _safe_query(conn, """
            SELECT metrics_json FROM pi_release_metric_snapshots
            WHERE release_id = ? AND snapshot_type = 'pre_release'
        """, (release["id"],))

        if not pre or not pre["metrics_json"]:
            try:
                conn.execute("""
                    UPDATE pi_release_log SET analysis_status = 'insufficient_data'
                    WHERE id = ?
                """, (release["id"],))
                conn.commit()
            except (sqlite3.OperationalError, sqlite3.Error):
                pass
            continue

        pre_metrics = json.loads(pre["metrics_json"])
        release_findings = []

        for dim, post_value in post_metrics.items():
            if post_value is None:
                continue
            pre_value = pre_metrics.get(dim)
            if pre_value is None or pre_value == 0:
                continue

            delta_pct = (post_value - pre_value) / pre_value

            worse_if_lower = dim in _WORSE_IF_LOWER
            is_regression = (
                (worse_if_lower and delta_pct < -0.10) or
                (not worse_if_lower and delta_pct > 0.10)
            )

            if is_regression:
                likely_cause = _infer_likely_cause(release, dim)
                version = release["app_version"]
                notes = release["release_notes"] or "Not provided"

                finding = _finding(
                    dim, "high",
                    (f"Post-release regression: {dim} "
                     f"{delta_pct * 100:+.1f}% after v{version}"),
                    (f"{dim} changed from {pre_value:.3f} to {post_value:.3f} "
                     f"({delta_pct * 100:+.1f}%) in the 48 hours following "
                     f"v{version}.\n\n"
                     f"Likely cause (heuristic): {likely_cause}\n\n"
                     f"Release notes: {notes}"),
                    f"Investigate v{version} for regression in {dim}.",
                    f"Fix regression in {dim} from v{version}.",
                    f"{delta_pct * 100:+.1f}%",
                    ["mandarin/"],
                )
                findings.append(finding)
                release_findings.append(finding.get("title", ""))

        status = "regression_detected" if release_findings else "clean"
        try:
            conn.execute("""
                UPDATE pi_release_log
                SET analysis_status = ?, analysis_run_at = ?,
                    generated_finding_ids = ?
                WHERE id = ?
            """, (status, now, json.dumps(release_findings), release["id"]))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

    return findings


def _infer_likely_cause(release, dimension):
    """Infer likely cause from release change flags and regressed dimension."""
    causes = []

    if release["changed_ux"] and dimension in ("ux", "frustration", "engagement"):
        causes.append("UX changes in this release")
    if release["changed_srs"] and dimension in ("srs_funnel", "retention", "drill_quality"):
        causes.append("SRS logic changes in this release")
    if release["changed_content"] and dimension in ("curriculum", "drill_quality"):
        causes.append("Content changes in this release")
    if release["changed_auth"] and dimension in ("onboarding", "engagement"):
        causes.append("Auth/session changes in this release")

    if not causes:
        causes.append("Unknown — no obvious change category match")

    return ", ".join(causes)


# ── UX Summary & Screen Health ──────────────────────────────────────────────

def get_ux_summary(conn, lookback_days=14) -> dict:
    """Aggregated UX signal: feedback trends, rage clicks, abandonment."""
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    # Session completion rate
    completion = _safe_query(conn, """
        SELECT AVG(CASE WHEN response_value = 1 THEN 1.0 ELSE 0.0 END) as rate,
               COUNT(*) as total
        FROM pi_ux_feedback
        WHERE feedback_type = 'session_completion' AND occurred_at >= ?
    """, (cutoff,))

    # Session frustration average
    frustration = _safe_query(conn, """
        SELECT AVG(response_value) as avg, COUNT(*) as total
        FROM pi_ux_feedback
        WHERE feedback_type = 'session_frustration' AND occurred_at >= ?
    """, (cutoff,))

    # Item difficulty distribution
    difficulty = _safe_query_all(conn, """
        SELECT response_value, COUNT(*) as cnt
        FROM pi_ux_feedback
        WHERE feedback_type = 'item_difficulty' AND occurred_at >= ?
          AND response_value IS NOT NULL
        GROUP BY response_value
    """, (cutoff,))

    diff_dist = {r["response_value"]: r["cnt"] for r in (difficulty or [])}
    diff_total = sum(diff_dist.values()) or 1

    # Rage click count
    rage_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_events
        WHERE event_type = 'rage_click' AND occurred_at >= ?
    """, (cutoff,), default=0)

    # Total events
    total_events = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_events WHERE occurred_at >= ?
    """, (cutoff,), default=0)

    # Error count
    error_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_events
        WHERE event_type = 'error_encounter' AND occurred_at >= ?
    """, (cutoff,), default=0)

    return {
        "lookback_days": lookback_days,
        "session_completion_rate": round(completion["rate"], 3) if completion and completion["rate"] else None,
        "session_completion_responses": completion["total"] if completion else 0,
        "session_frustration_avg": round(frustration["avg"], 3) if frustration and frustration["avg"] else None,
        "session_frustration_responses": frustration["total"] if frustration else 0,
        "item_difficulty": {
            "too_easy_pct": round(diff_dist.get(-1, 0) / diff_total, 3),
            "right_pct": round(diff_dist.get(0, 0) / diff_total, 3),
            "too_hard_pct": round(diff_dist.get(1, 0) / diff_total, 3),
            "total_responses": diff_total if difficulty else 0,
        },
        "rage_click_count": rage_count,
        "error_count": error_count,
        "total_interaction_events": total_events,
    }


def get_screen_health(conn, lookback_days=14) -> list:
    """Per-screen health: avg time, rage clicks, abandonment, friction score."""
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    screens = _safe_query_all(conn, """
        SELECT screen_name, COUNT(*) as visit_count
        FROM pi_interaction_events
        WHERE screen_name IS NOT NULL AND occurred_at >= ?
        GROUP BY screen_name
        HAVING visit_count >= 5
        ORDER BY visit_count DESC
    """, (cutoff,))

    if not screens:
        return []

    result = []
    for screen in screens:
        sn = screen["screen_name"]

        avg_time = _safe_scalar(conn, """
            SELECT AVG(time_on_screen_ms) FROM pi_interaction_events
            WHERE event_type = 'screen_exit' AND screen_name = ?
              AND time_on_screen_ms IS NOT NULL AND occurred_at >= ?
        """, (sn, cutoff), default=0)

        rage = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_interaction_events
            WHERE event_type = 'rage_click' AND screen_name = ? AND occurred_at >= ?
        """, (sn, cutoff), default=0)

        abandons = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_interaction_events
            WHERE event_type = 'session_abandon' AND screen_name = ? AND occurred_at >= ?
        """, (sn, cutoff), default=0)

        confusion = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_ux_feedback
            WHERE feedback_type = 'interface_confusion' AND screen_name = ? AND occurred_at >= ?
        """, (sn, cutoff), default=0)

        visits = screen["visit_count"]
        # Friction score: weighted composite
        friction = (
            (rage / max(visits, 1)) * 40 +
            (abandons / max(visits, 1)) * 30 +
            (confusion / max(visits, 1)) * 20 +
            min(1.0, (avg_time or 0) / 30000) * 10  # normalize to 30s max
        )

        result.append({
            "screen_name": sn,
            "visit_count": visits,
            "avg_time_ms": round(avg_time) if avg_time else 0,
            "rage_click_count": rage,
            "abandon_count": abandons,
            "confusion_count": confusion,
            "friction_score": round(friction, 2),
        })

    result.sort(key=lambda x: x["friction_score"], reverse=True)
    return result


def get_releases(conn) -> list:
    """Return all releases with analysis status."""
    rows = _safe_query_all(conn, """
        SELECT * FROM pi_release_log ORDER BY released_at DESC
    """)
    return [dict(r) for r in (rows or [])]


def get_release_analysis(conn, release_id: str) -> dict:
    """Full regression analysis for a specific release."""
    release = _safe_query(conn, """
        SELECT * FROM pi_release_log WHERE id = ?
    """, (release_id,))
    if not release:
        return None

    snapshots = _safe_query_all(conn, """
        SELECT * FROM pi_release_metric_snapshots
        WHERE release_id = ? ORDER BY snapshotted_at
    """, (release_id,))

    pre = None
    post = None
    for s in (snapshots or []):
        if s["snapshot_type"] == "pre_release":
            pre = json.loads(s["metrics_json"]) if s["metrics_json"] else {}
        elif s["snapshot_type"] == "post_release_48h":
            post = json.loads(s["metrics_json"]) if s["metrics_json"] else {}

    comparisons = []
    if pre and post:
        for dim in set(list(pre.keys()) + list(post.keys())):
            pre_val = pre.get(dim)
            post_val = post.get(dim)
            if pre_val is not None and post_val is not None and pre_val != 0:
                delta_pct = (post_val - pre_val) / pre_val
                comparisons.append({
                    "dimension": dim,
                    "pre_value": pre_val,
                    "post_value": post_val,
                    "delta_pct": round(delta_pct * 100, 1),
                    "is_regression": (
                        (dim in _WORSE_IF_LOWER and delta_pct < -0.10) or
                        (dim not in _WORSE_IF_LOWER and delta_pct > 0.10)
                    ),
                })

    return {
        "release": dict(release),
        "pre_metrics": pre,
        "post_metrics": post,
        "comparisons": comparisons,
        "regressions": [c for c in comparisons if c["is_regression"]],
    }


# Analyzers list for wiring into audit cycle
ANALYZERS = [
    analyze_ux_feedback,
    analyze_interaction_events,
]
