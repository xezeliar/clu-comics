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

CREDIT_KINDS = ("writer", "penciller", "inker", "colorist", "letterer", "coverartist",
                "editor", "translator")
ROLE_LABELS = {
    "writer": "Writer",
    "penciller": "Penciller",
    "inker": "Inker",
    "colorist": "Colorist",
    "letterer": "Letterer",
    "coverartist": "Cover artist",
    "editor": "Editor",
    "translator": "Translator",
}
FOLLOW_SCOPES = ("both", "ongoing", "limited")
CHARACTER_VIEWS = ("series", "year", "unread")


def _in(kinds):
    return ",".join("?" for _ in kinds)


def _scope(prefixes):
    """AND-clause + params for the user's folder scope ('' when unrestricted)."""
    clause, params = _metadata_prefix_clause(prefixes)
    return ((" AND " + clause) if clause else ""), params


def _names(name):
    """One name, or a team's set of member names, as a list."""
    return [name] if isinstance(name, str) else list(name)


def _name_match(col, names, negate=False):
    """``col = ? COLLATE NOCASE`` for one name, ``IN (...)`` for a set."""
    if len(names) == 1:
        return f"{col} {'!=' if negate else '='} ? COLLATE NOCASE"
    return f"{col} COLLATE NOCASE {'NOT IN' if negate else 'IN'} ({_in(names)})"


def _person_from(kinds, names=("",)):
    """FROM/WHERE shared by every per-person query (params: kinds..., names...)."""
    return (
        " FROM file_metadata_tags t JOIN file_index fi ON fi.path = t.file_path"
        f" WHERE t.kind IN ({_in(kinds)}) AND " + _name_match("t.value", names)
        + " AND " + _COMIC_FILE_CLAUSE_FI
    )


def person_page(kinds, name, prefixes=None, user_id=None, view="series",
                role_kinds=None):
    """Everything one creator/character page shows, or None when unknown.

    ``kinds`` is the tag kinds the name is looked up under (a creator under any
    credit kind, a character under ``characters``). ``role_kinds`` widens only
    the role pills, so filtering by one role keeps the others visible.
    """
    kinds = tuple(kinds)
    names = _names(name)
    uid = _resolve_user_id(user_id)
    scope_sql, scope_params = _scope(prefixes)
    base = _person_from(kinds, names) + scope_sql
    args = [*kinds, *names, *scope_params]

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
            "SELECT t.kind, COUNT(DISTINCT t.file_path) n" + _person_from(rk, names) + scope_sql +
            " GROUP BY t.kind ORDER BY n DESC", [*rk, *names, *scope_params])
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
        co_kinds = CREDIT_KINDS if set(kinds) <= set(CREDIT_KINDS) else ("characters",)
        c.execute(
            "SELECT t2.value AS name, COUNT(DISTINCT t.file_path) AS n"
            + base.replace(
                "WHERE",
                "JOIN file_metadata_tags t2 ON t2.file_path = t.file_path"
                f" AND t2.kind IN ({_in(co_kinds)})"
                " AND " + _name_match("t2.value", names, negate=True) + " WHERE", 1)
            + " GROUP BY t2.value COLLATE NOCASE ORDER BY n DESC, t2.value LIMIT 12",
            [*co_kinds, *names, *args])
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
    names = _names(name)
    uid = _resolve_user_id(user_id)
    scope_sql, scope_params = _scope(prefixes)
    base = _person_from(kinds, names).replace(
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
            [uid, *kinds, *names, folder, *scope_params]).fetchall()
    issues = [dict(r) for r in rows]
    issues.sort(key=lambda i: (_issue_sort_key(i["number"]), (i["name"] or "").casefold()))
    return issues


HEADER_ROLES = ("writer", "penciller", "coverartist")


