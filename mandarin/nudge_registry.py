"""Nudge Registry — centralized tracking, ethics evaluation, and conversion
measurement for all behavioral nudges across aelu.

Every user-facing nudge (upgrade prompt, email trigger, milestone message,
notification, session framing) should be registered here. The registry provides:

1. Central catalog of all nudges with type classification
2. DOCTRINE compliance scoring via Ollama/Qwen
3. Exposure and outcome logging for A/B testing
4. Agent-ready interface for proposing and evaluating nudge variants

DOCTRINE constraints enforced:
  §3: Exact, warm, brief feedback
  §6: Progress visibility, not manipulation. No guilt, no urgency.
  §8: Warm but rigorous. Humble but precise.
"""

from __future__ import annotations

import enum
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ── Nudge taxonomy (Thaler & Sunstein categories) ───────────────────────


class NudgeType(enum.Enum):
    """Classification of behavioral nudge mechanisms."""
    INFORMATIONAL = "informational"        # Pure information delivery
    DEFAULT_CHANGE = "default_change"      # Changing what happens if user does nothing
    SALIENCE = "salience"                  # Making important info more visible
    FEEDBACK = "feedback"                  # Performance/progress feedback
    COMMITMENT = "commitment"              # Supporting user self-commitments
    SOCIAL_PROOF = "social_proof"          # Factual social validation
    TIMING = "timing"                      # Delivering info at optimal moments
    CHOICE_ARCHITECTURE = "choice_architecture"  # Structuring choices to help


class NudgeStatus(enum.Enum):
    """Lifecycle status of a registered nudge."""
    DRAFT = "draft"          # Created, not yet ethics-scored
    REVIEW = "review"        # Ethics score pending human approval
    ACTIVE = "active"        # Live in production
    PAUSED = "paused"        # Temporarily disabled
    RETIRED = "retired"      # Permanently disabled


class OutcomeType(enum.Enum):
    """What happened after a nudge was shown."""
    CLICKED = "clicked"        # User engaged with the nudge
    CONVERTED = "converted"    # User completed the desired action
    DISMISSED = "dismissed"    # User explicitly closed/dismissed
    IGNORED = "ignored"        # No interaction within tracking window


# ── DOCTRINE ethics evaluation ───────────────────────────────────────────

_DOCTRINE_EVAL_SYSTEM = """You are an ethics evaluator for Aelu, a Mandarin learning app.

Aelu's Operating Doctrine has strict rules about user-facing communication:

FORBIDDEN (score 0 on any dimension that applies):
- Guilt: "you haven't...", "we miss you", "falling behind", "don't give up"
- Streak anxiety: "streak at risk", "don't lose your streak", "keep it alive"
- Manufactured urgency: "hurry", "limited time", "last chance", "expires soon"
- Normative social pressure: "others are ahead", "your friends are..."
- Manipulative loss framing: "you'll lose your progress"

REQUIRED (high scores):
- Progress framed as capability: "You can now understand..."
- Warm but honest tone: adult, respectful, non-patronizing
- Factual and verifiable: no exaggeration, no fabricated stats
- Learner autonomy: options, not demands; "whenever you're ready"
- Brief: one sentence for the message, not a paragraph

Evaluate the following nudge copy shown in the given context.
Return ONLY a JSON object with these float scores (0.0 to 1.0):
{
  "guilt_free": <score>,
  "urgency_free": <score>,
  "autonomy_respecting": <score>,
  "progress_focused": <score>,
  "tone_appropriate": <score>,
  "overall": <weighted average>
}
"""

_DOCTRINE_EVAL_PROMPT = """Nudge copy: "{copy}"
Context: {context}

Score this nudge against the DOCTRINE constraints. Return JSON only."""


@dataclass
class DoctrineScore:
    """Result of DOCTRINE compliance evaluation."""
    guilt_free: float = 1.0
    urgency_free: float = 1.0
    autonomy_respecting: float = 1.0
    progress_focused: float = 0.5
    tone_appropriate: float = 1.0
    overall: float = 0.8
    raw_response: str = ""

    @property
    def passes(self) -> bool:
        """Score >= 0.7 required for activation."""
        return self.overall >= 0.7

    def to_dict(self) -> dict:
        return {
            "guilt_free": self.guilt_free,
            "urgency_free": self.urgency_free,
            "autonomy_respecting": self.autonomy_respecting,
            "progress_focused": self.progress_focused,
            "tone_appropriate": self.tone_appropriate,
            "overall": self.overall,
        }


