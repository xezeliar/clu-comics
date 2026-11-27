/**
 * Series issue sheet (phones): a full-screen dialog over Home that swipes
 * through one series' issues, owned and missing, with the focused issue's
 * details, credits and actions below. Opened by collection.js
 * (openSeriesFromShelf) as window.CLUSeriesSheet.open(seriesId, openerEl).
 *
 * Native scroll-snap, no Swiper. The ground takes the focused cover's edge
 * colour (reader.js extractEdgeColor), so all text on it is fixed white.
 * Credits come from /api/dashboard/issue-info, fetched for the focused issue
 * only and cached per path. Feedback goes through CLU.toast.
 */
(function () {
    'use strict';

    const esc = (s) => CLU.escapeHtml(s == null ? '' : String(s));
    const $ = (id) => document.getElementById(id);
    const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const CREDIT_ROLES = [
        ['writer', 'Writer'], ['penciller', 'Penciller'], ['inker', 'Inker'],
        ['colorist', 'Colorist'], ['letterer', 'Letterer'],
        ['cover_artist', 'Cover artist'], ['editor', 'Editor'],
    ];

    let sheet, track, series = null, issues = [], idx = 0, opener = null;
    let pendingClose = null, infoTimer = null, raf = 0, token = 0;
    const infoCache = new Map();    // path -> Promise<issue-info payload | null>
    const savedCache = new Map();   // path -> bool
    const colourCache = new Map();  // path -> 'rgb(...)'
    const inertSaved = [];

    const num = (n) => (typeof stripIssueZeros === 'function' ? stripIssueZeros(String(n)) : String(n));

    function stateOf(it) {
        if (!it.owned) return 'miss';
        if (it.read) return 'read';
        if (it.page) return 'prog';
        return 'unread';
    }

    function fmtDate(d) {
        if (!d) return '';
        const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(d);
        if (!m) return String(d);
        const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3] || 1));
        return date.toLocaleDateString(undefined, m[3]
            ? { year: 'numeric', month: 'short', day: 'numeric' }
            : { year: 'numeric', month: 'short' });
    }

    // ---- open / close ------------------------------------------------------

    async function open(seriesId, openerEl) {
        init();
        const my = ++token;
        opener = openerEl || null;
        let data;
        try {
            const r = await fetch(`/api/dashboard/series/${encodeURIComponent(seriesId)}/issues`);
            data = await r.json();
        } catch (e) {
            data = null;
        }
        if (my !== token) return;
        if (!data || !data.success || !data.issues || !data.issues.length) {
            CLU.toast((data && data.error) || 'Could not load the issues of this series.', 'error');
            return;
        }
        series = data.series || { id: seriesId, name: '', monitored: false };
        issues = data.issues;
        idx = firstIndex();

        const img = opener && opener.querySelector('img.thumbnail');
        setColour(img ? sampleColour(img) : null);
        draw();
        info();

        sheet.classList.add('open');
        document.body.classList.add('series-sheet-open');
        for (const el of document.body.children) {
            if (el === sheet || el.id === 'toast-container') continue;
            inertSaved.push([el, el.inert]);
            el.inert = true;
        }
        // Back closes the sheet, so it owns one history entry (same URL).
        history.pushState({ ...(history.state || {}), seriesSheet: true }, '');
        requestAnimationFrame(() => {
            go(idx, false);
            scale();
            $('seriesSheetClose').focus({ preventScroll: true });
        });
        loadFocused();
    }

    /** Close; resolves once the sheet's history entry is gone too. */
    function close() {
        if (!sheet || !sheet.classList.contains('open')) return Promise.resolve();
        if (history.state && history.state.seriesSheet) {
            return new Promise((resolve) => {
                pendingClose = resolve;
                history.back();
            });
        }
        hide();
        return Promise.resolve();
    }

    function hide() {
        token++;
        sheet.classList.remove('open');
        document.body.classList.remove('series-sheet-open');
        while (inertSaved.length) {
            const [el, was] = inertSaved.pop();
            el.inert = was;
        }
        if (opener && document.contains(opener)) opener.focus({ preventScroll: true });
        if (pendingClose) { pendingClose(); pendingClose = null; }
    }

    function onPopState(event) {
        if (!sheet || !sheet.classList.contains('open')) return;
        // Leaving the sheet's own entry: close it and keep collection.js from
        // reloading the folder it never left.
        event.stopImmediatePropagation();
        hide();
    }

    // ---- carousel ------------------------------------------------------------

    function firstIndex() {
        const prog = issues.findIndex((it) => it.owned && !it.read && it.page);
        if (prog >= 0) return prog;
        const unread = issues.findIndex((it) => it.owned && !it.read);
        return unread >= 0 ? unread : 0;
    }

    function draw() {
        const n = issues.length;
        track.innerHTML = issues.map((it, i) => {
            const label = `Issue ${esc(num(it.number))}, ${i + 1} of ${n}`;
            const body = it.owned
                ? `<div class="ss-cover"><img loading="lazy" src="${esc(it.thumb_url || '')}" alt="" data-i="${i}"><span class="ss-num">#${esc(num(it.number))}</span></div>`
                : `<div class="ss-miss"><b>#${esc(num(it.number))}</b>Not in library</div>`;
            return `<div class="ss-sl" role="group" aria-roledescription="slide" aria-label="${label}">${body}</div>`;
        }).join('');
        track.querySelectorAll('img[data-i]').forEach((img) => {
            img.addEventListener('load', () => {
                const it = issues[Number(img.dataset.i)];
                if (!it || /\/(loading|error)\.svg/.test(img.currentSrc || img.src)) return;
                const c = sampleColour(img);
                if (c) colourCache.set(it.path, c);
                if (it === issues[idx] && c) setColour(c);
            });
            img.addEventListener('error', () => { img.src = CLU.staticUrl('images/error.svg'); }, { once: true });
        });
    }

    function scale() {
        if (reduced()) return;
        const mid = track.scrollLeft + track.clientWidth / 2;
        for (const el of track.children) {
            const d = Math.min(1, Math.abs(el.offsetLeft + el.offsetWidth / 2 - mid) / el.offsetWidth);
            el.style.transform = `scale(${1 - 0.18 * d})`;
            el.style.opacity = String(1 - 0.45 * d);
        }
    }

    function go(i, smooth = true) {
        const el = track.children[i];
        if (!el) return;
        track.scrollTo({
            left: el.offsetLeft + el.offsetWidth / 2 - track.clientWidth / 2,
            behavior: smooth && !reduced() ? 'smooth' : 'auto',
        });
    }

    function onScroll() {
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
            scale();
            const mid = track.scrollLeft + track.clientWidth / 2;
            let best = 0, bd = Infinity;
            Array.prototype.forEach.call(track.children, (el, i) => {
                const d = Math.abs(el.offsetLeft + el.offsetWidth / 2 - mid);
                if (d < bd) { bd = d; best = i; }
            });
            if (best !== idx) {
                idx = best;
                info();
                const c = colourCache.get(issues[idx].path);
                if (c) setColour(c);
                clearTimeout(infoTimer);
                infoTimer = setTimeout(loadFocused, 180);
            }
        });
    }

    // ---- colour ----------------------------------------------------------------

    function sampleColour(img) {
        if (typeof extractEdgeColor !== 'function' || !img.complete || !img.naturalWidth) return null;
        try {
            const c = extractEdgeColor(img);
            return `rgb(${c.r}, ${c.g}, ${c.b})`;
        } catch (e) {
            return null; // a tainted canvas: keep the current ground
        }
    }

    function setColour(c) {
        if (c) sheet.style.setProperty('--ss-c', c);
    }

    // ---- details -----------------------------------------------------------------

    function info() {
        const it = issues[idx];
        const st = stateOf(it);
        const n = num(it.number);
        $('seriesSheetTitle').textContent = series.name || '';
        $('seriesSheetPos').textContent = `${idx + 1} of ${issues.length}`;
        $('seriesSheetLine').style.width = `${((idx + 1) / issues.length) * 100}%`;
        $('seriesSheetPrev').disabled = idx === 0;
        $('seriesSheetNext').disabled = idx === issues.length - 1;

        const chip = {
            read: 'Read',
            prog: `Reading · p.${Number(it.page)}`,
            unread: 'Unread',
            miss: 'Not in library',
        }[st];
        const meta = it.path ? infoCache.get(it.path) : null;
        const extra = meta && meta.done ? meta.value : null;
        const title = (extra && extra.title) || it.title || '';
        const date = (extra && extra.date) || it.date || '';
        const summary = extra && extra.summary;
        const credits = extra && extra.credits
            ? CREDIT_ROLES.filter(([k]) => extra.credits[k]).map(([k, label]) =>
                `<div><dt>${label}</dt><dd>${esc(extra.credits[k])}</dd></div>`).join('')
            : '';

        let html = `<h3>Issue #${esc(n)}${title ? `: ${esc(title)}` : ''}</h3>`
            + `<div class="ss-meta">${date ? `<span>${esc(fmtDate(date))}</span>` : ''}`
            + `<span class="ss-chip" data-s="${st}">${chip}</span></div>`;
        if (summary) {
            html += `<p class="ss-desc" id="seriesSheetDesc">${esc(summary)}</p>`
                + '<button type="button" class="btn btn-link ss-more" id="seriesSheetMore" aria-expanded="false" aria-controls="seriesSheetDesc">More</button>';
        }
        if (it.owned) {
            if (!meta || !meta.done) html += '<p class="ss-wait">Loading credits…</p>';
            else if (credits) html += `<dl class="ss-cr">${credits}</dl><p class="ss-src">From ComicInfo.xml</p>`;
        }
        $('seriesSheetInfo').innerHTML = html;
        // Drop More when the summary fits in three lines.
        const desc = $('seriesSheetDesc');
        if (desc && desc.scrollHeight <= desc.clientHeight + 1) $('seriesSheetMore').hidden = true;

        actions(it, st);
    }

    function actions(it, st) {
        const read = $('seriesSheetRead');
        $('seriesSheetSecondary').hidden = st === 'miss';
        if (st === 'miss') {
            const wanted = series.monitored || it.wanted;
            read.innerHTML = `<i class="bi ${wanted ? 'bi-check2' : 'bi-plus-lg'}" aria-hidden="true"></i>${wanted ? 'On Wanted' : 'Add to Wanted'}`;
            read.disabled = !!wanted;
            return;
        }
        read.disabled = false;
        const label = st === 'prog' ? `Continue · p.${Number(it.page)}` : st === 'read' ? 'Read again' : 'Start Reading';
        read.innerHTML = `<i class="bi bi-book" aria-hidden="true"></i>${label}`;
        $('seriesSheetUnread').disabled = st !== 'read';
        const saved = savedCache.get(it.path) === true;
        const save = $('seriesSheetSave');
        save.setAttribute('aria-pressed', String(saved));
        save.querySelector('span').textContent = saved ? 'Saved' : 'Save';
        save.querySelector('i').className = `bi ${saved ? 'bi-bookmark-fill' : 'bi-bookmark'}`;
    }

    /** Lazily fetch the focused issue's ComicInfo and Want to Read state. */
    function loadFocused() {
        const it = issues[idx];
        if (!it || !it.owned || !it.path) return;
        const path = it.path;
        if (!infoCache.has(path)) {
            const entry = { done: false, value: null };
            infoCache.set(path, entry);
            fetch(`/api/dashboard/issue-info?path=${encodeURIComponent(path)}`)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null)
                .then((d) => {
                    entry.done = true;
                    entry.value = d && d.success ? d : null;
                    if (sheet.classList.contains('open') && issues[idx] && issues[idx].path === path) info();
                });
        }
        if (!savedCache.has(path)) {
            fetch(`/api/favorites/to-read/check?path=${encodeURIComponent(path)}`)
                .then((r) => r.json())
                .then((d) => {
                    savedCache.set(path, !!(d && d.is_to_read));
                    if (issues[idx] && issues[idx].path === path) actions(issues[idx], stateOf(issues[idx]));
                })
                .catch(() => {});
        }
    }

    // ---- actions --------------------------------------------------------------------

    async function onRead() {
        const it = issues[idx];
        if (!it.owned) return addToWanted(it);
        await close();
        if (typeof openReaderForFile === 'function') openReaderForFile(it.path);
    }

    async function addToWanted(it) {
        const btn = $('seriesSheetRead');
        btn.disabled = true;
        try {
            const r = await fetch(`/api/series/${encodeURIComponent(series.id)}/wanted-marks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ issue_numbers: [String(it.number)], wanted: true }),
            });
            const d = await r.json();
            if (!r.ok || !d.success) throw new Error(d.error || 'Failed');
            it.wanted = true;
            CLU.toast(`Issue #${num(it.number)} added to Wanted.`, 'success');
        } catch (e) {
            CLU.toast(`Could not add issue #${num(it.number)} to Wanted.`, 'error');
        }
        if (it === issues[idx]) actions(it, stateOf(it));
    }

    async function onUnread() {
        const it = issues[idx];
        const q = `?path=${encodeURIComponent(it.path)}`;
        try {
            let r = await fetch(`/api/dashboard/issue-read${q}`, { method: 'DELETE' });
            // Older server without the dashboard route: clear the bookmark only.
            if (r.status === 404 || r.status === 405) r = await fetch(`/api/reading-position${q}`, { method: 'DELETE' });
            const d = await r.json();
            if (!r.ok || !d.success) throw new Error('Failed');
            it.read = false;
            it.page = null;
            if (window._readerReadIssuesSet) window._readerReadIssuesSet.delete(it.path);
            if (typeof updateReadIcon === 'function') updateReadIcon(it.path, false);
            CLU.toast(`Issue #${num(it.number)} marked unread.`, 'success');
        } catch (e) {
            CLU.toast('Could not mark the issue unread.', 'error');
        }
        if (it === issues[idx]) info();
    }

    function onDownload() {
        const it = issues[idx];
        const a = document.createElement('a');
        a.href = `/api/download?path=${encodeURIComponent(it.path)}`;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    async function onSave() {
        const it = issues[idx];
        const saved = savedCache.get(it.path) === true;
        try {
            const r = await fetch('/api/favorites/to-read', {
                method: saved ? 'DELETE' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(saved ? { path: it.path } : { path: it.path, type: 'file' }),
            });
            const d = await r.json();
            if (!r.ok || !d.success) throw new Error('Failed');
            savedCache.set(it.path, !saved);
            CLU.toast(saved ? 'Removed from Want to Read.' : `Issue #${num(it.number)} saved to Want to Read.`, 'success');
        } catch (e) {
            CLU.toast('Could not update Want to Read.', 'error');
        }
        if (it === issues[idx]) actions(it, stateOf(it));
    }

    // ---- wiring ------------------------------------------------------------------------

    function init() {
        if (sheet) return;
        sheet = $('seriesSheet');
        track = $('seriesSheetTrack');
        // A direct child of <body>, so inerting the rest of the page leaves it live.
        document.body.appendChild(sheet);

        track.addEventListener('scroll', onScroll, { passive: true });
        sheet.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') { e.preventDefault(); go(Math.min(idx + 1, issues.length - 1)); }
            if (e.key === 'ArrowLeft') { e.preventDefault(); go(Math.max(idx - 1, 0)); }
        });
        $('seriesSheetPrev').addEventListener('click', () => go(idx - 1));
        $('seriesSheetNext').addEventListener('click', () => go(idx + 1));
        $('seriesSheetClose').addEventListener('click', () => close());
        $('seriesSheetRead').addEventListener('click', onRead);
        $('seriesSheetUnread').addEventListener('click', onUnread);
        $('seriesSheetDownload').addEventListener('click', onDownload);
        $('seriesSheetSave').addEventListener('click', onSave);
        $('seriesSheetInfo').addEventListener('click', (e) => {
            const more = e.target.closest('#seriesSheetMore');
            if (!more) return;
            const open = $('seriesSheetDesc').classList.toggle('open');
            more.textContent = open ? 'Less' : 'More';
            more.setAttribute('aria-expanded', String(open));
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && sheet.classList.contains('open')) {
                e.preventDefault();
                close();
            }
        });
        window.addEventListener('popstate', onPopState, true);
    }

    window.CLUSeriesSheet = { open: open, close: close };
})();
