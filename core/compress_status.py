"""Which comics are being compressed right now.

Auto-compress runs in ``monitor.py``, a separate process from the web worker,
and a manual compress runs in a subprocess of its own, so the answer has to live
somewhere all of them can see. Each running compress leaves a small marker file
in ``<CONFIG_DIR>/compressing/``; the File Manager reads them to badge the file
and ``/move`` reads them to refuse moving it half-rewritten.

A marker is trusted only while the process that wrote it is alive (and for a
bounded time, in case a pid is reused), so a crash cannot leave a file
"compressing" forever.
"""

import hashlib
import json
import os
import time

from core.app_logging import app_logger
from core.config import get_config_dir

# A compress that outlives this is not running any more, whatever its pid says.
MAX_MARKER_AGE = 6 * 3600


def _marker_dir():
    return os.path.join(get_config_dir(), "compressing")


def _norm(path):
    return os.path.normpath(path)


def _marker_path(path):
    digest = hashlib.md5(_norm(path).encode("utf-8", "surrogateescape")).hexdigest()
    return os.path.join(_marker_dir(), digest + ".json")


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True  # exists, just not ours
    except (OSError, ValueError, TypeError):
        return False
    return True


def begin(path):
    """Mark ``path`` as being compressed. Never raises: a status marker must not
    be able to stop the compress it describes."""
    try:
        os.makedirs(_marker_dir(), exist_ok=True)
        marker = _marker_path(path)
        tmp = marker + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"path": _norm(path), "pid": os.getpid(), "started": time.time()}, f)
        os.replace(tmp, marker)
    except Exception as e:
        app_logger.debug(f"compress status: could not mark {path}: {e}")


def end(path):
    """Clear the marker for ``path``. Never raises."""
    try:
        os.remove(_marker_path(path))
    except FileNotFoundError:
        pass
    except Exception as e:
        app_logger.debug(f"compress status: could not clear {path}: {e}")


def compressing_paths():
    """Normalised paths of every comic being compressed now (stale markers are
    dropped as they are found)."""
    found = set()
    try:
        names = os.listdir(_marker_dir())
    except OSError:
        return found
    now = time.time()
    for name in names:
        if not name.endswith(".json"):
            continue
        marker = os.path.join(_marker_dir(), name)
        try:
            with open(marker, "r", encoding="utf-8") as f:
                info = json.load(f)
            live = _pid_alive(info["pid"]) and now - float(info["started"]) < MAX_MARKER_AGE
            if live:
                found.add(_norm(info["path"]))
                continue
        except Exception:
            pass  # unreadable marker: treat as stale
        try:
            os.remove(marker)
        except OSError:
            pass
    return found


def is_compressing(path):
    return _norm(path) in compressing_paths()


def is_busy(path):
    """True if ``path`` is being compressed, or is a folder holding a comic that is."""
    target = _norm(path)
    prefix = target + os.sep
    return any(p == target or p.startswith(prefix) for p in compressing_paths())


def annotate_files(directory, files):
    """``files`` (``{"name", "size"}`` dicts) with ``compressing: True`` on each one
    being compressed. Returns a new list when anything changed and never mutates
    ``files``, which may be the cached listing."""
    busy = compressing_paths()
    if not busy:
        return files
    base = _norm(directory)
    out = []
    for f in files:
        if isinstance(f, dict) and _norm(os.path.join(base, f.get("name", ""))) in busy:
            f = dict(f, compressing=True)
        out.append(f)
    return out
