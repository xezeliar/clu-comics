/**
 * CLU CBZ Info Viewer  –  clu-cbz-info.js
 *
 * CBZ metadata viewer modal with optional navigation and page preview.
 * Provides: CLU.showCBZInfo, CLU.navigateCBZPrev, CLU.navigateCBZNext,
 *           CLU.cbzPagePrev, CLU.cbzPageNext
 *
 * Depends on: clu-utils.js (CLU.showToast, CLU.showError, CLU.showSuccess,
 *             CLU.formatFileSize, CLU.escapeHtml, CLU.splitCreditList)
 *
 * External contract:
 *   window._cluCbzInfo = {
 *     onClearComplete(path)      // called after successful ComicInfo.xml removal
 *     onMetadataSaved(path, ci)  // optional; called after hand-edited metadata is saved
 *   }
 *
 * DOM contracts (all from partials/modal_cbz_info.html, styled by css/cbz-info.css):
 *   #cbzInfoModal; header #cbzInfoModalLabel, #cbzInfoSub, #cbzInfoFileName,
 *   #cbzNavButtons (#cbzPrevBtn, #cbzNavPos, #cbzNextBtn); body #cbzInfoContent;
 *   footer #cbzInfoFooter (Delete ComicInfo.xml, unsaved count, Discard, Save)
 *   #clearComicInfoConfirmModal  (same partial) – required before ComicInfo.xml
 *   can be deleted; #clearComicInfoFileName, #confirmClearComicInfoBtn
 *   #cbzDiscardEditsModal  (same partial) – asked before Prev/Next drops staged
 *   metadata edits; #cbzDiscardEditsCount, #cbzConfirmDiscardEditsBtn
 *
 * Metadata editing: every row has a labelled pencil button ("Edit Writer");
 * clicking the value text is a pointer shortcut and F2 edits the focused row.
 * Edits are staged in _pendingEdits and written in ONE archive rebuild by
 * POST /cbz-update-comicinfo (a blank value removes the tag).
 */
