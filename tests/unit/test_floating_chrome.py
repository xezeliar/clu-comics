"""The navbar and the list toolbar are one floating look (DESIGN.md "Navigation").

The navbar used to be a full-width ``bg-primary`` slab with ``data-bs-theme="dark"``
on every theme. It now reads the theme's own tokens, so a regression that puts
those back would silently re-paint the header on all 20+ themes (and re-break the
Catppuccin contrast the new active state was chosen to avoid).
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _nav_tag():
    html = read("templates", "header.html")
    return re.search(r"<nav\b[^>]*>", html).group(0)


def test_navbar_is_the_floating_bar_not_a_primary_slab():
    tag = _nav_tag()
    assert 'class="navbar navbar-expand-lg clu-navbar"' in tag
    for banned in ("bg-primary", "navbar-dark", 'data-bs-theme="dark"'):
        assert banned not in tag, banned


def test_navbar_css_floats_on_the_raised_surface():
    css = read("static", "css", "clu-page.css")
    assert "nav.navbar.clu-navbar > [class*=\"container\"]" in css
    block = css[css.index("nav.navbar.clu-navbar > [class*=\"container\"]"):]
    block = block[:block.index("}")]
    assert "var(--bs-tertiary-bg)" in block
    assert "border-radius: 1rem" in block
    assert "box-shadow" in block


def test_active_item_never_relies_on_white_on_primary():
    css = read("static", "css", "clu-page.css")
    rules = re.findall(r"\.clu-navbar \.navbar-nav \.nav-link\.active \{[^}]*\}", css)
    assert rules, "active-item rule missing"
    for rule in rules:
        assert "#fff" not in rule and "white" not in rule
        assert "background-color" in rule
    assert "font-weight: 700" in rules[0]
    assert "var(--bs-link-color)" in rules[0]


def test_toolbar_matches_the_navbar_surface():
    css = read("static", "css", "clu-page.css")
    block = css[css.index("\n.clu-toolbar {"):]
    block = block[:block.index("}")]
    assert "var(--bs-tertiary-bg)" in block
    assert "border: 1px solid var(--bs-border-color)" in block
    assert "border-radius: 1rem" in block
    assert "box-shadow" in block


def test_file_manager_panes_have_their_own_toolbar_and_body():
    """Source and Destination are two tools: each pane macro draws its own
    floating toolbar and its own list box, and files.js's ids stay inside them."""
    html = read("templates", "files.html")
    macro = html[html.index("{% macro fm_pane"):html.index("{% endmacro %}")]
    assert macro.count('class="fm-toolbar"') == 1
    assert macro.count('class="fm-body"') == 1
    toolbar = macro[macro.index('class="fm-toolbar"'):macro.index('class="fm-body"')]
    for needle in ("fm-places", "-path-display", "-directory-filter"):
        assert needle in toolbar, needle
    body = macro[macro.index('class="fm-body"'):]
    assert "-list" in body and "-footer" in body
    css = read("static", "css", "files.css")
    assert ".fm-toolbar {" in css and ".fm-body {" in css
