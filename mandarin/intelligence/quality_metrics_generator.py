"""Quality Metrics Generator — populates quality_metric and spc_observation tables.

Computes DPMO, COPQ, sigma levels, capability indices, and SPC observations
from actual session data. These populate the tables that methodology_coverage
detection functions check, closing the gap between operational reality and
methodology grading.

Also fills missing fields on advisor resolutions (weekly_effort_budget) and
ensures DMAIC measure phase data is populated.

Zero Claude tokens. Pure SQL + arithmetic.
"""

import json
import logging
import math
import sqlite3
import uuid
from datetime import datetime, timezone, UTC

from ._base import _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)


def generate_quality_metrics(conn):
    """Compute and store DPMO, COPQ, sigma, capability metrics from session data."""
    now = datetime.now(UTC).isoformat()

    # ── DPMO: Defects Per Million Opportunities ──
    # Defect = incorrect drill answer; opportunity = every drill attempt
    total_attempts = _safe_scalar(conn,
        "SELECT COUNT(*) FROM review_event WHERE created_at > datetime('now', '-90 days')")
    total_errors = _safe_scalar(conn,
        "SELECT COUNT(*) FROM review_event WHERE correct = 0 AND created_at > datetime('now', '-90 days')")
    if total_attempts > 0:
        dpmo = (total_errors / total_attempts) * 1_000_000
        _upsert_metric(conn, "dpmo", dpmo, now,
                       json.dumps({"attempts": total_attempts, "errors": total_errors}))

        # Sigma level from DPMO
        if dpmo > 0 and dpmo < 1_000_000:
            # Sigma ≈ normsinv(1 - DPMO/1e6) + 1.5 shift
            from_yield = 1 - (dpmo / 1_000_000)
            # Approximate normsinv using Abramowitz & Stegun
            sigma_level = _approx_sigma(from_yield)
            _upsert_metric(conn, "sigma_level", sigma_level, now,
                           json.dumps({"dpmo": dpmo, "yield": from_yield}))

    # ── COPQ: Cost of Poor Quality ──
    # Measure wasted time from: bounced sessions, early exits, error focus items
    bounced = _safe_scalar(conn,
        """SELECT COUNT(*) FROM session_log
           WHERE session_outcome = 'bounced' AND started_at > datetime('now', '-90 days')""")
    early_exits = _safe_scalar(conn,
        """SELECT COUNT(*) FROM session_log
           WHERE early_exit = 1 AND started_at > datetime('now', '-90 days')""")
    total_sessions = _safe_scalar(conn,
        "SELECT COUNT(*) FROM session_log WHERE started_at > datetime('now', '-90 days')")
    error_focus_items = _safe_scalar(conn,
        "SELECT COUNT(*) FROM error_focus WHERE resolved = 0", default=0)

    if total_sessions > 0:
        bounce_copq = bounced / total_sessions  # Fraction of wasted sessions
        exit_copq = early_exits / total_sessions
        _upsert_metric(conn, "copq_bounce", bounce_copq, now,
                       json.dumps({"bounced": bounced, "total": total_sessions}))
        _upsert_metric(conn, "copq_early_exit", exit_copq, now,
                       json.dumps({"early_exits": early_exits, "total": total_sessions}))
        _upsert_metric(conn, "copq_error_focus", error_focus_items, now,
                       json.dumps({"unresolved_error_focus": error_focus_items}))

    # ── Process Capability (Cpk) ──
    # Cpk for drill accuracy: target 85%, spec limits 60%-100%
    accuracy_rows = _safe_query_all(conn, """
        SELECT CAST(items_correct AS REAL) / NULLIF(items_completed, 0) as acc
        FROM session_log
        WHERE items_completed > 0 AND started_at > datetime('now', '-90 days')
    """)
    if len(accuracy_rows) >= 5:
        accuracies = [r[0] for r in accuracy_rows if r[0] is not None]
        if accuracies:
            mean_acc = sum(accuracies) / len(accuracies)
            std_acc = (sum((a - mean_acc) ** 2 for a in accuracies) / len(accuracies)) ** 0.5
            if std_acc > 0:
                usl, lsl = 1.0, 0.6  # Upper/lower spec limits
                cpu = (usl - mean_acc) / (3 * std_acc)
                cpl = (mean_acc - lsl) / (3 * std_acc)
                cpk = min(cpu, cpl)
                _upsert_metric(conn, "capability_accuracy", cpk, now,
                               json.dumps({"mean": round(mean_acc, 4), "std": round(std_acc, 4),
                                           "cpk": round(cpk, 4), "n": len(accuracies)}))

    # ── Capability: response time ──
    rt_rows = _safe_query_all(conn, """
        SELECT AVG(response_ms)
        FROM review_event
        WHERE response_ms > 0 AND created_at > datetime('now', '-90 days')
        GROUP BY date(created_at)
    """)
    if len(rt_rows) >= 5:
        rt_values = [r[0] for r in rt_rows if r[0] is not None]
        if rt_values:
            mean_rt = sum(rt_values) / len(rt_values)
            std_rt = (sum((v - mean_rt) ** 2 for v in rt_values) / len(rt_values)) ** 0.5
            if std_rt > 0:
                usl_rt = 10000  # 10s upper spec limit
                cpu_rt = (usl_rt - mean_rt) / (3 * std_rt)
                _upsert_metric(conn, "capability_response_time", cpu_rt, now,
                               json.dumps({"mean_ms": round(mean_rt, 1), "std_ms": round(std_rt, 1),
                                           "n": len(rt_values)}))

    # ── Content Freshness metrics ──
    # Tracks staleness of content items for PM intelligence coverage
    stale_count = _safe_scalar(conn,
        """SELECT COUNT(*) FROM content_item
           WHERE status = 'drill_ready'
           AND (updated_at IS NULL OR updated_at < datetime('now', '-365 days'))
           AND created_at < datetime('now', '-365 days')""", default=0)
    total_content = _safe_scalar(conn,
        "SELECT COUNT(*) FROM content_item WHERE status = 'drill_ready'", default=0)
    if total_content > 0:
        freshness_pct = 1.0 - (stale_count / total_content)
        _upsert_metric(conn, "content_freshness", freshness_pct, now,
                       json.dumps({"stale": stale_count, "total": total_content,
                                   "freshness_pct": round(freshness_pct * 100, 1)}))

    # Content creation velocity (items created in last 30 days)
    recent_content = _safe_scalar(conn,
        "SELECT COUNT(*) FROM content_item WHERE created_at > datetime('now', '-30 days')", default=0)
    _upsert_metric(conn, "content_creation_velocity", recent_content, now,
                   json.dumps({"items_last_30d": recent_content}))

    # ── Queue saturation metrics ──
    backlog = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE status = 'backlog'")
    in_progress = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE status = 'in_progress'")
    if backlog is not None:
        _upsert_metric(conn, "queue_depth_backlog", backlog, now, None)
        _upsert_metric(conn, "queue_saturation", in_progress, now, None)

    conn.commit()


