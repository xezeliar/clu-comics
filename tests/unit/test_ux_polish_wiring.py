"""Structural checks for the UX polish items (templates and scripts are not
importable, so assert the wiring on source)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_gestures_script_is_loaded_everywhere_and_opens_the_existing_menu():
    assert "js/clu-gestures.js" in _read("templates/base.html")
    js = _read("static/js/clu-gestures.js")
    assert ".item-actions" in js and "contextmenu" in js and "HOLD_MS = 450" in js
    assert "clu-sheet" in _read("static/css/clu-page.css")


def test_settings_search_is_wired():
    html = _read("templates/config.html")
    assert "search_input('settingsSearch', 'Search settings'" in html
    assert "js/clu-settings-search.js" in html
    assert "settingsCount" in _read("static/js/clu-settings-search.js")


def test_reader_footer_has_progress_line_and_loupe():
    assert 'id="readerProgressLine"' in _read("templates/partials/reader_modal.html")
    js = _read("static/js/reader.js")
    assert "updateReaderPaceLine" in js and "under a minute left" in js and "initReaderLoupe" in js


def test_focus_ring_rule_exists():
    assert ":focus-visible" in _read("static/css/clu-page.css")
    assert "collapseCrumbs" in _read("static/js/collection.js")
