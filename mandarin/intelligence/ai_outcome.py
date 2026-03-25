"""AI Outcome Measurement Analyzer.

Measures whether AI components are net positive across every dimension:
learning impact, quality, delight, stickiness, performance, security,
UX, pedagogical integrity, commercial, and solo dev sustainability.

Adapted to Aelu schema: review_event, content_item, session_log, error_log.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)

COMPONENTS = [
    'difficulty_model', 'fuzzy_dedup', 'drill_generation',
    'error_explanation', 'reading_content',
]

DIMENSION_WEIGHTS = {
    'pedagogical_integrity': 3.0,
    'learning_impact': 2.5,
    'performance_engineering': 2.0,
    'sustainability': 2.0,
    'security': 2.0,
    'delight_stickiness': 1.5,
    'ux_design': 1.0,
    'commercial': 0.5,
}

STATUS_SCORES = {
    'healthy': 1.0,
    'degraded': 0.5,
    'critical': 0.0,
    'insufficient_data': 0.6,
    'not_applicable': None,
}


# ── Dimension 1: Learning Impact ──────────────────────────────────────

def measure_learning_impact(conn, component: str, window_days: int = 30) -> list[dict]:
    """Measure whether component accelerates actual learning."""
    measurements = []

    if component == 'difficulty_model':
        # Model-scheduled vs static-scheduled accuracy comparison
        model_rows = conn.execute("""
            SELECT re.correct, dp.difficulty_class, dp.predicted_accuracy
            FROM review_event re
            JOIN pi_difficulty_predictions dp ON dp.review_event_id = re.id
            WHERE re.created_at >= datetime('now', ?)
            AND dp.model_available = 1
        """, (f'-{window_days} days',)).fetchall()

        static_rows = conn.execute("""
            SELECT re.correct
            FROM review_event re
            LEFT JOIN pi_difficulty_predictions dp ON dp.review_event_id = re.id
            WHERE re.created_at >= datetime('now', ?)
            AND (dp.id IS NULL OR dp.model_available = 0)
        """, (f'-{window_days} days',)).fetchall()

        if len(model_rows) >= 30 and len(static_rows) >= 30:
            model_acc = sum(r['correct'] for r in model_rows) / len(model_rows)
            static_acc = sum(r['correct'] for r in static_rows) / len(static_rows)
            delta = model_acc - static_acc

            in_zone = [r for r in model_rows if r['difficulty_class'] == 'in_zone']
            zone_rate = len(in_zone) / len(model_rows) if model_rows else 0

            measurements.append({
                'metric_name': 'model_vs_static_accuracy_delta',
                'metric_value': delta,
                'metric_unit': 'rate',
                'threshold_low': -0.02,
                'threshold_high': 0.05,
                'status': 'healthy' if delta >= -0.02 else 'degraded',
                'evidence': (
                    f'Model-scheduled: {model_acc:.1%} accuracy. '
                    f'Static: {static_acc:.1%}. Delta: {delta:+.1%}. '
                    f'Zone hit rate: {zone_rate:.1%}.'
                ),
                'sample_size': len(model_rows) + len(static_rows),
                'confidence': min(1.0, (len(model_rows) + len(static_rows)) / 200),
            })
        else:
            measurements.append({
                'metric_name': 'model_vs_static_accuracy_delta',
                'metric_value': None,
                'metric_unit': 'rate',
                'threshold_low': -0.02,
                'threshold_high': 0.05,
                'status': 'insufficient_data',
                'evidence': (
                    f'Model-scheduled: {len(model_rows)} samples. '
                    f'Static: {len(static_rows)} samples. Need 30+ each.'
                ),
                'sample_size': len(model_rows) + len(static_rows),
                'confidence': 0.0,
            })

    elif component == 'drill_generation':
        # AI-generated vs manual items accuracy comparison
        ai_items = conn.execute("""
            SELECT ci.id, AVG(re.correct) as accuracy, COUNT(re.id) as reviews
            FROM content_item ci
            JOIN review_event re ON re.content_item_id = ci.id
            WHERE ci.source = 'ai_generated'
            AND ci.created_at >= datetime('now', ?)
            GROUP BY ci.id
        """, (f'-{window_days} days',)).fetchall()

        manual_items = conn.execute("""
            SELECT ci.id, AVG(re.correct) as accuracy, COUNT(re.id) as reviews
            FROM content_item ci
            JOIN review_event re ON re.content_item_id = ci.id
            WHERE (ci.source IS NULL OR ci.source != 'ai_generated')
            AND re.created_at >= datetime('now', ?)
            GROUP BY ci.id
            LIMIT 200
        """, (f'-{window_days} days',)).fetchall()

        if len(ai_items) >= 10 and len(manual_items) >= 10:
            ai_avg = sum(r['accuracy'] for r in ai_items) / len(ai_items)
            manual_avg = sum(r['accuracy'] for r in manual_items) / len(manual_items)
            delta = ai_avg - manual_avg

            measurements.append({
                'metric_name': 'ai_vs_manual_accuracy_delta',
                'metric_value': delta,
                'metric_unit': 'rate',
                'threshold_low': -0.10,
                'threshold_high': 0.05,
                'status': 'healthy' if delta >= -0.10 else 'degraded',
                'evidence': (
                    f'AI items: {ai_avg:.1%} accuracy ({len(ai_items)} items). '
                    f'Manual: {manual_avg:.1%} ({len(manual_items)} items). '
                    f'Delta: {delta:+.1%}.'
                ),
                'sample_size': len(ai_items) + len(manual_items),
                'confidence': min(1.0, min(len(ai_items), len(manual_items)) / 20),
            })
        else:
            measurements.append({
                'metric_name': 'ai_vs_manual_accuracy_delta',
                'metric_value': None,
                'metric_unit': 'rate',
                'threshold_low': -0.10,
                'threshold_high': 0.05,
                'status': 'insufficient_data',
                'evidence': f'AI items: {len(ai_items)}, manual: {len(manual_items)}. Need 10+ each.',
                'sample_size': len(ai_items) + len(manual_items),
                'confidence': 0.0,
            })

    elif component == 'error_explanation':
        # Next-exposure accuracy: explained vs not-explained misses
        explained = conn.execute("""
            SELECT r2.correct
            FROM review_event r1
            JOIN review_event r2 ON (
                r2.content_item_id = r1.content_item_id
                AND r2.user_id = r1.user_id
                AND r2.created_at > r1.created_at
            )
            WHERE r1.explanation_shown = 1
            AND r1.correct = 0
            AND NOT EXISTS (
                SELECT 1 FROM review_event r3
                WHERE r3.content_item_id = r1.content_item_id
                AND r3.user_id = r1.user_id
                AND r3.created_at > r1.created_at
                AND r3.created_at < r2.created_at
            )
            AND r1.created_at >= datetime('now', ?)
        """, (f'-{window_days} days',)).fetchall()

        not_explained = conn.execute("""
            SELECT r2.correct
            FROM review_event r1
            JOIN review_event r2 ON (
                r2.content_item_id = r1.content_item_id
                AND r2.user_id = r1.user_id
                AND r2.created_at > r1.created_at
            )
            WHERE (r1.explanation_shown = 0 OR r1.explanation_shown IS NULL)
            AND r1.correct = 0
            AND NOT EXISTS (
                SELECT 1 FROM review_event r3
                WHERE r3.content_item_id = r1.content_item_id
                AND r3.user_id = r1.user_id
                AND r3.created_at > r1.created_at
                AND r3.created_at < r2.created_at
            )
            AND r1.created_at >= datetime('now', ?)
        """, (f'-{window_days} days',)).fetchall()

        if len(explained) >= 20 and len(not_explained) >= 20:
            exp_acc = sum(r['correct'] for r in explained) / len(explained)
            no_exp_acc = sum(r['correct'] for r in not_explained) / len(not_explained)
            delta = exp_acc - no_exp_acc

            measurements.append({
                'metric_name': 'explanation_next_exposure_accuracy_delta',
                'metric_value': delta,
                'metric_unit': 'rate',
                'threshold_low': -0.02,
                'threshold_high': 0.08,
                'status': 'healthy' if delta >= 0 else ('degraded' if delta >= -0.02 else 'critical'),
                'evidence': (
                    f'Post-explanation: {exp_acc:.1%}. Without: {no_exp_acc:.1%}. '
                    f'Delta: {delta:+.1%} ({len(explained)} vs {len(not_explained)} samples).'
                ),
                'sample_size': len(explained) + len(not_explained),
                'confidence': min(1.0, min(len(explained), len(not_explained)) / 40),
            })
        else:
            measurements.append({
                'metric_name': 'explanation_next_exposure_accuracy_delta',
                'metric_value': None,
                'metric_unit': 'rate',
                'threshold_low': -0.02,
                'threshold_high': 0.08,
                'status': 'insufficient_data',
                'evidence': f'Explained: {len(explained)}, not explained: {len(not_explained)}. Need 20+ each.',
                'sample_size': len(explained) + len(not_explained),
                'confidence': 0.0,
            })

    return measurements


# ── Dimension 2: Session Delight + Stickiness ─────────────────────────

def measure_delight_and_stickiness(conn, component: str, window_days: int = 30) -> list[dict]:
    """Session completion, return rate, frequency trends."""
    measurements = []

    # Session completion rate by AI load
    completion = conn.execute("""
        SELECT
            CASE
                WHEN ai_count * 1.0 / NULLIF(total_count, 0) > 0.5
                THEN 'high_ai' ELSE 'low_ai'
            END as ai_load,
            AVG(CASE WHEN items_completed >= items_planned THEN 1.0 ELSE 0.0 END) as completion_rate,
            COUNT(*) as session_count
        FROM (
            SELECT sl.id, sl.items_completed, sl.items_planned,
                   COUNT(CASE WHEN ci.source = 'ai_generated' THEN 1 END) as ai_count,
                   COUNT(re.id) as total_count
            FROM session_log sl
            JOIN review_event re ON re.session_id = sl.id
            JOIN content_item ci ON ci.id = re.content_item_id
            WHERE sl.started_at >= datetime('now', ?)
            GROUP BY sl.id
        ) summary
        GROUP BY ai_load
    """, (f'-{window_days} days',)).fetchall()

    for row in completion:
        label = row['ai_load']
        rate = row['completion_rate'] or 0
        measurements.append({
            'metric_name': f'session_completion_rate_{label}',
            'metric_value': rate,
            'metric_unit': 'rate',
            'threshold_low': 0.70,
            'threshold_high': None,
            'status': 'healthy' if rate >= 0.70 else 'degraded',
            'evidence': f'{label}: {rate:.1%} completion ({row["session_count"]} sessions)',
            'sample_size': row['session_count'],
            'confidence': min(1.0, row['session_count'] / 20),
        })

    # Return within 24h rate
    return_rate = conn.execute("""
        SELECT AVG(returned) as rate, COUNT(*) as cnt FROM (
            SELECT s1.id,
                   CASE WHEN MIN(s2.started_at) IS NOT NULL THEN 1 ELSE 0 END as returned
            FROM session_log s1
            LEFT JOIN session_log s2 ON (
                s2.started_at > s1.started_at
                AND s2.started_at <= datetime(s1.started_at, '+24 hours')
                AND s2.id != s1.id
                AND s2.user_id = s1.user_id
            )
            WHERE s1.started_at >= datetime('now', ?)
            GROUP BY s1.id
        )
    """, (f'-{window_days} days',)).fetchone()

    if return_rate and (return_rate['cnt'] or 0) >= 10:
        rate = return_rate['rate'] or 0
        measurements.append({
            'metric_name': 'return_within_24h_rate',
            'metric_value': rate,
            'metric_unit': 'rate',
            'threshold_low': 0.40,
            'threshold_high': None,
            'status': 'healthy' if rate >= 0.40 else 'degraded',
            'evidence': f'{rate:.1%} sessions followed by another within 24h ({return_rate["cnt"]} sessions)',
            'sample_size': return_rate['cnt'],
            'confidence': min(1.0, return_rate['cnt'] / 30),
        })

    return measurements


# ── Dimension 3: Performance + Engineering ────────────────────────────

LATENCY_THRESHOLDS = {
    'difficulty_model': {'p50': 10, 'p95': 50},
    'fuzzy_dedup': {'p50': 500, 'p95': 2000},
    'drill_generation': {'p50': 8000, 'p95': 25000},
    'error_explanation': {'p50': 5000, 'p95': 15000},
    'reading_content': {'p50': 15000, 'p95': 40000},
}


def measure_performance_and_engineering(conn, component: str, window_days: int = 14) -> list[dict]:
    """Latency, error rates, fallback rates, training health."""
    measurements = []

    thresholds = LATENCY_THRESHOLDS.get(component, {})
    if thresholds:
        latencies = conn.execute("""
            SELECT latency_ms FROM pi_ai_latency_log
            WHERE component = ? AND occurred_at >= datetime('now', ?)
            AND succeeded = 1
            ORDER BY latency_ms
        """, (component, f'-{window_days} days')).fetchall()

        if latencies:
            all_ms = sorted(r['latency_ms'] for r in latencies)
            p50 = all_ms[len(all_ms) // 2]
            p95 = all_ms[int(len(all_ms) * 0.95)]

            for pct, val, key in [(50, p50, 'p50'), (95, p95, 'p95')]:
                thresh = thresholds[key]
                measurements.append({
                    'metric_name': f'latency_p{pct}_ms',
                    'metric_value': val,
                    'metric_unit': 'ms',
                    'threshold_low': None,
                    'threshold_high': thresh,
                    'status': 'healthy' if val <= thresh else ('degraded' if val <= thresh * 2 else 'critical'),
                    'evidence': f'{component} p{pct}: {val}ms (threshold: {thresh}ms, {len(latencies)} samples)',
                    'sample_size': len(latencies),
                    'confidence': min(1.0, len(latencies) / 20),
                })

    # Error + fallback rates
    ops = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN succeeded=0 THEN 1 ELSE 0 END) as failures,
               SUM(CASE WHEN used_fallback=1 THEN 1 ELSE 0 END) as fallbacks
        FROM pi_ai_latency_log
        WHERE component = ? AND occurred_at >= datetime('now', ?)
    """, (component, f'-{window_days} days')).fetchone()

    if ops and (ops['total'] or 0) >= 5:
        failure_rate = (ops['failures'] or 0) / ops['total']
        measurements.append({
            'metric_name': 'error_rate',
            'metric_value': failure_rate,
            'metric_unit': 'rate',
            'threshold_low': None,
            'threshold_high': 0.05,
            'status': 'healthy' if failure_rate <= 0.05 else ('degraded' if failure_rate <= 0.15 else 'critical'),
            'evidence': f'{failure_rate:.1%} failure rate ({ops["failures"]}/{ops["total"]})',
            'sample_size': ops['total'],
            'confidence': min(1.0, ops['total'] / 20),
        })

    # Training staleness (difficulty model only)
    if component == 'difficulty_model':
        last_train = conn.execute("""
            SELECT trained_at FROM pi_ml_model_versions
            WHERE model_name = 'difficulty_model' AND active = 1
            ORDER BY trained_at DESC LIMIT 1
        """).fetchone()

        if last_train and last_train['trained_at']:
            try:
                trained_dt = datetime.fromisoformat(last_train['trained_at'])
                days_since = (datetime.now(UTC) - trained_dt).days
                if days_since > 14:
                    measurements.append({
                        'metric_name': 'days_since_model_retrain',
                        'metric_value': days_since,
                        'metric_unit': 'days',
                        'threshold_low': None,
                        'threshold_high': 14,
                        'status': 'degraded',
                        'evidence': f'Model last retrained {days_since} days ago. Weekly retraining recommended.',
                        'sample_size': None,
                        'confidence': 0.95,
                    })
            except (ValueError, TypeError):
                pass

    return measurements