def evaluate_nudge_ethics(
    copy: str,
    context: str = "in-app message",
    conn: sqlite3.Connection = None,
) -> DoctrineScore:
    """Evaluate nudge copy against DOCTRINE constraints using Ollama/Qwen.

    Returns a DoctrineScore. If Ollama is unavailable, falls back to
    rule-based heuristic evaluation.
    """
    # Try LLM evaluation first
    try:
        from .ai.ollama_client import generate, is_ollama_available

        if is_ollama_available():
            prompt = _DOCTRINE_EVAL_PROMPT.format(copy=copy, context=context)
            resp = generate(
                prompt=prompt,
                system=_DOCTRINE_EVAL_SYSTEM,
                temperature=0.1,
                max_tokens=256,
                use_cache=True,
                conn=conn,
                task_type="nudge_ethics",
            )
            if resp.success and resp.text:
                return _parse_ethics_response(resp.text)
    except Exception as e:
        logger.debug("LLM ethics evaluation unavailable: %s", e)

    # Fallback: rule-based heuristic
    return _heuristic_ethics_score(copy)


def _parse_ethics_response(text: str) -> DoctrineScore:
    """Parse LLM JSON response into DoctrineScore."""
    try:
        # Extract JSON from response (may be wrapped in markdown)
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        return DoctrineScore(
            guilt_free=float(data.get("guilt_free", 0.5)),
            urgency_free=float(data.get("urgency_free", 0.5)),
            autonomy_respecting=float(data.get("autonomy_respecting", 0.5)),
            progress_focused=float(data.get("progress_focused", 0.5)),
            tone_appropriate=float(data.get("tone_appropriate", 0.5)),
            overall=float(data.get("overall", 0.5)),
            raw_response=text,
        )
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning("Failed to parse ethics response: %s", e)
        return DoctrineScore(overall=0.5, raw_response=text)


def _heuristic_ethics_score(copy: str) -> DoctrineScore:
    """Rule-based fallback when Ollama is unavailable."""
    import re
    lower = copy.lower()

    guilt_free = 1.0
    guilt_words = re.findall(
        r"\b(?:haven'?t|miss you|falling behind|letting|give up|disappointed)\b",
        lower,
    )
    if guilt_words:
        guilt_free = 0.0

    urgency_free = 1.0
    urgency_words = re.findall(
        r"\b(?:hurry|limited time|last chance|expires? soon|act now|running out)\b",
        lower,
    )
    if urgency_words:
        urgency_free = 0.0

    autonomy = 1.0
    pressure_words = re.findall(
        r"\b(?:you must|you need to|you should|don'?t miss)\b",
        lower,
    )
    if pressure_words:
        autonomy = 0.3

    progress = 0.5
    if re.search(r"you can now|you'?ve learned|progress|mastered", lower):
        progress = 0.9

    tone = 0.8
    if re.search(r"!!|amazing|incredible|awesome", lower):
        tone = 0.4  # Saccharine (DOCTRINE §3)

    overall = (guilt_free * 0.25 + urgency_free * 0.25 + autonomy * 0.2
               + progress * 0.15 + tone * 0.15)

    return DoctrineScore(
        guilt_free=guilt_free,
        urgency_free=urgency_free,
        autonomy_respecting=autonomy,
        progress_focused=progress,
        tone_appropriate=tone,
        overall=round(overall, 2),
    )


# ── Registry operations ──────────────────────────────────────────────────


