"""Comic reader: the toolbar is floating dark pills instead of bars tinted to
the page. Asserted on the assets as text (no JS runner); the look was checked
in a browser."""
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def function_body(source, name, keyword="function"):
    start = source.index("%s %s(" % (keyword, name))
    end = source.find("\n%s " % keyword, start + 1)
    return source[start:end if end != -1 else len(source)]


def rules_for(css, selector):
    """Bodies of the rules whose selector list has an item ending in `selector`."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        items = [" ".join(item.split()) for item in selectors.split(",")]
        if any(item.endswith(selector) for item in items):
            found.append(body)
    return found


@pytest.fixture(scope="module")
def js():
    return read("static", "js", "reader.js")


@pytest.fixture(scope="module")
def css():
    return read("static", "css", "reader.css")


@pytest.fixture(scope="module")
def html():
    return read("templates", "partials", "reader_modal.html")


def test_bars_not_painted(js):
    for name in ("applyReaderBackgroundColor", "resetReaderBackgroundColor"):
        body = function_body(js, name)
        assert "header" not in body and "footer" not in body
    assert "reader-light-bg" not in js


def test_no_percent_bar(js, css, html):
    for text in (js, css, html):
        assert "comic-reader-progress" not in text
    assert "#4CAF50" not in css.upper()
    assert "reader-light-bg" not in css


def test_pills_have_no_glass(css):
    assert "backdrop-filter" not in css
    for selector in (".reader-pill", ".reader-capsule"):
        rules = rules_for(css, selector)
        assert rules, selector
        assert any("rgba(18, 18, 18, 0.86)" in r for r in rules)
        assert not any("gradient" in r for r in rules)


def test_markup(html):
    assert 'id="comicReaderSubtitle"' in html
    assert 'class="reader-capsule"' in html
    assert 'class="reader-hidden-line"' in html
    assert "comicReaderPageInfo" not in html
    assert 'id="readerProgressLine"' in html


def test_hidden_chrome_is_inert(js):
    body = function_body(js, "toggleReaderChrome")
    assert ".inert" in body
    # Every path that hides the chrome goes through the one setter.
    assert "classList.add('reader-chrome-hidden')" not in js


def test_hidden_line_shows_only_when_hidden(css):
    assert rules_for(css, ".reader-chrome-hidden .reader-hidden-line")
    line = rules_for(css, ".reader-hidden-line > i")
    assert any("var(--reader-accent)" in r for r in line)


def test_zoom_only_with_mouse(css):
    assert re.search(r"@media \(pointer: fine\)\s*\{[^@]*\.reader-capsule \.zoom-btn", css)


def test_reduced_motion(css):
    blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", css, re.S)
    assert any(".comic-reader-header" in b and "transition: opacity" in b for b in blocks)


def test_pace_count_is_short(js, css):
    body = function_body(js, "updateReaderPaceLine")
    assert "pace" in body and " / " in body
    assert re.search(r"@media \(max-width: 480px\)\s*\{[^@]*\.pace", css)


def test_info_returns_title():
    app = read("routes", "reading.py")
    body = function_body(app, "read_comic_info", keyword="def")
    assert "get_reader_display_fields(" in body
    db = read("core", "database.py")
    helper = function_body(db, "get_reader_display_fields", keyword="def")
    assert "ci_title" in helper and "with db_conn()" in helper


def test_subtitle_is_filled(js):
    assert "comicReaderSubtitle" in function_body(js, "openComicReader")
    assert "comicReaderPageInfo" not in js


def test_keys_ignore_toolbar_buttons(js):
    body = function_body(js, "handleComicReaderKeydown")
    head = body[:body.index("e.code === 'Space'")]
    assert "e.target.closest('button')" in head


def test_reader_display_fields(tmp_path, monkeypatch):
    # The real helper against a real table: blank tags are not a title.
    import sqlite3
    from core import database

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE file_index (path TEXT, ci_series TEXT, ci_number TEXT, ci_title TEXT)")
    conn.execute("INSERT INTO file_index VALUES ('/l/a.cbz', 'Saga', '012', 'Chapter Twelve')")
    conn.execute("INSERT INTO file_index VALUES ('/l/b.cbz', '', '', '')")
    conn.commit()
    conn.close()

    def connect():
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(database, "get_db_connection", connect)
    assert database.get_reader_display_fields("/l/a.cbz") == {
        "series": "Saga", "number": "012", "title": "Chapter Twelve"}
    assert database.get_reader_display_fields("/l/b.cbz") == {
        "series": None, "number": None, "title": None}
    assert database.get_reader_display_fields("/l/missing.cbz") == {
        "series": None, "number": None, "title": None}
