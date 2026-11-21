"""Routes: /teams, /teams/<name>, the person-art image route, /api/insights/who,
and the `art` key on the people grids."""

import os
from types import SimpleNamespace as NS
from unittest.mock import patch
from urllib.parse import quote

import pytest

from core import person_art
from tests.unit.test_person_art import FakeMetron, _jpeg


def _file(conn, path, chars, writer="Tom King", publisher="DC", teams=""):
    parent, name = path.rsplit("/", 1)
    conn.execute(
        "INSERT INTO file_index (name, path, type, size, parent, has_comicinfo,"
        " ci_series, ci_number, ci_publisher, ci_characters, ci_writer, ci_teams)"
        " VALUES (?, ?, 'file', 1, ?, 1, ?, '1', ?, ?, ?, ?)",
        (name, path, parent, parent.rsplit("/", 1)[-1], publisher, chars, writer, teams))


@pytest.fixture
def library(db_connection, tmp_path):
    from core.database import _backfill_file_metadata_tags

    _file(db_connection, "/data/DC/Batman/B1.cbz", "Batman, Joker")
    _file(db_connection, "/data/DC/Batman/B2.cbz", "Batman, Superman", teams="Justice League")
    _file(db_connection, "/data/DC/Superman/S1.cbz", "Superman", teams="Justice League")
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
        assert kwargs["people"] == [{"name": "Justice League", "n": 2, "art": None}]

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
        assert rt.call_args.args[0] == "team.html" and rt.call_args.kwargs["kind"] == "teams"
        assert p["name"] == "Justice League" and len(p["issues"]) == 2
        # Batman is in B1 (no team) and B2 (the team): one issue together of two.
        assert [(m["name"], m["n"], m["total"]) for m in p["members"]["in"]] == [
            ("Superman", 2, 2), ("Batman", 1, 2)]
        assert p["members"]["out"] == []

    def test_character_detail_has_portrait(self, client, library):
        with patch("routes.creators.render_template", return_value="") as rt:
            client.get("/characters/Batman")
        assert rt.call_args.kwargs["p"]["art"].startswith("/api/person-art/character/Batman")

    def test_detail_portrait_renders_photo_or_initials(self, client, library):
        html = client.get("/characters/Batman").get_data(as_text=True)
        assert 'class="ch-pt"' in html and 'src="/api/person-art/character/Batman' in html
        # No team image cached: the first owned cover stands in, labelled.
        assert 'class="ch-src">Cover<' in client.get("/teams/" + quote("justice league")).get_data(as_text=True)

    def test_team_tabs_render(self, client, library):
        url = "/teams/" + quote("Justice League")
        html = client.get(url).get_data(as_text=True)
        assert ">Members<" in html and "2 members" in html and "All 2 members" in html
        members = client.get(url + "?tab=members").get_data(as_text=True)
        assert "In your library" in members and "2 with the team" in members
        assert 'href="/characters/Superman"' in members and "Not in your library" not in members
        issues = client.get(url + "?tab=comics&view=issues").get_data(as_text=True)
        assert 'id="chView"' in issues and 'id="chStatus"' in issues and "class=\"ch-yr\"" in issues
        series = client.get(url + "?tab=comics").get_data(as_text=True)
        assert 'id="chTitleSort"' in series

    def test_untagged_team_shows_empty_state_and_no_comics_tab(self, client, library):
        library.execute("UPDATE file_index SET ci_teams = ''")
        library.execute("DELETE FROM file_metadata_tags WHERE kind = 'teams'")
        library.commit()
        html = client.get("/teams/" + quote("Justice League")).get_data(as_text=True)
        assert "No issues tagged with Justice League" in html
        assert 'id="readNextBtn"' not in html and "tab=comics" not in html and "0 issues" not in html
        members = client.get("/teams/" + quote("Justice League") + "?tab=members").get_data(as_text=True)
        assert "with the team" not in members and "Most issues together" not in members

    def test_unknown_team_is_404(self, client, library):
        assert client.get("/teams/Avengers").status_code == 404

    def test_team_issues_api(self, client, library):
        r = client.get("/api/teams/Justice%20League/issues?folder=/data/DC/Batman")
        assert [i["name"] for i in r.get_json()["issues"]] == ["B2.cbz"]
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
            {"name": "Justice League", "count": 1, "art": None,
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


class TestRefreshProfile:
    @pytest.fixture
    def token(self, app):
        app.config["METRON_API_TOKEN"] = "t"
        yield
        app.config["METRON_API_TOKEN"] = ""

    def test_starts_a_forced_fetch(self, client, library, token):
        with patch("models.metron.paused_reason", return_value=None), \
                patch("core.person_art.ensure", return_value=True) as ensure:
            r = client.post("/api/teams/" + quote("Justice League") + "/refresh")
        assert r.status_code == 202 and r.get_json() == {"success": True, "started": True}
        args, kwargs = ensure.call_args
        assert args[1:] == ("team", "Justice League") and kwargs == {"force": True}

    def test_kind_maps_to_art_kind(self, client, library, token):
        with patch("models.metron.paused_reason", return_value=None), \
                patch("core.person_art.ensure", return_value=False) as ensure:
            assert client.post("/api/creators/Tom%20King%20%5B9%5D/refresh").status_code == 202
        assert ensure.call_args.args[1:] == ("creator", "Tom King")

    def test_paused_metron_is_503(self, client, library, token):
        with patch("models.metron.paused_reason", return_value="Metron rejected the token"), \
                patch("core.person_art.ensure") as ensure:
            r = client.post("/api/characters/Batman/refresh")
        assert r.status_code == 503 and r.get_json()["error"] == "Metron rejected the token"
        ensure.assert_not_called()

    def test_no_token_is_409(self, client, library):
        assert client.post("/api/characters/Batman/refresh").status_code == 409

    def test_unknown_grid_is_404(self, client, library, token):
        assert client.post("/api/publishers/DC/refresh").status_code == 404

    def test_reader_cannot_refresh(self, client, db_connection, monkeypatch, token):
        from core.database import create_user
        monkeypatch.delenv("CLU_USERNAME", raising=False)
        monkeypatch.delenv("CLU_PASSWORD", raising=False)
        create_user("owner", password="ownerpass", role="owner")
        create_user("reader", password="readerpass", role="reader")
        client.post("/login", data={"username": "reader", "password": "readerpass"})
        assert client.post("/api/characters/Batman/refresh").status_code == 403


class TestMatchRoutes:
    """Change match / Unmatch: search, record preview, POST and DELETE."""

    @pytest.fixture
    def token(self, app):
        app.config["METRON_API_TOKEN"] = "t"
        yield
        app.config["METRON_API_TOKEN"] = ""

    @pytest.fixture
    def api(self):
        api = FakeMetron(
            lists={("characters", "Batman"): [NS(id=1, name="Batman"), NS(id=2, name="Batman")]},
            details={("character", 2): NS(id=2, name="Batman", image=None, cv_id=None, desc="Earth-2",
                                         alias=[], universes=[], creators=[], resource_url=None)})
        with patch("models.metron.paused_reason", return_value=None), \
                patch("models.metron.get_flask_api", return_value=api):
            yield api

    def test_search_marks_the_current_match(self, client, library, token, api):
        r = client.get("/api/characters/Batman/match/search?q=Batman")
        assert r.status_code == 200
        data = r.get_json()
        assert data["current"] == 1 and data["unmatched"] is False
        assert [x["id"] for x in data["results"]] == [1, 2]

    def test_current_record_comes_from_the_stored_profile(self, client, library, token, api):
        from core import entity_profiles

        entity_profiles.store("character", "Batman", NS(id=1, cv_id=7, desc="Bruce", name="Batman (1940)"))
        api.calls.clear()
        data = client.get("/api/characters/Batman/match/search").get_json()
        rec = data["current_record"]
        assert rec["id"] == 1 and rec["desc"] == "Bruce" and rec["has_cv"]
        assert rec["name"] == "Batman (1940)"  # the record's own name, not the page's
        assert rec["image"].startswith("/api/person-art/character/Batman")
        assert api.calls == [("characters_list", {"name": "Batman"})]

    def test_record(self, client, library, token, api):
        with patch("core.person_art._default_fetch_image", return_value=None):
            r = client.get("/api/characters/metron-record/2")
        assert r.status_code == 200 and r.get_json()["record"]["desc"] == "Earth-2"

    def test_failed_search_says_failed(self, client, library, token, api):
        api.fail_list = True
        r = client.get("/api/characters/Batman/match/search")
        assert r.status_code == 502 and r.get_json()["reason"] == "failed"

    def test_quota_and_token_reasons(self, client, library, token):
        with patch("models.metron.paused_reason", return_value="Daily limit spent."):
            r = client.get("/api/characters/Batman/match/search")
        assert r.status_code == 503 and r.get_json()["reason"] == "quota"

    def test_no_token(self, client, library):
        r = client.get("/api/characters/Batman/match/search")
        assert r.status_code == 409 and r.get_json()["reason"] == "token"

    def test_post_pins_and_refetches(self, client, library, token, api):
        with patch("core.person_art.ensure", return_value=True) as ensure:
            r = client.post("/api/characters/Batman/match", json={"metron_id": 2})
        assert r.status_code == 202
        assert person_art.current_match("character", "Batman") == (2, False)
        assert ensure.call_args.args[1:] == ("character", "Batman")
        assert ensure.call_args.kwargs == {"force": True}

    def test_post_needs_a_number(self, client, library, token, api):
        assert client.post("/api/characters/Batman/match", json={"metron_id": "x"}).status_code == 400

    def test_delete_unmatches(self, client, library):
        assert client.delete("/api/characters/Batman/match").status_code == 200
        assert person_art.current_match("character", "Batman") == (None, True)
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "Unmatched by hand" in body and 'data-bs-target="#matchModal"' in body
        assert "#unmatchModal" not in body

    def test_matched_page_offers_change_and_unmatch(self, client, library):
        from core import entity_profiles

        entity_profiles.store("character", "Batman", NS(id=1, cv_id=None, desc="x"))
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "Change match" in body and 'data-bs-target="#unmatchModal"' in body
        assert "/static/js/entity-match.js" in body

    def test_reader_gets_403_and_no_modal(self, client, db_connection, library, monkeypatch, token):
        from core.database import create_user
        monkeypatch.delenv("CLU_USERNAME", raising=False)
        monkeypatch.delenv("CLU_PASSWORD", raising=False)
        create_user("owner", password="ownerpass", role="owner")
        create_user("reader", password="readerpass", role="reader")
        client.post("/login", data={"username": "reader", "password": "readerpass"})
        assert client.get("/api/characters/Batman/match/search").status_code == 403
        assert client.get("/api/characters/metron-record/2").status_code == 403
        assert client.post("/api/characters/Batman/match", json={"metron_id": 2}).status_code == 403
        assert client.delete("/api/characters/Batman/match").status_code == 403
        assert "matchModal" not in client.get("/characters/Batman").get_data(as_text=True)


class TestMatchAuditLog:
    """Change match, Unmatch and Refresh say who did it and what was there before."""

    def test_match_and_unmatch_name_the_user_and_old_id(self, client, db_connection, library, monkeypatch, app):
        from core.database import create_user
        monkeypatch.delenv("CLU_USERNAME", raising=False)
        monkeypatch.delenv("CLU_PASSWORD", raising=False)
        create_user("owner", password="ownerpass", role="owner")
        create_user("clerk1", password="clerkpass", role="clerk")
        client.post("/login", data={"username": "clerk1", "password": "clerkpass"})
        app.config["METRON_API_TOKEN"] = "t"
        try:
            with patch("models.metron.paused_reason", return_value=None), \
                    patch("models.metron.get_flask_api", return_value=FakeMetron()), \
                    patch("core.person_art.ensure", return_value=True), \
                    patch("routes.creators.app_logger") as log:
                assert client.post("/api/characters/Batman/match", json={"metron_id": 2}).status_code == 202
                assert client.delete("/api/characters/Batman/match").status_code == 200
                assert client.post("/api/characters/Batman/refresh").status_code == 202
        finally:
            app.config["METRON_API_TOKEN"] = ""
        assert [c.args[0] for c in log.info.call_args_list] == [
            "Person art: character 'Batman' matched to Metron 2 by clerk1 (was Metron 1)",
            "Person art: character 'Batman' unmatched by clerk1 (was Metron 2)",
            "Person art: character 'Batman' refresh asked by clerk1"]
