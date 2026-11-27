"""Series, a series' issue list, and the issue page.

Everything here reads ``core.library_series``: one cached model of the
library's series (built from ``file_index``) with the user's read state laid
over it. Reader-visible and scoped to the user's folders like the Library;
the maintenance parts (untagged counts, gaps, paths, tagging, ComicInfo) are
shown to Clerks and the Store Owner only.

- ``/series``              every series, with filters (query string)
- ``/series/issues``       one series' issues (``name`` + ``publisher``)
- ``/comic/<file_id>``     one issue
- ``/comic/by-path``       redirects a library path to its issue page
- ``/api/series/facet-values``   one filter group's options (its search box)
- ``/api/mark-comic-read/bulk``  mark many issues read or unread

``/smart-collections`` redirects to ``/series``: this page replaced it.
"""

import os
from urllib.parse import urlencode

from flask import (Blueprint, abort, jsonify, redirect, render_template,
                   request, url_for)

from core import library_series as ls
from core.app_logging import app_logger
from core.auth import (accessible_folder_prefixes, current_user,
                       enforce_path_access, role_at_least)
from core.database import current_user_id, db_conn

series_index_bp = Blueprint("series_index", __name__)

# ComicInfo fields in the CBZ Info modal's groups and order
# (static/js/clu-cbz-info.js ``_fieldGroups``), so the issue page and the modal
# list the same fields and count the same empty ones.
COMICINFO_GROUPS = [
    ("Issue", [("Series", "Series"), ("Number", "Number"), ("Title", "Title"),
               ("Volume", "Volume"), ("Count", "Count"),
               ("AlternateSeries", "Alternate series"), ("AlternateNumber", "Alternate number"),
               ("AlternateCount", "Alternate count"), ("Year", "Cover date")]),
    ("Publication", [("Publisher", "Publisher"), ("Imprint", "Imprint"), ("Format", "Format"),
                     ("PageCount", "Pages"), ("LanguageISO", "Language"),
                     ("AgeRating", "Age rating"), ("MetronId", "Metron ID")]),
    ("Credits", [("Writer", "Writer"), ("Penciller", "Penciller"), ("Inker", "Inker"),
                 ("Colorist", "Colorist"), ("Letterer", "Letterer"),
                 ("CoverArtist", "Cover artists"), ("Editor", "Editors"),
                 ("Translator", "Translator")]),
    ("Story", [("Characters", "Characters"), ("Teams", "Teams"), ("Locations", "Locations"),
               ("MainCharacterOrTeam", "Main character"), ("StoryArc", "Story arc"),
               ("Genre", "Genre"), ("SeriesGroup", "Series group")]),
    ("About", [("Summary", "Summary"), ("Notes", "Notes"), ("Web", "Web"),
               ("ScanInformation", "Scan information"), ("Review", "Review"),
               ("CommunityRating", "Rating"), ("BlackAndWhite", "Black & white"),
               ("Manga", "Manga")]),
]
CREDIT_FIELDS = [("Writer", "Writer"), ("Penciller", "Penciller"), ("Inker", "Inker"),
                 ("Colorist", "Colorist"), ("Letterer", "Letterer"),
                 ("CoverArtist", "Cover artists"), ("Editor", "Editors")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _is_maintainer():
    # As the nav does (header.html): no user means implicit-owner mode.
    user = current_user()
    return True if not user else role_at_least(user, "clerk")


def _int_arg(name, default, allowed=None):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    if allowed is not None:
        return value if value in allowed else default
    return max(1, value)


def _context():
    owner = _is_maintainer()
    prefixes = accessible_folder_prefixes(current_user())
    return owner, ls.get_model(prefixes), ls.user_state(current_user_id())


def _url(endpoint, args):
    """``url_for(endpoint)`` with a list of (key, value) query pairs."""
    pairs = [(k, v) for k, v in args if v not in (None, "")]
    base = url_for(endpoint)
    return base + ("?" + urlencode(pairs) if pairs else "")


class _Links:
    """Builds filter links from the current query string."""

    MULTI = {"creators": "creator", "characters": "character", "publishers": "publisher"}

    def __init__(self, args):
        self.pairs = [(k, v) for k in args for v in args.getlist(k)
                      if k not in ("page",)]

    def _without(self, key, value=None):
        return [(k, v) for k, v in self.pairs if not (k == key and (value is None or v == value))]

    def toggle(self, group, value):
        key = self.MULTI[group]
        if (key, value) in self.pairs:
            return _url("series_index.series_index", self._without(key, value))
        return _url("series_index.series_index", self.pairs + [(key, value)])

    def set(self, key, value):
        return _url("series_index.series_index", self._without(key) + [(key, value)])

    def drop(self, key, value=None):
        return _url("series_index.series_index", self._without(key, value))

    def page(self, n):
        return _url("series_index.series_index", self.pairs + [("page", n)])

    def clear(self):
        keep = [(k, v) for k, v in self.pairs if k in ("sort", "per_page", "creators_mode",
                                                        "characters_mode")]
        return _url("series_index.series_index", keep)


def _chips(f, links):
    chips = []
    for group, label in (("creators", "Creators"), ("characters", "Characters"),
                         ("publishers", "Publishers")):
        values = f[group]
        if not values:
            continue
        mode = f.get(group + "_mode")
        kind = label if len(values) == 1 or not mode else f"{label} ({mode})"
        for v in values:
            chips.append({"kind": kind, "value": v, "href": links.toggle(group, v)})
    names = {"decade": "Years", "read": "Read", "pull": "Pull List", "health": "Needs attention",
             "letter": "Letter", "q": "Search"}
    values = {"read": {"unread": "Unread", "progress": "In progress", "finished": "Finished"},
              "pull": {"tracked": "Tracked", "untracked": "Not tracked"},
              "health": {"any": "Anything to fix", "untagged": "Untagged issues",
                         "gaps": "Gaps in the run"},
              "decade": {"earlier": "Before 1990"}}
    for key in ("decade", "read", "pull", "health", "letter"):
        if f[key]:
            chips.append({"kind": names[key], "value": values.get(key, {}).get(f[key], f[key]),
                          "href": links.drop(key)})
    return chips


# ---------------------------------------------------------------------------
# /series
# ---------------------------------------------------------------------------

@series_index_bp.route("/series")
def series_index():
    owner, model, state = _context()
    f = ls.parse_filters(request.args, owner)
    per_page = _int_arg("per_page", ls.DEFAULT_PER_PAGE, ls.PAGE_SIZES)
    data = ls.query_series(model, f, state, owner, _int_arg("page", 1), per_page)
    links = _Links(request.args)
    for item in data["items"]:
        item["thumbnail_url"] = url_for("get_thumbnail", path=item["cover_path"])
        item["href"] = _url("series_index.series_issues",
                            [("name", item["name"]), ("publisher", item["publisher"])])
    for group in data["multi"]:
        for opt in group["items"]:
            opt["label"] = opt["value"]
            opt["href"] = links.toggle(group["group"], opt["value"])
    for group in data["singles"] + ([data["health"]] if data["health"] else []):
        for opt in group["items"]:
            opt["href"] = links.set(group["key"], opt["value"]) if opt["value"] else links.drop(group["key"])
    chips = _chips(f, links)
    return render_template(
        "series_index.html", data=data, f=f, owner=owner, chips=chips, links=links,
        sorts=ls.SORTS, page_sizes=ls.PAGE_SIZES,
        filter_count=len(chips) - (1 if f["letter"] else 0),
        mode_links={g: {m: links.set(g + "_mode", m) for m in ("any", "all")}
                    for g in ("creators", "characters")},
    )


@series_index_bp.route("/api/series/facet-values")
def api_facet_values():
    """One multi-select group's options under the current filters, for its search box."""
    owner, model, state = _context()
    f = ls.parse_filters(request.args, owner)
    group = request.args.get("group")
    if group not in ("creators", "characters", "publishers"):
        return jsonify({"success": False, "error": "Unknown group"}), 400
    query = request.args.get("fq") or ""
    limit = None if request.args.get("all") else 50
    values = ls.facet_values(model, f, state, group, query=query, limit=limit)
    links = _Links(request.args)
    for opt in values["items"]:
        opt["label"] = opt["value"]
        opt["href"] = links.toggle(group, opt["value"])
    return jsonify(dict(values, success=True))


@series_index_bp.route("/smart-collections")
def smart_collections_redirect():
    # Smart collections were replaced by the Series page; old bookmarks land here.
    return redirect(url_for("series_index.series_index"))


# ---------------------------------------------------------------------------
# /series/issues
# ---------------------------------------------------------------------------

@series_index_bp.route("/series/issues")
def series_issues():
    owner, model, state = _context()
    name = request.args.get("name", "")
    publisher = request.args.get("publisher", "")
    record = model["by_key"].get(ls.series_key(name, publisher))
    if not record:
        abort(404)
    per_page = _int_arg("per_page", ls.DEFAULT_PER_PAGE, ls.PAGE_SIZES)
    show = request.args.get("show", "all")
    q = (request.args.get("q") or "").strip()
    data = ls.series_issues(record, state, owner, show=show, q=q,
                            page=_int_arg("page", 1), per_page=per_page,
                            volume=request.args.get("volume", ""))
    base = [("name", name), ("publisher", publisher)]
    if data["volume"]:
        base.append(("volume", data["volume"]))

    def link(**changes):
        args = dict(show=data["show"] if data["show"] != "all" else "", q=q,
                    per_page=per_page if per_page != ls.DEFAULT_PER_PAGE else "",
                    view=request.args.get("view", ""))
        args.update(changes)
        return _url("series_index.series_issues", base + sorted(args.items()))

    for v in data["volumes"] or []:
        v["thumbnail_url"] = url_for("get_thumbnail", path=v["cover_path"])
        v["href"] = _url("series_index.series_issues", [*base, ("volume", v["name"])])
    for row in data["rows"]:
        if row.get("gap"):
            continue
        row["thumbnail_url"] = url_for("get_thumbnail", path=row["path"])
        row["href"] = url_for("series_index.comic_page", file_id=row["id"])
    top_credits = _top_credits(record)
    return render_template(
        "series_issues.html", record=record, data=data, owner=owner, q=q,
        all_volumes_href=_url("series_index.series_issues", [("name", name), ("publisher", publisher)]),
        view="table" if request.args.get("view") == "table" else "grid",
        link=link, page_sizes=ls.PAGE_SIZES,
        series_page=url_for("series.series_view", slug=record["slug"]) if record["slug"] else None,
        years=ls._years_label(record), credits=top_credits,
        continue_href=url_for("series_index.comic_page", file_id=data["continue"]["id"])
        if data["continue"] else None,
        missing_label=_missing_label(record) if owner else "",
    )


def _top_credits(record):
    """The most frequent writer and penciller in a series, for its header."""
    paths = [f["path"] for f in record["files"]]
    out = []
    if not paths:
        return out
    with db_conn() as conn:
        if not conn:
            return out
        for kind, label in (("writer", "Writer"), ("penciller", "Artist")):
            counts = {}
            for i in range(0, len(paths), 500):
                chunk = paths[i:i + 500]
                for value, n in conn.execute(
                        "SELECT value, COUNT(*) FROM file_metadata_tags WHERE kind = ?"
                        " AND file_path IN (" + ",".join("?" * len(chunk)) + ") GROUP BY value",
                        [kind] + chunk):
                    counts[value] = counts.get(value, 0) + n
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:2]
            if top:
                out.append({"label": label, "names": [v for v, _ in top]})
    return out


