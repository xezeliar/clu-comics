"""What the series page shows under "Year Ended".

The page used to print ``year_end or 'Ongoing'``, so every series Metron has no
end year for read as ongoing -- including one-shots, annuals and cancelled runs
whose Status beside it said Completed or Cancelled. Metron often leaves
``year_end`` blank on exactly those, so the status is the source of truth and
the year is only a detail.

The series *type* (One-Shot, Annual, Limited Series, Single Issue...) does not
enter into it: a cancelled Single Issue run has ended, an ongoing one has not.
"""

FINISHED_STATUSES = {"completed", "complete", "cancelled", "canceled", "ended"}
HIATUS_STATUSES = {"hiatus", "on hiatus"}
ONGOING_STATUSES = {"ongoing", "continuing"}

ONGOING = "Ongoing"
HIATUS = "On hiatus"
FINISHED = "Finished"
UNKNOWN = "-"


def _field(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def status_text(series):
    """The series status as plain lower-case text.

    A cached series stores a string; a live mokkari series may carry an object
    with a ``name``. Either way an empty answer is ``''``.
    """
    status = _field(series, "status")
    if status is None:
        return ""
    name = getattr(status, "name", None)
    text = name if isinstance(name, str) else str(status)
    return text.strip().lower()


def _year(value):
    """The year of a date, a datetime or an ISO date string, else None."""
    if value is None:
        return None
    year = getattr(value, "year", None)
    if isinstance(year, int):
        return year
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def last_issue_year(issues):
    """The latest cover year (store year as a fallback) among the issues."""
    years = []
    for issue in issues or ():
        year = _year(_field(issue, "cover_date")) or _year(_field(issue, "store_date"))
        if year:
            years.append(year)
    return max(years) if years else None


def year_ended_label(series, issues=None):
    """The text for the series page's Year Ended field.

    * an end year from the provider is shown as is;
    * a finished series (Completed / Cancelled / Ended) without one shows the
      year of its last issue, or "Finished" when no issue is dated;
    * Ongoing shows "Ongoing", Hiatus "On hiatus";
    * anything else (no status, a status we do not know) shows "-" rather
      than guessing "Ongoing".
    """
    end = _field(series, "year_ended") or _field(series, "year_end")
    if end:
        return str(end)

    status = status_text(series)
    if status in FINISHED_STATUSES:
        year = last_issue_year(issues)
        return str(year) if year else FINISHED
    if status in ONGOING_STATUSES:
        return ONGOING
    if status in HIATUS_STATUSES:
        return HIATUS
    return UNKNOWN
