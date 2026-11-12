/**
 * The Appearance panel (templates/partials/appearance_panel.html).
 *
 * Changes preview inside the panel. On /account, Save posts to
 * /api/account/appearance and reloads (the theme is linked server-side in
 * <head>); the reloaded page shows "Theme saved" with Undo for 8 seconds. On
 * /config the Personalization tab's Save reads CLU.appearancePayload(id).
 */
(function (window, document) {
  'use strict';

  var CLU = window.CLU = window.CLU || {};
  var UNDO_KEY = 'cluAppearanceUndo';
  var KEYS = ['theme', 'mode', 'light', 'dark', 'oled', 'accent', 'publisher_dots', 'cover_tilt'];

  // Contrast maths, as core/themes.py does it for the real page.
  function rgb(h) { return [1, 3, 5].map(function (i) { return parseInt(h.slice(i, i + 2), 16); }); }
  function lum(h) {
    var c = rgb(h).map(function (v) { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function contrast(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  function toward(a, b, t) {
    var bb = rgb(b);
    return '#' + rgb(a).map(function (v, i) { return Math.round(v + (bb[i] - v) * t).toString(16).padStart(2, '0'); }).join('');
  }
  function textSide(fill, page, ink) {
    for (var step = 0; step <= 20; step++) {
      var c = toward(fill, ink, step / 20);
      if (contrast(c, page) >= 4.5) return c;
    }
    return ink;
  }

  function payload(s) {
    return {
      bootstrapTheme: s.theme, mode: s.mode, lightTheme: s.light, darkTheme: s.dark,
      trueBlack: s.oled, accent: s.accent, publisherDots: s.publisher_dots, coverTilt: s.cover_tilt
    };
  }

  async function post(body) {
    var resp = await fetch('/api/account/appearance', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    return resp.json().catch(function () { return { success: false, error: 'Bad response' }; });
  }

  function remember(value) {
    try { window.sessionStorage.setItem(UNDO_KEY, JSON.stringify(value)); } catch (e) { /* no undo then */ }
  }

  CLU.initAppearance = function (id) {
    var root = document.getElementById(id);
    if (!root) return null;
    if (root._cluAppearance) return root._cluAppearance;

    var data = JSON.parse(root.querySelector('.clu-ap-data').textContent);
    var themes = data.catalog.themes;
    var perUser = root.dataset.perUser === 'true';
    var saved = data.state;
    var s = Object.assign({}, saved);
    var slot = themes[s.theme].dark ? 'dark' : 'light';
    var kind = function (t) { return themes[t].dark ? 'dark' : 'light'; };
    var current = function () { return s.mode === 'one' ? s.theme : s[slot]; };
    var dirty = function () { return KEYS.some(function (k) { return s[k] !== saved[k]; }); };

    function draw(focusSel) {
      var t = current(), pal = themes[t], dark = pal.dark;

      root.querySelectorAll('[data-mode]').forEach(function (b) {
        b.setAttribute('aria-checked', String(b.dataset.mode === s.mode));
      });
      root.querySelector('.clu-ap-follow').hidden = s.mode !== 'follow';
      root.querySelectorAll('[data-slot]').forEach(function (b) {
        var k = b.dataset.slot, p = themes[s[k]];
        b.setAttribute('aria-pressed', String(k === slot));
        b.querySelector('.clu-ap-slot-name').textContent = p.label;
        var chip = b.querySelector('.clu-ap-chip');
        chip.style.setProperty('--t-nav', p.nav);
        chip.style.setProperty('--t-bg', s.oled && k === 'dark' ? '#000000' : p.page);
        chip.style.setProperty('--t-fg', p.ink);
      });
      root.querySelector('.clu-ap-gal').setAttribute('aria-label',
        s.mode === 'follow' ? 'Theme when your device is ' + slot : 'Theme');

      var tiles = root.querySelectorAll('.clu-ap-tile');
      tiles.forEach(function (b) {
        var on = b.dataset.theme === t;
        b.setAttribute('aria-checked', String(on));
        b.disabled = s.mode === 'follow' && kind(b.dataset.theme) !== slot;
        b.tabIndex = on ? 0 : -1;
      });

      // True black: only dark themes have a page to turn black.
      var oled = root.querySelector('[data-k="oled"]');
      var oledOff = s.mode === 'one' && !dark;
      oled.checked = s.oled;
      oled.disabled = oledOff;
      document.getElementById(oled.getAttribute('aria-describedby')).textContent = oledOff
        ? pal.label + ' is a light theme. Pick a dark theme to use true black.'
        : s.mode === 'follow' ? 'Pure black pages on your dark theme. Saves battery on OLED screens.'
          : 'Pure black pages. Saves battery on OLED screens.';

      root.querySelectorAll('[data-accent]').forEach(function (b) {
        var on = b.dataset.accent === s.accent;
        b.setAttribute('aria-checked', String(on));
        b.tabIndex = on ? 0 : -1;
        if (!b.dataset.accent) { b.style.setProperty('--t1', pal.primary); b.style.setProperty('--t2', pal.page); }
        if (on) root.querySelector('.clu-ap-acc-name').textContent = b.getAttribute('aria-label');
      });
      root.querySelectorAll('[data-k="publisher_dots"], [data-k="cover_tilt"]').forEach(function (i) {
        i.checked = s[i.dataset.k];
      });

      // The preview, from the same palette the real stylesheet is made of.
      var bg = pal.page, raised = pal.raised, rule = pal.rule, pr = pal.primary, link = pal.link;
      if (s.oled && dark) { bg = '#000000'; raised = '#121212'; rule = '#2e2e2e'; }
      if (s.accent) { pr = s.accent; link = textSide(s.accent, bg, pal.emphasis); }
      var tp = root.querySelector('.clu-tp');
      var vars = {
        '--tp-bg': bg, '--tp-fg': pal.ink, '--tp-em': pal.emphasis, '--tp-mu': pal.muted,
        '--tp-raised': raised, '--tp-rule': rule, '--tp-pr': pr, '--tp-link': link,
        '--tp-ok': pal.success, '--tp-err': pal.error, '--tp-scheme': dark ? 'dark' : 'light',
        '--tp-nav': s.accent ? s.accent : pal.nav,
        '--tp-navrule': t === 'noir' ? '2px solid ' + pr : '0 solid transparent'
      };
      Object.keys(vars).forEach(function (k) { tp.style.setProperty(k, vars[k]); });
      tp.dataset.t = t;
      tp.classList.toggle('pubs', s.publisher_dots !== false);
      tp.setAttribute('aria-label', 'Preview of ' + pal.label);
      root.querySelector('.clu-ap-pv-name').textContent =
        'Preview · ' + pal.label + (s.oled && dark ? ', true black' : '');
      root.querySelector('.clu-ap-pv-slot').textContent = s.mode === 'follow' ? 'Showing ' + slot : '';

      var save = root.querySelector('[data-act="save"]');
      if (save) {
        save.disabled = !dirty();
        root.querySelector('[data-act="discard"]').hidden = !dirty();
      }
      if (focusSel) { var f = root.querySelector(focusSel); if (f) f.focus(); }
    }

    async function saveNow() {
      var btn = root.querySelector('[data-act="save"]');
      btn.disabled = true;
      try {
        var result = await post(payload(s));
        if (!result || !result.success) {
          CLU.showError((result && result.error) || 'Could not save the theme.');
          btn.disabled = false;
          return;
        }
        remember({ previous: saved, override: root.dataset.override === 'true' });
        window.location.reload();
      } catch (e) {
        CLU.showError('Could not save the theme: ' + e.message);
        btn.disabled = false;
      }
    }

    async function useSiteDefault() {
      var result = await post({ useSiteDefault: true });
      if (!result || !result.success) {
        CLU.showError((result && result.error) || 'Could not reset the theme.');
        return;
      }
      remember({ previous: saved, override: root.dataset.override === 'true' });
      window.location.reload();
    }

    root.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b || b.disabled || !root.contains(b)) return;
      if (b.dataset.mode) {
        s.mode = b.dataset.mode;
        if (s.mode === 'follow') { slot = kind(s.theme); s[slot] = s.theme; } else { s.theme = s[slot]; }
        return draw('[data-mode="' + s.mode + '"]');
      }
      if (b.dataset.slot) { slot = b.dataset.slot; return draw('[data-slot="' + slot + '"]'); }
      if (b.dataset.theme) {
        if (s.mode === 'one') s.theme = b.dataset.theme; else s[slot] = b.dataset.theme;
        return draw();
      }
      if (b.dataset.accent !== undefined) { s.accent = b.dataset.accent; return draw(); }
      if (b.dataset.act === 'discard') { s = Object.assign({}, saved); return draw('[data-act="save"]'); }
      if (b.dataset.act === 'save') return saveNow();
      if (b.dataset.act === 'site-default') return useSiteDefault();
    });
    root.addEventListener('change', function (e) {
      var k = e.target.dataset.k;
      if (!k) return;
      s[k] = e.target.checked;
      draw();
    });
    // Arrow keys move between the tiles (or swatches) and select, as radios do.
    root.addEventListener('keydown', function (e) {
      var steps = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      var group = e.target.closest('.clu-ap-gal, .clu-ap-acc');
      if (!group || !(e.key in steps)) return;
      e.preventDefault();
      var items = Array.prototype.filter.call(group.querySelectorAll('[role="radio"]'), function (b) {
        return !b.disabled && b.offsetParent !== null;
      });
      var i = items.indexOf(e.target);
      var next = items[(i + steps[e.key] + items.length) % items.length];
      next.click();
      next.focus();
    });

    draw();
    root._cluAppearance = { payload: function () { return payload(s); } };
    return root._cluAppearance;
  };

  /** The panel's current choice, as /api/config/styling takes it. */
  CLU.appearancePayload = function (id) {
    var panel = CLU.initAppearance(id);
    return panel ? panel.payload() : null;
  };

  // After a Save (or Use site default) reloads the page: "Theme saved", with
  // Undo for 8 seconds, which puts the previous appearance back.
  document.addEventListener('DOMContentLoaded', function () {
    var pending = null;
    try {
      pending = JSON.parse(window.sessionStorage.getItem(UNDO_KEY) || 'null');
      window.sessionStorage.removeItem(UNDO_KEY);
    } catch (e) { pending = null; }
    if (!pending || pending.undone) {
      if (pending && pending.undone) CLU.toast('Back to your previous theme.', 'success');
      return;
    }
    CLU.toast('Theme saved', 'success', {
      duration: 8000,
      action: {
        label: 'Undo',
        onClick: async function () {
          var body = pending.override ? payload(pending.previous) : { useSiteDefault: true };
          var result = await post(body);
          if (!result || !result.success) {
            CLU.showError((result && result.error) || 'Could not undo.');
            return;
          }
          remember({ undone: true });
          window.location.reload();
        }
      }
    });
  });
})(window, document);
