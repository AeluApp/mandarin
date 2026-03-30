"""Product Intelligence — Strategic Intelligence Layer (Doc 10).

Three components:
A) The Strategist — derives/maintains commercial thesis, prioritizes via trade-off logic
B) The Editorial Critic — assesses content quality against competitive benchmarks
C) The Competitor — structured comparative evaluation with harsh grading

Strategic findings differ from operational findings: they lead with commercial
implication, state priority (P0/P1/P2), and articulate trade-offs.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar, _f

logger = logging.getLogger(__name__)


# ── Editorial Standard ─────────────────────────────────────────────────────

EDITORIAL_STANDARD = {
    'specificity': {
        'description': 'Content is about something specific, not a generic topic category',
        'weight': 3.0,
    },
    'adult_assumption': {
        'description': 'Content assumes the learner is an intelligent adult',
        'weight': 2.5,
    },
    'world_revealing': {
        'description': 'Content reveals something true about Chinese life the learner did not know',
        'weight': 3.0,
    },
    'finish_pull': {
        'description': 'A motivated learner would want to finish this content once started',
        'weight': 2.5,
    },
    'language_density': {
        'description': 'The language is the kind a sophisticated speaker would actually use',
        'weight': 2.0,
    },
}


# ── Strategic Finding Builder ──────────────────────────────────────────────

def _make_strategic_finding(priority, title, implication, detail, action):
    """Strategic findings lead with commercial implication, not the problem."""
    return {
        'finding_type': 'strategic',
        'priority': priority,
        'title': title,
        'commercial_implication': implication,
        'detail': detail,
        'recommended_action': action,
        'dimension': 'strategic',
        'severity': 'critical' if priority == 'P0' else 'high' if priority == 'P1' else 'medium',
    }


# ── Part 1: Competitive Position ──────────────────────────────────────────

def _assess_competitive_position(conn) -> dict:
    """Compute Aelu's position from evaluation dimensions."""
    dimensions = _safe_query_all(conn, """
        SELECT * FROM pi_evaluation_dimensions ORDER BY weight DESC
    """)
    if not dimensions:
        return {'status': 'insufficient_data', 'leads_on': [], 'significant_lags': [],
                'critical_path_gaps': [], 'dimensions': [], 'weighted_score': 0}

    leads = [d for d in dimensions
             if (d['aelu_current_score'] or 0) > (d['best_in_class_score'] or 0)]
    significant_lags = [d for d in dimensions
                        if (d['gap'] or 0) >= 3 and (d['weight'] or 0) >= 2.0]
    critical_path = [d for d in dimensions if d['on_critical_path']]

    total_weight = sum(d['weight'] for d in dimensions if d['weight'])
    weighted_score = sum(
        (d['aelu_current_score'] or 0) * d['weight']
        for d in dimensions if d['weight'] and d['aelu_current_score']
    ) / total_weight if total_weight else 0

    return {
        'weighted_score': weighted_score,
        'leads_on': [d['dimension_name'] for d in leads],
        'significant_lags': [d['dimension_name'] for d in significant_lags],
        'critical_path_gaps': [d['dimension_name'] for d in critical_path],
        'dimensions': dimensions,
    }


# ── Part 2: The Strategist — Thesis Derivation ────────────────────────────

def _identify_viable_models(conn, position: dict) -> list:
    dim_scores = {
        d['dimension_name']: d['aelu_current_score']
        for d in position.get('dimensions', [])
        if d['aelu_current_score'] is not None
    }
    viable = []

    teacher = dim_scores.get('classroom_and_teacher_tools', 0)
    ux = dim_scores.get('ux_polish', 0)
    corpus = dim_scores.get('vocabulary_corpus_depth', 0)
    if (teacher + ux + corpus) / 3 >= 4.5:
        viable.append('b2b2c_teachers')

    activation = dim_scores.get('first_session_activation', 0)
    content = dim_scores.get('content_interest', 0)
    intelligence = dim_scores.get('intelligence_and_adaptivity', 0)
    if (activation + content + ux + intelligence) / 4 >= 5.0:
        viable.append('b2c_subscription')

    if not viable:
        viable.append('undetermined')
    return viable


