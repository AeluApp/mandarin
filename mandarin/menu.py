"""Non-terminal interactive menu — no command typing required.

Reuses all core logic from CLI modules. This is a presentation layer only.
"""

import logging
import sqlite3

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Heavy internal imports are deferred to function bodies so that when
# menu.py is invoked via `python -m mandarin.menu`, any import-time
# error in db/scheduler/runner/reports is caught by the __main__ crash
# handler instead of producing a raw traceback.

logger = logging.getLogger(__name__)

console = Console()


def _show(text: str, end="\n"):
    console.print(text, end=end, highlight=False)

def _input(prompt: str) -> str:
    return console.input(prompt)


def show_menu(expanded=False):
    """Display the main menu and return user choice."""
    console.print()
    console.print("  漫 [bold]Aelu[/bold]")
    console.print()

    # Primary actions — always visible
    console.print("  [bold bright_cyan]1. Study[/bold bright_cyan]              today's session")
    console.print("  2. Mini              90 seconds")
    console.print("  5. Status            current progress")

    if expanded:
        console.print()
        console.print("  [dim]Quick[/dim]")
        console.print("  3. Catch-up          weak spots")
        console.print("  4. Listen            passive immersion")
        console.print()
        console.print("  [dim]Progress[/dim]")
        console.print("  6. Goal              focus area")
        console.print("  7. Forecast          projections")
        console.print()
        console.print("  [dim]Media[/dim]")
        console.print("  13. Watch            real Chinese media + quiz")
        console.print()
        console.print("  [dim]8. Report  ·  9. History  ·  10. Errors  ·  11. Scenarios  ·  12. Web UI[/dim]")

    console.print()
    if expanded:
        console.print("  [dim]0. Quit[/dim]")
    else:
        console.print("  [dim]m. More  ·  0. Quit[/dim]")
    console.print()

    choice = _input("  > ").strip()
    return choice


def run_menu():
    """Main menu loop."""
    # Deferred imports: when menu.py runs as __main__, the crash handler
    # (installed in the if-__name__ block below) must be in place before
    # any heavy internal imports execute.  Importing here instead of at
    # module level ensures import-time errors get logged to crash.log.
    global db, plan_standard_session, plan_minimal_session
    global plan_catchup_session, get_day_profile, run_session, generate_status_report
    from . import db
    from .scheduler import plan_standard_session, plan_minimal_session, plan_catchup_session, get_day_profile
    from .runner import run_session
    from .reports import generate_status_report

    expanded = False
    while True:
        choice = show_menu(expanded=expanded)
        expanded = False  # reset after each action

        if choice.lower() == "m":
            expanded = True
            continue

        if choice in ("0", "q", "Q"):
            console.print("\n  Until next time.\n")
            break

        conn = db.ensure_db()

        try:
            if choice == "1":
                _run_today(conn)
            elif choice == "2":
                _run_mini(conn)
            elif choice == "3":
                _run_catchup(conn)
            elif choice == "4":
                _run_listen(conn)
            elif choice == "5":
                _show_status(conn)
            elif choice == "6":
                _show_goal(conn)
            elif choice == "7":
                _show_forecast(conn)
            elif choice == "8":
                _show_report(conn)
            elif choice == "9":
                _show_history(conn)
            elif choice == "10":
                _show_errors(conn)
            elif choice == "11":
                _show_scenarios(conn)
            elif choice == "12":
                conn.close()
                _launch_web()
                continue
            elif choice == "13":
                _run_watch(conn)
            else:
                console.print("  [dim]Pick a number (1-13) or 0 to quit.[/dim]")
        except KeyboardInterrupt:
            console.print("\n")
        finally:
            conn.close()


def _check_content(conn) -> bool:
    """Check that content is loaded; show error if not. Returns True if content exists."""
    if db.content_count(conn) == 0:
        console.print("\n  No content loaded. Run: ./run add-hsk 1\n")
        return False
    return True


def _run_today(conn, user_id: int = 1):
    if not _check_content(conn):
        return

    profile = db.get_profile(conn, user_id=user_id)
    day_profile = get_day_profile()
    console.print()
    console.print(f"  Loading session #{profile['total_sessions'] + 1}...", style="dim")
    plan = plan_standard_session(conn)
    console.print(f"  {len(plan.drills)} items ready · {day_profile['name']}", style="dim")
    run_session(conn, plan, _show, _input)


def _run_mini(conn):
    if not _check_content(conn):
        return
    console.print()
    console.print("  Loading mini session...", style="dim")
    plan = plan_minimal_session(conn)
    console.print(f"  {len(plan.drills)} items · ~90 seconds", style="dim")
    run_session(conn, plan, _show, _input)


