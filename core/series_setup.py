"""Set up the series a reading list touches, in one go.

An event reading order spans many series, and following one meant subscribing
to each series by hand (for its folder, cvinfo and series.json), then marking
every issue outside the event as Skipped. This does it from the list:

1. ``resolve_list`` groups the list's entries by series and finds each series
   on Metron -- by an entry's Metron issue id, by its ComicVine volume id, or
   by name. Nothing is written; the result is a preview the user confirms.
2. ``apply_setup`` caches each chosen series and its issues, then subscribes it
   through core.series_subscribe -- the same body as the Subscribe button --
   usually as Not monitored, so only the list's own issues are wanted (through
   the list's track-wanted option) rather than whole runs.

Things that look arbitrary and are not:

* **Resolution never guesses between candidates.** An id answers the question;
  a name answers it only when exactly one Metron series has that name (and the
  list's year, when it gives one). Anything else comes back as ``choose`` with
  the candidates, for the user to pick. Filing a download into the wrong
  series' folder is far worse than one more click.
* **One lookup per series, not per issue.** Entries are grouped first, and an
  issue id is looked up in the local ``issues`` table before Metron is asked.
* **A series already on the Pull List is reported, never changed.** Its folder
  and Monitor setting are the user's.
* **Groups are split by the volume's start year** as well as by name, so X-Men
  (1991) and X-Men (2019) in one list stay two series. Never by an entry's
  ``year`` alone: a CBL stores the *issue's* year there (Dark Nights: Metal
  #1-3 say 2017, #4-6 say 2018) and the volume's in ``volume``, while a Metron
  import writes the volume year into ``year``. CBLLoader.entry_year_hints is
  the one reader of that. An entry with a ComicVine volume id is grouped by
  the id, which settles it outright.
* **Two groups that turn out to be one series are merged** after resolving,
  and a series picked twice is set up once -- a second subscribe would only
  fail as "already on your Pull List".
"""

from core.app_logging import app_logger

RESOLVED = "resolved"  # found; can be set up
MAPPED = "mapped"  # already on the Pull List; left alone
CHOOSE = "choose"  # several candidates; the user picks
UNRESOLVED = "unresolved"  # nothing found

MAX_CANDIDATES = 8


def _norm(name):
    from core.wanted_reading_lists import _norm_series

    return _norm_series(name)


def _get(obj, *keys):
    """First non-empty attribute or key of ``obj`` among ``keys``."""
    for key in keys:
        value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if value not in (None, ""):
            return value
    return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def group_entries(entries):
    """Group reading-list entries by series, in the list's order.

    Returns a list of dicts: ``name``, ``year``, ``issues`` (numbers, in list
    order), ``metron_ids`` and ``cv_volume_ids`` (the ids the entries carry).
    Entries with no series name are left out: they cannot name a series.
    """
    from models.cbl import CBLLoader

    groups = {}
    for entry in entries or ():
        name = (entry.get("series") or "").strip()
        if not name:
            continue
        year, _issue_years = CBLLoader.entry_year_hints(entry)
        cv_volume_id = _as_int(entry.get("cv_volume_id"))
        key = ("cv", cv_volume_id) if cv_volume_id else (_norm(name), year)
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "key": f"{key[0]}|{key[1] or ''}",
                "name": name,
                "year": year,
                "issues": [],
                "metron_ids": [],
                "cv_volume_ids": [],
            }
        number = str(entry.get("issue_number") or "").strip()
        if number and number not in group["issues"]:
            group["issues"].append(number)
        for field, bucket in (("metron_id", "metron_ids"), ("cv_volume_id", "cv_volume_ids")):
            value = _as_int(entry.get(field))
            if value and value not in group[bucket]:
                group[bucket].append(value)
    return list(groups.values())


def _series_id_from_issue(api, issue_id):
    """The Metron series of an issue: the local cache first, then Metron."""
    from core.database import get_issue_by_id

    cached = get_issue_by_id(issue_id)
    if cached and cached.get("series_id"):
        return cached["series_id"]
    issue = api.using(context=f"resolving issue {issue_id}").issue(issue_id)
    series = getattr(issue, "series", None) if issue is not None else None
    return getattr(series, "id", None)


def _candidate(obj):
    return {
        "series_id": _get(obj, "id"),
        "name": _get(obj, "name", "display_name", "series") or "",
        "year_began": _as_int(_get(obj, "year_began")),
        "volume": _get(obj, "volume"),
        "issue_count": _get(obj, "issue_count"),
    }


