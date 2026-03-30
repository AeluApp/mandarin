"""Tests for curriculum graph with Dijkstra shortest-path routing.

Covers: build_curriculum_graph, shortest_path_to_goal, suggest_next_items,
_goal_to_item_ids from mandarin/quality/curriculum_graph.py.
"""

import sqlite3
import unittest

from mandarin.quality.curriculum_graph import (
    build_curriculum_graph,
    shortest_path_to_goal,
    suggest_next_items,
    _goal_to_item_ids,
)
from tests.shared_db import make_test_db


def _make_curriculum_db():
    """Create in-memory DB with the full production schema."""
    return make_test_db()


def _seed_hsk_items(conn, level, count, start_id=None):
    """Insert `count` content_items at the given hsk_level."""
    for i in range(count):
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status) "
            "VALUES (?, ?, ?, ?, 'drill_ready')",
            (f"char_L{level}_{i}", f"pin{i}", f"eng{i}", level),
        )
    conn.commit()


class TestBuildCurriculumGraph(unittest.TestCase):
    """Tests for build_curriculum_graph()."""

    def setUp(self):
        self.conn = _make_curriculum_db()

    def tearDown(self):
        self.conn.close()

    def test_graph_has_cross_level_edges(self):
        """5 HSK-1 items + 5 HSK-2 items produces edges between levels."""
        _seed_hsk_items(self.conn, level=1, count=5)
        _seed_hsk_items(self.conn, level=2, count=5)

        graph = build_curriculum_graph(self.conn)
        self.assertIsInstance(graph, dict)
        self.assertGreater(len(graph), 0)

        # Items in level 1 should have edges pointing to items in level 2
        hsk1_ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 1"
        ).fetchall()]
        hsk2_ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 2"
        ).fetchall()]

        # At least one HSK-1 item should have an edge to an HSK-2 item
        found_cross_edge = False
        for src_id in hsk1_ids:
            for neighbor_id, _weight in graph.get(src_id, []):
                if neighbor_id in hsk2_ids:
                    found_cross_edge = True
                    break
        self.assertTrue(found_cross_edge, "Expected cross-level edges from HSK 1 to HSK 2")

    def test_within_level_sequential_edges(self):
        """Items within the same level have sequential edges."""
        _seed_hsk_items(self.conn, level=1, count=5)

        graph = build_curriculum_graph(self.conn)
        ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 1 ORDER BY id"
        ).fetchall()]

        # Each item (except last) should have an edge to the next item
        for i in range(len(ids) - 1):
            neighbors = [n for n, _w in graph.get(ids[i], [])]
            self.assertIn(ids[i + 1], neighbors,
                          f"Item {ids[i]} should have edge to {ids[i + 1]}")

    def test_empty_content_returns_empty_graph(self):
        """No content_item rows -> empty graph."""
        graph = build_curriculum_graph(self.conn)
        self.assertEqual(graph, {})

    def test_edge_weights_are_positive(self):
        """All edge weights should be positive floats."""
        _seed_hsk_items(self.conn, level=1, count=3)

        graph = build_curriculum_graph(self.conn)
        for src, edges in graph.items():
            for neighbor, weight in edges:
                self.assertIsInstance(weight, float)
                self.assertGreater(weight, 0)


class TestShortestPathToGoal(unittest.TestCase):
    """Tests for shortest_path_to_goal()."""

    def setUp(self):
        self.conn = _make_curriculum_db()

    def tearDown(self):
        self.conn.close()

    def test_path_to_hsk2_returns_hsk2_ids(self):
        """Path to 'hsk_2' goal includes HSK-2 item IDs."""
        _seed_hsk_items(self.conn, level=1, count=5)
        _seed_hsk_items(self.conn, level=2, count=5)

        hsk2_ids = set(r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 2"
        ).fetchall())

        path = shortest_path_to_goal(self.conn, user_id=1, goal="hsk_2")
        self.assertIsInstance(path, list)
        # Path should contain at least some HSK-2 items
        self.assertTrue(
            any(item_id in hsk2_ids for item_id in path),
            "Path to hsk_2 should contain at least one HSK-2 item"
        )

    def test_nonexistent_goal_returns_empty_or_fallback(self):
        """A goal with no matching items returns an empty list."""
        _seed_hsk_items(self.conn, level=1, count=3)

        path = shortest_path_to_goal(self.conn, user_id=1, goal="hsk_99")
        self.assertIsInstance(path, list)
        self.assertEqual(len(path), 0)


