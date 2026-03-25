"""App store and directory listing automation.

Research, prepare, and track submissions to every relevant app directory,
product listing site, and educational software registry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Directory:
    name: str
    url: str
    category: str  # app_store, product_hunt, edtech, language, university, review_site, developer
    submission_url: str = ""
    requirements: list[str] = field(default_factory=list)
    priority: int = 3  # 1-5, 1=highest
    status: str = "not_submitted"
    submitted_date: str = ""
    listed_date: str = ""


@dataclass
class ListingCopy:
    title: str
    short_description: str  # max 80 chars
    description: str
    keywords: list[str]
    categories: list[str]
    screenshots_needed: list[str]
    icon_spec: str = "1024x1024 PNG, 漫 character in terracotta on warm stone"


@dataclass
class Review:
    platform: str
    rating: int
    text: str
    date: str
    responded: bool = False
    response: str = ""


# ── Directory database ────────────────────────────────────

_DIRECTORIES = [
    # App stores (priority 1)
    Directory("Apple App Store", "https://apps.apple.com", "app_store",
              "https://appstoreconnect.apple.com", ["iOS build", "screenshots", "privacy policy"], 1),
    Directory("Google Play Store", "https://play.google.com", "app_store",
              "https://play.google.com/console", ["Android build", "screenshots", "privacy policy"], 1),
    Directory("Mac App Store", "https://apps.apple.com/mac", "app_store",
              "https://appstoreconnect.apple.com", ["macOS build", "screenshots"], 2),

    # Product discovery (priority 2)
    Directory("ProductHunt", "https://producthunt.com", "product_hunt",
              "https://producthunt.com/posts/new", ["maker account", "tagline", "gallery images"], 1),
    Directory("AlternativeTo", "https://alternativeto.net", "product_hunt",
              "https://alternativeto.net/submit/", ["description", "category tags"], 2),
    Directory("Slant", "https://slant.co", "product_hunt", "", ["comparison-ready description"], 3),
    Directory("G2", "https://g2.com", "product_hunt",
              "https://sell.g2.com", ["business profile", "category selection"], 2),
    Directory("Capterra", "https://capterra.com", "product_hunt",
              "https://vendors.capterra.com", ["vendor profile", "screenshots"], 2),

    # EdTech (priority 2)
    Directory("EdSurge", "https://edsurge.com", "edtech",
              "https://edsurge.com/product-reviews", ["product profile"], 2),
    Directory("Class Central", "https://classcentral.com", "edtech",
              "https://classcentral.com/submit", ["course/tool description"], 3),
    Directory("eLearning Industry", "https://elearningindustry.com", "edtech",
              "https://elearningindustry.com/directory", ["directory listing"], 3),
    Directory("Educational App Store", "https://educationalappstore.com", "edtech",
              "https://educationalappstore.com/submit", ["review submission"], 2),
    Directory("Common Sense Education", "https://commonsense.org/education", "edtech",
              "", ["educator review", "age rating"], 2),

    # Language learning (priority 2)
    Directory("All Language Resources", "https://alllanguageresources.com", "language",
              "https://alllanguageresources.com/submit", ["tool profile"], 2),
    Directory("Language Learners Forum", "https://forum.language-learners.org", "language",
              "", ["community post"], 3),
    Directory("Mandarin Blueprint Directory", "https://mandarinblueprint.com", "language",
              "", ["partnership inquiry"], 3),
    Directory("FluentU Alternatives List", "https://fluentu.com", "language", "", ["comparison listing"], 4),
    Directory("Lingvist Alternatives", "https://lingvist.com", "language", "", ["comparison listing"], 4),

    # University / institutional (priority 3)
    Directory("EDUCAUSE", "https://educause.edu", "university",
              "", ["institutional profile", "LTI support documentation"], 3),
    Directory("IMS Global", "https://imsglobal.org", "university",
              "", ["LTI certification"], 3),
    Directory("University Software Portals", "https://example.edu/software", "university",
              "", ["institutional pricing", "FERPA compliance doc"], 3),

    # Review sites (priority 3)
    Directory("TrustPilot", "https://trustpilot.com", "review_site",
              "https://business.trustpilot.com", ["business profile"], 3),
    Directory("PCMag", "https://pcmag.com", "review_site", "", ["press kit", "review request"], 4),
    Directory("TechRadar", "https://techradar.com", "review_site", "", ["press kit"], 4),
    Directory("Wirecutter", "https://nytimes.com/wirecutter", "review_site", "", ["review submission"], 5),

    # Developer / open source (priority 4)
    Directory("GitHub Topics", "https://github.com/topics", "developer",
              "", ["topic tags on repo"], 4),
    Directory("awesome-chinese-nlp", "https://github.com/crownpku/awesome-chinese-nlp", "developer",
              "", ["PR to awesome list"], 4),
    Directory("Hacker News Show HN", "https://news.ycombinator.com", "developer",
              "", ["Show HN post"], 3),
    Directory("IndieHackers", "https://indiehackers.com", "developer",
              "https://indiehackers.com/products", ["product profile"], 3),
    Directory("BetaList", "https://betalist.com", "developer",
              "https://betalist.com/submit", ["startup profile", "landing page"], 2),
]


class DirectoryRegistry:
    """Comprehensive database of listing directories."""

    def __init__(self):
        self.directories = list(_DIRECTORIES)

    def get_directories(self) -> list[Directory]:
        return self.directories

    def get_by_category(self, category: str) -> list[Directory]:
        return [d for d in self.directories if d.category == category]

    def get_categories(self) -> list[str]:
        return sorted(set(d.category for d in self.directories))

    def get_by_priority(self, max_priority: int = 3) -> list[Directory]:
        return sorted(
            [d for d in self.directories if d.priority <= max_priority],
            key=lambda d: d.priority,
        )


class ListingCopyGenerator:
    """Generate platform-specific listing copy."""

    _AELU_TAGLINE = "Serious Mandarin learning for adults who want real results"
    _AELU_DESCRIPTION = (
        "Aelu is an evidence-based Mandarin learning system built for serious adult learners. "
        "Adaptive spaced repetition, tone grading with real audio analysis, 12 drill types, "
        "HSK 1-9 vocabulary, and a scheduler that adjusts to your life. No gamification gimmicks — "
        "just effective learning grounded in cognitive science."
    )

    def generate_listing(self, directory: Directory) -> ListingCopy:
        if directory.category == "product_hunt":
            return self._product_hunt_listing(directory)
        if directory.category == "app_store":
            return self._app_store_listing(directory)
        if directory.category == "edtech":
            return self._edtech_listing(directory)
        if directory.category == "review_site":
            return self._review_site_listing(directory)
        return self._default_listing(directory)

    def _product_hunt_listing(self, directory: Directory) -> ListingCopy:
        return ListingCopy(
            title="Aelu — Mandarin learning that respects your intelligence",
            short_description="Evidence-based Mandarin for serious adult learners",
            description=(
                f"{self._AELU_DESCRIPTION}\n\n"
                "Built by a learner, for learners. No streak anxiety, no fake points, "
                "no dumbed-down content. Just a system that adapts to you."
            ),
            keywords=["mandarin", "chinese", "language learning", "spaced repetition", "HSK"],
            categories=["Education", "Productivity"],
            screenshots_needed=["dashboard", "drill_session", "progress_report", "tone_grading"],
        )

    def _app_store_listing(self, directory: Directory) -> ListingCopy:
        return ListingCopy(
            title="Aelu: Learn Mandarin Chinese",
            short_description="Evidence-based Mandarin for serious learners",
            description=(
                f"{self._AELU_DESCRIPTION}\n\n"
                "FEATURES:\n"
                "- Adaptive spaced repetition (FSRS algorithm)\n"
                "- 12 drill types including tone grading\n"
                "- HSK 1-9 vocabulary (10,000+ items)\n"
                "- Reading passages and listening practice\n"
                "- Grammar pattern tracking\n"
                "- Offline support\n"
                "- No ads, no dark patterns"
            ),
            keywords=["mandarin", "chinese", "HSK", "spaced repetition", "tones", "vocabulary",
                       "language", "learning", "education"],
            categories=["Education", "Language Learning"],
            screenshots_needed=["home_screen", "drill_mc", "drill_tone", "progress", "settings"],
        )

    def _edtech_listing(self, directory: Directory) -> ListingCopy:
        return ListingCopy(
            title="Aelu — Adaptive Mandarin Learning Platform",
            short_description="Evidence-based Mandarin with institutional features",
            description=(
                f"{self._AELU_DESCRIPTION}\n\n"
                "INSTITUTIONAL FEATURES:\n"
                "- Classroom management with teacher dashboards\n"
                "- LTI 1.3 integration for LMS platforms\n"
                "- Student progress tracking and reporting\n"
                "- FERPA compliant data handling\n"
                "- Bulk enrollment and admin controls"
            ),
            keywords=["mandarin", "chinese", "edtech", "LTI", "FERPA", "classroom", "institutional"],
            categories=["Language Learning", "Higher Education", "K-12"],
            screenshots_needed=["admin_dashboard", "class_progress", "student_view", "teacher_reports"],
        )

    def _review_site_listing(self, directory: Directory) -> ListingCopy:
        return ListingCopy(
            title="Aelu",
            short_description="Mandarin learning app for serious adult learners",
            description=self._AELU_DESCRIPTION,
            keywords=["mandarin learning app", "chinese learning", "spaced repetition"],
            categories=["Education", "Language Learning"],
            screenshots_needed=["dashboard", "session", "progress"],
        )

    def _default_listing(self, directory: Directory) -> ListingCopy:
        return ListingCopy(
            title="Aelu — Serious Mandarin Learning",
            short_description=self._AELU_TAGLINE[:80],
            description=self._AELU_DESCRIPTION,
            keywords=["mandarin", "chinese", "language learning"],
            categories=["Education"],
            screenshots_needed=["dashboard", "session"],
        )


class SubmissionTracker:
    """Track directory submission status."""

    def __init__(self, conn=None):
        self.conn = conn
        if conn:
            self._ensure_table()

    def _ensure_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS directory_submission (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                directory_name TEXT UNIQUE, status TEXT DEFAULT 'not_submitted',
                listing_url TEXT, notes TEXT,
                submitted_at TEXT, listed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def get_submission_status(self) -> dict:
        if not self.conn:
            return {"error": "no connection"}
        try:
            rows = self.conn.execute(
                "SELECT status, COUNT(*) as cnt FROM directory_submission GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r["cnt"] for r in rows}
            return {
                "submitted": counts.get("submitted", 0),
                "pending": counts.get("pending", 0),
                "listed": counts.get("listed", 0),
                "rejected": counts.get("rejected", 0),
                "not_submitted": counts.get("not_submitted", 0),
            }
        except Exception:
            return {}

    def record_submission(self, directory_name: str, status: str, notes: str = ""):
        if not self.conn:
            return
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute("""
            INSERT INTO directory_submission (directory_name, status, notes, submitted_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(directory_name) DO UPDATE SET status = ?, notes = ?, submitted_at = ?
        """, (directory_name, status, notes, now, status, notes, now))
        self.conn.commit()

    def update_status(self, directory_name: str, status: str, listing_url: str = ""):
        if not self.conn:
            return
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute("""
            UPDATE directory_submission SET status = ?, listing_url = ?, listed_at = ?
            WHERE directory_name = ?
        """, (status, listing_url, now if status == "listed" else None, directory_name))
        self.conn.commit()

    def get_next_submissions(self, limit: int = 5) -> list[Directory]:
        registry = DirectoryRegistry()
        submitted = set()
        if self.conn:
            try:
                rows = self.conn.execute(
                    "SELECT directory_name FROM directory_submission WHERE status != 'not_submitted'"
                ).fetchall()
                submitted = {r["directory_name"] for r in rows}
            except Exception:
                pass

        unsubmitted = [d for d in registry.get_directories() if d.name not in submitted]
        return sorted(unsubmitted, key=lambda d: d.priority)[:limit]


class ReviewMonitor:
    """Monitor and respond to app reviews."""

    def get_unresponded_reviews(self) -> list[Review]:
        """Placeholder — in production, connects to App Store Connect / Play Console APIs."""
        return []

    def draft_response(self, review: Review) -> str:
        if review.rating >= 4:
            return f"Thank you for your kind review! We're glad Aelu is helping with your Mandarin learning."
        if review.rating >= 3:
            return (
                f"Thank you for the feedback. We're always looking to improve — "
                f"if there's something specific you'd like to see, please reach out to support@aelu.app."
            )
        return (
            f"We're sorry to hear about your experience. We'd like to help — "
            f"please email support@aelu.app with details and we'll look into it right away."
        )


class DirectoryManager:
    """Main interface for directory listing management."""

    def __init__(self, conn=None):
        self.registry = DirectoryRegistry()
        self.copy_gen = ListingCopyGenerator()
        self.tracker = SubmissionTracker(conn)
        self.reviewer = ReviewMonitor()

    def audit(self) -> dict:
        dirs = self.registry.get_directories()
        by_cat = {}
        for d in dirs:
            by_cat.setdefault(d.category, []).append(d.name)
        return {
            "total_directories": len(dirs),
            "by_category": {k: len(v) for k, v in by_cat.items()},
            "submission_status": self.tracker.get_submission_status(),
        }

    def prepare_submissions(self, limit: int = 5) -> list[dict]:
        next_dirs = self.tracker.get_next_submissions(limit)
        results = []
        for d in next_dirs:
            copy = self.copy_gen.generate_listing(d)
            results.append({
                "directory": d.name, "url": d.url, "category": d.category,
                "priority": d.priority, "requirements": d.requirements,
                "copy": {
                    "title": copy.title,
                    "short_description": copy.short_description,
                    "description": copy.description[:200] + "...",
                    "keywords": copy.keywords,
                },
            })
        return results

    def get_submission_checklist(self) -> list[dict]:
        dirs = self.registry.get_by_priority(3)
        return [
            {"directory": d.name, "category": d.category, "priority": d.priority,
             "requirements": d.requirements, "submission_url": d.submission_url}
            for d in dirs
        ]

    def track_submission(self, directory_name: str, status: str):
        self.tracker.record_submission(directory_name, status)

    def monitor_reviews(self) -> list[Review]:
        return self.reviewer.get_unresponded_reviews()