def _by_name(api, group):
    """Resolve a group by name. Returns (series_id or None, candidates)."""
    results = api.using(context=f"searching for series '{group['name']}'").series_list(
        {"name": group["name"]}
    )
    if not results:
        return None, []
    candidates = [_candidate(s) for s in results]
    want = _norm(group["name"])
    exact = [c for c in candidates if _norm(c["name"]) == want]
    year = group.get("year")
    if year:
        same_year = [c for c in exact if c["year_began"] == year]
        if len(same_year) == 1:
            return same_year[0]["series_id"], []
    elif len(exact) == 1:
        return exact[0]["series_id"], []

    pool = exact or candidates
    if year:
        pool = sorted(pool, key=lambda c: abs((c["year_began"] or 9999) - year))
    return None, pool[:MAX_CANDIDATES]


def find_series_id(api, group):
    """Find the Metron series for a group. Returns (series_id, how, candidates).

    ``how`` is "issue" (an entry's Metron issue id), "comicvine" (a ComicVine
    volume id Metron knows) or "name"; candidates are only returned when the
    name was ambiguous.
    """
    for issue_id in group["metron_ids"][:2]:
        series_id = _series_id_from_issue(api, issue_id)
        if series_id:
            return series_id, "issue", []

    if group["cv_volume_ids"]:
        from models.metron import get_series_id_by_comicvine_id

        series_id = get_series_id_by_comicvine_id(api, group["cv_volume_ids"][0])
        if series_id:
            return series_id, "comicvine", []

    series_id, candidates = _by_name(api, group)
    return series_id, ("name" if series_id else None), candidates


def series_details(api, series_id):
    """Name, years, volume, publisher and status of a series, for display and paths.

    The local cache answers for a series CLU already knows; otherwise one
    Metron call.
    """
    from core.database import get_series_by_id
    from core.series_status import status_text

    cached = get_series_by_id(series_id)
    if cached:
        return {
            "series_id": series_id,
            "name": cached.get("name") or "",
            "year_began": cached.get("year_began") or cached.get("volume_year"),
            "volume": cached.get("volume"),
            "publisher_name": cached.get("publisher_name"),
            "status": cached.get("status") or "",
            "issue_count": cached.get("issue_count"),
        }

    from models.metron import get_series

    info = get_series(api, series_id)
    if info is None:
        return None
    publisher = getattr(info, "publisher", None)
    return {
        "series_id": series_id,
        "name": getattr(info, "name", "") or "",
        "year_began": getattr(info, "year_began", None),
        "volume": getattr(info, "volume", None),
        "publisher_name": getattr(publisher, "name", None) if publisher else None,
        "status": status_text(info).title(),
        "issue_count": getattr(info, "issue_count", None),
    }


def resolve_list(api, entries, pattern=None, progress_cb=None):
    """Preview the series behind a reading list. Writes nothing.

    Returns one row per series group with ``state`` RESOLVED, MAPPED, CHOOSE or
    UNRESOLVED. A RESOLVED row carries ``relative_path``: the Subscribe folder
    for the series under a library root (the dialog adds the root). One group
    failing (Metron unreachable for it) makes that row UNRESOLVED; the rest
    still resolve.
    """
    from core.database import get_mapped_series_ids, get_series_mapping
    from core.series_subscribe import build_subscribe_path

    groups = group_entries(entries)
    mapped_ids = get_mapped_series_ids() or set()
    rows = []
    row_for_series = {}  # series id -> its row, to merge groups that are one series

    for i, group in enumerate(groups):
        row = {
            "key": group["key"],
            "list_name": group["name"],
            "list_year": group["year"],
            "issues": group["issues"],
            "state": UNRESOLVED,
            "how": None,
            "series": None,
            "candidates": [],
            "relative_path": None,
            "mapped_path": None,
        }
        try:
            series_id, how, candidates = find_series_id(api, group)
            if series_id and series_id in row_for_series:
                # Another group already resolved to this series (the list spells
                # it differently, or dates its issues differently): one row.
                merged = row_for_series[series_id]
                for number in group["issues"]:
                    if number not in merged["issues"]:
                        merged["issues"].append(number)
                row = None
            elif series_id:
                row_for_series[series_id] = row
                details = series_details(api, series_id)
                if details:
                    row["series"] = details
                    row["how"] = how
                    if series_id in mapped_ids:
                        row["state"] = MAPPED
                        row["mapped_path"] = get_series_mapping(series_id)
                    else:
                        row["state"] = RESOLVED
                        row["relative_path"] = build_subscribe_path(details, "", pattern)
            elif candidates:
                row["state"] = CHOOSE
                row["candidates"] = [
                    {**c, "mapped": c["series_id"] in mapped_ids} for c in candidates
                ]
        except Exception as e:
            app_logger.warning(f"Series setup: could not resolve '{group['name']}': {e}")
        if row is not None:
            rows.append(row)
        if progress_cb:
            progress_cb(i + 1, len(groups), group["name"])

    return rows


