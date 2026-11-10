"""Creator and character pages, and "follow a creator".

Everything here is a read over ``file_metadata_tags`` (the ComicInfo credit and
Characters tags, already exploded and indexed) joined to ``file_index``. No
provider is ever called.

Things that look arbitrary and are not:

* **A "series" on these pages is a folder** (``file_index.parent``). ComicInfo's
  ``Series`` text is not unique (two volumes share a name) and the library
  already keeps one run per folder.
* **Read progress is the requesting user's** (``issues_read.user_id``); the
  folder scope (``allowed_prefixes``) is the same per-user scope the metadata
  browser applies, so a creator page never names a series the user cannot open.
* **Following only ever turns Monitor on, for a series that is already on the
  Pull List.** Putting an unmapped library series on the Pull List needs a
  provider lookup, which this feature must not add. A series is left alone when
  the user ever decided its Monitor (``monitor_locked``) or when it was mapped
  before the creator was followed.
"""

from core.app_logging import app_logger
from core.database import (
    _COMIC_FILE_CLAUSE_FI,
    _metadata_prefix_clause,
    _resolve_user_id,
    db_conn,
    set_series_monitored_bulk,
)

CREDIT_KINDS = ("writer", "penciller", "inker", "colorist", "letterer", "coverartist")
ROLE_LABELS = {
    "writer": "Writer",
    "penciller": "Penciller",
    "inker": "Inker",
    "colorist": "Colorist",
    "letterer": "Letterer",
    "coverartist": "Cover artist",
}
FOLLOW_SCOPES = ("both", "ongoing", "limited")
CHARACTER_VIEWS = ("series", "year", "unread")


def _in(kinds):
    return ",".join("?" for _ in kinds)


def _scope(prefixes):
    """AND-clause + params for the user's folder scope ('' when unrestricted)."""
    clause, params = _metadata_prefix_clause(prefixes)
    return ((" AND " + clause) if clause else ""), params


def _person_from(kinds):
    """FROM/WHERE shared by every per-person query (params: kinds..., name)."""
    return (
        " FROM file_metadata_tags t JOIN file_index fi ON fi.path = t.file_path"
        f" WHERE t.kind IN ({_in(kinds)}) AND t.value = ? COLLATE NOCASE"
        " AND " + _COMIC_FILE_CLAUSE_FI
    )


