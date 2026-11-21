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


def test_toolbar_is_a_command_row_not_a_raised_panel():
    # The list-toolbar redesign: one hairline under the row, no surface.
    css = read("static", "css", "clu-page.css")
    block = css[css.index("\n.clu-toolbar {"):]
    block = block[:block.index("}")]
    assert "border-bottom: 1px solid var(--bs-border-color)" in block
    assert "var(--bs-tertiary-bg)" not in block and "box-shadow" not in block


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


def test_letters_are_a_text_strip_and_the_count_is_plain_text():
    css = read("static", "css", "clu-page.css")
    assert ".clu-letter.active {" in css and ".clu-letter-bar.btn-group" not in css
    assert ".clu-filter-options > .btn" in css
    count = css[css.index("\n.clu-toolbar-count {"):]
    count = count[:count.index("}")]
    assert "border" not in count


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


def test_file_manager_place_switcher_is_segmented_including_its_nested_dropdown():
    html = read("templates", "files.html")
    assert 'class="btn-group clu-seg fm-places files-source-views"' in html
    css = read("static", "css", "clu-page.css")
    assert ".btn-group.clu-seg > .btn-group > .btn" in css


def test_lone_toolbar_action_buttons_are_pills_but_grouped_ones_keep_corners():
    css = read("static", "css", "clu-page.css")
    block = css[css.index(".clu-toolbar-row > .btn,"):]
    block = block[:block.index("}")]
    for sel in (".clu-toolbar-row > .dropdown > .btn", ".clu-toolbar-end > .btn"):
        assert sel in block
    assert "border-radius: var(--bs-border-radius-pill)" in block
    # Never a bare descendant selector: that would round the joined groups too.
    assert ".clu-toolbar .btn {" not in css


# ── Round 2: compact toolbars, File Manager ring, series toolbar, cover shadow ──

def test_toolbar_controls_are_compact_but_still_touch_sized():
    """The app-wide rule makes every .btn-sm 44px on a touch screen, which made
    each toolbar a stack of tall blocks on an iPad. Inside a toolbar they are
    36px; outside it the 44px rule is untouched."""
    css = read("static", "css", "clu-page.css")
    assert ".btn-sm, .btn-group-sm > .btn { min-height: 44px; }" in css   # still there
    block = css[css.index(".clu-toolbar .btn-sm,\n.clu-toolbar .btn-group-sm > .btn {"):]
    block = block[:block.index("}")]
    assert "min-height: 2.25rem" in block
    assert "2.25rem" in css[css.index(".clu-toolbar .clu-search,"):][:200]


def test_file_manager_accent_and_ring_follow_the_rounded_parts():
    """The top accent and active ring used to be on .fm-pane, which is now a
    transparent column, so its square box showed as a second border around two
    rounded ones."""
    accent = read("static", "css", "clu-accent.css")
    assert ".fm-pane:not(.is-active) { box-shadow" not in accent
    assert ".fm-pane.is-active { border-color" not in accent
    assert ".fm-pane.is-active .fm-toolbar {" in accent
    assert ".fm-pane.is-active .fm-body {" in accent
    assert "inset 0 3px 0 var(--fm-hue)" in accent   # inset shadows follow the radius


def test_every_cover_uses_the_one_shadow_token():
    css = read("static", "css", "clu-page.css")
    assert "--clu-cover-shadow:" in css
    assert ':root[data-bs-theme="dark"] {\n    --clu-cover-shadow' in css
    for sel in (".pl-week img", ".sh-cover img", ".rl-it .book-cover"):
        assert sel in css[css.index("--clu-cover-shadow: 0 3px"):]
    coll = read("static", "css", "collection.css")
    for sel in (".thumbnail-container {", ".dashboard-card-img-container {"):
        block = coll[coll.index("\n" + sel):]
        assert "box-shadow: var(--clu-cover-shadow)" in block[:block.index("}")], sel
    # Performance: a plain box-shadow only. filter: drop-shadow() repaints the
    # whole element and was deliberately not used on covers.
    assert "drop-shadow" not in css.split("--clu-cover-shadow: 0 3px")[1][:600]


def test_series_mapping_is_a_toolbar_and_the_script_no_longer_finds_a_card():
    html = read("templates", "series.html")
    assert "import toolbar" in html
    assert "{% call toolbar('Collection mapping and series actions', id='mappingToolbar') %}" in html
    block = html[html.index("<!-- Mapping Section -->"):html.index("<!-- Progress indicator -->")]
    assert "card border-0 shadow-sm" not in block
    for ident in ("mapLocationBtn", "mappingActions", "aliasesRow", "checkMissingBtn",
                  "sync-btn", "refresh-btn", "stackSubscription", "monitorSeries",
                  "aliasesDisplay", "mapped-path-display"):
        assert f'id="{ident}"' in block, ident
    # Rows are always rendered and hidden until mapped, which series.js reveals.
    assert 'id="mappingActions"{% if not mapped_path %} hidden{% endif %}' in block
    js = read("static", "js", "series.js")
    assert "#mapping .card-body" not in js
    assert "mappingActions" in js and "aliasesRow" in js
    # No coloured outlines: every action is a small neutral outline button.
    assert "btn-outline-primary" not in block and "btn-outline-success" not in block
