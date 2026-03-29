"""Causal DAG — graph structure, confounder documentation, backdoor criterion.

Uses only stdlib.  The DAG is a lightweight bookkeeping structure so that
experiment analyses can record *why* an adjustment set was chosen and verify
that it satisfies the backdoor criterion.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import deque

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CausalDAG
# ---------------------------------------------------------------------------

class CausalDAG:
    """Simple directed acyclic graph for causal reasoning."""

    def __init__(self, nodes: list[str] | set[str] | None = None, edges: list[tuple[str, str]] | None = None):
        self.nodes: set[str] = set(nodes or [])
        self.edges: list[tuple[str, str]] = []  # list of (from, to) tuples
        self._children: dict[str, set[str]] = {}  # node -> set of children
        self._parents: dict[str, set[str]] = {}   # node -> set of parents
        for edge in (edges or []):
            self.add_edge(*edge)

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a directed edge from_node -> to_node."""
        self.nodes.add(from_node)
        self.nodes.add(to_node)
        self.edges.append((from_node, to_node))
        self._children.setdefault(from_node, set()).add(to_node)
        self._parents.setdefault(to_node, set()).add(from_node)

    def ancestors(self, node: str) -> set[str]:
        """All ancestors of a node (BFS upward through parents)."""
        visited: set[str] = set()
        queue = deque(self._parents.get(node, set()))
        while queue:
            current = queue.popleft()
            if current not in visited:
                visited.add(current)
                queue.extend(self._parents.get(current, set()) - visited)
        return visited

    def descendants(self, node: str) -> set[str]:
        """All descendants of a node (BFS downward through children)."""
        visited: set[str] = set()
        queue = deque(self._children.get(node, set()))
        while queue:
            current = queue.popleft()
            if current not in visited:
                visited.add(current)
                queue.extend(self._children.get(current, set()) - visited)
        return visited

    def is_ancestor(self, potential_ancestor: str, node: str) -> bool:
        """Return True if *potential_ancestor* is an ancestor of *node*."""
        return potential_ancestor in self.ancestors(node)

    def to_json(self) -> dict:
        """Serialize to a plain dict."""
        return {"nodes": sorted(self.nodes), "edges": self.edges}

    @classmethod
    def from_json(cls, data: dict) -> CausalDAG:
        """Deserialize from a plain dict."""
        return cls(nodes=data["nodes"], edges=[tuple(e) for e in data["edges"]])

    # -- helpers for backdoor analysis --

    def _undirected_neighbors(self) -> dict[str, set[str]]:
        """Build an undirected adjacency map (for path-finding on the skeleton)."""
        adj: dict[str, set[str]] = {}
        for u, v in self.edges:
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
        return adj


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS experiment_causal_dag (
    experiment_id INTEGER PRIMARY KEY,
    confounders   TEXT NOT NULL,
    dag_json      TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def document_confounders(
    conn: sqlite3.Connection,
    experiment_id: int,
    confounders: list[str],
    dag: CausalDAG,
) -> None:
    """Persist the causal DAG and declared confounders for an experiment.

    Creates the ``experiment_causal_dag`` table if it does not exist.
    """
    try:
        conn.execute(_CREATE_TABLE)
        conn.execute(
            "INSERT OR REPLACE INTO experiment_causal_dag "
            "(experiment_id, confounders, dag_json) VALUES (?, ?, ?)",
            (experiment_id, json.dumps(confounders), json.dumps(dag.to_json())),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.warning("Could not persist causal DAG for experiment %s", experiment_id)


# ---------------------------------------------------------------------------
# Backdoor criterion
# ---------------------------------------------------------------------------

def _find_all_undirected_paths(
    adj: dict[str, set[str]],
    start: str,
    end: str,
    blocked: set[str],
) -> list[list[str]]:
    """Return all simple paths between *start* and *end* on the skeleton,
    excluding nodes in *blocked* (except start/end themselves).
    """
    paths: list[list[str]] = []
    stack: list[tuple[str, list[str]]] = [(start, [start])]
    while stack:
        current, path = stack.pop()
        if current == end and len(path) > 1:
            paths.append(path)
            continue
        for neighbor in adj.get(current, set()):
            if neighbor not in path:
                if neighbor == end or neighbor not in blocked:
                    stack.append((neighbor, path + [neighbor]))
    return paths


def _is_backdoor_path(dag: CausalDAG, path: list[str], treatment: str) -> bool:
    """A backdoor path is any path that starts with an arrow *into* treatment."""
    if len(path) < 2:
        return False
    second = path[1]
    # The first edge on the path must point into treatment (second -> treatment)
    return second in dag._parents.get(treatment, set())


def check_backdoor_criterion(
    dag: CausalDAG,
    treatment: str,
    outcome: str,
    adjustment_set: list[str],
) -> dict:
    """Verify that *adjustment_set* blocks all backdoor paths from
    *treatment* to *outcome*.

    Returns::

        {"satisfied": bool, "explanation": str, "open_paths": list[str]}
    """
    adj = dag._undirected_neighbors()
    adjustment = set(adjustment_set)

    # Find all undirected paths between treatment and outcome
    all_paths = _find_all_undirected_paths(adj, treatment, outcome, blocked=set())

    # Filter to backdoor paths (those with an arrow into treatment)
    backdoor_paths = [p for p in all_paths if _is_backdoor_path(dag, p, treatment)]

    if not backdoor_paths:
        return {
            "satisfied": True,
            "explanation": "No backdoor paths exist — no adjustment needed.",
            "open_paths": [],
        }

    # Check which backdoor paths are blocked by the adjustment set
    open_paths: list[str] = []
    for path in backdoor_paths:
        intermediaries = path[1:-1]  # exclude treatment and outcome
        if not any(node in adjustment for node in intermediaries):
            open_paths.append(" -> ".join(path))

    if not open_paths:
        return {
            "satisfied": True,
            "explanation": (
                f"Adjustment set {sorted(adjustment)} blocks all "
                f"{len(backdoor_paths)} backdoor path(s)."
            ),
            "open_paths": [],
        }

    return {
        "satisfied": False,
        "explanation": (
            f"{len(open_paths)} backdoor path(s) remain open. "
            f"Adjustment set {sorted(adjustment)} is insufficient."
        ),
        "open_paths": open_paths,
    }


# ---------------------------------------------------------------------------
# Suggest controls
# ---------------------------------------------------------------------------

def suggest_controls(dag: CausalDAG, treatment: str, outcome: str) -> list[str]:
    """Return the parents of *treatment* that are not descendants of *treatment*
    as a minimal valid adjustment set.

    This is the standard "parent adjustment" strategy: conditioning on the
    direct causes of the treatment blocks all backdoor paths without
    accidentally conditioning on a descendant (which could open a path or
    introduce post-treatment bias).
    """
    treatment_descendants = dag.descendants(treatment)
    parents = dag._parents.get(treatment, set())
    controls = sorted(p for p in parents if p not in treatment_descendants)
    return controls
