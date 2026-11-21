/**
 * clu-filters.js: the list toolbar's behaviour, shared. base.html loads it on
 * every page. The markup twin is templates/partials/filters.html.
 *
 *   CLU.filterBar(group, {onChange, multi, toggleOff})
 *       Wires a row of toggle buttons (role="group", one button per
 *       data-value). Single choice by default; data-clu-filter="multi" or
 *       multi:true makes it multi-select, where '' (All) clears the others.
 *       data-clu-toggle-off or toggleOff:true sends a second click on the
 *       selected button back to ''. The buttons carry .active and
 *       aria-pressed. onChange(value, button) gets a string, or an array for
 *       a multi group ([] = All). Calling it again on the same group only
 *       swaps the options, so a page can re-render the buttons freely.
 *
 *   CLU.renderFilterOptions(group, options, active)
 *       Draws filter_bar's buttons from a script. options:
 *       [{value, label, icon, iconClass, count, disabled}]. A menu or facet
 *       group (data-clu-mode) gets checkbox/radio rows instead of pills, and
 *       a multi one leaves out the '' (All) option.
 *
 *   Menu filters (filter_bar mode='menu') keep their button's "Status: X",
 *   the chip row under the toolbar and its Clear all in step with the
 *   selection; facet groups (mode='facet') keep facet_column's Clear all, the
 *   "Filters · N" button and "Show N more". Both answer to the same
 *   onChange as the pills: a chip's x or Clear all calls it too.
 *
 *   CLU.letterBar(group, {letters, active, onChange, allLabel})
 *       Draws and wires the A-Z text strip: All, '#' (when present), then
 *       every letter A-Z; letters not in `letters` are greyed and out of the
 *       Tab order. A selected letter that is not in `letters` stays live so
 *       it can be switched off. Keyboard focus stays on the same letter
 *       across a redraw.
 *
 *   CLU.setFilterValue(group, value) / CLU.filterValue(group)
 *       Mark the selection without firing onChange / read it back.
 *
 *   CLU.bindSearch(input, fn, {delay})
 *       Calls fn(value) as the user types: after `delay` ms of quiet
 *       (default 250, for a search the server answers) or at once with
 *       delay 0 (a filter over rows already on the page). Enter runs it
 *       immediately. A value it already ran is skipped; a page may empty
 *       the box with input.value = '' and refresh itself.
 *
 *   CLU.formatCount(n)
 *       4132 -> "4,132", matching the server's '{:,}'.format().
 *
 *   CLU.countText({total, noun, one, shown, first, last}) / CLU.setCount(el, opts)
 *       A result count, worded as result_count() words it: "4,132 series",
 *       "Showing 12 of 245 publishers" (shown), "Showing 1–60 of 4,132
 *       series" (first/last, a paged list). one is the singular noun.
 *
 *   CLU.searchInput({id, label, value})
 *       Builds search_input's markup from a script; returns the wrapper.
 *       label is "Search <what it matches>"; the placeholder is the label
 *       plus an ellipsis, always.
 *
 *   CLU.setSearchLabel(input, label)
 *       Renames a search box when the list under it changes (Collection's
 *       views): the accessible name and the placeholder together.
 *
 *   Every input.form-control[type="search"] in the app clears on Escape
 *   (and fires `input`, so whatever listens refilters). A non-empty box eats
 *   the Escape, so clearing a search inside a modal does not also close it.
 */
