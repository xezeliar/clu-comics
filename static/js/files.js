// Global variables to track current navigation paths.
// Initialized empty - will be set by loadLibraryDropdowns on page load
let currentSourcePath = '';
let currentDestinationPath = '';
// (deleteTarget/deletePanel removed – delete handled by clu-delete.js)
// Global variable to hold selected file paths.
let selectedFiles = new Set();
// Global variables to store series data for sorting in GCD modal
let currentSeriesData = [];
let currentFilePath = '';
let currentFileName = '';
let currentIssueNumber = '';
// Global variables for CBZ info modal navigation
let cbzCurrentDirectory = '';
let cbzCurrentFileList = [];
let cbzCurrentIndex = -1;
let cbzCurrentFilePath = '';
// CBZ Page Preview Viewer State
let cbzViewerPath = null;
let cbzViewerPageCount = 0;
let cbzViewerCurrentPage = 0;
let cbzViewerPreloadedPages = new Set();

// Store raw data for each panel.
let sourceDirectoriesData = null;
let destinationDirectoriesData = null;

// Track current filter (default is 'all') per panel.
let currentFilter = { source: 'all', destination: 'all' };

// Store filter state per path for each panel (for persistence during navigation)
let filterHistory = { source: {}, destination: {} };

// Navigation history for scroll position preservation
let sourceScrollHistory = {};  // { path: scrollTop }
let destinationScrollHistory = {};

// Global variable to track GCD MySQL availability (legacy - kept for backwards compatibility)
let gcdAvailable = false;

// Global variable to track ComicVine API availability (legacy - kept for backwards compatibility)
let comicVineAvailable = false;

// Global variable to track Metron API availability (legacy - kept for backwards compatibility)
let metronAvailable = false;

// Library-specific provider tracking (new provider architecture)
let sourceLibraryId = null;
let destLibraryId = null;
let sourceLibraryProviders = [];
let destLibraryProviders = [];

// Global variable to store current folder path for XML update
// Global variable to store current file path for editing
let currentEditFilePath = null;

// Paths currently flagged "Want to Read" (feeds the collection dashboard swiper).
// Refreshed on page load and before each directory render so the dropdown can
// show Add vs Remove without a per-item /to-read/check round trip.
let wantToReadPaths = new Set();

// Format file size helper function
function formatSize(bytes) {
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  if (bytes === 0) return '0 B';
  const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)));
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
}

// ==========================================
// CBZ Page Preview Viewer (delegated to clu-cbz-info.js)
// ==========================================

// encodeFilePathForReader kept here – also used by reader.js bridge
function encodeFilePathForReader(path) {
  const cleanPath = path.startsWith('/') ? path.substring(1) : path;
  return cleanPath.split('/').map(c => encodeURIComponent(c)).join('/');
}

// Function to check GCD MySQL availability
function checkGCDAvailability() {
  fetch('/gcd-db-status')
    .then(response => response.json())
    .then(data => {
      gcdAvailable = data.gcd_available || false;
      console.log('GCD availability checked:', gcdAvailable);
    })
    .catch(error => {
      console.warn('Error checking GCD availability:', error);
      gcdAvailable = false;
    });
}

// Function to check ComicVine API availability
function checkComicVineAvailability() {
  fetch('/config')
    .then(response => response.text())
    .then(html => {
      // Check if ComicVine API key is configured (not empty)
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const apiKeyInput = doc.getElementById('comicvineApiKey');
      comicVineAvailable = apiKeyInput && apiKeyInput.value && apiKeyInput.value.trim().length > 0;
      console.log('ComicVine API availability checked:', comicVineAvailable);
    })
    .catch(error => {
      console.warn('Error checking ComicVine availability:', error);
      comicVineAvailable = false;
    });
}

// Function to check Metron API availability
function checkMetronAvailability() {
  fetch('/config')
    .then(response => response.text())
    .then(html => {
      // Check if Metron password is configured (not empty)
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const passwordInput = doc.getElementById('metronPassword');
      metronAvailable = passwordInput && passwordInput.value && passwordInput.value.trim().length > 0;
      console.log('Metron API availability checked:', metronAvailable);
    })
    .catch(error => {
      console.warn('Error checking Metron availability:', error);
      metronAvailable = false;
    });
}

// ==========================================
// Library Provider Functions (New Provider Architecture)
// ==========================================

// Fetch providers configured for a specific library
async function fetchLibraryProviders(libraryId) {
  if (!libraryId) return [];
  try {
    const response = await fetch(`/api/libraries/${libraryId}/providers`);
    const data = await response.json();
    if (data.success && data.providers) {
      // Filter to enabled providers, sorted by priority
      const providers = data.providers
        .filter(p => p.enabled)
        .sort((a, b) => a.priority - b.priority);
      console.log(`Loaded ${providers.length} providers for library ${libraryId}:`, providers.map(p => p.provider_type));
      return providers;
    }
  } catch (e) {
    console.error('Failed to fetch library providers:', e);
  }
  return [];
}

// Get providers for a specific panel
function getProvidersForPanel(panel) {
  return panel === 'source' ? sourceLibraryProviders : destLibraryProviders;
}

// Get library ID for a specific panel
function getLibraryIdForPanel(panel) {
  return panel === 'source' ? sourceLibraryId : destLibraryId;
}

// Check if a specific provider is available for the panel
function hasProvider(panel, providerType) {
  const providers = getProvidersForPanel(panel);
  return providers.some(p => p.provider_type === providerType);
}

// Helper: refresh the correct panel based on file path
function refreshPanelForPath(filePath) {
  if (currentSourcePath && filePath.startsWith(currentSourcePath)) {
    loadDirectories(currentSourcePath, 'source');
  } else if (currentDestinationPath && filePath.startsWith(currentDestinationPath)) {
    loadDirectories(currentDestinationPath, 'destination');
  } else {
    // Fallback: refresh both panels
    loadDirectories(currentSourcePath, 'source');
    loadDirectories(currentDestinationPath, 'destination');
  }
}

// Metadata contract for a single file on the files page. Shared by the
// provider search and Force Metadata Match, which answer with the same shape.
function setFileMetadataContract(fileName, panel) {
  window._cluMetadata = {
    getLibraryId: function () { return getLibraryIdForPanel(panel); },
    onMetadataFound: function (fp, data) {
      if (data.moved && data.new_file_path) {
        removeFileFromUI(fp);
      }
      if (data.rename_config && data.rename_config.enabled && data.metadata) {
        var actualPath = data.moved && data.new_file_path ? data.new_file_path : fp;
        promptRenameAfterMetadata(actualPath, fileName, data.metadata, data.rename_config);
      }
      refreshPanelForPath(fp);
    },
    onBatchComplete: function (dp) { refreshPanelForPath(dp); }
  };
}

// Set up metadata contract for files page and call CLU.searchMetadata
function searchMetadataForFile(filePath, fileName, panel) {
  setFileMetadataContract(fileName, panel);
  CLU.searchMetadata(filePath, fileName);
}

// Tag a file with a Metron/ComicVine issue the user names by id.
function forceMetadataMatchForFile(filePath, fileName, panel) {
  setFileMetadataContract(fileName, panel);
  CLU.forceMetadataMatch(filePath, fileName);
}

// Set up metadata contract for directory batch and call CLU.fetchDirectoryMetadata.
// When the target directory contains subfolders, route through the bulk
// metadata orchestrator instead (which auto-resolves what it can and queues
// the rest for end-of-run review). Leaf folders keep the existing SSE flow.
async function fetchDirectoryMetadataForPanel(dirPath, dirName, panel) {
  let hasSub = false;
  try {
    const resp = await fetch(`/api/bulk-metadata/has-subfolders?path=${encodeURIComponent(dirPath)}`);
    if (resp.ok) {
      const data = await resp.json();
      hasSub = !!(data && data.has_subfolders);
    }
  } catch (e) {
    // Network/server error — fall back to legacy single-folder flow.
    hasSub = false;
  }

  if (hasSub && typeof BulkMetadataReview !== 'undefined' && BulkMetadataReview.startJob) {
    BulkMetadataReview.startJob({
      scope: 'folder',
      paths: [dirPath],
      library_id: getLibraryIdForPanel(panel),
      onDone: function () { refreshPanelForPath(dirPath); }
    });
    return;
  }

  window._cluMetadata = {
    getLibraryId: function () { return getLibraryIdForPanel(panel); },
    onMetadataFound: function (fp, data) {
      refreshPanelForPath(fp);
    },
    onBatchComplete: function (dp) { refreshPanelForPath(dp); }
  };
  CLU.fetchDirectoryMetadata(dirPath, dirName);
}

// Normalize file object (handles both {name, size} or string)
function normalizeFile(file) {
  if (typeof file === 'object' && file.name) return file;
  return { name: file, size: null };
}

// Send a rename request. Resolves { ok } or { ok: false, error } so the inline
// rename can show the server's refusal under the field; a success reloads the pane.
function renameItem(oldPath, newName, panel) {
  const trimmedName = String(newName).trim();
  if (!trimmedName) return Promise.resolve({ ok: false, error: 'A name can’t be empty.' });
  const newPath = dirName(oldPath) + '/' + trimmedName;
  return fetch('/rename', {
    method: 'POST',
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old: oldPath, new: newPath })
  })
    .then(response => response.json())
    .then(result => {
      if (!result.success) return { ok: false, error: result.error || 'Rename failed.' };
      refreshFilePanel(panel);
      return { ok: true };
    })
    .catch(error => {
      console.error("Error in rename request:", error);
      return { ok: false, error: 'Rename failed due to a network or server error.' };
    });
}

// ==========================================
// Want to Read
// ==========================================

// Refresh the cached set of "Want to Read" paths. Never rejects – a failed
// lookup just leaves the dropdown offering "Add", which the server dedupes.
function refreshWantToReadPaths() {
  return fetch('/api/favorites/to-read')
    .then(response => response.json())
    .then(data => {
      if (data.success && Array.isArray(data.items)) {
        wantToReadPaths = new Set(data.items.map(item => item.path));
      }
    })
    .catch(error => {
      console.error("Error loading Want to Read list:", error);
    });
}

// Flag a file or folder for the "Want to Read" swiper on the collection page.
// itemType is 'file' or 'folder'. The menus read wantToReadPaths when opened.
function toggleWantToRead(fullPath, name, itemType) {
  const isMarked = wantToReadPaths.has(fullPath);
  const method = isMarked ? 'DELETE' : 'POST';

  fetch('/api/favorites/to-read', {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: fullPath, type: itemType })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        if (isMarked) {
          wantToReadPaths.delete(fullPath);
          CLU.showSuccess(`${name} removed from Want to Read`);
        } else {
          wantToReadPaths.add(fullPath);
          CLU.showSuccess(`${name} added to Want to Read`);
        }
      } else {
        CLU.showError('Failed to update Want to Read: ' + (data.error || 'Unknown error'));
      }
    })
    .catch(error => {
      console.error("Error updating Want to Read:", error);
      CLU.showError('Failed to update Want to Read');
    });
}

document.addEventListener('DOMContentLoaded', refreshWantToReadPaths);

// First letters present in a folder listing: 'A'..'Z', or '#' for the rest.
function directoryLetters(directories) {
  // CLU.sortLetters buckets each first character ('#' for a non-letter).
  const dirs = Array.isArray(directories) ? directories : [];
  return new Set(CLU.sortLetters(dirs.map(dir => dir.charAt(0))));
}

// Draw a panel's search box and A-Z bar. The search box is always there and
// narrows files and folders alike; the letter bar appears only in a folder of
// more than FM_MANY_FOLDERS folders and narrows folders only. A second click
// on the selected letter goes back to All (CLU.letterBar).
function updateFilterBar(panel, directories, files) {
  const outerContainer = document.getElementById(`${panel}-directory-filter`);
  if (!outerContainer) return;
  if (!Array.isArray(directories)) directories = [];

  const bar = outerContainer.querySelector('.clu-letter-bar');
  if (bar) {
    const many = directories.length > FM_MANY_FOLDERS;
    if (!many) currentFilter[panel] = 'all';
    bar.hidden = !many;
    CLU.letterBar(bar, {
      letters: many ? Array.from(directoryLetters(directories)) : [],
      active: currentFilter[panel] === 'all' ? '' : currentFilter[panel],
      onChange: value => {
        currentFilter[panel] = value || 'all';
        fmPanes[panel].cur = 0;
        fmRender(panel);
      }
    });
  }

  // The search box is drawn once per pane and kept, so typing never loses focus.
  const searchRow = document.getElementById(panel + '-directory-search-row');
  if (!searchRow) return;
  let input = document.getElementById(panel + '-directory-search');
  if (!input) {
    const box = CLU.searchInput({
      id: panel + '-directory-search',
      label: 'Search files and folders',
      value: panelSearch[panel],
    });
    searchRow.replaceChildren(box);
    input = box.querySelector('input');
    CLU.bindSearch(input, val => onPanelSearch(panel, val), { delay: 0 });
  }
  if (input.value.trim() !== (panelSearch[panel] || '')) input.value = panelSearch[panel] || '';
  input.disabled = !fmPanes[panel].loaded;
}

// Function to restore filter from history if valid for the given path
function restoreFilterIfValid(panel, path, directories) {
  const savedFilter = filterHistory[panel][path];
  if (!savedFilter || savedFilter === 'all') return;

  // Only restore if the saved letter is still in this folder
  if (directoryLetters(directories).has(savedFilter)) {
    currentFilter[panel] = savedFilter;
    // Redraw the bar to reflect the restored filter
    const data = panel === 'source' ? sourceDirectoriesData : destinationDirectoriesData;
    updateFilterBar(panel, directories, data && data.files);
  }
}

// --- SEARCH STATE, ONE PER PANEL (cleared on navigation) ---
const panelSearch = { source: '', destination: '' };
function onPanelSearch(panel, val) {
  panelSearch[panel] = val.trim();
  fmPanes[panel].cur = 0;
  fmRender(panel);
}

// Save scroll position before navigating away
function saveScrollPosition(panel) {
  const container = document.getElementById(panel === 'source' ? 'source-list' : 'destination-list');
  const currentPath = panel === 'source' ? currentSourcePath : currentDestinationPath;
  if (container && currentPath) {
    const history = panel === 'source' ? sourceScrollHistory : destinationScrollHistory;
    history[currentPath] = container.scrollTop;
  }
}

// Restore scroll position after rendering
function restoreScrollPosition(panel, path) {
  const container = document.getElementById(panel === 'source' ? 'source-list' : 'destination-list');
  const history = panel === 'source' ? sourceScrollHistory : destinationScrollHistory;
  if (container && history[path] !== undefined) {
    // Use setTimeout to ensure DOM has rendered
    setTimeout(() => {
      container.scrollTop = history[path];
    }, 0);
  }
}

// While a listed comic is being compressed, check the folder every few seconds
// and redraw the panel once nothing in it is compressing any more (so the badge
// goes away and the file becomes movable). Polls quietly: the redraw happens
// only when the answer changes, and stops as soon as the panel moves elsewhere.
const compressWatchTimers = {};
function watchCompressing(panel, data, kind = 'directories') {
  clearTimeout(compressWatchTimers[panel]);
  const path = data && data.current_path;
  if (!path || !Array.isArray(data.files) || !data.files.some(f => f && f.compressing)) return;
  // The Downloads button lists TARGET through its own route and loader.
  const listUrl = kind === 'downloads' ? '/list-downloads' : '/list-directories';
  const reload = kind === 'downloads' ? loadDownloads : loadDirectories;

  const check = () => {
    const stillHere = (panel === 'source' ? currentSourcePath : currentDestinationPath) === path;
    if (!stillHere) return;
    fetch(`${listUrl}?path=${encodeURIComponent(path)}`)
      .then(r => r.json())
      .then(next => {
        const stillHereNow = (panel === 'source' ? currentSourcePath : currentDestinationPath) === path;
        if (!stillHereNow || next.error) return;
        if ((next.files || []).some(f => f && f.compressing)) {
          compressWatchTimers[panel] = setTimeout(check, 4000);
        } else {
          reload(path, panel);
        }
      })
      .catch(() => { compressWatchTimers[panel] = setTimeout(check, 8000); });
  };
  compressWatchTimers[panel] = setTimeout(check, 4000);
}

// =============================================
// Trash browsing
// =============================================

// The Trash count on both panes' Trash buttons, and whether Trash is on (which
// decides whether Delete acts at once with Undo or asks first).
function updateTrashBadge() {
  fetch('/api/trash/info')
    .then(r => r.json())
    .then(data => {
      trashEnabled = !!(data.enabled && data.path);
      document.querySelectorAll('.fm-trash-count').forEach(badge => {
        const n = trashEnabled ? (data.item_count || 0) : 0;
        badge.textContent = n;
        badge.hidden = !n;
      });
    })
    .catch(() => {});
}

document.addEventListener('DOMContentLoaded', updateTrashBadge);

// =============================================================================
// File Manager: two panes, one row builder, one selection bar.
//
// Each pane (source, destination) shows a place: a library folder, Downloads
// (TARGET), Recent Files or Trash. Every row of every place is built by
// fmRow(); a row is a check box, a type icon, the name, a fact line and at most
// two controls (CBZ Information or Restore, and the row's menu). Everything
// else is in that menu, the open folder's menu (the breadcrumb's ⋮) or the
// selection bar. Names are always text (textContent), never markup.
// =============================================================================

const FM_PANELS = ['source', 'destination'];
const FM_MANY_FOLDERS = 40;   // the letter bar appears above this many folders

function fmNewPane() {
  return { place: 'library', parent: null, items: [], cur: 0, anchor: null, ren: null, renErr: '', loaded: false };
}
const fmPanes = { source: fmNewPane(), destination: fmNewPane() };
let fmActive = 'source';     // the pane the shortcuts and the bar act on
let fmTab = 'source';        // the pane shown on a phone
let selectionPane = null;    // the pane selectedFiles belongs to
let trashEnabled = null;     // from /api/trash/info; null until known
let fmDrag = null;           // { panel, items } while a row drag is on
let fmCreatePanel = 'destination';

function fmTargetDir() {
  const el = document.getElementById('fm');
  return el ? (el.dataset.targetDir || '') : '';
}
function otherPanel(panel) { return panel === 'source' ? 'destination' : 'source'; }
function fmPaneEl(panel) { return document.getElementById(panel + '-pane'); }
function fmListEl(panel) { return document.getElementById(panel + '-list'); }
function panelPath(panel) { return panel === 'source' ? currentSourcePath : currentDestinationPath; }
function setPanelPath(panel, path) {
  if (panel === 'source') currentSourcePath = path; else currentDestinationPath = path;
}
function setPanelData(panel, data) {
  if (panel === 'source') sourceDirectoriesData = data; else destinationDirectoriesData = data;
}
function isVirtualPlace(panel) {
  const place = fmPanes[panel].place;
  return place === 'recent' || place === 'trash';
}
function baseName(p) { return String(p).replace(/\/+$/, '').split('/').pop(); }
function dirName(p) { return String(p).substring(0, String(p).lastIndexOf('/')); }
function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
function fileExt(name) {
  const m = /\.([^./]+)$/.exec(String(name));
  return m ? m[1].toLowerCase() : '';
}
function isComicEntry(e) { return e.type === 'file' && ['cbz', 'cbr', 'zip'].includes(fileExt(e.name)); }
function isCbzEntry(e) { return e.type === 'file' && ['cbz', 'zip'].includes(fileExt(e.name)); }
function isSidecarEntry(e) { return e.type === 'file' && ['cvinfo', 'series.json'].includes(e.name.toLowerCase()); }
function fmNamed(entries) {
  return entries.length === 1 ? '“' + entries[0].name + '”' : plural(entries.length, 'item');
}

