"""Reader gestures: tap zones, pull past the end, swipe to close, spreads.

There is no JS runner in this repo, so these assert on the asset as text, as
test_reader_chrome_toggle.py does.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def reader_js():
    with open(os.path.join(ROOT, "static", "js", "reader.js"), encoding="utf-8") as f:
        return f.read()


class TestTapZones:
    def test_paged_side_taps_turn_the_page(self, reader_js):
        body = reader_js[reader_js.index("tap: function (swiper, event)"):reader_js.index("doubleTap:")]
        assert "readerAdvance()" in body and "readerRetreat()" in body

    def test_double_tap_zoom_is_middle_only(self, reader_js):
        body = reader_js[reader_js.index("doubleTap: function"):]
        assert "!== 'middle'" in body[:200]

    def test_scroll_mode_has_zones(self, reader_js):
        body = reader_js[reader_js.index("function handleScrollTap"):]
        assert "readerTapZone(s.scroller" in body[:300]


class TestPullPastTheEnd:
    def test_next_issue_marks_finished_previous_does_not(self, reader_js):
        body = reader_js[reader_js.index("function goToIssue"):reader_js.index("function readerOverscroll")]
        assert "continueToNextIssue()" in body
        assert "closeComicReader()" in body and "openComicReader(target.path)" in body

    def test_swipe_down_closes_only_from_a_touch_gesture(self, reader_js):
        body = reader_js[reader_js.index("function readerOverscroll"):reader_js.index("function readerWheelOverscroll")]
        assert "allowClose" in body and "closeComicReader()" in body
        # The wheel path must never close the reader.
        wheel = reader_js[reader_js.index("function readerWheelOverscroll"):reader_js.index("function attachReaderSwipes")]
        assert "readerOverscroll(dir, false)" in wheel

    def test_swipes_ignore_the_resume_prompt(self, reader_js):
        # Closing from page 1 would persist page 1 and clear the saved bookmark.
        body = reader_js[reader_js.index("function attachReaderSwipes"):]
        assert "resumeReadingOverlay" in body[:600]

    def test_gestures_are_attached(self, reader_js):
        assert "attachReaderSwipes(readerModal)" in reader_js


class TestSpreads:
    def test_cover_stands_alone_then_pairs(self, reader_js):
        assert "slidesPerGroupSkip: 1" in reader_js and "slidesPerGroup: 2" in reader_js
        assert "slidesOffsetBefore" in reader_js

    def test_spread_start_pairs_after_the_cover(self):
        # Mirror of spreadStart(): 0, then 1, 3, 5...
        start = lambda p: 0 if p <= 0 else (p if p % 2 == 1 else p - 1)
        assert [start(p) for p in range(6)] == [0, 1, 1, 3, 3, 5]

    def test_right_hand_page_counts_as_seen(self, reader_js):
        assert "lastSeen" in reader_js and "highestPageViewed = lastSeen" in reader_js
