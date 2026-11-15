"""Comic reader toolbar: the details left after the branch review. Asserted on
the assets as text (no JS runner); checked in a browser."""
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


def rule(css, selector):
    return re.search(r"(?:^|\})\s*%s\s*\{([^}]*)\}" % re.escape(selector), css, re.M).group(1)


@pytest.fixture(scope="module")
def js():
    return read("static", "js", "reader.js")


@pytest.fixture(scope="module")
def css():
    return read("static", "css", "reader.css")


def test_arrows_in_the_view_panel_move_between_choices(js):
    zoom = function_body(js, "handleZoomKeyboard")
    guard = zoom.index("readerViewPanel")
    # Before the scroll-mode hand-off, so it covers both layouts.
    assert guard < zoom.index("handleScrollKeyboard(event)")
    body = function_body(js, "handleViewPanelArrows")
    for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"):
        assert key in body
    assert ".focus()" in body and "preventDefault()" in body


def test_pace_counts_turns_not_pages_in_a_spread(js):
    body = function_body(js, "updateReaderPaceLine")
    assert "readerSpread ? Math.ceil(left / 2) : left" in body


def test_pace_ignores_jumps(js):
    body = function_body(js, "updateReaderPaceLine")
    assert "paceSkipGap" in body and "scrollState.programmatic" in body
    assert "paceSkipGap = true" in function_body(js, "readerSlideTo")


def test_scrub_tip_stays_on_screen(js):
    body = function_body(js, "showScrubTip")
    assert "window.innerWidth" in body and "Math.min(" in body and "Math.max(" in body


def test_hidden_line_clears_the_home_indicator(css):
    assert "env(safe-area-inset-bottom" in rule(css, ".reader-hidden-line")


def test_fill_is_lightened_for_the_dark_capsule(css):
    assert "--clu-select" not in css
    assert "--reader-accent" in rule(css, ".reader-hidden-line > i")
    assert "--reader-accent" in css[css.index("::-moz-range-progress"):][:200]
    supports = re.search(r"@supports \(color: color-mix\(in srgb, red, blue\)\)\s*\{(.*?)\n\}", css, re.S)
    assert supports and "--reader-accent: color-mix(" in supports.group(1)


@pytest.mark.parametrize("name", ["person.html", "smart_collections.html"])
def test_every_host_fetches_a_fresh_reader(name):
    html = read("templates", name)
    assert "filename='js/reader.js') }}?v=" in html
    assert "filename='css/reader.css') }}?v=" in html