function shortDate(d) {
  if (!(d instanceof Date) || isNaN(d)) return '';
  const opts = { day: 'numeric', month: 'short' };
  if (d.getFullYear() !== new Date().getFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString(undefined, opts);
}

// "CBR · 61.2 MB · 11 Nov" for a file, "12 items" for a folder.
function factLine(e) {
  if (e.busy) return 'Moving…';
  if (e.compressing) return 'Compressing…';
  if (e.type === 'directory') {
    if (e.trashName) return 'Folder' + (e.size != null ? ' · ' + formatSize(e.size) : '');
    return e.count == null ? 'Folder' : plural(e.count, 'item');
  }
  const parts = [(fileExt(e.name) || 'file').toUpperCase()];
  if (e.size != null) parts.push(formatSize(e.size));
  if (e.added) parts.push(getTimeAgo(e.added));
  else if (e.mtime) parts.push(shortDate(new Date(e.mtime * 1000)));
  return parts.join(' · ');
}

// ---------------------------------------------------------------------------
// Loading a place
// ---------------------------------------------------------------------------

function fmLoading(panel, text) {
  const list = fmListEl(panel);
  if (!list) return;
  const li = document.createElement('li');
  li.className = 'fm-empty text-center text-body-secondary small';
  const sp = document.createElement('span');
  sp.className = 'spinner-border spinner-border-sm me-2';
  sp.setAttribute('aria-hidden', 'true');
  li.append(sp, text || 'Loading…');
  list.replaceChildren(li);
}

function fmFailed(panel, title, err) {
  const p = fmPanes[panel];
  p.items = [];
  p.loaded = false;
  p.error = { title: title, message: err && err.message ? err.message : 'The server did not answer.' };
  fmRender(panel);
}

// A listing changed path: the search, the letter and this pane's selection go.
function fmArrive(panel, path) {
  const p = fmPanes[panel];
  const moved = panelPath(panel) !== path;
  if (moved) {
    const prev = panelPath(panel);
    if (prev && currentFilter[panel] !== 'all') filterHistory[panel][prev] = currentFilter[panel];
    else if (prev) delete filterHistory[panel][prev];
    panelSearch[panel] = '';
    currentFilter[panel] = 'all';
    p.cur = 0;
    p.anchor = null;
    p.ren = null;
    if (selectionPane === panel) { selectedFiles.clear(); selectionPane = null; }
  }
  setPanelPath(panel, path);
  return moved;
}

function fmLoadListing(panel, place, path) {
  const p = fmPanes[panel];
  if (p.place === place) saveScrollPosition(panel);
  p.place = place;
  p.error = null;
  fmDrawPlaces(panel);
  fmLoading(panel);
  const url = place === 'downloads' ? '/list-downloads' : '/list-directories';
  // Refresh the Want to Read set alongside the listing so the menus offer the
  // right Add / Remove label.
  return Promise.all([
    fetch(`${url}?path=${encodeURIComponent(path)}`).then(r => r.json()),
    refreshWantToReadPaths()
  ])
    .then(([data]) => {
      if (data.error) throw new Error(data.error);
      if (fmPanes[panel].place !== place) return;   // the user went elsewhere meanwhile
      const moved = fmArrive(panel, data.current_path);
      setPanelData(panel, data);
      p.parent = data.parent || null;
      p.items = fmEntriesFromListing(data);
      p.loaded = true;
      if (moved) restoreFilterIfValid(panel, data.current_path, data.directories);
      fmPruneSelection(panel);
      fmSyncLibraryName(panel, data.current_path);
      fmRender(panel);
      restoreScrollPosition(panel, data.current_path);
      if (p.focusPath) {
        const k = fmView(panel).findIndex(x => x.path === p.focusPath);
        p.focusPath = null;
        if (k >= 0) fmFocusRow(panel, k);
      }
      watchCompressing(panel, data, place === 'downloads' ? 'downloads' : 'directories');
    })
    .catch(error => {
      console.error('Error loading directory:', error);
      fmFailed(panel, place === 'downloads' ? 'Could not load Downloads' : 'Could not load this folder', error);
    });
}

function fmEntriesFromListing(data) {
  const base = data.current_path;
  const counts = data.dir_counts || {};
  const dirs = (Array.isArray(data.directories) ? data.directories : []).map(d => {
    const name = typeof d === 'object' && d ? d.name : d;
    return { name: name, path: base + '/' + name, type: 'directory', count: counts[name] != null ? counts[name] : null };
  });
  const files = (Array.isArray(data.files) ? data.files : []).map(f => {
    const fd = normalizeFile(f);
    return {
      name: fd.name, path: base + '/' + fd.name, type: 'file',
      size: fd.size, mtime: fd.mtime || null, compressing: !!fd.compressing
    };
  });
  return dirs.concat(files);
}

// Route virtual paths to their places; a path under TARGET is Downloads.
function loadDirectories(path, panel) {
  if (path === 'trash') { loadTrash(panel); return; }
  if (path === 'recent-files') { loadRecentFiles(panel); return; }
  const target = fmTargetDir();
  const inTarget = !!target && !!path && (path === target || path.startsWith(target + '/'));
  fmLoadListing(panel, inTarget ? 'downloads' : 'library', path || '');
}

function loadDownloads(path, panel) {
  fmLoadListing(panel, 'downloads', path || fmTargetDir());
}

function loadRecentFiles(panel) {
  const p = fmPanes[panel];
  p.place = 'recent';
  p.error = null;
  fmDrawPlaces(panel);
  fmLoading(panel, 'Loading recent files…');
  fetch('/list-recent-files?limit=100')
    .then(r => r.json())
    .then(data => {
      if (data.error) throw new Error(data.error);
      if (p.place !== 'recent') return;
      fmArrive(panel, 'recent-files');
      p.parent = null;
      p.items = (data.files || []).map(f => ({
        name: f.file_name, path: f.file_path, type: 'file', added: f.added_at
      }));
      p.loaded = true;
      fmPruneSelection(panel);
      fmRender(panel);
    })
    .catch(error => {
      console.error('Error loading recent files:', error);
      fmFailed(panel, 'Could not load recent files', error);
    });
}

function loadTrash(panel) {
  const p = fmPanes[panel];
  p.place = 'trash';
  p.error = null;
  fmDrawPlaces(panel);
  fmLoading(panel, 'Loading Trash…');
  fetch('/api/trash/list')
    .then(r => r.json())
    .then(data => {
      if (p.place !== 'trash') return;
      fmArrive(panel, 'trash');
      p.parent = null;
      p.trashOff = !data.enabled;
      p.items = (data.items || []).map(item => ({
        name: item.name, path: item.path, type: item.is_dir ? 'directory' : 'file',
        size: item.size, mtime: item.mtime, trashName: item.name, original: item.original_path || null
      }));
      p.loaded = true;
      fmPruneSelection(panel);
      fmRender(panel);
      updateTrashBadge();
    })
    .catch(error => {
      console.error('Error loading trash:', error);
      fmFailed(panel, 'Could not load Trash', error);
    });
}

// Reload a pane in whatever place it is showing.
function refreshFilePanel(panel) {
  const p = fmPanes[panel];
  if (p.place === 'recent') loadRecentFiles(panel);
  else if (p.place === 'trash') loadTrash(panel);
  else if (panelPath(panel)) loadDirectories(panelPath(panel), panel);
}

function fmRefreshAll() { FM_PANELS.forEach(refreshFilePanel); }

// Name the Library button for the library the pane is in.
function fmSyncLibraryName(panel, path) {
  const lib = fmLibraryFor(path);
  const span = document.getElementById(panel === 'source' ? 'sourceLibraryName' : 'destLibraryName');
  if (lib && span) span.textContent = lib.name;
}

function fmLibraryFor(path) {
  const libs = window.fmLibraries || [];
  let best = null;
  libs.forEach(lib => {
    const root = String(lib.path).replace(/\/+$/, '');
    if ((path === root || String(path).startsWith(root + '/')) && (!best || root.length > best.path.length)) {
      best = { name: lib.name, path: root };
    }
  });
  return best;
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

// The rows the pane shows: the search narrows files and folders alike; the
// letter narrows folders only.
function fmView(panel) {
  const p = fmPanes[panel];
  const term = (panelSearch[panel] || '').toLowerCase();
  const letter = currentFilter[panel];
  return p.items.filter(e => {
    if (term && !e.name.toLowerCase().includes(term)) return false;
    if (letter && letter !== 'all' && e.type === 'directory') {
      if (letter === '#') return !/^[A-Za-z]/.test(e.name.charAt(0));
      return e.name.charAt(0).toUpperCase() === letter;
    }
    return true;
  });
}

function fmIcon(cls) {
  const i = document.createElement('i');
  i.className = 'bi ' + cls;
  i.setAttribute('aria-hidden', 'true');
  return i;
}

function fmButton(cls, label, icon, attrs) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = cls;
  if (icon) b.appendChild(fmIcon(icon + (label ? ' me-1' : '')));
  if (label) b.appendChild(document.createTextNode(label));
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (v === false || v == null) return;
    b.setAttribute(k, v === true ? '' : v);
  });
  return b;
}

// The one row builder: library folders, Downloads, Recent Files and Trash.
function fmRow(panel, e, k) {
  const p = fmPanes[panel];
  const trash = p.place === 'trash';
  const current = k === p.cur;
  const tab = current ? '0' : '-1';
  const renaming = p.ren === e.path;
  const sel = selectionPane === panel && selectedFiles.has(e.path);

  const li = document.createElement('li');
  li.className = 'fm-row ' + (e.type === 'directory' ? 'is-dir' : 'is-file') + (e.busy ? ' is-busy' : '');
  li.setAttribute('role', 'row');
  li.setAttribute('aria-selected', sel ? 'true' : 'false');
  li.dataset.k = k;
  li.dataset.fullpath = e.path;
  li.tabIndex = current ? 0 : -1;
  li.draggable = !renaming && !e.busy && !e.compressing;
  if (e.original) li.title = 'From ' + e.original;

  const ckc = document.createElement('span');
  ckc.className = 'fm-ckc';
  ckc.setAttribute('role', 'gridcell');
  const ck = document.createElement('input');
  ck.type = 'checkbox';
  ck.className = 'form-check-input fm-ck';
  ck.tabIndex = -1;
  ck.checked = sel;
  ck.setAttribute('aria-label', 'Select ' + e.name);
  ckc.appendChild(ck);

  const ty = fmIcon((e.type === 'directory' ? 'bi-folder' : isComicEntry(e) ? 'bi-file-earmark-zip' : 'bi-file-earmark') + ' fm-ty');

  const nm = document.createElement('span');
  nm.className = 'fm-nm';
  nm.setAttribute('role', 'gridcell');
  if (renaming) {
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'fm-in';
    input.value = e.name;
    input.setAttribute('aria-label', 'New name for ' + e.name);
    if (p.renErr) {
      input.setAttribute('aria-invalid', 'true');
      input.setAttribute('aria-describedby', panel + '-fmErr');
    }
    nm.appendChild(input);
  } else if (e.type === 'directory' && !trash) {
    const go = document.createElement('button');
    go.type = 'button';
    go.className = 'fm-go';
    go.dataset.fmAct = 'open';
    go.tabIndex = -1;
    go.textContent = e.name;
    go.title = e.name;
    nm.appendChild(go);
  } else {
    nm.textContent = e.name;
    nm.title = e.name;
  }

  const mt = document.createElement('span');
  mt.className = 'fm-mt';
  mt.setAttribute('role', 'gridcell');
  mt.textContent = factLine(e);

  const acts = document.createElement('span');
  acts.className = 'fm-acts';
  acts.setAttribute('role', 'gridcell');
  if (trash) {
    acts.appendChild(fmButton('btn btn-sm btn-outline-secondary', 'Restore', null, {
      'data-fm-act': 'restore', tabindex: tab, disabled: !e.original,
      title: e.original ? 'Restore to ' + e.original : 'No original path recorded — drag it to a folder instead'
    }));
  } else if (isCbzEntry(e)) {
    acts.appendChild(fmButton('btn btn-sm fm-ib fm-info', '', 'bi-eye', {
      'data-fm-act': 'info', tabindex: tab, 'aria-label': 'CBZ Information for ' + e.name, title: 'CBZ Information'
    }));
  }
  acts.appendChild(fmButton('btn btn-sm fm-ib', '', 'bi-three-dots-vertical', {
    'data-fm-act': 'menu', tabindex: tab, 'aria-haspopup': 'menu', 'aria-expanded': 'false',
    'aria-label': 'More actions for ' + e.name, title: 'More actions'
  }));

  li.append(ckc, ty, nm, mt, acts);
  if (renaming && p.renErr) {
    const err = document.createElement('span');
    err.className = 'fm-err';
    err.id = panel + '-fmErr';
    err.textContent = p.renErr;
    li.appendChild(err);
  }
  return li;
}

function fmEmptyRow(panel) {
  const p = fmPanes[panel];
  const li = document.createElement('li');
  li.className = 'fm-empty';
  const query = (panelSearch[panel] || '').trim();
  const letterOn = currentFilter[panel] !== 'all';
  if (p.error) {
    li.appendChild(CLU.emptyState({ icon: 'bi-exclamation-triangle', title: p.error.title, message: p.error.message, compact: true }));
  } else if (p.items.length && (query || letterOn)) {
    li.appendChild(CLU.noMatches({
      noun: 'files or folders', query: query, filtered: letterOn, compact: true,
      onClear: () => clearDirectoryNarrowing(panel, letterOn)
    }));
  } else if (p.place === 'recent') {
    li.appendChild(CLU.emptyState({ icon: 'bi-clock-history', title: 'No recent files', message: 'Files added to a library show up here.', compact: true }));
  } else if (p.place === 'trash') {
    li.appendChild(p.trashOff
      ? CLU.emptyState({ icon: 'bi-info-circle', title: 'Trash is turned off', message: 'Deleted files are removed at once. Turn Trash on in Settings › File Processing.', compact: true })
      : CLU.emptyState({ icon: 'bi-trash3', title: 'Trash is empty', message: 'Deleted files wait here until it is emptied.', compact: true }));
  } else if (p.place === 'downloads' && !p.parent) {
    li.appendChild(CLU.emptyState({ icon: 'bi-cloud-check', title: 'No downloads waiting', message: 'Finished downloads land here until they are moved into a library.', compact: true }));
  } else {
    li.appendChild(CLU.emptyState({ icon: 'bi-folder2-open', title: 'This folder is empty', message: 'Move files here from the other pane, or drop them from your computer.', compact: true }));
  }
  return li;
}

function clearDirectoryNarrowing(panel, clearLetter) {
  if (clearLetter) currentFilter[panel] = 'all';
  panelSearch[panel] = '';
  const box = document.getElementById(panel + '-directory-search');
  if (box) box.value = '';
  fmRender(panel);
  if (box) box.focus();
}

