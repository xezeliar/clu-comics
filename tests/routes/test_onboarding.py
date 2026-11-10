"""Home-page setup checklist: state from real data, dismiss flag, empty-state copy."""
import pathlib
from unittest.mock import patch

TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "templates"


def _steps(client):
    return {s["id"]: s for s in client.get("/api/onboarding").get_json()["steps"]}


class TestOnboardingState:
    def test_steps_link_to_settings_and_reflect_state(self, client):
        with patch("core.database.get_libraries", return_value=[]), \
             patch("core.database.get_all_provider_credentials_status",
                   return_value=[{"provider_type": "metron"}]), \
             patch("core.config.get_watch_dir", return_value=""):
            data = client.get("/api/onboarding").get_json()
        steps = {s["id"]: s for s in data["steps"]}
        assert steps["library"]["done"] is False
        assert steps["provider"]["done"] is True
        assert steps["monitor"]["done"] is False
        assert steps["library"]["href"].endswith("/config#libraries")
        assert steps["provider"]["href"].endswith("/config#metadata-providers")
        assert data["visible"] is True

    def test_hidden_when_all_done(self, client):
        with patch("core.database.get_libraries", return_value=[{"id": 1}]), \
             patch("core.database.get_all_provider_credentials_status",
                   return_value=[{"provider_type": "comicvine"}]), \
             patch("core.config.get_watch_dir", return_value="/w"), \
             patch("core.config.get_target_dir", return_value="/t"), \
             patch("core.settings.get_bool", return_value=True), \
             patch("core.database.db_conn") as db:
            db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)
            data = client.get("/api/onboarding").get_json()
        assert all(s["done"] for s in data["steps"])
        assert data["visible"] is False

    def test_dismiss_hides_it(self, client):
        from core.settings import get_bool, invalidate
        assert client.post("/api/onboarding/dismiss").get_json()["success"] is True
        invalidate()
        assert get_bool("ONBOARDING_DISMISSED") is True
        assert client.get("/api/onboarding").get_json()["visible"] is False


def _read(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_empty_states_name_a_next_step():
    assert "'Pull list is empty'" in _read("pull_list.html")
    assert "Search Metron" in _read("pull_list.html")
    wanted = _read("wanted.html")
    assert "'Nothing wanted'" in wanted and "Link a library" in wanted
    assert "No indexers yet" in _read("config.html")
    assert "No downloads yet" in _read("weekly_packs.html")
    assert "No recommendations yet" in _read("collection.html")
    assert "No reading data yet" in _read("insights.html")
