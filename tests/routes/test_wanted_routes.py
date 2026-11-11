"""The Wanted page's per-issue state, Search and Ignore (core/wanted_state.py).

An issue's state is the newest download_run_items row for it; no row means
"Not searched yet". Ignore is issue_manual_status 'skipped'.
"""

import json
import re
from unittest.mock import MagicMock, patch

import pytest

from core.wanted_state import derive_state, issue_states, parse_issues


def _run(conn, truncated=0):
    cur = conn.execute(
        "INSERT INTO download_runs (kind, started_at, status, items_truncated)"
        " VALUES ('getcomics', '2026-11-09 03:00:00', 'ok', ?)", (truncated,))
    return cur.lastrowid


def _item(conn, run_id, sid, num, outcome, detail=None, download_id=None,
          download_status=None, provider="getcomics", when="2026-11-09 03:05:00"):
    conn.execute(
        "INSERT INTO download_run_items (run_id, series_id, series_name, issue_number,"
        " provider, outcome, detail, download_id, download_status, updated_at)"
        " VALUES (?, ?, 'Batman', ?, ?, ?, ?, ?, ?, ?)",
        (run_id, sid, num, provider, outcome, detail, download_id, download_status, when))


class TestDeriveState:
    def test_no_row_is_not_searched(self):
        assert derive_state(None) == {"code": "not_searched", "label": "Not searched yet"}

    def test_not_found_keeps_the_why(self):
        s = derive_state({"outcome": "no_match", "detail": "Batman #4 (2019): wrong year",
                          "provider": "getcomics", "when": "2026-11-09 03:05:00"}, tries=3)
        assert (s["code"], s["tries"], s["detail"]) == ("not_found", 3, "Batman #4 (2019): wrong year")

    def test_queued_is_waiting_in_downloads(self):
        s = derive_state({"outcome": "queued", "download_status": "queued"})
        assert (s["code"], s["label"]) == ("waiting", "Waiting in Downloads")

    def test_live_progress_is_downloading(self):
        s = derive_state({"outcome": "queued", "download_status": "queued"},
                         progress={"status": "in_progress", "progress": 64})
        assert (s["code"], s["label"]) == ("downloading", "Downloading 64%")

    @pytest.mark.parametrize("status", ["failed", "interrupted"])
    def test_failed_download(self, status):
        s = derive_state({"outcome": "queued", "download_status": status, "detail": "404"})
        assert (s["code"], s["label"], s["detail"]) == ("failed", "Failed", "404")

    def test_cancelled_is_searchable_again_not_failed(self):
        s = derive_state({"outcome": "queued", "download_status": "cancelled"})
        assert (s["code"], s["label"]) == ("not_searched", "Cancelled")

    def test_search_info_is_carried(self):
        s = derive_state({"outcome": "no_match", "search_info": '{"sources": ["getcomics"]}'})
        assert s["search"] == {"sources": ["getcomics"]}

    def test_unreadable_search_info_is_dropped(self):
        assert "search" not in derive_state({"outcome": "no_match", "search_info": "{oops"})

    def test_downloaded_but_not_filed_is_not_searched_again(self):
        assert derive_state({"outcome": "queued", "download_status": "complete"})["code"] == "waiting"


class TestIssueStates:
    def test_newest_row_wins_and_searches_are_counted(self, db_connection):
        r1, r2 = _run(db_connection), _run(db_connection)
        _item(db_connection, r1, 1, "4", "no_results")
        _item(db_connection, r2, 1, "4", "no_match", detail="closest: 2019 series",
              when="2026-11-10 03:05:00")
        _item(db_connection, r1, 1, "5", "no_results")
        _item(db_connection, r2, 1, "5", "queued", download_id="d1", download_status="failed")
        db_connection.commit()

        states = issue_states()
        assert states[(1, "4")]["code"] == "not_found"
        assert states[(1, "4")]["tries"] == 2
        assert states[(1, "4")]["detail"] == "closest: 2019 series"
        assert states[(1, "4")]["when"] == "2026-11-10 03:05:00"
        assert states[(1, "5")]["code"] == "failed"

    def test_search_info_reaches_the_state(self, db_connection):
        run = _run(db_connection)
        _item(db_connection, run, 1, "4", "no_match")
        db_connection.execute("UPDATE download_run_items SET search_info = ?",
                              ('{"sources": ["getcomics"], "queries": [], "nearest": null}',))
        db_connection.commit()
        assert issue_states()[(1, "4")]["search"]["sources"] == ["getcomics"]

    def test_a_capped_run_counts_only_the_items_it_lists(self, db_connection):
        run = _run(db_connection, truncated=1)
        _item(db_connection, run, 1, "4", "no_results")
        db_connection.commit()

        states = issue_states()
        assert (1, "4") in states
        assert (1, "9") not in states  # searched past the cap: no row, not searched


class TestParseIssues:
    def test_drops_malformed_entries(self):
        got = parse_issues({"issues": [
            {"series_id": "1", "issue_number": "4"}, {"series_id": "x", "issue_number": "5"},
            {"series_id": 2}, "junk", {"series_id": 3, "issue_number": "9" * 41}]})
        assert got == {(1, "4")}

    def test_not_a_list(self):
        assert parse_issues({"issues": "1:4"}) == set() and parse_issues(None) == set()


