#!/usr/bin/env python3
"""Ingest Chinese news articles from an RSS feed into reading passages.

Usage:
    python scripts/ingest_news.py <rss_url> [--hsk-max 3] [--limit 10] [--dry-run]

Fetches articles, extracts Chinese text, estimates HSK level using jieba +
HSK word frequency, and creates reading passage entries in the database.

Requires: feedparser, jieba, requests
    pip install feedparser jieba requests
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


# ── HSK word frequency data ──────────────────────────────────────────

# Built from HSK 3.0 standards; maps word → HSK level
_HSK_WORDS = {}
_HSK_LOADED = False


def _load_hsk_words(conn):
    """Load HSK word→level mapping from the content_item table."""
    global _HSK_WORDS, _HSK_LOADED
    if _HSK_LOADED:
        return
    try:
        rows = conn.execute(
            "SELECT hanzi, hsk_level FROM content_item WHERE hsk_level IS NOT NULL"
        ).fetchall()
        for r in rows:
            _HSK_WORDS[r["hanzi"]] = r["hsk_level"]
        _HSK_LOADED = True
        logger.info("Loaded %d HSK words for level estimation", len(_HSK_WORDS))
    except sqlite3.Error:
        logger.warning("Could not load HSK words from DB")


def estimate_hsk_level(text: str, conn=None) -> int:
    """Estimate HSK level of Chinese text using jieba segmentation.

    Returns estimated HSK level (1-9). Defaults to 3 if unable to estimate.
    """
    try:
        import jieba
    except ImportError:
        logger.warning("jieba not available; defaulting HSK level to 3")
        return 3

    if conn:
        _load_hsk_words(conn)

    if not _HSK_WORDS:
        return 3

    words = list(jieba.cut(text))
    if not words:
        return 1

    levels = []
    unknown_count = 0
    for w in words:
        w = w.strip()
        if not w or not re.search(r'[\u4e00-\u9fff]', w):
            continue
        level = _HSK_WORDS.get(w)
        if level:
            levels.append(level)
        else:
            unknown_count += 1

    if not levels:
        return 3

    # Use 80th percentile of word levels as the passage level
    levels.sort()
    idx = int(len(levels) * 0.8)
    estimated = levels[min(idx, len(levels) - 1)]

    # Bump up if many unknown words
    total_chinese = len(levels) + unknown_count
    unknown_ratio = unknown_count / total_chinese if total_chinese > 0 else 0
    if unknown_ratio > 0.3:
        estimated = min(9, estimated + 1)
    if unknown_ratio > 0.5:
        estimated = min(9, estimated + 1)

    return max(1, min(9, estimated))


def _extract_chinese_text(html_content: str) -> str:
    """Extract readable Chinese text from HTML content."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Decode HTML entities
    try:
        import html
        text = html.unescape(text)
    except ImportError:
        pass
    return text