(function () {
  'use strict';

  var CLU = window.CLU = window.CLU || {};

  function _getContract() { return window._cluCbzInfo || {}; }

  // ── Module state ──────────────────────────────────────────────────────────

  var _currentFilePath = '';
  var _currentFileName = '';
  var _currentDirectory = '';
  var _currentFileList = [];
  var _currentIndex = -1;
  var _currentData = null;        // last /cbz-metadata response

  // Page viewer state
  var _viewerPath = null;
  var _viewerPageCount = 0;
  var _viewerCurrentPage = 0;
  var _viewerPreloadedPages = {};

  // Metadata editing state
  var _currentComicInfo = {};     // tags as last read from the archive
  var _hasComicInfo = false;      // archive has a ComicInfo.xml at all
  var _currentProvider = null;    // core.comicinfo.provider_from_notes, from the route
  var _pendingEdits = {};         // key -> staged value ('' removes the tag)
  var _expanded = {};             // key -> long list / summary opened in place
  var _saving = false;
  var _afterDiscard = null;       // continuation for #cbzDiscardEditsModal
  var _SHOW_EMPTY_KEY = 'cluCbzShowEmptyFields';
  var _showEmptyFields = false;
  try { _showEmptyFields = localStorage.getItem(_SHOW_EMPTY_KEY) === '1'; } catch (e) { /* storage unavailable */ }

  var _MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];
  var _PROVIDER_LABELS = {
    metron: 'Metron', comicvine: 'ComicVine', comicvine_sqlite: 'ComicVine (Local DB)',
    gcd: 'GCD', gcd_api: 'GCD REST API', inducks: 'INDUCKS', anilist: 'AniList',
    bedetheque: 'Bedetheque', mangadex: 'MangaDex', mangaupdates: 'MangaUpdates'
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  function _encodePathForReader(path) {
    var clean = path.charAt(0) === '/' ? path.substring(1) : path;
    return clean.split('/').map(function (c) { return encodeURIComponent(c); }).join('/');
  }

  function _el(id) { return document.getElementById(id); }

  function _plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  // ── Field groups definition ───────────────────────────────────────────────
  //
  // `input` picks the editor: 'number' (a text box with a numeric keypad, so a
  // non-numeric value such as Volume "v2" is never blanked by the browser),
  // 'textarea', or 'select' with `options`. Default is a plain text box.
  // `parts` makes one row of several tags (Cover date = Year, Month, Day).
  // Keys must stay within EDITABLE_COMICINFO_FIELDS in routes/metadata.py.

  var _YES_NO_OPTIONS = ['', 'Unknown', 'No', 'Yes'];
  var _MANGA_OPTIONS = ['', 'Unknown', 'No', 'Yes', 'YesAndRightToLeft'];
  var _AGE_RATING_OPTIONS = [
    '', 'Unknown', 'Adults Only 18+', 'Early Childhood', 'Everyone', 'Everyone 10+',
    'G', 'Kids to Adults', 'M', 'MA15+', 'Mature 17+', 'PG', 'R18+',
    'Rating Pending', 'Teen', 'X18+'
  ];

  var _fieldGroups = [
    {
      title: 'Issue',
      fields: [
        { key: 'Series', label: 'Series' },
        { key: 'Number', label: 'Number' },
        { key: 'Title', label: 'Title' },
        { key: 'Volume', label: 'Volume', input: 'number' },
        { key: 'Count', label: 'Count', input: 'number' },
        { key: 'AlternateSeries', label: 'Alternate series' },
        { key: 'AlternateNumber', label: 'Alternate number' },
        { key: 'AlternateCount', label: 'Alternate count', input: 'number' },
        { key: 'Year', label: 'Cover date', parts: ['Year', 'Month', 'Day'] }
      ]
    },
    {
      title: 'Publication',
      fields: [
        { key: 'Publisher', label: 'Publisher' },
        { key: 'Imprint', label: 'Imprint' },
        { key: 'Format', label: 'Format' },
        { key: 'PageCount', label: 'Pages', input: 'number' },
        { key: 'LanguageISO', label: 'Language' },
        { key: 'AgeRating', label: 'Age rating', input: 'select', options: _AGE_RATING_OPTIONS },
        { key: 'MetronId', label: 'Metron ID' }
      ]
    },
    {
      title: 'Credits',
      fields: [
        { key: 'Writer', label: 'Writer', browse: 'writer' },
        { key: 'Penciller', label: 'Penciller', browse: 'penciller' },
        { key: 'Inker', label: 'Inker', list: true },
        { key: 'Colorist', label: 'Colorist', list: true },
        { key: 'Letterer', label: 'Letterer', list: true },
        { key: 'CoverArtist', label: 'Cover artists', list: true },
        { key: 'Editor', label: 'Editors', list: true },
        { key: 'Translator', label: 'Translator', list: true }
      ]
    },
    {
      title: 'Story',
      fields: [
        { key: 'Characters', label: 'Characters', browse: 'characters' },
        { key: 'Teams', label: 'Teams', list: true },
        { key: 'Locations', label: 'Locations', list: true },
        { key: 'MainCharacterOrTeam', label: 'Main character' },
        { key: 'StoryArc', label: 'Story arc' },
        { key: 'Genre', label: 'Genre', list: true },
        { key: 'SeriesGroup', label: 'Series group' }
      ]
    },
    {
      title: 'About',
      fields: [
        { key: 'Summary', label: 'Summary', input: 'textarea' },
        { key: 'Notes', label: 'Notes', input: 'textarea' },
        { key: 'Web', label: 'Web', url: true },
        { key: 'ScanInformation', label: 'Scan information', input: 'textarea' },
        { key: 'Review', label: 'Review', input: 'textarea' },
        { key: 'CommunityRating', label: 'Rating', input: 'number' },
        { key: 'BlackAndWhite', label: 'Black & white', input: 'select', options: _YES_NO_OPTIONS },
        { key: 'Manga', label: 'Manga', input: 'select', options: _MANGA_OPTIONS }
      ]
    }
  ];

  var _fieldByKey = {};
  _fieldGroups.forEach(function (g) {
    g.fields.forEach(function (f) { _fieldByKey[f.key] = f; });
  });

  // ── Navigation ────────────────────────────────────────────────────────────

  function _updateNavButtons() {
    var navButtons = _el('cbzNavButtons');
    if (!navButtons) return;
    var on = _currentFileList.length > 1 && _currentIndex >= 0;
    navButtons.classList.toggle('d-none', !on);
    if (!on) return;
    _el('cbzPrevBtn').disabled = _currentIndex <= 0;
    _el('cbzNextBtn').disabled = _currentIndex >= _currentFileList.length - 1;
    var pos = _el('cbzNavPos');
    if (pos) pos.textContent = (_currentIndex + 1) + ' of ' + _currentFileList.length;
  }

  /** Run `proceed` now, or after the user agrees to drop staged metadata edits. */
  function _guardPendingEdits(proceed) {
    var count = Object.keys(_pendingEdits).length;
    var el = _el('cbzDiscardEditsModal');
    if (count === 0 || !el) { proceed(); return; }

    var countEl = _el('cbzDiscardEditsCount');
    if (countEl) countEl.textContent = _plural(count, 'unsaved change');
    _afterDiscard = proceed;

    var modal = bootstrap.Modal.getInstance(el);
    if (!modal) modal = new bootstrap.Modal(el);
    modal.show();
  }

  function _doDiscardAndProceed() {
    var el = _el('cbzDiscardEditsModal');
    var modal = el && bootstrap.Modal.getInstance(el);
    if (modal) modal.hide();
    _pendingEdits = {};
    var proceed = _afterDiscard;
    _afterDiscard = null;
    if (typeof proceed === 'function') proceed();
  }

  CLU.navigateCBZPrev = function () {
    if (_currentIndex > 0) _guardPendingEdits(function () { _navigateTo(_currentIndex - 1); });
  };

  CLU.navigateCBZNext = function () {
    if (_currentIndex < _currentFileList.length - 1) _guardPendingEdits(function () { _navigateTo(_currentIndex + 1); });
  };

  function _navigateTo(index) {
    if (index < 0 || index >= _currentFileList.length) return;
    _currentIndex = index;
    var fn = _currentFileList[index];
    CLU.showCBZInfo(_currentDirectory + '/' + fn, fn, {
      directoryPath: _currentDirectory,
      fileList: _currentFileList
    });
  }

  // ── Page viewer ───────────────────────────────────────────────────────────

  function _setPageInfo(pageNum, dims) {
    var info = _el('cbzPageInfo');
    if (!info) return;
    var total = _viewerPageCount || (_currentData && _currentData.image_files) || 0;
    info.innerHTML = (total ? 'Page ' + (pageNum + 1) + ' of ' + total : '') +
      (dims ? '<br>' + CLU.escapeHtml(dims) : '');
  }

  /** Swap the shown image once the new one has loaded (no blank flash). */
  function _showImage(src, alt, onDone) {
    var img = new Image();
    img.alt = alt;
    img.onload = function () {
      var container = _el('cbzPreviewContainer');
      if (!container) return;
      container.innerHTML = '';
      container.appendChild(img);
      if (onDone) onDone(img);
    };
    img.onerror = function () {
      var container = _el('cbzPreviewContainer');
      if (container) container.innerHTML = '<p class="text-body-secondary small mb-0">Preview not available</p>';
    };
    img.src = src;
  }

  function _loadCbzPage(pageNum) {
    if (!_viewerPath || pageNum < 0 || pageNum >= _viewerPageCount) return;
    var path = _viewerPath;
    _viewerCurrentPage = pageNum;
    _updatePageButtons();
    _showImage('/api/read/' + _encodePathForReader(path) + '/page/' + pageNum, 'Page ' + (pageNum + 1), function (img) {
      if (path !== _viewerPath || pageNum !== _viewerCurrentPage) return;
      _fetchPageInfo(pageNum, img.naturalWidth, img.naturalHeight);
    });
  }

  function _fetchPageInfo(pageNum, width, height) {
    var dims = width + ' × ' + height;
    _setPageInfo(pageNum, dims);
    fetch('/api/read/' + _encodePathForReader(_viewerPath) + '/page/' + pageNum + '/info')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success || pageNum !== _viewerCurrentPage) return;
        _setPageInfo(pageNum, dims + (data.file_size ? ' · ' + CLU.formatFileSize(data.file_size) : ''));
        var info = _el('cbzPageInfo');
        if (info && data.file_name) info.title = data.file_name;
      })
      .catch(function () { /* the dimensions are already shown */ });
  }

  function _preloadPages(currentPage) {
    [currentPage + 1, currentPage + 2, currentPage - 1].forEach(function (pn) {
      if (pn >= 0 && pn < _viewerPageCount && !_viewerPreloadedPages[pn]) {
        var img = new Image();
        img.src = '/api/read/' + _encodePathForReader(_viewerPath) + '/page/' + pn;
        _viewerPreloadedPages[pn] = true;
      }
    });
  }

  function _updatePageButtons() {
    var prevBtn = document.querySelector('#cbzInfoModal .cbz-page-prev');
    var nextBtn = document.querySelector('#cbzInfoModal .cbz-page-next');
    var many = _viewerPageCount > 1;
    if (prevBtn) { prevBtn.disabled = _viewerCurrentPage <= 0; prevBtn.classList.toggle('invisible', !many); }
    if (nextBtn) { nextBtn.disabled = _viewerCurrentPage >= _viewerPageCount - 1; nextBtn.classList.toggle('invisible', !many); }
  }

  function _initPageViewer(filePath) {
    fetch('/api/read/' + _encodePathForReader(filePath) + '/info')
      .then(function (r) { return r.json(); })
      .then(function (info) {
        if (filePath !== _currentFilePath) return;
        _viewerPath = filePath;
        _viewerPageCount = info.page_count || 0;
        _viewerCurrentPage = 0;
        _viewerPreloadedPages = {};
        _updatePageButtons();
        if (_viewerPageCount > 1) _preloadPages(0);
      })
      .catch(function (err) {
        console.error('Error initializing page viewer:', err);
      });
  }

  function _resetPageViewer() {
    _viewerPath = null;
    _viewerPageCount = 0;
    _viewerCurrentPage = 0;
    _viewerPreloadedPages = {};
  }

  function _handleKeydown(e) {
    var modal = _el('cbzInfoModal');
    if (!modal || !modal.classList.contains('show')) return;
    // Don't flip pages behind the clear-ComicInfo confirmation stacked on top
    var confirmModal = _el('clearComicInfoConfirmModal');
    if (confirmModal && confirmModal.classList.contains('show')) return;
    var discardModal = _el('cbzDiscardEditsModal');
    if (discardModal && discardModal.classList.contains('show')) return;
    // Arrows and Space belong to a metadata editor while one has focus --
    // otherwise typing a space into Title flips the preview page.
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
              t.tagName === 'SELECT' || t.isContentEditable)) return;
    // Space on a focused button or summary is that control's own click.
    if (e.code === 'Space' && t && t.closest && t.closest('button, summary, a')) return;
    if (e.key === 'ArrowLeft') { CLU.cbzPagePrev(); }
    else if (e.key === 'ArrowRight' || e.code === 'Space') { e.preventDefault(); CLU.cbzPageNext(); }
  }

  CLU.cbzPagePrev = function () {
    if (_viewerCurrentPage > 0) {
      _loadCbzPage(_viewerCurrentPage - 1);
      _preloadPages(_viewerCurrentPage);
    }
  };

  CLU.cbzPageNext = function () {
    if (_viewerCurrentPage < _viewerPageCount - 1) {
      _loadCbzPage(_viewerCurrentPage + 1);
      _preloadPages(_viewerCurrentPage);
    }
  };

  // ── Clear ComicInfo.xml ───────────────────────────────────────────────────

  /** Open the confirmation modal; the delete itself runs from its confirm button. */
  function _promptClearComicInfoXml() {
    if (!_currentFilePath) {
      CLU.showError('No CBZ file is currently selected.');
      return;
    }

    var el = document.getElementById('clearComicInfoConfirmModal');
    if (!el) {
      // The partial that owns the confirmation is missing — refuse rather than
      // delete metadata unconfirmed.
      console.error('#clearComicInfoConfirmModal not found; include partials/modal_cbz_info.html');
      CLU.showError('Unable to confirm this deletion.');
      return;
    }

    var nameEl = document.getElementById('clearComicInfoFileName');
    if (nameEl) nameEl.textContent = _currentFilePath.split('/').pop();

    var modal = bootstrap.Modal.getInstance(el);
    if (!modal) modal = new bootstrap.Modal(el);
    modal.show();
  }

  function _doClearComicInfoXml() {
    if (!_currentFilePath) return;

    var el = document.getElementById('clearComicInfoConfirmModal');
    var modal = el && bootstrap.Modal.getInstance(el);
    if (modal) modal.hide();

    fetch('/cbz-clear-comicinfo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: _currentFilePath })
    })
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (result.success) {
          CLU.showSuccess('ComicInfo.xml has been successfully deleted.');
          var fn = _currentFilePath.split('/').pop();
          var opts = {};
          if (_currentDirectory && _currentFileList.length > 0) {
            opts.directoryPath = _currentDirectory;
            opts.fileList = _currentFileList;
          }
          CLU.showCBZInfo(_currentFilePath, fn, opts);

          var contract = _getContract();
          if (typeof contract.onClearComplete === 'function') {
            contract.onClearComplete(_currentFilePath);
          }
        } else {
          CLU.showError(result.error || 'Failed to delete ComicInfo.xml');
        }
      })
      .catch(function (err) {
        console.error('Error clearing ComicInfo.xml:', err);
        CLU.showError('An error occurred while trying to delete ComicInfo.xml.');
      });
  }

  // ── Render helpers ────────────────────────────────────────────────────────

  function _isBlank(value) {
    return value === undefined || value === null || String(value).trim() === '';
  }

  function _has(obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); }

  /** The raw tag text as the archive has it ('' when absent). */
  function _originalValue(key) {
    var v = _currentComicInfo[key];
    return _isBlank(v) ? '' : String(v);
  }

  /** The value the user currently sees: a staged edit wins over the archive. */
  function _effectiveValue(key) {
    return _has(_pendingEdits, key) ? _pendingEdits[key] : _originalValue(key);
  }

  function _parts(field) { return field.parts || [field.key]; }

  function _fieldDirty(field) {
    return _parts(field).some(function (k) { return _has(_pendingEdits, k); });
  }

  function _fieldBlank(field) {
    return _parts(field).every(function (k) { return _isBlank(_effectiveValue(k)); });
  }

  function _escapeAttr(text) {
    return CLU.escapeHtml(String(text)).replace(/"/g, '&quot;');
  }

  function _monthName(m) {
    var n = /^\s*\d{1,2}\s*$/.test(m) ? parseInt(m, 10) : 0;
    return n >= 1 && n <= 12 ? _MONTHS[n - 1] : m;
  }

  /** "1 April 2023" from Year / Month / Day, using whichever are set. */
  function _coverDate() {
    return [_effectiveValue('Day'), _monthName(_effectiveValue('Month')), _effectiveValue('Year')]
      .filter(function (v) { return !_isBlank(v); }).join(' ');
  }

  function _moreButton(key, label) {
    return ' <button type="button" class="ci-mo" data-cbz-action="more" data-key="' + key + '">' + label + '</button>';
  }

  /** Display HTML for one value (never the editor's seed -- that stays raw). */
  function _formatValue(field, value) {
    if (field.parts) return CLU.escapeHtml(_coverDate());
    if (field.key === 'PageCount') {
      var n = parseInt(value, 10);
      return CLU.escapeHtml(isNaN(n) ? value : _plural(n, 'page'));
    }
    if (field.key === 'BlackAndWhite' || field.key === 'Manga') {
      if (value === 'YesAndRightToLeft') return 'Yes (Right to Left)';
      if (value === 'Yes' || value === 'No') return value;
      return 'Unknown';
    }
    if (field.key === 'CommunityRating' && parseFloat(value) > 0) {
      return CLU.escapeHtml(value) + '/5';
    }
    if (field.url && /^https?:\/\/\S+$/i.test(value)) {
      var shown = value.replace(/^https?:\/\//i, '').replace(/\/$/, '');
      if (shown.length > 34) shown = shown.slice(0, 33) + '…';
      return '<a href="' + _escapeAttr(value) + '" target="_blank" rel="noopener noreferrer">' +
        CLU.escapeHtml(shown) + ' <i class="bi bi-box-arrow-up-right small" aria-hidden="true"></i>' +
        '<span class="visually-hidden"> (opens in a new tab)</span></a>';
    }
    // Comma-separated name lists: drop the tagger's "[3258]" provider IDs so a
    // 20-character cast reads as names rather than noise, link the ones
    // /browse/<category>/<name> can resolve, and show three before "+N more".
    if (field.browse || field.list) {
      var names = CLU.splitCreditList(value);
      // Nothing left once IDs were stripped: show the raw text so the field
      // can still be seen and edited.
      if (!names.length) return CLU.escapeHtml(value);
      var cut = names.length > 3 && !_expanded[field.key];
      var html = (cut ? names.slice(0, 3) : names).map(function (nm) {
        if (!field.browse) return CLU.escapeHtml(nm);
        var page = { writer: 'creators', penciller: 'creators', characters: 'characters' }[field.browse];
        return '<a href="/' + (page || 'browse/' + field.browse) + '/' +
          encodeURIComponent(nm) + '">' + CLU.escapeHtml(nm) + '</a>';
      }).join(', ');
      return html + (cut ? _moreButton(field.key, '+' + (names.length - 3) + ' more') : '');
    }
    if (field.input === 'textarea') {
      var long = value.length > 150;
      return '<span class="' + (long && !_expanded[field.key] ? 'ci-clamp' : 'ci-long') + '">' +
        CLU.escapeHtml(value) + '</span>' +
        (long ? _moreButton(field.key, _expanded[field.key] ? 'Less' : 'More') : '');
    }
    return CLU.escapeHtml(value);
  }

  function _renderRow(field) {
    var dirty = _fieldDirty(field);
    var display = _fieldBlank(field)
      ? '<span class="ci-empty">Not set</span>'
      : _formatValue(field, _effectiveValue(field.key));
    var label = _escapeAttr(field.label);
    return '<div class="ci-row' + (dirty ? ' ci-dirty' : '') + '" data-key="' + field.key + '">' +
      '<dt>' + label + (dirty ? '<span class="visually-hidden"> (edited)</span>' : '') + '</dt>' +
      '<dd><span class="ci-v" data-key="' + field.key + '">' + display + '</span>' +
        '<button type="button" class="ci-pen" data-cbz-edit="' + field.key + '" ' +
          'aria-label="Edit ' + label + '" title="Edit ' + label + '">' +
          '<i class="bi bi-pencil" aria-hidden="true"></i></button></dd>' +
      '</div>';
  }

  function _renderFieldGroups(showEmpty) {
    var html = '';
    _fieldGroups.forEach(function (group) {
      var visible = group.fields.filter(function (f) {
        return showEmpty || !_fieldBlank(f) || _fieldDirty(f);
      });
      if (visible.length === 0) return;
      html += '<div class="ci-g"><h6>' + group.title + '</h6><dl class="ci-dl">' +
        visible.map(_renderRow).join('') + '</dl></div>';
    });
    return html;
  }

  function _pendingCount() { return Object.keys(_pendingEdits).length; }

  function _emptyCount() {
    var n = 0;
    _fieldGroups.forEach(function (g) {
      g.fields.forEach(function (f) { if (_fieldBlank(f) && !_fieldDirty(f)) n++; });
    });
    return n;
  }

  function _showEmptyLabel() { return 'Show ' + _plural(_emptyCount(), 'empty field'); }

  function _providerText() {
    if (!_hasComicInfo || !_currentProvider) return '';
    if (_currentProvider === 'manual') return 'edited by hand';
    return 'tagged by ' + (_PROVIDER_LABELS[_currentProvider] || _currentProvider);
  }

  /** Inner HTML of #cbzComicInfoSection: heading, switch, hint, and the field list. */
  function _renderComicInfoSection() {
    var showEmpty = !_hasComicInfo || _showEmptyFields;
    var prov = _providerText();
    var html = '<div class="ci-mbar"><h6>ComicInfo.xml' +
      (prov ? ' <span>· ' + CLU.escapeHtml(prov) + '</span>' : '') + '</h6>';
    if (_hasComicInfo && _emptyCount() > 0) {
      html +=
        '<div class="form-check form-switch">' +
          '<input class="form-check-input" type="checkbox" role="switch" id="cbzShowEmptyFields"' +
            (_showEmptyFields ? ' checked' : '') + '>' +
          '<label class="form-check-label" for="cbzShowEmptyFields" id="cbzShowEmptyLabel">' +
            _showEmptyLabel() + '</label>' +
        '</div>';
    }
    html += '</div>';
    html += _hasComicInfo
      ? '<p class="ci-hint"><span class="ci-c">Click any value to edit it, or Tab to its pencil.</span>' +
        '<span class="ci-t">Tap a value, or its pencil, to edit it.</span></p>'
      : '<p class="ci-note">This file has no ComicInfo.xml. Fill in any field below and Save writes one into the archive.</p>';
    return html + _renderFieldGroups(showEmpty);
  }

  /** Header: "Series #Number", then Title · Publisher · cover date · pages, then the filename. */
  function _refreshHeader() {
    var title = _el('cbzInfoModalLabel');
    var sub = _el('cbzInfoSub');
    var fnEl = _el('cbzInfoFileName');
    var series = _effectiveValue('Series');
    var heading = _currentFileName.replace(/\.(cbz|zip)$/i, '');
    var bits = [];
    if (_currentData) {
      if (_hasComicInfo && series) {
        heading = series + (_effectiveValue('Number') ? ' #' + _effectiveValue('Number') : '');
      }
      if (_hasComicInfo) {
        var month = _effectiveValue('Month');
        var pages = _effectiveValue('PageCount') || _currentData.image_files;
        bits = [_effectiveValue('Title'), _effectiveValue('Publisher'),
          [month ? _monthName(month) : '', _effectiveValue('Year')].join(' ').trim(),
          pages ? _plural(parseInt(pages, 10) || 0, 'page') : ''];
      } else {
        bits = ['No ComicInfo.xml'];
      }
    }
    if (title) title.textContent = heading || 'CBZ Information';
    if (sub) {
      sub.innerHTML = bits.filter(function (b) { return !_isBlank(b); })
        .map(function (b) { return '<span>' + CLU.escapeHtml(b) + '</span>'; }).join('');
    }
    if (fnEl) fnEl.textContent = _currentData ? _currentFileName : '';
  }

  function _refreshComicInfoSection() {
    var section = _el('cbzComicInfoSection');
    if (section) section.innerHTML = _renderComicInfoSection();
    _refreshHeader();
    _refreshFooter();
  }

  /**
   * Footer: Delete ComicInfo.xml on the left; Close, or "N unsaved changes ·
   * Discard · Save changes". Rebuilt only when its shape changes, otherwise
   * the count is updated in place: an editor's blur refreshes it on mousedown
   * of Save, and swapping the button out between mousedown and mouseup would
   * swallow that click.
   */
  function _refreshFooter() {
    var footer = _el('cbzInfoFooter');
    if (!footer) return;
    var n = _pendingCount();
    var dirty = n > 0 || _saving;
    var sig = [!!_currentData, _hasComicInfo, dirty, _saving].join('|');
    if (footer.getAttribute('data-sig') === sig) {
      var count = footer.querySelector('.ci-dirty-n');
      if (count) count.textContent = _plural(n, 'unsaved change');
      return;
    }
    footer.setAttribute('data-sig', sig);
    var html = _currentData && _hasComicInfo
      ? '<button type="button" class="btn btn-link ci-del" data-cbz-action="clear">' +
          '<i class="bi bi-eraser" aria-hidden="true"></i>Delete ComicInfo.xml</button>'
      : '<span class="ci-spacer"></span>';
    if (dirty) {
      html += '<span class="ci-dirty-n" aria-live="polite">' + _plural(n, 'unsaved change') + '</span>' +
        '<button type="button" class="btn btn-outline-secondary" data-cbz-action="discard"' +
          (_saving ? ' disabled' : '') + '>Discard</button>' +
        '<button type="button" class="btn btn-primary" data-cbz-action="save"' +
          (_saving ? ' disabled' : '') + '>' +
          (_saving ? '<span class="spinner-border spinner-border-sm me-1" role="status"></span>Saving…' : 'Save changes') +
        '</button>';
    } else {
      html += '<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>';
    }
    footer.innerHTML = html;
  }

  // ── Click-to-edit ─────────────────────────────────────────────────────────

  function _buildEditor(field, value) {
    var el;
    if (field.input === 'select') {
      el = document.createElement('select');
      el.className = 'form-select form-select-sm cbz-ci-editor';
      var opts = field.options.slice();
      // Keep a non-standard value the file already has selectable.
      if (value && opts.indexOf(value) === -1) opts.push(value);
      opts.forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o;
        opt.textContent = o === '' ? '(none)' : (o === 'YesAndRightToLeft' ? 'Yes (Right to Left)' : o);
        el.appendChild(opt);
      });
    } else if (field.input === 'textarea') {
      el = document.createElement('textarea');
      el.className = 'form-control form-control-sm cbz-ci-editor';
      el.rows = 4;
    } else {
      el = document.createElement('input');
      el.type = 'text';
      el.className = 'form-control form-control-sm cbz-ci-editor';
      if (field.input === 'number') el.inputMode = 'decimal';
    }
    el.value = value;
    el.setAttribute('aria-label', field.label);
    el.setAttribute('data-part', field.key);
    return el;
  }

  /** The editor(s) for a row: one control, or Year / Month / Day for Cover date. */
  function _buildEditors(field) {
    var wrap = document.createElement('div');
    if (field.parts) {
      wrap.className = 'ci-date';
      field.parts.forEach(function (k) {
        var label = document.createElement('label');
        label.textContent = k;
        label.appendChild(_buildEditor({ key: k, label: k, input: 'number' }, _effectiveValue(k)));
        wrap.appendChild(label);
      });
      return wrap;
    }
    wrap.appendChild(_buildEditor(field, _effectiveValue(field.key)));
    if (field.input === 'textarea') {
      var hint = document.createElement('p');
      hint.className = 'ci-ed-k';
      hint.textContent = 'Ctrl+Enter keeps it, Escape puts it back';
      wrap.appendChild(hint);
    }
    return wrap;
  }

  function _startEdit(key) {
    if (_saving) return;
    var field = _fieldByKey[key];
    var content = _el('cbzInfoContent');
    var row = content && content.querySelector('.ci-row[data-key="' + key + '"]');
    if (!field || !row || row.classList.contains('ci-editing')) return;

    // Typing stages live, so Escape has to put the staged state back.
    var before = {};
    _parts(field).forEach(function (k) {
      if (_has(_pendingEdits, k)) before[k] = _pendingEdits[k];
    });
    var done = false;
    var dd = row.querySelector('dd');
    var editors = _buildEditors(field);
    var controls = editors.querySelectorAll('[data-part]');

    function finish(commit) {
      if (done) return null;
      done = true;
      _parts(field).forEach(function (k) { delete _pendingEdits[k]; });
      if (commit) {
        Array.prototype.forEach.call(controls, function (c) { _stageEdit(c.getAttribute('data-part'), c.value); });
      } else {
        Object.keys(before).forEach(function (k) { _pendingEdits[k] = before[k]; });
      }
      var fresh = document.createElement('div');
      fresh.innerHTML = _renderRow(field);
      var newRow = fresh.firstChild;
      if (row.parentNode) row.parentNode.replaceChild(newRow, row);
      var label = _el('cbzShowEmptyLabel');
      if (label) label.textContent = _showEmptyLabel();
      _refreshHeader();
      _refreshFooter();
      return newRow;
    }

    function finishAndFocus(commit) {
      var r = finish(commit);
      var pen = r && r.querySelector('.ci-pen');
      if (pen) pen.focus();
    }

    row.addEventListener('keydown', function (e) {
      if (done || !e.target.hasAttribute('data-part')) return;
      if (e.key === 'Escape') {
        // Keep Bootstrap from closing the whole modal.
        e.preventDefault();
        e.stopPropagation();
        finishAndFocus(false);
      } else if (e.key === 'Enter' && (e.target.tagName !== 'TEXTAREA' || e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        finishAndFocus(true);
      }
    });
    // Stage as the user types so Save is already in the footer to click.
    row.addEventListener('input', function (e) {
      if (done || !e.target.hasAttribute('data-part')) return;
      _stageEdit(e.target.getAttribute('data-part'), e.target.value);
      _refreshFooter();
    });
    // Commit when focus leaves the row, not each control (Cover date has three).
    row.addEventListener('focusout', function (e) {
      if (!row.contains(e.relatedTarget)) finish(true);
    });
    if (field.input === 'select') {
      row.addEventListener('change', function () { finishAndFocus(true); });
    }

    dd.innerHTML = '';
    dd.appendChild(editors);
    row.classList.add('ci-editing');
    controls[0].focus();
    if (controls[0].select && field.input !== 'select') controls[0].select();
  }

  function _stageEdit(key, value) {
    var v = String(value == null ? '' : value).trim();
    if (v === _originalValue(key)) delete _pendingEdits[key];
    else _pendingEdits[key] = v;
  }

  function _saveEdits() {
    if (_saving || _pendingCount() === 0 || !_currentFilePath) return;
    var path = _currentFilePath;
    var updates = {};
    Object.keys(_pendingEdits).forEach(function (k) { updates[k] = _pendingEdits[k]; });

    _saving = true;
    _refreshFooter();

    fetch('/cbz-update-comicinfo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path, updates: updates })
    })
      .then(function (r) {
        return r.json().catch(function () { return { success: false, error: 'HTTP ' + r.status }; });
      })
      .then(function (result) {
        _saving = false;
        if (path !== _currentFilePath) return;   // navigated away mid-save
        if (result.success) {
          _pendingEdits = {};
          _currentComicInfo = result.comicinfo || {};
          _hasComicInfo = Object.keys(_currentComicInfo).length > 0;
          _currentProvider = result.provider || null;
          _refreshComicInfoSection();
          CLU.showSuccess('Metadata saved');
          var contract = _getContract();
          if (typeof contract.onMetadataSaved === 'function') {
            contract.onMetadataSaved(path, _currentComicInfo);
          }
        } else {
          _refreshFooter();
          CLU.showError(result.error || 'Failed to save metadata');
        }
      })
      .catch(function (err) {
        _saving = false;
        _refreshFooter();
        console.error('Error saving ComicInfo.xml:', err);
        CLU.showError('An error occurred while saving metadata.');
      });
  }

  function _copyPath() {
    var done = function () { CLU.showSuccess('Path copied'); };
    var fail = function () { CLU.showError('Could not copy the path. Select it and copy it instead.'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(_currentFilePath).then(done, fail);
    } else {
      fail();
    }
  }

  /** Delegated handlers for #cbzInfoContent and #cbzInfoFooter (bound once; content is re-rendered). */
  function _onActionClick(e) {
    var actionEl = e.target.closest('[data-cbz-action]');
    if (actionEl) {
      var action = actionEl.getAttribute('data-cbz-action');
      if (action === 'save') _saveEdits();
      else if (action === 'discard') { _pendingEdits = {}; _refreshComicInfoSection(); }
      else if (action === 'clear') _promptClearComicInfoXml();
      else if (action === 'copy') _copyPath();
      else if (action === 'page-prev') CLU.cbzPagePrev();
      else if (action === 'page-next') CLU.cbzPageNext();
      else if (action === 'more') {
        var key = actionEl.getAttribute('data-key');
        _expanded[key] = !_expanded[key];
        var row = actionEl.closest('.ci-row');
        if (row && !row.classList.contains('ci-editing')) {
          var fresh = document.createElement('div');
          fresh.innerHTML = _renderRow(_fieldByKey[key]);
          row.parentNode.replaceChild(fresh.firstChild, row);
        }
      }
      return;
    }
    var pen = e.target.closest('[data-cbz-edit]');
    if (pen) { _startEdit(pen.getAttribute('data-cbz-edit')); return; }
    if (e.target.closest('a')) return;   // browse and web links still navigate
    // Clicking the value text is a pointer shortcut for its pencil.
    var span = e.target.closest('.ci-v');
    if (span) _startEdit(span.getAttribute('data-key'));
  }

  function _onContentKeydown(e) {
    if (e.key !== 'F2') return;
    var row = e.target.closest && e.target.closest('.ci-row:not(.ci-editing)');
    if (row) {
      e.preventDefault();
      _startEdit(row.getAttribute('data-key'));
    }
  }

  function _onContentChange(e) {
    if (e.target && e.target.id === 'cbzShowEmptyFields') {
      _showEmptyFields = e.target.checked;
      try { localStorage.setItem(_SHOW_EMPTY_KEY, _showEmptyFields ? '1' : '0'); } catch (err) { /* ignore */ }
      _refreshComicInfoSection();
      var sw = _el('cbzShowEmptyFields');
      if (sw) sw.focus();
    }
  }

  // ── showCBZInfo ───────────────────────────────────────────────────────────

  function _renderBody(filePath, data) {
    var entries = (data.file_list || []).map(function (f) {
      var xml = /(^|\/)comicinfo\.xml$/i.test(f);
      return '<li' + (xml ? ' class="ci-xml"' : '') + '>' + CLU.escapeHtml(f) + '</li>';
    }).join('');
    var size = CLU.formatFileSize(data.file_size);
    return '<div class="ci-body">' +
      '<section id="cbzComicInfoSection" aria-label="ComicInfo.xml">' + _renderComicInfoSection() + '</section>' +
      '<aside class="ci-side" aria-label="Preview and file">' +
        '<div id="cbzPreviewContainer">' +
          '<div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">Loading...</span></div>' +
        '</div>' +
        '<div id="cbzPageNav" class="ci-pg">' +
          '<button type="button" class="btn ci-ib ci-bd cbz-page-prev invisible" data-cbz-action="page-prev" ' +
            'aria-label="Previous page" title="Previous page (←)" disabled><i class="bi bi-chevron-left" aria-hidden="true"></i></button>' +
          '<span id="cbzPageInfo" aria-live="polite"></span>' +
          '<button type="button" class="btn ci-ib ci-bd cbz-page-next invisible" data-cbz-action="page-next" ' +
            'aria-label="Next page" title="Next page (→ or Space)" disabled><i class="bi bi-chevron-right" aria-hidden="true"></i></button>' +
        '</div>' +
        '<details class="ci-file">' +
          '<summary><i class="bi bi-chevron-right" aria-hidden="true"></i>File ' +
            '<small>· ' + size + ' · ' + ((data.total_files || 0) === 1 ? '1 entry' : (data.total_files || 0) + ' entries') + '</small></summary>' +
          '<div class="ci-path font-monospace"><span>' + CLU.escapeHtml(filePath) + '</span>' +
            '<button type="button" class="btn ci-ib" data-cbz-action="copy" aria-label="Copy path" title="Copy path">' +
              '<i class="bi bi-copy" aria-hidden="true"></i></button></div>' +
          '<dl class="ci-facts"><dt>Size</dt><dd>' + size + '</dd>' +
            '<dt>Images</dt><dd>' + (data.image_files || 0) + '</dd>' +
            '<dt>Entries</dt><dd>' + (data.total_files || 0) + '</dd></dl>' +
          (entries ? '<ul class="ci-ent font-monospace" aria-label="First archive entries">' + entries + '</ul>' : '') +
        '</details>' +
      '</aside>' +
    '</div>';
  }

  function _loadPreview(filePath, data) {
    fetch('/cbz-preview?path=' + encodeURIComponent(filePath) + '&size=large')
      .then(function (r) { return r.json(); })
      .then(function (pData) {
        if (filePath !== _currentFilePath) return;
        if (!pData.success) {
          var pc = _el('cbzPreviewContainer');
          if (pc) pc.innerHTML = '<p class="text-body-secondary small mb-0">Preview not available</p>';
          return;
        }
        _showImage(pData.preview, 'Cover of ' + _currentFileName, function (img) {
          var w = pData.original_size ? pData.original_size.width : img.naturalWidth;
          var h = pData.original_size ? pData.original_size.height : img.naturalHeight;
          if (_viewerCurrentPage === 0) _setPageInfo(0, w + ' × ' + h);
        });
        _initPageViewer(filePath);
      })
      .catch(function () {
        var pc = _el('cbzPreviewContainer');
        if (pc) pc.innerHTML = '<p class="text-danger small mb-0">Error loading preview</p>';
      });
  }

  /**
   * @param {string} filePath  – full path to CBZ file
   * @param {string} fileName  – display filename
   * @param {Object} [options] – { directoryPath, fileList } enables navigation
   */
  CLU.showCBZInfo = function (filePath, fileName, options) {
    options = options || {};
    var modalElement = _el('cbzInfoModal');
    var content = _el('cbzInfoContent');
    if (!modalElement || !content) return;

    _currentFilePath = filePath;
    _currentFileName = fileName || filePath.split('/').pop();
    _currentData = null;
    _currentComicInfo = {};
    _hasComicInfo = false;
    _currentProvider = null;
    _pendingEdits = {};
    _expanded = {};
    _saving = false;
    _resetPageViewer();

    // Navigation context
    if (options.directoryPath && options.fileList && options.fileList.length > 0) {
      _currentDirectory = options.directoryPath;
      _currentFileList = options.fileList;
      _currentIndex = options.fileList.indexOf(fileName);
    } else {
      _currentDirectory = '';
      _currentFileList = [];
      _currentIndex = -1;
    }
    _updateNavButtons();
    _refreshHeader();
    _refreshFooter();

    // Reset content (spinner)
    content.innerHTML =
      '<div class="text-center">' +
        '<div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div>' +
        '<p class="mt-2">Loading CBZ information...</p>' +
      '</div>';

    // Get or create modal instance
    var modal = bootstrap.Modal.getInstance(modalElement);
    if (!modal) modal = new bootstrap.Modal(modalElement);
    if (!modalElement.classList.contains('show')) modal.show();

    // Fetch metadata
    fetch('/cbz-metadata?path=' + encodeURIComponent(filePath))
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (filePath !== _currentFilePath) return;   // superseded by Prev/Next
        if (data.error) throw new Error(data.error);
        _currentData = data;
        _currentComicInfo = data.comicinfo || {};
        _hasComicInfo = !!data.comicinfo;
        _currentProvider = data.provider || null;

        // Edit, save, discard and clear are delegated from #cbzInfoContent
        // and #cbzInfoFooter (bound once in DOMContentLoaded).
        content.innerHTML = _renderBody(filePath, data);
        _refreshHeader();
        _refreshFooter();
        _loadPreview(filePath, data);
      })
      .catch(function (err) {
        if (filePath !== _currentFilePath) return;
        content.innerHTML = '<div class="alert alert-danger">Error loading CBZ information: ' +
          CLU.escapeHtml(err.message) + '</div>';
      });
  };

  // ── DOM wiring (DOMContentLoaded) ─────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var prevBtn = _el('cbzPrevBtn');
    var nextBtn = _el('cbzNextBtn');

    if (prevBtn) prevBtn.addEventListener('click', CLU.navigateCBZPrev);
    if (nextBtn) nextBtn.addEventListener('click', CLU.navigateCBZNext);

    var cbzInfoModal = _el('cbzInfoModal');
    if (cbzInfoModal) {
      cbzInfoModal.addEventListener('shown.bs.modal', function () {
        document.addEventListener('keydown', _handleKeydown);
      });
      cbzInfoModal.addEventListener('hidden.bs.modal', function () {
        document.removeEventListener('keydown', _handleKeydown);
        _resetPageViewer();
        // Closing the modal abandons staged metadata edits.
        _pendingEdits = {};
      });
    }

    var content = _el('cbzInfoContent');
    if (content) {
      content.addEventListener('click', _onActionClick);
      content.addEventListener('keydown', _onContentKeydown);
      content.addEventListener('change', _onContentChange);
    }
    var footer = _el('cbzInfoFooter');
    if (footer) footer.addEventListener('click', _onActionClick);

    var discardBtn = _el('cbzConfirmDiscardEditsBtn');
    if (discardBtn) discardBtn.addEventListener('click', _doDiscardAndProceed);
    var discardModal = _el('cbzDiscardEditsModal');
    if (discardModal) {
      discardModal.addEventListener('hidden.bs.modal', function () { _afterDiscard = null; });
    }

    // Stacking on top of #cbzInfoModal (focus, body.modal-open) is handled
    // generically in clu-utils.js.
    var confirmBtn = _el('confirmClearComicInfoBtn');
    if (confirmBtn) confirmBtn.addEventListener('click', _doClearComicInfoXml);
  });

})();
