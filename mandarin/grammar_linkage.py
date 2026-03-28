"""Content-Grammar Linkage — Focus on Form helpers.

Provides functions to link content items to grammar points by name,
enabling contextual grammar teaching where grammar is surfaced in
the context of meaningful content rather than in isolation.

Uses the ``content_grammar_link`` table (migration v122->v123).
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def get_grammar_points_for_item(
    conn: sqlite3.Connection,
    content_item_id: int,
) -> list[dict]:
    """Return all grammar points linked to a content item.

    Returns a list of dicts with keys:
        id, content_item_id, grammar_point, grammar_level,
        example_sentence, created_at
    """
    rows = conn.execute(
        """
        SELECT id, content_item_id, grammar_point, grammar_level,
               example_sentence, created_at
        FROM content_grammar_link
        WHERE content_item_id = ?
        ORDER BY grammar_level, grammar_point
        """,
        (content_item_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_items_for_grammar_point(
    conn: sqlite3.Connection,
    grammar_point: str,
) -> list[dict]:
    """Return all content items that use a given grammar point.

    Returns a list of dicts with keys:
        id, content_item_id, grammar_point, grammar_level,
        example_sentence, created_at
    """
    rows = conn.execute(
        """
        SELECT id, content_item_id, grammar_point, grammar_level,
               example_sentence, created_at
        FROM content_grammar_link
        WHERE grammar_point = ?
        ORDER BY grammar_level, content_item_id
        """,
        (grammar_point,),
    ).fetchall()
    return [dict(row) for row in rows]


def link_content_to_grammar(
    conn: sqlite3.Connection,
    content_item_id: int,
    grammar_point: str,
    level: int = 1,
    example: Optional[str] = None,
) -> int:
    """Create a link between a content item and a grammar point.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active database connection.
    content_item_id : int
        The id of the content_item to link.
    grammar_point : str
        A grammar point name (e.g. "把 construction", "了 completion").
    level : int
        Grammar difficulty level (1 = beginner, higher = more advanced).
    example : str | None
        An optional example sentence illustrating the grammar point
        in the context of this content item.

    Returns
    -------
    int
        The rowid of the newly created link.
    """
    cursor = conn.execute(
        """
        INSERT INTO content_grammar_link
            (content_item_id, grammar_point, grammar_level, example_sentence)
        VALUES (?, ?, ?, ?)
        """,
        (content_item_id, grammar_point, level, example),
    )
    conn.commit()
    logger.info(
        "Linked content_item %d to grammar point '%s' (level %d)",
        content_item_id,
        grammar_point,
        level,
    )
    return cursor.lastrowid


def unlink_content_from_grammar(
    conn: sqlite3.Connection,
    link_id: int,
) -> bool:
    """Remove a content-grammar link by its id.

    Returns True if a row was deleted, False if the id was not found.
    """
    cursor = conn.execute(
        "DELETE FROM content_grammar_link WHERE id = ?",
        (link_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_grammar_points_by_level(
    conn: sqlite3.Connection,
    grammar_level: int,
) -> list[dict]:
    """Return all distinct grammar points at a given level.

    Returns a list of dicts with keys: grammar_point, grammar_level, link_count
    """
    rows = conn.execute(
        """
        SELECT grammar_point, grammar_level, COUNT(*) AS link_count
        FROM content_grammar_link
        WHERE grammar_level = ?
        GROUP BY grammar_point
        ORDER BY link_count DESC
        """,
        (grammar_level,),
    ).fetchall()
    return [dict(row) for row in rows]
