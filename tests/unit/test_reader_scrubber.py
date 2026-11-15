"""Comic reader: a range scrubber with a page preview replaces the page
dropdown. Asserted on the assets as text (no JS runner)."""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def function_body(source, name):
    start = source.index("function %s(" % name)
    end = source.find("\nfunction ", start + 1)
    return source[start:end if end != -1 else len(source)]


def listener(body, event):
    start = body.index("addEventListener('%s'" % event)
    nxt = body.find("addEventListener(", start + 1)
    return body[start:nxt if nxt != -1 else len(body)]


@pytest.fixture(scope="module")
def js():
    return read("static", "js", "reader.js")


@pytest.fixture(scope="module")
def html():
    return read("templates", "partials", "reader_modal.html")


def test_select_gone(js, html):
    assert "pageSelector" not in js and "pageSelector" not in html
    assert 'id="pageScrubber"' in html and 'type="range"' in html
    assert "reader-scrub-tip" in html


def test_scrubber_has_valuetext(js):
    body = function_body(js, "syncPageScrubber")
    assert "aria-valuetext" in body and "setScrubFill(" in body
    assert "--p" in function_body(js, "setScrubFill")


def test_scrubber_snaps_to_spread(js):
    assert "spreadStart(" in function_body(js, "initializePageScrubber")


def test_scrubber_handles_scroll_mode(js):
    assert "scrollToReaderPage(" in function_body(js, "initializePageScrubber")


def test_navigates_on_change_not_input(js):
    body = function_body(js, "initializePageScrubber")
    change, typing = listener(body, "change"), listener(body, "input")
    assert "scrollToReaderPage(" in change and "readerSlideTo(" in change
    assert "scrollToReaderPage(" not in typing and "readerSlideTo(" not in typing
    assert "readerPageUrl(" in typing or "showScrubTip(" in typing


def test_listeners_are_bound_once(js):
    # initializePageScrubber runs on every (re)build, as the dropdown's did.
    assert "dataset.bound" in function_body(js, "initializePageScrubber")


def test_every_page_sync_goes_through_it(js):
    assert js.count("syncPageScrubber(") >= 3  # definition + paged + scroll