function fmDrawPlaces(panel) {
  const pane = fmPaneEl(panel);
  if (!pane) return;
  const place = fmPanes[panel].place;
  pane.querySelectorAll('[data-fm-place]').forEach(b => {
    const on = b.dataset.fmPlace === place;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  const pm = pane.querySelector('[data-fm-pane-menu]');
  if (pm) pm.hidden = place === 'recent';
}

// Update the breadcrumb for a pane: the place's root, then each folder below it.
function updateBreadcrumb(panel, fullPath) {
  const el = document.getElementById(panel + '-path-display');
  if (!el) return;
  el.replaceChildren();
  const p = fmPanes[panel];
  const here = document.createElement('span');
  here.setAttribute('aria-current', 'location');
  if (p.place === 'recent' || p.place === 'trash' || !fullPath) {
    here.textContent = p.place === 'trash' ? 'Trash' : p.place === 'recent' ? 'Recent Files' : '';
    el.appendChild(here);
    return;
  }
  const target = fmTargetDir().replace(/\/+$/, '');
  const lib = p.place === 'downloads' ? { name: 'Downloads', path: target } : fmLibraryFor(fullPath);
  let rootPath = lib && lib.path ? lib.path : '';
  const crumbs = [];
  if (rootPath && (fullPath === rootPath || fullPath.startsWith(rootPath + '/'))) {
    crumbs.push({ name: lib.name, path: rootPath });
  } else {
    rootPath = '';
  }
  let acc = rootPath;
  fullPath.slice(rootPath.length).split('/').filter(Boolean).forEach(part => {
    acc += '/' + part;
    crumbs.push({ name: part, path: acc });
  });
  crumbs.forEach((c, i) => {
    if (i) {
      const sep = document.createElement('span');
      sep.className = 'fm-sep';
      sep.setAttribute('aria-hidden', 'true');
      sep.textContent = '/';
      el.appendChild(sep);
    }
    if (i === crumbs.length - 1) {
      here.textContent = c.name;
      el.appendChild(here);
    } else {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = c.name;
      b.addEventListener('click', () => loadDirectories(c.path, panel));
      el.appendChild(b);
    }
  });
}

function fmDrawFooter(panel, shown) {
  const ft = document.getElementById(panel + '-footer');
  if (!ft) return;
  const p = fmPanes[panel];
  ft.replaceChildren();
  if (!p.loaded) return;
  const total = p.items.length;
  const what = document.createElement('span');
  const narrowed = (panelSearch[panel] || '').trim() || currentFilter[panel] !== 'all';
  if (narrowed) {
    what.textContent = `Showing ${shown} of ${plural(total, 'item')}`;
    ft.appendChild(what);
    return;
  }
  if (!total) return;
  const files = p.items.filter(e => e.type === 'file');
  const dirs = total - files.length;
  if (p.place === 'recent') {
    what.textContent = plural(total, 'recent file');
  } else {
    what.textContent = [dirs && plural(dirs, 'folder'), files.length && plural(files.length, 'file')].filter(Boolean).join(' · ');
  }
  ft.appendChild(what);
  const bytes = p.items.reduce((sum, e) => sum + (e.type === 'file' || p.place === 'trash' ? (e.size || 0) : 0), 0);
  if (bytes) {
    const size = document.createElement('span');
    size.className = 'fm-ft-size';
    size.textContent = formatSize(bytes);
    ft.appendChild(size);
  }
}

function fmRender(panel) {
  const list = fmListEl(panel);
  if (!list) return;
  const p = fmPanes[panel];
  fmDrawPlaces(panel);
  updateBreadcrumb(panel, panelPath(panel));
  const dirs = p.items.filter(e => e.type === 'directory').map(e => e.name);
  updateFilterBar(panel, dirs, p.items.filter(e => e.type === 'file'));
  const rows = fmView(panel);
  p.cur = Math.max(0, Math.min(p.cur, rows.length - 1));
  const frag = document.createDocumentFragment();
  if (rows.length) rows.forEach((e, k) => frag.appendChild(fmRow(panel, e, k)));
  else frag.appendChild(fmEmptyRow(panel));
  list.replaceChildren(frag);
  // One tab stop: the current row, or the list itself when it has none.
  list.tabIndex = rows.length ? -1 : 0;
  fmDrawFooter(panel, rows.length);
  fmDrawBar();
}

// Selection only: no rebuild.
function fmSyncSelection(panel) {
  const list = fmListEl(panel);
  if (!list) return;
  list.querySelectorAll('.fm-row').forEach(li => {
    const on = selectionPane === panel && selectedFiles.has(li.dataset.fullpath);
    li.setAttribute('aria-selected', on ? 'true' : 'false');
    const ck = li.querySelector('.fm-ck');
    if (ck) ck.checked = on;
  });
}

function fmSelectionChanged() {
  FM_PANELS.forEach(fmSyncSelection);
  fmDrawBar();
}

function fmSetActive(panel) {
  fmActive = panel;
  FM_PANELS.forEach(pn => {
    const el = fmPaneEl(pn);
    if (el) el.classList.toggle('is-active', pn === panel);
  });
}

function fmSetTab(panel) {
  fmTab = panel;
  FM_PANELS.forEach(pn => {
    const el = fmPaneEl(pn);
    if (el) el.classList.toggle('is-tab', pn === panel);
  });
  document.querySelectorAll('[data-fm-tab]').forEach(b => {
    b.setAttribute('aria-selected', b.dataset.fmTab === panel ? 'true' : 'false');
  });
  fmSetActive(panel);
  fmDrawBar();
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

// Selecting in one pane clears the other.
function fmSelect(panel, paths, mode) {
  if (selectionPane && selectionPane !== panel) selectedFiles.clear();
  selectionPane = panel;
  if (mode === 'only') selectedFiles.clear();
  paths.forEach(path => {
    if (mode === 'toggle' && selectedFiles.has(path)) selectedFiles.delete(path);
    else selectedFiles.add(path);
  });
  if (!selectedFiles.size) selectionPane = null;
  fmSetActive(panel);
  fmSelectionChanged();
}

function clearFileSelection() {
  selectedFiles.clear();
  selectionPane = null;
  fmSelectionChanged();
}

function fmPruneSelection(panel) {
  if (selectionPane !== panel) return;
  const here = new Set(fmPanes[panel].items.map(e => e.path));
  [...selectedFiles].forEach(path => { if (!here.has(path)) selectedFiles.delete(path); });
  if (!selectedFiles.size) selectionPane = null;
}

function fmSelectedEntries(panel) {
  return fmPanes[panel].items.filter(e => selectedFiles.has(e.path));
}

// What the next action works on: the selection, else the row it was asked on.
function fmTargets(panel, e) {
  if (e && !(selectionPane === panel && selectedFiles.has(e.path))) return [e];
  return selectionPane === panel ? fmSelectedEntries(panel) : (e ? [e] : []);
}

// Why the selection cannot move to the other pane, or '' when it can.
function fmMoveBlocked(panel) {
  const o = otherPanel(panel);
  const op = fmPanes[o];
  if (op.place === 'trash') return 'The other pane shows Trash. Use Delete to send items there.';
  if (op.place === 'recent') return 'The other pane shows Recent Files. Open a folder there to move here.';
  if (!op.loaded || !panelPath(o)) return 'The other pane has no folder open.';
  if (!isVirtualPlace(panel) && panelPath(o) === panelPath(panel)) {
    return 'Both panes show this folder. Open another folder in the other pane to move here.';
  }
  return '';
}

function fmFolderLabel(panel) {
  const p = fmPanes[panel];
  if (p.place === 'recent') return 'Recent Files';
  if (p.place === 'trash') return 'Trash';
  const path = panelPath(panel);
  const lib = p.place === 'downloads' ? null : fmLibraryFor(path);
  if (lib && lib.path === path) return lib.name;
  if (p.place === 'downloads' && !p.parent) return 'Downloads';
  return baseName(path) || path;
}

// ---------------------------------------------------------------------------
// The selection bar
// ---------------------------------------------------------------------------

function fmDrawBar() {
  const bar = document.getElementById('fmBar');
  if (!bar) return;
  const root = document.getElementById('fm');
  const n = selectionPane ? selectedFiles.size : 0;
  if (root) root.classList.toggle('is-picking', n > 0);
  bar.hidden = !n;
  bar.replaceChildren();
  if (!n) return;
  const panel = selectionPane;
  const p = fmPanes[panel];
  const entries = fmSelectedEntries(panel);

  const what = document.createElement('span');
  what.className = 'fm-bar-what';
  const b = document.createElement('b');
  b.textContent = plural(n, 'item');
  what.appendChild(b);
  if (p.place === 'trash') {
    what.appendChild(document.createTextNode(' in Trash'));
  } else {
    what.appendChild(document.createTextNode(' selected in '));
    const where = document.createElement('span');
    where.className = 'fm-mono';
    where.textContent = fmFolderLabel(panel);
    what.appendChild(where);
  }
  bar.appendChild(what);

  const clear = fmButton('btn btn-sm btn-outline-secondary', '', 'bi-x-lg', { 'aria-label': 'Clear selection', title: 'Clear selection' });
  const clearText = document.createElement('span');
  clearText.className = 'fm-opt ms-1';
  clearText.textContent = 'Clear';
  clear.appendChild(clearText);
  clear.addEventListener('click', () => { clearFileSelection(); fmFocusRow(panel); });
  bar.appendChild(clear);

  if (p.place === 'trash') {
    const restore = fmButton('btn btn-sm btn-primary', 'Restore ' + n, 'bi-arrow-counterclockwise');
    restore.addEventListener('click', () => fmRestore(panel, entries));
    const forever = fmButton('btn btn-sm btn-outline-secondary fm-danger', 'Delete forever…', 'bi-x-lg');
    forever.addEventListener('click', () => fmDeleteForever(panel, entries));
    bar.append(restore, forever);
    return;
  }

  const why = fmMoveBlocked(panel);
  const move = fmButton('btn btn-sm btn-primary', '', 'bi-arrow-right-square', why ? { disabled: true, 'aria-describedby': 'fmWhy' } : {});
  move.appendChild(document.createTextNode('Move ' + n + ' to '));
  const dest = document.createElement('span');
  dest.className = 'fm-mono';
  dest.textContent = fmFolderLabel(otherPanel(panel));
  move.appendChild(dest);
  move.addEventListener('click', () => fmMoveTo(panel, entries));
  bar.appendChild(move);

  const runBulk = fn => () => { contextMenuPanel = panel; fn(); };
  if (p.place !== 'recent') {
    const nf = fmButton('btn btn-sm btn-outline-secondary fm-opt', 'New folder with these', 'bi-folder-plus');
    nf.addEventListener('click', runBulk(createFolderWithSelection));
    bar.appendChild(nf);
  }
  const cbz = entries.filter(e => e.name.toLowerCase().endsWith('.cbz')).length;
  const combine = fmButton('btn btn-sm btn-outline-secondary fm-opt', 'Combine', 'bi-collection', cbz < 2 ? { disabled: true } : {});
  combine.addEventListener('click', runBulk(showCombineFilesModal));
  bar.appendChild(combine);

  const more = fmButton('btn btn-sm btn-outline-secondary', 'More', null, { 'aria-haspopup': 'menu', 'aria-expanded': 'false' });
  more.addEventListener('click', () => {
    const phone = window.matchMedia('(max-width: 767.98px)').matches;
    const items = [];
    if (phone && p.place !== 'recent') items.push({ label: 'New folder with these', run: runBulk(createFolderWithSelection) });
    if (phone && cbz >= 2) items.push({ label: 'Combine Files', run: runBulk(showCombineFilesModal) });
    items.push({ label: 'Merge Files…', run: runBulk(mergeSelectedPages), disabled: !mergeCandidates() });
    items.push({ label: 'Remove XML', run: runBulk(showRemoveXmlConfirmation), disabled: !cbz });
    fmOpenMenu(more, items);
  });
  bar.appendChild(more);

  const del = fmButton('btn btn-sm btn-outline-secondary fm-danger', 'Delete', 'bi-trash');
  del.addEventListener('click', () => fmDelete(panel, entries));
  bar.appendChild(del);

  if (why) {
    const reason = document.createElement('p');
    reason.className = 'fm-why';
    reason.id = 'fmWhy';
    reason.textContent = why;
    bar.appendChild(reason);
  }
}

// ---------------------------------------------------------------------------
// Menus: one menu element, positioned at the button (or the pointer).
// Items: { h: 'Group' } | '-' | { label, run, danger, disabled }
// ---------------------------------------------------------------------------

let fmMenuBack = null;

function fmTidyMenu(items) {
  const out = [];
  items.forEach((it, i) => {
    if (!it) return;
    if (it === '-') {
      if (out.length && out[out.length - 1] !== '-') out.push(it);
      return;
    }
    if (it.h) {
      // A group heading only when an item follows before the next break.
      const next = items.slice(i + 1).find(x => x && (x === '-' || x.h || x.label));
      if (next && next.label) out.push(it);
      return;
    }
    out.push(it);
  });
  while (out.length && (out[out.length - 1] === '-' || out[out.length - 1].h)) out.pop();
  while (out.length && out[0] === '-') out.shift();
  return out;
}

function fmOpenMenu(anchor, items, point) {
  const menu = document.getElementById('fmMenu');
  if (!menu) return;
  fmCloseMenu(false);
  menu.replaceChildren();
  fmTidyMenu(items).forEach(it => {
    if (it === '-') {
      const hr = document.createElement('hr');
      hr.className = 'dropdown-divider';
      menu.appendChild(hr);
    } else if (it.h) {
      const h = document.createElement('h6');
      h.className = 'dropdown-header';
      h.textContent = it.h;
      menu.appendChild(h);
    } else {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'dropdown-item' + (it.danger ? ' fm-danger' : '');
      b.setAttribute('role', 'menuitem');
      b.tabIndex = -1;
      b.textContent = it.label;
      if (it.disabled) b.disabled = true;
      b.addEventListener('click', () => { fmCloseMenu(true); it.run(); });
      menu.appendChild(b);
    }
  });
  menu.hidden = false;
  const w = menu.offsetWidth;
  const h = menu.offsetHeight;
  const r = point ? { left: point.x, right: point.x, top: point.y, bottom: point.y } : anchor.getBoundingClientRect();
  const left = Math.max(8, Math.min((point ? r.left : r.right - w), window.innerWidth - w - 8));
  const below = r.bottom + 4;
  const top = below + h > window.innerHeight - 8 ? Math.max(8, r.top - h - 4) : below;
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
  fmMenuBack = anchor;
  if (anchor) anchor.setAttribute('aria-expanded', 'true');
  const first = menu.querySelector('[role=menuitem]:not(:disabled)');
  if (first) first.focus();
}

function fmCloseMenu(refocus) {
  const menu = document.getElementById('fmMenu');
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  if (fmMenuBack) {
    fmMenuBack.setAttribute('aria-expanded', 'false');
    if (refocus && document.contains(fmMenuBack)) fmMenuBack.focus();
  }
  fmMenuBack = null;
}

function fmWantToReadItem(path, name, itemType) {
  const on = wantToReadPaths.has(path);
  return { label: on ? 'Remove from Want to Read' : 'Add to Want to Read', run: () => toggleWantToRead(path, name, itemType) };
}

// Jobs on a folder's files: the folder row's menu and the open folder's menu.
function fmFolderJobs(panel, path, name) {
  const providers = getProvidersForPanel(panel);
  const hasGCD = providers.some(pr => pr.provider_type === 'gcd');
  const legacy = gcdAvailable || comicVineAvailable || metronAvailable;
  const lib = () => getLibraryIdForPanel(panel);
  const refresh = () => refreshPanelForPath(path);
  const dirJob = type => () => executeScriptOnDirectory(type, path, panel);
  return [
    { h: 'Metadata' },
    (providers.length || legacy) && { label: 'Fetch Metadata for All Comics in Directory', run: () => fetchDirectoryMetadataForPanel(path, name, panel) },
    hasGCD && { label: 'Fetch GCD Metadata for All Comics', run: () => searchGCDMetadataForDirectory(path, name) },
    providers.length && { label: 'Re-tag with provider…', run: () => CLU.openRetagModal(path, name, lib(), refresh) },
    providers.length && { label: 'Backfill missing fields…', run: () => CLU.openBackfillModal(path, name, lib(), refresh) },
    { label: 'Update XML', run: () => CLU.openUpdateXmlModal(path, name) },
    { h: 'Names' },
    { label: 'Rename files in this directory', run: () => fmRenameDirectory(path, name, panel) },
    { label: 'Smart Rename', run: () => runSmartRename(path, panel) },
    { label: 'Remove Text…', run: () => openCustomRenameModal(path, panel) },
    { label: 'Replace Text…', run: () => openReplaceTextModal(path, panel) },
    { label: 'Rename Series…', run: () => openRenameFilesModal(path, panel) },
    { h: 'Convert' },
    { label: 'Convert CBR→CBZ', run: dirJob('convert') },
    { label: 'PDFs→CBZ', run: dirJob('pdf') },
    { label: 'Rebuild All Files', run: dirJob('rebuild') },
    { label: 'Enhance Images', run: dirJob('enhance_dir') },
    { label: 'Compress CBZ Files', run: dirJob('compress_dir') },
    { h: 'Series' },
    { label: 'Create/Update series.json', run: () => CLU.openSeriesJsonModal(path, name) },
    { label: 'Add CVINFO', run: () => promptForCVInfo(path, panel) },
    { label: 'Missing File Check', run: dirJob('missing') },
    { label: 'Add to Pull List', run: () => CLU.addFolderToPullList(path, name) },
    fmWantToReadItem(path, name, 'folder'),
    { label: 'Show folder information', run: () => fmFolderInfo(path, name) },
    '-',
    { label: 'Remove All XML', run: () => bulkRemoveXmlFromDirectory(path, panel), danger: true },
  ];
}

function fmFileItems(panel, e) {
  const path = e.path;
  const name = e.name;
  const ext = fileExt(name);
  const cbz = isCbzEntry(e);
  const providers = getProvidersForPanel(panel);
  const hasGCD = providers.some(pr => pr.provider_type === 'gcd');
  const fileJob = type => () => executeScriptOnFile(type, path, panel);
  if (!isComicEntry(e)) {
    return [
      isSidecarEntry(e) && { label: 'View ' + name, run: () => fmOpen(panel, e) },
      '-',
      { h: 'File' },
      { label: 'Rename', run: () => fmStartRename(panel, e) },
      { label: 'Move to…', run: () => fmMoveTo(panel, [e]) },
      '-',
      { label: 'Delete', run: () => fmDelete(panel, [e]), danger: true },
    ];
  }
  return [
    cbz && { label: 'CBZ Information', run: () => fmOpen(panel, e) },
    '-',
    { h: 'Metadata' },
    cbz && providers.length && { label: 'Fetch Metadata', run: () => searchMetadataForFile(path, name, panel) },
    cbz && hasGCD && { label: 'Search GCD Database Only', run: () => searchGCDMetadata(path, name) },
    cbz && !providers.length && gcdAvailable && { label: 'Search GCD for Metadata (legacy)', run: () => searchGCDMetadata(path, name) },
    ext !== 'cbr' && { label: 'Force Metadata Match', run: () => forceMetadataMatchForFile(path, name, panel) },
    { h: 'Pages' },
    { label: 'Crop Cover', run: fileJob('crop') },
    { label: 'Remove 1st Image', run: fileJob('remove') },
    { label: 'Edit File', run: () => openEditModal(path) },
    ext === 'cbz' && { label: 'Split File', run: () => openSplitModal(path) },
    { label: 'Add Blank to End', run: fileJob('add') },
    { h: 'File' },
    { label: 'Rename', run: () => fmStartRename(panel, e) },
    { label: 'Move to…', run: () => fmMoveTo(panel, [e]) },
    { label: 'Rebuild', run: fileJob('single_file') },
    { label: 'Enhance', run: fileJob('enhance_single') },
    ext === 'cbz' && { label: 'Compress (smaller file)', run: fileJob('compress') },
    { h: 'Lists' },
    fmWantToReadItem(path, name, 'file'),
    { label: 'Add to Reading List', run: () => openAddToReadingListModal(path) },
    '-',
    { label: 'Delete', run: () => fmDelete(panel, [e]), danger: true },
  ];
}

function fmSelectionItems(panel) {
  const p = fmPanes[panel];
  const entries = fmSelectedEntries(panel);
  const n = entries.length;
  if (p.place === 'trash') {
    return [
      { label: 'Restore ' + n, run: () => fmRestore(panel, entries) },
      '-',
      { label: 'Delete forever…', run: () => fmDeleteForever(panel, entries), danger: true },
    ];
  }
  const cbz = entries.filter(e => e.name.toLowerCase().endsWith('.cbz')).length;
  const runBulk = fn => () => { contextMenuPanel = panel; fn(); };
  return [
    { label: 'Move ' + n + ' to ' + fmFolderLabel(otherPanel(panel)), run: () => fmMoveTo(panel, entries), disabled: !!fmMoveBlocked(panel) },
    p.place !== 'recent' && { label: 'New folder with these', run: runBulk(createFolderWithSelection) },
    cbz >= 2 && { label: 'Combine Files', run: runBulk(showCombineFilesModal) },
    mergeCandidates() && { label: 'Merge Files…', run: runBulk(mergeSelectedPages) },
    cbz && { label: 'Remove XML', run: runBulk(showRemoveXmlConfirmation) },
    '-',
    { label: 'Delete', run: () => fmDelete(panel, entries), danger: true },
  ];
}

function fmRowItems(panel, e) {
  const p = fmPanes[panel];
  if (selectionPane === panel && selectedFiles.size > 1 && selectedFiles.has(e.path)) return fmSelectionItems(panel);
  if (p.place === 'trash') {
    return [
      { label: 'Restore', run: () => fmRestore(panel, [e]), disabled: !e.original },
      isCbzEntry(e) && { label: 'CBZ Information', run: () => showCBZInfo(e.path, e.name, dirName(e.path), []) },
      '-',
      { label: 'Delete forever…', run: () => fmDeleteForever(panel, [e]), danger: true },
    ];
  }
  if (e.type === 'directory') {
    return [
      { label: 'Open', run: () => fmOpen(panel, e) },
      { label: 'Rename', run: () => fmStartRename(panel, e) },
      { label: 'Move to…', run: () => fmMoveTo(panel, [e]) },
      '-',
      ...fmFolderJobs(panel, e.path, e.name),
      { label: 'Delete', run: () => fmDelete(panel, [e]), danger: true },
    ];
  }
  return fmFileItems(panel, e);
}

// The open folder's menu (the ⋮ at the end of the breadcrumb).
function fmPaneItems(panel) {
  const p = fmPanes[panel];
  const path = panelPath(panel);
  if (p.place === 'trash') {
    return [{ label: 'Empty Trash…', run: fmEmptyTrash, danger: true, disabled: !p.items.length || p.trashOff }];
  }
  const items = [{ label: 'New folder…', run: () => openCreateFolderModal(panel) }];
  // A library root or the Downloads root: no whole-library jobs from here.
  if (p.parent) items.push('-', ...fmFolderJobs(panel, path, baseName(path)));
  return items;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function fmEntryAt(panel, k) { return fmView(panel)[k] || null; }

function fmFocusRow(panel, k) {
  const p = fmPanes[panel];
  if (k != null) p.cur = k;
  const list = fmListEl(panel);
  if (!list) return;
  const rows = list.querySelectorAll('.fm-row');
  rows.forEach((li, i) => {
    const on = i === p.cur;
    li.tabIndex = on ? 0 : -1;
    li.querySelectorAll('[data-fm-act]:not(.fm-go)').forEach(b => { b.tabIndex = on ? 0 : -1; });
  });
  const row = rows[p.cur];
  if (row) { row.focus(); row.scrollIntoView({ block: 'nearest' }); } else list.focus();
}

function fmOpen(panel, e) {
  if (!e) return;
  const p = fmPanes[panel];
  if (p.place === 'trash') return;
  if (e.type === 'directory') { loadDirectories(e.path, panel); return; }
  if (isCbzEntry(e)) {
    const comics = p.place === 'recent' ? [] : p.items
      .filter(x => x.type === 'file' && ['cbz', 'zip', 'cbr'].includes(fileExt(x.name)))
      .map(x => x.name).sort();
    showCBZInfo(e.path, e.name, dirName(e.path), comics);
  } else if (isSidecarEntry(e)) {
    CLU.openSidecarViewer(dirName(e.path));
  }
}

function fmUp(panel) {
  const p = fmPanes[panel];
  if (isVirtualPlace(panel) || !p.parent) return;
  // Land on the folder we came from once the listing is in.
  p.focusPath = panelPath(panel);
  loadDirectories(p.parent, panel);
}

function fmRenameDirectory(path, name, panel) {
  fetch('/rename-directory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directory: path })
  })
    .then(r => r.json())
    .then(result => {
      if (result.success) {
        // The server reports how many files actually changed, so a no-op
        // rename is not presented as a success (#716).
        const renamedCount = result.renamed || 0;
        CLU.showToast(renamedCount ? 'Rename Successful' : 'Nothing to Rename',
          result.message || `Renamed ${renamedCount} file(s) in ${name}`, renamedCount ? 'success' : 'info');
        refreshFilePanel(panel);
      } else {
        CLU.showToast('Rename Error', result.error, 'error');
      }
    })
    .catch(error => CLU.showToast('Rename Error', error.message, 'error'));
}

function fmFolderInfo(path, name) {
  fetch(`/folder-size?path=${encodeURIComponent(path)}`)
    .then(res => res.json())
    .then(data => {
      if (data.size == null) { CLU.toast(`Could not read the size of ${name}`, 'error'); return; }
      const parts = [formatSize(data.size)];
      if (data.comic_count) parts.push(plural(data.comic_count, 'comic'));
      if (data.magazine_count) parts.push(plural(data.magazine_count, 'magazine'));
      CLU.toast(`${name}: ${parts.join(' · ')}`, 'info');
    })
    .catch(() => CLU.toast(`Could not read the size of ${name}`, 'error'));
}

// Inline rename: Enter saves, Escape or leaving the field cancels; an empty
// name or one with a slash is refused under the field.
function fmStartRename(panel, e) {
  const p = fmPanes[panel];
  if (p.place === 'trash') return;
  const k = fmView(panel).findIndex(x => x.path === e.path);
  if (k < 0) return;
  p.ren = e.path;
  p.renErr = '';
  p.cur = k;
  fmRender(panel);
  fmFocusRename(panel, e.name);
}

function fmFocusRename(panel, name) {
  const input = fmListEl(panel).querySelector('.fm-in');
  if (!input) return;
  input.focus();
  const stem = name.replace(/\.[^.]+$/, '');
  input.setSelectionRange(0, stem.length || name.length);
}

function fmEndRename(panel, refocus) {
  const p = fmPanes[panel];
  if (!p.ren) return;
  p.ren = null;
  p.renErr = '';
  fmRender(panel);
  if (refocus) fmFocusRow(panel);
}

function fmCommitRename(panel, value) {
  const p = fmPanes[panel];
  const e = p.items.find(x => x.path === p.ren);
  if (!e) { fmEndRename(panel, true); return; }
  const v = value.trim();
  p.renErr = !v ? 'A name can’t be empty.' : /[/\\]/.test(v) ? 'A name can’t contain a slash.' : '';
  if (p.renErr) {
    fmRender(panel);
    fmFocusRename(panel, value);
    const input = fmListEl(panel).querySelector('.fm-in');
    if (input) input.value = value;
    return;
  }
  if (v === e.name) { fmEndRename(panel, true); return; }
  p.renSaving = true;
  renameItem(e.path, v, panel).then(result => {
    p.renSaving = false;
    if (result.ok) { p.ren = null; p.renErr = ''; return; }  // renameItem reloads the pane
    p.renErr = result.error;
    fmRender(panel);
    fmFocusRename(panel, v);
    const input = fmListEl(panel).querySelector('.fm-in');
    if (input) input.value = v;
  });
}

// Move entries to the folder open in the other pane.
function fmMoveTo(panel, entries) {
  entries = entries.filter(Boolean);
  if (!entries.length) return;
  const why = fmMoveBlocked(panel);
  if (why) { CLU.toast(why, 'info'); return; }
  fmMoveInto(panel, entries, panelPath(otherPanel(panel)));
}

// Moves a batch into a folder. Refusals are error toasts; nothing moves.
function fmMoveInto(panel, entries, target) {
  const loop = entries.find(e => e.type === 'directory' && (target === e.path || target.startsWith(e.path + '/')));
  if (loop) {
    CLU.toast(`“${loop.name}” can’t move into itself. Nothing was moved.`, 'error');
    return;
  }
  const moving = entries.filter(e => dirName(e.path) !== target);
  if (!moving.length) {
    CLU.toast(`${entries.length === 1 ? 'It is' : 'They are'} already in ${baseName(target)}.`, 'info');
    return;
  }
  moveMultipleItems(moving.map(e => e.path), target, panel, moving.map(e => ({ path: e.path, type: e.type })));
}

function fmMarkBusy(paths, on) {
  const set = new Set(paths);
  FM_PANELS.forEach(panel => {
    let hit = false;
    fmPanes[panel].items.forEach(e => { if (set.has(e.path)) { e.busy = on; hit = true; } });
    if (hit) fmRender(panel);
  });
}

// Delete: to Trash at once with Undo; with Trash off, the shared confirmation.
function fmDelete(panel, entries) {
  entries = entries.filter(Boolean);
  if (!entries.length || fmPanes[panel].place === 'trash') return;
  const paths = entries.map(e => e.path);
  const refresh = () => { clearFileSelection(); fmRefreshAll(); };
  if (trashEnabled !== true) {
    window._cluDelete = {
      deleteEndpoint: '/delete',
      deletePayload: function (p) { return { target: p }; },
      onDeleteComplete: refresh,
      onDeleteError: function (path, error) { CLU.toast('Error deleting item: ' + error, 'error'); },
      onBulkDeleteComplete: function (ps, results) {
        const failures = results.filter(r => !r.success);
        if (failures.length) CLU.toast(`${plural(failures.length, 'item')} could not be deleted: ${failures[0].error}`, 'error');
        refresh();
      },
      onUndoDelete: fmRefreshAll
    };
    const opts = { permanent: trashEnabled === false };
    if (entries.length === 1) CLU.showDeleteConfirmation(paths[0], entries[0].name, opts);
    else CLU.showBulkDeleteConfirmation(paths, opts);
    return;
  }
  fmMarkBusy(paths, true);
  fetch('/api/delete-multiple', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ targets: paths })
  })
    .then(r => r.json())
    .then(data => {
      if (!data.results) throw new Error(data.error || 'Unexpected response from server');
      const done = data.results.filter(r => r.success);
      const failures = data.results.filter(r => !r.success);
      updateTrashBadge();
      if (done.length) {
        const gone = entries.filter(e => done.some(r => r.path === e.path));
        window._cluDelete = { onUndoDelete: fmRefreshAll };
        if (!CLU.offerUndoDelete(done.map(r => r.trash_name), fmNamed(gone))) {
          CLU.toast(`Deleted ${fmNamed(gone)}`, 'success');
        }
      }
      if (failures.length) {
        CLU.toast(`${plural(failures.length, 'item')} could not be deleted: ${failures[0].error}`, 'error');
      }
      refresh();
    })
    .catch(err => {
      CLU.toast('Delete failed: ' + err.message, 'error');
      fmMarkBusy(paths, false);
    });
}

// One at a time: each restore rewrites the same trash manifest.
function fmRestore(panel, entries) {
  entries = entries.filter(e => e && e.trashName);
  if (!entries.length) return;
  const restored = [];
  const errors = [];
  entries.reduce((chain, e) => chain.then(() =>
    fetch('/api/trash/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: e.trashName })
    })
      .then(r => r.json())
      .then(data => {
        if (data.success) restored.push({ e: e, to: data.restored_path });
        else errors.push(data.conflict ? `a file already exists at ${data.original_path}` : (data.error || 'Failed to restore'));
      })
      .catch(err => errors.push(err.message))
  ), Promise.resolve()).then(() => {
    if (restored.length) {
      const where = restored.length === 1 ? ' to ' + dirName(restored[0].to) : '';
      CLU.toast(`Restored ${fmNamed(restored.map(x => x.e))}${where}`, 'success');
    }
    if (errors.length) CLU.toast(`Could not restore ${plural(errors.length, 'item')}: ${errors[0]}`, 'error');
    clearFileSelection();
    updateTrashBadge();
    fmRefreshAll();
  });
}

function fmConfirmPermanent(label, run) {
  window._cluDelete = { onConfirm: run };
  CLU.showDeleteConfirmation('', label, { permanent: true });
}

function fmDeleteForever(panel, entries) {
  entries = entries.filter(e => e && e.trashName);
  if (!entries.length) return;
  fmConfirmPermanent(fmNamed(entries), () => {
    let ok = 0;
    const errors = [];
    entries.reduce((chain, e) => chain.then(() =>
      fetch('/api/trash/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: e.trashName })
      })
        .then(r => r.json())
        .then(data => { if (data.success) ok++; else errors.push(data.error || 'Failed to delete item'); })
        .catch(err => errors.push(err.message))
    ), Promise.resolve()).then(() => {
      if (ok) CLU.toast(`Deleted ${plural(ok, 'item')} for good`, 'success');
      if (errors.length) CLU.toast(errors[0], 'error');
      clearFileSelection();
      updateTrashBadge();
      fmRefreshAll();
    });
  });
}

// Empty Trash asks first, in the shared confirmation modal (never a native dialog).
function fmEmptyTrash() {
  fmConfirmPermanent('every item in the Trash', () => {
    fetch('/api/trash/empty', { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          CLU.showSuccess(`Emptied trash: ${data.count} item(s), ${CLU.formatFileSize(data.size_freed)} freed`);
        } else {
          CLU.showError('Failed to empty trash');
        }
        clearFileSelection();
        updateTrashBadge();
        fmRefreshAll();
      })
      .catch(err => CLU.showError('Error emptying trash: ' + err.message));
  });
}

// ---------------------------------------------------------------------------
// Events: delegated per list, so a row carries no listeners of its own.
// ---------------------------------------------------------------------------

function fmRowOf(target) {
  const row = target.closest && target.closest('.fm-row');
  if (!row) return null;
  const list = row.closest('.fm-list');
  const panel = list && list.id.replace(/-list$/, '');
  if (!fmPanes[panel]) return null;
  const k = +row.dataset.k;
  return { panel: panel, row: row, k: k, e: fmEntryAt(panel, k) };
}

function fmClickRow(panel, k, e, ev) {
  const p = fmPanes[panel];
  const rows = fmView(panel);
  if (ev.shiftKey && p.anchor) {
    const a = rows.findIndex(x => x.path === p.anchor);
    if (a >= 0) {
      const [lo, hi] = a < k ? [a, k] : [k, a];
      fmSelect(panel, rows.slice(lo, hi + 1).map(x => x.path), 'only');
    } else {
      fmSelect(panel, [e.path], 'only');
      p.anchor = e.path;
    }
  } else if (ev.ctrlKey || ev.metaKey) {
    fmSelect(panel, [e.path], 'toggle');
    p.anchor = e.path;
  } else {
    // Clicking the only selected row clears it.
    const only = selectionPane === panel && selectedFiles.size === 1 && selectedFiles.has(e.path);
    fmSelect(panel, only ? [] : [e.path], 'only');
    p.anchor = e.path;
  }
  fmFocusRow(panel, k);
}

