"""Data behind the Insights page: the reading overview, the collection facts
and the "Read credits from ComicInfo" background job.

Reading data is always the current (or given) user's. Library counts are
global. Nothing here reads a setting into a module constant.
"""
import os
import threading
from datetime import datetime, timedelta, timezone

from core.app_logging import app_logger
from core.database import _resolve_user_id, db_conn, get_user_preference


def _local_now():
    """Now in the user's configured UTC offset, as a naive datetime."""
    from core.user_time import parse_offset_hours

    hours = parse_offset_hours(get_user_preference("timezone", default="UTC"))
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=hours), hours


def _parse_read_at(value):
    """A stored read_at (UTC text, maybe ISO with a zone) as naive UTC, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def get_reading_overview(user_id=None):
    """Per-day read counts and per-year totals for one user.

    Returns ``{"today", "days": {"YYYY-MM-DD": n}, "years": {"2026": totals},
    "all": totals}`` where totals is ``{issues, pages, seconds, gap}``. Days and
    years are in the user's timezone, so the calendar, the run line and the
    year totals always agree. ``gap`` counts read issues with no writer that a
    credits re-read has not already looked at. Returns None when the database
    cannot be read, so the page shows an error rather than zeros.
    """
    uid = _resolve_user_id(user_id)
    now, hours = _local_now()
    shift = timedelta(hours=hours)
    with db_conn() as conn:
        if not conn:
            return None
        rows = conn.execute(
            "SELECT read_at, page_count, time_spent, writer, credits_read "
            "FROM issues_read WHERE user_id = ?",
            (uid,),
        ).fetchall()

    days, years = {}, {}
    total = {"issues": 0, "pages": 0, "seconds": 0, "gap": 0}
    for read_at, pages, seconds, writer, credits_read in rows:
        dt = _parse_read_at(read_at)
        if dt is None:
            continue
        local = dt + shift
        key = local.strftime("%Y-%m-%d")
        days[key] = days.get(key, 0) + 1
        gap = 1 if not (writer or "").strip() and not credits_read else 0
        for bucket in (years.setdefault(str(local.year), dict.fromkeys(total, 0)), total):
            bucket["issues"] += 1
            bucket["pages"] += pages or 0
            bucket["seconds"] += seconds or 0
            bucket["gap"] += gap
    return {"today": now.strftime("%Y-%m-%d"), "days": days, "years": years, "all": total}


def get_collection_overview(user_id=None):
    """Everything the "Your collection" section draws, in one dict.

    ``read`` is the user's unhidden reads that still have a file in the index,
    so a deleted or moved file never pushes it past the file count.
    ``added_per_month`` and ``added_30`` use ``file_index.modified_at`` -- the
    file's date, not an import date (CLU records none; ``last_updated`` changes
    on every reindex).
    """
    from models.stats import (
        get_file_type_distribution,
        get_largest_comics,
        get_library_stats,
        get_top_publishers,
        get_top_series_by_count,
    )

    uid = _resolve_user_id(user_id)
    lib = get_library_stats() or {}
    now = datetime.now(timezone.utc)
    # The twelve calendar months ending with this one, oldest first.
    months = []
    y, m = now.year, now.month
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months.reverse()
    window_start = datetime(int(months[0][:4]), int(months[0][5:]), 1, tzinfo=timezone.utc).timestamp()

    read = added_30 = missing = missing_series = 0
    per_month = {}
    with db_conn() as conn:
        if conn:
            try:
                read = conn.execute(
                    "SELECT COUNT(DISTINCT ir.issue_path) FROM issues_read ir "
                    "JOIN file_index fi ON fi.path = ir.issue_path AND fi.type = 'file' "
                    "WHERE ir.user_id = ? AND COALESCE(ir.hide, 0) = 0",
                    (uid,),
                ).fetchone()[0] or 0
                added_30 = conn.execute(
                    "SELECT COUNT(*) FROM file_index WHERE type = 'file' AND modified_at >= ?",
                    ((now - timedelta(days=30)).timestamp(),),
                ).fetchone()[0] or 0
                per_month = dict(conn.execute(
                    "SELECT strftime('%Y-%m', modified_at, 'unixepoch') AS m, COUNT(*) "
                    "FROM file_index WHERE type = 'file' AND modified_at >= ? GROUP BY m",
                    (window_start,),
                ).fetchall())
            except Exception as e:
                app_logger.error(f"Insights collection facts failed: {e}")
            try:
                missing, missing_series = conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT series_id) FROM wanted_issues "
                    "WHERE store_date IS NULL OR store_date <= date('now')"
                ).fetchone()
            except Exception:
                pass  # wanted cache not built yet

    return {
        "files": lib.get("total_files", 0),
        "folders": lib.get("total_directories", 0),
        "size": lib.get("total_size", 0),
        "read": min(read, lib.get("total_files", 0)),
        "missing": missing or 0,
        "missing_series": missing_series or 0,
        "added_30": added_30,
        "added_per_month": [{"month": k, "count": per_month.get(k, 0)} for k in months],
        "formats": get_file_type_distribution(),
        "publishers": get_top_publishers(limit=50),
        "series": get_top_series_by_count(limit=20),
        "largest": get_largest_comics(limit=20),
    }


# ── "Read credits from ComicInfo": a background job for one user ──

_results = {}
_results_lock = threading.Lock()


def get_backfill_result(op_id):
    """The finished job's summary, or None while it runs (or if unknown)."""
    with _results_lock:
        return _results.get(op_id)