def _run_listen(conn):
    from .audio import speak_and_wait, is_audio_available
    import time as _time

    if not is_audio_available():
        console.print("\n  Audio not available (needs macOS with Tingting voice).")
        return

    items = conn.execute("""
        SELECT ci.hanzi, ci.pinyin, ci.english, ci.hsk_level, ci.context_note
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = 'reading'
        WHERE ci.status = 'drill_ready'
        ORDER BY CASE WHEN p.total_attempts > 0 THEN 0 ELSE 1 END, RANDOM()
        LIMIT 20
    """).fetchall()

    if not items:
        console.print("\n  No items to listen to.\n")
        return

    console.print()
    console.print("  Passive Listening", style="bold")
    console.print(f"  {len(items)} items — just listen and absorb.")
    console.print("  Enter = next, Q = quit.")
    console.print()

    heard = 0
    for i, item in enumerate(items):
        item = dict(item)
        console.print(f"  [{i+1}/{len(items)}]  [bright_cyan]{item['hanzi']}[/bright_cyan]")
        speak_and_wait(item["hanzi"], rate=160)
        _time.sleep(1.5)
        console.print(f"          {item['pinyin']}  —  {item['english']}")
        if item.get("context_note"):
            console.print(f"          [dim italic]{item['context_note']}[/dim italic]")
        heard += 1
        try:
            response = console.input("  ").strip().upper()
            if response == "Q":
                break
        except (KeyboardInterrupt, EOFError):
            break

    console.print(f"\n  Heard {heard} items. Every bit helps.\n")


def _run_catchup(conn):
    if not _check_content(conn):
        return
    console.print()
    console.print("  Loading catch-up session...", style="dim")
    plan = plan_catchup_session(conn)
    if not plan.drills:
        console.print("  No items below catch-up threshold.")
        return
    console.print(f"  {len(plan.drills)} items to revisit", style="dim")
    run_session(conn, plan, _show, _input)


def _show_status(conn, user_id: int = 1):
    from .milestones import get_stage_counts, get_growth_summary
    from .diagnostics import get_speed_trend

    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions", 0) or 0
    days_gap = db.get_days_since_last_session(conn)
    stages = get_stage_counts(conn)
    solid = stages["stable"] + stages["durable"]
    growing = stages["stabilizing"]
    early = stages["seen"] + stages["passed_once"]
    needs_review = stages["decayed"]
    seen_total = solid + growing + early + needs_review

    console.print()
    console.print("  Status", style="bold")

    # ── Primary signal: Am I getting better? ──
    console.print()
    if total_sessions == 0:
        console.print(f"  {total_sessions} session completed. No items seen yet.")
    elif seen_total == 0:
        console.print(f"  {total_sessions} sessions completed. No items seen yet.")
    else:
        console.print(f"  {solid} stable, {growing} stabilizing, {seen_total} seen.")

    # ── Recency ──
    if days_gap is not None:
        if days_gap == 0:
            console.print("  Last session: today")
        elif days_gap == 1:
            console.print("  Last session: yesterday")
        elif days_gap <= 3:
            console.print(f"  Last session: {days_gap} days ago")
        else:
            console.print(f"  Last session: {days_gap} days ago")

    # ── Stabilized ──
    mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
    active_levels = {k: v for k, v in mastery.items() if v.get("seen", 0) > 0} if mastery else {}
    if active_levels:
        console.print()
        console.print("  [dim]── Mastery by level ──[/dim]")
        for level in sorted(active_levels.keys()):
            m = active_levels[level]
            total = m["total"]
            lvl_stable = m.get("stable", 0) + m.get("durable", 0)
            lvl_stabilizing = m.get("stabilizing", 0)
            not_seen = m.get("not_seen", 0)

            bar_len = 20
            stable_chars = round(lvl_stable / total * bar_len) if total > 0 else 0
            stabilizing_chars = round(lvl_stabilizing / total * bar_len) if total > 0 else 0
            empty_chars = bar_len - stable_chars - stabilizing_chars
            bar = "[green]" + "\u2588" * stable_chars + "[/green]" + \
                  "[yellow]" + "\u2588" * stabilizing_chars + "[/yellow]" + \
                  "[dim]" + "\u2591" * empty_chars + "[/dim]"
            console.print(f"    HSK {level}  {bar}  {lvl_stable} solid  {lvl_stabilizing} stabilizing  {not_seen} unseen")

    # ── Memory model ──
    try:
        from .retention import compute_retention_stats
        ret = compute_retention_stats(conn)
        if ret["total_items"] >= 5:
            console.print()
            console.print("  [dim]── Memory ──[/dim]")
            console.print(f"    {ret['retention_pct']:.0f}% of reviewed items above recall threshold")
            console.print(f"    Avg predicted recall: {ret['avg_recall']:.0%}  ·  Avg half-life: {ret['avg_half_life']:.1f} days")
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("Retention stats unavailable for status display: %s", e)

    # ── What you're building ──
    if growing > 0 or early > 0 or needs_review > 0:
        console.print()
        console.print("  [dim]── What you're building ──[/dim]")
        if growing > 0:
            console.print(f"    {growing} items stabilizing — getting stronger with repetition")
        if stages["passed_once"] > 0:
            console.print(f"    {stages['passed_once']} items passed once")
        if stages["seen"] > 0:
            console.print(f"    {stages['seen']} items seen (not yet reliable)")
        if needs_review > 0:
            console.print(f"    {needs_review} items need review (were stable)")

    # ── Secondary details (dimmer) ──
    speed = get_speed_trend(conn)
    growth = get_growth_summary(conn)
    has_details = speed["total_timed"] > 0 or growth["latest"]

    if has_details:
        console.print()
        console.print("  [dim]── Details ──[/dim]")
        if speed["total_timed"] > 0:
            console.print(f"    Speed: {speed['summary']}")
        if growth["latest"]:
            console.print(f"    {growth['phase_label']}")
            console.print(f"    ✦ {growth['latest']['label']}")

    console.print()


