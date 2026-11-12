"""The motion tokens and the reduced-motion rule live in clu-page.css."""
from pathlib import Path

CSS = (Path(__file__).parents[2] / "static/css/clu-page.css").read_text()

TOKENS = ["press: 120ms", "fast: 150ms", "base: 250ms", "travel-in: 400ms",
          "travel-back: 300ms", "long: 500ms", "ease:", "spring:", "stagger: 40ms"]


def test_tokens_defined():
    for t in TOKENS:
        assert f"--clu-dur-{t}" in CSS or f"--clu-{t}" in CSS, t
    assert "cubic-bezier(0.34, 1.35, 0.64, 1)" in CSS


def test_reduced_motion_rule_present():
    assert '@media (prefers-reduced-motion: reduce)' in CSS
    assert ':root:not([data-clu-motion="full"])' in CSS
    assert ':root[data-clu-motion="reduce"]' in CSS
    assert "transition-property: opacity, color, background-color" in CSS


ROOT = Path(__file__).parents[2]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_reduce_motion_setting_in_schema():
    from core.settings import SETTINGS_SCHEMA

    assert "REDUCE_MOTION" in SETTINGS_SCHEMA
    assert "reduce_motion" in repr(SETTINGS_SCHEMA["REDUCE_MOTION"])
    assert "system" in repr(SETTINGS_SCHEMA["REDUCE_MOTION"])


def test_html_tag_writes_data_clu_motion():
    for rel in ("templates/base.html", "templates/login.html"):
        html = _read(rel)
        tag = html[html.index("<html"):html.index(">", html.index("<html"))]
        assert 'data-clu-motion="{{ clu_motion }}"' in tag, rel
    assert "js/clu-motion.js" in _read("templates/base.html")


def test_every_keyframe_animation_is_off_under_both_reduced_selectors():
    import re

    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for name in re.findall(r"@keyframes\s+([\w-]+)", css):
        users = re.findall(r"([^{}]+)\{[^}]*animation:\s*" + re.escape(name) + r"\b", css)
        assert users, name
        for sel in users:
            for s in sel.split(","):
                s = s.strip()
                for guard in (':root:not([data-clu-motion="full"]) ', ':root[data-clu-motion="reduce"] '):
                    assert re.search(re.escape(guard + s) + r"\s*\{\s*animation:\s*none", css), (guard, s)


def test_view_transitions_are_off_under_both_reduced_selectors():
    assert "@view-transition { navigation: auto; }" in CSS
    assert ':root:not([data-clu-motion="full"])::view-transition-group(*) { animation: none; }' in CSS
    assert ':root[data-clu-motion="reduce"]::view-transition-group(*) { animation: none; }' in CSS


def test_tab_pill_and_shared_cover_are_named():
    assert "view-transition-name: clu-tab-pill" in CSS
    assert "view-transition-name: clu-cover" in CSS
    assert "clu-tabbar-pill" in _read("templates/partials/tab_bar.html")
    assert "clu-shared-cover" in _read("templates/series.html")


def test_scripts_go_through_the_one_reduced_motion_test():
    js = _read("static/js/clu-motion.js")
    assert "CLU.reducedMotion = function" in js
    assert 'data-clu-motion' in js and "prefers-reduced-motion: reduce" in js
    # Each helper bails out or degrades under reduced motion.
    for helper in ("CLU.staggerIn", "CLU.burst", "CLU.countUp", "CLU.readerOpened"):
        body = js[js.index(helper + " = function"):]
        body = body[:body.index("\n  };")]
        assert "reducedMotion()" in body, helper
    assert "CLU.reducedMotion" in _read("static/js/clu-toast.js")


def test_hooks_are_wired():
    assert "CLU.staggerIn(grid)" in _read("static/js/collection.js")
    assert "CLU.swapImage" in _read("static/js/collection.js")
    assert "CLU.burst(button)" in _read("static/js/collection.js")
    reader = _read("static/js/reader.js")
    assert "CLU.readerOpened(modal)" in reader and "CLU.readerClosing(modal)" in reader
    status = _read("templates/status.html")
    assert "CLU.flip(root" in status and "li.dataset.flipKey = row.key" in status
    insights = _read("static/js/insights.js")
    assert "data-clu-count" in insights and "CLU.countUp" in insights
