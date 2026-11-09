"""Bulk Unsubscribe clears the mapped folder and nothing else."""
from core.database import get_db_connection


def _add(sid, path):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO series (id, name, mapped_path) VALUES (?, ?, ?)",
        (sid, f"Series {sid}", path),
    )
    conn.commit()
    conn.close()


def _mapped(sid):
    conn = get_db_connection()
    row = conn.execute("SELECT mapped_path, name FROM series WHERE id = ?", (sid,)).fetchone()
    conn.close()
    return row["mapped_path"], row["name"]


class TestRemoveSeriesMappingsBulk:
    def test_clears_only_the_selected_series(self, db_connection):
        from core.database import remove_series_mappings_bulk

        _add(9001, "/lib/a")
        _add(9002, "/lib/b")
        _add(9003, "/lib/c")
        assert remove_series_mappings_bulk([9001, "9002", "bad"]) == 2
        assert _mapped(9001) == (None, "Series 9001")  # row kept, just unmapped
        assert _mapped(9002)[0] is None
        assert _mapped(9003)[0] == "/lib/c"

    def test_already_unmapped_series_are_not_counted(self, db_connection):
        from core.database import remove_series_mappings_bulk

        _add(9010, None)
        assert remove_series_mappings_bulk([9010]) == 0

    def test_empty_input(self, db_connection):
        from core.database import remove_series_mappings_bulk

        assert remove_series_mappings_bulk([]) == 0