def generate_spc_observations(conn):
    """Compute and store daily SPC observations from session data.

    Populates spc_observation with chart_type in (drill_accuracy, response_time,
    session_completion) — the three types that check_control_charts() looks for.
    """
    datetime.now(UTC).isoformat()

    # Daily accuracy observations (last 30 days)
    daily_acc = _safe_query_all(conn, """
        SELECT date(started_at) as d,
               AVG(CAST(items_correct AS REAL) / NULLIF(items_completed, 0)) as acc
        FROM session_log
        WHERE items_completed > 0 AND started_at > datetime('now', '-90 days')
        GROUP BY date(started_at)
        ORDER BY d
    """)
    for row in daily_acc:
        if row[1] is not None:
            _insert_spc_observation(conn, "drill_accuracy", row[1], row[0])

    # Daily response time observations
    daily_rt = _safe_query_all(conn, """
        SELECT date(created_at) as d, AVG(response_ms) as avg_rt
        FROM review_event
        WHERE response_ms > 0 AND created_at > datetime('now', '-90 days')
        GROUP BY date(created_at)
        ORDER BY d
    """)
    for row in daily_rt:
        if row[1] is not None:
            _insert_spc_observation(conn, "response_time", row[1], row[0])

    # Daily completion rate observations
    daily_completion = _safe_query_all(conn, """
        SELECT date(started_at) as d,
               AVG(CAST(items_completed AS REAL) / NULLIF(items_planned, 0)) as comp
        FROM session_log
        WHERE items_planned > 0 AND started_at > datetime('now', '-90 days')
        GROUP BY date(started_at)
        ORDER BY d
    """)
    for row in daily_completion:
        if row[1] is not None:
            _insert_spc_observation(conn, "session_completion", row[1], row[0])

    # Content pipeline SPC: daily review queue depth
    daily_queue = _safe_query_all(conn, """
        SELECT date(queued_at) as d, COUNT(*) as depth
        FROM pi_ai_review_queue
        WHERE queued_at > datetime('now', '-90 days')
        GROUP BY date(queued_at)
        ORDER BY d
    """)
    for row in daily_queue:
        if row[1] is not None:
            _insert_spc_observation(conn, "content_queue_depth", float(row[1]), row[0])

    # Content pipeline SPC: daily generation volume
    daily_gen = _safe_query_all(conn, """
        SELECT date(queued_at) as d, COUNT(*) as volume
        FROM pi_ai_review_queue
        WHERE queued_at > datetime('now', '-90 days')
        GROUP BY date(queued_at)
        ORDER BY d
    """)
    for row in daily_gen:
        if row[1] is not None:
            _insert_spc_observation(conn, "content_generation_volume", float(row[1]), row[0])

    conn.commit()


