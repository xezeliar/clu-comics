"""A comic that Auto-Compress is rewriting must not be filed away mid-rewrite.

The reported sequence: a subscribed issue is downloaded, lands in TARGET, shows
the Compressing badge, and is moved into its series folder before the compress
finishes -- so the filed copy keeps its original size.

Why it happened: api.py waits for WATCH to be empty and then runs
process_incoming_wanted_issues, which files TARGET into the library. WATCH is
empty the instant the monitor *moves* the file into TARGET, but the compress
runs after that. The compress refuses to write a file that was moved while it
worked (by design), so it quietly gave up.

Three things close it, and all three are needed:

* the monitor claims the destination BEFORE the move (not when the compress
  starts), so there is no window in which WATCH is empty and nothing is claimed;
* api.py waits for the claim to clear before it runs the filing pass;
* the TARGET collector never offers a claimed file to the matcher, whichever
  route started the pass (the Scan Downloads button runs it inline).

monitor.py and api.py cannot be imported in tests, so those two are asserted
structurally, as test_wanted_scan_target_guard.py does for app.py.
"""
import os
import pathlib

import pytest

from core import compress_status
from helpers.collection import collect_target_candidates

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _touch(path, data=b"stub"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _names(files):
    return sorted(name for name, _ in files)


@pytest.fixture(autouse=True)
def isolated_markers(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setattr(compress_status, "get_config_dir", lambda: str(cfg))
    monkeypatch.setattr("helpers.library.get_library_roots", lambda: [])


class TestCollectorLeavesACompressingComicAlone:

    def test_a_compressing_comic_is_not_a_candidate(self, tmp_path):
        target = tmp_path / "processed"
        busy = _touch(str(target / "Avengers 036 (2026).cbz"))
        _touch(str(target / "Thor 001 (2026).cbz"))
        compress_status.begin(busy)

        files, _ = collect_target_candidates(str(target), mapped_dirs=[])

        assert _names(files) == ["Thor 001 (2026).cbz"]

    def test_it_is_offered_again_once_the_compress_is_done(self, tmp_path):
        """Deferred, not forgotten: the next pass must pick it up."""
        target = tmp_path / "processed"
        busy = _touch(str(target / "Avengers 036 (2026).cbz"))
        compress_status.begin(busy)
        assert collect_target_candidates(str(target), mapped_dirs=[])[0] == []

        compress_status.end(busy)

        assert _names(collect_target_candidates(str(target), mapped_dirs=[])[0]) == [
            "Avengers 036 (2026).cbz"]

    def test_a_comic_inside_a_wrapper_folder_is_deferred_too(self, tmp_path):
        target = tmp_path / "processed"
        busy = _touch(str(target / "Release" / "Avengers 036 (2026).cbz"))
        compress_status.begin(busy)
        assert collect_target_candidates(str(target), mapped_dirs=[])[0] == []

    def test_another_comics_marker_changes_nothing(self, tmp_path):
        target = tmp_path / "processed"
        _touch(str(target / "Thor 001 (2026).cbz"))
        compress_status.begin(str(tmp_path / "elsewhere" / "Other 001.cbz"))
        assert _names(collect_target_candidates(str(target), mapped_dirs=[])[0]) == [
            "Thor 001 (2026).cbz"]

    def test_markers_are_read_once_per_scan_not_once_per_file(self, tmp_path, monkeypatch):
        target = tmp_path / "processed"
        for i in range(20):
            _touch(str(target / f"Book {i:03d} (2026).cbz"))
        calls = []
        real = compress_status.compressing_paths
        monkeypatch.setattr(compress_status, "compressing_paths",
                            lambda: calls.append(1) or real())
        collect_target_candidates(str(target), mapped_dirs=[])
        assert len(calls) == 1


@pytest.fixture(scope="module")
def monitor_move_file():
    src = (ROOT / "monitor.py").read_text(encoding="utf-8")
    body = src.split("    def _move_file(self, filepath):")[1]
    return body.split("\n    def ")[0]


class TestMonitorClaimsBeforeTheMove:

    def test_claim_is_taken_before_the_file_is_moved(self, monitor_move_file):
        claim = monitor_move_file.index("compress_status.begin(target_path)")
        move = monitor_move_file.index("move_download(filepath, target_path)")
        assert claim < move

    def test_claim_is_only_taken_when_auto_compress_is_on(self, monitor_move_file):
        claim = monitor_move_file.index("compress_status.begin(target_path)")
        assert "if self.auto_compress:" in monitor_move_file[claim - 80:claim]

    def test_a_converted_cbz_is_claimed_before_the_compress(self, monitor_move_file):
        final = monitor_move_file.index("compress_status.begin(final_target_path)")
        compress = monitor_move_file.index("auto_compress(final_target_path, monitor_logger)")
        assert final < compress
        assert "final_target_path != target_path" in monitor_move_file[final - 160:final]

    def test_every_claim_is_released_after_the_try_block(self, monitor_move_file):
        """After the except, so a failed move or a failed compress cannot leave
        a comic stuck as 'compressing' (the pid check is only the backstop)."""
        release = monitor_move_file.index("for path in claimed:")
        assert "compress_status.end(path)" in monitor_move_file[release:release + 120]
        assert monitor_move_file.index("moved = False") < release
        assert release < monitor_move_file.index("source_folder = os.path.dirname(filepath)")

    def test_claimed_is_defined_before_the_try(self, monitor_move_file):
        assert monitor_move_file.index("claimed = []") < monitor_move_file.index(
            "os.makedirs(os.path.dirname(target_path), exist_ok=True)")


class TestApiWaitsForTheCompress:

    @pytest.fixture(scope="class")
    def waiter(self):
        src = (ROOT / "api.py").read_text(encoding="utf-8")
        body = src.split("def check_wanted_after_watch_empty():")[1]
        return body.split("threading.Thread(target=check_wanted_after_watch_empty")[0]

    def test_filing_pass_waits_while_target_is_compressing(self, waiter):
        empty = waiter.index("if total == 0:")
        busy = waiter.index("compress_status.is_busy(target_dir)")
        run = waiter.index("process_incoming_wanted_issues()")
        assert empty < busy < run
        assert "continue" in waiter[busy:run]

    def test_it_asks_about_the_target_folder(self, waiter):
        assert 'target_dir = get_target_dir() or "/downloads/processed"' in waiter