def _stash(op_id, result):
    with _results_lock:
        _results[op_id] = result
        for stale in list(_results)[:-20]:
            del _results[stale]


def run_reading_credits_backfill(op_id, user_id):
    """Re-read Writer/Penciller/Characters/Publisher from ComicInfo.xml for
    every issue ``user_id`` has read, and mark each row it read so the
    Insights credits-gap note clears even when the file has no credits.

    Files are read with no database lock held; the updates land in one short
    write at the end.
    """
    from core import app_state
    from core.comicinfo import read_comicinfo_from_zip
    from core.database import clear_stats_cache_prefix
    from core.metadata_normalize import normalize_credit_list, strip_provider_ids

    try:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT id, issue_path FROM issues_read WHERE user_id = ?", (user_id,)
            ).fetchall() if conn else []
        app_state.update_operation(op_id, current=0, total=len(rows))

        updates, skipped = [], []
        for n, (row_id, path) in enumerate(rows, 1):
            name = os.path.basename(path)
            app_state.update_operation(op_id, current=n, detail=name)
            if not os.path.exists(path):
                skipped.append({"file": name, "reason": "File not found"})
                continue
            if not path.lower().endswith((".cbz", ".zip")):
                skipped.append({"file": name, "reason": "Not a CBZ/ZIP file"})
                continue
            try:
                info = read_comicinfo_from_zip(path)
            except Exception as e:
                app_logger.debug(f"Could not read ComicInfo.xml for {path}: {e}")
                skipped.append({"file": name, "reason": f"Error: {e}"})
                continue
            if info:
                updates.append((
                    normalize_credit_list(info.get("Writer", "")),
                    normalize_credit_list(info.get("Penciller", "")),
                    normalize_credit_list(info.get("Characters", "")),
                    strip_provider_ids(info.get("Publisher", "")),
                    row_id,
                ))
            else:
                # Read, and nothing to find: mark it so the gap note clears.
                updates.append((None, None, None, None, row_id))
                skipped.append({"file": name, "reason": "No ComicInfo.xml"})

        with db_conn() as conn:
            if conn and updates:
                conn.executemany(
                    "UPDATE issues_read SET writer = COALESCE(?, writer), "
                    "penciller = COALESCE(?, penciller), characters = COALESCE(?, characters), "
                    "publisher = COALESCE(?, publisher), credits_read = 1 "
                    "WHERE id = ? AND user_id = ?",
                    [u + (user_id,) for u in updates],
                )
                conn.commit()
        clear_stats_cache_prefix(f"u{user_id}:")

        updated = len(updates) - sum(1 for u in updates if u[0] is None)
        app_logger.info(f"Reading credits re-read: {updated} updated, {len(skipped)} skipped")
        _stash(op_id, {"user_id": user_id, "updated": updated, "skipped": len(skipped),
                       "skipped_issues": skipped})
        app_state.update_operation(op_id, detail=f"{updated} updated, {len(skipped)} skipped")
        app_state.complete_operation(op_id)
    except Exception as e:
        app_logger.error(f"Reading credits re-read failed: {e}")
        _stash(op_id, {"user_id": user_id, "error": str(e)})
        app_state.complete_operation(op_id, error=True)


def start_reading_credits_backfill(user_id=None):
    """Start the job on a daemon thread; returns its op_id at once."""
    from core import app_state

    uid = _resolve_user_id(user_id)
    op_id = app_state.register_operation(
        "reading_credits", "Reading credits from ComicInfo", user_id=uid
    )
    threading.Thread(
        target=run_reading_credits_backfill, args=(op_id, uid), daemon=True
    ).start()
    return op_id
