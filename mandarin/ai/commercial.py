"""Commercial Intelligence and Go-to-Market (Doc 19).

Institutional usage reporting, pricing recommendation, commercial readiness signals.
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def generate_institutional_usage_report(conn: sqlite3.Connection, cohort_id: int) -> dict:
    """Generates a usage and outcome report for a cohort."""
    cohort = None
    try:
        cohort = conn.execute(
            "SELECT * FROM cohorts WHERE id=?", (cohort_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not cohort:
        return {}

    members = []
    try:
        members = conn.execute("""
            SELECT cm.user_id FROM cohort_members cm
            WHERE cm.cohort_id=? AND cm.active=1
        """, (cohort_id,)).fetchall()
    except sqlite3.OperationalError:
        pass

    user_ids = [m['user_id'] for m in members]
    if not user_ids:
        return {'cohort_id': cohort_id, 'member_count': 0}

    placeholders = ','.join('?' * len(user_ids))

    # Engagement metrics
    engagement = {'active_users': 0, 'avg_sessions_per_week': 0, 'avg_accuracy': 0}
    try:
        engagement = conn.execute(f"""
            SELECT
                COUNT(DISTINCT user_id) as active_users,
                AVG(sessions_per_week) as avg_sessions_per_week,
                AVG(accuracy_30d) as avg_accuracy
            FROM (
                SELECT
                    user_id,
                    COUNT(*) * 1.0 / 4.0 as sessions_per_week,
                    AVG(CASE WHEN correct=1 THEN 100.0 ELSE 0.0 END) as accuracy_30d
                FROM review_event
                WHERE user_id IN ({placeholders})
                AND created_at >= datetime('now','-30 days')
                GROUP BY user_id
            )
        """, user_ids).fetchone()
    except sqlite3.OperationalError:
        pass

    # Vocabulary acquisition
    vocab = {'total_items_mastered': 0, 'avg_items_mastered': 0}
    try:
        vocab = conn.execute(f"""
            SELECT
                SUM(items_mastered) as total_items_mastered,
                AVG(items_mastered) as avg_items_mastered
            FROM (
                SELECT user_id, COUNT(*) as items_mastered
                FROM memory_states
                WHERE user_id IN ({placeholders})
                AND state='review' AND stability >= 21
                GROUP BY user_id
            )
        """, user_ids).fetchone()
    except sqlite3.OperationalError:
        pass

    # Proficiency progression
    progression = {'avg_hsk': 0, 'min_hsk': 0, 'max_hsk': 0}
    try:
        progression = conn.execute(f"""
            SELECT
                AVG(composite_hsk_estimate) as avg_hsk,
                MIN(composite_hsk_estimate) as min_hsk,
                MAX(composite_hsk_estimate) as max_hsk
            FROM learner_proficiency_zones
            WHERE user_id IN ({placeholders})
        """, user_ids).fetchone()
    except sqlite3.OperationalError:
        pass

    active_users = (engagement['active_users'] or 0) if engagement else 0
    avg_sessions = (engagement['avg_sessions_per_week'] or 0) if engagement else 0
    avg_accuracy = (engagement['avg_accuracy'] or 0) if engagement else 0
    total_mastered = (vocab['total_items_mastered'] or 0) if vocab else 0
    avg_mastered = (vocab['avg_items_mastered'] or 0) if vocab else 0
    avg_hsk = (progression['avg_hsk'] or 0) if progression else 0
    min_hsk = (progression['min_hsk'] or 0) if progression else 0
    max_hsk = (progression['max_hsk'] or 0) if progression else 0

    return {
        'cohort_name': (cohort['name'] if cohort else 'Cohort'),
        'member_count': len(user_ids),
        'report_period': '30 days',
        'engagement': {
            'active_users': active_users,
            'avg_sessions_per_week': round(avg_sessions, 1),
            'avg_accuracy_pct': round(avg_accuracy, 1),
        },
        'vocabulary': {
            'total_items_mastered': total_mastered,
            'avg_items_mastered_per_learner': round(avg_mastered),
        },
        'proficiency': {
            'avg_composite_hsk': round(avg_hsk, 1),
            'range': f"{round(min_hsk, 1)} – {round(max_hsk, 1)}",
        },
        'interpretation': _interpret_cohort_results(
            active_users, avg_sessions, avg_accuracy,
            avg_mastered, avg_hsk
        ),
    }


def _interpret_cohort_results(active_users, avg_sessions, avg_accuracy, avg_mastered, avg_hsk) -> str:
    """Plain language interpretation for non-technical audience."""
    parts = []
    if avg_sessions >= 3:
        parts.append(f"Learners are averaging {avg_sessions:.1f} study sessions per week — strong engagement.")
    elif avg_sessions >= 1:
        parts.append(f"Learners averaging {avg_sessions:.1f} sessions per week — moderate engagement.")
    else:
        parts.append("Low session frequency — consider intervention.")

    if avg_mastered >= 50:
        parts.append(f"An average of {round(avg_mastered)} vocabulary items have been durably acquired per learner.")

    if avg_hsk >= 1:
        parts.append(f"Cohort average proficiency estimate: HSK {avg_hsk:.1f}.")

    return ' '.join(parts)


def get_pricing_recommendation(conn: sqlite3.Connection) -> dict:
    """Returns current pricing recommendation based on commercial readiness."""
    confirmed = []
    pending = []
    try:
        readiness = conn.execute("""
            SELECT condition_name, current_status
            FROM pi_commercial_readiness
            ORDER BY condition_name
        """).fetchall()
        confirmed = [r['condition_name'] for r in readiness if r['current_status'] == 'met']
        pending = [r['condition_name'] for r in readiness if r['current_status'] in ('not_met', 'not_assessed', 'partial')]
    except sqlite3.OperationalError:
        pass

    b2c_ready = 'teacher_dashboard_deployed' in confirmed and 'student_onboarding_validated' in confirmed
    b2b_ready = b2c_ready and 'institutional_outcome_data' in confirmed

    return {
        'b2c_recommendation': {
            'ready': b2c_ready,
            'suggested_price': '$12/month or $99/year',
            'rationale': 'Undercuts Skritter ($14.99/mo) with superior adaptive intelligence.',
            'conditions_pending': [p for p in pending if 'student' in p or 'onboard' in p],
        },
        'b2b_recommendation': {
            'ready': b2b_ready,
            'suggested_price': '$200-400/teacher/year (5-10 students included)',
            'rationale': 'Teacher-first pricing aligns with institutional budget cycles.',
            'conditions_pending': [p for p in pending if 'institutional' in p or 'outcome' in p],
        },
    }


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

def analyze_commercial_intelligence(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for commercial readiness."""
    from ..intelligence._base import _finding
    findings = []

    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM cohorts c
            WHERE c.active=1
            AND NOT EXISTS (
                SELECT 1 FROM pi_commercial_readiness pcr
                WHERE pcr.condition_name='institutional_outcome_data'
                AND pcr.current_status='met'
            )
        """).fetchone()
        cnt = (row['cnt'] or 0) if row else 0

        if cnt > 0:
            findings.append(_finding(
                dimension="commercial",
                severity="high",
                title=f"{cnt} active cohort(s) without outcome report",
                analysis="Active cohorts should generate outcome reports for teacher relationship maintenance.",
                recommendation="Run generate_institutional_usage_report() for each active cohort.",
                claude_prompt="Check cohorts table for active cohorts without outcome data.",
                impact="Commercial evidence and teacher relationships at risk.",
                files=["mandarin/ai/commercial.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings
