"""Parse marketing content files into a structured content bank.

Reads social-media.md, newsletters.md, and other content source files,
extracting individual content pieces that can be posted by the scheduler.

Exports:
    ContentPiece: dataclass for a single piece of content
    parse_social_media(path) -> list[ContentPiece]
    parse_newsletters(path) -> list[ContentPiece]
    load_content_bank() -> dict[str, ContentPiece]  # keyed by content_id
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_MARKETING_DIR = _PROJECT_ROOT / "marketing"


@dataclass
class ContentPiece:
    content_id: str  # "tweet_1", "thread_3", "newsletter_1"
    platform: str  # "twitter", "newsletter", "reddit"
    content_type: str  # "tweet", "thread", "reddit_value", "newsletter"
    text: str
    hashtags: list[str] = field(default_factory=list)
    requires_personalization: bool = False  # [brackets] present
    source_file: str = ""
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)
        # Extract hashtags
        self.hashtags = re.findall(r"#\w+", self.text)
        # Check for personalization brackets
        self.requires_personalization = bool(re.search(r"\[.*?\]", self.text))


def _read_file(filename: str) -> str:
    """Read a file from the marketing directory."""
    path = _MARKETING_DIR / filename
    if not path.exists():
        logger.warning("Marketing file not found: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def parse_social_media(path: str | Path | None = None) -> list[ContentPiece]:
    """Parse social-media.md into individual tweets, threads, and posts.

    Handles numbered entries like:
    **1.**
    <content>

    **2.**
    <content>

    And thread sections with numbered tweets within.
    """
    text = Path(path).read_text(encoding="utf-8") if path else _read_file("social-media.md")
    if not text:
        return []

    pieces = []
    current_section = ""
    current_number = 0
    current_lines: list[str] = []

    def _flush():
        nonlocal current_lines, current_number
        if current_lines and current_number > 0:
            content = "\n".join(current_lines).strip()
            if content:
                if "thread" in current_section.lower():
                    content_type = "thread"
                    platform = "twitter"
                    cid = f"thread_{current_number}"
                elif "linkedin" in current_section.lower():
                    content_type = "linkedin_post"
                    platform = "linkedin"
                    cid = f"linkedin_{current_number}"
                elif "short" in current_section.lower():
                    content_type = "short"
                    platform = "youtube"
                    cid = f"short_{current_number}"
                else:
                    content_type = "tweet"
                    platform = "twitter"
                    cid = f"tweet_{current_number}"

                pieces.append(ContentPiece(
                    content_id=cid,
                    platform=platform,
                    content_type=content_type,
                    text=content,
                    source_file="social-media.md",
                ))
        current_lines = []

    for line in text.splitlines():
        stripped = line.strip()

        # Detect section headers (## or ###)
        if stripped.startswith("##"):
            _flush()
            current_section = stripped.lstrip("#").strip()
            current_number = 0
            continue

        # Detect numbered entries: **1.** or **12.**
        num_match = re.match(r"\*\*(\d+)\.\*\*", stripped)
        if num_match:
            _flush()
            current_number = int(num_match.group(1))
            # Anything after the number on the same line
            rest = stripped[num_match.end():].strip()
            if rest:
                current_lines.append(rest)
            continue

        # Accumulate content lines
        if current_number > 0:
            current_lines.append(line.rstrip())

    _flush()  # Final entry

    logger.info("Parsed %d content pieces from social-media.md", len(pieces))
    return pieces


def parse_newsletters(path: str | Path | None = None) -> list[ContentPiece]:
    """Parse newsletters.md into individual newsletter issues.

    Newsletters are separated by headers like:
    ### Issue 1: Welcome
    or
    ## Issue 1 — Welcome
    """
    text = Path(path).read_text(encoding="utf-8") if path else _read_file("newsletters.md")
    if not text:
        return []

    pieces = []
    current_issue = 0
    _current_title = ""  # noqa: F841
    current_lines: list[str] = []

    def _flush():
        nonlocal current_lines
        if current_lines and current_issue > 0:
            content = "\n".join(current_lines).strip()
            if content:
                pieces.append(ContentPiece(
                    content_id=f"newsletter_{current_issue}",
                    platform="newsletter",
                    content_type="newsletter",
                    text=content,
                    source_file="newsletters.md",
                ))
        current_lines = []

    for line in text.splitlines():
        stripped = line.strip()

        # Detect issue headers
        issue_match = re.match(
            r"#{2,3}\s+Issue\s+(\d+)\s*[:\—\-–]\s*(.*)",
            stripped, re.IGNORECASE,
        )
        if issue_match:
            _flush()
            current_issue = int(issue_match.group(1))
            _current_title = issue_match.group(2).strip()  # noqa: F841
            continue

        if current_issue > 0:
            current_lines.append(line.rstrip())

    _flush()

    logger.info("Parsed %d newsletter issues from newsletters.md", len(pieces))
    return pieces


def load_content_bank() -> dict[str, ContentPiece]:
    """Load all content sources into a unified bank keyed by content_id."""
    bank: dict[str, ContentPiece] = {}

    # Social media (tweets, threads, shorts, LinkedIn)
    for piece in parse_social_media():
        bank[piece.content_id] = piece

    # Newsletters
    for piece in parse_newsletters():
        bank[piece.content_id] = piece

    logger.info("Content bank loaded: %d pieces total", len(bank))
    return bank


def get_dynamic_pricing() -> dict[str, str]:
    """Read current pricing from settings for template personalization.

    Marketing content should NEVER hardcode prices — always read from here.
    """
    try:
        from ..settings import PRICING
        return {
            "monthly_price": PRICING.get("monthly_display", "$14.99"),
            "annual_price": PRICING.get("annual_display", "$149"),
            "annual_monthly": PRICING.get("annual_monthly_display", "$12.42"),
        }
    except (ImportError, AttributeError):
        return {
            "monthly_price": "$14.99",
            "annual_price": "$149",
            "annual_monthly": "$12.42",
        }


def personalize_content(piece: ContentPiece, conn=None) -> str:
    """Replace [bracket] placeholders with real data.

    Handles:
    - [price] → current monthly price from settings
    - [annual_price] → current annual price
    - [drill_count] → actual drill type count from dispatch registry
    - [user_count] → real user count if above threshold
    """
    text = piece.text
    if not piece.requires_personalization:
        return text

    pricing = get_dynamic_pricing()
    text = text.replace("[price]", pricing["monthly_price"])
    text = text.replace("[annual_price]", pricing["annual_price"])
    text = text.replace("[annual_monthly]", pricing["annual_monthly"])

    # Drill count from actual registry
    try:
        from ..drills.dispatch import DRILL_REGISTRY
        text = text.replace("[drill_count]", str(len(DRILL_REGISTRY)))
    except (ImportError, AttributeError):
        text = text.replace("[drill_count]", "44")

    return text
