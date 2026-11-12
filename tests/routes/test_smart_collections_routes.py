"""Routes: smart collections (/api/smart-collections) and the gap report (/api/gaps; /gaps redirects to Wanted)."""
import time

import pytest


def _seed(conn, name, **ci):
    cols = {"name": name, "path": "/data/" + name, "type": "file", "size": 1,
            "parent": "/data", "has_comicinfo": 1, "ci_publisher": "Image",
            "ci_series": "Saga", "ci_number": "1", "ci_year": "2024",
            "first_indexed_at": time.time()}
    cols.update(ci)
    conn.execute(f"INSERT INTO file_index ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 list(cols.values()))
    conn.commit()


@pytest.fixture
def library(db_connection):
    from core.database import _backfill_file_metadata_tags
    _seed(db_connection, "Saga 1.cbz", ci_writer="Brian K. Vaughan")
    _seed(db_connection, "Saga 2.cbz", ci_number="2", ci_year="2023", ci_writer="Brian K. Vaughan")
    _seed(db_connection, "Batman 1.cbz", ci_publisher="DC", ci_series="Batman", ci_genre="Superhero",
          first_indexed_at=time.time() - 40 * 86400)
    db_connection.execute(
        "INSERT INTO issues_read (user_id, issue_path) VALUES (1, '/data/Saga 1.cbz')")
    db_connection.commit()
    _backfill_file_metadata_tags(db_connection)
    return db_connection


def _create(client, rules, **extra):
    body = {"name": "C", "match": "all", "sort": "alpha", "rules": rules}
    body.update(extra)
    return client.post("/api/smart-collections", json=body)


def _count(client, rules, match="all"):
    cid = _create(client, rules, match=match, name="x" + str(time.time())).get_json()["collection"]["id"]
    return client.get(f"/api/smart-collections/{cid}/issues").get_json()["total"]


class TestCrud:
    def test_create_list_update_delete(self, client, library):
        r = _create(client, [{"field": "publisher", "op": "is", "value": "image"}])
        assert r.status_code == 201
        coll = r.get_json()["collection"]
        assert coll["count"] == 2
        listed = client.get("/api/smart-collections").get_json()["collections"]
        assert [c["name"] for c in listed] == ["C"]
        r = client.put(f"/api/smart-collections/{coll['id']}", json={
            "name": "D", "match": "any", "sort": "year",
            "rules": [{"field": "publisher", "op": "is", "value": "DC"}]})
        assert r.get_json()["collection"]["count"] == 1
        assert client.delete(f"/api/smart-collections/{coll['id']}").status_code == 200
        assert client.delete(f"/api/smart-collections/{coll['id']}").status_code == 404

    def test_duplicate_name_and_bad_rules_rejected(self, client, library):
        assert _create(client, []).status_code == 201
        assert _create(client, []).status_code == 400
        for bad in ([{"field": "nope", "op": "is", "value": "x"}],
                    [{"field": "year", "op": "is", "value": "abc"}],
                    [{"field": "read_status", "op": "is", "value": "maybe"}],
                    [{"field": "publisher", "op": "before", "value": "x"}]):
            assert _create(client, bad, name="n").status_code == 400
        assert _create(client, [], name="").status_code == 400
        assert _create(client, [], name="n", match="some").status_code == 400

    def test_unknown_collection_404(self, client, library):
        assert client.get("/api/smart-collections/999/issues").status_code == 404
        assert client.put("/api/smart-collections/999", json={"name": "a"}).status_code == 404

    def test_collections_are_per_user(self, client, library):
        from core.smart_collections import list_collections, save_collection
        save_collection({"name": "mine", "rules": []}, user_id=2)
        assert list_collections(user_id=2)[0]["name"] == "mine"
        assert client.get("/api/smart-collections").get_json()["collections"] == []


class TestRules:
    def test_rule_fields(self, client, library):
        assert _count(client, [{"field": "year", "op": "before", "value": "2024"}]) == 1
        assert _count(client, [{"field": "writer", "op": "is", "value": "brian k. vaughan"}]) == 2
        assert _count(client, [{"field": "writer", "op": "is_not", "value": "Brian K. Vaughan"}]) == 1
        assert _count(client, [{"field": "genre", "op": "is", "value": "Superhero"}]) == 1
        assert _count(client, [{"field": "series", "op": "contains", "value": "AG"}]) == 2
        assert _count(client, [{"field": "read_status", "op": "is", "value": "read"}]) == 1
        assert _count(client, [{"field": "read_status", "op": "is", "value": "unread"}]) == 2
        assert _count(client, [{"field": "added", "op": "within_days", "value": "30"}]) == 2

    def test_match_all_vs_any_and_empty(self, client, library):
        rules = [{"field": "publisher", "op": "is", "value": "DC"},
                 {"field": "year", "op": "is", "value": "2023"}]
        assert _count(client, rules, "all") == 0
        assert _count(client, rules, "any") == 2
        assert _count(client, []) == 0

    def test_like_wildcards_in_contains_are_literal(self, client, library):
        assert _count(client, [{"field": "series", "op": "contains", "value": "%"}]) == 0

    def test_folder_scope_is_respected(self, library):
        from core.smart_collections import count_matches
        coll = {"rules": [{"field": "year", "op": "after", "value": "1"}], "match": "all", "sort": "alpha"}
        assert count_matches(coll, prefixes=None, user_id=1) == 3
        assert count_matches(coll, prefixes=[], user_id=1) == 0
        assert count_matches(coll, prefixes=["/elsewhere"], user_id=1) == 0


class TestPages:
    def test_pages_render(self, client, library):
        assert client.get("/smart-collections").status_code == 200

    def test_gap_report_redirects_to_wanted_by_series(self, client, library):
        """The gap report is Wanted's By series view now; bookmarks land there."""
        resp = client.get("/gaps")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/wanted?view=series")


class TestGaps:
    def _wanted(self, conn, sid, name, numbers, released_total):
        conn.execute("INSERT OR IGNORE INTO series (id, name) VALUES (?, ?)", (sid, name))
        for i in range(1, released_total + 1):
            conn.execute("INSERT INTO issues (id, series_id, number) VALUES (?, ?, ?)",
                         (sid * 1000 + i, sid, str(i)))
        for n in numbers:
            conn.execute(
                "INSERT INTO wanted_issues (series_id, issue_id, issue_number, series_name)"
                " VALUES (?, ?, ?, ?)", (sid, sid * 1000 + int(n), str(n), name))
        conn.commit()

    def test_gap_report_groups_and_collapses(self, client, db_connection):
        self._wanted(db_connection, 1, "Batman", [4, 7, 8, 9, 12], 87)
        self._wanted(db_connection, 2, "Saga", [31], 70)
        d = client.get("/api/gaps").get_json()
        assert d["missing_total"] == 6
        b = d["gaps"][0]
        assert b["name"] == "Batman" and b["ranges"] == ["#4", "#7–#9", "#12"]
        assert (b["owned"], b["total"]) == (82, 87)
        assert b["check_url"] == "/api/series/1/check-missing"
        assert d["search_all_url"] == "/api/run-getcomics-now"

    def test_empty_report(self, client, db_connection):
        assert client.get("/api/gaps").get_json()["gaps"] == []

    def test_missing_ranges_non_numeric(self):
        from core.gaps import missing_ranges
        assert missing_ranges(["3", "1", "2", "1.MU", "10"]) == ["#1–#3", "#10", "#1.MU"]
