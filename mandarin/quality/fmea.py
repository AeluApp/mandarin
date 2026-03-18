"""Failure Mode and Effects Analysis (FMEA) — Six Sigma risk scoring.

Each failure mode gets severity x occurrence x detection = RPN (Risk Priority Number).
RPN > 100: critical. RPN 50-100: significant. RPN < 50: acceptable.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Seeded process FMEAs — severity/detection are design-time estimates,
# occurrence is updated from actual data when available.
_PROCESS_FMEAS = [
    # Drill Grading
    {"process": "drill_grading", "failure_mode": "Wrong answer accepted as correct",
     "cause": "Fuzzy matching too lenient", "effect": "Learner believes incorrect answer is right",
     "severity": 9, "occurrence": 2, "detection": 4,
     "data_query": "SELECT COUNT(*) FROM review_event WHERE rating >= 3 AND reviewed_at >= datetime('now', '-7 days')"},
    {"process": "drill_grading", "failure_mode": "Correct answer rejected",
     "cause": "Exact match required but variant is valid", "effect": "Learner frustrated, loses confidence",
     "severity": 6, "occurrence": 3, "detection": 5},
    {"process": "drill_grading", "failure_mode": "Tone not validated in production drill",
     "cause": "TTS comparison fails silently", "effect": "Tone errors not caught",
     "severity": 7, "occurrence": 4, "detection": 6},

    # SRS Scheduling
    {"process": "srs_scheduling", "failure_mode": "Item scheduled too late (forgotten)",
     "cause": "FSRS stability overestimated", "effect": "Learner forgets, must relearn from scratch",
     "severity": 8, "occurrence": 3, "detection": 3,
     "data_query": "SELECT COUNT(*) FROM review_event WHERE rating = 1 AND reviewed_at >= datetime('now', '-7 days')"},
    {"process": "srs_scheduling", "failure_mode": "Item scheduled too early (wasted time)",
     "cause": "Desirable difficulty too aggressive", "effect": "Easy items crowd out harder ones",
     "severity": 4, "occurrence": 4, "detection": 5},
    {"process": "srs_scheduling", "failure_mode": "New item ceiling too high",
     "cause": "Queue model underestimates load", "effect": "Cognitive overload, session too hard",
     "severity": 7, "occurrence": 2, "detection": 4},
    {"process": "srs_scheduling", "failure_mode": "Interference pair not separated",
     "cause": "Separation algorithm missed pair", "effect": "Confusion between similar items reinforced",
     "severity": 6, "occurrence": 3, "detection": 5},

    # Content Generation
    {"process": "content_generation", "failure_mode": "Generated Chinese contains errors",
     "cause": "LLM hallucination in character/pinyin", "effect": "Learner memorizes wrong content",
     "severity": 10, "occurrence": 3, "detection": 3,
     "data_query": "SELECT COUNT(*) FROM pi_ai_review_queue WHERE status='rejected' AND created_at >= datetime('now', '-7 days')"},
    {"process": "content_generation", "failure_mode": "Drill distractor is also correct",
     "cause": "MC option generation doesn't validate", "effect": "Ambiguous drill, learner confused",
     "severity": 7, "occurrence": 3, "detection": 4},
    {"process": "content_generation", "failure_mode": "Reading passage too hard for level",
     "cause": "Vocabulary coverage not checked", "effect": "Learner can't read, abandons session",
     "severity": 6, "occurrence": 2, "detection": 3},
    {"process": "content_generation", "failure_mode": "Generated content duplicates existing",
     "cause": "Dedup check fails", "effect": "Wasted generation, bloated content DB",
     "severity": 3, "occurrence": 4, "detection": 2},
    {"process": "content_generation", "failure_mode": "Conversation scenario culturally inappropriate",
     "cause": "LLM lacks cultural awareness", "effect": "Offensive content damages trust",
     "severity": 9, "occurrence": 1, "detection": 5},

    # Session Planning
    {"process": "session_planning", "failure_mode": "Session too long (user abandons)",
     "cause": "Block time budgets exceed target", "effect": "Low completion rate, churn",
     "severity": 7, "occurrence": 3, "detection": 3,
     "data_query": "SELECT COUNT(*) FROM session_log WHERE completed=0 AND started_at >= datetime('now', '-7 days')"},
    {"process": "session_planning", "failure_mode": "No reading block despite having passages",
     "cause": "Passage picker returns None", "effect": "Missed learning opportunity",
     "severity": 4, "occurrence": 3, "detection": 6},
    {"process": "session_planning", "failure_mode": "Conversation block with no scenarios for level",
     "cause": "HSK level has no scenarios", "effect": "Block skipped, session feels incomplete",
     "severity": 5, "occurrence": 2, "detection": 4},
    {"process": "session_planning", "failure_mode": "Thompson Sampling stuck on suboptimal drill type",
     "cause": "Insufficient exploration", "effect": "Learner gets wrong drill types repeatedly",
     "severity": 6, "occurrence": 2, "detection": 7},
    {"process": "session_planning", "failure_mode": "Dijkstra path leads to items beyond learner's level",
     "cause": "Graph edge weights miscalibrated", "effect": "Items too hard, frustration",
     "severity": 7, "occurrence": 2, "detection": 5},
    {"process": "session_planning", "failure_mode": "LP optimization produces degenerate solution",
     "cause": "scipy solver finds local minimum", "effect": "Suboptimal drill ordering",
     "severity": 4, "occurrence": 1, "detection": 3},
    {"process": "session_planning", "failure_mode": "Metacognitive prompts interrupt flow state",
     "cause": "Confidence prompt too frequent", "effect": "Session feels tedious",
     "severity": 5, "occurrence": 3, "detection": 6},
    {"process": "session_planning", "failure_mode": "SDT choice ignored in block allocation",
     "cause": "User choice not wired to block weights", "effect": "Autonomy promise broken",
     "severity": 6, "occurrence": 2, "detection": 4},
]


def get_process_fmeas(conn=None) -> list[dict]:
    """Return all FMEAs with RPNs, optionally updating occurrence from real data."""
    results = []
    for fmea in _PROCESS_FMEAS:
        f = dict(fmea)
        # Try to update occurrence from actual data
        if conn and f.get("data_query"):
            try:
                count = conn.execute(f["data_query"]).fetchone()[0]
                # Scale: 0-2 events=1, 3-10=3, 11-50=5, 51-200=7, 200+=9
                if count <= 2:
                    f["occurrence"] = max(1, f["occurrence"])
                elif count <= 10:
                    f["occurrence"] = max(3, f["occurrence"])
                elif count <= 50:
                    f["occurrence"] = 5
                elif count <= 200:
                    f["occurrence"] = 7
                else:
                    f["occurrence"] = 9
                f["occurrence_source"] = "data"
                f["occurrence_count"] = count
            except Exception:
                f["occurrence_source"] = "estimate"
        else:
            f["occurrence_source"] = "estimate"

        f["rpn"] = f["severity"] * f["occurrence"] * f["detection"]
        f.pop("data_query", None)
        results.append(f)

    return sorted(results, key=lambda x: x["rpn"], reverse=True)


def get_critical_fmeas(conn=None, threshold=100) -> list[dict]:
    """Return only FMEAs with RPN above threshold."""
    return [f for f in get_process_fmeas(conn) if f["rpn"] >= threshold]


def design_fmea(conn, feature_description: str) -> list[dict]:
    """Generate a design FMEA for a proposed new feature using LLM.

    Returns list of potential failure modes with RPN scores.
    Falls back to empty list if LLM unavailable.
    """
    try:
        from ..ai.ollama_client import generate, is_model_capable
        if not is_model_capable("experiment_design"):
            return []

        prompt = (
            "Analyze this proposed feature for a Mandarin learning app and "
            "identify 3-5 potential failure modes.\n\n"
            f"Feature: {feature_description}\n\n"
            "For each failure mode, provide:\n"
            "- failure_mode: what could go wrong\n"
            "- cause: why it might happen\n"
            "- effect: impact on the learner\n"
            "- severity: 1-10 (10=catastrophic)\n"
            "- occurrence: 1-10 (10=very likely)\n"
            "- detection: 1-10 (10=very hard to detect)\n\n"
            "Return JSON array."
        )

        result = generate(
            prompt=prompt,
            system="You are a Six Sigma Black Belt analyzing failure modes.",
            temperature=0.3,
            max_tokens=1024,
            conn=conn,
            task_type="experiment_design",
        )
        if result.success:
            import json
            modes = json.loads(result.text.strip())
            if isinstance(modes, list):
                for m in modes:
                    m["rpn"] = m.get("severity", 5) * m.get("occurrence", 5) * m.get("detection", 5)
                    m["process"] = "design_review"
                    m["source"] = "llm_generated"
                return modes
    except Exception:
        pass
    return []
