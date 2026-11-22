"""Routes: the gap report (/api/gaps; /gaps redirects to Wanted)."""


class TestPages:
    def test_gap_report_redirects_to_wanted_by_series(self, client):
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
