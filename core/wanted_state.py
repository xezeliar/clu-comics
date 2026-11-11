"""What CLU did about each wanted issue, and Ignore.

Nothing new is recorded. An issue's state is the newest ``download_run_items``
row for its series and number (core/download_runs.py): its outcome, provider,
detail and download status. No row means it was never searched. Run item lists
are capped (``items_truncated``), so a capped run counts as searched only for
the items it actually lists -- an issue past the cap simply has no row.

Ignore is the existing ``issue_manual_status`` row with status ``skipped``,
which the wanted cache, the sweep and the series counts already subtract.
"""

from collections import defaultdict

from core.app_logging import app_logger
from core.database import db_conn

_QUEUED = ("queued", "duplicate")
_FAILED = ("failed", "interrupted", "cancelled")
_DOWNLOADED = ("complete", "complete_no_move")


def derive_state(row, tries=0, progress=None):
    """One issue's state from its newest run item (or None).

    ``progress`` is the live ``api.download_progress`` entry for the item's
    download, when there is one. Wording matches the Downloads page.
    """
    if not row:
        return {"code": "not_searched", "label": "Not searched yet"}
    base = {
        "provider": row.get("provider"),
        "detail": row.get("detail"),
        "when": row.get("when"),
    }
    status = row.get("download_status")
    if row.get("outcome") in _QUEUED:
        if status in _FAILED:
            return dict(base, code="failed", label="Failed")
        if status in _DOWNLOADED:
            # Downloaded but not filed into the library yet.
            return dict(base, code="waiting", label="Downloaded, waiting to be filed")
        pct = (progress or {}).get("progress")
        if isinstance(pct, (int, float)) and 0 < pct < 100:
            return dict(base, code="downloading", label=f"Downloading {int(pct)}%",
                        pct=int(pct))
        return dict(base, code="waiting", label="Waiting in Downloads")
    return dict(base, code="not_found", label="Not found", tries=tries or 1)


def issue_states():
    """{(series_id, issue_number): state} for every issue a run listed."""
    from core.download_utils import _live_download_progress

    progress = _live_download_progress() or {}
    out = {}
    try:
        with db_conn() as conn:
            if not conn:
                return out
            rows = conn.execute(
                """
                SELECT d.series_id, d.issue_number, d.outcome, d.provider, d.detail,
                       d.download_id, d.download_status, d.updated_at AS "when", t.tries
                FROM download_run_items d
                JOIN (SELECT MAX(id) AS id,
                             SUM(outcome NOT IN ('queued', 'duplicate')) AS tries
                      FROM download_run_items WHERE series_id IS NOT NULL
                      GROUP BY series_id, issue_number) t ON t.id = d.id
                """
            ).fetchall()
    except Exception as e:
        app_logger.error(f"Could not read wanted issue states: {e}")
        return out
    for r in rows:
        r = dict(r)
        out[(r["series_id"], str(r["issue_number"]))] = derive_state(
            r, r["tries"], progress.get(r["download_id"]) if r["download_id"] else None)
    return out


def get_ignored_issues():
    """Every issue marked skipped, with what the Wanted rows show."""
    try:
        with db_conn() as conn:
            if not conn:
                return []
            rows = conn.execute(
                """
                SELECT ims.series_id, ims.issue_number, s.name AS series_name,
                       s.volume AS series_volume, MIN(i.id) AS issue_id,
                       MIN(i.name) AS issue_name, MIN(i.store_date) AS store_date,
                       MIN(i.cover_date) AS cover_date
                FROM issue_manual_status ims
                JOIN series s ON s.id = ims.series_id
                LEFT JOIN issues i ON i.series_id = ims.series_id
                                  AND i.number = ims.issue_number
                WHERE ims.status = 'skipped'
                GROUP BY ims.id
                ORDER BY s.name COLLATE NOCASE, ims.series_id, ims.issue_number
                """
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        app_logger.error(f"Could not read ignored wanted issues: {e}")
        return []


def parse_issues(data):
    """The request body's ``issues`` list as a set of (series_id, number) pairs.

    Anything malformed is dropped; the caller answers 400 for an empty set.
    """
    out = set()
    items = (data or {}).get("issues") if isinstance(data, dict) else None
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        try:
            sid = int(it.get("series_id"))
        except (TypeError, ValueError):
            continue
        num = str(it.get("issue_number") or "").strip()
        if num and len(num) <= 40:
            out.add((sid, num))
    return out


def _by_series(issues):
    groups = defaultdict(list)
    for sid, num in issues:
        groups[int(sid)].append(str(num))
    return groups


def ignore_issues(issues):
    """Mark (series_id, issue_number) pairs skipped and drop them from Wanted."""
    from core.database import bulk_set_manual_status, remove_wanted_issues

    done = 0
    for sid, nums in _by_series(issues).items():
        if bulk_set_manual_status(sid, nums, "skipped") >= 0:
            remove_wanted_issues(sid, nums)
            done += len(nums)
    return done


def unignore_issues(issues):
    """Clear the skipped mark (only that one, never 'owned') and recompute the
    series' wanted rows so the issues come back at once."""
    from helpers.collection import rebuild_wanted_for_series

    groups = _by_series(issues)
    done = 0
    with db_conn() as conn:
        if not conn:
            return 0
        for sid, nums in groups.items():
            marks = ",".join("?" * len(nums))
            done += conn.execute(
                "DELETE FROM issue_manual_status WHERE status = 'skipped' AND series_id = ?"
                f" AND issue_number IN ({marks})", [sid, *nums]).rowcount
        conn.commit()
    for sid in groups:
        rebuild_wanted_for_series(sid)
    return done