function fmBindList(panel) {
  const list = fmListEl(panel);
  const pane = fmPaneEl(panel);
  if (!list || !pane) return;

  pane.addEventListener('focusin', () => fmSetActive(panel));
  pane.addEventListener('pointerdown', () => fmSetActive(panel));

  list.addEventListener('click', ev => {
    const hit = fmRowOf(ev.target);
    if (!hit || !hit.e) return;
    const p = fmPanes[panel];
    if (p.ren === hit.e.path) return;
    const act = ev.target.closest('[data-fm-act]');
    if (act) {
      ev.stopPropagation();
      const a = act.dataset.fmAct;
      p.cur = hit.k;
      if (a === 'menu') fmOpenMenu(act, fmRowItems(panel, hit.e));
      else if (a === 'open' || a === 'info') fmOpen(panel, hit.e);
      else if (a === 'restore') fmRestore(panel, [hit.e]);
      return;
    }
    if (ev.target.classList.contains('fm-ck')) {
      fmSelect(panel, [hit.e.path], 'toggle');
      p.anchor = hit.e.path;
      fmFocusRow(panel, hit.k);
      return;
    }
    fmClickRow(panel, hit.k, hit.e, ev);
  });

  list.addEventListener('dblclick', ev => {
    const hit = fmRowOf(ev.target);
    if (!hit || !hit.e || ev.target.closest('button, input')) return;
    fmOpen(panel, hit.e);
  });

  // Right-click opens the row's menu (the selection's, on a selected row).
  list.addEventListener('contextmenu', ev => {
    const hit = fmRowOf(ev.target);
    if (!hit || !hit.e || fmPanes[panel].ren) return;
    ev.preventDefault();
    if (!(selectionPane === panel && selectedFiles.has(hit.e.path))) {
      fmSelect(panel, [hit.e.path], 'only');
      fmPanes[panel].anchor = hit.e.path;
    }
    fmFocusRow(panel, hit.k);
    fmOpenMenu(hit.row.querySelector('[data-fm-act="menu"]'), fmRowItems(panel, hit.e), { x: ev.clientX, y: ev.clientY });
  });

  list.addEventListener('keydown', ev => fmListKey(panel, ev));

  // Leaving the rename field cancels it (Enter saves first).
  list.addEventListener('focusout', ev => {
    if (!ev.target.classList.contains('fm-in')) return;
    setTimeout(() => {
      const p = fmPanes[panel];
      if (p.ren && !p.renSaving && !(document.activeElement && document.activeElement.classList.contains('fm-in'))) {
        fmEndRename(panel, false);
      }
    }, 0);
  });

  list.addEventListener('dragstart', ev => {
    const hit = fmRowOf(ev.target);
    if (!hit || !hit.e) return;
    if (!(selectionPane === panel && selectedFiles.has(hit.e.path))) {
      fmSelect(panel, [hit.e.path], 'only');
      fmPanes[panel].anchor = hit.e.path;
    }
    const items = fmSelectedEntries(panel);
    fmDrag = { panel: panel, items: items };
    ev.dataTransfer.effectAllowed = 'move';
    ev.dataTransfer.setData('text/plain', JSON.stringify(items.map(x => ({ path: x.path, type: x.type }))));
  });
  list.addEventListener('dragend', () => { fmDrag = null; fmClearDrop(); });
  list.addEventListener('dragover', ev => fmDragOver(panel, ev));
  list.addEventListener('dragleave', ev => { if (!list.contains(ev.relatedTarget)) fmClearDrop(); });
  list.addEventListener('drop', ev => fmDrop(panel, ev));
}

function fmClearDrop() {
  document.querySelectorAll('.fm-drop').forEach(x => x.classList.remove('fm-drop'));
  fmStopAutoScroll();
}

// Where a drag over this pane would land: a folder row, or the pane's folder.
function fmDropTarget(panel, ev) {
  const external = !fmDrag && ev.dataTransfer && Array.from(ev.dataTransfer.types || []).includes('Files');
  const hit = fmRowOf(ev.target);
  if (fmDrag && hit && hit.e && hit.e.type === 'directory' && fmPanes[panel].place !== 'trash' &&
      !fmDrag.items.some(x => x.path === hit.e.path)) {
    return { el: hit.row, path: hit.e.path };
  }
  if (isVirtualPlace(panel) || !panelPath(panel)) return null;
  if (external || (fmDrag && fmDrag.panel !== panel)) return { el: fmListEl(panel), path: panelPath(panel), external: external };
  return null;
}

let fmAutoScroll = null;
function fmStopAutoScroll() { clearInterval(fmAutoScroll); fmAutoScroll = null; }

function fmDragOver(panel, ev) {
  const list = fmListEl(panel);
  const r = list.getBoundingClientRect();
  const dir = ev.clientY - r.top < 40 ? -6 : r.bottom - ev.clientY < 40 ? 6 : 0;
  fmStopAutoScroll();
  if (dir) fmAutoScroll = setInterval(() => { list.scrollTop += dir; }, 30);
  const t = fmDropTarget(panel, ev);
  document.querySelectorAll('.fm-drop').forEach(x => { if (!t || x !== t.el) x.classList.remove('fm-drop'); });
  if (!t) return;
  ev.preventDefault();
  t.el.classList.add('fm-drop');
}

function fmDrop(panel, ev) {
  const t = fmDropTarget(panel, ev);
  fmClearDrop();
  if (!t) return;
  ev.preventDefault();
  if (t.external) {
    handleExternalFileDrop(ev.dataTransfer.files, t.path, panel);
    return;
  }
  const from = fmDrag;
  fmDrag = null;
  if (from) fmMoveInto(from.panel, from.items, t.path);
}

function fmListKey(panel, ev) {
  const t = ev.target;
  const p = fmPanes[panel];
  if (t.classList.contains('fm-in')) {
    if (ev.key === 'Enter') { ev.preventDefault(); fmCommitRename(panel, t.value); }
    else if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); fmEndRename(panel, true); }
    return;
  }
  const rows = fmView(panel);
  const hit = fmRowOf(t);
  const k = hit ? hit.k : p.cur;
  const e = rows[k] || null;
  const onRow = !!hit && t === hit.row;
  const key = ev.key;
  if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'PageDown', 'PageUp'].includes(key) && rows.length) {
    ev.preventDefault();
    const step = key === 'PageDown' ? 10 : key === 'PageUp' ? -10 : key === 'ArrowDown' ? 1 : -1;
    const to = key === 'Home' ? 0 : key === 'End' ? rows.length - 1 : Math.max(0, Math.min(rows.length - 1, k + step));
    if (ev.shiftKey) {
      if (!p.anchor && e) p.anchor = e.path;
      const a = Math.max(0, rows.findIndex(x => x.path === p.anchor));
      const [lo, hi] = a < to ? [a, to] : [to, a];
      fmSelect(panel, rows.slice(lo, hi + 1).map(x => x.path), 'only');
    }
    fmFocusRow(panel, to);
    return;
  }
  if (!e) return;
  if (key === ' ' && onRow) {
    ev.preventDefault();
    fmSelect(panel, [e.path], 'toggle');
    p.anchor = e.path;
  } else if (key === 'Enter' && onRow) {
    ev.preventDefault();
    fmOpen(panel, e);
  } else if (key === 'F2' && p.place !== 'trash') {
    ev.preventDefault();
    fmStartRename(panel, e);
  } else if (key === 'ContextMenu' || (key === 'F10' && ev.shiftKey)) {
    ev.preventDefault();
    fmOpenMenu(hit ? hit.row.querySelector('[data-fm-act="menu"]') : null, fmRowItems(panel, e));
  } else if ((key === 'a' || key === 'A') && (ev.metaKey || ev.ctrlKey)) {
    ev.preventDefault();
    fmSelect(panel, rows.map(x => x.path), 'only');
  } else if (fmPaneKey(panel, ev, e)) {
    ev.preventDefault();
  }
}

// Shortcuts that work on the pane, from a row or from the page itself.
function fmPaneKey(panel, ev, e) {
  const p = fmPanes[panel];
  const key = ev.key;
  if (ev.altKey || ((ev.metaKey || ev.ctrlKey) && key !== 'Backspace')) return false;
  const targets = () => fmTargets(panel, e);
  if (key === 'Backspace' && !ev.metaKey) { fmUp(panel); return true; }
  if ((key === 'm' || key === 'M') && p.place !== 'trash') {
    const list = targets();
    if (!list.length) return false;
    fmMoveTo(panel, list);
    return true;
  }
  if ((key === 'Delete' || (key === 'Backspace' && ev.metaKey)) && p.place !== 'trash') {
    const list = targets();
    if (!list.length) return false;
    fmDelete(panel, list);
    return true;
  }
  if (key === 'Escape' && selectionPane === panel) { clearFileSelection(); return true; }
  return false;
}

function fmInit() {
  const root = document.getElementById('fm');
  if (!root) return;
  FM_PANELS.forEach(fmBindList);
  fmSetTab('source');

  document.querySelectorAll('[data-fm-tab]').forEach(b => b.addEventListener('click', () => fmSetTab(b.dataset.fmTab)));
  document.querySelectorAll('[data-fm-pane-menu]').forEach(b => {
    b.addEventListener('click', () => {
      const panel = b.closest('.fm-pane').dataset.panel;
      fmSetActive(panel);
      fmOpenMenu(b, fmPaneItems(panel));
    });
  });

  const menu = document.getElementById('fmMenu');
  menu.addEventListener('keydown', ev => {
    const items = [...menu.querySelectorAll('[role=menuitem]:not(:disabled)')];
    const k = items.indexOf(document.activeElement);
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      const n = items.length;
      if (n) items[(k + (ev.key === 'ArrowDown' ? 1 : -1) + n) % n].focus();
    } else if (ev.key === 'Home' || ev.key === 'End') {
      ev.preventDefault();
      if (items.length) items[ev.key === 'Home' ? 0 : items.length - 1].focus();
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      fmCloseMenu(true);
    } else if (ev.key === 'Tab') {
      fmCloseMenu(false);
    }
  });
  document.addEventListener('pointerdown', ev => {
    if (!menu.hidden && !menu.contains(ev.target) && !(fmMenuBack && fmMenuBack.contains(ev.target))) fmCloseMenu(false);
  });
  window.addEventListener('resize', () => fmCloseMenu(false));
  document.addEventListener('scroll', () => fmCloseMenu(false), true);

  // The shortcuts reach the last-used pane when nothing else has the focus.
  document.addEventListener('keydown', ev => {
    const t = ev.target;
    if (t !== document.body || document.querySelector('.modal.show')) return;
    if (fmPaneKey(fmActive, ev, null)) ev.preventDefault();
  });
}

// Helper function to calculate "time ago" string
function getTimeAgo(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// Initialize when DOM is loaded. The library dropdowns (files.html) open the
// first folder in each pane once the libraries are known.
document.addEventListener('DOMContentLoaded', function () {
  checkGCDAvailability();
  checkComicVineAvailability();
  checkMetronAvailability();
  fmInit();

  // #updateXmlConfirmBtn is wired by clu-update-xml.js, which owns the modal —
  // binding it here too made every update submit twice.

  // Add event listener for Update XML field dropdown change
  const updateXmlFieldSelect = document.getElementById('updateXmlField');
  if (updateXmlFieldSelect) updateXmlFieldSelect.addEventListener('change', CLU.updateXmlFieldChanged);
});

// Poll one op until it leaves 'running'/'queued', then call done(op). The op is
// null when it already finished and was pruned -- absent means done, not failed.
// Polls /api/operation/<id>, never /api/operations: that one clears the
// header's pending notifications, so only base.html may poll it.
function pollOperation(opId, done) {
  let busy = false;  // skip a tick if the previous poll is still in-flight
  const interval = setInterval(() => {
    if (busy) return;
    busy = true;
    fetch('/api/operation/' + encodeURIComponent(opId)).then(r => r.json()).then(data => {
      const op = data.operation || null;
      if (op && (op.status === 'running' || op.status === 'queued')) return;
      clearInterval(interval);
      done(op);
    }).catch(() => {}).finally(() => { busy = false; });
  }, 2000);
  setTimeout(() => clearInterval(interval), 1800000); // 30min safety
}

// Wait for a move op, then toast with Undo and refresh both panes. The move
// itself is fast; metadata for the moved files runs afterwards as its own
// queued job, which the header's operations indicator follows.
function waitForMoveCompletion(opId, label, itemCount, undo) {
  pollOperation(opId, op => {
    const detail = (op && op.detail) || '';
    const tagNote = detail.includes('metadata queued') ? ' Metadata is being fetched in the background.' : '';
    if (op && op.status === 'error') {
      CLU.toast(detail || `Some of ${itemCount} move(s) failed`, 'error');
    } else {
      CLU.toast(`Moved ${label}.` + tagNote, 'success', undo ? { duration: 8000, action: { label: 'Undo', onClick: undo } } : undefined);
    }
    fmRefreshAll();
  });
}

// Batch renames run on the shared file-job queue (core/job_queue.py), so one
// can wait behind a tagging or Remove XML job. Say which it is.
function renameStartedHtml(data, startedText) {
  return data.queued
    ? '<strong>Queued.</strong> It will start when the current job finishes.'
    : '<strong>Started!</strong> ' + startedText;
}

// Wait for a batch-rename op, then toast and refresh.
// The heavy work runs in a background thread server-side, so the UI stays responsive.
function waitForRenameCompletion(opId, itemCount, refreshFn) {
  pollOperation(opId, op => {
    if (op && op.status === 'error') {
      CLU.showToast('Rename Errors', `Some of ${itemCount} rename(s) failed`, 'warning');
    } else {
      CLU.showToast('Rename Complete',
        itemCount === 1 ? 'Successfully renamed 1 file' : `Successfully renamed ${itemCount} files`,
        'success');
    }
    if (typeof refreshFn === 'function') refreshFn();
  });
}

/**
 * Handle files dropped from the desktop onto a panel (upload).
 * Posts to /upload-to-folder and refreshes the directory listing.
 */
function handleExternalFileDrop(fileList, targetPath, panel) {
  if (!targetPath || targetPath === 'recent-files' || targetPath === 'trash') {
    CLU.showToast('Upload Error', 'Navigate to a directory first before uploading files.', 'error');
    return;
  }

  const files = Array.from(fileList);
  if (files.length === 0) return;

  CLU.showToast('Uploading', `Uploading ${files.length} file(s) to ${targetPath.split('/').pop() || targetPath}...`, 'info');

  const formData = new FormData();
  formData.append('target_dir', targetPath);
  // folder.* / header.* / overlay.png become the folder's art, stored in the
  // cache volume rather than written into the library (#720).
  formData.append('folder_art', '1');
  files.forEach(file => {
    formData.append('files', file);
  });

  fetch('/upload-to-folder', {
    method: 'POST',
    body: formData
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        let msg = `Uploaded ${data.total_uploaded} file(s)`;
        if (data.total_skipped > 0) {
          msg += `, skipped ${data.total_skipped}`;
        }
        if (data.total_errors > 0) {
          msg += `, ${data.total_errors} error(s)`;
        }
        CLU.showToast('Upload Complete', msg, data.total_errors > 0 ? 'warning' : 'success');

        // Refresh the panel to show newly uploaded files
        loadDirectories(targetPath, panel);
      } else {
        CLU.showToast('Upload Failed', data.error || 'Unknown error', 'error');
      }
    })
    .catch(error => {
      console.error('Upload error:', error);
      CLU.showToast('Upload Failed', error.message, 'error');
    });
}


// Create Folder Modal functionality.
let createFolderModalEl = document.getElementById('createFolderModal');
let createFolderNameInput = document.getElementById('createFolderName');
let confirmCreateFolderBtn = document.getElementById('confirmCreateFolderBtn');

// Focus input when modal opens (only if modal exists)
if (createFolderModalEl) {
  createFolderModalEl.addEventListener('shown.bs.modal', function () {
    createFolderNameInput.focus();
  });
}

// Open modal function: the folder is made in the pane it was asked from.
function openCreateFolderModal(panel) {
  fmCreatePanel = fmPanes[panel] ? panel : fmActive;
  document.getElementById('createFolderName').value = '';
  let createFolderModal = new bootstrap.Modal(createFolderModalEl);
  createFolderModal.show();
}

// Function to create folder
function createFolder() {
  let folderName = createFolderNameInput.value.trim();
  if (!folderName) {
    CLU.toast('Folder name cannot be empty.', 'warning');
    createFolderNameInput.focus();
    return;
  }

  if (/[/\\]/.test(folderName)) {
    CLU.toast('A folder name can\u2019t contain a slash.', 'warning');
    createFolderNameInput.focus();
    return;
  }
  const panel = fmCreatePanel;
  let fullPath = panelPath(panel) + '/' + folderName;

  fetch('/create-folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: fullPath })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        let createFolderModal = bootstrap.Modal.getInstance(createFolderModalEl);
        createFolderModal.hide();
        currentFilter[panel] = 'all';
        refreshFilePanel(panel);
      } else {
        CLU.toast(data.error || 'Error creating folder.', 'error');
      }
    })
    .catch(err => {
      console.error('Error creating folder:', err);
      CLU.toast('An unexpected error occurred.', 'error');
    });
}

// Click event for "Create" button (only if button exists)
if (confirmCreateFolderBtn) {
  confirmCreateFolderBtn.addEventListener('click', createFolder);
}

// Enter key support comes from data-enter-confirm on #createFolderModal (clu-utils.js)


// One request, one server-side op for the whole selection (core/job_queue.py).
// One refused item refuses the batch, so nothing moves and the panes stay.
function moveMultipleItems(filePaths, targetFolder, panel, itemsWithTypes = null, isUndo = false) {
  const entries = filePaths.map(f => {
    const fileObj = normalizeFile(f);
    const sourcePath = typeof fileObj === 'string' ? fileObj : fileObj.path || fileObj.name;
    return { source: sourcePath, destination: targetFolder + '/' + baseName(sourcePath) };
  });
  if (entries.length === 0) return;
  const label = (entries.length === 1 ? '“' + baseName(entries[0].source) + '”' : plural(entries.length, 'item')) +
    ' to ' + (baseName(targetFolder) || targetFolder);
  fmMarkBusy(entries.map(e => e.source), true);

  fetch('/move-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: entries.map(e => ({ source: e.source, destination: e.destination })) })
  })
  .then(res => res.json())
  .then(data => {
    if (!data.success) {
      CLU.toast((isUndo ? 'Undo failed: ' : 'Nothing was moved: ') + (data.error || 'No items could be moved'), 'error');
      fmRefreshAll();
      return;
    }
    clearFileSelection();
    // Undo sends each item back where it came from. shortcut: an item that
    // auto-metadata renamed after the move is no longer at its destination,
    // so its Undo is refused; acceptable until the op reports final paths.
    const undo = isUndo ? null : () => {
      const back = {};
      entries.forEach(e => { (back[dirName(e.source)] = back[dirName(e.source)] || []).push(e.destination); });
      Object.entries(back).forEach(([dir, paths]) => moveMultipleItems(paths, dir, panel, null, true));
    };
    waitForMoveCompletion(data.op_id, label, entries.length, undo);
  })
  .catch(err => {
    CLU.toast('Move failed: ' + err.message, 'error');
    fmRefreshAll();
  });
}

// CBZ info – contract setup, adapts arguments for CLU.showCBZInfo
function showCBZInfo(filePath, fileName, directoryPath, fileList) {
  var opts = {};
  if (directoryPath && fileList) { opts.directoryPath = directoryPath; opts.fileList = fileList; }
  CLU.showCBZInfo(filePath, fileName, opts);
}

// CBZ info nav/clear/page viewer – handled by clu-cbz-info.js (DOMContentLoaded wiring is there too)
// Custom Rename Modal functionality
let customRenameModal;
let currentRenameDirectory = '';
let currentRenamePanel = '';
let fileList = [];

function openCustomRenameModal(directoryPath, panel) {
  console.log('openCustomRenameModal called with:', directoryPath, panel);
  currentRenameDirectory = directoryPath;
  currentRenamePanel = panel;

  // Validate that we have a valid directory path
  if (!directoryPath || directoryPath === '') {
    console.error('Invalid directory path provided to openCustomRenameModal:', directoryPath);
    CLU.toast('Error: No directory path provided for rename operation.', 'error');
    return;
  }

  // Reset modal state
  document.getElementById('textToRemove').value = '';
  document.getElementById('renamePreview').style.display = 'none';
  document.getElementById('previewRenameBtn').style.display = 'inline-block';
  document.getElementById('executeRenameBtn').style.display = 'none';

  // Show modal
  const modalEl = document.getElementById('customRenameModal');
  customRenameModal = new bootstrap.Modal(modalEl);
  customRenameModal.show();

  // Focus on input when modal opens
  modalEl.addEventListener('shown.bs.modal', function () {
    document.getElementById('textToRemove').focus();
  }, { once: true });
}

function previewCustomRename() {
  const textToRemove = document.getElementById('textToRemove').value;

  console.log('previewCustomRename called');
  console.log('currentRenameDirectory:', currentRenameDirectory);
  console.log('currentRenamePanel:', currentRenamePanel);
  console.log('textToRemove:', textToRemove);

  if (!textToRemove.trim()) {
    CLU.toast('Please enter text to remove from filenames.', 'warning');
    return;
  }

  if (!currentRenameDirectory || currentRenameDirectory === '') {
    CLU.toast('Error: No directory selected for rename operation.', 'error');
    console.error('currentRenameDirectory is empty');
    return;
  }

  // Fetch files in the directory
  const url = `/list-directories?path=${encodeURIComponent(currentRenameDirectory)}`;
  console.log('Fetching URL:', url);
  fetch(url)
    .then(response => response.json())
    .then(data => {
      if (data.error) {
        throw new Error(data.error);
      }

      fileList = [];
      const previewList = document.getElementById('renamePreviewList');
      previewList.innerHTML = '';

      // Filter only files (not directories) that contain the text to remove
      const filesToRename = (data.files || []).filter(file => {
        const fileData = normalizeFile(file);
        const nameWithoutExtension = fileData.name.substring(0, fileData.name.lastIndexOf('.')) || fileData.name;
        return nameWithoutExtension.includes(textToRemove);
      });

      if (filesToRename.length === 0) {
        previewList.innerHTML = '<div class="text-warning">No files found containing the specified text.</div>';
      } else {
        filesToRename.forEach(file => {
          const fileData = normalizeFile(file);
          const nameWithoutExtension = fileData.name.substring(0, fileData.name.lastIndexOf('.')) || fileData.name;
          const extension = fileData.name.substring(fileData.name.lastIndexOf('.')) || '';
          const newNameWithoutExtension = nameWithoutExtension.replace(new RegExp(escapeRegExp(textToRemove), 'g'), '');
          const newName = newNameWithoutExtension + extension;

          fileList.push({
            oldPath: `${currentRenameDirectory}/${fileData.name}`,
            newName: newName,
            oldName: fileData.name
          });

          const previewItem = document.createElement('div');
          previewItem.className = 'mb-2 p-2 border rounded';
          previewItem.innerHTML = `
                <div><strong>Old:</strong> <code>${CLU.escapeHtml(fileData.name)}</code></div>
                <div><strong>New:</strong> <code>${CLU.escapeHtml(newName)}</code></div>
              `;
          previewList.appendChild(previewItem);
        });
      }

      // Show preview and execute button
      document.getElementById('renamePreview').style.display = 'block';
      if (filesToRename.length > 0) {
        document.getElementById('executeRenameBtn').style.display = 'inline-block';
      }
    })
    .catch(error => {
      console.error('Error fetching directory contents:', error);
      CLU.toast('Error fetching directory contents: ' + error.message, 'error');
    });
}

function executeCustomRename() {
  if (fileList.length === 0) {
    CLU.toast('No files to rename.', 'warning');
    return;
  }

  // Disable buttons during execution
  document.getElementById('previewRenameBtn').disabled = true;
  document.getElementById('executeRenameBtn').disabled = true;
  document.getElementById('executeRenameBtn').textContent = 'Renaming...';

  const renames = fileList.map(file => ({
    old: file.oldPath,
    new: `${currentRenameDirectory}/${file.newName}`
  }));
  const directory = currentRenameDirectory;
  const panel = currentRenamePanel;
  const count = renames.length;

  // One batched request: the server renames all files in a background thread and
  // reconciles each affected series once (progress shown in the nav ops indicator).
  fetch('/custom-rename-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ renames })
  })
    .then(response => response.json())
    .then(data => {
      if (!data.success) {
        CLU.showToast('Rename Failed', data.error || 'Unknown error', 'error');
        return;
      }
      const renamePreviewList = document.getElementById('renamePreviewList');
      renamePreviewList.innerHTML = `
            <div class="alert alert-success text-center">
              <i class="bi bi-check-circle-fill me-2"></i>
              ${renameStartedHtml(data, `Renaming ${count} files…`)}
            </div>
          `;
      document.getElementById('previewRenameBtn').style.display = 'none';
      document.getElementById('executeRenameBtn').style.display = 'none';
      setTimeout(() => customRenameModal.hide(), 1500);
      waitForRenameCompletion(data.op_id, count, () => loadDownloads(directory, panel));
    })
    .catch(error => {
      console.error('Error during rename operation:', error);
      CLU.showToast('Rename Failed', 'Error during rename operation: ' + error.message, 'error');
    })
    .finally(() => {
      // Re-enable buttons
      document.getElementById('previewRenameBtn').disabled = false;
      document.getElementById('executeRenameBtn').disabled = false;
      document.getElementById('executeRenameBtn').textContent = 'Execute Rename';
    });
}