def register_nudge(
    conn: sqlite3.Connection,
    nudge_key: str,
    nudge_type: NudgeType,
    copy_template: str,
    context: str = "in-app",
    platforms: str = "web,ios,android,macos",
    experiment_id: int | None = None,
    auto_evaluate: bool = True,
) -> int:
    """Register a nudge in the registry. Returns the nudge ID.

    If auto_evaluate is True, runs DOCTRINE ethics evaluation and stores
    the score. Nudges with score < 0.7 are set to REVIEW status.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Evaluate ethics
    doctrine_score = None
    doctrine_json = None
    status = NudgeStatus.DRAFT.value
    if auto_evaluate:
        doctrine_score_obj = evaluate_nudge_ethics(copy_template, context, conn)
        doctrine_score = doctrine_score_obj.overall
        doctrine_json = json.dumps(doctrine_score_obj.to_dict())
        status = NudgeStatus.ACTIVE.value if doctrine_score_obj.passes else NudgeStatus.REVIEW.value

    try:
        cursor = conn.execute(
            """INSERT INTO nudge_registry
               (nudge_key, nudge_type, copy_template, doctrine_score,
                doctrine_evaluation, status, platforms, experiment_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(nudge_key) DO UPDATE SET
                 copy_template = excluded.copy_template,
                 doctrine_score = excluded.doctrine_score,
                 doctrine_evaluation = excluded.doctrine_evaluation,
                 status = excluded.status,
                 platforms = excluded.platforms,
                 experiment_id = excluded.experiment_id,
                 updated_at = excluded.updated_at""",
            (nudge_key, nudge_type.value, copy_template, doctrine_score,
             doctrine_json, status, platforms, experiment_id, now, now),
        )
        conn.commit()
        nudge_id = cursor.lastrowid
        logger.info(
            "nudge registered: key=%s type=%s score=%.2f status=%s",
            nudge_key, nudge_type.value, doctrine_score or 0, status,
        )
        return nudge_id
    except sqlite3.Error as e:
        logger.error("failed to register nudge %s: %s", nudge_key, e)
        raise


def log_nudge_exposure(
    conn: sqlite3.Connection,
    nudge_key: str,
    user_id: int,
    context: str = "",
    variant: str = "control",
) -> int | None:
    """Log that a user was shown a nudge. Returns exposure ID."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Look up nudge_id
        row = conn.execute(
            "SELECT id FROM nudge_registry WHERE nudge_key = ?", (nudge_key,)
        ).fetchone()
        if not row:
            logger.warning("nudge_exposure: unknown nudge_key=%s", nudge_key)
            return None

        cursor = conn.execute(
            """INSERT INTO nudge_exposure (nudge_id, user_id, context, variant, exposed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (row["id"], user_id, context, variant, now),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error("failed to log nudge exposure: %s", e)
        return None


def log_nudge_outcome(
    conn: sqlite3.Connection,
    exposure_id: int,
    outcome: OutcomeType,
) -> None:
    """Log the outcome of a nudge exposure."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT INTO nudge_outcome (nudge_exposure_id, outcome_type, outcome_at)
               VALUES (?, ?, ?)""",
            (exposure_id, outcome.value, now),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error("failed to log nudge outcome: %s", e)


def get_nudge_stats(conn: sqlite3.Connection, nudge_key: str) -> dict:
    """Get conversion stats for a nudge."""
    try:
        row = conn.execute(
            "SELECT id, doctrine_score, status FROM nudge_registry WHERE nudge_key = ?",
            (nudge_key,),
        ).fetchone()
        if not row:
            return {"error": "nudge not found"}

        nudge_id = row["id"]
        exposures = conn.execute(
            "SELECT COUNT(*) FROM nudge_exposure WHERE nudge_id = ?",
            (nudge_id,),
        ).fetchone()[0]
        outcomes = conn.execute(
            """SELECT outcome_type, COUNT(*) as cnt
               FROM nudge_outcome no
               JOIN nudge_exposure ne ON no.nudge_exposure_id = ne.id
               WHERE ne.nudge_id = ?
               GROUP BY outcome_type""",
            (nudge_id,),
        ).fetchall()

        outcome_counts = {r["outcome_type"]: r["cnt"] for r in outcomes}
        converted = outcome_counts.get("converted", 0)

        return {
            "nudge_key": nudge_key,
            "doctrine_score": row["doctrine_score"],
            "status": row["status"],
            "exposures": exposures,
            "outcomes": outcome_counts,
            "conversion_rate": round(converted / exposures, 4) if exposures > 0 else 0,
        }
    except sqlite3.Error as e:
        logger.error("failed to get nudge stats: %s", e)
        return {"error": str(e)}


def get_all_nudge_stats(conn: sqlite3.Connection) -> list[dict]:
    """Get stats for all registered nudges. Used by admin dashboard."""
    try:
        nudges = conn.execute(
            """SELECT id, nudge_key, nudge_type, doctrine_score, status,
                      platforms, experiment_id, created_at
               FROM nudge_registry ORDER BY created_at DESC"""
        ).fetchall()

        results = []
        for n in nudges:
            exposures = conn.execute(
                "SELECT COUNT(*) FROM nudge_exposure WHERE nudge_id = ?",
                (n["id"],),
            ).fetchone()[0]
            converted = conn.execute(
                """SELECT COUNT(*) FROM nudge_outcome no
                   JOIN nudge_exposure ne ON no.nudge_exposure_id = ne.id
                   WHERE ne.nudge_id = ? AND no.outcome_type = 'converted'""",
                (n["id"],),
            ).fetchone()[0]

            results.append({
                "nudge_key": n["nudge_key"],
                "nudge_type": n["nudge_type"],
                "doctrine_score": n["doctrine_score"],
                "status": n["status"],
                "platforms": n["platforms"],
                "experiment_id": n["experiment_id"],
                "exposures": exposures,
                "conversions": converted,
                "conversion_rate": round(converted / exposures, 4) if exposures > 0 else 0,
            })
        return results
    except sqlite3.Error as e:
        logger.error("failed to get all nudge stats: %s", e)
        return []
