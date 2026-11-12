"""The Insights page: /api/reading-overview, the credits re-read job and the
collection facts (core/insights.py, routes/insights.py)."""
import time

import pytest
from flask import render_template

from core import insights
from core.database import _resolve_user_id, create_user, mark_issue_read


@pytest.fixture(autouse=True)
def _store_owner(db_connection):
    create_user("boss", role="owner")


def _owner():
    return _resolve_user_id(None)  # the implicit owner, as in a request


def _add_file(conn, path, modified_at, size=100):
    conn.execute(
        "INSERT INTO file_index (name, path, type, size, parent, modified_at) "
        "VALUES (?, ?, 'file', ?, ?, ?)",
        (path.rsplit("/", 1)[1], path, size, path.rsplit("/", 1)[0], modified_at),
    )
    conn.commit()


class TestReadingOverview:
    def test_days_years_and_totals_are_per_user(self, client, db_connection):
        owner = _owner()
        other = 999  # another account's rows (no user row: a second user turns login on)
        mark_issue_read("/x/a.cbz", read_at="2025-03-01 10:00:00", page_count=20,
                        time_spent=600, writer="Ann", user_id=owner)
        mark_issue_read("/x/b.cbz", read_at="2026-01-02 10:00:00", page_count=10, user_id=owner)
        mark_issue_read("/x/c.cbz", read_at="2026-01-02 11:00:00", user_id=owner)
        mark_issue_read("/x/d.cbz", read_at="2026-01-05 11:00:00", user_id=other)

        d = client.get("/api/reading-overview").get_json()
        assert d.get("success") is True, d
        assert d["days"] == {"2025-03-01": 1, "2026-01-02": 2}
        assert d["years"]["2026"] == {"issues": 2, "pages": 10, "seconds": 0, "gap": 2}
        assert d["years"]["2025"]["gap"] == 0  # has a writer
        assert d["all"]["issues"] == 3 and d["all"]["pages"] == 30

    def test_days_follow_the_user_timezone(self, db_connection):
        from core.database import set_user_preference
        set_user_preference("timezone", "+5")
        mark_issue_read("/x/a.cbz", read_at="2026-01-01 22:00:00", user_id=_owner())
        assert insights.get_reading_overview(_owner())["days"] == {"2026-01-02": 1}

    def test_unreadable_database_is_an_error_not_zeros(self, client, monkeypatch):
        monkeypatch.setattr(insights, "get_reading_overview", lambda: None)
        assert client.get("/api/reading-overview").status_code == 500


class TestCreditsBackfill:
    def test_reread_fills_credits_and_clears_the_gap(self, db_connection, create_cbz):
        uid = _owner()
        with_credits = create_cbz(
            "a.cbz", comicinfo_xml="<ComicInfo><Writer>Ann [12]</Writer><Publisher>DC</Publisher></ComicInfo>")
        no_credits = create_cbz("b.cbz", comicinfo_xml="<ComicInfo><Title>x</Title></ComicInfo>")
        mark_issue_read(str(with_credits), read_at="2026-02-01 10:00:00", user_id=uid)
        mark_issue_read(str(no_credits), read_at="2026-02-01 10:00:00", user_id=uid)
        mark_issue_read("/gone/c.cbz", read_at="2026-02-01 10:00:00", user_id=uid)
        assert insights.get_reading_overview(uid)["years"]["2026"]["gap"] == 3

        insights.run_reading_credits_backfill("op1", uid)

        result = insights.get_backfill_result("op1")
        assert result["user_id"] == uid
        assert {s["reason"] for s in result["skipped_issues"]} >= {"File not found"}
        row = db_connection.execute(
            "SELECT writer, publisher FROM issues_read WHERE issue_path = ?", (str(with_credits),)
        ).fetchone()
        assert (row[0], row[1]) == ("Ann", "DC")
        # The file with no credits was read, so it no longer counts; the missing one still does.
        assert insights.get_reading_overview(uid)["years"]["2026"]["gap"] == 1

    def test_only_the_users_rows_are_touched(self, db_connection, create_cbz):
        other = create_user("bob", role="reader")
        path = create_cbz("a.cbz", comicinfo_xml="<ComicInfo><Writer>Ann</Writer></ComicInfo>")
        mark_issue_read(str(path), user_id=other)
        insights.run_reading_credits_backfill("op2", _owner())
        assert db_connection.execute(
            "SELECT writer, credits_read FROM issues_read WHERE user_id = ?", (other,)
        ).fetchone()[:] == ("", 0)

    def test_start_returns_an_op_and_the_result_follows(self, client, db_connection, monkeypatch):
        monkeypatch.setattr(insights, "run_reading_credits_backfill",
                            lambda op_id, uid: insights._stash(op_id, {"user_id": uid, "updated": 0,
                                                                       "skipped": 0, "skipped_issues": []}))
        resp = client.post("/api/backfill-reading-metadata")
        assert resp.status_code == 202
        op_id = resp.get_json()["op_id"]
        for _ in range(50):
            body = client.get(f"/api/backfill-reading-metadata/{op_id}").get_json()
            if not body["pending"]:
                break
            time.sleep(0.02)
        assert body["pending"] is False and body["result"]["updated"] == 0

    def test_another_users_result_stays_hidden(self, client, db_connection):
        insights._stash("foreign", {"user_id": 9999, "updated": 1})
        assert client.get("/api/backfill-reading-metadata/foreign").get_json()["pending"] is True


class TestCollectionOverview:
    def test_read_counts_only_files_still_in_the_index(self, db_connection):
        uid = _owner()
        now = time.time()
        _add_file(db_connection, "/lib/S/a.cbz", now)
        _add_file(db_connection, "/lib/S/b.cbz", now - 400 * 86400)
        mark_issue_read("/lib/S/a.cbz", user_id=uid)
        mark_issue_read("/lib/S/deleted.cbz", user_id=uid)

        c = insights.get_collection_overview(uid)
        assert c["files"] == 2 and c["read"] == 1
        assert c["added_30"] == 1
        assert len(c["added_per_month"]) == 12
        assert sum(m["count"] for m in c["added_per_month"]) == 1
        assert c["largest"][0]["folder"] == "S"


@pytest.mark.parametrize("files", [0, 1])
def test_page_renders(app, client, db_connection, files):
    if files:
        _add_file(db_connection, "/lib/S/a.cbz", time.time())

    app.add_url_rule("/insights-render", "insights_render", lambda: render_template(
        "insights.html", collection=insights.get_collection_overview()))
    html = client.get("/insights-render").get_data(as_text=True)
    assert "CLU Wrapped" in html and "Read credits from ComicInfo" in html
    assert ('id="inCollectionData"' in html) == bool(files)
    assert ("Your library is empty" in html) != bool(files)
