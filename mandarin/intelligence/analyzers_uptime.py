"""UptimeRobot monitoring analyzer — pulls uptime stats and generates findings.

Calls the UptimeRobot API v2 to retrieve monitor status and uptime ratios.
Generates findings when:
  - Any monitor is currently down (critical)
  - 30-day uptime drops below 99.5% (warning)
  - 7-day uptime drops below 99.5% (warning)

Gracefully skips when UPTIMEROBOT_API_KEY is not configured.

Exports:
    ANALYZERS: list of analyzer functions
    fetch_uptime_stats: standalone function for admin dashboard use
"""

import logging

import requests

from ._base import _finding

logger = logging.getLogger(__name__)

# UptimeRobot API v2 endpoint
_API_URL = "https://api.uptimerobot.com/v2/getMonitors"

# Monitor status codes
# https://uptimerobot.com/api/
_STATUS_LABELS = {
    0: "paused",
    1: "not_checked_yet",
    2: "up",
    8: "seems_down",
    9: "down",
}


def _get_api_key() -> str:
    """Retrieve the UptimeRobot API key from settings, returning '' if absent."""
    try:
        from ..settings import UPTIMEROBOT_API_KEY
        return UPTIMEROBOT_API_KEY or ""
    except (ImportError, AttributeError):
        return ""


