"""Turn Monitor off for a series that has ended and is fully owned.

A finished run whose every issue is already in its folder has nothing left to
search for. The Scan Library import has always applied that rule to the series
it creates; this module is the one copy of it, so it can also run for series
subscribed from the Pull List and for series that finish after they were added.

Things that look arbitrary and are not:

* **It only ever turns Monitor off, and only once per series.**
  ``series.monitor_locked`` records that Monitor was decided -- by this module,
  or by the user through any Monitor toggle -- and a locked series is never
  touched again. A user who turns Monitor back on keeps it on.
* **"Owned" means a file was found.** An issue marked Skipped or Owned by hand
  does not count: Skipped is how an event reader says "I don't want this", and
  turning such a series off is the user's call, not ours.
* **"Ended" is the provider's status** (Completed, Cancelled, Ended), the same
  set the series page uses for Year Ended. Not the Pull List's green "Complete",
  which only means nothing is missing *today*.
"""

import os

from core.app_logging import app_logger
from core.series_status import FINISHED_STATUSES, status_text


def is_finished(series):
    """True when the series' status says no more issues are coming."""
    return status_text(series) in FINISHED_STATUSES


def is_fully_owned(match_status):
    """True when every known issue was matched to a file on disk.

    ``match_status`` is what ``match_issues_to_collection`` returns. An empty
    one is not "fully owned": a series with no issue data proves nothing.
    """
    if not match_status:
        return False
    return all(entry.get("found") for entry in match_status.values())


def is_candidate(series):
    """Cheap pre-check on a series row, before any folder is matched."""
    if series.get("monitored") == 0:
        return False
    if series.get("monitor_locked"):
        return False
    return is_finished(series)


def maybe_auto_unmonitor(series_id, series, match_status, logger=None):
    """Apply the rule to one series whose match is already in hand.

    Returns True when Monitor was turned off by this call.
    """
    if not series_id or not is_finished(series):
        return False
    if not is_fully_owned(match_status):
        return False

    from core.database import auto_unmonitor_series

    if not auto_unmonitor_series(series_id):
        return False  # already off, or the user already decided

    name = series.get("name") if isinstance(series, dict) else getattr(series, "name", None)
    (logger or app_logger).info(
        f"Monitor turned off for {name or series_id} ({series_id}): "
        f"'{status_text(series)}' and every issue is in the folder"
    )
    return True


def check_series(series):
    """Match one mapped series row against its folder and apply the rule.

    For callers holding a row from ``get_all_mapped_series`` but no match yet.
    The match goes through the collection-status cache, so an unchanged folder
    costs no rescan.
    """
    if not is_candidate(series):
        return False

    mapped_path = series.get("mapped_path")
    if not mapped_path or not os.path.isdir(mapped_path):
        return False

    from core.database import get_issues_for_series
    from helpers.collection import match_issues_to_collection
    from models.issue import IssueObj, SeriesObj

    issues = get_issues_for_series(series["id"])
    if not issues:
        return False

    match_status = match_issues_to_collection(
        mapped_path, [IssueObj(i) for i in issues], SeriesObj(series)
    )
    return maybe_auto_unmonitor(series["id"], series, match_status)


def sweep_finished_series(series_list=None):
    """Apply the rule to every mapped series that could qualify.

    Run after the scheduled Metron sync, which is what learns that a series
    ended. Series that cannot qualify are skipped before their folder is read,
    and one series failing never stops the rest. Returns the number turned off.
    """
    if series_list is None:
        from core.database import get_all_mapped_series

        series_list = get_all_mapped_series()

    turned_off = 0
    for series in series_list or ():
        try:
            if check_series(series):
                turned_off += 1
        except Exception as e:
            app_logger.warning(
                f"Auto-monitor check failed for series {series.get('id')}: {e}"
            )
    if turned_off:
        app_logger.info(
            f"Monitor turned off for {turned_off} finished, fully owned series"
        )
    return turned_off
