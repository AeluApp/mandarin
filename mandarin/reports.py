"""Report generator — humane, concrete, actionable.

Tone principles:
- Frame gaps as normal, not failure
- Frame errors as information, not judgment
- Show data, not interpretation
- No praise, no encouragement
"""

import logging
import sqlite3
from datetime import date, timedelta
from . import db
from .diagnostics import assess_quick, project_forecast, compute_velocity, format_confidence

logger = logging.getLogger(__name__)


def _color_pct(value: float, green_thresh: float = 80, yellow_thresh: float = 50) -> str:
    """Wrap a percentage value in Rich color markup based on thresholds."""
    text = f"{value:.0f}%"
    if value >= green_thresh:
        return f"[green]{text}[/green]"
    elif value >= yellow_thresh:
        return f"[yellow]{text}[/yellow]"
    return f"[red]{text}[/red]"


def _color_pace(spw: float) -> str:
    """Color a sessions/week value: green >=3, yellow 1-3, red <1."""
    text = f"{spw:.1f}"
    if spw >= 3:
        return f"[green]{text}[/green]"
    elif spw >= 1:
        return f"[yellow]{text}[/yellow]"
    return f"[red]{text}[/red]"


def _rich_bar(pct: float, width: int = 20) -> str:
    """Build a Rich-markup colored bar chart segment."""
    filled = int(pct / (100 / width))
    filled = max(0, min(width, filled))
    empty = width - filled
    filled_str = "\u2588" * filled
    empty_str = "\u2591" * empty
    return f"[yellow]{filled_str}[/yellow][dim]{empty_str}[/dim]"


def _sparkline(values):
    """Generate a Unicode sparkline string from a list of numeric values."""
    if not values:
        return ""
    chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    mn, mx = min(values), max(values)
    if mn == mx:
        return chars[4] * len(values)
    scaled = [int((v - mn) / (mx - mn) * 7) for v in values]
    return "".join(chars[s] for s in scaled)


def _session_acc_pct(s):
    """Compute accuracy percentage for a session dict."""
    completed = s.get("items_completed") or 0
    correct = s.get("items_correct") or 0
    return (correct / completed * 100) if completed > 0 else 0


def _trend_arrow(recent_values, older_values, threshold=5.0):
    """Return a trend arrow comparing two sets of accuracy values."""
    if not recent_values or not older_values:
        return ""
    recent_avg = sum(recent_values) / len(recent_values)
    older_avg = sum(older_values) / len(older_values)
    diff = recent_avg - older_avg
    if diff > threshold:
        return " \u2191"
    elif diff < -threshold:
        return " \u2193"
    return " \u2192"


