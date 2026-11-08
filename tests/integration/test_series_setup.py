"""core/series_setup.py: set up a reading list's series in one go.

Against a real database and real folders; Metron is a fake that records what it
was asked, so the tests also pin how many calls a setup costs.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.factories.db_factories import create_issue, create_series


class _Model(SimpleNamespace):
    def model_dump(self, mode=None):
        out = {}
        for key, value in vars(self).items():
            out[key] = vars(value) if isinstance(value, SimpleNamespace) else value
        return out


class FakeMetron:
    """Enough of MetronClient for series setup; ``calls`` records every request."""

    def __init__(self, series=None, issues=None, issue_series=None, by_name=None, by_cv=None):
        self._series = series or {}
        self._issues = issues or {}
        self._issue_series = issue_series or {}
        self._by_name = by_name or {}
        self._by_cv = by_cv or {}
        self.calls = []

    def using(self, **_options):
        return self

    def issue(self, issue_id):
        self.calls.append(("issue", issue_id))
        sid = self._issue_series.get(issue_id)
        return SimpleNamespace(series=SimpleNamespace(id=sid)) if sid else None

    def series(self, series_id):
        self.calls.append(("series", series_id))
        data = self._series.get(series_id)
        if not data:
            return None
        return _Model(
            id=series_id,
            name=data["name"],
            volume=data.get("volume", 1),
            year_began=data.get("year_began"),
            year_end=data.get("year_end"),
            status=data.get("status", "Completed"),
            issue_count=data.get("issue_count"),
            cv_id=data.get("cv_id"),
            publisher=SimpleNamespace(id=data.get("publisher_id", 1),
                                      name=data.get("publisher", "Marvel")),
        )

    def series_list(self, params):
        self.calls.append(("series_list", dict(params)))
        if "cv_id" in params:
            sid = self._by_cv.get(params["cv_id"])
            return [SimpleNamespace(id=sid)] if sid else []
        return [SimpleNamespace(**c) for c in self._by_name.get(params.get("name"), [])]

    def issues_list(self, params):
        self.calls.append(("issues_list", dict(params)))
        return self._issues.get(params["series_id"], [])


def _entry(series, number, year=None, metron_id=None, cv_volume_id=None, volume=None):
    return {"series": series, "issue_number": number, "year": year, "volume": volume,
            "metron_id": metron_id, "cv_volume_id": cv_volume_id}


# Dark Nights: Metal as a real CBL stores it: Volume is the run's start year,
# Year is each issue's own year, so #4-6 say 2018 (as reported).
METAL = [
    _entry("Dark Nights: Metal", n, year, cv_volume_id=103508, volume=2017)
    for n, year in (("1", 2017), ("2", 2017), ("3", 2017),
                    ("4", 2018), ("5", 2018), ("6", 2018))
]


@pytest.fixture
def quiet_subscribe():
    """Network side effects of subscribing that these tests do not exercise."""
    with patch("models.getcomics.prepopulate_series_index"), \
         patch("models.series_json.write_series_json"), \
         patch("models.metron.get_flask_api", return_value=None):
        yield


class TestGroupEntries:

    def test_groups_by_series_in_list_order(self):
        from core.series_setup import group_entries

        groups = group_entries([
            _entry("X-Men", "21", 2019, metron_id=1),
            _entry("Immortal X-Men", "10", 2022),
            _entry("X-Men", "22", 2019, metron_id=2),
        ])
        assert [(g["name"], g["issues"]) for g in groups] == [
            ("X-Men", ["21", "22"]), ("Immortal X-Men", ["10"])]
        assert groups[0]["metron_ids"] == [1, 2]

    def test_same_name_different_year_is_two_series(self):
        from core.series_setup import group_entries

        groups = group_entries([_entry("X-Men", "1", 1991), _entry("X-Men", "1", 2019)])
        assert [g["year"] for g in groups] == [1991, 2019]

    def test_punctuation_does_not_split_a_series(self):
        from core.series_setup import group_entries

        groups = group_entries([_entry("Batman: Year One", "1"), _entry("Batman - Year One", "2")])
        assert len(groups) == 1 and groups[0]["issues"] == ["1", "2"]

    def test_issue_years_do_not_split_a_cbl_series(self):
        """The reported case: #1-3 (2017) and #4-6 (2018) are one series."""
        from core.series_setup import group_entries

        groups = group_entries(METAL)
        assert len(groups) == 1
        assert groups[0]["issues"] == ["1", "2", "3", "4", "5", "6"]
        assert groups[0]["year"] == 2017  # the volume's year, for name searches

    def test_volume_year_groups_a_cbl_without_ids(self):
        from core.series_setup import group_entries

        entries = [{**e, "cv_volume_id": None} for e in METAL]
        assert len(group_entries(entries)) == 1

    def test_metron_import_year_is_the_volume_year(self):
        """A Metron import writes the volume *number* into volume and the start year into year."""
        from core.series_setup import group_entries

        groups = group_entries([_entry("X-Men", "1", 2019, volume=6),
                                _entry("X-Men", "2", 2019, volume=6)])
        assert len(groups) == 1 and groups[0]["year"] == 2019

    def test_entries_without_a_series_name_are_left_out(self):
        from core.series_setup import group_entries

        assert group_entries([_entry("", "1"), _entry(None, "2")]) == []


