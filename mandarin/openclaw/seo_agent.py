"""SEO and content marketing automation.

Research what serious Mandarin learners ask online, draft SEO content
answering those questions, position Aelu's approach. Compounds over time.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class KeywordTarget:
    keyword: str
    search_volume: str  # high, medium, low
    difficulty: str  # high, medium, low
    intent: str  # informational, transactional, navigational
    aelu_relevance: float  # 0-1
    cluster: str = ""


@dataclass
class ForumThread:
    source: str
    title: str
    url: str
    question_summary: str
    answer_quality: str  # good, partial, unanswered
    aelu_angle: str


@dataclass
class BlogDraft:
    title: str
    slug: str
    meta_description: str
    outline: list[str]
    body_markdown: str
    word_count: int
    target_keyword: str
    internal_links: list[str] = field(default_factory=list)


@dataclass
class PlannedPost:
    week: int
    topic: KeywordTarget
    post_type: str  # how_to, comparison, guide, case_study
    priority: float
    estimated_impact: str  # high, medium, low


# ── Seed keyword database ─────────────────────────────────

_SEED_KEYWORDS = [
    # HSK prep cluster
    KeywordTarget("HSK 1 study plan", "medium", "low", "informational", 0.95, "hsk_prep"),
    KeywordTarget("HSK 2 vocabulary list", "medium", "low", "informational", 0.9, "hsk_prep"),
    KeywordTarget("HSK 3 vocabulary list", "medium", "medium", "informational", 0.9, "hsk_prep"),
    KeywordTarget("HSK 4 exam preparation", "medium", "medium", "informational", 0.85, "hsk_prep"),
    KeywordTarget("HSK 5 study guide", "low", "medium", "informational", 0.85, "hsk_prep"),
    KeywordTarget("HSK exam tips", "medium", "medium", "informational", 0.8, "hsk_prep"),
    KeywordTarget("how to pass HSK 3", "medium", "low", "informational", 0.9, "hsk_prep"),
    KeywordTarget("HSK vocabulary app", "medium", "high", "transactional", 0.95, "hsk_prep"),

    # Method cluster
    KeywordTarget("best way to learn Chinese characters", "high", "high", "informational", 0.9, "method"),
    KeywordTarget("spaced repetition Chinese", "medium", "medium", "informational", 0.95, "method"),
    KeywordTarget("Chinese tone practice", "medium", "medium", "informational", 0.95, "method"),
    KeywordTarget("how to remember Chinese characters", "high", "high", "informational", 0.9, "method"),
    KeywordTarget("learn Mandarin as adult", "medium", "medium", "informational", 0.95, "method"),
    KeywordTarget("Chinese character memorization techniques", "medium", "medium", "informational", 0.85, "method"),
    KeywordTarget("Mandarin pronunciation practice", "medium", "medium", "informational", 0.9, "method"),
    KeywordTarget("Chinese reading practice intermediate", "low", "low", "informational", 0.9, "method"),

    # Comparison cluster
    KeywordTarget("Duolingo Chinese review", "high", "high", "informational", 0.8, "comparison"),
    KeywordTarget("HelloChinese vs Anki", "low", "low", "informational", 0.85, "comparison"),
    KeywordTarget("best Chinese learning app 2026", "high", "high", "transactional", 0.95, "comparison"),
    KeywordTarget("Anki alternative Chinese", "medium", "medium", "transactional", 0.95, "comparison"),
    KeywordTarget("serious Chinese learning app", "medium", "medium", "transactional", 0.95, "comparison"),
    KeywordTarget("Chinese app for serious learners", "low", "low", "transactional", 0.95, "comparison"),
    KeywordTarget("Hack Chinese review", "low", "low", "informational", 0.8, "comparison"),
    KeywordTarget("Pleco vs Anki", "low", "low", "informational", 0.7, "comparison"),

    # Pain points cluster
    KeywordTarget("Chinese tones difficult", "medium", "low", "informational", 0.9, "pain_points"),
    KeywordTarget("forgetting Chinese characters", "medium", "low", "informational", 0.95, "pain_points"),
    KeywordTarget("Chinese learning plateau", "medium", "medium", "informational", 0.9, "pain_points"),
    KeywordTarget("why Chinese is hard", "high", "high", "informational", 0.7, "pain_points"),
    KeywordTarget("frustrated learning Chinese", "low", "low", "informational", 0.85, "pain_points"),
    KeywordTarget("Chinese characters overwhelming", "low", "low", "informational", 0.9, "pain_points"),
    KeywordTarget("stop forgetting vocabulary", "medium", "medium", "informational", 0.85, "pain_points"),
    KeywordTarget("language learning motivation", "medium", "high", "informational", 0.6, "pain_points"),

    # Advanced cluster
    KeywordTarget("Chinese reading practice", "medium", "medium", "informational", 0.9, "advanced"),
    KeywordTarget("Chinese listening comprehension", "medium", "medium", "informational", 0.9, "advanced"),
    KeywordTarget("business Chinese vocabulary", "medium", "medium", "informational", 0.8, "advanced"),
    KeywordTarget("Chinese grammar patterns", "medium", "medium", "informational", 0.9, "advanced"),
    KeywordTarget("intermediate Chinese study plan", "low", "low", "informational", 0.9, "advanced"),
    KeywordTarget("Chinese conversation practice", "medium", "medium", "informational", 0.85, "advanced"),
    KeywordTarget("Chinese measure words list", "medium", "low", "informational", 0.85, "advanced"),
    KeywordTarget("Chinese sentence patterns", "medium", "medium", "informational", 0.9, "advanced"),
]


class KeywordResearcher:
    """Research and manage target keywords."""

    def __init__(self):
        self.keywords = list(_SEED_KEYWORDS)

    def get_target_keywords(self) -> list[KeywordTarget]:
        return self.keywords

    def get_clusters(self) -> dict[str, list[KeywordTarget]]:
        clusters: dict[str, list[KeywordTarget]] = {}
        for kw in self.keywords:
            clusters.setdefault(kw.cluster, []).append(kw)
        return clusters

    def find_content_gaps(self, existing_slugs: list[str]) -> list[KeywordTarget]:
        covered = set(s.lower().replace("-", " ") for s in existing_slugs)
        return [
            kw for kw in self.keywords
            if not any(kw.keyword.lower() in c for c in covered)
        ]

    def prioritize(self) -> list[KeywordTarget]:
        vol_map = {"high": 3, "medium": 2, "low": 1}
        diff_map = {"low": 3, "medium": 2, "high": 1}

        def score(kw):
            return vol_map.get(kw.search_volume, 1) * kw.aelu_relevance * diff_map.get(kw.difficulty, 1)

        return sorted(self.keywords, key=score, reverse=True)


class TopicResearcher:
    """Research forum topics for content ideas."""

    _FORUM_SOURCES = [
        {"name": "r/ChineseLanguage", "url": "https://reddit.com/r/ChineseLanguage", "type": "reddit"},
        {"name": "r/languagelearning", "url": "https://reddit.com/r/languagelearning", "type": "reddit"},
        {"name": "Chinese-Forums.com", "url": "https://chinese-forums.com", "type": "forum"},
        {"name": "HackChinese Community", "url": "https://community.hackchinese.com", "type": "forum"},
    ]

    def get_sources(self) -> list[dict]:
        return self._FORUM_SOURCES

    def research_forums(self) -> list[ForumThread]:
        """Return structured forum research. In production, this would use web scraping."""
        # Built-in seed threads representing common questions
        return [
            ForumThread("r/ChineseLanguage", "Best way to practice tones alone?",
                        "", "Looking for apps that help with tone recognition and production",
                        "partial", "Aelu's tone grading with Parselmouth addresses this directly"),
            ForumThread("r/ChineseLanguage", "HSK 3 to HSK 4 feels impossible",
                        "", "The jump in difficulty between HSK 3 and 4 vocabulary",
                        "partial", "Aelu's adaptive scheduling smooths this transition"),
            ForumThread("r/languagelearning", "SRS for Chinese - Anki too much setup",
                        "", "Want spaced repetition but Anki requires too much manual configuration",
                        "good", "Aelu provides curated SRS without the setup overhead"),
        ]


class ContentDrafter:
    """Draft blog posts targeting keywords."""

    def draft_blog_post(
        self, topic: KeywordTarget, research: list[ForumThread] | None = None
    ) -> BlogDraft:
        outline = self._generate_outline(topic)
        title, meta = self._generate_meta(topic)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

        body = self._generate_body(topic, outline, research)
        word_count = len(body.split())

        return BlogDraft(
            title=title, slug=slug, meta_description=meta,
            outline=outline, body_markdown=body, word_count=word_count,
            target_keyword=topic.keyword,
            internal_links=["/pricing", "/about"],
        )

    def _generate_outline(self, topic: KeywordTarget) -> list[str]:
        base = [
            f"Introduction: Why {topic.keyword} matters",
            "The core challenge",
            "What actually works (evidence-based)",
            "How Aelu approaches this",
            "Practical tips you can use today",
            "Next steps",
        ]
        return base

    def _generate_meta(self, topic: KeywordTarget) -> tuple[str, str]:
        title = f"{topic.keyword.title()} — A Practical Guide | Aelu"
        if len(title) > 60:
            title = title[:57] + "..."
        meta = f"Learn about {topic.keyword} with evidence-based approaches. Practical advice for serious Mandarin learners."
        if len(meta) > 160:
            meta = meta[:157] + "..."
        return title, meta

    def _generate_body(
        self, topic: KeywordTarget, outline: list[str],
        research: list[ForumThread] | None = None,
    ) -> str:
        sections = []
        for heading in outline:
            sections.append(f"## {heading}\n\n[Content for: {heading}]\n")
        return "\n".join(sections)


class SEOMetadataGenerator:
    """Generate SEO metadata and structured data."""

    def generate_page_meta(self, page_type: str, **kwargs) -> dict:
        title = kwargs.get("title", "Aelu — Serious Mandarin Learning")
        description = kwargs.get("description", "Evidence-based Mandarin learning for serious adult learners.")

        if len(title) > 60:
            title = title[:57] + "..."
        if len(description) > 160:
            description = description[:157] + "..."

        return {
            "title": title,
            "description": description,
            "og_title": title,
            "og_description": description,
            "canonical_url": kwargs.get("url", ""),
            "structured_data": self.generate_structured_data(page_type, **kwargs),
        }

    def generate_structured_data(self, page_type: str, **kwargs) -> dict:
        if page_type == "blog_post":
            return {
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": kwargs.get("title", ""),
                "description": kwargs.get("description", ""),
                "author": {"@type": "Organization", "name": "Aelu"},
                "publisher": {"@type": "Organization", "name": "Aelu"},
                "datePublished": kwargs.get("date", ""),
            }
        if page_type == "software":
            return {
                "@context": "https://schema.org",
                "@type": "SoftwareApplication",
                "name": "Aelu",
                "applicationCategory": "EducationalApplication",
                "operatingSystem": "iOS, Android, Web, macOS",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            }
        if page_type == "faq":
            return {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": kwargs.get("questions", []),
            }
        return {"@context": "https://schema.org", "@type": "WebPage"}


class ContentCalendar:
    """Plan monthly content calendar."""

    def plan_month(self, existing_posts: list[str] | None = None) -> list[PlannedPost]:
        researcher = KeywordResearcher()
        gaps = researcher.find_content_gaps(existing_posts or [])
        prioritized = sorted(
            gaps,
            key=lambda k: ({"high": 3, "medium": 2, "low": 1}.get(k.search_volume, 1)
                           * k.aelu_relevance
                           * {"low": 3, "medium": 2, "high": 1}.get(k.difficulty, 1)),
            reverse=True,
        )

        posts = []
        types = ["how_to", "comparison", "guide", "how_to"]
        for i, topic in enumerate(prioritized[:4]):
            posts.append(PlannedPost(
                week=i + 1, topic=topic,
                post_type=types[i % len(types)],
                priority=4 - i,
                estimated_impact="high" if i < 2 else "medium",
            ))
        return posts


class SEOManager:
    """Main interface for SEO content management."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self.researcher = KeywordResearcher()
        self.drafter = ContentDrafter()
        self.metadata = SEOMetadataGenerator()
        self.calendar = ContentCalendar()

    def audit_current_content(self) -> dict:
        clusters = self.researcher.get_clusters()
        return {
            "total_keywords": len(self.researcher.keywords),
            "clusters": {k: len(v) for k, v in clusters.items()},
            "top_opportunities": [
                {"keyword": kw.keyword, "relevance": kw.aelu_relevance}
                for kw in self.researcher.prioritize()[:5]
            ],
        }

    def generate_content_plan(self) -> list[PlannedPost]:
        return self.calendar.plan_month()

    def draft_post(self, keyword: str) -> BlogDraft | None:
        target = next((k for k in self.researcher.keywords if k.keyword == keyword), None)
        if not target:
            return None
        return self.drafter.draft_blog_post(target)

    def queue_for_review(self, conn, draft: BlogDraft):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, slug TEXT, meta_description TEXT,
                body_markdown TEXT, target_keyword TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                approved_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO content_queue (title, slug, meta_description, body_markdown, target_keyword) VALUES (?, ?, ?, ?, ?)",
            (draft.title, draft.slug, draft.meta_description, draft.body_markdown, draft.target_keyword),
        )
        conn.commit()

    def get_pending_drafts(self, conn) -> list[dict]:
        try:
            rows = conn.execute(
                "SELECT * FROM content_queue WHERE status = 'pending' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def approve_draft(self, conn, draft_id: int) -> dict:
        try:
            conn.execute(
                "UPDATE content_queue SET status = 'approved', approved_at = datetime('now') WHERE id = ?",
                (draft_id,),
            )
            conn.commit()
            return {"status": "approved", "id": draft_id}
        except Exception as e:
            return {"error": str(e)}
