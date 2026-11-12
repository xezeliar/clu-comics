"""Series page "Change Location" picker when the mapped folder is gone.

A mapping whose folder was deleted outside CLU made ``/list-directories``
answer 404, and ``loadDirectories`` rendered the error body as an empty
listing: "No directories found", with no way to navigate anywhere. It now
walks up to the nearest folder that exists (404) or opens the default library
(403). Asserted structurally, and run through ``node`` when it is available.
"""
import os
import shutil
import subprocess

import pytest

SERIES_JS = os.path.join(
    os.path.dirname(__file__), "..", "..", "static", "js", "series.js"
)

# A fake DOM and fetch: /data/comics and /data/comics/Marvel exist, anything
# else under the library is a 404 and anything outside it a 403.
HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const existing = {'/data/comics': ['Marvel'], '/data/comics/Marvel': ['Excalibur']};
global.defaultLibraryPath = '/data/comics';
const calls = [];
global.fetch = url => {
  const p = decodeURIComponent(url.split('path=')[1]);
  calls.push(p);
  const ok = p in existing;
  const status = ok ? 200 : (p.startsWith('/data/comics') ? 404 : 403);
  return Promise.resolve({ ok, status, json: () => Promise.resolve(
    ok ? { current_path: p, directories: existing[p], parent: null } : { error: 'nope' }) });
};
const els = {};
global.document = {
  getElementById: id => els[id] || (els[id] = { innerHTML: '', textContent: '', appendChild() {}, style: {} }),
  querySelector: () => null,
  createElement: () => ({ style: {}, setAttribute() {}, appendChild() {} }),
};
global.CLU = { letterBar() {} };
eval(src + ';globalThis.loadDirectories = loadDirectories;');
const start = process.argv[2];
loadDirectories(start);
setTimeout(() => console.log(JSON.stringify({ calls, shown: els['current-path-display'].textContent })), 50);
"""


def _read():
    with open(SERIES_JS, encoding="utf-8") as fh:
        return fh.read()


def test_error_responses_are_not_rendered_as_a_listing():
    src = _read()
    body = src[src.index("function loadDirectories("):src.index("function updateFilterBar(")]
    assert "response.ok" in body and "status === 404" in body and "status === 403" in body


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("start, calls, shown", [
    ("/data/comics/Marvel/Gone/v2025",
     ["/data/comics/Marvel/Gone/v2025", "/data/comics/Marvel/Gone", "/data/comics/Marvel"],
     "/data/comics/Marvel"),
    ("/elsewhere/old", ["/elsewhere/old", "/data/comics"], "/data/comics"),
])
def test_walks_to_the_nearest_existing_folder(start, calls, shown):
    import json
    out = subprocess.run(["node", "-e", HARNESS, SERIES_JS, start],
                         capture_output=True, text=True, timeout=20, check=True)
    result = json.loads(out.stdout)
    assert result == {"calls": calls, "shown": shown}
