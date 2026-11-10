"""Release calendar: core/release_calendar.py and routes/release_calendar.py."""

from datetime import date, datetime
from types import SimpleNamespace as NS

from core.auth import required_role_for_request


def _role(app, path, method="GET"):
    with app.test_request_context(path, method=method):
        return required_role_for_request()
from core.release_calendar import build_week


def _issue(name, number, d, sid=1, volume=2016):
    return NS(series=NS(name=name, id=sid, volume=volume), number=number, store_date=d)


NORM = lambda s: s.lower()  # noqa: E731


def test_build_week_marks_and_orders():
    start = datetime(2026, 11, 8)  # Sunday
    wed = date(2026, 11, 11)
    rel = [_issue("Saga", "70", wed, sid=2), _issue("Batman", "14", wed, sid=1),
           _issue("Out", "1", date(2027, 1, 1))]
    days = build_week(start, rel, {1}, set(), NORM, lambda n, num, v: n == "Batman")
    assert [d["is_release_day"] for d in days] == [False, False, False, True, False, False, False]
    items = days[3]["items"]
    assert [i["series"] for i in items] == ["Batman", "Saga"]
    assert items[0]["on_pull_list"] and items[0]["in_library"]
    assert not items[1]["on_pull_list"] and not items[1]["in_library"]
    assert sum(len(d["items"]) for d in days) == 2  # out-of-week dropped


def test_name_volume_fallback_and_owned_only_asked_for_tracked():
    asked = []
    days = build_week(datetime(2026, 11, 8), [_issue("Nightwing", "5", date(2026, 11, 11), sid=9, volume=3),
                                              _issue("Other", "1", date(2026, 11, 11), sid=8)],
                      set(), {("nightwing", 3)}, NORM, lambda *a: asked.append(a) or False)
    assert days[3]["items"][0]["on_pull_list"] is True
    assert len(asked) == 1


def test_api_week(client, monkeypatch):
    from models import metron

    monkeypatch.setattr(metron, "get_flask_api", lambda: object())
    monkeypatch.setattr(metron, "get_releases",
                        lambda api, a, b: [_issue("Batman", "14", date(2026, 11, 11))])
    d = client.get("/api/release-calendar?date=2026-11-10").get_json()
    assert d["start"] == "2026-11-08" and d["end"] == "2026-11-14"
    assert d["prev"] == "2026-11-01" and d["next"] == "2026-11-15"
    assert d["days"][3]["items"][0]["series"] == "Batman"


def test_api_requires_metron_and_valid_date(client, monkeypatch):
    from models import metron

    assert client.get("/api/release-calendar?date=bad").status_code == 400
    monkeypatch.setattr(metron, "get_flask_api", lambda: None)
    assert client.get("/api/release-calendar").status_code == 503


def test_page_and_roles(app, client):
    assert client.get("/release-calendar").status_code == 200
    assert _role(app, "/release-calendar", "GET") == "clerk"
    assert _role(app, "/api/release-calendar", "GET") == "clerk"