class TestResolve:

    def test_issue_id_in_the_local_cache_needs_no_issue_call(self, db_connection):
        from core.series_setup import RESOLVED, resolve_list

        sid = create_series(series_id=471, name="Powers of X", mapped_path=None)
        create_issue(issue_id=9001, series_id=sid, number="1")
        # create_series maps by default; drop the mapping so it is not "mapped".
        from core.database import remove_series_mapping
        remove_series_mapping(sid)

        api = FakeMetron()
        rows = resolve_list(api, [_entry("Powers of X", "1", 2019, metron_id=9001)])

        assert rows[0]["state"] == RESOLVED
        assert rows[0]["how"] == "issue"
        assert rows[0]["series"]["series_id"] == 471
        assert not [c for c in api.calls if c[0] == "issue"]

    def test_issue_id_asks_metron_when_not_cached(self, db_connection):
        from core.series_setup import RESOLVED, resolve_list

        api = FakeMetron(issue_series={5: 100},
                         series={100: {"name": "Immortal X-Men", "year_began": 2022,
                                       "publisher": "Marvel", "status": "Completed"}})
        rows = resolve_list(api, [_entry("Immortal X-Men", "10", 2022, metron_id=5)],
                            pattern="{publisher}/{series_name} ({start_year})")

        row = rows[0]
        assert row["state"] == RESOLVED
        assert row["series"]["name"] == "Immortal X-Men"
        assert row["relative_path"] == "/Marvel/Immortal X-Men (2022)"
        assert api.calls == [("issue", 5), ("series", 100)]

    def test_one_lookup_per_series_not_per_issue(self, db_connection):
        from core.series_setup import resolve_list

        api = FakeMetron(issue_series={1: 100, 2: 100, 3: 100},
                         series={100: {"name": "X-Men", "year_began": 2019}})
        resolve_list(api, [_entry("X-Men", n, 2019, metron_id=i)
                           for i, n in ((1, "21"), (2, "22"), (3, "23"))])
        assert [c[0] for c in api.calls] == ["issue", "series"]

    def test_comicvine_volume_id(self, db_connection):
        from core.series_setup import resolve_list

        api = FakeMetron(by_cv={4050: 200}, series={200: {"name": "Inferno", "year_began": 2021}})
        rows = resolve_list(api, [_entry("Inferno", "1", 2021, cv_volume_id=4050)])
        assert rows[0]["how"] == "comicvine"
        assert rows[0]["series"]["series_id"] == 200

    def test_unique_name_and_year_resolves(self, db_connection):
        from core.series_setup import resolve_list

        api = FakeMetron(
            by_name={"X-Men": [
                {"id": 1, "name": "X-Men", "year_began": 1991},
                {"id": 2, "name": "X-Men", "year_began": 2019},
                {"id": 3, "name": "X-Men Legends", "year_began": 2021},
            ]},
            series={2: {"name": "X-Men", "year_began": 2019}},
        )
        rows = resolve_list(api, [_entry("X-Men", "1", 2019)])
        assert rows[0]["state"] == "resolved"
        assert rows[0]["how"] == "name"
        assert rows[0]["series"]["series_id"] == 2

    def test_ambiguous_name_asks_the_user(self, db_connection):
        from core.series_setup import CHOOSE, resolve_list

        api = FakeMetron(by_name={"X-Men": [
            {"id": 1, "name": "X-Men", "year_began": 1991},
            {"id": 2, "name": "X-Men", "year_began": 2019},
        ]})
        rows = resolve_list(api, [_entry("X-Men", "1")])  # no year to decide by
        assert rows[0]["state"] == CHOOSE
        assert [c["series_id"] for c in rows[0]["candidates"]] == [1, 2]
        assert ("series", 1) not in api.calls  # nothing fetched for a guess

    def test_candidates_already_on_the_pull_list_are_marked(self, db_connection, tmp_path):
        from core.series_setup import resolve_list

        create_series(series_id=2, name="X-Men", mapped_path=str(tmp_path / "X-Men"))
        api = FakeMetron(by_name={"X-Men": [
            {"id": 1, "name": "X-Men", "year_began": 1991},
            {"id": 2, "name": "X-Men", "year_began": 2019},
        ]})
        rows = resolve_list(api, [_entry("X-Men", "1")])
        assert [(c["series_id"], c["mapped"]) for c in rows[0]["candidates"]] == [(1, False), (2, True)]

    def test_reported_list_resolves_metal_once(self, db_connection):
        from core.series_setup import resolve_list

        api = FakeMetron(by_cv={103508: 2032},
                         series={2032: {"name": "Dark Nights: Metal", "year_began": 2017}})
        rows = resolve_list(api, METAL)
        assert len(rows) == 1
        assert rows[0]["issues"] == ["1", "2", "3", "4", "5", "6"]
        assert [c for c in api.calls if c[0] == "series_list"] == [("series_list", {"cv_id": 103508})]

    def test_groups_that_resolve_to_one_series_are_merged(self, db_connection):
        """Spelled two ways in one list, but the ids say it is one series."""
        from core.series_setup import resolve_list

        api = FakeMetron(issue_series={1: 2032, 2: 2032},
                         series={2032: {"name": "Dark Nights: Metal", "year_began": 2017}})
        rows = resolve_list(api, [
            _entry("Dark Nights: Metal", "1", metron_id=1),
            _entry("Other", "x", metron_id=99),
            _entry("Dark Nights Metal (2017)", "4", metron_id=2),
        ])
        assert [(r["list_name"], r["issues"]) for r in rows] == [
            ("Dark Nights: Metal", ["1", "4"]), ("Other", ["x"])]

    def test_nothing_found(self, db_connection):
        from core.series_setup import UNRESOLVED, resolve_list

        rows = resolve_list(FakeMetron(), [_entry("Nowhere Man", "1")])
        assert rows[0]["state"] == UNRESOLVED

    def test_series_already_on_the_pull_list_is_reported_not_offered(self, db_connection, tmp_path):
        from core.series_setup import MAPPED, resolve_list

        folder = tmp_path / "Powers of X"
        sid = create_series(series_id=471, name="Powers of X", mapped_path=str(folder))
        create_issue(issue_id=9001, series_id=sid, number="1")

        rows = resolve_list(FakeMetron(), [_entry("Powers of X", "1", metron_id=9001)])
        assert rows[0]["state"] == MAPPED
        assert rows[0]["mapped_path"] == str(folder)
        assert rows[0]["relative_path"] is None

    def test_one_failing_series_does_not_stop_the_rest(self, db_connection):
        from core.series_setup import resolve_list

        class Flaky(FakeMetron):
            def issue(self, issue_id):
                if issue_id == 1:
                    raise RuntimeError("boom")
                return super().issue(issue_id)

        api = Flaky(issue_series={2: 100}, series={100: {"name": "B", "year_began": 2020}})
        rows = resolve_list(api, [_entry("A", "1", metron_id=1), _entry("B", "1", metron_id=2)])
        assert [r["state"] for r in rows] == ["unresolved", "resolved"]


