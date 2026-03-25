"""FSRS-compatible memory model for Aelu (Doc 13).

Implements stability/retrievability state tracking, interference detection,
interleaving, cognitive load management, and memory model health analysis.

Zero Claude tokens at runtime — FSRS computations are purely deterministic.
LLM calls (interference detection via Qwen) are gated on is_ollama_available().
"""

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone, timedelta, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FSRS CORE PARAMETERS
# Default FSRS-5 parameters from the paper.
# Calibrated per-learner after 200+ reviews.
# ─────────────────────────────────────────────

FSRS_DEFAULTS = {
    "w": [
        0.4072, 1.1829, 3.1262, 15.4722,
        7.2102, 0.5316, 1.0651, 0.0589,
        1.4769, 0.1480, 1.0540, 1.9241,
        0.1011, 0.2900, 2.2700, 0.2500,
        2.9898,
    ],
    "request_retention": 0.90,
    "maximum_interval": 365,
}

# Rating scale (maps to FSRS grades)
RATING_AGAIN = 1  # Forgot — item enters relearning
RATING_HARD = 2   # Recalled with significant effort
RATING_GOOD = 3   # Recalled correctly
RATING_EASY = 4   # Recalled with zero effort


# ─────────────────────────────────────────────
# RETRIEVABILITY COMPUTATION
# ─────────────────────────────────────────────

def compute_retrievability(stability: float, elapsed_days: float) -> float:
    """FSRS formula: R = (1 + elapsed_days / (9 * stability)) ^ -1"""
    if elapsed_days <= 0:
        return 1.0
    if stability <= 0:
        return 0.0
    return math.pow(1 + elapsed_days / (9 * stability), -1)


def compute_next_interval(stability: float, target_retention: float = 0.90) -> int:
    """Optimal next review interval for target retention probability. Returns days."""
    if stability <= 0 or target_retention >= 1.0 or target_retention <= 0:
        return 1
    interval = stability * 9 * (1 / target_retention - 1)
    return max(1, round(interval))


# ─────────────────────────────────────────────
# DESIRABLE DIFFICULTY (Bjork & Bjork 2011)
# ─────────────────────────────────────────────

def desirable_difficulty_adjustment(stability: float, retrievability: float) -> dict:
    """Apply Bjork's desirable difficulty principles to FSRS scheduling.

    Desirable difficulties are encoding conditions that slow initial learning
    but improve long-term retention.  The optimal retrieval zone is 70-85%
    retrievability -- hard enough to strengthen memory, not so hard that
    retrieval fails entirely (Bjork & Bjork 2011, Kornell & Bjork 2008).

    Key insight from the research: hints REDUCE difficulty, which contradicts
    the goal.  For hard items we maintain the challenge but switch to
    recognition drills (lower production demand, same retrieval effort).

    Returns adjustment dict:
        interval_multiplier: float -- scale factor for the computed interval
        drill_type_override: str | None -- force drill type change
        context_variation: bool -- use different context for mastered items
    """
    result = {
        "interval_multiplier": 1.0,
        "drill_type_override": None,
        "context_variation": False,
    }

    try:
        # Zone 1: Too easy (R > 0.95) -- item is over-practiced
        # Bjork: "conditions that make performance appear smooth and steady
        # often fail to support long-term retention"
        # Fix: schedule earlier AND force production (harder retrieval)
        if retrievability > 0.95:
            result["interval_multiplier"] = 0.75  # 25% shorter interval
            if stability > 7:
                result["drill_type_override"] = "production"

        # Zone 2: Optimal difficulty (0.70-0.85) -- Bjork's sweet spot
        # Leave FSRS interval alone -- this is where learning happens
        elif 0.70 <= retrievability <= 0.85:
            pass  # no adjustment

        # Zone 3: Slightly easy (0.85-0.95) -- could be harder
        elif 0.85 < retrievability < 0.95:
            result["interval_multiplier"] = 0.90  # 10% shorter

        # Zone 4: Hard but productive (0.50-0.70)
        # This IS desirable difficulty -- do NOT add hints.
        # Switch to recognition drill so retrieval still succeeds
        # but requires effortful memory search.
        elif 0.50 <= retrievability < 0.70:
            result["drill_type_override"] = "recognition"

        # Zone 5: Too hard (R < 0.50) -- retrieval will likely fail
        # Shorten interval so next review is sooner; use recognition
        elif retrievability < 0.50:
            result["interval_multiplier"] = 0.60
            result["drill_type_override"] = "recognition"

        # Mastered items (stability > 30 days): contextual variation
        # Slamecka & Graf 1978 "generation effect"
        if stability > 30:
            result["drill_type_override"] = "production"
            result["context_variation"] = True
        elif stability > 14 and result["drill_type_override"] is None:
            result["drill_type_override"] = "production"

    except (TypeError, ValueError):
        pass

    return result


