"""Insights page JSON: the reading overview and the credits re-read job.

Everything here is the current user's own reading data, so a Reader may start
the re-read (``/api/backfill-reading-metadata`` is in
``_READER_WRITE_PREFIXES``). Not under ``/api/insights``: that prefix is
login-exempt for the Homepage widget.
"""

from flask import Blueprint, jsonify

from core import insights
from core.app_logging import app_logger
from core.database import current_user_id

insights_bp = Blueprint("insights", __name__)


@insights_bp.route("/api/reading-overview")
def reading_overview():
    data = insights.get_reading_overview()
    if data is None:
        return jsonify({"success": False, "error": "Reading data unavailable"}), 500
    return jsonify({"success": True, **data})


@insights_bp.route("/api/backfill-reading-metadata", methods=["POST"])
def start_backfill():
    """Start re-reading credits for the current user's read issues.

    Returns an op_id at once; progress shows in Active Operations and the page
    follows ``/api/operation/<op_id>``, then reads the summary below.
    """
    try:
        op_id = insights.start_reading_credits_backfill(current_user_id())
        return jsonify({"success": True, "op_id": op_id}), 202
    except Exception as e:
        app_logger.error(f"Could not start reading credits re-read: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@insights_bp.route("/api/backfill-reading-metadata/<op_id>")
def backfill_result(op_id):
    result = insights.get_backfill_result(op_id)
    if result is None or result.get("user_id") != current_user_id():
        return jsonify({"success": True, "pending": True})
    return jsonify({"success": True, "pending": False, "result": result})
