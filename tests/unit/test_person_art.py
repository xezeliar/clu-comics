"""core/person_art.py and the team queries in core/creators.py, against a fake Metron."""

import io
import os
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from PIL import Image

from core import creators, person_art


def _jpeg(w=800, h=600):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


class FakeMetron:
    """Only the MetronClient methods resolve() uses; None = failed request."""

    def __init__(self, lists=None, details=None, fail_list=False):
        self.lists = lists or {}
        self.details = details or {}
        self.fail_list = fail_list
        self.calls = []

    def _list(self, kind, params):
        self.calls.append((kind + "_list", params))
        return None if self.fail_list else self.lists.get((kind, params["name"]), [])

    def characters_list(self, params):
        return self._list("characters", params)

    def creators_list(self, params):
        return self._list("creators", params)

    def teams_list(self, params):
        return self._list("teams", params)

    def publishers_list(self, params):
        return self._list("publishers", params)

    def _detail(self, kind, _id):
        self.calls.append((kind, _id))
        return self.details.get((kind, _id))

    def character(self, _id):
        return self._detail("character", _id)

    def creator(self, _id):
        return self._detail("creator", _id)

    def team(self, _id):
        return self._detail("team", _id)

    def publisher(self, _id):
        return self._detail("publisher", _id)


@pytest.fixture
def cache(tmp_path, db_connection):
    with patch("core.person_art.get_cache_dir", return_value=str(tmp_path)):
        yield tmp_path


def _row(conn, kind, name):
    r = conn.execute("SELECT * FROM person_art WHERE kind = ? AND key = ?",
                     (kind, name.casefold())).fetchone()
    return dict(r) if r else None


BATMAN_API = dict(
    lists={("characters", "Batman"): [NS(id=2, name="Batman (Earth-2)"), NS(id=1, name="BATMAN")]},
    details={("character", 1): NS(id=1, name="Batman", image="https://img/batman.jpg",
                                 teams=[NS(id=10, name="Justice League"), NS(id=11, name="Outsiders")]),
             ("team", 10): NS(id=10, name="Justice League", image="https://img/jl.jpg")},
)


class TestResolve:
    def test_exact_match_stores_resized_image(self, cache, db_connection):
        api = FakeMetron(**BATMAN_API)
        fetched = []
        status = person_art.resolve("character", "Batman", api,
                                    lambda url: fetched.append(url) or _jpeg())
        assert status == "ok"
        assert fetched == ["https://img/batman.jpg"]
        row = _row(db_connection, "character", "Batman")
        assert row["metron_id"] == 1 and row["status"] == "ok"
        path = person_art.image_path("character", "batman")
        assert path.startswith(str(cache)) and os.path.isfile(path)
        with Image.open(path) as img:
            assert max(img.size) == 400 and img.format == "JPEG"
        # no temp file left behind in the shard dir
        assert os.listdir(os.path.dirname(path)) == [os.path.basename(path)]

    def test_no_exact_match_is_missing_and_never_guessed(self, cache, db_connection):
        api = FakeMetron(lists={("creators", "Tom King"): [NS(id=5, name="Tom Kingsley")]})
        assert person_art.resolve("creator", "Tom King", api, lambda u: _jpeg()) == "missing"
        assert ("creator", 5) not in api.calls
        assert _row(db_connection, "creator", "Tom King")["status"] == "missing"

    def test_failed_request_is_error_not_missing(self, cache, db_connection):
        api = FakeMetron(fail_list=True)
        assert person_art.resolve("creator", "Tom King", api, lambda u: _jpeg()) == "error"
        assert _row(db_connection, "creator", "Tom King")["status"] == "error"

    def test_character_teams_stored_and_team_rows_created(self, cache, db_connection):
        person_art.resolve("character", "Batman", FakeMetron(**BATMAN_API), lambda u: _jpeg())
        teams = db_connection.execute(
            "SELECT team_key, team_name, team_metron_id FROM character_teams"
            " WHERE character_key = 'batman' ORDER BY team_key").fetchall()
        assert [tuple(t) for t in teams] == [("justice league", "Justice League", 10),
                                             ("outsiders", "Outsiders", 11)]
        team = _row(db_connection, "team", "Justice League")
        assert team["metron_id"] == 10 and team["status"] is None

    def test_team_with_known_id_skips_the_list_lookup(self, cache, db_connection):
        api = FakeMetron(**BATMAN_API)
        person_art.resolve("character", "Batman", api, lambda u: _jpeg())
        api.calls.clear()
        assert person_art.resolve("team", "Justice League", api, lambda u: _jpeg()) == "ok"
        assert api.calls == [("team", 10)]

    def test_no_image_is_missing(self, cache, db_connection):
        api = FakeMetron(lists={("publishers", "DC"): [NS(id=3, name="DC")]},
                         details={("publisher", 3): NS(id=3, name="DC", image=None)})
        assert person_art.resolve("publisher", "DC", api, lambda u: _jpeg()) == "missing"


