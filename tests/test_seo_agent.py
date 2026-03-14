"""Tests for mandarin.openclaw.seo_agent — keywords, content drafting, SEO metadata, calendar."""

import sqlite3
import unittest

from mandarin.openclaw.seo_agent import (
    BlogDraft,
    ContentCalendar,
    ContentDrafter,
    ForumThread,
    KeywordResearcher,
    KeywordTarget,
    PlannedPost,
    SEOManager,
    SEOMetadataGenerator,
    TopicResearcher,
)


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── Dataclass construction ────────────────────────────────

class TestKeywordTarget(unittest.TestCase):
    def test_construction(self):
        kw = KeywordTarget("test keyword", "high", "low", "informational", 0.9, "test_cluster")
        self.assertEqual(kw.keyword, "test keyword")
        self.assertEqual(kw.search_volume, "high")
        self.assertEqual(kw.cluster, "test_cluster")

    def test_default_cluster(self):
        kw = KeywordTarget("k", "low", "low", "informational", 0.5)
        self.assertEqual(kw.cluster, "")


class TestForumThread(unittest.TestCase):
    def test_construction(self):
        ft = ForumThread("reddit", "title", "url", "q", "good", "angle")
        self.assertEqual(ft.source, "reddit")
        self.assertEqual(ft.answer_quality, "good")


class TestBlogDraft(unittest.TestCase):
    def test_defaults(self):
        bd = BlogDraft("Title", "slug", "meta", ["h1", "h2"], "body", 100, "kw")
        self.assertEqual(bd.internal_links, [])


class TestPlannedPost(unittest.TestCase):
    def test_construction(self):
        kw = KeywordTarget("k", "low", "low", "informational", 0.5, "c")
        pp = PlannedPost(week=1, topic=kw, post_type="how_to", priority=3.0, estimated_impact="high")
        self.assertEqual(pp.week, 1)
        self.assertEqual(pp.post_type, "how_to")


# ── KeywordResearcher ─────────────────────────────────────

class TestKeywordResearcher(unittest.TestCase):
    def setUp(self):
        self.r = KeywordResearcher()

    def test_at_least_40_keywords(self):
        kws = self.r.get_target_keywords()
        self.assertGreaterEqual(len(kws), 40)

    def test_all_keywords_have_cluster(self):
        for kw in self.r.get_target_keywords():
            self.assertNotEqual(kw.cluster, "", f"Keyword '{kw.keyword}' has no cluster")

    def test_clusters_present(self):
        clusters = self.r.get_clusters()
        expected = {"hsk_prep", "method", "comparison", "pain_points", "advanced"}
        self.assertEqual(set(clusters.keys()), expected)

    def test_cluster_sizes(self):
        clusters = self.r.get_clusters()
        for name, items in clusters.items():
            self.assertGreater(len(items), 0, f"Cluster {name} is empty")

    def test_find_content_gaps_empty_existing(self):
        gaps = self.r.find_content_gaps([])
        self.assertEqual(len(gaps), len(self.r.keywords))

    def test_find_content_gaps_with_coverage(self):
        # Slug that covers "hsk-1-study-plan"
        gaps = self.r.find_content_gaps(["hsk-1-study-plan"])
        covered = [g for g in gaps if g.keyword == "HSK 1 study plan"]
        self.assertEqual(len(covered), 0)

    def test_prioritize_returns_all(self):
        prioritized = self.r.prioritize()
        self.assertEqual(len(prioritized), len(self.r.keywords))

    def test_prioritize_order(self):
        prioritized = self.r.prioritize()
        # Top item should have high relevance or volume
        top = prioritized[0]
        self.assertGreaterEqual(top.aelu_relevance, 0.8)

    def test_all_intents_valid(self):
        for kw in self.r.get_target_keywords():
            self.assertIn(kw.intent, ("informational", "transactional", "navigational"))

    def test_all_volumes_valid(self):
        for kw in self.r.get_target_keywords():
            self.assertIn(kw.search_volume, ("high", "medium", "low"))

    def test_all_difficulties_valid(self):
        for kw in self.r.get_target_keywords():
            self.assertIn(kw.difficulty, ("high", "medium", "low"))


# ── TopicResearcher ───────────────────────────────────────

class TestTopicResearcher(unittest.TestCase):
    def test_sources_exist(self):
        tr = TopicResearcher()
        sources = tr.get_sources()
        self.assertGreater(len(sources), 0)
        self.assertTrue(all("name" in s for s in sources))

    def test_research_forums_returns_threads(self):
        tr = TopicResearcher()
        threads = tr.research_forums()
        self.assertGreater(len(threads), 0)
        self.assertIsInstance(threads[0], ForumThread)


# ── ContentDrafter ────────────────────────────────────────