def cache_series(api, series_id):
    """Make sure a series and its issues are in the local database.

    Subscribing reads the series from the database, and its issue list is what
    the Wanted page and the collection match work from. A series the user has
    opened before is already there; otherwise this is two Metron calls.
    Returns the series row, or None when Metron could not supply it.
    """
    from core.database import (
        get_issues_for_series,
        get_series_by_id,
        get_series_mapping,
        save_issues_bulk,
        save_publisher,
        save_series_mapping,
        update_series_sync_time,
    )
    from models.metron import get_all_issues_for_series, get_series

    cached = get_series_by_id(series_id)
    if cached and get_issues_for_series(series_id):
        return cached

    info = get_series(api, series_id)
    if info is None:
        return None

    publisher = getattr(info, "publisher", None)
    if publisher is not None and getattr(publisher, "id", None):
        save_publisher(publisher.id, getattr(publisher, "name", None))

    if hasattr(info, "model_dump"):
        series_dict = info.model_dump(mode="json")
    elif isinstance(info, dict):
        series_dict = dict(info)
    else:
        series_dict = {"id": series_id, "name": getattr(info, "name", "")}
    series_dict["id"] = series_id

    issues = list(get_all_issues_for_series(api, series_id) or [])
    cover = None
    if issues:
        def number(issue):
            value = _get(issue, "number")
            text = str(value or "").replace(".", "", 1)
            return float(value) if text.isdigit() else 999

        image = _get(sorted(issues, key=number)[0], "image")
        cover = str(image) if image else None

    # The series row first: the issues reference it.
    save_series_mapping(series_dict, get_series_mapping(series_id) or None, cover)
    save_issues_bulk(issues, series_id)
    update_series_sync_time(series_id, len(issues))
    return get_series_by_id(series_id)


def apply_setup(api, choices, monitored=False, pattern=None, library_path=None,
                progress_cb=None):
    """Subscribe each chosen series. Returns one result per choice.

    ``choices`` is a list of ``{"series_id", "path"}``; a missing path is built
    from the Subscribe pattern under ``library_path``. A series already mapped
    is skipped, untouched. One series failing never stops the rest.
    """
    from core.database import get_mapped_series_ids
    from core.series_subscribe import build_subscribe_path, subscribe_series
    from helpers.collection import rebuild_wanted_for_series

    mapped_ids = get_mapped_series_ids() or set()
    results = []

    # One series picked twice (two rows the user resolved to the same series)
    # is set up once; the repeat is dropped, not reported as a failure.
    seen = set()
    unique = []
    for choice in choices or ():
        series_id = _as_int(choice.get("series_id"))
        if series_id and series_id in seen:
            continue
        seen.add(series_id)
        unique.append(choice)
    choices = unique

    for i, choice in enumerate(choices):
        series_id = _as_int(choice.get("series_id"))
        result = {"series_id": series_id, "ok": False, "path": None, "error": None}
        try:
            if not series_id:
                result["error"] = "No series chosen"
            elif series_id in mapped_ids:
                result["error"] = "Already on your Pull List; left as it is"
            else:
                series = cache_series(api, series_id)
                if not series:
                    result["error"] = "Metron did not return this series"
                else:
                    result["name"] = series.get("name")
                    path = (choice.get("path") or "").strip() or build_subscribe_path(
                        series, library_path or "", pattern
                    )
                    result["path"] = subscribe_series(series_id, path, monitored=monitored)
                    mapped_ids.add(series_id)
                    # Bring the Wanted page in line now rather than at its next
                    # refresh (an unmonitored series simply contributes nothing).
                    rebuild_wanted_for_series(series_id)
                    result["ok"] = True
        except Exception as e:
            result["error"] = str(e)
        if not result["ok"]:
            # The dialog shows the reason too, but only until it is closed.
            label = result.get("name") or f"series {series_id}"
            app_logger.warning(f"Series setup: {label} was not set up: {result['error']}")
        results.append(result)
        if progress_cb:
            progress_cb(i + 1, len(choices), result.get("name") or str(series_id))

    done = sum(1 for r in results if r["ok"])
    app_logger.info(
        f"Series setup: {done} of {len(results)} series set up"
        f" ({'monitored' if monitored else 'not monitored'})"
    )
    return results