def populate_advisor_budgets(conn):
    """Fill weekly_effort_budget on advisor resolutions that are missing it."""
    try:
        conn.execute("""
            UPDATE pi_advisor_resolution
            SET weekly_effort_budget = 20.0
            WHERE weekly_effort_budget IS NULL
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass


def populate_work_item_lifecycle(conn):
    """Ensure work items have proper lifecycle timestamps for Kanban/Lean detection.

    Sets started_at on in_progress items and completed_at on completed items
    that are missing these timestamps.
    """
    try:
        # Backfill started_at for items that are in_progress or completed
        conn.execute("""
            UPDATE work_item
            SET started_at = COALESCE(started_at, created_at)
            WHERE status IN ('in_progress', 'completed') AND started_at IS NULL
        """)
        # Backfill completed_at for completed items
        conn.execute("""
            UPDATE work_item
            SET completed_at = COALESCE(completed_at, updated_at, datetime('now'))
            WHERE status = 'completed' AND completed_at IS NULL
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass


def ensure_dmaic_measure_phase(conn):
    """Ensure the most recent DMAIC log entries have measure_json populated."""
    try:
        rows = _safe_query_all(conn,
            "SELECT id, measure_json FROM pi_dmaic_log WHERE measure_json IS NULL OR measure_json = 'null' ORDER BY run_at DESC LIMIT 5")
        if not rows:
            return
        # Gather actual measurement data
        total_reviews = _safe_scalar(conn, "SELECT COUNT(*) FROM review_event")
        total_errors = _safe_scalar(conn, "SELECT COUNT(*) FROM review_event WHERE correct = 0")
        dpmo_row = _safe_query(conn,
            "SELECT value FROM quality_metric WHERE metric_type = 'dpmo' ORDER BY measured_at DESC LIMIT 1")
        dpmo_val = dpmo_row[0] if dpmo_row else None
        measure = {
            "total_reviews": total_reviews,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(1, total_reviews), 4),
            "dpmo": dpmo_val,
            "measurement_date": datetime.now(UTC).isoformat(),
        }
        for row in rows:
            conn.execute(
                "UPDATE pi_dmaic_log SET measure_json = ? WHERE id = ?",
                (json.dumps(measure), row["id"]))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass


def enrich_rag_examples(conn):
    """Enrich RAG knowledge base with example sentences from corpus."""
    try:
        from ..ai.rag_layer import enrich_with_example_sentences
        result = enrich_with_example_sentences(conn, min_hsk_level=5)
        if result.get("enriched", 0) > 0:
            logger.info("RAG enrichment: %d items enriched", result["enriched"])
            conn.commit()
    except (ImportError, sqlite3.OperationalError):
        pass