def person_page(kinds, name, prefixes=None, user_id=None, view="series",
                role_kinds=None):
    """Everything one creator/character page shows, or None when unknown.

    ``kinds`` is the tag kinds the name is looked up under (a creator under any
    credit kind, a character under ``characters``). ``role_kinds`` widens only
    the role pills, so filtering by one role keeps the others visible.
    """
    kinds = tuple(kinds)
    uid = _resolve_user_id(user_id)
    scope_sql, scope_params = _scope(prefixes)
    base = _person_from(kinds) + scope_sql
    args = [*kinds, name, *scope_params]

    with db_conn() as conn:
        if not conn:
            return None
        c = conn.cursor()
        c.execute("SELECT t.value" + base + " LIMIT 1", args)
        row = c.fetchone()
        if not row:
            return None

        rk = tuple(role_kinds or kinds)
        c.execute(
            "SELECT t.kind, COUNT(DISTINCT t.file_path) n" + _person_from(rk) + scope_sql +
            " GROUP BY t.kind ORDER BY n DESC", [*rk, name, *scope_params])
        roles = [{"kind": r["kind"], "label": ROLE_LABELS.get(r["kind"], r["kind"]),
                  "count": r["n"]} for r in c.fetchall()]

        c.execute(
            "SELECT fi.parent AS parent, MAX(fi.ci_series) AS name,"
            " MAX(fi.ci_publisher) AS publisher, MIN(NULLIF(fi.ci_year, 0)) AS year,"
            " COUNT(DISTINCT fi.path) AS issues, COUNT(DISTINCT r.issue_path) AS read,"
            " MIN(fi.path) AS cover"
            + base.replace(
                "WHERE",
                "LEFT JOIN issues_read r ON r.issue_path = fi.path AND r.user_id = ?"
                " WHERE", 1)
            + " GROUP BY fi.parent",
            [uid, *args])
        series = [dict(r) for r in c.fetchall()]

        # Co-credits: other credits for a creator, other characters for a character.
        co_kinds = ("characters",) if kinds == ("characters",) else CREDIT_KINDS
        c.execute(
            "SELECT t2.value AS name, COUNT(DISTINCT t.file_path) AS n"
            + base.replace(
                "WHERE",
                "JOIN file_metadata_tags t2 ON t2.file_path = t.file_path"
                f" AND t2.kind IN ({_in(co_kinds)})"
                " AND t2.value != ? COLLATE NOCASE WHERE", 1)
            + " GROUP BY t2.value COLLATE NOCASE ORDER BY n DESC, t2.value LIMIT 12",
            [*co_kinds, name, *args])
        often_with = [dict(r) for r in c.fetchall()]

        c.execute(
            "SELECT MAX(r.read_at) AS last_read"
            + base.replace(
                "WHERE",
                "JOIN issues_read r ON r.issue_path = fi.path AND r.user_id = ?"
                " WHERE", 1),
            [uid, *args])
        last_read = c.fetchone()["last_read"]

    for s in series:
        s["name"] = s["name"] or (s["parent"] or "").rstrip("/").rsplit("/", 1)[-1]
    issues = sum(s["issues"] for s in series)
    read = sum(s["read"] for s in series)
    if view == "unread":
        series = [s for s in series if s["read"] < s["issues"]]
    series.sort(key=(lambda s: (s["year"] or 9999, s["name"].casefold()))
                if view == "year" else (lambda s: s["name"].casefold()))

    years = [s["year"] for s in series if s["year"]]
    return {
        "name": row["value"],
        "roles": roles,
        "series": series,
        "often_with": often_with,
        "issues": issues,
        "read": read,
        "first_year": min(years) if years else None,
        "last_read": last_read,
    }


def person_issues(kinds, name, folder, prefixes=None, user_id=None):
    """The issues in one series folder that carry this person's tag.

    The series cards on a creator/character page expand to this list, so the
    reader can see *which* issues the person is on rather than being sent to
    the whole folder. Same name lookup and per-user folder scope as
    ``person_page``; ``folder`` must match ``file_index.parent`` exactly, so a
    caller cannot read outside what the page itself listed.
    """
    kinds = tuple(kinds)
    uid = _resolve_user_id(user_id)
    scope_sql, scope_params = _scope(prefixes)
    base = _person_from(kinds).replace(
        "WHERE",
        "LEFT JOIN issues_read r ON r.issue_path = fi.path AND r.user_id = ? WHERE", 1)
    with db_conn() as conn:
        if not conn:
            return None
        rows = conn.execute(
            "SELECT DISTINCT fi.path AS path, fi.name AS name, fi.ci_series AS series,"
            " fi.ci_number AS number, fi.ci_title AS title, fi.ci_year AS year,"
            " (r.issue_path IS NOT NULL) AS read"
            + base + " AND fi.parent = ?" + scope_sql,
            [uid, *kinds, name, folder, *scope_params]).fetchall()
    issues = [dict(r) for r in rows]
    issues.sort(key=lambda i: (_issue_sort_key(i["number"]), (i["name"] or "").casefold()))
    return issues


def _issue_sort_key(number):
    """Numeric issue order; non-numbers (annuals, specials) sort after the numbered ones."""
    try:
        return (0, float(str(number).strip()))
    except (TypeError, ValueError):
        return (1, 0.0)


def list_people(kinds, q="", prefixes=None, limit=300):
    """Names with issue counts, most credited first; ``q`` filters by substring."""
    kinds = tuple(kinds)
    scope_sql, scope_params = _scope(prefixes)
    where, params = "", []
    if (q or "").strip():
        where = " AND instr(lower(t.value), ?) > 0"
        params.append(q.strip().lower())
    with db_conn() as conn:
        if not conn:
            return []
        rows = conn.execute(
            "SELECT MIN(t.value) AS name, COUNT(DISTINCT t.file_path) AS n"
            " FROM file_metadata_tags t JOIN file_index fi ON fi.path = t.file_path"
            f" WHERE t.kind IN ({_in(kinds)}) AND " + _COMIC_FILE_CLAUSE_FI
            + where + scope_sql
            + " GROUP BY t.value COLLATE NOCASE ORDER BY n DESC, name LIMIT ?",
            [*kinds, *params, *scope_params, int(limit)]).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Follow a creator
