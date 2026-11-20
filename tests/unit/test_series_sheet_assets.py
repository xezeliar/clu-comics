"""Static ratchets for the dashboard Series shelf and its phone issue sheet."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/series-sheet.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/series-sheet.css").read_text(encoding="utf-8")
PARTIAL = (ROOT / "templates/partials/series_sheet.html").read_text(encoding="utf-8")
COLLECTION_JS = (ROOT / "static/js/collection.js").read_text(encoding="utf-8")
COLLECTION_HTML = (ROOT / "templates/collection.html").read_text(encoding="utf-8")


def test_section_registered_and_last_by_default():
    from routes.collection import DASHBOARD_SECTION_DEFS, DEFAULT_DASHBOARD_ORDER

    d = DASHBOARD_SECTION_DEFS["series"]
    assert d["title"] == "Series"
    assert d["swiper_id"] == "seriesSwiper"
    assert DEFAULT_DASHBOARD_ORDER[-1] == "series"


def test_no_native_dialogs():
    for src in (JS, COLLECTION_JS):
        assert not re.search(r"\b(alert|confirm|prompt)\s*\(", src)
    assert "CLU.toast(" in JS


def test_assets_loaded_through_asset_and_partial_included():
    assert "asset('js/series-sheet.js')" in COLLECTION_HTML
    assert "asset('css/series-sheet.css')" in COLLECTION_HTML
    assert "{% include 'partials/series_sheet.html' %}" in COLLECTION_HTML


def test_shelf_wiring_in_collection_js():
    assert "loadSeriesSwiper();" in COLLECTION_JS
    assert "case 'open-series':" in COLLECTION_JS
    assert 'data-dash-action="open-series"' in COLLECTION_JS
    assert "'reachEnd'" in COLLECTION_JS
    # Phone gets the sheet, wider screens the folder.
    assert "matchMedia('(max-width: 767.98px)')" in COLLECTION_JS
    assert "CLUSeriesSheet.open(" in COLLECTION_JS


def test_sheet_contract():
    for url in ("/api/dashboard/series/", "/api/dashboard/issue-info?path=",
                "/api/favorites/to-read", "/wanted-marks", "/api/download?path="):
        assert url in JS, url
    assert "openReaderForFile(" in JS
    assert "scroll-snap-stop: always" in CSS
    assert "prefers-reduced-motion" in CSS
    assert 'role="dialog"' in PARTIAL and 'aria-modal="true"' in PARTIAL


def test_no_raw_control_characters():
    for text in (JS, CSS, PARTIAL):
        assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text)
