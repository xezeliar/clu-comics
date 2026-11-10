"""Creator pages, character pages and follow-a-creator (core/creators.py)."""

from flask import Blueprint, abort, jsonify, render_template, request, url_for

from core import creators
from core.auth import accessible_folder_prefixes, current_user
from core.metadata_normalize import strip_provider_ids

creators_bp = Blueprint("creators", __name__)


def _page(kinds, name, template, role_kinds=None, **extra):
    name = strip_provider_ids(name) or name
    view = request.args.get("view", "series")
    if view not in creators.CHARACTER_VIEWS:
        view = "series"
    data = creators.person_page(
        kinds, name, prefixes=accessible_folder_prefixes(current_user()), view=view,
        role_kinds=role_kinds)
    if data is None:
        abort(404)
    for s in data["series"]:
        s["thumbnail_url"] = url_for("get_thumbnail", path=s["cover"])
        s["href"] = url_for("collection.collection", path=s["parent"])
    return render_template(template, p=data, view=view, **extra)


def _index(kinds, template, **extra):
    q = request.args.get("q", "")
    people = creators.list_people(
        kinds, q=q, prefixes=accessible_folder_prefixes(current_user()))
    return render_template(template, people=people, q=q, **extra)


@creators_bp.route("/creators")
def creators_index():
    return _index(creators.CREDIT_KINDS, "people_index.html",
                  kind="creators", title="Creators", icon="bi-pencil")


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


@creators_bp.route("/characters")
def characters_index():
    return _index(("characters",), "people_index.html",
                  kind="characters", title="Characters", icon="bi-people")


@creators_bp.route("/characters/<path:name>")
def character_page(name):
    return _page(("characters",), name, "person.html", kind="characters",
                 follow=None, role=None, roles={}, scopes=())


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
