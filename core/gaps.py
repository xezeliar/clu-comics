"""Gap report: which issue numbers each mapped series is missing.

Nothing new decides "missing". The Wanted cache (``wanted_issues``) already
holds every released, unowned issue of each mapped series; this groups it by
series. Searching goes through the existing per-series check-missing and
GetComics sweep routes.
"""

import re
from collections import defaultdict

from core.database import db_conn, get_cached_wanted_issues


def _split(numbers):
    ints, other = set(), []
    for n in numbers:
        s = str(n).strip()
        if re.fullmatch(r"\d+", s):
            ints.add(int(s))
        elif s and s not in other:
            other.append(s)
    return sorted(ints), other


def missing_ranges(numbers):
    """['#4', '#6–#14', '#22', '#1.MU']: consecutive numbers collapse to a range."""
    ints, other = _split(numbers)
    out, i = [], 0
    while i < len(ints):
        j = i
        while j + 1 < len(ints) and ints[j + 1] == ints[j] + 1:
            j += 1
        out.append(f"#{ints[i]}" if i == j else f"#{ints[i]}–#{ints[j]}")
        i = j + 1
    return out + [f"#{o}" for o in other]


def get_gaps(series_id=None):
    """Series with missing issues, most missing first.

    [{series_id, name, volume, missing, ranges, total, owned}]
    """
    groups = defaultdict(list)
    names = {}
    for w in get_cached_wanted_issues():
        if series_id is not None and w["series_id"] != series_id:
            continue
        if w["issue_number"] in (None, ""):
            continue
        groups[w["series_id"]].append(w["issue_number"])
        names[w["series_id"]] = (w["series_name"], w["series_volume"])
    if not groups:
        return []
    totals = {}
    with db_conn() as conn:
        if conn:
            marks = ",".join("?" * len(groups))
            for r in conn.execute(
                "SELECT series_id, COUNT(*) AS n FROM issues WHERE series_id IN ("
                + marks + ") AND (store_date <= date('now') OR store_date IS NULL)"
                " GROUP BY series_id", list(groups)):
                totals[r["series_id"]] = r["n"]
    out = []
    for sid, nums in groups.items():
        total = max(totals.get(sid, 0), len(nums))
        out.append({
            "series_id": sid, "name": names[sid][0], "volume": names[sid][1],
            "missing": len(nums), "ranges": missing_ranges(nums),
            "total": total, "owned": total - len(nums),
        })
    out.sort(key=lambda g: ((g["name"] or "").lower(), g["series_id"]))
    return out
