"""Creator, character and team pages, follow-a-creator (core/creators.py),
and the cached Metron photos those grids show (core/person_art.py)."""

from flask import (Blueprint, abort, current_app, jsonify, render_template, request,
                   send_file, url_for)

from core import creators, entity_profiles, person_art
from core.auth import accessible_folder_prefixes, current_user, role_at_least
from core.database import get_series_slugs_for_folders
from core.metadata_normalize import strip_provider_ids
from helpers.paging import snap_per_page

creators_bp = Blueprint("creators", __name__)


def _view():
    view = request.args.get("view", "series")
    return view if view in creators.CHARACTER_VIEWS else "series"


def _render_page(data, template, view, **extra):
    if data is None:
        abort(404)
    for s in data["series"]:
        s["thumbnail_url"] = url_for("get_thumbnail", path=s["cover"])
        s["href"] = url_for("collection.collection", path=s["parent"])
    if extra.get("kind") in ART_KINDS:
        kind = ART_KINDS[extra["kind"]]
        data["art"] = person_art.art_urls(kind, [data["name"]]).get(data["name"])
        data["profile"] = entity_profiles.get_profile(kind, data["name"])
        # Opening a detail page is the only thing that asks Metron for a photo
        # or a profile; ensure() is a no-op once both are stored.
        data["looking"] = False
        if (current_app.config.get("METRON_API_TOKEN") or "").strip():
            data["looking"] = person_art.ensure(
                current_app._get_current_object(), kind, data["name"]) or person_art.in_flight(
                kind, data["name"])
    return render_template(template, p=data, view=view, **extra)


def _page(kinds, name, template, role_kinds=None, **extra):
    name = strip_provider_ids(name) or name
    view = _view()
    data = creators.person_page(
        kinds, name, prefixes=accessible_folder_prefixes(current_user()), view=view,
        role_kinds=role_kinds)
    return _render_page(data, template, view, **extra)


# Grid kind -> person_art kind.
ART_KINDS = {"creators": "creator", "characters": "character", "teams": "team"}


def _index(people, kind, q, **extra):
    art = person_art.art_urls(ART_KINDS[kind], [p["name"] for p in people])
    for p in people:
        p["art"] = art.get(p["name"])
    return render_template("people_index.html", people=people, q=q, kind=kind, **extra)


def _issues(kinds, name, lookup=None):
    folder = request.args.get("folder", "")
    if not folder:
        return jsonify({"success": False, "error": "Missing folder"}), 400
    prefixes = accessible_folder_prefixes(current_user())
    name = strip_provider_ids(name) or name
    if lookup is not None:
        issues = lookup(name, folder, prefixes=prefixes)
    else:
        issues = creators.person_issues(kinds, name, folder, prefixes=prefixes)
    if issues is None:
        return jsonify({"success": False, "error": "Could not read issues"}), 500
    for i in issues:
        i["thumbnail_url"] = url_for("get_thumbnail", path=i["path"])
    slug = get_series_slugs_for_folders([folder]).get(folder)
    return jsonify({"success": True, "issues": issues,
                    "folder_href": url_for("collection.collection", path=folder),
                    "series_href": url_for("series.series_view", slug=slug) if slug else None})


@creators_bp.route("/creators")
def creators_index():
    q = request.args.get("q", "")
    people = creators.list_people(
        creators.CREDIT_KINDS, q=q, prefixes=accessible_folder_prefixes(current_user()))
    return _index(people, "creators", q, title="Creators", icon="bi-pencil")


@creators_bp.route("/creators/<path:name>")
def creator_page(name):
    kinds = creators.CREDIT_KINDS
    role = request.args.get("role")
    if role in creators.CREDIT_KINDS:
        kinds = (role,)
    follow = creators.get_follow(strip_provider_ids(name) or name)
    return _page(kinds, name, "person.html", role_kinds=creators.CREDIT_KINDS,
                 kind="creators", follow=follow,
                 role=role, roles=creators.ROLE_LABELS, scopes=creators.FOLLOW_SCOPES)


