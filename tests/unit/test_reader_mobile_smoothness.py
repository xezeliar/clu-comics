"""Mobile reader: no native page zoom, scroll-mode pinch, 100% not 100vw.

Asserted on the assets as text (no JS runner here, like the other reader
tests). Each of these is invisible when undone: the reader still opens, it
just shifts sideways on an iPhone after a pinch.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def js():
    return read("static", "js", "reader.js")


@pytest.fixture(scope="module")
def css():
    return read("static", "css", "reader.css")


def no_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def body(source, name):
    start = source.index("function %s(" % name)
    end = source.find("\nfunction ", start + 1)
    return source[start:end if end != -1 else len(source)]


class TestNativePageZoomIsOff:
    def test_gesture_events_are_cancelled_while_open(self, js):
        b = body(js, "blockNativePageZoom")
        for ev in ("gesturestart", "gesturechange", "gestureend"):
            assert ev in b
        assert "passive: false" in b  # a passive listener cannot preventDefault

    def test_open_blocks_and_close_restores(self, js):
        assert "blockNativePageZoom();" in body(js, "openComicReader") or \
            "blockNativePageZoom();" in js
        close = body(js, "closeComicReader")
        assert "allowNativePageZoom();" in close

    def test_close_clears_any_drift(self, js):
        assert "window.scrollTo(0, 0)" in body(js, "allowNativePageZoom")


class TestScrollModePinch:
    def test_built_with_the_strip_and_torn_down_with_it(self, js):
        assert "attachScrollPinch(s);" in js
        teardown = body(js, "destroyScrollReader") if "function destroyScrollReader(" in js else js
        for ev in ("touchstart", "touchmove", "touchend", "touchcancel"):
            assert "removeEventListener('%s'" % ev in teardown

    def test_touchmove_is_not_passive_and_stops_native_scroll(self, js):
        b = body(js, "attachScrollPinch")
        assert "'touchmove', s.onTouchMove, { passive: false }" in b
        assert "e.preventDefault()" in b

    def test_pinch_is_clamped_and_keeps_the_place(self, js):
        b = body(js, "attachScrollPinch")
        assert "SCROLL_PINCH_MIN" in b and "SCROLL_PINCH_MAX" in b
        assert "withScrollAnchor" in b

    def test_end_of_pinch_does_not_toggle_chrome(self, js):
        assert "suppressClickUntil" in js


class TestCss:
    def test_modal_is_not_sized_in_vw(self, css):
        modal = no_comments(css[css.index(".comic-reader-modal {"):css.index(".comic-reader-overlay")])
        assert "100vw" not in modal
        assert "inset: 0;" in modal

    def test_strip_lets_one_finger_scroll_and_blocks_native_pinch(self, css):
        strip = no_comments(css[css.index(".comic-reader-scroll {"):css.index(".comic-reader-scroll-column")])
        assert "touch-action: pan-x pan-y;" in strip
        assert "pinch-zoom" not in strip