// Replace Text Modal functionality
let replaceTextModal;
let currentReplaceDirectory = '';
let currentReplacePanel = '';
let replaceFileList = [];

function openReplaceTextModal(directoryPath, panel) {
  console.log('openReplaceTextModal called with:', directoryPath, panel);
  currentReplaceDirectory = directoryPath;
  currentReplacePanel = panel;

  // Validate that we have a valid directory path
  if (!directoryPath || directoryPath === '') {
    console.error('Invalid directory path provided to openReplaceTextModal:', directoryPath);
    CLU.toast('Error: No directory path provided for replace operation.', 'error');
    return;
  }

  // Reset modal state
  document.getElementById('textToReplace').value = '';
  document.getElementById('replacementText').value = '';
  document.getElementById('replacePreview').style.display = 'none';
  document.getElementById('previewReplaceBtn').style.display = 'inline-block';
  document.getElementById('executeReplaceBtn').style.display = 'none';

  // Show modal
  const modalEl = document.getElementById('replaceTextModal');
  replaceTextModal = new bootstrap.Modal(modalEl);
  replaceTextModal.show();

  // Focus on input when modal opens
  modalEl.addEventListener('shown.bs.modal', function () {
    document.getElementById('textToReplace').focus();
  }, { once: true });
}

function previewReplaceText() {
  const textToReplace = document.getElementById('textToReplace').value;
  const replacementText = document.getElementById('replacementText').value;

  console.log('previewReplaceText called');
  console.log('currentReplaceDirectory:', currentReplaceDirectory);
  console.log('currentReplacePanel:', currentReplacePanel);
  console.log('textToReplace:', textToReplace);
  console.log('replacementText:', replacementText);

  if (!textToReplace.trim()) {
    CLU.toast('Please enter text to replace in filenames.', 'warning');
    return;
  }

  if (!currentReplaceDirectory || currentReplaceDirectory === '') {
    CLU.toast('Error: No directory selected for replace operation.', 'error');
    console.error('currentReplaceDirectory is empty');
    return;
  }

  // Fetch files in the directory
  const url = `/list-directories?path=${encodeURIComponent(currentReplaceDirectory)}`;
  console.log('Fetching URL:', url);
  fetch(url)
    .then(response => response.json())
    .then(data => {
      if (data.error) {
        throw new Error(data.error);
      }

      replaceFileList = [];
      const previewList = document.getElementById('replacePreviewList');
      previewList.innerHTML = '';

      // Filter only files (not directories) that contain the text to replace
      const filesToRename = (data.files || []).filter(file => {
        const fileData = normalizeFile(file);
        const nameWithoutExtension = fileData.name.substring(0, fileData.name.lastIndexOf('.')) || fileData.name;
        return nameWithoutExtension.includes(textToReplace);
      });

      if (filesToRename.length === 0) {
        previewList.innerHTML = '<div class="text-warning">No files found containing the specified text.</div>';
      } else {
        filesToRename.forEach(file => {
          const fileData = normalizeFile(file);
          const nameWithoutExtension = fileData.name.substring(0, fileData.name.lastIndexOf('.')) || fileData.name;
          const extension = fileData.name.substring(fileData.name.lastIndexOf('.')) || '';
          const newNameWithoutExtension = nameWithoutExtension.replace(new RegExp(escapeRegExp(textToReplace), 'g'), replacementText);
          const newName = newNameWithoutExtension + extension;

          replaceFileList.push({
            oldPath: `${currentReplaceDirectory}/${fileData.name}`,
            newName: newName,
            oldName: fileData.name
          });

          const previewItem = document.createElement('div');
          previewItem.className = 'mb-2 p-2 border rounded';
          previewItem.innerHTML = `
                <div><strong>Old:</strong> <code>${CLU.escapeHtml(fileData.name)}</code></div>
                <div><strong>New:</strong> <code>${CLU.escapeHtml(newName)}</code></div>
              `;
          previewList.appendChild(previewItem);
        });
      }

      // Show preview and execute button
      document.getElementById('replacePreview').style.display = 'block';
      if (filesToRename.length > 0) {
        document.getElementById('executeReplaceBtn').style.display = 'inline-block';
      }
    })
    .catch(error => {
      console.error('Error fetching directory contents:', error);
      CLU.toast('Error fetching directory contents: ' + error.message, 'error');
    });
}

function executeReplaceText() {
  if (replaceFileList.length === 0) {
    CLU.toast('No files to rename.', 'warning');
    return;
  }

  // Disable buttons during execution
  document.getElementById('previewReplaceBtn').disabled = true;
  document.getElementById('executeReplaceBtn').disabled = true;
  document.getElementById('executeReplaceBtn').textContent = 'Replacing...';

  const renames = replaceFileList.map(file => ({
    old: file.oldPath,
    new: `${currentReplaceDirectory}/${file.newName}`
  }));
  const directory = currentReplaceDirectory;
  const panel = currentReplacePanel;
  const count = renames.length;

  fetch('/custom-rename-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ renames })
  })
    .then(response => response.json())
    .then(data => {
      if (!data.success) {
        CLU.showToast('Replace Failed', data.error || 'Unknown error', 'error');
        return;
      }
      const replacePreviewList = document.getElementById('replacePreviewList');
      replacePreviewList.innerHTML = `
            <div class="alert alert-success text-center">
              <i class="bi bi-check-circle-fill me-2"></i>
              ${renameStartedHtml(data, `Replacing text in ${count} files…`)}
            </div>
          `;
      document.getElementById('previewReplaceBtn').style.display = 'none';
      document.getElementById('executeReplaceBtn').style.display = 'none';
      setTimeout(() => replaceTextModal.hide(), 1500);
      waitForRenameCompletion(data.op_id, count, () => loadDownloads(directory, panel));
    })
    .catch(error => {
      console.error('Error during replace operation:', error);
      CLU.showToast('Replace Failed', 'Error during replace operation: ' + error.message, 'error');
    })
    .finally(() => {
      // Re-enable buttons
      document.getElementById('previewReplaceBtn').disabled = false;
      document.getElementById('executeReplaceBtn').disabled = false;
      document.getElementById('executeReplaceBtn').textContent = 'Execute Replace';
    });
}

// Helper function to escape special regex characters
function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Enter key support comes from data-enter-confirm on #customRenameModal (clu-utils.js)

// ============================================================================
// Series Rename Modal functionality
// ============================================================================
let renameFilesModal;
let currentSeriesRenameDirectory = '';
let currentSeriesRenamePanel = '';
let seriesFileList = [];

function openRenameFilesModal(directoryPath, panel) {
  console.log('openRenameFilesModal called with:', directoryPath, panel);
  currentSeriesRenameDirectory = directoryPath;
  currentSeriesRenamePanel = panel;

  // Validate that we have a valid directory path
  if (!directoryPath || directoryPath === '') {
    console.error('Invalid directory path provided to openRenameFilesModal:', directoryPath);
    CLU.showToast('Path Error', 'No directory path provided for series rename operation.', 'error');
    return;
  }

  // Reset modal state
  document.getElementById('newSeriesName').value = '';
  document.getElementById('renameFilesPreview').style.display = 'none';
  document.getElementById('previewRenameFilesBtn').style.display = 'inline-block';
  document.getElementById('executeRenameFilesBtn').style.display = 'none';
  document.getElementById('renameFilesPreviewList').innerHTML = '';

  // Initialize modal
  if (!renameFilesModal) {
    renameFilesModal = new bootstrap.Modal(document.getElementById('renameFilesModal'));
  }

  // Show modal
  renameFilesModal.show();

  // Focus on input field
  setTimeout(() => {
    document.getElementById('newSeriesName').focus();
  }, 300);
}

function previewRenameFiles() {
  const newSeriesName = document.getElementById('newSeriesName').value.trim();

  if (!newSeriesName) {
    CLU.showToast('Input Required', 'Please enter a new series name.', 'warning');
    return;
  }

  console.log('previewRenameFiles called with series name:', newSeriesName);

  // Fetch file list from the directory using the correct endpoint
  fetch(`/list-directories?path=${encodeURIComponent(currentSeriesRenameDirectory)}`)
    .then(response => response.json())
    .then(data => {
      console.log('Directory listing response:', data);

      if (data.error) {
        CLU.showToast('Directory Error', data.error, 'error');
        return;
      }

      if (!data.files || data.files.length === 0) {
        CLU.showToast('No Files Found', 'No files found in the directory.', 'warning');
        return;
      }

      // Filter only comic files
      const comicFiles = data.files.filter(file => {
        const fileData = typeof file === 'object' ? file : { name: file };
        return fileData.name.toLowerCase().endsWith('.cbz') || fileData.name.toLowerCase().endsWith('.zip') || fileData.name.toLowerCase().endsWith('.cbr');
      });

      if (comicFiles.length === 0) {
        CLU.showToast('No Comic Files', 'No comic files (.cbz/.cbr) found in the directory.', 'warning');
        return;
      }

      // Generate preview of renamed files
      seriesFileList = comicFiles.map(file => {
        const originalName = file.name;
        const newName = generateSeriesRename(originalName, newSeriesName);

        return {
          oldPath: `${currentSeriesRenameDirectory}/${originalName}`,
          originalName: originalName,
          newName: newName
        };
      });

      // Display preview
      displaySeriesRenamePreview(seriesFileList);

      // Show preview and enable execute button
      document.getElementById('renameFilesPreview').style.display = 'block';
      document.getElementById('executeRenameFilesBtn').style.display = 'inline-block';
    })
    .catch(error => {
      console.error('Error fetching directory listing:', error);
      CLU.showToast('Fetch Error', 'Error fetching file list: ' + error.message, 'error');
    });
}

function generateSeriesRename(originalName, newSeriesName) {
  // Extract issue number and year patterns from the filename
  // Common patterns: "Series Name 001 (1985).cbz", "Series Name #1 (1985).cbz", etc.

  // Try to extract issue and year information
  const patterns = [
    // "Series Name 001 (1985).cbz" or "Series Name #001 (1985).cbz"
    /^.*?(\s+#?\d{1,4})\s*\((\d{4})\)(\.\w+)$/,
    // "Series Name 001.cbz" (no year)
    /^.*?(\s+#?\d{1,4})(\.\w+)$/,
    // "Series Name (1985).cbz" (no issue)
    /^.*?\s*\((\d{4})\)(\.\w+)$/,
    // Just extension (fallback)
    /^.*?(\.\w+)$/
  ];

  for (let pattern of patterns) {
    const match = originalName.match(pattern);
    if (match) {
      if (match.length === 4) {
        // Issue and year found
        const issue = match[1];
        const year = match[2];
        const ext = match[3];
        return `${newSeriesName}${issue} (${year})${ext}`;
      } else if (match.length === 3) {
        // Check if it's issue + ext or year + ext
        if (match[1].includes('#') || /^\s+\d/.test(match[1])) {
          // Issue number found, no year
          const issue = match[1];
          const ext = match[2];
          return `${newSeriesName}${issue}${ext}`;
        } else {
          // Year found, no issue
          const year = match[1];
          const ext = match[2];
          return `${newSeriesName} (${year})${ext}`;
        }
      } else if (match.length === 2) {
        // Just extension
        const ext = match[1];
        return `${newSeriesName}${ext}`;
      }
    }
  }

  // Fallback: just replace everything before the extension
  const ext = originalName.substring(originalName.lastIndexOf('.'));
  return `${newSeriesName}${ext}`;
}

function displaySeriesRenamePreview(fileList) {
  const previewContainer = document.getElementById('renameFilesPreviewList');
  previewContainer.innerHTML = '';

  if (fileList.length === 0) {
    previewContainer.innerHTML = '<p class="text-muted">No files to rename.</p>';
    return;
  }

  fileList.forEach(file => {
    const div = document.createElement('div');
    div.className = 'mb-2 p-2 border rounded';
    div.innerHTML = `
          <div><strong>Original:</strong> <code>${file.originalName}</code></div>
          <div><strong>New:</strong> <code class="text-success">${file.newName}</code></div>
        `;
    previewContainer.appendChild(div);
  });
}

function executeRenameFiles() {
  if (seriesFileList.length === 0) {
    CLU.showToast('No Files', 'No files to rename.', 'warning');
    return;
  }

  // Disable buttons during execution
  document.getElementById('previewRenameFilesBtn').disabled = true;
  document.getElementById('executeRenameFilesBtn').disabled = true;
  document.getElementById('executeRenameFilesBtn').textContent = 'Renaming...';

  const renames = seriesFileList.map(file => ({
    old: file.oldPath,
    new: `${currentSeriesRenameDirectory}/${file.newName}`
  }));
  const directory = currentSeriesRenameDirectory;
  const panel = currentSeriesRenamePanel;
  const count = renames.length;

  fetch('/custom-rename-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ renames })
  })
    .then(response => response.json())
    .then(data => {
      if (!data.success) {
        CLU.showToast('Rename Error', data.error || 'Unknown error', 'error');
        return;
      }
      CLU.showToast(data.queued ? 'Rename Queued' : 'Rename Started',
        data.queued ? `Renaming ${count} files will start when the current job finishes.`
                    : `Renaming ${count} files with new series name…`, 'info');
      setTimeout(() => renameFilesModal.hide(), 1500);
      waitForRenameCompletion(data.op_id, count, () => loadDownloads(directory, panel));
    })
    .catch(error => {
      console.error('Error during series rename operation:', error);
      CLU.showToast('Rename Error', 'Error during series rename operation: ' + error.message, 'error');
    })
    .finally(() => {
      // Re-enable buttons
      document.getElementById('previewRenameFilesBtn').disabled = false;
      document.getElementById('executeRenameFilesBtn').disabled = false;
      document.getElementById('executeRenameFilesBtn').textContent = 'Execute Rename';
    });
}

// Enter key support comes from data-enter-confirm on #renameFilesModal (clu-utils.js)

// Search functionality
let searchModal;
let currentSearchController = null; // AbortController for current search

function openSearchModal() {
  searchModal = new bootstrap.Modal(document.getElementById('searchModal'));
  searchModal.show();

  // Clear previous search and focus on search input
  document.getElementById('searchQuery').value = '';
  document.getElementById('searchResults').style.display = 'none';
  document.getElementById('currentSearchTerm').textContent = '';

  // Cancel any ongoing search when modal opens
  cancelCurrentSearch();

  // Clear any pending search timeout
  if (searchTimeout) {
    clearTimeout(searchTimeout);
    searchTimeout = null;
  }

  // Focus on search input
  setTimeout(() => {
    document.getElementById('searchQuery').focus();
  }, 500);
}

function cancelCurrentSearch() {
  if (currentSearchController) {
    currentSearchController.abort();
    currentSearchController = null;
    console.log('Search cancelled');
  }
}

function performSearch() {
  const query = document.getElementById('searchQuery').value.trim();

  if (!query) {
    CLU.toast('Please enter a search term.', 'warning');
    return;
  }

  if (query.length < 2) {
    CLU.toast('Search term must be at least 2 characters.', 'warning');
    return;
  }

  // Cancel any ongoing search before starting a new one
  cancelCurrentSearch();

  // Create new AbortController for this search
  currentSearchController = new AbortController();

  // Show loading and update search term immediately
  document.getElementById('searchLoading').style.display = 'block';
  document.getElementById('searchResults').style.display = 'block';
  document.getElementById('currentSearchTerm').textContent = query;

  // Perform search with abort signal
  fetch(`/search-files?query=${encodeURIComponent(query)}`, {
    signal: currentSearchController.signal
  })
    .then(response => {
      // Check if the request was aborted
      if (response.ok) {
        return response.json();
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    })
    .then(data => {
      // Only process results if this is still the current search
      if (currentSearchController) {
        document.getElementById('searchLoading').style.display = 'none';

        if (data.error) {
          throw new Error(data.error);
        }

        // Check for timeout message
        if (data.timeout) {
          CLU.toast(`Search timeout: ${data.message}`, 'error');
        }

        displaySearchResults(data.results, query);
      }
    })
    .catch(error => {
      // Only show error if it's not an abort error
      if (error.name !== 'AbortError') {
        document.getElementById('searchLoading').style.display = 'none';
        console.error('Search error:', error);
        CLU.toast('Search error: ' + error.message, 'error');
      }
    });
}

function displaySearchResults(results, query) {
  const resultsContainer = document.getElementById('searchResultsList');
  const resultsDiv = document.getElementById('searchResults');

  resultsContainer.innerHTML = '';

  // Always show the results container with the search term
  resultsDiv.style.display = 'block';
  CLU.setCount(document.getElementById('searchResultsCount'),
    { total: results.length, noun: 'results', one: 'result' });

  if (results.length === 0) {
    // The search box is on the same modal, so the button just empties it.
    resultsContainer.appendChild(CLU.noMatches({
      noun: 'files or folders', query: query, compact: true,
      onClear: () => {
        const box = document.getElementById('searchQuery');
        if (box) { box.value = ''; box.focus(); }
        resultsDiv.style.display = 'none';
      },
    }));
  } else {
    results.forEach(item => {
      const resultItem = document.createElement('div');
      resultItem.className = 'list-group-item list-group-item-action d-flex align-items-center justify-content-between';

      const icon = item.type === 'directory' ? 'bi-folder' : 'bi-file-earmark-zip';
      const size = item.type === 'file' ? formatSize(item.size) : '';

      resultItem.innerHTML = `
            <div class="d-flex align-items-center">
              <i class="bi ${icon} me-2"></i>
              <span>${item.name}</span>
              ${size ? `<span class="text-info-emphasis small ms-2">(${size})</span>` : ''}
            </div>
            <div class="text-muted small">
              ${item.parent}
            </div>
          `;

      // Add click handler to navigate to the item
      resultItem.addEventListener('click', () => {
        navigateToSearchResult(item);
      });

      resultsContainer.appendChild(resultItem);
    });
  }

  // Reset scroll to the top whenever results are (re)rendered, so a new search
  // or changed term doesn't leave the user scrolled into the previous results.
  resultsContainer.scrollTop = 0;
}

function navigateToSearchResult(item) {
  // Close search modal
  searchModal.hide();

  // Navigate to the parent directory in the destination panel
  loadDirectories(item.parent, 'destination');

  // Highlight the item (optional - could add a visual indicator)
  setTimeout(() => {
    // You could add highlighting logic here if needed
    console.log('Navigated to:', item.parent, 'for item:', item.name);
  }, 500);
}

// Debounced search functionality
let searchTimeout = null;

// Add input event listener for debounced search (only if elements exist)
const searchQueryEl = document.getElementById('searchQuery');
const searchModalEl = document.getElementById('searchModal');

if (searchQueryEl) {
  searchQueryEl.addEventListener('input', function (e) {
    const query = e.target.value.trim();

    // Clear existing timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    // Cancel current search if there is one
    cancelCurrentSearch();

    // Hide loading and results for new input
    document.getElementById('searchLoading').style.display = 'none';
    document.getElementById('searchResults').style.display = 'none';

    // Only search if query is at least 2 characters
    if (query.length >= 2) {
      searchTimeout = setTimeout(() => {
        performSearch();
      }, 500); // 500ms delay
    }
  });

  // Add Enter key support for search input
  searchQueryEl.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
      // Clear the timeout and perform immediate search
      if (searchTimeout) {
        clearTimeout(searchTimeout);
        searchTimeout = null;
      }
      performSearch();
    }
  });
}

// Cancel search when modal is closed
if (searchModalEl) {
  searchModalEl.addEventListener('hidden.bs.modal', function () {
    cancelCurrentSearch();
    // Clear any pending search timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
      searchTimeout = null;
    }
    // Hide loading and results when modal is closed
    const searchLoading = document.getElementById('searchLoading');
    const searchResults = document.getElementById('searchResults');
    if (searchLoading) searchLoading.style.display = 'none';
    if (searchResults) searchResults.style.display = 'none';
  });
}





// Helper function to show toast notifications

// Function to format timestamp in a user-friendly way
function formatTimestamp(date) {
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) {
    return 'Just now';
  } else if (diffMins < 60) {
    return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
  } else if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  } else {
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
}

// Function to search GCD for metadata and add to CBZ
function searchGCDMetadata(filePath, fileName) {
  console.log('GCD Search Called with:', { filePath, fileName });

  // Validate inputs
  if (!filePath || !fileName) {
    console.error('Invalid parameters:', { filePath, fileName });
    CLU.showToast('GCD Search Error', 'Missing file path or name', 'error');
    return;
  }

  if (!fileName.toLowerCase().match(/\.(cbz|cbr)$/)) {
    console.error('Invalid file type:', fileName);
    CLU.showToast('GCD Search Error', 'File must be CBZ or CBR format', 'error');
    return;
  }

  // Parse series name and issue from filename
  const nameWithoutExt = fileName.replace(/\.(cbz|cbr)$/i, '');

  // Auto-search without confirmation

  // Show a simple loading indicator
  const loadingToast = document.createElement('div');
  loadingToast.className = 'toast show position-fixed top-0 end-0 m-3';
  loadingToast.style.zIndex = '1200';
  loadingToast.innerHTML = `
        <div class="toast-header bg-primary text-white">
          <strong class="me-auto">GCD Search</strong>
          <small>Searching...</small>
        </div>
        <div class="toast-body">
          <div class="d-flex align-items-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
            Searching GCD database for "${nameWithoutExt}"...
          </div>
        </div>
      `;
  document.body.appendChild(loadingToast);

  // Make request to backend
  const requestData = {
    file_path: filePath,
    file_name: fileName
  };
  console.log('GCD Search Request Data:', requestData);

  fetch('/search-gcd-metadata', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(requestData)
  })
    .then(response => {
      console.log('GCD Search Response Status:', response.status);
      if (!response.ok) {
        // For HTTP errors, get the error data and handle appropriately
        return response.json().then(errorData => {
          // Handle 404 as expected "not found" rather than error
          if (response.status === 404) {
            return { success: false, notFound: true, error: errorData.error || 'Issue not found in database' };
          }
          // For other HTTP errors, throw as before
          throw new Error(`HTTP ${response.status}: ${errorData.error || response.statusText}`);
        }).catch((jsonError) => {
          // If JSON parsing fails, throw the original HTTP error
          if (response.status === 404) {
            return { success: false, notFound: true, error: 'Issue not found in database' };
          }
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        });
      }
      return response.json();
    })
    .then(data => {
      console.log('GCD Search Response Data:', data);
      document.body.removeChild(loadingToast);

      if (data.success) {
        CLU.showToast('GCD Search',
          `Added metadata to "${fileName}". Series: ${data.metadata?.series || 'Unknown'}, ` +
          `issue ${data.metadata?.issue || 'Unknown'}; ${data.matches_found || 0} potential matches.`,
          'success', 6000);
      } else if (data.requires_selection) {
        // Show series selection modal
        showGCDSeriesSelectionModal(data, filePath, fileName);
      } else if (data.notFound) {
        // Not found is a warning, not an error.
        CLU.showToast('GCD Search', data.error || 'Issue not found in GCD database', 'warning');
      } else {
        CLU.showToast('GCD Search',
          'Failed to add metadata: ' + (data.error || data.message || 'Server returned no error message'), 'error');
      }
    })
    .catch(error => {
      console.error('GCD Search Network Error:', error);
      document.body.removeChild(loadingToast);

      CLU.showToast('Network Error', `Network error: ${error.message}`, 'error', 8000);
    });
}


