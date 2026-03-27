"""Parse content-calendar.md into structured actions.

The content calendar is a 12-week plan with daily actions per platform.
This module reads the markdown table format and returns CalendarAction objects
for a given date, relative to a configurable MARKETING_LAUNCH_DATE.

Exports:
    CalendarAction: dataclass for a single scheduled action
    parse_calendar(calendar_path) -> list[CalendarAction]
    get_actions_for_date(actions, target_date, launch_date) -> list[CalendarAction]
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CALENDAR_PATH = _PROJECT_ROOT / "marketing" / "content-calendar.md"

_DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_PLATFORM_KEYWORDS = {
    "twitter": "twitter", "twitter/x": "twitter", "x": "twitter",
    "reddit": "reddit", "r/": "reddit",
    "newsletter": "newsletter", "email": "newsletter",
    "blog": "blog",
    "youtube": "youtube", "yt shorts": "youtube", "tiktok": "youtube",
    "reels": "youtube",
    "linkedin": "linkedin",
    "product hunt": "producthunt", "producthunt": "producthunt",
    "hacker news": "hackernews", "hackernews": "hackernews",
    "discord": "discord",
}


@dataclass
class CalendarAction:
    week: int
    day_of_week: int  # 0=Mon..6=Sun
    action_description: str
    platform: str  # twitter, reddit, newsletter, blog, youtube, etc.
    source_file: str  # e.g. "social-media.md"
    ready_status: str  # "Y", "P", "Manual"
    requires_approval: bool  # True for Reddit, "P" items, "Manual" items
    phase: str  # "pre_launch", "launch", "post_launch"
    action_hash: str  # SHA256 for dedup

    @property
    def content_key(self) -> str:
        """Derive content key from description (e.g. 'tweet #25' -> 'tweet_25')."""
        text = self.action_description.lower()
        # Match patterns like "tweet #25", "thread 3", "newsletter issue 1"
        m = re.search(r"(tweet|thread|short|newsletter\s+issue|reddit\s+value\s+post|blog\s+post)\s*#?(\d+)", text)
        if m:
            kind = m.group(1).replace(" ", "_").strip()
            num = m.group(2)
            return f"{kind}_{num}"
        return ""


def _detect_platform(text: str) -> str:
    """Detect platform from action description or platform column."""
    lower = text.lower()
    for keyword, platform in _PLATFORM_KEYWORDS.items():
        if keyword in lower:
            return platform
    return "other"


def _detect_ready_status(text: str) -> str:
    """Extract ready status from the Ready? column."""
    text = text.strip().upper()
    if text in ("Y", "YES"):
        return "Y"
    if text in ("P", "PERSONALIZE"):
        return "P"
    return "Manual"


def _compute_hash(week: int, day: int, desc: str) -> str:
    """Compute dedup hash for an action."""
    raw = f"{week}:{day}:{desc.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def parse_calendar(calendar_path: str | Path | None = None) -> list[CalendarAction]:
    """Parse content-calendar.md into a list of CalendarAction objects.

    Handles the markdown table format with Week/Day/Action/Platform/Source/Ready columns.
    """
    path = Path(calendar_path) if calendar_path else _DEFAULT_CALENDAR_PATH
    if not path.exists():
        logger.warning("Content calendar not found at %s", path)
        return []

    text = path.read_text(encoding="utf-8")
    actions = []

    current_week = 0
    current_phase = "pre_launch"

    for line in text.splitlines():
        stripped = line.strip()

        # Detect phase headers
        if "pre-launch" in stripped.lower():
            current_phase = "pre_launch"
        elif "launch phase" in stripped.lower() or "launch week" in stripped.lower():
            current_phase = "launch"
        elif "post-launch" in stripped.lower():
            current_phase = "post_launch"

        # Detect week headers
        week_match = re.search(r"week\s+(\d+)", stripped, re.IGNORECASE)
        if week_match and not stripped.startswith("|"):
            current_week = int(week_match.group(1))
            continue

        # Parse table rows: | Day | Action | Platform | Source File | Ready? |
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]  # remove empty from leading/trailing |

        if len(cells) < 2:
            continue

        # Skip header rows and separator rows
        if cells[0].lower() in ("day", "---", "-----") or all(c.startswith("-") for c in cells):
            continue
        if re.match(r"^-+$", cells[0]):
            continue

        # Parse day
        day_text = cells[0].strip().lower()
        # Handle bold markers like **Tue 12:01 AM PT**
        day_text = re.sub(r"\*\*", "", day_text).strip()
        day_of_week = -1
        for key, val in _DAY_MAP.items():
            if day_text.startswith(key):
                day_of_week = val
                break
        if day_of_week < 0:
            continue

        action_desc = cells[1] if len(cells) > 1 else ""
        action_desc = re.sub(r"\*\*", "", action_desc).strip()  # strip bold

        platform_text = cells[2] if len(cells) > 2 else ""
        source_file = cells[3] if len(cells) > 3 else ""
        ready_text = cells[4] if len(cells) > 4 else "Manual"

        platform = _detect_platform(platform_text) or _detect_platform(action_desc)
        ready_status = _detect_ready_status(ready_text)

        # Reddit and Manual items always require approval
        requires_approval = (
            platform == "reddit"
            or ready_status == "Manual"
            or ready_status == "P"
        )

        action = CalendarAction(
            week=current_week,
            day_of_week=day_of_week,
            action_description=action_desc,
            platform=platform,
            source_file=source_file,
            ready_status=ready_status,
            requires_approval=requires_approval,
            phase=current_phase,
            action_hash=_compute_hash(current_week, day_of_week, action_desc),
        )
        actions.append(action)

    logger.info("Parsed %d calendar actions across %d weeks",
                len(actions), max((a.week for a in actions), default=0))
    return actions


def get_actions_for_date(
    actions: list[CalendarAction],
    target_date: date,
    launch_date: date | None = None,
) -> list[CalendarAction]:
    """Get actions scheduled for a specific date.

    Maps calendar weeks to real dates using launch_date as the start of week 1.
    If launch_date is not set, reads MARKETING_LAUNCH_DATE env var.
    """
    if launch_date is None:
        from ..settings import MARKETING_LAUNCH_DATE
        env_date = MARKETING_LAUNCH_DATE
        if not env_date:
            logger.debug("MARKETING_LAUNCH_DATE not set, cannot map calendar to dates")
            return []
        try:
            launch_date = date.fromisoformat(env_date)
        except ValueError:
            logger.error("Invalid MARKETING_LAUNCH_DATE: %s", env_date)
            return []

    # Week 1, Day 0 (Monday) = launch_date aligned to Monday
    # Find the Monday of the launch week
    launch_monday = launch_date - timedelta(days=launch_date.weekday())

    # Map target_date to week number and day of week
    days_since_start = (target_date - launch_monday).days
    if days_since_start < 0:
        return []  # Before calendar start

    target_week = (days_since_start // 7) + 1
    target_day = target_date.weekday()

    return [a for a in actions if a.week == target_week and a.day_of_week == target_day]
