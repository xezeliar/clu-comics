"""core/auto_monitor.py against a real database and real series folders.

A series that has ended (Completed / Cancelled / Ended) and has every issue in
its folder stops being monitored -- once, and never over the user's own choice.
"""
import pathlib

import pytest

from tests.factories.db_factories import create_issue, create_series

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _flags(series_id):
    from core.database import get_db_connection

    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT monitored, monitor_locked FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        return row["monitored"], row["monitor_locked"]
    finally:
        conn.close()


def _row(series_id):
    from core.database import get_all_mapped_series

    return next(s for s in get_all_mapped_series() if s["id"] == series_id)


def _series_with_files(tmp_path, name, status, numbers, on_disk):
    folder = tmp_path / name
    folder.mkdir()
    sid = create_series(name=name, status=status, mapped_path=str(folder))
    for n in numbers:
        create_issue(series_id=sid, number=n, store_date="2019-09-01")
    for n in on_disk:
        (folder / f"{name} #{n}.cbz").write_bytes(b"stub")
    return sid, folder


class TestDatabaseGuard:

    def test_turns_off_and_locks_once(self, db_connection):
        from core.database import auto_unmonitor_series

        sid = create_series(status="Completed")
        assert auto_unmonitor_series(sid) is True
        assert _flags(sid) == (0, 1)
        assert auto_unmonitor_series(sid) is False

    def test_user_choice_is_never_overridden(self, db_connection):
        from core.database import auto_unmonitor_series, set_series_monitored

        sid = create_series(status="Completed")
        set_series_monitored(sid, True, lock=True)  # the user said "monitor this"
        assert auto_unmonitor_series(sid) is False
        assert _flags(sid) == (1, 1)

    def test_turning_back_on_after_auto_off_sticks(self, db_connection):
        from core.database import auto_unmonitor_series, set_series_monitored

        sid = create_series(status="Completed")
        auto_unmonitor_series(sid)
        set_series_monitored(sid, True, lock=True)
        assert auto_unmonitor_series(sid) is False
        assert _flags(sid) == (1, 1)

    def test_automatic_set_does_not_lock(self, db_connection):
        from core.database import set_series_monitored

        sid = create_series()
        set_series_monitored(sid, False)
        assert _flags(sid) == (0, 0)

    def test_bulk_toggle_locks_every_row(self, db_connection):
        from core.database import set_series_monitored_bulk

        a, b = create_series(), create_series()
        assert set_series_monitored_bulk([a, b], True, lock=True) == 2
        assert _flags(a) == (1, 1) and _flags(b) == (1, 1)

    def test_resubscribing_keeps_the_flags(self, db_connection):
        from core.database import auto_unmonitor_series

        sid = create_series(series_id=4711, status="Completed")
        auto_unmonitor_series(sid)
        create_series(series_id=4711, status="Completed")  # same id saved again
        assert _flags(sid) == (0, 1)


class TestCheckSeries:

    def test_finished_and_every_issue_on_disk_turns_off(self, db_connection, tmp_path):
        from core.auto_monitor import check_series

        sid, _ = _series_with_files(tmp_path, "Powers of X", "Completed",
                                    ["1", "2"], ["1", "2"])
        assert check_series(_row(sid)) is True
        assert _flags(sid) == (0, 1)

    def test_a_missing_issue_keeps_it_on(self, db_connection, tmp_path):
        from core.auto_monitor import check_series

        sid, _ = _series_with_files(tmp_path, "Green Arrow", "Cancelled",
                                    ["1", "2"], ["1"])
        assert check_series(_row(sid)) is False
        assert _flags(sid) == (1, 0)

    def test_skipped_issue_is_not_owned(self, db_connection, tmp_path):
        """An event reader's Skipped marks are theirs to act on, not ours."""
        from core.auto_monitor import check_series
        from core.database import set_manual_status

        sid, _ = _series_with_files(tmp_path, "Inferno", "Completed",
                                    ["1", "2"], ["1"])
        set_manual_status(sid, "2", "skipped")
        assert check_series(_row(sid)) is False
        assert _flags(sid) == (1, 0)

    def test_ongoing_keeps_it_on(self, db_connection, tmp_path):
        from core.auto_monitor import check_series

        sid, _ = _series_with_files(tmp_path, "Absolute Batman", "Ongoing",
                                    ["1"], ["1"])
        assert check_series(_row(sid)) is False
        assert _flags(sid) == (1, 0)

    def test_user_locked_series_is_not_even_matched(self, db_connection, tmp_path, monkeypatch):
        from core import auto_monitor
        from core.database import set_series_monitored

        sid, _ = _series_with_files(tmp_path, "Watchmen", "Completed", ["1"], ["1"])
        set_series_monitored(sid, True, lock=True)

        def boom(*a, **k):
            raise AssertionError("a locked series must be skipped before matching")

        monkeypatch.setattr("helpers.collection.match_issues_to_collection", boom)
        assert auto_monitor.check_series(_row(sid)) is False


