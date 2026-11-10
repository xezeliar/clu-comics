"""Weekly release calendar for the pull list (core/release_calendar.py).

Clerk-level, enforced centrally (``/release-calendar`` page path and
``/api/release-calendar`` prefix in ``core.auth``).
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from core.release_calendar import build_week, parse_date
from models import metron

release_calendar_bp = Blueprint("release_calendar", __name__)

FMT = "%Y-%m-%d"


@release_calendar_bp.route("/release-calendar")
def page():
    return render_template("release_calendar.html", current_page="/release-calendar")


def _owned(series_name, number, volume):
    from core.database import search_by_comic_metadata
    from helpers.collection import series_names_compatible

    hits = search_by_comic_metadata(series_name, number, volume=volume, limit=5)
    return any(series_names_compatible(series_name, h.get("ci_series")) for h in hits)


@release_calendar_bp.route("/api/release-calendar", methods=["GET"])
def api_week():
    """One comic week (Sunday-Saturday) around ``date`` (default today)."""
    from core.database import (
        get_mapped_series_ids,
        get_tracked_series_lookup,
        normalize_series_name,
    )

    raw = request.args.get("date")
    anchor = parse_date(raw) if raw else datetime.now()
    if anchor is None:
        return jsonify({"success": False, "error": "date must be YYYY-MM-DD"}), 400

    api = metron.get_flask_api()
    if not api:
        return jsonify({"success": False, "error": "Metron API not configured or unavailable"}), 503

    start, end = metron.calculate_comic_week(anchor)
    releases = metron.get_releases(api, start.strftime(FMT), end.strftime(FMT))
    days = build_week(
        start, releases, get_mapped_series_ids(), get_tracked_series_lookup(),
        normalize_series_name, _owned,
    )
    return jsonify({
        "success": True,
        "start": start.strftime(FMT),
        "end": end.strftime(FMT),
        "prev": (start - timedelta(days=7)).strftime(FMT),
        "next": (start + timedelta(days=7)).strftime(FMT),
        "days": days,
    })
