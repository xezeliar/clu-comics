"""apply_follows: followed creators' new Pull List series join Wanted."""

import pytest

from core import creators


def _series(conn, sid, name, parent, monitored=0, locked=0, status="Ongoing",
            created="2999-01-01 00:00:00", publisher="DC"):
    conn.execute("INSERT OR IGNORE INTO publishers (id, name, path) VALUES (1, ?, '/data/DC')",
                 (publisher,))
    conn.execute(
        "INSERT INTO series (id, name, publisher_id, status, mapped_path, monitored,"
        " monitor_locked, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
        (sid, name, status, parent, monitored, locked, created))
    conn.execute(
        "INSERT INTO file_index (name, path, type, size, parent) VALUES (?, ?, 'file', 1, ?)",
        (f"{name}.cbz", f"{parent}/{name}.cbz", parent))
    conn.execute("INSERT INTO file_metadata_tags VALUES (?, 'writer', 'Tom King')",
                 (f"{parent}/{name}.cbz",))
    conn.commit()


def _monitored(conn, sid):
    return conn.execute("SELECT monitored FROM series WHERE id=?", (sid,)).fetchone()[0]


@pytest.fixture
def follow(db_connection):
    creators.follow_creator("Tom King")
    return db_connection


def test_turns_monitor_on_for_new_series(follow):
    _series(follow, 1, "New", "/data/DC/New")
    assert creators.apply_follows() == 1
    assert _monitored(follow, 1) == 1
    f = creators.get_follow("Tom King")
    assert (f["added_count"], f["last_added"]) == (1, "New")
    assert creators.apply_follows() == 0  # idempotent


def test_leaves_alone_locked_old_and_other_creators(follow):
    _series(follow, 1, "Locked", "/data/DC/Locked", locked=1)
    _series(follow, 2, "Old", "/data/DC/Old", created="2000-01-01 00:00:00")
    follow.execute("DELETE FROM file_metadata_tags WHERE file_path LIKE '%Locked%'")
    _series(follow, 3, "Mine", "/data/DC/Mine")
    follow.execute("DELETE FROM file_metadata_tags WHERE file_path LIKE '%Mine%'")
    follow.commit()
    assert creators.apply_follows() == 0
    assert [_monitored(follow, i) for i in (1, 2, 3)] == [0, 0, 0]


def test_publisher_and_scope_filters(db_connection):
    creators.follow_creator("Tom King", publisher="Image")
    _series(db_connection, 1, "A", "/data/DC/A")
    assert creators.apply_follows() == 0
    creators.follow_creator("Tom King", publisher="dc", scope="limited")
    assert creators.apply_follows() == 0  # ongoing series, limited-only follow
    creators.follow_creator("Tom King", publisher="dc", scope="ongoing")
    assert creators.apply_follows() == 1


def test_already_monitored_series_not_counted(follow):
    _series(follow, 1, "On", "/data/DC/On", monitored=1)
    assert creators.apply_follows() == 0


def test_refollow_keeps_followed_at(follow):
    before = creators.get_follow("Tom King")["followed_at"]
    creators.follow_creator("Tom King", scope="ongoing")
    assert creators.get_follow("Tom King")["followed_at"] == before


def test_sweep_and_blueprint_are_wired():
    """app.py cannot be imported in tests, so assert the wiring structurally."""
    src = open("app.py", encoding="utf-8").read()
    assert "app.register_blueprint(creators_bp)" in src
    assert src.index("apply_follows()") > src.index("def scheduled_getcomics_download")
