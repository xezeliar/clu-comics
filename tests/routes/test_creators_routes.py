"""Routes: creator pages, character pages, follow a creator."""

from urllib.parse import quote

import pytest


def _file(conn, parent, name, series, number, year=2020, **ci):
    path = f"{parent}/{name}"
    cols = {"name": name, "path": path, "type": "file", "size": 1, "parent": parent,
            "has_comicinfo": 1, "ci_publisher": "DC", "ci_series": series,
            "ci_number": str(number), "ci_year": year}
    cols.update(ci)
    conn.execute(
        f"INSERT INTO file_index ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        list(cols.values()))
    conn.commit()
    return path


@pytest.fixture(autouse=True)
def _library_root_is_data(monkeypatch):
    """The browse queries only count rows under a library root; these rows live under /data."""
    monkeypatch.setattr("helpers.library.get_library_roots", lambda: ["/data"])


@pytest.fixture
def library(db_connection):
    from core.database import _backfill_file_metadata_tags
    a = "/data/DC/Batman"
    b = "/data/DC/Detective"
    p1 = _file(db_connection, a, "B1.cbz", "Batman", 1, ci_writer="Tom King",
               ci_penciller="Mitch Gerads", ci_characters="Batman, Joker")
    _file(db_connection, a, "B2.cbz", "Batman", 2, ci_writer="Tom King",
          ci_penciller="Mitch Gerads", ci_characters="Batman, Catwoman")
    _file(db_connection, b, "D1.cbz", "Detective", 1, year=2018, ci_writer="Tom King",
          ci_penciller="Clay Mann", ci_characters="Batman")
    _file(db_connection, "/data/X", "X1.cbz", "Other", 1, ci_writer="Someone Else",
          ci_editor="Jamie Rich", ci_translator="Ana Ruiz")
    _backfill_file_metadata_tags(db_connection)
    db_connection.execute(
        "INSERT INTO issues_read (issue_path, user_id) VALUES (?, 1)", (p1,))
    db_connection.commit()
    return db_connection


class TestCreatorPage:
    def test_page_shows_roles_series_and_coworkers(self, client, library):
        body = client.get("/creators/" + quote("Tom King")).get_data(as_text=True)
        assert "Tom King" in body and "Credited most in" in body
        assert '<span class="clu-stat-value">3</span> issues' in body
        assert "Batman" in body and "Detective" in body
        # Works most with: everyone credited on the same issues, never the creator.
        assert "/creators/Mitch%20Gerads?role=penciller" in body and "Penciller · 2 issues" in body
        assert "/creators/Clay%20Mann?role=penciller" in body
        assert "Someone Else" not in body and "/creators/Tom%20King?role=writer" not in body
        # Credited characters: from the files, each a link.
        assert 'href="/characters/Batman"' in body and 'href="/characters/Catwoman"' in body
        assert 'id="followBtn"' in body and "Read next" in body

    def test_lookup_is_case_and_provider_id_insensitive(self, client, library):
        assert client.get("/creators/tom%20king").status_code == 200
        assert client.get("/creators/" + quote("Tom King [123]")).status_code == 200

    def test_unknown_creator_is_404(self, client, library):
        assert client.get("/creators/Nobody").status_code == 404

    @pytest.fixture
    def two_roles(self, library):
        from core.database import _backfill_file_metadata_tags
        _file(library, "/data/Y", "Y1.cbz", "Second", 1, ci_writer="Ana Ruiz")
        _backfill_file_metadata_tags(library)
        return library

    def test_role_filter_lists_only_owned_roles(self, client, two_roles):
        body = client.get("/creators/Ana%20Ruiz?tab=comics").get_data(as_text=True)
        assert 'id="chRole"' in body
        assert 'Writer<span class="clu-filter-count">1</span>' in body
        assert 'Translator<span class="clu-filter-count">1</span>' in body
        assert "Penciller<span" not in body
        # One role only: no Role filter.
        assert 'id="chRole"' not in client.get("/creators/Tom%20King?tab=comics").get_data(as_text=True)

    def test_role_narrows_series_and_issues(self, client, two_roles):
        series = client.get("/creators/Ana%20Ruiz?tab=comics&role=writer").get_data(as_text=True)
        grid = series[series.index('class="ch-grid"'):]
        assert ">Second<" in grid and ">Other<" not in grid
        issues = client.get("/creators/Ana%20Ruiz?tab=comics&view=issues&role=translator").get_data(as_text=True)
        assert 'aria-label="Read Other #1"' in issues and "Read Second #1" not in issues

    def test_role_alone_opens_comics(self, client, two_roles):
        body = client.get("/creators/Ana%20Ruiz?role=writer").get_data(as_text=True)
        assert 'id="chRole"' in body
        # A role the creator does not have is ignored, not a 404.
        assert client.get("/creators/Tom%20King?role=penciller").status_code == 200

    def test_editor_and_translator_have_pages(self, client, library):
        body = client.get("/creators/Jamie%20Rich").get_data(as_text=True)
        assert "Roles in your library" in body and "/creators/Jamie%20Rich?tab=comics&amp;role=editor" in body
        assert client.get("/creators/Ana%20Ruiz").status_code == 200

    def test_header_shows_initials_not_a_cover(self, client, library):
        body = client.get("/creators/Tom%20King").get_data(as_text=True)
        assert '<span class="ch-ini" aria-hidden="true">TK</span>' in body and 'class="ch-src"' not in body

    def test_index_lists_and_searches(self, client, library):
        body = client.get("/creators").get_data(as_text=True)
        assert "Tom King" in body and "Clay Mann" in body
        body = client.get("/creators?q=mann").get_data(as_text=True)
        assert "Clay Mann" in body and "Tom King" not in body


class TestCharacterPage:
    def test_page(self, client, library):
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "Batman" in body and "DC" in body
        assert '<span class="clu-stat-value">3</span> issues' in body
        assert '<span class="clu-stat-value">2</span> series' in body
        assert '<span class="clu-stat-value">1</span> read' in body
        assert "2018–2020" in body
        # Creators: most credited, any role, with their main role and a role filter link.
        assert "/creators/Tom%20King?role=writer" in body and "Writer · 3 issues" in body
        assert "Read next" in body

    def test_unknown_is_404(self, client, library):
        assert client.get("/characters/Nobody").status_code == 404

    def test_index(self, client, library):
        body = client.get("/characters").get_data(as_text=True)
        assert "Batman" in body and "Joker" in body

    def test_creator_names_are_not_characters(self, client, library):
        assert client.get("/characters/Tom%20King").status_code == 404

    def test_titles_tab_sorts(self, client, library):
        body = client.get("/characters/Batman?tab=titles&tsort=az").get_data(as_text=True)
        grid = body[body.index('class="ch-grid"'):]
        assert grid.index(">Batman<") < grid.index(">Detective<")
        grid = client.get("/characters/Batman?tab=titles").get_data(as_text=True)
        grid = grid[grid.index('class="ch-grid"'):]
        assert grid.index(">Batman<") < grid.index(">Detective<")  # 2 issues before 1
        grid = client.get("/characters/Batman?tab=titles&tsort=year").get_data(as_text=True)
        grid = grid[grid.index('class="ch-grid"'):]
        assert grid.index(">Detective<") < grid.index(">Batman<")  # 2018 before 2020

    def test_timeline_groups_by_year_and_filters(self, client, library):
        body = client.get("/characters/Batman?tab=timeline").get_data(as_text=True)
        assert body.index("<h3>2018") < body.index("<h3>2020")
        assert "3 issues</span>" in body
        unread = client.get("/characters/Batman?tab=timeline&status=unread").get_data(as_text=True)
        assert 'aria-label="Read Batman #1' not in unread and 'aria-label="Read Batman #2"' in unread
        read = client.get("/characters/Batman?tab=timeline&status=read").get_data(as_text=True)
        assert 'aria-label="Read Batman #1, read"' in read and "Detective #1" not in read.split('class="ch-body"')[1].split('<aside')[0]

    def test_timeline_page_size_snaps_and_page_clamps(self, client, library):
        body = client.get("/characters/Batman?tab=timeline&per_page=1&page=9").get_data(as_text=True)
        assert '<option value="24" selected>' in body  # 1 snaps to the nearest size
        assert 'data-page="1"' in body and 'data-pages="1"' in body

    def test_bad_query_values_fall_back(self, client, library):
        assert client.get("/characters/Batman?tab=x&sort=y&status=z&page=abc&per_page=-4").status_code == 200

    def test_read_next_is_earliest_unread(self, client, library):
        body = client.get("/characters/Batman").get_data(as_text=True)
        # D1 (2018) is unread and earliest; B1 is read.
        assert 'title="Detective #1"' in body

    def test_all_read_offers_read_again(self, client, library):
        for p in ("/data/DC/Batman/B2.cbz", "/data/DC/Detective/D1.cbz"):
            library.execute("INSERT INTO issues_read (issue_path, user_id) VALUES (?, 1)", (p,))
        library.commit()
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "Read again from the start" in body and "btn-primary\" id=\"readNextBtn" not in body

    def test_information_from_stored_profile(self, client, library):
        import json
        library.execute(
            "INSERT INTO entity_profiles (kind, key, name, metron_id, cv_id, metron_json, cv_json,"
            " metron_fetched_at, status) VALUES ('character', 'batman', 'Batman', 1, 2, ?, ?, '2026-11-01 00:00:00', 'ok')",
            (json.dumps({"desc": "The Dark Knight.", "gcd_id": 7, "url": "https://metron.cloud/character/batman/",
                         "alias": ["Bruce"], "universes": ["DC Universe"], "creators": ["Bob Kane"]}),
             json.dumps({"summary": "x", "real_name": "Bruce Wayne", "origin": "Human",
                         "url": "https://comicvine.gamespot.com/batman/4005-1699/",
                         "friends": [{"id": 1, "name": "Catwoman"}], "enemies": [{"id": 2, "name": "Bane"}],
                         "first_issue": {"id": 99, "name": "Chemical Syndicate", "number": "27"},
                         "powers": [], "teams": ["Justice League"]})))
        library.commit()
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "The Dark Knight." in body and "DC Universe" in body and "Bruce Wayne" in body
        assert '<a href="/characters/Catwoman">Catwoman</a>' in body  # in the library: a link
        assert "<span>Bane</span>" in body  # not in the library: plain text
        assert "Not in your library" in body
        assert "https://www.comics.org/character/7/" in body and "metron.cloud" in body
        assert "Details from Metron and ComicVine, stored 2026-11-01." in body

    def test_no_profile_says_so(self, client, library):
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "No Metron record yet." in body

    def test_reading_lists_featuring(self, client, library):
        library.execute("INSERT INTO reading_lists (id, name, source) VALUES (5, 'Year One', 'manual')")
        for p in ("/data/DC/Batman/B1.cbz", "/data/X/X1.cbz"):
            library.execute("INSERT INTO reading_list_entries (reading_list_id, matched_file_path) VALUES (5, ?)", (p,))
        library.commit()
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "/reading-lists/5" in body and "1 of 2 entries feature Batman" in body


class TestFollowApi:
    def test_follow_update_unfollow(self, client, library):
        r = client.post("/api/creators/follow", json={"name": "Tom King"})
        assert r.status_code == 200 and r.get_json()["follow"]["role"] == "writer"
        r = client.post("/api/creators/follow",
                        json={"name": "tom king", "role": "penciller", "scope": "ongoing"})
        assert r.get_json()["follow"]["scope"] == "ongoing"
        assert len(client.get("/api/creators/follows").get_json()["follows"]) == 1
        assert "Following" in client.get("/creators/Tom%20King").get_data(as_text=True)
        assert client.delete("/api/creators/follow", json={"name": "Tom King"}).status_code == 200
        assert client.delete("/api/creators/follow", json={"name": "Tom King"}).status_code == 404

    @pytest.mark.parametrize("body", [
        {}, {"name": "A", "role": "bogus"}, {"name": "A", "scope": "bogus"}])
    def test_bad_input_is_400(self, client, library, body):
        assert client.post("/api/creators/follow", json=body).status_code == 400

    def test_delete_without_name_is_400(self, client, library):
        assert client.delete("/api/creators/follow").status_code == 400


class TestExpandSeriesIssues:
    def test_lists_only_the_issues_the_person_is_on(self, client, library):
        d = client.get("/api/creators/Tom%20King/issues?folder=" + quote("/data/DC/Batman")).get_json()
        assert d["success"]
        assert [i["number"] for i in d["issues"]] == ["1", "2"]
        assert [i["read"] for i in d["issues"]] == [1, 0]
        assert d["folder_href"]

    def test_character_issues_are_filtered_by_the_tag(self, client, library):
        d = client.get("/api/characters/Joker/issues?folder=" + quote("/data/DC/Batman")).get_json()
        assert [i["number"] for i in d["issues"]] == ["1"]

    def test_role_narrows_to_that_credit(self, client, library):
        url = "/api/creators/Mitch%20Gerads/issues?role=writer&folder=" + quote("/data/DC/Batman")
        assert client.get(url).get_json()["issues"] == []

    def test_other_folder_or_unknown_person_is_empty(self, client, library):
        assert client.get("/api/creators/Tom%20King/issues?folder=" + quote("/data/X")).get_json()["issues"] == []
        assert client.get("/api/creators/Nobody/issues?folder=" + quote("/data/DC/Batman")).get_json()["issues"] == []

    def test_folder_is_required(self, client, library):
        assert client.get("/api/creators/Tom%20King/issues").status_code == 400

    def test_creator_page_has_the_reader(self, client, library):
        body = client.get("/creators/Tom%20King").get_data(as_text=True)
        assert 'id="comicReaderModal"' in body