def generate_status_report(conn, user_id: int = 1) -> str:
    """Generate a full status report.

    Answers: What does this mean? What should I do? How will I know?
    """
    profile = db.get_profile(conn, user_id=user_id)
    sessions = db.get_session_history(conn, limit=30, user_id=user_id)
    total = profile.get("total_sessions") or 0
    lines = []

    lines.append("[bold]  ──── Progress Report ────[/bold]\n")

    # Library and session stats
    item_count = db.content_count(conn)
    lines.append(f"  Library:  {item_count} items")
    lines.append(f"  Sessions: {total}")

    if not sessions:
        lines.append("\n  No sessions yet. Run `mandarin` to start.")
        return "\n".join(lines)

    # Velocity
    velocity = compute_velocity(sessions)
    if velocity["sessions_per_week"] > 0:
        spw = velocity["sessions_per_week"]
        lines.append(f"  {'Pace:':<20s} {_color_pace(spw)} sessions/week")
        if velocity["items_per_session"] > 0:
            lines.append(f"  {'Avg items/session:':<20s} {velocity['items_per_session']:>6.0f} "
                        f"({velocity.get('correct_per_session', 0):.0f} correct)")

    # Accuracy sparkline + trend arrow
    completed_sessions = [s for s in sessions if (s.get("items_completed") or 0) > 0]
    if len(completed_sessions) >= 3:
        acc_values = [_session_acc_pct(s) for s in reversed(completed_sessions)]
        spark = _sparkline(acc_values)
        recent_5 = acc_values[-5:] if len(acc_values) >= 5 else acc_values
        older_5 = acc_values[-10:-5] if len(acc_values) >= 10 else []
        arrow = _trend_arrow(recent_5, older_5)
        lines.append(f"  Trend: {spark}{arrow}")

    # Gap normalization
    days_gap = db.get_days_since_last_session(conn)
    if days_gap is not None:
        from .display import format_days_gap
        lines.append(f"  Last session: {format_days_gap(days_gap)}")

    # Levels (only if enough data)
    if total >= 10:
        diag = assess_quick(conn)
        if diag.get("ready"):
            lines.append("\n[dim bold]  ── Estimated Levels ──[/dim bold]")
            for mod, data in diag.get("estimated_levels", {}).items():
                level = data.get("level", 1.0)
                conf = data.get("confidence", 0.0)
                conf_str = format_confidence(conf, data.get("total_attempts", 0))
                lines.append(f"    {mod:12s}  HSK {level:.1f}  ({conf_str})")

            # Bottlenecks
            if diag.get("bottlenecks"):
                lines.append("\n[dim bold]  ── Top Bottlenecks ──[/dim bold]")
                for i, b in enumerate(diag["bottlenecks"][:3], 1):
                    lines.append(f"\n  {i}. {b['area']} \\[{b['severity']}]")
                    lines.append(f"     {b['data']}")
                    lines.append(f"     Action: {b['action']}")
                    lines.append(f"     Test: {b['test']}")

            # Per-modality projections from forecast
            try:
                fc = project_forecast(conn)
                pace = fc.get("pace", {})
                if pace.get("reliable"):
                    lines.append("\n[dim bold]  ── Projections ──[/dim bold]")
                    lines.append(f"    Pace: {pace.get('message', '')}")
                    modality_proj = fc.get("modality_projections", {})
                    for mod in ["reading", "listening", "ime", "speaking"]:
                        mp = modality_proj.get(mod, {})
                        current = mp.get("current_level", 1.0)
                        milestones = mp.get("milestones", [])
                        if milestones:
                            for m in milestones:
                                sessions = m.get("sessions", {})
                                calendar = m.get("calendar", {})
                                conf = m.get("confidence_label", "")
                                if "optimistic" in sessions:
                                    lines.append(
                                        f"    {mod.title():10s} HSK {current:.1f} → {m['target']}"
                                        f"  {sessions['optimistic']}-{sessions['pessimistic']} sessions"
                                        f"  ({calendar['optimistic']}-{calendar['pessimistic']})  \\[{conf}]"
                                    )
                                else:
                                    lines.append(
                                        f"    {mod.title():10s} HSK {current:.1f} → {m['target']}"
                                        f"  ~{sessions['expected']} sessions"
                                        f"  ({calendar['expected']})  \\[{conf}]"
                                    )
                        else:
                            lines.append(f"    {mod.title():10s} HSK {current:.1f}  (no timeline yet)")
                    cs = fc.get("aspirational", {}).get("core_stability", {})
                    if cs:
                        lines.append(f"    Core stability: {cs.get('description', '')}")
            except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
                logger.warning("Forecast generation failed; falling back to old-style projections: %s", e)
                # Fallback: show old-style projections if forecast fails
                if diag.get("projections"):
                    lines.append("\n[dim bold]  ── Projections ──[/dim bold]")
                    for p in diag["projections"]:
                        lines.append(
                            f"    HSK {p['current']:.1f} → {p['target']:.0f}  "
                            f"{p['calendar']} ({p.get('sessions_needed', '?')} sessions)  "
                            f"· {p['confidence']}"
                        )
    else:
        remaining = 10 - total
        lines.append(f"\n  {remaining} more session{'s' if remaining != 1 else ''} until level estimates are available.")
        # Show what we do have — accuracy from sessions so far
        if sessions:
            past_correct = sum(s.get("items_correct") or 0 for s in sessions)
            past_total = sum(s.get("items_completed") or 0 for s in sessions)
            if past_total > 0:
                past_pct = past_correct / past_total * 100
                # Trend arrow from recent 5 vs previous 5 sessions
                cs = [s for s in sessions if (s.get("items_completed") or 0) > 0]
                r5 = [_session_acc_pct(s) for s in cs[:5]]
                o5 = [_session_acc_pct(s) for s in cs[5:10]]
                arrow = _trend_arrow(r5, o5)
                lines.append(f"  Accuracy so far: {past_correct}/{past_total} ({_color_pct(past_pct)}){arrow} across {len(sessions)} session{'s' if len(sessions) != 1 else ''}.")

    # Error summary
    errors = db.get_error_summary(conn, last_n_sessions=10)
    if errors:
        lines.append("\n[dim bold]  ── Recent Errors ──[/dim bold]")
        total_errors = sum(errors.values()) or 1
        for etype, count in sorted(errors.items(), key=lambda x: -x[1]):
            pct = count / total_errors * 100
            bar = _rich_bar(pct)
            lines.append(f"    {etype:16s} {bar} {count} ({pct:.0f}%)")

    # Retention model
    try:
        from .retention import compute_retention_stats
        ret = compute_retention_stats(conn)
        if ret["total_items"] >= 5:
            lines.append("\n[dim bold]  ── Memory Model ──[/dim bold]")
            lines.append(f"    {'Items tracked:':<26s} {ret['total_items']:>5}")
            ret_pct = ret['retention_pct']
            ret_pct_colored = _color_pct(ret_pct, green_thresh=80, yellow_thresh=50)
            lines.append(f"    {'Above recall threshold:':<26s} {ret['above_threshold']:>5} ({ret_pct_colored})")
            lines.append(f"    {'Below recall threshold:':<26s} {ret['below_threshold']:>5}")
            avg_recall = ret['avg_recall'] * 100
            avg_recall_colored = _color_pct(avg_recall, green_thresh=80, yellow_thresh=50)
            lines.append(f"    {'Avg recall probability:':<26s} {avg_recall_colored}")
            lines.append(f"    {'Avg half-life:':<26s} {ret['avg_half_life']:>5.1f} days")
            # Mini visual: above/below ratio bar
            above = ret['above_threshold']
            below = ret['below_threshold']
            ratio_total = above + below
            if ratio_total > 0:
                above_width = int(above / ratio_total * 20)
                below_width = 20 - above_width
                ratio_bar = f"[green]{'█' * above_width}[/green][red]{'░' * below_width}[/red]"
                lines.append(f"    {'Threshold ratio:':<26s} {ratio_bar} {above}/{ratio_total}")
            if ret.get("by_modality"):
                for mod, mdata in ret["by_modality"].items():
                    mod_recall = mdata['avg_recall'] * 100
                    mod_recall_colored = _color_pct(mod_recall, green_thresh=80, yellow_thresh=50)
                    lines.append(f"      {mod}: {mod_recall_colored} recall"
                                f" ({mdata['above']} above / {mdata['below']} below)")
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.warning("Retention stats unavailable for status report: %s", e)

    # Concrete gains from recent sessions
    recent_gains = _compute_recent_gains(conn)
    if recent_gains:
        lines.append("\n[dim bold]  ── Recent Gains ──[/dim bold]")
        lines.append(f"    {'Items reviewed:':<26s} {recent_gains['items_reviewed']:>5}")
        lines.append(f"    {'New items learned:':<26s} {recent_gains['new_items']:>5}")
        mastered = recent_gains['newly_mastered']
        mastered_str = f"[green]{mastered}[/green]" if mastered > 0 else str(mastered)
        lines.append(f"    {'Items mastered (3+ streak):':<28s} {mastered_str}")

    lines.append("")
    return "\n".join(lines)


