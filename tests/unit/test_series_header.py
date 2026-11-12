"""Series page header: banner fallback, run strip vs ranges, creator ranking."""

from unittest.mock import patch

import pytest

from core import series_header
from core.creators import series_credits
from core.series_header import RUN_STRIP_MAX, banner_url, run_summary


class TestBannerFallback:
    """Series folder's own header art, then the publisher's, then none."""

    @staticmethod
    def _urls(have):
        return lambda path, kind: f"url:{path}" if (path, kind) in have else None

    def test_series_art_wins(self):
        have = {("/lib/DC/Batman", "header"), ("/lib/DC", "header")}
        with patch.object(series_header.folder_art, "art_url", self._urls(have)), \
             patch("helpers.library.is_library_root", return_value=False):
            assert banner_url("/lib/DC/Batman") == "url:/lib/DC/Batman"

    def test_falls_back_to_publisher_art(self):
        have = {("/lib/DC", "header")}
        with patch.object(series_header.folder_art, "art_url", self._urls(have)), \
             patch("helpers.library.is_library_root", return_value=False):
            assert banner_url("/lib/DC/Batman/") == "url:/lib/DC"

    def test_a_library_root_is_not_a_publisher(self):
        have = {("/lib", "header")}
        with patch.object(series_header.folder_art, "art_url", self._urls(have)), \
             patch("helpers.library.is_library_root", return_value=True):
            assert banner_url("/lib/Batman") is None

    def test_no_art_and_no_mapping_is_no_strip(self):
        with patch.object(series_header.folder_art, "art_url", return_value=None), \
             patch("helpers.library.is_library_root", return_value=False):
            assert banner_url("/lib/DC/Batman") is None
        assert banner_url(None) is None


class TestRunSummary:

    def test_cells_in_issue_order_with_states(self):
        run = run_summary(["3", "1", "2", "4"], found={"1", "3"}, missing={"2"})
        assert [c["number"] for c in run["cells"]] == ["1", "2", "3", "4"]
        assert [c["state"] for c in run["cells"]] == ["owned", "miss", "owned", "marked"]
        assert (run["total"], run["owned"], run["missing"], run["complete"]) == (4, 2, 1, False)

    def test_complete_when_nothing_is_missing(self):
        run = run_summary(["1", "2"], found={"1", "2"}, missing=set())
        assert run["complete"] is True

    def test_empty_run_is_not_complete(self):
        assert run_summary([], set(), set())["complete"] is False

    def test_strip_up_to_the_limit_then_ranges(self):
        nums = [str(n) for n in range(1, RUN_STRIP_MAX + 1)]
        assert len(run_summary(nums, set(nums), set())["cells"]) == RUN_STRIP_MAX
        nums.append(str(RUN_STRIP_MAX + 1))
        run = run_summary(nums, set(), set(nums))
        assert run["cells"] is None
        assert run["missing"] == RUN_STRIP_MAX + 1


def _file(conn, parent, name, **ci):
    cols = {"name": name, "path": f"{parent}/{name}", "type": "file", "size": 1,
            "parent": parent, "has_comicinfo": 1, **ci}
    conn.execute(
        f"INSERT INTO file_index ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        list(cols.values()))


@pytest.fixture
def series_folder(db_connection):
    from core.database import _backfill_file_metadata_tags
    folder = "/data/Image/Night Courier"
    for i in range(1, 10):
        _file(db_connection, folder, f"NC {i:03d}.cbz",
              ci_writer="Ines Varga" if i <= 6 else "Dan Ruiz",
              ci_penciller="Tomasz Okafor",
              ci_coverartist="Mei-Lin Oduya, Sana Hale" if i <= 2 else
              ("Mei-Lin Oduya" if i <= 7 else "Sana Hale"),
              ci_colorist="Third Person" if i == 1 else None,
              ci_inker="Piet Lindqvist" if i == 1 else None)
    # Owned but untagged, and a file in another folder that must not count.
    _file(db_connection, folder, "NC 010.cbz", has_comicinfo=0)
    _file(db_connection, "/data/Image/Other", "O 001.cbz", ci_writer="Ines Varga")
    db_connection.commit()
    _backfill_file_metadata_tags(db_connection)
    db_connection.commit()
    return folder


class TestSeriesCredits:

    def test_counts_and_coverage(self, series_folder):
        c = series_credits(series_folder, prefixes=["/data"])
        assert (c["issues"], c["credited"]) == (10, 9)

    def test_header_roles_top_two_ranked_by_issue_count(self, series_folder):
        c = series_credits(series_folder + "/", prefixes=["/data"], top=2)
        header = {r["kind"]: r["people"] for r in c["header"]}
        assert list(header) == ["writer", "penciller", "coverartist"]
        assert [(p["name"], p["count"]) for p in header["writer"]] == [
            ("Ines Varga", 6), ("Dan Ruiz", 3)]
        assert [(p["name"], p["count"]) for p in header["coverartist"]] == [
            ("Mei-Lin Oduya", 7), ("Sana Hale", 4)]

    def test_count_hidden_for_someone_on_every_issue(self, series_folder):
        c = series_credits(series_folder, prefixes=["/data"])
        pen = next(r for r in c["header"] if r["kind"] == "penciller")["people"]
        assert pen == [{"name": "Tomasz Okafor", "count": 9, "show_count": False}]

    def test_all_credits_lists_every_stored_role(self, series_folder):
        c = series_credits(series_folder, prefixes=["/data"])
        assert [r["kind"] for r in c["roles"]] == [
            "writer", "penciller", "inker", "colorist", "coverartist"]
        assert c["roles"][0]["label"] == "Writer"

    def test_scope_outside_the_folder_sees_nothing(self, series_folder):
        c = series_credits(series_folder, prefixes=["/elsewhere"])
        assert (c["issues"], c["credited"], c["roles"]) == (0, 0, [])
