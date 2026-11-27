"""Series, a series' issue list and the issue page (routes/series_index.py,
core/library_series.py). The Series page replaced Smart collections.
"""
import json
import time

import pytest


def _file(conn, parent, name, **ci):
    cols = {"name": name, "path": f"{parent}/{name}", "type": "file", "size": 2097152,
            "parent": parent, "has_comicinfo": 1, "ci_publisher": "DC",
            "ci_series": "Batman", "ci_number": "1", "ci_year": "2016",
            "ci_writer": "Tom King", "first_indexed_at": time.time()}
    cols.update(ci)
    conn.execute(f"INSERT INTO file_index ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 list(cols.values()))
    conn.commit()


@pytest.fixture(autouse=True)
def _library_root_is_data(monkeypatch):
    """The queries only count rows under a library root; these rows live under /data."""
    monkeypatch.setattr("helpers.library.get_library_roots", lambda: ["/data"])
    from core.database import invalidate_metadata_browser_cache
    invalidate_metadata_browser_cache()
    yield
    invalidate_metadata_browser_cache()


@pytest.fixture
def library(db_connection):
    from core.database import _backfill_file_metadata_tags
    b = "/data/DC/Batman"
    _file(db_connection, b, "Batman 001.cbz", ci_title="I Am Gotham", ci_characters="Batman, Gotham Girl")
    _file(db_connection, b, "Batman 002.cbz", ci_number="2", ci_writer="Tom King, Mikel Janin")
    _file(db_connection, b, "Batman 005.cbz", ci_number="5", ci_year="2017")
    _file(db_connection, b, "Batman 006.cbz", ci_series=None, ci_publisher=None, ci_number=None,
          ci_writer=None, ci_year=None, has_comicinfo=0)
    _file(db_connection, "/data/Image/Saga", "Saga 001.cbz", ci_publisher="Image", ci_series="Saga",
          ci_year="2012", ci_writer="Brian K. Vaughan", ci_characters="Alana, Marko")
    _file(db_connection, "/data/Loose", "Mystery.cbz", ci_series=None, ci_publisher=None, ci_number=None,
          ci_writer=None, ci_year=None, has_comicinfo=0)
    db_connection.execute(
        "INSERT INTO series (id, name, volume, mapped_path) VALUES (7, 'Batman', 3, '/data/DC/Batman')")
    db_connection.commit()
    _backfill_file_metadata_tags(db_connection)
    return db_connection


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.setattr("routes.series_index._is_maintainer", lambda: False)


def _body(client, url):
    resp = client.get(url)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


# ---- the model -------------------------------------------------------------

class TestModel:
    def test_numbers_sort_naturally(self):
        from core.library_series import number_sort_key
        assert sorted(["10", "2", "1.MU", "½", "Annual 1", "1", "0"], key=number_sort_key) == \
            ["0", "½", "1", "1.MU", "2", "10", "Annual 1"]

    def test_gap_runs_are_runs_of_whole_numbers(self):
        from core.library_series import gap_runs
        assert gap_runs([1, 2, 5, 6, 9, None]) == [(3, 4), (7, 8)]
        assert gap_runs([3]) == []

    def test_untagged_files_join_their_folders_series(self, library):
        from core.library_series import get_model
        model = get_model(None)
        batman = model["by_key"]["Batman\x1fDC"]
        assert batman["count"] == 4 and batman["untagged"] == 1
        assert [f["number"] for f in batman["files"]] == ["1", "2", "5", "6"]
        assert batman["gap_runs"] == [(3, 4)] and batman["gaps"] == 2
        assert batman["tracked"] and batman["slug"] == "batman-v3-7"
        assert model["orphans"] == 1  # Mystery.cbz matches no series

    def test_creator_counts_are_what_you_get_after_ticking(self, library):
        from core.library_series import facet_values, get_model, parse_filters
        from werkzeug.datastructures import MultiDict
        model = get_model(None)
        state = {"read": set(), "progress": {}, "to_read": set()}
        f = parse_filters(MultiDict([("creator", "Tom King")]), owner=True)
        counts = {i["value"]: i["count"] for i in facet_values(model, f, state, "creators", limit=None)["items"]}
        assert counts["Mikel Janin"] == 1 and counts["Brian K. Vaughan"] == 0
        f = parse_filters(MultiDict([("creator", "Tom King"), ("creators_mode", "any")]), owner=True)
        counts = {i["value"]: i["count"] for i in facet_values(model, f, state, "creators", limit=None)["items"]}
        assert counts["Brian K. Vaughan"] == 1  # Any widens: Saga would join


# ---- /series ---------------------------------------------------------------

class TestSeriesPage:
    def test_lists_series_linking_to_their_issue_lists(self, client, library):
        body = _body(client, "/series")
        assert "/series/issues?name=Batman&amp;publisher=DC" in body
        assert "/series/issues?name=Saga&amp;publisher=Image" in body
        assert "4 issues · DC · 2016–2017" in body

    def test_owner_sees_what_to_fix(self, client, library):
        body = _body(client, "/series")
        assert "3 to fix" in body  # 1 untagged + 2 missing (tracked series)
        assert "series have untagged issues" in body and "issues belong to no series" in body

    def test_reader_sees_no_maintenance(self, client, library, reader):
        body = _body(client, "/series")
        assert "to fix" not in body and "belong to no series" not in body
        assert "facet-health" not in body

    def test_filters_narrow_and_report_chips(self, client, library):
        body = _body(client, "/series?publisher=Image")
        assert "name=Saga" in body and "name=Batman" not in body
        assert "Publisher" in body and "Clear all" in body

    def test_creators_all_by_default_any_on_request(self, client, library):
        body = _body(client, "/series?creator=Tom+King&creator=Brian+K.+Vaughan")
        assert "name=Saga" not in body and "name=Batman" not in body
        body = _body(client, "/series?creator=Tom+King&creator=Brian+K.+Vaughan&creators_mode=any")
        assert "name=Saga" in body and "name=Batman" in body

    def test_search_letter_and_no_match(self, client, library):
        assert "name=Saga" in _body(client, "/series?q=sag")
        assert "name=Saga" not in _body(client, "/series?letter=B")
        assert "No series match" in _body(client, "/series?q=zzz")

    def test_empty_library(self, client, db_connection):
        assert "No series yet" in _body(client, "/series")

    def test_bad_params_fall_back(self, client, library):
        assert "name=Batman" in _body(client, "/series?sort=nope&letter=%3F&page=x&decade=99s&per_page=7")

    def test_facet_values_api(self, client, library):
        d = client.get("/api/series/facet-values?group=creators&fq=king").get_json()
        assert d["success"] and [i["value"] for i in d["items"]] == ["Tom King"]
        assert d["items"][0]["href"].startswith("/series?")
        assert client.get("/api/series/facet-values?group=nope").status_code == 400

    def test_smart_collections_redirects_here(self, client):
        resp = client.get("/smart-collections")
        assert resp.status_code == 302 and resp.headers["Location"].endswith("/series")


# ---- /series/issues ----------------------------------------------------------

class TestIssueList:
    URL = "/series/issues?name=Batman&publisher=DC"

    def test_issues_in_order_with_a_gap_run(self, client, library):
        body = _body(client, self.URL)
        grid = body[body.index('id="issuesGrid"'):]
        assert grid.index("Batman #1,") < grid.index("Batman #2,") < grid.index("#3–#4") < grid.index("Batman #5,")
        assert "2 issues not in your library" in body
        assert "No XML" in body and "Tag 1 issue" in body

    def test_reader_sees_no_gaps_or_untagged(self, client, library, reader):
        body = _body(client, self.URL)
        assert "#3–#4" not in body and "No XML" not in body and "Tag 1 issue" not in body
        assert "/data/DC/Batman" not in body.split('data-matching=')[0]

    def test_number_search_jumps_and_explains_gaps(self, client, library):
        body = _body(client, self.URL + "&q=%232")
        assert "Enter opens #2." in body
        body = _body(client, self.URL + "&q=4")
        assert "is one of the gaps" in body and "#4 · not in your library" in body

    def test_shows_filter(self, client, library):
        body = _body(client, self.URL + "&show=untagged")
        assert "Batman 006.cbz" in body and "I Am Gotham" not in body

    def test_table_view(self, client, library):
        body = _body(client, self.URL + "&view=table")
        assert "<table" in body and "Untagged" in body

    def test_continue_points_at_the_first_unread(self, client, library, db_connection):
        db_connection.execute("INSERT INTO issues_read (issue_path, user_id) VALUES (?, 1)",
                              ("/data/DC/Batman/Batman 001.cbz",))
        db_connection.commit()
        body = _body(client, self.URL)
        assert "Read #2" in body

    def test_unknown_series_is_404(self, client, library):
        assert client.get("/series/issues?name=Nope&publisher=").status_code == 404


# ---- /comic/<id> -------------------------------------------------------------

class TestIssuePage:
    def _id(self, conn, name):
        return conn.execute("SELECT id FROM file_index WHERE name = ?", (name,)).fetchone()[0]

    def test_untagged_issue_offers_tagging(self, client, library):
        body = _body(client, f"/comic/{self._id(library, 'Batman 006.cbz')}")
        assert "Untagged: this file has no ComicInfo.xml" in body
        assert "Tag this issue" in body and "Add ComicInfo" in body
        assert "More from Batman" in body

    def test_reader_view_of_an_untagged_issue(self, client, library, reader):
        body = _body(client, f"/comic/{self._id(library, 'Batman 006.cbz')}")
        assert "hasn’t been tagged yet" in body and "Tag this issue" not in body
        assert "Want to Read" in body

    def test_prev_and_next_follow_the_run(self, client, library):
        body = _body(client, f"/comic/{self._id(library, 'Batman 002.cbz')}")
        prev_id, next_id = self._id(library, "Batman 001.cbz"), self._id(library, "Batman 005.cbz")
        assert f'data-prev="/comic/{prev_id}"' in body and f'data-next="/comic/{next_id}"' in body

    def test_by_path_redirects(self, client, library):
        resp = client.get("/comic/by-path?path=/data/Image/Saga/Saga 001.cbz")
        assert resp.status_code == 302 and "/comic/" in resp.headers["Location"]
        assert client.get("/comic/by-path?path=/nope.cbz").status_code == 404

    def test_unknown_issue_is_404(self, client, library):
        assert client.get("/comic/999999").status_code == 404


# ---- bulk read state ---------------------------------------------------------

class TestBulkRead:
    def test_marks_only_what_changes_and_undoes(self, client, library):
        paths = ["/data/DC/Batman/Batman 001.cbz", "/data/DC/Batman/Batman 002.cbz", "/nope.cbz"]
        d = client.post("/api/mark-comic-read/bulk", json={"paths": paths, "read": True}).get_json()
        assert d["success"] and sorted(d["changed"]) == sorted(paths[:2])
        d = client.post("/api/mark-comic-read/bulk", json={"paths": paths[:2], "read": True}).get_json()
        assert d["changed"] == []
        d = client.post("/api/mark-comic-read/bulk", json={"paths": paths[:1], "read": False}).get_json()
        assert d["changed"] == paths[:1]

    def test_rejects_bad_input(self, client, library):
        assert client.post("/api/mark-comic-read/bulk", json={"paths": []}).status_code == 400
        assert client.post("/api/mark-comic-read/bulk", json={"paths": "x"}).status_code == 400

    def test_a_reader_may_mark_their_own(self):
        from core.auth import _READER_WRITE_PREFIXES, path_matches_prefix
        assert path_matches_prefix("/api/mark-comic-read/bulk", _READER_WRITE_PREFIXES)


# ---- the CBZ Info modal's issue page link -------------------------------------

def test_cbz_info_links_to_the_issue_page():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    js = (root / "static/js/clu-cbz-info.js").read_text(encoding="utf-8")
    html = (root / "templates/partials/modal_cbz_info.html").read_text(encoding="utf-8")
    assert 'id="cbzIssuePageLink"' in html
    assert "_setIssueLink(data.issue_url)" in js and "_guardPendingEdits(function () { window.location.href = url; })" in js
    src = (root / "routes/metadata.py").read_text(encoding="utf-8")
    assert 'metadata["issue_url"] = _issue_page_url(file_path)' in src


# ---- a series spread over volume folders ----------------------------------------

class TestVolumeFolders:
    URL = "/series/issues?name=Batman&publisher=DC"

    @pytest.fixture
    def volumes(self, db_connection):
        for folder, year in (("Vol.2 - 2011", "2011"), ("Vol.1 - 1940", "1940")):
            for n in ("1", "3"):
                _file(db_connection, f"/data/DC/Batman/{folder}", f"Batman {n}.cbz",
                      ci_number=n, ci_year=year)
        return db_connection

    def test_issues_are_grouped_by_folder_in_natural_order(self, client, volumes):
        body = _body(client, self.URL)
        assert body.count('class="sp-group"') == 2
        assert body.index("Vol.1 - 1940") < body.index("Vol.2 - 2011")

    def test_no_gap_cards_across_merged_volumes(self, client, volumes):
        # #2 is "missing" only if the volumes are merged; per folder it is a gap too,
        # but the run is computed over the merged numbers, so it is not shown.
        assert "not in your library" not in _body(client, self.URL)

    def test_single_folder_series_has_no_headings(self, client, library):
        assert 'class="sp-group"' not in _body(client, "/series/issues?name=Batman&publisher=DC")
