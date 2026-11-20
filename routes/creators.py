"""Creator, character and team pages, follow-a-creator (core/creators.py),
and the cached Metron photos those grids show (core/person_art.py)."""

from flask import (Blueprint, abort, current_app, jsonify, render_template, request,
                   send_file, url_for)

from core import creators, person_art
from core.auth import accessible_folder_prefixes, current_user
from core.database import get_series_slugs_for_folders
from core.metadata_normalize import strip_provider_ids

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
        # Opening a detail page is the only thing that asks Metron for a photo.
        if not data["art"] and (current_app.config.get("METRON_API_TOKEN") or "").strip():
            person_art.ensure(current_app._get_current_object(), kind, data["name"])
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


@creators_bp.route("/characters/<path:name>")
def character_page(name):
    return _page(("characters",), name, "person.html", kind="characters",
                 follow=None, role=None, roles={}, scopes=())


@creators_bp.route("/teams")
def teams_index():
    q = request.args.get("q", "")
    people = creators.list_teams(q=q, prefixes=accessible_folder_prefixes(current_user()))
    return _index(people, "teams", q, title="Teams", icon="bi-people-fill")


@creators_bp.route("/teams/<path:name>")
def team_page(name):
    view = _view()
    data = creators.team_page(
        strip_provider_ids(name) or name,
        prefixes=accessible_folder_prefixes(current_user()), view=view)
    return _render_page(data, "person.html", view, kind="teams",
                        follow=None, role=None, roles={}, scopes=())


@creators_bp.route("/api/teams/<path:name>/issues")
def api_team_issues(name):
    return _issues(("teams",), name)


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
