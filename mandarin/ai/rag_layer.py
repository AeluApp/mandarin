"""RAG Layer for HSK 6+ and GenAI Hardening (Doc 21).

Part 1: RAG architecture — retrieval-augmented generation for HSK 6+ vocabulary.
Part 2: G3 — prompt regression test suite.
Part 3: G6 — JSON generation failure logging and analysis.

Uses CC-CEDICT as the primary knowledge base source.
"""

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CC-CEDICT PARSER
# ─────────────────────────────────────────────

CEDICT_LINE_RE = re.compile(
    r'^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$'
)


def import_cc_cedict(conn: sqlite3.Connection, cedict_path: str) -> dict:
    """Parse CC-CEDICT and populate rag_knowledge_base.

    Only imports items that appear in the content_item table with hsk_level set.
    Idempotent — updates existing entries on re-import.
    """
    path = Path(cedict_path)
    if not path.exists():
        return {"error": f"CC-CEDICT file not found at {cedict_path}"}

    # Build HSK lookup from content_item
    try:
        hsk_items = conn.execute("""
            SELECT DISTINCT hanzi, hsk_level FROM content_item
            WHERE hsk_level IS NOT NULL AND status='drill_ready'
        """).fetchall()
    except sqlite3.OperationalError:
        return {"error": "content_item table not accessible"}

    hsk_lookup = {r["hanzi"]: r["hsk_level"] for r in hsk_items}

    imported = 0
    skipped = 0
    errors = 0
    version = _get_cedict_version(cedict_path)

    with open(cedict_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = CEDICT_LINE_RE.match(line)
            if not match:
                continue

            traditional, simplified, pinyin_raw, definitions_raw = match.groups()

            if simplified not in hsk_lookup:
                skipped += 1
                continue

            definitions = [d.strip() for d in definitions_raw.split("/") if d.strip()]
            substantive_defs = [
                d for d in definitions
                if not d.startswith("variant of") and
                   not d.startswith("see ") and
                   len(d) > 3
            ]
            if not substantive_defs:
                skipped += 1
                continue

            pinyin = pinyin_raw.replace("u:", "u:")

            try:
                existing = conn.execute(
                    "SELECT id FROM rag_knowledge_base WHERE hanzi=?",
                    (simplified,),
                ).fetchone()

                defs_json = json.dumps(substantive_defs, ensure_ascii=False)
                trad = traditional if traditional != simplified else None
                hsk = hsk_lookup[simplified]

                if existing:
                    conn.execute("""
                        UPDATE rag_knowledge_base SET
                            pinyin=?, cc_cedict_definitions=?,
                            traditional_form=?, hsk_level=?,
                            cc_cedict_version=?,
                            last_updated_at=datetime('now')
                        WHERE hanzi=?
                    """, (pinyin, defs_json, trad, hsk, version, simplified))
                else:
                    conn.execute("""
                        INSERT INTO rag_knowledge_base
                        (hanzi, pinyin, cc_cedict_definitions,
                         traditional_form, hsk_level, cc_cedict_version)
                        VALUES (?,?,?,?,?,?)
                    """, (simplified, pinyin, defs_json, trad, hsk, version))
                imported += 1
            except Exception as e:
                errors += 1
                logger.debug("CEDICT import error for %s: %s", simplified, e)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def _get_cedict_version(cedict_path: str) -> str:
    try:
        with open(cedict_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#! version="):
                    return line.strip().split("=")[1]
    except Exception:
        pass
    return "unknown"


# ─────────────────────────────────────────────
# EXAMPLE SENTENCE ENRICHMENT
# ─────────────────────────────────────────────

def enrich_with_example_sentences(
    conn: sqlite3.Connection,
    min_hsk_level: int = 5,
) -> dict:
    """Enrich KB entries with example sentences from approved content."""
    try:
        needs_examples = conn.execute("""
            SELECT hanzi, hsk_level FROM rag_knowledge_base
            WHERE hsk_level >= ?
            AND (example_sentences IS NULL OR example_sentences = '[]')
            ORDER BY hsk_level ASC
            LIMIT 50
        """, (min_hsk_level,)).fetchall()
    except sqlite3.OperationalError:
        return {"enriched": 0, "needs_examples": 0}

    enriched = 0
    for item in needs_examples:
        try:
            corpus_examples = conn.execute("""
                SELECT ci.hanzi as word, ci.english, ci.hsk_level
                FROM content_item ci
                WHERE ci.status='drill_ready'
                AND ci.hanzi LIKE '%' || ? || '%'
                AND ci.item_type IN ('sentence', 'phrase')
                LIMIT 3
            """, (item["hanzi"],)).fetchall()
        except sqlite3.OperationalError:
            continue

        examples = []
        for ex in corpus_examples:
            examples.append({
                "sentence_hanzi": ex["word"],
                "translation": ex["english"],
                "source": "aelu_corpus",
                "hsk_ceiling": ex["hsk_level"],
            })

        if examples:
            conn.execute("""
                UPDATE rag_knowledge_base
                SET example_sentences=?
                WHERE hanzi=?
            """, (json.dumps(examples, ensure_ascii=False), item["hanzi"]))
            enriched += 1

    return {"enriched": enriched, "needs_examples": len(needs_examples)}


# ─────────────────────────────────────────────
# RETRIEVAL FUNCTION
# ─────────────────────────────────────────────

def retrieve_context_for_generation(
    conn: sqlite3.Connection,
    hanzi_list: list[str],
    prompt_key: str,
    include_examples: bool = True,
    max_examples_per_item: int = 2,
) -> dict:
    """Retrieve RAG context for a list of vocabulary items.

    Returns structured context for injection into Qwen prompts.
    """
    found = []
    missing = []

    for hanzi in hanzi_list:
        entry = conn.execute(
            "SELECT * FROM rag_knowledge_base WHERE hanzi=?",
            (hanzi,),
        ).fetchone()

        if not entry:
            missing.append(hanzi)
            _log_retrieval(conn, hanzi, retrieved=0, prompt_key=prompt_key)
            continue

        entry = dict(entry)
        definitions = json.loads(entry["cc_cedict_definitions"] or "[]")
        examples = json.loads(entry["example_sentences"] or "[]")
        synonyms = json.loads(entry["near_synonyms"] or "[]")
        errors = json.loads(entry["learner_errors"] or "[]")

        item_context = {
            "hanzi": hanzi,
            "pinyin": entry["pinyin"],
            "definitions": definitions[:3],
            "examples": examples[:max_examples_per_item] if include_examples else [],
            "near_synonyms": synonyms[:2],
            "learner_errors": errors[:2],
            "drift_risk": entry["drift_risk"],
        }
        found.append(item_context)
        _log_retrieval(
            conn, hanzi, retrieved=1,
            num_examples=len(examples),
            prompt_key=prompt_key,
        )

    # --- Supplement with LanceDB vector search for missing items ---
    vector_supplemented = 0
    if missing:
        try:
            from .genai_layer import _get_lance_db, _get_multilingual_model
            db = _get_lance_db()
            if db is not None:
                table = db.open_table("item_embeddings")
                model = _get_multilingual_model()
                # Build a query from the missing hanzi
                query_text = " ".join(missing)
                query_emb = model.encode([query_text], show_progress_bar=False)[0].tolist()
                vector_results = table.search(query_emb).limit(3).to_pandas()

                found_ids = {item["hanzi"] for item in found}
                for _, vrow in vector_results.iterrows():
                    v_hanzi = vrow.get("hanzi", "")
                    if v_hanzi and v_hanzi not in found_ids:
                        # Try to get full context from KB
                        entry = conn.execute(
                            "SELECT * FROM rag_knowledge_base WHERE hanzi=?",
                            (v_hanzi,),
                        ).fetchone()
                        if entry:
                            entry = dict(entry)
                            definitions = json.loads(entry["cc_cedict_definitions"] or "[]")
                            examples = json.loads(entry["example_sentences"] or "[]")
                            synonyms = json.loads(entry["near_synonyms"] or "[]")
                            errors = json.loads(entry["learner_errors"] or "[]")
                            item_context = {
                                "hanzi": v_hanzi,
                                "pinyin": entry["pinyin"],
                                "definitions": definitions[:3],
                                "examples": examples[:max_examples_per_item] if include_examples else [],
                                "near_synonyms": synonyms[:2],
                                "learner_errors": errors[:2],
                                "drift_risk": entry["drift_risk"],
                            }
                            found.append(item_context)
                            found_ids.add(v_hanzi)
                            vector_supplemented += 1
                        else:
                            # No KB entry, but we have embedding metadata
                            found.append({
                                "hanzi": v_hanzi,
                                "pinyin": vrow.get("pinyin", ""),
                                "definitions": [vrow.get("english", "")],
                                "examples": [],
                                "near_synonyms": [],
                                "learner_errors": [],
                                "drift_risk": None,
                            })
                            found_ids.add(v_hanzi)
                            vector_supplemented += 1
                # Remove vector-found items from missing list
                missing = [h for h in missing if h not in found_ids]
        except Exception:
            pass  # Vector search is supplementary — never block retrieval

    context_text = _format_context_for_prompt(found, missing)

    return {
        "context_text": context_text,
        "items_found": found,
        "items_missing": missing,
        "retrieval_logged": True,
        "vector_supplemented": vector_supplemented,
    }


def _format_context_for_prompt(found: list, missing: list) -> str:
    """Format retrieved context as structured text for Qwen prompt injection."""
    if not found and not missing:
        return ""

    parts = ["## Reference vocabulary (use exactly as specified)\n"]

    for item in found:
        parts.append(f"**{item['hanzi']}** ({item['pinyin']})")
        if item["definitions"]:
            parts.append(f"  Meanings: {'; '.join(item['definitions'][:2])}")
        if item["examples"]:
            ex = item["examples"][0]
            parts.append(f"  Example: {ex.get('sentence_hanzi', '')}")
        if item["near_synonyms"]:
            for syn in item["near_synonyms"][:1]:
                parts.append(
                    f"  Distinguish from: {syn.get('hanzi', '')} -- "
                    f"{syn.get('distinction', '')}"
                )
        if item["learner_errors"]:
            err = item["learner_errors"][0]
            parts.append(f"  Common error: {err.get('error_description', '')}")
        if item["drift_risk"] == "high":
            parts.append("  WARNING: Usage may have evolved -- stay conservative")
        parts.append("")

    if missing:
        parts.append(
            f"## Items not in knowledge base (use with caution): {', '.join(missing)}"
        )
        parts.append("For these items, use conservative, widely-attested usage only.")

    return "\n".join(parts)


def _log_retrieval(conn, hanzi, retrieved, num_examples=0, prompt_key=None):
    try:
        conn.execute("""
            INSERT INTO rag_retrieval_log
            (hanzi, retrieved, num_examples_retrieved, generation_prompt_key)
            VALUES (?,?,?,?)
        """, (hanzi, retrieved, num_examples, prompt_key))
    except sqlite3.OperationalError:
        pass


# ─────────────────────────────────────────────
# RAG-AUGMENTED GENERATION
# ─────────────────────────────────────────────

def generate_with_rag(
    conn: sqlite3.Connection,
    hanzi_list: list[str],
    prompt_key: str,
    base_prompt: str,
    hsk_level: int | None = None,
    temperature: float = 0.7,
) -> dict | None:
    """Generate Qwen content with RAG augmentation for HSK 6+.

    If hsk_level < 6, calls Qwen without RAG.
    Logs all failures (G6).
    """
    try:
        from .ollama_client import generate, is_ollama_available
        from .genai_layer import _parse_llm_json
    except ImportError:
        return None

    if not is_ollama_available():
        return None

    use_rag = hsk_level is not None and hsk_level >= 6
    augmented_prompt = base_prompt

    if use_rag:
        retrieval = retrieve_context_for_generation(conn, hanzi_list, prompt_key)
        if retrieval["context_text"]:
            augmented_prompt = retrieval["context_text"] + "\n\n" + base_prompt

        drift_items = [
            i["hanzi"] for i in retrieval["items_found"]
            if i.get("drift_risk") == "high"
        ]
        if drift_items:
            _log_drift_risk_flag(conn, drift_items, prompt_key)

    result = generate(
        augmented_prompt,
        temperature=temperature,
        conn=conn,
        task_type=prompt_key,
    )

    if not result.success or not result.text.strip():
        log_json_failure(conn, prompt_key, augmented_prompt,
                         result.text or "", failure_type="empty_response")
        return None

    parsed = _parse_llm_json(result.text, conn=conn, task_type=prompt_key)
    if parsed is None:
        log_json_failure(conn, prompt_key, augmented_prompt, result.text)
        return None

    return parsed


# ─────────────────────────────────────────────
# G6: JSON FAILURE LOGGING
# ─────────────────────────────────────────────

def log_json_failure(
    conn: sqlite3.Connection,
    prompt_key: str,
    prompt: str,
    raw_response: str,
    failure_type: str = "invalid_json",
) -> None:
    """Log a Qwen generation failure for audit cycle analysis."""
    try:
        conn.execute("""
            INSERT INTO json_generation_failures
            (prompt_key, failure_type, prompt_length,
             response_length, response_sample)
            VALUES (?,?,?,?,?)
        """, (
            prompt_key, failure_type,
            len(prompt),
            len(raw_response) if raw_response else 0,
            (raw_response or "")[:500],
        ))
    except sqlite3.OperationalError:
        logger.debug("json_generation_failures table missing")


def _log_drift_risk_flag(conn, hanzi_list: list[str], prompt_key: str):
    try:
        conn.execute("""
            INSERT INTO drift_risk_flags (hanzi_list, prompt_key)
            VALUES (?,?)
        """, (json.dumps(hanzi_list), prompt_key))
    except sqlite3.OperationalError:
        pass


# ─────────────────────────────────────────────
# G3: PROMPT REGRESSION TEST SUITE
# ─────────────────────────────────────────────

PROMPT_REGRESSION_SUITE = {
    "drill_generation_recognition": {
        "description": "Generate recognition drill for vocabulary item",
        "reference_inputs": [
            {
                "input": {"hanzi": "民主", "pinyin": "minzhu", "meaning": "democracy",
                          "hsk_level": 6},
                "assertions": [
                    ("field_present", "question"),
                    ("field_present", "correct_answer"),
                    ("field_present", "distractors"),
                    ("list_length_gte", "distractors", 2),
                ],
            },
            {
                "input": {"hanzi": "把", "pinyin": "ba", "meaning": "disposal marker",
                          "hsk_level": 3},
                "assertions": [
                    ("field_present", "question"),
                    ("field_present", "correct_answer"),
                ],
            },
        ],
    },
    "error_shape_classification": {
        "description": "Classify error type from wrong answer event",
        "reference_inputs": [
            {
                "input": {"target": "买 (buy)", "response": "卖 (sell)",
                          "item_pinyin": "mai", "response_pinyin": "mai"},
                "assertions": [
                    ("field_present", "error_shape"),
                    ("field_value_in", "error_shape",
                     ["tonal", "lexical_selection", "near_synonym"]),
                ],
            },
        ],
    },
    "session_diagnostic": {
        "description": "Generate end-of-session diagnostic",
        "reference_inputs": [
            {
                "input": {"session_accuracy": 0.72, "dominant_error": "tonal",
                          "items_reviewed": 20, "new_items": 3},
                "assertions": [
                    ("field_present", "summary"),
                    ("field_present", "recommendation"),
                    ("field_length_gte", "summary", 20),
                ],
            },
        ],
    },
}


def run_prompt_regression_suite(conn: sqlite3.Connection) -> dict:
    """Run the regression suite against PROMPT_REGISTRY prompts.

    Called weekly from audit cycle and after PROMPT_REGISTRY updates.
    Returns {passed, failed, skipped, findings, audit_findings}.
    """
    try:
        from .ollama_client import is_ollama_available
        from .genai_layer import _parse_llm_json
    except ImportError:
        return {"passed": 0, "failed": 0, "skipped": 0, "findings": [],
                "error": "imports unavailable"}

    if not is_ollama_available():
        return {"passed": 0, "failed": 0, "skipped": len(PROMPT_REGRESSION_SUITE),
                "findings": [], "note": "ollama unavailable"}

    results = {"passed": 0, "failed": 0, "skipped": 0, "findings": []}

    try:
        from .genai_layer import PROMPT_REGISTRY
    except ImportError:
        PROMPT_REGISTRY = {}

    for prompt_key, suite in PROMPT_REGRESSION_SUITE.items():
        prompt_template = PROMPT_REGISTRY.get(prompt_key, {}).get("prompt_text")
        if not prompt_template:
            results["skipped"] += 1
            continue

        for i, test_case in enumerate(suite["reference_inputs"]):
            try:
                prompt = _build_prompt_from_template(prompt_template, test_case["input"])
                from .ollama_client import generate
                result = generate(prompt, temperature=0.3, conn=conn, task_type=prompt_key)

                if not result.success or not result.text.strip():
                    results["failed"] += 1
                    results["findings"].append({
                        "prompt_key": prompt_key, "test_case": i,
                        "failure": "no_response",
                    })
                    continue

                parsed = _parse_llm_json(result.text, conn=conn, task_type=prompt_key)
                if not parsed:
                    results["failed"] += 1
                    results["findings"].append({
                        "prompt_key": prompt_key, "test_case": i,
                        "failure": "invalid_json",
                        "response_sample": result.text[:200],
                    })
                    continue

                assertion_failures = run_assertions(parsed, test_case["assertions"])
                if assertion_failures:
                    results["failed"] += 1
                    results["findings"].append({
                        "prompt_key": prompt_key, "test_case": i,
                        "failure": "assertion_failure",
                        "failed_assertions": assertion_failures,
                    })
                else:
                    results["passed"] += 1

            except Exception as e:
                results["failed"] += 1
                results["findings"].append({
                    "prompt_key": prompt_key, "test_case": i,
                    "failure": f"exception: {str(e)[:100]}",
                })

    if results["failed"] > 0:
        results["audit_findings"] = [{
            "dimension": "genai",
            "title": f'{results["failed"]} prompt regression test(s) failed',
            "severity": "high",
            "detail": (
                f'{results["passed"]} passed, {results["failed"]} failed. '
                "Regression failures indicate prompt or model degradation."
            ),
            "recommendation": "Review failed test cases in regression log.",
        }]

    try:
        conn.execute("""
            INSERT INTO prompt_regression_log
            (passed, failed, skipped, findings_json)
            VALUES (?,?,?,?)
        """, (
            results["passed"], results["failed"], results["skipped"],
            json.dumps(results["findings"]),
        ))
    except sqlite3.OperationalError:
        pass

    return results


def run_assertions(parsed: dict, assertions: list) -> list[str]:
    """Run structured assertions against parsed Qwen output. Returns failures."""
    failures = []
    for assertion in assertions:
        kind = assertion[0]
        try:
            if kind == "field_present":
                if assertion[1] not in parsed:
                    failures.append(f"Missing field: {assertion[1]}")
            elif kind == "field_contains":
                val = str(parsed.get(assertion[1], ""))
                if assertion[2] not in val:
                    failures.append(f"Field '{assertion[1]}' does not contain '{assertion[2]}'")
            elif kind == "no_field_contains":
                val = str(parsed.get(assertion[1], ""))
                if assertion[2] in val:
                    failures.append(f"Field '{assertion[1]}' should not contain '{assertion[2]}'")
            elif kind == "list_length_gte":
                val = parsed.get(assertion[1], [])
                if not isinstance(val, list) or len(val) < assertion[2]:
                    actual = len(val) if isinstance(val, list) else 0
                    failures.append(f"Field '{assertion[1]}' length {actual} < {assertion[2]}")
            elif kind == "field_length_gte":
                val = str(parsed.get(assertion[1], ""))
                if len(val) < assertion[2]:
                    failures.append(f"Field '{assertion[1]}' too short: {len(val)} < {assertion[2]}")
            elif kind == "value_range":
                val = parsed.get(assertion[1])
                if val is None or not (assertion[2] <= float(val) <= assertion[3]):
                    failures.append(
                        f"Field '{assertion[1]}' value {val} not in [{assertion[2]}, {assertion[3]}]"
                    )
            elif kind == "value_less_than":
                val = parsed.get(assertion[1])
                if val is None or float(val) >= assertion[2]:
                    failures.append(f"Field '{assertion[1]}' value {val} not < {assertion[2]}")
            elif kind == "value_greater_than":
                val = parsed.get(assertion[1])
                if val is None or float(val) <= assertion[2]:
                    failures.append(f"Field '{assertion[1]}' value {val} not > {assertion[2]}")
            elif kind == "field_value_in":
                val = parsed.get(assertion[1])
                if val not in assertion[2]:
                    failures.append(f"Field '{assertion[1]}' value '{val}' not in {assertion[2]}")
        except Exception as e:
            failures.append(f"Assertion error ({kind}): {str(e)[:50]}")
    return failures


def _build_prompt_from_template(template: str, input_data: dict) -> str:
    try:
        return template.format(**input_data)
    except KeyError:
        for k, v in input_data.items():
            template = template.replace(f"{{{k}}}", str(v))
        return template


# ─────────────────────────────────────────────
# ANALYZERS
# ─────────────────────────────────────────────

def analyze_generation_failures(conn: sqlite3.Connection) -> list[dict]:
    """Detect JSON generation failure rate by prompt key. G6 audit."""
    from ..intelligence._base import _finding
    findings = []

    try:
        failure_stats = conn.execute("""
            SELECT prompt_key,
                   COUNT(*) as total_failures,
                   SUM(CASE WHEN failure_type='invalid_json' THEN 1 ELSE 0 END) as json_fails,
                   SUM(CASE WHEN failure_type='empty_response' THEN 1 ELSE 0 END) as empty_fails
            FROM json_generation_failures
            WHERE failed_at >= datetime('now','-30 days')
            GROUP BY prompt_key
            HAVING total_failures >= 3
            ORDER BY total_failures DESC
        """).fetchall()

        for row in failure_stats:
            severity = "high" if row["total_failures"] >= 10 else "medium"
            findings.append(_finding(
                dimension="genai",
                severity=severity,
                title=f"Prompt '{row['prompt_key']}' has {row['total_failures']} generation failures (30d)",
                analysis=f"{row['json_fails']} invalid JSON, {row['empty_fails']} empty responses.",
                recommendation="Inspect failure samples in json_generation_failures. "
                               "Check prompt structure and Ollama model.",
                claude_prompt=f"Query json_generation_failures WHERE prompt_key='{row['prompt_key']}' "
                              "for response_sample patterns.",
                impact="Silent generation failures degrade user-facing content quality.",
                files=["mandarin/ai/rag_layer.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # Drift risk items not reviewed
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM drift_risk_flags
            WHERE reviewed=0
            AND flagged_at >= datetime('now','-7 days')
        """).fetchone()
        unreviewed = (row["cnt"] if row else 0) or 0

        if unreviewed > 0:
            findings.append(_finding(
                dimension="genai",
                severity="medium",
                title=f"{unreviewed} generation request(s) with drift-risk vocabulary, unreviewed",
                analysis="Content generated with slang, political, or evolving vocabulary "
                         "should be reviewed by a native speaker.",
                recommendation="Review flagged items in drift_risk_flags table.",
                claude_prompt="Query drift_risk_flags WHERE reviewed=0 for pending review items.",
                impact="Drift-risk vocabulary may produce unnatural or incorrect Chinese.",
                files=["mandarin/ai/rag_layer.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings


def analyze_rag_coverage(conn: sqlite3.Connection) -> list[dict]:
    """Detect gaps in RAG knowledge base coverage."""
    from ..intelligence._base import _finding
    findings = []

    # HSK 6+ content items with no KB entry
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT ci.hanzi) as cnt
            FROM content_item ci
            WHERE ci.hsk_level >= 6
            AND ci.status = 'drill_ready'
            AND NOT EXISTS (
                SELECT 1 FROM rag_knowledge_base rkb
                WHERE rkb.hanzi = ci.hanzi
            )
        """).fetchone()
        missing_count = (row["cnt"] if row else 0) or 0

        if missing_count > 0:
            findings.append(_finding(
                dimension="rag",
                severity="high",
                title=f"{missing_count} HSK 6+ word(s) not in RAG knowledge base",
                analysis="Generation for these items falls back to unreliable parametric knowledge.",
                recommendation="Run import_cc_cedict() with latest CC-CEDICT file.",
                claude_prompt="Find content_item rows with hsk_level>=6 not in rag_knowledge_base.",
                impact="HSK 6+ content without RAG grounding risks inaccurate Chinese.",
                files=["mandarin/ai/rag_layer.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # Items in KB with no example sentences (HSK 6+)
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM rag_knowledge_base
            WHERE hsk_level >= 6
            AND (example_sentences IS NULL OR example_sentences = '[]')
        """).fetchone()
        no_examples = (row["cnt"] if row else 0) or 0

        if no_examples > 50:
            findings.append(_finding(
                dimension="rag",
                severity="medium",
                title=f"{no_examples} HSK 6+ items in KB with no example sentences",
                analysis="Generation quality improves significantly with example sentences.",
                recommendation="Run enrich_with_example_sentences(min_hsk_level=6).",
                claude_prompt="Query rag_knowledge_base for HSK 6+ entries without examples.",
                impact="Missing examples reduce grounding quality for rare vocabulary.",
                files=["mandarin/ai/rag_layer.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # Retrieval miss rate
    try:
        miss_stats = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN retrieved=0 THEN 1 ELSE 0 END) as misses
            FROM rag_retrieval_log
            WHERE queried_at >= datetime('now','-7 days')
        """).fetchone()

        total = (miss_stats["total"] or 0) if miss_stats else 0
        misses = (miss_stats["misses"] or 0) if miss_stats else 0

        if total >= 20 and misses / total > 0.15:
            rate = misses / total
            findings.append(_finding(
                dimension="rag",
                severity="medium",
                title=f"RAG retrieval miss rate {rate:.0%} this week",
                analysis=f"{misses} of {total} retrieval requests returned no context.",
                recommendation="Identify common misses from rag_retrieval_log and add to KB.",
                claude_prompt="Query rag_retrieval_log WHERE retrieved=0 for most common hanzi.",
                impact="High miss rate means RAG is not providing grounding where needed.",
                files=["mandarin/ai/rag_layer.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings
