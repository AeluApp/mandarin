"""AI Governance & Compliance Layer (Doc 11).

NIST AI RMF, ISO 42001/23894/24028, Biden AI Bill of Rights,
SR 11-7, BCBS 239 — calibrated proportionately for a learning app.

Components:
- AI component registry + model validation (SR 11-7)
- FERPA access control (hard dependency for teacher deployment)
- Data subject request handling (GDPR/CCPA)
- Learner-facing transparency (Biden Bill of Rights)
- Data quality checks (BCBS 239)
- Governance compliance analyzer (runs every audit cycle)
- Policy document management (ISO 42001)
"""

import json
import logging
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Component Registry Seed ────────────────────────────────────────────────

def _compute_next_validation(risk_tier: str) -> str:
    days = {'tier_1_high': 30, 'tier_2_medium': 90, 'tier_3_low': 180}
    return (date.today() + timedelta(days=days.get(risk_tier, 90))).isoformat()


def _get_component_definitions() -> list[dict]:
    return [
        {
            'component_name': 'difficulty_prediction_model',
            'component_description': 'LightGBM model predicting item difficulty for scheduling.',
            'ai_type': 'ml_model', 'decision_type': 'scheduling',
            'risk_tier': 'tier_2_medium',
            'risk_tier_rationale': 'Scheduling affects efficiency, not safety. Failures detectable.',
            'failure_mode': 'Inaccurate difficulty estimates from insufficient training data.',
            'failure_impact': 'Learner progresses slower than optimal.',
            'failure_detectability': 'delayed',
            'human_override_available': 1,
            'human_override_mechanism': 'Admin can adjust difficulty. Learner can flag items.',
            'monitoring_function': 'analyze_difficulty_model_performance',
            'known_limitations': 'Requires 200+ samples. Degrades on <10 reviews. Not validated above HSK 6.',
            'performance_benchmarks': 'Zone hit rate: 65%+. Prediction accuracy: within 15%.',
            'component_owner': 'jason_yee',
        },
        {
            'component_name': 'qwen25_content_generation',
            'component_description': 'Qwen2.5-7B local LLM generating drill items. Human review required.',
            'ai_type': 'generative_ai', 'decision_type': 'generation',
            'risk_tier': 'tier_2_medium',
            'risk_tier_rationale': 'Content errors internalized via SRS. Mitigated by mandatory human review.',
            'failure_mode': 'Generates incorrect pinyin/meanings passing automated validation.',
            'failure_impact': 'Learner internalizes incorrect vocabulary if review gate fails.',
            'failure_detectability': 'delayed',
            'human_override_available': 1,
            'human_override_mechanism': 'All content held in review queue. Human approval required.',
            'monitoring_function': 'analyze_ai_portfolio_verdict',
            'known_limitations': 'Not a Chinese linguistics model. Tonal pinyin imperfect. Not linguist-validated.',
            'performance_benchmarks': 'Human approval rate: 70%+.',
            'component_owner': 'jason_yee',
        },
        {
            'component_name': 'kokoro_tts',
            'component_description': 'Kokoro local TTS generating spoken audio for drills and passages.',
            'ai_type': 'ml_model', 'decision_type': 'generation',
            'risk_tier': 'tier_2_medium',
            'risk_tier_rationale': 'Tonal errors internalized via SRS. Latent detectability.',
            'failure_mode': 'Incorrect tones on sandhi cases.',
            'failure_impact': 'Learner internalizes incorrect tones.',
            'failure_detectability': 'latent',
            'human_override_available': 1,
            'human_override_mechanism': 'Tonal validation flags suspicious audio. macOS TTS fallback.',
            'monitoring_function': 'measure_voice_quality',
            'known_limitations': 'Heuristic validation. Not validated by native speaker on full corpus.',
            'performance_benchmarks': 'Tonal failure rate: <5%. Fallback rate: <10%.',
            'component_owner': 'jason_yee',
        },
        {
            'component_name': 'thompson_sampling_scheduler',
            'component_description': 'Multi-armed bandit selecting drill types for learning efficiency.',
            'ai_type': 'ml_model', 'decision_type': 'scheduling',
            'risk_tier': 'tier_3_low',
            'risk_tier_rationale': 'Drill type scheduling is low-stakes. Easily corrected.',
            'failure_mode': 'Converges on suboptimal drill type distribution.',
            'failure_impact': 'Learner over-practices one skill type. Recoverable in days.',
            'failure_detectability': 'delayed',
            'human_override_available': 1,
            'human_override_mechanism': 'Admin can adjust drill type weights.',
            'monitoring_function': 'analyze_srs_performance',
            'known_limitations': 'Requires exploration phase. May underexplore productive drills.',
            'performance_benchmarks': 'Convergence monitoring via existing analyzer.',
            'component_owner': 'jason_yee',
        },
        {
            'component_name': 'abandonment_risk_heuristic',
            'component_description': 'Rule-based model computing learner abandonment risk for teacher alerts.',
            'ai_type': 'rule_based', 'decision_type': 'assessment',
            'risk_tier': 'tier_2_medium',
            'risk_tier_rationale': 'Risk scores drive teacher intervention decisions for real students.',
            'failure_mode': 'Over-flags (alert fatigue) or misses at-risk students.',
            'failure_impact': 'Teacher makes intervention decisions on incorrect signal.',
            'failure_detectability': 'delayed',
            'human_override_available': 1,
            'human_override_mechanism': 'Teacher can dismiss alerts or manually flag students.',
            'monitoring_function': 'analyze_learner_engagement',
            'known_limitations': 'Rule-based, not empirical. Heuristic thresholds. Cultural assumptions.',
            'performance_benchmarks': 'False positive: <20%. False negative: <15%.',
            'component_owner': 'jason_yee',
        },
        {
            'component_name': 'editorial_critic',
            'component_description': 'Qwen2.5 assessing content quality against editorial standard. Admin-only.',
            'ai_type': 'generative_ai', 'decision_type': 'assessment',
            'risk_tier': 'tier_3_low',
            'risk_tier_rationale': 'Admin-facing only. No direct learner impact.',
            'failure_mode': 'Grades content inconsistently.',
            'failure_impact': 'Poor content prioritization in admin queue.',
            'failure_detectability': 'delayed',
            'human_override_available': 1,
            'human_override_mechanism': 'Admin can override any editorial score.',
            'monitoring_function': 'analyze_editorial_corpus',
            'known_limitations': 'Calibration depends on Qwen quality. Subjective judgment.',
            'performance_benchmarks': '70%+ agreement with human editorial assessment.',
            'component_owner': 'jason_yee',
        },
    ]


