"""Reading-list folders: nested, a list sits in one, deleting never deletes lists."""
import pytest
from core.database import create_reading_list


def _folder(client, name, parent_id=None):
    r = client.post("/api/reading-lists/folders", json={"name": name, "parent_id": parent_id})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["folder_id"]


class TestFolderApi:

    def test_create_nested_and_reject_bad_input(self, client):
        a = _folder(client, "Marvel")
        b = _folder(client, "Events", a)
        assert b != a
        for body in ({"name": " "}, {"name": "x", "parent_id": 9999}, {"name": "x", "parent_id": "1"}):
            assert client.post("/api/reading-lists/folders", json=body).status_code == 400

    def test_rename(self, client):
        a = _folder(client, "Old")
        assert client.patch(f"/api/reading-lists/folders/{a}", json={"name": "New"}).status_code == 200
        assert "New" in client.get("/reading-lists").get_data(as_text=True)
        assert client.patch(f"/api/reading-lists/folders/{a}", json={}).status_code == 400
        assert client.patch(f"/api/reading-lists/folders/{a}", json={"name": ""}).status_code == 400

    def test_move_refuses_cycles(self, client):
        a = _folder(client, "A")
        b = _folder(client, "B", a)
        c = _folder(client, "C", b)
        for target in (a, b, c):  # into itself or its own subtree
            assert client.patch(f"/api/reading-lists/folders/{a}",
                                json={"parent_id": target}).status_code == 400
        assert client.patch(f"/api/reading-lists/folders/{c}", json={"parent_id": None}).status_code == 200
        assert client.patch(f"/api/reading-lists/folders/{c}", json={"parent_id": 9999}).status_code == 400

    def test_delete_moves_contents_up_and_keeps_lists(self, client):
        top = _folder(client, "Top")
        mid = _folder(client, "Mid", top)
        leaf = _folder(client, "Leaf", mid)
        lst = create_reading_list("Civil War")
        client.post("/api/reading-lists/move", json={"ids": [lst], "folder_id": mid})
        assert client.delete(f"/api/reading-lists/folders/{mid}").status_code == 200
        assert client.delete(f"/api/reading-lists/folders/{mid}").status_code == 404
        # The list and the sub-folder now sit directly in Top.
        html = client.get(f"/reading-lists?folder={top}").get_data(as_text=True)
        assert "Civil War" in html and "Leaf" in html
        assert client.patch(f"/api/reading-lists/folders/{leaf}", json={"parent_id": top}).status_code == 200

    def test_move_lists(self, client):
        f = _folder(client, "F")
        a, b = create_reading_list("A"), create_reading_list("B")
        r = client.post("/api/reading-lists/move", json={"ids": [a, b, 99999], "folder_id": f})
        assert r.get_json()["moved"] == 2
        assert client.post("/api/reading-lists/move", json={"ids": [a], "folder_id": 9999}).status_code == 400
        assert client.post("/api/reading-lists/move", json={"ids": [], "folder_id": f}).status_code == 400
        assert client.post("/api/reading-lists/move", json={"ids": [a], "folder_id": None}).get_json()["moved"] == 1


class TestFolderBrowsing:

    def test_folder_shows_only_its_own_lists(self, client):
        f = _folder(client, "Batman")
        inside, outside = create_reading_list("Hush"), create_reading_list("Crisis")
        client.post("/api/reading-lists/move", json={"ids": [inside], "folder_id": f})
        top = client.get("/reading-lists").get_data(as_text=True)
        assert "Crisis" in top and "Hush" not in top and "Batman" in top
        inner = client.get(f"/reading-lists?folder={f}").get_data(as_text=True)
        assert "Hush" in inner and "Crisis" not in inner
        assert 'data-folder="%d"' % f in inner
        api = client.get(f"/api/reading-lists/page?folder={f}").get_json()
        assert api["total"] == 1
        assert client.get(f"/api/reading-lists/ids?folder={f}").get_json()["ids"] == [inside]

    def test_search_and_filters_span_every_folder(self, client):
        f = _folder(client, "Batman")
        inside = create_reading_list("Hush")
        client.post("/api/reading-lists/move", json={"ids": [inside], "folder_id": f})
        html = client.get("/reading-lists?q=hush").get_data(as_text=True)
        assert "Hush" in html and 'data-folder=""' in html

    def test_unknown_folder_falls_back_to_top_level(self, client):
        create_reading_list("Loose")
        assert "Loose" in client.get("/reading-lists?folder=9999").get_data(as_text=True)

    def test_empty_folder_says_so(self, client):
        create_reading_list("Loose")
        f = _folder(client, "Empty")
        assert "This folder has no lists" in client.get(f"/api/reading-lists/page?folder={f}").get_json()["html"]