// Function to search GCD for all comics in a directory
function searchGCDMetadataForDirectory(directoryPath, directoryName) {
  // Auto-search without confirmation

  // Show loading indicator
  const loadingToast = document.createElement('div');
  loadingToast.className = 'toast show position-fixed top-0 end-0 m-3';
  loadingToast.style.zIndex = '1200';
  loadingToast.innerHTML = `
        <div class="toast-header bg-primary text-white">
          <strong class="me-auto">GCD Directory Search</strong>
          <small>Scanning...</small>
        </div>
        <div class="toast-body">
          <div class="d-flex align-items-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
            Scanning directory for comic files...
          </div>
        </div>
      `;
  document.body.appendChild(loadingToast);

  // Get list of files in the directory
  fetch(`/list-directories?path=${encodeURIComponent(directoryPath)}`)
    .then(response => response.json())
    .then(data => {
      document.body.removeChild(loadingToast);

      if (data.error) {
        throw new Error(data.error);
      }

      // Filter for CBZ/CBR files
      const comicFiles = (data.files || []).filter(file => {
        const fileData = typeof file === 'object' ? file : { name: file };
        return fileData.name.toLowerCase().endsWith('.cbz') || fileData.name.toLowerCase().endsWith('.zip') || fileData.name.toLowerCase().endsWith('.cbr');
      });

      // Check for nested volume directories (e.g., v2015, v2016)
      const volumeDirectories = (data.directories || []).filter(dir => {
        const dirData = typeof dir === 'object' ? dir : { name: dir };
        return /^v\d{4}$/i.test(dirData.name); // Match v2015, v2016, etc.
      });

      // Approach 1: If current directory has no comics but has volume subdirectories, process all volumes
      if (comicFiles.length === 0 && volumeDirectories.length > 0) {
        CLU.showToast('Processing Volume Directories', `Found ${volumeDirectories.length} volume directories. Processing each separately...`, 'info');
        processNestedVolumeDirectories(directoryPath, directoryName, volumeDirectories);
        return;
      }

      // Approach 2: If current directory has comics, process normally
      if (comicFiles.length === 0) {
        CLU.showToast('No Comics Found', `No comic files (.cbz/.cbr) found in "${directoryName}"`, 'warning');
        return;
      }

      // Check if this is a volume directory (e.g., v2015) - Approach 2
      const volumeMatch = directoryName.match(/^v(\d{4})$/i);

      if (volumeMatch) {
        // This is a volume directory, get parent series name
        const pathParts = directoryPath.split('/');
        const parentDirectoryName = pathParts[pathParts.length - 2] || 'Unknown';
        const year = volumeMatch[1];

        CLU.showToast('Volume Directory Detected', `Processing volume ${directoryName} with parent series "${parentDirectoryName}"`, 'info');

        // Use parent directory name as series and pass volume info
        searchGCDForVolumeDirectory(directoryPath, directoryName, parentDirectoryName, year, comicFiles);
      } else {
        // Standard directory processing
        let seriesName = directoryName;

        // Clean up common directory naming patterns
        seriesName = seriesName.replace(/\s*\(\d{4}\).*$/, ''); // Remove (1994) and everything after
        seriesName = seriesName.replace(/\s*v\d+.*$/, ''); // Remove v1, v2 etc
        seriesName = seriesName.replace(/\s*-\s*complete.*$/i, ''); // Remove "- Complete" etc
        seriesName = seriesName.replace(/\s*\.INFO.*$/i, ''); // Remove .INFO

        // Start the GCD search for the directory
        searchGCDForDirectorySeries(directoryPath, directoryName, seriesName, comicFiles);
      }
    })
    .catch(error => {
      document.body.removeChild(loadingToast);
      CLU.showToast('Directory Scan Error', `Error scanning directory: ${error.message}`, 'error');
    });
}

// fetchAllMetadata – delegated to clu-metadata.js (CLU.fetchDirectoryMetadata)

// Function to process nested volume directories (e.g., Lady Killer/v2015, Lady Killer/v2016)
async function processNestedVolumeDirectories(parentPath, parentName, volumeDirectories) {
  // Extract series name from parent directory
  const seriesName = parentName;

  // Create progress modal for processing multiple volumes
  const progressModal = document.createElement('div');
  progressModal.className = 'modal fade';
  progressModal.setAttribute('data-bs-backdrop', 'static');
  progressModal.innerHTML = `
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">Processing Volume Directories: ${seriesName}</h5>
            </div>
            <div class="modal-body">
              <div class="mb-3">
                <div class="d-flex justify-content-between">
                  <span>Progress:</span>
                  <span id="volumeProgressText">0 / ${volumeDirectories.length}</span>
                </div>
                <div class="progress">
                  <div id="volumeProgressBar" class="progress-bar progress-bar-striped progress-bar-animated"
                       style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
              </div>
              <div id="volumeCurrentDir" class="text-muted small">Preparing...</div>
              <div id="volumeResults" class="mt-3 small" style="max-height: 200px; overflow-y: auto;">
                <!-- Results will be added here -->
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" id="volumeCloseBtn" class="btn btn-secondary" disabled>Close</button>
              <button type="button" id="volumeCancelBtn" class="btn btn-danger">Cancel</button>
            </div>
          </div>
        </div>
      `;
  document.body.appendChild(progressModal);

  const volumeModal = new bootstrap.Modal(progressModal);
  volumeModal.show();

  let processedCount = 0;
  let successCount = 0;
  let errorCount = 0;
  let cancelled = false;

  document.getElementById('volumeCancelBtn').onclick = () => {
    cancelled = true;
    document.getElementById('volumeCancelBtn').disabled = true;
    document.getElementById('volumeCurrentDir').textContent = 'Cancelling...';
  };

  document.getElementById('volumeCloseBtn').onclick = () => {
    volumeModal.hide();
    document.body.removeChild(progressModal);
  };

  // Process each volume directory
  for (let i = 0; i < volumeDirectories.length && !cancelled; i++) {
    const volumeDir = volumeDirectories[i];
    const volumeName = volumeDir.name || volumeDir;
    const volumePath = parentPath + '/' + volumeName;

    // Extract year from volume directory name (e.g., v2015 -> 2015)
    const yearMatch = volumeName.match(/^v(\d{4})$/i);
    const year = yearMatch ? yearMatch[1] : null;

    document.getElementById('volumeCurrentDir').textContent = `Processing: ${volumeName}`;

    try {
      // Get files in this volume directory
      const response = await fetch(`/list-directories?path=${encodeURIComponent(volumePath)}`);
      const data = await response.json();

      if (data.error) {
        throw new Error(data.error);
      }

      const comicFiles = (data.files || []).filter(file => {
        const fileData = typeof file === 'object' ? file : { name: file };
        return fileData.name.toLowerCase().endsWith('.cbz') || fileData.name.toLowerCase().endsWith('.zip') || fileData.name.toLowerCase().endsWith('.cbr');
      });

      if (comicFiles.length === 0) {
        throw new Error(`No comic files found in ${volumeName}`);
      }

      // Search for this specific year's series
      const searchSeriesName = year ? `${seriesName} (${year})` : seriesName;

      // Process this volume directory
      await processVolumeDirectory(volumePath, volumeName, searchSeriesName, comicFiles, year);

      successCount++;
      const resultsDiv = document.getElementById('volumeResults');
      const resultItem = document.createElement('div');
      resultItem.className = 'text-success';
      resultItem.innerHTML = `✓ ${volumeName} - ${comicFiles.length} files processed`;
      resultsDiv.appendChild(resultItem);

    } catch (error) {
      errorCount++;
      const resultsDiv = document.getElementById('volumeResults');
      const resultItem = document.createElement('div');
      resultItem.className = 'text-danger';
      resultItem.innerHTML = `✗ ${volumeName} - ${error.message}`;
      resultsDiv.appendChild(resultItem);
    }

    processedCount++;

    // Update progress
    document.getElementById('volumeProgressText').textContent = `${processedCount} / ${volumeDirectories.length}`;
    const progressPercent = Math.floor((processedCount / volumeDirectories.length) * 100);
    document.getElementById('volumeProgressBar').style.width = progressPercent + '%';
    document.getElementById('volumeProgressBar').setAttribute('aria-valuenow', progressPercent);

    // Scroll results to bottom
    const resultsDiv = document.getElementById('volumeResults');
    resultsDiv.scrollTop = resultsDiv.scrollHeight;
  }

  // Finished processing
  document.getElementById('volumeCloseBtn').disabled = false;
  document.getElementById('volumeCancelBtn').style.display = 'none';
  document.getElementById('volumeCurrentDir').textContent = cancelled
    ? `Cancelled after ${processedCount} volumes`
    : `Complete! Processed ${processedCount} volumes (${successCount} success, ${errorCount} errors)`;

  // Auto-close modal after 2 seconds if not cancelled
  if (!cancelled) {
    setTimeout(() => {
      volumeModal.hide();
    }, 2000);
  }
}

// Function to process a single volume directory
async function processVolumeDirectory(volumePath, volumeName, seriesName, comicFiles, year) {
  return new Promise((resolve, reject) => {
    // Use the first file for the search
    const firstFile = comicFiles[0];
    const firstFileName = firstFile.name || firstFile;
    const firstFilePath = volumePath + '/' + firstFileName;

    fetch('/search-gcd-metadata', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: firstFilePath,
        file_name: firstFileName,
        is_directory_search: true,
        directory_path: volumePath,
        directory_name: volumeName,
        total_files: comicFiles.length,
        parent_series_name: seriesName,
        volume_year: year
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          if (data.series_id) {
            // Auto-process with found series
            processBulkGCDMetadata(volumePath, volumeName, data.series_id, comicFiles);
            resolve();
          } else {
            reject(new Error('No series ID returned'));
          }
        } else {
          reject(new Error(data.error || 'Search failed'));
        }
      })
      .catch(error => {
        reject(error);
      });
  });
}

// Function to search GCD for a volume directory using parent series name
function searchGCDForVolumeDirectory(directoryPath, directoryName, parentSeriesName, year, comicFiles) {
  // Use first comic file for the search, but flag it as volume directory search
  const firstFile = comicFiles[0];
  const firstFileName = firstFile.name || firstFile;
  const firstFilePath = directoryPath + '/' + firstFileName;

  fetch('/search-gcd-metadata', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      file_path: firstFilePath,
      file_name: firstFileName,
      is_directory_search: true,
      directory_path: directoryPath,
      directory_name: directoryName,
      total_files: comicFiles.length,
      parent_series_name: parentSeriesName,
      volume_year: year
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // For volume directory search with exact match, proceed with bulk processing
        if (data.series_id) {
          CLU.showToast('Exact Match Found', `Found exact match for "${parentSeriesName} (${year})". Processing all files in volume...`, 'success');
          // Start bulk processing immediately with the found series
          processBulkGCDMetadata(directoryPath, directoryName, data.series_id, comicFiles);
        } else {
          CLU.showToast('Direct Match Found', `Found exact match for "${parentSeriesName} (${year})". Consider using individual file search instead.`, 'info');
        }
      } else if (data.requires_selection) {
        // Show series selection modal for volume processing
        showGCDDirectorySeriesSelectionModal(data, directoryPath, directoryName, comicFiles);
      } else {
        // Show error or no results
        CLU.showToast('No Series Found', data.error || `No series found matching "${parentSeriesName} (${year})" in GCD database`, 'error');
      }
    })
    .catch(error => {
      CLU.showToast('Search Error', `Error searching GCD database: ${error.message}`, 'error');
    });
}

// Function to search GCD for directory series and show selection modal
function searchGCDForDirectorySeries(directoryPath, directoryName, seriesName, comicFiles) {
  // Use first comic file for the search, but flag it as directory search
  const firstFile = comicFiles[0];
  const firstFileName = firstFile.name || firstFile;
  const firstFilePath = directoryPath + '/' + firstFileName;

  fetch('/search-gcd-metadata', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      file_path: firstFilePath,
      file_name: firstFileName,
      is_directory_search: true,
      directory_path: directoryPath,
      directory_name: directoryName,
      total_files: comicFiles.length
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // For directory search with exact match, proceed with bulk processing
        if (data.series_id) {
          CLU.showToast('Exact Match Found', `Found exact match for "${seriesName}". Processing all files in directory...`, 'success');
          // Start bulk processing immediately with the found series
          processBulkGCDMetadata(directoryPath, directoryName, data.series_id, comicFiles);
        } else {
          CLU.showToast('Direct Match Found', `Found exact match for "${seriesName}". Consider using individual file search instead.`, 'info');
        }
      } else if (data.requires_selection) {
        // Show series selection modal for directory processing
        // Use the directory information from the server response if available
        const actualDirectoryPath = data.directory_path || directoryPath;
        const actualDirectoryName = data.directory_name || directoryName;
        showGCDDirectorySeriesSelectionModal(data, actualDirectoryPath, actualDirectoryName, comicFiles);
      } else {
        // Show error or no results
        CLU.showToast('No Series Found', data.error || `No series found matching "${seriesName}" in GCD database`, 'error');
      }
    })
    .catch(error => {
      CLU.showToast('Search Error', `Error searching GCD database: ${error.message}`, 'error');
    });
}

// Function to render series list for directory processing
function renderDirectorySeriesList(seriesData, directoryPath, directoryName, comicFiles) {
  const seriesList = document.getElementById('gcdSeriesList');
  seriesList.innerHTML = '';

  seriesData.forEach(series => {
    const seriesItem = document.createElement('div');
    seriesItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-start';
    seriesItem.style.cursor = 'pointer';

    const yearRange = series.year_began
      ? (series.year_ended ? `${series.year_began}-${series.year_ended}` : `${series.year_began}-ongoing`)
      : 'Unknown';

    seriesItem.innerHTML = `
          <div class="ms-2 me-auto">
            <div class="fw-bold">${series.name}</div>
            <small class="text-muted">Publisher: ${series.publisher_name || 'Unknown'}<br>Issue Count: ${series.issue_count || 'Unknown'}</small>
          </div>
          <span class="badge bg-primary rounded-pill">${yearRange}</span>
        `;

    seriesItem.addEventListener('click', () => {
      // Highlight selected item
      seriesList.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
      });
      seriesItem.classList.add('active');

      // Call the bulk processing function for directory
      processBulkGCDMetadata(directoryPath, directoryName, series.id, comicFiles);
    });

    seriesList.appendChild(seriesItem);
  });
}

// Function to show GCD series selection modal for directory processing
function showGCDDirectorySeriesSelectionModal(data, directoryPath, directoryName, comicFiles) {
  // Populate the parsed filename information (using directory name)
  document.getElementById('gcdParsedSeries').textContent = data.parsed_filename.series_name;
  document.getElementById('gcdParsedIssue').textContent = `Directory (${comicFiles.length} files)`;
  document.getElementById('gcdParsedYear').textContent = data.parsed_filename.year || 'Unknown';

  // Store the data globally for sorting
  currentSeriesData = data.possible_matches;
  // Store directory-specific data in global variables for custom rendering
  currentFilePath = directoryPath;
  currentFileName = directoryName;
  currentIssueNumber = comicFiles;

  // Reset sort buttons
  markGCDSort('');

  // Render the series list with initial order (directory mode)
  renderDirectorySeriesList(currentSeriesData, directoryPath, directoryName, comicFiles);

  // Update modal title for directory processing
  document.getElementById('gcdSeriesModalLabel').textContent = `Select Series for Directory: ${directoryName}`;

  // Show the modal
  const modal = new bootstrap.Modal(document.getElementById('gcdSeriesModal'));
  modal.show();
}

// Function to process bulk GCD metadata for a directory
function processBulkGCDMetadata(directoryPath, directoryName, seriesId, comicFiles) {
  const modal = bootstrap.Modal.getInstance(document.getElementById('gcdSeriesModal'));
  if (modal) {
    modal.hide();
  }

  // Create progress modal
  const progressModal = document.createElement('div');
  progressModal.className = 'modal fade';
  progressModal.setAttribute('data-bs-backdrop', 'static');
  progressModal.innerHTML = `
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">Processing Directory: ${directoryName}</h5>
            </div>
            <div class="modal-body">
              <div class="mb-3">
                <div class="d-flex justify-content-between">
                  <span>Progress:</span>
                  <span id="bulkProgressText">0 / ${comicFiles.length}</span>
                </div>
                <div class="progress">
                  <div id="bulkProgressBar" class="progress-bar progress-bar-striped progress-bar-animated"
                       style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
              </div>
              <div id="bulkCurrentFile" class="text-muted small">Preparing...</div>
              <div id="bulkResults" class="mt-3 small" style="max-height: 200px; overflow-y: auto;">
                <!-- Results will be added here -->
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" id="bulkCloseBtn" class="btn btn-secondary" disabled>Close</button>
              <button type="button" id="bulkCancelBtn" class="btn btn-danger">Cancel</button>
            </div>
          </div>
        </div>
      `;
  document.body.appendChild(progressModal);

  const bulkModal = new bootstrap.Modal(progressModal);
  bulkModal.show();

  // Start processing files
  let processedCount = 0;
  let successCount = 0;
  let errorCount = 0;
  let cancelled = false;
  let failedFiles = []; // Track files that failed to get metadata

  document.getElementById('bulkCancelBtn').onclick = () => {
    cancelled = true;
    document.getElementById('bulkCancelBtn').disabled = true;
    document.getElementById('bulkCurrentFile').textContent = 'Cancelling...';
  };

  // Add close button functionality
  document.getElementById('bulkCloseBtn').onclick = () => {
    bulkModal.hide();
  };

  async function processNextFile(index) {
    if (cancelled || index >= comicFiles.length) {
      // Initial processing complete - check for failed files
      if (!cancelled && failedFiles.length > 0) {
        document.getElementById('bulkCurrentFile').textContent = `Searching for unmatched files using filenames...`;
        // Start secondary search for failed files
        await processFailedFiles();
      } else {
        // Processing complete or cancelled
        document.getElementById('bulkCloseBtn').disabled = false;
        document.getElementById('bulkCancelBtn').style.display = 'none';
        document.getElementById('bulkCurrentFile').textContent = cancelled
          ? `Cancelled after ${processedCount} files`
          : `Complete! Processed ${processedCount} files (${successCount} success, ${errorCount} errors)`;

        // Auto-close modal after 2 seconds if not cancelled
        if (!cancelled) {
          setTimeout(() => {
            bulkModal.hide();
          }, 2000);
        }
      }
      return;
    }

    const file = comicFiles[index];
    const fileName = file.name || file;
    const filePath = directoryPath + '/' + fileName;

    // Update progress - show current processing
    document.getElementById('bulkCurrentFile').textContent = `Processing: ${fileName}`;
    document.getElementById('bulkProgressText').textContent = `${processedCount} / ${comicFiles.length}`;

    const progressPercent = Math.floor((processedCount / comicFiles.length) * 100);
    document.getElementById('bulkProgressBar').style.width = progressPercent + '%';
    document.getElementById('bulkProgressBar').setAttribute('aria-valuenow', progressPercent);

    try {
      // Parse issue number from filename - look for common patterns
      let issueNumber = null;

      // Try multiple patterns to extract issue number
      const patterns = [
        /(?:^|\s)(\d{1,4})(?:\s*\(|\s*$|\s*\.)/,     // Standard: "Series 123 (year)" or "Series 123.cbz"
        /(?:^|\s)#(\d{1,4})(?:\s|$)/,                 // Hash prefix: "Series #123"
        /(?:issue\s*)(\d{1,4})/i,                     // Issue prefix: "Series Issue 123"
        /(?:no\.?\s*)(\d{1,4})/i,                     // No. prefix: "Series No. 123"
        /(?:vol\.\s*\d+\s+)(\d{1,4})/i                // Volume and issue: "Series Vol. 1 123"
      ];

      for (const pattern of patterns) {
        const match = fileName.match(pattern);
        if (match) {
          issueNumber = parseInt(match[1]);
          break;
        }
      }

      // If no issue number found, skip this file with a clear error
      if (issueNumber === null) {
        throw new Error(`Could not parse issue number from filename: ${fileName}`);
      }

      // First validate that this issue number exists in the series
      const validationResponse = await fetch('/validate-gcd-issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          series_id: seriesId,
          issue_number: issueNumber
        })
      });

      const validationResult = await validationResponse.json();
      if (!validationResult.success) {
        throw new Error(`Issue #${issueNumber} not found in series (parsed from filename)`);
      }

      const response = await fetch('/search-gcd-metadata-with-selection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: filePath,
          file_name: fileName,
          series_id: seriesId,
          issue_number: issueNumber
        })
      });

      const result = await response.json();

      const resultsDiv = document.getElementById('bulkResults');
      const resultItem = document.createElement('div');

      if (result.success) {
        if (result.skipped) {
          // File was skipped because it already has metadata
          successCount++;
          resultItem.className = 'text-info';
          resultItem.textContent = `✓ ${fileName} - Skipped XML Present`;
        } else {
          // File was successfully processed
          successCount++;
          resultItem.className = 'text-success';
          resultItem.textContent = `✓ ${fileName} - Issue #${result.metadata.issue}`;
        }
      } else {
        errorCount++;
        resultItem.className = 'text-danger';
        resultItem.textContent = `✗ ${fileName} - ${result.error}`;
        // Track failed file for secondary search
        failedFiles.push({ fileName, filePath, error: result.error });
      }

      resultsDiv.appendChild(resultItem);
      resultsDiv.scrollTop = resultsDiv.scrollHeight;

    } catch (error) {
      errorCount++;
      const resultsDiv = document.getElementById('bulkResults');
      const resultItem = document.createElement('div');
      resultItem.className = 'text-danger';
      // Show actual error message instead of generic "Network error"
      const errorMsg = error.message || 'Network error';
      resultItem.textContent = `✗ ${fileName} - ${errorMsg}`;
      resultsDiv.appendChild(resultItem);
      // Track failed file for secondary search
      failedFiles.push({ fileName, filePath, error: errorMsg });
      // Log error to console for debugging
      console.error(`Error processing ${fileName}:`, error);
    }

    processedCount++;

    // Update progress after completing the file
    document.getElementById('bulkProgressText').textContent = `${processedCount} / ${comicFiles.length}`;
    const newProgressPercent = Math.floor((processedCount / comicFiles.length) * 100);
    document.getElementById('bulkProgressBar').style.width = newProgressPercent + '%';
    document.getElementById('bulkProgressBar').setAttribute('aria-valuenow', newProgressPercent);

    // Process next file after a short delay
    setTimeout(() => processNextFile(index + 1), 100);
  }

  // Function to process failed files using filename-based search
  async function processFailedFiles() {
    let secondarySuccessCount = 0;
    let secondaryProcessedCount = 0;
    const totalFailed = failedFiles.length;

    document.getElementById('bulkCurrentFile').innerHTML = `
          <div class="mb-2">Secondary search phase: Using filename-based search for unmatched files</div>
          <div class="text-muted small">Processing ${totalFailed} unmatched files...</div>
        `;

    // Add a separator in results
    const resultsDiv = document.getElementById('bulkResults');
    const separator = document.createElement('div');
    separator.className = 'border-top mt-2 pt-2 mb-2 text-muted small';
    separator.innerHTML = '<strong>Secondary Search (by filename):</strong>';
    resultsDiv.appendChild(separator);

    for (let i = 0; i < failedFiles.length && !cancelled; i++) {
      const failedFile = failedFiles[i];

      document.getElementById('bulkCurrentFile').innerHTML = `
            <div class="mb-2">Secondary search phase: Using filename-based search</div>
            <div class="text-muted small">Processing: ${CLU.escapeHtml(failedFile.fileName)} (${i + 1}/${totalFailed})</div>
          `;

      try {
        // Search using just the filename (not tied to the original series)
        const response = await fetch('/search-gcd-metadata', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_path: failedFile.filePath,
            file_name: failedFile.fileName
          })
        });

        const result = await response.json();
        const resultItem = document.createElement('div');

        if (result.success && result.requires_selection) {
          // Found potential matches - show as warning and let user handle manually
          resultItem.className = 'text-warning';
          resultItem.textContent = `⚠ ${failedFile.fileName} - Found ${result.possible_matches?.length || 0} potential matches, requires manual selection`;
        } else if (result.success && result.series_id) {
          // Direct match found
          secondarySuccessCount++;
          resultItem.className = 'text-success';
          resultItem.textContent = `✓ ${failedFile.fileName} - Found direct match: ${result.parsed_filename?.series_name || 'Unknown Series'}`;
        } else {
          // Still no match
          resultItem.className = 'text-danger';
          resultItem.textContent = `✗ ${failedFile.fileName} - No match found in secondary search`;
        }

        resultsDiv.appendChild(resultItem);
        resultsDiv.scrollTop = resultsDiv.scrollHeight;

      } catch (error) {
        const resultItem = document.createElement('div');
        resultItem.className = 'text-danger';
        resultItem.textContent = `✗ ${failedFile.fileName} - Secondary search network error`;
        resultsDiv.appendChild(resultItem);
      }

      secondaryProcessedCount++;

      // Small delay to prevent overwhelming the server
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    // Final completion
    document.getElementById('bulkCloseBtn').disabled = false;
    document.getElementById('bulkCancelBtn').style.display = 'none';

    const totalSuccessCount = successCount + secondarySuccessCount;
    const totalErrorCount = errorCount - secondarySuccessCount; // Adjust error count for secondary successes

    document.getElementById('bulkCurrentFile').innerHTML = `
          <div><strong>Complete!</strong> Processed ${processedCount} files</div>
          <div class="text-muted small">
            Primary: ${successCount} success, ${errorCount} failed<br>
            Secondary: ${secondarySuccessCount} additional matches found<br>
            <strong>Total: ${totalSuccessCount} success, ${Math.max(0, totalErrorCount)} still unmatched</strong>
          </div>
        `;

    // Auto-close modal after 2 seconds
    setTimeout(() => {
      bulkModal.hide();
    }, 2000);
  }

  // Start processing
  processNextFile(0);

  // Clean up modal when closed
  progressModal.addEventListener('hidden.bs.modal', () => {
    document.body.removeChild(progressModal);
  });
}