class TestApply:

    def _api(self):
        return FakeMetron(
            series={100: {"name": "Immortal X-Men", "year_began": 2022, "publisher": "Marvel",
                          "status": "Completed"}},
            issues={100: [{"id": 10001, "number": "1", "cover_date": "2022-04-01",
                           "store_date": "2022-04-01"},
                          {"id": 10010, "number": "10", "cover_date": "2023-01-01",
                           "store_date": "2023-01-01"}]},
        )

    def _flags(self, series_id):
        from core.database import get_db_connection

        conn = get_db_connection()
        try:
            row = conn.execute("SELECT monitored, monitor_locked, mapped_path FROM series "
                               "WHERE id = ?", (series_id,)).fetchone()
            return dict(row)
        finally:
            conn.close()

    def test_subscribes_as_not_monitored_and_locked(self, db_connection, tmp_path, quiet_subscribe):
        from core.database import get_issues_for_series
        from core.series_setup import apply_setup

        target = tmp_path / "Marvel" / "Immortal X-Men"
        results = apply_setup(self._api(), [{"series_id": 100, "path": str(target)}],
                              monitored=False)

        assert results[0]["ok"] is True
        assert target.is_dir() and (target / "cvinfo").is_file()
        assert self._flags(100) == {"monitored": 0, "monitor_locked": 1,
                                    "mapped_path": str(target)}
        assert len(get_issues_for_series(100)) == 2

    def test_monitored_when_asked(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        apply_setup(self._api(), [{"series_id": 100, "path": str(tmp_path / "IXM")}],
                    monitored=True)
        assert self._flags(100)["monitored"] == 1

    def test_missing_path_uses_the_subscribe_pattern(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        results = apply_setup(self._api(), [{"series_id": 100}],
                              pattern="{publisher}/{series_name}", library_path=str(tmp_path))
        assert results[0]["path"] == f"{tmp_path}/Marvel/Immortal X-Men"

    def test_a_mapped_series_is_left_alone(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        create_series(series_id=100, name="Immortal X-Men", mapped_path=str(tmp_path / "Mine"))
        api = self._api()
        results = apply_setup(api, [{"series_id": 100, "path": str(tmp_path / "Other")}])

        assert results[0]["ok"] is False
        assert "Pull List" in results[0]["error"]
        assert self._flags(100)["mapped_path"] == str(tmp_path / "Mine")
        assert api.calls == []

    def test_a_cached_series_costs_no_calls(self, db_connection, tmp_path, quiet_subscribe):
        from core.database import remove_series_mapping
        from core.series_setup import apply_setup

        sid = create_series(series_id=100, name="Immortal X-Men")
        create_issue(series_id=sid, number="1")
        remove_series_mapping(sid)
        api = self._api()
        assert apply_setup(api, [{"series_id": 100, "path": str(tmp_path / "IXM")}])[0]["ok"]
        assert api.calls == []

    def test_a_series_picked_twice_is_set_up_once(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        with patch("core.series_setup.app_logger") as log:
            results = apply_setup(self._api(), [
                {"series_id": 100, "path": str(tmp_path / "IXM")},
                {"series_id": 100, "path": str(tmp_path / "IXM again")},
            ])
        assert [r["ok"] for r in results] == [True]
        assert not (tmp_path / "IXM again").exists()
        log.warning.assert_not_called()

    def test_a_series_not_set_up_is_logged_with_the_reason(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        create_series(series_id=100, name="Immortal X-Men", mapped_path=str(tmp_path / "Mine"))
        with patch("core.series_setup.app_logger") as log:
            apply_setup(self._api(), [
                {"series_id": 999, "path": str(tmp_path / "Gone")},
                {"series_id": 100, "path": str(tmp_path / "Other")},
            ])
        lines = [c.args[0] for c in log.warning.call_args_list]
        assert any("series 999" in l and "Metron did not return" in l for l in lines)
        assert any("series 100" in l and "Pull List" in l for l in lines)

    def test_a_successful_setup_logs_no_warning(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        with patch("core.series_setup.app_logger") as log:
            apply_setup(self._api(), [{"series_id": 100, "path": str(tmp_path / "IXM")}])
        log.warning.assert_not_called()

    def test_one_failure_does_not_stop_the_rest(self, db_connection, tmp_path, quiet_subscribe):
        from core.series_setup import apply_setup

        results = apply_setup(self._api(), [
            {"series_id": 999, "path": str(tmp_path / "Gone")},
            {"series_id": 100, "path": str(tmp_path / "IXM")},
        ])
        assert [r["ok"] for r in results] == [False, True]
