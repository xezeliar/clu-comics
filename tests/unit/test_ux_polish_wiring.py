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
    # Mouse as well as touch; a stale click guard is cleared on the next press;
    # native image drag cannot cancel the hold unnoticed.
    assert "e.pointerType !== 'touch'" not in js and "e.button !== 0" in js
    press = js[js.index("addEventListener('pointerdown'"):]
    assert press.index("swallowClick = false") < press.index("e.button !== 0")
    assert "'dragstart'" in js
    css = _read("static/css/clu-page.css")
    # The press must beat the hover lift, or a mouse never sees it.
    assert ".grid-item.clu-pressing:hover" in css
    assert "user-select: none" in css and "-webkit-user-drag: none" in css
    assert "clu-sheet" in css
    # A transformed ancestor (sticky :hover on a tapped card) must not contain
    # the fixed sheet on its first open.
    assert "clu-sheet-host" in js and ".clu-sheet-host {" in css
    # Built before the first paint, or the menu flashes as a dropdown.
    # Above its scrim (1055) whatever page rule sets a menu z-index.
    assert "z-index: 1056 !important" in css
    # A tapped item closes the sheet even when its handler stops propagation.
    assert "'.dropdown-menu.clu-sheet .dropdown-item'" in js and "}, true);" in js
    assert "'show.bs.dropdown'" in js and "'shown.bs.dropdown'" not in js


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


def test_swipe_rows_are_wired_to_the_row_menu():
    js = _read("static/js/clu-gestures.js")
    assert "[data-swipe-row]" in js and ".clu-swipe-acts" in js and ".clu-row-more" in js
    assert "touch-action" in _read("static/css/clu-page.css") and ".clu-swipe-acts" in _read("static/css/clu-page.css")
    rows = _read("templates/partials/pull_list_rows.html")
    assert "data-swipe-row" in rows and "clu-swipe-acts" in rows
    page = _read("templates/pull_list.html")
    # Undo restores through the server, never by faking the row back.
    assert "'restore-subscription'" in page and "label: 'Undo'" in page
    assert "'unsubscribe'" in page
