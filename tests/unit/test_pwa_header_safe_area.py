"""Standalone (home-screen) mode draws under the status bar; the navbar must clear it."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_translucent_status_bar_is_paired_with_a_navbar_inset():
    assert "black-translucent" in read("templates", "base.html")
    css = read("static", "css", "clu-page.css")
    assert "padding-top: env(safe-area-inset-top" in css
