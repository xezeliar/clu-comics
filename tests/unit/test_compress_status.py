"""core/compress_status.py -- which comics are being compressed right now.

The monitor (auto-compress) and the web worker are separate processes, so the
state is a marker file per running compress, trusted only while its writer lives.
"""
import json
import os
import subprocess
import sys

import pytest

from core import compress_status


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setattr(compress_status, "get_config_dir", lambda: str(cfg))
    return cfg


class TestMarkers:

    def test_begin_marks_and_end_clears(self, tmp_path):
        comic = str(tmp_path / "A 001.cbz")
        assert not compress_status.is_compressing(comic)
        compress_status.begin(comic)
        assert compress_status.is_compressing(comic)
        compress_status.end(comic)
        assert not compress_status.is_compressing(comic)

    def test_end_without_begin_is_harmless(self, tmp_path):
        compress_status.end(str(tmp_path / "never.cbz"))

    def test_path_is_normalised(self, tmp_path):
        comic = str(tmp_path / "x" / ".." / "A 001.cbz")
        compress_status.begin(comic)
        assert compress_status.is_compressing(str(tmp_path / "A 001.cbz"))

    def test_other_comic_is_not_marked(self, tmp_path):
        compress_status.begin(str(tmp_path / "A 001.cbz"))
        assert not compress_status.is_compressing(str(tmp_path / "A 002.cbz"))


class TestBusy:

    def test_folder_holding_a_compressing_comic_is_busy(self, tmp_path):
        compress_status.begin(str(tmp_path / "Series" / "A 001.cbz"))
        assert compress_status.is_busy(str(tmp_path / "Series"))
        assert compress_status.is_busy(str(tmp_path / "Series" / "A 001.cbz"))

    def test_sibling_with_a_shared_prefix_is_not_busy(self, tmp_path):
        compress_status.begin(str(tmp_path / "Series" / "A 001.cbz"))
        assert not compress_status.is_busy(str(tmp_path / "Series 2"))


class TestStaleMarkers:

    def _write(self, config_dir, path, pid, started):
        d = config_dir / "compressing"
        d.mkdir(exist_ok=True)
        marker = d / "stale.json"
        marker.write_text(json.dumps({"path": path, "pid": pid, "started": started}))
        return marker

    def test_dead_pid_is_ignored_and_removed(self, config_dir, tmp_path):
        # A pid that has just exited cannot be alive.
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        import time
        comic = str(tmp_path / "A 001.cbz")
        marker = self._write(config_dir, comic, proc.pid, time.time())
        assert not compress_status.is_compressing(comic)
        assert not marker.exists()

    def test_expired_marker_is_ignored_even_with_a_live_pid(self, config_dir, tmp_path):
        import time
        comic = str(tmp_path / "A 001.cbz")
        marker = self._write(config_dir, comic, os.getpid(),
                             time.time() - compress_status.MAX_MARKER_AGE - 5)
        assert not compress_status.is_compressing(comic)
        assert not marker.exists()

    def test_corrupt_marker_is_dropped(self, config_dir):
        d = config_dir / "compressing"
        d.mkdir()
        (d / "bad.json").write_text("{not json")
        assert compress_status.compressing_paths() == set()
        assert not (d / "bad.json").exists()


class TestAnnotateFiles:

    def test_flags_only_the_compressing_file_and_leaves_the_cache_alone(self, tmp_path):
        directory = str(tmp_path)
        files = [{"name": "A 001.cbz", "size": 1}, {"name": "A 002.cbz", "size": 2}]
        compress_status.begin(str(tmp_path / "A 001.cbz"))

        out = compress_status.annotate_files(directory, files)

        assert out[0]["compressing"] is True
        assert "compressing" not in out[1]
        assert "compressing" not in files[0]  # the cached listing is not mutated

    def test_returns_input_untouched_when_nothing_is_compressing(self, tmp_path):
        files = [{"name": "A 001.cbz", "size": 1}]
        assert compress_status.annotate_files(str(tmp_path), files) is files

    def test_never_raises_on_a_missing_marker_dir(self, tmp_path):
        assert compress_status.compressing_paths() == set()


class TestBothListingRoutesAreAnnotated:
    """The File Manager lists TARGET through /list-downloads (the Downloads button)
    and a library folder through /list-directories. app.py cannot be imported in
    tests, so assert structurally that neither returns the raw cached files."""

    def _body(self, fn):
        import pathlib
        import re
        src = (pathlib.Path(__file__).resolve().parents[2] / "routes" / "collection.py").read_text()
        start = src.index(f"def {fn}(")
        return src[start:src.index("\n@collection_bp.route", start)]

    @pytest.mark.parametrize("fn", ["list_directories", "list_downloads"])
    def test_files_go_through_annotate(self, fn):
        body = self._body(fn)
        assert body.count("compress_status.annotate_files(") == 2  # cached and fresh
        assert '"files": cached_data["files"]' not in body
        assert '"files": listing_data["files"]' not in body
