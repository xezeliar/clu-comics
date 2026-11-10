"""Download queue page: core/download_queue_ctl.py and routes/download_queue.py."""

import sys
import types
from queue import Queue

import pytest

from core import download_queue_ctl as ctl
from core.auth import required_role_for_request


def _role(app, path, method="GET"):
    with app.test_request_context(path, method=method):
        return required_role_for_request()


@pytest.fixture
def fake_api(monkeypatch):
    mod = types.ModuleType("api")
    mod.download_queue = Queue()
    mod.download_progress = {}
    monkeypatch.setitem(sys.modules, "api", mod)
    yield mod
    ctl.set_paused(False)


def _queue(api, *ids):
    for i in ids:
        api.download_progress[i] = {"status": "queued", "url": f"http://x/{i}", "progress": 0}
        api.download_queue.put({"download_id": i})


def test_view_classifies_and_orders_queue(client, fake_api):
    _queue(fake_api, "a", "b")
    fake_api.download_progress.update({
        "run": {"status": "in_progress", "filename": "/w/Batman.cbz", "progress": 40},
        "bad": {"status": "error", "error": "mirror down"},
        "done": {"status": "complete"},
    })
    ctl.reorder_queue(fake_api.download_queue, ["b", "a"])
    d = client.get("/api/download-queue").get_json()
    assert [r["id"] for r in d["queued"]] == ["b", "a"]
    assert d["active"][0]["name"] == "Batman.cbz"
    assert d["failed"][0]["error"] == "mirror down"
    assert d["history"][0]["id"] == "done"


def test_reorder_only_moves_listed_tasks_and_keeps_sentinel(client, fake_api):
    _queue(fake_api, "a", "b", "c")
    fake_api.download_queue.put(None)
    r = client.post("/api/download-queue/reorder", json={"order": ["c", "a"]})
    assert r.get_json()["placed"] == 2
    items = list(fake_api.download_queue.queue)
    assert [t and t["download_id"] for t in items] == ["c", "b", "a", None]


def test_reorder_rejects_bad_body(client, fake_api):
    assert client.post("/api/download-queue/reorder", json={"order": "x"}).status_code == 400


def test_remove_queued(client, fake_api):
    _queue(fake_api, "a", "b")
    assert client.delete("/api/download-queue/a").get_json()["success"] is True
    assert "a" not in fake_api.download_progress
    assert [t["download_id"] for t in fake_api.download_queue.queue] == ["b"]
    assert client.delete("/api/download-queue/a").status_code == 404


def test_pause_resume(client, fake_api):
    assert client.post("/api/download-queue/pause", json={"paused": True}).get_json()["paused"]
    assert client.get("/api/download-queue").get_json()["paused"] is True
    assert not client.post("/api/download-queue/pause", json={"paused": False}).get_json()["paused"]


def test_page_and_roles(app, client):
    assert client.get("/download-queue").status_code == 200
    assert _role(app, "/download-queue", "GET") == "clerk"
    assert _role(app, "/api/download-queue/pause", "POST") == "clerk"


def test_worker_waits_while_paused_structurally():
    src = open("api.py").read()
    body = src[src.index("def worker():"):src.index("worker_threads = []")]
    assert body.count("wait_if_paused()") == 2
    assert body.index("wait_if_paused()") < body.index("download_queue.get()")
    assert "set_paused(False)" in src[src.index("def shutdown_handler"):]
