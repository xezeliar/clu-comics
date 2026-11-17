"""Large covers for the Home hero.

The per-comic thumbnail (``core/thumbnail_cache.py``) is 300px tall, which is
right for a grid and blurry when stretched across a hero card. A hero cover is
the same first page at ``HERO_HEIGHT`` px, kept in its **own** cache directory so
the thumbnail cache, its job table and its in-flight guard are untouched.

It reuses the thumbnail module's page reader (``_first_page(height=)``), its
atomic temp-file-plus-``os.replace`` writer's rules and its staleness test, and
never upscales: a page smaller than ``HERO_HEIGHT`` is kept as it is.
"""
import hashlib
import os
import tempfile

from core.app_logging import app_logger
from core.config import get_cache_dir
from core import thumbnail_cache

HERO_HEIGHT = 720
HERO_JPEG_QUALITY = 88


def hero_root(cache_dir=None):
    return os.path.join(cache_dir or get_cache_dir(), "hero_covers")


def hero_cover_path(file_path, cache_dir=None):
    """``<cache>/hero_covers/<2 hex>/<md5(path)>.jpg``, the thumbnail formula."""
    digest = hashlib.md5(file_path.encode("utf-8"), usedforsecurity=False).hexdigest()
    return os.path.join(hero_root(cache_dir), digest[:2], f"{digest}.jpg")


def is_hero_cover_stale(file_path, cache_path):
    """Same rule as the thumbnail: the key is the path, so a rewritten comic
    must not keep its old cover. "Cannot tell" means serve what we have."""
    return thumbnail_cache.is_thumbnail_stale(file_path, cache_path)


def _write(img, cache_path):
    """Atomic write beside the destination; False on any failure."""
    shard_dir = os.path.dirname(cache_path)
    tmp_path = None
    try:
        os.makedirs(shard_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=shard_dir, suffix=".jpg.tmp")
        os.close(fd)
        img.save(tmp_path, format="JPEG", quality=HERO_JPEG_QUALITY)
        from helpers import match_parent_permissions
        match_parent_permissions(tmp_path)
        os.replace(tmp_path, cache_path)
        tmp_path = None
        return True
    except Exception as e:
        app_logger.error(f"Failed to write hero cover {cache_path}: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def ensure_hero_cover(file_path, cache_dir=None):
    """Return the path of a current hero cover for ``file_path``, building it if
    needed, or None when the comic has no readable first page.

    Never raises: the hero falls back to the small thumbnail on None.
    """
    if not thumbnail_cache.can_thumbnail(file_path):
        return None
    cache_path = hero_cover_path(file_path, cache_dir)
    if os.path.exists(cache_path) and not is_hero_cover_stale(file_path, cache_path):
        return cache_path
    try:
        img = thumbnail_cache._first_page(file_path, height=HERO_HEIGHT)
    except Exception as e:
        app_logger.warning(f"No hero cover for {file_path}: {e}")
        return None
    if img is None:
        return None
    return cache_path if _write(img, cache_path) else None
