"""Runs CLU.credited (static/js/clu-credited.js) under node: the per-role
drill-down filters on the series folder and series page. Filters combine with
AND, the URL keeps one param per filter, and the old credited=<kind>:<name>
(&role=) links still open. Skipped where node is not installed."""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

PEOPLE = [
    {"key": "creator:Mara Quell", "kind": "creator", "name": "Mara Quell",
     "paths": ["a", "b", "c", "d"],
     "roles": [{"kind": "writer", "label": "Writer", "paths": ["a", "b", "c"]},
               {"kind": "coverartist", "label": "Cover artist", "paths": ["d"]}]},
    {"key": "creator:Ito Vance", "kind": "creator", "name": "Ito Vance",
     "paths": ["a", "d"], "roles": [{"kind": "penciller", "label": "Penciller", "paths": ["a", "d"]}]},
    {"key": "character:Nadia Cross", "kind": "character", "name": "Nadia Cross",
     "paths": ["b", "c", "d"], "roles": []},
]

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const people = JSON.parse(process.argv[3]);
const sandbox = {
  document: { addEventListener() {}, removeEventListener() {} }, console, setTimeout,
  URLSearchParams,
  fetch: () => Promise.resolve({ json: () => Promise.resolve({ success: true, people }) }),
};
sandbox.window = sandbox;
sandbox.CLU = { escapeHtml: s => String(s).replace(/[&<>"]/g, c => '&#' + c.charCodeAt(0) + ';') };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);
const C = sandbox.CLU.credited;

const out = {};
const p = q => { const v = C.parse(new URLSearchParams(q)); return v && Object.assign({}, v); };
out.parsed = p('writer=Mara Quell&character=Nadia Cross');
out.legacyRole = p('credited=creator:Mara Quell&role=writer');
out.legacyAny = p('credited=creator:Mara Quell');
out.none = p('path=/x');
const w = new URLSearchParams('path=/x&credited=team:Old&role=writer');
C.write(w, { penciller: 'Ito Vance' });
out.written = w.toString();

const slot = {
  innerHTML: '', isConnected: true, classList: { toggle() {} },
  addEventListener() {}, querySelector() { return null; },
};
C.picker(slot, {
  folder: '/x', total: 5, value: { writer: 'mara quell', character: 'Nadia Cross' },
  onChange: (v, paths) => { out.change = paths ? Array.from(paths).sort() : null; },
});
setTimeout(() => {
  out.html = slot.innerHTML;
  console.log(JSON.stringify(out));
}, 20);
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    script = tmp_path_factory.mktemp("cred") / "h.js"
    script.write_text(HARNESS)
    res = subprocess.run([NODE, str(script), os.path.join(ROOT, "static/js/clu-credited.js"),
                          json.dumps(PEOPLE)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_url_has_one_param_per_filter(run):
    assert run["parsed"] == {"writer": "Mara Quell", "character": "Nadia Cross"}
    assert run["none"] is None
    # write() drops the old form and every filter it does not set.
    assert run["written"] == "path=%2Fx&penciller=Ito+Vance"


def test_old_credited_links_still_open(run):
    assert run["legacyRole"] == {"writer": "Mara Quell"}
    assert run["legacyAny"] == {"creator": "Mara Quell"}


def test_filters_combine_with_and(run):
    # Writer Mara Quell: a, b, c; Nadia Cross: b, c, d.
    assert run["change"] == ["b", "c"]


def test_one_button_per_role_present(run):
    html = run["html"]
    for f in ("writer", "penciller", "coverartist", "character"):
        assert f'data-open="{f}"' in html
    # Nobody inks, letters or forms a team here, and "creator" shows only when set.
    for f in ("inker", "letterer", "team", "creator"):
        assert f'data-open="{f}"' not in html
    assert "data-clearall" in html
