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
    start = js.index("async function loadFeaturedHero()")
    return js[start:js.index("async function loadOnTheStackSwiper()", start)]


def test_fallback_chain_is_on_the_stack_then_continue_reading_then_newest():
    body = _hero_js()
    order = [body.index(u) for u in (
        "/api/on-the-stack?limit=1",
        "/api/continue-reading?limit=1",
        "/list-recent-files?limit=1",
    )]
    assert order == sorted(order)


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
