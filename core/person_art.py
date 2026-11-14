"""Photos for creators, characters, teams and publishers, from Metron.

The one owner of the ``person_art`` and ``character_teams`` tables and of the
image files under ``CACHE_DIR/person-art``. The browser never hotlinks Metron:
images are fetched here, resized and served by ``/api/person-art/...``.

Things that look arbitrary and are not:

* **Never called from a request thread.** ``resolve`` sends up to three Metron
  requests and an image download. Opening a detail page only ``ensure()``s one
  name on a daemon thread; the index pages never fetch, and there is no
  scheduled sweep (a sweep hammered Metron into timeouts). Relies on
  gunicorn's single worker.
* **Only an exact (casefolded) name match is used.** A fuzzy match would put a
  stranger's face on a creator page, which is worse than initials.
* **A team is a Metron team with a member character in the library.** Teams
  come from ``Character.teams`` when a character is resolved; ComicInfo has no
  usable teams. The character's own row (any status) marks its teams as
  fetched, so a character on no team is not asked again.
* **Metron down or paused is a quiet no-op**: ``paused_reason()`` stops a sweep
  before it starts, a failed call is stored as ``error`` and retried after 15 minutes (a detail-page open is the only caller), a
  clean "not on Metron" as ``missing`` and retried after 30 days.
* **Files are written through a temp file + ``os.replace`` in the shard dir**,
  never saved onto the cache path (see the thumbnail cache's #548 notes).
"""

import hashlib
import io
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

from core.app_logging import app_logger
from core.config import get_cache_dir
from core.database import db_conn

KINDS = ("creator", "character", "team", "publisher")
_LIST_METHOD = {"creator": "creators_list", "character": "characters_list",
                "team": "teams_list", "publisher": "publishers_list"}
_DETAIL_METHOD = {"creator": "creator", "character": "character",
                  "team": "team", "publisher": "publisher"}
CREDIT_KINDS = ("writer", "penciller", "inker", "colorist", "letterer", "coverartist")

MAX_EDGE = 400
ERROR_RETRY = timedelta(minutes=15)
MISSING_RETRY = timedelta(days=30)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def key_for(name):
    return (name or "").strip().casefold()


def image_path(kind, key):
    """Absolute cache path for one entry's JPEG. Built from a hash, never the name."""
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(get_cache_dir(), "person-art", kind, h[:2], h + ".jpg")


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

def _get_row(kind, key):
    with db_conn() as conn:
        if not conn:
            return None
        row = conn.execute(
            "SELECT kind, key, name, metron_id, image_file, status, checked_at"
            " FROM person_art WHERE kind = ? AND key = ?", (kind, key)).fetchone()
        return dict(row) if row else None