def seed_component_registry(conn):
    """Seed all Aelu AI components into the registry. Idempotent."""
    components = _get_component_definitions()
    for c in components:
        existing = _safe_query(conn, """
            SELECT id FROM ai_component_registry WHERE component_name = ?
        """, (c['component_name'],))
        if existing:
            continue
        c['id'] = str(uuid.uuid4())
        c['next_validation_due'] = _compute_next_validation(c['risk_tier'])
        conn.execute("""
            INSERT INTO ai_component_registry
            (id, component_name, component_description, ai_type, decision_type,
             risk_tier, risk_tier_rationale, failure_mode, failure_impact,
             failure_detectability, human_override_available, human_override_mechanism,
             monitoring_function, known_limitations, performance_benchmarks,
             component_owner, next_validation_due)
            VALUES
            (:id,:component_name,:component_description,:ai_type,:decision_type,
             :risk_tier,:risk_tier_rationale,:failure_mode,:failure_impact,
             :failure_detectability,:human_override_available,:human_override_mechanism,
             :monitoring_function,:known_limitations,:performance_benchmarks,
             :component_owner,:next_validation_due)
        """, c)
    conn.commit()


# ── Policy Document Seeds ──────────────────────────────────────────────────

_POLICY_SEEDS = [
    {
        'document_key': 'ai_policy',
        'title': 'Aelu AI Policy',
        'user_facing': 0,
        'content': (
            '# Aelu AI Policy\n\n'
            '## AI components in use\n'
            'Difficulty prediction, content generation (human-reviewed), TTS, '
            'drill type scheduling, abandonment risk, editorial critic.\n\n'
            '## Human oversight\n'
            'No AI-generated content reaches a learner without human review.\n\n'
            '## Prohibited uses\n'
            'No consequential decisions without human review. No external AI services.\n\n'
            '## Review schedule: every 180 days.'
        ),
    },
    {
        'document_key': 'data_protection_policy',
        'title': 'Aelu Data Protection Policy',
        'user_facing': 0,
        'content': (
            '# Data Protection Policy\n\n'
            '## FERPA: Student records protected. Access logged.\n'
            '## COPPA: Users under 13 require parental consent.\n'
            '## Learner rights: Access, deletion, export within 30 days.\n'
            '## No third-party data sharing. All AI runs locally.'
        ),
    },
    {
        'document_key': 'ai_transparency_notice',
        'title': 'How AI Works in Aelu',
        'user_facing': 1,
        'content': (
            '# How AI Works in Aelu\n\n'
            'Aelu uses AI to schedule reviews, generate some drill content '
            '(human-reviewed before delivery), and produce spoken audio.\n\n'
            'All AI runs locally. No data sent to external services.\n'
            'Flag any content issues via long-press menu.'
        ),
    },
    {
        'document_key': 'incident_response_procedure',
        'title': 'AI Incident Response Procedure',
        'user_facing': 0,
        'content': (
            '# Incident Response\n\n'
            '## P0: Content bypassed review / data breach → immediate response.\n'
            '## P1: Systematic model failure → response within 24 hours.\n'
            '## P2/P3: Monitoring gap / performance degradation.\n\n'
            'Post-incident review: P0 within 7 days, P1 within 14 days.'
        ),
    },
]


