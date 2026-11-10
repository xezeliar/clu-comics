"""Activity feed: one persisted, pruned timeline of what CLU did.

Fed from the existing hook sites (download settle, wanted digest, run reports,
bulk metadata, damaged-file records) instead of parsing log files. Like the
notification hooks, every public function swallows its exceptions: recording an
event must never break the work it describes.

INFO-budget rules apply here too: one row per *operation* (a sweep, a digest,
a bulk job), never one per item in a loop.

Bounded on purpose: ``MAX_ROWS`` newest rows and ``MAX_AGE_DAYS``, pruned every
``PRUNE_EVERY`` inserts. All timestamps are UTC.
"""

import threading
from datetime import datetime, timedelta, timezone

from core.app_logging import app_logger

KIND_DOWNLOAD = "download"
KIND_MOVE = "move"
KIND_TAG = "tag"
KIND_SWEEP = "sweep"
KIND_ERROR = "error"
KINDS = (KIND_DOWNLOAD, KIND_MOVE, KIND_TAG, KIND_SWEEP, KIND_ERROR)

LEVEL_INFO = "info"
LEVEL_ERROR = "error"

MAX_ROWS = 5000
MAX_AGE_DAYS = 90
PRUNE_EVERY = 200
MAX_LIMIT = 200

_prune_lock = threading.Lock()
_inserts_since_prune = 0


def _clip(text, n):
    return None if text is None else str(text)[:n]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def prune(conn, now=None):
    """Drop rows past the age cap, then everything beyond the newest MAX_ROWS."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM activity_events WHERE ts < ?", (cutoff,))
    conn.execute(
        "DELETE FROM activity_events WHERE id NOT IN "
        "(SELECT id FROM activity_events ORDER BY id DESC LIMIT ?)",
        (MAX_ROWS,),
    )


def record_event(kind, title, detail=None, path=None, level=None):
    """Append one event. Returns True if written; never raises."""
    global _inserts_since_prune
    try:
        if kind not in KINDS:
            return False
        if level is None:
            level = LEVEL_ERROR if kind == KIND_ERROR else LEVEL_INFO
        from core.database import db_conn

        with db_conn() as conn:
            if not conn:
                return False
            conn.execute(
                "INSERT INTO activity_events (ts, kind, level, title, detail, path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), kind, level, _clip(title, 200), _clip(detail, 500),
                 _clip(path, 1000)),
            )
            with _prune_lock:
                _inserts_since_prune += 1
                due = _inserts_since_prune >= PRUNE_EVERY
                if due:
                    _inserts_since_prune = 0
            if due:
                prune(conn)
            conn.commit()
        return True
    except Exception as e:
        app_logger.debug(f"Could not record activity event: {e}")
        return False


def list_events(kind=None, limit=50, before_id=None):
    """Newest first. ``kind`` may be one of KINDS; ``errors`` is a kind.

    Returns None when the table cannot be read, so "no events yet" ([]) stays
    distinguishable from a failure.
    """
    try:
        limit = max(1, min(int(limit), MAX_LIMIT))
        where, args = [], []
        if kind:
            where.append("kind = ?")
            args.append(kind)
        if before_id:
            where.append("id < ?")
            args.append(int(before_id))
        sql = "SELECT id, ts, kind, level, title, detail, path FROM activity_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        from core.database import db_conn

        with db_conn() as conn:
            if not conn:
                return None
            return [dict(r) for r in conn.execute(sql, args + [limit]).fetchall()]
    except Exception as e:
        app_logger.error(f"Could not read activity events: {e}")
        return None


def count_errors(since_hours=24):
    """Errors in the last ``since_hours``, for the filter badge."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        from core.database import db_conn

        with db_conn() as conn:
            if not conn:
                return 0
            return conn.execute(
                "SELECT COUNT(*) FROM activity_events WHERE kind = ? AND ts >= ?",
                (KIND_ERROR, cutoff),
            ).fetchone()[0]
    except Exception:
        return 0


def clear_events(kind=None):
    """Delete every event, or only one ``kind``. Returns the number removed, or None on failure."""
    try:
        from core.database import db_conn

        with db_conn() as conn:
            if not conn:
                return None
            if kind:
                cur = conn.execute("DELETE FROM activity_events WHERE kind = ?", (kind,))
            else:
                cur = conn.execute("DELETE FROM activity_events")
            conn.commit()
            return cur.rowcount
    except Exception as e:
        app_logger.error(f"Could not clear activity events: {e}")
        return None
