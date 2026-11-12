"""The "New issue arrived" badge: an arrival is a file's first_indexed_at,
compared with each user's last visit to the folder (series_visits).

Set by anything that indexes a new comic (a download filed into a library, a
WATCH move the file watcher indexes, a scan); NOT by a rename, a conversion, a
metadata write, a folder rescan or a full rebuild.
"""
import os
import shutil
import subprocess
import time
from unittest.mock import patch

import pytest

SERIES = "/data/Image/Saga"


def _tick():
    # Arrival and visit times are compared as floats; keep them distinct.
    time.sleep(0.01)


def _add(name, parent=SERIES, **kw):
    from core.database import add_file_index_entry
    return add_file_index_entry(name, f"{parent}/{name}", "file", size=1,
                                parent=parent, **kw)


def _count(user_id=None, folder=SERIES):
    from core.database import get_new_arrival_counts
    return get_new_arrival_counts([folder], user_id=user_id).get(folder, 0)


def db_backdate_users():
    """users.created_at has second resolution; put it behind the arrivals."""
    from core.database import db_conn
    with db_conn() as conn:
        conn.execute("UPDATE users SET created_at = '2000-01-01 00:00:00'")
        conn.commit()


def _user(name):
    from core.database import create_user
    return create_user(name, role="reader")


@pytest.fixture
def owner(db_connection):
    """Single-user installs resolve to the owner (or 1); pin one id."""
    _tick()
    return 1


class TestSetOnArrival:
    def test_a_newly_indexed_comic_is_new(self, owner):
        _add("Saga 001.cbz")
        _add("Saga 002.cbr")
        _add("cover.jpg")  # not a comic
        assert _count(owner) == 2

    def test_nothing_indexed_before_the_epoch_is_new(self, db_connection, owner):
        _add("Saga 001.cbz")
        db_connection.execute("UPDATE file_index SET first_indexed_at = 1")
        db_connection.commit()
        assert _count(owner) == 0

    def test_a_scan_that_finds_a_new_issue_sets_it(self, owner):
        from core.database import sync_file_index_incremental
        _add("Saga 001.cbz")
        from core.database import mark_series_visited
        mark_series_visited(SERIES, user_id=owner)
        _tick()
        entries = [
            {"name": n, "path": f"{SERIES}/{n}", "type": "file", "size": 1,
             "parent": SERIES}
            for n in ("Saga 001.cbz", "Saga 002.cbz")
        ]
        sync_file_index_incremental(entries, walked_roots=["/data"])
        assert _count(owner) == 1


class TestNotSetWithoutAnArrival:
    @pytest.fixture
    def visited(self, owner):
        from core.database import mark_series_visited
        _add("Saga 001.cbr")
        mark_series_visited(SERIES, user_id=owner)
        _tick()
        assert _count(owner) == 0
        return owner

    def test_rename_keeps_the_arrival_time(self, visited):
        from core.database import move_indexed_path
        move_indexed_path(f"{SERIES}/Saga 001.cbr", f"{SERIES}/Saga #1.cbr", is_dir=False)
        assert _count(visited) == 0

    def test_metadata_write_upserts_the_same_row(self, visited):
        _add("Saga 001.cbr")  # what the watcher does after a ComicInfo write
        assert _count(visited) == 0

    def test_conversion_carries_the_arrival_time(self, visited, tmp_path):
        from core.database import add_file_index_entry
        from cbz_ops.single_file import convert_to_cbz
        cbr = tmp_path / "Saga 001.cbr"
        cbr.write_bytes(b"rar")
        folder = str(tmp_path)
        add_file_index_entry(cbr.name, str(cbr), "file", size=3, parent=folder)
        from core.database import mark_series_visited
        mark_series_visited(folder, user_id=visited)
        _tick()
        # The file watcher can index the new .cbz first, with "now".
        add_file_index_entry("Saga 001.cbz", str(tmp_path / "Saga 001.cbz"),
                             "file", size=3, parent=folder)

        def ok(rar_path, cbz_path, temp_dir, problem_source=None):
            with open(cbz_path, "wb") as f:
                f.write(b"cbz")
            return True

        with patch("cbz_ops.single_file.convert_single_rar_file", side_effect=ok):
            assert convert_to_cbz(str(cbr)) is True
        assert _count(visited, folder) == 0

    def test_full_rebuild_keeps_known_times(self, visited):
        from core.database import save_file_index_to_db
        save_file_index_to_db([{"name": "Saga 001.cbr", "path": f"{SERIES}/Saga 001.cbr",
                                "type": "file", "parent": SERIES}])
        assert _count(visited) == 0

    def test_first_build_moves_the_epoch(self, db_connection, owner):
        from core.database import save_file_index_to_db
        db_connection.execute("DELETE FROM file_index")
        db_connection.commit()
        save_file_index_to_db([{"name": "Saga 001.cbz", "path": f"{SERIES}/Saga 001.cbz",
                                "type": "file", "parent": SERIES}])
        assert _count(owner) == 0

    def test_rescan_keeps_known_times(self, visited):
        """The /api/scan-directory body: snapshot, delete subtree, re-add."""
        from core.database import (
            delete_file_index_entry, get_first_indexed_times, add_file_index_entry,
        )
        path = f"{SERIES}/Saga 001.cbr"
        arrived = get_first_indexed_times(SERIES)
        delete_file_index_entry(SERIES)
        add_file_index_entry("Saga 001.cbr", path, "file", parent=SERIES,
                             first_indexed_at=arrived.get(path))
        assert _count(visited) == 0