# ── Dimension 4: Security ─────────────────────────────────────────────

def measure_security(conn, component: str) -> list[dict]:
    """Security posture: prompt injection, content anomalies, network exposure."""
    measurements = []

    if component in ('drill_generation', 'error_explanation', 'reading_content'):
        # Suspicious encounter content (prompt injection candidates)
        suspicious = conn.execute("""
            SELECT COUNT(*) as cnt FROM vocab_encounter
            WHERE drill_generation_status = 'pending'
            AND (
                hanzi LIKE '%ignore%' OR hanzi LIKE '%system%'
                OR LENGTH(hanzi) > 50
            )
        """).fetchone()
        cnt = suspicious['cnt'] if suspicious else 0

        if cnt > 0:
            measurements.append({
                'metric_name': 'suspicious_encounter_count',
                'metric_value': cnt,
                'metric_unit': 'count',
                'threshold_low': None,
                'threshold_high': 0,
                'status': 'critical',
                'evidence': f'{cnt} pending encounter(s) contain suspicious content.',
                'sample_size': cnt,
                'confidence': 0.70,
            })

        # Unresolved security events
        sec_events = conn.execute("""
            SELECT COUNT(*) as cnt FROM pi_ai_security_events
            WHERE component = ? AND resolved = 0
            AND occurred_at >= datetime('now', '-7 days')
        """, (component,)).fetchone()
        sec_cnt = (sec_events['cnt'] if sec_events else 0) or 0

        measurements.append({
            'metric_name': 'unresolved_security_events',
            'metric_value': sec_cnt,
            'metric_unit': 'count',
            'threshold_low': None,
            'threshold_high': 0,
            'status': 'critical' if sec_cnt > 0 else 'healthy',
            'evidence': (
                f'{sec_cnt} unresolved security events in last 7 days.'
                if sec_cnt > 0 else 'No security anomalies detected.'
            ),
            'sample_size': None,
            'confidence': 0.90,
        })

    return measurements


