"""File names in the File Manager are text, never markup.

files.js once wrote a listing row as ``nameSpan.innerHTML = `${fileData.name} ...` ``,
so a file named ``<img src=x onerror=...>.cbz`` ran as script in the page.
This pins every innerHTML template in files.js: a file-name expression inside
one must go through ``CLU.escapeHtml``.
"""
import re
from pathlib import Path

FILES_JS = Path(__file__).resolve().parents[2] / "static" / "js" / "files.js"

# innerHTML = `...` or += `...`, possibly spanning lines.
INNER_HTML_TEMPLATE = re.compile(r"\.innerHTML\s*\+?=\s*`(.*?)`", re.S)
# ${ ... } whose expression names a file (fileData.name, failedFile.fileName, file.file_name ...).
NAME_EXPR = re.compile(r"\$\{([^}]*\b(?:fileData\.name|fileName|file_name)\b[^}]*)\}")


def test_file_names_are_escaped_in_innerhtml_templates():
    src = FILES_JS.read_text(encoding="utf-8")
    bad = []
    for m in INNER_HTML_TEMPLATE.finditer(src):
        for expr in NAME_EXPR.findall(m.group(1)):
            if "escapeHtml" not in expr:
                line = src.count("\n", 0, m.start()) + 1
                bad.append(f"files.js:{line}: ${{{expr}}}")
    assert not bad, "File names written as HTML without CLU.escapeHtml:\n" + "\n".join(bad)


def test_listing_row_name_is_text_content():
    """One row builder (fmRow) draws every place; it writes no markup at all."""
    src = FILES_JS.read_text(encoding="utf-8")
    row = src[src.index("function fmRow("):]
    row = row[:row.index("\n}\n")]
    assert "go.textContent = e.name;" in row
    assert "nm.textContent = e.name;" in row
    assert "innerHTML" not in row
    assert "nameSpan.innerHTML" not in src