class TestSweep:

    def test_turns_off_only_the_qualifying_series(self, db_connection, tmp_path):
        from core.auto_monitor import sweep_finished_series

        done, _ = _series_with_files(tmp_path, "Powers of X", "Completed", ["1"], ["1"])
        gap, _ = _series_with_files(tmp_path, "Green Arrow", "Cancelled", ["1", "2"], ["1"])
        live, _ = _series_with_files(tmp_path, "Absolute Batman", "Ongoing", ["1"], ["1"])

        assert sweep_finished_series() == 1
        assert _flags(done) == (0, 1)
        assert _flags(gap) == (1, 0)
        assert _flags(live) == (1, 0)

    def test_one_failing_series_does_not_stop_the_rest(self, db_connection, tmp_path, monkeypatch):
        from core import auto_monitor

        sid, _ = _series_with_files(tmp_path, "Powers of X", "Completed", ["1"], ["1"])
        broken = {"id": 999, "name": "Broken", "status": "Completed",
                  "mapped_path": None, "monitored": 1}
        real = auto_monitor.check_series

        def flaky(series):
            if series["id"] == 999:
                raise RuntimeError("boom")
            return real(series)

        monkeypatch.setattr(auto_monitor, "check_series", flaky)
        assert auto_monitor.sweep_finished_series([broken, _row(sid)]) == 1


class TestReconcileHook:

    def test_the_last_missing_issue_landing_turns_it_off(self, db_connection, tmp_path):
        from helpers.collection import reconcile_wanted_for_series

        sid, folder = _series_with_files(tmp_path, "House of X", "Completed",
                                         ["1", "2"], ["1"])
        reconcile_wanted_for_series(sid)
        assert _flags(sid) == (1, 0)

        (folder / "House of X #2.cbz").write_bytes(b"stub")
        reconcile_wanted_for_series(sid)
        assert _flags(sid) == (0, 1)


class TestAppHooks:
    """app.py cannot be imported in tests; assert both hook sites structurally."""

    @pytest.fixture(scope="class")
    def app_src(self):
        return (ROOT / "app.py").read_text(encoding="utf-8")

    def test_scheduled_sync_sweeps_after_the_sync_loop(self, app_src):
        body = app_src.split("def scheduled_series_sync():")[1].split("\ndef ")[0]
        sweep = body.index("sweep_finished_series()")
        assert body.index("Sync completed") < sweep
        assert "Auto-monitor sweep failed" in body[sweep:]

    def test_wanted_refresh_checks_each_matched_series(self, app_src):
        body = app_src.split("def refresh_wanted_cache_background():")[1].split("\ndef ")[0]
        match = body.index("issue_status = match_issues_to_collection(")
        hook = body.index("maybe_auto_unmonitor(series_id, series, issue_status)")
        assert match < hook

    def test_scan_library_import_uses_the_shared_rule(self):
        src = (ROOT / "models" / "library_automap.py").read_text(encoding="utf-8")
        assert "from core.auto_monitor import maybe_auto_unmonitor" in src
        assert "set_series_monitored(" not in src.split("def _maybe_default_monitor_off")[1].split("\ndef ")[0]