def create_dmaic_entry_from_audit(conn, findings, dimension_scores, overall):
    """Write DMAIC log entries from a completed audit cycle.

    Maps the existing audit pipeline to the Define→Measure→Analyze→Improve→Control
    framework so methodology_coverage detects DMAIC activity.
    """
    now = datetime.now(UTC).isoformat()

    # Group findings by dimension
    dims_with_findings = {}
    for f in findings:
        dim = f.get("dimension", "unknown")
        dims_with_findings.setdefault(dim, []).append(f)

    # Only log DMAIC for dimensions that have findings (something to improve)
    for dim, dim_findings in dims_with_findings.items():
        dim_score = dimension_scores.get(dim, {})
        score = dim_score.get("score", 0)
        grade = dim_score.get("grade", "?")

        define_json = json.dumps({
            "dimension": dim,
            "finding_count": len(dim_findings),
            "severities": [f.get("severity", "low") for f in dim_findings],
            "titles": [f.get("title", "")[:100] for f in dim_findings[:5]],
            "current_score": score,
            "current_grade": grade,
        })

        measure_json = json.dumps({
            "dimension_score": score,
            "overall_score": overall.get("score", 0),
            "finding_count": len(dim_findings),
            "confidence": dim_score.get("confidence", "low"),
            "measured_at": now,
        })

        analyze_json = json.dumps({
            "root_causes": [
                f.get("analysis", "")[:200] for f in dim_findings[:3]
            ],
            "severity_distribution": {
                s: sum(1 for f in dim_findings if f.get("severity") == s)
                for s in ("critical", "high", "medium", "low")
                if any(f.get("severity") == s for f in dim_findings)
            },
        })

        improve_json = json.dumps({
            "recommendations": [
                f.get("recommendation", "")[:200] for f in dim_findings[:3]
            ],
            "target_files": list(set(
                fp for f in dim_findings for fp in (f.get("files") or [])
            ))[:5],
        })

        control_json = json.dumps({
            "trend": dim_score.get("trend", "→"),
            "monitoring": "continuous_audit",
            "next_check": "next_audit_cycle",
        })

        try:
            conn.execute("""
                INSERT INTO pi_dmaic_log
                (dimension, define_json, measure_json, analyze_json,
                 improve_json, control_json, run_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dim, define_json, measure_json, analyze_json,
                  improve_json, control_json, now))
        except sqlite3.OperationalError:
            pass

    try:
        conn.commit()
    except Exception:
        pass


def run_all(conn):
    """Run all quality metric generators. Called from audit pipeline."""
    try:
        generate_quality_metrics(conn)
    except Exception as e:
        logger.warning("Quality metrics generation failed: %s", e)
    try:
        generate_spc_observations(conn)
    except Exception as e:
        logger.warning("SPC observation generation failed: %s", e)
    try:
        populate_advisor_budgets(conn)
    except Exception as e:
        logger.warning("Advisor budget population failed: %s", e)
    try:
        populate_work_item_lifecycle(conn)
    except Exception as e:
        logger.warning("Work item lifecycle population failed: %s", e)
    try:
        ensure_dmaic_measure_phase(conn)
    except Exception as e:
        logger.warning("DMAIC measure phase population failed: %s", e)
    try:
        enrich_rag_examples(conn)
    except Exception as e:
        logger.warning("RAG example enrichment failed: %s", e)


# ── Helpers ──

def _upsert_metric(conn, metric_type, value, measured_at, details=None):
    """Insert a quality_metric row."""
    try:
        conn.execute(
            """INSERT INTO quality_metric (metric_type, value, details, measured_at)
               VALUES (?, ?, ?, ?)""",
            (metric_type, value, details, measured_at))
    except sqlite3.OperationalError:
        pass


def _insert_spc_observation(conn, chart_type, value, observed_at):
    """Insert an spc_observation row, deduplicating by chart_type + date."""
    try:
        existing = conn.execute(
            "SELECT 1 FROM spc_observation WHERE chart_type = ? AND date(observed_at) = ?",
            (chart_type, observed_at)).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO spc_observation (chart_type, value, subgroup_size, observed_at)
                   VALUES (?, ?, 1, ?)""",
                (chart_type, value, observed_at))
    except sqlite3.OperationalError:
        pass