def _missing_label(record):
    if not record["gap_runs"]:
        return ""
    parts = [f"#{a}" if a == b else f"#{a}–#{b}" for a, b in record["gap_runs"][:3]]
    more = len(record["gap_runs"]) - 3
    return ", ".join(parts) + (f" and {more} more" if more > 0 else "")


# ---------------------------------------------------------------------------
# /comic/<id>
# ---------------------------------------------------------------------------

def _file_row(file_id):
    with db_conn() as conn:
        if not conn:
            return None
        row = conn.execute("SELECT * FROM file_index WHERE id = ? AND type = 'file'",
                           (file_id,)).fetchone()
        return dict(row) if row else None


@series_index_bp.route("/comic/by-path")
def comic_by_path():
    path = request.args.get("path", "")
    with db_conn() as conn:
        row = conn and conn.execute(
            "SELECT id FROM file_index WHERE path = ? AND type = 'file'", (path,)).fetchone()
    if not row:
        abort(404)
    return redirect(url_for("series_index.comic_page", file_id=row[0]))


def _split(value):
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def _cover_date(ci):
    year, month = (ci.get("Year") or "").strip(), (ci.get("Month") or "").strip()
    try:
        m = int(month)
        return f"{MONTHS[m - 1]} {year}".strip() if 1 <= m <= 12 else year
    except ValueError:
        return year


