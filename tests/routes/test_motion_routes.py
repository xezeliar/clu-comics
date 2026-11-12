"""reduce_motion: the two save routes and the data-clu-motion attribute.

/api/config/motion sets the site default (owner-only by its path);
/api/account/motion is any user's own override. Both copy page width's
fallback chain: personal override, else site default, else "system".
"""
import pytest

from core.database import create_user, get_user_setting_override, set_user_setting
from core.settings import get_setting, set_setting


def _login(client, username, password):
    return client.post("/login", data={"username": username, "password": password})


def _uid(username):
    from core.database import get_user_by_username
    return get_user_by_username(username)["id"]


@pytest.fixture(autouse=True)
def _users(db_connection, monkeypatch):
    monkeypatch.delenv("CLU_USERNAME", raising=False)
    monkeypatch.delenv("CLU_PASSWORD", raising=False)
    create_user("owner", password="ownerpass", role="owner")
    create_user("reader", password="readerpass", role="reader")
    yield


class TestSiteDefault:
    def test_owner_saves_site_default(self, client):
        set_user_setting("reduce_motion", "full", user_id=_uid("owner"))
        _login(client, "owner", "ownerpass")
        resp = client.post("/api/config/motion", json={"reduceMotion": "reduce"})

        assert resp.status_code == 200
        assert get_setting("REDUCE_MOTION") == "reduce"
        assert get_user_setting_override("reduce_motion", user_id=_uid("owner")) is None

    def test_unknown_value_rejected(self, client):
        _login(client, "owner", "ownerpass")
        resp = client.post("/api/config/motion", json={"reduceMotion": "wild"})

        assert resp.status_code == 400
        assert get_setting("REDUCE_MOTION") == "system"

    def test_reader_cannot_set_site_default(self, client):
        _login(client, "reader", "readerpass")
        assert client.post("/api/config/motion", json={"reduceMotion": "reduce"}).status_code == 403
        assert get_setting("REDUCE_MOTION") == "system"


class TestAccountOverride:
    def test_reader_saves_own_choice(self, client):
        _login(client, "reader", "readerpass")
        resp = client.post("/api/account/motion", json={"reduceMotion": "reduce"})

        assert resp.get_json() == {"success": True, "reduceMotion": "reduce", "override": True}
        assert get_user_setting_override("reduce_motion", user_id=_uid("reader")) == "reduce"
        assert get_setting("REDUCE_MOTION") == "system"

    def test_unknown_value_rejected(self, client):
        _login(client, "reader", "readerpass")
        assert client.post("/api/account/motion", json={"reduceMotion": "wild"}).status_code == 400

    def test_use_site_default_clears_override(self, client):
        set_setting("REDUCE_MOTION", "full")
        set_user_setting("reduce_motion", "reduce", user_id=_uid("reader"))
        _login(client, "reader", "readerpass")
        body = client.post("/api/account/motion", json={"useSiteDefault": True}).get_json()

        assert body == {"success": True, "reduceMotion": "full", "override": False}
        assert get_user_setting_override("reduce_motion", user_id=_uid("reader")) is None

    def test_unauthenticated_gets_401(self, client):
        assert client.post("/api/account/motion", json={"reduceMotion": "reduce"}).status_code == 401


class TestAttribute:
    def _html(self, client):
        return client.get("/account").get_data(as_text=True)

    def test_system_writes_nothing(self, client):
        _login(client, "reader", "readerpass")
        html = self._html(client)
        start = html.index("<html")
        assert "data-clu-motion" not in html[start:html.index(">", start)]

    def test_personal_reduce_is_written(self, client):
        set_user_setting("reduce_motion", "reduce", user_id=_uid("reader"))
        _login(client, "reader", "readerpass")
        assert 'data-clu-motion="reduce"' in self._html(client)

    def test_site_full_is_written(self, client):
        set_setting("REDUCE_MOTION", "full")
        _login(client, "reader", "readerpass")
        html = self._html(client)
        assert 'data-clu-motion="full"' in html
        assert 'id="motionStateBadge"' in html