def _select_primary_model(conn, viable_models: list) -> str:
    if 'b2b2c_teachers' in viable_models and 'b2c_subscription' in viable_models:
        return 'hybrid_b2c_b2b2c'
    elif 'b2b2c_teachers' in viable_models:
        return 'b2b2c_teachers'
    elif 'b2c_subscription' in viable_models:
        return 'b2c_subscription'
    return 'undetermined'


def _derive_target_user(conn, model: str, position: dict) -> str:
    if model in ('b2b2c_teachers', 'hybrid_b2c_b2b2c'):
        return (
            'Primary: Mandarin teachers at language schools, universities, and '
            'corporate training programs who need structured, intelligent learning '
            'with measurable progress tracking. '
            'Secondary: serious adult self-directed learners targeting HSK 5+.'
        )
    elif model == 'b2c_subscription':
        return (
            'Serious adult Mandarin learners targeting HSK 5-9, typically professionals '
            'with China-related work, academics, or high-commitment heritage speakers.'
        )
    return 'Target user not yet determined. Competitive position insufficient.'


def _derive_value_proposition(conn, position: dict, target_user: str) -> str:
    leads = position.get('leads_on', [])
    vp = []
    if 'intelligence_and_adaptivity' in leads:
        vp.append('the most adaptive Mandarin learning system available')
    if 'classroom_and_teacher_tools' in leads:
        vp.append('the only Mandarin platform with classroom intelligence built in')
    if 'advanced_learner_ceiling' in leads:
        vp.append('built to take serious learners to advanced fluency')
    if 'cultural_depth' in leads:
        vp.append('content grounded in real Chinese civic and cultural life')
    if not vp:
        return 'Value proposition not yet differentiated enough for confident derivation.'
    return 'Aelu is ' + ' and '.join(vp[:2]) + '.'


def _derive_primary_moat(conn, position: dict) -> str:
    leads = position.get('leads_on', [])
    if 'intelligence_and_adaptivity' in leads and 'classroom_and_teacher_tools' in leads:
        return (
            'The intelligence engine. No competitor has anything approaching '
            'Aelu\'s adaptive learning analytics. The classroom dimension adds a '
            'network effect: teacher adoption drives student adoption at scale.'
        )
    elif 'intelligence_and_adaptivity' in leads:
        return (
            'The intelligence engine and adaptive difficulty system. '
            'A technical moat that compounds with usage data.'
        )
    return 'Primary moat not yet established.'


def _derive_key_assumptions(model: str, position: dict, target_user: str) -> dict:
    if model in ('b2b2c_teachers', 'hybrid_b2c_b2b2c'):
        return {
            'key': [
                'Teachers at language schools have budget for software tools',
                'Teachers value student progress data enough to pay for it',
                'Intelligence engine produces measurably better outcomes',
                'UX is polished enough to deploy to students',
                'Teacher acquisition channel is efficient enough',
            ],
            'disconfirming': [
                'Teachers show no budget or authority to purchase',
                'Student activation rate in pilot below 40%',
                'Teachers report dashboard does not save them time',
                'Sales cycle exceeds 6 months for institutional buyers',
                'Competitors launch matching classroom features within 6 months',
            ],
            'confirming': [
                '3+ teachers successfully onboard classes without support',
                'Student D7 retention in teacher-managed classes exceeds 40%',
                'Teachers spontaneously recommend to other teachers',
                'At least one institution agrees to pay before pilot ends',
                'Learning velocity data shows measurable advantage',
            ],
        }
    return {
        'key': [
            'Serious adult learners will pay a premium for depth',
            'Activation experience converts visitors at 30%+',
            'Vocabulary corpus reaches HSK 5 depth within 6 months',
        ],
        'disconfirming': [
            'Paid conversion rate below 2% after activation improvements',
            'Churn rate above 40% in first 90 days',
        ],
        'confirming': [
            'Organic word-of-mouth from serious learner communities',
            'Activation rate above 30% after UX improvements',
        ],
    }


