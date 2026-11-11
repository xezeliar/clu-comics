"""Pull List: Next issue, This week, Needs attention and the have/missing bar."""
import pytest

from tests.factories.db_factories import create_publisher, create_issue
from tests.factories.db_factories import create_series as _create_series

TODAY = "2026-11-11"  # a Wednesday: the store week is Sun 8 - Sat 14 Nov


def create_series(**kw):
    """A series synced today, so a never-synced flag does not hide the reason under test."""
    from core.database import db_conn
    sid = _create_series(**kw)
    with db_conn() as conn:
        conn.execute("UPDATE series SET last_synced_at = ? WHERE id = ?", (TODAY + " 09:00:00", sid))
        conn.commit()
    return sid


def _mark(series_id, issue_id, number, found):
    from core.database import save_collection_status_bulk
    save_collection_status_bulk([{
        "series_id": series_id, "issue_id": issue_id, "issue_number": str(number),
        "found": 1 if found else 0, "file_path": "/data/x.cbz" if found else None,
        "file_mtime": 0.0, "matched_via": "filename",
    }])


def _row(series_id, **kw):
    from core.database import get_pull_list_page
    rows = get_pull_list_page(TODAY, **kw)["rows"]
    return next(r for r in rows if r["id"] == series_id)


@pytest.fixture
def pub(db_connection):
    return create_publisher(publisher_id=10, name="Image")


class TestNextIssue:

    def test_earliest_unowned_issue_in_window(self, pub):
        create_series(series_id=1, name="A", publisher_id=pub)
        i1 = create_issue(issue_id=11, series_id=1, number="1", store_date="2026-10-01")
        create_issue(issue_id=12, series_id=1, number="2", store_date="2026-11-18")
        _mark(1, i1, 1, True)
        row = _row(1)
        assert (row["next_number"], row["next_date"]) == ("2", "2026-11-18")
        assert row["next_label"] == "#2 · Wed 18 Nov" and not row["next_overdue"]

    def test_four_week_lookback_boundary(self, pub):
        # 28 days before TODAY is 2026-10-14: in; 10-13 is out.
        create_series(series_id=1, name="In", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="5", store_date="2026-10-14")
        create_series(series_id=2, name="Out", publisher_id=pub)
        create_issue(issue_id=21, series_id=2, number="5", store_date="2026-10-13")
        assert _row(1)["next_number"] == "5"
        assert _row(2)["next_number"] is None
        assert _row(2)["next_label"] == "None announced"

    def test_overdue_from_seven_days(self, pub):
        create_series(series_id=1, name="Six", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="3", store_date="2026-11-05")  # 6 days
        create_series(series_id=2, name="Seven", publisher_id=pub)
        create_issue(issue_id=21, series_id=2, number="3", store_date="2026-11-04")  # 7 days
        create_series(series_id=3, name="Three weeks", publisher_id=pub)
        create_issue(issue_id=31, series_id=3, number="7", store_date="2026-10-21")  # 21 days
        assert not _row(1)["next_overdue"]
        assert _row(2)["next_overdue"] and _row(2)["next_label"] == "#3 · 1 wk overdue"
        assert _row(3)["next_label"] == "#7 · 3 wk overdue"

    def test_today_and_ended(self, pub):
        create_series(series_id=1, name="T", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="45", store_date=TODAY)
        assert _row(1)["next_label"] == "#45 · Today"
        create_series(series_id=2, name="E", publisher_id=pub, status="Ended")
        assert _row(2)["next_label"] == "Ended"

    def test_manual_owned_is_not_next(self, pub):
        from core.database import set_manual_status
        create_series(series_id=1, name="A", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="1", store_date="2026-11-18")
        set_manual_status(1, "1", "owned")
        assert _row(1)["next_number"] is None

    def test_sort_by_next_puts_none_last(self, pub):
        create_series(series_id=1, name="Late", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="1", store_date="2026-12-01")
        create_series(series_id=2, name="Soon", publisher_id=pub)
        create_issue(issue_id=21, series_id=2, number="1", store_date="2026-11-12")
        create_series(series_id=3, name="None", publisher_id=pub)
        from core.database import get_pull_list_page
        names = [r["name"] for r in get_pull_list_page(TODAY, sort="next")["rows"]]
        assert names == ["Soon", "Late", "None"]
        names = [r["name"] for r in get_pull_list_page(TODAY, sort="next", descending=True)["rows"]]
        assert names == ["None", "Late", "Soon"]


