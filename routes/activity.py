"""Activity feed: one newest-first timeline of what CLU did (core/activity.py).

Clerk-level, enforced centrally: ``/activity`` is in
``core.auth._CLERK_PAGE_PATHS`` and ``/api/activity`` in ``_CLERK_PREFIXES``.
"""

from flask import Blueprint, jsonify, render_template, request

from core.activity import KINDS, clear_events, count_errors, list_events

activity_bp = Blueprint("activity", __name__)


@activity_bp.route("/activity")
def activity_page():
    return render_template("activity.html", current_page="/activity", kinds=KINDS)


@activity_bp.route("/api/activity", methods=["GET"])
def api_activity():
    """Events newest first; ``kind`` filters, ``before`` pages by event id."""
    from core.user_time import format_user_time

    kind = request.args.get("kind") or None
    if kind and kind not in KINDS:
        return jsonify({"success": False, "error": f"Unknown kind: {kind}"}), 400
    try:
        limit = int(request.args.get("limit", 50))
        before = int(request.args["before"]) if request.args.get("before") else None
    except ValueError:
        return jsonify({"success": False, "error": "limit and before must be numbers"}), 400

    events = list_events(kind=kind, limit=limit, before_id=before)
    if events is None:
        # Never [] -- an empty list has to mean "nothing yet".
        return jsonify({"success": False, "error": "Could not read activity"}), 500
    for e in events:
        e["ts_display"] = format_user_time(e["ts"])
    return jsonify({"success": True, "events": events, "errors_24h": count_errors()})


@activity_bp.route("/api/activity", methods=["DELETE"])
def api_clear_activity():
    """Clear the feed, or one ``kind`` of it. History only: nothing else is touched."""
    kind = request.args.get("kind") or None
    if kind and kind not in KINDS:
        return jsonify({"success": False, "error": f"Unknown kind: {kind}"}), 400
    removed = clear_events(kind)
    if removed is None:
        return jsonify({"success": False, "error": "Could not clear activity"}), 500
    return jsonify({"success": True, "removed": removed})
