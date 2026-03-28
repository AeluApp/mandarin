"""Product Intelligence — Output production, tone drill quality, tutor integration (Doc 8).

Three analyzer families:
A) Tone drill quality — coverage gaps, sandhi proportion, transfer gap
B) Output production — text-based productive drill grading cascade
C) Tutor integration — logging, auto-matching corrections to SRS items
"""

import logging
import sqlite3
import subprocess

from ._base import _finding, _safe_query_all, _safe_scalar, _f

logger = logging.getLogger(__name__)


# ── Part A: Tone Drill Quality ──────────────────────────────────────────────

_TONE_DRILL_TYPES = ("tone", "tone_sandhi", "minimal_pair", "listening_tone")
_ISOLATED_TONE_TYPES = ("tone", "minimal_pair")
_CONTEXTUAL_TONE_TYPES = ("tone_sandhi", "listening_tone")


def _compute_tone_coverage(conn, days=30):
    """Query review_event for tone drill types, return counts per type + totals."""
    counts = {}
    total = 0
    for dt in _TONE_DRILL_TYPES:
        n = _safe_scalar(conn, """
            SELECT COUNT(*) FROM review_event
            WHERE drill_type = ? AND created_at >= datetime('now', ?)
        """, (dt, f"-{days} days"))
        counts[dt] = n
        total += n
    counts["total"] = total
    return counts


def _compute_tone_transfer(conn, days=30):
    """Compute accuracy gap between isolated and contextual tone drills."""
    isolated_correct = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('tone', 'minimal_pair')
          AND correct = 1
          AND created_at >= datetime('now', ?)
    """, (f"-{days} days",))
    isolated_total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('tone', 'minimal_pair')
          AND created_at >= datetime('now', ?)
    """, (f"-{days} days",))

    contextual_correct = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('tone_sandhi', 'listening_tone')
          AND correct = 1
          AND created_at >= datetime('now', ?)
    """, (f"-{days} days",))
    contextual_total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('tone_sandhi', 'listening_tone')
          AND created_at >= datetime('now', ?)
    """, (f"-{days} days",))

    isolated_acc = (isolated_correct / isolated_total * 100) if isolated_total > 0 else None
    contextual_acc = (contextual_correct / contextual_total * 100) if contextual_total > 0 else None

    transfer_gap = None
    if isolated_acc is not None and contextual_acc is not None:
        transfer_gap = isolated_acc - contextual_acc

    return {
        "isolated_accuracy": isolated_acc,
        "contextual_accuracy": contextual_acc,
        "transfer_gap": transfer_gap,
        "isolated_total": isolated_total,
        "contextual_total": contextual_total,
    }


def analyze_tone_drill_quality(conn):
    """Analyze tone drill coverage, sandhi proportion, and transfer gap."""
    findings = []
    coverage = _compute_tone_coverage(conn)
    transfer = _compute_tone_transfer(conn)

    total = coverage.get("total", 0)

    # Sandhi proportion < 10%
    if total > 0:
        sandhi_count = coverage.get("tone_sandhi", 0)
        sandhi_pct = sandhi_count / total * 100
        if sandhi_pct < 10:
            findings.append(_finding(
                "tone_phonology", "high",
                "Sandhi drills underrepresented",
                f"Tone sandhi drills are only {sandhi_pct:.1f}% of tone practice "
                f"({sandhi_count}/{total}). Sandhi rules are critical for natural speech.",
                "Increase tone_sandhi drill proportion to at least 10% of tone practice.",
                "Adjust scheduler to boost tone_sandhi drill selection weight.",
                "Better sandhi accuracy in conversation",
                _f("scheduler"),
            ))

    # Transfer gap > 15 points
    gap = transfer.get("transfer_gap")
    if gap is not None and gap > 15:
        findings.append(_finding(
            "tone_phonology", "high",
            "Tone transfer gap: isolated vs contextual",
            f"Isolated tone accuracy ({transfer['isolated_accuracy']:.1f}%) is "
            f"{gap:.1f} points higher than contextual ({transfer['contextual_accuracy']:.1f}%). "
            f"Learner can identify tones in isolation but struggles in context.",
            "Add more contextual tone drills (sandhi pairs, listening in sentences).",
            "Add contextual tone scaffolding drills that bridge isolated → sentence-level.",
            "Close the isolated-to-contextual transfer gap",
            _f("drills", "scheduler"),
        ))

    # Total tone drills < 20 in 30d — nudge
    if total < 20:
        findings.append(_finding(
            "tone_phonology", "low",
            "Low tone drill volume",
            f"Only {total} tone drills in the last 30 days. "
            f"Minimum recommended is 20 for meaningful tone improvement.",
            "Schedule more tone-focused drills.",
            "Increase tone drill frequency in the scheduler.",
            "More consistent tone practice",
            _f("scheduler"),
        ))

    return findings


