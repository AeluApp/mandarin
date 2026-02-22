"""Display helpers — centralize Rich markup formatting.

All Rich markup lives here. Domain logic produces plain data;
these helpers wrap it for the current rendering engine (Rich console).
If the renderer changes (e.g. to HTML for the web UI), only this file
needs updating.

Semantic color mapping (CLI Rich → Web CSS):
  bright_cyan / bold bright_cyan  →  --color-accent  (rose)
  bright_magenta / bold bright_magenta  →  --color-accent  (drill hanzi)
  green / bold green  →  --color-correct
  red / bold red  →  --color-incorrect
  yellow / bold yellow  →  --color-secondary  (olive)
  dim  →  opacity 0.6
  dim italic  →  opacity 0.6 + italic
"""

# ── Canonical stage labels — single source of truth ──
# Used by CLI (runner.py) and web (routes.py → template context).
# Internal stage key → display label (sentence case, for both surfaces).
STAGE_LABELS = {
    "seen": "Encountered",
    "passed_once": "Introduced",
    "stabilizing": "Building",
    "stable": "Strong",
    "durable": "Mastered",
    "decayed": "Needs review",
    "weak": "Fresh",
    "improving": "Recovering",
    "not_seen": "New",
}


def dim(text: str) -> str:
    """Wrap text in dim markup, indented."""
    return f"  [dim]{text}[/dim]"


def dim_inline(text: str) -> str:
    """Wrap text in dim markup, no indent."""
    return f"[dim]{text}[/dim]"


def dim_italic(text: str) -> str:
    """Wrap text in dim italic markup, indented."""
    return f"  [dim italic]{text}[/dim italic]"


def hanzi(text: str) -> str:
    """Format hanzi in the system's signature style."""
    return f"[bold bright_cyan]{text}[/bold bright_cyan]"


def hanzi_with_detail(hz: str, pinyin: str, english: str) -> str:
    """Format hanzi + pinyin + english on one line, indented."""
    return f"    {hanzi(hz)}  {pinyin}  —  {english}"


def hint(text: str) -> str:
    """Format a parenthetical hint, indented."""
    return f"  [dim]({text})[/dim]"


def context_note(hanzi_text: str, english: str) -> str:
    """Format a personalized domain context note, indented."""
    return f"  [dim]In context: {hanzi_text} — {english}[/dim]"


def elaborative_prompt(prompt: str) -> str:
    """Format elaborative interrogation prompts, indented."""
    return f"  [dim italic]Think: {prompt}[/dim italic]"


def streak_label(text: str) -> str:
    """Format streak/momentum labels, indented."""
    return f"  [dim]{text}[/dim]"


def sparkline(label: str, spark: str) -> str:
    """Format sparkline display with label dim and spark prominent."""
    return f"  [dim]{label}[/dim] {hanzi(spark)}"


def modality_break() -> str:
    """Visual break between modality switches."""
    return "  [dim]· · ·[/dim]"


def mastery_stage(label: str, streak: int = 0) -> str:
    """Format mastery stage indicator, indented."""
    if streak > 0:
        return f"  [dim]{label} ({streak} streak)[/dim]"
    return f"  [dim]{label}[/dim]"


def tone_score(score: float) -> str:
    """Format a tone score with color based on quality."""
    if score >= 0.8:
        return f"  [green]Tone score: {score:.0%}[/green]"
    elif score >= 0.5:
        return f"  [yellow]Tone score: {score:.0%}[/yellow]"
    else:
        return f"  [red]Tone score: {score:.0%}[/red]"


def format_days_gap(days_gap: int) -> str:
    """Format a number of days since last session as human-readable text."""
    if days_gap == 0:
        return "today"
    elif days_gap == 1:
        return "yesterday"
    else:
        return f"{days_gap} days ago"


def correct_mark() -> str:
    """Green checkmark for correct answers."""
    return "  [green]✓[/green]"


def wrong_mark(correct_answer: str) -> str:
    """Arrow directing to the correct answer — not an alarm, a redirect."""
    return f"  → {correct_answer}"


# ── Semantic output helpers (for consistent CLI output) ──

def success(msg: str) -> str:
    """Format a success message, indented."""
    return f"  [green]{msg}[/green]"


def info(msg: str) -> str:
    """Format an informational message, indented."""
    return f"  {msg}"


def error(msg: str) -> str:
    """Format an error message, indented."""
    return f"  [red]{msg}[/red]"


def section_header(title: str) -> str:
    """Format a section header using heading style."""
    return f"\n  [bold]{title}[/bold]"