# ─────────────────────────────────────────────
# STABILITY UPDATE
# ─────────────────────────────────────────────

def update_stability_after_review(
    current_stability: float,
    current_difficulty: float,
    current_retrievability: float,
    rating: int,
    state: str,
    w: list = None,
) -> float:
    """FSRS stability update. Different formulas for each state."""
    if w is None:
        w = FSRS_DEFAULTS["w"]

    if state in ("new", "learning"):
        return _stability_for_new_card(rating, w)
    elif state == "review":
        if rating == RATING_AGAIN:
            return _stability_after_lapse(current_stability, current_difficulty,
                                          current_retrievability, w)
        else:
            return _stability_after_recall(current_stability, current_difficulty,
                                           current_retrievability, rating, w)
    elif state == "relearning":
        return _stability_after_relearning(current_stability, rating, w)
    return current_stability


def _stability_for_new_card(rating: int, w: list) -> float:
    return max(0.1, w[rating - 1])


def _stability_after_recall(s: float, d: float, r: float, rating: int, w: list) -> float:
    hard_penalty = w[15] if rating == RATING_HARD else 1.0
    easy_bonus = w[16] if rating == RATING_EASY else 1.0
    return s * (
        math.exp(w[8]) *
        (11 - d) *
        math.pow(s, -w[9]) *
        (math.exp(w[10] * (1 - r)) - 1) *
        hard_penalty *
        easy_bonus
    )


def _stability_after_lapse(s: float, d: float, r: float, w: list) -> float:
    return max(
        w[11],
        w[11] * math.pow(s, -w[12]) * (math.exp(w[13] * (1 - r)) - 1)
    )


def _stability_after_relearning(s: float, rating: int, w: list) -> float:
    idx = min(16, len(w) - 1)
    return max(w[11], s * math.exp(w[idx] * (rating - 3 + w[7])))


def update_difficulty(current_difficulty: float, rating: int, w: list = None) -> float:
    """Item-specific, learner-specific difficulty. Range [1.0, 10.0]."""
    if w is None:
        w = FSRS_DEFAULTS["w"]
    delta_d = -w[6] * (rating - 3)
    new_d = current_difficulty + delta_d
    new_d = new_d + w[7] * (w[4] - new_d)
    return max(1.0, min(10.0, new_d))


# ─────────────────────────────────────────────
# REVIEW PROCESSING
# ─────────────────────────────────────────────

