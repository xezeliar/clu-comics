"""Routes: /teams, /teams/<name>, the person-art image route, /api/insights/who,
and the `art` key on the people grids."""

import os
from types import SimpleNamespace as NS
from unittest.mock import patch
from urllib.parse import quote

import pytest

from core import person_art
from tests.unit.test_person_art import FakeMetron, _jpeg


def _file(conn, path, chars, writer="Tom King", publisher="DC"):
    parent, name = path.rsplit("/", 1)
    conn.execute(
        "INSERT INTO file_index (name, path, type, size, parent, has_comicinfo,"
        " ci_series, ci_number, ci_publisher, ci_characters, ci_writer)"
        " VALUES (?, ?, 'file', 1, ?, 1, ?, '1', ?, ?, ?)",
        (name, path, parent, parent.rsplit("/", 1)[-1], publisher, chars, writer))


@pytest.fixture
def library(db_connection, tmp_path):
    from core.database import _backfill_file_metadata_tags

    _file(db_connection, "/data/DC/Batman/B1.cbz", "Batman, Joker")
    _file(db_connection, "/data/DC/Batman/B2.cbz", "Batman, Superman")
    _file(db_connection, "/data/DC/Superman/S1.cbz", "Superman")
    db_connection.commit()
    _backfill_file_metadata_tags(db_connection)
    api = FakeMetron(
        lists={("characters", "Batman"): [NS(id=1, name="Batman")],
               ("characters", "Superman"): [NS(id=2, name="Superman")]},
        details={("character", 1): NS(id=1, image="https://img/b.jpg",
                                     teams=[NS(id=10, name="Justice League")]),
                 ("character", 2): NS(id=2, image=None, teams=[NS(id=10, name="Justice League")])})
    with patch("core.person_art.get_cache_dir", return_value=str(tmp_path)), \
            patch("helpers.library.get_library_roots", return_value=["/data"]):
        for n in ("Batman", "Superman"):
            person_art.resolve("character", n, api, lambda u: _jpeg())
        yield db_connection


class TestTeamPages:
    def test_index_lists_teams_with_art_key(self, client, library):
        with patch("routes.creators.render_template", return_value="") as rt:
            assert client.get("/teams").status_code == 200
        kwargs = rt.call_args.kwargs
        assert kwargs["kind"] == "teams" and kwargs["title"] == "Teams"
        assert kwargs["icon"] == "bi-people-fill"
        assert kwargs["people"] == [{"name": "Justice League", "n": 3, "art": None}]

    def test_characters_index_attaches_art(self, client, library):
        with patch("routes.creators.render_template", return_value="") as rt:
            client.get("/characters")
        art = {p["name"]: p["art"] for p in rt.call_args.kwargs["people"]}
        assert art["Batman"].startswith("/api/person-art/character/Batman")
        assert art["Superman"] is None and art["Joker"] is None

    def test_index_renders(self, client, library):
        r = client.get("/teams")
        assert r.status_code == 200 and "Justice League" in r.get_data(as_text=True)

    def test_detail_page(self, client, library):
        with patch("routes.creators.render_template", return_value="") as rt:
            assert client.get("/teams/" + quote("justice league")).status_code == 200
        p = rt.call_args.kwargs["p"]
        assert rt.call_args.args[0] == "person.html" and rt.call_args.kwargs["kind"] == "teams"
        assert p["name"] == "Justice League" and p["issues"] == 3
        assert p["members"] == [{"name": "Batman", "n": 2}, {"name": "Superman", "n": 2}]

    def test_unknown_team_is_404(self, client, library):
        assert client.get("/teams/Avengers").status_code == 404

    def test_team_issues_api(self, client, library):
        r = client.get("/api/teams/Justice%20League/issues?folder=/data/DC/Batman")
        assert [i["name"] for i in r.get_json()["issues"]] == ["B1.cbz", "B2.cbz"]
        assert client.get("/api/teams/Justice%20League/issues").status_code == 400


