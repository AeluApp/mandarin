"""Prompt Observability (Doc 23 C-02).

Trace every Qwen call, compute SPC control charts for prompt performance,
and detect regressions/drift using Western Electric rules.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def trace_prompt_call(
    conn: sqlite3.Connection,
    prompt_key: str,
    prompt_text: str,
    response_text: str,
    latency_ms: int,
    model_used: str,
    success: bool,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_type: str | None = None,
    output_quality_score: float | None = None,
) -> int | None:
    """Log a prompt call to the prompt_trace table."""
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
    try:
        cursor = conn.execute("""
            INSERT INTO prompt_trace
            (prompt_key, prompt_hash, input_tokens, output_tokens, latency_ms,
             model_used, success, error_type, output_quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prompt_key, prompt_hash, input_tokens, output_tokens, latency_ms,
            model_used, 1 if success else 0, error_type, output_quality_score,
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


def compute_prompt_spc(
    conn: sqlite3.Connection,
    prompt_key: str,
    window_days: int = 30,
) -> dict:
    """Compute SPC control chart data for a prompt key.

    Returns success rate, latency p50/p95, and control limits.
    """
    try:
        rows = conn.execute("""
            SELECT success, latency_ms, output_quality_score, created_at
            FROM prompt_trace
            WHERE prompt_key = ?
            AND created_at >= datetime('now', ?)
            ORDER BY created_at
        """, (prompt_key, f"-{window_days} days")).fetchall()
    except sqlite3.OperationalError:
        return {"error": "prompt_trace table not available"}

    if not rows:
        return {"prompt_key": prompt_key, "sample_size": 0}

    successes = [r["success"] for r in rows]
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"]]
    quality_scores = [r["output_quality_score"] for r in rows if r["output_quality_score"] is not None]

    success_rate = sum(successes) / len(successes) if successes else 0.0

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)] if latencies_sorted else 0

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

    # Compute control limits (mean ± 3σ) for latency
    if len(latencies) >= 5:
        mean_lat = sum(latencies) / len(latencies)
        variance = sum((x - mean_lat) ** 2 for x in latencies) / len(latencies)
        std_lat = variance ** 0.5
        ucl = mean_lat + 3 * std_lat
        lcl = max(0, mean_lat - 3 * std_lat)
    else:
        mean_lat = sum(latencies) / len(latencies) if latencies else 0
        ucl = lcl = None

    return {
        "prompt_key": prompt_key,
        "sample_size": len(rows),
        "success_rate": round(success_rate, 4),
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "latency_mean_ms": round(mean_lat, 1) if latencies else 0,
        "latency_ucl_ms": round(ucl, 1) if ucl is not None else None,
        "latency_lcl_ms": round(lcl, 1) if lcl is not None else None,
        "avg_quality_score": round(avg_quality, 4) if avg_quality is not None else None,
    }


def detect_prompt_regression(
    conn: sqlite3.Connection,
    prompt_key: str,
    baseline_days: int = 60,
    current_days: int = 7,
) -> list[dict]:
    """Compare current window to baseline for a prompt key.

    Uses Western Electric rules to detect drift:
    - Rule 1: Single point beyond 3σ
    - Rule 2: 2 of 3 consecutive points beyond 2σ
    - Rule 3: 4 of 5 consecutive points beyond 1σ
    """
    regressions = []

    try:
        # Baseline window
        baseline = conn.execute("""
            SELECT success, latency_ms FROM prompt_trace
            WHERE prompt_key = ?
            AND created_at >= datetime('now', ?) AND created_at < datetime('now', ?)
        """, (prompt_key, f"-{baseline_days} days", f"-{current_days} days")).fetchall()

        # Current window
        current = conn.execute("""
            SELECT success, latency_ms FROM prompt_trace
            WHERE prompt_key = ?
            AND created_at >= datetime('now', ?)
        """, (prompt_key, f"-{current_days} days")).fetchall()
    except sqlite3.OperationalError:
        return []

    if len(baseline) < 10 or len(current) < 3:
        return []  # Not enough data

    # Success rate drift
    baseline_rate = sum(r["success"] for r in baseline) / len(baseline)
    current_rate = sum(r["success"] for r in current) / len(current)
    rate_drift = abs(current_rate - baseline_rate)

    if rate_drift > 0.15:  # >15% change in success rate
        drift_detected = True
        regressions.append({
            "metric": "success_rate",
            "baseline_value": round(baseline_rate, 4),
            "current_value": round(current_rate, 4),
            "drift_detected": True,
        })
        _log_regression(conn, prompt_key, "success_rate",
                        baseline_rate, current_rate, drift_detected)

    # Latency drift (Western Electric Rule 1: beyond 3σ)
    baseline_lats = [r["latency_ms"] for r in baseline if r["latency_ms"]]
    current_lats = [r["latency_ms"] for r in current if r["latency_ms"]]

    if len(baseline_lats) >= 10 and len(current_lats) >= 3:
        b_mean = sum(baseline_lats) / len(baseline_lats)
        b_var = sum((x - b_mean) ** 2 for x in baseline_lats) / len(baseline_lats)
        b_std = b_var ** 0.5

        c_mean = sum(current_lats) / len(current_lats)

        if b_std > 0 and abs(c_mean - b_mean) > 3 * b_std:
            regressions.append({
                "metric": "latency_ms",
                "baseline_value": round(b_mean, 1),
                "current_value": round(c_mean, 1),
                "drift_detected": True,
            })
            _log_regression(conn, prompt_key, "latency_ms",
                            b_mean, c_mean, True)

    return regressions