# ── Dimension 5: UX/Design ────────────────────────────────────────────

def measure_ux_and_design(conn, component: str, window_days: int = 14) -> list[dict]:
    """Review queue backlog, rejection categories."""
    measurements = []

    # Review queue backlog
    queue = conn.execute("""
        SELECT COUNT(*) as pending,
               AVG(JULIANDAY('now') - JULIANDAY(queued_at)) as avg_age_days
        FROM pi_ai_review_queue WHERE reviewed_at IS NULL
    """).fetchone()

    if queue:
        pending = queue['pending'] or 0
        avg_age = queue['avg_age_days'] or 0

        status = 'healthy'
        if pending > 20:
            status = 'critical'
        elif pending > 10 or avg_age > 7:
            status = 'degraded'

        measurements.append({
            'metric_name': 'review_queue_backlog',
            'metric_value': pending,
            'metric_unit': 'count',
            'threshold_low': None,
            'threshold_high': 10,
            'status': status,
            'evidence': f'{pending} items pending review. Avg age: {avg_age:.1f} days.',
            'sample_size': pending,
            'confidence': 0.95,
        })

    # Rejection categories
    rejections = conn.execute("""
        SELECT rejection_category, COUNT(*) as cnt
        FROM pi_ai_review_outcomes
        WHERE reviewed_at >= datetime('now', ?)
        AND rejection_category IS NOT NULL
        GROUP BY rejection_category ORDER BY cnt DESC
    """, (f'-{window_days} days',)).fetchall()

    if rejections:
        sum(r['cnt'] for r in rejections
                        if r['rejection_category'] in ('formatting_error', 'awkward_chinese'))
        accuracy_cnt = sum(r['cnt'] for r in rejections
                          if r['rejection_category'] in ('accuracy_error', 'tone_error'))

        if accuracy_cnt > 0:
            measurements.append({
                'metric_name': 'accuracy_rejection_count',
                'metric_value': accuracy_cnt,
                'metric_unit': 'count',
                'threshold_low': None,
                'threshold_high': 1,
                'status': 'critical' if accuracy_cnt > 1 else 'degraded',
                'evidence': f'{accuracy_cnt} items rejected for accuracy/tone errors.',
                'sample_size': None,
                'confidence': 0.95,
            })

    return measurements