@creators_bp.route("/api/creators/<path:name>/issues")
def api_creator_issues(name):
    role = request.args.get("role")
    kinds = (role,) if role in creators.CREDIT_KINDS else creators.CREDIT_KINDS
    return _issues(kinds, name)


@creators_bp.route("/api/characters/<path:name>/issues")
def api_character_issues(name):
    return _issues(("characters",), name)


@creators_bp.route("/characters")
def characters_index():
    q = request.args.get("q", "")
    people = creators.list_people(
        ("characters",), q=q, prefixes=accessible_folder_prefixes(current_user()))
    return _index(people, "characters", q, title="Characters", icon="bi-people")


CHARACTER_TABS = ("overview", "titles", "timeline")
TITLE_SORTS = {"most": "Most issues", "az": "A–Z", "year": "First year"}
TIMELINE_SORTS = {"old": "Oldest first", "new": "Newest first"}
TIMELINE_STATUS = ("all", "unread", "read")


def _arg(key, allowed, default):
    value = request.args.get(key, default)
    return value if value in allowed else default


def _can_refresh():
    """Refresh is for Clerk and up. No user means no accounts (the implicit
    owner), as in partials/tab_bar.html; the POST is checked again anyway."""
    user = current_user()
    return not user or role_at_least(user, "clerk")


