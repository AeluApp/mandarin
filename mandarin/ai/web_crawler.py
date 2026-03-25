"""Automated Web Crawling (Doc 23 A-05 upgrade).

Replaces manual log_competitor_signal()/log_research_signal() stubs with
automated discovery via httpx + BeautifulSoup.
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone, UTC
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    logger.debug("beautifulsoup4 not installed — web crawling disabled")


_RATE_LIMIT_DELAY = 2.0  # seconds between requests
_USER_AGENT = "Aelu-Research-Bot/1.0 (educational; +https://aeluapp.com)"
_TIMEOUT = 15.0


def crawl_source(conn: sqlite3.Connection, source_id: int) -> dict:
    """Fetch URL, parse with BS4, extract relevant items.

    Returns dict with status, items_found, items_new.
    """
    if BeautifulSoup is None:
        return {"status": "error", "error": "beautifulsoup4 not installed"}

    # Get source config
    source = conn.execute(
        "SELECT * FROM crawl_source WHERE id = ? AND active = 1",
        (source_id,),
    ).fetchone()
    if not source:
        return {"status": "error", "error": "source not found or inactive"}

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Create crawl run record
    cursor = conn.execute("""
        INSERT INTO crawl_run (source_id, status, started_at)
        VALUES (?, 'running', ?)
    """, (source_id, now))
    run_id = cursor.lastrowid
    conn.commit()

    try:
        # Respect robots.txt (basic check)
        if not _check_robots_allowed(source["url"]):
            _complete_run(conn, run_id, "skipped", error="robots.txt disallows")
            return {"status": "skipped", "reason": "robots.txt disallows"}

        # Fetch page
        resp = httpx.get(
            source["url"],
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        source_type = source["source_type"]
        source_name = source["name"]

        if source_type == "competitor":
            items = extract_competitor_signals(soup, source_name, source["url"])
        elif source_type == "research":
            items = extract_research_signals(soup, source_name)
        else:
            items = extract_news_signals(soup, source_name, source["url"])

        # Store signals using existing infrastructure
        from .agentic import log_competitor_signal, log_research_signal
        items_new = 0
        for item in items:
            if source_type == "competitor":
                result = log_competitor_signal(
                    conn, source=source_name,
                    signal_type=item.get("signal_type", "update"),
                    title=item["title"],
                    detail=item.get("detail", ""),
                    source_url=item.get("url"),
                )
            else:
                result = log_research_signal(
                    conn, source=source_name,
                    title=item["title"],
                    finding=item.get("detail", ""),
                    applicability_score=item.get("applicability_score", 0.5),
                    doi=item.get("doi"),
                )
            if result is not None:
                items_new += 1

        # Update source last_crawl_at
        conn.execute(
            "UPDATE crawl_source SET last_crawl_at = ? WHERE id = ?",
            (now, source_id),
        )
        _complete_run(conn, run_id, "completed",
                      items_found=len(items), items_new=items_new)

        time.sleep(_RATE_LIMIT_DELAY)

        return {
            "status": "completed",
            "run_id": run_id,
            "items_found": len(items),
            "items_new": items_new,
        }

    except Exception as e:
        error_msg = str(e)
        logger.warning("Crawl source %s failed: %s", source_id, error_msg)
        _complete_run(conn, run_id, "error", error=error_msg)
        return {"status": "error", "run_id": run_id, "error": error_msg}


def extract_competitor_signals(soup, source_name: str, base_url: str = "") -> list[dict]:
    """Extract product announcements and feature releases from HTML."""
    if soup is None:
        return []

    items = []
    # Look for article/post elements (common blog patterns)
    for article in soup.find_all(["article", "div"], class_=lambda c: c and any(
        kw in (c if isinstance(c, str) else " ".join(c))
        for kw in ["post", "article", "entry", "blog", "card"]
    ), limit=20):
        title_el = article.find(["h1", "h2", "h3", "a"])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        link = title_el.get("href", "") if title_el.name == "a" else ""
        if not link:
            link_el = article.find("a")
            link = link_el.get("href", "") if link_el else ""

        detail = ""
        desc_el = article.find("p")
        if desc_el:
            detail = desc_el.get_text(strip=True)[:500]

        # Classify signal type
        signal_type = "update"
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["launch", "new feature", "introducing", "release"]):
            signal_type = "feature_release"
        elif any(kw in title_lower for kw in ["pricing", "plan", "subscription"]):
            signal_type = "pricing_change"

        items.append({
            "title": title[:200],
            "detail": detail,
            "signal_type": signal_type,
            "url": link if link.startswith("http") else "",
        })

    return items


def extract_research_signals(soup, source_name: str) -> list[dict]:
    """Extract research papers/findings from HTML (arxiv RSS, scholar)."""
    if soup is None:
        return []

    items = []
    # RSS/Atom feed items
    for entry in soup.find_all(["item", "entry"], limit=20):
        title_el = entry.find("title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        abstract_el = entry.find(["description", "summary", "content"])
        abstract = abstract_el.get_text(strip=True)[:500] if abstract_el else ""

        doi_el = entry.find("id")
        doi = doi_el.get_text(strip=True) if doi_el else None

        items.append({
            "title": title[:200],
            "detail": abstract,
            "doi": doi,
            "applicability_score": 0.5,
        })

    # Fallback: look for article links on non-RSS pages
    if not items:
        for link in soup.find_all("a", href=True, limit=20):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if text and len(text) > 10 and any(
                kw in href.lower() for kw in ["arxiv", "paper", "doi", "abstract"]
            ):
                items.append({
                    "title": text[:200],
                    "detail": "",
                    "doi": href if "doi" in href else None,
                    "applicability_score": 0.5,
                })

    return items


def extract_news_signals(soup, source_name: str, base_url: str = "") -> list[dict]:
    """Extract general news items from HTML."""
    return extract_competitor_signals(soup, source_name, base_url)


def _check_robots_allowed(url: str) -> bool:
    """Basic robots.txt check. Returns True if crawling is allowed."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        resp = httpx.get(robots_url, timeout=5.0,
                         headers={"User-Agent": _USER_AGENT})
        if resp.status_code != 200:
            return True  # No robots.txt = allowed
        text = resp.text.lower()
        # Very basic: check for blanket disallow
        if "disallow: /" in text and "user-agent: *" in text:
            # Check if our specific path is allowed
            return False
        return True
    except Exception:
        return True  # On error, assume allowed


