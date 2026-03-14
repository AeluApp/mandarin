"""Agentic Technology Layer (Doc 23).

Closes loops that currently require human intervention:
A-01: Structured output enforcement (Pydantic validation)
A-02: Parallel audit orchestration
A-03: Autonomous content generation pipeline
A-04: Focused learner context retrieval
A-05: Competitor/research signal monitoring (schema + stubs)
A-06: Prescription execution agent

All implementations work with existing infrastructure and can be
upgraded to Instructor, LangGraph, LlamaIndex, mem0, Crawl4AI,
LangChain respectively.
"""

import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# A-01: STRUCTURED OUTPUT ENFORCEMENT
# Pydantic models for PROMPT_REGISTRY output schemas.
# Currently validates post-generation; upgradeable to Instructor
# for sampling-level enforcement.
# ─────────────────────────────────────────────

try:
    from pydantic import BaseModel, Field, ValidationError
except ImportError:
    # Fallback: no Pydantic available, validation is a no-op
    BaseModel = None
    Field = None
    ValidationError = None


if BaseModel is not None:
    class UsageMapOutput(BaseModel):
        """Schema for usage_map_generation prompt output."""
        usage_context: str = Field(description="Primary usage context")
        register: str = Field(description="Formal/neutral/casual register")
        example_sentence: str = Field(description="Natural example sentence")
        notes: Optional[str] = Field(default=None, description="Additional usage notes")

    class TutorAnalysisOutput(BaseModel):
        """Schema for tutor_analysis prompt output."""
        summary: str = Field(description="Session summary")
        corrections: list = Field(default_factory=list, description="List of corrections")
        focus_areas: list = Field(default_factory=list, description="Areas needing focus")
        recommended_drills: list = Field(default_factory=list, description="Drill suggestions")

    class LearningInsightOutput(BaseModel):
        """Schema for learning_insight prompt output."""
        insight: str = Field(description="Key learning insight")
        pattern: str = Field(description="Error pattern identified")
        recommendation: str = Field(description="Study recommendation")

    class DrillGenerationOutput(BaseModel):
        """Schema for drill_generation prompt output."""
        hanzi: str = Field(description="Chinese characters")
        pinyin: str = Field(description="Pinyin with tones")
        english: str = Field(description="English translation")
        drill_type: str = Field(description="Type of drill")
        distractors: list = Field(default_factory=list, description="Wrong answer options")

    class ErrorExplanationOutput(BaseModel):
        """Schema for error_explanation prompt output."""
        explanation: str = Field(description="Why this error occurred")
        correct_usage: str = Field(description="Correct usage pattern")
        mnemonic: Optional[str] = Field(default=None, description="Memory aid")

    # Registry mapping prompt keys to their Pydantic models
    OUTPUT_SCHEMA_REGISTRY = {
        "usage_map_generation": UsageMapOutput,
        "tutor_analysis": TutorAnalysisOutput,
        "learning_insight": LearningInsightOutput,
        "drill_generation": DrillGenerationOutput,
        "error_explanation": ErrorExplanationOutput,
    }
else:
    OUTPUT_SCHEMA_REGISTRY = {}


def validate_structured_output(raw_json: dict, prompt_key: str) -> tuple[bool, Optional[str]]:
    """Validate LLM output against Pydantic schema.

    Returns (is_valid, error_message).
    Upgradeable to Instructor for sampling-level enforcement.
    """
    if not OUTPUT_SCHEMA_REGISTRY:
        return True, None  # No Pydantic, skip validation

    model_class = OUTPUT_SCHEMA_REGISTRY.get(prompt_key)
    if not model_class:
        return True, None  # No schema defined for this key

    try:
        model_class(**raw_json)
        return True, None
    except ValidationError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Validation error: {e}"