class TestContentDrafter(unittest.TestCase):
    def setUp(self):
        self.drafter = ContentDrafter()
        self.topic = KeywordTarget("Chinese tone practice", "medium", "medium",
                                    "informational", 0.95, "method")

    def test_draft_blog_post_structure(self):
        draft = self.drafter.draft_blog_post(self.topic)
        self.assertIsInstance(draft, BlogDraft)
        self.assertIn("tone", draft.title.lower())
        self.assertGreater(len(draft.outline), 0)
        self.assertGreater(draft.word_count, 0)
        self.assertEqual(draft.target_keyword, "Chinese tone practice")

    def test_slug_format(self):
        draft = self.drafter.draft_blog_post(self.topic)
        self.assertNotIn(" ", draft.slug)
        self.assertTrue(draft.slug.replace("-", "").replace(".", "").isalnum())

    def test_meta_description_length(self):
        draft = self.drafter.draft_blog_post(self.topic)
        self.assertLessEqual(len(draft.meta_description), 160)

    def test_title_length(self):
        draft = self.drafter.draft_blog_post(self.topic)
        self.assertLessEqual(len(draft.title), 60)

    def test_outline_has_introduction(self):
        outline = self.drafter._generate_outline(self.topic)
        self.assertTrue(any("introduction" in h.lower() for h in outline))

    def test_internal_links(self):
        draft = self.drafter.draft_blog_post(self.topic)
        self.assertIn("/pricing", draft.internal_links)

    def test_very_long_keyword_title_truncated(self):
        long_kw = KeywordTarget("x" * 100, "low", "low", "informational", 0.5, "c")
        draft = self.drafter.draft_blog_post(long_kw)
        self.assertLessEqual(len(draft.title), 60)


# ── SEOMetadataGenerator ─────────────────────────────────

class TestSEOMetadataGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = SEOMetadataGenerator()

    def test_blog_post_meta(self):
        meta = self.gen.generate_page_meta("blog_post", title="My Post", date="2026-03-10")
        self.assertIn("title", meta)
        self.assertIn("structured_data", meta)
        self.assertEqual(meta["structured_data"]["@type"], "BlogPosting")

    def test_software_meta(self):
        meta = self.gen.generate_page_meta("software")
        sd = meta["structured_data"]
        self.assertEqual(sd["@type"], "SoftwareApplication")
        self.assertEqual(sd["name"], "Aelu")

    def test_faq_meta(self):
        meta = self.gen.generate_page_meta("faq", questions=[{"q": "test"}])
        self.assertEqual(meta["structured_data"]["@type"], "FAQPage")

    def test_unknown_page_type(self):
        meta = self.gen.generate_page_meta("unknown_type")
        self.assertEqual(meta["structured_data"]["@type"], "WebPage")

    def test_title_truncation(self):
        long_title = "A" * 100
        meta = self.gen.generate_page_meta("blog_post", title=long_title)
        self.assertLessEqual(len(meta["title"]), 60)
        self.assertTrue(meta["title"].endswith("..."))

    def test_description_truncation(self):
        long_desc = "B" * 200
        meta = self.gen.generate_page_meta("blog_post", description=long_desc)
        self.assertLessEqual(len(meta["description"]), 160)


# ── ContentCalendar ───────────────────────────────────────

class TestContentCalendar(unittest.TestCase):
    def test_plan_month_returns_4_posts(self):
        cal = ContentCalendar()
        posts = cal.plan_month()
        self.assertEqual(len(posts), 4)

    def test_plan_month_weeks_1_to_4(self):
        cal = ContentCalendar()
        posts = cal.plan_month()
        weeks = [p.week for p in posts]
        self.assertEqual(weeks, [1, 2, 3, 4])

    def test_plan_month_post_types(self):
        cal = ContentCalendar()
        posts = cal.plan_month()
        types = {p.post_type for p in posts}
        self.assertIn("how_to", types)

    def test_plan_month_with_existing_coverage(self):
        cal = ContentCalendar()
        posts = cal.plan_month(existing_posts=["hsk-1-study-plan"])
        # Should still return 4 posts, but HSK 1 study plan shouldn't be the topic
        self.assertEqual(len(posts), 4)


# ── SEOManager (integration) ─────────────────────────────

class TestSEOManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SEOManager()

    def test_audit_current_content(self):
        audit = self.mgr.audit_current_content()
        self.assertGreaterEqual(audit["total_keywords"], 40)
        self.assertIn("clusters", audit)
        self.assertIn("top_opportunities", audit)
        self.assertLessEqual(len(audit["top_opportunities"]), 5)

    def test_generate_content_plan(self):
        plan = self.mgr.generate_content_plan()
        self.assertEqual(len(plan), 4)

    def test_draft_post_existing_keyword(self):
        draft = self.mgr.draft_post("spaced repetition Chinese")
        self.assertIsNotNone(draft)
        self.assertIsInstance(draft, BlogDraft)

    def test_draft_post_nonexistent_keyword(self):
        draft = self.mgr.draft_post("nonexistent keyword xyz")
        self.assertIsNone(draft)

    def test_queue_and_retrieve(self):
        conn = _make_conn()
        draft = self.mgr.draft_post("spaced repetition Chinese")
        self.mgr.queue_for_review(conn, draft)
        pending = self.mgr.get_pending_drafts(conn)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "pending")

    def test_approve_draft(self):
        conn = _make_conn()
        draft = self.mgr.draft_post("Chinese tone practice")
        self.mgr.queue_for_review(conn, draft)
        pending = self.mgr.get_pending_drafts(conn)
        result = self.mgr.approve_draft(conn, pending[0]["id"])
        self.assertEqual(result["status"], "approved")

    def test_get_pending_no_table(self):
        conn = _make_conn()
        result = self.mgr.get_pending_drafts(conn)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
