/**
 * CLU motion  –  clu-motion.js  (design board "Motion")
 *
 * Small Web Animations helpers on the tokens in clu-page.css. Every helper:
 *  - applies the state change at once and animates *from* the old state, so
 *    nothing waits on an animation and a new action simply cancels it;
 *  - under reduced motion (CLU.reducedMotion(): data-clu-motion on <html>, else
 *    the system media query) keeps only a 150ms opacity fade, or nothing;
 *  - never sets pointer-events on live content, so input is never blocked.
 *
 * Loaded in <head> by base.html; the DOM-dependent parts use delegation or
 * wait for DOMContentLoaded.
 *
 *   CLU.reducedMotion()            the one reduced-motion test for scripts
 *   CLU.motion.animate(el, frames, opts)   el.animate, reduced-aware
 *   CLU.staggerIn(grid)            first-render entrance, once per visit
 *   CLU.swapImage(img, src)        set src, fade in when it loads (not cached)
 *   CLU.readerOpened(modal) / CLU.readerClosing(modal)   reader FLIP
 *   CLU.burst(button, dots)        favourite / subscribe pop
 *   CLU.flip(container, change)    rows slide to their new place (FLIP)
 *   CLU.countUp(el)                count from 0 (Insights, data-clu-count)
 */
(function (window, document) {
  'use strict';

  var CLU = window.CLU = window.CLU || {};
  var root = document.documentElement;
  var mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  CLU.reducedMotion = function () {
    var mode = root.getAttribute('data-clu-motion');
    if (mode === 'reduce') return true;
    if (mode === 'full') return false;
    return !!(mq && mq.matches);
  };

  function tok(name) {
    return getComputedStyle(root).getPropertyValue('--clu-' + name).trim();
  }
  function ms(name) {
    var v = parseFloat(tok('dur-' + name));
    return isNaN(v) ? 250 : v;
  }
  function ease() { return tok('ease') || 'ease-out'; }

  // el.animate, but reduced motion keeps only the opacity frames at 150ms.
  function animate(el, frames, opts) {
    if (!el || !el.animate) return null;
    opts = opts || {};
    if (CLU.reducedMotion()) {
      frames = frames.filter(function (f) { return 'opacity' in f; })
        .map(function (f) { return { opacity: f.opacity }; });
      if (frames.length < 2) return null;
      opts = { duration: ms('fast'), fill: opts.fill };
    }
    return el.animate(frames, opts);
  }
  function then(a, fn) {
    // A cancelled animation rejects: a newer action took over.
    if (a) a.finished.then(fn, function () {}); else fn();
  }
  CLU.motion = { animate: animate, ms: ms, tok: tok };

  function isBackForward() {
    var nav = window.performance && performance.getEntriesByType &&
      performance.getEntriesByType('navigation')[0];
    return !!(nav && nav.type === 'back_forward');
  }

  // ---- Staggered grid entrance -------------------------------------------
  // Once per visit, on the first non-empty render only: paging, filtering,
  // sorting, polling and going back never replay it. Rows start 40ms apart,
  // five rows at most, so it is over in under half a second.
  var staggered = false;
  CLU.staggerIn = function (grid) {
    if (staggered || !grid || !grid.children.length) return;
    staggered = true;
    if (CLU.reducedMotion() || isBackForward()) return;
    var kids = Array.prototype.filter.call(grid.children, function (k) { return k.offsetParent; });
    var tops = [];
    kids.forEach(function (k) { if (tops.indexOf(k.offsetTop) < 0) tops.push(k.offsetTop); });
    tops.sort(function (a, b) { return a - b; });
    var step = parseFloat(tok('stagger')) || 40;
    kids.forEach(function (k) {
      k.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }],
        { duration: ms('base'), delay: Math.min(tops.indexOf(k.offsetTop), 4) * step,
          easing: ease(), fill: 'backwards' });
    });
  };

  // ---- Cover load-in ------------------------------------------------------
  // The image fades in over 150ms when it finishes loading; one already in the
  // browser cache (complete at once) shows at once. Reduced: it swaps in.
  CLU.swapImage = function (img, src) {
    img.setAttribute('data-clu-fade', '');
    img.src = src;
    if (img.complete) img.removeAttribute('data-clu-fade');
  };
  document.addEventListener('load', function (e) {
    var img = e.target;
    if (!img || img.tagName !== 'IMG' || !img.hasAttribute('data-clu-fade')) return;
    img.removeAttribute('data-clu-fade');
    if (CLU.reducedMotion() || /\/(loading|error)\.svg/.test(img.src)) return;
    img.animate([{ opacity: 0 }, { opacity: 1 }], { duration: ms('fast') });
  }, true);

  // ---- Reader open and close from the cover ---------------------------------
  // The reader is an overlay on the same page, so this is a FLIP on the
  // reader's container. The tapped cover is remembered on click (capture), so
  // reader.js needs no plumbing beyond the two calls.
  var lastCover = null, lastCoverAt = 0, readerCover = null;
  document.addEventListener('click', function (e) {
    var card = e.target.closest && e.target.closest('.grid-item, .dashboard-card, .swiper-slide, .card');
    var img = card && card.querySelector('img');
    if (img) { lastCover = img; lastCoverAt = Date.now(); }
  }, true);

  function flipTransform(from, to) {
    return 'translate(' + (from.left - to.left) + 'px,' + (from.top - to.top) + 'px) scale(' +
      (from.width / to.width) + ',' + (from.height / to.height) + ')';
  }
  function onScreen(r) {
    return r.width > 0 && r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
  }

  CLU.readerOpened = function (modal) {
    if (!modal || modal._cluOpen) return;   // next-issue reopens in place: no replay
    modal._cluOpen = true;
    var src = lastCover && lastCover.isConnected && Date.now() - lastCoverAt < 1500 ? lastCover : null;
    lastCover = null;
    readerCover = src;
    animate(modal, [{ opacity: 0 }, { opacity: 1 }], { duration: ms('base') });
    var box = modal.querySelector('.comic-reader-container') || modal;
    if (!src || CLU.reducedMotion()) return;
    var from = src.getBoundingClientRect(), to = box.getBoundingClientRect();
    if (!onScreen(from) || !to.width || !to.height) return;
    box.animate([{ transformOrigin: '0 0', transform: flipTransform(from, to) },
      { transformOrigin: '0 0', transform: 'none' }], { duration: ms('travel-in'), easing: ease() });
  };

  // Called just before reader.js hides the modal. The modal goes away at once;
  // a pointer-events:none ghost of the page shrinks back to the cover (or
  // fades, if the cover has scrolled away) while the backdrop fades out.
  CLU.readerClosing = function (modal) {
    if (!modal || !modal._cluOpen) return;   // never opened: nothing to close
    modal._cluOpen = false;
    var cover = readerCover;
    readerCover = null;
    if (!document.body) return;
    var dur = ms('travel-back');
    var back = document.createElement('div');
    back.className = 'clu-motion-ghost';
    back.style.cssText = 'inset:0;background:#000;';
    document.body.appendChild(back);
    then(animate(back, [{ opacity: 1 }, { opacity: 0 }], { duration: dur, fill: 'forwards' }),
      function () { back.remove(); });

    var page = Array.prototype.find.call(modal.querySelectorAll('img'), function (i) {
      return i.complete && i.naturalWidth && onScreen(i.getBoundingClientRect());
    });
    if (!page) return;
    var from = page.getBoundingClientRect();
    var ghost = page.cloneNode(false);
    ghost.removeAttribute('id');
    ghost.className = 'clu-motion-ghost';
    ghost.style.cssText = 'left:' + from.left + 'px;top:' + from.top + 'px;width:' + from.width +
      'px;height:' + from.height + 'px;transform-origin:0 0;object-fit:contain;';
    document.body.appendChild(ghost);
    var to = cover && cover.isConnected ? cover.getBoundingClientRect() : null;
    var frames = to && onScreen(to) && !CLU.reducedMotion()
      ? [{ transform: 'none' }, { transform: flipTransform(to, from) }]
      : [{ opacity: 1 }, { opacity: 0 }];
    then(animate(ghost, frames, { duration: dur, easing: ease(), fill: 'forwards' }),
      function () { ghost.remove(); });
  };

  // ---- Favourite burst --------------------------------------------------------
  // Only when turning on. The icon pops to 125%; with dots, six Favourite
  // Amber dots fly 18px out (they sit on cover art, so a fixed colour). Reduced:
  // the colour change alone.
  CLU.burst = function (button, dots) {
    if (!button || CLU.reducedMotion()) return;
    var icon = button.querySelector('i, svg') || button;
    if (getComputedStyle(icon).display === 'inline') icon.style.display = 'inline-block';
    icon.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.25)' }, { transform: 'scale(1)' }],
      { duration: ms('base'), easing: ease() });
    if (dots === false) return;
    for (var i = 0; i < 6; i++) {
      var s = document.createElement('i');
      s.className = 'clu-spark';
      s.setAttribute('aria-hidden', 'true');
      button.appendChild(s);
      var a = i * Math.PI / 3 + 0.5;
      then(s.animate([{ transform: 'translate(0,0) scale(1)', opacity: 1 },
        { transform: 'translate(' + Math.cos(a) * 18 + 'px,' + Math.sin(a) * 18 + 'px) scale(.4)', opacity: 0 }],
        { duration: ms('long'), easing: ease() }), s.remove.bind(s));
    }
  };

  // ---- Queue rows: FLIP -------------------------------------------------------
  // CLU.flip(container, change): rows carry data-flip-key; change() may
  // rebuild them from scratch (a poll does). A row whose key moved slides from
  // its old place in 250ms, a new key fades in, a row that did not move does
  // nothing, so a poll that changed nothing animates nothing. The first fill
  // (nothing measured before) never animates. Reduced: rows swap, new rows fade.
  // Descendants, not just children: Downloads nests its rows inside groups.
  function keyed(container) {
    return Array.prototype.slice.call(container.querySelectorAll('[data-flip-key]'));
  }
  CLU.flip = function (container, change) {
    if (!container) { change(); return; }
    var before = {}, had = false;
    keyed(container).forEach(function (c) { before[c.dataset.flipKey] = c.getBoundingClientRect().top; had = true; });
    change();
    if (!had) return;
    keyed(container).forEach(function (c) {
      var k = c.dataset.flipKey;
      if (!(k in before)) {
        animate(c, [{ opacity: 0 }, { opacity: 1 }], { duration: ms('fast') });
        return;
      }
      var d = before[k] - c.getBoundingClientRect().top;
      if (Math.abs(d) > 0.5) {
        animate(c, [{ transform: 'translateY(' + d + 'px)' }, { transform: 'none' }],
          { duration: ms('base'), easing: ease() });
      }
    });
  };

  // ---- Count-up (Insights) ------------------------------------------------------
  // The real value is in the page from the start (screen readers, no script);
  // it counts from zero in 500ms once, when it first scrolls into view.
  // Reduced: no count.
  var fmt = window.Intl ? new Intl.NumberFormat('en-US') : { format: String };
  CLU.countUp = function (el) {
    var target = parseInt(el.textContent.replace(/[^0-9]/g, ''), 10);
    if (!isFinite(target) || target <= 0 || CLU.reducedMotion()) return;
    var t0 = performance.now(), dur = ms('long'), wrote = null;
    function step(now) {
      // Someone else (a filter fetch) wrote a new value: stop counting.
      if (wrote !== null && el.textContent !== wrote) return;
      var t = Math.min(1, (now - t0) / dur), k = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      wrote = el.textContent = fmt.format(Math.round(target * k));
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  };

  // ---- Shared-element open (cross-document view transitions) ----------------------
  // A cover that links to a series page is named on click; the series header's
  // cover (.clu-shared-cover) carries the same name, so the browser moves it.
  // Names must be unique per page, hence on click rather than per card.
  // Browsers without cross-document view transitions cut over as before.
  var named = null;
  function clearNamed() { if (named) { named.style.viewTransitionName = ''; named = null; } }
  function nameCover(img) { clearNamed(); img.style.viewTransitionName = 'clu-cover'; named = img; }
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    var a = e.target.closest && e.target.closest('a[href*="/series/"]');
    var img = a && a.querySelector('img');
    if (img) nameCover(img);
  });
  window.addEventListener('pageshow', clearNamed);
  // Back sends it home in 300ms instead of 400: mark the return, and name the
  // cover on this page that links to where we came from.
  window.addEventListener('pagereveal', function (e) {
    var act = window.navigation && window.navigation.activation;
    if (!e.viewTransition || !act || act.navigationType !== 'traverse') return;
    root.classList.add('clu-vt-back');
    var from = act.from && act.from.url;
    if (from) {
      var path = new URL(from).pathname;
      var a = Array.prototype.find.call(document.querySelectorAll('a[href*="/series/"]'), function (l) {
        return new URL(l.href, location.href).pathname === path && l.querySelector('img');
      });
      if (a) nameCover(a.querySelector('img'));
    }
    e.viewTransition.finished.finally(function () { root.classList.remove('clu-vt-back'); clearNamed(); });
  });

  // ---- Toast swipe lives in clu-toast.js; page wiring below ------------------------
  document.addEventListener('DOMContentLoaded', function () {
    var counts = document.querySelectorAll('[data-clu-count]');
    if (!counts.length) return;
    if (!('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        CLU.countUp(en.target);
      });
    });
    counts.forEach(function (el) { io.observe(el); });
  });
})(window, document);
