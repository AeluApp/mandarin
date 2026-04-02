"""CLI interface — Typer + Rich, calm and tasteful.

Utilities: _sparkline, _trend_arrow, _session_accuracy_pct
"""

import logging
import sqlite3
import sys
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

logger = logging.getLogger(__name__)

from . import db
from .cli_auth import get_cli_user_id
from .scheduler import plan_standard_session, plan_minimal_session, plan_catchup_session
from .runner import run_session
from datetime import UTC

app = typer.Typer(
    name="mandarin",
    help="Aelu — patient Mandarin study. Default: run today's session.",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()


def _sparkline(values, width=None):
    """Generate a Unicode sparkline string from a list of numeric values."""
    if not values:
        return ""
    chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    mn, mx = min(values), max(values)
    if mn == mx:
        return chars[4] * len(values)
    scaled = [int((v - mn) / (mx - mn) * 7) for v in values]
    return "".join(chars[s] for s in scaled)


def _trend_arrow(recent_values, older_values, threshold=5.0):
    """Return a trend arrow comparing two sets of accuracy values.

    threshold is in percentage points (e.g. 5 means +/-5%).
    """
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


def _session_accuracy_pct(s):
    """Compute accuracy percentage for a session dict."""
    completed = s.get("items_completed") or 0
    correct = s.get("items_correct") or 0
    return (correct / completed * 100) if completed > 0 else 0


def _show(text: str, end="\n"):
    console.print(text, end=end, highlight=False)

def _input(prompt: str) -> str:
    return console.input(prompt)


# ── Main command ──────────────────────────────

@app.callback(invoke_without_command=True)
def today(ctx: typer.Context):
    """Run today's session. This is the default command."""
    if ctx.invoked_subcommand is not None:
        return

    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        item_count = db.content_count(conn)

        if item_count == 0:
            _onboard_first_run(conn)
            return

        profile = db.get_profile(conn, user_id=user_id)
        _run_session_flow(conn, profile, user_id=user_id)


def _onboard_first_run(conn):
    """Interactive first-run onboarding: offer to load HSK 1 vocabulary."""
    console.print(Panel(
        "[bold]漫 Aelu[/bold]\n\n"
        "HSK 1-9 word lists available (10,000+ items).\n"
        "HSK 1 has ~500 words.\n",
        title="漫 Aelu", border_style="dim",
    ))

    resp = console.input("  Load HSK 1 vocabulary? (y/n) ").strip().lower()
    if resp in ("y", "yes", ""):
        from .importer import import_hsk_level
        try:
            added, skipped = import_hsk_level(conn, 1)
            console.print(f"\n  Loaded {added} HSK 1 items.")
            console.print(f"  Run [bold]./run[/bold] again to begin.")
            console.print(f"  Later: [bold]mandarin add-hsk 2[/bold] to add the next level.\n")
        except FileNotFoundError:
            console.print("\n  HSK 1 data file not found.")
            console.print("  Run: [bold]mandarin add-hsk 1[/bold] after checking data/hsk/\n")
    else:
        console.print()
        console.print("  To load vocabulary later:")
        console.print("    [bold]mandarin add-hsk 1[/bold]   — Load HSK 1 (~500 words)")
        console.print("    [bold]mandarin add-hsk 2[/bold]   — Load HSK 2")
        console.print("    [bold]mandarin sync-hsk[/bold]    — Load all available levels")
        console.print("    [bold]mandarin add[/bold]         — Add items manually")
        console.print()


def _show_warm_start(conn, profile, user_id: int = 1):
    """Show warm-start context: stored intention, compact HSK bars, items due."""
    from datetime import datetime, timezone, timedelta

    # Stored intention (if set within last 3 days)
    intention = profile.get("next_session_intention")
    intention_at = profile.get("intention_set_at")
    if intention and intention_at:
        try:
            set_dt = datetime.fromisoformat(intention_at)
            age = datetime.now(UTC) - set_dt
            if age < timedelta(days=3):
                console.print(f"  [dim]You planned:[/dim] [italic]{intention}[/italic]")
        except (ValueError, TypeError):
            pass

    # Compact HSK progress bars (1 line per active level)
    mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
    active = {k: v for k, v in mastery.items() if v.get("seen", 0) > 0} if mastery else {}
    if active:
        parts = []
        for level in sorted(active.keys()):
            m = active[level]
            total = m["total"]
            if total == 0:
                continue
            solid = m.get("stable", 0) + m.get("durable", 0)
            pct = round(solid / total * 100)
            bar_len = 10
            filled = round(pct / 100 * bar_len)
            bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
            parts.append(f"HSK {level} [green]{bar}[/green] {pct}%")
        if parts:
            console.print(f"  [dim]{' · '.join(parts)}[/dim]")

    # Items due
    due = db.get_items_due_count(conn)
    if due > 0:
        console.print(f"  [dim]{due} items due for review[/dim]")
    console.print()


def _run_session_flow(conn, profile, user_id: int = 1):
    """Shared session logic for the default command and the session/s aliases."""
    from .scheduler import get_day_profile
    day_profile = get_day_profile(conn, user_id=user_id)

    total_sessions = profile.get("total_sessions", 0) or 0

    console.print()
    console.print("  漫 Aelu", style="bold")
    console.print(f"  Session #{total_sessions + 1} · {day_profile['name']}", style="dim")
    console.print()

    if total_sessions == 0:
        console.print("  Q = done, B = skip, N = unsure, ? = hint")
        console.print("  MC drills: answer by number. Typing drills: type pinyin.")
        console.print("  Web UI: [bold]./run app[/bold]")
        console.print()
    else:
        # ── Warm start: intention, HSK snapshot, items due ──
        _show_warm_start(conn, profile, user_id=user_id)

    # Pre-commitment: auto-switch to mini on pre-committed weak days
    from datetime import date as _date
    minimal_days = (profile.get("minimal_days") or "").strip()
    today_dow = _date.today().weekday()
    if minimal_days and str(today_dow) in minimal_days.split(","):
        from .scheduler import plan_minimal_session
        console.print("  [dim]Mini session today (pre-commitment day). Override with: ./run session[/dim]")
        console.print()
        plan = plan_minimal_session(conn)
    else:
        plan = plan_standard_session(conn, user_id=user_id)
    run_session(conn, plan, _show, _input, user_id=user_id)


@app.command()
def session():
    """Start today's session."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        if db.content_count(conn) == 0:
            console.print("\n  No content loaded. Run: mandarin add-hsk 1\n")
            return
        profile = db.get_profile(conn, user_id=user_id)
        _run_session_flow(conn, profile, user_id=user_id)


# ── Session commands ──────────────────────────────

@app.command()
def mini():
    """Run a minimal 90-second session."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        if db.content_count(conn) == 0:
            console.print("\n  [dim]No content loaded. Run: mandarin add-hsk 1[/dim]\n")
            return

        console.print()
        console.print("  漫 Aelu — Mini Session", style="bold")
        console.print()

        plan = plan_minimal_session(conn)
        run_session(conn, plan, _show, _input, user_id=user_id)


@app.command()
def catchup():
    """Run a catch-up session focused on weak spots."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        if db.content_count(conn) == 0:
            console.print("\n  [dim]No content loaded. Run: mandarin add-hsk 1[/dim]\n")
            return

        console.print()
        console.print("  漫 Aelu — Catch-up Session", style="bold")
        console.print()

        plan = plan_catchup_session(conn)
        if not plan.drills:
            console.print("  No weak spots found yet. Run standard sessions first.\n")
            return

        run_session(conn, plan, _show, _input, user_id=user_id)


# ── Content commands ──────────────────────────────

@app.command(name="import-csv")
def import_csv(
    file_path: str = typer.Argument(..., help="Path to CSV file"),
    hsk: int = typer.Option(None, "--hsk", help="HSK level (1-9)"),
    register: str = typer.Option("neutral", "--register", help="Register: casual/neutral/professional"),
    lens: str = typer.Option(None, "--lens", help="Content lens tag"),
):
    """Import vocabulary from a CSV file."""
    with db.connection() as conn:
        from .importer import import_csv as do_import

        try:
            added, skipped = do_import(conn, file_path, hsk_level=hsk, register=register, content_lens=lens)
            console.print(f"\n  Added {added} items ({skipped} skipped).")
            console.print(f"  Total library: {db.content_count(conn)} items.\n")
        except FileNotFoundError:
            console.print(f"\n  File not found: {file_path}\n")


@app.command(name="import-srt")
def import_srt(
    file_path: str = typer.Argument(..., help="Path to .srt subtitle file"),
    register: str = typer.Option("mixed", "--register", help="Register: casual/neutral/professional/mixed"),
    lens: str = typer.Option(None, "--lens", help="Content lens tag"),
):
    """Import sentences from a subtitle (.srt) file."""
    with db.connection() as conn:
        from .importer import import_srt as do_import

        try:
            added, skipped = do_import(conn, file_path, register=register, content_lens=lens)
            console.print(f"\n  Extracted {added} sentences ({skipped} duplicates).")
            console.print(f"  Total library: {db.content_count(conn)} items.\n")
        except FileNotFoundError:
            console.print(f"\n  File not found: {file_path}\n")


@app.command()
def add(
    hanzi: str = typer.Argument(..., help="Chinese characters"),
    pinyin: str = typer.Argument(..., help="Pinyin with tone marks or numbers"),
    english: str = typer.Argument(..., help="English meaning"),
    hsk: int = typer.Option(None, "--hsk", help="HSK level (1-9)"),
    register: str = typer.Option("neutral", "--register"),
    lens: str = typer.Option(None, "--lens", help="Content lens tag"),
):
    """Add a single vocabulary item."""
    with db.connection() as conn:
        from .importer import add_item

        item_id = add_item(conn, hanzi, pinyin, english, hsk_level=hsk, register=register, content_lens=lens)
        if item_id:
            console.print(f"\n  Added: {hanzi} ({pinyin}) — {english}\n")
        else:
            console.print(f"\n  Already exists: {hanzi}\n")


@app.command(name="add-hsk")
def add_hsk(
    level: int = typer.Argument(..., help="HSK level to load (1-9)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be loaded without changing"),
):
    """Load HSK vocabulary for a given level."""
    with db.connection() as conn:
        from .importer import import_hsk_level

        try:
            added, skipped = import_hsk_level(conn, level, dry_run=dry_run)
            if dry_run:
                console.print(f"\n  [dry run] Would add {added} HSK {level} items ({skipped} already exist).\n")
            else:
                console.print(f"\n  Loaded {added} HSK {level} items ({skipped} duplicates skipped).")
                console.print(f"  Total library: {db.content_count(conn)} items.\n")
        except FileNotFoundError as e:
            console.print(f"\n  {e}\n")


@app.command(name="add-audio")
def add_audio(
    hsk_level: int = typer.Option(0, "--hsk", help="Only generate for this HSK level (0 = all)"),
    limit: int = typer.Option(0, "--limit", help="Max items to process (0 = no limit)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count items without generating"),
    voice: str = typer.Option("female", help="TTS voice (female, male, female_young)"),
):
    """Pre-generate TTS audio for content items and cache to disk."""
    from .audio import generate_audio_file, get_persistent_audio_dir

    with db.connection() as conn:
        query = "SELECT id, hanzi FROM content_item WHERE hanzi IS NOT NULL AND audio_available = 0"
        params: list = []
        if hsk_level > 0:
            query += " AND hsk_level = ?"
            params.append(hsk_level)
        query += " ORDER BY hsk_level ASC, id ASC"
        if limit > 0:
            query += f" LIMIT {limit}"

        items = conn.execute(query, params).fetchall()

        if dry_run:
            console.print(f"\n  [dry run] {len(items)} items need audio generation.\n")
            return

        if not items:
            console.print("\n  All content items already have audio.\n")
            return

        console.print(f"\n  Generating audio for {len(items)} items (voice={voice})...")
        generated = 0
        failed = 0
        for item in items:
            fname = generate_audio_file(item["hanzi"], voice=voice)
            if fname:
                conn.execute(
                    "UPDATE content_item SET audio_available = 1, audio_file_path = ? WHERE id = ?",
                    (fname, item["id"]),
                )
                generated += 1
            else:
                failed += 1
            if generated % 50 == 0 and generated > 0:
                conn.commit()
                console.print(f"    ... {generated}/{len(items)}")

        conn.commit()
        console.print(f"  Done: {generated} generated, {failed} failed.")
        console.print(f"  Audio cache: {get_persistent_audio_dir()}\n")


@app.command(name="tag-lenses")
def tag_lenses(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be tagged without changing"),
):
    """Auto-tag content items with content lenses."""
    with db.connection() as conn:
        from .importer import auto_tag_lens

        counts = auto_tag_lens(conn, dry_run=dry_run)
        console.print()
        if counts:
            label = "Would tag" if dry_run else "Tagged"
            for lens, count in sorted(counts.items(), key=lambda x: -x[1]):
                console.print(f"  {label} {count} items as '{lens}'")
            total = sum(counts.values())
            console.print(f"\n  Total: {total} items\n")
        else:
            console.print("  No untagged items found (or no matches).\n")


@app.command()
def library():
    """Show content library status breakdown."""
    with db.connection() as conn:
        # Status breakdown
        status_rows = conn.execute("""
            SELECT status, COUNT(*) as count FROM content_item GROUP BY status
        """).fetchall()
        status_counts = {r["status"]: r["count"] for r in status_rows}

        # Source breakdown
        source_rows = conn.execute("""
            SELECT
                CASE
                    WHEN source LIKE 'subtitle:%' THEN 'subtitle'
                    WHEN source LIKE 'csv:%' THEN 'csv'
                    WHEN source = 'manual' THEN 'manual'
                    WHEN source = 'seed' THEN 'seed'
                    ELSE COALESCE(source, 'unknown')
                END as source_group,
                COUNT(*) as count
            FROM content_item GROUP BY source_group
        """).fetchall()

        # HSK breakdown
        hsk_rows = conn.execute("""
            SELECT hsk_level, COUNT(*) as count FROM content_item
            GROUP BY hsk_level ORDER BY hsk_level
        """).fetchall()

        # Items needing enrichment
        raw_count = status_counts.get("raw", 0)
        enriched_count = status_counts.get("enriched", 0)
        ready_count = status_counts.get("drill_ready", 0)
        total = sum(status_counts.values())

        console.print()
        console.print("  漫 Aelu — Library", style="bold")
        console.print()

        status_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        status_table.add_column("Label", style="dim")
        status_table.add_column("Count", justify="right")
        status_table.add_row("Total items", str(total))
        status_table.add_row("  drill_ready", str(ready_count))
        status_table.add_row("  enriched", str(enriched_count))
        status_table.add_row("  raw", str(raw_count))
        console.print(status_table)

        if source_rows:
            src_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
            src_table.add_column("Source", style="dim")
            src_table.add_column("Count", justify="right")
            for r in source_rows:
                src_table.add_row(r['source_group'], str(r['count']))
            console.print(src_table)

        if hsk_rows:
            hsk_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
            hsk_table.add_column("HSK Level", style="dim")
            hsk_table.add_column("Count", justify="right")
            for r in hsk_rows:
                level = r["hsk_level"] if r["hsk_level"] is not None else "unset"
                hsk_table.add_row(f"HSK {level}", str(r['count']))
            console.print(hsk_table)

        if raw_count > 0:
            console.print()
            console.print(f"  {raw_count} items need enrichment (missing pinyin/english).")
            console.print("  Import a CSV with pinyin+english for the same hanzi to enrich them.")

        console.print()


# ── Information commands ──────────────────────────────

@app.command()
def guide():
    """Quick reference — what to run and when."""
    console.print()
    console.print("  漫 Aelu — Quick Guide", style="bold")
    console.print()

    guide_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    guide_table.add_column("Command", style="bold")
    guide_table.add_column("Description", style="dim")

    guide_table.add_row("[dim]── Everyday ──[/dim]", "")
    guide_table.add_row("mandarin", "Run today's session (default)")
    guide_table.add_row("mandarin mini", "Quick 5-item session")
    guide_table.add_row("mandarin status", "See where you stand")
    guide_table.add_row("", "")
    guide_table.add_row("[dim]── Go deeper ──[/dim]", "")
    guide_table.add_row("mandarin status -d", "Full mastery + retention breakdown")
    guide_table.add_row("mandarin forecast", "When you'll reach each HSK level")
    guide_table.add_row("mandarin assess", "Diagnose strengths and weaknesses")
    guide_table.add_row("mandarin focus X", "Boost a specific lens for 3 sessions")
    guide_table.add_row("", "")
    guide_table.add_row("[dim]── Customize ──[/dim]", "")
    guide_table.add_row("mandarin personalize", "Set preferred topics")
    guide_table.add_row("mandarin settings", "View/change session settings")
    guide_table.add_row("mandarin speak X", "Hear pronunciation for any hanzi")
    console.print(guide_table)

    console.print("  [dim]Shortcuts: s = session, m = mini, st = status, dx = diagnose, f = forecast, fo = focus[/dim]")
    console.print()


@app.command(name="media-check")
def media_check():
    """Validate all media shelf URLs for accessibility."""
    from .media import validate_media_urls
    console.print("\n  Checking media URLs...", style="dim")
    results = validate_media_urls(timeout=10)
    broken = [r for r in results if r["status"] != "ok"]
    ok_count = len(results) - len(broken)
    console.print(f"  {ok_count}/{len(results)} URLs accessible")
    if broken:
        console.print()
        for r in broken:
            console.print(f"  [{r['status']}] {r['id']}: {r.get('error', r.get('http_status', 'unknown'))}", style="yellow")
    else:
        console.print("  All media URLs are healthy.", style="green")
    console.print()


@app.command()
def status(
    detail: bool = typer.Option(False, "--detail", "-d", help="Show extended mastery, retention, and error details"),
):
    """Show current learning status."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        profile = db.get_profile(conn, user_id=user_id)
        total_sessions = profile.get("total_sessions", 0) or 0
        days_gap = db.get_days_since_last_session(conn, user_id=user_id)

        from .milestones import get_stage_counts, get_growth_summary
        from .diagnostics import get_speed_trend

        stages = get_stage_counts(conn)
        solid = stages["stable"] + stages["durable"]
        growing = stages["stabilizing"]
        early = stages["seen"] + stages["passed_once"]
        needs_review = stages["decayed"]
        seen_total = solid + growing + early + needs_review

        console.print()
        console.print("  漫 Aelu — Status", style="bold")

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

        # ── Accuracy sparkline ──
        sparkline_sessions = db.get_session_history(conn, limit=20, user_id=user_id)
        completed_sessions = [s for s in sparkline_sessions if (s.get("items_completed") or 0) > 0]
        if len(completed_sessions) >= 3:
            acc_values = [_session_accuracy_pct(s) for s in reversed(completed_sessions)]
            spark = _sparkline(acc_values)
            recent_5 = acc_values[-5:] if len(acc_values) >= 5 else acc_values
            older_5 = acc_values[-10:-5] if len(acc_values) >= 10 else []
            arrow = _trend_arrow(recent_5, older_5)
            console.print(f"  [dim]Accuracy trend:[/dim] [bold bright_cyan]{spark}[/bold bright_cyan]{arrow}  [dim](last {len(completed_sessions)} sessions)[/dim]")

        # ── Mastery by HSK level ──
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
            logger.debug("Retention stats unavailable for status: %s", e)

        # ── What you're building ──
        if growing > 0 or early > 0 or needs_review > 0:
            console.print()
            console.print("  [dim]── What you're building ──[/dim]")
            if stages["durable"] > 0:
                console.print(f"    {stages['durable']} items durable")
            if growing > 0:
                console.print(f"    {growing} items stabilizing — getting stronger with repetition")
            if stages["passed_once"] > 0:
                console.print(f"    {stages['passed_once']} items passed once")
            if stages["seen"] > 0:
                console.print(f"    {stages['seen']} items seen (not yet reliable)")
            if needs_review > 0:
                console.print(f"    {needs_review} items need review (were stable)")

        if not detail:
            console.print()
            console.print("  [dim]Use --detail / -d for full breakdown.[/dim]")

        # ── Secondary details (only with --detail) ──
        if detail:
            # Mastery breakdown by stage
            console.print()
            console.print("  [dim]── Mastery Breakdown ──[/dim]")
            mastery_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            mastery_table.add_column("Stage", min_width=14)
            mastery_table.add_column("Count", justify="right")
            from mandarin.display import STAGE_LABELS
            stage_keys = ["durable", "stable", "stabilizing", "passed_once", "seen", "decayed"]
            for key in stage_keys:
                count = stages.get(key, 0)
                if count > 0:
                    mastery_table.add_row(STAGE_LABELS.get(key, key.title()), str(count))
            unseen = stages.get("unseen", 0)
            if unseen > 0:
                mastery_table.add_row(STAGE_LABELS.get("not_seen", "New"), str(unseen))
            console.print(mastery_table)

            # Retention stats
            try:
                from .retention import compute_retention_stats
                ret = compute_retention_stats(conn)
                if ret["total_items"] >= 5:
                    console.print()
                    console.print("  [dim]── Retention Details ──[/dim]")
                    ret_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
                    ret_table.add_column("Metric", style="dim")
                    ret_table.add_column("Value", justify="right")
                    ret_table.add_row("Items tracked", str(ret['total_items']))
                    ret_table.add_row("Above threshold", f"{ret['retention_pct']:.0f}%")
                    ret_table.add_row("Avg recall", f"{ret['avg_recall']:.0%}")
                    ret_table.add_row("Avg half-life", f"{ret['avg_half_life']:.1f} days")
                    console.print(ret_table)
            except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
                logger.debug("Retention details unavailable: %s", e)

            # Recent errors
            errors = db.get_error_summary(conn, user_id=user_id)
            if errors:
                console.print()
                console.print("  [dim]── Recent Errors ──[/dim]")
                err_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
                err_table.add_column("Error Type", min_width=18)
                err_table.add_column("Count", justify="right")
                for etype, count in list(errors.items())[:6]:
                    err_table.add_row(etype, str(count))
                console.print(err_table)

            speed = get_speed_trend(conn)
            growth = get_growth_summary(conn)
            sessions_list = db.get_session_history(conn, limit=14, user_id=user_id)

            has_details = (speed["total_timed"] > 0 or growth["latest"]
                           or len(sessions_list) >= 4)

            if has_details:
                console.print()
                console.print("  [dim]── Details ──[/dim]")

                if speed["total_timed"] > 0:
                    console.print(f"    Speed: {speed['summary']}")

                if growth["latest"]:
                    console.print(f"    {growth['phase_label']}")
                    console.print(f"    ✦ {growth['latest']['label']}")

                if len(sessions_list) >= 4:
                    recent_acc = _avg_accuracy(sessions_list[:4])
                    older_acc = _avg_accuracy(sessions_list[4:8]) if len(sessions_list) >= 8 else None
                    completed = sum(1 for s in sessions_list if s.get("items_completed", 0) > 0)
                    cadence_val = round(completed / 2) if completed >= 2 else None
                    cadence_str = "7+" if cadence_val and cadence_val > 7 else str(cadence_val) if cadence_val else None
                    momentum = f"    Momentum: {completed} sessions in 2 weeks"
                    if cadence_str:
                        momentum += f" (~{cadence_str}x/week)"
                    if older_acc is not None:
                        if recent_acc > older_acc + 0.05:
                            momentum += " — trending up"
                        elif recent_acc < older_acc - 0.05:
                            momentum += " — needs attention"
                    console.print(momentum)

                # Consistency indicator (inter-session gap variance)
                if len(sessions_list) >= 4:
                    from datetime import date as dt_date
                    session_dates = []
                    for s in sessions_list:
                        if s.get("started_at"):
                            try:
                                session_dates.append(dt_date.fromisoformat(s["started_at"][:10]))
                            except (ValueError, TypeError):
                                pass
                    if len(session_dates) >= 3:
                        gaps = [(session_dates[i] - session_dates[i+1]).days
                                for i in range(len(session_dates) - 1)]
                        if gaps:
                            from statistics import mean, stdev
                            gap_mean = mean(gaps) if gaps else 1
                            if len(gaps) >= 2 and gap_mean > 0:
                                gap_std = stdev(gaps)
                                cv = gap_std / gap_mean
                                if cv < 0.5:
                                    console.print("    Consistent rhythm")
                                elif cv > 1.0:
                                    console.print("    Irregular — steadier pace helps retention")

        console.print()


def _avg_accuracy(sessions: list) -> float:
    total = sum(s.get("items_completed", 0) for s in sessions)
    correct = sum(s.get("items_correct", 0) for s in sessions)
    return correct / total if total > 0 else 0


@app.command()
def debug():
    """Show debug info: last session trace, drill errors, anomalies."""
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent / "data"
    errors_log = data_dir / "drill_errors.log"
    trace_log = data_dir / "session_trace.jsonl"

    console.print()

    # ── Drill errors ──
    if errors_log.exists() and errors_log.stat().st_size > 0:
        content = errors_log.read_text()
        # Count error blocks
        n_errors = content.count("=" * 60)
        console.print(f"  [bold red]Drill errors:[/] {n_errors} logged")
        # Show last error
        blocks = content.split("=" * 60)
        last = blocks[-1].strip() if blocks else ""
        if last:
            console.print(f"  [dim]Latest:[/]")
            for line in last.split("\n")[:8]:
                console.print(f"    {line}")
        console.print(f"  [dim]Full log: data/drill_errors.log[/]")
    else:
        console.print("  [green]No drill errors logged.[/]")

    console.print()

    # ── Session trace ──
    if trace_log.exists() and trace_log.stat().st_size > 0:
        lines = trace_log.read_text().strip().split("\n")
        # Find the last session
        events = []
        last_session_id = None
        for line in reversed(lines):
            try:
                e = json.loads(line)
                if last_session_id is None:
                    last_session_id = e.get("session")
                if e.get("session") == last_session_id:
                    events.append(e)
                else:
                    break
            except json.JSONDecodeError:
                continue
        events.reverse()

        if events:
            console.print(f"  [bold]Last session[/] (id={last_session_id}):")
            # Summary stats
            start_ev = next((e for e in events if e["event"] == "session_start"), None)
            end_ev = next((e for e in events if e["event"] == "session_end"), None)
            crashes = [e for e in events if e["event"] == "drill_crash"]
            skips = [e for e in events if e["event"] == "drill_skip"]
            pivots = [e for e in events if e["event"] == "struggle_pivot"]

            if start_ev:
                console.print(f"    Plan: {start_ev.get('n_drills', '?')} drills ({start_ev.get('session_type', '?')})")
            if end_ev:
                console.print(f"    Result: {end_ev.get('correct', '?')}/{end_ev.get('completed', '?')} correct, "
                              f"{end_ev.get('elapsed_s', '?')}s")
                if end_ev.get("early_exit"):
                    console.print("    [yellow]Early exit[/]")

            if crashes:
                console.print(f"    [bold red]Crashes: {len(crashes)}[/]")
                for c in crashes:
                    console.print(f"      {c.get('drill_type', '?')} on {c.get('hanzi', '?')}: {c.get('error', '?')[:80]}")
            if skips:
                console.print(f"    [yellow]Skips: {len(skips)}[/]")
            if pivots:
                console.print(f"    [yellow]Struggle pivot at accuracy {pivots[0].get('accuracy', '?')}[/]")

            # Per-drill breakdown
            drills = [e for e in events if e["event"] == "drill_done"]
            if drills:
                console.print(f"\n    [dim]Drill-by-drill:[/]")
                for d in drills:
                    mark = "✓" if d.get("correct") else "✗"
                    ms = d.get("ms", "")
                    ms_str = f" {ms}ms" if ms else ""
                    console.print(f"      {mark} {d.get('drill_type', '?'):18s} {d.get('hanzi', ''):6s}{ms_str}")

        console.print(f"\n  [dim]Full trace: data/session_trace.jsonl[/]")
    else:
        console.print("  [dim]No session trace yet. Run a session first.[/]")

    console.print()


@app.command()
def report():
    """Generate a full progress report."""
    with db.connection() as conn:
        from .reports import generate_status_report

        console.print()
        console.print(generate_status_report(conn))


@app.command()
def assess(
    full: bool = typer.Option(False, "--full", help="Run full assessment (requires ≥20 sessions)"),
):
    """Run a diagnostic assessment."""
    with db.connection() as conn:
        from .diagnostics import assess_quick, assess_full as do_assess_full

        if full:
            result = do_assess_full(conn)
        else:
            result = assess_quick(conn)

        if not result.get("ready"):
            console.print(f"\n  {result['message']}\n")
            return

        console.print()
        console.print("  漫 Aelu — Assessment", style="bold")
        console.print()

        # Levels
        from .diagnostics import format_confidence
        level_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        level_table.add_column("Modality", min_width=10)
        level_table.add_column("Level", justify="right")
        level_table.add_column("Confidence", style="dim")
        for mod, data in result["estimated_levels"].items():
            conf_str = format_confidence(data['confidence'], data.get('total_attempts', 0))
            level_table.add_row(mod, f"HSK {data['level']:.1f}", conf_str)
        console.print(level_table)

        # Bottlenecks
        if result.get("bottlenecks"):
            console.print()
            console.print("  Top Bottlenecks:")
            for i, b in enumerate(result["bottlenecks"], 1):
                console.print(f"\n  {i}. {b['area']} [{b['severity']}]")
                console.print(f"     {b['data']}")
                console.print(f"     Do: {b['action']}")
                console.print(f"     Test: {b['test']}")

        # Projections
        if result.get("projections"):
            console.print()
            proj_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Projections (at current pace)", title_style="")
            proj_table.add_column("From", justify="right")
            proj_table.add_column("To", justify="right")
            proj_table.add_column("Timeline")
            proj_table.add_column("Confidence", style="dim")
            for p in result["projections"]:
                proj_table.add_row(
                    f"HSK {p['current']:.1f}",
                    f"HSK {p['target']:.0f}",
                    p['calendar'],
                    p['confidence'],
                )
            console.print(proj_table)

        # Full assessment extras
        if result.get("is_full"):
            if result.get("error_trends"):
                console.print()
                et_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Error Trends", title_style="")
                et_table.add_column("Type")
                et_table.add_column("Direction")
                et_table.add_column("Older", justify="right")
                et_table.add_column("Recent", justify="right")
                for etype, trend in result["error_trends"].items():
                    et_table.add_row(etype, trend['direction'], str(trend['older']), str(trend['recent']))
                console.print(et_table)

            if result.get("core_coverage"):
                console.print()
                cov_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Core Domain Coverage", title_style="")
                cov_table.add_column("Domain")
                cov_table.add_column("Coverage", justify="right")
                cov_table.add_column("Seen/Total", justify="right")
                cov_table.add_column("Status")
                for lens, cov in result["core_coverage"].items():
                    cov_status = "[yellow]needs focus[/yellow]" if cov["needs_attention"] else "[green]OK[/green]"
                    cov_table.add_row(lens, f"{cov['coverage_pct']:.0f}%", f"{cov['seen']}/{cov['total']}", cov_status)
                console.print(cov_table)

        console.print()


@app.command()
def calibrate():
    """Run a calibration session to estimate your level across modalities."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        if db.content_count(conn) < 20:
            console.print("\n  Need at least 20 items in library to calibrate.")
            console.print("  Run: mandarin add-hsk 1\n")
            return

        from .diagnostics import plan_calibrate_session, update_calibration_levels

        console.print()
        console.print("  漫 Aelu — Calibration", style="bold")
        console.print()

        plan = plan_calibrate_session(conn)
        if not plan.drills:
            console.print("  Not enough drill-ready items to calibrate.")
            return

        state = run_session(conn, plan, _show, _input)

        # Update levels from calibration results
        if state.items_completed >= 5:
            update_calibration_levels(conn, state.results)
            console.print("  Level estimates updated from calibration.\n")

            profile = db.get_profile(conn, user_id=user_id)
            cal_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
            cal_table.add_column("Modality", min_width=10)
            cal_table.add_column("Level", justify="right")
            cal_table.add_column("Confidence", justify="right", style="dim")
            for mod in ["reading", "listening", "ime"]:
                level = profile.get(f"level_{mod}", 1.0)
                conf = profile.get(f"confidence_{mod}", 0.0)
                cal_table.add_row(mod, f"HSK {level:.1f}", f"{conf:.0%}")
            console.print(cal_table)
        else:
            console.print("  Too few items completed to update levels.\n")


@app.command()
def goal():
    """Show your north star readiness score and what to focus on."""
    with db.connection() as conn:
        from .diagnostics import compute_readiness
        from .milestones import get_growth_summary

        readiness = compute_readiness(conn)
        growth = get_growth_summary(conn)

        console.print()
        console.print("  漫 Aelu — Goal", style="bold")
        console.print()

        # Readiness score
        score = readiness["score"]
        bar_len = 20
        filled = round(score / 100 * bar_len)
        bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
        console.print(f"  Readiness:  {bar}  {score:.0f}%  ({readiness['label']})")
        console.print()

        # Components
        labels = {
            "scenario_mastery": "Scenarios",
            "item_stability": "Stability",
            "modality_breadth": "Breadth",
            "practice_consistency": "Consistency",
        }
        comp_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        comp_table.add_column("Component", min_width=12)
        comp_table.add_column("Bar")
        comp_table.add_column("Score", justify="right")
        comp_table.add_column("Detail", style="dim")
        for key in ["scenario_mastery", "item_stability", "modality_breadth", "practice_consistency"]:
            comp = readiness["components"][key]
            c_filled = round(comp["score"] / 100 * 10)
            c_bar = "\u2588" * c_filled + "\u2591" * (10 - c_filled)
            comp_table.add_row(labels[key], c_bar, f"{comp['score']:.0f}%", comp['detail'])
        console.print(comp_table)

        # Current milestone
        if growth["latest"]:
            console.print()
            console.print(f"  {growth['phase_label']}")
            console.print(f"  \u2726 {growth['latest']['label']}")
            if growth["next"]:
                console.print(f"    Next: {growth['next']['label']}")

        # Ambiguity comfort
        from .diagnostics import compute_ambiguity_comfort
        comfort = compute_ambiguity_comfort(conn)
        if comfort["total_attempts"] > 0:
            console.print()
            console.print(f"  Ambiguity comfort: {comfort['comfort_label']}")
            console.print(f"    {comfort['summary']}")

        # Focus recommendation
        console.print()
        console.print(f"  Focus: {readiness['focus']}")

        console.print()


@app.command()
def forecast():
    """Show learning projections and milestones."""
    with db.connection() as conn:
        from .diagnostics import project_forecast, format_confidence

        fc = project_forecast(conn)
        pace = fc["pace"]

        console.print()
        console.print("  漫 Aelu — Forecast", style="bold")
        console.print()

        # Pace line
        console.print(f"  Current pace: {pace['message']}")
        console.print()

        if not pace["reliable"]:
            # Low session count — frame as building baseline, not showing flat numbers
            total = fc.get("total_sessions", 0)
            remaining = max(0, 8 - total)
            if total == 0:
                console.print("  No sessions yet — levels will appear as you practice.")
            elif total < 3:
                console.print(f"  {total} sessions completed. Levels firm up after a few more.")
            else:
                console.print(f"  Building baseline — {remaining} more sessions for projections.")
            console.print()
            # Show levels but frame them as estimates-in-progress
            console.print("  [dim]Estimated levels (will stabilize with more data):[/dim]")
            fc_est_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            fc_est_table.add_column("Modality", min_width=10)
            fc_est_table.add_column("Level", justify="right")
            fc_est_table.add_column("Detail", style="dim")
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
                fc_est_table.add_row(mod, f"HSK {data['level']:.1f}", detail)
            console.print(fc_est_table)
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


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of sessions to show"),
):
    """Show recent session history."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        sessions = db.get_session_history(conn, limit=limit, user_id=user_id)

        console.print()
        console.print("  Recent sessions:", style="bold")
        console.print()

        if not sessions:
            console.print("  No sessions yet.")
            console.print()
            return

        hist_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        hist_table.add_column("Date")
        hist_table.add_column("Type")
        hist_table.add_column("Score", justify="right")
        hist_table.add_column("Duration", justify="right", style="dim")
        hist_table.add_column("Notes", style="dim")
        for s in sessions:
            d = s["started_at"][:10]
            completed = s["items_completed"]
            correct = s["items_correct"]
            stype = s["session_type"]
            duration = s.get("duration_seconds")
            dur_str = f"{duration // 60}m{duration % 60:02d}s" if duration else ""

            accuracy = f"{correct}/{completed}" if completed else "\u2014"
            gap = s.get("days_since_last_session")
            notes_parts = []
            if gap and gap >= 3:
                notes_parts.append(f"gap: {gap}d")
            if s.get("early_exit"):
                notes_parts.append("early")
            if s.get("boredom_flags"):
                notes_parts.append(f"B\u00d7{s['boredom_flags']}")
            notes_str = ", ".join(notes_parts)

            hist_table.add_row(d, stype, accuracy, dur_str, notes_str)

        console.print(hist_table)


# ── Self-improvement commands ──────────────────────────────

@app.command(name="improve")
def improve_cmd(
    apply_id: int = typer.Option(None, "--apply", help="Apply a proposal by ID"),
    rollback_id: int = typer.Option(None, "--rollback", help="Rollback a proposal by ID"),
):
    """Detect patterns and propose system improvements."""
    with db.connection() as conn:
        from .improve import detect_patterns, save_proposal, get_proposals, apply_proposal, rollback_proposal

        if apply_id is not None:
            apply_proposal(conn, apply_id)
            console.print(f"\n  Applied proposal #{apply_id}.\n")
            return

        if rollback_id is not None:
            rollback_proposal(conn, rollback_id)
            console.print(f"\n  Rolled back proposal #{rollback_id}.\n")
            return

        # Detect new patterns
        proposals = detect_patterns(conn)

        if not proposals:
            # Check for existing proposals
            existing = get_proposals(conn, status="proposed")
            if existing:
                console.print("\n  Existing proposals:")
                for p in existing:
                    console.print(f"    #{p['id']}: {p['observation'][:80]}")
                console.print(f"\n  Use --apply <id> or --rollback <id> to manage.")
            else:
                console.print("\n  No improvement patterns detected. System looks good.")
            console.print()
            return

        console.print()
        console.print("  漫 Aelu — System Improvement Proposals", style="bold")
        console.print()

        for p in proposals:
            save_proposal(conn, p)
            console.print(f"  [{p['severity'].upper()}] {p['observation']}")
            console.print(f"  Why: {p['why_it_matters']}")
            console.print(f"  Change: {p['proposed_change']}")
            console.print(f"  Test: {p['expected_benefit']}")
            console.print(f"  Rollback: {p['rollback']}")
            console.print()

        console.print("  These are proposals only — no changes made.")
        console.print("  Use: mandarin improve --apply <id> to accept a proposal.")
        console.print()


# ── Export commands ──────────────────────────────

@app.command(name="export")
def export_cmd(
    export_type: str = typer.Option("progress", "--type", "-t", help="Export type: progress, sessions, or errors"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
):
    """Export data as CSV (progress, sessions, or errors)."""
    from .export import (
        export_progress_csv, export_sessions_csv, export_errors_csv,
        to_csv_string,
    )

    exporters = {
        "progress": export_progress_csv,
        "sessions": export_sessions_csv,
        "errors": export_errors_csv,
    }
    exporter = exporters.get(export_type)
    if not exporter:
        console.print(f"\n  Unknown export type: {export_type}")
        console.print("  Available: progress, sessions, errors\n")
        return

    with db.connection() as conn:
        header, data = exporter(conn)

    csv_text = to_csv_string(header, data)
    if output:
        with open(output, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        console.print(f"\n  Exported {len(data)} rows to {output}\n")
    else:
        sys.stdout.write(csv_text)


# ── Utility commands ──────────────────────────────

@app.command()
def errors(
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """Show recent error details."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT el.*, ci.hanzi, ci.pinyin, ci.english
            FROM error_log el
            JOIN content_item ci ON el.content_item_id = ci.id
            ORDER BY el.created_at DESC LIMIT ?
        """, (limit,)).fetchall()

        console.print()
        if not rows:
            console.print("  No errors recorded yet.")
            console.print()
            return

        console.print("  Recent errors:", style="bold")
        console.print()
        err_detail_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        err_detail_table.add_column("Type")
        err_detail_table.add_column("Item", style="bright_cyan")
        err_detail_table.add_column("Pinyin", style="dim")
        err_detail_table.add_column("You said")
        err_detail_table.add_column("Expected")
        err_detail_table.add_column("Drill", style="dim")
        for r in rows:
            r = dict(r)
            err_detail_table.add_row(
                r['error_type'],
                r['hanzi'],
                r['pinyin'],
                r['user_answer'] or "\u2014",
                r['expected_answer'] or "\u2014",
                r['drill_type'],
            )
        console.print(err_detail_table)


@app.command(name="import-scenarios")
def import_scenarios(
    dir_path: str = typer.Argument(..., help="Path to directory of scenario JSON files"),
):
    """Import dialogue scenarios from a directory."""
    with db.connection() as conn:
        from .scenario_loader import load_scenario_dir

        try:
            added, skipped, updated = load_scenario_dir(conn, dir_path)
            console.print(f"\n  Loaded {added} scenarios ({skipped} skipped).\n")
        except FileNotFoundError as e:
            console.print(f"\n  {e}\n")


@app.command(name="update-scenarios")
def update_scenarios(
    dir_path: str = typer.Argument(..., help="Path to directory of scenario JSON files"),
):
    """Update existing scenarios with new data (preserves stats)."""
    with db.connection() as conn:
        from .scenario_loader import load_scenario_dir

        try:
            added, skipped, updated = load_scenario_dir(conn, dir_path, update_existing=True)
            console.print(f"\n  Updated {updated} scenarios, added {added} new ({skipped} unchanged).\n")
        except FileNotFoundError as e:
            console.print(f"\n  {e}\n")


@app.command()
def scenarios():
    """List available dialogue scenarios."""
    with db.connection() as conn:
        from .scenario_loader import get_available_scenarios

        rows = get_available_scenarios(conn, hsk_max=9, limit=50)
        console.print()
        if not rows:
            console.print("  No scenarios loaded.")
            console.print("  Run: mandarin import-scenarios data/scenarios/")
            console.print()
            return

        console.print("  漫 Aelu — Dialogue Scenarios", style="bold")
        console.print()
        sc_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        sc_table.add_column("ID", justify="right")
        sc_table.add_column("HSK", justify="right")
        sc_table.add_column("Title")
        sc_table.add_column("Register", style="dim")
        sc_table.add_column("Played", justify="right")
        sc_table.add_column("Avg", justify="right", style="dim")
        for s in rows:
            score_str = f"{s['avg_score']:.0%}" if s.get("avg_score") is not None else ""
            sc_table.add_row(
                str(s['id']),
                str(s['hsk_level']),
                s['title'],
                s['register'],
                f"{s['times_presented']}x",
                score_str,
            )
        console.print(sc_table)


@app.command()
def grammar():
    """Show grammar points in the system."""
    with db.connection() as conn:
        rows = db.get_grammar_points(conn, hsk_max=9)

        console.print()
        if not rows:
            console.print("  No grammar points loaded.")
            console.print("  Run: mandarin seed-grammar")
            console.print()
            return

        console.print("  Grammar Points", style="bold")
        console.print()
        gram_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        gram_table.add_column("HSK", justify="right")
        gram_table.add_column("Category", style="dim")
        gram_table.add_column("Name")
        gram_table.add_column("Description", style="dim")
        for r in rows:
            gram_table.add_row(
                str(r['hsk_level']),
                r['category'],
                r['name'],
                r.get('description') or "",
            )
        console.print(gram_table)


@app.command()
def skills():
    """Show tracked language skills."""
    with db.connection() as conn:
        coverage = db.get_skill_coverage(conn)
        all_skills = db.get_skills(conn)

        console.print()
        if not all_skills:
            console.print("  No skills loaded.")
            console.print("  Run: mandarin seed-grammar")
            console.print()
            return

        console.print("  Language Skills", style="bold")
        console.print()
        skill_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        skill_table.add_column("HSK", justify="right")
        skill_table.add_column("Category", style="dim")
        skill_table.add_column("Name")
        for s in all_skills:
            skill_table.add_row(str(s['hsk_level']), s['category'], s['name'])
        console.print(skill_table)

        if coverage:
            console.print()
            cov_sk_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Coverage by category", title_style="")
            cov_sk_table.add_column("Category", min_width=10)
            cov_sk_table.add_column("Bar")
            cov_sk_table.add_column("Practiced", justify="right")
            cov_sk_table.add_column("Pct", justify="right")
            for c in coverage:
                pct = c["pct"]
                bar_len = 15
                filled = round(pct / 100 * bar_len)
                bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
                cov_sk_table.add_row(c['category'], bar, f"{c['practiced']}/{c['total_skills']}", f"{pct:.0f}%")
            console.print(cov_sk_table)

        console.print()


@app.command(name="seed")
def seed():
    """Idempotently seed all reference data: HSK vocabulary (1-9) and grammar points.

    Safe to run multiple times — existing rows are skipped. Runs automatically
    on every Fly.io deploy via the release_command in fly.toml, ensuring
    production and local dev stay in sync on reference data.
    """
    from .importer import import_hsk_level
    from .grammar_seed import seed_grammar_and_skills

    console.print()
    console.print("  [bold]Seeding reference data…[/bold]")
    console.print()

    with db.connection() as conn:
        # ── 1. Grammar points + skills ──────────────────────────────────
        # Note: link_all() is intentionally omitted here — it does O(n×m)
        # substring matching across all content items and takes too long for
        # a release command.  Run `mandarin seed-grammar` on-demand to populate
        # content_grammar / content_skill links.
        added_g, added_s = seed_grammar_and_skills(conn)
        console.print(f"  Grammar:   +{added_g} points, +{added_s} skills")

        # ── 2. HSK vocabulary, levels 1-9 ───────────────────────────────
        total_added = 0
        total_skipped = 0
        for level in range(1, 10):
            try:
                added, skipped = import_hsk_level(conn, level)
                if added > 0:
                    console.print(f"  HSK {level}:    +{added} items  ({skipped} already present)")
                total_added += added
                total_skipped += skipped
            except FileNotFoundError:
                console.print(f"  HSK {level}:    [dim]data file not found — skipping[/dim]")

        console.print(
            f"  Vocab:     +{total_added} new  /  {total_skipped} already present"
        )

    console.print()
    console.print("  [dim]Seed complete.[/dim]")
    console.print()


@app.command(name="seed-grammar")
def seed_grammar():
    """Load built-in grammar points and language skills, then auto-link to content."""
    with db.connection() as conn:
        from .grammar_seed import seed_grammar_and_skills
        from .grammar_linker import link_all
        added_g, added_s = seed_grammar_and_skills(conn)
        console.print(f"\n  Loaded {added_g} grammar points, {added_s} skills.")
        g_links, s_links = link_all(conn)
        console.print(f"  Linked {g_links} grammar→content, {s_links} skill→content.\n")


@app.command(name="import-cedict")
def import_cedict():
    """Download CC-CEDICT and import into dictionary_entry + rag_knowledge_base.

    Downloads the latest CC-CEDICT release directly from cc-cedict.org,
    extracts it to a temp file, and runs import_cc_cedict(). Safe to re-run —
    existing entries are skipped. Typical runtime: 2-3 minutes.
    """
    import gzip
    import shutil
    import tempfile
    import urllib.request

    CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"

    console.print()
    console.print("  [bold]Importing CC-CEDICT…[/bold]")
    console.print(f"  Downloading from {CEDICT_URL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        gz_path = f"{tmpdir}/cedict.txt.gz"
        txt_path = f"{tmpdir}/cedict.txt"

        try:
            urllib.request.urlretrieve(CEDICT_URL, gz_path)
        except Exception as e:
            console.print(f"  [red]Download failed: {e}[/red]")
            raise SystemExit(1)

        with gzip.open(gz_path, "rb") as f_in, open(txt_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        console.print("  Download complete. Importing…")

        from .ai.rag_layer import import_cc_cedict
        with db.connection() as conn:
            result = import_cc_cedict(conn, txt_path)

        if "error" in result:
            console.print(f"  [red]Import error: {result['error']}[/red]")
            raise SystemExit(1)

        added = result.get("added", 0)
        skipped = result.get("skipped", 0)
        console.print(f"  Added {added:,} entries, skipped {skipped:,} already present.")

    console.print()
    console.print("  [dim]CC-CEDICT import complete.[/dim]")
    console.print()


@app.command()
def settings(
    audio: str = typer.Option(None, help="Audio playback: on/off"),
):
    """View or change system settings."""
    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        profile = db.get_profile(conn, user_id=user_id)

        if audio is not None:
            val = 1 if audio.lower() in ("on", "true", "1", "yes") else 0
            conn.execute("UPDATE learner_profile SET audio_enabled = ? WHERE user_id = ?", (val, user_id))
            conn.commit()
            console.print(f"\n  Audio: {'on' if val else 'off'}\n")
        else:
            # Show current settings
            from .audio import is_audio_available
            console.print()
            settings_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            settings_table.add_column("Setting", style="dim")
            settings_table.add_column("Value")
            settings_table.add_row("Audio", 'on' if profile.get('audio_enabled', 1) else 'off')
            settings_table.add_row("Session length", f"{profile.get('preferred_session_length', 12)} items")
            settings_table.add_row("Sessions/week", str(profile.get('target_sessions_per_week', 4)))
            settings_table.add_row("TTS available", 'yes' if is_audio_available() else 'no')
            console.print(settings_table)


@app.command()
def focus(
    lens: str = typer.Argument(..., help="Content lens to focus on (e.g., food, travel, comedy)"),
    sessions: int = typer.Option(3, "--sessions", "-n", help="Number of sessions to boost"),
):
    """Temporarily boost a content lens for upcoming sessions."""
    with db.connection() as conn:
        valid_lenses = [
            "quiet_observation", "institutions", "urban_texture",
            "humane_mystery", "identity", "comedy", "food", "travel",
        ]
        if lens not in valid_lenses:
            console.print(f"\n  Unknown lens: {lens}")
            console.print(f"  Available: {', '.join(valid_lenses)}\n")
            return

        user_id = get_cli_user_id() or 1
        # Safe: lens is validated against valid_lenses whitelist above
        col = f"lens_{lens}"
        conn.execute(
            f"UPDATE learner_profile SET {col} = MIN(1.0, {col} + 0.3) WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        console.print(f"\n  Boosted '{lens}' lens for upcoming sessions.")
        console.print(f"  Content from this area will appear more frequently.\n")


@app.command()
def personalize(
    domain: str = typer.Argument(None, help="Domain to set: civic, governance, urbanism, travel, culture"),
    clear: bool = typer.Option(False, "--clear", help="Clear preferred domains"),
):
    """View or set preferred interest domains for personalized content."""
    with db.connection() as conn:
        from .personalization import INTEREST_DOMAINS, get_available_domains, get_domain_stats

        user_id = get_cli_user_id() or 1
        if clear:
            conn.execute("UPDATE learner_profile SET preferred_domains = '' WHERE user_id = ?", (user_id,))
            conn.commit()
            console.print("\n  Preferred domains cleared.\n")
            return

        if domain is not None:
            if domain not in INTEREST_DOMAINS:
                console.print(f"\n  Unknown domain: {domain}")
                console.print(f"  Available: {', '.join(INTEREST_DOMAINS.keys())}\n")
                return

            profile = db.get_profile(conn, user_id=user_id)
            current = (profile.get("preferred_domains") or "").strip()
            current_list = [d.strip() for d in current.split(",") if d.strip()]
            if domain not in current_list:
                current_list.append(domain)
            new_val = ",".join(current_list)
            conn.execute("UPDATE learner_profile SET preferred_domains = ? WHERE user_id = ?", (new_val, user_id))
            conn.commit()
            console.print(f"\n  Added domain: {INTEREST_DOMAINS[domain]['label']}")
            console.print(f"  Active domains: {new_val}\n")
            return

        # Show current state
        profile = db.get_profile(conn, user_id=user_id)
        current = (profile.get("preferred_domains") or "").strip()
        available = get_available_domains()
        stats = get_domain_stats()

        console.print()
        console.print("  Personalization Domains", style="bold")
        console.print()

        if current:
            console.print(f"  Active: {current}")
        else:
            console.print("  No domains set. Use: mandarin personalize <domain>")
        console.print()

        domain_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        domain_table.add_column("")
        domain_table.add_column("Domain")
        domain_table.add_column("Label")
        domain_table.add_column("Data", style="dim")
        for domain_key, meta in INTEREST_DOMAINS.items():
            has_data = domain_key in available
            count = stats.get(domain_key, {}).get("total", 0)
            marker = "[green]\u25cf[/green]" if domain_key in (current or "").split(",") else "\u25cb"
            data_str = f"{count} sentences" if has_data else "no data"
            domain_table.add_row(marker, domain_key, meta['label'], data_str)
        console.print(domain_table)


@app.command()
def speak():
    """Run a speaking practice session (voice tone grading)."""
    with db.connection() as conn:
        if db.content_count(conn) == 0:
            console.print("\n  [dim]No content loaded. Run: mandarin add-hsk 1[/dim]\n")
            return

        from .tone_grading import is_recording_available
        if not is_recording_available():
            console.print("\n  Microphone not available.")
            console.print("  Speaking drills require sounddevice + a working mic.")
            console.print("  Install: pip install sounddevice numpy\n")
            return

        from .scheduler import plan_speaking_session
        console.print()
        console.print("  漫 Aelu — Speaking Practice", style="bold")
        console.print()

        plan = plan_speaking_session(conn)
        if not plan.drills:
            console.print("  No items available for speaking practice.")
            return

        run_session(conn, plan, _show, _input)


@app.command()
def listen(
    count: int = typer.Option(20, "--count", "-n", help="Number of items to hear"),
    hsk: int = typer.Option(9, "--hsk", help="Max HSK level (1-9)"),
    pace: str = typer.Option("normal", "--pace", help="slow / normal / fast"),
):
    """Passive listening — hear vocabulary with TTS. No quizzing, just absorb.

    Plays through items: hear the Chinese, see hanzi + pinyin + english.
    Press Enter to continue, Q to quit. Pure immersion.
    """
    from .audio import speak_and_wait, is_audio_available
    import time as _time

    if not is_audio_available():
        console.print("\n  Audio not available (needs macOS with Tingting voice).")
        console.print("  Install: System Settings → Accessibility → Spoken Content → Manage Voices\n")
        return

    with db.connection() as conn:
        # Get items: mix of due-for-review and recent
        items = conn.execute("""
            SELECT ci.hanzi, ci.pinyin, ci.english, ci.hsk_level, ci.context_note,
                   p.mastery_stage, p.total_attempts
            FROM content_item ci
            LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = 'reading'
            WHERE ci.status = 'drill_ready'
              AND (ci.hsk_level IS NULL OR ci.hsk_level <= ?)
            ORDER BY
                CASE WHEN p.total_attempts > 0 THEN 0 ELSE 1 END,
                RANDOM()
            LIMIT ?
        """, (hsk, count)).fetchall()

        if not items:
            console.print("\n  No items to listen to.\n")
            return

    rate_map = {"slow": 120, "normal": 160, "fast": 200}
    tts_rate = rate_map.get(pace, 160)
    pause = {"slow": 2.5, "normal": 1.5, "fast": 0.8}.get(pace, 1.5)

    console.print()
    console.print("  漫 Aelu — Passive Listening", style="bold")
    console.print(f"  {len(items)} items · HSK ≤{hsk} · {pace} pace")
    console.print("  Just listen and absorb. Enter = next, Q = quit.")
    console.print()

    for i, item in enumerate(items):
        item = dict(item)
        hanzi = item["hanzi"]
        pinyin = item["pinyin"]
        english = item["english"]
        item.get("hsk_level") or "?"
        context = item.get("context_note")

        # Show item number
        console.print(f"  [{i+1}/{len(items)}]  [bright_cyan]{hanzi}[/bright_cyan]")

        # Play audio
        speak_and_wait(hanzi, rate=tts_rate)
        _time.sleep(pause)

        # Show details after hearing
        console.print(f"          {pinyin}  —  {english}")
        if context:
            console.print(f"          [dim italic]{context}[/dim italic]")

        # Wait for input
        try:
            response = console.input("  ").strip().upper()
            if response == "Q":
                break
        except (KeyboardInterrupt, EOFError):
            break

    console.print(f"\n  Heard {min(i+1, len(items))} items. Every bit helps.\n")


@app.command("app")
def web_app(
    port: int = typer.Option(None, "--port", "-p", help="Port to run on"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't auto-open browser"),
):
    """Launch the web interface in your browser."""
    from .web import create_app
    from .settings import PORT as _env_port, DEFAULT_PORT
    import webbrowser
    import threading

    port = port or _env_port or DEFAULT_PORT
    flask_app = create_app()
    url = f"http://localhost:{port}"

    if not no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    console.print(f"\n  漫 Aelu — Web UI at {url}")
    console.print("  Press Ctrl+C to stop.\n")

    flask_app.run(host="127.0.0.1", port=port, debug=False)


@app.command("hsk-reqs")
def hsk_reqs(
    level: int = typer.Argument(..., help="HSK level (1-9)"),
):
    """Show HSK requirements for a given level."""
    from .diagnostics import get_hsk_requirements
    reqs = get_hsk_requirements(level)

    if not reqs:
        console.print(f"\n  No requirements data for HSK {level}.\n")
        return

    console.print()
    console.print(f"  HSK {level} Requirements", style="bold")
    console.print()

    console.print(f"  Vocabulary: {reqs.get('vocab_count', '?')} words")

    grammar = reqs.get("grammar", [])
    if grammar:
        console.print()
        console.print("  Grammar:")
        for g in grammar:
            console.print(f"    • {g}")

    skills = reqs.get("skills", [])
    if skills:
        console.print()
        console.print("  Skills:")
        for s in skills:
            console.print(f"    • {s}")

    for modality in ["listening", "reading", "speaking"]:
        mod_data = reqs.get(modality, {})
        if mod_data:
            desc = mod_data.get("description", "")
            target = mod_data.get("accuracy_target")
            target_str = f" (target: {target:.0%})" if target else ""
            console.print(f"\n  {modality.title()}: {desc}{target_str}")

    console.print()


@app.command("seed-context")
def seed_context():
    """Load culturally rich context notes for seed vocabulary."""
    with db.connection() as conn:
        from .context_notes import CONTEXT_NOTES
        updated = db.seed_context_notes(conn, CONTEXT_NOTES)
        console.print(f"\n  Updated {updated} items with context notes.\n")


@app.command()
def portfolio():
    """Show your mastered vocabulary as a character wall."""
    with db.connection() as conn:
        from .milestones import get_stage_counts, get_growth_summary

        stages = get_stage_counts(conn)
        growth = get_growth_summary(conn)

        console.print()
        console.print("  漫 Aelu — Portfolio", style="bold")
        console.print(f"  [dim]{growth['phase_label']}[/dim]")
        console.print()

        # Stage summary
        console.print(f"  [green]{stages['durable']} durable[/green] · "
                      f"[green]{stages['stable']} stable[/green] · "
                      f"[yellow]{stages['stabilizing']} stabilizing[/yellow] · "
                      f"[dim]{stages['passed_once'] + stages['seen']} early[/dim] · "
                      f"[dim]{stages.get('unseen', 0)} unseen[/dim]")
        console.print()

        # Character wall: stable + durable items grouped by HSK level
        rows = conn.execute("""
            SELECT ci.hanzi, ci.hsk_level, p.mastery_stage
            FROM content_item ci
            JOIN progress p ON ci.id = p.content_item_id
            WHERE p.mastery_stage IN ('stable', 'durable')
              AND ci.status = 'drill_ready'
            ORDER BY ci.hsk_level, ci.hanzi
        """).fetchall()

        if not rows:
            console.print("  No stable items yet. Keep practicing — they'll appear here.")
            console.print()
            return

        # Group by HSK level
        by_level = {}
        for r in rows:
            level = r["hsk_level"] or 1
            by_level.setdefault(level, []).append(r)

        for level in sorted(by_level.keys()):
            items = by_level[level]
            durable = [r["hanzi"] for r in items if r["mastery_stage"] == "durable"]
            stable = [r["hanzi"] for r in items if r["mastery_stage"] == "stable"]

            console.print(f"  [dim]── HSK {level} ({len(items)} items) ──[/dim]")
            if durable:
                # Wrap at ~60 chars
                wall = " ".join(durable)
                console.print(f"    [bold green]{wall}[/bold green]")
            if stable:
                wall = " ".join(stable)
                console.print(f"    [green]{wall}[/green]")
            console.print()

        # Unlocked milestones
        if growth["unlocked"]:
            console.print("  [dim]── Milestones ──[/dim]")
            for m in growth["unlocked"]:
                console.print(f"    ✦ {m['label']}")
            console.print()

        # Next milestone
        if growth["next"]:
            console.print(f"  [dim]Next: {growth['next']['label']}[/dim]")
            console.print()


@app.command("seed-constructions")
def seed_constructions_cmd():
    """Seed grammatical construction patterns and link to content items."""
    with db.connection() as conn:
        inserted = db.seed_constructions(conn)
        row = conn.execute("SELECT COUNT(*) FROM construction").fetchone()
        total = row[0] if row else 0
        row = conn.execute("SELECT COUNT(*) FROM content_construction").fetchone()
        linked = row[0] if row else 0
        console.print(f"\n  {inserted} new constructions added ({total} total, {linked} item links).\n")


@app.command("tone-analysis")
def tone_analysis():
    """Show tone confusion matrix and perceptual patterns."""
    with db.connection() as conn:
        from .diagnostics import get_tone_confusion_matrix
        result = get_tone_confusion_matrix(conn)

        console.print()
        console.print("  Tone Confusion Analysis", style="bold")
        console.print()

        if result["total_tone_errors"] == 0:
            console.print("  No tone errors recorded yet.")
            console.print()
            return

        console.print(f"  {result['summary']}")
        console.print(f"  Total confused: {result['total_tone_errors']}")
        console.print()

        if result["top_confusions"]:
            tc_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Top confusions", title_style="")
            tc_table.add_column("Expected")
            tc_table.add_column("Heard as")
            tc_table.add_column("Count", justify="right")
            for expected, guessed, count in result["top_confusions"]:
                tc_table.add_row(f"Tone {expected}", f"Tone {guessed}", f"{count}x")
            console.print(tc_table)

        # Show matrix
        console.print()
        mx_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Confusion matrix (expected \u2192 guessed)", title_style="")
        mx_table.add_column("", style="bold")
        for t in range(1, 6):
            mx_table.add_column(f"T{t}", justify="right")
        for expected in range(1, 6):
            cells = []
            for guessed in range(1, 6):
                val = result["matrix"][expected][guessed]
                if expected == guessed:
                    cells.append("[dim]\u00b7[/dim]")
                elif val > 0:
                    cells.append(str(val))
                else:
                    cells.append("[dim]\u2014[/dim]")
            mx_table.add_row(f"T{expected}", *cells)
        console.print(mx_table)


@app.command("speed")
def speed_analysis():
    """Show response time / processing speed analysis."""
    with db.connection() as conn:
        from .diagnostics import get_speed_trend
        result = get_speed_trend(conn)

        console.print()
        console.print("  Processing Speed", style="bold")
        console.print()

        if result["total_timed"] == 0:
            console.print("  No response time data yet. Complete a session first.")
            console.print()
            return

        console.print(f"  {result['summary']}")
        console.print(f"  Items tracked: {result['total_timed']}")
        console.print(f"  Fast (<3s): {result['fast_count']}  |  Slow (>8s): {result['slow_count']}")

        if result["by_hsk"]:
            console.print()
            spd_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), title="Average by HSK level", title_style="")
            spd_table.add_column("HSK", justify="right")
            spd_table.add_column("Time", justify="right")
            spd_table.add_column("Bar")
            for level, avg in sorted(result["by_hsk"].items()):
                bar_char = "\u258a" if avg < 4000 else "\u258b" if avg < 7000 else "\u258e"
                secs = avg / 1000
                spd_table.add_row(str(level), f"{secs:.1f}s", bar_char * min(20, int(secs * 2)))
            console.print(spd_table)


@app.command(name="validate-hsk")
def validate_hsk(
    level: int = typer.Argument(None, help="HSK level (1-9), or omit for all"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show missing/extra items"),
):
    """Validate DB vocabulary against canonical HSK 3.0 word lists."""
    from .validator import validate_all, validate_level

    with db.connection() as conn:
        if level:
            result = validate_all(conn, levels=[level])
        else:
            result = validate_all(conn)

    summary = result["summary"]
    console.print()
    console.print(f"  [bold]HSK Vocabulary Validation[/bold]")
    console.print(f"  Canonical: {summary['total_canonical']}  "
                  f"In DB: {summary['total_in_db']}  "
                  f"Missing: {summary['total_missing']}  "
                  f"Extra: {summary['total_extra']}  "
                  f"Mismatch: {summary['total_mismatch']}")
    console.print(f"  Coverage: {summary['overall_coverage_pct']}%")
    console.print()

    val_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    val_table.add_column("HSK", justify="right")
    val_table.add_column("Coverage", justify="right")
    val_table.add_column("In DB", justify="right")
    val_table.add_column("Missing", justify="right")
    val_table.add_column("Extra", justify="right")
    val_table.add_column("Mismatch", justify="right")
    for lvl, data in sorted(result["levels"].items()):
        if data.get("error"):
            val_table.add_row(str(lvl), data['error'], "", "", "", "")
            continue

        color = "green" if data["coverage_pct"] >= 90 else "yellow" if data["coverage_pct"] >= 50 else "red"
        val_table.add_row(
            str(lvl),
            f"[{color}]{data['coverage_pct']}%[/{color}]",
            f"{data['db_count']}/{data['canonical_count']}",
            str(len(data['missing'])),
            str(len(data['extra'])),
            str(len(data['level_mismatch'])),
        )
    console.print(val_table)

    if verbose:
        for lvl, data in sorted(result["levels"].items()):
            if data.get("error"):
                continue
            if data["missing"]:
                console.print(f"  [dim]HSK {lvl} — Missing ({len(data['missing'])}):[/dim]")
                miss_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
                miss_table.add_column("Hanzi", style="bright_cyan")
                miss_table.add_column("Pinyin", style="dim")
                miss_table.add_column("English")
                for item in data["missing"][:20]:
                    miss_table.add_row(item['hanzi'], item['pinyin'], item['english'])
                console.print(miss_table)
                if len(data["missing"]) > 20:
                    console.print(f"    ... and {len(data['missing']) - 20} more")
            if data["extra"]:
                console.print(f"  [dim]HSK {lvl} — Extra ({len(data['extra'])}):[/dim]")
                extra_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
                extra_table.add_column("Hanzi", style="bright_cyan")
                extra_table.add_column("Pinyin", style="dim")
                extra_table.add_column("English")
                for item in data["extra"][:10]:
                    extra_table.add_row(item['hanzi'], item['pinyin'], item['english'])
                console.print(extra_table)
            if data["level_mismatch"]:
                console.print(f"  [dim]HSK {lvl} — Level mismatch ({len(data['level_mismatch'])}):[/dim]")
                mm_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
                mm_table.add_column("Hanzi", style="bright_cyan")
                mm_table.add_column("Canonical", justify="right")
                mm_table.add_column("DB", justify="right")
                for item in data["level_mismatch"][:10]:
                    mm_table.add_row(item['hanzi'], str(item['canonical_level']), str(item['db_level']))
                console.print(mm_table)

    console.print()


@app.command(name="sync-hsk")
def sync_hsk(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
):
    """Import missing HSK vocab and fix level assignments from canonical data."""
    from .importer import import_hsk_level
    from .validator import fix_levels, validate_all

    with db.connection() as conn:
        # Step 1: Import missing items for all levels with data files
        console.print()
        console.print("  [bold]HSK Sync[/bold]")
        total_added = 0
        total_skipped = 0
        for level in range(1, 10):
            try:
                added, skipped = import_hsk_level(conn, level, dry_run=dry_run)
                if added > 0:
                    console.print(f"  HSK {level}: +{added} new items ({skipped} existing)")
                total_added += added
                total_skipped += skipped
            except FileNotFoundError:
                pass

        # Step 2: Fix level assignments
        result = fix_levels(conn, dry_run=dry_run)
        if result["fixed"] > 0:
            console.print(f"  Level corrections: {result['fixed']} items")
            for d in result["details"][:10]:
                console.print(f"    {d['hanzi']}: HSK {d['from']} → {d['to']}")
            if len(result["details"]) > 10:
                console.print(f"    ... and {len(result['details']) - 10} more")

        # Step 3: Show validation summary
        validation = validate_all(conn)
        summary = validation["summary"]
        console.print()
        console.print(f"  {'[dry run] ' if dry_run else ''}Added: {total_added}  "
                      f"Fixed: {result['fixed']}  "
                      f"Coverage: {summary['overall_coverage_pct']}%  "
                      f"({summary['total_in_db']}/{summary['total_canonical']})")
        console.print()


@app.command()
def watch(
    media_id: str = typer.Argument(None, help="Specific media ID to watch"),
    hsk: int = typer.Option(None, "--hsk", help="Max HSK level for recommendations"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List all catalog entries"),
    history: bool = typer.Option(False, "--history", help="Show watch history"),
):
    """Recommend real Chinese media and quiz on what you watched."""
    from .media import (
        load_media_catalog, get_media_entry, recommend_media,
        run_media_comprehension, record_media_presentation,
        record_media_skip, get_watch_history, get_watch_stats,
        _ensure_media_rows, _estimate_time_budget, _get_duration_minutes,
    )
    from rich.table import Table

    user_id = get_cli_user_id() or 1
    with db.connection() as conn:
        catalog = load_media_catalog()
        if not catalog:
            console.print("\n  No media catalog found.")
            console.print("  Expected: data/media_catalog.json\n")
            return

        _ensure_media_rows(conn, catalog)

        # --list: show full catalog
        if list_all:
            table = Table(title="Media Catalog", show_lines=False, pad_edge=False)
            table.add_column("ID", style="dim", max_width=28)
            table.add_column("Title", max_width=35)
            table.add_column("HSK", justify="center", width=4)
            table.add_column("Type", width=12)
            table.add_column("Cost", width=8)
            table.add_column("Status", width=10)
            table.add_column("Score", justify="right", width=6)

            watch_rows = {dict(r)["media_id"]: dict(r) for r in
                          conn.execute("SELECT * FROM media_watch").fetchall()}

            for entry in sorted(catalog, key=lambda e: e.get("hsk_level", 1)):
                w = watch_rows.get(entry["id"], {})
                status = w.get("status", "available")
                avg = w.get("avg_score")
                score_str = f"{avg:.0%}" if avg is not None else "—"
                liked = w.get("liked")
                if liked == 1:
                    status += " ♥"
                table.add_row(
                    entry["id"],
                    entry.get("title", ""),
                    str(entry.get("hsk_level", "?")),
                    entry.get("media_type", ""),
                    entry.get("cost", "free"),
                    status,
                    score_str,
                )

            console.print()
            console.print(table)
            stats = get_watch_stats(conn)
            console.print(f"\n  {stats.get('watched', 0)}/{stats.get('total_entries', 0)} watched  "
                          f"avg: {stats.get('overall_avg', 0) or 0:.0%}  "
                          f"liked: {stats.get('liked_count', 0)}")
            console.print()
            return

        # --history: show watch history
        if history:
            hist = get_watch_history(conn)
            if not hist:
                console.print("\n  No watch history yet. Try: ./run watch\n")
                return

            table = Table(title="Watch History", show_lines=False, pad_edge=False)
            table.add_column("Title", max_width=35)
            table.add_column("HSK", justify="center", width=4)
            table.add_column("Score", justify="right", width=6)
            table.add_column("Best", justify="right", width=6)
            table.add_column("Watched", justify="right", width=8)
            table.add_column("Last", width=16)

            for w in hist:
                avg = w.get("avg_score")
                best = w.get("best_score")
                table.add_row(
                    w.get("title", ""),
                    str(w.get("hsk_level", "?")),
                    f"{avg:.0%}" if avg is not None else "—",
                    f"{best:.0%}" if best is not None else "—",
                    str(w.get("times_watched", 0)),
                    (w.get("last_watched_at") or "")[:16],
                )

            console.print()
            console.print(table)
            console.print()
            return

        # Default flow: recommend and quiz
        profile = db.get_profile(conn, user_id=user_id)
        max_hsk = hsk or max(int(profile.get("level_reading", 1) or 1), 1) + 1

        # Build lens weights from profile
        lens_weights = {}
        for col in ("lens_quiet_observation", "lens_institutions", "lens_urban_texture",
                     "lens_humane_mystery", "lens_identity", "lens_comedy",
                     "lens_food", "lens_travel", "lens_explainers",
                     "lens_wit", "lens_ensemble_comedy", "lens_sharp_observation",
                     "lens_satire", "lens_moral_texture"):
            lens_weights[col] = float(profile.get(col) or 0.5)

        # If specific media_id given, go straight to it
        if media_id:
            entry = get_media_entry(media_id)
            if not entry:
                console.print(f"\n  Media ID not found: {media_id}")
                console.print("  Use ./run watch --list to see all entries.\n")
                return
            _show_media_entry(entry)
            record_media_presentation(conn, media_id)
            resp = _input("\n  Press Enter when you've watched it, S to skip, Q to quit: ").strip().upper()
            if resp == "Q":
                return
            if resp == "S":
                record_media_skip(conn, media_id)
                console.print("  Skipped.\n")
                return
            run_media_comprehension(entry, _show, _input, conn=conn)
            return

        # Recommend — time-aware
        time_budget = _estimate_time_budget()
        recs = recommend_media(conn, hsk_max=max_hsk, lens_weights=lens_weights,
                               limit=3, time_budget=time_budget)
        if not recs:
            console.print("\n  No recommendations available for current level.\n")
            return

        console.print(f"\n  [dim]~{time_budget} min available — "
                      f"{'short clips' if time_budget <= 5 else 'medium content' if time_budget <= 15 else 'longer content OK'}[/dim]")

        rec_idx = 0
        while rec_idx < len(recs):
            entry, watch = recs[rec_idx]
            _show_media_entry(entry)
            record_media_presentation(conn, entry["id"])

            resp = _input("\n  Press Enter when you've watched it, S to skip, Q to quit: ").strip().upper()

            if resp == "Q":
                return
            if resp == "S":
                record_media_skip(conn, entry["id"])
                console.print("  Skipped.")
                rec_idx += 1
                continue

            # Run comprehension
            run_media_comprehension(entry, _show, _input, conn=conn)
            return


def _show_media_entry(entry: dict):
    """Display a media entry's details for the user."""
    from .media import _get_duration_minutes
    duration = _get_duration_minutes(entry)
    console.print()
    console.print(f"  [bold bright_cyan]{entry.get('title_zh', '')}[/bold bright_cyan]")
    console.print(f"  {entry.get('title', '')}  ({entry.get('year', '')})  [dim]{duration} min[/dim]")
    console.print()

    seg = entry.get("segment", {})
    if seg:
        ep = seg.get("episode", "")
        if ep:
            console.print(f"  Episode: {ep}")
        start = seg.get("start_time", "")
        end = seg.get("end_time", "")
        if start and end:
            console.print(f"  Segment: {start} → {end}")
        desc = seg.get("description", "")
        desc_zh = seg.get("description_zh", "")
        if desc_zh:
            console.print(f"  {desc_zh}")
        if desc:
            console.print(f"  {desc}")

    console.print()

    wtf = entry.get("where_to_find", {})
    if wtf:
        cost = entry.get("cost", "free")
        cost_label = {"free": "free", "subscription": "subscription",
                      "rental": "rental", "purchase": "purchase"}.get(cost, cost)
        console.print(f"  [dim]Where to find ({cost_label}):[/dim]")
        if wtf.get("primary"):
            console.print(f"    {wtf['primary']}")
        if wtf.get("alt"):
            console.print(f"    Alt: {wtf['alt']}")

    console.print()

    # Vocab preview
    vocab = entry.get("vocab_preview", [])
    if vocab:
        console.print(f"  [dim]Vocab preview:[/dim]")
        for v in vocab:
            console.print(f"    [bold bright_cyan]{v['hanzi']}[/bold bright_cyan]  "
                          f"{v.get('pinyin', '')}  —  {v.get('english', '')}")


@app.command()
def encounters(
    days: int = typer.Option(7, "--days", "-d", help="Lookback window in days"),
):
    """Show recent vocab encounters from reading and listening."""
    with db.connection() as conn:
        # Check if table exists
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "vocab_encounter" not in tables:
            console.print("\n  No encounter data yet. Use the web reader or listener first.\n")
            return

        total = conn.execute(
            """SELECT COUNT(*) as cnt FROM vocab_encounter
               WHERE looked_up = 1 AND created_at >= datetime('now', ? || ' days')""",
            (f"-{days}",)
        ).fetchone()
        total_count = total["cnt"] if total else 0

        if total_count == 0:
            console.print(f"\n  No vocab lookups in the last {days} days.\n")
            return

        console.print(f"\n  Vocab encounters (last {days} days): {total_count} lookups\n")

        # Top words
        top = conn.execute(
            """SELECT hanzi, COUNT(*) as cnt
               FROM vocab_encounter
               WHERE looked_up = 1 AND created_at >= datetime('now', ? || ' days')
               GROUP BY hanzi ORDER BY cnt DESC LIMIT 15""",
            (f"-{days}",)
        ).fetchall()

        if top:
            table = Table(title="Most Looked Up", show_lines=False, pad_edge=False)
            table.add_column("Hanzi", style="bold bright_cyan")
            table.add_column("Lookups", justify="right")
            for r in top:
                table.add_row(r["hanzi"], str(r["cnt"]))
            console.print(table)

        # Source breakdown
        sources = conn.execute(
            """SELECT source_type, COUNT(*) as cnt
               FROM vocab_encounter
               WHERE looked_up = 1 AND created_at >= datetime('now', ? || ' days')
               GROUP BY source_type""",
            (f"-{days}",)
        ).fetchall()
        if sources:
            console.print("\n  Sources:")
            for s in sources:
                console.print(f"    {s['source_type']}: {s['cnt']}")
        console.print()


@app.command()
def reset():
    """Reset the database (destructive — asks for confirmation)."""
    if typer.confirm("\nThis will delete all progress. Are you sure?", default=False):
        import os
        if db.DB_PATH.exists():
            os.remove(db.DB_PATH)
            console.print("\n  Database reset.\n")
        else:
            console.print("\n  No database to reset.\n")


@app.command(name="retention-purge")
def retention_purge(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be purged without deleting"),
):
    """Purge data past retention policies (data governance)."""
    from .data_retention import get_policies, purge_expired

    with db.connection() as conn:
        policies = get_policies(conn)
        if not policies:
            console.print("\n  No retention policies found.\n")
            return

        console.print("\n  [bold]Retention Policies[/bold]\n")
        from rich.table import Table
        t = Table(show_header=True, header_style="bold")
        t.add_column("Table")
        t.add_column("Retention")
        t.add_column("Last Purged")
        for p in policies:
            days = p["retention_days"]
            ret_str = "indefinite" if days < 0 else f"{days} days"
            t.add_row(p["table_name"], ret_str, p.get("last_purged") or "never")
        console.print(t)

        if dry_run:
            console.print("\n  [dim]Dry run — counting expired rows...[/dim]")
        else:
            console.print("\n  Purging expired rows...")

        results = purge_expired(conn, dry_run=dry_run)

        if results:
            action = "Would delete" if dry_run else "Deleted"
            for table, count in sorted(results.items()):
                if count > 0:
                    console.print(f"    {action} {count} rows from {table}")
            if not any(v > 0 for v in results.values()):
                console.print("    No expired rows found.")
        else:
            console.print("    No tables eligible for purge.")
        console.print()


# ── Command aliases ──────────────────────────────

@app.command(name="g", hidden=True)
def alias_g():
    """Alias for guide."""
    guide()


@app.command(name="s", hidden=True)
def alias_s():
    """Alias for session."""
    session()


@app.command(name="m", hidden=True)
def alias_m():
    """Alias for mini."""
    mini()


@app.command(name="st", hidden=True)
def alias_st(
    detail: bool = typer.Option(False, "--detail", "-d", help="Show extended details"),
):
    """Alias for status."""
    status(detail=detail)


@app.command(name="dx", hidden=True)
def alias_dx(
    full: bool = typer.Option(False, "--full", help="Run full assessment"),
):
    """Alias for diagnose."""
    diagnose(full=full)


@app.command(name="f", hidden=True)
def alias_f():
    """Alias for forecast."""
    forecast()


@app.command(name="fo", hidden=True)
def alias_fo(
    lens: str = typer.Argument(..., help="Content lens to focus on"),
    sessions: int = typer.Option(3, "--sessions", "-n", help="Number of sessions to boost"),
):
    """Alias for focus."""
    focus(lens=lens, sessions=sessions)


@app.command(name="w", hidden=True)
def alias_w(
    media_id: str = typer.Argument(None),
    hsk: int = typer.Option(None, "--hsk"),
    list_all: bool = typer.Option(False, "--list", "-l"),
    history: bool = typer.Option(False, "--history"),
):
    """Alias for watch."""
    watch(media_id=media_id, hsk=hsk, list_all=list_all, history=history)


@app.command(name="memory", hidden=True)
def alias_memory(
    detail: bool = typer.Option(False, "--detail", "-d"),
):
    """Alias: matches web 'Memory' panel."""
    status(detail=detail)


@app.command(name="sessions", hidden=True)
def alias_sessions(
    n: int = typer.Option(10, "--last", "-n"),
):
    """Alias: matches web 'Recent Sessions' panel."""
    history(n=n)


# ── Marketing analytics ──────────────────────────────

@app.command(name="churn-report")
def churn_report(
    output_format: str = typer.Option("rich", "--format", "-f",
                                       help="Output format: rich or plain"),
    api: bool = typer.Option(False, "--api", help="Output JSON for scripting"),
    min_risk: int = typer.Option(60, "--min-risk", help="Min risk score for --api mode"),
):
    """Run churn detection and risk scoring report."""
    from .churn_detection import run_report, get_at_risk_users
    if api:
        import json as _json
        users = get_at_risk_users(min_risk=min_risk)
        console.print(_json.dumps(users, indent=2, default=str))
    else:
        run_report(output_format=output_format)


@app.command()
def metrics(
    output_format: str = typer.Option("rich", "--format", "-f",
                                       help="Output format: rich, plain, or quiet"),
    no_save: bool = typer.Option(False, "--no-save", help="Do not save report files"),
):
    """Generate weekly metrics report with KPIs."""
    from .metrics_report import generate_report
    generate_report(output_format=output_format, save=not no_save)


@app.command()
def wiring():
    """Check integration wiring (CSS, data fields, API contracts)."""
    from .wiring import run_checks, print_report
    results = run_checks()
    print_report(results)


# ── Auth commands ──────────────────────────────

@app.command()
def login():
    """Log in to your Aelu account."""
    from .cli_auth import get_cli_auth, save_cli_auth
    from .auth import authenticate

    existing = get_cli_auth()
    if existing:
        console.print(f"\n  Already logged in as {existing['email']}.")
        console.print("  Run [bold]./run logout[/bold] first to switch accounts.\n")
        return

    email = console.input("  Email: ").strip()
    if not email:
        console.print("\n  Cancelled.\n")
        return

    import getpass
    password = getpass.getpass("  Password: ")
    if not password:
        console.print("\n  Cancelled.\n")
        return

    with db.connection() as conn:
        user = authenticate(conn, email, password)
        if user:
            save_cli_auth(user["id"], user["email"])
            console.print(f"\n  Logged in as {user['email']}.\n")
        else:
            console.print("\n  Invalid email or password.\n")


@app.command()
def logout():
    """Log out of your Aelu account."""
    from .cli_auth import get_cli_auth, clear_cli_auth

    existing = get_cli_auth()
    if not existing:
        console.print("\n  Not logged in.\n")
        return

    clear_cli_auth()
    console.print(f"\n  Logged out ({existing['email']}).\n")


@app.command()
def register():
    """Create a new Aelu account."""
    from .cli_auth import get_cli_auth, save_cli_auth
    from .auth import create_user

    existing = get_cli_auth()
    if existing:
        console.print(f"\n  Already logged in as {existing['email']}.")
        console.print("  Run [bold]./run logout[/bold] first.\n")
        return

    email = console.input("  Email: ").strip()
    if not email:
        console.print("\n  Cancelled.\n")
        return

    import getpass
    password = getpass.getpass("  Password (min 8 chars): ")
    if not password:
        console.print("\n  Cancelled.\n")
        return

    confirm = getpass.getpass("  Confirm password: ")
    if password != confirm:
        console.print("\n  Passwords do not match.\n")
        return

    display_name = console.input("  Display name (optional): ").strip()

    with db.connection() as conn:
        try:
            user = create_user(conn, email, password, display_name=display_name)
            save_cli_auth(user["id"], user["email"])
            console.print(f"\n  Account created. Logged in as {user['email']}.\n")
        except ValueError as e:
            console.print(f"\n  {e}\n")


@app.command(name="claim-account")
def claim_account():
    """Claim the bootstrap account (user 1) with your email and password.

    This preserves all existing session history, progress, and learner profile
    under your new login credentials.
    """
    from .cli_auth import save_cli_auth
    from werkzeug.security import generate_password_hash
    from datetime import datetime, timezone

    with db.connection() as conn:
        user = conn.execute("SELECT id, email, password_hash FROM user WHERE id = 1").fetchone()
        if not user:
            console.print("\n  No bootstrap user found.\n")
            return

        if user["email"] != "local@localhost" and user["password_hash"] != "bootstrap_no_login":
            console.print(f"\n  Account already claimed ({user['email']}).")
            console.print("  Use [bold]./run login[/bold] instead.\n")
            return

        email = console.input("  Email: ").strip()
        if not email or "@" not in email:
            console.print("\n  Invalid email.\n")
            return

        import getpass
        password = getpass.getpass("  Password (min 8 chars): ")
        if len(password) < 8:
            console.print("\n  Password must be at least 8 characters.\n")
            return

        confirm = getpass.getpass("  Confirm password: ")
        if password != confirm:
            console.print("\n  Passwords do not match.\n")
            return

        display_name = console.input("  Display name (optional): ").strip() or email.split("@")[0]

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        conn.execute(
            """UPDATE user SET email = ?, password_hash = ?, display_name = ?,
               updated_at = ?, last_login_at = ? WHERE id = 1""",
            (email.lower(), password_hash, display_name, now, now)
        )
        conn.commit()

        save_cli_auth(1, email.lower())
        console.print(f"\n  Account claimed. You can now log in as {email}.")
        console.print("  All your existing history is preserved.\n")


@app.command(name="invite-create")
def invite_create(
    count: int = typer.Argument(1, help="Number of invite codes to generate"),
    max_uses: int = typer.Option(1, "--max-uses", help="Max uses per code"),
):
    """Generate invite codes."""
    import secrets
    from datetime import datetime, timezone

    with db.connection() as conn:
        codes = []
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        for _ in range(count):
            code = secrets.token_urlsafe(8)
            conn.execute(
                "INSERT INTO invite_code (code, created_at, max_uses) VALUES (?, ?, ?)",
                (code, now, max_uses)
            )
            codes.append(code)
        conn.commit()

        console.print()
        for code in codes:
            console.print(f"  {code}")
        console.print(f"\n  {len(codes)} invite code(s) created.\n")


@app.command(name="invite-list")
def invite_list():
    """List all invite codes and their usage."""
    with db.connection() as conn:
        rows = conn.execute(
            """SELECT code, created_at, used_by, used_at, max_uses, use_count
               FROM invite_code ORDER BY created_at DESC"""
        ).fetchall()

        if not rows:
            console.print("\n  No invite codes found.\n")
            return

        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        table.add_column("Code")
        table.add_column("Created", style="dim")
        table.add_column("Uses", justify="right")
        table.add_column("Max", justify="right")
        table.add_column("Status")

        for r in rows:
            uses = r["use_count"] or 0
            max_u = r["max_uses"] or 1
            status = "[green]available[/green]" if uses < max_u else "[dim]used[/dim]"
            table.add_row(
                r["code"],
                (r["created_at"] or "")[:10],
                str(uses),
                str(max_u),
                status,
            )

        console.print()
        console.print(table)
        console.print()


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
