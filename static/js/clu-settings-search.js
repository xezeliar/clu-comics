/**
 * Settings search: filters the settings page by label as you type. A group
 * (.clu-settings-panel) stays when any of its headings or labels matches;
 * empty groups hide, the matching labels are marked, and while a query is
 * active every tab's groups show together. Esc clears it (clu-filters.js).
 * Markup: #settingsSearch (search_input) and #settingsCount in config.html.
 */
(function () {
    'use strict';
    var input = document.getElementById('settingsSearch');
    var content = document.getElementById('configTabsContent');
    if (!input || !content) return;
    var count = document.getElementById('settingsCount');
    var panels = Array.prototype.slice.call(content.querySelectorAll('.clu-settings-panel'));
    var LABELS = 'h2, h3, h4, h5, h6, label';

    function apply(value) {
        var q = (value || '').trim().toLowerCase();
        var shown = 0;
        content.classList.toggle('clu-searching', !!q);
        panels.forEach(function (panel) {
            var hits = 0;
            panel.querySelectorAll(LABELS).forEach(function (el) {
                var hit = !!q && el.textContent.toLowerCase().indexOf(q) !== -1;
                el.classList.toggle('clu-setting-hit', hit);
                if (hit) hits++;
            });
            var keep = !q || hits > 0;
            panel.hidden = !keep;
            if (keep) shown++;
        });
        if (count && window.CLU && CLU.setCount) {
            CLU.setCount(count, { total: panels.length, noun: 'setting groups', one: 'setting group', shown: shown });
        }
    }
    CLU.bindSearch(input, apply, { delay: 0 });
    apply('');
})();
