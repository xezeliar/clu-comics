"""Story-arc pages must not score as every issue of their parent series.

A reading-list sweep for Dawn of X downloaded "New Mutants – Truth Or Death
#1 – 3 (1997)" for New Mutants #5, "Wolverine – Paradise #1" for Wolverine #2,
"X-Men – Road To Onslaught Omnibus v02" for X-Men #4 and so on. Two bugs:

* the page-title cleanup cut at the first " – ", which is also the
  series/arc separator, so the title scored was just "New Mutants";
* a bare series name with no issue number scored 45 (accept bar 40) for any
  issue, because nothing in it contradicted the wanted number.
"""

from unittest.mock import MagicMock, patch

import pytest


def _decide(title, series, issue, issue_year=None, volume_year=None):
    from models.getcomics import score_getcomics_result, accept_result
    return accept_result(*score_getcomics_result(
        title, series, issue, issue_year, volume_year=volume_year))


class TestSiteSuffix:

    @pytest.mark.parametrize("raw, expected", [
        ("New Mutants – Truth Or Death #1 – 3 (1997) – GetComics",
         "New Mutants – Truth Or Death #1 – 3 (1997)"),
        ("Wolverine – Paradise #1 (2026) | GetComics",
         "Wolverine – Paradise #1 (2026)"),
        ("X-Men #4 (2019) - GetComics", "X-Men #4 (2019)"),
        ("Top 10 #1 - 12 (1999)", "Top 10 #1 - 12 (1999)"),
        ("X-Men #4 (2019)", "X-Men #4 (2019)"),
    ])
    def test_only_the_site_name_is_dropped(self, raw, expected):
        from models.getcomics import strip_getcomics_site_suffix
        assert strip_getcomics_site_suffix(raw) == expected


class TestBareSeriesTitle:

    @pytest.mark.parametrize("title, series, issue", [
        ("X-Men", "X-Men", "4"),
        ("Wolverine", "Wolverine", "2"),
        ("New Mutants", "New Mutants", "5"),
        ("X-Force", "X-Force", "2"),
    ])
    def test_bare_name_is_not_a_direct_match(self, title, series, issue):
        assert _decide(title, series, issue, 2020, 2019) != "ACCEPT"

    @pytest.mark.parametrize("title, series, issue", [
        ("New Mutants - Truth Or Death #1 - 3 (1997)", "New Mutants", "5"),
        ("New Mutants - Dead Souls #4 (2018)", "New Mutants", "4"),
        ("Wolverine - Paradise #1 (2026)", "Wolverine", "2"),
        ("X-Force - Champions '98 #1 (1998)", "X-Force", "2"),
        ("X-Men - Road To Onslaught Omnibus v02", "X-Men", "4"),
    ])
    def test_arc_titles_are_rejected(self, title, series, issue):
        assert _decide(title, series, issue, 2020, 2019) == "REJECT"

    def test_the_real_issue_still_accepts(self):
        assert _decide("X-Men #4 (2020)", "X-Men", "4", 2020, 2019) == "ACCEPT"

    def test_numberless_one_shot_still_accepts_issue_1(self):
        from models.getcomics import score_getcomics_result
        score, _, _ = score_getcomics_result("Juggernaut (2020)", "Juggernaut", "1", 2020)
        assert score >= 40


ARC_PAGE = """<html><head>
<title>New Mutants – Truth Or Death #1 – 3 (1997) – GetComics</title>
</head><body><div class="post-contents">
<a class="aio-red" href="https://getcomics.org/dls/x">Download Now</a>
</div></body></html>"""


@patch("models.getcomics.scraper")
def test_arc_page_is_not_a_candidate_for_a_main_series_issue(mock_scraper):
    from models.getcomics import scrape_and_score_candidate
    mock_scraper.get.return_value = MagicMock(status_code=200, text=ARC_PAGE)

    assert scrape_and_score_candidate(
        "https://getcomics.org/marvel/new-mutants-truth-or-death/",
        "New Mutants", "5", 2020, volume_year=2020) is None