def _derive_price_rationale(model: str, position: dict) -> str:
    if model in ('b2b2c_teachers', 'hybrid_b2c_b2b2c'):
        return (
            'B2B2C: per-student pricing at $3-5/student/month positions below '
            'HelloChinese ($10) but above free tools. Teacher-pays model. '
            'B2C: $8-12/month positions against Hack Chinese ($9) and '
            "Chairman's Bao ($12) with broader value proposition."
        )
    elif model == 'b2c_subscription':
        return (
            '$8-12/month: positions against Hack Chinese ($9) and '
            "Chairman's Bao ($12). Justified by broader feature set and adaptivity."
        )
    return 'Price point cannot be determined until revenue model is selected.'


def _identify_blockers(conn, model: str) -> list:
    blockers = []
    if model in ('b2b2c_teachers', 'hybrid_b2c_b2b2c'):
        blockers.extend([
            'Teacher dashboard not yet deployed to real users',
            'No institutional pricing structure defined',
            'No teacher-facing marketing page',
            'Student onboarding not validated for classroom context',
            'No progress report format for administrators',
        ])
    if model in ('b2c_subscription', 'hybrid_b2c_b2b2c'):
        blockers.extend([
            'Vocabulary corpus below competitive threshold at HSK 4-5',
            'First-session activation not validated',
            'No pricing page or subscription infrastructure',
            'UX polish below HelloChinese benchmark',
        ])
    return blockers


def _estimate_months_to_monetization(conn, model: str) -> int:
    if model == 'b2b2c_teachers':
        return 3
    elif model == 'b2c_subscription':
        return 6
    elif model == 'hybrid_b2c_b2b2c':
        return 3
    return 12


def _compute_thesis_confidence(conn, position: dict, model: str) -> float:
    base = 0.5
    leads = position.get('leads_on', [])
    lags = position.get('significant_lags', [])
    if 'intelligence_and_adaptivity' in leads:
        base += 0.10
    if 'classroom_and_teacher_tools' in leads:
        base += 0.10
    if len(lags) > 4:
        base -= 0.10
    if model == 'undetermined':
        base -= 0.20
    return round(min(0.85, max(0.20, base)), 2)


def _explain_confidence(confidence: float, model: str, position: dict) -> str:
    if confidence >= 0.65:
        return f'Moderate-high confidence. Aelu leads on {len(position.get("leads_on", []))} dimensions.'
    elif confidence >= 0.45:
        return f'Moderate confidence. Significant lags: {", ".join(position.get("significant_lags", [])[:3])}.'
    return f'Low confidence. Revenue model is {model}. More data needed.'


def derive_strategic_thesis(conn) -> dict:
    """Derive a commercial thesis from competitive knowledge and current capabilities."""
    position = _assess_competitive_position(conn)
    viable_models = _identify_viable_models(conn, position)
    primary_model = _select_primary_model(conn, viable_models)
    target_user = _derive_target_user(conn, primary_model, position)
    value_prop = _derive_value_proposition(conn, position, target_user)
    moat = _derive_primary_moat(conn, position)
    assumptions = _derive_key_assumptions(primary_model, position, target_user)
    confidence = _compute_thesis_confidence(conn, position, primary_model)

    return {
        'target_user': target_user,
        'value_proposition': value_prop,
        'revenue_model': primary_model,
        'price_point_rationale': _derive_price_rationale(primary_model, position),
        'primary_moat': moat,
        'key_assumptions': json.dumps(assumptions['key']),
        'disconfirming_conditions': json.dumps(assumptions['disconfirming']),
        'confirming_conditions': json.dumps(assumptions['confirming']),
        'monetization_blockers': json.dumps(_identify_blockers(conn, primary_model)),
        'estimated_months_to_monetization': _estimate_months_to_monetization(conn, primary_model),
        'confidence_score': confidence,
        'confidence_rationale': _explain_confidence(confidence, primary_model, position),
    }


# ── Part 2b: Strategist Analyzers ─────────────────────────────────────────