# ── Dimension 6: Pedagogical Integrity ────────────────────────────────

def measure_pedagogical_integrity(conn, component: str) -> list[dict]:
    """Wrong tones/characters actively harm acquisition."""
    measurements = []

    total_reviewed = conn.execute("""
        SELECT COUNT(*) as cnt FROM pi_ai_review_outcomes WHERE component = ?
    """, (component,)).fetchone()
    total = (total_reviewed['cnt'] if total_reviewed else 0) or 0

    accuracy_rej = conn.execute("""
        SELECT COUNT(*) as cnt FROM pi_ai_review_outcomes
        WHERE component = ?
        AND rejection_category IN ('accuracy_error', 'tone_error', 'difficulty_mismatch')
    """, (component,)).fetchone()
    rej_cnt = (accuracy_rej['cnt'] if accuracy_rej else 0) or 0

    if total >= 10:
        rate = rej_cnt / total
        measurements.append({
            'metric_name': 'pedagogical_accuracy_rejection_rate',
            'metric_value': rate,
            'metric_unit': 'rate',
            'threshold_low': None,
            'threshold_high': 0.05,
            'status': 'healthy' if rate <= 0.05 else ('degraded' if rate <= 0.10 else 'critical'),
            'evidence': f'{rate:.1%} rejected for accuracy errors ({rej_cnt}/{total})',
            'sample_size': total,
            'confidence': min(1.0, total / 20),
        })
    else:
        measurements.append({
            'metric_name': 'pedagogical_accuracy_rejection_rate',
            'metric_value': None,
            'metric_unit': 'rate',
            'threshold_low': None,
            'threshold_high': 0.05,
            'status': 'insufficient_data',
            'evidence': f'Only {total} items reviewed for {component}. Need 10+.',
            'sample_size': total,
            'confidence': 0.0,
        })

    return measurements


