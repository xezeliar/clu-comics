"""Wanted marks: the per-issue opt-in for a Not monitored series."""
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import core.database as db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE issue_wanted_marks (series_id INTEGER NOT NULL, issue_number TEXT NOT NULL,"
        " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (series_id, issue_number))"
    )
    return c


def test_mark_and_unmark_round_trip():
    conn = _conn()

    @contextmanager
    def fake():
        yield conn

    with patch.object(db, "db_conn", fake):
        assert db.set_wanted_marks(1, [3, "4"], True)
        assert db.set_wanted_marks(1, ["3"], True)  # idempotent
        assert db.get_wanted_marks(1) == {"3", "4"}
        assert db.get_wanted_marks(2) == set()
        assert db.set_wanted_marks(1, ["3"], False)
        assert db.get_wanted_marks(1) == {"4"}