def _detail(data, tag, prefixes, tabs):
    """Fill a character or team page's shared parts from the query string:
    the tab, Titles (series) sort, the paged Timeline (issues), Read next."""
    details = creators.entity_details(tag, data["name"], prefixes=prefixes)
    if details is None:
        abort(503)
    data.update(details)
    st = {"tab": _arg("tab", tabs, "overview"),
          "view": _arg("view", ("series", "issues"), "series"),
          "tsort": _arg("tsort", TITLE_SORTS, "most"),
          "sort": _arg("sort", TIMELINE_SORTS, "old"),
          "status": _arg("status", TIMELINE_STATUS, "all"),
          "per_page": snap_per_page(request.args.get("per_page"))}

    issues = data["issues"]
    for i in issues:
        i["thumbnail_url"] = url_for("get_thumbnail", path=i["path"])
    titles = sorted(data["series"], key=lambda s: s["name"].casefold())
    if st["tsort"] == "most":
        titles.sort(key=lambda s: -s["issues"])
    elif st["tsort"] == "year":
        titles.sort(key=lambda s: s["year"] or 9999)
    data["titles"] = titles

    rows = [i for i in issues if st["status"] == "all" or i["read"] == (st["status"] == "read")]
    if st["sort"] == "new":
        rows = rows[::-1]
    pages = max(1, -(-len(rows) // st["per_page"]))
    try:
        page = min(max(1, int(request.args.get("page", 1))), pages)
    except ValueError:
        page = 1
    start = (page - 1) * st["per_page"]
    st.update(page=page, pages=pages, total=len(rows), first=start + 1,
              last=start + len(rows[start:start + st["per_page"]]))
    data["timeline"] = rows[start:start + st["per_page"]]
    data["read_total"] = sum(1 for i in issues if i["read"])

    nxt = data["next_index"]
    # Read next opens the reader on a run of issues, so its Next button keeps
    # going in Timeline order without sending every issue to the browser.
    run = issues[nxt:nxt + 100] if nxt is not None else issues[:100]
    data["reader_run"] = [{"type": "file", "name": i["name"], "path": i["path"],
                           "thumbnailUrl": i["thumbnail_url"]} for i in run]
    years = [i["year"] for i in issues if i["year"]]
    data["last_year"] = max(years) if years else None
    data["newest"] = [i for i in issues if i["year"]][-6:][::-1]
    data["most"] = sorted(data["series"], key=lambda s: -s["issues"])[:6]
    data["cover_fallback"] = issues[0]["thumbnail_url"] if issues else None
    return st


def _detail_extra(st):
    return {"st": st, "title_sorts": TITLE_SORTS, "timeline_sorts": TIMELINE_SORTS,
            "can_refresh": _can_refresh(),
            "has_token": bool((current_app.config.get("METRON_API_TOKEN") or "").strip())}


@creators_bp.route("/characters/<path:name>")
def character_page(name):
    name = strip_provider_ids(name) or name
    prefixes = accessible_folder_prefixes(current_user())
    data = creators.person_page(("characters",), name, prefixes=prefixes)
    if data is None:
        abort(404)
    st = _detail(data, "characters", prefixes, CHARACTER_TABS)
    profile = entity_profiles.get_profile("character", data["name"])
    data["info"] = creators.character_info(data["name"], profile, data["issues"], prefixes=prefixes)
    return _render_page(data, "character.html", "series", kind="characters", **_detail_extra(st))


TEAM_TABS = ("overview", "members", "comics")
MEMBER_SORTS = {"most": "Most issues together", "az": "A–Z"}


@creators_bp.route("/teams")
def teams_index():
    q = request.args.get("q", "")
    people = creators.list_teams(q=q, prefixes=accessible_folder_prefixes(current_user()))
    return _index(people, "teams", q, title="Teams", icon="bi-people-fill")


@creators_bp.route("/teams/<path:name>")
def team_page(name):
    prefixes = accessible_folder_prefixes(current_user())
    data = creators.team_page(strip_provider_ids(name) or name, prefixes=prefixes)
    if data is None:
        abort(404)
    st = _detail(data, "teams", prefixes, TEAM_TABS)
    # With no tagged issues every member has 0 issues together: sort by name.
    st["msort"] = _arg("msort", MEMBER_SORTS, "most") if data["issues"] else "az"
    profile = entity_profiles.get_profile("team", data["name"])
    data["info"] = creators.team_info(data["name"], profile, data["issues"], prefixes=prefixes)
    data["members"] = creators.team_members(
        data["name"], data["info"]["cv_members"], prefixes=prefixes, sort=st["msort"])
    names = [m["name"] for m in data["members"]["in"]]
    art = person_art.art_urls("character", names)
    for m in data["members"]["in"]:
        m["art"] = art.get(m["name"])
    return _render_page(data, "team.html", "series", kind="teams",
                        member_sorts=MEMBER_SORTS, **_detail_extra(st))


@creators_bp.route("/api/teams/<path:name>/issues")
def api_team_issues(name):
    return _issues(("teams",), name)


@creators_bp.route("/api/<any(characters, teams, creators):grid>/<path:name>/refresh",
                   methods=["POST"])
def refresh_profile(grid, name):
    """Refetch one profile and photo from Metron and ComicVine (Clerk and up).

    The only way a stored profile changes. Runs on a daemon thread; the answer
    says whether it started, or why Metron cannot be asked right now.
    """
    from models import metron

    if not (current_app.config.get("METRON_API_TOKEN") or "").strip():
        return jsonify({"success": False, "error": "Add a Metron API token in Settings first"}), 409
    reason = metron.paused_reason()
    if reason:
        return jsonify({"success": False, "error": reason}), 503
    name = strip_provider_ids(name) or name
    started = person_art.ensure(current_app._get_current_object(), ART_KINDS[grid], name,
                                force=True)
    return jsonify({"success": True, "started": started}), 202


@creators_bp.route("/api/person-art/<kind>/<path:name>", endpoint="person_art")
def person_art_image(kind, name):
    """A cached Metron photo. The file path is a hash of the name, never the name."""
    path = person_art.served_file(kind, name)
    if path is None:
        abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=86400)


# --- follow a creator (clerk+: following adds series to the shared Wanted list) ---

@creators_bp.route("/api/creators/follows", methods=["GET"])
def api_follows():
    return jsonify({"success": True, "follows": creators.list_follows()})


@creators_bp.route("/api/creators/follow", methods=["POST"])
def api_follow():
    body = request.get_json(silent=True) or {}
    try:
        follow = creators.follow_creator(
            body.get("name"), body.get("role", "writer"),
            body.get("publisher"), body.get("scope", "both"))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "follow": follow})


@creators_bp.route("/api/creators/follow", methods=["DELETE"])
def api_unfollow():
    name = (request.get_json(silent=True) or {}).get("name") or request.args.get("name")
    if not name:
        return jsonify({"success": False, "error": "Missing name"}), 400
    if not creators.unfollow_creator(name):
        return jsonify({"success": False, "error": "Not following"}), 404
    return jsonify({"success": True})