# ── Dimension 7: Commercial ───────────────────────────────────────────

def measure_commercial_value(conn, component: str) -> list[dict]:
    """Before/after experiment presence and verdict."""
    measurements = []

    experiment = conn.execute("""
        SELECT * FROM pi_ai_component_experiments
        WHERE component = ? ORDER BY activated_at DESC LIMIT 1
    """, (component,)).fetchone()

    if not experiment:
        measurements.append({
            'metric_name': 'baseline_experiment_present',
            'metric_value': 0,
            'metric_unit': 'boolean',
            'threshold_low': None,
            'threshold_high': None,
            'status': 'degraded',
            'evidence': f'No before/after experiment for {component}. Cannot demonstrate ROI.',
            'sample_size': None,
            'confidence': 0.95,
        })
    elif not experiment['verdict']:
        measurements.append({
            'metric_name': 'experiment_verdict_computed',
            'metric_value': 0,
            'metric_unit': 'boolean',
            'threshold_low': None,
            'threshold_high': None,
            'status': 'degraded',
            'evidence': f'Experiment exists for {component} but verdict not yet computed.',
            'sample_size': None,
            'confidence': 0.80,
        })
    else:
        status_map = {
            'net_positive': 'healthy', 'net_neutral': 'degraded',
            'net_negative': 'critical', 'insufficient_data': 'insufficient_data',
        }
        measurements.append({
            'metric_name': 'component_roi_verdict',
            'metric_value': 1 if experiment['verdict'] == 'net_positive' else 0,
            'metric_unit': 'boolean',
            'threshold_low': None,
            'threshold_high': None,
            'status': status_map.get(experiment['verdict'], 'degraded'),
            'evidence': f'{component} verdict: {experiment["verdict"]}.',
            'sample_size': None,
            'confidence': 0.85,
        })

    return measurements


