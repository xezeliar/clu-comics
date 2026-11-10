"""Weekly release calendar: Metron's releases for one comic week, laid out by
day and marked *on pull list* / *in library*.

Pure functions (no Metron, no database) so the grouping and marking are
testable; ``routes/release_calendar.py`` supplies the data. Pull-list matching
is the same rule as the Releases page: the Metron series id, else the
(normalised name, volume) pair.
"""

from datetime import date, datetime, timedelta

RELEASE_WEEKDAY = 2  # Wednesday


def parse_date(raw):
    """``YYYY-MM-DD`` -> datetime, or None (callers fall back to today)."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _issue_date(issue):
    d = getattr(issue, "store_date", None) or getattr(issue, "cover_date", None)
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_week(start, releases, tracked_ids, tracked_lookup, normalize, owned):
    """Seven day buckets from ``start`` (the week's first day).

    ``owned(series_name, number, volume)`` is only asked for pull-list items:
    ownership of a series the user does not follow is not the calendar's
    question, and each answer is a ``file_index`` search.
    """
    days = [
        {
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "weekday": (start + timedelta(days=i)).strftime("%a"),
            "is_release_day": (start + timedelta(days=i)).weekday() == RELEASE_WEEKDAY,
            "items": [],
        }
        for i in range(7)
    ]
    by_date = {d["date"]: d for d in days}
    for issue in releases or []:
        when = _issue_date(issue)
        day = by_date.get(when.strftime("%Y-%m-%d")) if when else None
        if day is None:
            continue
        series = getattr(issue, "series", None)
        name = getattr(series, "name", "") or ""
        volume = getattr(series, "volume", None)
        number = getattr(issue, "number", None) or ""
        on_list = getattr(series, "id", None) in tracked_ids or (
            normalize(name), volume or 0
        ) in tracked_lookup
        day["items"].append({
            "series": name,
            "number": number,
            "series_id": getattr(series, "id", None),
            "on_pull_list": on_list,
            "in_library": bool(on_list and owned(name, number, volume)),
        })
    for day in days:
        day["items"].sort(key=lambda i: (not i["on_pull_list"], i["series"].lower()))
    return days