def seed_policy_documents(conn):
    """Seed policy documents. Idempotent."""
    for doc in _POLICY_SEEDS:
        existing = _safe_query(conn, """
            SELECT id FROM ai_policy_documents WHERE document_key = ?
        """, (doc['document_key'],))
        if existing:
            continue
        next_review = (date.today() + timedelta(days=180)).isoformat()
        conn.execute("""
            INSERT INTO ai_policy_documents
            (id, document_key, title, content, status, user_facing, next_review_due, owner)
            VALUES (?, ?, ?, ?, 'active', ?, ?, 'jason_yee')
        """, (str(uuid.uuid4()), doc['document_key'], doc['title'],
              doc['content'], doc['user_facing'], next_review))
    conn.commit()


# ── Model Validation (SR 11-7) ────────────────────────────────────────────

def _get_component_monitoring_status(conn, component_name: str) -> str:
    """Pull latest health status from intelligence engine findings."""
    dimension_map = {
        'difficulty_prediction_model': 'difficulty_model',
        'qwen25_content_generation': 'ai_portfolio',
        'kokoro_tts': 'voice_quality',
        'thompson_sampling_scheduler': 'srs',
        'abandonment_risk_heuristic': 'engagement',
        'editorial_critic': 'editorial',
    }
    dimension = dimension_map.get(component_name)
    if not dimension:
        return 'unknown'

    # Check pi_finding if it exists
    recent = _safe_query(conn, """
        SELECT severity FROM pi_finding
        WHERE dimension = ? AND created_at >= datetime('now', '-7 days')
        ORDER BY created_at DESC LIMIT 1
    """, (dimension,))

    if not recent:
        return 'unknown'
    severity = recent['severity']
    if severity == 'critical':
        return 'critical'
    elif severity in ('high', 'medium'):
        return 'degraded'
    return 'healthy'


