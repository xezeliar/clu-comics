/*
 * Set up series -- subscribe every series a reading list touches in one go.
 *
 * Two background steps on the server (core/series_setup.py), both polled at
 * /api/reading-lists/series-setup/<task_id>:
 *   resolve -- find each series on Metron; writes nothing. Fills the table.
 *   apply   -- subscribe the ticked series, then optionally track the list.
 *
 * Row states from the server: resolved (ticked), mapped (already on the Pull
 * List, never changed), choose (several Metron series share the name; the
 * user picks one), unresolved (nothing found).
 *
 * Every name and path reaching the DOM goes through CLU.escapeHtml.
 */
(function () {
    'use strict';

    const POLL_MS = 1500;
    const esc = (v) => CLU.escapeHtml(v == null ? '' : String(v));

    let listId = null;
    let modal = null;
    let busy = false;

    function el(id) { return document.getElementById(id); }

    function libraryPath() {
        const select = el('seriesSetupLibrary');
        const path = select ? select.value : (window._cluSeriesSetupDefaultLibrary || '/data');
        return (path || '').replace(/\/+$/, '');
    }

    function show(part) {
        el('seriesSetupProgress').classList.toggle('d-none', part !== 'progress');
        el('seriesSetupBody').classList.toggle('d-none', part !== 'table');
        el('seriesSetupResults').classList.toggle('d-none', part !== 'results');
    }

    function setProgress(text) {
        el('seriesSetupProgressText').textContent = text;
    }

    // Poll a setup task until it completes; resolves with its result.
    function poll(taskId, label) {
        return new Promise((resolve, reject) => {
            function check() {
                fetch(`/api/reading-lists/series-setup/${encodeURIComponent(taskId)}`)
                    .then(r => r.json())
                    .then(task => {
                        if (!task.success) { reject(new Error(task.message || 'Task not found')); return; }
                        if (task.status === 'complete') { resolve(task.result); return; }
                        if (task.status === 'error') { reject(new Error(task.message || 'Failed')); return; }
                        if (task.total) {
                            setProgress(`${label} ${task.processed} of ${task.total}` +
                                (task.message && task.processed ? ` — ${task.message}` : ''));
                        }
                        setTimeout(check, POLL_MS);
                    })
                    .catch(() => setTimeout(check, POLL_MS * 2));
            }
            check();
        });
    }

    function seriesLabel(s) {
        const year = s.year_began ? ` (${esc(s.year_began)})` : '';
        const extra = [s.publisher_name, s.status].filter(Boolean).map(esc).join(' · ');
        return `<div class="fw-semibold">${esc(s.name)}${year}</div>` +
            (extra ? `<div class="small text-muted">${extra}</div>` : '');
    }

    function issuesLabel(issues) {
        const shown = issues.slice(0, 8).map(n => '#' + esc(n)).join(', ');
        return issues.length > 8 ? `${shown} <span class="text-muted">+${issues.length - 8} more</span>` : shown;
    }

    const HOW = {
        issue: 'matched by issue id',
        comicvine: 'matched by ComicVine id',
        name: 'matched by name — check it',
    };

    function pathInput(row) {
        const rel = row.relative_path || '';
        const value = rel ? libraryPath() + rel : '';
        return `<input type="text" class="form-control form-control-sm series-setup-path"
            data-rel="${esc(rel)}" value="${esc(value)}" aria-label="Folder for ${esc(row.list_name)}"
            placeholder="Built from your folder pattern">`;
    }

    function renderRow(row) {
        const issues = issuesLabel(row.issues || []);
        const listName = esc(row.list_name) + (row.list_year ? ` (${esc(row.list_year)})` : '');

        if (row.state === 'resolved') {
            const how = row.how === 'name' ? 'text-warning' : 'text-muted';
            return `<tr data-series-id="${esc(row.series.series_id)}">
                <td><input class="form-check-input series-setup-tick" type="checkbox" checked
                    aria-label="Set up ${esc(row.series.name)}"></td>
                <td>${seriesLabel(row.series)}<div class="small ${how}">${esc(HOW[row.how] || '')}</div></td>
                <td class="small">${issues}</td>
                <td>${pathInput(row)}</td>
            </tr>`;
        }
        if (row.state === 'mapped') {
            return `<tr class="text-muted">
                <td><i class="bi bi-check-circle text-success" title="Already on your Pull List"></i></td>
                <td>${seriesLabel(row.series)}</td>
                <td class="small">${issues}</td>
                <td class="small">Already on your Pull List<div class="text-truncate">${esc(row.mapped_path || '')}</div></td>
            </tr>`;
        }
        if (row.state === 'choose') {
            // A candidate already on the Pull List is shown, but cannot be picked:
            // setting it up again would change nothing.
            const options = row.candidates.map(c =>
                `<option value="${esc(c.series_id)}"${c.mapped ? ' disabled' : ''}>${esc(c.name)}` +
                `${c.year_began ? ' (' + esc(c.year_began) + ')' : ''}` +
                `${c.issue_count ? ' — ' + esc(c.issue_count) + ' issues' : ''}` +
                `${c.mapped ? ' — already on your Pull List' : ''}</option>`).join('');
            return `<tr data-series-id="">
                <td><input class="form-check-input series-setup-tick" type="checkbox" disabled
                    aria-label="Set up ${listName}"></td>
                <td><div class="fw-semibold">${listName}</div>
                    <select class="form-select form-select-sm mt-1 series-setup-pick" aria-label="Which series is ${listName}?">
                        <option value="">Several series have this name — pick one…</option>${options}
                    </select></td>
                <td class="small">${issues}</td>
                <td>${pathInput(row)}</td>
            </tr>`;
        }
        return `<tr class="text-muted">
            <td><i class="bi bi-exclamation-triangle text-warning" title="Not found"></i></td>
            <td><div class="fw-semibold">${listName}</div>
                <div class="small">Not found on Metron. Subscribe to it from its series page.</div></td>
            <td class="small">${issues}</td>
            <td></td>
        </tr>`;
    }

    function selected() {
        return Array.from(el('seriesSetupRows').querySelectorAll('tr[data-series-id]'))
            .filter(tr => tr.dataset.seriesId && tr.querySelector('.series-setup-tick')?.checked)
            .map(tr => ({
                series_id: Number(tr.dataset.seriesId),
                path: (tr.querySelector('.series-setup-path')?.value || '').trim(),
            }));
    }

    function updateApplyButton() {
        const count = busy ? 0 : selected().length;
        const btn = el('seriesSetupApplyBtn');
        btn.disabled = count === 0;
        btn.querySelector('span').textContent = count ? `Set up ${count} series` : 'Set up';
    }

    function renderTable(rows) {
        const body = el('seriesSetupRows');
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="4" class="text-muted">This list has no series names to look up.</td></tr>';
        } else {
            body.innerHTML = rows.map(renderRow).join('');
        }
        show('table');
        updateApplyButton();
    }

    function renderResults(result) {
        const items = (result.series || []).map(r => {
            const icon = r.ok ? 'bi-check-circle text-success' : 'bi-x-circle text-danger';
            const what = r.ok ? esc(r.path) : esc(r.error || 'Failed');
            return `<li class="list-group-item d-flex gap-2">
                <i class="bi ${icon} mt-1" aria-hidden="true"></i>
                <div><div class="fw-semibold">${esc(r.name || ('Series ' + r.series_id))}</div>
                <div class="small text-muted text-break">${what}</div></div></li>`;
        }).join('');
        const done = (result.series || []).filter(r => r.ok).length;
        const how = result.monitored
            ? 'as <strong>monitored</strong>: every missing issue of these series is wanted.'
            : 'as <strong>Not monitored</strong>: only issues you want through this list are searched for.';
        const tracked = result.track_wanted
            ? '<p class="mb-2">This list is now tracked: its missing issues are on your Wanted page.</p>' : '';
        el('seriesSetupResults').innerHTML =
            `<p class="fw-semibold mb-2">${done} series set up ${how}</p>${tracked}<ul class="list-group">${items}</ul>`;
        show('results');
    }

    function onTableChange(event) {
        const target = event.target;
        if (target.classList.contains('series-setup-pick')) {
            const tr = target.closest('tr');
            tr.dataset.seriesId = target.value;
            const tick = tr.querySelector('.series-setup-tick');
            tick.disabled = !target.value;
            tick.checked = !!target.value;
        }
        if (target.classList.contains('series-setup-path')) {
            target.dataset.edited = '1';
        }
        updateApplyButton();
    }

    // A library change moves every folder the user has not edited.
    function onLibraryChange() {
        el('seriesSetupRows').querySelectorAll('.series-setup-path').forEach(input => {
            if (input.dataset.edited || !input.dataset.rel) return;
            input.value = libraryPath() + input.dataset.rel;
        });
    }

    function apply() {
        const choices = selected();
        if (!choices.length || busy) return;
        busy = true;
        updateApplyButton();
        setProgress('Setting up series…');
        show('progress');

        fetch(`/api/reading-lists/${listId}/series-setup/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                series: choices,
                monitored: el('seriesSetupMonitored').checked,
                track_wanted: el('seriesSetupTrackWanted').checked,
                library_path: libraryPath(),
            }),
        })
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.message || 'Could not start');
                return poll(data.task_id, 'Setting up');
            })
            .then(result => {
                renderResults(result);
                const btn = el('seriesSetupApplyBtn');
                btn.classList.add('d-none');
                el('seriesSetupCancelBtn').textContent = 'Close';
                // The Track Wanted button on the page reflects the new state after a reload.
                el('seriesSetupModal').addEventListener('hidden.bs.modal', () => window.location.reload(), { once: true });
            })
            .catch(err => {
                CLU.toast('Set up failed: ' + err.message, 'error', 10000);
                show('table');
            })
            .finally(() => { busy = false; updateApplyButton(); });
    }

    CLU.openSeriesSetup = function (id) {
        listId = id;
        busy = false;
        modal = modal || new bootstrap.Modal(el('seriesSetupModal'));
        el('seriesSetupRows').innerHTML = '';
        el('seriesSetupResults').innerHTML = '';
        el('seriesSetupApplyBtn').classList.remove('d-none');
        el('seriesSetupCancelBtn').textContent = 'Cancel';
        // Back to the defaults every time: a browser restores checkbox state on
        // reload, so a box ticked once could otherwise come back ticked unseen.
        el('seriesSetupMonitored').checked = false;
        el('seriesSetupTrackWanted').checked = true;
        setProgress('Finding series on Metron…');
        show('progress');
        updateApplyButton();
        modal.show();

        fetch(`/api/reading-lists/${id}/series-setup/resolve`, { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.message || 'Could not start');
                return poll(data.task_id, 'Looking up series');
            })
            .then(rows => renderTable(rows || []))
            .catch(err => {
                modal.hide();
                CLU.toast('Could not look up series: ' + err.message, 'error', 10000);
            });
    };

    document.addEventListener('DOMContentLoaded', () => {
        const rows = el('seriesSetupRows');
        if (!rows) return; // not a manager: no dialog on the page
        rows.addEventListener('change', onTableChange);
        rows.addEventListener('input', onTableChange);
        el('seriesSetupApplyBtn').addEventListener('click', apply);
        const library = el('seriesSetupLibrary');
        if (library) library.addEventListener('change', onLibraryChange);
    });
})();
