/**
 * Pull-to-refresh  –  clu-pull-refresh.js
 *
 * On touch devices, dragging down from the very top of a page refreshes it.
 * A page can supply its own refresh (reload its list without leaving the
 * page) as window._cluRefresh(); otherwise the page reloads. It stays out of
 * the way of anything that scrolls on its own: an open modal, the comic reader
 * (the body is locked while it is up) and any scrolled container.
 */
(function () {
  'use strict';

  if (!window.matchMedia('(pointer: coarse)').matches) return;

  var THRESHOLD = 80;   // px of pull that arms a refresh
  var MAX_PULL = 120;
  var start = null;     // { y, x } while a pull may be under way
  var pull = 0;
  var el = null;

  function indicator() {
    if (!el) {
      el = document.createElement('div');
      el.className = 'clu-ptr';
      el.setAttribute('aria-hidden', 'true');
      el.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
      document.body.appendChild(el);
    }
    return el;
  }

  function reset() {
    start = null;
    pull = 0;
    if (el) {
      el.classList.remove('is-armed');
      el.style.transform = '';
      el.style.opacity = '0';
    }
  }

  function canPull(target) {
    if (window.scrollY > 0 || document.body.classList.contains('modal-open')) return false;
    if (document.body.style.overflow === 'hidden') return false;  // reader open
    for (var n = target; n && n !== document.body; n = n.parentElement) {
      if (n.scrollTop > 0) return false;  // inside a scrolled container
    }
    return true;
  }

  document.addEventListener('touchstart', function (e) {
    start = e.touches.length === 1 && canPull(e.target)
      ? { y: e.touches[0].clientY, x: e.touches[0].clientX } : null;
  }, { passive: true });

  document.addEventListener('touchmove', function (e) {
    if (!start) return;
    var dy = e.touches[0].clientY - start.y;
    var dx = e.touches[0].clientX - start.x;
    if (e.touches.length > 1 || dy <= 0 || Math.abs(dx) > dy) { reset(); return; }
    pull = Math.min(dy, MAX_PULL);
    var node = indicator();
    node.style.opacity = String(Math.min(1, pull / THRESHOLD));
    node.style.transform = 'translate(-50%, ' + (pull / 2) + 'px) rotate(' + pull * 3 + 'deg)';
    node.classList.toggle('is-armed', pull >= THRESHOLD);
  }, { passive: true });

  document.addEventListener('touchend', function () {
    var armed = start && pull >= THRESHOLD;
    reset();
    if (!armed) return;
    if (typeof window._cluRefresh === 'function') window._cluRefresh();
    else window.location.reload();
  }, { passive: true });

  document.addEventListener('touchcancel', reset, { passive: true });
})();