def _show_goal(conn):
    from .diagnostics import compute_readiness
    from .milestones import get_growth_summary

    readiness = compute_readiness(conn)
    growth = get_growth_summary(conn)

    console.print()
    console.print("  Goal & Readiness", style="bold")
    console.print()

    score = readiness["score"]
    bar_len = 20
    filled = round(score / 100 * bar_len)
    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
    console.print(f"  Readiness:  {bar}  {score:.0f}%  ({readiness['label']})")
    console.print()

    labels = {
        "scenario_mastery": "Scenarios",
        "item_stability": "Stability",
        "modality_breadth": "Breadth",
        "practice_consistency": "Consistency",
    }
    for key in ["scenario_mastery", "item_stability", "modality_breadth", "practice_consistency"]:
        comp = readiness["components"][key]
        c_filled = round(comp["score"] / 100 * 10)
        c_bar = "\u2588" * c_filled + "\u2591" * (10 - c_filled)
        console.print(f"    {labels[key]:14s} {c_bar} {comp['score']:5.0f}%  ({comp['detail']})")

    if growth["latest"]:
        console.print()
        console.print(f"  {growth['phase_label']}")
        console.print(f"  \u2726 {growth['latest']['label']}")
        if growth["next"]:
            console.print(f"    Next: {growth['next']['label']}")

    # ── Ambiguity comfort ──
    from .diagnostics import compute_ambiguity_comfort
    comfort = compute_ambiguity_comfort(conn)
    if comfort["total_attempts"] > 0:
        console.print()
        console.print(f"  Ambiguity comfort: {comfort['comfort_label']}")
        console.print(f"    {comfort['summary']}")

    console.print()
    console.print(f"  Focus: {readiness['focus']}")
    console.print()


