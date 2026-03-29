"""Media Shelf — Authentic Input Channel.

Provides functions to manage a curated shelf of authentic Chinese content
(articles, audio clips, videos, podcasts) tagged by HSK level and topic.
Learners use the shelf for comprehensible input outside of drills.

Uses the ``media_shelf`` table (migration v123->v124).
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def get_shelf_items(
    conn: sqlite3.Connection,
    hsk_level: int | None = None,
    content_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Query the media shelf with optional filters.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active database connection.
    hsk_level : int | None
        Filter by HSK level (1-9). None returns all levels.
    content_type : str | None
        Filter by type: 'article', 'audio', 'video', 'podcast'.
        None returns all types.
    limit : int
        Maximum number of items to return (default 20).

    Returns
    -------
    list[dict]
        Shelf items ordered by most recently created first.
    """
    clauses = []
    params: list = []

    if hsk_level is not None:
        clauses.append("hsk_level = ?")
        params.append(hsk_level)

    if content_type is not None:
        clauses.append("content_type = ?")
        params.append(content_type)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    params.append(limit)

    rows = conn.execute(
        "SELECT id, title, source_url, content_type, hsk_level,"
        " topic, summary, full_text, duration_seconds,"
        " created_at, curated_by"
        " FROM media_shelf "
        + where
        + " ORDER BY created_at DESC"
        " LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def add_shelf_item(
    conn: sqlite3.Connection,
    title: str,
    content_type: str,
    hsk_level: int,
    source_url: str | None = None,
    topic: str | None = None,
    summary: str | None = None,
    full_text: str | None = None,
    duration_seconds: int | None = None,
    curated_by: str = "system",
) -> int:
    """Add an item to the media shelf.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active database connection.
    title : str
        Display title for the media item.
    content_type : str
        One of 'article', 'audio', 'video', 'podcast'.
    hsk_level : int
        Estimated HSK level (1-9).
    source_url : str | None
        URL to the original content.
    topic : str | None
        Topic tag (e.g. "food", "travel", "technology").
    summary : str | None
        Brief description of the content.
    full_text : str | None
        Full text content (for articles).
    duration_seconds : int | None
        Duration in seconds (for audio/video/podcast).
    curated_by : str
        Who added this item (default 'system').

    Returns
    -------
    int
        The rowid of the newly created shelf item.
    """
    if content_type not in ("article", "audio", "video", "podcast"):
        raise ValueError(
            f"Invalid content_type '{content_type}'. "
            "Must be one of: article, audio, video, podcast"
        )

    cursor = conn.execute(
        """
        INSERT INTO media_shelf
            (title, source_url, content_type, hsk_level, topic,
             summary, full_text, duration_seconds, curated_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            source_url,
            content_type,
            hsk_level,
            topic,
            summary,
            full_text,
            duration_seconds,
            curated_by,
        ),
    )
    conn.commit()
    logger.info(
        "Added media shelf item '%s' (type=%s, hsk=%d)",
        title,
        content_type,
        hsk_level,
    )
    return cursor.lastrowid


def get_shelf_item_by_id(
    conn: sqlite3.Connection,
    item_id: int,
) -> dict | None:
    """Fetch a single shelf item by id. Returns None if not found."""
    row = conn.execute(
        """
        SELECT id, title, source_url, content_type, hsk_level,
               topic, summary, full_text, duration_seconds,
               created_at, curated_by
        FROM media_shelf
        WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    return dict(row) if row else None


def remove_shelf_item(
    conn: sqlite3.Connection,
    item_id: int,
) -> bool:
    """Remove a shelf item by id. Returns True if deleted."""
    cursor = conn.execute(
        "DELETE FROM media_shelf WHERE id = ?",
        (item_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


# ── Seed data ────────────────────────────────────────────────────────────────

SEED_ITEMS = [
    {
        "title": "My Daily Routine",
        "content_type": "article",
        "hsk_level": 2,
        "topic": "daily life",
        "summary": "A short first-person account of a student's daily routine in Beijing, covering morning habits, meals, and evening study.",
        "full_text": (
            "我每天早上七点起床。先刷牙洗脸，然后吃早饭。"
            "我喜欢喝豆浆，吃包子。八点我去学校上课。"
            "中午我和同学一起吃午饭。下午三点下课。"
            "晚上我在家看书，十一点睡觉。"
        ),
        "curated_by": "seed",
    },
    {
        "title": "Ordering at a Restaurant",
        "content_type": "article",
        "hsk_level": 3,
        "topic": "food",
        "summary": "A dialogue between a customer and a waiter at a Sichuan restaurant, practising ordering food, asking about spice levels, and paying the bill.",
        "full_text": (
            "服务员：欢迎光临！请坐。这是菜单。\n"
            "客人：谢谢。请问你们的麻婆豆腐辣不辣？\n"
            "服务员：有点辣，但是可以做微辣的。\n"
            "客人：好的，我要一份微辣的麻婆豆腐，一碗米饭。\n"
            "服务员：好的，请稍等。"
        ),
        "curated_by": "seed",
    },
    {
        "title": "Breakfast China: Changsha Rice Noodles",
        "content_type": "video",
        "hsk_level": 4,
        "topic": "food",
        "source_url": "https://www.youtube.com/results?search_query=早餐中国+长沙米粉",
        "summary": "A five-minute documentary segment about a husband-and-wife team making rice noodles before sunrise in Changsha.",
        "duration_seconds": 300,
        "curated_by": "seed",
    },
    {
        "title": "ChinesePod: Taking the Subway",
        "content_type": "podcast",
        "hsk_level": 3,
        "topic": "transport",
        "source_url": "https://chinesepod.com",
        "summary": "A podcast lesson on navigating the subway system in a Chinese city, covering buying tickets, reading signs, and asking for directions.",
        "duration_seconds": 900,
        "curated_by": "seed",
    },
    {
        "title": "How Young Chinese Use the Internet",
        "content_type": "article",
        "hsk_level": 5,
        "topic": "technology",
        "summary": "An intermediate-level article about how young people in China use social media, short video apps, and online shopping in daily life.",
        "full_text": (
            "在中国，年轻人的生活离不开互联网。"
            "他们用微信聊天、付款、看新闻。"
            "很多人每天花两三个小时看短视频。"
            "网上购物也非常方便，快递一般第二天就能到。"
            "有些人觉得花太多时间上网不好，"
            "但也有人认为互联网让生活更方便了。"
        ),
        "curated_by": "seed",
    },
]


def seed_shelf(conn: sqlite3.Connection) -> int:
    """Insert seed media shelf items. Skips items whose title already exists.

    Returns the number of items inserted.
    """
    inserted = 0
    for item in SEED_ITEMS:
        existing = conn.execute(
            "SELECT 1 FROM media_shelf WHERE title = ?",
            (item["title"],),
        ).fetchone()
        if existing:
            continue
        add_shelf_item(conn, **item)
        inserted += 1
    logger.info("Seeded %d media shelf items", inserted)
    return inserted
