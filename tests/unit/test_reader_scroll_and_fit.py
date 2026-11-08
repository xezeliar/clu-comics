"""Comic reader: scroll (webtoon) mode and fit-to-width.

There is no JS test runner in this repo, so, like test_reader_pan_controls.py,
these assert on the assets as text. The behaviour itself was checked in a real
browser; what is pinned here is each decision that is easy to undo by accident
and invisible when it is.
"""
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
READER_TEMPLATES = [
    "collection.html",
    "metadata_browser.html",
    "reading_list_view.html",
    "source_wall.html",
]


def read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def function_body(source, name):
    start = source.index("function %s(" % name)
    end = source.find("\nfunction ", start + 1)
    return source[start:end if end != -1 else len(source)]


def js_list(source, name):
    raw = re.search(r"const %s = \[([^\]]*)\]" % name, source).group(1)
    return [part.strip().strip("'") for part in raw.split(",")]


@pytest.fixture(scope="module")
def js():
    return read("static", "js", "reader.js")


@pytest.fixture(scope="module")
def css():
    return read("static", "css", "reader.css")


class TestSettings:
    def test_schema_entries(self):
        from core.settings import SETTINGS_SCHEMA

        assert SETTINGS_SCHEMA["READER_MODE"].pref == "reader_mode"
        assert SETTINGS_SCHEMA["READER_MODE"].default == "paged"
        assert SETTINGS_SCHEMA["READER_FIT"].pref == "reader_fit"
        # Fit-to-width is the default: it is what removes the side gaps.
        assert SETTINGS_SCHEMA["READER_FIT"].default == "width"

    def test_route_and_js_agree_on_the_allowed_values(self, js):
        from routes.reading import READER_FITS, READER_MODES

        assert js_list(js, "READER_MODES") == list(READER_MODES)
        assert js_list(js, "READER_FITS") == list(READER_FITS)

    def test_a_reader_role_can_save_it(self):
        from core.auth import _READER_WRITE_PREFIXES

        assert "/api/reader-prefs" in _READER_WRITE_PREFIXES

    def test_prefs_are_loaded_on_every_open(self, js):
        body = function_body(js, "openComicReader")
        assert "loadReaderPrefs()" in body
        assert "ensureReaderViewControls()" in body


class TestControlsAreBuiltInJs:
    def test_not_hand_rolled_in_the_four_templates(self, js):
        # The modal is duplicated across four templates; building the buttons in
        # JS is what keeps those copies from drifting.
        assert "readerModeBtn" in js and "readerFitBtn" in js
        for name in READER_TEMPLATES:
            html = read("templates", name)
            assert "readerModeBtn" not in html
            assert "readerFitBtn" not in html

    def test_handlers_are_assigned_not_stacked(self, js):
        # initializeZoomControls / initializePageSelector run on every (re)build,
        # which a mode switch now does mid-comic. addEventListener there made one
        # click zoom several steps.
        zoom = function_body(js, "initializeZoomControls")
        assert "zoomInBtn.onclick" in zoom and "zoomOutBtn.onclick" in zoom
        assert "zoomInBtn.addEventListener" not in zoom
        assert "pageSelector.onchange" in function_body(js, "initializePageSelector")

    def test_no_native_dialogs(self, js):
        assert not re.search(r"(?<![.\w])(alert|confirm|prompt)\(", js)