def fetch_uptime_stats() -> dict | None:
    """Fetch monitor data from UptimeRobot API.

    Returns a dict with:
        monitors: list of monitor dicts (name, status, uptime_7d, uptime_30d, url)
        summary: dict with overall_uptime_7d, overall_uptime_30d, all_up, down_count

    Returns None if API key is not set or the API call fails.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        resp = requests.post(
            _API_URL,
            data={
                "api_key": api_key,
                "format": "json",
                "custom_uptime_ratios": "7-30",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("UptimeRobot API returned status %s", resp.status_code)
            return None

        data = resp.json()
        if data.get("stat") != "ok":
            logger.warning("UptimeRobot API error: %s", data.get("error", {}).get("message", "unknown"))
            return None

        monitors = []
        down_count = 0
        uptime_7d_values = []
        uptime_30d_values = []

        for m in data.get("monitors", []):
            status_code = m.get("status", 0)
            status_label = _STATUS_LABELS.get(status_code, f"unknown({status_code})")

            # custom_uptime_ratio contains "7d-30d" as a hyphen-separated string
            ratios = (m.get("custom_uptime_ratio") or "0-0").split("-")
            uptime_7d = float(ratios[0]) if len(ratios) > 0 else 0.0
            uptime_30d = float(ratios[1]) if len(ratios) > 1 else 0.0

            monitors.append({
                "name": m.get("friendly_name", "Unknown"),
                "url": m.get("url", ""),
                "status": status_label,
                "status_code": status_code,
                "uptime_7d": round(uptime_7d, 3),
                "uptime_30d": round(uptime_30d, 3),
            })

            if status_code in (8, 9):
                down_count += 1

            uptime_7d_values.append(uptime_7d)
            uptime_30d_values.append(uptime_30d)

        overall_7d = round(sum(uptime_7d_values) / len(uptime_7d_values), 3) if uptime_7d_values else 0.0
        overall_30d = round(sum(uptime_30d_values) / len(uptime_30d_values), 3) if uptime_30d_values else 0.0

        return {
            "monitors": monitors,
            "summary": {
                "overall_uptime_7d": overall_7d,
                "overall_uptime_30d": overall_30d,
                "all_up": down_count == 0,
                "down_count": down_count,
                "monitor_count": len(monitors),
            },
        }

    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("UptimeRobot API call failed: %s", exc)
        return None


def _analyze_uptime(conn) -> list[dict]:
    """Analyzer function that checks UptimeRobot monitors for issues.

    Follows the standard analyzer pattern: takes a db connection, returns
    a list of finding dicts.
    """
    findings: list[dict] = []

    stats = fetch_uptime_stats()
    if stats is None:
        # API key not set or API unreachable — skip silently
        return findings

    monitors = stats.get("monitors", [])
    summary = stats.get("summary", {})

    # ── 1. Any monitor currently down → critical ────────────────────────
    down_monitors = [m for m in monitors if m["status_code"] in (8, 9)]
    if down_monitors:
        names = ", ".join(m["name"] for m in down_monitors)
        findings.append(_finding(
            "runtime_health", "critical",
            f"Monitor(s) down: {names}",
            f"{len(down_monitors)} UptimeRobot monitor(s) are currently reporting "
            f"down status: {names}. Immediate investigation required.",
            "Check server health, Fly.io dashboard, and application logs. "
            "Verify the application is running and responding to health checks.",
            f"URGENT: {len(down_monitors)} monitor(s) down: {names}. "
            f"Check Fly.io dashboard, application logs, and health check endpoints.",
            "Service availability",
            ["Dockerfile", "fly.toml"],
        ))

        # Send alert email for down monitors
        _send_uptime_alert(down_monitors)

    # ── 2. 30-day uptime below 99.5% → warning ─────────────────────────
    for m in monitors:
        if m["uptime_30d"] < 99.5 and m["status_code"] not in (8, 9):
            severity = "high" if m["uptime_30d"] < 99.0 else "medium"
            findings.append(_finding(
                "runtime_health", severity,
                f"Low 30-day uptime: {m['name']} at {m['uptime_30d']}%",
                f"Monitor '{m['name']}' has {m['uptime_30d']}% uptime over the last "
                f"30 days (target: 99.5%+). 7-day uptime: {m['uptime_7d']}%.",
                "Review recent downtime incidents. Check deployment stability, "
                "health check configuration, and server resource utilization.",
                f"Investigate low uptime for '{m['name']}' ({m['uptime_30d']}% over 30d). "
                f"Check Fly.io metrics, deployment history, and error logs.",
                "Service reliability",
                ["fly.toml"],
            ))

    # ── 3. 7-day uptime below 99.5% → warning (recent regression) ──────
    for m in monitors:
        if m["uptime_7d"] < 99.5 and m["uptime_30d"] >= 99.5 and m["status_code"] not in (8, 9):
            findings.append(_finding(
                "runtime_health", "medium",
                f"Recent uptime drop: {m['name']} at {m['uptime_7d']}% (7d)",
                f"Monitor '{m['name']}' has {m['uptime_7d']}% uptime over the last "
                f"7 days, down from {m['uptime_30d']}% over 30 days. This suggests "
                f"a recent regression in service availability.",
                "Check recent deployments and changes that may have introduced instability.",
                f"Investigate recent uptime regression for '{m['name']}'. "
                f"7-day: {m['uptime_7d']}%, 30-day: {m['uptime_30d']}%. "
                f"Review recent deployment history.",
                "Service reliability",
                ["fly.toml"],
            ))

    # ── 4. Overall uptime below 99% → send alert email ─────────────────
    overall_30d = summary.get("overall_uptime_30d", 100)
    if overall_30d < 99.0:
        _send_uptime_degraded_alert(overall_30d, monitors)

    return findings


def _send_uptime_alert(down_monitors: list[dict]) -> None:
    """Send email and Matrix alert when monitors are down."""
    # Email notification
    try:
        from ..email import send_uptime_alert
        from ..settings import ADMIN_EMAIL
        admin_email = ADMIN_EMAIL or ""
        if admin_email:
            send_uptime_alert(
                to_email=admin_email,
                down_monitors=down_monitors,
            )
    except (ImportError, Exception) as exc:
        logger.warning("Failed to send uptime down alert email: %s", exc)

    # Matrix / Beeper notification
    try:
        from ..notifications.matrix_client import send_alert as matrix_alert
        names = ", ".join(m.get("name", "?") for m in down_monitors)
        matrix_alert(
            subject=f"{len(down_monitors)} monitor(s) DOWN",
            details=f"Down monitors: {names}",
        )
    except (ImportError, Exception) as exc:
        logger.warning("Failed to send uptime down Matrix alert: %s", exc)


def _send_uptime_degraded_alert(overall_uptime: float, monitors: list[dict]) -> None:
    """Send email and Matrix alert when overall uptime drops below 99%."""
    # Email notification
    try:
        from ..email import send_uptime_degraded_alert
        from ..settings import ADMIN_EMAIL
        admin_email = ADMIN_EMAIL or ""
        if admin_email:
            send_uptime_degraded_alert(
                to_email=admin_email,
                overall_uptime=overall_uptime,
                monitors=monitors,
            )
    except (ImportError, Exception) as exc:
        logger.warning("Failed to send uptime degraded alert email: %s", exc)

    # Matrix / Beeper notification
    try:
        from ..notifications.matrix_client import send_alert as matrix_alert
        matrix_alert(
            subject=f"Uptime degraded: {overall_uptime:.2f}%",
            details=f"Overall 30-day uptime is {overall_uptime:.2f}%, below the 99% threshold.",
        )
    except (ImportError, Exception) as exc:
        logger.warning("Failed to send uptime degraded Matrix alert: %s", exc)


# ── Exported analyzer list ────────────────────────────────────────────────

ANALYZERS = [_analyze_uptime]