def _show_forecast(conn):
    from .diagnostics import project_forecast, format_confidence

    fc = project_forecast(conn)
    pace = fc["pace"]

    console.print()
    console.print("  Forecast", style="bold")
    console.print()

    # Pace line
    console.print(f"  Current pace: {pace['message']}")
    console.print()

    if not pace["reliable"]:
        # Low session count — frame as building baseline
        total = fc.get("total_sessions", 0)
        remaining = max(0, 8 - total)
        if total == 0:
            console.print("  No sessions yet — levels will appear as you practice.")
        elif total < 3:
            console.print(f"  {total} sessions completed. Levels firm up after a few more.")
        else:
            console.print(f"  Building baseline — {remaining} more sessions for projections.")
        console.print()
        console.print("  [dim]Estimated levels (will stabilize with more data):[/dim]")
        for mod in ["reading", "listening", "speaking", "ime"]:
            data = fc["estimated_levels"].get(mod, {"level": 1.0, "confidence": 0.0, "total_attempts": 0})
            attempts = data.get("total_attempts", 0)
            if attempts == 0:
                detail = "no data yet"
            elif attempts < 30:
                detail = f"{attempts} attempts — very early"
            else:
                conf_label = format_confidence(data["confidence"], attempts)
                detail = conf_label
            console.print(f"    {mod:12s}  HSK {data['level']:.1f}  ({detail})")
        console.print()
        return

    # Per-modality projections
    console.print("  ── Per-Modality Projections ──")
    console.print()

    modality_proj = fc["modality_projections"]
    for mod in ["reading", "listening", "ime", "speaking"]:
        mp = modality_proj.get(mod, {})
        current = mp.get("current_level", 1.0)
        console.print(f"  {mod.title()} (currently HSK {current:.1f}):")
        milestones = mp.get("milestones", [])
        if milestones:
            for m in milestones:
                sessions = m["sessions"]
                calendar = m["calendar"]
                conf = m.get("confidence_label", "")
                if "optimistic" in sessions:
                    console.print(
                        f"    {m['target']}    {sessions['optimistic']}-{sessions['pessimistic']} sessions"
                        f"  ({calendar['optimistic']}-{calendar['pessimistic']})  [{conf}]"
                    )
                else:
                    console.print(
                        f"    {m['target']}    ~{sessions['expected']} sessions"
                        f"  ({calendar['expected']})  [{conf}]"
                    )
        else:
            console.print("    (no timeline yet)")
        console.print()

    # Tone projection
    tone = modality_proj.get("tone", {})
    if tone.get("tone_error_rate", 0) > 0:
        rate_pct = int(tone["tone_error_rate"] * 100)
        target_pct = int(tone["target"] * 100)
        console.print(f"  Tone Perception:")
        line = f"    Error rate: {rate_pct}% → target: <{target_pct}%"
        if "sessions_est" in tone:
            se = tone["sessions_est"]
            conf = tone.get("confidence_label", "")
            if "optimistic" in se:
                line += f"    est: {se['optimistic']}-{se['pessimistic']} sessions  [{conf}]"
            else:
                line += f"    est: ~{se['expected']} sessions  [{conf}]"
        console.print(line)
        console.print()

    # Aspirational milestones
    aspirational = fc.get("aspirational", {})
    asp_labels = [
        ("casual_media", "Casual media comprehension"),
        ("professional", "Professional competence"),
        ("advanced", "Advanced proficiency"),
        ("near_native", "Near-native fluency"),
    ]
    if any(aspirational.get(label) for label, _ in asp_labels):
        console.print("  ── Aspirational Milestones ──")
        console.print()

        for label, display in asp_labels:
            asp = aspirational.get(label)
            if asp:
                cal = asp["calendar"]
                hsk = asp["hsk_target"]
                conf = asp.get("confidence", "")
                if "optimistic" in cal:
                    console.print(f"  {display} (HSK {hsk}):  {cal['optimistic']}-{cal['pessimistic']}  [{conf}]")
                else:
                    console.print(f"  {display} (HSK {hsk}):  {cal['expected']}  [{conf}]")

    # Core stability
    cs = aspirational.get("core_stability", {})
    if cs:
        console.print(f"  Core stability:  {cs.get('description', '')}")

    # Retention model
    retention = fc.get("retention")
    if retention and retention["total_items"] >= 5:
        console.print(f"  Retention: {retention['retention_pct']:.0f}% above recall threshold"
                      f"  (avg recall: {retention['avg_recall']:.0%},"
                      f" avg half-life: {retention['avg_half_life']:.1f}d)")

    console.print()


def _show_report(conn):
    console.print()
    console.print(generate_status_report(conn))


def _show_history(conn, user_id: int = 1):
    sessions = db.get_session_history(conn, limit=10, user_id=user_id)
    console.print()
    console.print("  Recent sessions:", style="bold")
    console.print()

    if not sessions:
        console.print("  No sessions yet.\n")
        return

    for s in sessions:
        d = s["started_at"][:10]
        completed = s["items_completed"]
        correct = s["items_correct"]
        stype = s["session_type"]
        duration = s.get("duration_seconds")
        dur_str = f" ({duration // 60}m{duration % 60:02d}s)" if duration else ""
        accuracy = f"{correct}/{completed}" if completed else "—"
        console.print(f"  {d}  {stype:8s}  {accuracy:>7s}{dur_str}")
    console.print()


def _show_errors(conn):
    rows = conn.execute("""
        SELECT el.*, ci.hanzi, ci.pinyin, ci.english
        FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        ORDER BY el.created_at DESC LIMIT 15
    """).fetchall()

    console.print()
    if not rows:
        console.print("  No errors recorded yet.\n")
        return

    console.print("  Recent errors:", style="bold")
    console.print()
    for r in rows:
        r = dict(r)
        console.print(
            f"  [{r['error_type']:15s}] {r['hanzi']} ({r['pinyin']})  "
            f"you: {r['user_answer'] or '—'}  expected: {r['expected_answer'] or '—'}"
        )
    console.print()