# ── Dimension 8: Solo Dev Sustainability ──────────────────────────────

def measure_sustainability(conn, window_days: int = 14) -> list[dict]:
    """Maintenance burden of the AI portfolio."""
    measurements = []

    # Review throughput vs generation rate
    pending = conn.execute(
        "SELECT COUNT(*) as cnt FROM pi_ai_review_queue WHERE reviewed_at IS NULL"
    ).fetchone()
    pending_cnt = (pending['cnt'] if pending else 0) or 0

    gen_rate = conn.execute("""
        SELECT COUNT(*) * 1.0 / ? as per_day
        FROM pi_ai_generation_log
        WHERE occurred_at >= datetime('now', ?) AND success = 1
        AND task_type != 'error_explanation'
    """, (window_days, f'-{window_days} days')).fetchone()
    gen_per_day = (gen_rate['per_day'] if gen_rate else 0) or 0

    review_rate = conn.execute("""
        SELECT COUNT(*) * 1.0 / ? as per_day
        FROM pi_ai_review_outcomes
        WHERE reviewed_at >= datetime('now', ?)
    """, (window_days, f'-{window_days} days')).fetchone()
    rev_per_day = (review_rate['per_day'] if review_rate else 0) or 0

    accumulation = gen_per_day - rev_per_day
    status = 'healthy'
    if accumulation > 2:
        status = 'critical'
    elif accumulation > 0.5:
        status = 'degraded'

    measurements.append({
        'metric_name': 'review_queue_accumulation_rate_per_day',
        'metric_value': round(accumulation, 2),
        'metric_unit': 'count',
        'threshold_low': None,
        'threshold_high': 0.5,
        'status': status,
        'evidence': (
            f'Generation: {gen_per_day:.1f}/day. Review: {rev_per_day:.1f}/day. '
            f'Net: {accumulation:+.1f}/day. Backlog: {pending_cnt}.'
        ),
        'sample_size': None,
        'confidence': min(1.0, window_days / 14),
    })

    # Pipeline failures
    failures = conn.execute("""
        SELECT COUNT(*) as cnt FROM pi_ml_pipeline_runs
        WHERE results_json LIKE '%"status": "error"%'
        AND run_at >= datetime('now', ?)
    """, (f'-{window_days} days',)).fetchone()
    fail_cnt = (failures['cnt'] if failures else 0) or 0

    if fail_cnt > 0:
        measurements.append({
            'metric_name': 'training_pipeline_failures',
            'metric_value': fail_cnt,
            'metric_unit': 'count',
            'threshold_low': None,
            'threshold_high': 1,
            'status': 'degraded' if fail_cnt <= 2 else 'critical',
            'evidence': f'{fail_cnt} pipeline failure(s) in {window_days} days.',
            'sample_size': None,
            'confidence': 0.90,
        })

    # Estimated maintenance hours
    est_queue_hrs = pending_cnt / 30  # ~2 min/item
    est_pipeline_hrs = fail_cnt * 0.5
    total_hrs = est_queue_hrs + est_pipeline_hrs

    measurements.append({
        'metric_name': 'estimated_weekly_ai_maintenance_hours',
        'metric_value': round(total_hrs, 1),
        'metric_unit': 'hours',
        'threshold_low': None,
        'threshold_high': 3.0,
        'status': 'healthy' if total_hrs <= 3.0 else ('degraded' if total_hrs <= 6.0 else 'critical'),
        'evidence': f'Estimated {total_hrs:.1f} hrs/week: {est_queue_hrs:.1f} review + {est_pipeline_hrs:.1f} pipeline.',
        'sample_size': None,
        'confidence': 0.55,
    })

    return measurements


# ── Portfolio Synthesis ────────────────────────────────────────────────

DIMENSION_FUNCTIONS = {
    'learning_impact': measure_learning_impact,
    'delight_stickiness': measure_delight_and_stickiness,
    'performance_engineering': measure_performance_and_engineering,
    'security': measure_security,
    'ux_design': measure_ux_and_design,
    'pedagogical_integrity': measure_pedagogical_integrity,
    'commercial': measure_commercial_value,
}


