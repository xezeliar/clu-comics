"""Library series: every series in the library, built from ``file_index``.

The Series page, a series' issue list and the issue page all read one model,
built from the indexed ComicInfo and cached with the Library browser's cache
(``_mb_cache``: 45s TTL, cleared whenever ``file_index`` changes). The model is
the same for every user with the same folder scope; read state is per user and
is laid over it on each request (``user_state``).

A series is every comic sharing a ``ci_series`` and ``ci_publisher``, as on the
Library's Series tab. An *untagged* comic (``has_comicinfo`` is 0, or no series
in its ComicInfo) joins the series that most of its folder's tagged comics
belong to; comics that match no series that way are counted as orphans.

Gaps are whole issue numbers missing between the lowest and highest whole
number owned. They count towards "to fix" only for a series tracked on the
Pull List: an untracked run is often incomplete on purpose.
"""

import os
import re
from collections import Counter, defaultdict

from core.app_logging import app_logger

CREATOR_KINDS = ("writer", "penciller", "inker", "colorist", "letterer",
                 "coverartist", "editor")
PAGE_SIZES = (24, 60, 120, 240)
DEFAULT_PER_PAGE = 60
FACET_LIMIT = 5
FACET_MAX = 300
GAP_RUN_LIMIT = 5000  # a run with a bigger hole than this is not a run

_NUM_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(.*)$")
_FRACTIONS = {"½": 0.5, "1/2": 0.5, "¼": 0.25, "¾": 0.75}


# ---------------------------------------------------------------------------
# Issue numbers
# ---------------------------------------------------------------------------

def number_sort_key(number):
    """Natural order: 0, ½, 1, 1.MU, 2 ... then anything without a number.

    Returns a tuple so mixed values compare. Text after the number (".MU",
    "AU") sorts after the plain number.
    """
    text = (number or "").strip()
    if text in _FRACTIONS:
        return (0, _FRACTIONS[text], "")
    m = _NUM_RE.match(text)
    if m:
        return (0, float(m.group(1)), m.group(2).lower())
    return (1, 0.0, text.lower())


def whole_number(number):
    """The issue number as an int when it is a plain whole number, else None."""
    text = (number or "").strip()
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return None


def gap_runs(numbers):
    """Runs of whole numbers missing between the lowest and highest owned.

    ``numbers`` is an iterable of ints (duplicates fine). Returns a list of
    (first, last) tuples in order.
    """
    owned = sorted({n for n in numbers if n is not None and n >= 0})
    runs = []
    for a, b in zip(owned, owned[1:]):
        if b - a > 1 and b - a <= GAP_RUN_LIMIT:
            runs.append((a + 1, b - 1))
    return runs


def _sort_name(name):
    text = (name or "").strip()
    low = text.lower()
    for article in ("the ", "a ", "an "):
        if low.startswith(article) and len(text) > len(article):
            return text[len(article):]
    return text


def _letter(name):
    c = _sort_name(name)[:1].upper()
    return c if "A" <= c <= "Z" else "#"


def _year(value):
    try:
        y = int(str(value).strip()[:4])
        return y if 1800 < y < 2200 else None
    except (TypeError, ValueError):
        return None


def series_key(name, publisher):
    return (name or "") + "\x1f" + (publisher or "")


# ---------------------------------------------------------------------------
# The model (cached, per folder scope)
# ---------------------------------------------------------------------------

def get_model(allowed_prefixes=None):
    """Every series in scope. Cached until ``file_index`` changes."""
    from core.database import _mb_cache_get, _mb_cache_key, _mb_cache_put
    key = _mb_cache_key("library_series", allowed_prefixes)
    cached = _mb_cache_get(key)
    if cached is not None:
        return cached
    model = _build_model(allowed_prefixes)
    _mb_cache_put(key, model)
    return model