class TestScrollMode:
    def test_pages_are_lazy_loaded_and_released(self, js):
        assert "new IntersectionObserver" in js
        assert "SCROLL_LOAD_MARGIN" in js
        body = function_body(js, "unloadDistantScrollPages")
        assert "removeAttribute('src')" in body
        # The observer, not a loop over every page, decides what loads.
        init = function_body(js, "initializeScrollReader")
        assert "loadScrollPage(" in init and "pages.forEach(p => s.observer.observe(p))" in init
        assert "loadComicPage" not in init

    def test_current_page_follows_the_reading_line(self, js):
        assert "SCROLL_READING_LINE" in function_body(js, "scrollPageIndexAtLine")
        body = function_body(js, "syncScrollIndex")
        assert "highestPageViewed" in body
        assert "scheduleAutoSave()" in body
        assert "checkAndShowNextIssueOverlay()" in body

    def test_a_jump_is_not_counted_as_reading(self, js):
        body = function_body(js, "syncScrollIndex")
        assert "if (!s.programmatic)" in body
        assert "s.programmatic = true" in function_body(js, "scrollToReaderPage")
        # ...and neither is rebuilding the view when the mode is switched.
        assert "rebuildingReaderView" in function_body(js, "setReaderMode")
        assert "rebuildingReaderView" in function_body(js, "initializeScrollReader")

    def test_position_works_in_either_mode(self, js):
        assert "getReaderCurrentIndex() + 1" in function_body(js, "_readerPositionPayload")
        assert "readerHasView()" in function_body(js, "persistReadingPosition")
        assert "scrollToReaderPage(index)" in function_body(js, "readerSlideTo")

    def test_every_teardown_path_clears_the_strip(self, js):
        assert "destroyReaderView()" in function_body(js, "closeComicReader")
        assert "destroyReaderView()" in function_body(js, "continueToNextIssue")
        assert "destroyReaderView()" in function_body(js, "initializeComicReader")
        body = function_body(js, "teardownScrollReader")
        assert "observer.disconnect()" in body
        assert "removeEventListener('scroll'" in body

    def test_zoom_buttons_and_keys_work_in_scroll_mode(self, js):
        assert "stepScrollWidth(direction)" in function_body(js, "stepZoom")
        assert "handleScrollKeyboard(event)" in function_body(js, "handleZoomKeyboard")
        assert "scrollReaderBy(" in function_body(js, "handleComicReaderKeydown")

    def test_layout_changes_keep_the_readers_place(self, js, css):
        assert "withScrollAnchor(s," in function_body(js, "loadScrollPage")
        assert "withScrollAnchor(s," in function_body(js, "stepScrollWidth")
        # Browser anchoring off, or two mechanisms adjust at once.
        assert re.search(r"\.comic-reader-scroll\s*\{[^}]*overflow-anchor:\s*none", css)

    def test_pages_are_stacked_without_a_gap(self, css):
        page = re.search(r"\.comic-scroll-page\s*\{([^}]*)\}", css).group(1)
        assert "margin" not in page and "gap" not in page
        img = re.search(r"\.comic-scroll-page img\s*\{([^}]*)\}", css).group(1)
        assert "display: block" in img and "width: 100%" in img


class TestFitToWidth:
    def test_default_is_width(self, js):
        assert "let readerFit = 'width';" in js

    def test_fit_is_a_zoom_relative_to_the_laid_out_image(self, js):
        body = function_body(js, "applyReaderFit")
        assert "slide.clientWidth / img.offsetWidth" in body
        assert "swiper.zoom.in(scale)" in body
        assert "alignFitView(" in body
        assert "if (readerFit !== 'width') return;" in body

    def test_fit_is_applied_on_open_and_on_every_page(self, js):
        assert "applyReaderFit('top')" in function_body(js, "loadComicPage")
        assert "applyReaderFit(pendingFitAlign)" in js

    def test_zoom_buttons_step_relative_to_the_fit(self, js):
        body = function_body(js, "pagedZoomSteps")
        assert "fitBaseScale" in body and "ZOOM_STEPS" in body
        assert "pagedZoomSteps()" in function_body(js, "stepZoom")

    def test_fitted_is_not_zoomed_in(self, js):
        # Otherwise a page fitted to the width would swallow taps (chrome
        # toggle) and double-taps.
        assert "function readerZoomedBeyondFit(" in js
        assert "readerZoomedBeyondFit()" in function_body(js, "initializeComicReader")

    def test_wheel_reads_down_the_page_then_turns_it(self, js):
        body = function_body(js, "initializeMousewheelHandler")
        assert "WHEEL_TURN_COOLDOWN_MS" in body
        assert "slideNext()" in body and "slidePrev()" in body
        assert "pendingFitAlign = 'bottom'" in body

    def test_swipers_dead_zoom_cache_is_avoided(self, js):
        # zoom.out()/in() cache the slide they were first called on; calling
        # them before its image is in leaves zoom dead until the next turn.
        assert "activePagedImage(this)" in function_body(js, "initializeComicReader")
        assert "activePagedImage(comicReaderSwiper)" in function_body(js, "resetPagedZoomToFit")

    def test_swipers_toggle_is_off(self, js):
        # Its toggle knows nothing about the fitted scale.
        assert "toggle: false" in js

    def test_window_resize_refits(self, js):
        assert "addEventListener('resize'" in js
