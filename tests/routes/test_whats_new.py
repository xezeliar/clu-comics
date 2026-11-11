"""Home "What's new" card: shown until this version's card is dismissed."""
from core.settings import invalidate


def test_visible_until_dismissed_then_stays_hidden(client):
    from core.version import __version__
    data = client.get("/api/whats-new").get_json()
    assert data["visible"] is True
    assert data["version"] == __version__
    assert 1 <= len(data["items"]) <= 3
    assert data["changelog_url"].startswith("https://")

    assert client.post("/api/whats-new/dismiss").get_json()["success"] is True
    invalidate()
    assert client.get("/api/whats-new").get_json()["visible"] is False


def test_a_newer_version_shows_the_card_again(client):
    from unittest.mock import patch
    client.post("/api/whats-new/dismiss")
    invalidate()
    with patch("core.version.__version__", "999.0"):
        assert client.get("/api/whats-new").get_json()["visible"] is True


def test_dismissal_is_per_user_and_a_reader_may_dismiss(client, db_connection, monkeypatch):
    from core.database import create_user
    monkeypatch.delenv("CLU_USERNAME", raising=False)
    monkeypatch.delenv("CLU_PASSWORD", raising=False)
    create_user("owner", password="ownerpass", role="owner")
    create_user("reader", password="readerpass", role="reader")

    client.post("/login", data={"username": "reader", "password": "readerpass"})
    assert client.post("/api/whats-new/dismiss").status_code == 200
    assert client.get("/api/whats-new").get_json()["visible"] is False

    client.get("/logout")
    client.post("/login", data={"username": "owner", "password": "ownerpass"})
    assert client.get("/api/whats-new").get_json()["visible"] is True
