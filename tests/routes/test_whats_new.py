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
