/**
 * The Credited filter: one button that narrows a series folder's issues to
 * the ones a creator, character or team is tagged on (ComicInfo, read through
 * /api/credited, the same index the Creator/Character/Team pages use).
 * Used by the Collection folder view and the series page.
 *
 *   CLU.credited.parse(params)        -> {kind, name, role} | null, from
 *                                         credited=<kind>:<name>&role=<role>
 *   CLU.credited.write(params, value) sets or deletes those two params
 *   CLU.credited.picker(slot, {folder, total, value, onChange})
 *       Draws the button into `slot` and loads who is credited. onChange(value,
 *       paths) runs once the data arrives (when a value is set) and on every
 *       choice; paths is a Set of file paths, or null for Anyone. Returns
 *       {value()}. A role (only ever from the URL) narrows a creator to that
 *       credit; choosing in the picker means any role.
 */
(function () {
    'use strict';

    window.CLU = window.CLU || {};
    var KINDS = ['creator', 'character', 'team'];
    var GROUPS = { creator: 'Creators', character: 'Characters', team: 'Teams' };

    function parse(params) {
        var raw = params.get('credited') || '';
        var i = raw.indexOf(':');
        var kind = raw.slice(0, i);
        var name = raw.slice(i + 1).trim();
        if (i < 0 || KINDS.indexOf(kind) < 0 || !name) return null;
        return { kind: kind, name: name, role: kind === 'creator' ? (params.get('role') || '') : '' };
    }

    function write(params, value) {
        params.delete('credited');
        params.delete('role');
        if (!value) return;
        params.set('credited', value.kind + ':' + value.name);
        if (value.role) params.set('role', value.role);
    }

    function picker(slot, opts) {
        var value = opts.value || null;
        var people = null;
        var open = false;
        var q = '';

        function find(v) {
            if (!v || !people) return null;
            var key = (v.kind + ':' + v.name).toLowerCase();
            return people.find(function (p) { return p.key.toLowerCase() === key; }) || null;
        }
        function roleOf(p, v) {
            return p && v && v.role ? p.roles.find(function (r) { return r.kind === v.role; }) || null : null;
        }
        function paths() {
            if (!value) return null;
            var p = find(value);
            var r = roleOf(p, value);
            return new Set(r ? r.paths : p ? p.paths : []);
        }
        function label() {
            if (!value) return 'Credited: Anyone';
            var p = find(value);
            var r = roleOf(p, value);
            return '<b>' + CLU.escapeHtml(p ? p.name : value.name) + '</b>' + (r ? ' · ' + CLU.escapeHtml(r.label) : '');
        }

        function rows() {
            var term = q.trim().toLowerCase();
            var cur = find(value);
            var html = term ? '' : '<button type="button" class="clu-cred-opt" data-pick="" aria-pressed="' + !value + '">' +
                '<span class="n">Anyone</span><span class="c">' + opts.total + '</span></button>';
            KINDS.forEach(function (kind) {
                var hits = (people || []).filter(function (p) {
                    return p.kind === kind && (!term || p.name.toLowerCase().indexOf(term) >= 0);
                });
                if (!hits.length) return;
                html += '<h3>' + GROUPS[kind] + '</h3>';
                hits.forEach(function (p) {
                    var on = p === cur;
                    var r = on ? roleOf(p, value) : null;
                    var sub = r ? r.label + ' only' : p.roles.map(function (x) { return x.label; }).join(' · ');
                    html += '<button type="button" class="clu-cred-opt" data-pick="' + CLU.escapeHtml(p.key) + '" aria-pressed="' + on + '">' +
                        '<span class="n">' + CLU.escapeHtml(p.name) + '</span>' + (sub ? '<small>' + CLU.escapeHtml(sub) + '</small>' : '') +
                        '<span class="c">' + (r ? r.paths.length : p.paths.length) + '</span></button>';
                });
            });
            if (people === null) return '<p class="clu-cred-none" role="status">Loading…</p>';
            if (!people.length) return '<p class="clu-cred-none">No one is tagged in these issues’ ComicInfo yet.</p>' + html;
            if (term && html === '') return '<p class="clu-cred-none">No one named “' + CLU.escapeHtml(q) + '” is credited here.</p>';
            return html;
        }

        function render(focus) {
            slot.classList.toggle('on', !!value);
            slot.innerHTML =
                '<button type="button" class="btn btn-sm btn-outline-secondary clu-cred-btn" data-open aria-haspopup="dialog" aria-expanded="' + open + '"' +
                ' aria-label="' + CLU.escapeHtml(value ? 'Credited: ' + label().replace(/<[^>]+>/g, '') + '. Change' : 'Credited: Anyone. Choose who') + '">' +
                '<i class="bi bi-person" aria-hidden="true"></i><span class="v">' + label() + '</span><i class="bi bi-chevron-down" aria-hidden="true"></i></button>' +
                (value ? '<button type="button" class="btn btn-sm btn-outline-secondary clu-cred-x" data-clear aria-label="Clear Credited filter" title="Clear"><i class="bi bi-x-lg" aria-hidden="true"></i></button>' : '') +
                (open ? '<div class="clu-cred-scrim" aria-hidden="true"></div><div class="clu-cred-pop" role="dialog" aria-modal="true" aria-label="Credited">' +
                    '<div class="clu-cred-sh"><span>Credited</span><button type="button" class="btn btn-sm" data-close aria-label="Close"><i class="bi bi-x-lg" aria-hidden="true"></i></button></div>' +
                    '<input type="search" class="form-control form-control-sm clu-cred-q" data-q placeholder="Search creators, characters, teams…" aria-label="Search who is credited" value="' + CLU.escapeHtml(q) + '">' +
                    '<div class="clu-cred-list">' + rows() + '</div></div>' : '');
            if (focus) {
                var f = slot.querySelector(focus);
                if (f) f.focus();
            }
        }

        function close() { open = false; q = ''; render('[data-open]'); }
        function choose(v) {
            value = v;
            opts.onChange(value, paths());
        }

        slot.addEventListener('click', function (e) {
            if (e.target.closest('[data-open]')) { open = !open; q = ''; render(open ? '[data-q]' : '[data-open]'); return; }
            if (e.target.closest('[data-close]')) { close(); return; }
            if (e.target.closest('[data-clear]')) { choose(null); render('[data-open]'); return; }
            var pick = e.target.closest('[data-pick]');
            if (pick) {
                var p = find(pick.dataset.pick ? { kind: pick.dataset.pick.split(':')[0], name: pick.dataset.pick.slice(pick.dataset.pick.indexOf(':') + 1) } : null);
                choose(p ? { kind: p.kind, name: p.name, role: '' } : null);
                close();
                return;
            }
            // The phone sheet's scrim belongs to the picker, so a tap on it closes the
            // sheet instead of landing on the page underneath.
            if (e.target.closest('.clu-cred-scrim')) close();
        });
        slot.addEventListener('input', function (e) {
            if (!e.target.matches('[data-q]')) return;
            q = e.target.value;
            slot.querySelector('.clu-cred-list').innerHTML = rows();
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
                var opt = Array.prototype.slice.call(slot.querySelectorAll('[data-q], .clu-cred-opt'));
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

        render();
        fetch('/api/credited?folder=' + encodeURIComponent(opts.folder))
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!slot.isConnected) return;
                people = d.success ? d.people : [];
                render(open ? '[data-q]' : null);
                if (value) opts.onChange(value, paths());
            })
            .catch(function () {
                people = [];
                render();
                if (value) opts.onChange(value, paths());
            });

        return { value: function () { return value; } };
    }

    CLU.credited = { parse: parse, write: write, picker: picker };
})();