def generate_session_summary(conn, session_id: int) -> str:
    """Generate a summary for a specific completed session."""
    session = conn.execute(
        "SELECT * FROM session_log WHERE id = ?", (session_id,)
    ).fetchone()
    if not session:
        return "  Session not found."

    session = dict(session)
    lines = []

    completed = session.get("items_completed") or 0
    correct = session.get("items_correct") or 0
    accuracy = (correct / completed * 100) if completed > 0 else 0

    lines.append(f"  Session #{session_id}: {correct}/{completed} ({accuracy:.0f}%)")

    if session.get("duration_seconds"):
        m, s = divmod(session["duration_seconds"], 60)
        lines.append(f"  Duration: {m}m {s:02d}s")

    if session.get("days_since_last_session") and session["days_since_last_session"] >= 3:
        lines.append(f"  Gap: {session['days_since_last_session']} days")

    return "\n".join(lines)


def _compute_recent_gains(conn, days: int = 14) -> dict:
    """Compute concrete gains from the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) FROM progress
        WHERE last_review_date >= ?
    """, (cutoff,)).fetchone()
    reviewed = row[0] if row else 0

    row = conn.execute("""
        SELECT COUNT(*) FROM progress
        WHERE repetitions = 1 AND last_review_date >= ?
    """, (cutoff,)).fetchone()
    new_items = row[0] if row else 0

    row = conn.execute("""
        SELECT COUNT(*) FROM progress
        WHERE streak_correct >= 3 AND last_review_date >= ?
    """, (cutoff,)).fetchone()
    mastered = row[0] if row else 0

    return {
        "items_reviewed": reviewed or 0,
        "new_items": new_items or 0,
        "newly_mastered": mastered or 0,
    }
