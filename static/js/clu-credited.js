/**
 * The Credited filters: one drill-down filter per credit role (Writer,
 * Penciller, ... Editor), then Characters and Teams, narrowing a series
 * folder's issues to the ones tagged in ComicInfo (read through /api/credited,
 * the same index the Creator/Character/Team pages use). Filters combine with
 * AND, and each menu lists only who is on the issues the other filters leave,
 * with counts recomputed. Used by the Collection folder view and the series page.
 *
 *   CLU.credited.parse(params)        -> {writer: 'Name', character: 'Name', ...} | null
 *   CLU.credited.write(params, value) sets or deletes the filter params
 *   CLU.credited.picker(slot, {folder, total, value, onChange})
 *       Draws the filters into `slot` and loads who is credited. onChange(value,
 *       paths) runs once the data arrives (when a value is set) and on every
 *       choice; paths is a Set of file paths, or null when nothing is set.
 *
 * URL: one param per filter (?writer=Mara Quell&character=Nadia Cross).
 * `creator=` means a creator in any role (an entity page with no Role chosen);
 * it shows as its own filter only while set. The old credited=<kind>:<name>
 * (&role=) form is still read.
 */
(function () {
    'use strict';

    window.CLU = window.CLU || {};
    var ROLES = ['writer', 'penciller', 'inker', 'colorist', 'letterer', 'coverartist', 'editor', 'translator'];
    var FACETS = ROLES.concat(['creator', 'character', 'team']);
    var LABELS = {
        writer: 'Writer', penciller: 'Penciller', inker: 'Inker', colorist: 'Colorist',
        letterer: 'Letterer', coverartist: 'Cover artist', editor: 'Editor', translator: 'Translator',
        creator: 'Creator', character: 'Character', team: 'Team'
    };
    var PLURAL = { character: 'Characters', team: 'Teams' };

    function parse(params) {
        var v = {};
        FACETS.forEach(function (f) {
            var n = (params.get(f) || '').trim();
            if (n) v[f] = n;
        });
        var raw = params.get('credited') || '';
        var i = raw.indexOf(':');
        var kind = raw.slice(0, i), name = raw.slice(i + 1).trim();
        if (i > 0 && name) {
            var role = params.get('role') || '';
            if (kind === 'creator' && ROLES.indexOf(role) >= 0) v[role] = v[role] || name;
            else if (kind === 'creator' || kind === 'character' || kind === 'team') v[kind] = v[kind] || name;
        }
        return Object.keys(v).length ? v : null;
    }

    function write(params, value) {
        FACETS.concat(['credited', 'role']).forEach(function (f) { params.delete(f); });
        if (!value) return;
        FACETS.forEach(function (f) { if (value[f]) params.set(f, value[f]); });
    }

    function picker(slot, opts) {
        var value = opts.value ? Object.assign({}, opts.value) : {};
        var people = null;
        var open = '';
        var q = '';

        function kindOf(f) { return f === 'character' || f === 'team' ? f : 'creator'; }
        function same(a, b) { return a.toLowerCase() === b.toLowerCase(); }
        function pathsFor(p, f) {
            if (f === 'creator' || f === 'character' || f === 'team') return p.paths;
            var r = p.roles.find(function (x) { return x.kind === f; });
            return r ? r.paths : [];
        }
        function find(f, name) {
            return (people || []).find(function (p) { return p.kind === kindOf(f) && same(p.name, name); }) || null;
        }
        // Who can be picked for facet f, with their paths in it.
        function members(f) {
            return (people || []).filter(function (p) { return p.kind === kindOf(f) && pathsFor(p, f).length; });
        }
        // Issues left by every set filter except `skip` (null = no narrowing).
        function narrowed(skip) {
            var out = null;
            Object.keys(value).forEach(function (f) {
                if (f === skip) return;
                var p = find(f, value[f]);
                var s = new Set(p ? pathsFor(p, f) : []);
                out = out ? new Set(Array.from(out).filter(function (x) { return s.has(x); })) : s;
            });
            return out;
        }
        function paths() { return Object.keys(value).length ? narrowed(null) : null; }
        function visible() {
            if (!people) return FACETS.filter(function (f) { return value[f]; });
            return FACETS.filter(function (f) { return value[f] || (f !== 'creator' && members(f).length); });
        }

        function rows(f) {
            if (people === null) return '<p class="clu-cred-none" role="status">Loading…</p>';
            var term = q.trim().toLowerCase();
            var left = narrowed(f);
            var list = members(f).map(function (p) {
                var own = pathsFor(p, f);
                return { p: p, n: left ? own.filter(function (x) { return left.has(x); }).length : own.length };
            }).filter(function (x) { return !term || x.p.name.toLowerCase().indexOf(term) >= 0; })
              .sort(function (a, b) { return b.n - a.n || a.p.name.localeCompare(b.p.name); });
            var html = term ? '' : '<button type="button" class="clu-cred-opt" data-pick="" aria-pressed="' + !value[f] + '">' +
                '<span class="n">Anyone</span><span class="c">' + (left ? left.size : opts.total) + '</span></button>';
            list.forEach(function (x) {
                var on = !!value[f] && same(value[f], x.p.name);
                // Nobody drops out of the menu when the other filters exclude them:
                // they stay, greyed, so the list does not jump.
                var off = !x.n && !on;
                html += '<button type="button" class="clu-cred-opt' + (off ? ' zero' : '') + '" data-pick="' + CLU.escapeHtml(x.p.name) + '" aria-pressed="' + on + '"' +
                    (off ? ' aria-disabled="true"' : '') + '><span class="n">' + CLU.escapeHtml(x.p.name) + '</span>' +
                    '<span class="c">' + x.n + '</span></button>';
            });
            if (term && !list.length) return '<p class="clu-cred-none">No one named “' + CLU.escapeHtml(q) + '” here.</p>';
            return html;
        }

        function facet(f) {
            var set = !!value[f];
            var name = set ? (find(f, value[f]) || { name: value[f] }).name : '';
            var label = LABELS[f];
            var plural = PLURAL[f] || label + 's';
            return '<div class="clu-cred-f' + (set ? ' on' : '') + '" data-f="' + f + '">' +
                '<button type="button" class="btn btn-sm btn-outline-secondary clu-cred-btn" data-open="' + f + '" aria-haspopup="dialog" aria-expanded="' + (open === f) + '"' +
                ' aria-label="' + CLU.escapeHtml(set ? label + ': ' + name + '. Change' : plural + ': anyone. Choose') + '">' +
                '<span class="v">' + (set ? CLU.escapeHtml(label) + ': <b>' + CLU.escapeHtml(name) + '</b>' : CLU.escapeHtml(plural)) + '</span>' +
                '<i class="bi bi-chevron-down" aria-hidden="true"></i></button>' +
                (set ? '<button type="button" class="btn btn-sm btn-outline-secondary clu-cred-x" data-clear="' + f + '" aria-label="Clear ' + CLU.escapeHtml(label) + ' filter" title="Clear"><i class="bi bi-x-lg" aria-hidden="true"></i></button>' : '') +
                (open === f ? '<div class="clu-cred-scrim" aria-hidden="true"></div><div class="clu-cred-pop" role="dialog" aria-modal="true" aria-label="' + CLU.escapeHtml(plural) + '">' +
                    '<div class="clu-cred-sh"><span>' + CLU.escapeHtml(plural) + '</span><button type="button" class="btn btn-sm" data-close aria-label="Close"><i class="bi bi-x-lg" aria-hidden="true"></i></button></div>' +
                    '<input type="search" class="form-control form-control-sm clu-cred-q" data-q placeholder="Search ' + CLU.escapeHtml(plural.toLowerCase()) + '…" aria-label="Search ' + CLU.escapeHtml(plural.toLowerCase()) + '" value="' + CLU.escapeHtml(q) + '">' +
                    '<div class="clu-cred-list">' + rows(f) + '</div></div>' : '') +
                '</div>';
        }

        function render(focus) {
            var fs = visible();
            var n = Object.keys(value).length;
            slot.classList.toggle('on', n > 0);
            slot.innerHTML = (people && !people.length && !n)
                ? '<span class="clu-cred-none-inline">No credits in these issues’ ComicInfo</span>'
                : fs.map(facet).join('') + (n > 1 ? '<button type="button" class="btn btn-link btn-sm clu-cred-all" data-clearall>Clear all</button>' : '');
            // A filter near the right edge opens its menu leftwards (phones use the bottom sheet).
            var pop = slot.querySelector('.clu-cred-pop');
            if (pop && getComputedStyle(pop).position === 'absolute' &&
                pop.getBoundingClientRect().right > document.documentElement.clientWidth - 8) pop.classList.add('end');
            if (focus) {
                var el = slot.querySelector(focus);
                if (el) el.focus();
            }
        }

        function close() { var f = open; open = ''; q = ''; render(f ? '[data-open="' + f + '"]' : null); }
        function changed(focus) {
            render(focus);
            opts.onChange(Object.keys(value).length ? Object.assign({}, value) : null, paths());
        }

        slot.addEventListener('click', function (e) {
            var o = e.target.closest('[data-open]');
            if (o) { var f = o.dataset.open; open = open === f ? '' : f; q = ''; render(open ? '[data-q]' : '[data-open="' + f + '"]'); return; }
            if (e.target.closest('[data-close]')) { close(); return; }
            var c = e.target.closest('[data-clear]');
            if (c) { delete value[c.dataset.clear]; changed('.clu-cred-btn'); return; }
            if (e.target.closest('[data-clearall]')) { value = {}; changed('.clu-cred-btn'); return; }
            var pick = e.target.closest('[data-pick]');
            if (pick) {
                if (pick.getAttribute('aria-disabled') === 'true') return;
                var g = open;
                open = ''; q = '';
                if (pick.dataset.pick) value[g] = pick.dataset.pick; else delete value[g];
                changed('[data-open="' + g + '"]');
                return;
            }
            // The phone sheet's scrim belongs to the filter, so a tap on it closes the
            // sheet instead of landing on the page underneath.
            if (e.target.closest('.clu-cred-scrim')) close();
        });
        slot.addEventListener('input', function (e) {
            if (!e.target.matches('[data-q]')) return;
            q = e.target.value;
            slot.querySelector('.clu-cred-list').innerHTML = rows(open);
        });
        slot.addEventListener('keydown', function (e) {
            if (!open) return;
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return; }
            var items = Array.prototype.slice.call(slot.querySelectorAll('.clu-cred-pop [data-q], .clu-cred-pop button'))
                .filter(function (x) { return x.offsetParent; });
            var i = items.indexOf(document.activeElement);
            if (e.key === 'Tab' && items.length) {
                if (e.shiftKey && i === 0) { e.preventDefault(); items[items.length - 1].focus(); }
                else if (!e.shiftKey && i === items.length - 1) { e.preventDefault(); items[0].focus(); }
            } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                var opt = Array.prototype.slice.call(slot.querySelectorAll('.clu-cred-pop [data-q], .clu-cred-opt'));
                var j = opt.indexOf(document.activeElement) + (e.key === 'ArrowDown' ? 1 : -1);
                var n = opt[Math.max(0, Math.min(opt.length - 1, j))];
                if (n) { e.preventDefault(); n.focus(); }
            }
        });
        function outside(e) {
            if (!slot.isConnected) { document.removeEventListener('pointerdown', outside); return; }
            if (open && !slot.contains(e.target)) close();
        }
        document.addEventListener('pointerdown', outside);

        function loaded(list) {
            if (!slot.isConnected) return;
            people = list;
            render(open ? '[data-q]' : null);
            if (Object.keys(value).length) opts.onChange(Object.assign({}, value), paths());
        }
        render();
        fetch('/api/credited?folder=' + encodeURIComponent(opts.folder))
            .then(function (r) { return r.json(); })
            .then(function (d) { loaded(d.success ? d.people : []); })
            .catch(function () { loaded([]); });

        return { value: function () { return Object.keys(value).length ? Object.assign({}, value) : null; } };
    }

    CLU.credited = { parse: parse, write: write, picker: picker };
})();