@series_index_bp.route("/comic/<int:file_id>")
def comic_page(file_id):
    row = _file_row(file_id)
    if not row:
        abort(404)
    denied = enforce_path_access(row["path"], mode="full")
    if denied:
        return denied
    owner, model, state = _context()
    key = model["by_path"].get(row["path"])
    record = model["by_key"].get(key) if key else None

    ci = {}
    if row["path"].lower().endswith((".cbz", ".zip")) and os.path.isfile(row["path"]):
        try:
            from core.comicinfo import read_comicinfo_from_zip
            ci = read_comicinfo_from_zip(row["path"]) or {}
        except Exception as e:
            app_logger.warning(f"comic_page: could not read ComicInfo from {row['path']}: {e}")
    tagged = bool(ci) and bool((ci.get("Series") or "").strip())

    groups, empty, set_count = [], 0, 0
    for title, fields in COMICINFO_GROUPS:
        rows = []
        for key_, label in fields:
            value = _cover_date(ci) if key_ == "Year" else (ci.get(key_) or "")
            value = str(value).strip()
            if value:
                set_count += 1
            else:
                empty += 1
            rows.append({"label": label, "value": value})
        groups.append({"title": title, "rows": rows})

    credits = [{"label": label, "names": _split(ci.get(k))} for k, label in CREDIT_FIELDS if _split(ci.get(k))]
    cast = [("character", v) for v in _split(ci.get("Characters"))] + \
           [("team", v) for v in _split(ci.get("Teams"))]

    prev_f, next_f, strip = ls.neighbours(record, row["path"]) if record else (None, None, [])
    status = ls.issue_status(row["path"], state)
    page_no, page_total = state["progress"].get(row["path"], (0, 0))
    number = (ci.get("Number") or "").strip() or (
        next((f["number"] for f in (record["files"] if record else []) if f["path"] == row["path"]), ""))
    series_name = (ci.get("Series") or "").strip() or (record["name"] if record else "")

    def issue_link(f):
        return url_for("series_index.comic_page", file_id=f["id"]) if f else None

    strip_items = [{
        "href": issue_link(f), "number": f["number"], "title": f["title"],
        "thumbnail_url": url_for("get_thumbnail", path=f["path"]),
        "read": f["path"] in state["read"], "current": f["path"] == row["path"],
        "untagged": f["untagged"] and owner,
    } for f in strip]

    return render_template(
        "comic_issue.html", row=row, ci=ci, tagged=tagged, owner=owner,
        record=record, series_name=series_name, number=number,
        title=(ci.get("Title") or "").strip(),
        cover_date=_cover_date(ci), groups=groups, empty_count=empty, set_count=set_count,
        credits=credits, cast=cast, summary=(ci.get("Summary") or "").strip(),
        meta=[v for v in (ci.get("Publisher"), _cover_date(ci),
                          f"{ci.get('PageCount')} pages" if ci.get("PageCount") else "",
                          ci.get("Genre"), ci.get("AgeRating")) if v],
        status=status, page_no=page_no, page_total=page_total,
        want=row["path"] in state["to_read"],
        prev_href=issue_link(prev_f), next_href=issue_link(next_f),
        prev_number=prev_f["number"] if prev_f else "", next_number=next_f["number"] if next_f else "",
        strip=strip_items,
        series_href=_url("series_index.series_issues",
                         [("name", record["name"]), ("publisher", record["publisher"])]) if record else None,
        publisher_href=_url("series_index.series_index", [("publisher", record["publisher"])])
        if record and record["publisher"] else None,
        thumbnail_url=url_for("get_thumbnail", path=row["path"]),
        size_mb=round((row.get("size") or 0) / 1048576, 1),
    )


