"""core/entity_profiles.py: Metron + ComicVine profiles stored by person_art.resolve."""

from datetime import date, timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from core import entity_profiles, person_art
from tests.unit.test_person_art import FakeMetron, _jpeg


@pytest.fixture
def cache(tmp_path, db_connection):
    with patch("core.person_art.get_cache_dir", return_value=str(tmp_path)):
        yield tmp_path


class FakeCV:
    def __init__(self, records=None, fail=False):
        self.records, self.fail, self.calls = records or {}, fail, []

    def _get(self, kind, _id):
        self.calls.append((kind, _id))
        if self.fail:
            raise RuntimeError("ComicVine is down")
        return self.records[(kind, _id)]

    def get_character(self, _id):
        return self._get("character", _id)

    def get_team(self, _id):
        return self._get("team", _id)

    def get_creator(self, _id):
        return self._get("creator", _id)


BATMAN = NS(id=1, name="Batman", image=None, teams=[], cv_id=1699, gcd_id=7,
            desc="The Dark Knight.", alias=["The Bat"],
            resource_url="https://metron.cloud/character/batman/",
            universes=[NS(id=1, name="Earth 0")], creators=[NS(id=2, name="Bob Kane")])
BATMAN_CV = NS(
    summary="Billionaire detective.", aliases="Matches Malone\nThe Bat-Man\n",
    image=NS(original_url="https://cv/b.jpg"), real_name="Bruce Wayne",
    first_issue=NS(id=5, name="The Case of the Chemical Syndicate", number="27"),
    origin=NS(name="Human"), powers=[NS(name="Genius Intellect")],
    friends=[NS(id=9, name="Alfred")], enemies=[NS(id=8, name="Joker")],
    teams=[NS(id=3, name="Justice League")], creators=[NS(id=4, name="Bill Finger")],
    site_url="javascript:alert(1)")


def _api():
    return FakeMetron(lists={("characters", "Batman"): [NS(id=1, name="Batman")]},
                      details={("character", 1): BATMAN})


def test_resolve_stores_metron_and_comicvine(cache, db_connection):
    cv = FakeCV({("character", 1699): BATMAN_CV})
    person_art.resolve("character", "Batman", _api(), lambda u: None, cv)
    p = entity_profiles.get_profile("character", "batman")
    assert (p["status"], p["metron_id"], p["cv_id"], p["error"]) == ("ok", 1, 1699, None)
    assert p["metron"] == {"desc": "The Dark Knight.", "gcd_id": 7, "alias": ["The Bat"],
                           "url": "https://metron.cloud/character/batman/",
                           "universes": ["Earth 0"], "creators": ["Bob Kane"]}
    assert p["cv"]["aliases"] == ["Matches Malone", "The Bat-Man"]
    assert p["cv"]["first_issue"] == {"id": 5, "name": "The Case of the Chemical Syndicate",
                                      "number": "27"}
    assert p["cv"]["enemies"] == [{"id": 8, "name": "Joker"}]
    assert p["cv"]["real_name"] == "Bruce Wayne" and p["cv"]["origin"] == "Human"
    assert p["cv"]["teams"] == ["Justice League"] and p["cv"]["creators"] == ["Bill Finger"]
    assert p["cv"]["url"] is None  # only http(s) becomes an href
    assert p["metron_fetched_at"] and p["cv_fetched_at"]
    assert cv.calls == [("character", 1699)]


def test_comicvine_only_through_metron_cv_id(cache, db_connection):
    api = FakeMetron(lists={("characters", "Batman"): [NS(id=1, name="Batman")]},
                     details={("character", 1): NS(id=1, image=None, teams=[], cv_id=None)})
    cv = FakeCV()
    person_art.resolve("character", "Batman", api, lambda u: None, cv)
    assert cv.calls == [] and entity_profiles.get_profile("character", "Batman")["cv"] is None


