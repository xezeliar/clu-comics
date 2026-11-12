"""core/publishers.py: the fixed table behind the publisher dot, and the macro."""
import pytest
from flask import Flask, render_template_string

from core.publishers import PUBLISHER_COLORS, publisher_color


@pytest.mark.parametrize("name", [
    "DC Comics", "dc comics", "Marvel", "Image Comics", "Dark Horse Comics", "IDW Publishing",
    "BOOM! Studios", "Dynamite Entertainment", "Oni Press", "Titan Comics", "Valiant",
    "Archie Comics", "Vault Comics", "Mad Cave Studios", "Ahoy Comics",
])
def test_known_houses_get_a_colour(name):
    assert publisher_color(name) in PUBLISHER_COLORS.values()


@pytest.mark.parametrize("name", ["Vertigo", "Fantagraphics", "Image Titan", "", None])
def test_other_publishers_get_no_dot(name):
    assert publisher_color(name) is None


def _render(**ctx):
    app = Flask(__name__, template_folder="../../templates")
    app.add_template_global(publisher_color, "publisher_color")
    with app.test_request_context():
        return render_template_string(
            '{% from "partials/publisher_dot.html" import publisher_dot with context %}'
            "{{ publisher_dot('Marvel Comics') }}|{{ publisher_dot('Nobody') }}", **ctx)


def test_macro_draws_dot_only_for_known_house():
    html = _render()
    assert html.count("pub-dot") == 1 and "--pub: #ec1d24" in html


def test_macro_hidden_when_switch_is_off():
    assert "pub-dot" not in _render(appearance_publisher_dots=False)
