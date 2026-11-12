"""Series page links from the Library, Creators/Characters and Smart collections.

A folder is a series once a ``series`` row's ``mapped_path`` names it; each page
links to ``/series/<slug>`` only for such folders.
"""
import os
import time
from unittest.mock import MagicMock, patch
from urllib.parse import quote

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
