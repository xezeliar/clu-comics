"""Comic reader toolbar: focus and dismiss rules found in the branch review.
Asserted on reader.js as text (no JS runner)."""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def function_body(source, name):
    start = source.index("function %s(" % name)
    end = source.find("\nfunction ", start + 1)
    return source[start:end if end != -1 else len(source)]


@pytest.fixture(scope="module")
def js():
    with open(os.path.join(REPO_ROOT, "static", "js", "reader.js"), encoding="utf-8") as f:
        return f.read()


def test_close_clears_inert_through_the_one_setter(js):
    # Closing with the chrome hidden left the pills inert on the next open.
    body = function_body(js, "closeComicReader")
    assert "toggleReaderChrome(false)" in body
    assert "classList.remove('reader-chrome-hidden')" not in body


def test_pointer_scrub_gives_the_keys_back(js):
    # Focus left on the range made → step the scrubber, so reading went uncounted.
    body = function_body(js, "initializePageScrubber")
    assert "addEventListener('pointerup'" in body and ".blur()" in body


def test_jump_to_the_current_page_sets_no_flag(js):
    # Swiper fires no slideChange for it, so the flag would eat the next real turn.
    body = function_body(js, "readerSlideTo")
    same = body.index("comicReaderSwiper.activeIndex")
    assert same < body.index("suppressProgressOnNextChange = true")
    assert "syncPageScrubber(" in body


def test_space_after_a_mouse_click_still_reads(js):
    body = function_body(js, "handleComicReaderKeydown")
    head = body[:body.index("e.code === 'Space'")]
    assert ":focus-visible" in head


def test_dismissing_the_panel_does_not_also_tap_the_page(js):
    panel = function_body(js, "initializeReaderViewPanel")
    assert "'pointerdown'" in panel and "capture: true" in panel
    assert "readerPanelJustDismissed()" in js[js.index("tap: function (swiper, event)"):][:600]
    assert "readerPanelJustDismissed()" in function_body(js, "handleScrollTap")
    onclick = js[js.index("s.onClick = () => {"):][:400]
    assert "readerPanelJustDismissed()" in onclick
    assert "overlay.addEventListener('click', closeComicReader)" not in js
