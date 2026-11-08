"""Compress a CBZ: shrink its page images to save disk space.

Every page is re-encoded as WebP at WEBP_QUALITY, at its original resolution:
the aim is a smaller file with no visible loss, not a smaller picture. A page whose new version is not
smaller keeps its original bytes, and a comic that would not shrink by at least
MIN_SAVING is left untouched. Page order is kept: a page keeps its name and only
its extension changes. Everything that is not a page (ComicInfo.xml and other
files) is copied byte-for-byte.

Run as ``python -m cbz_ops.compress <file.cbz | directory>``. A directory means
every CBZ directly inside it (not subfolders).
"""

import io
import os
import sys
import zipfile

from PIL import Image

from core.app_logging import app_logger
from helpers import is_hidden, open_zip_for_write

# Measured on two HD comics (1988x3056 JPEG pages): quality 90 at full size
# matches the "small" downloads Batcave serves (PSNR ~42-44 dB against the
# original) and saves 27-44%. Scaling pages down saved far more but was the
# main source of visible softening, so pages keep their resolution.
WEBP_QUALITY = 90
MIN_SAVING = 0.05

PAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _shrink_page(data):
    """Return (bytes, ext) for a smaller version of one page, or None to keep it."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            if img.mode not in ("RGB", "RGBA", "L", "LA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            out = io.BytesIO()
            img.save(out, "WEBP", quality=WEBP_QUALITY, method=4)
    except Exception as e:  # unreadable page: keep it exactly as it was
        app_logger.debug(f"Compress: keeping unreadable page as-is: {e}")
        return None
    new = out.getvalue()
    return (new, ".webp") if len(new) < len(data) else None


def compress_cbz(cbz_path):
    """Compress one CBZ in place. Returns (old_size, new_size); equal when the
    file was left untouched."""
    if not cbz_path.lower().endswith(".cbz"):
        raise ValueError("only CBZ files can be compressed; convert it to CBZ first")
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
                shrunk = _shrink_page(data)
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
    try:
        old, new = compress_cbz(path)
    except Exception as e:
        logger.warning(f"Auto-compress skipped for '{path}': {e}")
        return
    if new < old:
        logger.info(f"Auto-compressed '{os.path.basename(path)}': {_mb(old)} -> {_mb(new)}")


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
