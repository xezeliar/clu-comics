"""Download queue controls: pause, reorder, remove, and a classified view.

api.py owns the in-memory ``download_queue`` and ``download_progress`` and runs
three worker threads in ONE gunicorn worker, so everything here takes those
objects as arguments (api.py cannot be imported by tests) and the pause flag is
a plain process-local Event. Nothing here is persisted: a restart empties the
queue exactly as it always did.
"""

import threading

from core.download_utils import build_status_snapshot

_resumed = threading.Event()
_resumed.set()


def is_paused():
    return not _resumed.is_set()


def set_paused(paused):
    """Pause stops workers taking new tasks; running transfers finish."""
    if paused:
        _resumed.clear()
    else:
        _resumed.set()


def wait_if_paused():
    """Called by each worker before taking (and after taking) a task."""
    _resumed.wait()


def _task_ids(queue):
    return [t.get("download_id") for t in list(queue.queue) if isinstance(t, dict)]


def reorder_queue(queue, ordered_ids):
    """Reorder the still-queued tasks named in ``ordered_ids``.

    Tasks keep the slots they already occupy; only which listed task sits in
    which slot changes. Unlisted tasks and shutdown sentinels never move.
    Returns the number of tasks placed.
    """
    with queue.mutex:
        items = list(queue.queue)
        slots = [i for i, t in enumerate(items)
                 if isinstance(t, dict) and t.get("download_id") in ordered_ids]
        by_id = {items[i]["download_id"]: items[i] for i in slots}
        wanted = [by_id[d] for d in ordered_ids if d in by_id]
        for slot, task in zip(slots, wanted):
            items[slot] = task
        queue.queue.clear()
        queue.queue.extend(items)
    return len(wanted)


def remove_queued(queue, progress, download_id):
    """Take a not-yet-started task out of the queue and forget it.

    Returns False if it is not waiting in the queue (already running, or gone).
    """
    with queue.mutex:
        items = list(queue.queue)
        keep = [t for t in items
                if not (isinstance(t, dict) and t.get("download_id") == download_id)]
        if len(keep) == len(items):
            return False
        queue.queue.clear()
        queue.queue.extend(keep)
        # Workers call task_done() per get(); keep the unfinished count honest.
        queue.unfinished_tasks = max(0, queue.unfinished_tasks - (len(items) - len(keep)))
    progress.pop(download_id, None)
    return True


def _row(download_id, e):
    return {
        "id": download_id,
        "name": e.get("filename") and str(e["filename"]).rsplit("/", 1)[-1]
                or e.get("url") or download_id,
        "provider": e.get("provider"),
        "status": e.get("status"),
        "progress": e.get("progress") or 0,
        "bytes_total": e.get("bytes_total") or 0,
        "bytes_downloaded": e.get("bytes_downloaded") or 0,
        "error": e.get("error"),
        "retry_in": e.get("retry_in"),
        "retry_count": e.get("retry_count") or 0,
        "retry_max": e.get("retry_max"),
        # Cloudflare marker: the page offers "Download manually", not Retry.
        "manual_url": e.get("manual_url"),
    }


def build_view(queue, progress):
    """Classify downloads into the page's tabs; queued rows in queue order."""
    snap = build_status_snapshot(progress)
    order = {d: i for i, d in enumerate(_task_ids(queue))}
    view = {"paused": is_paused(), "active": [], "queued": [], "failed": [], "history": []}
    for did, e in snap.items():
        if not isinstance(e, dict):
            continue
        status = e.get("status")
        if status == "in_progress" or status == "retry_pending":
            view["active"].append(_row(did, e))
        elif status == "queued":
            view["queued"].append(_row(did, e))
        elif status == "error":
            view["failed"].append(_row(did, e))
        elif status in ("complete", "cancelled"):
            view["history"].append(_row(did, e))
    view["queued"].sort(key=lambda r: order.get(r["id"], len(order)))
    return view