class TestSuggestNextItems(unittest.TestCase):
    """Tests for suggest_next_items()."""

    def setUp(self):
        self.conn = _make_curriculum_db()

    def tearDown(self):
        self.conn.close()

    def test_no_mastery_suggests_hsk1_items(self):
        """With no mastered items, suggestions should come from HSK-1."""
        _seed_hsk_items(self.conn, level=1, count=5)
        _seed_hsk_items(self.conn, level=2, count=5)

        hsk1_ids = set(r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 1"
        ).fetchall())

        suggestions = suggest_next_items(self.conn, user_id=1, goal="hsk_1")
        self.assertIsInstance(suggestions, list)
        # All suggestions (if any) should be HSK-1 items
        for item_id in suggestions:
            self.assertIn(item_id, hsk1_ids)

    def test_suggest_respects_n_limit(self):
        """suggest_next_items respects the n parameter."""
        _seed_hsk_items(self.conn, level=1, count=10)

        suggestions = suggest_next_items(self.conn, user_id=1, goal="hsk_1", n=3)
        self.assertLessEqual(len(suggestions), 3)

    def test_empty_db_returns_empty(self):
        """Empty content table -> empty suggestions."""
        suggestions = suggest_next_items(self.conn, user_id=1)
        self.assertIsInstance(suggestions, list)
        self.assertEqual(len(suggestions), 0)


class TestGoalToItemIds(unittest.TestCase):
    """Tests for _goal_to_item_ids()."""

    def setUp(self):
        self.conn = _make_curriculum_db()

    def tearDown(self):
        self.conn.close()

    def test_hsk1_goal_returns_correct_ids(self):
        """'hsk_1' returns all drill-ready HSK-1 item IDs."""
        _seed_hsk_items(self.conn, level=1, count=5)
        _seed_hsk_items(self.conn, level=2, count=3)

        expected = [r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 1 AND status = 'drill_ready' ORDER BY id"
        ).fetchall()]

        result = _goal_to_item_ids(self.conn, "hsk_1")
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 5)

    def test_hsk2_goal_excludes_hsk1(self):
        """'hsk_2' should not include HSK-1 items."""
        _seed_hsk_items(self.conn, level=1, count=5)
        _seed_hsk_items(self.conn, level=2, count=5)

        hsk1_ids = set(r["id"] for r in self.conn.execute(
            "SELECT id FROM content_item WHERE hsk_level = 1"
        ).fetchall())

        result = _goal_to_item_ids(self.conn, "hsk_2")
        for item_id in result:
            self.assertNotIn(item_id, hsk1_ids)

    def test_nonexistent_hsk_level_returns_empty(self):
        """Goal for a level with no items returns empty list."""
        _seed_hsk_items(self.conn, level=1, count=3)

        result = _goal_to_item_ids(self.conn, "hsk_9")
        self.assertEqual(result, [])

    def test_non_drill_ready_excluded(self):
        """Items with status != 'drill_ready' are excluded from goal IDs."""
        _seed_hsk_items(self.conn, level=1, count=3)
        # Mark one item as not drill-ready
        self.conn.execute("UPDATE content_item SET status = 'raw' WHERE id = 1")
        self.conn.commit()

        result = _goal_to_item_ids(self.conn, "hsk_1")
        self.assertNotIn(1, result)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