def _seed_commercial_readiness(conn, thesis_id: str, model: str):
    """Seed pi_commercial_readiness conditions for a thesis."""
    conditions = []
    if model in ('b2b2c_teachers', 'hybrid_b2c_b2b2c'):
        conditions.extend([
            ('teacher_dashboard_deployed', 'Teacher dashboard deployed to real users', 'product', 'blocking'),
            ('institutional_pricing', 'Institutional pricing structure defined', 'market', 'blocking'),
            ('teacher_marketing_page', 'Teacher-facing marketing page exists', 'market', 'blocking'),
            ('classroom_onboarding', 'Student onboarding validated for classroom context', 'ux', 'blocking'),
            ('admin_progress_reports', 'Progress report format for administrators', 'product', 'blocking'),
        ])
    if model in ('b2c_subscription', 'hybrid_b2c_b2b2c'):
        conditions.extend([
            ('vocabulary_corpus_hsk5', 'Vocabulary corpus at HSK 4-5 competitive threshold', 'content', 'blocking'),
            ('activation_validated', 'First-session activation experience validated', 'ux', 'important'),
            ('pricing_infrastructure', 'Pricing page and subscription infrastructure', 'product', 'blocking'),
            ('ux_polish_benchmark', 'UX polish at HelloChinese benchmark on key flows', 'ux', 'important'),
        ])

    for name, desc, ctype, priority in conditions:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO pi_commercial_readiness
                (id, thesis_id, revenue_model, condition_name, condition_description,
                 condition_type, current_status, priority)
                VALUES (?, ?, ?, ?, ?, ?, 'not_assessed', ?)
            """, (str(uuid.uuid4()), thesis_id, model, name, desc, ctype, priority))
        except sqlite3.IntegrityError:
            pass
    conn.commit()


def _assess_commercial_readiness(conn, thesis) -> list:
    findings = []
    conditions = _safe_query_all(conn, """
        SELECT * FROM pi_commercial_readiness
        WHERE thesis_id = ? AND current_status != 'met' AND priority = 'blocking'
        ORDER BY condition_type
    """, (thesis['id'],))

    if conditions:
        findings.append(_make_strategic_finding(
            priority='P0',
            title=f'{len(conditions)} blocking condition(s) unmet for {thesis["revenue_model"]}',
            implication='Cannot charge money until these are resolved. Everything else is secondary.',
            detail='\n'.join(f'- {c["condition_name"]}: {c["condition_description"]}' for c in conditions),
            action='Address blocking conditions in priority order.',
        ))
    return findings


def _analyze_critical_path_gaps(conn, thesis) -> list:
    findings = []
    critical_gaps = _safe_query_all(conn, """
        SELECT * FROM pi_evaluation_dimensions
        WHERE on_critical_path = 1 AND gap > 2 AND gap_closeable = 1
        ORDER BY weight DESC, gap DESC
    """)

    for gap in critical_gaps[:3]:
        cost = gap['closing_cost']
        findings.append(_make_strategic_finding(
            priority='P1' if cost in ('low', 'medium') else 'P2',
            title=f'Critical path gap: {gap["dimension_name"]} (Aelu: {gap["aelu_current_score"]}/10, best: {gap["best_in_class_score"]}/10)',
            implication=f'Gap of {gap["gap"]} on {gap["weight"]}x-weighted dimension. '
                        f'{"On critical path." if gap["on_critical_path"] else ""}',
            detail=f'Closing cost: {cost}. Target: {gap["aelu_target_score"]}. Best: {gap["best_in_class_competitor"]}.',
            action=f'Close {gap["dimension_name"]} gap before non-critical dimensions.',
        ))
    return findings


def _check_disconfirming_condition(conn, condition: str) -> dict | None:
    """Check if a disconfirming condition can be assessed from data. Returns None if no data."""
    condition_lower = condition.lower()

    if 'activation rate' in condition_lower and 'below 40%' in condition_lower:
        activation = _safe_scalar(conn, """
            SELECT conversion_signup_to_activation FROM pi_funnel_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
        """, default=None)
        if activation is not None and activation < 0.40:
            return {'disconfirmed': True, 'detail': f'Activation rate is {activation:.0%}, below 40% threshold.'}

    if 'no budget' in condition_lower or 'no authority' in condition_lower:
        # Cannot assess from data alone
        return None

    return None


def _stress_test_thesis(conn, thesis) -> list:
    findings = []
    disconfirming = json.loads(thesis['disconfirming_conditions'] or '[]')

    for condition in disconfirming:
        evidence = _check_disconfirming_condition(conn, condition)
        if evidence and evidence.get('disconfirmed'):
            findings.append(_make_strategic_finding(
                priority='P0',
                title='Thesis stress test: disconfirming evidence detected',
                implication=f'Current commercial thesis may need revision. Condition: {condition}',
                detail=f'Evidence: {evidence["detail"]}',
                action='Review thesis. Revise if disconfirming evidence is valid.',
            ))
    return findings


def _check_monetization_timeline(conn, thesis) -> list:
    findings = []
    if not thesis['estimated_months_to_monetization']:
        return findings

    met = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_commercial_readiness
        WHERE thesis_id = ? AND current_status = 'met'
    """, (thesis['id'],), default=0)

    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_commercial_readiness WHERE thesis_id = ?
    """, (thesis['id'],), default=0)

    if total > 0:
        rate = met / total
        if rate < 0.30 and thesis['estimated_months_to_monetization'] <= 3:
            findings.append(_make_strategic_finding(
                priority='P1',
                title=f'Monetization timeline at risk: {rate:.0%} conditions met, {thesis["estimated_months_to_monetization"]}mo target',
                implication='At current pace, monetization timeline will slip.',
                detail=f'{met} of {total} commercial readiness conditions met.',
                action='Reprioritize development toward monetization requirements.',
            ))
    return findings


def run_strategist(conn) -> list:
    """Primary strategic analysis. Runs every audit cycle."""
    findings = []

    active_thesis = _safe_query(conn, """
        SELECT * FROM pi_strategic_theses WHERE status = 'active'
        ORDER BY version DESC LIMIT 1
    """)

    if not active_thesis:
        thesis_data = derive_strategic_thesis(conn)
        thesis_id = str(uuid.uuid4())
        try:
            conn.execute("""
                INSERT INTO pi_strategic_theses
                (id, version, status, target_user, value_proposition,
                 revenue_model, price_point_rationale, primary_moat,
                 key_assumptions, disconfirming_conditions, confirming_conditions,
                 monetization_blockers, estimated_months_to_monetization,
                 confidence_score, confidence_rationale)
                VALUES (?,1,'active',?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                thesis_id,
                thesis_data['target_user'],
                thesis_data['value_proposition'],
                thesis_data['revenue_model'],
                thesis_data['price_point_rationale'],
                thesis_data['primary_moat'],
                thesis_data['key_assumptions'],
                thesis_data['disconfirming_conditions'],
                thesis_data['confirming_conditions'],
                thesis_data['monetization_blockers'],
                thesis_data['estimated_months_to_monetization'],
                thesis_data['confidence_score'],
                thesis_data['confidence_rationale'],
            ))
            conn.commit()

            _seed_commercial_readiness(conn, thesis_id, thesis_data['revenue_model'])

            active_thesis = conn.execute(
                "SELECT * FROM pi_strategic_theses WHERE id = ?", (thesis_id,)
            ).fetchone()
        except sqlite3.Error as e:
            logger.warning("Thesis creation failed: %s", e)
            return findings

        findings.append(_make_strategic_finding(
            priority='P0',
            title='Commercial thesis derived — review and validate',
            implication='This is the engine\'s best derivation of what Aelu should be and how to monetize.',
            detail=f'Model: {thesis_data["revenue_model"]}. Confidence: {thesis_data["confidence_score"]:.0%}.',
            action='Review thesis in strategic admin panel. Override any incorrect component.',
        ))

    if active_thesis:
        findings.extend(_assess_commercial_readiness(conn, active_thesis))
        findings.extend(_analyze_critical_path_gaps(conn, active_thesis))
        findings.extend(_stress_test_thesis(conn, active_thesis))
        findings.extend(_check_monetization_timeline(conn, active_thesis))

    return findings