def compute_ai_portfolio_verdict(conn, audit_cycle_id=None) -> dict:
    """Is the AI portfolio net positive? Runs all measurements, synthesizes verdict."""
    all_measurements = []
    component_verdicts = {}
    dimension_scores = {d: [] for d in list(DIMENSION_FUNCTIONS) + ['sustainability']}

    for component in COMPONENTS:
        comp_measurements = []

        for dimension, fn in DIMENSION_FUNCTIONS.items():
            try:
                ms = fn(conn, component)
                for m in ms:
                    m['component'] = component
                    m['dimension'] = dimension
                    all_measurements.append(m)
                    comp_measurements.append(m)
                    score = STATUS_SCORES.get(m['status'])
                    if score is not None:
                        dimension_scores[dimension].append(score)
            except Exception as e:
                all_measurements.append({
                    'component': component, 'dimension': dimension,
                    'metric_name': 'measurement_error', 'status': 'degraded',
                    'evidence': f'Measurement failed: {e}', 'confidence': 0.0,
                })

        # Component verdict
        comp_scores, comp_weights = [], []
        for m in comp_measurements:
            score = STATUS_SCORES.get(m['status'])
            if score is not None:
                w = DIMENSION_WEIGHTS.get(m['dimension'], 1.0)
                comp_scores.append(score * w)
                comp_weights.append(w)

        if comp_weights:
            weighted = sum(comp_scores) / sum(comp_weights)
            if weighted >= 0.80:
                verdict = 'net_positive'
            elif weighted >= 0.55:
                verdict = 'net_neutral'
            else:
                verdict = 'net_negative'
        else:
            verdict = 'insufficient_data'
        component_verdicts[component] = verdict

    # Sustainability (portfolio-level)
    for m in measure_sustainability(conn):
        m['component'] = 'portfolio'
        m['dimension'] = 'sustainability'
        all_measurements.append(m)
        score = STATUS_SCORES.get(m['status'])
        if score is not None:
            dimension_scores['sustainability'].append(score)

    # Dimension aggregate
    dimension_aggregate = {}
    for dim, scores in dimension_scores.items():
        if scores:
            dimension_aggregate[dim] = {
                'score': sum(scores) / len(scores),
                'weight': DIMENSION_WEIGHTS.get(dim, 1.0),
            }

    # Portfolio score
    p_scores, p_weights = [], []
    for dim, data in dimension_aggregate.items():
        p_scores.append(data['score'] * data['weight'])
        p_weights.append(data['weight'])
    portfolio_score = sum(p_scores) / sum(p_weights) if p_weights else 0.5

    # Net verdict
    measured = sum(1 for s in dimension_scores.values() if s)
    if measured < 3:
        net_verdict = 'insufficient_data'
    elif portfolio_score >= 0.80:
        net_verdict = 'net_positive'
    elif portfolio_score >= 0.60:
        net_verdict = 'net_neutral'
    elif portfolio_score >= 0.40:
        net_verdict = 'mixed'
    else:
        net_verdict = 'net_negative'

    positive = [c for c, v in component_verdicts.items() if v == 'net_positive']
    negative = [c for c, v in component_verdicts.items() if v == 'net_negative']
    top_win = positive[0] if positive else None
    top_risk = negative[0] if negative else None

    maintenance = next(
        (m['metric_value'] for m in all_measurements
         if m.get('metric_name') == 'estimated_weekly_ai_maintenance_hours'), None)

    recommendation = _generate_recommendation(net_verdict, component_verdicts, dimension_aggregate, maintenance)

    # Persist
    _persist_measurements(conn, all_measurements, audit_cycle_id)
    _persist_assessment(conn, {
        'net_verdict': net_verdict,
        'component_verdicts': component_verdicts,
        'dimension_scores': dimension_aggregate,
        'top_ai_win': top_win,
        'top_ai_risk': top_risk,
        'maintenance_burden_estimate_hrs_week': maintenance,
        'recommendation': recommendation,
        'audit_cycle_id': audit_cycle_id,
    })

    return {
        'net_verdict': net_verdict,
        'portfolio_score': round(portfolio_score, 3),
        'component_verdicts': component_verdicts,
        'dimension_aggregate': {k: {'score': round(v['score'], 3), 'weight': v['weight']}
                                for k, v in dimension_aggregate.items()},
        'top_win': top_win,
        'top_risk': top_risk,
        'maintenance_hrs_week': maintenance,
        'recommendation': recommendation,
        'measurements_count': len(all_measurements),
    }