def _validate_component(conn, component) -> dict:
    """Validate a single AI component. Returns validation record dict."""
    name = component['component_name']

    limitations_acknowledged = bool(component['known_limitations'])
    override_available = bool(component['human_override_available'])
    conceptual_soundness = (
        'sound' if limitations_acknowledged and override_available else 'needs_review'
    )

    monitoring_status = _get_component_monitoring_status(conn, name)

    # Prediction accuracy from ledger
    prediction_accuracy = None
    row = _safe_query(conn, """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN outcome_confirmed = 1 THEN 1 ELSE 0 END) as confirmed
        FROM pi_predictions
        WHERE prediction_domain LIKE ?
          AND outcome_observed_at IS NOT NULL
          AND prediction_made_at >= datetime('now', '-90 days')
    """, (f'%{name}%',))
    if row and row['total'] and row['total'] > 0:
        prediction_accuracy = row['confirmed'] / row['total']

    # Verdict
    if (conceptual_soundness == 'sound'
            and monitoring_status != 'critical'
            and (prediction_accuracy is None or prediction_accuracy >= 0.50)):
        verdict = 'validated'
    elif monitoring_status == 'critical':
        verdict = 'validation_failed'
    else:
        verdict = 'needs_review'

    return {
        'component_name': name,
        'verdict': verdict,
        'conceptual_soundness': conceptual_soundness,
        'limitations_acknowledged': int(limitations_acknowledged),
        'override_available': int(override_available),
        'monitoring_status': monitoring_status,
        'prediction_accuracy_90d': prediction_accuracy,
        'notes': None,
    }


def _write_validation_record(conn, record: dict):
    conn.execute("""
        INSERT INTO ai_validation_log
        (id, component_name, verdict, prediction_accuracy_90d,
         monitoring_status, conceptual_soundness,
         limitations_acknowledged, override_available, notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), record['component_name'], record['verdict'],
        record['prediction_accuracy_90d'], record['monitoring_status'],
        record['conceptual_soundness'], record['limitations_acknowledged'],
        record['override_available'], record['notes'],
    ))


def run_model_validation(conn) -> list[dict]:
    """Validate all Tier 1 and Tier 2 AI components."""
    components = _safe_query_all(conn, """
        SELECT * FROM ai_component_registry
        WHERE risk_tier IN ('tier_1_high', 'tier_2_medium')
    """)

    records = []
    for c in components:
        record = _validate_component(conn, c)
        _write_validation_record(conn, record)
        records.append(record)
        try:
            conn.execute("""
                UPDATE ai_component_registry
                SET last_validated_at = date('now'), next_validation_due = ?
                WHERE component_name = ?
            """, (_compute_next_validation(c['risk_tier']), c['component_name']))
        except sqlite3.Error:
            pass
    conn.commit()
    return records


# ── FERPA Access Control ───────────────────────────────────────────────────

def check_ferpa_access(conn, requesting_user_id, target_user_id, data_table,
                       request_context='') -> dict:
    """Validate access to student records. Logs all attempts."""
    is_self = requesting_user_id == target_user_id

    is_teacher = False
    # Check if cohort tables exist
    cohort_check = _safe_scalar(conn, """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type='table' AND name='cohort_members'
    """, default=0)
    if cohort_check and not is_self:
        teacher_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM cohort_members cm
            JOIN cohorts c ON c.id = cm.cohort_id
            WHERE c.teacher_id = ? AND cm.user_id = ? AND cm.active = 1
        """, (requesting_user_id, target_user_id), default=0)
        is_teacher = teacher_count > 0

    permitted = is_self or is_teacher
    basis = (
        'self_access' if is_self else
        'legitimate_educational_interest' if is_teacher else
        'denied_no_basis'
    )

    try:
        conn.execute("""
            INSERT INTO ferpa_access_audit
            (id, requesting_user_id, target_user_id, data_table,
             access_permitted, access_basis, request_context)
            VALUES (?,?,?,?,?,?,?)
        """, (str(uuid.uuid4()), requesting_user_id, target_user_id,
              data_table, int(permitted), basis, request_context))
        conn.commit()
    except sqlite3.Error as e:
        logger.warning("FERPA audit log failed: %s", e)

    return {'permitted': permitted, 'basis': basis}


# ── Data Subject Requests ──────────────────────────────────────────────────

def handle_deletion_request(conn, user_id: str) -> dict:
    """Delete user learning data. GDPR Article 17 / CCPA."""
    tables = [
        'review_event', 'session_log', 'vocab_encounter',
        'output_drill_responses', 'tutor_sessions', 'tutor_corrections',
        'speaking_practice_sessions', 'pi_funnel_events',
        'user_consent_records', 'user_age_classification',
    ]
    deleted = {}
    for table in tables:
        exists = _safe_query(conn, """
            SELECT 1 FROM sqlite_master WHERE type='table' AND name=?
        """, (table,))
        if not exists:
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if 'user_id' not in cols:
            continue
        count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?",
                             (user_id,)).fetchone()[0]
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        deleted[table] = count
    conn.commit()
    return {'status': 'completed', 'deleted_records': deleted}


