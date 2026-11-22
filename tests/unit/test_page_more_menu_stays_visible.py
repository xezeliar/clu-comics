"""A click inside the page header's More menu must not hide that menu.

partials/page_header.html renders the menu as <ul data-clu-more>, and the
facet "Show N more" button in static/js/clu-filters.js used the same attribute.
Its document-level click handler matched t.closest('[data-clu-more]'), so a
click on any header menu item (Reading Lists > More > From GitHub) took the
<ul> for a facet button and set ``hidden`` on it. Bootstrap kept toggling
.show, the menu never painted again, and only a reload brought it back -- on
every page with a header More menu.

Runs the real click handler under node against a stubbed DOM. Skipped where
node is not installed; the structural checks below run everywhere.
"""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE = shutil.which("node")
FILTERS_JS = os.path.join(ROOT, "static", "js", "clu-filters.js")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const listeners = {};
const sandbox = {
  document: {
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    querySelectorAll() { return []; },
    readyState: 'complete',
  },
  window: {}, console, setTimeout, clearTimeout,
  requestAnimationFrame: f => f(),
};
sandbox.window = sandbox;
sandbox.Element = function Element() {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);

// What the header renders: a toggle button followed by <ul data-clu-more>.
function el(attrs) {
  const e = Object.create(sandbox.Element.prototype);
  e.hidden = false;
  e.attrs = attrs;
  e.hasAttribute = a => a in attrs;
  return e;
}
const toggle = el({ 'data-bs-toggle': 'dropdown' });
const menu = el({ 'data-clu-more': '' });
menu.previousElementSibling = toggle;
toggle.nextElementSibling = menu;
toggle.querySelectorAll = () => [];
const item = el({ 'data-bs-toggle': 'modal' });
// closest(): the item sits in the menu, so only selectors naming the menu match.
item.closest = sel => sel.split(',').some(s => {
  s = s.trim();
  const m = s.match(/^\[([\w-]+)\]$/);
  return m && m[1] in menu.attrs;
}) ? menu : null;

(listeners.click || []).forEach(f => f({ target: item, preventDefault() {}, stopPropagation() {} }));
console.log(JSON.stringify({ menuHidden: menu.hidden, handlers: (listeners.click || []).length }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_clicking_a_header_menu_item_does_not_hide_the_menu(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS)
    out = subprocess.run(
        [NODE, str(harness), FILTERS_JS],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["handlers"] >= 1
    assert result["menuHidden"] is False


def test_facet_show_more_has_its_own_attribute():
    js = _read("static/js/clu-filters.js")
    assert "setAttribute('data-clu-facet-more', '')" in js
    assert "closest('[data-clu-facet-more]')" in js
    # The shared name belongs to the header menu and the dashboard card button.
    assert "closest('[data-clu-more]')" not in js
    assert "setAttribute('data-clu-more'" not in js


def test_header_more_menu_still_uses_data_clu_more():
    # clu-page.js folds header actions into the menu by this attribute.
    assert "data-clu-more" in _read("templates/partials/page_header.html")
    assert "[data-clu-more]" in _read("static/js/clu-page.js")
