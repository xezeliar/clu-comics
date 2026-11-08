"""core.series_subscribe.build_subscribe_path -- the Python twin of the Subscribe dialog.

Bulk series setup has no dialog, so it builds the folder in Python. It must give
the folder buildSubscribePath() in templates/series.html gives, including the
#616 rule that a repeated token is replaced every time.
"""
import re
from pathlib import Path

import pytest

from core.series_subscribe import build_subscribe_path, clean_folder_path

ROOT = Path(__file__).resolve().parents[2]

GREEN_LANTERN = {"publisher_name": "DC Comics", "name": "Green Lantern",
                 "year_began": 2021, "volume": 7}


@pytest.fixture(autouse=True)
def default_char_map(monkeypatch):
    monkeypatch.setattr("core.filename_chars.load_char_map", lambda: {":": " -"})


def test_default_pattern():
    assert build_subscribe_path(GREEN_LANTERN, "/data") == "/data/DC Comics/Green Lantern/v2021"


def test_repeated_token_resolves_everywhere():
    """The same case the node test in test_subscribe_path_tokens.py runs."""
    pattern = "{publisher}/{series_name}/{series_name} {volume_number} ({start_year}) {issue_number}"
    assert build_subscribe_path(GREEN_LANTERN, "/data", pattern) == \
        "/data/DC Comics/Green Lantern/Green Lantern v7 (2021)"


def test_missing_values_leave_no_empty_brackets():
    series = {"publisher_name": "Image", "name": "Saga"}
    assert build_subscribe_path(series, "/data", "{publisher}/{series_name} ({start_year}) [{volume_number}]") \
        == "/data/Image/Saga"


def test_names_go_through_the_character_map():
    series = {"publisher_name": "Marvel", "name": "X-Men: Red", "year_began": 2022}
    assert build_subscribe_path(series, "/data", "{publisher}/{series_name}") == "/data/Marvel/X-Men - Red"


def test_publisher_may_be_nested_as_from_metron():
    series = {"publisher": {"name": "Marvel"}, "name": "Inferno", "year_began": 2021}
    assert build_subscribe_path(series, "/lib/", "{publisher}/{series_name}") == "/lib/Marvel/Inferno"


def test_unknown_publisher_and_name():
    assert build_subscribe_path({}, "/data", "{publisher}/{series_name}") == "/data/Unknown/Unknown"


def test_relative_when_no_library_given():
    assert build_subscribe_path(GREEN_LANTERN, "", "{publisher}/{series_name}") == "/DC Comics/Green Lantern"


def test_same_tokens_as_the_dialog():
    src = (ROOT / "templates" / "series.html").read_text(encoding="utf-8")
    body = src[src.index("function buildSubscribePath()"):src.index("function openSubscribeModal()")]
    js_tokens = set(re.findall(r"/\\\{(\w+)\\\}/g", body))
    assert js_tokens == {"publisher", "series_name", "start_year", "volume_number"}


class TestCleanFolderPath:

    def test_hostile_characters_removed_separators_kept(self):
        assert clean_folder_path("/data/DC/Batman: Year One?") == "/data/DC/Batman - Year One"

    @pytest.mark.parametrize("path", ["", "/", "/<>|?*/", "   "])
    def test_nothing_usable_is_empty(self, path):
        assert clean_folder_path(path) == ""