# ── Part B: Output Production ────────────────────────────────────────────────

_PRODUCTION_DRILL_TYPES = ("translation", "sentence_build", "word_order", "ime_type")
_RECOGNITION_DRILL_TYPES = ("mc", "reverse_mc")


def _compute_character_similarity(expected, user_input):
    """Character-level similarity: Jaccard + position-weighted (0-1).

    Returns 0.0 for empty strings, 1.0 for identical strings.
    """
    if not expected and not user_input:
        return 0.0
    if not expected or not user_input:
        return 0.0
    if expected == user_input:
        return 1.0

    # Jaccard similarity on character sets
    set_e = set(expected)
    set_u = set(user_input)
    intersection = set_e & set_u
    union = set_e | set_u
    jaccard = len(intersection) / len(union) if union else 0.0

    # Position-weighted: how many characters match at the same position
    max_len = max(len(expected), len(user_input))
    position_matches = sum(
        1 for i in range(min(len(expected), len(user_input)))
        if expected[i] == user_input[i]
    )
    position_score = position_matches / max_len if max_len > 0 else 0.0

    # Blend: 50/50
    return (jaccard + position_score) / 2


def grade_output_response(user_response, expected, acceptable_variants=None, conn=None):
    """Grade a text production response using a cascade.

    Returns dict with: is_correct, score, method, feedback
    Cascade: exact match → char similarity ≥ 0.90 → variant → Qwen semantic → fallback
    """
    # Normalize whitespace
    user_clean = user_response.strip()
    expected_clean = expected.strip()

    # 1. Exact match
    if user_clean == expected_clean:
        return {
            "is_correct": True,
            "score": 1.0,
            "method": "exact_match",
            "feedback": None,
        }

    # 2. Character similarity
    sim = _compute_character_similarity(expected_clean, user_clean)
    if sim >= 0.90:
        return {
            "is_correct": True,
            "score": sim,
            "method": "character_similarity",
            "feedback": f"Close match ({sim:.0%} similar). Expected: {expected_clean}",
        }

    # 3. Variant match
    if acceptable_variants:
        for variant in acceptable_variants:
            if user_clean == variant.strip():
                return {
                    "is_correct": True,
                    "score": 1.0,
                    "method": "variant_match",
                    "feedback": None,
                }

    # 4. Qwen semantic (if ollama available)
    qwen_result = _try_qwen_semantic(user_clean, expected_clean)
    if qwen_result is not None:
        return qwen_result

    # 5. Fallback — use character similarity score
    return {
        "is_correct": sim >= 0.70,
        "score": sim,
        "method": "fallback",
        "feedback": f"Expected: {expected_clean}",
    }


