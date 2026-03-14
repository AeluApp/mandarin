"""Research Synthesis (Doc 23 B-01).

Automated discovery of SLA/CALL research relevant to Aelu's methodology.
Searches arxiv + Semantic Scholar, scores relevance, synthesizes applications.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_ARXIV_API = "https://export.arxiv.org/api/query"
_SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_TIMEOUT = 15.0

# Default search terms for SLA/CALL research
_DEFAULT_QUERIES = [
    "second language acquisition spaced repetition",
    "computer assisted language learning Chinese",
    "Mandarin tone acquisition technology",
    "vocabulary retention algorithm",
]


def discover_papers(
    conn: sqlite3.Connection,
    query_terms: Optional[list[str]] = None,
    max_results: int = 10,
) -> list[dict]:
    """Search arxiv + Semantic Scholar for SLA/CALL papers.

    Returns list of discovered paper dicts.
    """
    terms = query_terms or _DEFAULT_QUERIES
    papers = []

    for query in terms:
        # Try arxiv
        arxiv_papers = _search_arxiv(query, max_results=max_results // len(terms) + 1)
        papers.extend(arxiv_papers)

        # Try Semantic Scholar
        ss_papers = _search_semantic_scholar(query, max_results=max_results // len(terms) + 1)
        papers.extend(ss_papers)

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for p in papers:
        title_key = p["title"].lower().strip()[:80]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(p)

    # Store in DB
    stored = 0
    for paper in unique[:max_results]:
        paper_id = _store_paper(conn, paper)
        if paper_id:
            paper["id"] = paper_id
            stored += 1

    logger.info("Research discovery: %d papers found, %d stored", len(unique), stored)
    return unique[:max_results]


def _search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    """Search arxiv API."""
    try:
        resp = httpx.get(
            _ARXIV_API,
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        # Parse Atom XML
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
        except ImportError:
            return []

        papers = []
        for entry in soup.find_all("entry"):
            title = entry.find("title")
            summary = entry.find("summary")
            doi_el = entry.find("arxiv:doi")
            published = entry.find("published")
            authors = entry.find_all("author")

            papers.append({
                "source": "arxiv",
                "title": title.get_text(strip=True) if title else "",
                "abstract": summary.get_text(strip=True)[:1000] if summary else "",
                "doi": doi_el.get_text(strip=True) if doi_el else None,
                "published_date": published.get_text(strip=True)[:10] if published else None,
                "authors": ", ".join(
                    a.find("name").get_text(strip=True) for a in authors[:5]
                    if a.find("name")
                ),
            })
        return papers

    except Exception as e:
        logger.debug("arxiv search failed: %s", e)
        return []


def _search_semantic_scholar(query: str, max_results: int = 5) -> list[dict]:
    """Search Semantic Scholar API."""
    try:
        resp = httpx.get(
            _SEMANTIC_SCHOLAR_API,
            params={
                "query": query,
                "limit": max_results,
                "fields": "title,abstract,authors,externalIds,year",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        papers = []
        for item in data.get("data", []):
            doi = None
            ext_ids = item.get("externalIds", {})
            if ext_ids:
                doi = ext_ids.get("DOI")

            authors = item.get("authors", [])
            author_names = ", ".join(a.get("name", "") for a in authors[:5])

            papers.append({
                "source": "semantic_scholar",
                "title": item.get("title", ""),
                "abstract": (item.get("abstract") or "")[:1000],
                "doi": doi,
                "published_date": str(item.get("year", "")) if item.get("year") else None,
                "authors": author_names,
            })
        return papers

    except Exception as e:
        logger.debug("Semantic Scholar search failed: %s", e)
        return []


def _store_paper(conn: sqlite3.Connection, paper: dict) -> Optional[int]:
    """Store paper in research_paper table. Skips duplicates by title."""
    try:
        existing = conn.execute(
            "SELECT id FROM research_paper WHERE title = ?",
            (paper["title"],),
        ).fetchone()
        if existing:
            return None

        cursor = conn.execute("""
            INSERT INTO research_paper
            (source, title, authors, abstract, doi, published_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            paper.get("source", "unknown"),
            paper["title"],
            paper.get("authors"),
            paper.get("abstract"),
            paper.get("doi"),
            paper.get("published_date"),
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


def score_relevance(
    conn: sqlite3.Connection,
    paper_id: int,
    aelu_components: Optional[list[str]] = None,
) -> float:
    """Score a paper's relevance to Aelu's methodology.

    Uses embedding similarity if available, otherwise keyword matching.
    """
    if aelu_components is None:
        aelu_components = [
            "spaced repetition", "FSRS", "tone acquisition", "character recognition",
            "vocabulary retention", "Mandarin learning", "adaptive scheduling",
            "error taxonomy", "pronunciation feedback", "reading comprehension",
        ]

    paper = conn.execute(
        "SELECT * FROM research_paper WHERE id = ?", (paper_id,)
    ).fetchone()
    if not paper:
        return 0.0

    abstract = (paper["abstract"] or "").lower()
    title = (paper["title"] or "").lower()
    text = f"{title} {abstract}"

    # Keyword-based relevance scoring
    score = 0.0
    for component in aelu_components:
        if component.lower() in text:
            score += 1.0 / len(aelu_components)

    # Boost for SLA-specific terms
    sla_terms = ["sla", "second language", "l2", "acquisition", "mandarin",
                 "chinese", "tone", "hanzi", "pinyin"]
    sla_matches = sum(1 for t in sla_terms if t in text)
    score += min(0.3, sla_matches * 0.05)

    score = min(1.0, score)

    # Update paper record
    try:
        conn.execute(
            "UPDATE research_paper SET relevance_score = ? WHERE id = ?",
            (score, paper_id),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass

    return round(score, 3)


def synthesize_application(
    conn: sqlite3.Connection,
    paper_id: int,
) -> Optional[dict]:
    """Use Qwen to synthesize how a paper could apply to Aelu.

    Returns application dict or None if LLM unavailable.
    """
    from .ollama_client import generate as ollama_generate, is_ollama_available
    from .genai_layer import _parse_llm_json

    if not is_ollama_available():
        return None

    paper = conn.execute(
        "SELECT * FROM research_paper WHERE id = ?", (paper_id,)
    ).fetchone()
    if not paper:
        return None

    prompt = (
        f"Paper: {paper['title']}\n"
        f"Abstract: {paper['abstract'] or 'N/A'}\n\n"
        f"Aelu is a Mandarin learning app using FSRS spaced repetition, "
        f"tone grading, adaptive scheduling, and multi-modal drills.\n\n"
        f"Analyze this paper and return JSON with:\n"
        f"- aelu_component: which Aelu component could benefit\n"
        f"- proposed_change: what specific change to make\n"
        f"- impact_estimate: expected impact (low/medium/high)"
    )

    resp = ollama_generate(
        prompt=prompt,
        system="You are an SLA researcher analyzing papers for practical application in a language learning app. Return JSON.",
        temperature=0.3,
        conn=conn,
        task_type="research_synthesis",
    )

    if not resp.success:
        return None

    parsed = _parse_llm_json(resp.text, conn=conn, task_type="research_synthesis")
    if not parsed:
        return None

    # Store application
    try:
        conn.execute("""
            INSERT INTO research_application
            (paper_id, aelu_component, proposed_change, impact_estimate)
            VALUES (?, ?, ?, ?)
        """, (
            paper_id,
            parsed.get("aelu_component", "unknown"),
            parsed.get("proposed_change", ""),
            parsed.get("impact_estimate", "low"),
        ))
        conn.commit()
    except sqlite3.OperationalError:
        pass

    return parsed


def get_research_digest(
    conn: sqlite3.Connection,
    since_days: int = 7,
) -> dict:
    """Weekly summary of new relevant papers."""
    try:
        papers = conn.execute("""
            SELECT * FROM research_paper
            WHERE created_at >= datetime('now', ?)
            AND relevance_score > 0
            ORDER BY relevance_score DESC
            LIMIT 20
        """, (f"-{since_days} days",)).fetchall()

        applications = conn.execute("""
            SELECT ra.*, rp.title as paper_title
            FROM research_application ra
            JOIN research_paper rp ON rp.id = ra.paper_id
            WHERE ra.created_at >= datetime('now', ?)
            ORDER BY ra.created_at DESC
        """, (f"-{since_days} days",)).fetchall()

        return {
            "period_days": since_days,
            "papers_found": len(papers),
            "papers": [dict(p) for p in papers],
            "applications": [dict(a) for a in applications],
        }
    except sqlite3.OperationalError:
        return {"period_days": since_days, "papers_found": 0, "papers": [], "applications": []}