def process_review(
    conn: sqlite3.Connection,
    user_id: int,
    content_item_id: int,
    rating: int,
    response_ms: int = None,
) -> dict:
    """Process a learner review and update memory state.

    Called after every drill response. Updates stability, retrievability,
    difficulty, state, and next due date.
    """
    state_row = conn.execute(
        "SELECT * FROM memory_states WHERE user_id=? AND content_item_id=?",
        (user_id, content_item_id),
    ).fetchone()

    now = datetime.now(UTC)

    if not state_row:
        return _initialize_memory_state(conn, user_id, content_item_id, rating, now)

    state = dict(state_row)
    last_reviewed = (
        datetime.fromisoformat(state["last_reviewed_at"])
        if state["last_reviewed_at"] else now
    )
    # Handle naive datetimes from DB
    if last_reviewed.tzinfo is None:
        last_reviewed = last_reviewed.replace(tzinfo=UTC)
    elapsed_days = max(0, (now - last_reviewed).total_seconds() / 86400)

    current_r = compute_retrievability(state["stability"], elapsed_days)

    new_stability = update_stability_after_review(
        current_stability=state["stability"],
        current_difficulty=state["difficulty"],
        current_retrievability=current_r,
        rating=rating,
        state=state["state"],
    )
    new_difficulty = update_difficulty(state["difficulty"], rating)
    new_state = _next_state(state["state"], rating)

    if new_state == "relearning":
        next_days = 1
    else:
        next_days = min(
            compute_next_interval(new_stability),
            FSRS_DEFAULTS["maximum_interval"],
        )

        # Apply desirable difficulty adjustment (Bjork & Bjork 2011)
        try:
            dd = desirable_difficulty_adjustment(new_stability, current_r)
            if dd["interval_multiplier"] != 1.0:
                next_days = max(1, round(next_days * dd["interval_multiplier"]))
        except Exception:
            pass  # Graceful degradation

    next_due = now + timedelta(days=next_days)
    new_lapses = state["lapses"] + (
        1 if rating == RATING_AGAIN and state["state"] == "review" else 0
    )

    conn.execute("""
        UPDATE memory_states SET
            stability=?, retrievability=?, difficulty=?,
            state=?, last_reviewed_at=?, next_review_due=?,
            scheduled_days=?, reps=reps+1, lapses=?
        WHERE user_id=? AND content_item_id=?
    """, (
        new_stability, current_r, new_difficulty,
        new_state, now.isoformat(), next_due.isoformat(),
        next_days, new_lapses,
        user_id, content_item_id,
    ))

    return {
        "new_stability": new_stability,
        "new_difficulty": new_difficulty,
        "new_state": new_state,
        "next_review_days": next_days,
        "next_review_due": next_due.isoformat(),
        "retrievability_at_review": current_r,
    }


def _initialize_memory_state(conn, user_id, content_item_id, rating, now):
    initial_stability = FSRS_DEFAULTS["w"][rating - 1]
    initial_difficulty = FSRS_DEFAULTS["w"][4]
    next_days = 1 if rating == RATING_AGAIN else max(1, round(initial_stability))
    next_due = now + timedelta(days=next_days)

    conn.execute("""
        INSERT INTO memory_states
        (user_id, content_item_id, stability, retrievability, difficulty,
         state, last_reviewed_at, next_review_due, scheduled_days, reps)
        VALUES (?,?,?,?,?,'learning',?,?,?,1)
    """, (
        user_id, content_item_id,
        initial_stability, 0.0, initial_difficulty,
        now.isoformat(), next_due.isoformat(), next_days,
    ))

    return {
        "new_stability": initial_stability,
        "new_difficulty": initial_difficulty,
        "new_state": "learning",
        "next_review_days": next_days,
        "next_review_due": next_due.isoformat(),
        "retrievability_at_review": 0.0,
    }


def _next_state(current_state: str, rating: int) -> str:
    if current_state == "new":
        return "learning"
    if current_state == "learning":
        return "review" if rating >= RATING_GOOD else "learning"
    if current_state == "review":
        return "relearning" if rating == RATING_AGAIN else "review"
    if current_state == "relearning":
        return "review" if rating >= RATING_GOOD else "relearning"
    return current_state


# ─────────────────────────────────────────────
# INTERFERENCE DETECTION
# ─────────────────────────────────────────────