class TestPerUserClear:
    def test_visit_clears_only_that_user(self, owner):
        from core.database import mark_series_visited
        alice, bob = _user("alice"), _user("bob")
        assert alice != bob
        db_backdate_users()
        _add("Saga 001.cbz")
        assert _count(alice) == 1 and _count(bob) == 1
        mark_series_visited(SERIES, user_id=alice)
        assert _count(alice) == 0
        assert _count(bob) == 1

    def test_a_user_is_not_shown_what_arrived_before_they_existed(self, owner):
        _add("Saga 001.cbz")
        _tick()
        time.sleep(1)  # users.created_at has second resolution
        reader = _user("latecomer")
        assert _count(reader) == 0

    def test_arrivals_survive_the_clear_for_the_series_page(self, owner):
        from core.database import mark_series_visited
        _add("Saga 001.cbz")
        mark_series_visited(SERIES, user_id=owner)
        _tick()
        _add("Saga 002.cbz")
        _add("Saga 003.cbz")
        arrived = mark_series_visited(SERIES, user_id=owner)
        assert arrived == [f"{SERIES}/Saga 002.cbz", f"{SERIES}/Saga 003.cbz"]
        assert _count(owner) == 0
        # A reload still shows the same batch until more arrive.
        assert mark_series_visited(SERIES, user_id=owner) == arrived

    def test_visit_follows_a_folder_rename(self, owner):
        from core.database import mark_series_visited, move_indexed_path
        _add("Saga 001.cbz")
        mark_series_visited(SERIES, user_id=owner)
        move_indexed_path(SERIES, "/data/Image/Saga (2012)", is_dir=True)
        assert _count(owner, "/data/Image/Saga (2012)") == 0


class TestPullListFilter:
    def test_new_arrivals_status_and_count(self, owner):
        from tests.factories.db_factories import create_series
        from core.database import get_pull_list_page, get_pull_list_facets
        create_series(series_id=1, name="Saga", mapped_path=SERIES)
        create_series(series_id=2, name="Paper Girls", mapped_path="/data/Image/Paper Girls")
        _add("Saga 001.cbz")
        assert get_pull_list_facets()["new_arrivals"] == 1
        rows = get_pull_list_page("2026-01-01", status="new")["rows"]
        assert [r["id"] for r in rows] == [1]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_sticker_wording():
    js = os.path.join(os.path.dirname(__file__), "..", "..", "static", "js", "collection.js")
    src = open(js, encoding="utf-8").read()
    start = src.index("function newIssuesLabel")
    body = src[start:src.index("\n}\n", start) + 3]
    out = subprocess.run(
        ["node", "-e", body + "console.log([1,2,9,10,42].map(newIssuesLabel).join('|'))"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "New|2 new|9 new|9+ new|9+ new"
