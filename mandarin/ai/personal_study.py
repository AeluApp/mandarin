"""Jason's Personal HSK 9 Study System (Doc 20).

Personal configuration and HSK 9 goal tracking.
"""

import logging
import sqlite3
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


HSK9_PERSONAL_PHASES = {
    'phase_1': {
        'name': 'HSK 4 Consolidation',
        'current_hsk_start': 3.5,
        'target_hsk': 4.5,
        'estimated_months': 6,
        'primary_method': 'SRS drilling with 4x weekly sessions',
        'milestones': [
            '80% HSK 4 vocabulary stable (approx 960 items)',
            '把 construction mastered',
            'Resultative complements mastered',
            '是...的 cleft construction mastered',
            'Reading HSK 4 texts without dictionary',
        ],
        'tutor_focus': 'Correcting production errors at HSK 4 level; sandhi automation',
        'weekly_commitment': 4,
        'new_items_per_session': 5,
        'reading_target': '2 HSK 4 texts per week',
    },
    'phase_2': {
        'name': 'HSK 5 Acquisition',
        'current_hsk_start': 4.5,
        'target_hsk': 5.5,
        'estimated_months': 8,
        'primary_method': 'SRS drilling + graded reading (balanced)',
        'milestones': [
            '80% HSK 5 vocabulary stable (approx 2000 items)',
            'Potential complement patterns mastered',
            'Complex topic-comment structures mastered',
            'Reading contemporary newspaper articles with occasional lookup',
            'Listening to slow Mandarin Corner episodes without transcript',
        ],
        'tutor_focus': 'Register awareness; formal vs colloquial in production',
        'weekly_commitment': 4,
        'new_items_per_session': 7,
        'reading_target': '3 HSK 5 texts per week including 1 authentic source',
    },
    'phase_3': {
        'name': 'HSK 6 Acquisition and Reading Transition',
        'current_hsk_start': 5.5,
        'target_hsk': 6.5,
        'estimated_months': 12,
        'primary_method': 'Reading-primary acquisition with SRS for targeted vocabulary',
        'milestones': [
            '80% HSK 6 vocabulary stable (approx 4000 items)',
            "Reading Chairman's Bao intermediate articles fluently",
            'Watching Mandarin Corner interviews without subtitles (most)',
            'Written production in formal register on familiar topics',
        ],
        'tutor_focus': 'Written production correction; literary register introduction',
        'weekly_commitment': 5,
        'new_items_per_session': 8,
        'reading_target': '30+ minutes extensive reading daily',
    },
    'phase_4': {
        'name': 'HSK 7-9 Long Haul',
        'current_hsk_start': 6.5,
        'target_hsk': 9.0,
        'estimated_months': 48,
        'primary_method': 'Immersive reading and listening; SRS for specialized vocabulary',
        'milestones': [
            'Reading contemporary Chinese novels',
            'Understanding political and academic discourse',
            'Production in multiple registers',
            'Classical allusions and 成语 fluency',
            'HSK 9 certification',
        ],
        'tutor_focus': 'Literary analysis; classical patterns; writing development',
        'weekly_commitment': 5,
        'new_items_per_session': 10,
        'reading_target': '60+ minutes extensive reading daily',
    },
}


PERSONAL_CONFIG = {
    'active_phase': 'phase_1',
    'preferred_session_length_minutes': 20,
    'preferred_session_time': 'evening',
    'weekly_commitment_target': 4,
    'primary_tutor_platform': 'italki',
    'tutor_session_frequency': 'biweekly',
    'primary_reading_source': 'chairman_bao',
    'reading_target_per_session': 1,
    'active_lenses': [
        'civic_institutions',
        'urban_texture',
        'social_texture',
        'cultural_memory',
    ],
    'audit_report_frequency': 'weekly',
    'milestone_alerts': True,
    'hsk9_target_year': 2031,
}


def get_personal_study_dashboard(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Personalized study dashboard for HSK 9 goal tracking."""
    # Get learner context
    current_hsk = 0.0
    try:
        proficiency = conn.execute(
            "SELECT * FROM learner_proficiency_zones WHERE user_id=?",
            (user_id,)
        ).fetchone()
        if proficiency:
            current_hsk = proficiency['composite_hsk_estimate'] or 0.0
    except sqlite3.OperationalError:
        pass

    current_phase = PERSONAL_CONFIG['active_phase']
    phase = HSK9_PERSONAL_PHASES[current_phase]

    target_hsk = phase['target_hsk']
    phase_range = max(0.1, target_hsk - phase['current_hsk_start'])
    progress_in_phase = max(0, min(1,
        (current_hsk - phase['current_hsk_start']) / phase_range
    ))

    # Sessions this week
    sessions_this_week = 0
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id=?
            AND started_at >= date('now','weekday 0','-7 days')
            AND ended_at IS NOT NULL
        """, (user_id,)).fetchone()
        sessions_this_week = (row['cnt'] or 0) if row else 0
    except sqlite3.OperationalError:
        pass

    # Curriculum recommendation (try import, graceful fail)
    recommendation = ''
    try:
        from .curriculum import get_curriculum_recommendation
        rec = get_curriculum_recommendation(conn, user_id)
        recommendation = rec.get('recommendation', '')
    except Exception:
        pass

    return {
        'current_hsk': current_hsk,
        'target_hsk_this_phase': target_hsk,
        'phase_name': phase['name'],
        'phase_progress_pct': round(progress_in_phase * 100),
        'estimated_months_remaining_in_phase': round(
            phase['estimated_months'] * (1 - progress_in_phase)
        ),
        'hsk9_year_estimate': _estimate_hsk9_year(conn, user_id, current_hsk),
        'this_week': {
            'sessions_completed': sessions_this_week,
            'sessions_target': PERSONAL_CONFIG['weekly_commitment_target'],
            'on_track': sessions_this_week >= (
                PERSONAL_CONFIG['weekly_commitment_target'] *
                (_days_into_week() / 7)
            ),
        },
        'curriculum_recommendation': recommendation,
    }


def _estimate_hsk9_year(conn: sqlite3.Connection, user_id: int, current_hsk: float) -> int:
    """Rough estimate of year to reach HSK 9 based on current trajectory."""
    if current_hsk <= 0:
        return PERSONAL_CONFIG['hsk9_target_year']

    # Estimate monthly HSK progress from recent trend
    six_months_ago_hsk = None
    try:
        row = conn.execute("""
            SELECT composite_hsk_estimate FROM learner_proficiency_zones
            WHERE user_id=?
            AND computed_at <= datetime('now','-180 days')
            ORDER BY computed_at DESC LIMIT 1
        """, (user_id,)).fetchone()
        if row:
            six_months_ago_hsk = row['composite_hsk_estimate']
    except sqlite3.OperationalError:
        pass

    if six_months_ago_hsk:
        monthly_progress = (current_hsk - six_months_ago_hsk) / 6
    else:
        monthly_progress = 0.15

    if monthly_progress <= 0:
        return PERSONAL_CONFIG['hsk9_target_year']

    months_to_hsk9 = (9.0 - current_hsk) / monthly_progress
    target_year = date.today().year + round(months_to_hsk9 / 12)
    return target_year


def _days_into_week() -> int:
    return date.today().weekday() + 1
