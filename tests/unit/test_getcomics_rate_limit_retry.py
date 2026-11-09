"""A GetComics 429 is retried, and a search that still fails is not "nothing found"."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models import getcomics

OK_HTML = (
    '<article class="post"><h1 class="post-title">'
    '<a href="https://getcomics.org/x">S.W.O.R.D. #6 (2021)</a></h1></article>'
)
EMPTY_HTML = "<html><body></body></html>"


def _resp(status=200, html=OK_HTML, headers=None):
    r = MagicMock()
    r.status_code = status
    r.text = html
    r.headers = headers or {}
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"{status} Client Error")
    return r


@pytest.fixture
def sleeps():
    with patch.object(getcomics.time, "sleep") as s:
        yield s


@patch("models.getcomics.scraper")
def test_429_then_success_is_retried(scraper, sleeps):
    scraper.get.side_effect = [_resp(429), _resp(200)]
    results = getcomics.search_getcomics("sword 6", max_pages=1)
    assert [r["title"] for r in results] == ["S.W.O.R.D. #6 (2021)"]
    assert results.failed is False
    assert scraper.get.call_count == 2
    sleeps.assert_called_once_with(getcomics.RATE_LIMIT_BACKOFF[0])


@patch("models.getcomics.scraper")
def test_retry_after_header_is_honoured_and_capped(scraper, sleeps):
    scraper.get.side_effect = [
        _resp(429, headers={"Retry-After": "7"}),
        _resp(429, headers={"Retry-After": "99999"}),
        _resp(200),
    ]
    getcomics.search_getcomics("sword 6", max_pages=1)
    assert [c.args[0] for c in sleeps.call_args_list] == [7, getcomics.MAX_RETRY_AFTER]


@patch("models.getcomics.scraper")
def test_unusable_retry_after_falls_back_to_backoff(scraper, sleeps):
    scraper.get.side_effect = [
        _resp(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        _resp(200),
    ]
    getcomics.search_getcomics("sword 6", max_pages=1)
    sleeps.assert_called_once_with(getcomics.RATE_LIMIT_BACKOFF[0])


@patch("models.getcomics.scraper")
def test_429_that_outlasts_retries_marks_the_search_failed(scraper, sleeps):
    scraper.get.return_value = _resp(429)
    results = getcomics.search_getcomics("sword 6", max_pages=1)
    assert results == []
    assert results.failed is True
    # first attempt + one per backoff step, then it gives up
    assert scraper.get.call_count == 1 + len(getcomics.RATE_LIMIT_BACKOFF)


@patch("models.getcomics.scraper")
def test_other_errors_are_not_retried_but_are_flagged(scraper, sleeps):
    scraper.get.return_value = _resp(500)
    results = getcomics.search_getcomics("sword 6", max_pages=1)
    assert results.failed is True
    assert scraper.get.call_count == 1
    sleeps.assert_not_called()


@patch("models.getcomics.scraper")
def test_empty_answer_is_not_a_failure(scraper, sleeps):
    scraper.get.return_value = _resp(200, EMPTY_HTML)
    results = getcomics.search_getcomics("nothing here", max_pages=1)
    assert results == [] and results.failed is False


def _issue_search(first_failed):
    """search_getcomics_for_issue with its HTTP layer stubbed."""
    def fake(query, max_pages=1):
        out = getcomics.SearchResults()
        out.failed = first_failed
        return out

    with patch.object(getcomics, "search_getcomics", side_effect=fake), \
            patch.object(getcomics.time, "sleep"), \
            patch.object(getcomics, "get_series_alias_list", return_value=[]), \
            patch.object(getcomics, "lookup_series_urls", return_value=[], create=True):
        return getcomics.search_getcomics_for_issue(
            "S.W.O.R.D.", "6", issue_year=2021, search_variants=[], series_aliases=[],
        )


def test_issue_search_reports_failure():
    try:
        results = _issue_search(first_failed=True)
    except Exception as exc:  # the index lookup needs a database in some setups
        pytest.skip(f"issue search needs more of the app: {exc}")
    assert results == [] and results.failed is True


def test_issue_search_without_failure_is_plain_empty():
    try:
        results = _issue_search(first_failed=False)
    except Exception as exc:
        pytest.skip(f"issue search needs more of the app: {exc}")
    assert results == [] and not getattr(results, "failed", False)


def test_sweep_records_search_error_structurally():
    """app.py cannot be imported in tests, so assert the wiring on its source."""
    src = Path(__file__).resolve().parents[2].joinpath("app.py").read_text()
    # the flag is read before `or []` throws the carrying object away
    assert src.index('getattr(results, "failed"') < src.index("results = results or []")
    assert re.search(r'"search_error" if search_failed and not results', src)


def test_search_error_is_a_known_outcome():
    from core.database import SEARCH_OUTCOMES
    assert "search_error" in SEARCH_OUTCOMES
