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
    _file(db_connection, "/data/X", "X1.cbz", "Other", 1, ci_writer="Someone Else")
    _backfill_file_metadata_tags(db_connection)
    db_connection.execute(
        "INSERT INTO issues_read (issue_path, user_id) VALUES (?, 1)", (p1,))
    db_connection.commit()
    return db_connection


class TestCreatorPage:
    def test_page_shows_roles_series_and_coworkers(self, client, library):
        body = client.get("/creators/" + quote("Tom King")).get_data(as_text=True)
        assert "Tom King" in body
        assert 'Writer<span class="clu-filter-count">3</span>' in body
        assert "Batman" in body and "Detective" in body
        assert 'Mitch Gerads<span class="clu-filter-count">2</span>' in body
        assert 'Clay Mann<span class="clu-filter-count">1</span>' in body
        assert "Someone Else" not in body

    def test_lookup_is_case_and_provider_id_insensitive(self, client, library):
        assert client.get("/creators/tom%20king").status_code == 200
        assert client.get("/creators/" + quote("Tom King [123]")).status_code == 200

    def test_unknown_creator_is_404(self, client, library):
        assert client.get("/creators/Nobody").status_code == 404

    def test_role_filter_keeps_other_pills(self, client, library):
        body = client.get("/creators/Mitch%20Gerads?role=penciller").get_data(as_text=True)
        assert 'Penciller<span class="clu-filter-count">2</span>' in body
        assert client.get("/creators/Tom%20King?role=penciller").status_code == 404

    def test_unread_view_hides_finished_series(self, client, library, db_connection):
        db_connection.execute(
            "INSERT INTO issues_read (issue_path, user_id) VALUES ('/data/DC/Detective/D1.cbz', 1)")
        db_connection.commit()
        body = client.get("/creators/Tom%20King?view=unread").get_data(as_text=True)
        assert "Detective" not in body and "Batman" in body

    def test_read_progress(self, client, library):
        body = client.get("/creators/Tom%20King").get_data(as_text=True)
        assert "3 issues owned · 1 read" in body

    def test_index_lists_and_searches(self, client, library):
        body = client.get("/creators").get_data(as_text=True)
        assert "Tom King" in body and "Clay Mann" in body
        body = client.get("/creators?q=mann").get_data(as_text=True)
        assert "Clay Mann" in body and "Tom King" not in body


class TestCharacterPage:
    def test_page(self, client, library):
        body = client.get("/characters/Batman").get_data(as_text=True)
        assert "2 series · 3 issues owned · 1 read" in body
        assert 'Joker<span class="clu-filter-count">1</span>' in body and 'Catwoman<span class="clu-filter-count">1</span>' in body
        assert "first seen 2018" in body

    def test_unknown_is_404(self, client, library):
        assert client.get("/characters/Nobody").status_code == 404

    def test_index(self, client, library):
        body = client.get("/characters").get_data(as_text=True)
        assert "Batman" in body and "Joker" in body

    def test_creator_names_are_not_characters(self, client, library):
        assert client.get("/characters/Tom%20King").status_code == 404


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

    def test_cards_expand_instead_of_linking(self, client, library):
        body = client.get("/creators/Tom%20King").get_data(as_text=True)
        assert 'class="person-card"' in body and 'aria-expanded="false"' in body
        assert 'id="comicReaderModal"' in body
