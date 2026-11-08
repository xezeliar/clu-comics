"""Compress a CBZ: shrink its page images to save disk space.

Every page is re-encoded as WebP. How hard is the ``compress_level`` setting
(see LEVELS): "full" keeps the resolution at quality 90, "balanced" keeps it at
quality 80, "small" also limits a page's longest side to 1600 px at quality 75.
A page whose new version is not smaller keeps its original bytes, and a comic
that would not shrink by at least MIN_SAVING is left untouched. Page order is kept: a page keeps its name and only
its extension changes. Everything that is not a page (ComicInfo.xml and other
files) is copied byte-for-byte.

Run as ``python -m cbz_ops.compress <file.cbz | directory>``. A directory means
every CBZ directly inside it (not subfolders).
"""

import io
import os
import sys
import time
import zipfile

from PIL import Image

from core import compress_status
from core.app_logging import app_logger
from core.settings import get_setting
from helpers import is_hidden, open_zip_for_write

# level -> (WebP quality, longest side in px or None to keep the resolution).
# Measured on HD comics (1988x3056 JPEG pages), as a share of the original size:
#   full      q90, full size      ~68%   no visible loss; scaling down was the
#                                        main source of visible softening
#   balanced  q80, full size      ~43%
#   small     q75, longest 1600   ~12%   what Batcave serves (1041x1600 pages);
#                                        fine on a phone or tablet, softer on a
#                                        large monitor, and not reversible
LEVELS = {
    "full": (90, None),
    "balanced": (80, None),
    "small": (75, 1600),
}
DEFAULT_LEVEL = "full"
MIN_SAVING = 0.05

PAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def normalize_level(value):
    """A valid level name for ``value``; anything unknown is the default, so a
    stale or hand-edited preference can never make a compress fail."""
    level = str(value or "").strip().lower()
    return level if level in LEVELS else DEFAULT_LEVEL


def get_level():
    """The configured level, asked per call: never a module constant, because the
    monitor, the web worker and the manual subprocess must all follow a change."""
    return normalize_level(get_setting("COMPRESS_LEVEL"))


