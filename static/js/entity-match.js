// Change match / Unmatch on the character, team and creator pages
// (templates/partials/match_modal.html, docs/browse-hub.md "Matching").
// Metron's search returns only names, so picking a row loads that one record;
// Use this match turns on once a record other than Current has loaded.
(function () {
    const modal = document.getElementById('matchModal');
    if (!modal) return;
    const d = modal.dataset;
    const mid = document.getElementById('matchMid');
    const form = document.getElementById('matchForm');
    const q = document.getElementById('matchQ');
    const use = document.getElementById('matchUse');
    const note = document.getElementById('matchNote');
    const phone = window.matchMedia('(max-width: 575.98px)');
    const st = { results: null, current: null, sel: null, loaded: null, records: {}, error: null, recError: null, loading: false, step: 'list', ran: false };
    let token = 0;

    const esc = CLU.escapeHtml;

    async function getJSON(url, opts) {
        let res;
        try { res = await fetch(url, opts); } catch (e) { return { reason: 'failed', error: 'Could not reach CLU.' }; }
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) return { reason: data.reason || 'failed', error: data.error || 'The request failed.' };
        return data;
    }

    function box(err, retry) {
        if (err.reason === 'quota')
            return `<div class="mt-box warn" role="status"><span>${esc(err.error)} The current match is kept.</span></div>`;
        if (err.reason === 'token')
            return `<div class="mt-box" role="status"><span>${esc(err.error)}.</span>${d.settingsUrl ? `<a class="btn btn-sm btn-outline-secondary" href="${esc(d.settingsUrl)}">Open Settings</a>` : ''}</div>`;
        return `<div class="mt-box" role="alert"><span>${esc(err.error)} The current match is kept.</span><button type="button" class="btn btn-sm btn-outline-secondary" data-retry="${retry}"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i> Retry</button></div>`;
    }

    function list() {
        const tab = st.sel ?? st.results[0].id;
        return `<ul class="mt-list" role="listbox" aria-label="Metron results">${st.results.map(r =>
            `<li role="presentation"><button type="button" class="mt-opt" role="option" data-pick="${r.id}" aria-selected="${st.sel === r.id}" tabindex="${r.id === tab ? 0 : -1}">
            <span class="mt-opt-t"><b>${esc(r.name)}</b><small>Metron ${r.id}</small></span>${st.current === r.id ? '<span class="mt-tag">Current</span>' : ''}</button></li>`).join('')}</ul>`;
    }

    function preview() {
        if (st.sel == null) return '<div class="mt-hint">Pick a result to see its Metron record.</div>';
        if (st.loading) return '<div class="mt-pv" aria-busy="true"><span class="mt-img mt-sk"></span><span class="mt-sk" style="width:60%"></span><span class="mt-sk" style="width:85%"></span><span class="mt-sk" style="width:70%"></span></div>';
        if (st.recError) return box({ ...st.recError, error: `Could not load Metron ${st.sel}: ${st.recError.error}` }, 'record');
        const r = st.records[st.sel];
        if (!r) return '';
        const rows = [['Universe', (r.universes || []).join(', ')], ['Created by', (r.creators || []).join(', ')],
            ['Aliases', (r.alias || []).join(', ')], ['Born', r.birth], ['Died', r.death]].filter(x => x[1]);
        return `<div class="mt-pv">
            ${r.image ? `<img class="mt-img" src="${esc(r.image)}" alt="">` : '<span class="mt-img" aria-hidden="true"></span>'}
            <h3>${esc(r.name)}</h3>
            <span class="mt-meta">Metron ${r.id} · ${r.has_cv ? 'has a ComicVine record' : 'no ComicVine record'}</span>
            ${r.url ? `<a class="small" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Open on Metron <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i><span class="visually-hidden"> (opens in a new tab)</span></a>` : ''}
            ${r.desc ? `<p class="mt-desc">${esc(r.desc)}</p>` : ''}
            ${rows.length ? `<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}</div>`;
    }

    function draw() {
        let html;
        if (st.loading && !st.results) html = '<p class="mt-hint" role="status">Searching Metron…</p>';
        else if (st.error) html = box(st.error, 'search');
        else if (!st.results) html = '';
        else if (!st.results.length) html = '';
        else if (phone.matches && st.step === 'pv' && st.sel != null)
            html = `<button type="button" class="btn btn-link mt-back" data-back><i class="bi bi-chevron-left" aria-hidden="true"></i> Back to results</button>${preview()}`;
        else html = phone.matches ? list() : `<div class="mt-cols">${list()}${preview()}</div>`;
        const listFocus = mid.contains(document.activeElement) && document.activeElement.classList.contains('mt-opt');
        mid.innerHTML = html;
        if (st.results && !st.results.length && !st.error) mid.appendChild(CLU.emptyState({
            compact: true, icon: 'bi-search', title: `No Metron ${d.noun}s match “${st.ran}”`,
            message: `Try another spelling${d.noun === 'character' ? ', or the character’s real name' : ''}.` }));
        if (listFocus) { const o = mid.querySelector('.mt-opt[tabindex="0"]'); if (o) o.focus(); }
        note.hidden = !!st.error;
        use.disabled = !(st.sel != null && st.sel !== st.current && st.loaded === st.sel && !st.loading && !st.recError);
    }

    async function search() {
        const term = q.value.trim();
        if (!term) { q.focus(); return; }
        const my = ++token;
        Object.assign(st, { results: null, error: null, sel: null, loaded: null, recError: null, loading: true, step: 'list', ran: term });
        draw();
        const data = await getJSON(`${d.searchUrl}?q=${encodeURIComponent(term)}`);
        if (my !== token) return;
        st.loading = false;
        if (data.error) { st.error = data; draw(); return; }
        st.results = data.results;
        st.current = data.current;
        if (data.current_record) st.records[data.current] = data.current_record;
        if (st.results.some(r => r.id === st.current)) pick(st.current, false);
        else { draw(); if (!st.results.length) q.focus(); }
    }

    async function pick(id, focus = true) {
        // The preselected Current row keeps the phone on the results list.
        st.sel = id; st.step = focus ? 'pv' : 'list'; st.recError = null;
        if (st.records[id]) { ++token; st.loading = false; st.loaded = id; draw(); return; }
        const my = ++token;
        st.loading = true; st.loaded = null; draw();
        const data = await getJSON(d.recordUrl.replace(/\/0$/, '/' + id));
        if (my !== token) return;
        st.loading = false;
        if (data.error) st.recError = data;
        else { st.records[id] = data.record; st.loaded = id; }
        draw();
        if (focus && phone.matches) { const back = mid.querySelector('[data-back]'); if (back) back.focus(); }
    }

    form.addEventListener('submit', e => { e.preventDefault(); search(); });
    mid.addEventListener('click', e => {
        const opt = e.target.closest('[data-pick]');
        if (opt) { pick(+opt.dataset.pick); return; }
        if (e.target.closest('[data-back]')) {
            st.step = 'list'; draw();
            const sel = mid.querySelector('.mt-opt[tabindex="0"]'); if (sel) sel.focus();
            return;
        }
        const retry = e.target.closest('[data-retry]');
        if (retry) retry.dataset.retry === 'record' ? pick(st.sel) : search();
    });
    mid.addEventListener('keydown', e => {
        const o = e.target.closest('.mt-opt');
        if (!o || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const opts = [...mid.querySelectorAll('.mt-opt')];
        const i = opts.indexOf(o);
        const next = opts[{ ArrowDown: Math.min(i + 1, opts.length - 1), ArrowUp: Math.max(i - 1, 0), Home: 0, End: opts.length - 1 }[e.key]];
        o.tabIndex = -1; next.tabIndex = 0; next.focus();
    });
    phone.addEventListener('change', draw);
    modal.addEventListener('shown.bs.modal', () => { q.focus(); if (!st.ran) search(); });

    use.addEventListener('click', async () => {
        use.disabled = true;
        const data = await getJSON(d.matchUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ metron_id: st.sel }) });
        if (data.error) { CLU.toast(data.error, 'error'); draw(); return; }
        location.reload();
    });

    // The menu item is hidden once the modal opens, so Bootstrap cannot refocus it.
    ['matchModal', 'unmatchModal'].forEach(id => {
        const m = document.getElementById(id);
        if (!m) return;
        let toggle = null;
        m.addEventListener('show.bs.modal', e => {
            const menu = e.relatedTarget && e.relatedTarget.closest('.dropdown-menu');
            toggle = menu ? menu.parentElement.querySelector('[data-bs-toggle="dropdown"]') : null;
        });
        m.addEventListener('hidden.bs.modal', () => { if (toggle && !document.hidden) toggle.focus(); });
    });

    const unmatch = document.getElementById('unmatchBtn');
    if (unmatch) unmatch.addEventListener('click', async () => {
        unmatch.disabled = true;
        const data = await getJSON(d.matchUrl, { method: 'DELETE' });
        if (data.error) { CLU.toast(data.error, 'error'); unmatch.disabled = false; return; }
        location.reload();
    });
})();
