"""The series page's Year Ended field follows the series Status.

It used to print ``year_end or 'Ongoing'``, so a one-shot Metron has no end year
for (Absolute Evil: Status Completed, Year Ended "Ongoing") contradicted itself.
The cases below are real Metron series, as reported.
"""
import datetime
import pathlib
from types import SimpleNamespace

import pytest

from core.series_status import (
    FINISHED,
    HIATUS,
    ONGOING,
    UNKNOWN,
    last_issue_year,
    status_text,
    year_ended_label,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _series(status, year_end=None, **extra):
    return {"status": status, "year_end": year_end, **extra}


def _issues(*cover_dates):
    return [{"number": str(i + 1), "cover_date": d} for i, d in enumerate(cover_dates)]


class TestReportedSeries:
    """The five series from the report, by series type."""

    def test_annual_completed_without_end_year_is_finished(self):
        # Absolute Batman 2025 Annual: Annual, Completed, no Year End.
        label = year_ended_label(_series("Completed"), _issues("2025-10-01"))
        assert label == "2025"

    def test_one_shot_completed_without_end_year_is_finished(self):
        # Bug Wars: The Spyder Wytch Special: One-Shot, Completed, no Year End.
        label = year_ended_label(_series("Completed"), _issues("2026-04-01"))
        assert label == "2026"

    def test_single_issue_cancelled_without_end_year_is_finished(self):
        # Green Arrow (2023): Single Issue, Cancelled, no Year End.
        issues = _issues("2023-06-01", "2024-08-01", "2025-01-01")
        assert year_ended_label(_series("Cancelled"), issues) == "2025"

    def test_single_issue_ongoing_is_ongoing(self):
        # Absolute Batman (2024): Single Issue, Ongoing.
        issues = _issues("2024-12-01", "2026-10-01")
        assert year_ended_label(_series("Ongoing"), issues) == ONGOING

    def test_limited_series_completed_shows_its_end_year(self):
        # Powers of X (2019): Limited Series, Completed, Year End 2019.
        assert year_ended_label(_series("Completed", 2019), _issues("2019-09-01")) == "2019"


class TestRules:

    def test_provider_end_year_wins(self):
        assert year_ended_label(_series("Completed", 2020), _issues("2025-01-01")) == "2020"

    def test_year_ended_spelling_is_read_too(self):
        assert year_ended_label({"status": "Completed", "year_ended": 2018}) == "2018"

    def test_finished_without_any_dated_issue_says_finished(self):
        assert year_ended_label(_series("Completed"), []) == FINISHED
        assert year_ended_label(_series("Ended"), None) == FINISHED

    @pytest.mark.parametrize("status", ["Completed", "Cancelled", "Canceled", "Ended", "completed"])
    def test_every_finished_status_counts(self, status):
        assert year_ended_label(_series(status), []) == FINISHED

    def test_hiatus_is_not_called_ongoing(self):
        assert year_ended_label(_series("Hiatus"), _issues("2022-01-01")) == HIATUS

    @pytest.mark.parametrize("status", [None, "", "Something new"])
    def test_unknown_status_does_not_guess_ongoing(self, status):
        assert year_ended_label(_series(status), _issues("2020-01-01")) == UNKNOWN

    def test_series_type_does_not_matter(self):
        """Only the status decides: an ongoing annual is still ongoing."""
        series = _series("Ongoing", series_type={"name": "Annual"})
        assert year_ended_label(series, _issues("2024-01-01")) == ONGOING


class TestShapes:
    """Cached series are dicts with string dates; live ones are mokkari objects."""

    def test_object_series_with_named_status(self):
        series = SimpleNamespace(status=SimpleNamespace(name="Cancelled"), year_end=None)
        issues = [SimpleNamespace(cover_date=datetime.date(2024, 3, 1), store_date=None)]
        assert year_ended_label(series, issues) == "2024"

    def test_plain_string_status_on_an_object(self):
        assert status_text(SimpleNamespace(status=" Completed ")) == "completed"

    def test_store_date_is_the_fallback_for_an_undated_cover(self):
        issues = [{"cover_date": None, "store_date": "2021-05-05"}]
        assert last_issue_year(issues) == 2021

    def test_garbage_dates_are_ignored(self):
        issues = [{"cover_date": "unknown"}, {"cover_date": "2019-01-01"}]
        assert last_issue_year(issues) == 2019


class TestPageWiring:
    """series.html is rendered by one route; assert both halves are connected."""

    def test_template_uses_the_label_not_an_ongoing_fallback(self):
        html = (ROOT / "templates" / "series.html").read_text(encoding="utf-8")
        assert "{{ year_ended_label }}" in html
        assert "or 'Ongoing'" not in html

    def test_route_passes_the_label(self):
        src = (ROOT / "routes" / "series.py").read_text(encoding="utf-8")
        assert "year_ended_label=year_ended_label(series_info, all_issues)" in src
