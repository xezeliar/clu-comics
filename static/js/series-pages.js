/**
 * series-pages.js: the Series page, a series' issue list and the issue page
 * (templates/series_index.html, series_issues.html, comic_issue.html).
 *
 * The server filters, sorts and pages; these pages change the query string
 * and reload. The scripts here are the controls that need more than a link:
 *
 *   CLU.seriesIndex({facetApi})   search, sort, letters, facet groups (their
 *                                 search boxes and "Show all"), pager, and
 *                                 "Tag N issues..." for an Untagged filter.
 *   CLU.seriesIssues({markApi})   search with #number jump, pager, Select mode
 *                                 (s / Esc, Shift-click ranges, a selection
 *                                 kept across pages), the bulk bar (Tag, Mark
 *                                 read/unread with Undo), and the cover's
 *                                 Edit ComicInfo button (i).
 *   CLU.comicIssue()              the issue page's actions and [ / ] keys.
 *
 * Bulk tagging goes through BulkMetadataReview.startJob, which shows progress
 * and the match review; nothing is written before the user picks a match.
 */
(function () {
    'use strict';

    window.CLU = window.CLU || {};

    function $(id) { return document.getElementById(id); }

    function plural(n, one, many) {
        return CLU.formatCount(n) + ' ' + (n === 1 ? one : many);
    }

    // The query string after `changes` (a value of '' or null removes a key;
    // an array replaces every value of a repeated key). Any change but `page`
    // itself goes back to page 1.
    function urlWith(changes) {
        var u = new URL(window.location.href);
        Object.keys(changes).forEach(function (k) {
            var v = changes[k];
            u.searchParams.delete(k);
            if (Array.isArray(v)) {
                v.forEach(function (x) { u.searchParams.append(k, x); });
            } else if (v !== '' && v != null) {
                u.searchParams.set(k, v);
            }
        });
        if (!('page' in changes)) u.searchParams.delete('page');
        return u.toString();
    }

    function go(changes) { window.location.href = urlWith(changes); }

    // Several onChange calls in one tick (Clear all) become one navigation.
    var pending = null;
    function goSoon(changes) {
        pending = Object.assign(pending || {}, changes);
        window.setTimeout(function () {
            if (!pending) return;
            var c = pending;
            pending = null;
            go(c);
        }, 0);
    }

    function typing(e) {
        var t = e.target;
        return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    }

    function modalOpen() {
        return !!document.querySelector('.modal.show, .offcanvas.show');
    }

    function wirePager(navId, onGo) {
        var nav = $(navId);
        if (!nav) return;
        var page = parseInt(nav.getAttribute('data-page'), 10) || 1;
        var pages = parseInt(nav.getAttribute('data-pages'), 10) || 1;
        if (pages < 2) return;
        nav.style.display = '';
        CLU.renderPageLinks(nav.querySelector('.pagination'), page, pages, onGo);
    }

    function wirePerPage(id) {
        var sel = $(id);
        if (sel) sel.addEventListener('change', function () { go({ per_page: sel.value }); });
    }

    function startTag(paths, overwrite, onDone) {
        if (!paths.length) return;
        if (!window.BulkMetadataReview || !BulkMetadataReview.startJob) {
            CLU.showError('Tagging failed to load. Refresh the page and try again.');
            return;
        }
        BulkMetadataReview.startJob({
            scope: 'files',
            paths: paths,
            overwrite_existing: !!overwrite,
            onDone: onDone || function () { window.location.reload(); }
        });
    }

    function postJson(url, method, body) {
        return fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (d) {
                if (!r.ok || d.success === false) throw new Error(d.error || ('Request failed (' + r.status + ')'));
                return d;
            });
        });
    }

    // ---------------------------------------------------------------------
    // The Series page
    // ---------------------------------------------------------------------

    var MULTI_PARAM = { creators: 'creator', characters: 'character', publishers: 'publisher' };
    var SINGLE_PARAM = { health: 'health', decade: 'decade', read: 'read', pull: 'pull' };

    CLU.seriesIndex = function (opts) {
        var o = opts || {};

        var search = $('seriesSearch');
        if (search) CLU.bindSearch(search, function (v) { go({ q: v }); });

        var sort = $('seriesSort');
        if (sort) sort.addEventListener('change', function () { go({ sort: sort.value === 'alpha' ? '' : sort.value }); });

        var letters = $('seriesLetters');
        if (letters) CLU.filterBar(letters, { toggleOff: true, onChange: function (v) { goSoon({ letter: v }); } });

        Object.keys(MULTI_PARAM).forEach(function (group) {
            var el = $('facet-' + group);
            if (!el) return;
            CLU.filterBar(el, { multi: true, onChange: function (values) {
                var change = {};
                change[MULTI_PARAM[group]] = values || [];
                goSoon(change);
            } });

            function render(params) {
                var u = new URL(o.facetApi, window.location.origin);
                new URL(window.location.href).searchParams.forEach(function (v, k) { u.searchParams.append(k, v); });
                u.searchParams.set('group', group);
                Object.keys(params).forEach(function (k) { u.searchParams.set(k, params[k]); });
                return fetch(u.toString()).then(function (r) { return r.json(); }).then(function (d) {
                    if (!d.success) throw new Error(d.error || 'Could not load the list');
                    var active = d.items.filter(function (i) { return i.checked; }).map(function (i) { return i.value; });
                    CLU.renderFilterOptions(el, d.items.map(function (i) {
                        return { value: i.value, label: i.value, count: i.count };
                    }), active);
                    return d;
                }).catch(function (err) { CLU.showError(err.message); });
            }

            var box = $('facetSearch-' + group);
            if (box) CLU.bindSearch(box, function (v) { render({ fq: v }); });

            var all = document.querySelector('[data-sp-show-all="' + group + '"]');
            if (all) all.addEventListener('click', function () {
                render({ all: '1' }).then(function () {
                    el.classList.add('sp-scroll');
                    el.style.maxHeight = '16rem';
                    el.style.overflow = 'auto';
                    all.hidden = true;
                });
            });
        });

        Object.keys(SINGLE_PARAM).forEach(function (key) {
            var el = $('facet-' + key);
            if (!el) return;
            CLU.filterBar(el, { toggleOff: true, onChange: function (v) {
                var change = {};
                change[SINGLE_PARAM[key]] = v || '';
                goSoon(change);
            } });
        });

        wirePager('seriesPager', function (p) { go({ page: p > 1 ? String(p) : '' }); });
        wirePerPage('seriesPerPage');

        var tagAll = $('seriesTagAll');
        if (tagAll) tagAll.addEventListener('click', function () {
            var paths = [];
            try { paths = JSON.parse(tagAll.getAttribute('data-paths') || '[]'); } catch (e) { paths = []; }
            startTag(paths, false);
        });
    };

    // ---------------------------------------------------------------------
    // A series' issue list
    // ---------------------------------------------------------------------

    CLU.seriesIssues = function (opts) {
        var o = opts || {};
        var root = $('issuesRoot');
        if (!root) return;
        var owner = root.getAttribute('data-owner') === 'true';
        var storeKey = 'clu-series-sel:' + root.getAttribute('data-series');
        var matching = [];
        try { matching = JSON.parse(root.getAttribute('data-matching') || '[]'); } catch (e) { matching = []; }

        var search = $('issuesSearch');
        var startQ = search ? search.value.trim() : '';
        if (search) {
            CLU.bindSearch(search, function (v) { go({ q: v }); });
            search.addEventListener('keydown', function (e) {
                if (e.key !== 'Enter' || search.value.trim() !== startQ || !startQ) return;
                var cards = root.querySelectorAll('.sp-card[data-path] a[href]');
                if (cards.length === 1) window.location.href = cards[0].getAttribute('href');
            });
        }
        wirePager('issuesPager', function (p) { go({ page: p > 1 ? String(p) : '' }); });
        wirePerPage('issuesPerPage');

        // ---- Select mode ----
        var selected = new Set();
        try {
            JSON.parse(sessionStorage.getItem(storeKey) || '[]').forEach(function (p) { selected.add(p); });
        } catch (e) { /* storage blocked: the selection lives for this page only */ }
        var selecting = selected.size > 0;
        var lastIndex = null;

        function cards() { return Array.prototype.slice.call(root.querySelectorAll('.sp-card[data-path]')); }
        function onPage() { return cards().map(function (c) { return c.getAttribute('data-path'); }); }

        function save() {
            try { sessionStorage.setItem(storeKey, JSON.stringify(Array.from(selected))); } catch (e) { /* ignore */ }
        }

        function paint() {
            root.classList.toggle('is-selecting', selecting);
            root.querySelectorAll('.sp-sel-col').forEach(function (c) { c.hidden = !selecting; });
            cards().forEach(function (c) {
                var on = selected.has(c.getAttribute('data-path'));
                c.classList.toggle('is-selected', on);
                var box = c.querySelector('.sp-pick, .sp-pick-row');
                if (box) {
                    box.checked = on;
                    box.tabIndex = selecting ? 0 : -1;
                }
            });
            var bar = $('issuesBulk');
            if (!bar) return;
            bar.hidden = !selecting;
            var n = selected.size;
            var here = onPage();
            var hidden = Array.from(selected).filter(function (p) { return here.indexOf(p) === -1; }).length;
            $('issuesBulkCount').textContent = plural(n, 'issue', 'issues') + ' selected';
            $('issuesBulkHidden').hidden = !hidden;
            $('issuesBulkHidden').textContent = '· ' + CLU.formatCount(hidden) + ' not on this page';
            var allIn = matching.length && matching.every(function (p) { return selected.has(p); });
            $('issuesSelectAll').hidden = !matching.length || allIn;
            $('issuesClearSel').hidden = !n;
            $('issuesBulkEmpty').hidden = !!n;
            ['issuesBulkTag', 'issuesBulkRead', 'issuesBulkUnread'].forEach(function (id) {
                if ($(id)) $(id).hidden = !n;
            });
        }

        function setSelecting(on) {
            selecting = on;
            if (!on) { selected.clear(); save(); }
            paint();
        }

        function toggle(card, shift) {
            var list = cards();
            var idx = list.indexOf(card);
            var path = card.getAttribute('data-path');
            var on = !selected.has(path);
            if (shift && lastIndex !== null && lastIndex !== idx) {
                var a = Math.min(lastIndex, idx), b = Math.max(lastIndex, idx);
                list.slice(a, b + 1).forEach(function (c) {
                    var p = c.getAttribute('data-path');
                    if (on) selected.add(p); else selected.delete(p);
                });
            } else if (on) {
                selected.add(path);
            } else {
                selected.delete(path);
            }
            lastIndex = idx;
            save();
            paint();
        }

        root.addEventListener('click', function (e) {
            if (!selecting) return;
            var box = e.target.closest('.sp-pick, .sp-pick-row');
            if (!box) return;
            e.preventDefault();
            toggle(box.closest('.sp-card'), e.shiftKey);
        });
        root.addEventListener('keydown', function (e) {
            var box = e.target.closest && e.target.closest('.sp-pick, .sp-pick-row');
            if (box && (e.key === ' ' || e.key === 'Enter')) {
                e.preventDefault();
                toggle(box.closest('.sp-card'), e.shiftKey);
            }
        });

        var selBtn = $('issuesSelectBtn');
        if (selBtn) selBtn.addEventListener('click', function () { setSelecting(!selecting); });
        if ($('issuesBulkDone')) $('issuesBulkDone').addEventListener('click', function () { setSelecting(false); });
        if ($('issuesClearSel')) $('issuesClearSel').addEventListener('click', function () {
            selected.clear(); save(); paint();
        });
        if ($('issuesSelectAll')) $('issuesSelectAll').addEventListener('click', function () {
            matching.forEach(function (p) { selected.add(p); });
            save(); paint();
        });

        // ---- Bulk actions ----
        function names(paths) {
            var shown = paths.slice(0, 8).map(function (p) { return p.split(/[\\/]/).pop(); });
            return shown.join(', ') + (paths.length > 8 ? ' and ' + CLU.formatCount(paths.length - 8) + ' more' : '');
        }

        function markRead(read, paths) {
            return postJson(o.markApi, 'POST', { paths: paths, read: read }).then(function (d) {
                var changed = d.changed || [];
                changed.forEach(function (p) {
                    var card = root.querySelector('.sp-card[data-path="' + CSS.escape(p) + '"]');
                    var num = card && card.querySelector('.sp-num');
                    if (num) num.classList.toggle('is-read', read);
                });
                var already = paths.length - changed.length;
                var msg = changed.length
                    ? 'Marked ' + plural(changed.length, 'issue', 'issues') + (read ? ' read' : ' unread')
                    : 'Nothing changed';
                if (already) msg += ' · ' + CLU.formatCount(already) + ' already ' + (read ? 'read' : 'unread');
                CLU.toast(msg, changed.length ? 'success' : 'info', changed.length ? {
                    duration: 10000,
                    action: { label: 'Undo', onClick: function () {
                        markRead(!read, changed).then(function () { CLU.toast('Undone', 'info'); });
                    } }
                } : undefined);
            }).catch(function (err) { CLU.showError(err.message); });
        }

        function confirmThen(title, body, hiddenPaths, goLabel, run) {
            var modalEl = $('issuesConfirmModal');
            $('issuesConfirmTitle').textContent = title;
            $('issuesConfirmBody').textContent = body;
            $('issuesConfirmHidden').textContent = hiddenPaths.length ? 'Not on this page: ' + names(hiddenPaths) : '';
            var goBtn = $('issuesConfirmGo');
            goBtn.textContent = goLabel;
            var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            goBtn.onclick = function () { modal.hide(); run(); };
            modal.show();
        }

        function bulkRead(read) {
            var paths = Array.from(selected);
            if (!paths.length) return;
            var here = onPage();
            var hidden = paths.filter(function (p) { return here.indexOf(p) === -1; });
            if (hidden.length || paths.length > 20) {
                confirmThen(
                    'Mark ' + plural(paths.length, 'issue', 'issues') + (read ? ' read?' : ' unread?'),
                    'Issues already ' + (read ? 'read' : 'unread') + ' are left as they are. You can undo this from the message that follows.',
                    hidden, read ? 'Mark read' : 'Mark unread', function () { markRead(read, paths); });
            } else {
                markRead(read, paths);
            }
        }

        if ($('issuesBulkRead')) $('issuesBulkRead').addEventListener('click', function () { bulkRead(true); });
        if ($('issuesBulkUnread')) $('issuesBulkUnread').addEventListener('click', function () { bulkRead(false); });
        if ($('issuesBulkTag')) $('issuesBulkTag').addEventListener('click', function () {
            startTag(Array.from(selected), true, function () { setSelecting(false); window.location.reload(); });
        });
        var tagUntagged = $('issuesTagUntagged');
        if (tagUntagged) tagUntagged.addEventListener('click', function () {
            var paths = [];
            try { paths = JSON.parse(root.getAttribute('data-untagged') || '[]'); } catch (e) { paths = []; }
            startTag(paths, false);
        });

        // ---- Edit ComicInfo (the cover's i button, the table's, or the i key) ----
        function openInfo(card) {
            if (!owner || !card || !CLU.showCBZInfo) return;
            var path = card.getAttribute('data-path');
            var name = card.getAttribute('data-name');
            var dir = path.slice(0, Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\')));
            var siblings = cards().filter(function (c) {
                var p = c.getAttribute('data-path');
                return p.slice(0, Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'))) === dir;
            }).map(function (c) { return c.getAttribute('data-name'); });
            CLU.showCBZInfo(path, name, { directoryPath: dir, fileList: siblings });
        }
        window._cluCbzInfo = {
            onMetadataSaved: function () { window.location.reload(); },
            onClearComplete: function () { window.location.reload(); }
        };
        root.addEventListener('click', function (e) {
            var btn = e.target.closest('.sp-open-info');
            if (!btn) return;
            e.preventDefault();
            openInfo(btn.closest('.sp-card'));
        });

        document.addEventListener('keydown', function (e) {
            if (typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;
            if (e.key === 'Escape' && selecting && !modalOpen()) { setSelecting(false); return; }
            if (modalOpen()) return;
            if (e.key === 's') { e.preventDefault(); setSelecting(!selecting); }
            else if (e.key === 'i' && owner) {
                var card = document.activeElement && document.activeElement.closest && document.activeElement.closest('.sp-card[data-path]');
                if (card) { e.preventDefault(); openInfo(card); }
            }
        });

        paint();
    };

    // ---------------------------------------------------------------------
    // The issue page
    // ---------------------------------------------------------------------

    CLU.comicIssue = function () {
        var root = $('issueRoot');
        if (!root) return;
        var path = root.getAttribute('data-path');
        var name = root.getAttribute('data-name');

        var read = $('issueRead');
        if (read) read.addEventListener('click', function () {
            if (typeof window.openComicReader !== 'function') {
                CLU.showError('The reader failed to load. Refresh the page and try again.');
                return;
            }
            window.openComicReader(path);
        });

        var mark = $('issueMarkRead');
        if (mark) mark.addEventListener('click', function () {
            var on = mark.getAttribute('aria-pressed') === 'true';
            postJson('/api/favorites/issues', on ? 'DELETE' : 'POST', { path: path }).then(function () {
                mark.setAttribute('aria-pressed', on ? 'false' : 'true');
                CLU.toast(on ? 'Marked unread' : 'Marked read', 'success');
            }).catch(function (err) { CLU.showError(err.message); });
        });

        function wantToggle(btn, labelEl) {
            if (!btn) return;
            btn.addEventListener('click', function () {
                var on = btn.getAttribute('aria-pressed') === 'true' ||
                    (labelEl && labelEl.textContent.indexOf('Remove') === 0);
                postJson('/api/favorites/to-read', on ? 'DELETE' : 'POST', { path: path, type: 'file' }).then(function () {
                    if (btn.hasAttribute('aria-pressed')) btn.setAttribute('aria-pressed', on ? 'false' : 'true');
                    if (labelEl) labelEl.textContent = on ? 'Want to Read' : 'Remove from Want to Read';
                    CLU.toast(on ? 'Removed from Want to Read' : 'Added to Want to Read', 'success');
                }).catch(function (err) { CLU.showError(err.message); });
            });
        }
        wantToggle($('issueWant'));
        var wantMenu = $('issueWantMenu');
        wantToggle(wantMenu, wantMenu && wantMenu.querySelector('span'));

        window._cluCbzInfo = {
            onMetadataSaved: function () { window.location.reload(); },
            onClearComplete: function () { window.location.reload(); }
        };
        var edit = $('issueEditInfo');
        if (edit) edit.addEventListener('click', function () {
            if (CLU.showCBZInfo) CLU.showCBZInfo(path, name);
        });
        ['issueTag', 'issueRetag'].forEach(function (id) {
            var b = $(id);
            if (b) b.addEventListener('click', function () { startTag([path], true); });
        });

        var copy = $('issueCopyPath');
        if (copy) copy.addEventListener('click', function () {
            if (!navigator.clipboard) { CLU.showError('Copying needs a secure (https) page.'); return; }
            navigator.clipboard.writeText(path).then(function () { CLU.toast('Path copied', 'success'); },
                function () { CLU.showError('Could not copy the path.'); });
        });

        var showEmpty = $('issueShowEmpty');
        if (showEmpty) showEmpty.addEventListener('change', function () {
            $('issueFields').classList.toggle('show-empty', showEmpty.checked);
        });

        var prev = root.getAttribute('data-prev'), next = root.getAttribute('data-next');
        document.addEventListener('keydown', function (e) {
            if (typing(e) || modalOpen() || e.ctrlKey || e.metaKey || e.altKey) return;
            if (e.key === '[' && prev) window.location.href = prev;
            else if (e.key === ']' && next) window.location.href = next;
        });
    };
})();