def _complete_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    items_found: int = 0,
    items_new: int = 0,
    error: str | None = None,
) -> None:
    """Update crawl_run with completion status."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            UPDATE crawl_run
            SET status = ?, items_found = ?, items_new = ?, error_detail = ?, completed_at = ?
            WHERE id = ?
        """, (status, items_found, items_new, error, now, run_id))
        conn.commit()
    except sqlite3.OperationalError:
        pass


def get_sources_due_for_crawl(conn: sqlite3.Connection) -> list[dict]:
    """Get active crawl sources that are due for their next crawl."""
    try:
        rows = conn.execute("""
            SELECT * FROM crawl_source
            WHERE active = 1
            AND (last_crawl_at IS NULL
                 OR last_crawl_at < datetime('now', '-' || crawl_interval_hours || ' hours'))
            ORDER BY last_crawl_at ASC NULLS FIRST
        """).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def seed_crawl_sources(conn: sqlite3.Connection) -> int:
    """Seed default crawl sources. Idempotent."""
    sources = [
        ("Duolingo Blog", "https://blog.duolingo.com/", "competitor", 24),
        ("HelloChinese Updates", "https://www.hellochinese.cc/blog/", "competitor", 48),
        ("arXiv SLA RSS", "https://export.arxiv.org/rss/cs.CL", "research", 168),
    ]
    seeded = 0
    for name, url, source_type, interval in sources:
        existing = conn.execute(
            "SELECT id FROM crawl_source WHERE url = ?", (url,)
        ).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO crawl_source (name, url, source_type, crawl_interval_hours)
                VALUES (?, ?, ?, ?)
            """, (name, url, source_type, interval))
            seeded += 1
    if seeded:
        conn.commit()
    return seeded