# ---------------------------------------------------------------------------
# Bulk read state (a Reader may change their own)
# ---------------------------------------------------------------------------

@series_index_bp.route("/api/mark-comic-read/bulk", methods=["POST"])
def api_mark_read_bulk():
    """Mark many issues read (``read: true``) or unread. Returns the paths that changed.

    Only paths in the file index and inside the user's folders are touched;
    issues already in the requested state are left alone and not reported,
    so Undo reverses exactly what this call changed.
    """
    from core.auth import filter_paths_for_user
    from core.database import mark_issue_read, unmark_issue_read
    data = request.get_json(silent=True) or {}
    paths = data.get("paths")
    read = bool(data.get("read", True))
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        return jsonify({"success": False, "error": "paths must be a non-empty list"}), 400
    if len(paths) > 5000:
        return jsonify({"success": False, "error": "Too many issues at once"}), 400
    allowed = set(filter_paths_for_user(current_user(), paths))
    state = ls.user_state(current_user_id())
    with db_conn() as conn:
        known = set()
        if conn:
            for i in range(0, len(paths), 500):
                chunk = paths[i:i + 500]
                known |= {r[0] for r in conn.execute(
                    "SELECT path FROM file_index WHERE type = 'file' AND path IN ("
                    + ",".join("?" * len(chunk)) + ")", chunk)}
    changed = []
    for p in dict.fromkeys(paths):
        if p not in allowed or p not in known:
            continue
        if read and p not in state["read"]:
            if mark_issue_read(p):
                changed.append(p)
        elif not read and p in state["read"]:
            if unmark_issue_read(p):
                changed.append(p)
    try:
        from core.database import clear_stats_cache_prefix
        clear_stats_cache_prefix(f"u{current_user_id()}:")
    except Exception as e:
        app_logger.debug(f"bulk read: stats cache not cleared: {e}")
    return jsonify({"success": True, "changed": changed,
                    "unchanged": len(paths) - len(changed)})
