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


def test_view_toggles_are_segmented_controls_with_a_non_fill_selection():
    css = read("static", "css", "clu-page.css")
    assert ".btn-group.clu-seg" in css
    sel = css[css.index('.btn-group.clu-seg > .btn[aria-pressed="true"]'):]
    sel = sel[:sel.index("}")]
    assert "font-weight: 700" in sel and "var(--bs-link-color)" in sel
    for template, needle in (("collection.html", 'aria-label="Layout"'),
                             ("releases.html", 'aria-label="View mode"'),
                             ("wanted.html", 'id="wantedView"')):
        html = read("templates", template)
        tag = html[html.rindex("<div", 0, html.index(needle)):html.index(needle)]
        assert "clu-seg" in tag, template


def test_filters_and_letters_are_pills_and_the_count_is_a_chip():
    css = read("static", "css", "clu-page.css")
    assert ".clu-letter-bar.btn-group > .btn" in css
    assert ".clu-filter-options > .btn" in css
    count = css[css.index("\n.clu-toolbar-count {"):]
    count = count[:count.index("}")]
    assert "border-radius: var(--bs-border-radius-pill)" in count


def test_toolbar_navigation_buttons_are_quiet_link_pills():
    html = read("templates", "collection.html")
    for ident in ("folderViewBtn", "allBooksBtn", "missingXmlBtn", "rescanMissingXmlBtn"):
        tag = html[html.rindex("<button", 0, html.index(f'id="{ident}"')):html.index(f'id="{ident}"')]
        assert "clu-nav-btn" in tag, ident
    css = read("static", "css", "clu-page.css")
    block = css[css.index(".btn.clu-nav-btn {"):]
    block = block[:block.index("}")]
    assert "--bs-btn-color: var(--bs-link-color)" in block
    assert "--bs-btn-border-color: transparent" in block
