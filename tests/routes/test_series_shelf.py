"""Tests for the dashboard Series shelf routes (routes/series_shelf.py)."""
import os
import zipfile

import pytest

from core.database import db_conn, get_new_arrival_counts, set_wanted_marks
from tests.factories.db_factories import (
    create_issue,
    create_file_index_entry, create_issue_read, create_reading_position,
    create_series,
)


@pytest.fixture
def shelf(app, db_connection):
    from routes.series_shelf import series_shelf_bp

    app.register_blueprint(series_shelf_bp)
    return app.test_client()


def _issue(parent, n, indexed_at):
    path = create_file_index_entry(name=f"S {n:03d}.cbz", parent=parent)
    with db_conn() as conn:
        conn.execute(
            "UPDATE file_index SET first_indexed_at = ?, ci_number = ? WHERE path = ?",
            (indexed_at, str(n), path))
        conn.commit()
    return path


def test_series_order_paging_and_counts(shelf):
    a = create_series(name="Alpha", mapped_path="/data/P/Alpha")
    b = create_series(name="Beta", mapped_path="/data/P/Beta")
    create_series(name="Empty", mapped_path="/data/P/Empty")
    _issue("/data/P/Alpha", 1, 100)
    _issue("/data/P/Beta", 1, 200)
    with db_conn() as conn:
        conn.execute("UPDATE series SET issue_count = 12 WHERE id = ?", (b,))
        conn.commit()

    d = shelf.get("/api/dashboard/series").get_json()
    assert d["success"] and d["total"] == 3
    assert [s["name"] for s in d["series"]] == ["Beta", "Alpha", "Empty"]
    beta = d["series"][0]
    assert beta["id"] == b and beta["owned"] == 1 and beta["total"] == 12
    assert d["series"][1]["total"] is None
    assert d["series"][2]["cover_url"] is None and d["series"][2]["owned"] == 0
    assert beta["cover_url"].startswith("/api/thumbnail")
    assert beta["folder_url"].startswith("/collection?path=")

    page = shelf.get("/api/dashboard/series?offset=1&limit=1").get_json()
    assert page["total"] == 3 and [s["name"] for s in page["series"]] == ["Alpha"]
    assert a  # series ids are returned


def test_new_count_not_cleared(shelf):
    create_series(name="Fresh", mapped_path="/data/P/Fresh")
    _issue("/data/P/Fresh", 1, 4102444800)  # far future: newer than any visit
    first = shelf.get("/api/dashboard/series").get_json()["series"][0]["new_count"]
    again = shelf.get("/api/dashboard/series").get_json()["series"][0]["new_count"]
    assert first == again == 1
    assert get_new_arrival_counts(["/data/P/Fresh"]) == {"/data/P/Fresh": 1}


def test_issues_owned_missing_sorted_with_progress(shelf):
    sid = create_series(name="Mix", mapped_path="/data/P/Mix")
    p10 = _issue("/data/P/Mix", 10, 1)
    p2 = _issue("/data/P/Mix", 2, 1)
    create_issue_read(issue_path=p2)
    create_reading_position(comic_path=p10, page_number=5, total_pages=20)
    for num in ("2", "5", "1"):
        create_issue(series_id=sid, number=num, name=f"Missing {num}")
    create_issue(series_id=sid, number="7", store_date="2999-01-01", cover_date="2999-01-01")
    with db_conn() as conn:
        conn.execute("UPDATE series SET monitored = 0 WHERE id = ?", (sid,))
        conn.commit()
    set_wanted_marks(sid, ["5"], True)

    d = shelf.get(f"/api/dashboard/series/{sid}/issues").get_json()
    assert d["series"] == {"id": sid, "name": "Mix", "monitored": False}
    assert [(i["number"], i["owned"]) for i in d["issues"]] == [
        ("1", False), ("2", True), ("5", False), ("10", True)]
    by = {i["number"]: i for i in d["issues"]}
    assert by["2"]["read"] is True and by["10"]["read"] is False
    assert by["10"]["page"] == 5 and by["10"]["total_pages"] == 20
    assert by["10"]["thumb_url"].startswith("/api/thumbnail")
    assert "path" not in by["1"]
    assert by["5"]["wanted"] is True and by["1"]["wanted"] is False
    assert "7" not in by  # unreleased issues are not "missing"


def test_issues_unknown_series_404(shelf):
    assert shelf.get("/api/dashboard/series/999999/issues").status_code == 404


def _cbz(path, xml):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.jpg", b"x")
        if xml:
            z.writestr("ComicInfo.xml", xml)


def test_issue_info_credits(shelf, data_dir_library, tmp_path):
    path = os.path.join(data_dir_library, "a.cbz")
    _cbz(path, "<ComicInfo><Title>T</Title><Summary>S</Summary><Year>2020</Year>"
               "<Month>3</Month><Writer>W</Writer><CoverArtist>C</CoverArtist>"
               "</ComicInfo>")
    d = shelf.get("/api/dashboard/issue-info", query_string={"path": path}).get_json()
    assert d["success"] and d["title"] == "T" and d["summary"] == "S"
    assert d["date"] == "2020-3"
    assert d["credits"]["writer"] == "W" and d["credits"]["cover_artist"] == "C"
    assert d["credits"]["inker"] == ""


def test_issue_info_cbr_is_empty_not_error(shelf, data_dir_library):
    path = os.path.join(data_dir_library, "a.cbr")
    open(path, "wb").write(b"Rar!")
    d = shelf.get("/api/dashboard/issue-info", query_string={"path": path}).get_json()
    assert d["success"] and d["title"] == "" and d["credits"]["writer"] == ""


def test_issue_info_outside_library_rejected(shelf, data_dir_library, tmp_path):
    outside = tmp_path / "out.cbz"
    _cbz(str(outside), None)
    r = shelf.get("/api/dashboard/issue-info", query_string={"path": str(outside)})
    assert 400 <= r.status_code < 500
    assert shelf.get("/api/dashboard/issue-info").status_code == 400


def test_unmark_read_removes_read_and_position(shelf):
    from core.database import get_reading_position, is_issue_read

    p = create_issue_read(issue_path="/data/P/X/1.cbz")
    create_reading_position(comic_path=p)
    r = shelf.delete("/api/dashboard/issue-read", query_string={"path": p})
    assert r.get_json() == {"success": True}
    assert not is_issue_read(p) and get_reading_position(p) is None
    assert shelf.delete("/api/dashboard/issue-read").status_code == 400