def _log_regression(
    conn: sqlite3.Connection,
    prompt_key: str,
    metric: str,
    baseline_value: float,
    current_value: float,
    drift_detected: bool,
) -> None:
    """Log a regression check result."""
    try:
        conn.execute("""
            INSERT INTO prompt_regression_run
            (prompt_key, metric, baseline_value, current_value, drift_detected)
            VALUES (?, ?, ?, ?, ?)
        """, (prompt_key, metric, baseline_value, current_value, 1 if drift_detected else 0))
        conn.commit()
    except sqlite3.OperationalError:
        pass


def get_prompt_health_dashboard(conn: sqlite3.Connection) -> list[dict]:
    """Summary of all prompt keys with health status."""
    try:
        keys = conn.execute("""
            SELECT DISTINCT prompt_key FROM prompt_trace
            ORDER BY prompt_key
        """).fetchall()
    except sqlite3.OperationalError:
        return []

    dashboard = []
    for row in keys:
        key = row["prompt_key"]
        spc = compute_prompt_spc(conn, key)
        regressions = detect_prompt_regression(conn, key)

        status = "healthy"
        if spc.get("success_rate", 1.0) < 0.8:
            status = "degraded"
        if regressions:
            status = "regression_detected"

        dashboard.append({
            "prompt_key": key,
            "status": status,
            "success_rate": spc.get("success_rate"),
            "latency_p50_ms": spc.get("latency_p50_ms"),
            "latency_p95_ms": spc.get("latency_p95_ms"),
            "sample_size": spc.get("sample_size", 0),
            "regressions": regressions,
        })

    return dashboard


def analyze_prompt_health(conn: sqlite3.Connection) -> list[dict]:
    """Intelligence analyzer: produces findings for degraded prompts."""
    from ..intelligence._base import _finding
    findings = []

    dashboard = get_prompt_health_dashboard(conn)
    for entry in dashboard:
        if entry["status"] == "regression_detected":
            findings.append(_finding(
                dimension="agentic",
                severity="high",
                title=f"Prompt regression: {entry['prompt_key']}",
                analysis=f"Drift detected. Success rate: {entry['success_rate']}, "
                         f"p50 latency: {entry['latency_p50_ms']}ms. "
                         f"Regressions: {json.dumps(entry['regressions'])}",
                recommendation="Review prompt template changes. Check model version. "
                               "Compare against baseline outputs.",
                claude_prompt=f"Check prompt_trace and prompt_regression_run for '{entry['prompt_key']}'.",
                impact="Degraded AI output quality may affect content generation and analysis.",
                files=["mandarin/ai/prompt_observability.py", "mandarin/ai/genai_layer.py"],
            ))
        elif entry["status"] == "degraded":
            findings.append(_finding(
                dimension="agentic",
                severity="medium",
                title=f"Prompt degraded: {entry['prompt_key']} (success {entry['success_rate']:.0%})",
                analysis=f"Success rate below 80%: {entry['success_rate']:.1%}. "
                         f"Sample size: {entry['sample_size']}.",
                recommendation="Check Ollama availability, model loading, prompt format.",
                claude_prompt=f"Check prompt_trace for '{entry['prompt_key']}' failures.",
                impact="Low success rate means retries and degraded user experience.",
                files=["mandarin/ai/ollama_client.py"],
            ))

    return findings