def retry_with_structured_output(
    conn: sqlite3.Connection,
    prompt: str,
    system: str,
    prompt_key: str,
    max_retries: int = 3,
    temperature: float = 0.7,
) -> Optional[dict]:
    """Generate structured output with validation and retry.

    Tries Instructor (sampling-level enforcement) first, falls back to
    post-hoc Pydantic validation with retry loop.
    """
    from .ollama_client import generate as ollama_generate, generate_structured
    from .genai_layer import _parse_llm_json

    # Try Instructor path first (A-01 upgrade)
    model_class = OUTPUT_SCHEMA_REGISTRY.get(prompt_key)
    if model_class is not None:
        try:
            result = generate_structured(
                prompt=prompt,
                response_model=model_class,
                system=system,
                temperature=temperature,
                conn=conn,
                task_type=f"structured_{prompt_key}",
            )
            if result is not None:
                return result.model_dump() if hasattr(result, 'model_dump') else dict(result)
        except Exception:
            logger.debug("Instructor path failed for %s, falling back", prompt_key)

    # Fallback: post-hoc validation with retry
    for attempt in range(max_retries):
        response = ollama_generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            conn=conn,
            task_type=f"structured_{prompt_key}",
        )
        if not response.success:
            continue

        parsed = _parse_llm_json(response.text, conn=conn, task_type=prompt_key)
        if parsed is None:
            continue

        is_valid, error = validate_structured_output(parsed, prompt_key)
        if is_valid:
            return parsed

        logger.warning(
            "Structured output validation failed for %s (attempt %d): %s",
            prompt_key, attempt + 1, error,
        )

    # Log failure
    try:
        conn.execute("""
            INSERT INTO json_generation_failures
            (task_type, error_type, error_detail, prompt_snippet)
            VALUES (?, 'schema_validation', ?, ?)
        """, (prompt_key, f"Failed after {max_retries} retries", prompt[:200]))
    except sqlite3.OperationalError:
        pass

    return None


# ─────────────────────────────────────────────
# A-02: PARALLEL AUDIT ORCHESTRATION
# Uses concurrent.futures; upgradeable to LangGraph DAG.
# ─────────────────────────────────────────────

def run_parallel_audit(conn: sqlite3.Connection, analyzers: list, max_workers: int = 4) -> list[dict]:
    """Run analyzers in parallel using ThreadPoolExecutor.

    Each analyzer is independent (no data dependencies between them).
    Returns aggregated findings. Upgradeable to LangGraph DAG.
    """
    findings = []
    node_results = []

    def _run_analyzer(analyzer):
        start = datetime.now(timezone.utc)
        try:
            results = analyzer(conn)
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            return {
                "analyzer": analyzer.__name__,
                "findings": results,
                "duration_seconds": round(elapsed, 2),
                "error": None,
            }
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.warning("Analyzer %s failed: %s", analyzer.__name__, e)
            return {
                "analyzer": analyzer.__name__,
                "findings": [],
                "duration_seconds": round(elapsed, 2),
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_analyzer, a): a for a in analyzers}
        for future in as_completed(futures):
            result = future.result()
            node_results.append(result)
            findings.extend(result["findings"])

    # Log execution graph
    try:
        conn.execute("""
            INSERT INTO agent_task_log
            (task_type, task_data, status, completed_at)
            VALUES ('parallel_audit', ?, 'completed', datetime('now'))
        """, (json.dumps({
            "node_count": len(analyzers),
            "total_findings": len(findings),
            "nodes": [{
                "name": r["analyzer"],
                "duration": r["duration_seconds"],
                "findings": len(r["findings"]),
                "error": r["error"],
            } for r in node_results],
        }),))
    except sqlite3.OperationalError:
        pass

    return findings


# ─────────────────────────────────────────────
# A-03: CONTENT GENERATION PIPELINE
# Gap detection → content spec → generation → queue.
# Upgradeable to LlamaIndex Workflows.
# ─────────────────────────────────────────────

# Circuit breaker: pause if rejection rate > 40% over 7 days
_CIRCUIT_BREAKER_THRESHOLD = 0.40
_CIRCUIT_BREAKER_WINDOW_DAYS = 7
_MAX_PENDING_AUTO = 30