def series_credits(folder, prefixes=None, top=2):
    """Who is credited in one series folder's owned issues, for the series header.

    ``{"issues": owned files, "credited": files with any credit, "roles": [...],
    "header": [...]}``. ``roles`` lists every stored role in ``CREDIT_KINDS``
    order, each with every person ranked by how many owned issues credit them;
    ``header`` is Writer/Penciller/Cover artist cut to the top ``top``. A
    person's ``show_count`` is False when they are on every credited issue,
    where the number would only repeat the total. None when unreadable.
    """
    folder = (folder or "").rstrip("/\\")
    if not folder:
        return None
    scope_sql, scope_params = _scope(prefixes)
    where = " WHERE fi.parent = ? AND " + _COMIC_FILE_CLAUSE_FI + scope_sql
    try:
        with db_conn() as conn:
            if not conn:
                return None
            issues = conn.execute(
                "SELECT COUNT(*) FROM file_index fi" + where,
                [folder, *scope_params]).fetchone()[0]
            credited = conn.execute(
                "SELECT COUNT(DISTINCT t.file_path) FROM file_metadata_tags t"
                " JOIN file_index fi ON fi.path = t.file_path" + where
                + f" AND t.kind IN ({_in(CREDIT_KINDS)})",
                [folder, *scope_params, *CREDIT_KINDS]).fetchone()[0]
            rows = conn.execute(
                "SELECT t.kind AS kind, MIN(t.value) AS name,"
                " COUNT(DISTINCT t.file_path) AS n"
                " FROM file_metadata_tags t JOIN file_index fi ON fi.path = t.file_path"
                + where + f" AND t.kind IN ({_in(CREDIT_KINDS)})"
                " GROUP BY t.kind, t.value COLLATE NOCASE",
                [folder, *scope_params, *CREDIT_KINDS]).fetchall()
    except Exception as e:
        app_logger.error(f"Failed to read series credits for {folder}: {e}")
        return None

    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(
            {"name": r["name"], "count": r["n"], "show_count": r["n"] < credited})
    roles = []
    for kind in CREDIT_KINDS:
        people = by_kind.get(kind)
        if people:
            people.sort(key=lambda p: (-p["count"], p["name"].casefold()))
            roles.append({"kind": kind, "label": ROLE_LABELS[kind], "people": people})
    header = [dict(r, people=r["people"][:top]) for r in roles if r["kind"] in HEADER_ROLES]
    return {"issues": issues, "credited": credited, "roles": roles, "header": header}


def kind_for_role(role_name):
    """The ``CREDIT_KINDS`` entry a provider's role name belongs to, or None.

    Substring matches, because Metron spells roles out ("Script", "Cover
    Artist", "Colorist (Flats)"). ``cover`` goes first: "Cover Artist" must not
    fall into penciller through "artist"."""
    r = (role_name or "").lower()
    for needle, kind in (("cover", "coverartist"), ("writer", "writer"),
                         ("script", "writer"), ("plot", "writer"),
                         ("pencil", "penciller"), ("artist", "penciller"),
                         ("ink", "inker"), ("colo", "colorist"),
                         ("letter", "letterer")):
        if needle in r:
            return kind
    return None


def pending_provider_issue_ids(series_id, issue_ids):
    """The ids in ``issue_ids`` whose Metron credits were never fetched."""
    try:
        with db_conn() as conn:
            if not conn:
                return list(issue_ids)
            done = {r[0] for r in conn.execute(
                "SELECT DISTINCT issue_id FROM metron_issue_credits WHERE series_id = ?",
                (series_id,))}
    except Exception as e:
        app_logger.error(f"Failed to read fetched Metron credits for {series_id}: {e}")
        return list(issue_ids)
    return [i for i in issue_ids if i not in done]


