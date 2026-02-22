"""xAPI (Experience API) statement generation -- IEEE 9274.1.1 / ADL.

Generates xAPI statements from drill sessions for learning record interoperability.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import db

logger = logging.getLogger(__name__)

# xAPI verb IRIs
VERBS = {
    "answered": "http://adlnet.gov/expapi/verbs/answered",
    "completed": "http://adlnet.gov/expapi/verbs/completed",
    "mastered": "http://adlnet.gov/expapi/verbs/mastered",
    "attempted": "http://adlnet.gov/expapi/verbs/attempted",
    "experienced": "http://adlnet.gov/expapi/verbs/experienced",
    "progressed": "http://adlnet.gov/expapi/verbs/progressed",
}

ACTIVITY_BASE = "https://mandarin.app/activities"


def _make_actor(user_id: int, email: Optional[str] = None) -> Dict[str, Any]:
    """Create an xAPI actor (Agent) from user info."""
    actor = {
        "objectType": "Agent",
        "account": {
            "homePage": "https://mandarin.app",
            "name": str(user_id),
        },
    }
    if email:
        actor["mbox"] = f"mailto:{email}"
    return actor


def _make_verb(verb_key: str) -> Dict[str, Any]:
    """Create an xAPI verb object."""
    return {
        "id": VERBS.get(verb_key, VERBS["attempted"]),
        "display": {"en-US": verb_key},
    }


def _make_object(item_id: int, item_type: str = "drill",
                 name: Optional[str] = None) -> Dict[str, Any]:
    """Create an xAPI activity object."""
    obj = {
        "objectType": "Activity",
        "id": f"{ACTIVITY_BASE}/{item_type}/{item_id}",
        "definition": {
            "type": f"http://adlnet.gov/expapi/activities/{item_type}",
        },
    }
    if name:
        obj["definition"]["name"] = {"zh-CN": name}
    return obj


def generate_statement(
    user_id: int,
    verb: str,
    item_id: int,
    item_type: str = "drill",
    name: Optional[str] = None,
    score: Optional[float] = None,
    success: Optional[bool] = None,
    duration_seconds: Optional[float] = None,
    email: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a single xAPI statement."""
    stmt = {
        "id": str(uuid.uuid4()),
        "actor": _make_actor(user_id, email),
        "verb": _make_verb(verb),
        "object": _make_object(item_id, item_type, name),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if score is not None or success is not None or duration_seconds is not None:
        result = {}
        if score is not None:
            result["score"] = {"scaled": min(1.0, max(0.0, score))}
        if success is not None:
            result["success"] = success
        if duration_seconds is not None:
            # ISO 8601 duration
            result["duration"] = f"PT{duration_seconds:.1f}S"
        stmt["result"] = result

    if context:
        stmt["context"] = context

    return stmt


def get_statements(
    conn, user_id: int, since: Optional[str] = None, until: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Generate xAPI statements from error log and session log history.

    Converts stored error_log rows into xAPI "answered" statements and
    session_log rows into xAPI "completed" statements on-the-fly.
    """
    statements = []

    # --- Item-level statements from error_log ---
    err_query = """
        SELECT el.id, el.session_id, el.content_item_id, el.drill_type,
               el.error_type, el.user_answer, el.expected_answer,
               el.created_at,
               ci.hanzi, ci.english
        FROM error_log el
        JOIN content_item ci ON ci.id = el.content_item_id
        WHERE el.user_id = ?
    """
    params: list = [user_id]

    if since:
        err_query += " AND el.created_at >= ?"
        params.append(since)
    if until:
        err_query += " AND el.created_at <= ?"
        params.append(until)

    err_query += " ORDER BY el.created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(err_query, params).fetchall()

    for row in rows:
        stmt = generate_statement(
            user_id=user_id,
            verb="answered",
            item_id=row["content_item_id"],
            item_type="drill",
            name=row["hanzi"],
            score=0.0,
            success=False,
            context={
                "extensions": {
                    f"{ACTIVITY_BASE}/drill-type": row["drill_type"] or "unknown",
                    f"{ACTIVITY_BASE}/session-id": row["session_id"] or 0,
                    f"{ACTIVITY_BASE}/error-type": row["error_type"],
                },
            },
        )
        stmt["timestamp"] = row["created_at"]
        statements.append(stmt)

    # --- Session-level completed statements ---
    sess_query = """
        SELECT id, started_at, ended_at, items_completed, items_correct,
               session_type, duration_seconds
        FROM session_log
        WHERE user_id = ?
    """
    sess_params: list = [user_id]

    if since:
        sess_query += " AND started_at >= ?"
        sess_params.append(since)
    if until:
        sess_query += " AND started_at <= ?"
        sess_params.append(until)

    sess_query += " ORDER BY started_at DESC LIMIT ?"
    sess_params.append(limit)

    sess_rows = conn.execute(sess_query, sess_params).fetchall()

    for row in sess_rows:
        if row["ended_at"]:
            total = row["items_completed"] or 1
            correct = row["items_correct"] or 0
            stmt = generate_statement(
                user_id=user_id,
                verb="completed",
                item_id=row["id"],
                item_type="session",
                score=correct / total if total > 0 else 0.0,
                success=True,
                duration_seconds=float(row["duration_seconds"]) if row["duration_seconds"] else None,
                context={
                    "extensions": {
                        f"{ACTIVITY_BASE}/session-type": row["session_type"],
                    },
                },
            )
            stmt["timestamp"] = row["ended_at"]
            statements.append(stmt)

    # Sort all statements by timestamp descending
    statements.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
    return statements[:limit]
