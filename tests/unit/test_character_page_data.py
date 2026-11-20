"""core/creators.py character page data: Timeline order, creators, reading lists, Information."""

import pytest

from core import creators


def _file(conn, parent, name, series, number, year, **ci):
    path = f"{parent}/{name}"
    cols = {"name": name, "path": path, "type": "file", "size": 1, "parent": parent,
            "has_comicinfo": 1, "ci_publisher": "DC", "ci_series": series,
            "ci_number": str(number), "ci_year": year, "ci_characters": "Batman"}
    cols.update(ci)
    conn.execute(
        f"INSERT INTO file_index ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        list(cols.values()))
    return path


@pytest.fixture
def lib(db_connection, monkeypatch):
    from core.database import _backfill_file_metadata_tags
    monkeypatch.setattr("helpers.library.get_library_roots", lambda: ["/data"])
    c = db_connection
    _file(c, "/data/B", "B10.cbz", "Batman", 10, 2020, ci_writer="Ann", ci_penciller="Ann")
    _file(c, "/data/B", "B2.cbz", "Batman", 2, 2020, ci_penciller="Ann", ci_cvid=55)
    _file(c, "/data/D", "D1.cbz", "Detective", 1, 2019, ci_letterer="Lee", ci_inker="Ann")
    _file(c, "/data/U", "U1.cbz", "Undated", 1, 0, ci_characters="Batman, Robin", ci_teams="Bat-Family")
    _file(c, "/data/S", "S1.cbz", "Secret", 1, 2001)
    _backfill_file_metadata_tags(c)
    c.execute("INSERT INTO issues_read (issue_path, user_id) VALUES ('/data/D/D1.cbz', 1)")
    c.commit()
    return c


def test_timeline_order_and_read_next(lib):
    d = creators.entity_details("characters", "Batman")
    assert [i["name"] for i in d["issues"]] == ["S1.cbz", "D1.cbz", "B2.cbz", "B10.cbz", "U1.cbz"]
    assert d["issues"][d["next_index"]]["name"] == "S1.cbz"
    assert d["publisher"] == "DC"


def test_folder_scope_hides_other_folders(lib):
    d = creators.entity_details("characters", "Batman", prefixes=["/data/B", "/data/D", "/data/U"])
    assert "S1.cbz" not in [i["name"] for i in d["issues"]]
    assert d["issues"][d["next_index"]]["name"] == "B2.cbz"  # D1 is read


def test_creators_ranked_with_main_role(lib):
    d = creators.entity_details("characters", "Batman")
    # Ann: 3 issues; penciller on 2, writer on 1, inker on 1.
    assert d["creators"][0] == {"name": "Ann", "n": 3, "kind": "penciller", "role": "Penciller"}
    assert d["creators"][1]["name"] == "Lee" and d["creators"][1]["kind"] == "letterer"


def test_reading_lists_count_only_this_characters_issues(lib):
    lib.execute("INSERT INTO reading_lists (id, name, source) VALUES (1, 'L', 'manual'), (2, 'Other', 'manual')")
    for path in ("/data/B/B2.cbz", "/data/B/B10.cbz", "/nowhere.cbz"):
        lib.execute("INSERT INTO reading_list_entries (reading_list_id, matched_file_path) VALUES (1, ?)", (path,))
    lib.execute("INSERT INTO reading_list_entries (reading_list_id, manual_override_path) VALUES (2, '/data/S/S1.cbz')")
    lib.commit()
    lists = creators.entity_details("characters", "Batman", prefixes=["/data/B", "/data/D", "/data/U"])["lists"]
    assert [(l["name"], l["hits"], l["total"]) for l in lists] == [("L", 2, 3)]


def test_information_merges_and_links(lib):
    lib.execute("INSERT INTO character_teams VALUES ('batman', 'bat-family', 'Bat-Family', 1)")
    lib.commit()
    issues = creators.entity_details("characters", "Batman")["issues"]
    profile = {"metron": {"desc": None, "gcd_id": "x", "creators": ["Ann", "Bob Kane"]},
               "cv": {"summary": "Short bio.", "teams": ["bat-family", "JLA"],
                      "friends": [{"id": 1, "name": "Robin"}, {"id": 2, "name": "Alfred"}],
                      "enemies": [], "first_issue": {"id": 55, "name": "x", "number": "2"}}}
    info = creators.character_info("Batman", profile, issues)
    assert info["bio"] == "Short bio."
    assert info["teams"] == [{"name": "Bat-Family", "n": 1}, {"name": "JLA", "n": 0}]
    assert info["allies"] == [{"name": "Robin", "n": 1}, {"name": "Alfred", "n": 0}]
    assert info["created_by"] == [{"name": "Ann", "n": 3}, {"name": "Bob Kane", "n": 0}]
    assert info["first_appearance"]["issue"]["name"] == "B2.cbz"
    assert info["first_owned"]["name"] == "S1.cbz"
    assert info["links"] == []  # a non-numeric GCD id makes no link


def test_information_without_profile(lib):
    info = creators.character_info("Batman", None, [])
    assert info["bio"] is None and info["first_appearance"] is None and not info["has_metron"]


def test_team_information(lib):
    issues = creators.entity_details("teams", "Bat-Family")["issues"]
    profile = {"metron": {"desc": "Gotham's heroes.", "creators": ["Ann"]},
               "cv": {"friends": [{"id": 1, "name": "Robin"}], "enemies": [{"id": 2, "name": "Bane"}],
                      "members": [{"id": 3, "name": "Robin"}, {"id": 4, "name": "Oracle"}],
                      "disbanded_in": [{"id": 9, "name": "Finale"}]}}
    info = creators.team_info("Bat-Family", profile, issues)
    assert info["bio"] == "Gotham's heroes."
    assert info["created_by"] == [{"name": "Ann", "n": 3}]
    assert info["allies"] == [{"name": "Robin", "n": 1}]
    assert info["enemies"] == [{"name": "Bane", "n": 0}]
    assert info["disbanded_in"] == [{"name": "Finale", "issue": None}]
    assert info["cv_members"] == ["Robin", "Oracle"]
    assert info["first_owned"]["name"] == "U1.cbz"
