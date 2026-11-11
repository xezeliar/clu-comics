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
