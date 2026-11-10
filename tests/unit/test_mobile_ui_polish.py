"""Mobile UI polish: pull-to-refresh, grid skeleton, touch targets.
Asserts on the assets as text (no JS runner here)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_pull_to_refresh_is_loaded_everywhere_and_skips_the_reader():
    assert "clu-pull-refresh.js" in read("templates", "base.html")
    assert "overflow === 'hidden'" in read("static", "js", "clu-pull-refresh.js")


def test_grid_loads_with_a_skeleton():
    assert "clu-skeleton-card" in read("templates", "collection.html")
    assert "prefers-reduced-motion" in read("static", "css", "clu-page.css")


def test_touch_targets_are_coarse_pointer_only():
    css = read("static", "css", "clu-page.css")
    assert "@media (pointer: coarse)" in css and "min-height: 44px" in css