def _try_qwen_semantic(user_input, expected):
    """Try Qwen via ollama for semantic equivalence check. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["ollama", "run", "qwen2.5:7b",
             f"Are these two Chinese sentences semantically equivalent? "
             f"Answer only 'yes' or 'no'.\n"
             f"Sentence A: {expected}\n"
             f"Sentence B: {user_input}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            answer = result.stdout.strip().lower()
            if "yes" in answer:
                return {
                    "is_correct": True,
                    "score": 0.85,
                    "method": "qwen_semantic",
                    "feedback": "Semantically equivalent (different wording accepted).",
                }
            elif "no" in answer:
                return {
                    "is_correct": False,
                    "score": 0.3,
                    "method": "qwen_semantic",
                    "feedback": f"Not semantically equivalent. Expected: {expected}",
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def analyze_output_production(conn):
    """Analyze output production vs recognition gap and output drill ratio."""
    findings = []

    # Production accuracy
    prod_correct = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('translation', 'sentence_build', 'word_order', 'ime_type')
          AND correct = 1
          AND created_at >= datetime('now', '-30 days')
    """)
    prod_total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('translation', 'sentence_build', 'word_order', 'ime_type')
          AND created_at >= datetime('now', '-30 days')
    """)

    # Recognition accuracy
    rec_correct = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('mc', 'reverse_mc')
          AND correct = 1
          AND created_at >= datetime('now', '-30 days')
    """)
    rec_total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('mc', 'reverse_mc')
          AND created_at >= datetime('now', '-30 days')
    """)

    prod_acc = (prod_correct / prod_total * 100) if prod_total > 0 else None
    rec_acc = (rec_correct / rec_total * 100) if rec_total > 0 else None

    # Production-recognition gap > 20pt
    if prod_acc is not None and rec_acc is not None:
        gap = rec_acc - prod_acc
        if gap > 20:
            findings.append(_finding(
                "output_production", "medium",
                "Production-recognition gap",
                f"Recognition accuracy ({rec_acc:.1f}%) exceeds production ({prod_acc:.1f}%) "
                f"by {gap:.1f} points. Learner can recognize but struggles to produce.",
                "Increase production drill proportion to narrow the gap.",
                "Boost production drill types (translation, sentence_build) in scheduler.",
                "Better active recall and production ability",
                _f("scheduler", "drills"),
            ))

    # Output ratio < 15% of all review_events
    total_reviews = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE created_at >= datetime('now', '-30 days')
    """)
    if total_reviews > 0 and prod_total is not None:
        output_ratio = prod_total / total_reviews * 100
        if output_ratio < 15:
            findings.append(_finding(
                "output_production", "low",
                "Low output drill ratio",
                f"Only {output_ratio:.1f}% of drills are production-type "
                f"({prod_total}/{total_reviews}). Aim for at least 15%.",
                "Schedule more production drills.",
                "Increase production drill weight in scheduler configuration.",
                "Balanced skill development",
                _f("scheduler"),
            ))

    return findings


# ── Part C: Tutor Integration ────────────────────────────────────────────────

def process_tutor_session(conn, session_id):
    """Process a tutor session: match corrections to content_items, create encounters.

    Sets tutor_corrected=1 and increments tutor_correction_count on matched items.
    Creates vocab_encounter entries for flagged vocabulary.
    Marks session as processed=1.
    """
    # Get corrections for this session
    corrections = _safe_query_all(conn, """
        SELECT id, correct_form, wrong_form FROM tutor_corrections
        WHERE tutor_session_id = ?
    """, (session_id,))

    matched = 0
    for corr in (corrections or []):
        corr_id, correct_form, _wrong_form = corr[0], corr[1], corr[2]
        # Try to match by hanzi
        item = conn.execute("""
            SELECT id FROM content_item WHERE hanzi = ? LIMIT 1
        """, (correct_form,)).fetchone()
        if item:
            item_id = item[0]
            conn.execute("""
                UPDATE tutor_corrections
                SET linked_content_item_id = ?, added_to_srs = 1
                WHERE id = ?
            """, (item_id, corr_id))
            conn.execute("""
                UPDATE content_item
                SET tutor_corrected = 1,
                    tutor_correction_count = tutor_correction_count + 1
                WHERE id = ?
            """, (item_id,))
            matched += 1

    # Process vocabulary flags
    flags = _safe_query_all(conn, """
        SELECT id, hanzi FROM tutor_vocabulary_flags
        WHERE tutor_session_id = ?
    """, (session_id,))

    for flag in (flags or []):
        flag_id, hanzi = flag[0], flag[1]
        # Try to match
        item = conn.execute("""
            SELECT id FROM content_item WHERE hanzi = ? LIMIT 1
        """, (hanzi,)).fetchone()
        if item:
            item_id = item[0]
            conn.execute("""
                UPDATE tutor_vocabulary_flags
                SET linked_content_item_id = ?, added_to_srs = 1
                WHERE id = ?
            """, (item_id, flag_id))
            conn.execute("""
                UPDATE content_item SET tutor_flagged = 1 WHERE id = ?
            """, (item_id,))

        # Create vocab_encounter regardless of match
        try:
            content_item_id = item[0] if item else None
            conn.execute("""
                INSERT INTO vocab_encounter
                    (content_item_id, hanzi, source_type, source_id, looked_up, created_at)
                VALUES (?, ?, 'tutor', ?, 0, datetime('now'))
            """, (content_item_id, hanzi, session_id))
        except sqlite3.Error:
            pass

    # Mark processed
    conn.execute("UPDATE tutor_sessions SET processed = 1 WHERE id = ?", (session_id,))
    conn.commit()

    return {"matched_corrections": matched, "flags_processed": len(flags or [])}


