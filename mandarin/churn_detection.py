"""Churn Detection & Risk Scoring — Marketing analytics for the Aelu app.

Analyzes session data for churn risk signals and produces a formatted report.
Designed for the current single-user local database, but structured to support
multi-user when that migration ships.

Signals detected:
  1. Session frequency drop (30%+ decline over 2 weeks vs. trailing 30-day avg)
  2. No session in 5+ days
  3. No session in 10+ days
  4. No session in 14+ days
  5. Session duration drop (avg drops 50%+ from baseline)
  6. Accuracy plateau (same range for 3+ weeks)
  7. Single drill type usage (80%+ same type for 3+ weeks)
  8. No reading/listening usage in 30+ days

Composite churn risk score: 0-100 (weighted signals).

Usage:
    python -m mandarin.churn_detection
    python -m mandarin.churn_detection --db-path /path/to/mandarin.db
    ./run churn-report
"""

import argparse
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .settings import DB_PATH as _DEFAULT_DB_PATH


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a read-only connection with Row factory."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _col_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    # Validate table name against known schema tables before PRAGMA
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if table not in existing:
        return False
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


# ---------------------------------------------------------------------------
# Signal detection queries — single-user adapted
# ---------------------------------------------------------------------------

def _days_since_last_session(conn: sqlite3.Connection, user_id: int = 1) -> Optional[float]:
    """Return days since most recent session, or None if no sessions."""
    if not _table_exists(conn, "session_log"):
        return None
    row = conn.execute(
        "SELECT MAX(started_at) AS last_at FROM session_log WHERE items_completed > 0 AND user_id = ?",
        (user_id,)
    ).fetchone()
    last_at = row["last_at"] if row else None
    if not last_at:
        return None
    try:
        last_dt = datetime.fromisoformat(last_at)
    except ValueError:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now - last_dt).total_seconds() / 86400