class TestWantedPageStates:
    @staticmethod
    def _rows(html):
        m = re.search(r'<script type="application/json" id="wantedData">(.*?)</script>', html, re.S)
        assert m, "the Missing section's data is missing"
        return json.loads(m.group(1))

    def _seed(self, app, conn):
        from core.database import save_wanted_issues_for_series
        app.jinja_env.globals["generate_series_slug"] = lambda n, sid, v=None: f"{sid}-slug"
        conn.execute("INSERT OR IGNORE INTO series (id, name) VALUES (1, 'Batman')")
        conn.commit()
        save_wanted_issues_for_series(1, "Batman", 2020, [
            {"id": 10 + int(n), "number": n, "name": None, "store_date": "2024-01-0" + n,
             "cover_date": None, "image": None} for n in ("4", "5")])

    def test_rows_carry_their_state(self, app, client, db_connection):
        self._seed(app, db_connection)
        _item(db_connection, _run(db_connection), 1, "4", "no_results")
        db_connection.commit()

        rows = {r["number"]: r for r in self._rows(client.get("/wanted").get_data(as_text=True))}
        assert rows["4"]["state"]["code"] == "not_found"
        assert rows["5"]["state"] == {"code": "not_searched", "label": "Not searched yet"}

    def test_ignore_moves_an_issue_to_ignored_and_back(self, app, client, db_connection):
        self._seed(app, db_connection)
        body = {"issues": [{"series_id": 1, "issue_number": "4"}]}

        resp = client.post("/api/wanted/ignore", json=body)
        assert resp.get_json() == {"success": True, "count": 1}
        status = db_connection.execute(
            "SELECT status FROM issue_manual_status WHERE series_id = 1 AND issue_number = '4'"
        ).fetchone()[0]
        assert status == "skipped"
        rows = {r["number"]: r["state"]["code"]
                for r in self._rows(client.get("/wanted").get_data(as_text=True))}
        assert rows == {"5": "not_searched", "4": "ignored"}

        with patch("helpers.collection.rebuild_wanted_for_series") as rebuild:
            resp = client.delete("/api/wanted/ignore", json=body)
        assert resp.get_json()["count"] == 1
        rebuild.assert_called_once_with(1)
        assert db_connection.execute("SELECT COUNT(*) FROM issue_manual_status").fetchone()[0] == 0

    def test_bring_back_never_clears_owned(self, client, db_connection):
        from core.database import set_manual_status
        db_connection.execute("INSERT OR IGNORE INTO series (id, name) VALUES (1, 'Batman')")
        db_connection.commit()
        set_manual_status(1, "4", "owned")
        with patch("helpers.collection.rebuild_wanted_for_series"):
            resp = client.delete("/api/wanted/ignore",
                                 json={"issues": [{"series_id": 1, "issue_number": "4"}]})
        assert resp.get_json()["count"] == 0
        assert db_connection.execute("SELECT status FROM issue_manual_status").fetchone()[0] == "owned"

    def test_ignore_needs_issues(self, client, db_connection):
        assert client.post("/api/wanted/ignore", json={}).status_code == 400


class TestWantedSearch:
    def test_starts_a_run_over_exactly_those_issues(self, client):
        with patch.dict("sys.modules", {"app": MagicMock()}), \
                patch("routes.downloads.threading") as mock_threading:
            resp = client.post("/api/wanted/search", json={"issues": [
                {"series_id": 1, "issue_number": "4"}, {"series_id": 2, "issue_number": "7"}]})
        data = resp.get_json()
        assert resp.status_code == 200 and data["count"] == 2
        kwargs = mock_threading.Thread.call_args.kwargs["kwargs"]
        assert kwargs == {"only_issues": {(1, "4"), (2, "7")}, "op_id": data["op_id"]}
        import core.app_state as app_state
        app_state.complete_operation(data["op_id"])

    def test_no_issues_is_400(self, client):
        assert client.post("/api/wanted/search", json={"issues": []}).status_code == 400

    def test_one_wanted_search_at_a_time(self, client):
        import core.app_state as app_state
        scope = app_state.getcomics_sweep_scope(only_issues=True)
        assert app_state.claim_getcomics_sweep(scope)
        try:
            resp = client.post("/api/wanted/search",
                               json={"issues": [{"series_id": 1, "issue_number": "4"}]})
        finally:
            app_state.release_getcomics_sweep(scope)
        assert resp.status_code == 409


class TestWhyPanelTemplate:
    """Provider strings reach the page as text only."""

    def _panel(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "wanted.html")
        src = open(path, encoding="utf-8").read()
        start = src.index("function whyPanel")
        return src[start:src.index("function checkbox", start)]

    def test_renders_search_info_without_innerhtml(self):
        panel = self._panel()
        for key in ("q.sources", "q.queries", "q.nearest"):
            assert key in panel
        assert "innerHTML" not in panel and "insertAdjacentHTML" not in panel