def _seed_library(conn):
    from core.database import _backfill_file_metadata_tags

    def f(path, chars, writer="W"):
        parent, name = path.rsplit("/", 1)
        conn.execute(
            "INSERT INTO file_index (name, path, type, size, parent, has_comicinfo,"
            " ci_series, ci_number, ci_publisher, ci_characters, ci_writer)"
            " VALUES (?, ?, 'file', 1, ?, 1, ?, '1', 'DC', ?, ?)",
            (name, path, parent, parent.rsplit("/", 1)[-1], chars, writer))
    f("/data/DC/Batman/B1.cbz", "Batman, Joker")
    f("/data/DC/Batman/B2.cbz", "Batman, Superman")
    f("/data/DC/Superman/S1.cbz", "Superman")
    f("/data/DC/Flash/F1.cbz", "Flash")
    conn.commit()
    _backfill_file_metadata_tags(conn)


class TestSweep:
    def test_respects_limit_and_resolves_characters_first(self, cache, db_connection):
        _seed_library(db_connection)
        api = FakeMetron(**BATMAN_API)
        with patch("models.metron.paused_reason", return_value=None):
            summary = person_art.sweep(limit=2, api=api, fetch_image=lambda u: _jpeg())
        assert sum(summary.values()) == 2
        kinds = {r["kind"] for r in db_connection.execute("SELECT kind FROM person_art WHERE status IS NOT NULL")}
        assert kinds == {"character"}

    def test_paused_is_a_quiet_no_op(self, cache, db_connection):
        _seed_library(db_connection)
        api = FakeMetron(**BATMAN_API)
        with patch("models.metron.paused_reason", return_value="Metron is down"):
            assert person_art.sweep(limit=5, api=api, fetch_image=lambda u: _jpeg()) == {}
        assert api.calls == []

    def test_resolved_names_are_not_due_again(self, cache, db_connection):
        _seed_library(db_connection)
        api = FakeMetron(**BATMAN_API)
        with patch("models.metron.paused_reason", return_value=None):
            person_art.sweep(limit=100, api=api, fetch_image=lambda u: _jpeg())
            # Teams are discovered by the first pass and fetched by the next.
            assert {k for k, _ in person_art.pending(100)} == {"team"}
            person_art.sweep(limit=100, api=api, fetch_image=lambda u: _jpeg())
            assert person_art.pending(100) == []


class TestTeams:
    @pytest.fixture
    def teams(self, cache, db_connection):
        _seed_library(db_connection)
        api = FakeMetron(
            lists={("characters", "Batman"): [NS(id=1, name="Batman")],
                   ("characters", "Superman"): [NS(id=2, name="Superman")],
                   ("characters", "Flash"): [NS(id=3, name="Flash")]},
            details={("character", 1): NS(id=1, image=None, teams=[NS(id=10, name="Justice League")]),
                     ("character", 2): NS(id=2, image=None, teams=[NS(id=10, name="Justice League")]),
                     ("character", 3): NS(id=3, image=None, teams=[])})
        for n in ("Batman", "Superman", "Flash"):
            person_art.resolve("character", n, api, lambda u: None)
        return db_connection

    def test_list_teams_counts_distinct_issues(self, teams):
        assert creators.list_teams(prefixes=["/data"]) == [{"name": "Justice League", "n": 3}]
        assert creators.list_teams(q="xyz", prefixes=["/data"]) == []

    def test_character_on_no_team_is_not_refetched(self, teams):
        assert ("character", "Flash") not in person_art.pending(100)

    def test_team_page_and_members(self, teams):
        data = creators.team_page("justice league", prefixes=["/data"])
        assert data["name"] == "Justice League"
        assert data["issues"] == 3
        assert data["members"] == [{"name": "Batman", "n": 2}, {"name": "Superman", "n": 2}]
        assert {s["name"] for s in data["series"]} == {"Batman", "Superman"}
        assert [o["name"] for o in data["often_with"]] == ["Joker"]
        assert creators.team_page("Avengers", prefixes=["/data"]) is None

    def test_team_issues(self, teams):
        issues = creators.team_issues("Justice League", "/data/DC/Batman", prefixes=["/data"])
        assert [i["name"] for i in issues] == ["B1.cbz", "B2.cbz"]

    def test_read_team_counts_once_per_issue(self, teams):
        assert creators.read_team_counts([["Batman", "Superman"], ["Flash"], ["batman"]]) == [
            ("Justice League", 2)]


class TestArtUrls:
    def test_only_ok_rows_with_a_file_get_a_url(self, cache, db_connection):
        from flask import Flask
        from routes.creators import creators_bp

        person_art.resolve("character", "Batman", FakeMetron(**BATMAN_API), lambda u: _jpeg())
        app = Flask(__name__)
        app.register_blueprint(creators_bp)
        with app.test_request_context():
            urls = person_art.art_urls("character", ["Batman", "Joker"])
        assert urls["Joker"] is None
        assert urls["Batman"].startswith("/api/person-art/character/Batman?v=")
