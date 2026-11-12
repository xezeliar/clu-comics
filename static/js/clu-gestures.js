/**
 * clu-gestures.js: touch shortcuts. Every gesture here only opens something a
 * visible button already does (nothing is reachable by touch alone).
 *
 *   Long-press (450ms) or right-click a cover opens its "More actions" menu,
 *   the same one the round button on the card opens from the keyboard.
 *
 *   Below 576px the card menu and the page header's More menu open as a
 *   bottom sheet: drag handle, scrim, drag down 80px or tap the scrim to
 *   dismiss; Esc is Bootstrap's own. Wider screens keep the dropdown.
 *
 *   Swipe rows: on a touch screen, dragging a [data-swipe-row] left reveals
 *   its .clu-swipe-acts, two items of the row's own More menu. A full swipe
 *   never commits; swipe back or tap the row to close.
 */
(function () {
    'use strict';

    var HOLD_MS = 450, MOVE_PX = 10, DRAG_PX = 80;

    function toggleOf(card) {
        return card.querySelector('.item-actions [data-bs-toggle="dropdown"]');
    }

    // ── Long-press / right-click a cover ────────────────────────────────────
    var timer = null, origin = null, pressed = null, swallowClick = false;

    function openMenu(card) {
        var btn = toggleOf(card);
        if (btn && window.bootstrap) bootstrap.Dropdown.getOrCreateInstance(btn).show();
        return !!btn;
    }
    function release() {
        clearTimeout(timer);
        timer = null;
        if (pressed) pressed.classList.remove('clu-pressing');
        pressed = null;
    }
    document.addEventListener('pointerdown', function (e) {
        if (e.pointerType !== 'touch' || e.target.closest('button, a, input')) return;
        var card = e.target.closest('.grid-item');
        if (!card || !toggleOf(card)) return;
        release();
        pressed = card;
        origin = { x: e.clientX, y: e.clientY };
        card.classList.add('clu-pressing');
        timer = setTimeout(function () {
            if (openMenu(card)) swallowClick = true;
            release();
        }, HOLD_MS);
    });
    document.addEventListener('pointermove', function (e) {
        if (timer && Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > MOVE_PX) release();
    });
    ['pointerup', 'pointercancel'].forEach(function (n) { document.addEventListener(n, release); });
    // The finger lifting after a long-press must not also open the comic.
    document.addEventListener('click', function (e) {
        if (!swallowClick) return;
        swallowClick = false;
        e.preventDefault();
        e.stopPropagation();
    }, true);
    document.addEventListener('contextmenu', function (e) {
        var card = e.target.closest('.grid-item');
        if (card && toggleOf(card) && !e.target.closest('input, textarea')) {
            e.preventDefault();
            openMenu(card);
        }
    });

    // ── Bottom sheet for menus on phones ────────────────────────────────────
    var phone = window.matchMedia('(max-width: 575.98px)');
    var scrim = null;

    function menuFor(btn) {
        return btn.parentElement && btn.parentElement.querySelector('.dropdown-menu');
    }
    document.addEventListener('shown.bs.dropdown', function (e) {
        var btn = e.target, menu = menuFor(btn);
        if (!phone.matches || !menu || !btn.closest('.item-actions, .clu-page-more, .clu-row-more')) return;
        menu.classList.add('clu-sheet');
        scrim = document.createElement('div');
        scrim.className = 'clu-sheet-scrim';
        scrim.addEventListener('click', function () { bootstrap.Dropdown.getOrCreateInstance(btn).hide(); btn.focus(); });
        document.body.appendChild(scrim);
        var y0 = null;
        menu.ontouchstart = function (t) { y0 = menu.scrollTop <= 0 ? t.touches[0].clientY : null; };
        menu.ontouchmove = function (t) {
            if (y0 === null) return;
            var dy = t.touches[0].clientY - y0;
            menu.style.translate = '0 ' + Math.max(dy, 0) + 'px';
            if (dy > DRAG_PX) { y0 = null; bootstrap.Dropdown.getOrCreateInstance(btn).hide(); btn.focus(); }
        };
        menu.ontouchend = function () { menu.style.translate = ''; y0 = null; };
    });
    document.addEventListener('hidden.bs.dropdown', function (e) {
        var menu = menuFor(e.target);
        if (menu) { menu.classList.remove('clu-sheet'); menu.style.translate = ''; }
        if (scrim) { scrim.remove(); scrim = null; }
    });

    // ── Swipe rows ──────────────────────────────────────────────────────────
    var SWIPE_W = 176, swRow = null, swX0 = 0, swY0 = 0, swDx = 0, swMode = null, swOpen = null;

    function setSwipe(row, x) {
        var acts = row.querySelector('.clu-swipe-acts');
        row.style.setProperty('--clu-sw-x', x + 'px');
        row.classList.toggle('clu-swiping', x !== 0);
        if (acts) {
            acts.hidden = x === 0;
            acts.querySelectorAll('button').forEach(function (b) { b.tabIndex = x ? 0 : -1; });
        }
        if (swOpen && swOpen !== row) setSwipe(swOpen, 0);
        swOpen = x ? row : null;
    }
    // The table may scroll sideways on a phone: a left drag scrolls it until
    // its right edge, and only then swipes the row.
    function canSwipe(row) {
        var box = row.closest('.table-responsive');
        return !box || box.scrollLeft + box.clientWidth >= box.scrollWidth - 1;
    }
    document.addEventListener('touchstart', function (e) {
        var row = e.target.closest('[data-swipe-row]');
        if (swOpen && row !== swOpen && !e.target.closest('.clu-swipe-acts')) setSwipe(swOpen, 0);
        if (!row || e.touches.length !== 1 || e.target.closest('.clu-swipe-acts, input')) { swRow = null; return; }
        swRow = row; swMode = null; swDx = 0;
        swX0 = e.touches[0].clientX; swY0 = e.touches[0].clientY;
    }, { passive: true });
    document.addEventListener('touchmove', function (e) {
        if (!swRow) return;
        var t = e.touches[0], dx = t.clientX - swX0, dy = t.clientY - swY0;
        var base = swRow === swOpen ? -SWIPE_W : 0;
        if (swMode === null) {
            if (Math.hypot(dx, dy) < MOVE_PX) return;
            swMode = Math.abs(dx) > Math.abs(dy) && (base || (dx < 0 && canSwipe(swRow))) ? 'swipe' : 'scroll';
            if (swMode === 'swipe') swRow.classList.add('clu-swipe-drag');
        }
        if (swMode !== 'swipe') return;
        e.preventDefault();
        swDx = Math.max(-SWIPE_W, Math.min(0, base + dx));
        swRow.style.setProperty('--clu-sw-x', swDx + 'px');
        swRow.classList.add('clu-swiping');
    }, { passive: false });
    function endSwipe() {
        if (!swRow) return;
        var row = swRow;
        swRow = null;
        row.classList.remove('clu-swipe-drag');
        if (swMode !== 'swipe') return;
        swallowClick = true;  // the lifting finger must not open the row's link
        setSwipe(row, swDx < -60 ? -SWIPE_W : 0);
        setTimeout(function () { swallowClick = false; }, 400);
    }
    document.addEventListener('touchend', endSwipe);
    document.addEventListener('touchcancel', endSwipe);
    // Tapping an open row (not its actions) closes it.
    document.addEventListener('click', function (e) {
        if (swOpen && !e.defaultPrevented && !e.target.closest('.clu-swipe-acts')) {
            var hit = e.target.closest('[data-swipe-row]') === swOpen;
            setSwipe(swOpen, 0);
            if (hit) { e.preventDefault(); e.stopPropagation(); }
        }
    }, true);
})();
