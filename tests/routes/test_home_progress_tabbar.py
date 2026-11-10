"""Home shelves, cover progress marks and the phone tab bar."""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


def _recent(name, days_ago):
    added = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    return {"file_name": name, "file_path": f"/data/S/{name}", "added_at": added}


class TestNewThisWeek:
    def test_only_unread_files_from_last_seven_days(self, client):
        files = [_recent("new.cbz", 1), _recent("read.cbz", 2), _recent("old.cbz", 30)]
        with patch("routes.collection.get_recent_files", return_value=files), \
                patch("core.database.get_issues_read",
                      return_value=[{"issue_path": "/data/S/read.cbz"}]):
            data = client.get("/api/new-this-week").get_json()
        assert [f["file_name"] for f in data["files"]] == ["new.cbz"]

    def test_empty(self, client):
        with patch("routes.collection.get_recent_files", return_value=[]):
            data = client.get("/api/new-this-week").get_json()
        assert data == {"success": True, "files": [], "total_count": 0}


class TestReadingProgress:
    def test_only_partly_read_comics(self, client):
        positions = [
            {"comic_path": "/a.cbz", "page_number": 11, "total_pages": 22},
            {"comic_path": "/done.cbz", "page_number": 21, "total_pages": 22},
            {"comic_path": "/nototal.cbz", "page_number": 5, "total_pages": None},
        ]
        with patch("core.database.get_all_reading_positions", return_value=positions):
            data = client.get("/api/reading-progress").get_json()
        assert data == {"progress": {"/a.cbz": 50}}


class TestFolderReadProgress:
    def test_counts_read_over_owned(self, client, db_connection):
        from tests.factories.db_factories import create_file_index_entry, create_issue_read
        for n in (1, 2, 3):
            create_file_index_entry(path=f"/data/Series_%/{n}.cbz", parent="/data/Series_%")
        create_file_index_entry(path="/data/Series_%x/1.cbz", parent="/data/Series_%x")
        create_issue_read(issue_path="/data/Series_%/1.cbz")
        create_issue_read(issue_path="/data/Series_%x/1.cbz")
        resp = client.post("/api/folder-read-progress",
                           json={"paths": ["/data/Series_%", "/data/Empty"]})
        assert resp.get_json()["progress"] == {
            "/data/Series_%": {"read": 1, "total": 3},
            "/data/Empty": {"read": 0, "total": 0},
        }

    @pytest.mark.parametrize("body", [{}, {"paths": "x"}, {"paths": [1]}])
    def test_rejects_bad_payload(self, client, body):
        assert client.post("/api/folder-read-progress", json=body).status_code == 400


class TestHomeShelves:
    def test_new_this_week_is_a_default_shelf(self, client):
        html = client.get("/collection").get_data(as_text=True)
        assert 'id="newThisWeekSwiper"' in html
        assert html.index("continueReadingSwiper") < html.index("newThisWeekSwiper") \
            < html.index("onTheStackSwiper")

    def test_every_shelf_can_be_hidden_when_empty(self):
        from routes.collection import DASHBOARD_SECTION_DEFS
        for sid, d in DASHBOARD_SECTION_DEFS.items():
            if d.get("swiper_id"):
                assert d.get("section_html_id"), sid
                assert d.get("view_all_text"), sid

    def test_js_hides_empty_shelves_and_marks_covers(self):
        js = open("static/js/collection.js", encoding="utf-8").read()
        assert js.count("hideEmptyShelf(swiper)") >= 6
        assert "No recently added files" not in js
        assert js.count("CLU.progress.apply(") >= 3
        assert "CLU.progress.markRead(path)" in js


class TestTabBar:
    def test_rendered_with_five_tabs_for_owner(self, client):
        html = client.get("/collection").get_data(as_text=True)
        nav = html[html.index('class="clu-tabbar"'):]
        nav = nav[:nav.index("</nav>")]
        for label in ("Home", "Library", "Reading", "Settings"):
            assert f"<span>{label}</span>" in nav
        # /collection is the Home page's browse view, so Home is the active tab
        assert '<a href="/" class="active" aria-current="page">' in nav

    def test_viewport_covers_the_safe_area(self, client):
        assert "viewport-fit=cover" in client.get("/collection").get_data(as_text=True)

    def test_css_phone_only_safe_area_and_reader_hidden(self):
        css = open("static/css/clu-page.css", encoding="utf-8").read()
        block = css[css.index(".clu-tabbar { display: none; }"):]
        assert "max-width: 767.98px" in block
        assert "env(safe-area-inset-bottom" in block
        assert "#comicReaderModal" in block