def _save(kind, name, metron_id, status, image_file=None):
    with db_conn() as conn:
        if not conn:
            return
        conn.execute(
            "INSERT INTO person_art (kind, key, name, metron_id, image_file, status, checked_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(kind, key) DO UPDATE SET name = excluded.name,"
            " metron_id = COALESCE(excluded.metron_id, person_art.metron_id),"
            " image_file = excluded.image_file, status = excluded.status,"
            " checked_at = excluded.checked_at",
            (kind, key_for(name), name, metron_id, image_file, status,
             _utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()


def _save_teams(character_name, teams):
    """Replace one character's teams, and give each team a row of its own."""
    ckey = key_for(character_name)
    rows = [(ckey, key_for(t.name), t.name, getattr(t, "id", None))
            for t in teams if getattr(t, "name", None)]
    with db_conn() as conn:
        if not conn:
            return
        conn.execute("DELETE FROM character_teams WHERE character_key = ?", (ckey,))
        conn.executemany(
            "INSERT OR REPLACE INTO character_teams"
            " (character_key, team_key, team_name, team_metron_id) VALUES (?, ?, ?, ?)", rows)
        # status stays NULL until the sweep fetches the team's own image.
        conn.executemany(
            "INSERT INTO person_art (kind, key, name, metron_id) VALUES ('team', ?, ?, ?)"
            " ON CONFLICT(kind, key) DO UPDATE SET name = excluded.name,"
            " metron_id = COALESCE(excluded.metron_id, person_art.metron_id)",
            [(r[1], r[2], r[3]) for r in rows])
        conn.commit()


def _write_image(kind, key, data):
    """Resize to MAX_EDGE and write atomically. Returns the path relative to the cache."""
    from PIL import Image

    dest = image_path(kind, key)
    shard = os.path.dirname(dest)
    os.makedirs(shard, exist_ok=True)
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        fd, tmp = tempfile.mkstemp(dir=shard, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                img.save(fh, "JPEG", quality=85)
            os.replace(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return os.path.relpath(dest, get_cache_dir())


# --------------------------------------------------------------------------
# Resolve one name
# --------------------------------------------------------------------------

def _fail(kind, name, metron_id, why):
    """Store ``error`` and say why: at most one line per name per retry window."""
    app_logger.warning(f"Person art: {kind} {name!r} (Metron id {metron_id}): {why}")
    _save(kind, name, metron_id, "error")
    return "error"


def resolve(kind, name, api, fetch_image):
    """Look one name up on Metron and store what was found. Returns the status.

    ``api`` is a ``MetronClient`` (its methods return None on a failed request
    and ``[]`` for "no results"); ``fetch_image(url)`` returns bytes or None.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown kind {kind!r}")
    key = key_for(name)
    row = _get_row(kind, key)
    metron_id = row["metron_id"] if row else None

    if metron_id is None:
        results = getattr(api, _LIST_METHOD[kind])({"name": name})
        if results is None:
            return _fail(kind, name, None, "Metron search request failed")
        match = next((r for r in results if key_for(getattr(r, "name", "")) == key), None)
        if match is None:
            _save(kind, name, None, "missing")
            return "missing"
        metron_id = match.id

    detail = getattr(api, _DETAIL_METHOD[kind])(metron_id)
    if detail is None:
        return _fail(kind, name, metron_id, "Metron detail request failed")
    if kind == "character":
        _save_teams(name, getattr(detail, "teams", None) or [])

    url = getattr(detail, "image", None)
    if not url:
        _save(kind, name, metron_id, "missing")
        return "missing"
    data = fetch_image(str(url))
    if not data:
        return _fail(kind, name, metron_id, f"image download failed ({url})")
    try:
        image_file = _write_image(kind, key, data)
    except Exception as e:
        return _fail(kind, name, metron_id, f"could not store image: {e}")
    _save(kind, name, metron_id, "ok", image_file)
    return "ok"


# --------------------------------------------------------------------------
# What to resolve next
# --------------------------------------------------------------------------

def _is_due(row, now):
    if row is None or not row["status"]:
        return True
    try:
        checked = datetime.strptime(row["checked_at"], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    if row["status"] == "error":
        return now - checked >= ERROR_RETRY
    if row["status"] == "missing":
        return now - checked >= MISSING_RETRY
    return False


def _default_fetch_image(url):
    """Image bytes via the shared, paced HTTP client; None on any failure."""
    from core.http_client import HttpClient, shared_http_client
    from core.version import CLU_USER_AGENT

    client = shared_http_client("metron-images", lambda: HttpClient(
        "metron-images", "Metron images", "https://static.metron.cloud", 30,
        headers={"User-Agent": CLU_USER_AGENT}))
    resp = client.get(url, context=f"image {url[-60:]}")
    if resp is None or not resp.content:
        return None
    return resp.content


_in_flight = set()
_in_flight_lock = threading.Lock()


def _run_one(app, kind, name):
    from models import metron

    try:
        if metron.paused_reason():
            return
        api = metron.get_flask_api(app)
        if not api:
            return
        status = resolve(kind, name, api, _default_fetch_image)
        app_logger.debug(f"Person art: {kind} {name!r} -> {status}")
    except Exception as e:
        app_logger.debug(f"Person art: {kind} {name!r} failed: {e}")
    finally:
        with _in_flight_lock:
            _in_flight.discard((kind, key_for(name)))


def ensure(app, kind, name):
    """Resolve one name on a daemon thread when its detail page is opened.

    No-op when it is already cached, not yet due for a retry, or already in
    flight. This is the only thing that talks to Metron: there is no sweep.
    """
    if kind not in KINDS or not name:
        return False
    key = key_for(name)
    if not _is_due(_get_row(kind, key), _utcnow()):
        return False
    with _in_flight_lock:
        if (kind, key) in _in_flight:
            return False
        _in_flight.add((kind, key))
    threading.Thread(target=_run_one, args=(app, kind, name), daemon=True,
                     name="person-art").start()
    return True


# --------------------------------------------------------------------------
# Serving
# --------------------------------------------------------------------------

def art_urls(kind, names):
    """``{name: url or None}`` for names, in one query. None draws initials."""
    from flask import url_for

    names = list(names)
    out = dict.fromkeys(names)
    if kind not in KINDS or not names:
        return out
    keys = {key_for(n): n for n in names}
    rows = {}
    with db_conn() as conn:
        if conn:
            for i in range(0, len(keys), 500):
                chunk = list(keys)[i:i + 500]
                rows.update({r["key"]: r for r in conn.execute(
                    "SELECT key, checked_at FROM person_art WHERE kind = ? AND status = 'ok'"
                    f" AND key IN ({','.join('?' for _ in chunk)})", [kind, *chunk])})
    for name in names:
        row = rows.get(key_for(name))
        if row and os.path.exists(image_path(kind, key_for(name))):
            out[name] = url_for("creators.person_art", kind=kind, name=name,
                                v=(row["checked_at"] or "").replace(" ", "T"))
    return out


def served_file(kind, name):
    """The cached JPEG for one entry, or None. The path never comes from the name."""
    if kind not in KINDS:
        return None
    path = image_path(kind, key_for(name))
    return path if os.path.isfile(path) else None