def analyze_tutor_integration(conn):
    """Analyze tutor session coverage and corrected item performance."""
    findings = []

    total_sessions = _safe_scalar(conn, """
        SELECT COUNT(*) FROM tutor_sessions WHERE user_id = 1
    """)
    last_session = _safe_scalar(conn, """
        SELECT MAX(session_date) FROM tutor_sessions WHERE user_id = 1
    """, default=None)

    # No sessions ever — gentle nudge
    if total_sessions == 0:
        findings.append(_finding(
            "tutor_integration", "low",
            "No tutor sessions logged",
            "No external tutor sessions have been recorded. "
            "Logging tutor corrections helps the SRS prioritize problem areas.",
            "Log your next tutor session to get targeted SRS boosts.",
            "Add tutor session logging UI or CLI command.",
            "Better SRS targeting from tutor feedback",
            _f("routes"),
        ))
        return findings

    # No sessions in 21+ days
    if last_session:
        days_since = _safe_scalar(conn, """
            SELECT CAST(julianday('now') - julianday(?) AS INTEGER)
        """, (last_session,))
        if days_since and days_since > 21:
            findings.append(_finding(
                "tutor_integration", "medium",
                "No recent tutor sessions",
                f"Last tutor session was {days_since} days ago. "
                f"Regular tutor feedback improves SRS targeting.",
                "Schedule a tutor session and log corrections.",
                "Consider tutor session reminders in the engagement system.",
                "Fresher tutor correction data for SRS",
                _f("scheduler"),
            ))

    # Corrected items performing < 60% accuracy
    corrected_acc = _safe_scalar(conn, """
        SELECT AVG(CASE WHEN re.correct = 1 THEN 100.0 ELSE 0.0 END)
        FROM review_event re
        JOIN content_item ci ON re.content_item_id = ci.id
        WHERE ci.tutor_corrected = 1
          AND re.created_at >= datetime('now', '-30 days')
    """, default=None)

    if corrected_acc is not None and corrected_acc < 60:
        findings.append(_finding(
            "tutor_integration", "medium",
            "Tutor-corrected items still struggling",
            f"Items flagged by tutor corrections have {corrected_acc:.1f}% accuracy "
            f"(target: 60%+). The SRS boost may not be sufficient.",
            "Increase priority boost for tutor-corrected items or add targeted drills.",
            "Raise srs_priority_boost for tutor corrections, add focused review sessions.",
            "Tutor corrections actually lead to mastery",
            _f("scheduler"),
        ))

    return findings


# ── Exported ANALYZERS list ──────────────────────────────────────────────────

ANALYZERS = [analyze_tone_drill_quality, analyze_output_production, analyze_tutor_integration]