class TestPersonArtRoute:
    def test_serves_cached_jpeg(self, client, library):
        r = client.get("/api/person-art/character/Batman")
        assert r.status_code == 200 and r.mimetype == "image/jpeg"
        assert "max-age=86400" in r.headers["Cache-Control"]

    def test_missing_is_404(self, client, library):
        assert client.get("/api/person-art/character/Superman").status_code == 404

    @pytest.mark.parametrize("url", [
        "/api/person-art/character/..%2F..%2Fetc%2Fpasswd",
        "/api/person-art/character/../../comic_utils.db",
        "/api/person-art/..%2Fcharacter/Batman",
        "/api/person-art/secrets/Batman",
    ])
    def test_traversal_and_unknown_kind_are_404(self, client, library, url):
        assert client.get(url).status_code == 404


class TestInsightsWho:
    @pytest.fixture
    def reads(self, library):
        for path, chars, writer, pub, at in (
                ("/data/DC/Batman/B1.cbz", "Batman, Joker", "Tom King", "DC", "2024-03-01 10:00:00"),
                ("/data/DC/Batman/B2.cbz", "Batman, Superman", "Tom King", "DC", "2024-03-02 10:00:00"),
                ("/data/X.cbz", "Spawn", "Todd McFarlane", "Image", "2023-01-01 10:00:00")):
            library.execute(
                "INSERT INTO issues_read (issue_path, user_id, read_at, characters, writer, publisher)"
                " VALUES (?, 1, ?, ?, ?, ?)", (path, at, chars, writer, pub))
        library.commit()
        return library

    def test_shape_and_counts(self, client, reads):
        d = client.get("/api/insights/who?year=all&limit=8").get_json()
        assert set(d) == {"teams", "characters", "writers", "publishers"}
        assert d["teams"] == {"total": 1, "items": [
            {"name": "Justice League", "count": 2, "art": None,
             "href": "/teams/Justice%20League"}]}
        chars = d["characters"]
        assert chars["total"] == 4
        assert chars["items"][0]["name"] == "Batman" and chars["items"][0]["count"] == 2
        assert chars["items"][0]["art"].startswith("/api/person-art/character/Batman")
        assert chars["items"][0]["href"] == "/characters/Batman"
        assert d["writers"]["items"][0] == {"name": "Tom King", "count": 2, "art": None,
                                           "href": "/creators/Tom%20King"}
        assert d["publishers"]["items"][0]["href"] == "/browse/publisher/DC"

    def test_year_and_limit(self, client, reads):
        d = client.get("/api/insights/who?year=2023&limit=1").get_json()
        assert "teams" not in d
        assert d["characters"] == {"total": 1, "items": [
            {"name": "Spawn", "count": 1, "art": None, "href": "/characters/Spawn"}]}

    def test_empty_history_omits_every_section(self, client, library):
        assert client.get("/api/insights/who").get_json() == {}

    def test_not_login_exempt(self, client, db_connection, monkeypatch):
        from core.database import create_user
        monkeypatch.delenv("CLU_USERNAME", raising=False)
        monkeypatch.delenv("CLU_PASSWORD", raising=False)
        create_user("owner", password="ownerpass", role="owner")
        create_user("reader", password="readerpass", role="reader")
        assert client.get("/api/insights/who").status_code == 401
        # the Homepage widget's exact path stays exempt
        assert client.get("/api/insights").status_code == 200

    def test_reading_trends_helper_unchanged(self, reads):
        from core.database import get_reading_trends
        assert get_reading_trends("characters", user_id=1, limit=2) == [
            {"name": "Batman", "count": 2}, {"name": "Joker", "count": 1}]
        assert get_reading_trends("characters", year=2023, user_id=1) == [
            {"name": "Spawn", "count": 1}]
        assert get_reading_trends("bogus") == []
