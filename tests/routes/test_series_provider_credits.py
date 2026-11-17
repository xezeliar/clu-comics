"""Series page: every creator Metron lists, fetched on demand and cached."""
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from core.creators import (kind_for_role, pending_provider_issue_ids, provider_credits,
                           save_provider_issue_credits)


@pytest.mark.parametrize("role,kind", [
    ("Writer", "writer"), ("Script", "writer"), ("Cover Artist", "coverartist"),
    ("Artist", "penciller"), ("Penciller", "penciller"), ("Inker", "inker"),
    ("Colorist", "colorist"), ("Letterer", "letterer"), ("Editor", None), ("", None)])
def test_kind_for_role(role, kind):
    assert kind_for_role(role) == kind


def _issue(*credits):
    return NS(credits=[NS(creator=n, role=[NS(name=r) for r in roles]) for n, roles in credits])


class TestProviderCredits:

    def test_store_and_read_back(self, db_connection):
        save_provider_issue_credits(1, 10, [("writer", "Alan Moore"), ("penciller", "Dave Gibbons")])
        save_provider_issue_credits(1, 11, [("writer", "alan moore")])
        save_provider_issue_credits(1, 12, [])  # fetched, nobody credited
        data = provider_credits(1)
        assert data["fetched"] == 3
        writer = next(r for r in data["roles"] if r["kind"] == "writer")
        assert writer["people"] == [{"name": "Alan Moore", "count": 2}]
        assert pending_provider_issue_ids(1, [10, 11, 12, 13]) == [13]
        assert provider_credits(2) is None

    def test_refetch_replaces_an_issue(self, db_connection):
        save_provider_issue_credits(1, 10, [("writer", "Old")])
        save_provider_issue_credits(1, 10, [("writer", "New")])
        names = [p["name"] for r in provider_credits(1)["roles"] for p in r["people"]]
        assert names == ["New"]

    def test_endpoint_fetches_in_batches(self, client, db_connection):
        ids = list(range(100, 112))  # 12 issues > one batch of 10
        issues = {i: _issue(("Writer Person", ["Writer"]), ("Cover Person", ["Cover Artist"]))
                  for i in ids}
        with patch("routes.series.metron.get_flask_api", return_value=object()), \
             patch("routes.series.get_issues_for_series", return_value=[{"id": i} for i in ids]), \
             patch("routes.series.metron.fetch_issue_detail",
                   side_effect=lambda api, i: issues[i]):
            first = client.post("/api/series/5/provider-credits").get_json()
            assert first == {"success": True, "remaining": 2, "total": 12}
            second = client.post("/api/series/5/provider-credits").get_json()
            assert second["remaining"] == 0
        data = provider_credits(5)
        assert data["fetched"] == 12
        assert {r["kind"] for r in data["roles"]} == {"writer", "coverartist"}

    def test_endpoint_reports_a_paused_provider(self, client, db_connection):
        with patch("routes.series.metron.get_flask_api", return_value=object()), \
             patch("routes.series.get_issues_for_series", return_value=[{"id": 1}]), \
             patch("routes.series.metron.fetch_issue_detail", return_value=None), \
             patch("routes.series.metron.paused_reason", return_value="rate limited"):
            resp = client.post("/api/series/5/provider-credits")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "rate limited"

    def test_endpoint_without_credentials(self, client, db_connection):
        with patch("routes.series.metron.get_flask_api", return_value=None):
            assert client.post("/api/series/5/provider-credits").status_code == 400
