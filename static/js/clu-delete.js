/**
 * CLU Delete  –  clu-delete.js
 *
 * Single-file and bulk delete confirmation modals with API integration.
 * Provides: CLU.showDeleteConfirmation, CLU.confirmDelete,
 *           CLU.showBulkDeleteConfirmation, CLU.confirmBulkDelete
 *
 * Depends on: clu-utils.js (CLU.showToast, CLU.showError, CLU.showSuccess,
 *             CLU.formatFileSize, CLU.showProgressIndicator, CLU.hideProgressIndicator)
 *
 * External contract:
 *   window._cluDelete = {
 *     // Single delete
 *     deleteEndpoint: '/api/delete-file',        // default
 *     deletePayload:  function(path) {},          // default: { path: path }
 *     onDeleteComplete(path, result),
 *     onDeleteError(path, error),
 *
 *     // Bulk delete
 *     onBulkDeleteComplete(paths, results),
 *     onBulkDeleteError(paths, error),
 *
 *     // After an Undo restored items (default: reload the page)
 *     onUndoDelete(),
 *
 *     // Instead of the delete request: the single modal only asks, and
 *     // onConfirm() does the work (Empty Trash, Delete forever)
 *     onConfirm()
 *   }
 *
 * DOM contracts:
 *   #deleteConfirmModal  (from modal_delete_confirm.html)
 *   #deleteFileName, #deleteFileDetails, #deleteFileSize, #deleteFilePath,
 *   #confirmDeleteBtn
 *   #deleteMultipleModal
 *   #deleteMultipleCount, #deleteMultipleFileList, #confirmDeleteMultipleBtn
 */
