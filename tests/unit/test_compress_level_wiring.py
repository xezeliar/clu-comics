"""The Compression Level must survive the round trip from the Config page.

Same shape as test_date_check_settings_wiring: the File Processing tab collects
element ids into a JSON payload for /api/config/file-processing, so a setting
can be rendered and read by the compressor and still be impossible to change
from the UI. Source-level assertions, because app.py cannot be imported in tests.
"""
import pathlib
import re

import pytest

from cbz_ops.compress import LEVELS, DEFAULT_LEVEL
from core.settings import SETTINGS_SCHEMA

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def config_html():
    return (ROOT / "templates" / "config.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_py():
    return (ROOT / "app.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def save_handler(app_py):
    return app_py.split('@app.route("/api/config/file-processing"')[1].split("@app.route")[0]


def test_setting_is_in_the_schema_with_the_default_level():
    spec = SETTINGS_SCHEMA["COMPRESS_LEVEL"]
    assert spec.pref == "compress_level"
    assert spec.type == "str"
    assert spec.default == DEFAULT_LEVEL
    assert spec.category == "file_processing"


def test_select_offers_exactly_the_known_levels(config_html):
    block = config_html.split('id="compressLevel"')[1].split("</select>")[0]
    offered = re.findall(r'<option value="([^"]+)"', block)
    assert offered == list(LEVELS)


def test_each_option_is_preselected_from_the_stored_level(config_html):
    block = config_html.split('id="compressLevel"')[1].split("</select>")[0]
    for level in LEVELS:
        assert f"compressLevel == '{level}'" in block


def test_field_is_collected_into_the_save_payload(config_html):
    payload = config_html.split("async function saveFileProcessingSettings()")[1].split("fetch(")[0]
    assert "compressLevel" in payload


def test_endpoint_validates_before_storing(save_handler):
    assert '"compressLevel" in data' in save_handler, "absent must mean 'not on this form'"
    assert 'set_setting("COMPRESS_LEVEL", normalize_compress_level(' in save_handler


def test_page_passes_a_validated_level_to_the_template(app_py):
    assert 'compressLevel=normalize_compress_level(st["COMPRESS_LEVEL"])' in app_py


def test_app_imports_the_one_normaliser(app_py):
    assert "from cbz_ops.compress import normalize_level as normalize_compress_level" in app_py


def test_compressor_reads_the_setting_per_call_not_at_import():
    src = (ROOT / "cbz_ops" / "compress.py").read_text(encoding="utf-8")
    assert re.search(r"^\w*LEVEL\w* = get_setting", src, re.M) is None
    assert 'get_setting("COMPRESS_LEVEL")' in src


# ---- Recommended level and the comparison viewer -----------------------------

CHOICES = ["original", *LEVELS]  # the viewer shows the untouched page plus every level


def _select_block(config_html):
    return config_html.split('id="compressLevel"')[1].split("</select>")[0]


def _modal_block(config_html):
    return config_html.split('id="compressCompareModal"')[1].split("{% include 'partials/modal_regenerate")[0]


def test_balanced_is_the_recommended_level_and_only_balanced(config_html):
    options = re.findall(r'<option value="([^"]+)"[^>]*>([^<]*)</option>', _select_block(config_html))
    recommended = [value for value, label in options if "Recommended" in label]
    assert recommended == ["balanced"]


def test_recommendation_does_not_change_the_default():
    """The label is advice; changing the default would silently alter every install."""
    assert DEFAULT_LEVEL == "full"


@pytest.mark.parametrize("choice", CHOICES)
def test_comparison_image_ships_and_is_a_real_webp(choice):
    path = ROOT / "static" / "images" / f"compress-compare-{choice}.webp"
    head = path.read_bytes()[:12]
    assert head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    assert 20_000 < path.stat().st_size < 1_000_000


@pytest.mark.parametrize("choice", CHOICES)
def test_modal_points_at_each_image_through_url_for(config_html, choice):
    modal = _modal_block(config_html)
    assert f"url_for('static', filename='images/compress-compare-{choice}.webp')" in modal


def test_modal_has_one_radio_per_choice_and_original_starts_selected(config_html):
    modal = _modal_block(config_html)
    radios = re.findall(r'<input type="radio"[^>]*name="compressCompareChoice"[^>]*>', modal, re.S)
    assert len(radios) == len(CHOICES)
    assert "checked" in radios[0] and "compress-compare-original" in radios[0]


def test_compare_button_opens_the_modal(config_html):
    assert 'data-bs-target="#compressCompareModal"' in config_html


def test_images_are_not_fetched_until_the_modal_opens(config_html):
    """The <img> has no src of its own; the script sets it on show.bs.modal."""
    modal = _modal_block(config_html)
    tag = re.search(r'<img id="compressCompareImg"[^>]*>', modal).group(0)
    assert " src=" not in tag
    assert "show.bs.modal" in config_html.split("compressCompareModal")[-1]


def test_comparison_uses_a_modal_not_a_native_dialog(config_html):
    modal = _modal_block(config_html)
    assert "alert(" not in modal and "confirm(" not in modal
