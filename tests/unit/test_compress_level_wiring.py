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