# ── Part 3: The Editorial Critic ───────────────────────────────────────────

def _run_editorial_critic(conn, content_text: str, content_context: str, content_type: str) -> dict:
    """Score content against editorial standard. Uses Qwen if available, else conservative defaults."""
    try:
        from ..ai.ollama_client import generate, is_ollama_available
        if is_ollama_available():
            standard_desc = '\n'.join(
                f'- {dim} (weight {s["weight"]}x): {s["description"]}'
                for dim, s in EDITORIAL_STANDARD.items()
            )
            prompt = (
                f"You are an editorial critic calibrated against Chairman's Bao and Mandarin Corner.\n"
                f"Grade harshly. 70+ = genuinely good. 50 = adequate but forgettable. <40 = fails.\n\n"
                f"Type: {content_type}\nContext: {content_context}\n"
                f"Content:\n{content_text[:800]}\n\n"
                f"Standard:\n{standard_desc}\n\n"
                f"Return ONLY JSON:\n"
                f'{{"specificity": <1-100>, "adult_assumption": <1-100>, '
                f'"world_revealing": <1-100>, "finish_pull": <1-100>, '
                f'"language_density": <1-100>}}'
            )
            resp = generate(prompt=prompt, temperature=0.2, max_tokens=200,
                            conn=conn, task_type="editorial_critic")
            if resp.success:
                import re
                cleaned = re.sub(r'```json|```', '', resp.text).strip()
                data = json.loads(cleaned)
                return {dim: int(data.get(dim, 60)) for dim in EDITORIAL_STANDARD}
    except (ImportError, json.JSONDecodeError, Exception) as e:
        logger.debug("Editorial critic LLM unavailable: %s", e)

    # Conservative defaults when no LLM
    return {dim: 60 for dim in EDITORIAL_STANDARD}


