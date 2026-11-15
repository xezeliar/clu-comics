"""Per-issue roles in a reading list: stored, synced, and kept when set by hand."""

from unittest.mock import MagicMock


def _roles(db_connection, list_id):
    return {
        r[0]: (r[1], r[2])
        for r in db_connection.execute(
            "SELECT issue_number, role, role_manual FROM reading_list_entries "
            "WHERE reading_list_id = ?", (list_id,),
        ).fetchall()
    }


def _ids(db_connection, list_id):
    return {
        r[0]: r[1]
        for r in db_connection.execute(
            "SELECT issue_number, id FROM reading_list_entries WHERE reading_list_id = ?",
            (list_id,),
        ).fetchall()
    }


def test_import_stores_role_and_ignores_unknown(db_connection):
    from core.database import add_reading_list_entries, create_reading_list

    list_id = create_reading_list("Bad Seeds", source="metron://reading-list/1")
    add_reading_list_entries(list_id, [
        {"series": "B", "issue_number": "1", "role": "prologue"},
        {"series": "B", "issue_number": "2", "role": "bogus"},
        {"series": "B", "issue_number": "3"},
    ])
    assert _roles(db_connection, list_id) == {
        "1": ("prologue", 0), "2": (None, 0), "3": (None, 0)}


def test_sync_updates_source_roles_but_keeps_manual_ones(db_connection):
    from core.database import (
        add_reading_list_entries, create_reading_list,
        set_entry_roles, sync_reading_list_entries,
    )

    list_id = create_reading_list("Bad Seeds", source="metron://reading-list/1")
    add_reading_list_entries(list_id, [
        {"series": "B", "issue_number": "1", "role": "core"},
        {"series": "B", "issue_number": "2", "role": "core"},
        {"series": "B", "issue_number": "3", "role": "tie_in"},
    ])
    ids = _ids(db_connection, list_id)
    assert set_entry_roles(list_id, [ids["2"]], "epilogue") == 1
    # Clearing is a manual choice too.
    assert set_entry_roles(list_id, [ids["3"]], None) == 1

    sync_reading_list_entries(list_id, [
        {"series": "B", "issue_number": "1", "role": "prologue"},
        {"series": "B", "issue_number": "2", "role": "core"},
        {"series": "B", "issue_number": "3", "role": "tie_in"},
        {"series": "B", "issue_number": "4", "role": "tie_in"},
    ])
    assert _roles(db_connection, list_id) == {
        "1": ("prologue", 0),
        "2": ("epilogue", 1),
        "3": (None, 1),
        "4": ("tie_in", 0),
    }


def test_set_entry_roles_only_touches_its_own_list(db_connection):
    from core.database import add_reading_list_entries, create_reading_list, set_entry_roles

    a = create_reading_list("A")
    b = create_reading_list("B")
    add_reading_list_entries(a, [{"series": "S", "issue_number": "1"}])
    add_reading_list_entries(b, [{"series": "S", "issue_number": "1"}])
    other = _ids(db_connection, b)["1"]
    assert set_entry_roles(a, [other], "core") == 0
    assert _roles(db_connection, b) == {"1": (None, 0)}


def test_metron_issue_type_maps_to_role():
    from core.reading_list_sync import metron_issue_to_entry, metron_role

    assert [metron_role(t) for t in
            ("Prologue", "Core Issue", "Tie-In", "Epilogue", "", None, "Other")] == \
        ["prologue", "core", "tie_in", "epilogue", None, None, None]
    loader = MagicMock()
    loader.match_file.return_value = None
    issue = {"id": 7, "number": "1", "series": {"name": "Batman"}}
    assert metron_issue_to_entry(issue, loader, "Tie-In")["role"] == "tie_in"
    assert metron_issue_to_entry(issue, loader)["role"] is None
