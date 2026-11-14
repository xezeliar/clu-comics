"""Insights page JSON: the reading overview and the credits re-read job.

Everything here is the current user's own reading data, so a Reader may start
the re-read (``/api/backfill-reading-metadata`` is in
``_READER_WRITE_PREFIXES``). Not under ``/api/insights``: that prefix is
login-exempt for the Homepage widget.
"""

from flask import Blueprint, jsonify, request, url_for

from core import insights, person_art
from core.app_logging import app_logger
from core.database import current_user_id

insights_bp = Blueprint("insights", __name__)


@insights_bp.route("/api/reading-overview")
def reading_overview():
    data = insights.get_reading_overview()
    if data is None:
        return jsonify({"success": False, "error": "Reading data unavailable"}), 500
    return jsonify({"success": True, **data})


# section -> (person_art kind, detail endpoint or None for publishers)
_WHO_LINKS = {
    "teams": ("team", "creators.team_page"),
    "characters": ("character", "creators.character_page"),
    "writers": ("creator", "creators.creator_page"),
    "publishers": ("publisher", None),
}


@insights_bp.route("/api/insights/who")
def who_you_read():
    """Teams, Characters, Writers and Publishers the user read, with photos.

    Under /api/insights but NOT login-exempt: routes/auth.py exempts the
    Homepage widget's exact path only, since this is per-user reading data.
    """
    raw_year = (request.args.get("year") or "all").strip()
    year = int(raw_year) if raw_year.isdigit() else None
    limit = max(1, min(request.args.get("limit", 8, type=int) or 8, 100))
    data = insights.get_who_you_read(year=year)
    out = {}
    for section, ranked in data.items():
        kind, endpoint = _WHO_LINKS[section]
        top = ranked[:limit]
        art = person_art.art_urls(kind, [name for name, _ in top])
        out[section] = {"total": len(ranked), "items": [{
            "name": name,
            "count": count,
            "art": art.get(name),
            "href": (url_for(endpoint, name=name) if endpoint else
                     url_for("collection.browse_by_metadata", category="publisher", name=name)),
        } for name, count in top]}
    return jsonify(out)


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