def _launch_web():
    """Launch the web interface and open the browser."""
    import webbrowser
    import threading
    from .web import create_app
    from .settings import PORT, DEFAULT_PORT

    port = PORT or DEFAULT_PORT
    url = f"http://localhost:{port}"
    flask_app = create_app()

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    console.print(f"\n  Opening browser at {url}")
    console.print("  Press Ctrl+C to stop and return to menu.\n")

    try:
        flask_app.run(host="127.0.0.1", port=port, debug=False)
    except KeyboardInterrupt:
        console.print("\n  Web server stopped.\n")


def _show_scenarios(conn):
    try:
        from .scenario_loader import get_available_scenarios
        rows = get_available_scenarios(conn, hsk_max=9, limit=50)
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.warning("Failed to load scenarios: %s", e)
        rows = []

    console.print()
    if not rows:
        console.print("  No scenarios loaded.")
        console.print("  Run: ./run import-scenarios data/scenarios/\n")
        return

    console.print("  Dialogue Scenarios", style="bold")
    console.print()
    for s in rows:
        score_str = f" avg: {s['avg_score']:.0%}" if s.get("avg_score") is not None else ""
        console.print(
            f"  [{s['id']}] HSK {s['hsk_level']}  {s['title']}"
            f"  ({s['register']}, played {s['times_presented']}x{score_str})"
        )
    console.print()


def _run_watch(conn, user_id: int = 1):
    from .media import (
        load_media_catalog, recommend_media, run_media_comprehension,
        record_media_presentation, record_media_skip, _ensure_media_rows,
    )

    catalog = load_media_catalog()
    if not catalog:
        console.print("\n  No media catalog found.")
        console.print("  Expected: data/media_catalog.json\n")
        return

    _ensure_media_rows(conn, catalog)

    profile = db.get_profile(conn, user_id=user_id)
    max_hsk = max(int(profile.get("level_reading", 1) or 1), 1) + 1

    lens_weights = {}
    for col in ("lens_quiet_observation", "lens_institutions", "lens_urban_texture",
                 "lens_humane_mystery", "lens_identity", "lens_comedy",
                 "lens_food", "lens_travel", "lens_explainers",
                 "lens_wit", "lens_ensemble_comedy", "lens_sharp_observation",
                 "lens_satire", "lens_moral_texture"):
        lens_weights[col] = float(profile.get(col) or 0.5)

    recs = recommend_media(conn, hsk_max=max_hsk, lens_weights=lens_weights, limit=3)
    if not recs:
        console.print("\n  No recommendations available for current level.\n")
        return

    for entry, watch in recs:
        console.print()
        console.print(f"  [bold bright_cyan]{entry.get('title_zh', '')}[/bold bright_cyan]")
        console.print(f"  {entry.get('title', '')}  ({entry.get('year', '')})")
        seg = entry.get("segment", {})
        if seg.get("description"):
            console.print(f"  {seg['description']}")
        wtf = entry.get("where_to_find", {})
        if wtf.get("primary"):
            console.print(f"  [dim]{wtf['primary']}[/dim]")
        vocab = entry.get("vocab_preview", [])
        if vocab:
            console.print(f"  [dim]Vocab:[/dim] " + ", ".join(
                f"{v['hanzi']} ({v.get('english', '')})" for v in vocab))

        record_media_presentation(conn, entry["id"])
        resp = _input("\n  Press Enter when you've watched it, S to skip, Q to quit: ").strip().upper()

        if resp == "Q":
            return
        if resp == "S":
            record_media_skip(conn, entry["id"])
            console.print("  Skipped.")
            continue

        run_media_comprehension(entry, _show, _input, conn=conn)
        return


if __name__ == "__main__":
    import sys
    import traceback
    from .log_config import configure_logging, utc_now_iso, CRASH_LOG
    configure_logging(mode="cli")
    _logger = logging.getLogger(__name__)
    try:
        run_menu()
    except KeyboardInterrupt:
        print("\n")
        sys.exit(0)
    except Exception:
        log_dir = CRASH_LOG.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        tb = traceback.format_exc()
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{utc_now_iso()}\n")
            f.write(tb)
        _logger.error("Unhandled exception in menu: %s", tb.splitlines()[-1])
        print(f"\n  Something went wrong. Details saved to: {CRASH_LOG}", file=sys.stderr)
        print(f"  Run again or check the log.\n", file=sys.stderr)
        sys.exit(1)