def handle_access_request(conn, user_id: str) -> dict:
    """Return all data held about a user. GDPR Article 15."""
    tables = ['review_event', 'session_log', 'vocab_encounter', 'user_consent_records']
    export = {}
    for table in tables:
        exists = _safe_query(conn, """
            SELECT 1 FROM sqlite_master WHERE type='table' AND name=?
        """, (table,))
        if not exists:
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if 'user_id' not in cols:
            continue
        rows = conn.execute(f"SELECT * FROM {table} WHERE user_id=?", (user_id,)).fetchall()
        export[table] = [dict(r) for r in rows]
    return {'status': 'completed', 'data': export}


# ── Learner Transparency ──────────────────────────────────────────────────

def get_transparency_report(conn, user_id: str) -> dict:
    """Learner-facing plain language description of AI use."""
    return {
        'what_ai_does_in_aelu': {
            'adaptive_scheduling': {
                'plain_language': (
                    'Aelu uses a model trained on your review history to schedule '
                    'items at the right difficulty — roughly 75% accuracy target.'
                ),
                'how_to_adjust': 'Settings → Learning → Difficulty',
            },
            'ai_generated_content': {
                'plain_language': (
                    'Some drill items were generated by an AI model and reviewed '
                    'by a human before reaching you. Flag errors via long-press.'
                ),
                'how_to_flag': 'Long-press any drill item → Report an issue',
            },
            'spoken_audio': {
                'plain_language': (
                    'All audio is generated by a local TTS model. Tones are validated '
                    'automatically but may occasionally be imprecise on sandhi cases.'
                ),
                'how_to_flag': 'Long-press any audio → Report pronunciation issue',
            },
        },
        'your_data': {
            'what_is_stored': 'Review history, session timing, accuracy.',
            'what_is_not_stored': 'No audio recordings. No external AI services.',
            'how_to_delete': 'Settings → Privacy → Delete my learning data',
        },
        'your_rights': {
            'human_review': 'All AI content is human-reviewed before delivery.',
            'flag_errors': 'Flag any incorrect content. Items removed from queue immediately.',
            'opt_out_of_adaptive': 'Settings → Learning → Use fixed difficulty.',
            'data_deletion': 'Settings → Privacy → Request data deletion.',
        },
    }


def explain_item_scheduling(conn, item_id: str, user_id: str) -> dict:
    """Plain language explanation of why a specific item is being shown."""
    history = _safe_query_all(conn, """
        SELECT correct, created_at FROM review_event
        WHERE content_item_id = ? AND user_id = ?
        ORDER BY created_at DESC LIMIT 5
    """, (item_id, user_id))

    if not history:
        reason = "This is a new item you haven't seen before."
        accuracy_note = ""
    else:
        last_at = history[0]['created_at']
        days = _safe_scalar(conn, """
            SELECT julianday('now') - julianday(?)
        """, (last_at,), default=0)
        days = int(days) if days else 0
        if days >= 1:
            reason = (f"You reviewed this {days} day{'s' if days != 1 else ''} ago. "
                      f"Reviewing now reinforces it before you forget.")
        else:
            reason = "This item is scheduled for review based on your recent history."

        recent_correct = sum(1 for r in history if r['correct'])
        accuracy_note = f"Recent accuracy: {recent_correct}/{len(history)} correct."

    return {
        'item_id': item_id,
        'scheduling_reason': reason,
        'accuracy_note': accuracy_note,
    }


# ── Data Quality (BCBS 239) ───────────────────────────────────────────────

