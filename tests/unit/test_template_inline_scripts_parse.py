"""Every inline <script> in templates/ must parse.

One missing comma in config.html's settings script (an upstream merge) was a
SyntaxError that dropped the whole block, so the Appearance panel never
initialised and no theme could be picked, with no server-side symptom.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\b(?:src|type)=)[^>]*>(.*?)</script>", re.S)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _scripts():
    for path in sorted(TEMPLATES.rglob("*.html")):
        for i, m in enumerate(INLINE_SCRIPT.finditer(path.read_text(encoding="utf-8"))):
            # Jinja expressions become a value and tags vanish, so the JS around them is checked.
            js = re.sub(r"\{\{.*?\}\}", "null", m.group(1), flags=re.S)
            js = re.sub(r"\{%.*?%\}", "", js, flags=re.S)
            yield pytest.param(js, id=f"{path.relative_to(TEMPLATES)}#{i}")


@pytest.mark.parametrize("js", _scripts())
def test_inline_script_parses(js, tmp_path):
    f = tmp_path / "inline.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