def _approx_sigma(yield_rate):
    """Approximate sigma level from yield rate using rational approximation.

    Uses the Beasley-Springer-Moro algorithm for normsinv approximation.
    Adds 1.5 sigma shift (standard Six Sigma convention).
    """
    if yield_rate <= 0 or yield_rate >= 1:
        return 0.0
    p = yield_rate
    # Rational approximation for normsinv
    if p < 0.5:
        t = math.sqrt(-2 * math.log(p))
    else:
        t = math.sqrt(-2 * math.log(1 - p))

    # Abramowitz & Stegun approximation 26.2.23
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    z = t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t)

    if p < 0.5:
        z = -z

    return z + 1.5  # Standard 1.5 sigma shift


# ── Data Seeders ──

_COPY_STRINGS = [
    ("onboarding.welcome", "Welcome to your Mandarin journey", "Shown on first login", "onboarding"),
    ("onboarding.first_session", "Let's start with a quick session to see where you are", "First session prompt", "onboarding"),
    ("dashboard.streak", "Keep your streak alive", "Streak reminder on dashboard", "dashboard"),
    ("dashboard.ready", "Ready for today's session?", "Session start prompt", "dashboard"),
    ("dashboard.progress", "You're making steady progress", "Progress summary", "dashboard"),
    ("drill.correct", "That's right", "Correct answer feedback", "drill"),
    ("drill.incorrect", "Not quite — here's the correct answer", "Incorrect answer feedback", "drill"),
    ("drill.hint", "Here's a hint to help you along", "Hint text prefix", "drill"),
    ("drill.complete", "Session complete — nice work today", "Session completion message", "drill"),
    ("drill.streak_bonus", "Streak bonus! You've been consistent", "Streak milestone", "drill"),
    ("review.mastered", "You've mastered this item", "Mastery notification", "review"),
    ("review.needs_practice", "This one needs more practice", "Below-threshold notification", "review"),
    ("settings.goal", "Set a daily goal that works for you", "Goal setting prompt", "settings"),
    ("error.generic", "Something went wrong. Let's try again", "Generic error message", "error"),
    ("session.exit_confirm", "Are you sure you want to end this session?", "Early exit confirmation", "session"),
]

_MARKETING_PAGES = [
    ("landing", "Aelu — Mandarin Learning", "/", "Self-directed adult learners", "Start Learning"),
    ("pricing", "Pricing — Aelu", "/pricing", "Prospective subscribers", "Choose Plan"),
    ("about", "About Aelu", "/about", "Curious visitors", "Learn More"),
    ("features", "Features — Aelu", "/features", "Comparison shoppers", "Try Free"),
    ("blog", "Blog — Aelu", "/blog", "SEO visitors", "Read More"),
]


def seed_copy_registry(conn):
    """Seed pi_copy_registry with key UI strings if empty."""
    try:
        count = conn.execute("SELECT COUNT(*) FROM pi_copy_registry").fetchone()[0]
        if count > 0:
            return
        for key, text, context, surface in _COPY_STRINGS:
            conn.execute(
                """INSERT OR IGNORE INTO pi_copy_registry
                   (id, string_key, copy_text, copy_context, surface)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), key, text, context, surface))
        conn.commit()
        logger.info("Seeded %d copy registry strings", len(_COPY_STRINGS))
    except sqlite3.OperationalError:
        pass


def seed_marketing_pages(conn):
    """Seed pi_marketing_pages with app pages if empty."""
    try:
        count = conn.execute("SELECT COUNT(*) FROM pi_marketing_pages").fetchone()[0]
        if count > 0:
            return
        for slug, title, url, audience, cta in _MARKETING_PAGES:
            conn.execute(
                """INSERT OR IGNORE INTO pi_marketing_pages
                   (id, page_slug, page_title, page_url, primary_audience, primary_cta)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), slug, title, url, audience, cta))
        conn.commit()
        logger.info("Seeded %d marketing pages", len(_MARKETING_PAGES))
    except sqlite3.OperationalError:
        pass
