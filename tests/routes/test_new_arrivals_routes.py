"""Routes behind the "New issue arrived" badge: /api/browse carries each
folder's count and opening a folder clears it; the Pull List's Status filter
gains "New arrivals" with a count."""
import os
import time

import tests.routes.test_series_routes as series_routes_tests


def _index_comic(folder, name):
    from core.database import add_file_index_entry
    add_file_index_entry(name, os.path.join(folder, name), "file", size=1, parent=folder)


class TestBrowseNewCount:
    def test_folder_count_then_cleared_by_opening_it(self, client, data_dir_library):
        from core.database import add_file_index_entry
        series = os.path.join(data_dir_library, "Saga")
        os.makedirs(series, exist_ok=True)
        add_file_index_entry("Saga", series, "directory", parent=data_dir_library)
        time.sleep(0.01)
        _index_comic(series, "Saga 001.cbz")
        _index_comic(series, "Saga 002.cbz")

        dirs = client.get(f"/api/browse?path={data_dir_library}").get_json()["directories"]
        assert [d["new_count"] for d in dirs if d["name"] == "Saga"] == [2]

        assert client.get(f"/api/browse?path={series}").status_code == 200

        dirs = client.get(f"/api/browse?path={data_dir_library}").get_json()["directories"]
        assert [d["new_count"] for d in dirs if d["name"] == "Saga"] == [0]


class TestPullListNewArrivals:
    def test_status_filter_offers_new_arrivals_with_count(self, app, client_with_data):
        series_routes_tests.TestPullListPage._register_slug_global(app)
        time.sleep(0.01)
        _index_comic("/data/DC Comics/Batman", "Batman 099.cbz")

        html = client_with_data.get("/pull-list").get_data(as_text=True)
        status = html.split('id="statusFilter"', 1)[1].split("</div>", 1)[0]
        assert 'data-value="new"' in status
        assert "New arrivals" in status
        assert '<span class="clu-filter-count">1</span>' in status

        html = client_with_data.get("/pull-list?status=new").get_data(as_text=True)
        assert 'data-series-id="100"' in html
        assert 'data-series-id="200"' not in html