def assess_editorial_quality(conn, content_item_id: str) -> dict:
    """Assess content quality on editorial dimensions."""
    item = _safe_query(conn, """
        SELECT id, hanzi, english, item_type FROM content_item WHERE id = ?
    """, (content_item_id,))

    if not item:
        return {'error': 'not_found'}

    content_text = item['hanzi'] or ''
    if not content_text:
        return {'error': 'no_content'}

    content_type = item['item_type'] or 'vocabulary'
    content_context = f'{content_type}: {item["english"] or ""}'

    scores = _run_editorial_critic(conn, content_text, content_context, content_type)

    # Weighted overall
    total_weight = sum(s['weight'] for s in EDITORIAL_STANDARD.values())
    weighted = sum(scores.get(dim, 50) * EDITORIAL_STANDARD[dim]['weight']
                   for dim in EDITORIAL_STANDARD)
    overall = weighted / total_weight if total_weight else 50

    # Bottom quartile: below 55 overall or below 40 on 3x-weight dimension
    high_weight = [d for d, s in EDITORIAL_STANDARD.items() if s['weight'] >= 3.0]
    fails_high = any(scores.get(d, 50) < 40 for d in high_weight)
    bottom_quartile = overall < 55 or fails_high

    return {
        'content_item_id': content_item_id,
        'overall_editorial_score': round(overall, 1),
        'dimension_scores': scores,
        'bottom_quartile': bottom_quartile,
        'worst_dimension': min(scores, key=scores.get) if scores else None,
    }


def analyze_editorial_corpus(conn) -> list:
    """Assess editorial quality across content corpus."""
    findings = []

    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item WHERE status = 'drill_ready'
    """, default=0)

    if total < 10:
        return findings

    # Use context_notes or hanzi length as proxy for content depth
    short_content = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE status = 'drill_ready' AND length(hanzi) < 4
    """, default=0)

    if total > 0 and short_content / total > 0.80:
        findings.append(_make_strategic_finding(
            priority='P1',
            title=f'Content corpus is {short_content}/{total} single-word items',
            implication=(
                'If the thesis is "depth and seriousness," a corpus of mostly '
                'isolated vocabulary items undermines it. Serious learners need passages.'
            ),
            detail=f'{short_content} of {total} drill-ready items are short vocabulary entries.',
            action='Expand content beyond vocabulary to passages, dialogues, and listening items.',
        ))

    return findings


# ── Part 4: The Competitor ─────────────────────────────────────────────────

