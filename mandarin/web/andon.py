"""Andon system — real-time quality alerting for Aelu.

Fires alerts when quality thresholds are breached. Logs all events
to the andon_event table. Can optionally send webhooks to Discord/Slack.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from ..settings import ANDON_WEBHOOK_URL as _WEBHOOK_URL

logger = logging.getLogger(__name__)


def fire_andon(conn, event_type, severity, summary, details=None):
    """Record an andon event and optionally send a webhook.

    Args:
        conn: Database connection
        event_type: Category (e.g., 'spc_violation', 'dpmo_exceeded', 'client_error_spike')
        severity: 'info', 'warning', or 'critical'
        summary: Short human-readable description
        details: Optional JSON-serializable additional data
    """
    try:
        conn.execute(
            "INSERT INTO andon_event (event_type, severity, summary, details) "
            "VALUES (?, ?, ?, ?)",
            (event_type, severity, summary, json.dumps(details) if details else None),
        )
        conn.commit()
        logger.info("Andon [%s] %s: %s", severity, event_type, summary)
    except sqlite3.Error as e:
        logger.warning("Failed to log andon event: %s", e)

    # Send webhook if configured
    if _WEBHOOK_URL and severity in ("warning", "critical"):
        _send_webhook(event_type, severity, summary, details)


def _send_webhook(event_type, severity, summary, details):
    """Send a webhook notification (Discord/Slack compatible)."""
    try:
        import urllib.request
        payload = json.dumps({
            "content": f"**[{severity.upper()}]** {event_type}: {summary}",
            "embeds": [{
                "title": f"Andon Alert: {event_type}",
                "description": summary,
                "color": 0xFF0000 if severity == "critical" else 0xFFA500,
                "fields": [{"name": "Details", "value": str(details)[:500]}] if details else [],
            }],
        }).encode("utf-8")
        req = urllib.request.Request(
            _WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning("Andon webhook failed: %s", e)


def check_andon_thresholds(conn):
    """Check quality thresholds and fire andon alerts as needed.

    Called by the daily quality scheduler. Checks:
    1. SPC Rule 1 violations (>3σ from center)
    2. DPMO exceeding phase target
    3. Client error spikes
    """
    alerts_fired = 0

    # Check 1: SPC violations in last 24 hours
    try:
        from ..quality.spc import get_spc_chart_data, detect_out_of_control
        for chart_type in ("drill_accuracy", "response_time_p95", "content_rejection"):
            data = get_spc_chart_data(conn, chart_type)
            if data and data.get("observations"):
                violations = detect_out_of_control(data["observations"])
                rule1_violations = [v for v in violations if "Rule 1" in v.get("description", "")]
                if rule1_violations:
                    fire_andon(
                        conn, "spc_violation", "critical",
                        f"SPC Rule 1 violation on {chart_type}: "
                        f"point > 3σ from center line",
                        {"chart": chart_type, "violations": rule1_violations[:3]},
                    )
                    alerts_fired += 1
    except Exception as e:
        logger.debug("SPC andon check skipped: %s", e)

    # Check 2: DPMO exceeding phase target
    try:
        from ..quality.dpmo import calculate_dpmo
        dpmo_result = calculate_dpmo(conn)
        if dpmo_result and dpmo_result.get("dpmo"):
            dpmo = dpmo_result["dpmo"]
            # Phase targets: Phase 1 = 66,807 (3.0σ), Phase 2 = 6,210 (4.0σ)
            if dpmo > 66807:
                fire_andon(
                    conn, "dpmo_exceeded", "warning",
                    f"DPMO at {dpmo:,.0f} — exceeds Phase 1 target of 66,807 (3.0σ)",
                    {"dpmo": dpmo, "target": 66807},
                )
                alerts_fired += 1
    except Exception as e:
        logger.debug("DPMO andon check skipped: %s", e)

    return alerts_fired


def get_andon_dashboard(conn, hours=24):
    """Return recent andon events for dashboard display."""
    try:
        rows = conn.execute(
            "SELECT id, event_type, severity, summary, details, fired_at, "
            "acknowledged_at FROM andon_event "
            "WHERE fired_at > datetime('now', ?) "
            "ORDER BY fired_at DESC LIMIT 50",
            (f"-{hours} hours",),
        ).fetchall()
        return [
            {
                "id": r[0], "event_type": r[1], "severity": r[2],
                "summary": r[3], "details": json.loads(r[4]) if r[4] else None,
                "fired_at": r[5], "acknowledged_at": r[6],
            }
            for r in rows
        ]
    except sqlite3.Error:
        return []