def check_data_quality(conn) -> list[dict]:
    """Validate data integrity for the intelligence engine."""
    findings = []

    # Completed sessions with no review events
    orphaned = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log s
        WHERE s.started_at >= datetime('now', '-30 days')
        AND NOT EXISTS (
            SELECT 1 FROM review_event r WHERE r.session_id = s.id
        )
    """, default=0)

    if orphaned > 0:
        findings.append(_gov_finding(
            'data_quality', 'high',
            f'{orphaned} sessions with no review events',
            'Sessions without review events corrupt accuracy calculations.',
            'Investigate session/event logging pipeline.',
        ))

    # Future timestamps
    future = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE created_at > datetime('now', '+1 hour')
    """, default=0)

    if future > 0:
        findings.append(_gov_finding(
            'data_quality', 'medium',
            f'{future} review events with future timestamps',
            'Future timestamps indicate clock skew or data corruption.',
            'Audit timestamp handling.',
        ))

    return findings


# ── Governance Compliance Analyzer ─────────────────────────────────────────

def _gov_finding(dimension, severity, title, detail, recommendation):
    return {
        'dimension': dimension,
        'severity': severity,
        'title': title,
        'analysis': detail,
        'recommendation': recommendation,
        'claude_prompt': recommendation,
        'impact': 'Governance compliance',
        'files': [],
        'finding_type': 'governance',
    }


def analyze_governance_compliance(conn) -> list[dict]:
    """Main governance analyzer. Runs every audit cycle."""
    findings = []

    # 1. Components overdue for validation
    overdue = _safe_query_all(conn, """
        SELECT component_name, risk_tier, next_validation_due
        FROM ai_component_registry
        WHERE risk_tier IN ('tier_1_high', 'tier_2_medium')
          AND (next_validation_due IS NULL OR next_validation_due < date('now'))
    """)
    if overdue:
        names = [r['component_name'] for r in overdue]
        findings.append(_gov_finding(
            'governance', 'high',
            f'{len(overdue)} AI component(s) overdue for validation',
            f'Overdue: {", ".join(names)}. SR 11-7 requires periodic validation.',
            'Run model validation and review results.',
        ))

    # 2. Open P0/P1 incidents
    open_critical = _safe_scalar(conn, """
        SELECT COUNT(*) FROM ai_incident_log
        WHERE severity IN ('P0', 'P1') AND resolved_at IS NULL
          AND detected_at >= datetime('now', '-30 days')
    """, default=0)
    if open_critical > 0:
        findings.append(_gov_finding(
            'governance', 'critical',
            f'{open_critical} open critical incident(s) unresolved',
            'P0/P1 incidents must not remain unresolved.',
            'Review open incidents. Log resolution.',
        ))

    # 3. Overdue data subject requests
    overdue_requests = _safe_scalar(conn, """
        SELECT COUNT(*) FROM data_subject_requests
        WHERE status IN ('pending', 'in_progress')
          AND response_due_date < date('now')
    """, default=0)
    if overdue_requests > 0:
        findings.append(_gov_finding(
            'governance', 'critical',
            f'{overdue_requests} data subject request(s) past legal deadline',
            f'GDPR: 30 days. CCPA: 45 days. Regulatory risk.',
            'Respond immediately.',
        ))

    # 4. COPPA subjects without consent
    minors_no_consent = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user_age_classification
        WHERE is_coppa_subject = 1 AND parental_consent_obtained = 0
    """, default=0)
    if minors_no_consent > 0:
        findings.append(_gov_finding(
            'governance', 'critical',
            f'{minors_no_consent} user(s) under 13 without parental consent',
            'COPPA requires verifiable parental consent for users under 13.',
            'Restrict access until consent obtained.',
        ))

    # 5. Overdue policy documents
    overdue_policies = _safe_query_all(conn, """
        SELECT title FROM ai_policy_documents
        WHERE status = 'active' AND next_review_due < date('now')
    """)
    if overdue_policies:
        findings.append(_gov_finding(
            'governance', 'medium',
            f'{len(overdue_policies)} policy document(s) overdue for review',
            ', '.join(r['title'] for r in overdue_policies),
            'Review and update overdue policy documents.',
        ))

    # 6. Data quality
    findings.extend(check_data_quality(conn))

    return findings


# ── Analyzer Registry ──────────────────────────────────────────────────────

ANALYZERS = [
    analyze_governance_compliance,
]