def test_failed_refetch_keeps_old_data(cache, db_connection):
    person_art.resolve("character", "Batman", _api(), lambda u: None,
                       FakeCV({("character", 1699): BATMAN_CV}))
    person_art.resolve("character", "Batman", _api(), lambda u: None, FakeCV(fail=True))
    p = entity_profiles.get_profile("character", "Batman")
    assert p["status"] == "ok" and p["error"] == "ComicVine: ComicVine is down"
    assert p["cv"]["real_name"] == "Bruce Wayne"

    dead = FakeMetron(lists={("characters", "Batman"): [NS(id=1, name="Batman")]})
    person_art.resolve("character", "Batman", dead, lambda u: None)
    p = entity_profiles.get_profile("character", "Batman")
    assert p["status"] == "error" and p["error"] == "Metron detail request failed"
    assert p["metron"]["desc"] == "The Dark Knight." and p["cv"]["real_name"] == "Bruce Wayne"


def test_no_metron_match_is_missing(cache, db_connection):
    person_art.resolve("creator", "Nobody", FakeMetron(), lambda u: None)
    assert entity_profiles.get_profile("creator", "Nobody")["status"] == "missing"
    assert not entity_profiles.is_due("creator", "Nobody", person_art._utcnow())


def test_creator_fields_and_sanitized_description(cache, db_connection):
    api = FakeMetron(
        lists={("creators", "Mara Quell"): [NS(id=4, name="Mara Quell")]},
        details={("creator", 4): NS(id=4, image=None, cv_id=40, gcd_id=None, desc="",
                                    alias=None, birth=date(1970, 1, 2), death=None)})
    cv = FakeCV({("creator", 40): NS(
        summary="Writer.", aliases=None, image=None, hometown="Leeds", country="UK",
        website="https://mara.example", description='<p onclick="x()">Hi<script>bad()</script></p>')})
    person_art.resolve("creator", "Mara Quell", api, lambda u: None, cv)
    p = entity_profiles.get_profile("creator", "Mara Quell")
    assert p["metron"] == {"desc": None, "gcd_id": None, "url": None, "alias": [],
                           "birth": "1970-01-02", "death": None}
    assert (p["cv"]["hometown"], p["cv"]["country"], p["cv"]["website"]) == (
        "Leeds", "UK", "https://mara.example")
    assert "script" not in p["cv"]["description"] and "onclick" not in p["cv"]["description"]


def test_publishers_have_no_profile(cache, db_connection):
    api = FakeMetron(lists={("publishers", "DC"): [NS(id=3, name="DC")]},
                     details={("publisher", 3): NS(id=3, name="DC", image=None)})
    person_art.resolve("publisher", "DC", api, lambda u: None)
    assert entity_profiles.get_profile("publisher", "DC") is None


class TestEnsure:
    @pytest.fixture
    def started(self):
        calls = []
        with patch("core.person_art.threading.Thread",
                   lambda **kw: NS(start=lambda: calls.append(kw["args"]))):
            yield calls
        person_art._in_flight.clear()

    def test_photo_cached_but_no_profile_is_fetched(self, cache, db_connection, started):
        person_art._save("character", "Batman", 1, "ok", "x.jpg")
        assert person_art.ensure(object(), "character", "Batman") is True

    def test_stored_profile_is_not_fetched_again(self, cache, db_connection, started):
        person_art._save("character", "Batman", 1, "ok", "x.jpg")
        entity_profiles.store("character", "Batman", BATMAN)
        assert person_art.ensure(object(), "character", "Batman") is False
        assert person_art.ensure(object(), "character", "Batman", force=True) is True

    def test_error_is_retried_after_the_window(self, cache, db_connection, started):
        person_art._save("character", "Batman", 1, "ok", "x.jpg")
        entity_profiles.record_error("character", "Batman", "down")
        now = person_art._utcnow()
        assert not entity_profiles.is_due("character", "Batman", now)
        assert entity_profiles.is_due("character", "Batman", now + timedelta(minutes=16))
