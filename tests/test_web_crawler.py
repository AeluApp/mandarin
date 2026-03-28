"""Tests for Doc 23 A-05: Automated Web Crawling."""

import pytest
pytest.importorskip("httpx")

import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.web_crawler import (
    crawl_source,
    extract_competitor_signals,
    extract_research_signals,
    get_sources_due_for_crawl,
    seed_crawl_sources,
)


from tests.shared_db import make_test_db as _make_db


class TestSeedCrawlSources(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_seed_creates_sources(self):
        count = seed_crawl_sources(self.conn)
        self.assertEqual(count, 3)

    def test_seed_is_idempotent(self):
        seed_crawl_sources(self.conn)
        count = seed_crawl_sources(self.conn)
        self.assertEqual(count, 0)


class TestGetSourcesDue(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_new_source_is_due(self):
        self.conn.execute("""
            INSERT INTO crawl_source (name, url, source_type)
            VALUES ('Test', 'https://example.com', 'competitor')
        """)
        sources = get_sources_due_for_crawl(self.conn)
        self.assertEqual(len(sources), 1)

    def test_recently_crawled_not_due(self):
        self.conn.execute("""
            INSERT INTO crawl_source (name, url, source_type, last_crawl_at)
            VALUES ('Test', 'https://example.com', 'competitor', datetime('now'))
        """)
        sources = get_sources_due_for_crawl(self.conn)
        self.assertEqual(len(sources), 0)

    def test_inactive_source_excluded(self):
        self.conn.execute("""
            INSERT INTO crawl_source (name, url, source_type, active)
            VALUES ('Test', 'https://example.com', 'competitor', 0)
        """)
        sources = get_sources_due_for_crawl(self.conn)
        self.assertEqual(len(sources), 0)


class TestExtractCompetitorSignals(unittest.TestCase):
    def test_extract_from_html(self):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            self.skipTest("beautifulsoup4 not installed")

        html = """
        <html><body>
            <article class="post">
                <h2><a href="https://example.com/new-feature">Introducing New Feature</a></h2>
                <p>We're excited to launch our new writing practice mode.</p>
            </article>
            <article class="post">
                <h3>Update to Our Pricing Plans</h3>
                <p>Check out our new pricing tiers.</p>
            </article>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        signals = extract_competitor_signals(soup, "test_source")
        self.assertGreaterEqual(len(signals), 1)
        # Check that signal types are classified
        types = {s["signal_type"] for s in signals}
        self.assertTrue(len(types) > 0)

    def test_empty_html(self):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            self.skipTest("beautifulsoup4 not installed")
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        signals = extract_competitor_signals(soup, "test")
        self.assertEqual(signals, [])

    def test_none_soup(self):
        signals = extract_competitor_signals(None, "test")
        self.assertEqual(signals, [])


class TestExtractResearchSignals(unittest.TestCase):
    def test_extract_from_rss(self):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            self.skipTest("beautifulsoup4 not installed")

        rss = """
        <rss>
            <item>
                <title>Improved Spaced Repetition via Neural Networks</title>
                <description>We propose a new method for scheduling reviews.</description>
                <id>https://arxiv.org/abs/2024.12345</id>
            </item>
        </rss>
        """
        soup = BeautifulSoup(rss, "html.parser")
        signals = extract_research_signals(soup, "arxiv")
        self.assertEqual(len(signals), 1)
        self.assertIn("Spaced Repetition", signals[0]["title"])

    def test_none_soup(self):
        signals = extract_research_signals(None, "test")
        self.assertEqual(signals, [])


class TestCrawlSource(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_inactive_source_error(self):
        result = crawl_source(self.conn, 9999)
        self.assertEqual(result["status"], "error")

    def test_bs4_not_installed(self):
        self.conn.execute("""
            INSERT INTO crawl_source (name, url, source_type)
            VALUES ('Test', 'https://example.com', 'competitor')
        """)
        with patch("mandarin.ai.web_crawler.BeautifulSoup", None):
            result = crawl_source(self.conn, 1)
            self.assertEqual(result["status"], "error")
            self.assertIn("beautifulsoup4", result["error"])


if __name__ == "__main__":
    unittest.main()