def save_provider_issue_credits(series_id, issue_id, credits):
    """Store one issue's ``[(kind, name), ...]``; an empty list records "none"."""
    rows = sorted({(k, n) for k, n in credits if k in CREDIT_KINDS and n}) or [("", "")]
    try:
        with db_conn() as conn:
            if not conn:
                return False
            conn.execute("DELETE FROM metron_issue_credits WHERE issue_id = ?", (issue_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO metron_issue_credits (series_id, issue_id, kind, name)"
                " VALUES (?, ?, ?, ?)", [(series_id, issue_id, k, n) for k, n in rows])
            conn.commit()
            return True
    except Exception as e:
        app_logger.error(f"Failed to save Metron credits for issue {issue_id}: {e}")
        return False


def provider_credits(series_id):
    """Everyone Metron credits on a series' fetched issues, shaped like
    ``series_credits``: ``{"fetched": issues fetched, "roles": [...]}`` with
    each person's issue count. None when nothing is fetched or unreadable."""
    try:
        with db_conn() as conn:
            if not conn:
                return None
            fetched = conn.execute(
                "SELECT COUNT(DISTINCT issue_id) FROM metron_issue_credits WHERE series_id = ?",
                (series_id,)).fetchone()[0]
            rows = conn.execute(
                "SELECT kind, MIN(name) AS name, COUNT(DISTINCT issue_id) AS n"
                " FROM metron_issue_credits WHERE series_id = ? AND kind != ''"
                " GROUP BY kind, name COLLATE NOCASE", (series_id,)).fetchall()
    except Exception as e:
        app_logger.error(f"Failed to read Metron credits for {series_id}: {e}")
        return None
    if not fetched:
        return None
    roles = []
    for kind in CREDIT_KINDS:
        people = sorted(({"name": r["name"], "count": r["n"]} for r in rows if r["kind"] == kind),
                        key=lambda p: (-p["count"], p["name"].casefold()))
        if people:
            roles.append({"kind": kind, "label": ROLE_LABELS[kind], "people": people})
    return {"fetched": fetched, "roles": roles}


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
# Teams. Where a team appears comes only from ComicInfo <Teams> (the "teams"
# tag kind): guessing from members counted a Batman solo issue as Justice
# League. Who is on a team comes from character_teams (core/person_art.py).
# --------------------------------------------------------------------------

def list_teams(q="", prefixes=None, limit=300):
    """Teams tagged in owned issues, with issue counts, most first."""
    return list_people(("teams",), q=q, prefixes=prefixes, limit=limit)


def team_members(team, prefixes=None):
    """``[{"name", "n"}]``: the team's member characters the library owns."""
    scope_sql, scope_params = _scope(prefixes)
    with db_conn() as conn:
        if not conn:
            return []
        rows = conn.execute(
            "SELECT MIN(t.value) AS name, COUNT(DISTINCT t.file_path) AS n"
            " FROM character_teams ct"
            " JOIN person_art pa ON pa.kind = 'character' AND pa.key = ct.character_key"
            " JOIN file_metadata_tags t ON t.kind = 'characters' AND t.value = pa.name COLLATE NOCASE"
            " JOIN file_index fi ON fi.path = t.file_path"
            " WHERE " + _COMIC_FILE_CLAUSE_FI + " AND ct.team_key = ?" + scope_sql
            + " GROUP BY t.value COLLATE NOCASE ORDER BY n DESC, name",
            [(team or "").strip().casefold(), *scope_params]).fetchall()
        return [dict(r) for r in rows]


def team_name(team):
    """The team's spelling from Metron membership, or None when no character names it."""
    with db_conn() as conn:
        if not conn:
            return None
        row = conn.execute(
            "SELECT team_name FROM character_teams WHERE team_key = ? LIMIT 1",
            ((team or "").strip().casefold(),)).fetchone()
        return row["team_name"] if row else None


def team_page(team, prefixes=None, user_id=None, view="series"):
    """A team page: ``person_page`` over issues tagged with the team, plus ``members``.

    A team known only through its members (no issue carries it in <Teams>) still
    has a page, with no issues. None when neither source knows the name.
    """
    data = person_page(("teams",), team, prefixes=prefixes, user_id=user_id, view=view)
    if data is None:
        name = team_name(team)
        if name is None:
            return None
        data = {"name": name, "roles": [], "series": [], "often_with": [], "issues": 0,
                "read": 0, "first_year": None, "last_read": None}
    data["members"] = team_members(team, prefixes)
    return data


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


# ---------------------------------------------------------------------------
# Character page
# ---------------------------------------------------------------------------

def _number_key(number):
    """Issue numbers in reading order: 1, 2, 10, 10.5, then anything non-numeric."""
    try:
        return (0, float(number), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(number or ""))


def timeline_key(issue):
    """Timeline order: year, then series, then issue number. Undated issues last."""
    return (issue["year"] or 9999, (issue["series"] or "").casefold(),
            _number_key(issue["number"]), issue["path"])


def tag_counts(kinds, names, prefixes=None):
    """``{casefolded name: {"name", "n"}}`` for the names the library has under kinds.

    How allies, teams and creators become links: a name in the result has a
    CLU page and an issue count, any other stays plain text.
    """
    names = [n for n in dict.fromkeys(names or ()) if n]
    if not names:
        return {}
    kinds = tuple(kinds)
    scope_sql, scope_params = _scope(prefixes)
    with db_conn() as conn:
        if not conn:
            return {}
        rows = conn.execute(
            "SELECT MIN(t.value) AS name, COUNT(DISTINCT t.file_path) AS n"
            + _person_from(kinds, names) + scope_sql + " GROUP BY t.value COLLATE NOCASE",
            [*kinds, *names, *scope_params]).fetchall()
    return {r["name"].casefold(): dict(r) for r in rows}


def character_teams(name):
    """Team names Metron lists for the character (``character_teams``)."""
    with db_conn() as conn:
        if not conn:
            return []
        rows = conn.execute(
            "SELECT team_name FROM character_teams WHERE character_key = ?"
            " ORDER BY team_name COLLATE NOCASE",
            ((name or "").strip().casefold(),)).fetchall()
    return [r["team_name"] for r in rows if r["team_name"]]


def character_details(name, prefixes=None, user_id=None, top_creators=8):
    """What a character page adds to ``person_page``, or None on a read failure.

    ``issues`` is every owned issue in Timeline order (Timeline, Read next,
    Newest, first in the library); ``creators`` the people credited most on
    them, any role, with the role they hold most there; ``lists`` the reading
    lists holding any of them, counted within the user's folder scope.
    """
    uid = _resolve_user_id(user_id)
    scope_sql, scope_params = _scope(prefixes)
    base = _person_from(("characters",), [name]) + scope_sql
    args = ["characters", name, *scope_params]

    with db_conn() as conn:
        if not conn:
            return None
        c = conn.cursor()
        c.execute(
            "SELECT DISTINCT fi.path AS path, fi.name AS name, fi.parent AS parent,"
            " fi.ci_series AS series, fi.ci_number AS number,"
            " NULLIF(CAST(fi.ci_year AS INTEGER), 0) AS year, fi.ci_title AS title,"
            " fi.ci_publisher AS publisher, fi.ci_cvid AS cvid,"
            " (r.issue_path IS NOT NULL) AS read"
            + base.replace(
                "WHERE",
                "LEFT JOIN issues_read r ON r.issue_path = fi.path AND r.user_id = ?"
                " WHERE", 1),
            [uid, *args])
        issues = [dict(r) for r in c.fetchall()]

        credits = base.replace(
            "WHERE",
            "JOIN file_metadata_tags t2 ON t2.file_path = t.file_path"
            f" AND t2.kind IN ({_in(CREDIT_KINDS)}) WHERE", 1)
        c.execute(
            "SELECT MIN(t2.value) AS name, COUNT(DISTINCT t.file_path) AS n" + credits
            + " GROUP BY t2.value COLLATE NOCASE ORDER BY n DESC, name LIMIT ?",
            [*CREDIT_KINDS, *args, top_creators])
        people = [dict(r) for r in c.fetchall()]
        roles = {}
        if people:
            c.execute(
                "SELECT t2.value AS name, t2.kind AS kind, COUNT(DISTINCT t.file_path) AS n"
                + credits + " AND " + _name_match("t2.value", [p["name"] for p in people])
                + " GROUP BY t2.value COLLATE NOCASE, t2.kind",
                [*CREDIT_KINDS, *args, *[p["name"] for p in people]])
            for r in c.fetchall():
                best = roles.get(r["name"].casefold())
                # Ties go to the order of CREDIT_KINDS: writer before penciller...
                if not best or (r["n"], -CREDIT_KINDS.index(r["kind"])) > (
                        best["n"], -CREDIT_KINDS.index(best["kind"])):
                    roles[r["name"].casefold()] = dict(r)

        c.execute(
            "SELECT e.reading_list_id AS id,"
            " COALESCE(e.manual_override_path, e.matched_file_path) AS path"
            " FROM reading_list_entries e"
            " JOIN file_metadata_tags t ON t.file_path = COALESCE(e.manual_override_path, e.matched_file_path)"
            " AND t.kind = 'characters' AND t.value = ? COLLATE NOCASE",
            [name])
        owned = {i["path"] for i in issues}
        hits = {}
        for r in c.fetchall():
            if r["path"] in owned:
                hits.setdefault(r["id"], set()).add(r["path"])
        lists = []
        if hits:
            ids = list(hits)
            c.execute(
                "SELECT rl.id, rl.name, COUNT(e.id) AS total,"
                " MIN(COALESCE(e.manual_override_path, e.matched_file_path)) AS cover"
                " FROM reading_lists rl LEFT JOIN reading_list_entries e ON e.reading_list_id = rl.id"
                f" WHERE rl.id IN ({_in(ids)}) GROUP BY rl.id", ids)
            lists = [{**dict(r), "hits": len(hits[r["id"]])} for r in c.fetchall()]
            lists.sort(key=lambda l: (-l["hits"], l["name"].casefold()))

    issues.sort(key=timeline_key)
    for i in issues:
        i["read"] = bool(i["read"])
        i["series"] = i["series"] or (i["parent"] or "").rstrip("/").rsplit("/", 1)[-1]
    for p in people:
        r = roles.get(p["name"].casefold(), {})
        p["kind"] = r.get("kind", "writer")
        p["role"] = ROLE_LABELS.get(p["kind"], p["kind"])
    publishers = {}
    for i in issues:
        if i["publisher"]:
            publishers[i["publisher"]] = publishers.get(i["publisher"], 0) + 1
    unread = next((n for n, i in enumerate(issues) if not i["read"]), None)
    return {
        "issues": issues,
        "creators": people,
        "lists": lists,
        "publisher": max(publishers, key=publishers.get) if publishers else None,
        # Read next: the earliest unread issue; None once every issue is read.
        "next_index": unread,
    }


def _merge_names(*lists):
    """Names from several sources, one per casefolded spelling, first spelling wins."""
    seen = {}
    for names in lists:
        for n in names or ():
            if n and n.casefold() not in seen:
                seen[n.casefold()] = n
    return list(seen.values())


def _linked(names, counts):
    """``[{"name", "n"}]``: names the library has (with a count) first, then the rest."""
    rows = [{"name": counts[n.casefold()]["name"], "n": counts[n.casefold()]["n"]}
            if n.casefold() in counts else {"name": n, "n": 0} for n in names]
    return sorted(rows, key=lambda r: (-r["n"], r["name"].casefold()))


def character_info(name, profile, issues, prefixes=None):
    """The Information column: one winner per field (docs/browse-hub.md).

    ``profile`` is ``entity_profiles.get_profile`` (or None); ``issues`` is
    ``character_details``' Timeline list, for the first appearance and first
    in your library. Allies, teams and creators carry an issue count when the
    library has them, which is what makes them links.
    """
    m = (profile or {}).get("metron") or {}
    cv = (profile or {}).get("cv") or {}
    teams = _merge_names(character_teams(name), cv.get("teams"))
    creators = m.get("creators") or cv.get("creators") or []
    friends = [f["name"] for f in cv.get("friends") or () if f.get("name")]
    enemies = [f["name"] for f in cv.get("enemies") or () if f.get("name")]
    chars = tag_counts(("characters",), friends + enemies, prefixes)

    first = None
    fi = cv.get("first_issue") or {}
    if fi.get("id"):
        owned = next((i for i in issues if i["cvid"] == fi["id"]), None)
        first = {"issue": owned, "name": fi.get("name"), "number": fi.get("number")}

    links = []
    if m.get("url"):
        links.append(("Metron", m["url"]))
    if cv.get("url"):
        links.append(("ComicVine", cv["url"]))
    if str(m.get("gcd_id") or "").isdigit():
        links.append(("GCD", f"https://www.comics.org/character/{m['gcd_id']}/"))

    return {
        "bio": m.get("desc") or cv.get("summary"),
        "universe": ", ".join(m.get("universes") or []),
        "real_name": cv.get("real_name"),
        "aliases": m.get("alias") or cv.get("aliases") or [],
        "created_by": _linked(creators, tag_counts(CREDIT_KINDS, creators, prefixes)),
        "first_appearance": first,
        "first_owned": issues[0] if issues else None,
        "origin": cv.get("origin"),
        "teams": _linked(teams, tag_counts(("teams",), teams, prefixes)),
        "powers": cv.get("powers") or [],
        "allies": _linked(friends, chars),
        "enemies": _linked(enemies, chars),
        "links": links,
        "has_metron": bool(m),
        "has_cv": bool(cv),
    }