// Function to show GCD series selection modal
function showGCDSeriesSelectionModal(data, filePath, fileName, skipProviders) {
  // Populate the parsed filename information
  document.getElementById('gcdParsedSeries').textContent = data.parsed_filename.series_name;
  document.getElementById('gcdParsedIssue').textContent = data.parsed_filename.issue_number;
  document.getElementById('gcdParsedYear').textContent = data.parsed_filename.year || 'Unknown';

  // Store the data globally for sorting
  currentSeriesData = data.possible_matches;
  currentFilePath = filePath;
  currentFileName = fileName;
  currentIssueNumber = data.parsed_filename.issue_number;

  // Reset sort buttons
  markGCDSort('');

  // Render the series list with initial order
  renderSeriesList(currentSeriesData);

  // Wire the "Skip to next provider" button (shared logic from clu-metadata.js)
  if (window.CLU && typeof CLU.wireSkipButton === 'function') {
    CLU.wireSkipButton('gcdSkipProviderBtn', data, filePath, fileName, skipProviders || []);
  }

  // Show the modal
  const modal = new bootstrap.Modal(document.getElementById('gcdSeriesModal'));
  modal.show();
}

// Function to handle series selection
function selectGCDSeries(filePath, fileName, seriesId, issueNumber) {
  // Show loading indicator
  const modal = bootstrap.Modal.getInstance(document.getElementById('gcdSeriesModal'));

  // Create loading toast
  const loadingToast = document.createElement('div');
  loadingToast.className = 'toast show position-fixed top-0 end-0 m-3';
  loadingToast.style.zIndex = '1200';
  loadingToast.innerHTML = `
        <div class="toast-header bg-primary text-white">
          <strong class="me-auto">GCD Search</strong>
          <small>Processing...</small>
        </div>
        <div class="toast-body">
          <div class="d-flex align-items-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
            Adding metadata from selected series...
          </div>
        </div>
      `;
  document.body.appendChild(loadingToast);

  // Close the modal (if it exists)
  if (modal) {
    modal.hide();
  }

  // Call the backend endpoint
  fetch('/search-gcd-metadata-with-selection', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      file_path: filePath,
      file_name: fileName,
      series_id: seriesId,
      issue_number: issueNumber
    })
  })
    .then(response => response.json())
    .then(data => {
      document.body.removeChild(loadingToast);

      if (data.success) {
        // Show success message
        CLU.showToast('GCD Search Success', `Added metadata to "${fileName}". Series: ${data.metadata?.series || 'Unknown'}, issue ${data.metadata?.issue || 'Unknown'}, title ${data.metadata?.title || 'Unknown'}, publisher ${data.metadata?.publisher || 'Unknown'}`, 'success', 5000);
      } else {
        // Show error message
        CLU.showToast('GCD Search Error', `Failed to add metadata: ${data.error || data.message || 'Server returned no error message'}`, 'error', 8000);
      }
    })
    .catch(error => {
      console.error('GCD Search Network Error:', error);
      document.body.removeChild(loadingToast);

      CLU.showToast('Network Error', `Network error: ${error.message}`, 'error', 8000);
    });
}


// Mark the GCD sort buttons (#sortBySeries / #sortByYear, data-value);
// '' clears both, which is how the modal opens.
function markGCDSort(sortBy) {
  document.querySelectorAll('#sortBySeries, #sortByYear').forEach(btn => {
    const on = btn.getAttribute('data-value') === sortBy;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}

// Function to sort GCD series results
function sortGCDSeries(sortBy) {
  markGCDSort(sortBy);

  // Sort the data
  let sortedData = [...currentSeriesData];

  if (sortBy === 'series') {
    sortedData.sort((a, b) => a.name.localeCompare(b.name));
  } else if (sortBy === 'year') {
    sortedData.sort((a, b) => {
      const yearA = a.year_began || 9999; // Put unknown years at the end
      const yearB = b.year_began || 9999;
      return yearA - yearB;
    });
  }

  // Re-render the series list - detect if this is directory mode or single file mode
  if (Array.isArray(currentIssueNumber)) {
    // Directory mode - currentIssueNumber contains the comicFiles array
    renderDirectorySeriesList(sortedData, currentFilePath, currentFileName, currentIssueNumber);
  } else {
    // Single file mode - currentIssueNumber is a number
    renderSeriesList(sortedData);
  }
}

// Function to render the series list
function renderSeriesList(seriesData) {
  const seriesList = document.getElementById('gcdSeriesList');
  seriesList.innerHTML = '';

  seriesData.forEach(series => {
    const seriesItem = document.createElement('div');
    seriesItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-start';
    seriesItem.style.cursor = 'pointer';

    const yearRange = series.year_began
      ? (series.year_ended ? `${series.year_began}-${series.year_ended}` : `${series.year_began}-ongoing`)
      : 'Unknown';

    seriesItem.innerHTML = `
          <div class="ms-2 me-auto">
            <div class="fw-bold">${series.name}</div>
            <small class="text-muted">Publisher: ${series.publisher_name || 'Unknown'}<br>Issue Count: ${series.issue_count || 'Unknown'}</small>
          </div>
          <div class="text-end">
            <span class="badge bg-primary rounded-pill">${yearRange}</span><br>
            <span class="badge bg-dark rounded-pill">${series.language}</span>
          </div>
        `;

    seriesItem.addEventListener('click', () => {
      // Highlight selected item
      seriesList.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
      });
      seriesItem.classList.add('active');

      // Call the backend with the selected series
      selectGCDSeries(currentFilePath, currentFileName, series.id, currentIssueNumber);
    });

    seriesList.appendChild(seriesItem);
  });
}



// A file left this pane (moved by metadata): drop its row now; the refresh
// that follows draws the truth.
function removeFileFromUI(filePath) {
  FM_PANELS.forEach(panel => {
    const p = fmPanes[panel];
    const n = p.items.length;
    p.items = p.items.filter(e => e.path !== filePath);
    selectedFiles.delete(filePath);
    if (p.items.length !== n) fmRender(panel);
  });
}

// ComicVine metadata search function
function searchComicVineMetadata(filePath, fileName) {
  console.log('ComicVine Search Called with:', { filePath, fileName });

  // Validate inputs
  if (!filePath || !fileName) {
    console.error('Invalid parameters:', { filePath, fileName });
    CLU.showToast('ComicVine Search Error', 'Missing file path or name', 'error');
    return;
  }

  if (!fileName.toLowerCase().match(/\.(cbz|cbr)$/)) {
    console.error('Invalid file type:', fileName);
    CLU.showToast('ComicVine Search Error', 'File must be CBZ or CBR format', 'error');
    return;
  }

  // Parse series name and issue from filename
  const nameWithoutExt = fileName.replace(/\.(cbz|cbr)$/i, '');

  // Show a simple loading indicator
  const loadingToast = document.createElement('div');
  loadingToast.className = 'toast show position-fixed top-0 end-0 m-3';
  loadingToast.style.zIndex = '1200';
  loadingToast.innerHTML = `
    <div class="toast-header bg-success text-white">
      <strong class="me-auto">ComicVine Search</strong>
      <small>Searching...</small>
    </div>
    <div class="toast-body">
      <div class="d-flex align-items-center">
        <div class="spinner-border spinner-border-sm me-2" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        Searching ComicVine for "${nameWithoutExt}"...
      </div>
    </div>
  `;
  document.body.appendChild(loadingToast);

  // Make request to backend
  const requestData = {
    file_path: filePath,
    file_name: fileName
  };
  console.log('ComicVine Search Request Data:', requestData);

  fetch('/search-comicvine-metadata', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(requestData)
  })
    .then(response => {
      console.log('ComicVine Search Response Status:', response.status);
      if (!response.ok) {
        return response.json().then(errorData => {
          if (response.status === 404) {
            return { success: false, notFound: true, error: errorData.error || 'Issue not found in ComicVine' };
          }
          throw new Error('HTTP error: ' + (errorData.error || response.statusText));
        }).catch((jsonError) => {
          if (response.status === 404) {
            return { success: false, notFound: true, error: 'Issue not found in ComicVine' };
          }
          throw new Error('HTTP error: ' + response.statusText);
        });
      }
      return response.json();
    })
    .then(data => {
      console.log('ComicVine Search Response Data:', data);
      document.body.removeChild(loadingToast);

      if (data.success) {
        CLU.showToast('ComicVine Search', `Added metadata to "${fileName}". Series: ${data.metadata && data.metadata.Series || 'Unknown'}, issue ${data.metadata && data.metadata.Number || 'Unknown'}`, 'success', 5000);

        // Remove file from UI if it was moved to a new location
        if (data.moved) {
          console.log('File was moved, removing from current panel');
          removeFileFromUI(filePath);
        }

        // Handle file rename if configured
        if (data.metadata && data.metadata.Series) {
          const actualFilePath = data.moved ? data.new_file_path : filePath;
          promptRenameAfterMetadata(actualFilePath, fileName, data.metadata, data.rename_config);
        }
      } else if (data.requires_selection) {
        // Show selection modal based on provider
        if (['mangadex', 'mangaupdates', 'anilist'].indexOf(data.provider) !== -1) {
          showMangaSeriesSelectionModal(data, filePath, fileName);
        } else if (data.provider === 'gcd_api') {
          if (data.requires_start_year) {
            showGCDApiStartYearPrompt(data, filePath, fileName);
          } else {
            showGCDApiSeriesSelectionModal(data, filePath, fileName);
          }
        } else {
          showComicVineVolumeSelectionModal(data, filePath, fileName);
        }
      } else if (data.notFound) {
        // Show not found message as warning
        CLU.showToast('ComicVine Search', `${data.error || 'Issue not found in ComicVine'}`, 'warning', 5000);
      } else {
        // Show error message
        CLU.showToast('ComicVine Search Error', `Failed to add metadata: ${data.error || 'Unknown error'}`, 'error', 8000);
      }
    })
    .catch(error => {
      console.error('ComicVine Search Network Error:', error);
      if (document.body.contains(loadingToast)) {
        document.body.removeChild(loadingToast);
      }

      CLU.showToast('Network Error', `Network error: ${error.message}`, 'error', 8000);
    });
}

// Stub for ComicVine volume selection modal - will be implemented similar to GCD
function showComicVineVolumeSelectionModal(data, filePath, fileName) {
  console.log('Showing ComicVine volume selection modal', data);

  // Populate parsed filename info
  document.getElementById('cvParsedSeries').textContent = data.parsed_filename.series_name;
  document.getElementById('cvParsedIssue').textContent = data.parsed_filename.issue_number;
  document.getElementById('cvParsedYear').textContent = data.parsed_filename.year || 'Unknown';

  // Update modal title
  const modalTitle = document.getElementById('comicVineVolumeModalLabel');
  if (modalTitle) {
    modalTitle.textContent = `Found ${data.possible_matches.length} Volume(s) - Select Correct One`;
  }

  // Populate volume list
  const volumeList = document.getElementById('cvVolumeList');
  volumeList.innerHTML = '';

  data.possible_matches.forEach(volume => {
    const volumeItem = document.createElement('div');
    volumeItem.className = 'list-group-item list-group-item-action d-flex align-items-start';
    volumeItem.style.cursor = 'pointer';

    const yearDisplay = volume.start_year || 'Unknown';
    const descriptionPreview = volume.description ?
      `<small class="text-muted d-block mt-1">${volume.description}</small>` : '';

    // Display thumbnail if available, otherwise show placeholder
    const thumbnailHtml = volume.image_url ?
      `<img src="${volume.image_url}" class="img-thumbnail me-3" style="width: 80px; height: 120px; object-fit: cover;" alt="${volume.name} cover">` :
      `<div class="me-3 d-flex align-items-center justify-content-center bg-secondary text-white" style="width: 80px; height: 120px; font-size: 10px;">No Cover</div>`;

    volumeItem.innerHTML = `
      ${thumbnailHtml}
      <div class="flex-grow-1 d-flex justify-content-between align-items-start">
        <div class="me-2">
          <div class="fw-bold">${volume.name}</div>
          <small class="text-muted">Publisher: ${volume.publisher_name || 'Unknown'}<br>Issues: ${volume.count_of_issues || 'Unknown'}</small>
          ${descriptionPreview}
        </div>
        <span class="badge bg-success rounded-pill">${yearDisplay}</span>
      </div>
    `;

    volumeItem.addEventListener('click', () => {
      // Highlight selected item
      volumeList.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
      });
      volumeItem.classList.add('active');

      // Call backend with selected volume (including publisher)
      selectComicVineVolume(filePath, fileName, volume.id, volume.publisher_name, data.parsed_filename.issue_number, data.parsed_filename.year);
    });

    volumeList.appendChild(volumeItem);
  });

  // Show the modal
  const modal = new bootstrap.Modal(document.getElementById('comicVineVolumeModal'));
  modal.show();
}

function showGCDApiSeriesSelectionModal(data, filePath, fileName) {
  console.log('Showing GCD API series selection modal', data);

  // Reuse the ComicVine volume modal UI
  document.getElementById('cvParsedSeries').textContent = data.parsed_filename.series_name;
  document.getElementById('cvParsedIssue').textContent = data.parsed_filename.issue_number;
  document.getElementById('cvParsedYear').textContent = data.parsed_filename.year || 'Unknown';

  const modalTitle = document.getElementById('comicVineVolumeModalLabel');
  if (modalTitle) {
    modalTitle.textContent = `Found ${data.possible_matches.length} Series (via GCD API) — Select Correct One`;
  }

  // Hide refine search row
  const refineRow = document.getElementById('cvRefineSearchRow');
  if (refineRow) refineRow.style.display = 'none';

  // Build language/country filter dropdown
  const allMatches = data.possible_matches;
  const langSet = {};
  allMatches.forEach(v => {
    const key = (v.language || v.country || '').toUpperCase();
    if (key) langSet[key] = (langSet[key] || 0) + 1;
  });

  // Remove old language filter if present
  const oldLangFilter = document.getElementById('gcdApiLangFilterFiles');
  if (oldLangFilter) oldLangFilter.parentNode.removeChild(oldLangFilter);

  let activeLangFilter = '';

  function renderFilteredList() {
    const volumeList = document.getElementById('cvVolumeList');
    volumeList.innerHTML = '';

    const filtered = activeLangFilter
      ? allMatches.filter(v => (v.language || '').toUpperCase() === activeLangFilter || (v.country || '').toUpperCase() === activeLangFilter)
      : allMatches;

    filtered.forEach(volume => {
      const volumeItem = document.createElement('div');
      volumeItem.className = 'list-group-item list-group-item-action d-flex align-items-start';
      volumeItem.style.cursor = 'pointer';

      const yearDisplay = volume.start_year || 'Unknown';
      const langDisplay = (volume.language || '').toUpperCase();
      const descriptionPreview = volume.description ?
        `<small class="text-muted d-block mt-1">${volume.description}</small>` : '';

      const thumbnailHtml = volume.image_url ?
        `<img src="${volume.image_url}" class="img-thumbnail me-3" style="width: 80px; height: 120px; object-fit: cover;" alt="${volume.name} cover">` :
        `<div class="me-3 d-flex align-items-center justify-content-center bg-secondary text-white" style="width: 80px; height: 120px; font-size: 10px;">No Cover</div>`;

      volumeItem.innerHTML = `
        ${thumbnailHtml}
        <div class="flex-grow-1 d-flex justify-content-between align-items-start">
          <div class="me-2">
            <div class="fw-bold">${volume.name}</div>
            <small class="text-muted">Publisher: ${volume.publisher_name || 'Unknown'}<br>Issues: ${volume.count_of_issues || 'Unknown'}</small>
            ${descriptionPreview}
          </div>
          <div class="text-end">
            <span class="badge bg-success rounded-pill">${yearDisplay}</span>
            ${langDisplay ? `<span class="badge bg-info rounded-pill ms-1">${langDisplay}</span>` : ''}
          </div>
        </div>
      `;

      volumeItem.addEventListener('click', () => {
        volumeList.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active'));
        volumeItem.classList.add('active');

        const modal = bootstrap.Modal.getInstance(document.getElementById('comicVineVolumeModal'));
        if (modal) modal.hide();

        CLU.showToast('GCD API', 'Retrieving metadata...', 'info');
        fetch('/api/search-metadata', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_path: filePath,
            file_name: fileName,
            selected_match: { provider: 'gcd_api', series_id: volume.id }
          })
        })
          .then(response => response.json())
          .then(result => {
            if (result.success) {
              CLU.showToast('Metadata Found', 'Metadata applied via GCD API', 'success');
              if (typeof window.refreshCurrentPage === 'function') window.refreshCurrentPage();
            } else {
              CLU.showToast('Metadata Error', result.error || 'No metadata found for selection', 'error');
            }
          })
          .catch(error => {
            CLU.showToast('Metadata Error', error.message || 'Failed to apply metadata', 'error');
          });
      });

      volumeList.appendChild(volumeItem);
    });
  }

  // Add language filter if multiple languages present
  if (Object.keys(langSet).length > 1) {
    const filterContainer = document.getElementById('cvFilterWrap') || document.getElementById('cvFilterInput');
    if (filterContainer && filterContainer.parentNode) {
      const selectEl = document.createElement('select');
      selectEl.id = 'gcdApiLangFilterFiles';
      selectEl.className = 'form-select form-select-sm';
      selectEl.style.width = '120px';
      selectEl.innerHTML = '<option value="">All languages</option>';
      Object.keys(langSet).sort().forEach(key => {
        selectEl.innerHTML += `<option value="${key}">${key} (${langSet[key]})</option>`;
      });
      filterContainer.parentNode.insertBefore(selectEl, filterContainer);
      selectEl.addEventListener('change', () => {
        activeLangFilter = selectEl.value;
        renderFilteredList();
      });
    }
  }

  renderFilteredList();

  const modal = new bootstrap.Modal(document.getElementById('comicVineVolumeModal'));
  modal.show();
}

function showGCDApiStartYearPrompt(data, filePath, fileName) {
  console.log('Showing GCD API start year prompt', data);

  const seriesName = (data.parsed_filename && data.parsed_filename.series_name) || 'Unknown';
  const message = data.message || `No series found for "${seriesName}". Enter the year the series started.`;

  // Reuse the ComicVine volume modal
  const modalTitle = document.getElementById('comicVineVolumeModalLabel');
  if (modalTitle) {
    modalTitle.textContent = 'GCD API - Series Start Year Required';
  }

  document.getElementById('cvParsedSeries').textContent = seriesName;
  document.getElementById('cvParsedIssue').textContent = data.parsed_filename.issue_number || '';
  document.getElementById('cvParsedYear').textContent = data.parsed_filename.year || 'Unknown';

  const refineRow = document.getElementById('cvRefineSearchRow');
  if (refineRow) refineRow.style.display = 'none';

  const volumeList = document.getElementById('cvVolumeList');
  volumeList.innerHTML = `
    <div class="p-3">
      <p class="text-muted">${message}</p>
      <p class="text-muted small">The GCD API filters by the year a series <strong>started</strong>,
        not the issue publication year. For example, a 2026 issue may belong to a series that started in 2025.</p>
      <div class="input-group mb-2">
        <input type="number" id="gcdApiStartYearInput" class="form-control" placeholder="e.g. 2025" min="1900" max="2100">
        <button class="btn btn-primary" type="button" id="gcdApiStartYearSearchBtn">
          <i class="bi bi-search me-1"></i>Search
        </button>
      </div>
      <button class="btn btn-outline-secondary btn-sm" type="button" id="gcdApiNoYearSearchBtn">
        Search without year filter
      </button>
    </div>
  `;

  const searchBtn = document.getElementById('gcdApiStartYearSearchBtn');
  const yearInput = document.getElementById('gcdApiStartYearInput');
  const noYearBtn = document.getElementById('gcdApiNoYearSearchBtn');

  function doSearch(startYear) {
    searchBtn.disabled = true;
    noYearBtn.disabled = true;
    searchBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Searching...';

    fetch('/api/search-metadata', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: filePath,
        file_name: fileName,
        search_term: seriesName,
        gcd_api_start_year: startYear || null
      })
    })
      .then(response => response.json())
      .then(result => {
        searchBtn.disabled = false;
        noYearBtn.disabled = false;
        searchBtn.innerHTML = '<i class="bi bi-search me-1"></i>Search';

        if (result.requires_selection && result.provider === 'gcd_api' && !result.requires_start_year) {
          const cvModal = bootstrap.Modal.getInstance(document.getElementById('comicVineVolumeModal'));
          if (cvModal) cvModal.hide();
          showGCDApiSeriesSelectionModal(result, filePath, fileName);
        } else if (result.success) {
          const cvModal = bootstrap.Modal.getInstance(document.getElementById('comicVineVolumeModal'));
          if (cvModal) cvModal.hide();
          CLU.showToast('Metadata Found', 'Metadata applied via GCD API', 'success');
          if (typeof window.refreshCurrentPage === 'function') {
            window.refreshCurrentPage();
          }
        } else if (result.requires_start_year) {
          CLU.showToast('No Results', 'No series found with that year. Try a different year.', 'warning');
        } else {
          CLU.showToast('No Results', result.error || 'No metadata found', 'warning');
        }
      })
      .catch(error => {
        searchBtn.disabled = false;
        noYearBtn.disabled = false;
        searchBtn.innerHTML = '<i class="bi bi-search me-1"></i>Search';
        CLU.showToast('Search Error', error.message || 'Search failed', 'error');
      });
  }

  searchBtn.addEventListener('click', () => {
    const yr = parseInt(yearInput.value, 10);
    if (!yr || yr < 1900 || yr > 2100) {
      CLU.showToast('Invalid Year', 'Please enter a valid year (1900-2100)', 'warning');
      return;
    }
    doSearch(yr);
  });

  yearInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') searchBtn.click();
  });

  noYearBtn.addEventListener('click', () => doSearch(null));

  const modal = new bootstrap.Modal(document.getElementById('comicVineVolumeModal'));
  modal.show();

  document.getElementById('comicVineVolumeModal').addEventListener('shown.bs.modal', function handler() {
    yearInput.focus();
    document.getElementById('comicVineVolumeModal').removeEventListener('shown.bs.modal', handler);
  });
}

