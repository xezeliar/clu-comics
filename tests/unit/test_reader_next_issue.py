"""The last page leads straight into the next issue.

The "Continue Reading?" popup only repeated what scrolling past the end already
did, and it was the one way forward for the keys. Now every forward gesture on
the last page (Right arrow, Space, a right-edge tap) opens the next issue;
goToIssue(1) does nothing when there is none.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def function_body(source, name):
    start = source.index("function %s(" % name)
    end = source.find("\nfunction ", start + 1)
    return source[start:end if end != -1 else len(source)]


def case_body(body, key):
    m = re.search(r"case '%s':(.*?)break;" % key, body, re.S)
    assert m, key
    return m.group(1)


JS = read("static", "js", "reader.js")


def test_no_continue_reading_overlay():
    for parts in (("static", "js", "reader.js"), ("static", "css", "reader.css"),
                  ("templates", "partials", "reader_modal.html")):
        text = read(*parts)
        assert "nextIssueOverlay" not in text
        assert "next-issue" not in text


def test_advance_on_last_page_opens_next_issue():
    body = function_body(JS, "readerAdvance")
    assert "isEnd" in body and "goToIssue(1)" in body


def test_arrow_right_on_last_page_opens_next_issue():
    assert "goToIssue(1)" in case_body(function_body(JS, "handleZoomKeyboard"), "ArrowRight")


def test_scroll_mode_forward_at_end_opens_next_issue():
    right = case_body(function_body(JS, "handleScrollKeyboard"), "ArrowRight")
    assert "s.pageCount - 1" in right and "goToIssue(1)" in right


def test_scroll_mode_space_at_end_opens_next_issue():
    body = function_body(JS, "handleComicReaderKeydown")
    assert "goToIssue(1)" in body
