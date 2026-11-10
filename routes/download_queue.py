"""Download queue page: active / queued / failed / history, pause, reorder.

Reads and steers api.py's in-memory ``download_queue`` / ``download_progress``
through ``core.download_queue_ctl`` (imported lazily: api.py starts worker
threads at import). Retry, cancel, dismiss and clear reuse api.py's existing
``/retry_download``, ``/cancel_download``, ``/dismiss_download`` and
``/clear_downloads`` routes; only what they cannot do lives here.

Clerk-level, enforced centrally (``/download-queue`` page path and
``/api/download-queue`` prefix in ``core.auth``).
"""

from flask import Blueprint, jsonify, render_template, request

from core import download_queue_ctl as ctl

download_queue_bp = Blueprint("download_queue", __name__)


@download_queue_bp.route("/download-queue")
def page():
    return render_template("download_queue.html", current_page="/download-queue")


@download_queue_bp.route("/api/download-queue", methods=["GET"])
def api_state():
    from api import download_queue, download_progress

    return jsonify({"success": True, **ctl.build_view(download_queue, download_progress)})


@download_queue_bp.route("/api/download-queue/pause", methods=["POST"])
def api_pause():
    """Body ``{"paused": bool}``. Running transfers finish; none new start."""
    data = request.get_json(silent=True) or {}
    ctl.set_paused(bool(data.get("paused", True)))
    return jsonify({"success": True, "paused": ctl.is_paused()})


@download_queue_bp.route("/api/download-queue/reorder", methods=["POST"])
def api_reorder():
    from api import download_queue

    ids = (request.get_json(silent=True) or {}).get("order")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return jsonify({"success": False, "error": "order must be a list of ids"}), 400
    return jsonify({"success": True, "placed": ctl.reorder_queue(download_queue, ids)})


@download_queue_bp.route("/api/download-queue/<download_id>", methods=["DELETE"])
def api_remove(download_id):
    """Remove a download that has not started."""
    from api import download_queue, download_progress

    if not ctl.remove_queued(download_queue, download_progress, download_id):
        return jsonify({"success": False, "error": "Not waiting in the queue"}), 404
    return jsonify({"success": True})
