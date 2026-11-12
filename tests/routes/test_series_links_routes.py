"""Series page links from the Library, Creators/Characters and Smart collections.

A folder is a series once a ``series`` row's ``mapped_path`` names it; each page
links to ``/series/<slug>`` only for such folders.
"""
import os
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, quote, urlsplit

import pytest


def _series(conn, sid, name, volume, path):
    conn.execute("INSERT INTO series (id, name, volume, mapped_path) VALUES (?, ?, ?, ?)",
                 (sid, name, volume, path))
    conn.commit()


def _file(conn, parent, name, **ci):
    cols = {"name": name, "path": f"{parent}/{name}", "type": "file", "size": 1,
            "parent": parent, "has_comicinfo": 1, "ci_publisher": "DC",
            "ci_series": "Batman", "ci_number": "1", "ci_year": "2020",
            "ci_writer": "Tom King", "first_indexed_at": time.time()}
    cols.update(ci)
    conn.execute(f"INSERT INTO file_index ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 list(cols.values()))
    conn.commit()


class TestSlugLookup:
    def test_only_mapped_folders_and_lowest_id_wins(self, db_connection):
        from core.database import get_series_slugs_for_folders
        _series(db_connection, 20, "Batman", 3, "/data/DC/Batman")
        _series(db_connection, 10, "Batman", 2, "/data/DC/Batman")
        _series(db_connection, 30, "Saga", None, "/data/Image/Saga")
        got = get_series_slugs_for_folders(
            ["/data/DC/Batman", "/data/Image/Saga", "/data/None", "", "/data/DC/Batman"])
        assert got == {"/data/DC/Batman": "batman-v2-10", "/data/Image/Saga": "saga-30"}

    def test_empty_input(self, db_connection):
        from core.database import get_series_slugs_for_folders
        assert get_series_slugs_for_folders([]) == {}


class TestBrowse:
    @patch("routes.collection.get_directory_children")
    def test_mapped_folder_carries_series_url(self, mock_children, client, db_connection, tmp_path):
        root = str(tmp_path / "data")
        os.makedirs(root, exist_ok=True)
        mapped, plain = os.path.join(root, "Batman"), os.path.join(root, "Other")
        _series(db_connection, 7, "Batman", 1, mapped)
        mock_children.return_value = (
            [{"name": "Batman", "path": mapped, "has_thumbnail": False},
             {"name": "Other", "path": plain, "has_thumbnail": False}], [])
        with patch.dict("sys.modules", {"app": MagicMock(DATA_DIR=root)}):
            dirs = client.get(f"/api/browse?path={root}").get_json()["directories"]
        by_name = {d["name"]: d for d in dirs}
        assert by_name["Batman"]["series_url"] == "/series/batman-v1-7"
        assert "series_url" not in by_name["Other"]

    @patch("routes.collection.get_directory_children")
    def test_sidecar_folder_carries_resolve_url(self, mock_children, client, db_connection, tmp_path):
        root = str(tmp_path / "data")
        sidecar, plain = os.path.join(root, "Saga"), os.path.join(root, "Other")
        os.makedirs(sidecar)
        os.makedirs(plain)
        open(os.path.join(sidecar, "cvinfo"), "w").close()
        mock_children.return_value = (
            [{"name": "Saga", "path": sidecar, "has_thumbnail": False},
             {"name": "Other", "path": plain, "has_thumbnail": False}], [])
        with patch.dict("sys.modules", {"app": MagicMock(DATA_DIR=root)}):
            dirs = client.get(f"/api/browse?path={root}").get_json()["directories"]
        by_name = {d["name"]: d for d in dirs}
        url = urlsplit(by_name["Saga"]["series_resolve_url"])
        assert url.path == "/api/series/for-folder" and parse_qs(url.query)["path"] == [sidecar]
        assert "series_resolve_url" not in by_name["Other"]


class TestSeriesForFolder:
    @pytest.fixture
    def folder(self, tmp_path):
        d = tmp_path / "Saga"
        d.mkdir()
        with patch("helpers.library.is_valid_library_path", return_value=True):
            yield str(d)

    def _get(self, client, path, ident):
        with patch("models.library_automap._resolve_identity", return_value=ident), \
             patch("routes.series.metron.get_flask_api", return_value=None), \
             patch("models.comicvine_source.is_available", return_value=False):
            return client.get("/api/series/for-folder?path=" + quote(path))

    def test_mapped_folder_uses_its_series(self, client, db_connection, folder):
        _series(db_connection, 7, "Saga", 1, folder)
        assert self._get(client, folder, None).get_json()["url"] == "/series/saga-v1-7"

    def test_sidecar_metron_id(self, client, folder):
        d = self._get(client, folder, {"metron_id": 42, "series_name": "Saga"}).get_json()
        assert d == {"success": True, "url": "/series/saga-42"}

    def test_unresolvable_sidecar_reports_why(self, client, folder):
        d = self._get(client, folder, {"metron_id": None, "reason": "no id"}).get_json()
        assert d == {"success": False, "error": "no id"}

    def test_comicvine_only_needs_pull_list(self, client, folder):
        from helpers.comicvine_ids import make_comicvine_series_id
        d = self._get(client, folder, {"metron_id": make_comicvine_series_id(5), "series_name": "Saga"}).get_json()
        assert d["success"] is False and "Pull List" in d["error"]

    def test_outside_library_is_404(self, client, tmp_path):
        with patch("helpers.library.is_valid_library_path", return_value=False):
            assert client.get("/api/series/for-folder?path=" + quote(str(tmp_path))).status_code == 404


class TestCreatorIssues:
    @pytest.fixture
    def library(self, db_connection):
        from core.database import _backfill_file_metadata_tags
        _file(db_connection, "/data/DC/Batman", "B1.cbz")
        _file(db_connection, "/data/DC/Other", "O1.cbz", ci_series="Other")
        _backfill_file_metadata_tags(db_connection)
        _series(db_connection, 7, "Batman", 1, "/data/DC/Batman")
        return db_connection

    def test_mapped_folder_returns_series_href(self, client, library):
        d = client.get("/api/creators/Tom%20King/issues?folder=" + quote("/data/DC/Batman")).get_json()
        assert d["series_href"] == "/series/batman-v1-7"

    def test_unmapped_folder_has_none(self, client, library):
        d = client.get("/api/creators/Tom%20King/issues?folder=" + quote("/data/DC/Other")).get_json()
        assert d["series_href"] is None

    def test_panel_shows_the_link(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "person.html")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        assert "if (d.series_href)" in body and "'Series page'" in body


class TestSmartCollectionReader:
    def test_cards_open_the_reader(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "smart_collections.html")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        assert "partials/reader_modal.html" in body
        assert "js/reader.js" in body
        assert "window.openComicReader(it.path)" in body


class TestSmartCollectionIssues:
    def test_items_carry_series_url(self, client, db_connection):
        from core.database import _backfill_file_metadata_tags
        _file(db_connection, "/data/DC/Batman", "B1.cbz")
        _file(db_connection, "/data/DC/Other", "O1.cbz", ci_series="Other")
        _backfill_file_metadata_tags(db_connection)
        _series(db_connection, 7, "Batman", 1, "/data/DC/Batman")
        # Results are confined to the library roots.
        with patch("helpers.library.get_library_roots", return_value=["/data"]):
            cid = client.post("/api/smart-collections", json={
                "name": "C", "match": "all", "sort": "alpha",
                "rules": [{"field": "publisher", "op": "is", "value": "dc"}]}).get_json()["collection"]["id"]
            items = client.get(f"/api/smart-collections/{cid}/issues").get_json()["items"]
        by_path = {i["path"]: i["series_url"] for i in items}
        assert by_path == {"/data/DC/Batman/B1.cbz": "/series/batman-v1-7",
                           "/data/DC/Other/O1.cbz": None}
