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
        if (!phone.matches || !menu || !btn.closest('.item-actions, .clu-page-more')) return;
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
})();
