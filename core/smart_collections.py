"""Smart collections: saved metadata filters that are re-evaluated on every view.

Nothing is materialised -- a collection is a name, a match mode, a sort and a
list of rules, and its members are whatever ``file_index`` holds right now. The
comic-file restriction and the per-user folder scope come from the Library's own
``_build_metadata_where``; only the rule clauses are built here.
"""

import json
import sqlite3
import time

from core.database import _build_metadata_where, db_conn, current_user_id

MATCH_MODES = ("all", "any")

SORTS = {
    "newest": "first_indexed_at DESC, name COLLATE NOCASE",
    "oldest": "first_indexed_at ASC, name COLLATE NOCASE",
    "alpha": ("ci_series COLLATE NOCASE, CAST(ci_number AS INTEGER), ci_number,"
              " name COLLATE NOCASE"),
    "year": ("CAST(ci_year AS INTEGER) DESC, ci_series COLLATE NOCASE,"
             " CAST(ci_number AS INTEGER)"),
}

# field -> (kind, column-or-tag-kind, allowed ops)
_TEXT_OPS = ("is", "is_not", "contains")
_TAG_OPS = ("is", "is_not")
FIELDS = {
    "publisher": ("text", "ci_publisher", _TEXT_OPS),
    "series": ("text", "ci_series", _TEXT_OPS),
    "year": ("year", "ci_year", ("is", "before", "after")),
    "writer": ("tag", "writer", _TAG_OPS),
    "penciller": ("tag", "penciller", _TAG_OPS),
    "character": ("tag", "characters", _TAG_OPS),
    "genre": ("tag", "genre", _TAG_OPS),
    "read_status": ("read", None, ("is",)),
    "added": ("added", "first_indexed_at", ("within_days",)),
}
MAX_RULES = 20
MAX_NAME = 80


def _clean_rule(raw):
    if not isinstance(raw, dict):
        raise ValueError("Invalid rule")
    field = raw.get("field")
    op = raw.get("op")
    value = str(raw.get("value", "")).strip()
    if field not in FIELDS or op not in FIELDS[field][2]:
        raise ValueError(f"Invalid rule: {field} {op}")
    kind = FIELDS[field][0]
    if kind == "read" and value not in ("read", "unread"):
        raise ValueError("Read status must be read or unread")
    if kind in ("year", "added"):
        if not value.isdigit():
            raise ValueError(f"{field} needs a whole number")
    elif not value:
        raise ValueError(f"{field} needs a value")
    return {"field": field, "op": op, "value": value}


def validate_definition(data):
    """(name, match, sort, rules) from a request body; ValueError if unusable."""
    data = data or {}
    name = str(data.get("name", "")).strip()
    if not name or len(name) > MAX_NAME:
        raise ValueError("Name is required (80 characters at most)")
    match = data.get("match", "all")
    sort = data.get("sort", "newest")
    if match not in MATCH_MODES:
        raise ValueError("Invalid match mode")
    if sort not in SORTS:
        raise ValueError("Invalid sort")
    raw_rules = data.get("rules") or []
    if not isinstance(raw_rules, list) or len(raw_rules) > MAX_RULES:
        raise ValueError("Invalid rules")
    return name, match, sort, [_clean_rule(r) for r in raw_rules]


def _row(r):
    return {"id": r["id"], "name": r["name"], "match": r["match"],
            "sort": r["sort"], "rules": json.loads(r["rules"] or "[]")}


def list_collections(user_id=None):
    uid = current_user_id() if user_id is None else user_id
    with db_conn() as conn:
        if not conn:
            return []
        rows = conn.execute(
            "SELECT * FROM smart_collections WHERE user_id = ?"
            " ORDER BY name COLLATE NOCASE", (uid,)).fetchall()
        return [_row(r) for r in rows]


def get_collection(coll_id, user_id=None):
    uid = current_user_id() if user_id is None else user_id
    with db_conn() as conn:
        if not conn:
            return None
        r = conn.execute(
            "SELECT * FROM smart_collections WHERE id = ? AND user_id = ?",
            (coll_id, uid)).fetchone()
        return _row(r) if r else None