def _build_model(allowed_prefixes):
    from core.database import (_build_metadata_where, db_conn,
                                get_series_slugs_for_folders)
    model = {"series": [], "by_key": {}, "by_path": {}, "orphans": 0}
    where_sql, params = _build_metadata_where({}, allowed_prefixes)
    with db_conn() as conn:
        if not conn:
            return model
        rows = conn.execute(
            "SELECT id, path, name, parent, ci_series, ci_publisher, ci_number,"
            " ci_year, ci_title, has_comicinfo, first_indexed_at, size"
            " FROM file_index " + where_sql, params).fetchall()
        kinds = CREATOR_KINDS + ("characters",)
        tag_rows = conn.execute(
            "SELECT t.file_path, t.kind, t.value FROM file_index"
            " JOIN file_metadata_tags t ON t.file_path = file_index.path "
            + where_sql + " AND t.kind IN (" + ",".join("?" * len(kinds)) + ")",
            params + list(kinds)).fetchall()

    tags = defaultdict(lambda: {"creators": set(), "characters": set()})
    for path, kind, value in tag_rows:
        tags[path]["characters" if kind == "characters" else "creators"].add(value)

    groups = defaultdict(list)
    untagged_rows = []
    folder_votes = defaultdict(Counter)
    for r in rows:
        name = (r["ci_series"] or "").strip()
        if name:
            key = series_key(name, (r["ci_publisher"] or "").strip())
            groups[key].append(r)
            folder_votes[r["parent"]][key] += 1
        else:
            untagged_rows.append(r)
    for r in untagged_rows:
        votes = folder_votes.get(r["parent"])
        if votes:
            groups[votes.most_common(1)[0][0]].append(r)
        else:
            model["orphans"] += 1

    all_folders = {r["parent"] for rs in groups.values() for r in rs if r["parent"]}
    slugs = get_series_slugs_for_folders(list(all_folders)) if all_folders else {}

    for key, rs in groups.items():
        name, publisher = key.split("\x1f", 1)
        files = []
        creators, characters = set(), set()
        years = []
        numbers = []
        for r in rs:
            untagged = not (r["ci_series"] or "").strip() or r["has_comicinfo"] == 0
            number = (r["ci_number"] or "").strip()
            if not number and untagged:
                m = re.search(r"(?<!\d)(\d{1,4})(?!\d)", os.path.splitext(r["name"])[0]
                              .replace(name, "", 1) if name else r["name"])
                number = m.group(1).lstrip("0") or "0" if m else ""
            files.append({
                "id": r["id"], "path": r["path"], "name": r["name"],
                "number": number, "title": (r["ci_title"] or "").strip(),
                "year": _year(r["ci_year"]), "untagged": untagged,
                "indexed": r["first_indexed_at"] or 0, "size": r["size"] or 0,
            })
            t = tags.get(r["path"])
            if t:
                creators |= t["creators"]
                characters |= t["characters"]
            y = _year(r["ci_year"])
            if y:
                years.append(y)
            numbers.append(whole_number(number))
        files.sort(key=lambda f: (number_sort_key(f["number"]), f["name"].lower()))
        folders = sorted({r["parent"] for r in rs if r["parent"]})
        slug = next((slugs[f] for f in folders if f in slugs), None)
        tagged_files = [f for f in files if not f["untagged"]]
        cover = (tagged_files or files)[0]
        runs = gap_runs(numbers)
        record = {
            "key": key, "name": name, "publisher": publisher,
            "sort_name": _sort_name(name).lower(), "letter": _letter(name),
            "files": files, "count": len(files),
            "creators": creators, "characters": characters,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "folders": folders, "slug": slug, "tracked": bool(slug),
            "untagged": sum(1 for f in files if f["untagged"]),
            "gap_runs": runs, "gaps": sum(b - a + 1 for a, b in runs),
            "cover_path": cover["path"],
            "last_added": max((f["indexed"] for f in files), default=0),
        }
        model["series"].append(record)
        model["by_key"][key] = record
        for f in files:
            model["by_path"][f["path"]] = key
    return model


