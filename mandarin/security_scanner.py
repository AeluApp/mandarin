"""Automated security scanning — SAST (bandit) + dependency audit (pip-audit)."""

import json
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent


def run_sast_scan(conn):
    """Run bandit SAST scan, store findings, return summary dict."""
    import shutil
    if not shutil.which("bandit"):
        logger.info("bandit not installed — skipping SAST scan (CI-only tool)")
        return {"high": 0, "medium": 0, "low": 0, "total": 0, "skipped": True}
    scan_id = _create_scan(conn, "sast")
    start = time.monotonic()
    try:
        result = subprocess.run(
            [
                "bandit", "-r", "mandarin/", "-c", ".bandit",
                "-f", "json", "--severity-level", "medium",
            ],
            capture_output=True, text=True, timeout=300,
            cwd=str(_PROJECT_ROOT),
        )
        # bandit exits 1 when findings exist — not an error
        output = result.stdout
        if not output:
            return _complete_scan(conn, scan_id, start, {"high": 0, "medium": 0, "low": 0, "total": 0})

        data = json.loads(output)
        findings = data.get("results", [])

        for f in findings:
            conn.execute(
                """INSERT INTO security_scan_finding
                   (scan_id, severity, category, title, description, file_path, line_number)
                   VALUES (?, ?, 'sast', ?, ?, ?, ?)""",
                (scan_id, f.get("issue_severity", "MEDIUM").upper(), f.get("test_name", ""),
                 f.get("issue_text", ""), f.get("filename", ""), f.get("line_number")),
            )

        summary = _build_summary(findings, key="issue_severity")
        return _complete_scan(conn, scan_id, start, summary)

    except Exception as e:
        return _fail_scan(conn, scan_id, start, str(e))


def run_dependency_scan(conn):
    """Run pip-audit dependency scan, store findings, return summary dict."""
    import shutil
    if not shutil.which("pip-audit"):
        logger.info("pip-audit not installed — skipping dependency scan (CI-only tool)")
        return {"high": 0, "medium": 0, "low": 0, "total": 0, "skipped": True}
    scan_id = _create_scan(conn, "dependency")
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json"],
            capture_output=True, text=True, timeout=300,
            cwd=str(_PROJECT_ROOT),
        )
        output = result.stdout
        if not output:
            return _complete_scan(conn, scan_id, start, {"high": 0, "medium": 0, "low": 0, "total": 0})

        data = json.loads(output)
        # pip-audit JSON is a list of vulnerability dicts
        vulns = data if isinstance(data, list) else data.get("dependencies", [])

        for dep in vulns:
            dep_vulns = dep.get("vulns", [])
            if not dep_vulns:
                continue
            for v in dep_vulns:
                # Map CVSS-style severity or default to MEDIUM
                severity = _map_pip_audit_severity(v)
                conn.execute(
                    """INSERT INTO security_scan_finding
                       (scan_id, severity, category, title, description,
                        package_name, installed_version, fixed_version)
                       VALUES (?, ?, 'dependency', ?, ?, ?, ?, ?)""",
                    (scan_id, severity, v.get("id", ""),
                     v.get("description", "")[:500],
                     dep.get("name", ""), dep.get("version", ""),
                     v.get("fix_versions", [""])[0] if v.get("fix_versions") else ""),
                )

        total_findings = sum(len(d.get("vulns", [])) for d in vulns)
        summary = {"high": 0, "medium": 0, "low": 0, "total": total_findings}
        # Count by mapped severity
        for dep in vulns:
            for v in dep.get("vulns", []):
                sev = _map_pip_audit_severity(v).lower()
                summary[sev] = summary.get(sev, 0) + 1

        return _complete_scan(conn, scan_id, start, summary)

    except Exception as e:
        return _fail_scan(conn, scan_id, start, str(e))


def run_full_scan(conn):
    """Run both SAST and dependency scans, return combined summary."""
    sast = run_sast_scan(conn)
    dep = run_dependency_scan(conn)
    return {
        "sast": sast,
        "dependency": dep,
        "combined": {
            "high": sast["high"] + dep["high"],
            "medium": sast["medium"] + dep["medium"],
            "low": sast["low"] + dep["low"],
            "total": sast["total"] + dep["total"],
        },
    }


def get_latest_scan(conn):
    """Get the most recent completed scan with its findings."""
    row = conn.execute(
        "SELECT * FROM security_scan ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    scan = dict(row)
    findings = conn.execute(
        "SELECT * FROM security_scan_finding WHERE scan_id = ? ORDER BY severity",
        (scan["id"],),
    ).fetchall()
    scan["findings"] = [dict(f) for f in findings]
    return scan


def get_scan_history(conn, limit=20):
    """Get recent scan history with summaries."""
    rows = conn.execute(
        "SELECT * FROM security_scan ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Internal helpers ───────────────────────────────────────────────


def _create_scan(conn, scan_type):
    """Insert a new scan row and return its id."""
    cur = conn.execute(
        "INSERT INTO security_scan (scan_type, status) VALUES (?, 'running')",
        (scan_type,),
    )
    conn.commit()
    return cur.lastrowid


def _complete_scan(conn, scan_id, start, summary):
    """Mark scan completed with summary."""
    duration = int(time.monotonic() - start)
    conn.execute(
        """UPDATE security_scan
           SET status = 'completed', completed_at = datetime('now'),
               summary = ?, duration_seconds = ?
           WHERE id = ?""",
        (json.dumps(summary), duration, scan_id),
    )
    conn.commit()
    logger.info("Security scan %d completed: %s", scan_id, summary)
    return summary


def _fail_scan(conn, scan_id, start, error_msg):
    """Mark scan as failed."""
    duration = int(time.monotonic() - start)
    conn.execute(
        """UPDATE security_scan
           SET status = 'failed', completed_at = datetime('now'),
               error_message = ?, duration_seconds = ?
           WHERE id = ?""",
        (error_msg[:2048], duration, scan_id),
    )
    conn.commit()
    logger.error("Security scan %d failed: %s", scan_id, error_msg)
    return {"high": 0, "medium": 0, "low": 0, "total": 0}


def _build_summary(findings, key="issue_severity"):
    """Count findings by severity."""
    summary = {"high": 0, "medium": 0, "low": 0, "total": len(findings)}
    for f in findings:
        sev = f.get(key, "MEDIUM").lower()
        if sev in summary:
            summary[sev] += 1
    return summary


def _map_pip_audit_severity(vuln):
    """Map pip-audit vulnerability to HIGH/MEDIUM/LOW."""
    # pip-audit doesn't always include severity; use aliases/id heuristics
    vuln.get("id", "")
    desc = vuln.get("description", "").lower()
    if "critical" in desc or "remote code execution" in desc:
        return "HIGH"
    if "high" in desc:
        return "HIGH"
    if "low" in desc or "informational" in desc:
        return "LOW"
    return "MEDIUM"
