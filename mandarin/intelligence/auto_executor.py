"""Product Intelligence — Auto-fix executor.

Executes findings classified as 'auto_fix' by human_loop.classify_decision().
Reads target files, generates fixes via Ollama, validates, and applies them.

Safety guardrails:
- Only processes auto_fix findings
- Max 3 files per finding
- Only modifies files under mandarin/
- Smoke test after each fix (python -c "import mandarin")
- Reverts on failure and escalates to human
- Max 5 fixes per execution cycle
- Disabled by default (AUTO_FIX_ENABLED=true to enable)

Exports:
    execute_auto_fixes(conn) -> list[dict]
    execute_single_fix(conn, finding_id: int) -> dict
    EXECUTOR_ENABLED: bool
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, UTC
from pathlib import Path

from ._base import _safe_query, _safe_query_all, _safe_scalar
from .human_loop import classify_decision
from .prescription import _FINDING_TO_ACTION

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

from ..settings import AUTO_FIX_ENABLED
EXECUTOR_ENABLED = AUTO_FIX_ENABLED

_MAX_FIXES_PER_CYCLE = 5
_MAX_FILES_PER_FINDING = 3
_ALLOWED_PREFIX = "mandarin/"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SMOKE_TEST_TIMEOUT = 30  # seconds


# ── Table creation ─────────────────────────────────────────────────────────

def _ensure_tables(conn) -> None:
    """Create the auto_fix_execution log table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auto_fix_execution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            target_files TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'generating', 'validating',
                                 'applied', 'reverted', 'failed', 'escalated')),
            llm_model TEXT,
            llm_prompt TEXT,
            llm_response TEXT,
            generation_time_ms INTEGER,
            validation_passed INTEGER,
            validation_error TEXT,
            smoke_test_passed INTEGER,
            smoke_test_error TEXT,
            reverted INTEGER DEFAULT 0,
            escalated INTEGER DEFAULT 0,
            notes TEXT
        )
    """)
    conn.commit()


# ── Main entry points ─────────────────────────────────────────────────────

def execute_auto_fixes(conn) -> list[dict]:
    """Main entry point: find and execute all pending auto_fix findings.

    Returns a list of result dicts, one per attempted fix.
    Respects the EXECUTOR_ENABLED flag and rate limit.
    """
    if not EXECUTOR_ENABLED:
        logger.debug("Auto-fix executor disabled (set AUTO_FIX_ENABLED=true)")
        return []

    _ensure_tables(conn)

    # Query pending auto_fix findings
    candidates = _query_auto_fix_candidates(conn)
    if not candidates:
        logger.debug("Auto-fix executor: no pending auto_fix findings")
        return []

    results = []
    for candidate in candidates[:_MAX_FIXES_PER_CYCLE]:
        finding_id = candidate["id"]
        try:
            result = execute_single_fix(conn, finding_id)
            results.append(result)
        except Exception as exc:
            logger.exception("Auto-fix executor: unexpected error for finding #%d", finding_id)
            results.append({
                "finding_id": finding_id,
                "status": "failed",
                "error": str(exc),
            })

    applied = sum(1 for r in results if r.get("status") == "applied")
    failed = sum(1 for r in results if r.get("status") in ("failed", "reverted", "escalated"))
    logger.info(
        "Auto-fix executor: processed %d findings — %d applied, %d failed/escalated",
        len(results), applied, failed,
    )

    return results


def execute_single_fix(conn, finding_id: int) -> dict:
    """Execute a fix for a single finding.

    Steps:
    1. Validate finding is auto_fix eligible
    2. Resolve target files from _FINDING_TO_ACTION
    3. Read current file contents
    4. Generate fix via Ollama
    5. Apply the fix
    6. Validate (syntax check + smoke test)
    7. On failure: revert and escalate

    Returns a result dict with status and details.
    """
    _ensure_tables(conn)

    result = {
        "finding_id": finding_id,
        "status": "pending",
        "target_files": [],
        "error": None,
    }

    # 1. Load and validate finding
    finding_row = _safe_query(conn, """
        SELECT id, dimension, severity, title, analysis, status
        FROM pi_finding WHERE id = ?
    """, (finding_id,))

    if not finding_row:
        result["status"] = "failed"
        result["error"] = f"Finding #{finding_id} not found"
        _log_execution(conn, result)
        return result

    # Check finding is in an actionable state
    if finding_row["status"] in ("resolved", "rejected", "implemented", "verified"):
        result["status"] = "failed"
        result["error"] = f"Finding #{finding_id} is in terminal state: {finding_row['status']}"
        _log_execution(conn, result)
        return result

    # Reconstruct finding dict for classify_decision
    finding_dict = {
        "dimension": finding_row["dimension"],
        "severity": finding_row["severity"],
        "title": finding_row["title"],
        "analysis": finding_row["analysis"] or "",
        "files": [],
    }

    # Resolve files from _FINDING_TO_ACTION
    target_file, target_parameter, direction = _resolve_target(finding_dict)
    if target_file:
        finding_dict["files"] = [target_file]

    # Verify this is actually classified as auto_fix
    decision_class = classify_decision(finding_dict)
    if decision_class != "auto_fix":
        result["status"] = "failed"
        result["error"] = (
            f"Finding #{finding_id} classified as '{decision_class}', not 'auto_fix'. "
            f"Skipping to prevent unauthorized changes."
        )
        _log_execution(conn, result)
        return result

    # 2. Resolve target files
    if not target_file:
        result["status"] = "failed"
        result["error"] = f"No target file resolved for finding #{finding_id}"
        _log_execution(conn, result)
        return result

    # Expand directory targets to specific files (e.g. "mandarin/drills/" -> skip)
    if target_file.endswith("/"):
        result["status"] = "failed"
        result["error"] = (
            f"Target is a directory ({target_file}), not a specific file. "
            f"Cannot auto-fix directory-level targets."
        )
        _log_execution(conn, result)
        return result

    # Safety: only modify files under mandarin/
    if not target_file.startswith(_ALLOWED_PREFIX):
        result["status"] = "failed"
        result["error"] = f"Target file '{target_file}' is outside {_ALLOWED_PREFIX}"
        _log_execution(conn, result)
        return result

    # Safety: max files check
    target_files = [target_file]
    if len(target_files) > _MAX_FILES_PER_FINDING:
        result["status"] = "failed"
        result["error"] = f"Too many target files ({len(target_files)} > {_MAX_FILES_PER_FINDING})"
        _log_execution(conn, result)
        return result

    result["target_files"] = target_files

    # 3. Read current file contents
    abs_path = _PROJECT_ROOT / target_file
    if not abs_path.exists():
        result["status"] = "failed"
        result["error"] = f"Target file does not exist: {target_file}"
        _log_execution(conn, result)
        return result

    try:
        original_content = abs_path.read_text(encoding="utf-8")
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Cannot read {target_file}: {exc}"
        _log_execution(conn, result)
        return result

    # 4. Generate fix via Ollama
    _update_execution_status(conn, result, "generating")

    fix_result = _generate_fix(
        conn=conn,
        finding=finding_dict,
        target_file=target_file,
        target_parameter=target_parameter or "",
        direction=direction or "improve",
        file_content=original_content,
    )

    if not fix_result["success"]:
        result["status"] = "failed"
        result["error"] = f"LLM generation failed: {fix_result.get('error', 'unknown')}"
        _log_execution(conn, result, llm_response=fix_result)
        return result

    new_content = fix_result["new_content"]

    # Sanity: LLM should produce different content
    if new_content.strip() == original_content.strip():
        result["status"] = "failed"
        result["error"] = "LLM returned identical content — no fix generated"
        _log_execution(conn, result, llm_response=fix_result)
        return result

    # 5. Apply the fix (with backup)
    backup_path = _backup_file(abs_path)
    try:
        abs_path.write_text(new_content, encoding="utf-8")
    except Exception as exc:
        _restore_file(backup_path, abs_path)
        result["status"] = "failed"
        result["error"] = f"Failed to write fix: {exc}"
        _log_execution(conn, result, llm_response=fix_result)
        return result

    # 6. Validate
    _update_execution_status(conn, result, "validating")

    # 6a. Syntax check
    syntax_ok, syntax_error = _validate_syntax(abs_path)
    if not syntax_ok:
        _restore_file(backup_path, abs_path)
        result["status"] = "reverted"
        result["error"] = f"Syntax validation failed: {syntax_error}"
        _log_execution(conn, result, llm_response=fix_result,
                       validation_passed=False, validation_error=syntax_error)
        _escalate_finding(conn, finding_id, f"Auto-fix syntax error: {syntax_error}")
        result["status"] = "escalated"
        return result

    # 6b. Smoke test
    smoke_ok, smoke_error = _smoke_test(target_file)
    if not smoke_ok:
        _restore_file(backup_path, abs_path)
        result["status"] = "reverted"
        result["error"] = f"Smoke test failed: {smoke_error}"
        _log_execution(conn, result, llm_response=fix_result,
                       validation_passed=True, smoke_test_passed=False,
                       smoke_test_error=smoke_error)
        _escalate_finding(conn, finding_id, f"Auto-fix smoke test failed: {smoke_error}")
        result["status"] = "escalated"
        return result

    # 7. Success — record outcome
    _cleanup_backup(backup_path)
    result["status"] = "applied"
    _log_execution(conn, result, llm_response=fix_result,
                   validation_passed=True, smoke_test_passed=True)

    # Record to action_ledger for outcome verification and calibration
    try:
        from .action_ledger import record_action
        record_action(
            conn, "auto_executor", "apply_auto_fix", target_file,
            f"Auto-fixed finding #{finding_id}: {finding_dict['title'][:80]}",
            {"finding_severity": finding_dict["severity"],
             "finding_dimension": finding_dict["dimension"],
             "target_parameter": target_parameter or ""},
            verification_hours=48,
        )
    except Exception as exc:
        logger.debug("Auto-fix: action_ledger record failed: %s", exc)

    # Advance finding lifecycle: investigating -> diagnosed -> recommended -> implemented
    _advance_finding(conn, finding_id)

    logger.info(
        "Auto-fix executor: applied fix for finding #%d (%s) in %s",
        finding_id, finding_dict["title"][:60], target_file,
    )

    return result


# ── Query helpers ──────────────────────────────────────────────────────────

def _query_auto_fix_candidates(conn) -> list:
    """Find findings eligible for auto-fix execution.

    Criteria:
    - Status is investigating, diagnosed, or recommended (not terminal)
    - Classified as auto_fix by human_loop
    - Not already processed by auto_executor
    - Low severity (auto_fix gate in human_loop requires low severity)
    - OR runtime_health findings with auto-fixable patterns (any severity)
    """
    candidates = _safe_query_all(conn, """
        SELECT pf.id, pf.dimension, pf.severity, pf.title, pf.analysis, pf.status
        FROM pi_finding pf
        WHERE pf.status NOT IN ('resolved', 'rejected', 'implemented', 'verified')
          AND (
              pf.severity = 'low'
              OR (pf.dimension = 'runtime_health' AND pf.severity IN ('low', 'medium'))
          )
          AND pf.id NOT IN (
              SELECT finding_id FROM auto_fix_execution
              WHERE status IN ('applied', 'escalated')
          )
        ORDER BY pf.times_seen DESC, pf.created_at ASC
        LIMIT ?
    """, (_MAX_FIXES_PER_CYCLE * 2,))  # Fetch extra since some may not be auto_fix

    if not candidates:
        return []

    # Filter to only auto_fix classified findings
    auto_fix_candidates = []
    for row in candidates:
        finding_dict = {
            "dimension": row["dimension"],
            "severity": row["severity"],
            "title": row["title"],
            "analysis": row["analysis"] or "",
            "files": [],
        }
        # Resolve target file to populate files list
        target_file, _, _ = _resolve_target(finding_dict)
        if target_file:
            finding_dict["files"] = [target_file]

        if classify_decision(finding_dict) == "auto_fix":
            auto_fix_candidates.append(row)

    return auto_fix_candidates


def _resolve_target(finding_dict: dict) -> tuple:
    """Resolve target file, parameter, and direction from _FINDING_TO_ACTION.

    Returns (target_file, target_parameter, direction) or (None, None, None).
    """
    dimension = finding_dict.get("dimension", "")
    title = finding_dict.get("title", "")

    # runtime_health: extract file paths from analysis (Sentry stacktraces)
    if dimension == "runtime_health":
        analysis = finding_dict.get("analysis", "")
        target_file = _extract_runtime_target_file(analysis)
        if target_file:
            error_pattern = _detect_runtime_error_pattern(title, analysis)
            return target_file, error_pattern, "fix"

    # Try keyword match first
    for (dim, keyword), (f, p, d) in _FINDING_TO_ACTION.items():
        if dim != dimension:
            continue
        if keyword and keyword.lower() in title.lower():
            return f, p, d

    # Dimension-level fallback
    fallback = _FINDING_TO_ACTION.get((dimension, ""))
    if fallback:
        return fallback

    return None, None, None


def _extract_runtime_target_file(analysis: str) -> str | None:
    """Extract the most relevant file path from runtime_health analysis.

    Looks for mandarin/ paths in stacktrace or affected files sections.
    Returns the first (most relevant) file under mandarin/.
    """
    if not analysis:
        return None

    # Look for "Affected files:" section first
    affected_match = re.search(r"Affected files?:\s*(.+?)(?:\n|$)", analysis)
    if affected_match:
        files_str = affected_match.group(1)
        for f in files_str.split(","):
            f = f.strip()
            if f.startswith("mandarin/") and not f.endswith("/"):
                return f

    # Fall back to stacktrace file references
    # Match patterns like File "mandarin/web/routes.py", line 42
    file_refs = re.findall(r'[Ff]ile\s+"?(mandarin/\S+\.py)"?', analysis)
    if file_refs:
        # Return the last one (innermost frame, most relevant)
        return file_refs[-1]

    # Try bare mandarin/ paths
    bare_paths = re.findall(r'(mandarin/\S+\.py)', analysis)
    if bare_paths:
        return bare_paths[-1]

    return None


def _detect_runtime_error_pattern(title: str, analysis: str) -> str:
    """Detect the specific error pattern for targeted fix generation.

    Returns a pattern identifier used by the LLM prompt to generate
    more targeted fixes.
    """
    combined = (title + " " + analysis).lower()

    if "nameerror" in combined:
        return "add_missing_import"
    if "importerror" in combined or "modulenotfounderror" in combined:
        return "fix_import_path"
    if "'nonetype'" in combined and "attributeerror" in combined:
        return "add_none_check"
    if "keyerror" in combined:
        return "add_dict_get_default"
    if "zerodivisionerror" in combined:
        return "add_zero_check"
    if "typeerror" in combined:
        return "fix_type_mismatch"

    return "general_error_fix"


# ── Input sanitization ─────────────────────────────────────────────────────

def _sanitize_finding_text(text: str) -> str:
    """Sanitize finding text before inserting into LLM prompts.

    Defends against prompt injection by:
    1. Stripping markdown code fences
    2. Removing lines that look like LLM instructions
    3. Truncating to 500 chars
    4. Stripping non-printable characters
    """
    if not text:
        return ""

    # 1. Strip markdown code fences
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 2. Remove lines that look like injected LLM instructions
    _INJECTION_PATTERNS = re.compile(
        r"^.*("
        r"ignore previous|system:|you are|instead,"
        r").*$",
        re.IGNORECASE | re.MULTILINE,
    )
    text = _INJECTION_PATTERNS.sub("", text)

    # 3. Strip non-printable characters (keep newlines, tabs, normal printable)
    text = re.sub(r"[^\x20-\x7E\n\t]", "", text)

    # 4. Collapse excessive whitespace left by removals
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # 5. Truncate to 500 chars
    if len(text) > 500:
        text = text[:500] + "..."

    return text


# ── LLM fix generation ────────────────────────────────────────────────────

def _generate_fix(
    conn,
    finding: dict,
    target_file: str,
    target_parameter: str,
    direction: str,
    file_content: str,
) -> dict:
    """Generate a fix using Ollama.

    Returns dict with 'success', 'new_content', 'model_used', 'generation_time_ms', 'error'.
    """
    from ..ai.ollama_client import generate, is_ollama_available

    if not is_ollama_available():
        return {"success": False, "error": "Ollama not available", "new_content": ""}

    system_prompt = (
        "You are a code maintenance assistant. You fix low-severity issues in Python "
        "and web projects. You receive the current file content and a description of "
        "the issue. You return ONLY the complete fixed file content — no explanations, "
        "no markdown code fences, no commentary. Just the raw file content.\n\n"
        "CONSTRAINTS: Do not add new import statements for os, subprocess, socket, "
        "http, urllib, requests, or shutil. Do not add calls to os.system, "
        "subprocess.run, eval, exec, or open() with write mode."
    )

    # Truncate file content if too large for context
    max_content_len = 8000
    truncated = len(file_content) > max_content_len
    display_content = file_content[:max_content_len] if truncated else file_content
    truncation_note = (
        "\n\n[FILE TRUNCATED — only showing first 8000 chars. "
        "Return the complete file with your fix applied to the visible portion.]"
        if truncated else ""
    )

    # Runtime health findings get pattern-specific guidance for higher confidence
    runtime_guidance = ""
    if finding.get("dimension") == "runtime_health" and target_parameter:
        runtime_guidance = _get_runtime_fix_guidance(target_parameter)

    # Sanitize finding text to defend against prompt injection
    safe_title = _sanitize_finding_text(finding["title"])
    safe_analysis = _sanitize_finding_text(finding.get("analysis", "N/A"))

    prompt = (
        f"Fix the following issue in `{target_file}`:\n\n"
        f"**Issue:** {safe_title}\n"
        f"**Analysis:** {safe_analysis}\n"
        f"**Parameter:** {target_parameter}\n"
        f"**Direction:** {direction}\n"
        f"**Severity:** {finding['severity']}\n"
        f"{runtime_guidance}\n\n"
        f"Current file content:\n```\n{display_content}\n```{truncation_note}\n\n"
        f"Return ONLY the complete fixed file content. No markdown fences. "
        f"No explanations. Make minimal, targeted changes."
    )

    response = generate(
        prompt=prompt,
        system=system_prompt,
        temperature=0.3,  # Low temperature for deterministic fixes
        max_tokens=max_content_len + 2000,
        use_cache=False,  # Don't cache fix generations
        conn=conn,
        task_type="auto_fix",
    )

    if not response.success:
        return {
            "success": False,
            "error": response.error or "LLM generation failed",
            "new_content": "",
            "model_used": response.model_used,
            "generation_time_ms": response.generation_time_ms,
        }

    # Clean up LLM response — strip markdown fences if present
    new_content = _clean_llm_output(response.text, file_content)

    return {
        "success": True,
        "new_content": new_content,
        "model_used": response.model_used,
        "generation_time_ms": response.generation_time_ms,
        "prompt": prompt[:2000],
        "error": None,
    }


def _get_runtime_fix_guidance(error_pattern: str) -> str:
    """Return pattern-specific fix guidance for runtime_health errors.

    These patterns are highly auto-fixable and produce higher-confidence fixes
    when the LLM has explicit instructions for the fix pattern.
    """
    guidance_map = {
        "add_missing_import": (
            "\n**Fix pattern:** NameError — a name is not defined. "
            "Find the undefined name in the traceback and add the correct import "
            "statement at the top of the file. Check other files in the project for "
            "where this name is defined. Do NOT remove any existing code."
        ),
        "fix_import_path": (
            "\n**Fix pattern:** ImportError/ModuleNotFoundError — a module cannot be found. "
            "Check the import path for typos, verify the module exists, and fix the "
            "import statement. If the module was renamed or moved, update the path. "
            "If it is a third-party dependency, note it but fix any local path issues."
        ),
        "add_none_check": (
            "\n**Fix pattern:** AttributeError: 'NoneType' — a variable is None when "
            "an object was expected. Add a None check (guard clause) before the "
            "attribute access. Use 'if variable is None: return/continue/default' "
            "or 'if variable is not None:' pattern. Preserve the existing logic flow."
        ),
        "add_dict_get_default": (
            "\n**Fix pattern:** KeyError — a dictionary key is missing. "
            "Replace dict[key] with dict.get(key, default_value) where the default "
            "is appropriate for the context (None, empty string, 0, empty list, etc.). "
            "Do NOT change the surrounding logic."
        ),
        "add_zero_check": (
            "\n**Fix pattern:** ZeroDivisionError — division by zero. "
            "Add a check for zero before the division. Use 'if denominator != 0:' "
            "or 'if denominator:' and provide a sensible default when zero."
        ),
        "fix_type_mismatch": (
            "\n**Fix pattern:** TypeError — wrong argument type. "
            "Check the function signature and the types being passed. Add type "
            "conversion or validation as appropriate. Common fixes: str() wrapping, "
            "int() conversion, or handling None values."
        ),
    }
    return guidance_map.get(error_pattern, "")


def _clean_llm_output(raw_output: str, original_content: str) -> str:
    """Clean LLM output by stripping markdown code fences and other artifacts."""
    text = raw_output.strip()

    # Strip leading/trailing markdown code fences
    if text.startswith("```"):
        # Remove first line (```python or ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]

    if text.endswith("```"):
        text = text[:-3].rstrip()

    # If the LLM returned something that doesn't look like the original file
    # (e.g., just an explanation), fall back to original
    if not text.strip():
        return original_content

    return text


# ── Validation ─────────────────────────────────────────────────────────────

def _validate_syntax(file_path: Path) -> tuple[bool, str]:
    """Run Python syntax check on the file.

    Returns (passed, error_message).
    """
    if not file_path.suffix == ".py":
        # For non-Python files, skip syntax check (CSS, JS, HTML, etc.)
        return True, ""

    try:
        result = subprocess.run(
            ["python", "-c", f"import py_compile; py_compile.compile('{file_path}', doraise=True)"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            return False, error[:500]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Syntax check timed out"
    except Exception as exc:
        return False, str(exc)[:500]


def _smoke_test(target_file: str = "") -> tuple[bool, str]:
    """Run import smoke test and, if possible, the target module's tests.

    Returns (passed, error_message).
    """
    # 1. Basic import test
    try:
        result = subprocess.run(
            ["python", "-c", "import mandarin"],
            capture_output=True,
            text=True,
            timeout=_SMOKE_TEST_TIMEOUT,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            return False, error[:500]
    except subprocess.TimeoutExpired:
        return False, "Smoke test timed out"
    except Exception as exc:
        return False, str(exc)[:500]

    # 2. If target_file provided, try to run its tests
    if target_file and target_file.endswith(".py"):
        module_name = target_file.replace("/", ".").replace(".py", "")
        # Extract the leaf module name (e.g. "routes" from "mandarin.web.routes")
        leaf_name = module_name.split(".")[-1] if "." in module_name else module_name
        test_file = _PROJECT_ROOT / "tests" / f"test_{leaf_name}.py"
        if test_file.exists():
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", str(test_file), "-x", "--tb=short", "-q"],
                    capture_output=True, text=True,
                    timeout=60, cwd=str(_PROJECT_ROOT),
                )
                if result.returncode != 0:
                    error = result.stdout.strip()[-500:] or result.stderr.strip()[-500:]
                    return False, f"Module tests failed: {error}"
            except subprocess.TimeoutExpired:
                return False, "Module tests timed out"
            except Exception as exc:
                # Test runner unavailable — don't block on this
                logger.warning("Could not run module tests: %s", exc)

    return True, ""


# ── File backup / restore ─────────────────────────────────────────────────

def _backup_file(file_path: Path) -> Path:
    """Create a temporary backup of a file. Returns the backup path."""
    backup_dir = _PROJECT_ROOT / ".auto_fix_backups"
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"{file_path.name}.{int(time.time())}.bak"
    shutil.copy2(file_path, backup_path)
    return backup_path


def _restore_file(backup_path: Path, original_path: Path) -> None:
    """Restore a file from backup."""
    if backup_path.exists():
        shutil.copy2(backup_path, original_path)
        logger.info("Auto-fix executor: reverted %s from backup", original_path)
        _cleanup_backup(backup_path)


def _cleanup_backup(backup_path: Path) -> None:
    """Remove a backup file."""
    try:
        if backup_path.exists():
            backup_path.unlink()
    except Exception:
        pass


# ── Finding lifecycle helpers ──────────────────────────────────────────────

def _advance_finding(conn, finding_id: int) -> None:
    """Advance finding through lifecycle states toward 'implemented'.

    Uses the transition_finding function which enforces valid transitions.
    The path is: investigating -> diagnosed -> recommended -> implemented.
    """
    from .finding_lifecycle import transition_finding
    from .feedback_loops import emit_prediction

    # Get current status
    finding = _safe_query(conn, "SELECT status, dimension FROM pi_finding WHERE id = ?",
                          (finding_id,))
    if not finding:
        return

    current_status = finding["status"]

    # Define the advancement path
    advance_path = {
        "investigating": ["diagnosed", "recommended", "implemented"],
        "diagnosed": ["recommended", "implemented"],
        "recommended": ["implemented"],
    }

    steps = advance_path.get(current_status, [])

    # Before marking implemented, ensure a prediction record exists
    if "implemented" in steps:
        try:
            existing_pred = _safe_query(conn, """
                SELECT id FROM pi_prediction_ledger WHERE finding_id = ?
            """, (finding_id,))
            if not existing_pred:
                emit_prediction(
                    conn,
                    finding_id=finding_id,
                    model_id=finding["dimension"],
                    dimension=finding["dimension"],
                    metric_name=finding["dimension"],
                    predicted_delta=1.0,
                    confidence=0.5,
                )
        except Exception as exc:
            logger.debug("Auto-fix: prediction emission failed for finding #%d: %s",
                         finding_id, exc)

    for step in steps:
        ok = transition_finding(conn, finding_id, step)
        if not ok:
            logger.warning(
                "Auto-fix: failed to advance finding #%d to %s",
                finding_id, step,
            )
            break


def _escalate_finding(conn, finding_id: int, reason: str) -> None:
    """Mark a finding as needing human intervention after auto-fix failure.

    Records the escalation in both the execution log and the decision log.
    """
    try:
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, presented_to,
                 decision, decision_reason)
            VALUES (?, 'informed_fix', 'alert', 'solo',
                    'Auto-fix failed — escalated to human', ?)
        """, (finding_id, reason))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Auto-fix: escalation log failed for finding #%d: %s",
                      finding_id, exc)


