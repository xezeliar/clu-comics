"""/api/hero-cover: the Home hero's large cover (core/hero_cover.py).

The per-comic thumbnail is 300px tall; the hero serves the same first page at
720px from its own cache, confined the way /api/folder-thumbnail is.
"""
import os
import zipfile
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image


def _jpeg(size):
    buf = BytesIO()
    Image.new("RGB", size, "purple").save(buf, format="JPEG")
    return buf.getvalue()


def _make_cbz(path, size=(1200, 1800)):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("002.jpg", _jpeg((10, 10)))
        zf.writestr("001.jpg", _jpeg(size))


@pytest.fixture
def comic(tmp_path):
    folder = tmp_path / "data" / "Batman"
    folder.mkdir(parents=True)
    path = folder / "Batman 001.cbz"
    _make_cbz(path)
    return str(path)


@pytest.fixture(autouse=True)
def hero_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    with patch("core.hero_cover.get_cache_dir", return_value=str(cache)):
        yield cache


class TestHeroCoverRoute:

    def test_missing_path_is_400(self, client):
        assert client.get("/api/hero-cover").status_code == 400

    def test_path_outside_every_root_is_404_and_opens_nothing(self, client, comic):
        with patch("routes.collection.is_allowed_path", return_value=False), \
                patch("core.hero_cover.ensure_hero_cover") as ensure:
            resp = client.get("/api/hero-cover", query_string={"path": comic})
        assert resp.status_code == 404
        ensure.assert_not_called()

    def test_serves_a_720px_cover_not_the_300px_thumbnail(self, client, comic):
        with patch("routes.collection.is_allowed_path", return_value=True):
            resp = client.get("/api/hero-cover", query_string={"path": comic})
        assert resp.status_code == 200
        assert resp.mimetype == "image/jpeg"
        img = Image.open(BytesIO(resp.data))
        assert img.height == 720
        assert img.width == 480  # 2:3 page keeps its aspect ratio

    def test_never_upscales_a_small_page(self, client, tmp_path):
        small = tmp_path / "data" / "Small" / "Small 001.cbz"
        small.parent.mkdir(parents=True)
        _make_cbz(small, size=(200, 300))
        with patch("routes.collection.is_allowed_path", return_value=True):
            resp = client.get("/api/hero-cover", query_string={"path": str(small)})
        assert resp.status_code == 200
        assert Image.open(BytesIO(resp.data)).height == 300

    def test_a_comic_with_no_pages_is_404_so_the_page_falls_back(self, client, tmp_path):
        empty = tmp_path / "data" / "Empty" / "Empty 001.cbz"
        empty.parent.mkdir(parents=True)
        with zipfile.ZipFile(empty, "w") as zf:
            zf.writestr("ComicInfo.xml", "<ComicInfo/>")
        with patch("routes.collection.is_allowed_path", return_value=True):
            resp = client.get("/api/hero-cover", query_string={"path": str(empty)})
        assert resp.status_code == 404

    def test_second_request_is_served_from_the_cache(self, client, comic):
        with patch("routes.collection.is_allowed_path", return_value=True):
            client.get("/api/hero-cover", query_string={"path": comic})
            with patch("core.thumbnail_cache._first_page") as reader:
                resp = client.get("/api/hero-cover", query_string={"path": comic})
        assert resp.status_code == 200
        reader.assert_not_called()

    def test_a_rewritten_comic_gets_a_new_cover(self, client, comic):
        from core.hero_cover import hero_cover_path
        with patch("routes.collection.is_allowed_path", return_value=True):
            client.get("/api/hero-cover", query_string={"path": comic})
            cached = hero_cover_path(comic)
            old = os.path.getmtime(cached)
            os.utime(comic, (old + 100, old + 100))  # comic is now newer
            _make_cbz(comic, size=(600, 1800))
            os.utime(comic, (old + 100, old + 100))
            resp = client.get("/api/hero-cover", query_string={"path": comic})
        assert resp.status_code == 200
        assert Image.open(BytesIO(resp.data)).width == 240  # 1:3 page at 720 tall


class TestHeroCoverCache:

    def test_cache_is_separate_from_the_thumbnail_cache(self, comic, hero_cache):
        from core.hero_cover import hero_cover_path
        from core.thumbnail_cache import thumbnail_cache_path
        assert hero_cover_path(comic).startswith(str(hero_cache / "hero_covers"))
        assert hero_cover_path(comic) != thumbnail_cache_path(comic)

    def test_thumbnail_height_is_unchanged_by_the_shared_reader(self, comic):
        from core.thumbnail_cache import THUMBNAIL_HEIGHT, _first_page
        assert THUMBNAIL_HEIGHT == 300
        assert _first_page(comic).height == 300