(function () {
  'use strict';

  var CLU = window.CLU = window.CLU || {};

  function _getContract() { return window._cluDelete || {}; }

  // ── Module state ──────────────────────────────────────────────────────────

  var _currentDeletePath = '';
  var _currentDeleteName = '';
  var _currentBulkPaths = [];

  // ── Undo ──────────────────────────────────────────────────────────────────
  // A delete moves the item to the trash, so undoing it is a restore. The
  // delete routes return `trash_name` (what /api/trash/restore takes); an item
  // that was deleted outright has none and cannot be offered back.

  function _restoreOne(name) {
    return fetch('/api/trash/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) { return !!d.success; })
      .catch(function () { return false; });
  }

  function _undoDelete(names) {
    // One at a time: each restore rewrites the same trash manifest.
    var ok = 0;
    names.reduce(function (chain, name) {
      return chain.then(function () {
        return _restoreOne(name).then(function (done) { if (done) ok++; });
      });
    }, Promise.resolve()).then(function () {
      if (typeof updateTrashBadge === 'function') updateTrashBadge();
      if (ok) CLU.showSuccess('Restored ' + ok + ' item(s)');
      if (ok < names.length) CLU.showError((names.length - ok) + ' item(s) could not be restored');
      if (!ok) return;
      var contract = _getContract();
      if (typeof contract.onUndoDelete === 'function') contract.onUndoDelete();
      else window.location.reload();
    });
  }

  /** Toast with an Undo button for the given trash names. False if none. */
  CLU.offerUndoDelete = function (names, what) {
    names = (names || []).filter(Boolean);
    if (!names.length) return false;
    CLU.toast('Moved ' + what + ' to trash', 'success', {
      duration: 8000,
      action: { label: 'Undo', onClick: function () { _undoDelete(names); } }
    });
    return true;
  };

  // A permanent delete must not promise the Trash. The note's markup is
  // remembered so the next ordinary delete gets it back.
  function _setTrashNote(id, permanent) {
    var el = document.getElementById(id);
    if (!el) return;
    if (el.dataset.trashNote === undefined) el.dataset.trashNote = el.innerHTML;
    if (permanent) el.textContent = 'This cannot be undone.';
    else el.innerHTML = el.dataset.trashNote;
  }

  // ── showDeleteConfirmation ────────────────────────────────────────────────

  /**
   * Show a single-file delete confirmation modal.
   * @param {string} path  - Full file path
   * @param {string} name  - Display name
   * @param {Object} [options] - { size: number, type: string, showDetails: boolean,
   *                               note: string, permanent: boolean }
   */
  CLU.showDeleteConfirmation = function (path, name, options) {
    _currentDeletePath = path;
    _currentDeleteName = name;
    var opts = options || {};

    var nameEl = document.getElementById('deleteFileName');
    if (nameEl) nameEl.textContent = name;
    _setTrashNote('deleteTrashNote', !!opts.permanent);

    // Detail section (size + path) — shown when showDetails is true
    var detailsEl = document.getElementById('deleteFileDetails');
    if (detailsEl) {
      if (opts.showDetails) {
        detailsEl.style.display = '';
        var sizeEl = document.getElementById('deleteFileSize');
        if (sizeEl) {
          sizeEl.textContent = opts.type === 'folder'
            ? 'Folder'
            : CLU.formatFileSize(opts.size || 0);
        }
        var pathEl = document.getElementById('deleteFilePath');
        if (pathEl) pathEl.textContent = path;
      } else {
        detailsEl.style.display = 'none';
      }
    }

    // Extra consequence the caller wants spelled out (e.g. "the issue goes
    // back on the wanted list"). Hidden unless a note is supplied.
    var noteEl = document.getElementById('deleteExtraNote');
    if (noteEl) {
      if (opts.note) {
        noteEl.textContent = opts.note;
        noteEl.style.display = '';
      } else {
        noteEl.textContent = '';
        noteEl.style.display = 'none';
      }
    }

    var modal = new bootstrap.Modal(document.getElementById('deleteConfirmModal'));
    modal.show();
  };

  // ── confirmDelete ─────────────────────────────────────────────────────────

  CLU.confirmDelete = function () {
    var contract = _getContract();
    if (typeof contract.onConfirm === 'function') {
      var askInst = bootstrap.Modal.getInstance(document.getElementById('deleteConfirmModal'));
      if (askInst) askInst.hide();
      contract.onConfirm();
      return;
    }
    var endpoint = contract.deleteEndpoint || '/api/delete-file';
    var payload = typeof contract.deletePayload === 'function'
      ? contract.deletePayload(_currentDeletePath)
      : { path: _currentDeletePath };

    // Close modal
    var modalEl = document.getElementById('deleteConfirmModal');
    var modalInst = bootstrap.Modal.getInstance(modalEl);
    if (modalInst) modalInst.hide();

    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (result.success) {
          if (typeof updateTrashBadge === 'function') updateTrashBadge();
          var offered = CLU.offerUndoDelete([result.trash_name], 'item');
          if (typeof contract.onDeleteComplete === 'function') {
            contract.onDeleteComplete(_currentDeletePath, result);
          } else if (!offered) {
            CLU.showSuccess('File moved to trash');
          }
        } else {
          var errMsg = result.error || 'Unknown error';
          if (typeof contract.onDeleteError === 'function') {
            contract.onDeleteError(_currentDeletePath, errMsg);
          } else {
            CLU.showError('Error deleting file: ' + errMsg);
          }
        }
      })
      .catch(function (err) {
        if (typeof contract.onDeleteError === 'function') {
          contract.onDeleteError(_currentDeletePath, err.message);
        } else {
          CLU.showError('Delete failed: ' + err.message);
        }
      });
  };

  // ── showBulkDeleteConfirmation ────────────────────────────────────────────

  /**
   * Show a bulk delete confirmation modal with a file list.
   * @param {string[]} paths - Array of file paths to delete
   * @param {Object} [options] - { permanent: boolean }
   */
  CLU.showBulkDeleteConfirmation = function (paths, options) {
    _currentBulkPaths = paths;
    _setTrashNote('deleteMultipleTrashNote', !!(options && options.permanent));

    var countEl = document.getElementById('deleteMultipleCount');
    if (countEl) countEl.textContent = paths.length;

    var listEl = document.getElementById('deleteMultipleFileList');
    if (listEl) {
      listEl.innerHTML = '';
      paths.forEach(function (p) {
        var li = document.createElement('li');
        li.className = 'list-group-item';
        li.textContent = p.split('/').pop();
        listEl.appendChild(li);
      });
    }

    var modal = new bootstrap.Modal(document.getElementById('deleteMultipleModal'));
    modal.show();
  };

  // ── confirmBulkDelete ─────────────────────────────────────────────────────

  CLU.confirmBulkDelete = function () {
    var contract = _getContract();
    var paths = _currentBulkPaths;
    if (!paths || paths.length === 0) return;

    var modalInst = bootstrap.Modal.getInstance(
      document.getElementById('deleteMultipleModal')
    );
    if (modalInst) modalInst.hide();

    fetch('/api/delete-multiple', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets: paths })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.results) {
          CLU.showError('Unexpected response from server');
          return;
        }

        if (typeof updateTrashBadge === 'function') updateTrashBadge();

        var successes = data.results.filter(function (r) { return r.success; });
        var offered = CLU.offerUndoDelete(
          successes.map(function (r) { return r.trash_name; }),
          successes.length + ' item(s)');
        if (typeof contract.onBulkDeleteComplete === 'function') {
          contract.onBulkDeleteComplete(paths, data.results);
        } else {
          var failures = data.results.filter(function (r) { return !r.success; });
          if (successes.length > 0 && !offered) {
            CLU.showSuccess('Deleted ' + successes.length + ' file(s)');
          }
          if (failures.length > 0) {
            CLU.showError(failures.length + ' file(s) failed to delete');
          }
        }
      })
      .catch(function (err) {
        if (typeof contract.onBulkDeleteError === 'function') {
          contract.onBulkDeleteError(paths, err.message);
        } else {
          CLU.showError('Error deleting files: ' + err.message);
        }
      });
  };

  // ── DOM wiring ────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    // Single delete confirm button
    var confirmBtn = document.getElementById('confirmDeleteBtn');
    if (confirmBtn) confirmBtn.addEventListener('click', CLU.confirmDelete);

    // Bulk delete confirm button
    var bulkBtn = document.getElementById('confirmDeleteMultipleBtn');
    if (bulkBtn) bulkBtn.addEventListener('click', CLU.confirmBulkDelete);

    // Keyboard support: Enter key to confirm in single delete modal
    var deleteModal = document.getElementById('deleteConfirmModal');
    if (deleteModal) {
      deleteModal.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          CLU.confirmDelete();
        }
      });
    }

    // Keyboard support: Enter key to confirm in bulk delete modal
    var bulkModal = document.getElementById('deleteMultipleModal');
    if (bulkModal) {
      bulkModal.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          CLU.confirmBulkDelete();
        }
      });
    }
  });

})();
