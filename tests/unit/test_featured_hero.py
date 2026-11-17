"""The Home hero (static/js/collection.js loadFeaturedHero, /api/hero-cover).

collection.js cannot run under pytest, so the wiring is asserted structurally.
What each assertion protects:

* the fallback order, so Home never shows an empty header while the library has
  a comic (On the Stack, then Continue Reading, then newest added);
* the cover is the 720px /api/hero-cover, with the 300px thumbnail only as the
  fallback (stretching the thumbnail is what looks blurry);
* no Save button: the app has no use for it here.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _hero_js():
    js = read("static", "js", "collection.js")
    start = js.index("const HERO_MAX = ")
    return js[start:js.index("async function loadOnTheStackSwiper()", start)]


def test_five_slides_with_recent_additions_in_slots_two_and_four():
    body = _hero_js()
    assert "const HERO_MAX = 5;" in body
    assert "const HERO_ADDED_SLOTS = [1, 3];" in body   # the 2nd and 4th, zero-based
    for url in ("/api/on-the-stack?limit=${HERO_MAX}",
                "/api/continue-reading?limit=${HERO_MAX}",
                "/list-recent-files?limit=${HERO_MAX}"):
        assert url in body
    # Reading is On the Stack first, then Continue Reading.
    assert body.index("label: 'Up next'") < body.index("label: 'Continue reading'")
    assert "label: 'Recently added'" in body
    # Each slot draws from its own queue, tops up from the other, never repeats.
    assert "HERO_ADDED_SLOTS.includes(slot) ? added : reading" in body
    assert "take(wanted) || take(other)" in body
    assert "seen.has(pick.path)" in body
    assert "slot < HERO_MAX" in body


def test_there_is_no_auto_advance():
    """A slide that changes while you are deciding is a misclick waiting to
    happen, and moving content would need a pause control and reduced-motion
    handling. Swipe, dots, arrows and the arrow keys are the only ways."""
    body = _hero_js()
    for banned in ("setInterval", "setTimeout", "autoplay", "autoPlay", "requestIdleCallback"):
        assert banned not in body, banned


def test_covers_load_lazily_for_the_current_and_next_slide_only():
    body = _hero_js()
    assert "card.loadCover = " in body
    assert "Math.abs(n - i) <= 1" in body
    # Nothing fetches a cover while the slides are being built.
    build = body[body.index("const buildSlide"):body.index("const slides = ")]
    assert build.count("/api/hero-cover") == 1
    assert "img.src = cover" in build and "card.loadCover = () =>" in build


def test_carousel_is_keyboard_and_screen_reader_usable():
    body = _hero_js()
    assert "aria-roledescription', 'carousel'" in body
    assert "aria-roledescription', 'slide'" in body
    assert "slide.inert = n !== i" in body        # off-screen slides take no focus
    assert "'aria-current'" in body                # the current dot
    assert "Show slide ${n + 1} of ${slides.length}" in body
    assert "ArrowRight" in body and "ArrowLeft" in body
    assert "prefers-reduced-motion" in body        # no smooth scrolling if reduced
    css = read("static", "css", "collection.css")
    assert "scroll-snap-type: x mandatory" in css
    dot = css[css.index(".featured-hero-dot {"):]
    assert "width: 2.75rem" in dot[:dot.index("}")] and "height: 2.75rem" in dot[:dot.index("}")]


def test_cover_is_the_large_one_with_the_thumbnail_as_fallback_only():
    body = _hero_js()
    assert "/api/hero-cover?path=" in body
    assert "/api/thumbnail?path=" in body
    assert body.index("/api/hero-cover") < body.index("/api/thumbnail")
    assert "img.onerror" in body


def test_hero_has_no_save_button_and_no_native_dialogs():
    body = _hero_js()
    assert "Save" not in body
    assert "to-read" not in body
    assert not re.search(r"\b(alert|confirm|prompt)\(", body)


def test_text_is_never_injected_as_html():
    body = _hero_js()
    assert "innerHTML" not in body


def test_hero_is_loaded_on_home_and_has_a_dashboard_section_to_hide():
    js = read("static", "js", "collection.js")
    assert "loadFeaturedHero();" in js
    html = read("templates", "collection.html")
    assert 'id="featuredHero"' in html
    # A .dashboard-section, so every mode that hides the dashboard hides it.
    assert re.search(r'<section class="dashboard-section[^"]*" id="featuredHero"', html)


def test_hero_css_blurs_the_cover_behind_a_sharp_one():
    css = read("static", "css", "collection.css")
    assert ".featured-hero-bg" in css and "filter: blur(" in css
    assert ".featured-hero-cover" in css
