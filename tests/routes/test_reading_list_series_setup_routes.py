"""Routes for setting up a reading list's series.

POST /api/reading-lists/<id>/series-setup/resolve
POST /api/reading-lists/<id>/series-setup/apply
GET  /api/reading-lists/series-setup/<task_id>

The work runs on a thread in production; here the thread runs inline so the
status route can be read straight after.
"""
from unittest.mock import patch

import pytest

from tests.integration.test_series_setup import FakeMetron


class _InlineThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _api():
    return FakeMetron(
        issue_series={5: 100},
        series={100: {"name": "Immortal X-Men", "year_began": 2022, "publisher": "Marvel",
                      "status": "Completed"}},
        issues={100: [{"id": 10010, "number": "10", "cover_date": "2023-01-01",
                       "store_date": "2023-01-01"}]},
    )


@pytest.fixture
def metron(monkeypatch):
    api = _api()
    monkeypatch.setattr("routes.reading_lists.threading.Thread", _InlineThread)
    monkeypatch.setattr("routes.reading_lists.is_metron_configured", lambda: True)
    monkeypatch.setattr("routes.reading_lists.get_flask_api", lambda app=None: api)
    with patch("models.getcomics.prepopulate_series_index"), \
         patch("models.series_json.write_series_json"), \
         patch("models.metron.get_flask_api", return_value=None):
        yield api


def _list():
    from core.database import add_reading_list_entry, create_reading_list

    list_id = create_reading_list("Fall of X")
    add_reading_list_entry(list_id, {"series": "Immortal X-Men", "issue_number": "10",
                                     "year": 2022, "metron_id": 5})
    return list_id


def _status(client, task_id):
    resp = client.get(f"/api/reading-lists/series-setup/{task_id}")
    assert resp.status_code == 200
    return resp.get_json()


class TestResolve:

    def test_unknown_list_is_404(self, client, metron):
        assert client.post("/api/reading-lists/99999/series-setup/resolve").status_code == 404

    def test_needs_metron(self, client, monkeypatch):
        monkeypatch.setattr("routes.reading_lists.is_metron_configured", lambda: False)
        resp = client.post(f"/api/reading-lists/{_list()}/series-setup/resolve")
        assert resp.status_code == 400

    def test_preview_lists_the_series_and_writes_nothing(self, client, metron):
        from core.database import get_series_by_id

        resp = client.post(f"/api/reading-lists/{_list()}/series-setup/resolve")
        assert resp.status_code == 200
        task = _status(client, resp.get_json()["task_id"])

        assert task["status"] == "complete"
        row = task["result"][0]
        assert row["state"] == "resolved"
        assert row["series"]["name"] == "Immortal X-Men"
        assert row["issues"] == ["10"]
        assert get_series_by_id(100) is None


class TestApply:

    def test_no_series_is_400(self, client, metron):
        resp = client.post(f"/api/reading-lists/{_list()}/series-setup/apply", json={"series": []})
        assert resp.status_code == 400

    def test_unknown_list_is_404(self, client, metron):
        resp = client.post("/api/reading-lists/99999/series-setup/apply",
                           json={"series": [{"series_id": 100}]})
        assert resp.status_code == 404

    def test_sets_up_unmonitored_and_tracks_the_list(self, client, metron, tmp_path):
        from core.database import get_reading_list, get_series_by_id

        list_id = _list()
        folder = tmp_path / "Marvel" / "Immortal X-Men"
        resp = client.post(f"/api/reading-lists/{list_id}/series-setup/apply", json={
            "series": [{"series_id": 100, "path": str(folder)}],
        })
        task = _status(client, resp.get_json()["task_id"])

        assert task["status"] == "complete"
        assert task["result"]["series"][0]["ok"] is True
        assert task["result"]["track_wanted"] is True
        assert task["result"]["monitored"] is False
        series = get_series_by_id(100)
        assert series["mapped_path"] == str(folder)
        assert series["monitored"] == 0 and series["monitor_locked"] == 1
        assert get_reading_list(list_id)["track_wanted"] == 1

    def test_options_monitored_and_no_tracking(self, client, metron, tmp_path):
        from core.database import get_reading_list, get_series_by_id

        list_id = _list()
        resp = client.post(f"/api/reading-lists/{list_id}/series-setup/apply", json={
            "series": [{"series_id": 100, "path": str(tmp_path / "IXM")}],
            "monitored": True, "track_wanted": False,
        })
        task = _status(client, resp.get_json()["task_id"])

        assert task["result"]["track_wanted"] is False
        assert task["result"]["monitored"] is True
        assert get_series_by_id(100)["monitored"] == 1
        assert not get_reading_list(list_id)["track_wanted"]

    @pytest.mark.parametrize("value", [None, False, "false", "true", 1, 0])
    def test_only_a_real_true_monitors(self, client, metron, tmp_path, value):
        """Anything but JSON true (absent, false, a string, a number) means Not monitored."""
        from core.database import get_series_by_id

        body = {"series": [{"series_id": 100, "path": str(tmp_path / "IXM")}]}
        if value is not None:
            body["monitored"] = value
        resp = client.post(f"/api/reading-lists/{_list()}/series-setup/apply", json=body)
        _status(client, resp.get_json()["task_id"])
        assert get_series_by_id(100)["monitored"] == 0

    def test_every_series_in_a_run_gets_the_setting(self, client, metron, tmp_path):
        """Not just the first: each of several series comes out Not monitored and locked."""
        from core.database import get_series_by_id

        metron._series.update({101: {"name": "X-Men", "year_began": 2021},
                               102: {"name": "Inferno", "year_began": 2021}})
        resp = client.post(f"/api/reading-lists/{_list()}/series-setup/apply", json={
            "series": [{"series_id": sid, "path": str(tmp_path / str(sid))} for sid in (100, 101, 102)],
            "monitored": False,
        })
        _status(client, resp.get_json()["task_id"])
        for sid in (100, 101, 102):
            row = get_series_by_id(sid)
            assert (row["monitored"], row["monitor_locked"]) == (0, 1), sid

    def test_metron_unavailable_reports_an_error(self, client, metron, monkeypatch):
        monkeypatch.setattr("routes.reading_lists.get_flask_api", lambda app=None: None)
        resp = client.post(f"/api/reading-lists/{_list()}/series-setup/apply",
                           json={"series": [{"series_id": 100}]})
        task = _status(client, resp.get_json()["task_id"])
        assert task["status"] == "error"
        assert "Metron" in task["message"]


class TestStatus:

    def test_unknown_task_is_404(self, client):
        assert client.get("/api/reading-lists/series-setup/nope").status_code == 404


class TestPage:

    def test_manager_sees_the_menu_item_and_dialog(self, client):
        html = client.get(f"/reading-lists/{_list()}").get_data(as_text=True)
        assert 'id="seriesSetupBtn"' in html
        assert 'id="seriesSetupModal"' in html
        assert "reading-list-series-setup.js" in html
