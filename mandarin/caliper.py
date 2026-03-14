"""IMS Caliper 1.2 analytics event generation.

Generates Caliper events from drill sessions for learning analytics interoperability.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import db
from .settings import CANONICAL_URL

CALIPER_CONTEXT = "http://purl.imsglobal.org/ctx/caliper/v1p2"
CALIPER_BASE = CANONICAL_URL

# Caliper event types
EVENT_TYPES = {
    "assessment": "AssessmentEvent",
    "assessment_item": "AssessmentItemEvent",
    "session": "SessionEvent",
    "grade": "GradeEvent",
}

# Caliper actions
ACTIONS = {
    "started": "Started",
    "completed": "Completed",
    "submitted": "Submitted",
    "graded": "Graded",
    "paused": "Paused",
    "resumed": "Resumed",
}


def _make_person(user_id: int) -> Dict[str, Any]:
    """Create a Caliper Person entity."""
    return {
        "id": f"{CALIPER_BASE}/users/{user_id}",
        "type": "Person",
    }


def _make_assessment(session_id: int) -> Dict[str, Any]:
    """Create a Caliper Assessment entity for a drill session."""
    return {
        "id": f"{CALIPER_BASE}/sessions/{session_id}",
        "type": "Assessment",
        "name": f"Drill Session {session_id}",
    }


def _make_assessment_item(item_id: int, name: Optional[str] = None) -> Dict[str, Any]:
    """Create a Caliper AssessmentItem entity."""
    entity = {
        "id": f"{CALIPER_BASE}/items/{item_id}",
        "type": "AssessmentItem",
    }
    if name:
        entity["name"] = name
    return entity


def generate_event(
    user_id: int,
    event_type: str,
    action: str,
    object_type: str = "assessment",
    object_id: int = 0,
    object_name: Optional[str] = None,
    score: Optional[float] = None,
    duration_seconds: Optional[float] = None,
    extensions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a single Caliper event."""
    event = {
        "@context": CALIPER_CONTEXT,
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": EVENT_TYPES.get(event_type, "Event"),
        "action": ACTIONS.get(action, action),
        "actor": _make_person(user_id),
        "eventTime": datetime.now(timezone.utc).isoformat(),
    }

    if object_type == "assessment":
        event["object"] = _make_assessment(object_id)
    else:
        event["object"] = _make_assessment_item(object_id, object_name)

    if score is not None:
        event["generated"] = {
            "id": f"urn:uuid:{uuid.uuid4()}",
            "type": "Score",
            "scoreGiven": score,
            "maxScore": 1.0,
        }

    if extensions:
        event["extensions"] = extensions

    return event


def get_events(
    conn, user_id: int, since: Optional[str] = None, until: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Generate Caliper events from session log history."""
    events = []

    # Session-level events
    sess_query = """
        SELECT id, started_at, ended_at, items_completed, items_correct,
               session_type, duration_seconds
        FROM session_log
        WHERE user_id = ?
    """
    params: list = [user_id]

    if since:
        sess_query += " AND started_at >= ?"
        params.append(since)
    if until:
        sess_query += " AND started_at <= ?"
        params.append(until)

    sess_query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    for row in conn.execute(sess_query, params).fetchall():
        # Session started event
        started = generate_event(
            user_id=user_id,
            event_type="assessment",
            action="started",
            object_type="assessment",
            object_id=row["id"],
            extensions={
                "session_type": row["session_type"],
            },
        )
        started["eventTime"] = row["started_at"]
        events.append(started)

        # Session completed event (if ended)
        if row["ended_at"]:
            total = row["items_completed"] or 1
            correct = row["items_correct"] or 0
            completed = generate_event(
                user_id=user_id,
                event_type="assessment",
                action="completed",
                object_type="assessment",
                object_id=row["id"],
                score=correct / total if total > 0 else 0.0,
                duration_seconds=float(row["duration_seconds"]) if row["duration_seconds"] else None,
            )
            completed["eventTime"] = row["ended_at"]
            events.append(completed)

    # Sort by eventTime
    events.sort(key=lambda e: e.get("eventTime", ""))
    return events
