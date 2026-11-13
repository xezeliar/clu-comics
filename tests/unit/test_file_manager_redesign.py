"""The File Manager redesign's rules that a regression would quietly undo.

Rows are quiet (neutral buttons, one row builder for every place), Empty Trash
asks in the shared modal rather than confirm(), rows log nothing, and the
selection bar, not a badge or a right-click-only menu, carries the actions.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static" / "js" / "files.js").read_text(encoding="utf-8")
HTML = (ROOT / "templates" / "files.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "files.css").read_text(encoding="utf-8")
CTX = (ROOT / "static" / "js" / "files_context_menu.js").read_text(encoding="utf-8")

COLOUR_BUTTON = re.compile(r"btn-(?:outline-)?(?:info|success|primary|dark|warning|danger)\b")


def _fn(name, src=JS):
    body = src[src.index("function " + name + "("):]
    return body[:body.index("\n}\n")]


def test_one_row_builder_with_neutral_buttons():
    row = _fn("fmRow")
    assert not COLOUR_BUTTON.search(row)
    assert "console.log" not in row
    assert "function createListItem(" not in JS
    # Library, Downloads, Recent and Trash all draw through it.
    assert JS.count("fmRow(panel, ") == 2  # its definition and its one caller


def test_no_old_row_colours_left_in_the_stylesheet():
    for gone in ("#bf9300", "100vh - 485px", "selection-badge", "linear-gradient"):
        assert gone not in CSS, gone


def test_empty_trash_asks_in_the_shared_modal():
    assert "confirm(" not in re.sub(r"(showDeleteConfirmation|confirmDelete|_cluDelete|onConfirm)", "", JS)
    assert "fmConfirmPermanent('every item in the Trash'" in _fn("fmEmptyTrash")
    assert "onConfirm: run" in _fn("fmConfirmPermanent")


def test_no_debug_leftovers():
    assert "testToast" not in JS and "Test Toast" not in JS


def test_badge_and_right_click_only_menu_are_gone():
    for gone in ("selectionBadge", "fileContextMenu", "filesBulkActionBar"):
        assert gone not in HTML, gone
        assert gone not in CTX, gone
    assert 'id="fmBar"' in HTML


def test_move_names_its_target_and_says_why_it_cannot():
    bar = _fn("fmDrawBar")
    assert "'Move ' + n + ' to '" in bar
    assert "fmMoveBlocked(panel)" in bar and "fm-why" in bar
    blocked = _fn("fmMoveBlocked")
    assert "Both panes show this folder" in blocked
    assert "into itself" in _fn("fmMoveInto")


def test_moves_and_deletes_offer_undo():
    assert "label: 'Undo'" in _fn("waitForMoveCompletion")
    assert "CLU.offerUndoDelete(" in _fn("fmDelete")
    # Trash off: Delete keeps the shared confirmation.
    assert "CLU.showDeleteConfirmation(" in _fn("fmDelete")


def test_both_panes_share_one_head():
    assert HTML.count("{{ fm_pane(") == 2
    for place in ("library", "downloads", "recent", "trash"):
        assert f'data-fm-place="{place}"' in HTML
