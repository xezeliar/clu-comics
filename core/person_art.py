"""Photos for creators, characters, teams and publishers, from Metron.

The one owner of the ``person_art`` and ``character_teams`` tables and of the
image files under ``CACHE_DIR/person-art``. The browser never hotlinks Metron:
images are fetched here, resized and served by ``/api/person-art/...``.

Things that look arbitrary and are not:

* **Never called from a request thread.** ``resolve`` sends up to three Metron
  requests and an image download. The index pages only ``kick()`` a daemon
  thread (at most once per ``KICK_INTERVAL``); the scheduled job in app.py runs
  ``run_sweep`` every 30 minutes. Both rely on gunicorn's single worker.
* **Only an exact (casefolded) name match is used.** A fuzzy match would put a
  stranger's face on a creator page, which is worse than initials.
* **A team is a Metron team with a member character in the library.** Teams
  come from ``Character.teams`` when a character is resolved; ComicInfo has no
  usable teams. The character's own row (any status) marks its teams as
  fetched, so a character on no team is not asked again.
* **Metron down or paused is a quiet no-op**: ``paused_reason()`` stops a sweep
  before it starts, a failed call is stored as ``error`` and retried after a
  day, a clean "not on Metron" as ``missing`` and retried after 30 days.
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
from core.database import _COMIC_FILE_CLAUSE_FI, db_conn

KINDS = ("creator", "character", "team", "publisher")
_LIST_METHOD = {"creator": "creators_list", "character": "characters_list",
                "team": "teams_list", "publisher": "publishers_list"}
_DETAIL_METHOD = {"creator": "creator", "character": "character",
                  "team": "team", "publisher": "publisher"}
CREDIT_KINDS = ("writer", "penciller", "inker", "colorist", "letterer", "coverartist")

MAX_EDGE = 400
ERROR_RETRY = timedelta(days=1)
MISSING_RETRY = timedelta(days=30)
KICK_INTERVAL = 600  # seconds between index-page kicks
_CANDIDATES_PER_KIND = 2000


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
            _save(kind, name, None, "error")
            return "error"
        match = next((r for r in results if key_for(getattr(r, "name", "")) == key), None)
        if match is None:
            _save(kind, name, None, "missing")
            return "missing"
        metron_id = match.id

    detail = getattr(api, _DETAIL_METHOD[kind])(metron_id)
    if detail is None:
        _save(kind, name, metron_id, "error")
        return "error"
    if kind == "character":
        _save_teams(name, getattr(detail, "teams", None) or [])

    url = getattr(detail, "image", None)
    if not url:
        _save(kind, name, metron_id, "missing")
        return "missing"
    data = fetch_image(str(url))
    if not data:
        _save(kind, name, metron_id, "error")
        return "error"
    try:
        image_file = _write_image(kind, key, data)
    except Exception as e:
        app_logger.debug(f"Person art: could not store image for {kind} {name}: {e}")
        _save(kind, name, metron_id, "error")
        return "error"
    _save(kind, name, metron_id, "ok", image_file)
    return "ok"


# --------------------------------------------------------------------------
# What to resolve next
# --------------------------------------------------------------------------

def _library_names(conn, kind):
    """Names the library uses for ``kind``, most used first."""
    if kind == "team":
        sql = ("SELECT name, 0 AS n FROM person_art WHERE kind = 'team'")
        return [r["name"] for r in conn.execute(sql).fetchall() if r["name"]]
    if kind == "publisher":
        sql = ("SELECT MIN(fi.ci_publisher) AS name, COUNT(*) AS n FROM file_index fi"
               " WHERE fi.ci_publisher IS NOT NULL AND fi.ci_publisher != '' AND "
               + _COMIC_FILE_CLAUSE_FI +
               " GROUP BY fi.ci_publisher COLLATE NOCASE ORDER BY n DESC LIMIT ?")
        params = [_CANDIDATES_PER_KIND]
    else:
        kinds = ("characters",) if kind == "character" else CREDIT_KINDS
        sql = ("SELECT MIN(t.value) AS name, COUNT(DISTINCT t.file_path) AS n"
               " FROM file_metadata_tags t"
               f" WHERE t.kind IN ({','.join('?' for _ in kinds)})"
               " GROUP BY t.value COLLATE NOCASE ORDER BY n DESC LIMIT ?")
        params = [*kinds, _CANDIDATES_PER_KIND]
    return [r["name"] for r in conn.execute(sql, params).fetchall() if r["name"]]


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


def pending(limit=25):
    """Up to ``limit`` (kind, name) pairs that need resolving, most used first.

    Characters go first: resolving one is also what discovers teams.
    """
    now = _utcnow()
    out = []
    with db_conn() as conn:
        if not conn:
            return out
        for kind in ("character", "team", "creator", "publisher"):
            rows = {r["key"]: r for r in conn.execute(
                "SELECT key, status, checked_at FROM person_art WHERE kind = ?", (kind,))}
            for name in _library_names(conn, kind):
                if _is_due(rows.get(key_for(name)), now):
                    out.append((kind, name))
                    if len(out) >= limit:
                        return out
    return out


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------

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


def sweep(limit=25, api=None, fetch_image=None, app=None):
    """Resolve up to ``limit`` pending names. Quiet when Metron is unavailable.

    Returns a ``{status: count}`` summary (empty when nothing ran).
    """
    from models import metron

    if metron.paused_reason():
        app_logger.debug(f"Person art sweep skipped: {metron.paused_reason()}")
        return {}
    work = pending(limit)
    if not work:
        return {}
    if api is None:
        api = metron.get_flask_api(app) if app is not None else None
        if not api:
            app_logger.debug("Person art sweep skipped: Metron not configured")
            return {}
    fetch_image = fetch_image or _default_fetch_image

    summary = {}
    for kind, name in work:
        if metron.paused_reason():
            break
        try:
            status = resolve(kind, name, api, fetch_image)
        except Exception as e:
            app_logger.debug(f"Person art: {kind} {name!r} failed: {e}")
            status = "error"
        app_logger.debug(f"Person art: {kind} {name!r} -> {status}")
        summary[status] = summary.get(status, 0) + 1
    app_logger.info(
        "Person art: checked " + str(sum(summary.values())) + " names ("
        + ", ".join(f"{v} {k}" for k, v in sorted(summary.items())) + ")")
    return summary


_sweep_lock = threading.Lock()
_last_kick = 0.0


def run_sweep(app, limit=25):
    """One sweep at a time; never raises. The scheduled job and kicks call this."""
    if not _sweep_lock.acquire(blocking=False):
        return {}
    try:
        return sweep(limit=limit, app=app)
    except Exception as e:
        app_logger.debug(f"Person art sweep failed: {e}")
        return {}
    finally:
        _sweep_lock.release()


def kick(app):
    """Start a sweep on a daemon thread, at most once per KICK_INTERVAL."""
    global _last_kick
    now = time.monotonic()
    if _last_kick and now - _last_kick < KICK_INTERVAL:
        return False
    _last_kick = now
    threading.Thread(target=run_sweep, args=(app,), daemon=True,
                     name="person-art-sweep").start()
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
