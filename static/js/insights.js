/**
 * Insights page: "Your reading" and "Your collection".
 *
 * Every chart here is HTML and CSS on theme variables (static/css/insights.css),
 * so it follows the theme with no redraw. Reading data comes from
 * /api/reading-overview (per user, in the user's timezone); the collection
 * data is rendered into the page as JSON. One year control drives the whole
 * reading section.
 */
(function () {
  'use strict';

  var root = document.getElementById('insights');
  var URLS = root ? root.dataset : {};
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var TABS = [['writer', 'Writers'], ['penciller', 'Artists'], ['characters', 'Characters'], ['publisher', 'Publishers']];

  var fmt = function (n) { return Number(n || 0).toLocaleString(); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var plural = function (n, w) { return fmt(n) + ' ' + w + (n === 1 ? '' : 's'); };
  var day = function (s) { return new Date(s + 'T00:00:00Z'); };
  var iso = function (d) { return d.toISOString().slice(0, 10); };
  var nice = function (s) { var d = day(s); return DOW[d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' + MON[d.getUTCMonth()]; };
  var hm = function (sec) { var m = Math.floor((sec || 0) / 60); return Math.floor(m / 60) + 'h ' + (m % 60) + 'm'; };
  var and = function (a) { return a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]; };
  var size = function (b) {
    var u = ['bytes', 'KB', 'MB', 'GB', 'TB'], i = 0;
    while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
    return (i && b < 10 ? b.toFixed(1) : Math.round(b)) + ' ' + u[i];
  };
  var stem = function (name) { return String(name || '').replace(/\.[^.\/]+$/, ''); };
  var folderOf = function (p) { return p.slice(0, p.lastIndexOf('/')); };
  var thumb = function (p) { return '/api/thumbnail?path=' + encodeURIComponent(p); };
  var openHref = function (p) { return URLS.collection + '?path=' + encodeURIComponent(folderOf(p)); };
  var sum = function (o) { return Object.keys(o).reduce(function (a, k) { return a + o[k]; }, 0); };
  var lvl = function (n, max) { return n ? 'in-l' + Math.min(4, Math.ceil(n / max * 4)) : ''; };

  var state = { data: null, year: null, tab: 'writer', all: {}, who: {}, cont: null, recent: null, error: false };

  // ── Ranked lists ────────────────────────────────────────────────────────
  // Bars say nothing for one or two names, or for tiny counts: a sentence then.
  function rank(key, list, n, link) {
    if (!list.length) return '';
    if (list.length < 3 || list[0].count < 3) {
      var same = list.every(function (r) { return r.count === list[0].count; });
      if (same) {
        var c = list[0].count;
        return '<p>' + esc(and(list.map(function (r) { return r.name; }))) + ', ' +
          (c === 1 ? 'one issue' : fmt(c) + ' issues') + (list.length > 1 ? ' each' : '') + '.</p>';
      }
      return '<p>' + esc(and(list.map(function (r) { return r.name + ' (' + fmt(r.count) + ')'; }))) + '.</p>';
    }
    var open = !!state.all[key], rows = open ? list : list.slice(0, n), max = list[0].count;
    return '<ol class="in-rank">' + rows.map(function (r) {
      var name = link ? '<a class="n" href="' + esc(link(r.name)) + '" title="' + esc(r.name) + '">' + esc(r.name) + '</a>'
        : '<span class="n" title="' + esc(r.name) + '">' + esc(r.name) + '</span>';
      return '<li>' + name + '<span class="c">' + fmt(r.count) + '</span><span class="b" aria-hidden="true"><i style="width:' +
        Math.max(2, r.count / max * 100) + '%"></i></span></li>';
    }).join('') + '</ol>' + more(key, list.length, n);
  }
  function more(key, total, n) {
    if (total <= n) return '';
    var open = !!state.all[key];
    return '<button type="button" class="btn btn-link btn-sm in-more" data-in-all="' + key + '" aria-expanded="' + open + '">' +
      (open ? 'Show fewer' : 'Show all ' + total) + '</button>';
  }

  // ── Reading ─────────────────────────────────────────────────────────────
  function daysFor(y) {
    var all = state.data.days;
    if (y === 'all') return all;
    var out = {};
    Object.keys(all).forEach(function (k) { if (k.slice(0, 4) === y) out[k] = all[k]; });
    return out;
  }
  function runs(days, today) {
    var ks = Object.keys(days).sort(), best = 0, bestEnd = '', cur = 0, prev = null;
    ks.forEach(function (k) {
      cur = prev && (day(k) - day(prev)) === 864e5 ? cur + 1 : 1;
      if (cur > best) { best = cur; bestEnd = k; }
      prev = k;
    });
    // A run is still on if you read today or yesterday.
    var now = 0, t = day(today);
    if (!days[today]) t.setUTCDate(t.getUTCDate() - 1);
    while (days[iso(t)]) { now++; t.setUTCDate(t.getUTCDate() - 1); }
    return { best: best, bestEnd: bestEnd, now: now };
  }
  function busiest(days) {
    var ks = Object.keys(days), byM = {};
    var dTop = ks.reduce(function (a, b) { return days[b] > days[a] ? b : a; });
    ks.forEach(function (k) { var m = k.slice(0, 7); byM[m] = (byM[m] || 0) + days[k]; });
    var mTop = Object.keys(byM).reduce(function (a, b) { return byM[b] > byM[a] ? b : a; });
    return { dTop: dTop, dN: days[dTop], m: MONTH[+mTop.slice(5) - 1], mN: byM[mTop] };
  }
  function calendar(days, y, today) {
    var start = day(y + '-01-01'), off = start.getUTCDay(), max = Math.max.apply(null, Object.keys(days).map(function (k) { return days[k]; }));
    var h = '', lastM = -1;
    for (var d = new Date(start); d.getUTCFullYear() === +y; d.setUTCDate(d.getUTCDate() + 1)) {
      var i = Math.round((d - start) / 864e5) + off, w = Math.floor(i / 7) + 1, k = iso(d), n = days[k] || 0, fut = k > today;
      if (d.getUTCMonth() !== lastM) { lastM = d.getUTCMonth(); h += '<span class="m" style="grid-area:1/' + w + '/auto/span 4">' + MON[lastM] + '</span>'; }
      h += '<i class="' + (fut ? 'f' : lvl(n, max)) + '" style="grid-area:' + (d.getUTCDay() + 2) + '/' + w + '" title="' + nice(k) + ': ' +
        (fut ? 'to come' : n ? plural(n, 'issue') : 'nothing read') + '"></i>';
    }
    var b = busiest(days);
    return '<div class="in-cal-wrap"><div class="in-cal" role="img" aria-label="' + plural(sum(days), 'issue') + ' on ' +
      plural(Object.keys(days).length, 'day') + ' in ' + y + '.">' + h + '</div></div>' +
      '<div class="in-cal-foot"><span>Busiest day <b>' + nice(b.dTop) + '</b>, ' + plural(b.dN, 'issue') + '</span>' +
      '<span>Busiest month <b>' + b.m + '</b>, ' + plural(b.mN, 'issue') + '</span>' +
      '<span class="in-key" aria-hidden="true">Less <i></i><i class="in-l1"></i><i class="in-l2"></i><i class="in-l3"></i><i class="in-l4"></i> More</span></div>';
  }
  function monthRows(days, ys) {
    var cells = {};
    Object.keys(days).forEach(function (k) { var m = k.slice(0, 7); cells[m] = (cells[m] || 0) + days[k]; });
    var max = Math.max.apply(null, Object.keys(cells).map(function (k) { return cells[k]; }));
    return '<div class="in-yrs" role="img" aria-label="Issues read per month, ' + ys[ys.length - 1] + (ys.length > 1 ? ' to ' + ys[0] : '') + '"><span></span>' +
      MON.map(function (m) { return '<span class="in-yrs-h">' + m[0] + '</span>'; }).join('') +
      ys.map(function (y) {
        return '<span>' + y + '</span>' + MON.map(function (m, i) {
          var n = cells[y + '-' + (i < 9 ? '0' : '') + (i + 1)] || 0;
          return '<i class="' + lvl(n, max) + '" title="' + MONTH[i] + ' ' + y + ': ' + plural(n, 'issue') + '">' + (n || '') + '</i>';
        }).join('');
      }).join('') + '</div>';
  }
  function dayList(days) {
    return '<ul class="in-days">' + Object.keys(days).sort().reverse().map(function (k) {
      return '<li><time datetime="' + k + '">' + nice(k) + '</time><span>' + plural(days[k], 'issue') + '</span></li>';
    }).join('') + '</ul>';
  }
  function strip(items) { return '<ol class="in-strip">' + items.join('') + '</ol>'; }
  function cover(path, title) {
    return '<a class="in-cover" href="' + esc(openHref(path)) + '" aria-label="Open ' + esc(title) + '">' +
      '<img src="' + esc(thumb(path)) + '" alt="" loading="lazy"></a>';
  }
  function strips() {
    var cont = state.cont || [], recent = state.recent || [];
    if (!cont.length && !recent.length) return '';
    var h = '<div class="in-two">';
    if (cont.length) {
      h += '<div><h3>Continue reading</h3>' + strip(cont.map(function (it) {
        var t = stem(it.file_name), p = it.page_number, n = it.total_pages;
        return '<li>' + cover(it.comic_path, t) + '<div class="in-prog" role="progressbar" aria-label="' + esc(t) +
          '" aria-valuenow="' + p + '" aria-valuemin="0" aria-valuemax="' + n + '"><i style="width:' + Math.min(100, p / n * 100) + '%"></i></div>' +
          '<div class="ct" title="' + esc(t) + '">' + esc(t) + '</div><div class="cm">p. ' + fmt(p) + ' of ' + fmt(n) + '</div></li>';
      })) + '</div>';
    }
    if (recent.length) {
      h += '<div><h3>Recently read <a class="in-lk" href="' + esc(URLS.timeline) + '">Timeline</a></h3>' + strip(recent.map(function (it) {
        var t = stem(it.name), k = String(it.read_at || '').slice(0, 10);
        return '<li>' + cover(it.path, t) + '<div class="ct" title="' + esc(t) + '">' + esc(t) + '</div>' +
          (k ? '<div class="cm">' + nice(k) + '</div>' : '') + '</li>';
      })) + '</div>';
    }
    return h + '</div>';
  }
  function whoList(y) {
    var key = state.tab + ':' + y, list = state.who[key];
    var label = TABS.filter(function (t) { return t[0] === state.tab; })[0][1].toLowerCase();
    if (list === undefined) return '<p class="text-body-secondary small">Loading&hellip;</p>';
    if (list === null) return '<p class="text-danger small">Could not load the ' + label + '.</p>';
    if (!list.length) return '<p class="text-body-secondary small">No ' + label + ' recorded for these issues.</p>';
    var field = state.tab;
    return rank('who', list, 10, function (name) { return '/browse/' + field + '/' + encodeURIComponent(name); });
  }
  function loadWho(y) {
    var key = state.tab + ':' + y;
    if (key in state.who) return;
    state.who[key] = undefined;
    fetch('/api/reading-trends/' + state.tab + '?limit=50' + (y === 'all' ? '' : '&year=' + y))
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (list) { state.who[key] = list; })
      .catch(function () { state.who[key] = null; })
      .then(renderReading);
  }

  function renderReading() {
    var box = document.getElementById('inReading'), yrBox = document.getElementById('inYears');
    if (state.error) { box.innerHTML = '<p class="text-danger">Could not load your reading. Reload the page to try again.</p>'; return; }
    var d = state.data;
    if (!d) return;
    var ys = Object.keys(d.years).sort().reverse();
    if (!ys.length) {
      yrBox.innerHTML = '';
      box.replaceChildren(CLU.emptyState({
        icon: 'bi-book', title: 'Nothing read yet',
        message: 'Issues you finish in the reader show up here, with who and what you read most.',
        actions: [{ label: 'Browse the library', href: URLS.home, primary: true }]
      }));
      return;
    }
    var y = state.year;
    yrBox.innerHTML = '<div class="in-yr" role="group" aria-label="Year">' + ys.concat(['all']).map(function (v) {
      return '<button type="button" class="btn btn-sm btn-outline-secondary" data-in-yr="' + v + '" aria-pressed="' + (v === y) + '">' +
        (v === 'all' ? 'All time' : v) + '</button>';
    }).join('') + '</div>';

    var t = y === 'all' ? d.all : d.years[y], days = daysFor(y), label = y === 'all' ? 'all time' : 'in ' + y;
    if (!t.issues) {
      box.replaceChildren(CLU.emptyState({
        icon: 'bi-book', title: 'Nothing read in ' + y + ' yet',
        message: 'Issues you finish in the reader show up here.',
        actions: [{ label: 'Browse the library', href: URLS.home, primary: true }]
      }));
      return;
    }
    var r = runs(days, d.today), nd = Object.keys(days).length, run = '';
    if (r.best >= 2) {
      run = '<p class="text-body-secondary mb-0">' + (r.now >= 2 && r.now === r.best
        ? 'On a ' + r.now + '-day run, your longest ' + label
        : (r.now >= 2 ? 'On a ' + r.now + '-day run · ' : '') + 'Longest ' + label + ': ' + r.best + ' days, to ' + nice(r.bestEnd)) + '</p>';
    }
    var readOn = '<p class="small text-body-secondary mb-2">Read on ' + plural(nd, 'day') + ' ' + label + '</p>';
    var cal = y === 'all' ? monthRows(days, ys) : nd < 7 ? readOn + dayList(days) : nd <= 40 ? readOn + monthRows(days, [y]) : calendar(days, y, d.today);
    var gap = y !== 'all' && t.gap ? '<p class="in-note">' + fmt(t.gap) + ' of ' + plural(t.issues, 'issue') + ' read ' + label +
      ' have no credits, so they are not counted. <button type="button" class="btn btn-link" data-in-backfill>Read credits from ComicInfo</button></p>' : '';

    box.innerHTML =
      '<div><p class="in-lede"><b>' + fmt(t.issues) + '</b> ' + (t.issues === 1 ? 'issue' : 'issues') + ', <b>' + fmt(t.pages) +
      '</b> pages and <b>' + hm(t.seconds) + '</b> of reading ' + label + '.</p>' + run + '</div>' +
      '<div>' + cal + '</div>' + strips() +
      '<div class="in-solo"><h3>Who you read</h3><div class="in-tabs" role="group" aria-label="Rank by">' + TABS.map(function (tb) {
        return '<button type="button" class="btn btn-sm btn-outline-secondary" data-in-tab="' + tb[0] + '" aria-pressed="' + (tb[0] === state.tab) + '">' + tb[1] + '</button>';
      }).join('') + '</div>' + whoList(y) + gap + '</div>';
    var w = box.querySelector('.in-cal-wrap');
    if (w) w.scrollLeft = w.scrollWidth;
  }

  // ── Collection ──────────────────────────────────────────────────────────
  function renderCollection() {
    var el = document.getElementById('inCollectionData');
    var c = JSON.parse(el.textContent), box = document.getElementById('inCollection');
    var pct = c.files ? Math.round(c.read / c.files * 100) : 0;
    var facts = [
      c.read ? '<div><dt>Read</dt><dd><b data-clu-count>' + fmt(c.read) + '</b> of ' + fmt(c.files) + ' · ' + pct + '%<span class="in-meter" aria-hidden="true"><i style="width:' + pct + '%"></i></span></dd></div>' : '',
      c.missing ? '<div><dt>Missing</dt><dd><a href="' + esc(URLS.wanted) + '"><b data-clu-count>' + fmt(c.missing) + '</b> ' + (c.missing === 1 ? 'issue' : 'issues') + ' in ' + fmt(c.missing_series) + ' series' + '</a></dd></div>' : '',
      c.added_30 ? '<div><dt>Dated in the last 30 days</dt><dd><b data-clu-count>' + fmt(c.added_30) + '</b></dd></div>' : ''
    ].join('');

    var am = c.added_per_month, nz = am.filter(function (m) { return m.count; });
    var mLabel = function (k) { return MONTH[+k.slice(5) - 1] + ' ' + k.slice(0, 4); };
    var amax = Math.max.apply(null, am.map(function (m) { return m.count; }));
    var added;
    if (nz.length >= 3) {
      added = '<div class="in-cols" role="img" aria-label="Comics per month by file date, ' + mLabel(am[0].month) + ' to ' + mLabel(am[am.length - 1].month) + ': ' +
        am.map(function (m) { return MON[+m.month.slice(5) - 1] + ' ' + m.count; }).join(', ') + '">' +
        am.map(function (m) { return '<i class="' + (m.count ? '' : 'z') + '" style="height:' + (m.count / amax * 100) + '%" title="' + mLabel(m.month) + ': ' + plural(m.count, 'comic') + '"></i>'; }).join('') +
        '</div><div class="in-cols-l" aria-hidden="true">' + am.map(function (m) {
          return '<span><b>' + (m.count ? fmt(m.count) : '&nbsp;') + '</b>' + MON[+m.month.slice(5) - 1] + '</span>';
        }).join('') + '</div>';
    } else if (!nz.length) {
      added = '<p>No comics are dated in the last twelve months.</p>';
    } else if (nz.length === 1 && nz[0].count === c.files) {
      added = '<p>All ' + fmt(c.files) + ' comics are dated ' + mLabel(nz[0].month) + '.</p>';
    } else {
      added = '<p>' + and(nz.map(function (m) { return fmt(m.count) + ' dated ' + mLabel(m.month); })) + '.</p>';
    }

    var f = c.formats || [], ftot = f.reduce(function (a, x) { return a + x.count; }, 0), formats = '';
    if (f.length === 1) formats = '<p>All ' + fmt(ftot) + ' comics are ' + esc(f[0].type.toUpperCase()) + '.</p>';
    else if (f.length) {
      formats = '<div class="in-share" role="img" aria-label="' + esc(f.map(function (x) { return x.type.toUpperCase() + ' ' + fmt(x.count); }).join(', ')) + '">' +
        f.map(function (x) { return '<i style="flex:' + x.count + '"></i>'; }).join('') + '</div><ul class="in-share-k">' +
        f.map(function (x) { return '<li>' + esc(x.type.toUpperCase()) + ' ' + fmt(x.count) + ' <span>' + Math.max(1, Math.round(x.count / ftot * 100)) + '%</span></li>'; }).join('') + '</ul>';
    }

    var big = c.largest || [], files = state.all.files ? big : big.slice(0, 8);
    box.innerHTML =
      '<div><p class="in-lede"><b>' + fmt(c.files) + '</b> comics in <b>' + fmt(c.folders) + '</b> folders, <b>' + size(c.size) + '</b> on disk.</p></div>' +
      (facts ? '<dl class="in-facts">' + facts + '</dl>' : '') +
      '<div class="in-two"><div><h3>Added per month <span>by file date</span></h3>' + added + '</div><div><h3>Formats</h3>' + formats + '</div></div>' +
      '<div class="in-two"><div><h3>Publishers</h3>' + rank('pubs', c.publishers || [], 8) + '</div>' +
      '<div><h3>Biggest series <span>issues</span></h3>' + rank('series', c.series || [], 8) + '</div></div>' +
      (big.length ? '<div class="in-solo"><h3>Largest files</h3><ol class="in-files">' + files.map(function (x) {
        return '<li><span class="font-monospace n" title="' + esc(x.name) + '">' + esc(x.name) + '</span>' +
          (x.folder ? '<span class="sub">' + esc(x.folder) + '</span>' : '') + '<span class="c">' + size(x.size) + '</span></li>';
      }).join('') + '</ol>' + more('files', big.length, 8) + '</div>' : '');
    // Count the facts up once, on first draw (clu-motion scans only static markup).
    if (!state.counted && window.CLU && CLU.countUp) {
      state.counted = true;
      box.querySelectorAll('[data-clu-count]').forEach(CLU.countUp);
    }
  }

  // ── Read credits from ComicInfo ─────────────────────────────────────────
  var backfilling = false;
  function showSkipped(items) {
    document.getElementById('skippedIssuesList').innerHTML = items.map(function (it) {
      return '<div class="list-group-item d-flex justify-content-between align-items-start gap-2"><div class="text-truncate" title="' +
        esc(it.file) + '">' + esc(it.file) + '</div><span class="badge text-bg-secondary">' + esc(it.reason) + '</span></div>';
    }).join('');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('skippedIssuesModal')).show();
  }
  function finishBackfill(opId, tries) {
    fetch('/api/backfill-reading-metadata/' + encodeURIComponent(opId)).then(function (r) { return r.json(); }).then(function (j) {
      if (j.pending) {
        if (tries > 20) { backfilling = false; return; }
        return setTimeout(function () { finishBackfill(opId, tries + 1); }, 1000);
      }
      backfilling = false;
      var res = j.result;
      if (res.error) return CLU.showError('Could not read credits: ' + res.error);
      var msg = 'Credits read: ' + fmt(res.updated) + ' updated' + (res.skipped ? ', ' + fmt(res.skipped) + ' skipped.' : '.');
      CLU.toast(msg, 'success', res.skipped ? { duration: 10000, action: { label: 'View skipped', onClick: function () { showSkipped(res.skipped_issues); } } } : undefined);
      state.who = {};
      if (root) loadReading();
    }).catch(function () { backfilling = false; });
  }
  function pollBackfill(opId) {
    fetch('/api/operation/' + encodeURIComponent(opId)).then(function (r) { return r.json(); }).then(function (j) {
      var op = j.operation;
      if (op && (op.status === 'running' || op.status === 'queued')) return setTimeout(function () { pollBackfill(opId); }, 1500);
      finishBackfill(opId, 0);
    }).catch(function () { setTimeout(function () { pollBackfill(opId); }, 3000); });
  }
  function startBackfill() {
    if (backfilling) return CLU.toast('Credits are already being read. Progress shows in Active Operations.', 'info');
    backfilling = true;
    fetch('/api/backfill-reading-metadata', { method: 'POST' }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.success) throw new Error(j.error || 'Unknown error');
      CLU.toast('Reading credits from ComicInfo. Progress shows in Active Operations.', 'info');
      pollBackfill(j.op_id);
    }).catch(function (e) {
      backfilling = false;
      CLU.showError('Could not start reading credits: ' + e.message);
    });
  }

  // ── Wiring ──────────────────────────────────────────────────────────────
  function loadReading() {
    fetch('/api/reading-overview').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
      state.data = d;
      state.error = false;
      if (!state.year || (state.year !== 'all' && !d.years[state.year])) {
        var cy = d.today.slice(0, 4), ys = Object.keys(d.years).sort().reverse();
        state.year = d.years[cy] ? cy : (ys[0] || cy);
      }
      renderReading();
      loadWho(state.year);
    }).catch(function () { state.error = true; renderReading(); });
  }
  function getList(url, key, pick) {
    fetch(url).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) { state[key] = j ? pick(j) : []; })
      .catch(function () { state[key] = []; }).then(renderReading);
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-in-backfill]')) { e.preventDefault(); startBackfill(); return; }
    var t = e.target.closest('#insights [data-in-yr], #insights [data-in-tab], #insights [data-in-all]');
    if (!t) return;
    if (t.dataset.inYr) { state.year = t.dataset.inYr; renderReading(); loadWho(state.year); }
    else if (t.dataset.inTab) { state.tab = t.dataset.inTab; renderReading(); loadWho(state.year); }
    else {
      var k = t.dataset.inAll;
      state.all[k] = !state.all[k];
      if (k === 'who') renderReading(); else renderCollection();
    }
  });

  if (!root) return;
  renderCollection();
  loadReading();
  getList('/api/continue-reading?limit=12', 'cont', function (j) { return j.items || []; });
  getList('/api/recently-read?limit=12', 'recent', function (j) { return j; });
})();