def decades(record):
    lo, hi = record["year_min"], record["year_max"]
    if lo is None:
        return []
    return [str(d) + "s" for d in range(lo // 10 * 10, hi + 1, 10)]


def to_fix(record):
    """Problems a maintainer can act on: untagged issues, plus gaps when tracked."""
    return record["untagged"] + (record["gaps"] if record["tracked"] else 0)


# ---------------------------------------------------------------------------
# Per-user state
# ---------------------------------------------------------------------------

def user_state(user_id):
    """Read paths, in-progress pages and Want to Read paths for one user."""
    from core.database import db_conn
    state = {"read": set(), "progress": {}, "to_read": set()}
    with db_conn() as conn:
        if not conn:
            return state
        try:
            state["read"] = {r[0] for r in conn.execute(
                "SELECT issue_path FROM issues_read WHERE user_id = ?", (user_id,))}
        except Exception as e:  # an old schema without user_id
            app_logger.debug(f"user_state: issues_read: {e}")
        try:
            for path, page, total in conn.execute(
                    "SELECT comic_path, page_number, total_pages FROM reading_positions"
                    " WHERE user_id = ?", (user_id,)):
                state["progress"][path] = (page or 0, total or 0)
        except Exception as e:
            app_logger.debug(f"user_state: reading_positions: {e}")
        try:
            state["to_read"] = {r[0] for r in conn.execute(
                "SELECT path FROM to_read WHERE user_id = ?", (user_id,))}
        except Exception as e:
            app_logger.debug(f"user_state: to_read: {e}")
    return state


def issue_status(path, state):
    if path in state["read"]:
        return "read"
    if path in state["progress"]:
        return "progress"
    return "unread"


def series_status(record, state):
    n_read = sum(1 for f in record["files"] if f["path"] in state["read"])
    if n_read and n_read >= record["count"]:
        return "Finished", n_read
    if n_read or any(f["path"] in state["progress"] for f in record["files"]):
        return "In progress", n_read
    return "Unread", n_read


# ---------------------------------------------------------------------------
# The Series page query
# ---------------------------------------------------------------------------

SORTS = {"alpha": "A–Z", "count": "Most issues", "newest": "Newest series",
         "recent": "Recently added"}
MULTI_GROUPS = (("creators", "Creators", "creators"),
                ("characters", "Characters", "characters"),
                ("publishers", "Publishers", "publishers"))


def parse_filters(args, owner):
    """Filters from a request's query string (a MultiDict)."""
    def many(name):
        return [v for v in args.getlist(name) if v.strip()][:50]

    f = {
        "q": (args.get("q") or "").strip(),
        "creators": many("creator"), "characters": many("character"),
        "publishers": many("publisher"),
        "creators_mode": "any" if args.get("creators_mode") == "any" else "all",
        "characters_mode": "any" if args.get("characters_mode") == "any" else "all",
        "decade": (args.get("decade") or "").strip(),
        "read": args.get("read") if args.get("read") in ("unread", "progress", "finished") else "",
        "pull": args.get("pull") if args.get("pull") in ("tracked", "untracked") else "",
        "health": (args.get("health") if owner and args.get("health") in ("untagged", "gaps", "any") else ""),
        "letter": "",
        "sort": args.get("sort") if args.get("sort") in SORTS else "alpha",
    }
    letter = (args.get("letter") or "").strip().upper()
    if letter == "#" or (len(letter) == 1 and "A" <= letter <= "Z"):
        f["letter"] = letter
    if not re.fullmatch(r"(19|20)\d0s|earlier", f["decade"]):
        f["decade"] = ""
    return f


def _in_decade(record, decade):
    ds = decades(record)
    if decade == "earlier":
        return any(int(d[:4]) < 1990 for d in ds)
    return decade in ds


_STATUS_KEYS = {"unread": "Unread", "progress": "In progress", "finished": "Finished"}


def _matches(record, f, state, skip=None, override=None, statuses=None):
    if override:
        f = dict(f, **override)
    if f["q"] and f["q"].lower() not in record["name"].lower():
        return False
    if f["letter"] and record["letter"] != f["letter"]:
        return False
    for group, field in (("creators", "creators"), ("characters", "characters")):
        sel = f[group]
        if skip != group and sel:
            have = record[field]
            if f[group + "_mode"] == "any":
                if not any(v in have for v in sel):
                    return False
            elif not all(v in have for v in sel):
                return False
    if skip != "publishers" and f["publishers"] and record["publisher"] not in f["publishers"]:
        return False
    if skip != "decade" and f["decade"] and not _in_decade(record, f["decade"]):
        return False
    if skip != "read" and f["read"]:
        status = statuses[record["key"]] if statuses else series_status(record, state)[0]
        if status != _STATUS_KEYS[f["read"]]:
            return False
    if skip != "pull" and f["pull"] and (f["pull"] == "tracked") != record["tracked"]:
        return False
    if skip != "health" and f["health"]:
        if f["health"] == "untagged" and not record["untagged"]:
            return False
        if f["health"] == "gaps" and not record["gaps"]:
            return False
        if f["health"] == "any" and not to_fix(record):
            return False
    return True


def facet_values(model, f, state, group, query="", limit=FACET_LIMIT, statuses=None):
    """Options for one multi-select group, with counts.

    In an "all" group each count is the number of series you would see after
    ticking that value (it can only narrow). In an "any" group (and Publishers)
    it is the number of series having that value under the other groups'
    filters, so a value with no matches reads 0 and is dimmed.
    """
    field = {"creators": "creators", "characters": "characters", "publishers": None}[group]
    sel = f[group]
    mode = f.get(group + "_mode", "any") if field else "any"
    base = [s for s in model["series"] if _matches(s, f, state, skip=group, statuses=statuses)]
    if mode == "all" and sel:
        pool = [s for s in base if all(v in s[field] for v in sel)]
    else:
        pool = base
    counts = Counter()
    every = set()
    for s in model["series"]:
        every |= ({s["publisher"]} if field is None else s[field])
    for s in pool:
        for v in ({s["publisher"]} if field is None else s[field]):
            counts[v] += 1
    every.discard("")
    q = (query or "").strip().lower()
    names = [v for v in every if not q or q in v.lower()]
    names.sort(key=lambda v: (v not in sel, -counts[v], v.lower()))
    total = len(every)
    shown = names if (q or limit is None) else names[:max(limit, len(sel))]
    return {
        "group": group, "mode": mode, "total": total, "matching": len(names),
        "items": [{"value": v, "count": counts[v], "checked": v in sel} for v in shown[:FACET_MAX]],
    }


def _single(model, f, state, key, options, test, statuses):
    base = [s for s in model["series"] if _matches(s, f, state, skip=key, statuses=statuses)]
    items = []
    for value, label in options:
        n = len(base) if not value else sum(1 for s in base if test(s, value))
        items.append({"value": value, "label": label, "count": n, "checked": f[key] == value})
    return {"key": key, "items": items}


def query_series(model, f, state, owner, page=1, per_page=DEFAULT_PER_PAGE):
    statuses = {s["key"]: series_status(s, state)[0] for s in model["series"]}
    shown = [s for s in model["series"] if _matches(s, f, state, statuses=statuses)]
    sort = f["sort"]
    if sort == "count":
        shown.sort(key=lambda s: (-s["count"], s["sort_name"]))
    elif sort == "newest":
        shown.sort(key=lambda s: (-(s["year_min"] or 0), s["sort_name"]))
    elif sort == "recent":
        shown.sort(key=lambda s: (-s["last_added"], s["sort_name"]))
    else:
        shown.sort(key=lambda s: (s["sort_name"], s["year_min"] or 0, s["publisher"].lower()))

    total = len(shown)
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    items = []
    for s in shown[start:start + per_page]:
        status, n_read = series_status(s, state)
        items.append({
            "name": s["name"], "publisher": s["publisher"], "count": s["count"],
            "years": _years_label(s), "cover_path": s["cover_path"],
            "status": status, "n_read": n_read,
            "to_fix": to_fix(s) if owner else 0,
            "untagged": s["untagged"] if owner else 0,
            "gaps": s["gaps"] if owner and s["tracked"] else 0,
        })

    no_letter = dict(f, letter="")
    letters = sorted({s["letter"] for s in model["series"]
                      if _matches(s, no_letter, state, statuses=statuses)})

    present = set()
    for s in model["series"]:
        present.update(decades(s))
    decade_opts = [("", "Any")] + [(d, d) for d in sorted(
        (d for d in present if int(d[:4]) >= 1990), reverse=True)]
    if any(int(d[:4]) < 1990 for d in present):
        decade_opts.append(("earlier", "Earlier"))

    singles = [
        _single(model, f, state, "decade", decade_opts, _in_decade, statuses),
        _single(model, f, state, "read",
                [("", "Any"), ("unread", "Unread"), ("progress", "In progress"), ("finished", "Finished")],
                lambda s, v: statuses[s["key"]] == _STATUS_KEYS[v], statuses),
        _single(model, f, state, "pull",
                [("", "Any"), ("tracked", "Tracked"), ("untracked", "Not tracked")],
                lambda s, v: (v == "tracked") == s["tracked"], statuses),
    ]
    health = None
    if owner:
        health = _single(model, f, state, "health",
                         [("", "Any"), ("any", "Anything to fix"), ("untagged", "Untagged issues"),
                          ("gaps", "Gaps in the run")],
                         lambda s, v: (to_fix(s) > 0 if v == "any" else
                                       s["untagged"] > 0 if v == "untagged" else s["gaps"] > 0),
                         statuses)
    health_pool = [s for s in shown if s["untagged"]] if owner else []
    return {
        "items": items, "total": total, "all_total": len(model["series"]),
        "page": page, "pages": pages, "per_page": per_page,
        "first": start + 1 if items else 0, "last": start + len(items),
        "letters": letters,
        "multi": [facet_values(model, f, state, g, statuses=statuses) for g, _, _ in MULTI_GROUPS],
        "singles": singles, "health": health,
        "orphans": model["orphans"] if owner else 0,
        "untagged_series": sum(1 for s in model["series"] if s["untagged"]) if owner else 0,
        "untagged_in_view": sum(s["untagged"] for s in health_pool),
        "untagged_series_in_view": len(health_pool),
        "untagged_paths": [x["path"] for s in health_pool for x in s["files"] if x["untagged"]],
    }


def _years_label(record):
    lo, hi = record["year_min"], record["year_max"]
    if lo is None:
        return ""
    return str(lo) if hi == lo else f"{lo}–{hi}"


# ---------------------------------------------------------------------------
# One series' issue list
# ---------------------------------------------------------------------------

SHOWS = ("all", "unread", "read", "untagged", "gaps")


def series_issues(record, state, owner, show="all", q="", page=1, per_page=DEFAULT_PER_PAGE):
    """Rows for the issue list: issues and (owner, tracked or not) gap runs.

    A gap run is one slot, however many numbers it covers, so a sparse run
    never pushes owned covers off the page.
    """
    if show not in SHOWS or (not owner and show in ("untagged", "gaps")):
        show = "all"
    issues = []
    for f in record["files"]:
        st = issue_status(f["path"], state)
        page_no, total = state["progress"].get(f["path"], (0, 0))
        issues.append(dict(f, status=st, page_no=page_no, page_total=total,
                           sort=number_sort_key(f["number"])))
    gaps = [{"gap": True, "first": a, "last": b, "count": b - a + 1,
             "sort": number_sort_key(str(a))} for a, b in record["gap_runs"]] if owner else []

    counts = {
        "all": len(issues),
        "unread": sum(1 for i in issues if i["status"] != "read"),
        "read": sum(1 for i in issues if i["status"] == "read"),
        "untagged": sum(1 for i in issues if i["untagged"]) if owner else 0,
        "gaps": sum(g["count"] for g in gaps),
    }

    pool = issues
    if show == "unread":
        pool = [i for i in issues if i["status"] != "read"]
    elif show == "read":
        pool = [i for i in issues if i["status"] == "read"]
    elif show == "untagged":
        pool = [i for i in issues if i["untagged"]]
    elif show == "gaps":
        pool = []

    jump = None
    text = (q or "").strip()
    num_q = text.lstrip("#").strip() if re.fullmatch(r"#?\s*[\w.½-]+", text) and re.search(r"\d|½", text) else None
    if text and num_q is not None:
        wanted = number_sort_key(num_q)
        pool = [i for i in pool if i["sort"] == wanted]
        jump = {"number": num_q, "found": bool(pool)}
        whole = whole_number(num_q)
        in_gap = [g for g in gaps if whole is not None and g["first"] <= whole <= g["last"]]
        jump["gap"] = bool(in_gap)
        rows = pool + ([dict(in_gap[0], first=whole, last=whole, count=1)] if in_gap and not pool else [])
    elif text:
        low = text.lower()
        pool = [i for i in pool if low in (i["title"] or "").lower() or low in i["name"].lower()]
        rows = pool
    elif show == "gaps":
        rows = gaps
    elif show == "all":
        rows = sorted(pool + gaps, key=lambda r: r["sort"])
    else:
        rows = pool

    total_slots = len(rows)
    pages = max(1, -(-total_slots // per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    cont = next((i for i in issues if i["status"] == "progress"), None) \
        or next((i for i in issues if i["status"] == "unread"), None)
    return {
        "rows": page_rows, "show": show, "counts": counts, "jump": jump,
        "total_slots": total_slots, "page": page, "pages": pages, "per_page": per_page,
        "first": start + 1 if page_rows else 0, "last": start + len(page_rows),
        "issues_on_page": [r for r in page_rows if not r.get("gap")],
        "matching_paths": [i["path"] for i in pool],
        "continue": cont,
        "all_read": bool(issues) and all(i["status"] == "read" for i in issues),
    }


def neighbours(record, path, span=5):
    """(previous, next, strip) around one issue in its series' natural order."""
    files = record["files"]
    idx = next((k for k, f in enumerate(files) if f["path"] == path), None)
    if idx is None:
        return None, None, []
    prev_f = files[idx - 1] if idx > 0 else None
    next_f = files[idx + 1] if idx + 1 < len(files) else None
    lo = max(0, idx - 2)
    strip = files[lo:lo + span * 2]
    return prev_f, next_f, strip