def _generate_recommendation(verdict, comp_verdicts, dim_scores, maint_hrs):
    if verdict == 'net_positive':
        return 'AI portfolio is net positive. Continue current configuration.'
    if verdict == 'net_negative':
        failing = [c for c, v in comp_verdicts.items() if v == 'net_negative']
        return (
            f'AI portfolio is net negative. '
            f'Underperforming: {", ".join(failing)}. '
            f'Recommend disabling underperforming components.'
        )
    if verdict == 'mixed' and dim_scores:
        worst = min(dim_scores.items(), key=lambda x: x[1]['score'] * x[1]['weight'])
        return (
            f'Mixed results. Weakest: {worst[0]} ({worst[1]["score"]:.0%}). '
            f'Address before adding new AI components.'
        )
    if maint_hrs and maint_hrs > 3:
        return (
            f'AI requires ~{maint_hrs:.1f} hrs/week maintenance. '
            f'Above sustainable threshold. Reduce generation rate or automate review.'
        )
    return 'Insufficient data. Continue accumulating history.'


def _persist_measurements(conn, measurements, audit_cycle_id):
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    for m in measurements:
        try:
            conn.execute("""
                INSERT INTO pi_ai_outcome_measurements
                (id, measured_at, audit_cycle_id, component, dimension,
                 metric_name, metric_value, metric_unit,
                 threshold_low, threshold_high, status, evidence,
                 sample_size, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), now, audit_cycle_id,
                m.get('component', ''), m.get('dimension', ''),
                m.get('metric_name', ''), m.get('metric_value'),
                m.get('metric_unit'), m.get('threshold_low'),
                m.get('threshold_high'), m.get('status', 'insufficient_data'),
                m.get('evidence', ''), m.get('sample_size'),
                m.get('confidence'),
            ))
        except Exception:
            logger.debug("Failed to persist measurement", exc_info=True)
    try:
        conn.commit()
    except Exception:
        pass


def _persist_assessment(conn, data):
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Get prior verdict for trend
    prior = conn.execute("""
        SELECT net_verdict FROM pi_ai_portfolio_assessments
        ORDER BY assessed_at DESC LIMIT 1
    """).fetchone()
    prior_verdict = prior['net_verdict'] if prior else None

    # Compute trend
    verdict_rank = {'net_positive': 3, 'net_neutral': 2, 'mixed': 1, 'net_negative': 0, 'insufficient_data': -1}
    curr_rank = verdict_rank.get(data['net_verdict'], -1)
    prior_rank = verdict_rank.get(prior_verdict, -1)
    if prior_rank < 0 or curr_rank < 0:
        trend = None
    elif curr_rank > prior_rank:
        trend = 'improving'
    elif curr_rank < prior_rank:
        trend = 'declining'
    else:
        trend = 'stable'

    try:
        conn.execute("""
            INSERT INTO pi_ai_portfolio_assessments
            (id, assessed_at, audit_cycle_id, net_verdict,
             component_verdicts_json, dimension_scores_json,
             top_ai_win, top_ai_risk,
             maintenance_burden_estimate_hrs_week,
             recommendation, prior_verdict, trend)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), now, data.get('audit_cycle_id'),
            data['net_verdict'],
            json.dumps(data['component_verdicts']),
            json.dumps(data['dimension_scores'], default=str),
            data.get('top_ai_win'), data.get('top_ai_risk'),
            data.get('maintenance_burden_estimate_hrs_week'),
            data['recommendation'], prior_verdict, trend,
        ))
        conn.commit()
    except Exception:
        logger.debug("Failed to persist portfolio assessment", exc_info=True)


# ── Intelligence Analyzer Integration ─────────────────────────────────

def generate_ai_outcome_findings(conn) -> list[dict]:
    """Run AI outcome measurement and generate intelligence findings."""
    findings = []

    try:
        result = compute_ai_portfolio_verdict(conn)
    except Exception as e:
        logger.warning("AI outcome measurement failed: %s", e)
        return findings

    # Net negative verdict → high finding
    if result['net_verdict'] == 'net_negative':
        findings.append({
            'dimension': 'engineering',
            'severity': 'high',
            'title': f'AI portfolio is net negative (score: {result["portfolio_score"]:.0%})',
            'analysis': result['recommendation'],
            'recommendation': 'Disable underperforming AI components.',
            'claude_prompt': 'Review AI portfolio assessment and disable net-negative components.',
            'impact': 'AI systems consuming resources without net benefit',
            'files': ['mandarin/intelligence/ai_outcome.py'],
        })

    # Individual component failures
    for comp, verdict in result.get('component_verdicts', {}).items():
        if verdict == 'net_negative':
            findings.append({
                'dimension': 'engineering',
                'severity': 'medium',
                'title': f'AI component {comp} is net negative',
                'analysis': f'{comp} is degrading more dimensions than it improves.',
                'recommendation': f'Consider suspending {comp}.',
                'claude_prompt': f'Investigate why {comp} is net negative and fix or disable.',
                'impact': f'{comp} actively hurting product quality',
                'files': ['mandarin/intelligence/ai_outcome.py'],
            })

    return findings


ANALYZERS = [generate_ai_outcome_findings]
