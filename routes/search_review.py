"""Search review: why GetComics candidates were accepted or rejected.

The sweep (``app.scheduled_getcomics_download``) records each searched issue
with its top candidates; with Review before download on it also holds
borderline picks as ``waiting``. This blueprint lists them and lets the user
approve, skip, or ask for a fresh search.

Clerk-level, enforced centrally: ``/search-review`` is in
``core.auth._CLERK_PAGE_PATHS`` and ``/api/search-review`` in ``_CLERK_PREFIXES``.
"""

import uuid

from flask import Blueprint, jsonify, render_template, request

from core.app_logging import app_logger
from core.database import (
    SEARCH_OUTCOMES,
    clear_search_queue_stamps,
    count_waiting_search_attempts,
    get_search_attempt,
    list_search_attempts,
    set_search_attempt_outcome,
)

search_review_bp = Blueprint("search_review", __name__)


@search_review_bp.route("/search-review")
def search_review_page():
    return render_template("search_review.html")


@search_review_bp.route("/api/search-review", methods=["GET"])
def api_list():
    outcome = request.args.get("outcome") or None
    if outcome and outcome not in SEARCH_OUTCOMES:
        return jsonify({"success": False, "error": "Unknown outcome"}), 400
    attempts = list_search_attempts(outcome=outcome)
    if attempts is None:
        return jsonify({"success": False, "error": "Could not read attempts"}), 500
    return jsonify({
        "success": True,
        "attempts": attempts,
        "waiting": count_waiting_search_attempts(),
    })


def queue_candidate(attempt, candidate):
    """Queue one candidate through the same path the sweep uses.

    Returns the number of downloads queued. Raises on no usable link.
    """
    from api import download_progress, download_queue
    from core.settings import get_setting
    from models.getcomics import (
        PROVIDER_LABELS,
        download_filename,
        get_result_parts,
        is_pack_download,
        select_download_url,
        select_parts_for_issue,
    )

    tier = "range fallback" if candidate["decision"] == "FALLBACK" else "direct match"
    parts = select_parts_for_issue(
        get_result_parts({"link": candidate["link"]}),
        attempt["issue_number"], attempt["series_name"],
    )
    priority = get_setting("DOWNLOAD_PROVIDER_PRIORITY")
    queued = 0
    for part in parts:
        (provider, url), fallbacks = select_download_url(part["links"], priority)
        if not url:
            continue
        if part["label"]:
            raw_title = part["label"]
        elif is_pack_download(part, tier):
            raw_title = candidate["title"]
        else:
            raw_title = f"{attempt['series_name']} {attempt['issue_number']}"
        filename = download_filename(raw_title)
        download_id = str(uuid.uuid4())
        download_progress[download_id] = {
            "url": url, "progress": 0, "bytes_total": 0, "bytes_downloaded": 0,
            "status": "queued", "filename": filename, "error": None,
            "provider": PROVIDER_LABELS.get(provider),
        }
        download_queue.put({
            "download_id": download_id, "url": url, "dest_filename": filename,
            "internal": True, "fallback_urls": fallbacks, "provider": provider,
            "page_url": candidate["link"],
        })
        queued += 1
    if not queued:
        raise ValueError("No download link found for this candidate")
    return queued


@search_review_bp.route("/api/search-review/<int:attempt_id>/approve", methods=["POST"])
def api_approve(attempt_id):
    attempt = get_search_attempt(attempt_id)
    if not attempt:
        return jsonify({"success": False, "error": "Not found"}), 404
    if attempt["outcome"] != "waiting":
        return jsonify({"success": False, "error": "Not waiting for approval"}), 409
    wanted = (request.get_json(silent=True) or {}).get("candidate_id")
    cands = attempt["candidates"]
    candidate = next(
        (c for c in cands if wanted is not None and c["id"] == wanted),
        next((c for c in cands if c["chosen"]), None),
    )
    if not candidate:
        return jsonify({"success": False, "error": "No candidate to approve"}), 400
    # Claim first so a double click cannot queue twice.
    if not set_search_attempt_outcome(attempt_id, "queued", only_from="waiting"):
        return jsonify({"success": False, "error": "Not waiting for approval"}), 409
    try:
        queued = queue_candidate(attempt, candidate)
    except Exception as e:
        set_search_attempt_outcome(attempt_id, "waiting")
        app_logger.error(f"Search review approve failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 502
    return jsonify({"success": True, "queued": queued})


@search_review_bp.route("/api/search-review/<int:attempt_id>/skip", methods=["POST"])
def api_skip(attempt_id):
    if not get_search_attempt(attempt_id):
        return jsonify({"success": False, "error": "Not found"}), 404
    if not set_search_attempt_outcome(attempt_id, "skipped", only_from="waiting"):
        return jsonify({"success": False, "error": "Not waiting for approval"}), 409
    return jsonify({"success": True})


@search_review_bp.route("/api/search-review/<int:attempt_id>/research", methods=["POST"])
def api_research(attempt_id):
    """Clear the queue stamps so the next sweep searches this issue again."""
    attempt = get_search_attempt(attempt_id)
    if not attempt:
        return jsonify({"success": False, "error": "Not found"}), 404
    cleared = clear_search_queue_stamps(
        attempt["series_id"], attempt["series_name"], attempt["issue_number"]
    )
    return jsonify({"success": True, "cleared": cleared})
