"""Smart collections and the gap report: pages and their JSON APIs.

Smart collections are per user (``smart_collections.user_id``); a Reader may
manage their own (``/api/smart-collections`` is in ``_READER_WRITE_PREFIXES``).
The gap report is a Clerk feature like Wanted (``/gaps``, ``/api/gaps``).
"""

import os

from flask import Blueprint, jsonify, render_template, request, url_for

from core import smart_collections as sc
from core.app_logging import app_logger
from core.auth import accessible_folder_prefixes, current_user
from core.database import get_series_slugs_for_folders
from core.gaps import get_gaps

smart_collections_bp = Blueprint("smart_collections", __name__)

PAGE_SIZE = 60


@smart_collections_bp.route("/smart-collections")
def smart_collections_page():
    return render_template(
        "smart_collections.html",
        fields={k: {"kind": v[0], "ops": list(v[2])} for k, v in sc.FIELDS.items()},
        sorts=list(sc.SORTS),
    )


def _with_count(coll, prefixes):
    return dict(coll, count=sc.count_matches(coll, prefixes))


@smart_collections_bp.route("/api/smart-collections", methods=["GET"])
def api_list():
    prefixes = accessible_folder_prefixes(current_user())
    return jsonify({"success": True, "collections": [
        _with_count(c, prefixes) for c in sc.list_collections()]})


def _save(coll_id=None):
    try:
        saved = sc.save_collection(request.get_json(silent=True), coll_id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    if saved is None:
        return jsonify({"success": False, "error": "Collection not found"}), 404
    coll = _with_count(sc.get_collection(saved),
                       accessible_folder_prefixes(current_user()))
    return jsonify({"success": True, "collection": coll}), (201 if coll_id is None else 200)


@smart_collections_bp.route("/api/smart-collections", methods=["POST"])
def api_create():
    return _save()


@smart_collections_bp.route("/api/smart-collections/<int:coll_id>", methods=["PUT"])
def api_update(coll_id):
    return _save(coll_id)


@smart_collections_bp.route("/api/smart-collections/<int:coll_id>", methods=["DELETE"])
def api_delete(coll_id):
    if not sc.delete_collection(coll_id):
        return jsonify({"success": False, "error": "Collection not found"}), 404
    return jsonify({"success": True})


@smart_collections_bp.route("/api/smart-collections/<int:coll_id>/issues")
def api_issues(coll_id):
    coll = sc.get_collection(coll_id)
    if not coll:
        return jsonify({"success": False, "error": "Collection not found"}), 404
    try:
        offset = max(0, int(request.args.get("offset", 0)))
        limit = min(200, max(1, int(request.args.get("limit", PAGE_SIZE))))
    except (TypeError, ValueError):
        offset, limit = 0, PAGE_SIZE
    items, total = sc.collection_issues(
        coll, offset, limit, accessible_folder_prefixes(current_user()))
    # An issue in a folder mapped to a series links to its series page.
    slugs = get_series_slugs_for_folders(
        [os.path.dirname(it["path"]) for it in items])
    for it in items:
        it["thumbnail_url"] = url_for("get_thumbnail", path=it["path"])
        slug = slugs.get(os.path.dirname(it["path"]))
        it["series_url"] = url_for("series.series_view", slug=slug) if slug else None
    return jsonify({"success": True, "items": items, "total": total,
                    "offset": offset, "limit": limit})


@smart_collections_bp.route("/gaps")
def gaps_page():
    return render_template("gaps.html")


@smart_collections_bp.route("/api/gaps")
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
