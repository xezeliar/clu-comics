"""ComicInfo <Teams>, <Editor> and <Translator> reach file_index and the tag table,
and every credit in the CBZ info panel links to its page (docs/browse-hub.md)."""

import os
import re

from core.database import (
    add_file_index_entry,
    init_db,
    update_file_index_from_comicinfo,
    update_file_metadata,
)

XML = {"Series": "JLA", "Number": "1", "Teams": "Justice League [10], JSA",
       "Editor": "Mike Carlin", "Translator": "Ana Ruiz [3]"}


def _tags(conn, path):
    return sorted((r["kind"], r["value"]) for r in conn.execute(
        "SELECT kind, value FROM file_metadata_tags WHERE file_path = ?"
        " AND kind IN ('teams', 'editor', 'translator')", (path,)))


EXPECTED = [("editor", "Mike Carlin"), ("teams", "JSA"), ("teams", "Justice League"),
            ("translator", "Ana Ruiz")]


def test_comicinfo_write_indexes_teams_editor_translator(db_connection):
    path = "/data/DC/JLA/JLA 001.cbz"
    add_file_index_entry("JLA 001.cbz", path, "file", parent="/data/DC/JLA")
    assert update_file_index_from_comicinfo(path, XML)
    row = db_connection.execute(
        "SELECT ci_teams, ci_editor, ci_translator FROM file_index WHERE path = ?",
        (path,)).fetchone()
    assert tuple(row) == ("Justice League, JSA", "Mike Carlin", "Ana Ruiz")
    assert _tags(db_connection, path) == EXPECTED


def test_scanner_write_indexes_teams_editor_translator(db_connection):
    path = "/data/DC/JLA/JLA 002.cbz"
    add_file_index_entry("JLA 002.cbz", path, "file", parent="/data/DC/JLA")
    fid = db_connection.execute("SELECT id FROM file_index WHERE path = ?", (path,)).fetchone()[0]
    assert update_file_metadata(fid, {"ci_teams": XML["Teams"], "ci_editor": XML["Editor"],
                                      "ci_translator": XML["Translator"]}, 1.0, 1)
    assert _tags(db_connection, path) == EXPECTED


def test_files_scanned_before_teams_existed_are_backfilled_once(db_connection):
    # The main scan query skips has_comicinfo=1, so only the idle backfill can
    # re-read these (an empty Teams index otherwise).
    from core.database import get_files_needing_provider_backfill
    c = db_connection
    c.execute("INSERT INTO file_index (name, path, type, has_comicinfo, metadata_scanned_at,"
              " ci_provider) VALUES ('a.cbz', '/data/a.cbz', 'file', 1, 5, ''),"
              " ('b.cbz', '/data/b.cbz', 'file', 0, 5, '')")
    c.commit()
    assert [f["path"] for f in get_files_needing_provider_backfill()] == ["/data/a.cbz"]
    fid = c.execute("SELECT id FROM file_index WHERE path = '/data/a.cbz'").fetchone()[0]
    update_file_metadata(fid, {"ci_teams": "X-Men"}, 6.0, 1)
    assert get_files_needing_provider_backfill() == []


def test_every_credit_and_team_in_cbz_info_links():
    js = open(os.path.join(os.path.dirname(__file__), "..", "..",
                           "static", "js", "clu-cbz-info.js")).read()
    credits = js[js.index("title: 'Credits'"):js.index("title: 'Story'")]
    keys = re.findall(r"key: '(\w+)'.*?\}", credits)
    assert keys == ["Writer", "Penciller", "Inker", "Colorist", "Letterer",
                    "CoverArtist", "Editor", "Translator"]
    assert credits.count("browse: '") == len(keys)
    assert "{ key: 'Teams', label: 'Teams', browse: 'teams' }" in js
    assert "'/creators/' + encodeURIComponent(nm) + '?role=' + field.browse" in js
