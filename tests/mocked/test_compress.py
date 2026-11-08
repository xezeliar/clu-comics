"""Tests for cbz_ops/compress.py -- shrink a CBZ's page images."""
import io
import os
import zipfile
from unittest.mock import patch

import pytest
from PIL import Image

COMICINFO = b"<?xml version='1.0'?><ComicInfo><Series>Test</Series></ComicInfo>"


def _png(width, height):
    """A gradient page: compresses far better as WebP than as PNG."""
    img = Image.linear_gradient("L").resize((width, height)).convert("RGB")
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def big_cbz(tmp_path):
    path = tmp_path / "Series 001.cbz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ComicInfo.xml", COMICINFO)
        zf.writestr("001.png", _png(1000, 3000))
        zf.writestr("002.png", _png(1000, 1500))
        zf.writestr("003.png", _png(2000, 1500))
    return path


@pytest.fixture(autouse=True)
def no_thumbnail_cache():
    with patch("core.thumbnail_cache.regenerate_thumbnail"):
        yield


class TestCompressCbz:

    def test_shrinks_and_converts_pages(self, big_cbz):
        from cbz_ops.compress import compress_cbz, MAX_PAGE_HEIGHT

        old, new = compress_cbz(str(big_cbz))

        assert new < old
        assert os.path.getsize(big_cbz) == new
        with zipfile.ZipFile(big_cbz) as zf:
            names = zf.namelist()
            # Same order, same stems; pages now WebP.
            assert names == ["ComicInfo.xml", "001.webp", "002.webp", "003.webp"]
            assert zf.read("ComicInfo.xml") == COMICINFO
            with Image.open(io.BytesIO(zf.read("001.webp"))) as img:
                assert img.format == "WEBP"
                assert img.size == (800, MAX_PAGE_HEIGHT)
            # Pages under the cap keep their size, spreads included.
            with Image.open(io.BytesIO(zf.read("003.webp"))) as img:
                assert img.size == (2000, 1500)

    def test_leaves_already_small_file_untouched(self, tmp_path):
        from cbz_ops.compress import compress_cbz

        out = io.BytesIO()
        Image.new("RGB", (100, 150), "red").save(out, "WEBP", quality=50)
        path = tmp_path / "small.cbz"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("001.webp", out.getvalue())
        before = path.read_bytes()

        old, new = compress_cbz(str(path))

        assert old == new
        assert path.read_bytes() == before

    def test_unreadable_page_is_kept_exactly(self, big_cbz):
        from cbz_ops.compress import compress_cbz

        with zipfile.ZipFile(big_cbz, "a") as zf:
            zf.writestr("004.jpg", b"not really a jpeg")

        compress_cbz(str(big_cbz))

        with zipfile.ZipFile(big_cbz) as zf:
            assert zf.read("004.jpg") == b"not really a jpeg"

    def test_failed_write_leaves_original(self, big_cbz):
        from cbz_ops import compress

        before = big_cbz.read_bytes()
        with patch.object(compress, "open_zip_for_write", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                compress.compress_cbz(str(big_cbz))
        assert big_cbz.read_bytes() == before

    def test_refuses_non_cbz(self, tmp_path):
        from cbz_ops.compress import compress_cbz

        path = tmp_path / "x.cbr"
        path.write_bytes(b"rar")
        with pytest.raises(ValueError):
            compress_cbz(str(path))


class TestCompressPath:

    def test_directory_compresses_each_cbz_and_reports_failures(self, tmp_path, big_cbz):
        from cbz_ops.compress import compress_path

        (tmp_path / "broken.cbz").write_bytes(b"not a zip")
        (tmp_path / "notes.txt").write_text("skip me")

        failed = compress_path(str(tmp_path))

        assert failed == 1
        with zipfile.ZipFile(big_cbz) as zf:
            assert "001.webp" in zf.namelist()