def _generate_passage_id(title: str, url: str) -> str:
    """Generate a stable passage ID from title and URL."""
    import hashlib
    raw = f"{title}:{url}"
    return "news_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def fetch_and_parse_feed(feed_url: str, limit: int = 10) -> list:
    """Fetch an RSS feed and return parsed entries.

    Returns list of dicts: {title, link, content, published}
    """
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed: pip install feedparser")
        return []

    try:
        import requests
        resp = requests.get(feed_url, timeout=30,
                           headers={"User-Agent": "Aelu/1.0 (Mandarin Learning)"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except ImportError:
        # Fall back to feedparser's built-in fetching
        feed = feedparser.parse(feed_url)
    except Exception as e:
        logger.error("Failed to fetch feed %s: %s", feed_url, e)
        return []

    entries = []
    for entry in feed.entries[:limit]:
        # Extract content from summary or content field
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary or ""
        elif hasattr(entry, "description"):
            content = entry.description or ""

        title = getattr(entry, "title", "Untitled")
        link = getattr(entry, "link", "")
        published = getattr(entry, "published", "")

        entries.append({
            "title": title,
            "link": link,
            "content": content,
            "published": published,
        })

    return entries


def ingest_article(conn, title: str, link: str, content: str,
                   hsk_max: int = 9, dry_run: bool = False) -> dict:
    """Process a single article and store as a reading passage.

    Returns dict with status info.
    """
    text = _extract_chinese_text(content)
    if not text:
        return {"status": "skipped", "reason": "no content"}

    # Check if it's actually Chinese
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chinese_chars) < 20:
        return {"status": "skipped", "reason": "insufficient Chinese text"}

    # Estimate HSK level
    hsk_level = estimate_hsk_level(text, conn=conn)

    if hsk_level > hsk_max:
        return {"status": "skipped", "reason": f"HSK {hsk_level} exceeds max {hsk_max}"}

    passage_id = _generate_passage_id(title, link)

    # Check for duplicates
    existing = conn.execute(
        "SELECT 1 FROM content_item WHERE source = ? LIMIT 1",
        (f"rss:{link}",),
    ).fetchone()
    if existing:
        return {"status": "skipped", "reason": "duplicate"}

    # Truncate very long articles
    if len(text) > 2000:
        # Take first ~2000 chars, breaking at sentence boundary
        truncated = text[:2000]
        last_period = max(truncated.rfind("。"), truncated.rfind("！"),
                         truncated.rfind("？"))
        if last_period > 500:
            text = truncated[:last_period + 1]
        else:
            text = truncated

    # Word count (Chinese characters)
    word_count = len(chinese_chars)

    if dry_run:
        return {
            "status": "dry_run",
            "title": title,
            "hsk_level": hsk_level,
            "word_count": word_count,
            "passage_id": passage_id,
        }

    # Insert as content_item with item_type='sentence' (paragraph-scale)
    try:
        # Extract a representative sentence for hanzi/pinyin/english fields
        sentences = re.split(r'[。！？]', text)
        representative = next((s for s in sentences if len(s) >= 10), text[:50])

        conn.execute(
            """INSERT INTO content_item
               (hanzi, pinyin, english, item_type, hsk_level, source, source_context,
                scale_level, status, review_status, context_note)
               VALUES (?, '', ?, 'sentence', ?, ?, ?, 'article', 'drill_ready',
                       'pending_review', ?)""",
            (representative.strip(),
             title,
             hsk_level,
             f"rss:{link}",
             text[:500],
             f"News article: {title} ({word_count} chars, HSK ~{hsk_level})"),
        )
        conn.commit()

        return {
            "status": "ingested",
            "title": title,
            "hsk_level": hsk_level,
            "word_count": word_count,
            "passage_id": passage_id,
        }

    except sqlite3.Error as e:
        logger.error("DB insert failed for %s: %s", title, e)
        return {"status": "error", "reason": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Chinese news from RSS into reading passages"
    )
    parser.add_argument("feed_url", help="RSS feed URL")
    parser.add_argument("--hsk-max", type=int, default=6,
                        help="Maximum HSK level to accept (default: 6)")
    parser.add_argument("--limit", type=int, default=10,
                        help="Maximum articles to process (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Estimate HSK levels without writing to DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    from mandarin import db

    logger.info("Fetching feed: %s (limit %d)", args.feed_url, args.limit)
    entries = fetch_and_parse_feed(args.feed_url, limit=args.limit)
    logger.info("Found %d entries", len(entries))

    if not entries:
        logger.info("No entries to process")
        return

    results = {"ingested": 0, "skipped": 0, "error": 0, "dry_run": 0}

    with db.connection() as conn:
        for entry in entries:
            result = ingest_article(
                conn,
                title=entry["title"],
                link=entry["link"],
                content=entry["content"],
                hsk_max=args.hsk_max,
                dry_run=args.dry_run,
            )
            status = result["status"]
            results[status] = results.get(status, 0) + 1

            if args.verbose or status in ("ingested", "dry_run"):
                logger.info(
                    "  %s: %s (HSK %s, %s chars)",
                    status.upper(),
                    result.get("title", entry["title"])[:60],
                    result.get("hsk_level", "?"),
                    result.get("word_count", "?"),
                )

    logger.info(
        "Done. Ingested: %d, Skipped: %d, Errors: %d",
        results.get("ingested", 0) + results.get("dry_run", 0),
        results["skipped"],
        results["error"],
    )


if __name__ == "__main__":
    main()