// showBatchVolumeSelectionModal, fetchAllMetadataWithVolume – delegated to clu-metadata.js

function showMangaSeriesSelectionModal(data, filePath, fileName, libraryId, skipProviders) {
  console.log('Showing manga series selection modal', data);

  const provider = data.provider;
  const providerLabel = provider === 'mangadex' ? 'MangaDex' :
    provider === 'mangaupdates' ? 'MangaUpdates' : 'AniList';

  // Populate parsed filename info
  document.getElementById('mangaParsedSeries').textContent = data.parsed_filename.series_name;
  document.getElementById('mangaParsedIssue').textContent = data.parsed_filename.issue_number;
  document.getElementById('mangaParsedYear').textContent = data.parsed_filename.year || 'Unknown';

  // Update modal title
  const modalTitle = document.getElementById('mangaSeriesModalLabel');
  if (modalTitle) {
    modalTitle.textContent = `Select Correct Series (${providerLabel}) - ${data.possible_matches.length} result(s)`;
  }

  // Populate series list
  const seriesList = document.getElementById('mangaSeriesList');
  seriesList.innerHTML = '';

  data.possible_matches.forEach(series => {
    const seriesItem = document.createElement('div');
    seriesItem.className = 'list-group-item list-group-item-action d-flex align-items-start';
    seriesItem.style.cursor = 'pointer';

    const yearDisplay = series.start_year || 'Unknown';
    const descriptionPreview = series.description ?
      `<small class="text-muted d-block mt-1">${series.description.substring(0, 200)}${series.description.length > 200 ? '...' : ''}</small>` : '';

    const thumbnailHtml = series.image_url ?
      `<img src="${series.image_url}" class="img-thumbnail me-3" style="width: 80px; height: 120px; object-fit: cover;" alt="${series.name} cover">` :
      `<div class="me-3 d-flex align-items-center justify-content-center bg-secondary text-white" style="width: 80px; height: 120px; font-size: 10px;">No Cover</div>`;

    seriesItem.innerHTML = `
      ${thumbnailHtml}
      <div class="flex-grow-1 d-flex justify-content-between align-items-start">
        <div class="me-2">
          <div class="fw-bold">${series.name}</div>
          <small class="text-muted">Volumes: ${series.count_of_issues || 'Unknown'}</small>
          ${descriptionPreview}
        </div>
        <span class="badge bg-success rounded-pill">${yearDisplay}</span>
      </div>
    `;

    seriesItem.addEventListener('click', () => {
      // Highlight selected
      seriesList.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active'));
      seriesItem.classList.add('active');

      // Close modal and send selection
      const modal = bootstrap.Modal.getInstance(document.getElementById('mangaSeriesModal'));
      modal.hide();

      selectMangaSeries(filePath, fileName, provider, series.id, series.name, series.alternate_title, libraryId);
    });

    seriesList.appendChild(seriesItem);
  });

  // Wire the "Skip to next provider" button (shared logic from clu-metadata.js)
  if (window.CLU && typeof CLU.wireSkipButton === 'function') {
    CLU.wireSkipButton('mangaSkipProviderBtn', data, filePath, fileName, skipProviders || []);
  }

  const modal = new bootstrap.Modal(document.getElementById('mangaSeriesModal'));
  modal.show();
}

function selectMangaSeries(filePath, fileName, provider, seriesId, preferredTitle, alternateTitle, libraryId) {
  CLU.showToast(provider, 'Retrieving metadata...', 'info');

  fetch('/api/search-metadata', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_path: filePath,
      file_name: fileName,
      library_id: libraryId || null,
      selected_match: {
        provider: provider,
        series_id: seriesId,
        preferred_title: preferredTitle,
        alternate_title: alternateTitle
      }
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        CLU.showToast('Metadata Found', 'Metadata applied via ' + data.source, 'success');
        if (typeof window.refreshCurrentPage === 'function') {
          window.refreshCurrentPage();
        }
      } else {
        CLU.showToast('Metadata Error', data.error || 'No metadata found for selection', 'error');
      }
    })
    .catch(error => {
      CLU.showToast('Metadata Error', error.message || 'Failed to apply metadata', 'error');
    });
}

function selectComicVineVolume(filePath, fileName, volumeId, publisherName, issueNumber, year) {
  console.log('ComicVine volume selected:', { filePath, fileName, volumeId, publisherName, issueNumber, year });

  // Close the modal
  const modal = bootstrap.Modal.getInstance(document.getElementById('comicVineVolumeModal'));
  modal.hide();

  // Show loading indicator
  const loadingToast = document.createElement('div');
  loadingToast.className = 'toast show position-fixed top-0 end-0 m-3';
  loadingToast.style.zIndex = '1200';
  loadingToast.innerHTML = `
    <div class="toast-header bg-success text-white">
      <strong class="me-auto">ComicVine</strong>
      <small>Processing...</small>
    </div>
    <div class="toast-body">
      <div class="d-flex align-items-center">
        <div class="spinner-border spinner-border-sm me-2" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        Retrieving metadata...
      </div>
    </div>
  `;
  document.body.appendChild(loadingToast);

  // Make request to backend
  fetch('/search-comicvine-metadata-with-selection', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      file_path: filePath,
      file_name: fileName,
      volume_id: volumeId,
      publisher_name: publisherName,
      issue_number: issueNumber,
      year: year
    })
  })
    .then(response => response.json())
    .then(data => {
      document.body.removeChild(loadingToast);

      if (data.success) {
        // Show success with cover image
        CLU.showToast('ComicVine Success', `Added metadata to "${fileName}". Series: ${data.metadata?.Series || 'Unknown'}, issue ${data.metadata?.Number || 'Unknown'}`, 'success', 5000);

        // Remove file from UI if it was moved to a new location
        if (data.moved) {
          console.log('File was moved, removing from current panel');
          removeFileFromUI(filePath);
        }

        // Handle file rename if configured
        if (data.metadata?.Series) {
          const actualFilePath = data.moved ? data.new_file_path : filePath;
          promptRenameAfterMetadata(actualFilePath, fileName, data.metadata, data.rename_config);
        }
      } else {
        CLU.showToast('ComicVine Error', data.error || 'Failed to retrieve metadata', 'error');
      }
    })
    .catch(error => {
      document.body.removeChild(loadingToast);
      CLU.showToast('ComicVine Error', error.message, 'error');
    });
}

// Rename-template name building lives in clu-metadata.js (CLU.buildRenamedName /
// CLU.padIssueNumber / CLU.parseDateParts) so every page renames identically.

function promptRenameAfterMetadata(filePath, fileName, metadata, renameConfig) {
  // Name building is shared across pages — see CLU.buildRenamedName.
  const suggestedName = CLU.buildRenamedName(metadata, renameConfig, fileName);
  if (!suggestedName) {
    // null when the name wouldn't change.
    return;
  }

  // Only auto-rename when enabled; otherwise leave the file as-is.
  if (renameConfig && renameConfig.auto_rename) {
    renameFileAfterMetadata(filePath, fileName, suggestedName);
  }
}

function renameFileAfterMetadata(filePath, oldName, newName) {
  console.log('renameFileAfterMetadata called with:', { filePath, oldName, newName });

  // Construct the new full path
  const directory = filePath.substring(0, filePath.lastIndexOf('/'));
  const newPath = directory + '/' + newName;

  console.log('Constructed paths:', { old: filePath, new: newPath, directory });

  // Show loading toast
  const loadingToast = document.createElement('div');
  loadingToast.className = 'toast show position-fixed top-0 end-0 m-3';
  loadingToast.style.zIndex = '1200';
  loadingToast.innerHTML = `
    <div class="toast-header bg-primary text-white">
      <strong class="me-auto">Renaming</strong>
    </div>
    <div class="toast-body">
      <div class="d-flex align-items-center">
        <div class="spinner-border spinner-border-sm me-2" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        Renaming file...
      </div>
    </div>
  `;
  document.body.appendChild(loadingToast);

  fetch('/rename', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      old: filePath,
      new: newPath
    })
  })
    .then(response => {
      if (!response.ok) {
        return response.json().then(err => {
          throw new Error(err.error || 'Rename failed');
        });
      }
      return response.json();
    })
    .then(data => {
      document.body.removeChild(loadingToast);
      if (data.success) {
        CLU.showToast('File Renamed', `Successfully renamed to: ${newName}`, 'success');

        // Update the file in the DOM instead of reloading entire list
        updateRenamedFileInDOM(filePath, newPath, newName);
      } else {
        CLU.showToast('Rename Failed', data.error || 'Failed to rename file', 'error');
      }
    })
    .catch(error => {
      if (document.body.contains(loadingToast)) {
        document.body.removeChild(loadingToast);
      }
      console.error('Rename error:', error);
      CLU.showToast('Rename Error', error.message, 'error');
    });
}

function updateRenamedFileInDOM(oldPath, newPath, newName) {
  FM_PANELS.forEach(panel => {
    const e = fmPanes[panel].items.find(x => x.path === oldPath);
    if (!e) return;
    e.path = newPath;
    e.name = newName;
    fmRender(panel);
  });
}

// ============================================================================
// THREE-DOTS MENU ACTIONS (FROM COLLECTION.HTML)
// ============================================================================

/**
 * Execute a script action on a file (crop, remove first image, rebuild, enhance, add)
 * Contract setup wrapper for CLU.executeStreamingOp
 */
function executeScriptOnFile(scriptType, filePath, panel) {
  // Set up streaming contract for files.js page-specific behavior
  window._cluStreaming = {
    onComplete: function (type, path) {
      const currentPath = panel === 'source' ? currentSourcePath : currentDestinationPath;
      loadDirectories(currentPath, panel);
    },
    onError: function () {}
  };
  CLU.executeStreamingOp(scriptType, filePath);
}

/**
 * Hide the progress indicator
 * Contract setup wrapper for CLU streaming module
 */

/**
 * Show the missing file check results modal
 * @param {Object} data - The missing file data containing path, count, summary
 */
function showMissingFileCheckModal(data) {
  // Update summary
  const summaryEl = document.getElementById('missingFileCheckSummary');
  if (summaryEl) {
    summaryEl.textContent = data.summary || `Found ${data.count} missing issues.`;
  }

  // Update file path display
  const pathEl = document.getElementById('missingFileCheckPath');
  if (pathEl) {
    pathEl.textContent = data.path + '/missing.txt';
  }

  // Update file link
  const linkEl = document.getElementById('missingFileCheckLink');
  if (linkEl) {
    // Use static URL if available, otherwise construct download URL
    if (data.staticUrl) {
      linkEl.href = data.staticUrl;
    } else {
      linkEl.href = `/api/download?path=${encodeURIComponent(data.path + '/missing.txt')}`;
    }
    linkEl.target = '_blank';
  }

  // Show the modal
  const modalElement = document.getElementById('missingFileCheckModal');
  if (modalElement) {
    const modal = new bootstrap.Modal(modalElement);
    modal.show();
  }
}

/**
 * Execute a script operation on a directory
 * @param {string} scriptType - The type of script to run (convert, rebuild, pdf, missing, enhance_dir)
 * @param {string} directoryPath - Full path to the directory
 * @param {string} panel - Which panel the directory is in (source or destination)
 */
function bulkRemoveXmlFromDirectory(directoryPath, panel) {
  const folderName = directoryPath.split('/').pop() || directoryPath;
  document.getElementById('removeXmlDirName').textContent = folderName;

  // Store the path on the confirm button so the handler can read it
  const confirmBtn = document.getElementById('confirmRemoveXmlDirBtn');
  confirmBtn.dataset.directory = directoryPath;

  const modal = new bootstrap.Modal(document.getElementById('removeXmlDirModal'));
  modal.show();
}

// ============================================================================
// SMART RENAME
// ============================================================================

async function runSmartRename(directoryPath, panel) {
  const libraryId = getLibraryIdForPanel(panel);
  const folderName = directoryPath.split('/').pop() || directoryPath;
  let previewEnabled = true;
  try {
    const resp = await fetch('/api/preferences/smart_rename_preview_enabled');
    if (resp.ok) {
      const j = await resp.json();
      if (j && typeof j.value !== 'undefined' && j.value !== null) {
        previewEnabled = j.value !== false && j.value !== 0 && j.value !== '0';
      }
    }
  } catch (_) { /* default true */ }

  CLU.showToast('Smart Rename', `Building plan for ${folderName}...`, 'info');
  let planResp;
  try {
    planResp = await fetch('/smart-rename/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory: directoryPath, library_id: libraryId })
    });
  } catch (e) {
    CLU.showToast('Smart Rename Error', e.message, 'error');
    return;
  }
  const planJson = await planResp.json();
  if (!planResp.ok || planJson.error) {
    CLU.showToast('Smart Rename Error', planJson.error || `HTTP ${planResp.status}`, 'error');
    return;
  }
  const plan = planJson.plan;
  if (plan && plan.error) {
    CLU.showToast('Smart Rename Error', plan.error, 'error');
    return;
  }

  if (!previewEnabled) {
    await applySmartRenamePlan(plan, panel);
    return;
  }

  showSmartRenameModal(plan, panel);
}

function showSmartRenameModal(plan, panel) {
  const summaryEl = document.getElementById('smartRenameSummary');
  const tbody = document.getElementById('smartRenameTbody');
  const issuesEl = document.getElementById('smartRenameIssues');
  const applyBtn = document.getElementById('smartRenameApplyBtn');

  tbody.innerHTML = '';
  issuesEl.innerHTML = '';

  let okCount = 0;
  let skipCount = 0;
  const issues = [];

  for (const dir of (plan.directories || [])) {
    if (dir.status !== 'ok') {
      const reason = dir.reason ? ` — ${dir.reason}` : '';
      issues.push(`<li><code>${escapeHtml(dir.dir)}</code>: ${escapeHtml(dir.status)}${escapeHtml(reason)}</li>`);
      continue;
    }
    if (dir.warning) {
      issues.push(`<li><code>${escapeHtml(dir.dir)}</code>: ${escapeHtml(dir.warning)}</li>`);
    }
    for (const f of (dir.files || [])) {
      if (f.status === 'ok') {
        okCount++;
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="text-muted small text-truncate" style="max-width:300px" title="${escapeHtml(f.old_path)}">${escapeHtml(f.old_name)}</td>
          <td class="small text-truncate" style="max-width:300px" title="${escapeHtml(f.new_path)}">${escapeHtml(f.new_name)}</td>`;
        tbody.appendChild(tr);
      } else {
        skipCount++;
        const label = f.status === 'excluded_term'
          ? `skipped (matched "${escapeHtml(f.matched_term || '')}")`
          : escapeHtml(f.status);
        issues.push(`<li><code>${escapeHtml(f.old_name)}</code>: ${label}</li>`);
      }
    }
  }

  summaryEl.textContent = `${okCount} file(s) will be renamed. ${skipCount} skipped.`;
  issuesEl.innerHTML = issues.length ? `<details class="mt-2"><summary class="text-muted small">Issues (${issues.length})</summary><ul class="small mt-2">${issues.join('')}</ul></details>` : '';

  applyBtn.disabled = okCount === 0;
  applyBtn.onclick = async () => {
    applyBtn.disabled = true;
    applyBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Renaming...';
    const ok = await applySmartRenamePlan(plan, panel);
    const modal = bootstrap.Modal.getInstance(document.getElementById('smartRenamePreviewModal'));
    if (modal) modal.hide();
    applyBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>Apply';
    applyBtn.disabled = !ok;
  };

  const modalEl = document.getElementById('smartRenamePreviewModal');
  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

async function applySmartRenamePlan(plan, panel) {
  try {
    const resp = await fetch('/smart-rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan })
    });
    const j = await resp.json();
    if (!resp.ok || j.error) {
      CLU.showToast('Smart Rename Error', j.error || `HTTP ${resp.status}`, 'error');
      return false;
    }
    const s = j.summary || {};
    const msg = `Renamed ${s.renamed || 0}, skipped ${s.skipped || 0}, failed ${s.failed || 0}`;
    CLU.showToast('Smart Rename', msg, (s.failed || 0) > 0 ? 'warning' : 'success');
    const currentPath = panel === 'source' ? currentSourcePath : currentDestinationPath;
    if (currentPath) loadDirectories(currentPath, panel);
    return true;
  } catch (e) {
    CLU.showToast('Smart Rename Error', e.message, 'error');
    return false;
  }
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Execute a script operation on a directory
 * Contract setup wrapper for CLU.executeDirectoryOp
 */
function executeScriptOnDirectory(scriptType, directoryPath, panel, options) {
  // Set up streaming contract for files.js page-specific behavior
  window._cluStreaming = {
    onComplete: function (type, path) {
      const currentPath = panel === 'source' ? currentSourcePath : currentDestinationPath;
      loadDirectories(currentPath, panel);
    },
    onError: function () {}
  };
  CLU.executeDirectoryOp(scriptType, directoryPath, options || {});
}

/**
 * Open the edit modal for a CBZ file
 * @param {string} filePath - Path to the CBZ file to edit
 */
function openEditModal(filePath) {
  // Store the file path for later use when saving
  currentEditFilePath = filePath;

  // Open the edit modal
  const editModal = new bootstrap.Modal(document.getElementById('editCBZModal'));
  const container = document.getElementById('editInlineContainer');

  // Show loading spinner
  container.innerHTML = `<div class="d-flex justify-content-center my-3">
                              <button class="btn btn-primary" type="button" disabled>
                                  <span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span>
                                  Unpacking CBZ File ...
                              </button>
                          </div>`;

  editModal.show();
  CLU.setupEditModalDropZone();

  // Update modal title with filename
  const filename = filePath.split('/').pop().split('\\').pop();
  document.getElementById('editCBZModalText').textContent = `Editing ${filename}`;

  // Load CBZ contents
  fetch(`/edit?file_path=${encodeURIComponent(filePath)}`)
    .then(response => {
      if (!response.ok) {
        throw new Error("Failed to load edit content.");
      }
      return response.json();
    })
    .then(data => {
      document.getElementById('editInlineContainer').innerHTML = data.modal_body;
      document.getElementById('editInlineFolderName').value = data.folder_name;
      document.getElementById('editInlineZipFilePath').value = data.zip_file_path;
      document.getElementById('editInlineOriginalFilePath').value = data.original_file_path;
      CLU.sortInlineEditCards();
      CLU.initEditModalReorder();
    })
    .catch(error => {
      container.innerHTML = `<div class="alert alert-danger" role="alert">
                                  <strong>Error:</strong> ${error.message}
                              </div>`;
      CLU.showToast('Error', error.message, 'error');
    });
}

function saveEditedCBZ() {
  window._cluCbzEdit = {
    onSaveComplete: function (filePath) {
      if (currentSourcePath && currentEditFilePath && currentEditFilePath.startsWith(currentSourcePath)) {
        loadDirectories(currentSourcePath, 'source');
      } else if (currentDestinationPath && currentEditFilePath && currentEditFilePath.startsWith(currentDestinationPath)) {
        loadDirectories(currentDestinationPath, 'destination');
      }
    }
  };
  CLU.saveEditedCBZ();
}

// ============================================================================
// SPLIT MODAL
// ============================================================================

var currentSplitFilePath = null;

/**
 * Open the split modal for a multi-issue CBZ file.
 * @param {string} filePath - Path to the CBZ file to split
 */
function openSplitModal(filePath) {
  currentSplitFilePath = filePath;

  const splitModal = new bootstrap.Modal(document.getElementById('splitCBZModal'));
  const container = document.getElementById('splitInlineContainer');
  const folderInput = document.getElementById('splitOutputFolderName');
  if (folderInput) folderInput.value = '';

  container.innerHTML = `<div class="d-flex justify-content-center my-3">
                              <button class="btn btn-primary" type="button" disabled>
                                  <span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span>
                                  Unpacking CBZ File ...
                              </button>
                          </div>`;

  splitModal.show();

  const filename = filePath.split('/').pop().split('\\').pop();
  document.getElementById('splitCBZModalText').textContent = `Split ${filename}`;

  fetch(`/api/split-cbz/inspect?file_path=${encodeURIComponent(filePath)}`)
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(res => {
      if (!res.ok || !res.data.success) {
        throw new Error((res.data && res.data.error) || 'Failed to load split content.');
      }
      CLU.renderSplitGroups(res.data);
    })
    .catch(error => {
      container.innerHTML = `<div class="alert alert-danger" role="alert">
                                  <strong>Error:</strong> ${error.message}
                              </div>`;
      CLU.showToast('Error', error.message, 'error');
    });
}

function saveSplitCBZ() {
  window._cluCbzSplit = {
    onSaveComplete: function (filePath) {
      if (currentSourcePath && currentSplitFilePath && currentSplitFilePath.startsWith(currentSourcePath)) {
        loadDirectories(currentSourcePath, 'source');
      } else if (currentDestinationPath && currentSplitFilePath && currentSplitFilePath.startsWith(currentDestinationPath)) {
        loadDirectories(currentDestinationPath, 'destination');
      }
    }
  };
  CLU.saveSplitCBZ();
}

// ============================================================================
// EDIT MODAL CARD FUNCTIONS
// ============================================================================

// ============================================================================
// FREE-FORM CROP FUNCTIONALITY (delegated to clu-cbz-crop.js)
// ============================================================================

/**
 * Open the ComicVine URL modal for user to enter the URL
 * @param {string} directoryPath - The directory to save the cvinfo file in
 * @param {string} panel - The panel ('source' or 'destination') to refresh after saving
 */
function promptForCVInfo(directoryPath, panel) {
  // Store the directory path and panel in hidden fields
  document.getElementById('cvInfoDirectoryPath').value = directoryPath;
  document.getElementById('cvInfoPanel').value = panel;

  // Clear the input fields
  document.getElementById('cvInfoIdInput').value = '';
  document.getElementById('metronIdInput').value = '';

  // Show the modal
  const modal = new bootstrap.Modal(document.getElementById('cvInfoModal'));
  modal.show();

  // Focus the input field after modal is shown
  document.getElementById('cvInfoModal').addEventListener('shown.bs.modal', function () {
    document.getElementById('cvInfoIdInput').focus();
  }, { once: true });
}

/**
 * Save the ComicVine URL from the modal
 */
function saveCVInfo() {
  const cvId = document.getElementById('cvInfoIdInput').value.trim();
  const metronId = document.getElementById('metronIdInput').value.trim();
  const directoryPath = document.getElementById('cvInfoDirectoryPath').value;
  const panel = document.getElementById('cvInfoPanel').value;

  if (!cvId) {
    CLU.showToast('Error', 'Please enter a Comic Vine Volume ID', 'error');
    return;
  }

  // Validate that it's a number
  if (!/^\d+$/.test(cvId)) {
    CLU.showToast('Error', 'Comic Vine ID must be a number', 'error');
    return;
  }

  // Validate Metron ID if provided
  if (metronId && !/^\d+$/.test(metronId)) {
    CLU.showToast('Error', 'Metron ID must be a number', 'error');
    return;
  }

  // Build the file content
  let content = `https://comicvine.gamespot.com/volume/4050-${cvId}`;
  if (metronId) {
    content += `\nseries_id: ${metronId}`;
  }

  // Hide the modal
  const modalEl = document.getElementById('cvInfoModal');
  const modal = bootstrap.Modal.getInstance(modalEl);
  modal.hide();

  // Save the cvinfo file
  fetch('/api/save-cvinfo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      directory: directoryPath,
      content: content
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        CLU.showToast('Success', 'CVINFO file saved successfully!', 'success');
        // Refresh the directory listing to show the new file
        loadDirectories(directoryPath, panel);
      } else {
        CLU.showToast('Error', data.error || 'Failed to save CVINFO file', 'error');
      }
    })
    .catch(error => {
      console.error('Error saving CVINFO:', error);
      CLU.showToast('Error', 'An error occurred while saving the CVINFO file', 'error');
    });
}
