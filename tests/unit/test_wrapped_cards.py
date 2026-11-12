"""wrapped.py: theme palettes, card styles and formats, and the remembered choice."""
import io
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

import wrapped
from core.themes import THEME_ORDER

NEW_THEMES = ("nord", "dracula", "tokyo-night", "rose-pine", "everforest", "one-dark",
              "solarized-dark", "solarized-light", "kanagawa", "newsprint", "noir",
              "pop-art", "manga")


def test_every_theme_has_a_wrapped_palette():
    assert [t for t in THEME_ORDER if t not in wrapped.THEME_COLORS] == []


def test_new_themes_have_palettes():
    for t in NEW_THEMES:
        assert {"primary", "bg", "text", "text_muted", "is_dark"} <= set(wrapped.THEME_COLORS[t])


@pytest.mark.parametrize("style", wrapped.CARD_STYLES)
@pytest.mark.parametrize("fmt,size", [("story", (1080, 1920)), ("square", (1080, 1080))])
def test_card_renders_at_format_size(style, fmt, size):
    with patch.object(wrapped, "get_yearly_total_read", return_value=312), \
         patch.object(wrapped, "get_most_read_series",
                      return_value=[{"name": "Blue Harbor", "count": 41, "path": ""}]), \
         patch.object(wrapped, "get_read_issues", return_value=[]):
        png = wrapped.generate_card(2026, "noir", style, fmt)
    assert Image.open(io.BytesIO(png)).size == size


def test_unknown_style_and_format_fall_back_to_default():
    with patch.object(wrapped, "get_yearly_total_read", return_value=1), \
         patch.object(wrapped, "get_most_read_series", return_value=[]), \
         patch.object(wrapped, "get_read_issues", return_value=[]):
        png = wrapped.generate_card(2026, "nope", "weird", "huge")
    assert Image.open(io.BytesIO(png)).size == (1080, 1920)


def test_card_choice_is_remembered_per_user(db_connection):
    from core.database import create_user, set_user_setting
    assert wrapped.card_prefs() == wrapped.DEFAULT_CARD
    assert wrapped.save_card_prefs("wall", "square") is True
    assert wrapped.card_prefs() == ("wall", "square")
    assert wrapped.save_card_prefs("wall", "huge") is False
    assert wrapped.save_card_prefs("neon", "story") is False
    assert wrapped.card_prefs() == ("wall", "square")


def test_app_routes_use_the_requesters_theme_and_card_prefs():
    src = (Path(__file__).resolve().parents[2] / "app.py").read_text()
    assert 'theme = get_setting("BOOTSTRAP_THEME")' not in src  # every wrapped route asks _wrapped_theme
    assert src.count("theme = _wrapped_theme()") == 4
    assert "_resolve_request_theme" in src
    assert "/api/wrapped/card-prefs" in src and "card_prefs()" in src
