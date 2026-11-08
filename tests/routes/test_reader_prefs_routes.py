"""/api/reader-prefs (routes/reading.py): the comic reader's layout preference.

``mode`` is paged or scroll (webtoon), ``fit`` is width or height. Site defaults
live in SETTINGS_SCHEMA (READER_MODE / READER_FIT); each account's own choice is
a per-user setting that wins over them.
"""
import pytest

from core.database import (
    create_user,
    get_user_setting_override,
    set_user_setting,
)
from core.settings import get_setting, set_setting


def _login(client, username, password):
    return client.post("/login", data={"username": username, "password": password})


@pytest.fixture
def users(db_connection, monkeypatch):
    monkeypatch.delenv("CLU_USERNAME", raising=False)
    monkeypatch.delenv("CLU_PASSWORD", raising=False)
    create_user("owner", password="ownerpass", role="owner")
    create_user("reader", password="readerpass", role="reader")
    create_user("reader2", password="reader2pass", role="reader")


class TestDefaults:
    def test_defaults_are_paged_and_fit_to_width(self, client):
        body = client.get("/api/reader-prefs").get_json()
        assert body == {"success": True, "mode": "paged", "fit": "width"}

    def test_schema_declares_both_settings(self):
        assert get_setting("READER_MODE") == "paged"
        assert get_setting("READER_FIT") == "width"

    def test_site_default_is_honoured(self, client):
        set_setting("READER_MODE", "scroll")
        set_setting("READER_FIT", "height")
        body = client.get("/api/reader-prefs").get_json()
        assert (body["mode"], body["fit"]) == ("scroll", "height")


class TestSave:
    def test_round_trip(self, client):
        r = client.post("/api/reader-prefs", json={"mode": "scroll", "fit": "height"})
        assert r.status_code == 200
        assert r.get_json() == {"success": True, "mode": "scroll", "fit": "height"}
        again = client.get("/api/reader-prefs").get_json()
        assert (again["mode"], again["fit"]) == ("scroll", "height")

    def test_only_sent_fields_change(self, client):
        client.post("/api/reader-prefs", json={"mode": "scroll"})
        body = client.post("/api/reader-prefs", json={"fit": "height"}).get_json()
        assert (body["mode"], body["fit"]) == ("scroll", "height")

    def test_personal_choice_does_not_touch_the_site_default(self, client):
        client.post("/api/reader-prefs", json={"mode": "scroll"})
        assert get_setting("READER_MODE") == "paged"

    @pytest.mark.parametrize("payload", [
        {"mode": "carousel"},
        {"fit": "diagonal"},
        {"mode": None},
        {"mode": ["scroll"]},
        {"mode": "scroll", "fit": "nope"},
    ])
    def test_invalid_value_is_400_and_writes_nothing(self, client, payload):
        r = client.post("/api/reader-prefs", json=payload)
        assert r.status_code == 400
        assert r.get_json()["success"] is False
        body = client.get("/api/reader-prefs").get_json()
        assert (body["mode"], body["fit"]) == ("paged", "width")

    def test_body_that_is_not_json_is_400(self, client):
        r = client.post("/api/reader-prefs", data="not json",
                        content_type="text/plain")
        assert r.status_code == 400

    def test_empty_object_is_a_no_op_read(self, client):
        r = client.post("/api/reader-prefs", json={})
        assert r.status_code == 200
        assert r.get_json()["mode"] == "paged"

    def test_a_corrupt_stored_value_falls_back_to_the_default(self, client):
        set_user_setting("reader_mode", "sideways")
        set_user_setting("reader_fit", 42)
        body = client.get("/api/reader-prefs").get_json()
        assert (body["mode"], body["fit"]) == ("paged", "width")


class TestPerUser:
    def test_each_account_keeps_its_own_choice(self, client, users):
        _login(client, "reader", "readerpass")
        assert client.post("/api/reader-prefs", json={"mode": "scroll"}).status_code == 200
        client.get("/logout")

        _login(client, "reader2", "reader2pass")
        assert client.get("/api/reader-prefs").get_json()["mode"] == "paged"
        client.get("/logout")

        _login(client, "reader", "readerpass")
        assert client.get("/api/reader-prefs").get_json()["mode"] == "scroll"

    def test_a_reader_role_may_save_it(self, client, users):
        # POST defaults to Clerk; a Reader must still be able to set how THEY read.
        _login(client, "reader", "readerpass")
        r = client.post("/api/reader-prefs", json={"fit": "height"})
        assert r.status_code == 200
        assert r.get_json()["fit"] == "height"

    def test_signed_out_is_refused(self, client, users):
        assert client.get("/api/reader-prefs").status_code in (302, 401, 403)
        assert client.post("/api/reader-prefs", json={"mode": "scroll"}).status_code in (302, 401, 403)