# --------------------------------------------------------------------------

def list_follows():
    with db_conn() as conn:
        if not conn:
            return []
        return [dict(r) for r in conn.execute(
            "SELECT name, role, publisher, scope, followed_at, added_count, last_added"
            " FROM followed_creators ORDER BY name COLLATE NOCASE")]


def get_follow(name):
    with db_conn() as conn:
        if not conn:
            return None
        row = conn.execute(
            "SELECT name, role, publisher, scope, followed_at, added_count, last_added"
            " FROM followed_creators WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def follow_creator(name, role="writer", publisher=None, scope="both"):
    """Follow (or update the options of) a creator. Raises ValueError on bad input."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Missing creator name")
    if role not in CREDIT_KINDS:
        raise ValueError("Invalid role")
    if scope not in FOLLOW_SCOPES:
        raise ValueError("Invalid scope")
    publisher = (publisher or "").strip() or None
    with db_conn() as conn:
        if not conn:
            raise RuntimeError("Database unavailable")
        # Upsert keeps followed_at, so changing options never re-opens the
        # "existing series are left alone" window.
        conn.execute(
            "INSERT INTO followed_creators (name, role, publisher, scope)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET role = excluded.role,"
            " publisher = excluded.publisher, scope = excluded.scope",
            (name, role, publisher, scope))
        conn.commit()
    return get_follow(name)


def unfollow_creator(name):
    with db_conn() as conn:
        if not conn:
            return False
        cur = conn.execute("DELETE FROM followed_creators WHERE name = ?", (name,))
        conn.commit()
        return cur.rowcount > 0


def apply_follows():
    """Turn Monitor on for new Pull List series by followed creators.

    Called by the scheduled sweep. Never raises. Returns the number of series
    switched on.
    """
    from core.series_status import FINISHED_STATUSES, status_text

    try:
        added_total = 0
        for f in list_follows():
            with db_conn() as conn:
                if not conn:
                    return added_total
                rows = conn.execute(
                    "SELECT s.id, s.name, s.status, p.name AS publisher"
                    " FROM series s LEFT JOIN publishers p ON p.id = s.publisher_id"
                    " WHERE s.mapped_path IS NOT NULL AND s.mapped_path != ''"
                    " AND s.monitored = 0 AND COALESCE(s.monitor_locked, 0) = 0"
                    " AND s.created_at >= ?"
                    " AND s.mapped_path IN (SELECT fi.parent FROM file_metadata_tags t"
                    "   JOIN file_index fi ON fi.path = t.file_path"
                    "   WHERE t.kind = ? AND t.value = ? COLLATE NOCASE)",
                    (f["followed_at"], f["role"], f["name"])).fetchall()
            picked = []
            for r in rows:
                if f["publisher"] and (r["publisher"] or "").casefold() != f["publisher"].casefold():
                    continue
                finished = status_text(dict(r)) in FINISHED_STATUSES
                if (f["scope"] == "ongoing" and finished) or (
                        f["scope"] == "limited" and not finished):
                    continue
                picked.append(r)
            if not picked:
                continue
            set_series_monitored_bulk([r["id"] for r in picked], True)
            with db_conn() as conn:
                if conn:
                    conn.execute(
                        "UPDATE followed_creators SET added_count = added_count + ?,"
                        " last_added = ? WHERE name = ?",
                        (len(picked), picked[-1]["name"], f["name"]))
                    conn.commit()
            added_total += len(picked)
        if added_total:
            app_logger.info(f"Followed creators: added {added_total} series to Wanted")
        return added_total
    except Exception as e:
        app_logger.error(f"Followed creators sweep failed: {e}")
        return 0
