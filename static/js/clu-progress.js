/**
 * Cover progress marks: a thin bar for a partly read issue, a dot for unread,
 * a tick for finished; a series (folder) cover shows read/owned as a bar.
 *
 * One module for the collection grid and the home shelves. Read state comes from
 * the same two endpoints the grid badge already uses (/api/issues-read-paths)
 * plus /api/reading-progress for partly read comics; series counts come from
 * /api/folder-read-progress. Marks never touch the issue badge's read icon.
 */
(function () {
    var CLU = window.CLU = window.CLU || {};
    var CARD = '.grid-item.has-comic[data-path], .dashboard-card.has-thumbnail[data-path]';
    var BOX = '.thumbnail-container, .dashboard-card-img-container';
    var readSet = new Set();
    var positions = {};
    var folders = {};
    var ready = null;

    function load() {
        if (!ready) {
            ready = Promise.all([
                fetch('/api/issues-read-paths').then(function (r) { return r.json(); }),
                fetch('/api/reading-progress').then(function (r) { return r.json(); })
            ]).then(function (res) {
                readSet = new Set(res[0].paths || []);
                positions = res[1].progress || {};
            }).catch(function () { /* marks are decoration: render without */ });
        }
        return ready;
    }

    function put(box, cls, pct, label) {
        box.querySelectorAll('.clu-prog').forEach(function (e) { e.remove(); });
        if (!cls) return;
        var el = document.createElement('div');
        el.className = 'clu-prog clu-prog-' + cls;
        if (label) el.title = label;
        if (cls === 'bar') {
            var fill = document.createElement('i');
            fill.style.width = pct + '%';
            el.appendChild(fill);
        } else if (cls === 'tick') {
            el.innerHTML = '<i class="bi bi-check-lg"></i>';
        }
        box.appendChild(el);
    }

    function markIssue(card) {
        var box = card.querySelector(BOX);
        // The Continue Reading shelf draws its own bar.
        if (!box || box.querySelector('.progress')) return;
        var path = card.dataset.path;
        if (readSet.has(path)) put(box, 'tick', 0, 'Finished');
        else if (positions[path] != null) put(box, 'bar', positions[path], positions[path] + '% read');
        else put(box, 'dot', 0, 'Unread');
    }

    function markSeries(card, p) {
        var box = card.querySelector(BOX);
        if (!box || !p || !p.total) return;
        var label = p.read + ' of ' + p.total + ' read';
        if (p.read >= p.total) put(box, 'tick', 0, label);
        else put(box, 'bar', Math.round(p.read / p.total * 100), label);
    }

    function apply(root) {
        if (!root) return Promise.resolve();
        return load().then(function () {
            root.querySelectorAll(CARD).forEach(markIssue);
            var pending = [];
            root.querySelectorAll('.grid-item.folder[data-path]').forEach(function (el) {
                if (folders[el.dataset.path]) markSeries(el, folders[el.dataset.path]);
                else pending.push(el);
            });
            if (!pending.length) return;
            return fetch('/api/folder-read-progress', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paths: pending.map(function (e) { return e.dataset.path; }) })
            }).then(function (r) { return r.json(); }).then(function (d) {
                Object.assign(folders, d.progress || {});
                pending.forEach(function (el) { markSeries(el, folders[el.dataset.path]); });
            });
        }).catch(function () { });
    }

    // The reader finished a comic: flip its marks, and let series counts refetch.
    function markRead(path) {
        readSet.add(path);
        delete positions[path];
        folders = {};
        document.querySelectorAll(CARD).forEach(function (c) {
            if (c.dataset.path === path) markIssue(c);
        });
    }

    CLU.progress = { apply: apply, markRead: markRead, load: load };
})();