def _session_frequency_drop(conn: sqlite3.Connection, user_id: int = 1) -> float:
    """Return the decline ratio (0.0 = no decline, 1.0 = 100% decline).

    Compares sessions in the last 14 days vs. the 14 days before that,
    normalized to a weekly rate.
    """
    if not _table_exists(conn, "session_log"):
        return 0.0
    recent = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()["cnt"] or 0
    prior = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-28 days')
          AND started_at < datetime('now', '-14 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()["cnt"] or 0

    if prior == 0:
        return 0.0  # no baseline
    decline = 1.0 - (recent / prior)
    return max(0.0, decline)


def _session_duration_drop(conn: sqlite3.Connection, user_id: int = 1) -> float:
    """Return the decline ratio of average session duration.

    Compares last 14 days avg vs. prior 14 days avg.
    Returns 0.0 (no decline) to 1.0 (100% decline).
    """
    if not _table_exists(conn, "session_log"):
        return 0.0
    recent = conn.execute("""
        SELECT AVG(duration_seconds) AS avg_dur FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
          AND items_completed > 0
          AND duration_seconds IS NOT NULL AND duration_seconds > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    prior = conn.execute("""
        SELECT AVG(duration_seconds) AS avg_dur FROM session_log
        WHERE started_at >= datetime('now', '-28 days')
          AND started_at < datetime('now', '-14 days')
          AND items_completed > 0
          AND duration_seconds IS NOT NULL AND duration_seconds > 0
          AND user_id = ?
    """, (user_id,)).fetchone()

    recent_avg = recent["avg_dur"] if recent else None
    prior_avg = prior["avg_dur"] if prior else None

    if not prior_avg or prior_avg == 0:
        return 0.0
    if not recent_avg:
        return 1.0  # no recent sessions at all

    decline = 1.0 - (recent_avg / prior_avg)
    return max(0.0, min(1.0, decline))


def _accuracy_plateau(conn: sqlite3.Connection, user_id: int = 1) -> bool:
    """Return True if accuracy has been flat (within 5pp) for 30+ days."""
    if not _table_exists(conn, "session_log"):
        return False

    rows = conn.execute("""
        SELECT
            CASE WHEN started_at >= datetime('now', '-15 days') THEN 'recent' ELSE 'older' END AS bucket,
            SUM(items_correct) AS correct,
            SUM(items_completed) AS completed
        FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
          AND items_completed > 0
          AND user_id = ?
        GROUP BY bucket
    """, (user_id,)).fetchall()

    buckets = {}
    for r in rows:
        completed = r["completed"] or 0
        correct = r["correct"] or 0
        if completed > 0:
            buckets[r["bucket"]] = correct / completed * 100

    if "recent" not in buckets or "older" not in buckets:
        return False

    return abs(buckets["recent"] - buckets["older"]) < 5.0


def _drill_type_diversity(conn: sqlite3.Connection, user_id: int = 1) -> Tuple[int, Optional[float]]:
    """Return (unique_types_used, dominant_type_pct) over the last 21 days.

    dominant_type_pct is the percentage of errors for the most-used drill type.
    """
    if not _table_exists(conn, "error_log"):
        return (0, None)

    rows = conn.execute("""
        SELECT drill_type, COUNT(*) AS cnt FROM error_log
        WHERE created_at >= datetime('now', '-21 days')
          AND drill_type IS NOT NULL
          AND user_id = ?
        GROUP BY drill_type
        ORDER BY cnt DESC
    """, (user_id,)).fetchall()

    if not rows:
        # Also check session modality_counts for drill diversity
        if _table_exists(conn, "session_log"):
            sess_rows = conn.execute("""
                SELECT modality_counts FROM session_log
                WHERE started_at >= datetime('now', '-21 days')
                  AND items_completed > 0
                  AND modality_counts IS NOT NULL
                  AND user_id = ?
            """, (user_id,)).fetchall()
            import json
            types_seen = set()
            for sr in sess_rows:
                try:
                    mc = json.loads(sr["modality_counts"])
                    for k, v in mc.items():
                        if v and v > 0:
                            types_seen.add(k)
                except (json.JSONDecodeError, TypeError):
                    pass
            return (len(types_seen), None)
        return (0, None)

    total = sum(r["cnt"] for r in rows)
    dominant_pct = (rows[0]["cnt"] / total * 100) if total > 0 else 0
    return (len(rows), dominant_pct)


def _reading_listening_usage(conn: sqlite3.Connection, user_id: int = 1) -> Dict[str, bool]:
    """Return dict with 'reading' and 'listening' booleans for last 30 days."""
    result = {"reading": False, "listening": False}
    if not _table_exists(conn, "session_log"):
        return result

    import json
    rows = conn.execute("""
        SELECT modality_counts FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
          AND items_completed > 0
          AND modality_counts IS NOT NULL
          AND user_id = ?
    """, (user_id,)).fetchall()

    for r in rows:
        try:
            mc = json.loads(r["modality_counts"])
            if mc.get("reading", 0) > 0:
                result["reading"] = True
            if mc.get("listening", 0) > 0:
                result["listening"] = True
        except (json.JSONDecodeError, TypeError):
            pass

    return result


# ---------------------------------------------------------------------------
# Composite churn risk score
# ---------------------------------------------------------------------------

def compute_churn_risk(conn: sqlite3.Connection, user_id: int = 1) -> Dict:
    """Compute composite churn risk score (0-100) with signal details.

    Weights (adapted from churn-prevention.md):
        Days since last session:    30%
        Session frequency trend:    20%
        Session duration trend:     10%
        Accuracy trend (30-day):    10%
        Drill type diversity:        5%
        Reading/listening usage:    10%
        (Cancel page / complaints not available in local DB — reallocated)
        Reserved (future signals):  15%

    Returns dict with keys:
        score: int (0-100)
        risk_level: str (Low / Medium / High / Critical)
        signals: list of dicts describing each signal
    """
    signals = []
    total_score = 0.0

    # -- 1. Days since last session (30 pts max) --
    days_gap = _days_since_last_session(conn, user_id=user_id)
    if days_gap is not None:
        # Linear: 0 pts at 0 days, 30 pts at 14+ days
        gap_pts = min(30.0, (days_gap / 14.0) * 30.0)
        total_score += gap_pts
        risk = "OK"
        if days_gap >= 14:
            risk = "Critical"
        elif days_gap >= 10:
            risk = "High"
        elif days_gap >= 5:
            risk = "Medium"
        signals.append({
            "name": "Days since last session",
            "value": f"{days_gap:.1f} days",
            "points": round(gap_pts, 1),
            "max_points": 30,
            "risk": risk,
        })
    else:
        signals.append({
            "name": "Days since last session",
            "value": "No sessions found",
            "points": 30,
            "max_points": 30,
            "risk": "Critical",
        })
        total_score += 30

    # -- 2. Session frequency trend (20 pts max) --
    freq_decline = _session_frequency_drop(conn, user_id=user_id)
    freq_pts = freq_decline * 20.0
    total_score += freq_pts
    signals.append({
        "name": "Session frequency trend",
        "value": f"{freq_decline * 100:.0f}% decline",
        "points": round(freq_pts, 1),
        "max_points": 20,
        "risk": "High" if freq_decline > 0.5 else ("Medium" if freq_decline > 0.3 else "OK"),
    })

    # -- 3. Session duration trend (10 pts max) --
    dur_decline = _session_duration_drop(conn, user_id=user_id)
    dur_pts = dur_decline * 10.0
    total_score += dur_pts
    signals.append({
        "name": "Session duration trend",
        "value": f"{dur_decline * 100:.0f}% decline",
        "points": round(dur_pts, 1),
        "max_points": 10,
        "risk": "Medium" if dur_decline > 0.5 else "OK",
    })

    # -- 4. Accuracy plateau (10 pts max) --
    plateau = _accuracy_plateau(conn, user_id=user_id)
    plateau_pts = 10.0 if plateau else 0.0
    total_score += plateau_pts
    signals.append({
        "name": "Accuracy plateau (30 days)",
        "value": "Yes" if plateau else "No",
        "points": round(plateau_pts, 1),
        "max_points": 10,
        "risk": "Medium" if plateau else "OK",
    })

    # -- 5. Drill type diversity (5 pts max) --
    unique_types, dominant_pct = _drill_type_diversity(conn, user_id=user_id)
    if unique_types <= 1:
        div_pts = 5.0
    elif unique_types == 2:
        div_pts = 3.0
    elif dominant_pct is not None and dominant_pct >= 80:
        div_pts = 4.0
    else:
        div_pts = 0.0
    total_score += div_pts
    signals.append({
        "name": "Drill type diversity",
        "value": f"{unique_types} types" + (f" (dominant: {dominant_pct:.0f}%)" if dominant_pct else ""),
        "points": round(div_pts, 1),
        "max_points": 5,
        "risk": "Low" if div_pts >= 3 else "OK",
    })

    # -- 6. Reading/listening usage (10 pts max, 5 each) --
    rl_usage = _reading_listening_usage(conn, user_id=user_id)
    rl_pts = 0.0
    if not rl_usage["reading"]:
        rl_pts += 5.0
    if not rl_usage["listening"]:
        rl_pts += 5.0
    total_score += rl_pts
    signals.append({
        "name": "Reading/listening usage (30 days)",
        "value": f"reading={'Yes' if rl_usage['reading'] else 'No'}, "
                 f"listening={'Yes' if rl_usage['listening'] else 'No'}",
        "points": round(rl_pts, 1),
        "max_points": 10,
        "risk": "Low" if rl_pts > 0 else "OK",
    })

    # -- 7. Reserved / future signals (15 pts) --
    # Cancel page visits and support complaints are not available in the local DB.
    # These slots remain at 0 until the multi-user web version ships.
    signals.append({
        "name": "Cancel page / support signals",
        "value": "N/A (local DB)",
        "points": 0,
        "max_points": 15,
        "risk": "N/A",
    })

    # Final score
    score = int(round(min(100, max(0, total_score))))

    if score >= 76:
        risk_level = "Critical"
    elif score >= 51:
        risk_level = "High"
    elif score >= 26:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # Churn type classification (Doctrine §13: differentiate churn causes)
    churn_type, intervention = _classify_churn_type(signals, days_gap, freq_decline,
                                                     dur_decline, plateau, div_pts)

    return {
        "score": score,
        "risk_level": risk_level,
        "signals": signals,
        "churn_type": churn_type,
        "intervention": intervention,
    }


# ---------------------------------------------------------------------------
# Churn type classification (Doctrine §13: type-matched interventions)
# ---------------------------------------------------------------------------

_CHURN_TYPES = {
    "life_event": {
        "description": "Life event interruption — sudden gap after regular usage",
        "intervention": "Welcome back. Your items are ready — we kept your place.",
    },
    "boredom": {
        "description": "Boredom — sessions getting shorter, low drill variety",
        "intervention": "New drill types unlocked. Try a listening or speaking session.",
    },
    "frustration": {
        "description": "Frustration — accuracy plateau or declining, sessions shortening",
        "intervention": "Session difficulty adjusted. Focus on your strongest items first.",
    },
    "habit_fade": {
        "description": "Habit fade — gradual frequency decline, no acute trigger",
        "intervention": "5 minutes keeps your rhythm. 12 items ready for review.",
    },
    "unknown": {
        "description": "Insufficient data to classify churn type",
        "intervention": "Items ready for review. About 5 minutes.",
    },
}


def _classify_churn_type(signals: list, days_gap, freq_decline, dur_decline,
                         plateau, div_pts) -> tuple:
    """Classify churn into actionable types using a decision tree.

    Returns (churn_type_key, intervention_message).
    """
    # Life event: sudden large gap (10+ days) but previously regular
    if days_gap is not None and days_gap >= 10 and freq_decline < 0.3:
        ct = "life_event"
    # Frustration: accuracy plateau + duration declining
    elif plateau and dur_decline > 0.3:
        ct = "frustration"
    # Boredom: duration declining + low drill diversity
    elif dur_decline > 0.4 and div_pts >= 3:
        ct = "boredom"
    # Habit fade: gradual frequency decline
    elif freq_decline > 0.3:
        ct = "habit_fade"
    else:
        ct = "unknown"

    info = _CHURN_TYPES[ct]
    return ct, info["intervention"]


# ---------------------------------------------------------------------------
# Public API for other modules (e.g., email trigger hooks)
# ---------------------------------------------------------------------------

def get_at_risk_users(db_path: str = None, min_risk: int = 60,
                      user_id: int = 1) -> List[Dict]:
    """Return a list of user risk profiles where score >= min_risk.

    For the current single-user system, returns a list with 0 or 1 entries.
    For multi-user, this function would iterate over all users.

    Each entry contains:
        user_id: str or int
        score: int
        risk_level: str
        signals: list of signal dicts
        days_since_last_session: float or None

    Args:
        db_path: Path to the SQLite database. Defaults to the standard location.
        min_risk: Minimum risk score to include (default 60 = High + Critical).
        user_id: User ID to check.

    Returns:
        List of risk profile dicts.
    """
    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    if not path.exists():
        return []

    conn = _get_connection(path)
    try:
        risk = compute_churn_risk(conn, user_id=user_id)
        if risk["score"] >= min_risk:
            return [{
                "user_id": user_id,
                "score": risk["score"],
                "risk_level": risk["risk_level"],
                "signals": risk["signals"],
                "days_since_last_session": _days_since_last_session(conn, user_id=user_id),
            }]
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _format_report_rich(risk: Dict) -> None:
    """Print a formatted churn report using Rich."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console = Console()

    # Header
    score = risk["score"]
    level = risk["risk_level"]
    level_colors = {
        "Low": "green",
        "Medium": "yellow",
        "High": "red",
        "Critical": "bold red",
    }
    color = level_colors.get(level, "white")

    console.print()
    console.print(Panel(
        f"[bold]Churn Risk Score: [{color}]{score}[/{color}] / 100[/bold]\n"
        f"Risk Level: [{color}]{level}[/{color}]",
        title="Churn Detection Report",
        border_style="dim",
        width=72,
    ))

    # Signals table
    table = Table(
        title="Signal Breakdown",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        width=72,
    )
    table.add_column("Signal", style="bold", min_width=32)
    table.add_column("Value", min_width=14)
    table.add_column("Pts", justify="right", min_width=6)
    table.add_column("Max", justify="right", min_width=4)
    table.add_column("Risk", min_width=8)

    for sig in risk["signals"]:
        risk_style = {
            "OK": "[green]OK[/green]",
            "Low": "[yellow]Low[/yellow]",
            "Medium": "[yellow]Medium[/yellow]",
            "High": "[red]High[/red]",
            "Critical": "[bold red]Critical[/bold red]",
            "N/A": "[dim]N/A[/dim]",
        }.get(sig["risk"], sig["risk"])

        table.add_row(
            sig["name"],
            str(sig["value"]),
            str(sig["points"]),
            str(sig["max_points"]),
            risk_style,
        )

    console.print(table)

    # Action thresholds reference
    console.print()
    console.print("  [dim]Score thresholds: 0-25 Low | 26-50 Medium | 51-75 High | 76-100 Critical[/dim]")

    # Recommended actions
    actions = {
        "Low": "Monitor. In-app nudges only.",
        "Medium": "Trigger re-engagement email sequence.",
        "High": "Trigger personal outreach email. Offer session restructuring.",
        "Critical": "Trigger save email with pause offer. Flag for personal review.",
    }
    console.print(f"  [bold]Recommended action:[/bold] {actions.get(level, 'Monitor.')}")
    console.print()


def _format_report_plain(risk: Dict) -> str:
    """Format a plain-text churn report."""
    lines = []
    score = risk["score"]
    level = risk["risk_level"]

    lines.append("")
    lines.append("=" * 60)
    lines.append("CHURN DETECTION REPORT")
    lines.append("=" * 60)
    lines.append(f"  Churn Risk Score: {score} / 100")
    lines.append(f"  Risk Level:       {level}")
    lines.append("-" * 60)
    lines.append("")
    lines.append("  SIGNAL BREAKDOWN")
    lines.append(f"  {'Signal':<34} {'Value':<16} {'Pts':>4} {'Max':>4} {'Risk':<8}")
    lines.append(f"  {'-'*34} {'-'*16} {'-'*4} {'-'*4} {'-'*8}")

    for sig in risk["signals"]:
        lines.append(
            f"  {sig['name']:<34} {str(sig['value']):<16} {sig['points']:>4} "
            f"{sig['max_points']:>4} {sig['risk']:<8}"
        )

    lines.append("")
    lines.append("  Score thresholds: 0-25 Low | 26-50 Medium | 51-75 High | 76-100 Critical")

    actions = {
        "Low": "Monitor. In-app nudges only.",
        "Medium": "Trigger re-engagement email sequence.",
        "High": "Trigger personal outreach email. Offer session restructuring.",
        "Critical": "Trigger save email with pause offer. Flag for personal review.",
    }
    lines.append(f"  Recommended action: {actions.get(level, 'Monitor.')}")
    lines.append("")
    return "\n".join(lines)


def run_report(db_path: str = None, output_format: str = "rich",
               user_id: int = 1) -> Dict:
    """Run the full churn detection report.

    Args:
        db_path: Path to the SQLite database. Defaults to the standard location.
        output_format: 'rich' for formatted terminal output, 'plain' for text.
        user_id: User ID to generate report for.

    Returns:
        The risk dict (score, risk_level, signals).
    """
    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    if not path.exists():
        logger.warning("Database not found at: %s", path)
        logger.warning("Run a session first to create the database.")
        return {"score": 0, "risk_level": "Unknown", "signals": []}

    conn = _get_connection(path)
    try:
        risk = compute_churn_risk(conn, user_id=user_id)
    finally:
        conn.close()

    if output_format == "rich":
        try:
            _format_report_rich(risk)
        except ImportError:
            print(_format_report_plain(risk))
    else:
        print(_format_report_plain(risk))

    return risk


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Churn Detection Report — Aelu",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database (default: data/mandarin.db)",
    )
    parser.add_argument(
        "--output-format",
        choices=["rich", "plain"],
        default="rich",
        help="Output format: rich (default) or plain text.",
    )
    parser.add_argument(
        "--min-risk",
        type=int,
        default=60,
        help="Minimum risk score for get_at_risk_users (default: 60).",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Print at-risk users as JSON (for scripting / email hooks).",
    )

    args = parser.parse_args()

    if args.api:
        import json
        users = get_at_risk_users(db_path=args.db_path, min_risk=args.min_risk)
        print(json.dumps(users, indent=2, default=str))
    else:
        run_report(db_path=args.db_path, output_format=args.output_format)


if __name__ == "__main__":
    main()
