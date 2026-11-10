"""Activity feed: core/activity.py and routes/activity.py."""

from core import activity as act
from core.auth import required_role_for_request


def _role(app, path, method="GET"):
    with app.test_request_context(path, method=method):
        return required_role_for_request()


def test_record_and_list_newest_first(client):
    act.record_event("download", "A")
    act.record_event("move", "B")
    data = client.get("/api/activity").get_json()
    assert [e["title"] for e in data["events"]] == ["B", "A"]
    assert data["events"][0]["ts_display"]


def test_filter_by_kind_and_error_count(client):
    act.record_event("download", "ok")
    act.record_event("error", "bad", path="/x/y.cbz")
    data = client.get("/api/activity?kind=error").get_json()
    assert [e["title"] for e in data["events"]] == ["bad"]
    assert data["events"][0]["level"] == "error"
    assert data["errors_24h"] == 1


def test_paging_by_before(client):
    for i in range(5):
        act.record_event("sweep", f"s{i}")
    first = client.get("/api/activity?limit=2").get_json()["events"]
    nxt = client.get(f"/api/activity?limit=2&before={first[-1]['id']}").get_json()["events"]
    assert [e["title"] for e in first + nxt] == ["s4", "s3", "s2", "s1"]


def test_bad_params(client):
    assert client.get("/api/activity?kind=nope").status_code == 400
    assert client.get("/api/activity?limit=x").status_code == 400


def test_unknown_kind_not_recorded(client):
    assert act.record_event("bogus", "x") is False


def test_empty_is_empty_list(client):
    assert client.get("/api/activity").get_json()["events"] == []


def test_read_failure_is_500(client, monkeypatch):
    monkeypatch.setattr("routes.activity.list_events", lambda **kw: None)
    assert client.get("/api/activity").status_code == 500


def test_prune_caps_rows(client, monkeypatch):
    from core.database import db_conn

    monkeypatch.setattr(act, "MAX_ROWS", 3)
    for i in range(6):
        act.record_event("sweep", f"s{i}")
    with db_conn() as conn:
        act.prune(conn)
        conn.commit()
    assert [e["title"] for e in act.list_events()] == ["s5", "s4", "s3"]


def test_page_renders_and_is_clerk_level(app, client):
    assert client.get("/activity").status_code == 200
    assert _role(app, "/activity", "GET") == "clerk"
    assert _role(app, "/api/activity", "GET") == "clerk"


def test_poller_hook_records(client):
    from core.notifications import notify_download_terminal

    notify_download_terminal("complete", "Batman 001.cbz", source="usenet")
    notify_download_terminal("failed", "Saga 002.cbz", error="boom", source="usenet")
    kinds = [e["kind"] for e in act.list_events()]
    assert kinds == ["error", "download"]


def test_run_finish_records_one_sweep_row(client):
    from core import download_runs as dr

    rec = dr.start_run(dr.KIND_GETCOMICS)
    rec.item("Batman", "1", dr.OUTCOME_QUEUED, download_id="d1")
    rec.finish(dr.STATUS_OK)
    (ev,) = act.list_events()
    assert ev["kind"] == "sweep" and "1 issues" in ev["title"]


def test_new_problem_file_records_once(client, tmp_path):
    from core.problem_files import record_problem

    p = str(tmp_path / "Hellboy 003.cbz")
    record_problem(p, "scan", error_class="Bad", error_message="Corrupt archive")
    record_problem(p, "scan", error_class="Bad", error_message="Corrupt archive")
    events = act.list_events(kind="error")
    assert len(events) == 1 and events[0]["path"] == p
