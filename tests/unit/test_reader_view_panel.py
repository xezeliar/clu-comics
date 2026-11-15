"""Comic reader: one View panel with labelled choices replaces the three
buttons that changed a setting on every click. Asserted on the assets as text
(no JS runner); the behaviour was checked in a browser."""
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def function_body(source, name):
    start = source.index("function %s(" % name)
    end = source.find("\nfunction ", start + 1)
    return source[start:end if end != -1 else len(source)]


@pytest.fixture(scope="module")
def js():
    return read("static", "js", "reader.js")


@pytest.fixture(scope="module")
def html():
    return read("templates", "partials", "reader_modal.html")


def test_panel_markup(html):
    assert 'id="readerViewPanel"' in html
    assert 'id="readerViewBtn"' in html and 'aria-controls="readerViewPanel"' in html
    choices = {}
    for key, value in re.findall(r'data-set="(\w+)" data-v="(\w+)"', html):
        choices.setdefault(key, set()).add(value)
    assert choices == {
        "mode": {"paged", "scroll"},
        "fit": {"width", "height"},
        "turn": {"slide", "turn", "none"},
    }


def test_no_cycling_buttons(js):
    for name in ("readerModeBtn", "readerFitBtn", "readerTurnBtn"):
        assert name not in js


def test_turn_row_hidden_in_scroll(js):
    body = function_body(js, "updateReaderViewControls")
    assert 'data-row="turn"' in body
    assert "readerMode === 'scroll'" in body
    assert "aria-pressed" in body


def test_panel_clicks_use_the_existing_setters(js):
    body = function_body(js, "initializeReaderViewPanel")
    for setter in ("setReaderMode(", "setReaderFit(", "setReaderTurn("):
        assert setter in body


def test_escape_closes_panel_first(js):
    start = js.index("if (e.key !== 'Escape' || !currentComicPath) return;")
    handler = js[start:js.index("closeComicReader();", start)]
    assert "setReaderViewPanel(false" in handler
    assert "return;" in handler[handler.index("setReaderViewPanel(false"):]
    body = function_body(js, "setReaderViewPanel")
    assert "readerViewBtn" in body and ".focus()" in body