def save_collection(data, coll_id=None, user_id=None):
    """Create (coll_id None) or update. Returns the id, or None if not found.

    ValueError for a bad definition or a duplicate name.
    """
    uid = current_user_id() if user_id is None else user_id
    name, match, sort, rules = validate_definition(data)
    with db_conn() as conn:
        if not conn:
            raise RuntimeError("database unavailable")
        try:
            if coll_id is None:
                cur = conn.execute(
                    "INSERT INTO smart_collections (user_id, name, match, sort, rules)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (uid, name, match, sort, json.dumps(rules)))
                conn.commit()
                return cur.lastrowid
            cur = conn.execute(
                "UPDATE smart_collections SET name=?, match=?, sort=?, rules=?"
                " WHERE id = ? AND user_id = ?",
                (name, match, sort, json.dumps(rules), coll_id, uid))
            conn.commit()
            return coll_id if cur.rowcount else None
        except sqlite3.IntegrityError:
            conn.rollback()
            raise ValueError("You already have a collection with that name")


def delete_collection(coll_id, user_id=None):
    uid = current_user_id() if user_id is None else user_id
    with db_conn() as conn:
        if not conn:
            return False
        cur = conn.execute(
            "DELETE FROM smart_collections WHERE id = ? AND user_id = ?",
            (coll_id, uid))
        conn.commit()
        return cur.rowcount > 0


def _rule_sql(rule, uid, now):
    field, op, value = rule["field"], rule["op"], rule["value"]
    kind, col, _ = FIELDS[field]
    if kind == "text":
        if op == "contains":
            return f"LOWER(COALESCE({col},'')) LIKE ? ESCAPE '\\'", [
                "%" + value.lower().replace("\\", "\\\\").replace("%", "\\%")
                .replace("_", "\\_") + "%"]
        eq = f"LOWER(COALESCE({col},'')) = ?"
        return (eq if op == "is" else "NOT " + eq), [value.lower()]
    if kind == "tag":
        sql = ("EXISTS (SELECT 1 FROM file_metadata_tags t WHERE t.file_path ="
               " file_index.path AND t.kind = ? AND t.value = ? COLLATE NOCASE)")
        return (sql if op == "is" else "NOT " + sql), [col, value]
    if kind == "year":
        sym = {"is": "=", "before": "<", "after": ">"}[op]
        return f"CAST(ci_year AS INTEGER) {sym} ?", [int(value)]
    if kind == "read":
        sql = ("EXISTS (SELECT 1 FROM issues_read r WHERE r.issue_path ="
               " file_index.path AND r.user_id = ?)")
        return (sql if value == "read" else "NOT " + sql), [uid]
    return "first_indexed_at >= ?", [now - int(value) * 86400]  # added


def collection_where(coll, prefixes=None, user_id=None, now=None):
    """(where_sql, params): the Library's base clause plus this collection's rules."""
    uid = current_user_id() if user_id is None else user_id
    where, params = _build_metadata_where({}, prefixes)
    rules = coll["rules"]
    if not rules:
        return where + " AND 1=0", params
    now = time.time() if now is None else now
    parts = [_rule_sql(r, uid, now) for r in rules]
    joiner = " AND " if coll["match"] == "all" else " OR "
    return (where + " AND (" + joiner.join(p[0] for p in parts) + ")",
            params + [x for p in parts for x in p[1]])


def count_matches(coll, prefixes=None, user_id=None):
    where, params = collection_where(coll, prefixes, user_id)
    with db_conn() as conn:
        if not conn:
            return 0
        return conn.execute(
            "SELECT COUNT(*) FROM file_index " + where, params).fetchone()[0]


def collection_issues(coll, offset=0, limit=60, prefixes=None, user_id=None):
    where, params = collection_where(coll, prefixes, user_id)
    with db_conn() as conn:
        if not conn:
            return [], 0
        total = conn.execute(
            "SELECT COUNT(*) FROM file_index " + where, params).fetchone()[0]
        rows = conn.execute(
            "SELECT name, path, ci_title, ci_series, ci_number, ci_year,"
            " ci_publisher FROM file_index " + where +
            " ORDER BY " + SORTS[coll["sort"]] + " LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
        return [{
            "name": r["name"], "path": r["path"], "title": r["ci_title"] or "",
            "series": r["ci_series"] or "", "number": r["ci_number"] or "",
            "year": r["ci_year"] or "", "publisher": r["ci_publisher"] or "",
        } for r in rows], total
