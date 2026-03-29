"""Curriculum graph with Dijkstra shortest-path for optimal learning routes."""

import heapq
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def build_curriculum_graph(conn, user_id: int = None) -> dict:
    """Build adjacency list from content_item + grammar_prerequisites.

    Nodes: content_item IDs
    Edges: HSK level ordering (items in level N depend on level N-1 mastery)
           + grammar_prerequisites (explicit dependencies)
    Weights: estimated_time_to_master from FSRS stability prediction

    Returns: {node_id: [(neighbor_id, weight), ...]}
    """
    graph = defaultdict(list)

    try:
        # Get all items with HSK levels
        items = conn.execute("""
            SELECT id, hsk_level, hanzi FROM content_item
            WHERE status = 'drill_ready'
            ORDER BY hsk_level, id
        """).fetchall()
    except Exception:
        return dict(graph)

    # Group by HSK level
    by_level = defaultdict(list)
    for item in items:
        by_level[item["hsk_level"]].append(item["id"])

    # HSK level edges: each item in level N has edges FROM representative items in level N-1
    sorted_levels = sorted(by_level.keys())
    for i in range(1, len(sorted_levels)):
        prev_level = sorted_levels[i - 1]
        curr_level = sorted_levels[i]
        # Connect last 5 items of prev level to first 5 of current
        prev_items = by_level[prev_level][-5:]
        curr_items = by_level[curr_level][:5]
        for p in prev_items:
            for c in curr_items:
                graph[p].append((c, _estimate_mastery_time(conn, user_id, c)))

    # Within-level edges: sequential ordering
    for _level, item_ids in by_level.items():
        for i in range(len(item_ids) - 1):
            weight = _estimate_mastery_time(conn, user_id, item_ids[i + 1])
            graph[item_ids[i]].append((item_ids[i + 1], weight))

    # Grammar prerequisite edges
    try:
        prereqs = conn.execute("""
            SELECT grammar_point_id, prerequisite_id FROM grammar_prerequisites
        """).fetchall()
        for row in prereqs:
            graph[row["prerequisite_id"]].append((row["grammar_point_id"],
                                                   _estimate_mastery_time(conn, user_id, row["grammar_point_id"])))
    except Exception:
        pass

    return dict(graph)


def _estimate_mastery_time(conn, user_id, item_id, default_days=3.0) -> float:
    """Estimate days to master an item based on FSRS state."""
    if not conn or not user_id:
        return default_days
    try:
        row = conn.execute("""
            SELECT stability, retrievability, difficulty FROM memory_states
            WHERE user_id = ? AND content_item_id = ?
        """, (user_id, item_id)).fetchone()
        if row:
            stability = row["stability"] or 1.0
            difficulty = row["difficulty"] or 5.0
            # Already learning: time = stability * (1 - retrievability)
            r = row["retrievability"] or 0.5
            return max(0.5, stability * (1.0 - r) * (difficulty / 5.0))
        else:
            # Not started: estimate from item difficulty
            return default_days
    except Exception:
        return default_days


def shortest_path_to_goal(conn, user_id: int, goal: str) -> list[int]:
    """Find shortest path from current knowledge to a goal using Dijkstra.

    Goals: "hsk_3", "hsk_4", "read_restaurant_menu", etc.
    Returns: ordered list of content_item IDs to study.
    """
    graph = build_curriculum_graph(conn, user_id)

    # Determine target items based on goal
    target_ids = _goal_to_item_ids(conn, goal)
    if not target_ids:
        return []

    # Determine start nodes: items already mastered (stability > 1)
    try:
        mastered = conn.execute("""
            SELECT content_item_id FROM memory_states
            WHERE user_id = ? AND stability > 1.0
        """, (user_id,)).fetchall()
        start_ids = {r["content_item_id"] for r in mastered}
    except Exception:
        start_ids = set()

    if not start_ids:
        # No mastery yet: start from first HSK 1 items
        try:
            first_items = conn.execute("""
                SELECT id FROM content_item WHERE hsk_level = 1 AND status = 'drill_ready'
                ORDER BY id LIMIT 5
            """).fetchall()
            start_ids = {r["id"] for r in first_items}
        except Exception:
            return []

    # Dijkstra from all start nodes to any target
    dist = {}
    prev = {}
    pq = []

    for s in start_ids:
        dist[s] = 0.0
        heapq.heappush(pq, (0.0, s))

    target_set = set(target_ids)
    reached_target = None

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float('inf')):
            continue
        if u in target_set:
            reached_target = u
            break
        for v, w in graph.get(u, []):
            new_dist = d + w
            if new_dist < dist.get(v, float('inf')):
                dist[v] = new_dist
                prev[v] = u
                heapq.heappush(pq, (new_dist, v))

    if reached_target is None:
        return list(target_ids)[:20]  # fallback: just return targets

    # Reconstruct path
    path = []
    node = reached_target
    while node in prev:
        path.append(node)
        node = prev[node]
    path.reverse()

    # Filter out already-mastered items
    return [item_id for item_id in path if item_id not in start_ids]


def suggest_next_items(conn, user_id: int, goal: str = None, n: int = 5) -> list[int]:
    """Suggest next items to study, preferring shortest-path items."""
    if goal:
        path = shortest_path_to_goal(conn, user_id, goal)
        return path[:n]

    # No explicit goal: default to next HSK level
    try:
        row = conn.execute("""
            SELECT MAX(ci.hsk_level) as max_level
            FROM memory_states ms
            JOIN content_item ci ON ms.content_item_id = ci.id
            WHERE ms.user_id = ? AND ms.stability > 5.0
        """, (user_id,)).fetchone()
        current_level = (row["max_level"] or 1) if row else 1
        return shortest_path_to_goal(conn, user_id, f"hsk_{current_level + 1}")[:n]
    except Exception:
        return []


def _goal_to_item_ids(conn, goal: str) -> list[int]:
    """Convert a goal string to target content_item IDs."""
    try:
        if goal.startswith("hsk_"):
            level = int(goal.split("_")[1])
            rows = conn.execute("""
                SELECT id FROM content_item
                WHERE hsk_level = ? AND status = 'drill_ready'
                ORDER BY id
            """, (level,)).fetchall()
            return [r["id"] for r in rows]

        # Topic-based goals: search content_item by tags/categories
        rows = conn.execute("""
            SELECT id FROM content_item
            WHERE (english LIKE ? OR hanzi LIKE ?) AND status = 'drill_ready'
            ORDER BY hsk_level, id LIMIT 50
        """, (f"%{goal}%", f"%{goal}%")).fetchall()
        return [r["id"] for r in rows]
    except Exception:
        return []
