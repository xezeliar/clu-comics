"""The series page header: banner art and how much of the run is owned.

Things that look arbitrary and are not:

* **The banner is folder art, never the cover.** The series folder's own
  ``header`` art, then its publisher folder's (the parent), then nothing. No
  provider supplies banners, and a 2:3 cover cropped to a strip is unreadable.
  A parent that is a library root is not a publisher, so it is skipped.
* **Past ``RUN_STRIP_MAX`` issues the strip gives way to ranges**
  (``core.gaps.missing_ranges``): 200 cells are a texture, not a list.
"""

import os

from core import folder_art
from core.creators import _issue_sort_key

RUN_STRIP_MAX = 60


def banner_url(mapped_path):
    """URL of the series' banner art, or None when neither folder has any."""
    if not mapped_path:
        return None
    url = folder_art.art_url(mapped_path, "header")
    if url:
        return url
    from helpers.library import is_library_root

    parent = os.path.dirname(mapped_path.rstrip("/\\"))
    if parent and parent != mapped_path and not is_library_root(parent):
        return folder_art.art_url(parent, "header")
    return None


def run_summary(numbers, found, missing):
    """Owned/missing counts and the per-issue strip for the released run.

    ``numbers`` are the released issue numbers, ``found`` and ``missing`` sets
    of the owned and missing ones (an issue marked by hand is neither).
    ``cells`` is None past ``RUN_STRIP_MAX``, which tells the page to show
    ranges instead.
    """
    ordered = sorted(dict.fromkeys(numbers), key=_issue_sort_key)
    owned = sum(1 for n in ordered if n in found)
    n_missing = sum(1 for n in ordered if n in missing)
    cells = None
    if len(ordered) <= RUN_STRIP_MAX:
        cells = [{"number": n,
                  "state": "owned" if n in found else "miss" if n in missing else "marked"}
                 for n in ordered]
    return {
        "total": len(ordered),
        "owned": owned,
        "missing": n_missing,
        "complete": bool(ordered) and n_missing == 0,
        "cells": cells,
    }