def run_competitor_analysis(conn) -> list:
    """Competitive findings with strategic implications. Grades Aelu harshly."""
    findings = []

    dimensions = _safe_query_all(conn, """
        SELECT * FROM pi_evaluation_dimensions ORDER BY weight DESC, gap DESC
    """)

    # High-weight dimensions where Aelu significantly lags
    for dim in dimensions:
        gap = dim['gap'] or 0
        weight = dim['weight'] or 1.0
        aelu_score = dim['aelu_current_score'] or 0

        if gap >= 4 and weight >= 2.5:
            findings.append(_make_strategic_finding(
                priority='P1' if dim['on_critical_path'] else 'P2',
                title=f'Competitive deficit: {dim["dimension_name"]} — Aelu {aelu_score}/10 vs {dim["best_in_class_competitor"]} {dim["best_in_class_score"]}/10',
                implication=f'Gap of {gap} on {weight}x-weighted dimension. '
                            f'{"On critical path." if dim["on_critical_path"] else "Not blocking monetization."}',
                detail=f'Closing cost: {dim["closing_cost"]}. Target: {dim["aelu_target_score"]}.',
                action=f'Close {dim["dimension_name"]} gap.',
            ))

    # Dimensions where Aelu leads — protect these
    leads = [d for d in dimensions if (d['gap'] or 0) < 0]
    if leads:
        lead_names = [d['dimension_name'] for d in leads]
        findings.append(_make_strategic_finding(
            priority='P2',
            title=f'Competitive advantages to protect: {", ".join(lead_names)}',
            implication='These are Aelu\'s genuine differentiators. Protect them.',
            detail='No competitor currently matches Aelu on these dimensions.',
            action='Ensure roadmap investments maintain and extend these leads.',
        ))

    # Stale competitive data
    stale = _safe_query_all(conn, """
        SELECT name FROM pi_competitors
        WHERE last_assessed_at < date('now', '-90 days') OR last_assessed_at IS NULL
    """)
    if stale:
        findings.append(_make_strategic_finding(
            priority='P2',
            title=f'Competitive data stale for {len(stale)} competitor(s)',
            implication='Strategy based on stale data produces wrong priorities.',
            detail=', '.join(r['name'] for r in stale),
            action='Run competitive research update.',
        ))

    # Unaddressed competitive signals
    signals = _safe_query_all(conn, """
        SELECT * FROM pi_competitive_signals
        WHERE requires_aelu_response = 1 AND response_logged_at IS NULL
          AND detected_at >= datetime('now', '-60 days')
    """)
    if signals:
        findings.append(_make_strategic_finding(
            priority='P1',
            title=f'{len(signals)} competitive signal(s) requiring response',
            implication='Unaddressed competitive moves compound.',
            detail='\n'.join(f'- {s["signal_description"]}' for s in signals),
            action='Review signals and log response decision for each.',
        ))

    return findings


# ── Thesis Revision ────────────────────────────────────────────────────────

def revise_thesis(conn, old_thesis_id: str, revision_trigger: str) -> str:
    """Create a new thesis version superseding the old one. Returns new thesis ID."""
    thesis_data = derive_strategic_thesis(conn)
    new_id = str(uuid.uuid4())

    # Get current version
    old = conn.execute("SELECT version FROM pi_strategic_theses WHERE id = ?",
                       (old_thesis_id,)).fetchone()
    new_version = (old['version'] + 1) if old else 1

    conn.execute("""
        UPDATE pi_strategic_theses SET status = 'superseded', superseded_by = ?
        WHERE id = ?
    """, (new_id, old_thesis_id))

    conn.execute("""
        INSERT INTO pi_strategic_theses
        (id, version, status, target_user, value_proposition,
         revenue_model, price_point_rationale, primary_moat,
         key_assumptions, disconfirming_conditions, confirming_conditions,
         monetization_blockers, estimated_months_to_monetization,
         confidence_score, confidence_rationale, revision_trigger)
        VALUES (?,?,'active',?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        new_id, new_version,
        thesis_data['target_user'], thesis_data['value_proposition'],
        thesis_data['revenue_model'], thesis_data['price_point_rationale'],
        thesis_data['primary_moat'], thesis_data['key_assumptions'],
        thesis_data['disconfirming_conditions'], thesis_data['confirming_conditions'],
        thesis_data['monetization_blockers'],
        thesis_data['estimated_months_to_monetization'],
        thesis_data['confidence_score'], thesis_data['confidence_rationale'],
        revision_trigger,
    ))

    _seed_commercial_readiness(conn, new_id, thesis_data['revenue_model'])
    conn.commit()
    return new_id


# ── Analyzer Registry ──────────────────────────────────────────────────────

ANALYZERS = [
    run_strategist,
    analyze_editorial_corpus,
    run_competitor_analysis,
]
