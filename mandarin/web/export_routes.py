"""Export routes — CSV, xAPI, Caliper, Common Cartridge."""

import logging
import sqlite3
from datetime import date as dt_date

from flask import Blueprint, jsonify, request, Response
from flask_login import current_user

from .. import db
from ..tier_gate import check_tier_access
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)

export_bp = Blueprint("export", __name__)


def _csv_response(export_fn, label):
    """Helper to generate CSV download responses."""
    from ..export import to_csv_string
    try:
        with db.connection() as conn:
            header, data = export_fn(conn)
        csv_text = to_csv_string(header, data)
        filename = f"mandarin_{label}_{dt_date.today().isoformat()}.csv"
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except (sqlite3.Error, OSError, KeyError, TypeError) as e:
        logger.error("export %s error: %s", label, e)
        return jsonify({"error": "Export failed"}), 500


@export_bp.route("/api/export/progress")
@api_error_handler("Export progress")
def export_progress():
    """Download progress data as CSV."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if not check_tier_access(conn, user_id, "export"):
            return jsonify({"error": "Upgrade to access exports"}), 403
    from ..export import export_progress_csv
    return _csv_response(export_progress_csv, "progress")


@export_bp.route("/api/export/sessions")
@api_error_handler("Export sessions")
def export_sessions():
    """Download session history as CSV."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if not check_tier_access(conn, user_id, "export"):
            return jsonify({"error": "Upgrade to access exports"}), 403
    from ..export import export_sessions_csv
    return _csv_response(export_sessions_csv, "sessions")


@export_bp.route("/api/export/errors")
@api_error_handler("Export errors")
def export_errors():
    """Download error log as CSV."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if not check_tier_access(conn, user_id, "export"):
            return jsonify({"error": "Upgrade to access exports"}), 403
    from ..export import export_errors_csv
    return _csv_response(export_errors_csv, "errors")


@export_bp.route("/api/xapi/statements")
@api_error_handler("xAPI statements")
def api_xapi_statements():
    """Return xAPI statements for the authenticated user."""
    user_id = _get_user_id()
    from ..xapi import get_statements
    with db.connection() as conn:
        since = request.args.get("since")
        until = request.args.get("until")
        statements = get_statements(conn, user_id, since=since, until=until)
        return jsonify({"statements": statements})


@export_bp.route("/api/caliper/events")
@api_error_handler("Caliper events")
def api_caliper_events():
    """Return Caliper 1.2 events for the authenticated user."""
    user_id = _get_user_id()
    from ..caliper import get_events
    with db.connection() as conn:
        since = request.args.get("since")
        events = get_events(conn, user_id, since=since)
        return jsonify({"events": events})


@export_bp.route("/api/export/common-cartridge")
def api_export_cc():
    """Export vocabulary as Common Cartridge ZIP."""
    user_id = _get_user_id()
    with db.connection() as gate_conn:
        if not check_tier_access(gate_conn, user_id, "export"):
            return jsonify({"error": "Upgrade to access exports"}), 403
    level = request.args.get("level", 1, type=int)
    try:
        from ..cc_export import export_cc
        with db.connection() as conn:
            zip_bytes = export_cc(conn, user_id, level)
            return Response(
                zip_bytes,
                mimetype="application/zip",
                headers={"Content-Disposition": f'attachment; filename="mandarin-hsk{level}.imscc"'},
            )
    except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
        logger.error("CC export error: %s", e)
        return jsonify({"error": "Export failed"}), 500