class TestThisWeek:

    def test_store_week_is_sunday_to_saturday(self, pub):
        from core.database import get_pull_list_this_week
        create_series(series_id=1, name="A", publisher_id=pub)
        for n, d in (("1", "2026-11-07"), ("2", "2026-11-08"), ("3", "2026-11-14"), ("4", "2026-11-15")):
            create_issue(issue_id=10 + int(n), series_id=1, number=n, store_date=d)
        assert [r["number"] for r in get_pull_list_this_week(TODAY)] == ["2", "3"]
        # On a Sunday the week starts that day.
        assert [r["number"] for r in get_pull_list_this_week("2026-11-08")] == ["2", "3"]

    def test_found_and_unmapped(self, pub):
        from core.database import get_pull_list_this_week
        create_series(series_id=1, name="A", publisher_id=pub)
        i = create_issue(issue_id=11, series_id=1, number="1", store_date=TODAY)
        _mark(1, i, 1, True)
        create_series(series_id=2, name="Unmapped", publisher_id=pub)
        from core.database import db_conn
        with db_conn() as conn:
            conn.execute("UPDATE series SET mapped_path = NULL WHERE id = 2")
            conn.commit()
        create_issue(issue_id=21, series_id=2, number="1", store_date=TODAY)
        rows = get_pull_list_this_week(TODAY)
        assert [(r["name"], r["found"]) for r in rows] == [("A", 1)]


class TestAttentionAndBar:

    def _item(self, sid, number, outcome, status=None, download_id=None):
        from core.database import db_conn
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO download_run_items (run_id, series_id, issue_number, outcome,"
                " download_id, download_status) VALUES (1, ?, ?, ?, ?, ?)",
                (sid, number, outcome, download_id, status))
            conn.commit()

    def _attempt(self, sid, number, outcome):
        from core.database import record_search_attempt
        record_search_attempt(sid, "x", number, "manual", outcome, [])

    def test_failed_download_flags_until_a_later_success(self, pub):
        from core.database import get_pull_list_page
        create_series(series_id=1, name="A", publisher_id=pub)
        self._item(1, "4", "queued", "failed", "d1")
        assert _row(1)["attention"] == "Last download failed"
        assert [r["id"] for r in get_pull_list_page(TODAY, attention=True)["rows"]] == [1]
        self._item(1, "4", "queued", "complete", "d2")
        assert _row(1)["attention"] == ""
        assert get_pull_list_page(TODAY, attention=True)["total"] == 0

    def test_not_found_needs_three_searches(self, pub):
        create_series(series_id=1, name="A", publisher_id=pub)
        for _ in range(2):
            self._attempt(1, "4", "nothing_found")
        assert _row(1)["attention"] == ""
        self._attempt(1, "4", "nothing_found")
        assert "3 searches" in _row(1)["attention"]

    def test_overdue_and_stale_sync(self, pub):
        create_series(series_id=1, name="Overdue", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="1", store_date="2026-11-04")
        create_series(series_id=2, name="Fresh", publisher_id=pub)
        create_issue(issue_id=21, series_id=2, number="1", store_date="2026-11-05")
        assert _row(1)["attention"] == "Next issue is overdue"
        assert _row(2)["attention"] == ""
        from core.database import db_conn
        with db_conn() as conn:
            conn.execute("UPDATE series SET last_synced_at = '2026-10-27 10:00:00' WHERE id = 2")
            conn.execute("UPDATE series SET last_synced_at = '2026-10-30 10:00:00' WHERE id = 1")
            conn.commit()
        assert _row(2)["attention"] == "Not synced for 15 days"
        # 12 days is not stale (series 1 is flagged only for being overdue).
        assert _row(1)["attention"] == "Next issue is overdue"

    def test_never_synced_needs_attention(self, pub):
        sid = _create_series(series_id=1, name="Never", publisher_id=pub)
        assert _row(sid)["attention"] == "Never synced"
        assert _row(sid, attention=True)["id"] == sid

    def test_facet_count(self, pub):
        from core.database import get_pull_list_facets
        create_series(series_id=1, name="A", publisher_id=pub)
        create_series(series_id=2, name="B", publisher_id=pub)
        create_issue(issue_id=11, series_id=1, number="1", store_date="2026-11-04")
        assert get_pull_list_facets(TODAY)["attention"] == 1
        assert get_pull_list_facets()["attention"] == 0

    def test_bar_runs_and_have_count(self, pub):
        create_series(series_id=1, name="A", publisher_id=pub)
        for n, found in (("1", True), ("2", True), ("3", False), ("10", True)):
            i = create_issue(issue_id=100 + int(n), series_id=1, number=n, store_date="2020-01-01")
            _mark(1, i, n, found)
        row = _row(1)
        assert row["bar"] == [[1, 2], [0, 1], [1, 1]]  # numeric order: 1,2 | 3 | 10
        assert (row["have"], row["total_issues"]) == (3, 4)