def detect_interference_pairs(conn: sqlite3.Connection) -> list[dict]:
    """Detect pairs of items with high interference risk.

    Uses embedding similarity (from genai_item_embeddings) and optionally
    Qwen analysis for homophones/visual similarity. Run nightly.
    """
    embedding_pairs = _detect_by_embedding(conn)

    known_pairs = {(p["item_id_a"], p["item_id_b"]) for p in embedding_pairs}
    qwen_pairs = _detect_by_qwen(conn, known_pairs)

    all_pairs = embedding_pairs + qwen_pairs
    _insert_interference_pairs(conn, all_pairs)
    return all_pairs


def _detect_by_embedding(conn: sqlite3.Connection, threshold: float = 0.88) -> list[dict]:
    """Flag item pairs with cosine similarity above threshold."""
    try:
        import numpy as np
    except ImportError:
        return []

    try:
        rows = conn.execute(
            "SELECT content_item_id, embedding FROM genai_item_embeddings"
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    if len(rows) < 2:
        return []

    ids = [r["content_item_id"] for r in rows]
    matrix = np.stack([
        np.frombuffer(r["embedding"], dtype="float32") for r in rows
    ])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = matrix / (norms + 1e-8)
    similarity = normalized @ normalized.T

    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if similarity[i, j] >= threshold:
                pairs.append({
                    "item_id_a": ids[i],
                    "item_id_b": ids[j],
                    "interference_type": "near_synonym",
                    "interference_strength": "high" if similarity[i, j] >= 0.95 else "medium",
                    "detected_by": "embedding_similarity",
                })
    return pairs


def _detect_by_qwen(conn: sqlite3.Connection, known_pairs: set) -> list[dict]:
    """Use Qwen for near-homophone and visual-similarity detection."""
    try:
        from .ollama_client import generate, is_ollama_available
    except ImportError:
        return []

    if not is_ollama_available():
        return []

    try:
        items = conn.execute("""
            SELECT id, hanzi, pinyin, english
            FROM content_item WHERE status='drill_ready' AND review_status='approved'
            ORDER BY RANDOM() LIMIT 50
        """).fetchall()
    except sqlite3.OperationalError:
        return []

    if len(items) < 2:
        return []

    item_list = json.dumps([dict(i) for i in items], ensure_ascii=False)

    prompt = f"""You are a Mandarin linguistics specialist.

Review these vocabulary items and identify pairs with HIGH interference risk:
{item_list}

Interference types to check:
- near_homophone: same or very similar pronunciation, different tone (e.g., 买/卖)
- visual_similarity: characters share components causing confusion (e.g., 土/士, 己/已/巳)
- near_synonym: very similar meaning in common contexts

Only report HIGH confidence pairs. Return JSON only:
{{
  "interference_pairs": [
    {{
      "item_id_a": <id>,
      "item_id_b": <id>,
      "interference_type": "<near_homophone|visual_similarity|near_synonym>",
      "interference_strength": "<high|medium>",
      "reason": "<brief explanation>"
    }}
  ]
}}"""

    result = generate(prompt, temperature=0.1, conn=conn, task_type="interference_detection")
    if not result.success:
        return []

    try:
        from .genai_layer import _parse_llm_json
        parsed = _parse_llm_json(result.text, conn=conn, task_type="interference_detection")
    except ImportError:
        try:
            parsed = json.loads(result.text)
        except (json.JSONDecodeError, ValueError):
            return []

    if not parsed:
        return []

    pairs = []
    for p in parsed.get("interference_pairs", []):
        pair_key = (p.get("item_id_a"), p.get("item_id_b"))
        rev_key = (p.get("item_id_b"), p.get("item_id_a"))
        if pair_key in known_pairs or rev_key in known_pairs:
            continue
        if p.get("item_id_a") and p.get("item_id_b"):
            pairs.append({
                "item_id_a": p["item_id_a"],
                "item_id_b": p["item_id_b"],
                "interference_type": p.get("interference_type", "near_synonym"),
                "interference_strength": p.get("interference_strength", "medium"),
                "detected_by": "qwen_analysis",
            })

    return pairs


def _insert_interference_pairs(conn: sqlite3.Connection, pairs: list[dict]):
    for p in pairs:
        existing = conn.execute("""
            SELECT 1 FROM interference_pairs
            WHERE (item_id_a=? AND item_id_b=?)
               OR (item_id_a=? AND item_id_b=?)
        """, (p["item_id_a"], p["item_id_b"],
              p["item_id_b"], p["item_id_a"])).fetchone()
        if existing:
            continue
        conn.execute("""
            INSERT INTO interference_pairs
            (item_id_a, item_id_b, interference_type,
             interference_strength, detected_by)
            VALUES (?,?,?,?,?)
        """, (
            p["item_id_a"], p["item_id_b"],
            p["interference_type"], p["interference_strength"],
            p["detected_by"],
        ))


# ─────────────────────────────────────────────
# INTERFERENCE-AWARE SCHEDULING
# ─────────────────────────────────────────────

def apply_interference_separation(
    conn: sqlite3.Connection,
    user_id: int,
    candidate_items: list[int],
    already_in_session: list[int],
) -> list[int]:
    """Filter candidates to remove high-interference items already in session."""
    if not already_in_session:
        return candidate_items

    placeholders = ",".join("?" * len(already_in_session))
    blocked_pairs = conn.execute(f"""
        SELECT item_id_a, item_id_b, interference_strength
        FROM interference_pairs
        WHERE interference_strength = 'high'
        AND (item_id_a IN ({placeholders}) OR item_id_b IN ({placeholders}))
    """, already_in_session + already_in_session).fetchall()

    session_set = set(already_in_session)
    avoid = set()
    for pair in blocked_pairs:
        if pair["item_id_a"] in session_set:
            avoid.add(pair["item_id_b"])
        if pair["item_id_b"] in session_set:
            avoid.add(pair["item_id_a"])

    return [item for item in candidate_items if item not in avoid]


# ─────────────────────────────────────────────
# INTERLEAVING SCHEDULER
# ─────────────────────────────────────────────

def build_interleaved_session(
    conn: sqlite3.Connection,
    user_id: int = 1,
    target_count: int = 20,
) -> list[dict]:
    """Build a session queue with enforced interleaving.

    No two consecutive items should be of the same semantic category.
    Thompson Sampling still selects drill type probabilities,
    but the final ordering is interleaved.
    Enforces cognitive load ceiling: max new_item_ceiling new items.
    """
    config = conn.execute(
        "SELECT * FROM learner_dd_config WHERE user_id=?",
        (user_id,)
    ).fetchone()

    new_item_ceiling = config["new_item_ceiling"] if config else 5
    interleaving = config["interleaving_strength"] if config else "moderate"

    due_items = conn.execute("""
        SELECT ms.content_item_id, ms.state, ms.stability, ms.difficulty,
               ms.retrievability, ci.hanzi, ci.english, ci.content_lens,
               ci.hsk_level
        FROM memory_states ms
        JOIN content_item ci ON ci.id = ms.content_item_id
        WHERE ms.user_id = ?
        AND ms.next_review_due <= datetime('now')
        ORDER BY ms.next_review_due ASC
        LIMIT ?
    """, (user_id, target_count * 2)).fetchall()

    new_items = [dict(i) for i in due_items if i["state"] in ("new", "learning")][:new_item_ceiling]
    review_items = [dict(i) for i in due_items if i["state"] in ("review", "relearning")]

    candidates = review_items + new_items
    candidates = candidates[:target_count]

    if interleaving == "light" or len(candidates) <= 1:
        return candidates

    return _interleave_items(candidates)


def _interleave_items(items: list[dict]) -> list[dict]:
    """Reorder items to maximize interleaving across semantic categories and states.

    Greedy: always pick the next item most different from the previous.
    """
    if len(items) <= 1:
        return items

    result = [items[0]]
    remaining = list(items[1:])

    while remaining:
        last = result[-1]
        last_lens = last.get("content_lens")
        last_state = last.get("state")

        def difference_score(item):
            score = 0
            if item.get("content_lens") != last_lens:
                score += 2
            if item.get("state") != last_state:
                score += 1
            return score

        best = max(remaining, key=difference_score)
        result.append(best)
        remaining.remove(best)

    return result


# ─────────────────────────────────────────────
# COGNITIVE LOAD MONITOR
# ─────────────────────────────────────────────

def check_session_load(
    conn: sqlite3.Connection,
    session_id: int,
    user_id: int = 1,
) -> dict:
    """Check whether current session is at cognitive load ceiling.

    Returns: {within_ceiling, new_items_this_session, ceiling, recommendation}
    """
    config = conn.execute(
        "SELECT new_item_ceiling FROM learner_dd_config WHERE user_id=?",
        (user_id,)
    ).fetchone()
    ceiling = config["new_item_ceiling"] if config else 5

    row = conn.execute("""
        SELECT COUNT(DISTINCT re.content_item_id) as cnt
        FROM review_event re
        JOIN memory_states ms ON ms.content_item_id=re.content_item_id
                              AND ms.user_id=re.user_id
        WHERE re.session_id=?
        AND re.user_id=?
        AND ms.state IN ('new','learning')
        AND ms.reps = 1
    """, (session_id, user_id)).fetchone()
    new_items_count = (row["cnt"] if row else 0) or 0

    within = new_items_count < ceiling

    return {
        "within_ceiling": within,
        "new_items_this_session": new_items_count,
        "ceiling": ceiling,
        "recommendation": (
            "Ceiling reached. Only review items for remainder of session."
            if not within else
            f"{ceiling - new_items_count} new items remaining this session."
        ),
    }


def log_session_load(
    conn: sqlite3.Connection,
    session_id: int,
    user_id: int = 1,
) -> None:
    """Log session load at end of session for audit tracking."""
    load = check_session_load(conn, session_id, user_id)

    active_learning = conn.execute("""
        SELECT COUNT(*) as cnt FROM memory_states
        WHERE user_id=? AND state IN ('learning', 'relearning')
    """, (user_id,)).fetchone()

    total_reviews = conn.execute("""
        SELECT COUNT(*) as cnt FROM review_event
        WHERE session_id=? AND user_id=?
    """, (session_id, user_id)).fetchone()

    conn.execute("""
        INSERT INTO session_load_log
        (session_id, user_id, new_items_introduced, active_learning_count,
         total_reviews, load_exceeded)
        VALUES (?,?,?,?,?,?)
    """, (
        session_id, user_id,
        load["new_items_this_session"],
        (active_learning["cnt"] if active_learning else 0) or 0,
        (total_reviews["cnt"] if total_reviews else 0) or 0,
        0 if load["within_ceiling"] else 1,
    ))


# ─────────────────────────────────────────────
# MEMORY MODEL ANALYZER
# Wired into the audit cycle via intelligence/memory_audit.py
# ─────────────────────────────────────────────

def analyze_memory_model(conn: sqlite3.Connection) -> list[dict]:
    """Memory model health analyzer. Detects stability distribution anomalies,
    high lapse rates, interference pair accumulation, load violations."""
    from ..intelligence._base import _finding

    findings = []

    # 1. Items with high lapse rates — encoding failure signal
    try:
        high_lapse_items = conn.execute("""
            SELECT content_item_id, user_id, lapses, reps,
                   CAST(lapses AS REAL)/reps as lapse_rate
            FROM memory_states
            WHERE reps >= 5
            AND CAST(lapses AS REAL)/reps > 0.40
            ORDER BY lapse_rate DESC
            LIMIT 10
        """).fetchall()

        if high_lapse_items:
            findings.append(_finding(
                dimension="memory_model",
                severity="medium",
                title=f"{len(high_lapse_items)} item(s) with lapse rate > 40%",
                analysis=(
                    "High lapse rates indicate items that were never well encoded. "
                    "These may benefit from reintroduction with different context "
                    "or from interference separation."
                ),
                recommendation="Review high-lapse items for interference pairs. "
                               "Consider reintroduction with new context.",
                claude_prompt="Analyze the high-lapse items in memory_states and check "
                              "for interference pairs or encoding problems.",
                impact="Wasted review time on items unlikely to stabilize without intervention.",
                files=["mandarin/ai/memory_model.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 2. Session load violations
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_load_log
            WHERE load_exceeded = 1
            AND started_at >= datetime('now','-7 days')
        """).fetchone()
        load_violations = (row["cnt"] if row else 0) or 0

        if load_violations > 3:
            findings.append(_finding(
                dimension="memory_model",
                severity="medium",
                title=f"{load_violations} sessions exceeded cognitive load ceiling this week",
                analysis="Exceeding the new-item ceiling degrades acquisition of all "
                         "new items in that session.",
                recommendation="Review session planner. Lower new_item_ceiling or enforce "
                               "ceiling more strictly.",
                claude_prompt="Check session_load_log for patterns in load ceiling violations.",
                impact="Degraded encoding quality when too many new items are introduced.",
                files=["mandarin/ai/memory_model.py", "mandarin/scheduler.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 3. Stability distribution — items in review state with very low stability
    try:
        stability_stats = conn.execute("""
            SELECT
                AVG(stability) as avg_s,
                MAX(stability) as max_s,
                COUNT(*) as total,
                SUM(CASE WHEN stability > 180 THEN 1 ELSE 0 END) as very_stable,
                SUM(CASE WHEN stability < 3 AND state='review' THEN 1 ELSE 0 END) as unstable_review
            FROM memory_states
            WHERE reps >= 3
        """).fetchone()

        unstable = (stability_stats["unstable_review"] or 0) if stability_stats else 0
        if unstable > 10:
            findings.append(_finding(
                dimension="memory_model",
                severity="medium",
                title=f"{unstable} review-state items with very low stability",
                analysis=(
                    "Items in review state should have stability > 3 days. "
                    "These may have been promoted to review state prematurely."
                ),
                recommendation="Check state transition thresholds. These items "
                               "may need to return to learning state.",
                claude_prompt="Find items in memory_states with state='review' and stability < 3.",
                impact="Premature promotion leads to inefficient review scheduling.",
                files=["mandarin/ai/memory_model.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 4. Unaddressed high-interference pairs
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt
            FROM interference_pairs ip
            WHERE interference_strength = 'high'
            AND NOT EXISTS (
                SELECT 1 FROM memory_states ms
                WHERE ms.content_item_id = ip.item_id_a
                AND ms.encoding_quality = 'interference'
            )
        """).fetchone()
        unaddressed_high = (row["cnt"] if row else 0) or 0

        if unaddressed_high > 5:
            findings.append(_finding(
                dimension="memory_model",
                severity="low",
                title=f"{unaddressed_high} high-interference pairs not flagged in memory states",
                analysis="Interference pairs detected but not yet reflected in encoding quality flags.",
                recommendation="Run update to propagate interference flags to memory_states.",
                claude_prompt="Update memory_states encoding_quality for items in "
                              "high-interference pairs.",
                impact="Without flagging, scheduler cannot adjust for interference.",
                files=["mandarin/ai/memory_model.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings


# ─────────────────────────────────────────────
# ACTIVE CONTRAST PAIRS (minimal-pair drilling)
# ─────────────────────────────────────────────

def get_active_contrast_pairs(conn: sqlite3.Connection, user_id: int, limit: int = 10) -> list[dict]:
    """Find high-interference pairs where both items are known but frequently confused.

    Candidates for explicit minimal-pair contrast drilling. Both items must
    have a memory_states row (i.e. the learner has encountered them), and
    the pair must have high or medium interference strength.
    """
    try:
        rows = conn.execute("""
            SELECT ip.item_id_a, ip.item_id_b, ip.interference_type,
                   ip.interference_strength,
                   ca.hanzi AS hanzi_a, ca.pinyin AS pinyin_a, ca.english AS english_a,
                   cb.hanzi AS hanzi_b, cb.pinyin AS pinyin_b, cb.english AS english_b
            FROM interference_pairs ip
            JOIN content_item ca ON ip.item_id_a = ca.id
            JOIN content_item cb ON ip.item_id_b = cb.id
            WHERE ip.interference_strength IN ('high', 'medium')
              AND EXISTS (
                  SELECT 1 FROM memory_states ms
                  WHERE ms.content_item_id = ip.item_id_a AND ms.user_id = ?
              )
              AND EXISTS (
                  SELECT 1 FROM memory_states ms
                  WHERE ms.content_item_id = ip.item_id_b AND ms.user_id = ?
              )
            ORDER BY CASE ip.interference_strength
                         WHEN 'high' THEN 1 ELSE 2
                     END,
                     COALESCE(ip.error_co_occurrence, 0) DESC
            LIMIT ?
        """, (user_id, user_id, limit)).fetchall()
        return [dict(r) for r in rows] if rows else []
    except sqlite3.OperationalError:
        # Table may not exist yet — graceful degradation
        return []


# ─────────────────────────────────────────────
# CALIBRATION
# ─────────────────────────────────────────────

def calibrate_fsrs_parameters(conn: sqlite3.Connection, user_id: int = 1) -> dict | None:
    """Fit FSRS parameters to individual learner's review history.

    Requires 200+ reviews. Returns calibrated parameters or None.
    Full calibration requires fsrs-optimizer (pip install fsrs-optimizer).
    Falls back to defaults if library unavailable.
    """
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_event WHERE user_id=?",
            (user_id,),
        ).fetchone()
        review_count = (row["cnt"] if row else 0) or 0
    except sqlite3.OperationalError:
        return None

    if review_count < 200:
        return None

    # Placeholder: returns defaults until fsrs-optimizer is integrated
    return FSRS_DEFAULTS


# ─────────────────────────────────────────────
# MIGRATION HELPER: backfill memory_states from review history
# ─────────────────────────────────────────────

def backfill_memory_states(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Populate memory_states for items with existing review history.

    For each content_item with review_event rows but no memory_state,
    creates an initial state based on total correct/incorrect reviews.
    Returns count of states created.
    """
    items = conn.execute("""
        SELECT re.content_item_id,
               COUNT(*) as total_reviews,
               SUM(CASE WHEN re.correct=1 THEN 1 ELSE 0 END) as correct_count,
               MIN(re.created_at) as first_review,
               MAX(re.created_at) as last_review
        FROM review_event re
        WHERE re.user_id=?
        AND NOT EXISTS (
            SELECT 1 FROM memory_states ms
            WHERE ms.content_item_id=re.content_item_id AND ms.user_id=re.user_id
        )
        GROUP BY re.content_item_id
    """, (user_id,)).fetchall()

    count = 0
    for item in items:
        total = item["total_reviews"]
        correct = item["correct_count"]
        accuracy = correct / total if total > 0 else 0

        # Estimate initial stability from accuracy and review count
        if accuracy >= 0.9 and total >= 5:
            stability = min(30.0, total * 2.0)
            state = "review"
        elif accuracy >= 0.6:
            stability = max(1.0, total * 0.5)
            state = "review"
        else:
            stability = 1.0
            state = "learning"

        difficulty = max(1.0, min(10.0, (1 - accuracy) * 10))

        conn.execute("""
            INSERT OR IGNORE INTO memory_states
            (user_id, content_item_id, stability, retrievability, difficulty,
             state, last_reviewed_at, next_review_due, scheduled_days, reps, lapses)
            VALUES (?,?,?,0.0,?,?,?,datetime('now'),?,?,0)
        """, (
            user_id, item["content_item_id"],
            stability, difficulty, state,
            item["last_review"],
            max(1, round(stability)),
            total,
        ))
        count += 1

    return count
