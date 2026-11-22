"""The gap report: Wanted's By series view.

``/api/gaps`` is its data and ``/gaps`` redirects there (both Clerk-only, like
Wanted).
"""

from flask import Blueprint, jsonify, redirect, url_for

from core.app_logging import app_logger
from core.gaps import get_gaps

gaps_bp = Blueprint("gaps", __name__)


@gaps_bp.route("/gaps")
def gaps_page():
    # The gap report is now Wanted's By series view; old bookmarks land there.
    return redirect(url_for("series.wanted", view="series"))


@gaps_bp.route("/api/gaps")
def api_gaps():
    try:
        gaps = get_gaps()
    except Exception as e:  # keep the page usable; the log has the cause
        app_logger.error(f"Gap report failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    for g in gaps:
        g["check_url"] = url_for("downloads.api_check_series_missing",
                                 series_id=g["series_id"])
    return jsonify({"success": True, "gaps": gaps,
                    "missing_total": sum(g["missing"] for g in gaps),
                    "search_all_url": url_for("downloads.api_run_getcomics_now")})
