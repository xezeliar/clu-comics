"""The comic reader's markup lives in one partial.

It used to be pasted into four page templates, and the copies drifted (two
lacked the footer progress line, one relabelled the bookmark). Every page now
includes partials/reader_modal.html, so a reader change lands once.
"""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(REPO_ROOT, "templates")
HOSTS = ["collection.html", "metadata_browser.html", "reading_list_view.html", "source_wall.html"]


def _read(name):
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("name", HOSTS)
def test_reader_markup_lives_only_in_partial(name):
    html = _read(name)
    assert "{% include 'partials/reader_modal.html' %}" in html
    assert 'id="comicReaderModal"' not in html


def test_partial_holds_the_reader_once():
    assert _read("partials/reader_modal.html").count('id="comicReaderModal"') == 1
