"""Routes of the Search review page (routes/search_review.py)."""

import pytest

from core import database as db
from core.auth import required_role_for_request


def _attempt(outcome="waiting", n=1, series_id=7):
    return db.record_search_attempt(
        series_id, "New Mutants", str(n), "nightly", outcome,
        [
            {"title": "New Mutants 005", "link": "http://x/1", "score": 50,
             "decision": "ACCEPT", "reason": "series matches and issue #5 is named",
             "chosen": True},
            {"title": "New Mutants - Truth Or Death", "link": "http://x/2", "score": 20,
             "decision": "REJECT", "reason": "arc page, not this series", "chosen": False},
        ],
    )


def test_page_renders(client):
    assert client.get("/search-review").status_code == 200


def test_list_filters_and_counts(client):
    _attempt("waiting", 1)
    _attempt("nothing_found", 2)
    data = client.get("/api/search-review?outcome=waiting").get_json()
    assert [a["issue_number"] for a in data["attempts"]] == ["1"]
    assert data["waiting"] == 1
    assert len(data["attempts"][0]["candidates"]) == 2
    assert client.get("/api/search-review").get_json()["attempts"].__len__() == 2
    assert client.get("/api/search-review?outcome=bogus").status_code == 400


def test_approve_queues_chosen(client, monkeypatch):
    aid = _attempt()
    seen = []
    monkeypatch.setattr("routes.search_review.queue_candidate",
                        lambda a, c: seen.append(c["link"]) or 1)
    assert client.post(f"/api/search-review/{aid}/approve").get_json()["queued"] == 1
    assert seen == ["http://x/1"]
    assert db.get_search_attempt(aid)["outcome"] == "queued"
    # second click does not queue again
    assert client.post(f"/api/search-review/{aid}/approve").status_code == 409
    assert seen == ["http://x/1"]


def test_approve_failure_returns_to_waiting(client, monkeypatch):
    aid = _attempt()

    def boom(a, c):
        raise ValueError("no link")

    monkeypatch.setattr("routes.search_review.queue_candidate", boom)
    assert client.post(f"/api/search-review/{aid}/approve").status_code == 502
    assert db.get_search_attempt(aid)["outcome"] == "waiting"


def test_approve_unknown_and_not_waiting(client):
    assert client.post("/api/search-review/999/approve").status_code == 404
    aid = _attempt("nothing_found")
    assert client.post(f"/api/search-review/{aid}/approve").status_code == 409


def test_skip(client):
    aid = _attempt()
    assert client.post(f"/api/search-review/{aid}/skip").get_json()["success"]
    assert db.get_search_attempt(aid)["outcome"] == "skipped"
    assert client.post(f"/api/search-review/{aid}/skip").status_code == 409
    assert client.post("/api/search-review/999/skip").status_code == 404


def test_research_clears_stamps(client):
    aid = _attempt("nothing_found", series_id=7)
    db.mark_wanted_issue_queued(7, "1")
    assert client.post(f"/api/search-review/{aid}/research").get_json()["success"]
    assert db.get_wanted_queue_stamps(7) == {}
    assert client.post("/api/search-review/999/research").status_code == 404


def test_research_all_clears_every_failed_issue(client):
    _attempt("search_error", 1, series_id=7)
    _attempt("search_error", 2, series_id=8)
    _attempt("nothing_found", 3, series_id=9)
    for sid, issue in ((7, "1"), (8, "2"), (9, "3")):
        db.mark_wanted_issue_queued(sid, issue)
    data = client.post("/api/search-review/research-all").get_json()
    assert data == {"success": True, "issues": 2}
    assert db.get_wanted_queue_stamps(7) == {} and db.get_wanted_queue_stamps(8) == {}
    assert db.get_wanted_queue_stamps(9) != {}  # other outcomes untouched


def test_research_all_rejects_other_outcomes(client):
    r = client.post("/api/search-review/research-all", json={"outcome": "waiting"})
    assert r.status_code == 400


def test_prune_keeps_newest(app, monkeypatch):
    monkeypatch.setattr(db, "SEARCH_ATTEMPTS_KEEP", 3)
    ids = [_attempt(n=i) for i in range(5)]
    kept = [a["id"] for a in db.list_search_attempts()]
    assert kept == sorted(ids[2:], reverse=True)


def test_clerk_only(app):
    with app.test_request_context("/search-review"):
        assert required_role_for_request() == "clerk"
    with app.test_request_context("/api/search-review"):
        assert required_role_for_request() == "clerk"


def test_search_error_outcome_is_listed_and_filterable(client):
    _attempt("search_error", 3)
    _attempt("nothing_found", 4)
    data = client.get("/api/search-review?outcome=search_error").get_json()
    assert [a["issue_number"] for a in data["attempts"]] == ["3"]
    assert client.get("/search-review").status_code == 200


def test_clear_keeps_waiting_picks(client):
    _attempt("waiting", 1)
    _attempt("nothing_found", 2)
    _attempt("search_error", 3)
    r = client.post("/api/search-review/clear", json={}).get_json()
    assert r["success"] and r["removed"] == 2
    left = client.get("/api/search-review").get_json()
    assert [a["outcome"] for a in left["attempts"]] == ["waiting"]


def test_clear_one_outcome_only(client):
    _attempt("nothing_found", 1)
    _attempt("search_error", 2)
    r = client.post("/api/search-review/clear", json={"outcome": "search_error"}).get_json()
    assert r["removed"] == 1
    assert [a["outcome"] for a in client.get("/api/search-review").get_json()["attempts"]] == ["nothing_found"]


def test_clear_refuses_waiting_and_unknown(client):
    _attempt("waiting", 1)
    assert client.post("/api/search-review/clear", json={"outcome": "waiting"}).status_code == 400
    assert client.post("/api/search-review/clear", json={"outcome": "bogus"}).status_code == 400
    assert len(client.get("/api/search-review").get_json()["attempts"]) == 1