(function () {
    'use strict';

    window.CLU = window.CLU || {};

    var OWNER = '[data-clu-filter],[role="group"],[role="radiogroup"],[role="menu"]';

    function buttons(group) {
        return Array.prototype.filter.call(group.querySelectorAll('[data-value]'),
            function (b) { return b.closest(OWNER) === group; });
    }

    function isMulti(group) {
        return group.getAttribute('data-clu-filter') === 'multi';
    }

    function modeOf(group) {
        return group.getAttribute('data-clu-mode') || 'bar';
    }

    function inert(b) {
        return b.disabled || b.getAttribute('aria-disabled') === 'true';
    }

    function mark(group, values) {
        var set = values.length ? values : [''];
        buttons(group).forEach(function (b) {
            var on = set.indexOf(b.getAttribute('data-value')) !== -1;
            b.classList.toggle('active', on);
            b.setAttribute(b.hasAttribute('aria-checked') ? 'aria-checked' : 'aria-pressed', on ? 'true' : 'false');
        });
        sync(group);
    }

    // Counts read 4,132 everywhere: the same grouping the server's
    // '{:,}'.format() gives the page header, whatever the browser's locale.
    CLU.formatCount = function (n) {
        var v = Number(n);
        return isFinite(v) ? v.toLocaleString('en-US') : String(n);
    };

    CLU.countText = function (o) {
        var opts = o || {};
        var total = Number(opts.total) || 0;
        var noun = opts.noun || '';
        var name = total === 1 && opts.one ? opts.one : noun;
        var f = CLU.formatCount;
        var paged = opts.first != null && opts.last != null && total > 0 &&
            !(Number(opts.first) === 1 && Number(opts.last) === total);
        if (paged) {
            return 'Showing ' + f(opts.first) + '\u2013' + f(opts.last) + ' of ' + f(total) + ' ' + name;
        }
        if (opts.shown != null && Number(opts.shown) !== total) {
            return 'Showing ' + f(opts.shown) + ' of ' + f(total) + ' ' + name;
        }
        return f(total) + ' ' + name;
    };

    CLU.setCount = function (el, opts) {
        if (!el) return;
        el.textContent = CLU.countText(opts);
        syncShowN();
    };

    CLU.filterValue = function (group) {
        var on = buttons(group)
            .filter(function (b) { return b.classList.contains('active'); })
            .map(function (b) { return b.getAttribute('data-value'); });
        if (isMulti(group)) return on.filter(function (v) { return v !== ''; });
        return on.length ? on[0] : '';
    };

    CLU.setFilterValue = function (group, value) {
        if (!group) return;
        var values = Array.isArray(value) ? value.map(String) : [String(value == null ? '' : value)];
        values = values.filter(function (v) { return v !== ''; });
        mark(group, values);
    };

    CLU.filterBar = function (group, opts) {
        if (!group) return;
        var o = opts || {};
        if (o.multi) group.setAttribute('data-clu-filter', 'multi');
        else if (!group.hasAttribute('data-clu-filter')) group.setAttribute('data-clu-filter', 'single');
        if (o.toggleOff) group.setAttribute('data-clu-toggle-off', '');
        group._cluFilterOpts = o;
        sync(group);
        if (CLU.watchFilterScroll) CLU.watchFilterScroll(group);
        if (group._cluFilterWired) return;
        group._cluFilterWired = true;

        group.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-value]');
            if (!btn || inert(btn) || btn.closest(OWNER) !== group) return;
            var value = btn.getAttribute('data-value');
            var cur = CLU.filterValue(group);
            var next;
            if (isMulti(group)) {
                if (value === '') {
                    next = [];
                } else if (cur.indexOf(value) !== -1) {
                    next = cur.filter(function (v) { return v !== value; });
                } else {
                    next = cur.concat([value]);
                }
                mark(group, next);
            } else {
                if (value === cur) {
                    if (!group.hasAttribute('data-clu-toggle-off') || value === '') return;
                    value = '';
                }
                next = value;
                mark(group, value === '' ? [] : [value]);
            }
            var cb = group._cluFilterOpts && group._cluFilterOpts.onChange;
            if (cb) cb(next, btn);
        });
    };

    function countNode(count) {
        var c = document.createElement('span');
        c.className = 'clu-filter-count';
        c.textContent = typeof count === 'number' ? CLU.formatCount(count) : String(count);
        return c;
    }

    function hasCount(opt) {
        return opt.count !== undefined && opt.count !== null && opt.count !== '';
    }

    function iconNode(opt) {
        var i = document.createElement('i');
        i.className = 'bi ' + opt.icon + (opt.iconClass ? ' ' + opt.iconClass : '') + ' me-1';
        i.setAttribute('aria-hidden', 'true');
        return i;
    }

    function makeButton(opt, on, small) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn ' + (small ? 'btn-sm ' : '') + 'btn-outline-secondary' + (on ? ' active' : '');
        b.setAttribute('data-value', String(opt.value == null ? '' : opt.value));
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        if (opt.icon) b.appendChild(iconNode(opt));
        b.appendChild(document.createTextNode(String(opt.label)));
        if (hasCount(opt)) b.appendChild(countNode(opt.count));
        if (opt.disabled && !on) b.disabled = true;
        if (opt.title) b.title = opt.title;
        return b;
    }

    // A row of a menu or facet group: box, label, count (filter_bar's _opt_button).
    function makeOption(opt, on, mode, multi) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'clu-opt' + (mode === 'menu' ? ' dropdown-item' : '') + (on ? ' active' : '') +
            (opt.count === 0 ? ' is-zero' : '');
        b.setAttribute('role', mode === 'menu' ? (multi ? 'menuitemcheckbox' : 'menuitemradio') : (multi ? 'checkbox' : 'radio'));
        b.setAttribute('aria-checked', on ? 'true' : 'false');
        b.setAttribute('data-value', String(opt.value == null ? '' : opt.value));
        b.setAttribute('data-label', String(opt.label));
        if (opt.disabled && !on) b.setAttribute('aria-disabled', 'true');
        var box = document.createElement('span');
        box.className = 'clu-opt-box' + (multi ? '' : ' is-radio');
        box.setAttribute('aria-hidden', 'true');
        var label = document.createElement('span');
        label.className = 'clu-opt-label';
        if (opt.icon) label.appendChild(iconNode(opt));
        label.appendChild(document.createTextNode(String(opt.label)));
        b.appendChild(box);
        b.appendChild(label);
        if (hasCount(opt)) b.appendChild(countNode(opt.count));
        if (opt.title) b.title = opt.title;
        return b;
    }

    // Keyboard focus survives a redraw: remember the focused value, put focus
    // back on the same one (or the selected one) afterwards.
    function redraw(group, draw) {
        var focused = document.activeElement;
        var key = (focused && group.contains(focused) && focused.hasAttribute('data-value'))
            ? focused.getAttribute('data-value') : null;
        group.innerHTML = '';
        draw();
        sync(group);
        if (key === null) return;
        var target = buttons(group).filter(function (b) {
            return b.getAttribute('data-value') === key && !inert(b);
        })[0] || group.querySelector('.active');
        if (target) target.focus({ preventScroll: true });
    }

    CLU.renderFilterOptions = function (group, options, active) {
        if (!group) return;
        var values = Array.isArray(active) ? active.map(String) : [String(active == null ? '' : active)];
        values = values.filter(function (v) { return v !== ''; });
        if (!values.length) values = [''];
        var mode = modeOf(group);
        var multi = isMulti(group);
        var needBtnSm = !group.classList.contains('btn-group-sm');
        redraw(group, function () {
            (options || []).forEach(function (opt) {
                var v = String(opt.value == null ? '' : opt.value);
                var on = values.indexOf(v) !== -1;
                if (mode === 'bar') {
                    group.appendChild(makeButton(opt, on, needBtnSm));
                } else if (!(multi && v === '')) {
                    group.appendChild(makeOption(opt, on, mode, multi));
                }
            });
        });
    };

    // '#' first, then A-Z: the order every letter bar uses.
    CLU.sortLetters = function (letters) {
        var seen = {};
        var out = [];
        Array.from(letters || []).forEach(function (l) {
            var k = String(l).toUpperCase();
            if (k !== '#' && !/^[A-Z]$/.test(k)) k = '#';
            if (!seen[k]) { seen[k] = true; out.push(k); }
        });
        return out.sort(function (a, b) {
            if (a === '#') return -1;
            if (b === '#') return 1;
            return a < b ? -1 : a > b ? 1 : 0;
        });
    };

    var ALPHABET = [];
    for (var cc = 65; cc <= 90; cc++) ALPHABET.push(String.fromCharCode(cc));

    function makeLetter(value, label, on, live) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'clu-letter' + (value === '' ? ' clu-letter-all' : '') + (on ? ' active' : '');
        b.setAttribute('data-value', value);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        b.textContent = label;
        if (!live) {
            b.setAttribute('aria-disabled', 'true');
            b.tabIndex = -1;
            b.setAttribute('aria-label', label + ', none');
        }
        return b;
    }

    CLU.letterBar = function (group, opts) {
        if (!group) return;
        var o = opts || {};
        var active = o.active ? String(o.active).toUpperCase() : '';
        var letters = CLU.sortLetters(o.letters);
        if (active && letters.indexOf(active) === -1) letters = CLU.sortLetters(letters.concat([active]));

        // Templates written for the old joined pills still carry btn-group.
        group.classList.remove('btn-group', 'btn-group-sm');
        group.classList.add('clu-letter-bar', 'clu-filter-scroll');
        group.setAttribute('role', 'group');
        if (!group.hasAttribute('aria-label')) group.setAttribute('aria-label', 'Filter by first letter');

        var strip = (letters.indexOf('#') !== -1 ? ['#'] : []).concat(ALPHABET);
        redraw(group, function () {
            group.appendChild(makeLetter('', o.allLabel || 'All', !active, true));
            strip.forEach(function (l) {
                group.appendChild(makeLetter(l, l, l === active, letters.indexOf(l) !== -1));
            });
        });
        CLU.filterBar(group, { onChange: o.onChange, toggleOff: true });
    };

    // ---- Menu filters, chips and the facet column -----------------------

    // The number a "Show N" button offers: what the list's count says it
    // shows ("Showing 12 of 77" -> 12, "Showing 1-60 of 4,132" -> 4,132,
    // "77 releases" -> 77). The count is the page's, so no page passes it.
    function shownNumber() {
        var el = document.querySelector('.clu-page-header .clu-toolbar-count') ||
            document.querySelector('.clu-toolbar-count');
        if (!el) return null;
        var nums = (el.textContent.match(/[\d,]+/g) || []).map(function (n) { return n.replace(/,/g, ''); });
        if (!nums.length) return null;
        var paged = /\u2013|-/.test(el.textContent) && nums.length >= 3;
        return Number(paged ? nums[2] : nums[0]);
    }

    function syncShowN(root) {
        var n = shownNumber();
        (root || document).querySelectorAll('[data-clu-show-n]').forEach(function (b) {
            b.textContent = n === null ? 'Show results' : 'Show ' + CLU.formatCount(n);
        });
    }

    function selectedLabels(group) {
        return buttons(group).filter(function (b) {
            return b.classList.contains('active') && b.getAttribute('data-value') !== '';
        }).map(function (b) { return b.getAttribute('data-label') || b.textContent.trim(); });
    }

    function setValueText(btn, labels) {
        var v = btn.querySelector('.clu-fmenu-v');
        if (!v) return;
        v.textContent = '';
        btn.classList.toggle('is-set', labels.length > 0);
        if (!labels.length) return;
        var b = document.createElement('b');
        b.textContent = labels.length === 1 ? labels[0] : String(labels.length);
        v.appendChild(document.createTextNode(': '));
        v.appendChild(b);
    }

    // Set a group to `value` and tell the page, as a click would.
    function setAndFire(group, value) {
        var next = isMulti(group) ? (Array.isArray(value) ? value : []) : (Array.isArray(value) ? '' : value);
        mark(group, isMulti(group) ? next : (next === '' ? [] : [next]));
        var cb = group._cluFilterOpts && group._cluFilterOpts.onChange;
        if (cb) cb(next, null);
    }

    function clearGroups(groups) {
        groups.forEach(function (g) {
            if (selectedLabels(g).length) setAndFire(g, isMulti(g) ? [] : '');
        });
    }

    function syncChips(toolbar) {
        var groups = Array.prototype.slice.call(toolbar.querySelectorAll('[data-clu-mode="menu"]'));
        var chips = toolbar.querySelector(':scope > .clu-filter-chips');
        if (!chips) {
            if (!groups.length) return;
            chips = document.createElement('div');
            chips.className = 'clu-filter-chips';
            chips.setAttribute('role', 'group');
            chips.setAttribute('aria-label', 'Active filters');
            var row = groups[0].closest('.clu-toolbar-row');
            if (row && row.parentNode === toolbar) row.after(chips); else toolbar.appendChild(chips);
        }
        chips.textContent = '';
        groups.forEach(function (g) {
            var name = (g.closest('.clu-fmenu').querySelector('.clu-fmenu-k') || {}).textContent || '';
            buttons(g).forEach(function (b) {
                var v = b.getAttribute('data-value');
                if (!b.classList.contains('active') || v === '') return;
                var label = name + ': ' + (b.getAttribute('data-label') || b.textContent.trim());
                var chip = document.createElement('span');
                chip.className = 'clu-chip';
                chip.appendChild(document.createTextNode(label));
                var x = document.createElement('button');
                x.type = 'button';
                x.className = 'clu-chip-x';
                x.setAttribute('aria-label', 'Remove ' + label);
                x.innerHTML = '<i class="bi bi-x" aria-hidden="true"></i>';
                x._cluChip = { group: g, value: v };
                chip.appendChild(x);
                chips.appendChild(chip);
            });
        });
        chips.hidden = !chips.children.length;
        if (chips.children.length) {
            var all = document.createElement('button');
            all.type = 'button';
            all.className = 'btn btn-link btn-sm clu-chips-clear';
            all.setAttribute('data-clu-clear-chips', '');
            all.textContent = 'Clear all';
            chips.appendChild(all);
        }
    }

    var MORE_AFTER = 6;

    function syncMore(group) {
        var opts = buttons(group);
        var long = opts.length > MORE_AFTER + 1 && !group._cluShowAll;
        opts.forEach(function (b, i) {
            b.hidden = long && i >= MORE_AFTER && !b.classList.contains('active');
        });
        var more = group.nextElementSibling;
        if (!more || !more.hasAttribute('data-clu-more')) {
            if (!long) return;
            more = document.createElement('button');
            more.type = 'button';
            more.className = 'btn btn-link btn-sm clu-facet-more';
            more.setAttribute('data-clu-more', '');
            group.after(more);
        }
        var hidden = opts.filter(function (b) { return b.hidden; }).length;
        more.hidden = !hidden;
        more.textContent = 'Show ' + hidden + ' more';
    }

    function syncFacets(column) {
        var groups = Array.prototype.slice.call(column.querySelectorAll('[data-clu-mode="facet"]'));
        var n = groups.reduce(function (a, g) { return a + selectedLabels(g).length; }, 0);
        var clear = column.querySelector('[data-clu-clear-facets]');
        if (clear) clear.hidden = !n;
        document.querySelectorAll('[data-clu-facets-btn][data-bs-target="#' + column.id + '"]').forEach(function (btn) {
            btn.classList.toggle('is-set', n > 0);
            var v = btn.querySelector('.clu-fmenu-v');
            if (v) v.textContent = n ? ' \u00b7 ' + n : '';
        });
    }

    function sync(group) {
        var mode = modeOf(group);
        if (mode === 'menu') {
            var wrap = group.closest('.clu-fmenu');
            if (wrap) setValueText(wrap.querySelector('.clu-fmenu-btn'), selectedLabels(group));
            var toolbar = group.closest('.clu-toolbar');
            if (toolbar) syncChips(toolbar);
        } else if (mode === 'facet') {
            syncMore(group);
            var column = group.closest('.clu-facets');
            if (column) syncFacets(column);
        }
    }

    function dropdownToggle(el) {
        var dd = el.closest('.dropdown');
        return dd && dd.querySelector('[data-bs-toggle="dropdown"]');
    }

    function hideDropdown(el) {
        var t = dropdownToggle(el);
        if (t && window.bootstrap) bootstrap.Dropdown.getOrCreateInstance(t).hide();
        if (t) t.focus();
    }

    document.addEventListener('click', function (e) {
        var t = e.target;
        if (!(t instanceof Element)) return;
        var x = t.closest('.clu-chip-x');
        if (x && x._cluChip) {
            var g = x._cluChip.group;
            var v = x._cluChip.value;
            var bar = g.closest('.clu-toolbar');
            setAndFire(g, isMulti(g) ? CLU.filterValue(g).filter(function (k) { return k !== v; }) : '');
            var next = bar && (bar.querySelector('.clu-chip-x') || bar.querySelector('.clu-fmenu-btn'));
            if (next) next.focus();
            return;
        }
        if (t.closest('[data-clu-clear-chips]')) {
            var tb = t.closest('.clu-toolbar');
            clearGroups(Array.prototype.slice.call(tb.querySelectorAll('[data-clu-mode="menu"]')));
            var first = tb.querySelector('.clu-fmenu-btn');
            if (first) first.focus();
            return;
        }
        var clearFacets = t.closest('[data-clu-clear-facets]');
        if (clearFacets) {
            clearGroups(Array.prototype.slice.call(clearFacets.closest('.clu-facets').querySelectorAll('[data-clu-mode="facet"]')));
            return;
        }
        var more = t.closest('[data-clu-more]');
        if (more) {
            var group = more.previousElementSibling;
            group._cluShowAll = true;
            var firstHidden = buttons(group).filter(function (b) { return b.hidden; })[0];
            syncMore(group);
            if (firstHidden) firstHidden.focus();
            return;
        }
        if (t.closest('[data-clu-close]')) {
            hideDropdown(t);
            return;
        }
    });

    // On a phone a toolbar menu is a bottom sheet (clu-page.css). The dimmed
    // page above it is a real element, so a tap there closes the sheet and
    // lands on nothing else.
    var PHONE = window.matchMedia ? window.matchMedia('(max-width: 767.98px)') : null;

    document.addEventListener('show.bs.dropdown', function (e) {
        var dd = e.target.closest('.dropdown');
        var menu = dd && (dd.querySelector(':scope > .clu-sheet') ||
            (dd.closest('.clu-toolbar') && dd.querySelector(':scope > .dropdown-menu')));
        if (!menu) return;
        syncShowN(menu);
        if (!PHONE || !PHONE.matches || dd.querySelector(':scope > .clu-scrim')) return;
        var scrim = document.createElement('div');
        scrim.className = 'clu-scrim';
        scrim.addEventListener('click', function () { hideDropdown(menu); });
        dd.insertBefore(scrim, menu);
    });
    document.addEventListener('hidden.bs.dropdown', function (e) {
        var dd = e.target.closest('.dropdown');
        var scrim = dd && dd.querySelector(':scope > .clu-scrim');
        if (scrim) scrim.remove();
    });
    document.addEventListener('show.bs.offcanvas', function (e) {
        if (e.target.classList && e.target.classList.contains('clu-facets')) syncShowN(e.target);
    });

    // ---- Search boxes -------------------------------------------------------

    CLU.bindSearch = function (input, fn, opts) {
        if (!input || !fn) return;
        var delay = opts && typeof opts.delay === 'number' ? opts.delay : 250;
        var timer = null;
        var last = null;
        function run() {
            clearTimeout(timer);
            timer = null;
            var v = input.value.trim();
            if (v === last) return;
            last = v;
            fn(v);
        }
        last = input.value.trim();
        // A page's Clear button sets input.value directly, which fires no
        // event, so `last` would keep the old query and typing it again would
        // be skipped. With nothing pending, the box should hold what last ran:
        // anything else was set by code, and what the page now shows is
        // unknown, so the next query runs whatever it is.
        input.addEventListener('beforeinput', function () {
            if (timer === null && input.value.trim() !== last) last = null;
        });
        input.addEventListener('input', function (e) {
            // An input event dispatched by code is a request to search now,
            // even for the query that last ran: the page may have reset its
            // own state (a modal reopened on its browse list) under it.
            if (e && e.isTrusted === false) { last = null; run(); return; }
            if (delay <= 0) { run(); return; }
            clearTimeout(timer);
            timer = setTimeout(run, delay);
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); run(); }
        });
    };

    CLU.searchInput = function (o) {
        var opts = o || {};
        var wrap = document.createElement('div');
        wrap.className = 'input-group input-group-sm clu-search' + (opts.classes ? ' ' + opts.classes : '');
        var icon = document.createElement('span');
        icon.className = 'input-group-text bg-body';
        icon.setAttribute('aria-hidden', 'true');
        icon.innerHTML = '<i class="bi bi-search"></i>';
        var input = document.createElement('input');
        input.type = 'search';
        input.className = 'form-control';
        if (opts.id) input.id = opts.id;
        CLU.setSearchLabel(input, opts.label || 'Search');
        input.value = opts.value || '';
        input.autocomplete = 'off';
        input.spellcheck = false;
        input.setAttribute('enterkeyhint', 'search');
        wrap.appendChild(icon);
        wrap.appendChild(input);
        return wrap;
    };

    CLU.setSearchLabel = function (input, label) {
        if (!input) return;
        input.setAttribute('aria-label', label);
        input.placeholder = label + '\u2026';
    };

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape' || e.defaultPrevented) return;
        var t = e.target;
        if (!t || t.tagName !== 'INPUT' || t.type !== 'search' || !t.value) return;
        e.preventDefault();
        e.stopPropagation();
        t.value = '';
        t.dispatchEvent(new Event('input', { bubbles: true }));
    }, true);
})();
