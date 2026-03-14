"""Automated release notes from git commits.

Watches git commits, classifies changes, generates user-facing changelog
entries, queues for approval. Translates developer commits into plain
English that users care about.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ChangeCategory(Enum):
    FEATURE = "feature"
    IMPROVEMENT = "improvement"
    FIX = "fix"
    CONTENT = "content"
    INFRASTRUCTURE = "infrastructure"
    INTERNAL = "internal"


@dataclass
class ParsedCommit:
    hash: str
    author: str
    date: str
    message: str
    files_changed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class ChangelogEntry:
    date: str
    version_hint: str
    sections: dict  # ChangeCategory.value -> list[str]
    summary: str
    commit_count: int = 0


class CommitParser:
    """Parse git log output into structured commits."""

    def parse_recent(
        self, repo_path: str, since: str = "1 week ago", limit: int = 50
    ) -> list[ParsedCommit]:
        try:
            result = subprocess.run(
                ["git", "log", f"--since={since}", f"-n{limit}",
                 "--pretty=format:%H|%an|%ai|%s", "--stat"],
                cwd=repo_path, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return []
            return self._parse_git_log(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []

    def _parse_git_log(self, output: str) -> list[ParsedCommit]:
        commits = []
        current = None
        files = []

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Commit header line: hash|author|date|message
            if "|" in line and len(line.split("|")) >= 4:
                parts = line.split("|", 3)
                if len(parts[0]) == 40 and all(c in "0123456789abcdef" for c in parts[0]):
                    if current:
                        current.files_changed = files
                        commits.append(current)
                        files = []
                    current = ParsedCommit(
                        hash=parts[0], author=parts[1],
                        date=parts[2], message=parts[3],
                    )
                    continue

            # Stat summary line: "X files changed, Y insertions(+), Z deletions(-)"
            stat_match = re.match(
                r"\s*(\d+)\s+files?\s+changed(?:,\s+(\d+)\s+insert)?(?:.*,\s+(\d+)\s+delet)?",
                line,
            )
            if stat_match and current:
                current.insertions = int(stat_match.group(2) or 0)
                current.deletions = int(stat_match.group(3) or 0)
                continue

            # File stat line: " path/to/file | 42 ++++--"
            file_match = re.match(r"\s*(.+?)\s+\|\s+\d+", line)
            if file_match:
                files.append(file_match.group(1).strip())

        if current:
            current.files_changed = files
            commits.append(current)

        return commits


class ChangeClassifier:
    """Classify commits into user-facing categories."""

    _FEATURE_PATHS = {"mandarin/drills/", "mandarin/scheduler.py", "mandarin/runner.py"}
    _UI_PATHS = {"mandarin/web/static/", "mandarin/web/templates/"}
    _CONTENT_PATHS = {"data/", "data/scenarios/", "data/contexts/"}
    _INFRA_PATHS = {".github/", "Dockerfile", "fly.toml", "docker-", "litestream"}
    _INTERNAL_PATHS = {"tests/", "docs/"}

    _FIX_WORDS = {"fix", "bug", "crash", "error", "broken", "hotfix", "patch", "repair"}
    _FEATURE_WORDS = {"add", "new", "implement", "introduce", "create", "support"}

    def classify(self, commit: ParsedCommit) -> ChangeCategory:
        msg_lower = commit.message.lower()
        files = commit.files_changed

        # Check message keywords first
        if any(w in msg_lower for w in self._FIX_WORDS):
            return ChangeCategory.FIX

        # Check file paths
        if files:
            all_internal = all(
                any(f.startswith(p) for p in self._INTERNAL_PATHS) for f in files
            )
            if all_internal:
                return ChangeCategory.INTERNAL

            all_infra = all(
                any(p in f for p in self._INFRA_PATHS) for f in files
            )
            if all_infra:
                return ChangeCategory.INFRASTRUCTURE

            has_content = any(
                any(f.startswith(p) for p in self._CONTENT_PATHS) for f in files
            )
            if has_content and not any(f.endswith(".py") for f in files):
                return ChangeCategory.CONTENT

            has_feature_path = any(
                any(f.startswith(p) for p in self._FEATURE_PATHS) for f in files
            )
            if has_feature_path and any(w in msg_lower for w in self._FEATURE_WORDS):
                return ChangeCategory.FEATURE

            has_ui = any(
                any(f.startswith(p) for p in self._UI_PATHS) for f in files
            )
            if has_ui:
                return ChangeCategory.IMPROVEMENT

        if any(w in msg_lower for w in self._FEATURE_WORDS):
            return ChangeCategory.FEATURE

        return ChangeCategory.IMPROVEMENT

    @staticmethod
    def is_user_facing(category: ChangeCategory) -> bool:
        return category in (
            ChangeCategory.FEATURE, ChangeCategory.IMPROVEMENT,
            ChangeCategory.FIX, ChangeCategory.CONTENT,
        )


class ChangelogDrafter:
    """Draft user-facing changelog entries from classified commits."""

    _HUMANIZE_PATTERNS = [
        (re.compile(r"fix\s+(?:NPE|null|crash)\s+in\s+(\w+)", re.I),
         lambda m: f"Fixed an issue where {m.group(1).replace('_', ' ')} could fail unexpectedly"),
        (re.compile(r"add\s+HSK\s*(\d+)\s+scenario", re.I),
         lambda m: f"Added new conversation practice scenarios for HSK {m.group(1)}"),
        (re.compile(r"add\s+(\w+)\s+drill", re.I),
         lambda m: f"New drill type: {m.group(1).replace('_', ' ')}"),
        (re.compile(r"update\s+style|css|visual|layout|design", re.I),
         lambda _: "Visual improvements to the learning interface"),
        (re.compile(r"improve\s+(\w+)", re.I),
         lambda m: f"Improved {m.group(1).replace('_', ' ')}"),
        (re.compile(r"fix\s+(.+)", re.I),
         lambda m: f"Fixed: {m.group(1).strip()}"),
    ]

    def draft_entry(
        self, commits: list[ParsedCommit], classifications: list[ChangeCategory]
    ) -> ChangelogEntry:
        sections: dict[str, list[str]] = {}

        for commit, cat in zip(commits, classifications):
            if not ChangeClassifier.is_user_facing(cat):
                continue
            human = self._humanize_commit(commit, cat)
            sections.setdefault(cat.value, []).append(human)

        # Deduplicate within sections
        for key in sections:
            sections[key] = list(dict.fromkeys(sections[key]))

        summary = self._generate_summary(sections)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return ChangelogEntry(
            date=date, version_hint="", sections=sections,
            summary=summary, commit_count=len(commits),
        )

    def _humanize_commit(self, commit: ParsedCommit, category: ChangeCategory) -> str:
        msg = commit.message.strip()
        for pattern, rewriter in self._HUMANIZE_PATTERNS:
            m = pattern.search(msg)
            if m:
                return rewriter(m)

        # Default: clean up the commit message
        msg = re.sub(r"^(feat|fix|chore|refactor|docs|style|test)\s*[:!]\s*", "", msg, flags=re.I)
        msg = msg.strip().capitalize()
        if not msg.endswith("."):
            msg += "."
        return msg

    def _generate_summary(self, sections: dict[str, list[str]]) -> str:
        parts = []
        if "feature" in sections:
            parts.append(f"{len(sections['feature'])} new feature(s)")
        if "improvement" in sections:
            parts.append(f"{len(sections['improvement'])} improvement(s)")
        if "fix" in sections:
            parts.append(f"{len(sections['fix'])} bug fix(es)")
        if "content" in sections:
            parts.append(f"{len(sections['content'])} content update(s)")
        return ", ".join(parts) if parts else "Maintenance update"


class ChangelogFormatter:
    """Format changelog entries for different outputs."""

    _SECTION_TITLES = {
        "feature": "New Features",
        "improvement": "Improvements",
        "fix": "Bug Fixes",
        "content": "New Content",
    }

    def format_markdown(self, entry: ChangelogEntry) -> str:
        lines = [f"## {entry.date}"]
        if entry.summary:
            lines.append(f"\n{entry.summary}\n")
        for cat_val, items in entry.sections.items():
            title = self._SECTION_TITLES.get(cat_val, cat_val.title())
            lines.append(f"\n### {title}\n")
            for item in items:
                lines.append(f"- {item}")
        return "\n".join(lines)

    def format_html(self, entry: ChangelogEntry) -> str:
        parts = [f'<div class="changelog-entry"><h2>{entry.date}</h2>']
        if entry.summary:
            parts.append(f"<p>{entry.summary}</p>")
        for cat_val, items in entry.sections.items():
            title = self._SECTION_TITLES.get(cat_val, cat_val.title())
            parts.append(f"<h3>{title}</h3><ul>")
            for item in items:
                parts.append(f"<li>{item}</li>")
            parts.append("</ul>")
        parts.append("</div>")
        return "\n".join(parts)

    def format_plain(self, entry: ChangelogEntry) -> str:
        lines = [entry.date, entry.summary, ""]
        for cat_val, items in entry.sections.items():
            title = self._SECTION_TITLES.get(cat_val, cat_val.title())
            lines.append(f"{title}:")
            for item in items:
                lines.append(f"  - {item}")
            lines.append("")
        return "\n".join(lines)


class ChangelogManager:
    """Main interface for changelog generation."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self.parser = CommitParser()
        self.classifier = ChangeClassifier()
        self.drafter = ChangelogDrafter()
        self.formatter = ChangelogFormatter()

    def generate(self, since: str = "1 week ago") -> Optional[ChangelogEntry]:
        commits = self.parser.parse_recent(self.repo_path, since)
        if not commits:
            return None

        classifications = [self.classifier.classify(c) for c in commits]
        has_user_facing = any(self.classifier.is_user_facing(c) for c in classifications)
        if not has_user_facing:
            return None

        return self.drafter.draft_entry(commits, classifications)

    def queue_for_review(self, conn, entry: ChangelogEntry):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS changelog_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, summary TEXT, sections_json TEXT,
                commit_count INTEGER, status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                approved_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO changelog_queue (date, summary, sections_json, commit_count) VALUES (?, ?, ?, ?)",
            (entry.date, entry.summary, json.dumps(entry.sections), entry.commit_count),
        )
        conn.commit()

    def get_pending(self, conn) -> list[dict]:
        try:
            rows = conn.execute(
                "SELECT * FROM changelog_queue WHERE status = 'pending' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def approve_and_publish(self, conn, entry_id: int) -> dict:
        try:
            row = conn.execute(
                "SELECT * FROM changelog_queue WHERE id = ?", (entry_id,)
            ).fetchone()
            if not row:
                return {"error": "not found"}
            conn.execute(
                "UPDATE changelog_queue SET status = 'published', approved_at = datetime('now') WHERE id = ?",
                (entry_id,),
            )
            conn.commit()
            sections = json.loads(row["sections_json"] or "{}")
            entry = ChangelogEntry(
                date=row["date"], version_hint="", sections=sections,
                summary=row["summary"], commit_count=row["commit_count"],
            )
            return {
                "markdown": self.formatter.format_markdown(entry),
                "html": self.formatter.format_html(entry),
                "plain": self.formatter.format_plain(entry),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_published(self, conn, limit: int = 10) -> list[dict]:
        try:
            rows = conn.execute(
                "SELECT * FROM changelog_queue WHERE status = 'published' ORDER BY approved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


# json import needed for queue_for_review
import json  # noqa: E402