def check_content_pipeline_circuit_breaker(conn: sqlite3.Connection) -> bool:
    """Returns True if pipeline should be paused (circuit open)."""
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected
            FROM content_generation_queue
            WHERE created_at >= datetime('now', ?)
            AND status IN ('approved', 'rejected')
        """, (f"-{_CIRCUIT_BREAKER_WINDOW_DAYS} days",)).fetchone()

        total = (row["total"] or 0) if row else 0
        if total >= 5:
            rejected = (row["rejected"] or 0)
            if rejected / total > _CIRCUIT_BREAKER_THRESHOLD:
                return True

        # Check pending count
        pending = conn.execute("""
            SELECT COUNT(*) as cnt FROM content_generation_queue
            WHERE status='pending'
        """).fetchone()
        if (pending["cnt"] or 0) >= _MAX_PENDING_AUTO:
            return True
    except sqlite3.OperationalError:
        pass

    return False


def detect_content_gaps(conn: sqlite3.Connection) -> list[dict]:
    """Detect corpus gaps from audit findings that can be auto-filled."""
    gaps = []

    # Grammar patterns at current levels with no content items
    try:
        pattern_gaps = conn.execute("""
            SELECT gp.id, gp.name, gp.hsk_level, gp.category
            FROM grammar_point gp
            WHERE gp.hsk_level <= 6
            AND NOT EXISTS (
                SELECT 1 FROM content_grammar cg WHERE cg.grammar_point_id = gp.id
            )
            LIMIT 10
        """).fetchall()

        for p in pattern_gaps:
            gaps.append({
                "gap_type": "grammar_pattern_no_items",
                "grammar_point_id": p["id"],
                "name": p["name"],
                "hsk_level": p["hsk_level"],
                "priority": "high" if (p["hsk_level"] or 0) <= 4 else "medium",
            })
    except sqlite3.OperationalError:
        pass

    return gaps


def queue_auto_generation(
    conn: sqlite3.Connection,
    gap: dict,
    generation_brief: str,
) -> Optional[int]:
    """Queue a content generation task from a detected gap."""
    if check_content_pipeline_circuit_breaker(conn):
        logger.info("Content pipeline circuit breaker is OPEN — skipping auto-generation")
        return None

    try:
        cursor = conn.execute("""
            INSERT INTO content_generation_queue
            (gap_type, gap_data, generation_brief, status)
            VALUES (?, ?, ?, 'pending')
        """, (
            gap.get("gap_type", "unknown"),
            json.dumps(gap, ensure_ascii=False),
            generation_brief,
        ))
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


# ─────────────────────────────────────────────
# A-04: FOCUSED LEARNER CONTEXT RETRIEVAL
# Replaces monolithic get_learner_model_context() with
# task-focused context. Upgradeable to mem0.
# ─────────────────────────────────────────────

def get_focused_learner_context(
    conn: sqlite3.Connection,
    user_id: int,
    task_type: str,
    target_hsk: int = None,
    target_hanzi: str = None,
) -> dict:
    """Retrieve focused learner context relevant to a specific task.

    Instead of serializing the full learner state, retrieves only
    the context relevant to the generation task at hand.
    """
    context = {"user_id": user_id, "task_type": task_type}

    # Always include proficiency estimate
    try:
        proficiency = conn.execute(
            "SELECT * FROM learner_proficiency_zones WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if proficiency:
            context["composite_hsk"] = proficiency["composite_hsk_estimate"] or 0
            context["vocab_hsk"] = proficiency["vocab_hsk_estimate"] or 0
    except sqlite3.OperationalError:
        pass

    # Task-specific context
    if task_type == "drill_generation":
        # Recent error patterns (top 5 most-errored items)
        try:
            errors = conn.execute("""
                SELECT ci.hanzi, ci.hsk_level, COUNT(*) as error_count
                FROM review_event re
                JOIN content_item ci ON ci.id = re.content_item_id
                WHERE re.user_id = ? AND re.correct = 0
                AND re.created_at >= datetime('now', '-30 days')
                GROUP BY ci.id
                ORDER BY error_count DESC
                LIMIT 5
            """, (user_id,)).fetchall()
            context["recent_errors"] = [dict(e) for e in errors]
        except sqlite3.OperationalError:
            pass

    elif task_type == "error_explanation":
        # Interference pairs for the target item
        if target_hanzi:
            try:
                pairs = conn.execute("""
                    SELECT ip.hanzi_a, ip.hanzi_b, ip.confusion_type
                    FROM interference_pairs ip
                    WHERE ip.hanzi_a = ? OR ip.hanzi_b = ?
                    LIMIT 5
                """, (target_hanzi, target_hanzi)).fetchall()
                context["interference_pairs"] = [dict(p) for p in pairs]
            except sqlite3.OperationalError:
                pass

    elif task_type == "usage_map":
        # Current thematic lenses in use
        try:
            lenses = conn.execute("""
                SELECT DISTINCT content_lens FROM content_item
                WHERE status = 'drill_ready' AND content_lens IS NOT NULL
                LIMIT 10
            """).fetchall()
            context["active_lenses"] = [r["content_lens"] for r in lenses]
        except sqlite3.OperationalError:
            pass

    return context


# ─────────────────────────────────────────────
# A-05: COMPETITOR/RESEARCH MONITORING
# Schema + stubs. Upgradeable to Crawl4AI.
# ─────────────────────────────────────────────

def log_competitor_signal(
    conn: sqlite3.Connection,
    source: str,
    signal_type: str,
    title: str,
    detail: str,
    source_url: str = None,
) -> Optional[int]:
    """Log a competitor intelligence signal."""
    try:
        cursor = conn.execute("""
            INSERT INTO competitor_signals
            (source, signal_type, title, detail, source_url)
            VALUES (?, ?, ?, ?, ?)
        """, (source, signal_type, title, detail, source_url))
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


def log_research_signal(
    conn: sqlite3.Connection,
    source: str,
    title: str,
    finding: str,
    applicability_score: float,
    doi: str = None,
) -> Optional[int]:
    """Log a research finding signal."""
    try:
        cursor = conn.execute("""
            INSERT INTO research_signals
            (source, title, finding, applicability_score, doi)
            VALUES (?, ?, ?, ?, ?)
        """, (source, title, finding, applicability_score, doi))
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


# ─────────────────────────────────────────────
# A-06: PRESCRIPTION EXECUTION AGENT
# Auto-executes mechanical prescriptions.
# Upgradeable to LangChain Tools.
# ─────────────────────────────────────────────

# Prescription categories that can be auto-executed
_AUTO_EXECUTABLE_ACTIONS = {
    "generate_content",     # Trigger content generation pipeline
    "recalibrate_fsrs",     # Run FSRS calibration
    "refresh_rag",          # Refresh RAG knowledge base
    "update_difficulty",    # Adjust difficulty parameters
}


def classify_prescription(instruction: str, target_parameter: str = None) -> str:
    """Classify whether a prescription is auto-executable or requires human judgment."""
    instruction_lower = (instruction or "").lower()

    if "generate" in instruction_lower and "content" in instruction_lower:
        return "generate_content"
    if "calibrat" in instruction_lower and ("fsrs" in instruction_lower or "parameter" in instruction_lower):
        return "recalibrate_fsrs"
    if "rag" in instruction_lower and ("refresh" in instruction_lower or "update" in instruction_lower):
        return "refresh_rag"
    if "difficulty" in instruction_lower and ("adjust" in instruction_lower or "update" in instruction_lower):
        return "update_difficulty"

    return "requires_human"


def execute_prescription(conn: sqlite3.Connection, work_order_id: int) -> dict:
    """Execute a prescription if it's auto-executable.

    Returns execution result. Non-auto prescriptions route to human queue.
    """
    try:
        wo = conn.execute(
            "SELECT * FROM pi_work_order WHERE id=? AND status='pending'",
            (work_order_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"status": "error", "reason": "work_order table not available"}

    if not wo:
        return {"status": "error", "reason": "work_order not found or not pending"}

    instruction = wo["instruction"] or ""
    try:
        target_param = wo["target_parameter"]
    except (IndexError, KeyError):
        target_param = None
    action_type = classify_prescription(instruction, target_param)

    if action_type not in _AUTO_EXECUTABLE_ACTIONS:
        return {"status": "requires_human", "action_type": action_type}

    # Execute the action
    result = _execute_action(conn, action_type, wo)

    # Log execution
    try:
        conn.execute("""
            INSERT INTO prescription_execution_log
            (work_order_id, action_type, status, result_data)
            VALUES (?, ?, ?, ?)
        """, (
            work_order_id,
            action_type,
            result.get("status", "unknown"),
            json.dumps(result, ensure_ascii=False),
        ))
    except sqlite3.OperationalError:
        pass

    return result


def _execute_action(conn: sqlite3.Connection, action_type: str, work_order) -> dict:
    """Execute a specific auto-executable action."""
    if action_type == "generate_content":
        gaps = detect_content_gaps(conn)
        if gaps:
            queued = 0
            for gap in gaps[:5]:
                brief = f"Auto-generated from work order {work_order['id']}: {gap.get('name', 'unknown')}"
                if queue_auto_generation(conn, gap, brief):
                    queued += 1
            return {"status": "executed", "items_queued": queued}
        return {"status": "executed", "items_queued": 0, "note": "no gaps found"}

    elif action_type == "recalibrate_fsrs":
        try:
            from .memory_model import calibrate_fsrs_parameters
            result = calibrate_fsrs_parameters(conn)
            return {"status": "executed", "calibration": result}
        except (ImportError, Exception) as e:
            return {"status": "error", "reason": str(e)}

    elif action_type == "refresh_rag":
        try:
            from .rag_layer import import_cc_cedict
            result = import_cc_cedict(conn)
            return {"status": "executed", "rag_refresh": result}
        except (ImportError, Exception) as e:
            return {"status": "error", "reason": str(e)}

    elif action_type == "update_difficulty":
        return {"status": "executed", "note": "difficulty update requires specific parameters"}

    return {"status": "unknown_action"}


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

def analyze_agentic_health(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for agentic layer health."""
    from ..intelligence._base import _finding
    findings = []

    # 1. Content pipeline circuit breaker status
    if check_content_pipeline_circuit_breaker(conn):
        findings.append(_finding(
            dimension="agentic",
            severity="high",
            title="Content generation pipeline circuit breaker is OPEN",
            analysis="Auto-generated content rejection rate exceeds 40% or pending queue exceeds 30 items.",
            recommendation="Review rejection reasons. Check prompt quality and gap detection accuracy.",
            claude_prompt="Check content_generation_queue rejection rate and pending count.",
            impact="Content gaps not being auto-filled while circuit breaker is open.",
            files=["mandarin/ai/agentic.py"],
        ))

    # 2. Prescription execution rate
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='executed' THEN 1 ELSE 0 END) as executed,
                   SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors
            FROM prescription_execution_log
            WHERE created_at >= datetime('now', '-30 days')
        """).fetchone()

        total = (row["total"] or 0) if row else 0
        if total >= 5:
            errors = (row["errors"] or 0)
            if errors / total > 0.30:
                findings.append(_finding(
                    dimension="agentic",
                    severity="medium",
                    title=f"Prescription execution error rate: {errors}/{total}",
                    analysis="More than 30% of auto-executed prescriptions are failing.",
                    recommendation="Review prescription_execution_log for error patterns.",
                    claude_prompt="Check prescription_execution_log for recent errors.",
                    impact="Automated loop closure degraded — prescriptions require manual execution.",
                    files=["mandarin/ai/agentic.py"],
                ))
    except sqlite3.OperationalError:
        pass

    # 3. Stale competitor signals
    try:
        row = conn.execute("""
            SELECT MAX(created_at) as last_signal FROM competitor_signals
        """).fetchone()
        if row and row["last_signal"]:
            # Check if older than 14 days
            last = row["last_signal"]
            check = conn.execute(
                "SELECT ? < datetime('now', '-14 days') as stale", (last,)
            ).fetchone()
            if check and check["stale"]:
                findings.append(_finding(
                    dimension="agentic",
                    severity="low",
                    title="No competitor signals in 14+ days",
                    analysis="Competitor monitoring has not produced signals recently.",
                    recommendation="Check competitor crawl pipeline or add signals manually.",
                    claude_prompt="Check competitor_signals table for recent entries.",
                    impact="Strategic intelligence may be stale.",
                    files=["mandarin/ai/agentic.py"],
                ))
    except sqlite3.OperationalError:
        pass

    return findings
