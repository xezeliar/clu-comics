"""Stored Metron and ComicVine profiles for character, team and creator pages.

The one owner of the ``entity_profiles`` table. ``core/person_art.py`` already
fetches the Metron detail for a name when its page opens; it hands that detail
here, and this module adds the ComicVine record through Metron's ``cv_id``.

Things that look arbitrary and are not:

* **ComicVine is reached only through Metron's ``cv_id``.** It is never searched
  by name: two characters share a name far more often than a CV id is wrong.
* **Stored forever, refreshed by hand.** A page view only reads the row. There
  is no expiry and no sweep, because Metron and ComicVine limits are shared
  with tagging. Refresh on the detail page is the only thing that rewrites one.
* **A failed fetch keeps the old data.** It updates ``status``/``error`` only.
* **Only the fields the pages show are stored**, not whole responses. CV's
  long ``description`` is kept for creators only, sanitized on write.
"""

import json
from datetime import timedelta

from core.app_logging import app_logger
from core.database import db_conn

KINDS = ("character", "team", "creator")
ERROR_RETRY = timedelta(minutes=15)
_CV_METHOD = {"character": "get_character", "team": "get_team", "creator": "get_creator"}


def _names(items):
    return [getattr(i, "name", None) for i in items or () if getattr(i, "name", None)]


def _entries(items):
    """``[{"id", "name"}]`` from provider list entries."""
    return [{"id": getattr(i, "id", None), "name": i.name}
            for i in items or () if getattr(i, "name", None)]


def _date(value):
    return value.isoformat() if hasattr(value, "isoformat") else None


def _aliases(text):
    """ComicVine keeps aliases as one newline-separated string."""
    return [a.strip() for a in (text or "").splitlines() if a.strip()]


def metron_fields(kind, detail):
    """The Metron fields a page shows, as plain JSON-able values."""
    out = {"desc": getattr(detail, "desc", None) or None,
           "gcd_id": getattr(detail, "gcd_id", None)}
    if kind in ("character", "creator"):
        out["alias"] = list(getattr(detail, "alias", None) or [])
    if kind in ("character", "team"):
        out["universes"] = _names(getattr(detail, "universes", None))
        out["creators"] = _names(getattr(detail, "creators", None))
    if kind == "creator":
        out["birth"] = _date(getattr(detail, "birth", None))
        out["death"] = _date(getattr(detail, "death", None))
    return out


def cv_fields(kind, record):
    """The ComicVine fields a page shows, as plain JSON-able values."""
    image = getattr(record, "image", None)
    out = {"summary": getattr(record, "summary", None) or None,
           "aliases": _aliases(getattr(record, "aliases", None)),
           "image": getattr(image, "original_url", None) and str(image.original_url)}
    if kind in ("character", "team"):
        first = getattr(record, "first_issue", None)
        out["first_issue"] = ({"id": first.id, "name": getattr(first, "name", None),
                               "number": getattr(first, "number", None)} if first else None)
        out["friends"] = _entries(getattr(record, "friends", None))
        out["enemies"] = _entries(getattr(record, "enemies", None))
    if kind == "character":
        origin = getattr(record, "origin", None)
        out["real_name"] = getattr(record, "real_name", None) or None
        out["origin"] = getattr(origin, "name", None)
        out["powers"] = _names(getattr(record, "powers", None))
    if kind == "team":
        out["members"] = _entries(getattr(record, "members", None))
        out["disbanded_in"] = _entries(getattr(record, "issues_disbanded_in", None))
    if kind == "creator":
        from core.description_html import sanitize_description_html

        website = getattr(record, "website", None)
        out["description"] = sanitize_description_html(
            getattr(record, "description", None) or "") or None
        out["hometown"] = getattr(record, "hometown", None) or None
        out["country"] = getattr(record, "country", None) or None
        out["website"] = str(website) if website else None
    return out


def _now():
    from core.person_art import _utcnow

    return _utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _key(name):
    from core.person_art import key_for

    return key_for(name)


def get_profile(kind, name):
    """The stored row with ``metron``/``cv`` decoded, or None. Never fetches."""
    if kind not in KINDS or not name:
        return None
    with db_conn() as conn:
        if not conn:
            return None
        row = conn.execute(
            "SELECT * FROM entity_profiles WHERE kind = ? AND key = ?",
            (kind, _key(name))).fetchone()
    if not row:
        return None
    out = dict(row)
    for col, field in (("metron_json", "metron"), ("cv_json", "cv")):
        try:
            out[field] = json.loads(out.pop(col)) if out.get(col) else None
        except (TypeError, ValueError):
            out[field] = None
    return out


def is_due(kind, name, now):
    """True when a page open should fetch: never fetched, or an error worth retrying."""
    from datetime import datetime

    if kind not in KINDS:
        return False
    row = get_profile(kind, name)
    if row is None or not row["status"]:
        return True
    if row["status"] != "error":
        return False
    try:
        checked = datetime.strptime(row["checked_at"], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    return now - checked >= ERROR_RETRY


def _upsert(kind, name, **cols):
    """Write the given columns for one row; columns left out keep their values."""
    cols = {**cols, "name": name, "checked_at": _now()}
    names = list(cols)
    with db_conn() as conn:
        if not conn:
            return
        conn.execute(
            f"INSERT INTO entity_profiles (kind, key, {', '.join(names)})"
            f" VALUES (?, ?, {', '.join('?' for _ in names)})"
            " ON CONFLICT(kind, key) DO UPDATE SET "
            + ", ".join(f"{n} = excluded.{n}" for n in names),
            [kind, _key(name), *cols.values()])
        conn.commit()


def record_missing(kind, name):
    """Metron has no exact match for the name."""
    if kind in KINDS:
        _upsert(kind, name, status="missing", error=None)


def record_error(kind, name, why):
    """A Metron request failed; whatever was stored before stays."""
    if kind in KINDS:
        _upsert(kind, name, status="error", error=why)


def store(kind, name, detail, cv=None):
    """Store the Metron detail, then fetch and store ComicVine by its ``cv_id``.

    ``cv`` is a ``ComicVineClient`` or None (no key, or paused). Returns the
    status written. A ComicVine failure keeps the old ``cv_json`` and is noted
    in ``error``; the Metron half is still stored.
    """
    if kind not in KINDS:
        return None
    cv_id = getattr(detail, "cv_id", None)
    cols = {"metron_id": getattr(detail, "id", None), "cv_id": cv_id,
            "metron_json": json.dumps(metron_fields(kind, detail)),
            "metron_fetched_at": _now(), "status": "ok", "error": None}
    if cv_id and cv is not None:
        try:
            record = getattr(cv, _CV_METHOD[kind])(cv_id)
            cols["cv_json"] = json.dumps(cv_fields(kind, record))
            cols["cv_fetched_at"] = _now()
        except Exception as e:
            app_logger.warning(f"Profile: ComicVine {kind} {cv_id} for {name!r} failed: {e}")
            cols["error"] = f"ComicVine: {e}"
    elif not cv_id:
        # Metron no longer names a CV record: what was stored belongs to another one.
        cols["cv_json"] = None
        cols["cv_fetched_at"] = None
    _upsert(kind, name, **cols)
    return "ok"