def _shrink_page(data, level=DEFAULT_LEVEL):
    """Return (bytes, ext) for a smaller version of one page, or None to keep it."""
    quality, max_side = LEVELS[normalize_level(level)]
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            if img.mode not in ("RGB", "RGBA", "L", "LA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            longest = max(img.size)
            if max_side and longest > max_side:  # never upscale a smaller page
                scale = max_side / longest
                img = img.resize((max(1, round(img.width * scale)),
                                  max(1, round(img.height * scale))), Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, "WEBP", quality=quality, method=4)
    except Exception as e:  # unreadable page: keep it exactly as it was
        app_logger.debug(f"Compress: keeping unreadable page as-is: {e}")
        return None
    new = out.getvalue()
    return (new, ".webp") if len(new) < len(data) else None


def compress_cbz(cbz_path):
    """Compress one CBZ in place. Returns (old_size, new_size); equal when the
    file was left untouched.

    The file is marked as compressing for the whole run (see
    core.compress_status) so the File Manager can say so and /move can refuse
    to take it away half-rewritten. Every caller -- the monitor's auto-compress
    and the manual one -- goes through here, so the marker cannot be forgotten."""
    if not cbz_path.lower().endswith(".cbz"):
        raise ValueError("only CBZ files can be compressed; convert it to CBZ first")
    compress_status.begin(cbz_path)
    try:
        return _compress_cbz(cbz_path)
    finally:
        compress_status.end(cbz_path)


def _compress_cbz(cbz_path):
    level = get_level()  # once per comic, so one file is never half one level, half another
    old_size = os.path.getsize(cbz_path)
    with zipfile.ZipFile(cbz_path) as src:
        members = [m for m in src.infolist() if not m.is_dir()]
        names = {m.filename.lower() for m in members}
        entries = []  # (arcname, bytes, is_page)
        before = 0  # member bytes before, compared like-for-like with after
        pages = [m for m in members if m.filename.lower().endswith(PAGE_EXTENSIONS)]
        done = 0
        for member in members:
            data = src.read(member)
            before += len(data)
            name = member.filename
            is_page = name.lower().endswith(PAGE_EXTENSIONS)
            if is_page:
                done += 1
                print(f"Processing page {done}/{len(pages)}", flush=True)
                shrunk = _shrink_page(data, level)
                if shrunk:
                    new_name = os.path.splitext(name)[0] + shrunk[1]
                    # Never collide with another member (e.g. 01.jpg + 01.webp).
                    if new_name == name or new_name.lower() not in names:
                        names.add(new_name.lower())
                        name, data = new_name, shrunk[0]
            entries.append((name, data, is_page))

    after = sum(len(d) for _, d, _ in entries)
    if after > before * (1 - MIN_SAVING):
        return old_size, old_size

    # Encoding takes a while; if the comic was moved or replaced meanwhile (the
    # Wanted sweep files TARGET comics away), writing would resurrect or clobber it.
    if not os.path.exists(cbz_path) or os.path.getsize(cbz_path) != old_size:
        raise RuntimeError("file was moved or changed while compressing; left as it is")

    # Built on local storage and moved into place: a failure leaves the
    # original untouched.
    with open_zip_for_write(cbz_path, zipfile.ZIP_DEFLATED) as dst:
        for name, data, is_page in entries:
            # Pages are already compressed; deflating them again only costs time.
            dst.writestr(name, data,
                         compress_type=zipfile.ZIP_STORED if is_page else zipfile.ZIP_DEFLATED)

    try:
        from core.thumbnail_cache import regenerate_thumbnail
        regenerate_thumbnail(cbz_path)
    except Exception as e:  # the comic is already written; a cache miss is harmless
        app_logger.warning(f"Compress: could not refresh thumbnail for {cbz_path}: {e}")
    return old_size, os.path.getsize(cbz_path)


def auto_compress(path, logger):
    """Pipeline hook: compress ``path`` if it is a CBZ. Never raises, so a
    failure can only cost the saving, never the move that called it."""
    if not path or not path.lower().endswith(".cbz") or not os.path.exists(path):
        return
    name = os.path.basename(path)
    # A large issue takes tens of seconds; without a start line the log is silent
    # for the whole run and it looks as though nothing is happening.
    try:
        logger.info(f"Auto-compressing '{name}' ({_mb(os.path.getsize(path))}, level "
                    f"{get_level()}); it is marked as compressing until this finishes")
        started = time.monotonic()
        old, new = compress_cbz(path)
    except Exception as e:
        logger.warning(f"Auto-compress skipped for '{path}': {e}")
        return
    took = f"{time.monotonic() - started:.0f}s"
    if new < old:
        logger.info(f"Auto-compressed '{name}': {_mb(old)} -> {_mb(new)} in {took}")
    else:
        logger.info(f"Auto-compress left '{name}' unchanged (no worthwhile saving) after {took}")


def _mb(n):
    return f"{n / (1024 * 1024):.1f} MB"


def compress_path(target):
    """Compress a CBZ, or every CBZ directly inside a directory. Returns the
    number of files that failed."""
    if os.path.isdir(target):
        files = sorted(
            os.path.join(target, f) for f in os.listdir(target)
            if f.lower().endswith(".cbz") and not is_hidden(os.path.join(target, f))
        )
    else:
        files = [target]

    failed = 0
    saved = 0
    print(f"Compression level: {get_level()}", flush=True)
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        print(f"Processing file: {name} ({i}/{len(files)})", flush=True)
        try:
            old, new = compress_cbz(path)
        except Exception as e:
            failed += 1
            app_logger.error(f"Compress failed for {path}: {e}")
            print(f"Failed: {name}: {e}", flush=True)
            continue
        if new < old:
            saved += old - new
            print(f"{name}: {_mb(old)} -> {_mb(new)}", flush=True)
        else:
            print(f"{name}: already small, left unchanged", flush=True)

    app_logger.info(
        f"Compress: {len(files)} file(s) in {target}, saved {_mb(saved)}, {failed} failed"
    )
    print(f"Compression complete: saved {_mb(saved)}", flush=True)
    return failed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("No file or directory provided!", flush=True)
        sys.exit(1)
    sys.exit(1 if compress_path(sys.argv[1]) else 0)
