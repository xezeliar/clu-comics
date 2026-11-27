"""The photo tile (partials/person_tile.html) and its Insights twin.

A tile with no cached image keeps the same box and shows the initials, so a
missing image, or Metron being down, never changes the layout. The Insights
page draws the same markup in JavaScript (static/js/insights.js), so the class
names are pinned in both places.
"""

import pathlib

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
_env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True)


def _tile(person, href="/characters/x"):
    t = _env.from_string(
        "{% from 'partials/person_tile.html' import person_tile %}{{ person_tile(p, h) }}")
    return t.render(p=person, h=href)


def test_tile_with_art_shows_the_image():
    html = _tile({"name": "Wolverine", "n": 14, "art": "/api/person-art/character/wolverine"})
    assert '<img src="/api/person-art/character/wolverine"' in html
    assert "pt-ini" not in html
    assert "14 issues" in html
    assert 'aria-hidden="true"' in html  # the image is decorative


def test_tile_without_art_shows_initials_in_the_same_box():
    html = _tile({"name": "Jonathan Hickman", "n": 1, "art": None})
    assert "<img" not in html
    assert '<span class="pt-ini">JH</span>' in html
    assert "1 issue<" in html and "1 issues" not in html


def test_initials_skip_the_and_split_hyphens():
    html = _tile({"name": "The X-Men", "n": 2, "art": None})
    assert '<span class="pt-ini">XM</span>' in html


def test_name_is_escaped():
    html = _tile({"name": 'A "<b>"', "n": 3, "art": None})
    assert "<b>" not in html