# ── Execution logging ─────────────────────────────────────────────────────

def _log_execution(
    conn,
    result: dict,
    llm_response: dict | None = None,
    validation_passed: bool | None = None,
    validation_error: str | None = None,
    smoke_test_passed: bool | None = None,
    smoke_test_error: str | None = None,
) -> None:
    """Record an execution attempt in the auto_fix_execution table."""
    try:
        conn.execute("""
            INSERT INTO auto_fix_execution
                (finding_id, target_files, status, llm_model, llm_prompt,
                 llm_response, generation_time_ms, validation_passed,
                 validation_error, smoke_test_passed, smoke_test_error,
                 reverted, escalated, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result["finding_id"],
            json.dumps(result.get("target_files", [])),
            result["status"],
            llm_response.get("model_used") if llm_response else None,
            llm_response.get("prompt", "")[:2000] if llm_response else None,
            llm_response.get("new_content", "")[:4000] if llm_response else None,
            llm_response.get("generation_time_ms") if llm_response else None,
            1 if validation_passed else (0 if validation_passed is False else None),
            validation_error,
            1 if smoke_test_passed else (0 if smoke_test_passed is False else None),
            smoke_test_error,
            1 if result["status"] == "reverted" else 0,
            1 if result["status"] == "escalated" else 0,
            result.get("error"),
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Auto-fix: execution logging failed: %s", exc)


def _update_execution_status(conn, result: dict, status: str) -> None:
    """Update the in-progress status (for observability)."""
    result["status"] = status
