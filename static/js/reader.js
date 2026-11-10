// ============================================================================
// COMIC READER FUNCTIONALITY (Shared Module)
// ============================================================================
//
// Extracted from collection.js so it can be reused by source_wall and other pages.
//
// External contracts:
//   - window._readerAllItems: Array of {name, path, type, thumbnailUrl?} for next-issue detection
//   - window._readerReadIssuesSet: Set of paths already read (optional, for mark-read tracking)
//   - showError(msg) / showSuccess(msg): toast helpers (optional; errors silently ignored if missing)
//   - Swiper must be loaded before this script.
// ============================================================================

let comicReaderSwiper = null;
let currentComicPath = null;
let currentComicPageCount = 0;
let highestPageViewed = 0;
let currentComicSiblings = [];  // All comic files in current folder
let currentComicIndex = -1;     // Index of current comic in siblings
let nextIssueOverlayShown = false;  // Track if overlay is currently shown
let savedReadingPosition = null;  // Track saved reading position for current comic
let readingStartTime = null;      // Start time of current reading session
let accumulatedTime = 0;          // Total time spent reading prior to this session
let pageEdgeColors = new Map();   // Cache of extracted edge colors per page index

// --- Reading-position bookkeeping -------------------------------------------
// `highestPageViewed` is EVIDENCE OF READING: the furthest page the user
// actually paged to. It must never be advanced by a programmatic jump (resume,
// page-selector), or merely resuming a bookmark near the end would look like
// "finished" and destroy that bookmark. `suppressProgressOnNextChange` is set
// by readerSlideTo() for exactly that reason. The progress bar reads
// activeIndex instead, so display and evidence stay separate concerns.
let suppressProgressOnNextChange = false;
let autoSaveTimer = null;         // Trailing-edge timer for the throttled autosave
let lastAutoSaveAt = 0;           // Timestamp of the last throttled autosave
let lastPersistedPage = null;     // Page of the last write, to skip no-op saves
let completionSent = false;       // Guards against double mark-read/delete
let preserveBookmarkOnClose = false;  // Set when the resume prompt was deferred

const AUTOSAVE_INTERVAL_MS = 10000;

// Event listener references for cleanup
let zoomKeyboardHandler = null;
let mousewheelHandler = null;
let wheelTimeout = null;

// Immersive reader chrome state
let readerChromeHidden = false;
let chromeToggleTimeout = null;

// Comic file extensions
const COMIC_EXTENSIONS = ['.cbz', '.cbr', '.cb7', '.zip', '.rar', '.7z', '.pdf'];

// Zoom step levels: 3 increments from minRatio (1) to maxRatio (3)
const ZOOM_STEPS = [1, 1.67, 2.33, 3];

// --- Layout: paged vs. scroll, and what a page is fitted to -------------------
// readerMode  'paged'  one page at a time (Swiper)
//             'scroll' one continuous vertical strip, webtoon style
// readerFit   'width'  a page fills the window's width (no side margins)
//             'height' a page is shown whole (the old behaviour)
// Both are per-account preferences (/api/reader-prefs). The defaults here only
// apply until that fetch answers, or when it fails.
const READER_MODES = ['paged', 'scroll'];
const READER_FITS = ['width', 'height'];
let readerMode = 'paged';
let readerFit = 'width';

// Paged + fit-to-width. A portrait page is laid out by CSS to fit the window's
// HEIGHT (that is what `max-height: 100%` does), so fitting its width is a
// Swiper zoom of `slide width / laid-out image width`. fitBaseScale is that
// scale for the active page (1 when nothing needs zooming); the zoom buttons
// step relative to it, and "zoomed" means "beyond it".
let fitBaseScale = 1;
let pendingFitAlign = 'top';      // where to land on the next page: top | bottom
let lastWheelTurnAt = 0;          // cooldown so one wheel flick turns one page
const WHEEL_TURN_COOLDOWN_MS = 450;
const FIT_STEP_MULTIPLIERS = [1.5, 2];  // zoom steps above the fitted scale
let resizeTimer = null;

// Scroll mode state (null unless the strip is on screen). See
// initializeScrollReader().
let scrollState = null;
// True while setReaderMode() rebuilds the view on the page the user is on.
// Landing there is navigation: it must not advance highestPageViewed.
let rebuildingReaderView = false;
const SCROLL_WIDTH_STEPS = [40, 55, 70, 85, 100, 125, 150];  // column width, %
const SCROLL_DEFAULT_WIDTH = 100;
const SCROLL_PINCH_MIN = 40;   // pinch limits, column width %
const SCROLL_PINCH_MAX = 300;
// Pages are fetched from this far outside the viewport, and released once they
// are this many viewport heights away, so a 100-page comic never has more than
// a handful of decoded images alive.
const SCROLL_LOAD_MARGIN = '200% 0px';
const SCROLL_UNLOAD_VIEWPORTS = 6;
// The page that counts as "current" is the one under this line (fraction of
// the viewport height measured from the top).
const SCROLL_READING_LINE = 0.35;

// --- Panning the zoom window -------------------------------------------------
// Zooming always centres on the page, so without these the zoomed-in reader can
// only ever show the middle of the artwork. Keys that pan:
//
//   Shift/Ctrl + arrows   pan (arrows need a modifier -- bare arrows are
//                         already page-turn (left/right) and zoom (up/down))
//   W A S D               pan, no modifier needed
//   0 / Home              re-centre without changing the zoom level
//   wheel                 pan vertically; Shift+wheel pans horizontally
//
// One key press moves the view by this fraction of the visible page, so the
// step stays useful at every zoom level (a fixed pixel step is imperceptible
// at 3x on a large display).
const PAN_STEP_FRACTION = 0.2;

// Wheel deltas arrive in three units depending on the device and browser;
// normalise them to pixels before treating them as a pan distance.
const WHEEL_LINE_HEIGHT = 16;

// Keys that pan, mapped to a direction. Direction is the direction the VIEW
// moves, so the image translates the opposite way -- the scroll convention.
const PAN_KEYS = {
    ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
    w: 'up', W: 'up', s: 'down', S: 'down',
    a: 'left', A: 'left', d: 'right', D: 'right'
};

// The pan hint is a one-off nudge, not a permanent HUD: it appears the first
// time the user zooms in and then only for the first few sessions ever.
const PAN_HINT_STORAGE_KEY = 'cluReaderPanHintSeen';
const PAN_HINT_MAX_SHOWS = 3;
const PAN_HINT_DURATION_MS = 4000;
let panHintTimeout = null;
let panHintShownThisSession = false;

// --- Tap zones ---------------------------------------------------------------
// A tap in the left third goes back, the right third goes forward, the middle
// toggles the toolbars. Side taps act at once (no double-tap wait), so
// double-tap-to-zoom only exists in the middle third.
const TAP_ZONE_FRACTION = 1 / 3;

/** 'back' | 'forward' | 'middle' for a viewport x inside `el`. */
function readerTapZone(el, clientX) {
    const rect = el.getBoundingClientRect();
    const f = rect.width ? (clientX - rect.left) / rect.width : 0.5;
    if (f < TAP_ZONE_FRACTION) return 'back';
    if (f > 1 - TAP_ZONE_FRACTION) return 'forward';
    return 'middle';
}

// --- Two-page spreads --------------------------------------------------------
// iPad landscape shows two pages side by side, the cover alone on the right
// like a book. Slides stay one per page, so every page index in this file keeps
// meaning what it did; Swiper does the grouping (see the spread options in
// initializeComicReader). shortcut: a wide double-page scan is shown at half
// width, not joined; upgrade by probing page sizes server-side.
const SPREAD_QUERY = '(orientation: landscape) and (min-width: 1000px) and (pointer: coarse)';
let readerSpread = false;

function wantsSpread() {
    return readerMode === 'paged' && window.matchMedia(SPREAD_QUERY).matches;
}

/** First page of the spread holding `page`: 0, then 1, 3, 5... */
function spreadStart(page) {
    return page <= 0 ? 0 : (page % 2 === 1 ? page : page - 1);
}

// --- Pull past the end ---------------------------------------------------------
// Swipe up (or wheel down) past the last page opens the next issue; swipe down
// (or wheel up) past the first page opens the previous one. A swipe down
// anywhere else, once the page is at its top edge, closes the reader.
const OVERSCROLL_SWIPE_PX = 90;
const OVERSCROLL_WHEEL_PX = 240;
const OVERSCROLL_SETTLE_MS = 400;   // rest at the edge first, so momentum can't carry through
let overscrollTouch = null;
let overscrollWheel = { sum: 0, last: 0, dir: null };
let lastPageChangeAt = 0;

/**
 * Encode a file path for URL while preserving slashes
 * @param {string} path - The file path to encode
 * @returns {string} Encoded path (without leading slash for use in URLs)
 */
function encodeFilePath(path) {
    // Remove leading slash if present (will be part of the URL path)
    const cleanPath = path.startsWith('/') ? path.substring(1) : path;
    // Split by slash, encode each component, then rejoin
    return cleanPath.split('/').map(component => encodeURIComponent(component)).join('/');
}

/**
 * Is the key going to a control that owns its own keyboard handling?
 *
 * The reader's own page selector is a <select>: swallowing Space there would
 * stop it opening, and swallowing W/A/S/D would break its typeahead. The reader
 * binds on `document`, so this is the only thing keeping those keys off it.
 *
 * @param {EventTarget} target
 * @returns {boolean}
 */
function _isFormControlTarget(target) {
    if (!target || !target.tagName) return false;
    if (target.isContentEditable) return true;
    return ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName);
}

/**
 * Handle keydown events specific to comic reader (spacebar only)
 * Arrow keys are handled by handleZoomKeyboard
 * @param {KeyboardEvent} e - The keydown event
 */
function handleComicReaderKeydown(e) {
    if (!readerHasView()) return;
    if (_isFormControlTarget(e.target)) return;

    // Spacebar to advance
    if (e.code === 'Space') {
        e.preventDefault(); // Prevent page scroll
        if (scrollState) {
            scrollReaderBy((e.shiftKey ? -1 : 1) * 0.9);
        } else {
            readerAdvance();
        }
    }
}

/** Is a reader view (paged or scroll) built and on screen? */
function readerHasView() {
    return !!(comicReaderSwiper || scrollState);
}

/** Zero-based index of the page the reader is on, in either mode. */
function getReaderCurrentIndex() {
    if (scrollState) return scrollState.index;
    return comicReaderSwiper ? comicReaderSwiper.activeIndex : 0;
}

/** URL of one page image. */
function readerPageUrl(pageNum) {
    return `/api/read/${encodeFilePath(currentComicPath)}/page/${pageNum}`;
}

// ---------------------------------------------------------------------------
// Layout preferences and the two toolbar buttons
// ---------------------------------------------------------------------------

/** Fetch this account's layout prefs. Never rejects: failure keeps defaults. */
function loadReaderPrefs() {
    return fetch('/api/reader-prefs')
        .then(r => r.json())
        .then(data => {
            if (!data || !data.success) return;
            if (READER_MODES.includes(data.mode)) readerMode = data.mode;
            if (READER_FITS.includes(data.fit)) readerFit = data.fit;
        })
        .catch(() => { /* keep whatever we had */ });
}

/** Persist the layout prefs. Best effort: the reader works without it. */
function saveReaderPrefs() {
    fetch('/api/reader-prefs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: readerMode, fit: readerFit })
    }).catch(err => console.error('Failed to save reader preferences:', err));
}

/**
 * Build the layout buttons on first use.
 *
 * Created here rather than in markup because the reader modal is duplicated
 * across four templates; injecting them keeps those copies from drifting (the
 * pan hint does the same).
 */
function ensureReaderViewControls() {
    const controls = document.querySelector('.comic-reader-footer-controls');
    if (!controls) return;

    if (!document.getElementById('readerModeBtn')) {
        const modeBtn = document.createElement('button');
        modeBtn.id = 'readerModeBtn';
        modeBtn.type = 'button';
        modeBtn.className = 'btn btn-sm btn-outline-light zoom-btn';
        modeBtn.innerHTML = '<i class="bi bi-view-stacked text-light" aria-hidden="true"></i>';
        modeBtn.onclick = () => setReaderMode(readerMode === 'scroll' ? 'paged' : 'scroll');
        controls.insertBefore(modeBtn, document.getElementById('pageSelector'));
    }
    if (!document.getElementById('readerFitBtn')) {
        const fitBtn = document.createElement('button');
        fitBtn.id = 'readerFitBtn';
        fitBtn.type = 'button';
        fitBtn.className = 'btn btn-sm btn-outline-light zoom-btn';
        fitBtn.innerHTML = '<i class="bi text-light" aria-hidden="true"></i>';
        fitBtn.onclick = () => setReaderFit(readerFit === 'width' ? 'height' : 'width');
        controls.insertBefore(fitBtn, document.getElementById('pageSelector'));
    }
    updateReaderViewControls();
}

/** Make the buttons say what they are doing and what a click will do. */
function updateReaderViewControls() {
    const modeBtn = document.getElementById('readerModeBtn');
    if (modeBtn) {
        const scroll = readerMode === 'scroll';
        const label = scroll ? 'Scroll mode is on. Switch to page-by-page' : 'Switch to continuous scroll';
        modeBtn.title = label;
        modeBtn.setAttribute('aria-label', label);
        modeBtn.setAttribute('aria-pressed', scroll ? 'true' : 'false');
        modeBtn.classList.toggle('active', scroll);
    }
    const fitBtn = document.getElementById('readerFitBtn');
    if (fitBtn) {
        const width = readerFit === 'width';
        const label = width ? 'Fitted to width. Fit whole page instead' : 'Whole page shown. Fit to width instead';
        fitBtn.title = label;
        fitBtn.setAttribute('aria-label', label);
        const icon = fitBtn.querySelector('i');
        if (icon) {
            icon.classList.toggle('bi-arrow-left-right', width);
            icon.classList.toggle('bi-arrow-down-up', !width);
        }
        // Scroll mode is always as wide as its column; fit has no meaning there.
        fitBtn.style.display = readerMode === 'scroll' ? 'none' : '';
    }
}

/** Switch between paged and scroll, staying on the same page. */
function setReaderMode(mode) {
    if (!READER_MODES.includes(mode) || mode === readerMode) return;
    readerMode = mode;
    saveReaderPrefs();
    updateReaderViewControls();
    if (!currentComicPath || currentComicPageCount <= 0) return;

    const index = getReaderCurrentIndex();
    // Rebuilding is navigation, not reading: it must not count the page it
    // lands on as read (highestPageViewed survives, see init handlers).
    rebuildingReaderView = true;
    try {
        initializeComicReader(currentComicPageCount, index);
    } finally {
        rebuildingReaderView = false;
    }
}

/** Change what pages are fitted to (paged mode). */
function setReaderFit(fit) {
    if (!READER_FITS.includes(fit) || fit === readerFit) return;
    readerFit = fit;
    saveReaderPrefs();
    updateReaderViewControls();
    if (comicReaderSwiper) {
        resetPagedZoomToFit('top');
    }
}

/**
 * Check if this is a phone/tablet: a narrow viewport OR a touch-first device.
 * Width alone is not enough -- a tablet rotated to landscape is 1180-1366px
 * wide, and would otherwise be treated as a desktop the moment it turns.
 * @returns {boolean}
 */
function isMobileOrTablet() {
    return window.matchMedia('(max-width: 1024px), (hover: none), (pointer: coarse)').matches;
}

/**
 * Toggle the reader chrome (header/footer) visibility. Works at every size:
 * the chrome overlays the page, so hiding it never resizes the swiper.
 */
function toggleReaderChrome() {
    const container = document.querySelector('.comic-reader-container');
    if (!container) return;
    readerChromeHidden = !readerChromeHidden;
    container.classList.toggle('reader-chrome-hidden', readerChromeHidden);
}

/** Helper: get the items array for sibling detection */
function _getReaderItems() {
    return window._readerAllItems || [];
}

/** Helper: get the readIssuesSet for mark-read tracking */
function _getReadIssuesSet() {
    return window._readerReadIssuesSet || new Set();
}

/** Helper: add path to readIssuesSet if available */
function _markPathAsRead(path) {
    const s = window._readerReadIssuesSet;
    if (s && typeof s.add === 'function') s.add(path);
    // Optional host hook so a page can refresh its own read badges.
    if (typeof window._readerOnMarkedRead === 'function') {
        try { window._readerOnMarkedRead(path); } catch (e) { /* host's problem */ }
    }
}

/** Helper: report an error via the toast helper if the page has one. */
function _readerError(message) {
    if (window.CLU && typeof CLU.showError === 'function') {
        CLU.showError(message);
    } else {
        console.error(message);
    }
}

/**
 * Total seconds to report for this comic.
 *
 * INVARIANT: `accumulatedTime` is the server's stored total as of open and is
 * never reassigned; `readingStartTime` is set once at open and never reset.
 * Every write therefore reports an ABSOLUTE total, which makes writes
 * idempotent under the server's INSERT OR REPLACE. Do not "optimise" this by
 * folding the session into accumulatedTime after a save unless you also reset
 * readingStartTime -- otherwise the periodic autosave double-counts time.
 */
function _readerTotalTime() {
    let sessionTime = Math.max(0, (Date.now() - readingStartTime) / 1000);
    // Ignore very short sessions (previewing) when nothing was recorded before.
    if (sessionTime < 10) sessionTime = 0;
    return Math.round(accumulatedTime + sessionTime);
}

/** Build the payload for POST /api/reading-position. */
function _readerPositionPayload() {
    return {
        comic_path: currentComicPath,
        page_number: getReaderCurrentIndex() + 1,
        total_pages: currentComicPageCount,
        time_spent: _readerTotalTime()
    };
}

/**
 * Persist the current reading position.
 *
 * The server treats page_number <= 1 as "clear my bookmark", which is what lets
 * an unload flush express "start over" -- sendBeacon can only issue a POST.
 *
 * @param {Object}  [opts]
 * @param {boolean} [opts.useBeacon] Use a transport that survives page unload.
 */
function persistReadingPosition({ useBeacon = false } = {}) {
    if (!currentComicPath || !readerHasView() || currentComicPageCount <= 0) return;

    const payload = _readerPositionPayload();

    // The user deferred the resume prompt and never left page 1. Writing page 1
    // would clear a bookmark they never chose to discard, so leave it alone.
    if (preserveBookmarkOnClose && payload.page_number <= 1) return;

    // Duplicate writes are harmless (absolute time + INSERT OR REPLACE); this
    // is purely to avoid pointless requests. A beacon is the last chance to
    // save, so it always goes out.
    if (!useBeacon && payload.page_number === lastPersistedPage) return;
    lastPersistedPage = payload.page_number;

    const body = JSON.stringify(payload);

    if (useBeacon && navigator.sendBeacon) {
        // A Blob carries a real Content-Type; a bare string would be sent as
        // text/plain. The server tolerates both, but prefer the correct one.
        const blob = new Blob([body], { type: 'application/json' });
        if (navigator.sendBeacon('/api/reading-position', blob)) return;
        // sendBeacon returns false when over the UA queue budget -> fall through.
    }

    fetch('/api/reading-position', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: useBeacon
    }).catch(err => console.error('Failed to save reading position:', err));
}

/** Cancel any pending throttled autosave. */
function cancelPendingAutoSave() {
    if (autoSaveTimer) {
        clearTimeout(autoSaveTimer);
        autoSaveTimer = null;
    }
}

/**
 * Throttled autosave, called on every real page turn.
 * Leading-edge plus a trailing timer so the final page turn is never lost.
 */
function scheduleAutoSave() {
    const now = Date.now();
    if (now - lastAutoSaveAt >= AUTOSAVE_INTERVAL_MS) {
        lastAutoSaveAt = now;
        persistReadingPosition();
        return;
    }
    cancelPendingAutoSave();
    autoSaveTimer = setTimeout(() => {
        autoSaveTimer = null;
        lastAutoSaveAt = Date.now();
        persistReadingPosition();
    }, AUTOSAVE_INTERVAL_MS - (now - lastAutoSaveAt));
}

/**
 * Mark the current comic finished: record the read and drop the bookmark.
 * Guarded so the next-issue overlay and closeComicReader can't both fire it.
 */
function markCurrentComicFinished() {
    if (!currentComicPath || currentComicPageCount <= 0 || completionSent) return;
    completionSent = true;

    const path = currentComicPath;
    cancelPendingAutoSave();

    fetch('/api/mark-comic-read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            path,
            page_count: currentComicPageCount,
            time_spent: _readerTotalTime()
        })
    }).then(() => {
        _markPathAsRead(path);
    }).catch(err => console.error('Failed to mark comic as read:', err));

    fetch(`/api/reading-position?path=${encodeURIComponent(path)}`, {
        method: 'DELETE'
    }).catch(err => console.error('Failed to delete reading position:', err));
}

/**
 * Has the user actually finished this comic?
 *
 * Uses highestPageViewed (real paging only -- see the note by its declaration).
 * Short comics must be read to the final page; from 10 pages up, the
 * second-to-last page counts, which skips trailing ads/credits without ever
 * being vacuously true the way the old `currentPage > pageCount - 3` was.
 */
function hasFinishedCurrentComic() {
    if (currentComicPageCount <= 0) return false;
    const lastIndex = currentComicPageCount - 1;
    const endThreshold = currentComicPageCount >= 10 ? lastIndex - 1 : lastIndex;
    return highestPageViewed >= endThreshold;
}

/** Slide without counting the jump as pages read. */
function readerSlideTo(index) {
    if (scrollState) {
        scrollToReaderPage(index);
        return;
    }
    if (!comicReaderSwiper) return;
    suppressProgressOnNextChange = true;
    comicReaderSwiper.slideTo(index);
}

/**
 * Open comic reader for a specific file
 * @param {string} filePath - Path to the comic file
 */
function openComicReader(filePath) {
    currentComicPath = filePath;
    // Reset BEFORE the info fetch: if it fails, closeComicReader() runs with a
    // stale page count and would evaluate completion for the previous comic.
    currentComicPageCount = 0;
    highestPageViewed = 0;
    nextIssueOverlayShown = false;
    savedReadingPosition = null;
    readingStartTime = Date.now();
    accumulatedTime = 0;
    pageEdgeColors = new Map();
    suppressProgressOnNextChange = false;
    lastPersistedPage = null;
    lastAutoSaveAt = 0;
    completionSent = false;
    preserveBookmarkOnClose = false;
    cancelPendingAutoSave();

    // Track sibling comics for "next issue" feature
    currentComicSiblings = _getReaderItems().filter(item => {
        if (item.type !== 'file') return false;
        // Test the path, falling back to name: some hosts (reading lists) use a
        // display label like "Batman #1" as the name, which has no extension.
        const subject = (item.path || item.name || '').toLowerCase();
        const ext = subject.substring(subject.lastIndexOf('.'));
        return COMIC_EXTENSIONS.includes(ext);
    });
    currentComicIndex = currentComicSiblings.findIndex(item => item.path === filePath);

    const modal = document.getElementById('comicReaderModal');
    const titleEl = document.getElementById('comicReaderTitle');
    const pageInfoEl = document.getElementById('comicReaderPageInfo');

    // Hide overlays if visible from previous session
    hideNextIssueOverlay();
    hideResumeReadingOverlay();

    // Reset bookmark button state
    updateBookmarkButtonState(false);

    ensureReaderViewControls();

    // Show modal
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent scrolling
    blockNativePageZoom();

    // Immersive mode: hide chrome by default on mobile/tablet
    if (isMobileOrTablet()) {
        const container = document.querySelector('.comic-reader-container');
        if (container) {
            container.classList.add('reader-chrome-hidden');
            readerChromeHidden = true;
        }
    }

    // Set title
    const fileName = filePath.split(/[/\\]/).pop();
    titleEl.textContent = fileName;

    // Show loading
    pageInfoEl.textContent = 'Loading...';

    // Encode the path properly for URL
    const encodedPath = encodeFilePath(filePath);

    // Fetch comic info and saved position in parallel
    Promise.all([
        fetch(`/api/read/${encodedPath}/info`).then(r => r.json()),
        // A failed position lookup must not stop the comic from opening.
        fetch(`/api/reading-position?path=${encodeURIComponent(filePath)}`)
            .then(r => r.json())
            .catch(() => ({ page_number: null })),
        // Layout prefs: never rejects, a failure keeps the defaults.
        loadReaderPrefs()
    ])
        .then(([comicData, positionData]) => {
            if (comicData.success) {
                currentComicPageCount = comicData.page_count;

                // Get accumulated time if available
                if (positionData && positionData.time_spent) {
                    accumulatedTime = positionData.time_spent;
                }

                // Check if there's a saved position
                if (positionData.page_number !== null && positionData.page_number > 0) {
                    savedReadingPosition = positionData.page_number;
                    // Show resume prompt
                    showResumeReadingOverlay(positionData.page_number, comicData.page_count);
                    // Initialize reader but don't navigate yet
                    initializeComicReader(comicData.page_count, 0);
                    updateBookmarkButtonState(true);
                } else {
                    initializeComicReader(comicData.page_count, 0);
                }
            } else {
                _readerError('Failed to load comic: ' + (comicData.error || 'Unknown error'));
                closeComicReader();
            }
        })
        .catch(error => {
            console.error('Error loading comic:', error);
            _readerError('An error occurred while loading the comic.');
            closeComicReader();
        });

    // Add keyboard listener
    document.addEventListener('keydown', handleComicReaderKeydown);
}

/**
 * Initialize the Swiper comic reader
 * @param {number} pageCount - Total number of pages
 * @param {number} startPage - Page to start on (0-indexed, default 0)
 */
function initializeComicReader(pageCount, startPage = 0) {
    // Tear down whichever view is up (a mode switch rebuilds in place).
    destroyReaderView();
    lastPageChangeAt = Date.now();  // a fresh view must settle before a wheel push counts

    if (readerMode === 'scroll') {
        readerSpread = false;
        initializeScrollReader(pageCount, startPage);
        initializePageSelector(pageCount, startPage);
        initializeZoomControls();
        return;
    }

    const wrapper = document.getElementById('comicReaderWrapper');
    const pageInfoEl = document.getElementById('comicReaderPageInfo');

    // Clear existing slides
    wrapper.innerHTML = '';

    readerSpread = wantsSpread();
    if (readerSpread) startPage = spreadStart(startPage);

    // Create slides for each page
    for (let i = 0; i < pageCount; i++) {
        const slide = document.createElement('div');
        slide.className = 'swiper-slide';
        slide.dataset.pageNum = i;

        // Add loading spinner initially
        slide.innerHTML = `
            <div class="comic-page-loading">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>
        `;

        wrapper.appendChild(slide);
    }

    // Initialize Swiper with zoom support
    comicReaderSwiper = new Swiper('#comicReaderSwiper', {
        direction: 'horizontal',
        loop: false,
        initialSlide: startPage,
        // Spread: two slides per view, grouped in pairs after a lone cover that
        // is pushed to the right half by an offset of one slide width.
        ...(readerSpread ? {
            slidesPerView: 2,
            slidesPerGroup: 2,
            slidesPerGroupSkip: 1,
            slidesOffsetBefore: Math.round(document.getElementById('comicReaderSwiper').clientWidth / 2),
        } : {}),
        keyboard: {
            enabled: false, // Disable default keyboard to handle zoom with arrow keys
            onlyInViewport: false,
        },
        mousewheel: {
            enabled: false, // Disabled - using custom handler for zoom-aware behavior
        },
        navigation: {
            nextEl: '.swiper-button-next',
            prevEl: '.swiper-button-prev',
        },
        lazy: {
            loadPrevNext: true,
            loadPrevNextAmount: 2,
        },
        // Enable zoom for pinch-to-zoom on mobile
        zoom: {
            maxRatio: 3,
            minRatio: 1,
            // Off: Swiper's own toggle zooms out to 1 or in to maxRatio, which
            // knows nothing about the fitted scale. Our doubleTap handler below
            // does the toggling.
            toggle: false,
        },
        // Improve touch handling for mobile
        touchEventsTarget: 'container',
        passiveListeners: true,
        on: {
            slideChange: function () {
                const currentIndex = this.activeIndex;
                lastPageChangeAt = Date.now();
                // In a spread the right-hand page is on screen too.
                const lastSeen = readerSpread ? Math.min(currentIndex + 1, pageCount - 1) : currentIndex;
                pageInfoEl.textContent = readerSpread && lastSeen > currentIndex
                    ? `Pages ${currentIndex + 1}-${lastSeen + 1} of ${pageCount}`
                    : `Page ${currentIndex + 1} of ${pageCount}`;

                // Update page selector dropdown
                const pageSelector = document.getElementById('pageSelector');
                if (pageSelector) {
                    pageSelector.value = currentIndex;
                }

                // Track highest page viewed for read progress. A programmatic
                // jump (resume / page-selector) is not evidence of reading, so
                // it must not advance the high-water mark.
                if (suppressProgressOnNextChange) {
                    suppressProgressOnNextChange = false;
                } else {
                    if (lastSeen > highestPageViewed) {
                        highestPageViewed = lastSeen;
                    }
                    scheduleAutoSave();
                }
                updateReadingProgress(currentIndex);

                // Reset zoom when changing slides, then fit the new page. If its
                // image is not in yet, loadComicPage() fits it when it lands.
                // Not before the image is in: Swiper's zoom.out()/in() cache the
                // slide they were first called on, and a call made while it
                // has no image leaves zoom dead until the next slide change.
                if (this.zoom && activePagedImage(this)) {
                    this.zoom.out();
                }
                fitBaseScale = 1;
                applyReaderFit(pendingFitAlign);
                pendingFitAlign = 'top';

                // Check if reached last page - show next issue overlay if available
                if (lastSeen === pageCount - 1) {
                    checkAndShowNextIssueOverlay();
                } else {
                    // Hide overlay if navigating away from last page
                    hideNextIssueOverlay();
                }

                // Load current page
                loadComicPage(currentIndex);

                // Preload next 2 pages
                if (currentIndex + 1 < pageCount) {
                    loadComicPage(currentIndex + 1);
                }
                if (currentIndex + 2 < pageCount) {
                    loadComicPage(currentIndex + 2);
                }

                // Preload previous page for backward navigation
                if (currentIndex - 1 >= 0) {
                    loadComicPage(currentIndex - 1);
                }

                // Clean up pages that are far away to save memory
                unloadDistantPages(currentIndex, pageCount);

                // Apply cached edge color for this page
                const cachedColor = pageEdgeColors.get(currentIndex);
                if (cachedColor) {
                    applyReaderBackgroundColor(cachedColor.r, cachedColor.g, cachedColor.b);
                }
            },
            // Single tap/click: toggle chrome (with delay to avoid conflict with double-tap).
            // Not gated on device: a mouse click hides it on desktop too, and the
            // gate is what left a rotated tablet unable to hide it.
            tap: function (swiper, event) {
                // Don't toggle chrome when zoomed in (user is panning). Being
                // fitted to the width is not "zoomed in".
                if (readerZoomedBeyondFit()) return;
                // Don't toggle chrome when tapping navigation buttons
                if (event && event.target && event.target.closest('.swiper-button-next, .swiper-button-prev')) return;
                // Side zones turn the page straight away.
                const zone = readerTapEventZone(swiper, event);
                if (zone === 'forward') { readerAdvance(); return; }
                if (zone === 'back') { readerRetreat(); return; }
                // Start a 300ms timer; if a double-tap comes, it will cancel this.
                // Swiper emits `tap` for BOTH taps of a double-tap, so drop the
                // first tap's timer here; otherwise doubleTap could only cancel
                // the second and the toolbars flipped on every double-tap zoom.
                if (chromeToggleTimeout) clearTimeout(chromeToggleTimeout);
                chromeToggleTimeout = setTimeout(function () {
                    chromeToggleTimeout = null;
                    toggleReaderChrome();
                }, 300);
            },
            // Double-tap to reset zoom (cancel any pending chrome toggle)
            doubleTap: function (swiper, event) {
                if (readerTapEventZone(swiper, event) !== 'middle') return;
                if (chromeToggleTimeout) {
                    clearTimeout(chromeToggleTimeout);
                    chromeToggleTimeout = null;
                }
                if (readerZoomedBeyondFit()) {
                    resetPagedZoomToFit('top');
                } else {
                    stepZoom('in');
                }
            },
            init: function () {
                const initialPage = this.activeIndex;
                pageInfoEl.textContent = `Page ${initialPage + 1} of ${pageCount}`;
                // max(): a mode switch rebuilds mid-comic, and must not lower
                // the evidence of how far the user has actually read.
                if (!rebuildingReaderView) {
                    highestPageViewed = Math.max(highestPageViewed, initialPage);
                }
                updateReadingProgress(initialPage);

                // Load initial page and adjacent pages
                loadComicPage(initialPage);
                if (initialPage + 1 < pageCount) loadComicPage(initialPage + 1);
                if (initialPage + 2 < pageCount) loadComicPage(initialPage + 2);
                if (initialPage - 1 >= 0) loadComicPage(initialPage - 1);
            }
        }
    });

    // Initialize page selector dropdown
    initializePageSelector(pageCount, startPage);

    // Initialize zoom controls
    initializeZoomControls();

    // Initialize custom mousewheel handler for zoom-aware navigation
    initializeMousewheelHandler();
}

/**
 * Initialize page selector dropdown
 * @param {number} pageCount - Total number of pages
 * @param {number} startPage - Initial page (0-indexed)
 */
function initializePageSelector(pageCount, startPage) {
    const pageSelector = document.getElementById('pageSelector');
    if (!pageSelector) return;

    // Clear existing options
    pageSelector.innerHTML = '';

    // Populate dropdown with page options
    for (let i = 0; i < pageCount; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = `Page ${i + 1} of ${pageCount}`;
        if (i === startPage) {
            option.selected = true;
        }
        pageSelector.appendChild(option);
    }

    // Add change event listener
    // `onchange`, not addEventListener: this runs on every (re)build, and
    // listeners would pile up.
    pageSelector.onchange = function() {
        const selectedPage = parseInt(this.value, 10);
        if (readerHasView() && !isNaN(selectedPage)) {
            // Jumping is navigation, not reading -- don't let it count as
            // progress, or a peek at the last page marks the issue finished.
            readerSlideTo(selectedPage);
        }
    };
}

/**
 * Step the zoom level up or down by one increment
 * @param {'in'|'out'} direction - Zoom direction
 */
function stepZoom(direction) {
    if (scrollState) {
        stepScrollWidth(direction);
        return;
    }
    if (!comicReaderSwiper || !comicReaderSwiper.zoom) return;
    const current = comicReaderSwiper.zoom.scale;
    const steps = pagedZoomSteps();
    // Zooming in from the fitted view keeps showing the top of the page rather
    // than drifting to wherever Swiper's centre-zoom leaves the offset.
    const wasAtFit = fitBaseScale > 1.02 && !readerZoomedBeyondFit() && current > 1.01;

    if (direction === 'in') {
        // Find the next step above the current scale
        for (let i = 0; i < steps.length; i++) {
            if (steps[i] > current + 0.01) {
                comicReaderSwiper.zoom.in(steps[i]);
                // Landing back on the fitted scale should show the top of the
                // page, like opening it does.
                if (wasAtFit || steps[i] === fitBaseScale) alignFitView('top');
                // Zoom always lands on the centre of the page; tell the user how
                // to get to the rest of it.
                maybeShowPanHint();
                return;
            }
        }
    } else {
        // Find the next step below the current scale
        for (let i = steps.length - 1; i >= 0; i--) {
            if (steps[i] < current - 0.01) {
                if (steps[i] <= 1) {
                    comicReaderSwiper.zoom.out();
                } else {
                    comicReaderSwiper.zoom.in(steps[i]);
                    if (steps[i] === fitBaseScale) alignFitView('top');
                }
                return;
            }
        }
        comicReaderSwiper.zoom.out();
    }
}

/**
 * The scales the zoom buttons step through in paged mode. 1 is the whole page;
 * when the page is fitted to the width the fitted scale and two steps above it
 * follow, otherwise the classic 1 -> 3 ladder.
 */
function pagedZoomSteps() {
    if (fitBaseScale <= 1.02) return ZOOM_STEPS;
    const steps = [1, fitBaseScale];
    FIT_STEP_MULTIPLIERS.forEach(m => steps.push(fitBaseScale * m));
    return steps;
}

/** The active slide's loaded <img>, or null while it is still a spinner. */
function activePagedImage(swiper) {
    const slide = swiper && swiper.slides[swiper.activeIndex];
    return slide ? slide.querySelector('.swiper-zoom-container img') : null;
}

/** Is the page zoomed in past what "fitted" means for it? */
function readerZoomedBeyondFit() {
    if (!comicReaderSwiper || !comicReaderSwiper.zoom) return false;
    const scale = comicReaderSwiper.zoom.scale || 1;
    return scale > Math.max(1, fitBaseScale) * 1.02;
}

/**
 * Fit the active page to the window's width (readerFit === 'width').
 *
 * Needs the image to be in the DOM; loadComicPage() calls this when the active
 * page lands, and slideChange calls it for a page that is already loaded.
 *
 * @param {'top'|'bottom'} align - Which end of the page to show.
 */
function applyReaderFit(align) {
    const swiper = comicReaderSwiper;
    if (!swiper || !swiper.zoom) return;
    fitBaseScale = 1;
    swiper.params.zoom.maxRatio = ZOOM_STEPS[ZOOM_STEPS.length - 1];
    if (readerFit !== 'width') return;
    if (readerSpread) return;  // a spread is already wide

    const slide = swiper.slides[swiper.activeIndex];
    const img = activePagedImage(swiper);
    if (!img || !img.offsetWidth) return;

    // Layout sizes ignore the transform, so this holds at any current zoom.
    const scale = slide.clientWidth / img.offsetWidth;
    if (scale <= 1.02) return;  // already as wide as the window allows

    fitBaseScale = scale;
    swiper.params.zoom.maxRatio = scale * FIT_STEP_MULTIPLIERS[FIT_STEP_MULTIPLIERS.length - 1];
    swiper.zoom.in(scale);
    alignFitView(align || 'top');
    maybeShowPanHint();
}

/**
 * Show the top (or bottom) of a fitted page instead of its middle: Swiper
 * zooms about the centre, which for a tall page hides the start of it.
 */
function alignFitView(where) {
    const ctx = getZoomPanContext();
    if (!ctx) return;
    applyZoomPan(ctx, 0, where === 'bottom' ? -ctx.maxY : ctx.maxY);
}

/** Drop any zoom and fit the active page again (fit button, resize, reset). */
function resetPagedZoomToFit(align) {
    if (!comicReaderSwiper || !comicReaderSwiper.zoom) return;
    if (!activePagedImage(comicReaderSwiper)) return;  // see slideChange
    comicReaderSwiper.zoom.out();
    applyReaderFit(align);
}

/**
 * Space in paged mode. A page fitted to the width is taller than the window, so
 * Space reads down it first and only turns the page from the bottom.
 */
function readerAdvance() {
    if (!comicReaderSwiper) return;
    if (!readerZoomedBeyondFit()) {
        const ctx = getZoomPanContext();
        if (ctx && ctx.y > -ctx.maxY + 1) {
            applyZoomPan(ctx, ctx.x, ctx.y - ctx.slide.offsetHeight * 0.85);
            return;
        }
    }
    comicReaderSwiper.slideNext();
}

/** Mirror of readerAdvance: read back up a fitted page first, then turn back. */
function readerRetreat() {
    if (!comicReaderSwiper || comicReaderSwiper.isBeginning) return;
    if (!readerZoomedBeyondFit()) {
        const ctx = getZoomPanContext();
        if (ctx && ctx.y < ctx.maxY - 1) {
            applyZoomPan(ctx, ctx.x, ctx.y + ctx.slide.offsetHeight * 0.85);
            return;
        }
    }
    pendingFitAlign = 'bottom';  // land at the bottom of the earlier page
    comicReaderSwiper.slidePrev();
}

/** Tap zone of a Swiper tap/doubleTap event; 'middle' when it can't be told. */
function readerTapEventZone(swiper, event) {
    const pt = event && ((event.changedTouches && event.changedTouches[0]) || event);
    if (!pt || typeof pt.clientX !== 'number' || !swiper || !swiper.el) return 'middle';
    return readerTapZone(swiper.el, pt.clientX);
}

/**
 * Which ends is the view resting against? A page fitted to the width can be
 * panned, so "top" means its top edge is showing; zoomed beyond fit pans freely
 * and never counts as an edge. In scroll mode the edges are the strip's own.
 */
function readerEdges() {
    const index = getReaderCurrentIndex();
    let top = true, bottom = true, first = index <= 0, last = index >= currentComicPageCount - 1;
    if (scrollState) {
        const sc = scrollState.scroller;
        top = sc.scrollTop <= 1;
        bottom = sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 1;
        first = top;
        last = bottom;
    } else if (comicReaderSwiper) {
        last = comicReaderSwiper.isEnd;
        const ctx = getZoomPanContext();
        if (readerZoomedBeyondFit()) {
            top = bottom = false;
        } else if (ctx) {
            top = ctx.y >= ctx.maxY - 1;
            bottom = ctx.y <= -ctx.maxY + 1;
        }
    }
    return { top, bottom, first, last };
}

/** Open the sibling `offset` issues away (1 next, -1 previous). False if none. */
function goToIssue(offset) {
    const target = currentComicSiblings[currentComicIndex + offset];
    if (currentComicIndex < 0 || !target) return false;
    if (offset > 0) {
        continueToNextIssue();  // also marks this one finished
        return true;
    }
    closeComicReader();  // saves where we were; siblings are rebuilt on open
    openComicReader(target.path);
    return true;
}

/**
 * A pull past an end of the comic.
 * @param {'forward'|'back'} dir
 * @param {boolean} allowClose  A downward pull away from the first page closes.
 * @param {Object} [edges]      Edges as they were when the pull began.
 */
function readerOverscroll(dir, allowClose, edges = readerEdges()) {
    if (!readerHasView() || !currentComicPath) return;
    if (dir === 'forward') {
        if (edges.bottom && edges.last) goToIssue(1);
        return;
    }
    if (!edges.top) return;
    if (edges.first && goToIssue(-1)) return;
    if (allowClose) closeComicReader();
}

/** Wheel / trackpad version: needs a sustained push, after the view has settled. */
function readerWheelOverscroll(dir, px) {
    const now = Date.now();
    if (now - lastPageChangeAt < OVERSCROLL_SETTLE_MS) return;
    const w = overscrollWheel;
    if (now - w.last > 300 || w.dir !== dir) w.sum = 0;
    w.last = now;
    w.dir = dir;
    w.sum += Math.abs(px);
    if (w.sum >= OVERSCROLL_WHEEL_PX) {
        w.sum = 0;
        readerOverscroll(dir, false);
    }
}

/** Vertical swipes on the reader: next/previous issue, or swipe down to close. */
function attachReaderSwipes(modal) {
    modal.addEventListener('touchstart', e => {
        const resume = document.getElementById('resumeReadingOverlay');
        const blocked = e.touches.length !== 1 || !readerHasView() ||
            (resume && resume.style.display === 'flex') ||
            e.target.closest('button, select, a, input, .comic-reader-header, .comic-reader-footer');
        overscrollTouch = blocked ? null : { x: e.touches[0].clientX, y: e.touches[0].clientY, edges: readerEdges() };
    }, { passive: true });
    modal.addEventListener('touchmove', e => {
        if (e.touches.length > 1) overscrollTouch = null;  // a pinch
    }, { passive: true });
    modal.addEventListener('touchend', e => {
        const t = overscrollTouch;
        overscrollTouch = null;
        if (!t || !e.changedTouches.length) return;
        const dx = e.changedTouches[0].clientX - t.x;
        const dy = e.changedTouches[0].clientY - t.y;
        if (Math.abs(dy) < OVERSCROLL_SWIPE_PX || Math.abs(dy) < Math.abs(dx) * 1.5) return;
        readerOverscroll(dy < 0 ? 'forward' : 'back', true, t.edges);
    }, { passive: true });
    // Scroll mode scrolls natively, so only watch the wheel for a push past an end.
    modal.addEventListener('wheel', e => {
        if (!scrollState) return;
        const edges = readerEdges();
        if (e.deltaY > 0 && edges.bottom) readerWheelOverscroll('forward', e.deltaY);
        else if (e.deltaY < 0 && edges.top) readerWheelOverscroll('back', e.deltaY);
        else lastPageChangeAt = Date.now();  // still moving: the edge hasn't settled
    }, { passive: true });
}

/**
 * Initialize zoom controls (buttons and keyboard)
 */
function initializeZoomControls() {
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');

    // Zoom in button - step up one increment
    if (zoomInBtn) {
        // onclick, not addEventListener: initializeZoomControls runs on every
        // (re)build, and stacked listeners made one click zoom several steps.
        zoomInBtn.onclick = function() {
            stepZoom('in');
        };
    }

    // Zoom out button - step down one increment
    if (zoomOutBtn) {
        zoomOutBtn.onclick = function() {
            stepZoom('out');
        };
    }

    // Remove existing keyboard listener if present
    if (zoomKeyboardHandler) {
        document.removeEventListener('keydown', zoomKeyboardHandler);
    }

    // Add keyboard event listener for arrow up/down to zoom
    zoomKeyboardHandler = handleZoomKeyboard;
    document.addEventListener('keydown', zoomKeyboardHandler);
}

/**
 * Resolve everything needed to pan the current page, or null if there is
 * nothing to pan (reader closed, page not loaded yet, or not zoomed in).
 *
 * Swiper splits the zoom across two elements: `translate3d()` on the
 * `.swiper-zoom-container`, `scale()` on the `<img>` inside it. We therefore
 * read and write ONLY the container's translate -- appending a `scale()` of our
 * own there multiplies against the image's and blows the page up on the first
 * pan. Swiper re-reads that translate off the DOM on touchstart, so panning by
 * keyboard and then by drag picks up exactly where the keyboard left off.
 *
 * @returns {?{zoomContainer: HTMLElement, slide: HTMLElement, x: number,
 *            y: number, maxX: number, maxY: number}}
 */
function getZoomPanContext() {
    if (!comicReaderSwiper || !comicReaderSwiper.zoom) return null;

    const scale = comicReaderSwiper.zoom.scale || 1;
    if (scale <= 1) return null;

    const slide = comicReaderSwiper.slides[comicReaderSwiper.activeIndex];
    if (!slide) return null;

    const zoomContainer = slide.querySelector('.swiper-zoom-container');
    const img = zoomContainer ? zoomContainer.querySelector('img') : null;
    if (!zoomContainer || !img) return null;

    // Same bounds Swiper uses for drag panning: half the overhang of the scaled
    // image past the slide on each axis. offsetWidth/Height are layout sizes and
    // so are unaffected by the transform.
    const maxX = Math.max(0, (img.offsetWidth * scale - slide.offsetWidth) / 2);
    const maxY = Math.max(0, (img.offsetHeight * scale - slide.offsetHeight) / 2);

    let x = 0, y = 0;
    const match = (zoomContainer.style.transform || '')
        .match(/translate3d\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px/);
    if (match) {
        x = parseFloat(match[1]) || 0;
        y = parseFloat(match[2]) || 0;
    }

    return { zoomContainer, slide, x, y, maxX, maxY };
}

/**
 * Write a clamped pan offset onto the zoom container.
 * @param {Object} ctx - Context from getZoomPanContext()
 * @param {number} x - Desired horizontal offset in px
 * @param {number} y - Desired vertical offset in px
 */
function applyZoomPan(ctx, x, y) {
    const clampedX = Math.max(-ctx.maxX, Math.min(ctx.maxX, x));
    const clampedY = Math.max(-ctx.maxY, Math.min(ctx.maxY, y));

    // Swiper leaves a 300ms transition on the container after a zoom step, which
    // makes a held-down pan key lag well behind the keyboard. Swiper restores
    // the duration itself on its next zoom in/out, so this is safe to clear.
    ctx.zoomContainer.style.transitionDuration = '0ms';
    ctx.zoomContainer.style.transform =
        `translate3d(${clampedX}px, ${clampedY}px, 0px)`;

    // The user has clearly found the controls; stop telling them about them.
    if (panHintTimeout) hidePanHint();
}

/**
 * Pan the zoomed page by a pixel delta.
 * @param {number} dx - Horizontal delta applied to the image
 * @param {number} dy - Vertical delta applied to the image
 * @returns {boolean} True if a pan was applied
 */
function panZoomedView(dx, dy) {
    const ctx = getZoomPanContext();
    if (!ctx) return false;
    if (!dx && !dy) return false;
    applyZoomPan(ctx, ctx.x + dx, ctx.y + dy);
    return true;
}

/**
 * Pan by one key press: a fraction of the visible page in the given direction.
 * @param {'up'|'down'|'left'|'right'} direction - Direction the VIEW moves
 * @returns {boolean} True if a pan was applied
 */
function panZoomedViewByKey(direction) {
    const ctx = getZoomPanContext();
    if (!ctx) return false;

    const stepX = ctx.slide.offsetWidth * PAN_STEP_FRACTION;
    const stepY = ctx.slide.offsetHeight * PAN_STEP_FRACTION;

    let dx = 0, dy = 0;
    switch (direction) {
        case 'up':    dy = stepY; break;
        case 'down':  dy = -stepY; break;
        case 'left':  dx = stepX; break;
        case 'right': dx = -stepX; break;
        default: return false;
    }

    applyZoomPan(ctx, ctx.x + dx, ctx.y + dy);
    return true;
}

/**
 * Re-centre the zoom window without changing the zoom level.
 * @returns {boolean} True if the view was re-centred
 */
function recenterZoomedView() {
    const ctx = getZoomPanContext();
    if (!ctx) return false;
    // Centre, except on a page fitted to the width, whose natural resting place
    // is its top.
    const fitted = fitBaseScale > 1.02 && !readerZoomedBeyondFit();
    applyZoomPan(ctx, 0, fitted ? ctx.maxY : 0);
    return true;
}

/**
 * Normalise a wheel delta to pixels. Firefox reports lines (deltaMode 1) and,
 * for page-scroll gestures, pages (deltaMode 2); untranslated, a delta of 3
 * would read as a 3px pan and the wheel would feel dead when zoomed.
 * @param {number} delta - Raw delta from the wheel event
 * @param {number} mode - event.deltaMode
 * @param {number} pageSize - Size of the viewport along this axis
 * @returns {number} Delta in pixels
 */
function normalizeWheelDelta(delta, mode, pageSize) {
    if (mode === 1) return delta * WHEEL_LINE_HEIGHT;
    if (mode === 2) return delta * pageSize;
    return delta;
}

/**
 * Show the "you can pan now" hint, unless the user has seen it enough times.
 * Called when the reader zooms in. Keyboard-only advice, so it is skipped on
 * touch layouts where pinch-and-drag is already the obvious gesture.
 */
function maybeShowPanHint() {
    if (panHintShownThisSession || isMobileOrTablet()) return;

    let seen = 0;
    try {
        seen = parseInt(localStorage.getItem(PAN_HINT_STORAGE_KEY), 10) || 0;
    } catch (e) {
        // Private mode / blocked storage: show the hint, just don't remember it.
    }
    if (seen >= PAN_HINT_MAX_SHOWS) return;

    const hint = ensurePanHintElement();
    if (!hint) return;

    panHintShownThisSession = true;
    try {
        localStorage.setItem(PAN_HINT_STORAGE_KEY, String(seen + 1));
    } catch (e) {
        // Non-fatal, as above.
    }

    hint.classList.add('visible');
    clearTimeout(panHintTimeout);
    panHintTimeout = setTimeout(hidePanHint, PAN_HINT_DURATION_MS);
}

/** Hide the pan hint and cancel its timer. */
function hidePanHint() {
    clearTimeout(panHintTimeout);
    panHintTimeout = null;
    const hint = document.getElementById('readerPanHint');
    if (hint) hint.classList.remove('visible');
}

/**
 * Build the pan hint on first use.
 *
 * Created here rather than in markup because the reader modal is duplicated
 * across four templates (collection, metadata_browser, reading_list_view,
 * source_wall) -- injecting it keeps those four copies from drifting.
 *
 * @returns {?HTMLElement}
 */
function ensurePanHintElement() {
    const existing = document.getElementById('readerPanHint');
    if (existing) return existing;

    const container = document.querySelector('.comic-reader-container');
    if (!container) return null;

    const hint = document.createElement('div');
    hint.id = 'readerPanHint';
    hint.className = 'reader-pan-hint';
    hint.setAttribute('role', 'status');
    hint.innerHTML =
        '<i class="bi bi-arrows-move" aria-hidden="true"></i>' +
        '<span>Pan with <kbd>Shift</kbd>+arrows, <kbd>W</kbd><kbd>A</kbd>' +
        '<kbd>S</kbd><kbd>D</kbd> or the scroll wheel &middot; ' +
        '<kbd>0</kbd> to re-centre</span>';
    container.appendChild(hint);
    return hint;
}

/**
 * Check if an RGB color is perceptually light
 * @param {number} r - Red (0-255)
 * @param {number} g - Green (0-255)
 * @param {number} b - Blue (0-255)
 * @returns {boolean} True if the color is light
 */
function isLightColor(r, g, b) {
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b);
    return luminance > 140;
}

/**
 * Handle keyboard events for zoom (arrow keys)
 * @param {KeyboardEvent} event
 */
function handleZoomKeyboard(event) {
    // Only handle if comic reader is open
    if (scrollState) {
        handleScrollKeyboard(event);
        return;
    }
    if (!comicReaderSwiper) return;
    if (_isFormControlTarget(event.target)) return;

    // Check if user is zoomed in
    const isZoomed = comicReaderSwiper.zoom && comicReaderSwiper.zoom.scale > 1;

    // Pan the zoom window. Arrows need Shift or Ctrl, because unmodified arrows
    // already mean page-turn (left/right) and zoom (up/down); W/A/S/D pan bare.
    // Alt+arrow is browser history and Cmd/Ctrl+letter are browser shortcuts, so
    // neither is claimed here.
    const panDirection = PAN_KEYS[event.key];
    if (panDirection) {
        const isArrow = event.key.indexOf('Arrow') === 0;
        const wantsPan = isArrow
            ? ((event.shiftKey || event.ctrlKey) && !event.altKey && !event.metaKey)
            : !(event.ctrlKey || event.altKey || event.metaKey);

        if (wantsPan) {
            // Swallowed even when not zoomed: a modified arrow must never fall
            // through to a page turn, or an early pan press skips the page.
            event.preventDefault();
            panZoomedViewByKey(panDirection);
            return;
        }
        // A bare letter reaching here carries a browser modifier -- leave it be.
        if (!isArrow) return;
    }

    // Re-centre after panning around, without losing the zoom level.
    if ((event.key === '0' || event.key === 'Home') &&
        !event.ctrlKey && !event.altKey && !event.metaKey && isZoomed) {
        event.preventDefault();
        recenterZoomedView();
        return;
    }

    switch(event.key) {
        case 'ArrowUp':
            // Zoom in with arrow up (stepped)
            event.preventDefault();
            stepZoom('in');
            break;
        case 'ArrowDown':
            // Zoom out with arrow down (stepped)
            event.preventDefault();
            stepZoom('out');
            break;
        case 'ArrowLeft':
            // Always navigate to previous page (zoom resets on slide change)
            event.preventDefault();
            comicReaderSwiper.slidePrev();
            break;
        case 'ArrowRight':
            // Always navigate to next page (zoom resets on slide change)
            event.preventDefault();
            comicReaderSwiper.slideNext();
            break;
    }
}

/**
 * Initialize custom mousewheel handler for zoom-aware navigation
 */
function initializeMousewheelHandler() {
    const swiperEl = document.getElementById('comicReaderSwiper');
    if (!swiperEl) return;

    // Clear any existing timeout
    if (wheelTimeout) {
        clearTimeout(wheelTimeout);
        wheelTimeout = null;
    }

    // Remove existing mousewheel listener if present
    if (mousewheelHandler) {
        swiperEl.removeEventListener('wheel', mousewheelHandler);
    }

    // Create the handler function
    mousewheelHandler = function(event) {
        if (!comicReaderSwiper) return;

        // Check if currently zoomed
        const isZoomed = comicReaderSwiper.zoom && comicReaderSwiper.zoom.scale > 1;

        if (isZoomed) {
            // Swiper's mousewheel module is off (see the config) and its zoom
            // module ignores the wheel entirely, so nothing moves a zoomed page
            // unless we do it here -- the wheel used to be dead while zoomed.
            // Shift+wheel pans horizontally, matching normal page scrolling.
            const slide = comicReaderSwiper.slides[comicReaderSwiper.activeIndex];
            const pageW = slide ? slide.offsetWidth : window.innerWidth;
            const pageH = slide ? slide.offsetHeight : window.innerHeight;
            const deltaY = normalizeWheelDelta(event.deltaY, event.deltaMode, pageH);
            const deltaX = normalizeWheelDelta(event.deltaX, event.deltaMode, pageW);

            const dx = event.shiftKey ? -deltaY : -deltaX;
            const dy = event.shiftKey ? 0 : -deltaY;

            // A page fitted to the width is "zoomed" as far as Swiper cares, so
            // the wheel reads down it. Once it hits the end the NEXT flick turns
            // the page (one page per flick: momentum scrolling sends a stream
            // of events, hence the cooldown).
            const ctx = getZoomPanContext();
            if (ctx && !readerZoomedBeyondFit() && !event.shiftKey && dy) {
                const target = Math.max(-ctx.maxY, Math.min(ctx.maxY, ctx.y + dy));
                if (Math.abs(target - ctx.y) < 0.5) {
                    event.preventDefault();
                    const now = Date.now();
                    if (dy < 0 && comicReaderSwiper.isEnd) {
                        readerWheelOverscroll('forward', dy);
                    } else if (dy > 0 && comicReaderSwiper.isBeginning) {
                        readerWheelOverscroll('back', dy);
                    } else if (now - lastWheelTurnAt >= WHEEL_TURN_COOLDOWN_MS) {
                        lastWheelTurnAt = now;
                        if (dy < 0) {
                            comicReaderSwiper.slideNext();
                        } else {
                            // Going back: land at the bottom of the earlier page.
                            pendingFitAlign = 'bottom';
                            comicReaderSwiper.slidePrev();
                        }
                    }
                    return;
                }
            }

            if (panZoomedView(dx, dy)) {
                event.preventDefault();
            }
            return;
        }

        // When not zoomed, use mousewheel to navigate pages
        event.preventDefault();

        if (event.deltaY > 0 && comicReaderSwiper.isEnd) {
            readerWheelOverscroll('forward', event.deltaY);
            return;
        }
        if (event.deltaY < 0 && comicReaderSwiper.isBeginning) {
            readerWheelOverscroll('back', event.deltaY);
            return;
        }

        // Debounce to prevent too fast navigation
        clearTimeout(wheelTimeout);
        wheelTimeout = setTimeout(() => {
            if (event.deltaY > 0) {
                // Scroll down = next page
                comicReaderSwiper.slideNext();
            } else if (event.deltaY < 0) {
                // Scroll up = previous page
                comicReaderSwiper.slidePrev();
            }
        }, 50);
    };

    // Add the event listener
    swiperEl.addEventListener('wheel', mousewheelHandler, { passive: false });
}

/**
 * Update reading progress bar display
 */
function updateReadingProgress(pageIndex) {
    if (currentComicPageCount === 0) return;
    // Display only: reflects where the user IS, not how far they have read.
    // Completion is decided by hasFinishedCurrentComic() via highestPageViewed.
    // The index is passed in by the swiper callbacks because during the `init`
    // hook the module-level `comicReaderSwiper` is not assigned yet.
    let currentIndex = pageIndex;
    if (currentIndex === undefined) {
        currentIndex = readerHasView() ? getReaderCurrentIndex() : highestPageViewed;
    }
    const progress = ((currentIndex + 1) / currentComicPageCount) * 100;
    const progressBar = document.querySelector('.comic-reader-progress-fill');
    const progressText = document.querySelector('.comic-reader-progress-text');
    if (progressBar) progressBar.style.width = `${progress}%`;
    if (progressText) progressText.textContent = `${Math.round(progress)}%`;
}

/**
 * Extract the average edge color from an image by sampling pixels along all 4 edges
 * @param {HTMLImageElement} img - The loaded image element
 * @returns {{r: number, g: number, b: number}} Average RGB color of edge pixels
 */
function extractEdgeColor(img) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    // Scale down to max 100px on longest side for performance
    const scale = Math.min(100 / img.naturalWidth, 100 / img.naturalHeight, 1);
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(img.naturalHeight * scale));
    canvas.width = w;
    canvas.height = h;
    ctx.drawImage(img, 0, 0, w, h);

    const imageData = ctx.getImageData(0, 0, w, h);
    const data = imageData.data;
    let rSum = 0, gSum = 0, bSum = 0, count = 0;

    function addPixel(x, y) {
        const idx = (y * w + x) * 4;
        rSum += data[idx];
        gSum += data[idx + 1];
        bSum += data[idx + 2];
        count++;
    }

    // Sample all 4 edges
    for (let x = 0; x < w; x++) {
        addPixel(x, 0);         // top edge
        addPixel(x, h - 1);     // bottom edge
    }
    for (let y = 1; y < h - 1; y++) {
        addPixel(0, y);         // left edge
        addPixel(w - 1, y);     // right edge
    }

    if (count === 0) return { r: 0, g: 0, b: 0 };
    return {
        r: Math.round(rSum / count),
        g: Math.round(gSum / count),
        b: Math.round(bSum / count)
    };
}

/**
 * Apply a darkened version of the given color to the reader chrome elements
 * @param {number} r - Red component (0-255)
 * @param {number} g - Green component (0-255)
 * @param {number} b - Blue component (0-255)
 */
function applyReaderBackgroundColor(r, g, b) {
    const overlay = document.querySelector('.comic-reader-overlay');
    const header = document.querySelector('.comic-reader-header');
    const footer = document.querySelector('.comic-reader-footer');
    const slides = document.querySelectorAll('.comic-reader-swiper .swiper-slide');

    if (overlay) overlay.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
    if (header) header.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
    if (footer) footer.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
    slides.forEach(slide => {
        slide.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
    });

    // Toggle button styling based on background brightness
    const light = isLightColor(r, g, b);
    const container = document.querySelector('.comic-reader-container');
    if (container) {
        container.classList.toggle('reader-light-bg', light);
    }
}

/**
 * Reset reader chrome background colors to CSS defaults
 */
function resetReaderBackgroundColor() {
    const overlay = document.querySelector('.comic-reader-overlay');
    const header = document.querySelector('.comic-reader-header');
    const footer = document.querySelector('.comic-reader-footer');
    const slides = document.querySelectorAll('.comic-reader-swiper .swiper-slide');

    if (overlay) overlay.style.backgroundColor = '';
    if (header) header.style.backgroundColor = '';
    if (footer) footer.style.backgroundColor = '';
    slides.forEach(slide => {
        slide.style.backgroundColor = '';
    });

    // Reset button styling to default (light buttons on dark background)
    const container = document.querySelector('.comic-reader-container');
    if (container) {
        container.classList.remove('reader-light-bg');
    }
}

/**
 * Load a specific comic page
 * @param {number} pageNum - Page number to load
 */
function loadComicPage(pageNum) {
    const slide = document.querySelector(`.swiper-slide[data-page-num="${pageNum}"]`);
    if (!slide) return;

    // Check if already loaded or loading
    if (slide.querySelector('img') || slide.dataset.loading === 'true') return;

    // Mark as loading to prevent duplicate requests
    slide.dataset.loading = 'true';

    const imageUrl = readerPageUrl(pageNum);

    // Create image element
    const img = document.createElement('img');
    img.src = imageUrl;
    img.alt = `Page ${pageNum + 1}`;

    // Add decoding hint for faster rendering
    img.decoding = 'async';

    // Add fetchpriority for current/next pages
    const currentIndex = comicReaderSwiper ? comicReaderSwiper.activeIndex : 0;
    if (Math.abs(pageNum - currentIndex) <= 1) {
        img.fetchPriority = 'high';
    } else {
        img.fetchPriority = 'low';
    }

    img.onload = function () {
        // Remove loading spinner and wrap image in zoom container for pinch-to-zoom
        slide.innerHTML = '';

        // Create zoom container (required for Swiper zoom module)
        const zoomContainer = document.createElement('div');
        zoomContainer.className = 'swiper-zoom-container';
        zoomContainer.appendChild(img);

        slide.appendChild(zoomContainer);
        slide.dataset.loading = 'false';

        // Extract and cache edge color for dynamic background
        try {
            const color = extractEdgeColor(img);
            pageEdgeColors.set(pageNum, color);
            // If this is the currently active slide, apply color immediately
            if (comicReaderSwiper && comicReaderSwiper.activeIndex === pageNum) {
                applyReaderBackgroundColor(color.r, color.g, color.b);
            }
        } catch (e) {
            // Silently ignore color extraction failures (e.g., CORS)
        }

        // The page the user is looking at has just appeared: fit it.
        if (comicReaderSwiper && comicReaderSwiper.activeIndex === pageNum) {
            applyReaderFit('top');
        }
    };

    img.onerror = function () {
        slide.innerHTML = `
            <div class="comic-page-loading">
                <p>Failed to load page ${pageNum + 1}</p>
            </div>
        `;
        slide.dataset.loading = 'false';
    };
}

/**
 * Unload pages that are far from the current page to save memory
 * @param {number} currentIndex - Current page index
 * @param {number} pageCount - Total number of pages
 */
function unloadDistantPages(currentIndex, pageCount) {
    const keepDistance = 5; // Keep pages within 5 pages of current

    for (let i = 0; i < pageCount; i++) {
        // Skip pages close to current position
        if (Math.abs(i - currentIndex) <= keepDistance) continue;

        const slide = document.querySelector(`.swiper-slide[data-page-num="${i}"]`);
        if (!slide) continue;

        const img = slide.querySelector('img');
        if (img) {
            // Replace with loading spinner to free memory
            slide.innerHTML = `
                <div class="comic-page-loading">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            `;
            slide.dataset.loading = 'false';
        }
    }
}

// ---------------------------------------------------------------------------
// Scroll (webtoon) mode
// ---------------------------------------------------------------------------
//
// One scrolling column of every page, top to bottom, no gap and no page turn.
// Built beside the Swiper (which is hidden, never initialised) rather than
// inside it: Swiper is a carousel, and everything that makes a strip work --
// native scrolling, lazy loading by IntersectionObserver, a reading line that
// decides the "current" page -- fights it.
//
// The moving parts, all in `scrollState`:
//   pages[]     one box per page, always present, so the scrollbar and the
//               page numbers are right before a single image has loaded.
//               An unloaded box keeps the height it last had (aspect-ratio).
//   observer    loads a page's image when it comes within SCROLL_LOAD_MARGIN of
//               the viewport; pages far away are released again so a 100-page
//               comic never holds 100 decoded images.
//   index       the page under the reading line. It drives the page counter,
//               the dropdown, the progress bar, the autosave and
//               highestPageViewed exactly as a slide change does in paged mode.
//   programmatic  true while WE moved the scroll (resume, page dropdown, mode
//               switch). Like suppressProgressOnNextChange in paged mode, that
//               is navigation and not evidence of reading.

/** Tear the scroll strip down and give the screen back to the Swiper. */
function teardownScrollReader() {
    const swiperEl = document.getElementById('comicReaderSwiper');
    if (swiperEl) swiperEl.style.display = '';
    if (!scrollState) return;

    const s = scrollState;
    scrollState = null;
    if (s.observer) s.observer.disconnect();
    clearTimeout(s.programmaticTimer);
    clearTimeout(s.unloadTimer);
    clearTimeout(s.tapTimer);
    if (s.scroller) {
        s.scroller.removeEventListener('scroll', s.onScroll);
        s.scroller.removeEventListener('click', s.onClick);
        s.scroller.removeEventListener('touchstart', s.onTouchStart);
        s.scroller.removeEventListener('touchmove', s.onTouchMove);
        s.scroller.removeEventListener('touchend', s.onTouchEnd);
        s.scroller.removeEventListener('touchcancel', s.onTouchEnd);
        s.scroller.removeEventListener('pointerdown', s.onPointerDown);
        s.scroller.removeEventListener('pointerup', s.onPointerUp);
        s.scroller.removeEventListener('pointercancel', s.onPointerCancel);
        s.scroller.remove();
    }
}

/** Destroy whichever reader view is up (Swiper and/or the scroll strip). */
function destroyReaderView() {
    if (comicReaderSwiper) {
        comicReaderSwiper.destroy(true, true);
        comicReaderSwiper = null;
    }
    teardownScrollReader();
}

/**
 * Build the scroll strip.
 * @param {number} pageCount - Total number of pages
 * @param {number} startPage - Page to land on (0-indexed)
 */
function initializeScrollReader(pageCount, startPage = 0) {
    const swiperEl = document.getElementById('comicReaderSwiper');
    const container = document.querySelector('.comic-reader-container');
    if (!swiperEl || !container) return;

    swiperEl.style.display = 'none';

    const scroller = document.createElement('div');
    scroller.id = 'comicReaderScroll';
    scroller.className = 'comic-reader-scroll';
    scroller.tabIndex = -1;
    const column = document.createElement('div');
    column.className = 'comic-reader-scroll-column';
    column.style.width = SCROLL_DEFAULT_WIDTH + '%';
    scroller.appendChild(column);

    const pages = [];
    for (let i = 0; i < pageCount; i++) {
        const page = document.createElement('div');
        page.className = 'comic-scroll-page';
        page.dataset.pageNum = i;
        page.innerHTML = scrollSpinnerHtml();
        column.appendChild(page);
        pages.push(page);
    }
    swiperEl.insertAdjacentElement('afterend', scroller);

    const s = {
        scroller, column, pages, pageCount,
        index: 0,
        widthPct: SCROLL_DEFAULT_WIDTH,
        loaded: new Set(),
        programmatic: false,
        programmaticTimer: null,
        unloadTimer: null,
        framePending: false,
        observer: null,
        onScroll: null,
        onClick: null
    };
    scrollState = s;

    s.observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                loadScrollPage(parseInt(entry.target.dataset.pageNum, 10));
            }
        });
    }, { root: scroller, rootMargin: SCROLL_LOAD_MARGIN });
    pages.forEach(p => s.observer.observe(p));

    s.onScroll = () => {
        if (s.framePending) return;
        s.framePending = true;
        requestAnimationFrame(() => {
            s.framePending = false;
            if (scrollState === s) syncScrollIndex();
        });
        clearTimeout(s.unloadTimer);
        s.unloadTimer = setTimeout(() => {
            if (scrollState === s) unloadDistantScrollPages();
        }, 250);
    };
    scroller.addEventListener('scroll', s.onScroll, { passive: true });

    // A mouse click on the page hides/shows the chrome, as a tap does when
    // paged. Not after a text selection or a drag. Touch is handled by
    // attachScrollTap below: iOS WebKit never sends `click` for a tap on a
    // plain element, so on an iPhone this listener alone did nothing.
    s.onClick = () => {
        if (s.lastPointerType && s.lastPointerType !== 'mouse') return;
        if (s.suppressClickUntil && Date.now() < s.suppressClickUntil) return;
        const sel = window.getSelection && window.getSelection();
        if (sel && String(sel).length) return;
        toggleReaderChrome();
    };
    scroller.addEventListener('click', s.onClick);
    attachScrollPinch(s);
    attachScrollTap(s);

    // Land on the start page. Navigation, not reading.
    s.index = Math.max(0, Math.min(startPage, pageCount - 1));
    applyScrollIndexUi(s.index);
    if (!rebuildingReaderView) {
        highestPageViewed = Math.max(highestPageViewed, s.index);
    }
    if (s.index > 0) scrollToReaderPage(s.index);
}

function scrollSpinnerHtml() {
    return `
        <div class="comic-page-loading">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    `;
}

/**
 * Run a layout change without the reader losing its place. Anything that
 * resizes a box above the reading line (an image arriving, the column width)
 * would otherwise shove the page the user is on up or down the screen. The
 * browser's own scroll anchoring is switched off in CSS: Safari lacks it, and
 * two mechanisms adjusting at once overshoot.
 */
function withScrollAnchor(s, change) {
    const anchor = s.pages[s.index];
    const before = anchor ? anchor.offsetTop - s.scroller.scrollTop : 0;
    change();
    if (anchor) s.scroller.scrollTop = anchor.offsetTop - before;
}

/** Fetch one page's image into its box. */
function loadScrollPage(pageNum) {
    const s = scrollState;
    if (!s) return;
    const page = s.pages[pageNum];
    if (!page || s.loaded.has(pageNum) || page.dataset.loading === 'true') return;
    page.dataset.loading = 'true';

    const img = document.createElement('img');
    img.alt = `Page ${pageNum + 1}`;
    img.decoding = 'async';
    img.draggable = false;
    img.onload = function () {
        page.dataset.loading = 'false';
        if (scrollState !== s) return;  // the strip was torn down meanwhile
        withScrollAnchor(s, () => {
            page.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
            page.innerHTML = '';
            page.appendChild(img);
            // Until measured, boxes use the first real page's shape: a strip of
            // same-sized pages then barely moves as the images arrive.
            if (!s.column.style.getPropertyValue('--scroll-page-ratio')) {
                s.column.style.setProperty(
                    '--scroll-page-ratio', `${img.naturalWidth} / ${img.naturalHeight}`);
            }
        });
        s.loaded.add(pageNum);

        try {
            const color = extractEdgeColor(img);
            pageEdgeColors.set(pageNum, color);
            if (s.index === pageNum) applyReaderBackgroundColor(color.r, color.g, color.b);
        } catch (e) {
            // Ignore colour extraction failures, as paged mode does.
        }
    };
    img.onerror = function () {
        page.dataset.loading = 'false';
        if (scrollState !== s) return;
        page.innerHTML = `
            <div class="comic-page-loading">
                <p>Failed to load page ${pageNum + 1}</p>
            </div>
        `;
    };
    img.src = readerPageUrl(pageNum);
}

/** Release the images of pages far from the viewport. Boxes keep their height. */
function unloadDistantScrollPages() {
    const s = scrollState;
    if (!s) return;
    const limit = s.scroller.clientHeight * SCROLL_UNLOAD_VIEWPORTS;
    const view = s.scroller.getBoundingClientRect();
    Array.from(s.loaded).forEach(pageNum => {
        const page = s.pages[pageNum];
        const rect = page.getBoundingClientRect();
        const distance = rect.bottom < view.top ? view.top - rect.bottom
            : rect.top > view.bottom ? rect.top - view.bottom : 0;
        if (distance <= limit) return;
        // Release the decoded bitmap: drop the src, then the element.
        const img = page.querySelector('img');
        if (img) { img.onload = null; img.removeAttribute('src'); }
        page.innerHTML = scrollSpinnerHtml();
        page.dataset.loading = 'false';
        s.loaded.delete(pageNum);
    });
}

/** The page under the reading line. */
function scrollPageIndexAtLine(s) {
    const sc = s.scroller;
    // The bottom of the strip is the last page, however short or tall it is.
    if (sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2) return s.pageCount - 1;
    const line = sc.scrollTop + sc.clientHeight * SCROLL_READING_LINE;
    let lo = 0, hi = s.pageCount - 1;
    while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (s.pages[mid].offsetTop <= line) lo = mid; else hi = mid - 1;
    }
    return lo;
}

/** Counter, dropdown, progress and background for a page, in scroll mode. */
function applyScrollIndexUi(index) {
    const s = scrollState;
    const total = s ? s.pageCount : currentComicPageCount;
    const pageInfoEl = document.getElementById('comicReaderPageInfo');
    if (pageInfoEl) pageInfoEl.textContent = `Page ${index + 1} of ${total}`;
    const pageSelector = document.getElementById('pageSelector');
    if (pageSelector) pageSelector.value = index;
    updateReadingProgress(index);
    const cached = pageEdgeColors.get(index);
    if (cached) applyReaderBackgroundColor(cached.r, cached.g, cached.b);
}

/** Recompute the current page from the scroll position and react to a change. */
function syncScrollIndex() {
    const s = scrollState;
    if (!s) return;
    const index = scrollPageIndexAtLine(s);
    if (index === s.index) return;
    s.index = index;
    applyScrollIndexUi(index);

    // Same bookkeeping as a paged slideChange. A jump WE made is not reading.
    if (!s.programmatic) {
        if (index > highestPageViewed) highestPageViewed = index;
        scheduleAutoSave();
    }
    if (index === s.pageCount - 1) {
        checkAndShowNextIssueOverlay();
    } else {
        hideNextIssueOverlay();
    }
}

/**
 * Scroll so a page's top is at the top of the strip.
 * Counts as navigation, not reading (see `programmatic` above).
 */
function scrollToReaderPage(index) {
    const s = scrollState;
    if (!s) return;
    const target = Math.max(0, Math.min(index, s.pageCount - 1));
    s.programmatic = true;
    clearTimeout(s.programmaticTimer);
    s.scroller.scrollTop = s.pages[target].offsetTop;
    syncScrollIndex();
    // Page boxes near the target may be re-measured as they load; keep the jump
    // flagged until the scrolling has settled.
    s.programmaticTimer = setTimeout(() => { s.programmatic = false; }, 300);
}

/** Scroll by a fraction of the viewport height (negative = up). */
function scrollReaderBy(fraction) {
    const s = scrollState;
    if (!s) return;
    s.scroller.scrollBy({ top: s.scroller.clientHeight * fraction, behavior: 'auto' });
}

// --- Native page zoom (iOS) ---------------------------------------------------
// Safari on iPhone pinch-zooms the PAGE underneath the reader as well as the
// reader's own zoom, and after zooming back out the layout is left shifted
// sideways (the page behind shows as a white strip). The reader does its own
// zooming (Swiper when paged, the column width when scrolling), so the browser's
// is switched off while the reader is open. `gesturestart` is the one event
// Safari lets a page cancel to stop its own pinch; it is not a touch event, so
// Swiper's pinch is unaffected.
function _cancelNativeGesture(e) { e.preventDefault(); }

function blockNativePageZoom() {
    ['gesturestart', 'gesturechange', 'gestureend'].forEach(type => {
        document.addEventListener(type, _cancelNativeGesture, { passive: false });
    });
}

function allowNativePageZoom() {
    ['gesturestart', 'gesturechange', 'gestureend'].forEach(type => {
        document.removeEventListener(type, _cancelNativeGesture);
    });
    // Whatever drift a gesture left behind must not outlive the reader.
    window.scrollTo(0, 0);
}

// --- Pinch to zoom in scroll mode --------------------------------------------
// The strip had no pinch of its own, so a pinch reached the browser. Here two
// fingers resize the column (the same thing the zoom buttons do, continuously),
// one finger scrolls as before, and the reader keeps its place while it grows.
function attachScrollPinch(s) {
    let startDist = 0;
    let startWidth = s.widthPct;
    let pending = null;
    let raf = 0;

    const dist = t => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);

    const apply = () => {
        raf = 0;
        if (scrollState !== s || pending === null) return;
        const next = pending;
        pending = null;
        s.widthPct = next;
        withScrollAnchor(s, () => { s.column.style.width = next + '%'; });
    };

    s.onTouchStart = e => {
        if (e.touches.length === 2) {
            startDist = dist(e.touches);
            startWidth = s.widthPct;
            s.pinching = true;
        }
    };
    s.onTouchMove = e => {
        if (!s.pinching || e.touches.length !== 2 || !startDist) return;
        e.preventDefault();  // no native scroll or zoom while two fingers are down
        const ratio = dist(e.touches) / startDist;
        pending = Math.max(SCROLL_PINCH_MIN, Math.min(SCROLL_PINCH_MAX, startWidth * ratio));
        if (!raf) raf = requestAnimationFrame(apply);
    };
    s.onTouchEnd = e => {
        if (e.touches.length < 2) {
            // A pinch that ends in a tap-like lift must not toggle the chrome.
            // Only after a real pinch: on every lift it swallowed the second
            // tap of a double-tap.
            if (s.pinching) s.suppressClickUntil = Date.now() + 350;
            s.pinching = false;
            startDist = 0;
        }
    };
    s.scroller.addEventListener('touchstart', s.onTouchStart, { passive: true });
    s.scroller.addEventListener('touchmove', s.onTouchMove, { passive: false });
    s.scroller.addEventListener('touchend', s.onTouchEnd, { passive: true });
    s.scroller.addEventListener('touchcancel', s.onTouchEnd, { passive: true });
}

// --- Tap and double-tap in scroll mode ---------------------------------------
// Detected from pointer events, not `click`: iOS WebKit (Safari, and Chrome on
// iPhone, which must use WebKit) does not deliver `click` for a tap on a plain
// element, so the toolbars could not be opened in scroll mode on an iPhone.
// A tap is one finger, short, and still: a scroll, a fling or a pinch is not.
// One tap toggles the toolbars (after a short wait, so a double-tap can claim
// it); a double-tap zooms the column in, or back to fitted.
const SCROLL_TAP_MAX_MS = 500;
const SCROLL_TAP_MAX_MOVE = 10;       // px, finger travel and scroll travel
const SCROLL_DOUBLE_TAP_MS = 300;
const SCROLL_DOUBLE_TAP_WIDTH = 200;  // column width %, zoomed by a double-tap

function attachScrollTap(s) {
    s.onPointerDown = e => {
        s.lastPointerType = e.pointerType;
        if (e.pointerType === 'mouse') return;
        if (!e.isPrimary) { s.tapStart = null; return; }  // a second finger: a pinch
        s.tapStart = { x: e.clientX, y: e.clientY, t: Date.now(),
                       top: s.scroller.scrollTop, left: s.scroller.scrollLeft };
    };
    s.onPointerUp = e => {
        const st = s.tapStart;
        s.tapStart = null;
        if (!st || e.pointerType === 'mouse' || !e.isPrimary) return;
        if (s.pinching || (s.suppressClickUntil && Date.now() < s.suppressClickUntil)) return;
        if (Date.now() - st.t > SCROLL_TAP_MAX_MS) return;
        if (Math.hypot(e.clientX - st.x, e.clientY - st.y) > SCROLL_TAP_MAX_MOVE) return;
        if (Math.abs(s.scroller.scrollTop - st.top) > SCROLL_TAP_MAX_MOVE ||
            Math.abs(s.scroller.scrollLeft - st.left) > SCROLL_TAP_MAX_MOVE) return;
        handleScrollTap(s, e.clientX, e.clientY);
    };
    s.onPointerCancel = () => { s.tapStart = null; };  // the browser took it as a scroll
    s.scroller.addEventListener('pointerdown', s.onPointerDown, { passive: true });
    s.scroller.addEventListener('pointerup', s.onPointerUp, { passive: true });
    s.scroller.addEventListener('pointercancel', s.onPointerCancel, { passive: true });
}

function handleScrollTap(s, x, y) {
    const zone = readerTapZone(s.scroller, x);
    if (zone !== 'middle') {
        scrollReaderBy(zone === 'back' ? -0.9 : 0.9);
        return;
    }
    const now = Date.now();
    if (s.tapTimer && now - s.lastTapAt < SCROLL_DOUBLE_TAP_MS &&
        Math.hypot(x - s.lastTapX, y - s.lastTapY) < 40) {
        clearTimeout(s.tapTimer);
        s.tapTimer = null;
        toggleScrollZoomAt(s, x);
        return;
    }
    s.lastTapAt = now;
    s.lastTapX = x;
    s.lastTapY = y;
    clearTimeout(s.tapTimer);
    s.tapTimer = setTimeout(() => {
        s.tapTimer = null;
        if (scrollState === s) toggleReaderChrome();
    }, SCROLL_DOUBLE_TAP_MS);
}

/** Double-tap in scroll mode: zoom the column in about the tap, or back to fitted. */
function toggleScrollZoomAt(s, clientX) {
    const next = s.widthPct > SCROLL_DEFAULT_WIDTH ? SCROLL_DEFAULT_WIDTH : SCROLL_DOUBLE_TAP_WIDTH;
    const rect = s.scroller.getBoundingClientRect();
    const offsetX = clientX - rect.left;
    const colWidth = s.column.offsetWidth || 1;
    const fraction = (s.scroller.scrollLeft + offsetX) / colWidth;
    s.widthPct = next;
    withScrollAnchor(s, () => { s.column.style.width = next + '%'; });
    // Keep the tapped point under the finger horizontally.
    s.scroller.scrollLeft = Math.max(0, fraction * s.column.offsetWidth - offsetX);
}

/** Step the column width: the scroll-mode equivalent of the zoom buttons. */
function stepScrollWidth(direction) {
    const s = scrollState;
    if (!s) return;
    const steps = SCROLL_WIDTH_STEPS;
    let next = s.widthPct;
    if (direction === 'in') {
        next = steps.find(w => w > s.widthPct) || steps[steps.length - 1];
    } else {
        for (let i = steps.length - 1; i >= 0; i--) {
            if (steps[i] < s.widthPct) { next = steps[i]; break; }
        }
    }
    if (next === s.widthPct) return;
    s.widthPct = next;
    withScrollAnchor(s, () => { s.column.style.width = next + '%'; });
}

/** Keyboard in scroll mode: arrows scroll, left/right turn pages. */
function handleScrollKeyboard(event) {
    const s = scrollState;
    if (!s || _isFormControlTarget(event.target)) return;
    if (event.ctrlKey || event.altKey || event.metaKey) return;

    let handled = true;
    switch (event.key) {
        case 'ArrowDown': case 's': case 'S':
            scrollReaderBy(0.15); break;
        case 'ArrowUp': case 'w': case 'W':
            scrollReaderBy(-0.15); break;
        case 'PageDown':
            scrollReaderBy(0.9); break;
        case 'PageUp':
            scrollReaderBy(-0.9); break;
        case 'ArrowRight':
            scrollToReaderPage(s.index + 1); break;
        case 'ArrowLeft':
            scrollToReaderPage(s.index - 1); break;
        case 'd': case 'D':
            s.scroller.scrollBy({ left: s.scroller.clientWidth * 0.2 }); break;
        case 'a': case 'A':
            s.scroller.scrollBy({ left: -s.scroller.clientWidth * 0.2 }); break;
        case 'Home':
            scrollToReaderPage(0); break;
        case 'End':
            s.programmatic = true;
            clearTimeout(s.programmaticTimer);
            s.scroller.scrollTop = s.scroller.scrollHeight;
            syncScrollIndex();
            s.programmaticTimer = setTimeout(() => { s.programmatic = false; }, 300);
            break;
        default:
            handled = false;
    }
    if (handled) event.preventDefault();
}

/**
 * Close the comic reader
 */
function closeComicReader() {
    // Cancel the throttled autosave FIRST. A pending timer -- or the
    // slideChange that swiper.destroy() fires below -- would otherwise write a
    // position back after we just deleted it, resurrecting a dead bookmark.
    cancelPendingAutoSave();

    if (currentComicPath && currentComicPageCount > 0) {
        if (hasFinishedCurrentComic()) {
            // Finished: record the read and drop the bookmark.
            markCurrentComicFinished();
        } else {
            // Stopped mid-read. Always persist: the server clears the row when
            // page_number <= 1, so "closed on page 1" correctly means "no
            // bookmark" instead of silently leaving a stale one behind.
            persistReadingPosition();
        }
    }

    // Reset dynamic background colors before hiding
    resetReaderBackgroundColor();
    pageEdgeColors = new Map();
    hidePanHint();

    const modal = document.getElementById('comicReaderModal');
    modal.style.display = 'none';
    document.body.style.overflow = ''; // Restore scrolling
    allowNativePageZoom();

    // Reset immersive reader chrome state
    const container = document.querySelector('.comic-reader-container');
    if (container) {
        container.classList.remove('reader-chrome-hidden');
    }
    readerChromeHidden = false;
    if (chromeToggleTimeout) {
        clearTimeout(chromeToggleTimeout);
        chromeToggleTimeout = null;
    }

    // Clear state BEFORE destroying the swiper: destroy() fires slideChange,
    // and persistReadingPosition()/scheduleAutoSave() both no-op once
    // currentComicPath is null. Otherwise the teardown itself could re-save a
    // position we just deleted.
    currentComicPath = null;
    currentComicPageCount = 0;
    highestPageViewed = 0;
    currentComicSiblings = [];
    currentComicIndex = -1;
    nextIssueOverlayShown = false;
    savedReadingPosition = null;
    lastPersistedPage = null;

    // Destroy whichever view is up
    destroyReaderView();
    cancelPendingAutoSave();
    fitBaseScale = 1;
    pendingFitAlign = 'top';

    // Hide overlays
    hideNextIssueOverlay();
    hideResumeReadingOverlay();

    // Remove keyboard listeners
    document.removeEventListener('keydown', handleComicReaderKeydown);
    if (zoomKeyboardHandler) {
        document.removeEventListener('keydown', zoomKeyboardHandler);
        zoomKeyboardHandler = null;
    }

    // Remove mousewheel listener
    if (mousewheelHandler) {
        const swiperEl = document.getElementById('comicReaderSwiper');
        if (swiperEl) {
            swiperEl.removeEventListener('wheel', mousewheelHandler);
        }
        mousewheelHandler = null;
    }

    // Clear any pending wheel timeout
    if (wheelTimeout) {
        clearTimeout(wheelTimeout);
        wheelTimeout = null;
    }
}

/**
 * Check if there's a next issue and show the overlay
 */
function checkAndShowNextIssueOverlay() {
    // Check if there's a next comic in the folder
    if (currentComicIndex >= 0 && currentComicIndex + 1 < currentComicSiblings.length) {
        const nextComic = currentComicSiblings[currentComicIndex + 1];
        showNextIssueOverlay(nextComic);
    }
    // If no next issue, do nothing (close normally per user preference)
}

/**
 * Show the next issue overlay with comic info
 * @param {Object} nextComic - The next comic file object {name, path}
 */
function showNextIssueOverlay(nextComic) {
    if (nextIssueOverlayShown) return;  // Already shown

    const overlay = document.getElementById('nextIssueOverlay');
    const thumbnail = document.getElementById('nextIssueThumbnail');
    const nameEl = document.getElementById('nextIssueName');

    if (!overlay) return;

    // Set the next comic name
    nameEl.textContent = nextComic.name;
    nameEl.title = nextComic.name;

    // Set thumbnail URL - use existing thumbnailUrl from allItems if available
    if (nextComic.thumbnailUrl) {
        thumbnail.src = nextComic.thumbnailUrl;
    } else {
        // Fallback to placeholder if no thumbnail available
        thumbnail.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 150"%3E%3Crect fill="%23333" width="100" height="150"/%3E%3Ctext x="50" y="75" text-anchor="middle" fill="%23666" font-size="12"%3ENo Preview%3C/text%3E%3C/svg%3E';
    }
    thumbnail.onerror = function () {
        // Fallback to placeholder on error
        this.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 150"%3E%3Crect fill="%23333" width="100" height="150"/%3E%3Ctext x="50" y="75" text-anchor="middle" fill="%23666" font-size="12"%3ENo Preview%3C/text%3E%3C/svg%3E';
    };

    // Show overlay
    overlay.style.display = 'flex';
    nextIssueOverlayShown = true;
}

/**
 * Hide the next issue overlay
 */
function hideNextIssueOverlay() {
    const overlay = document.getElementById('nextIssueOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
    nextIssueOverlayShown = false;
}

/**
 * Show the resume reading overlay
 * @param {number} pageNumber - The saved page number
 * @param {number} totalPages - Total pages in the comic
 */
function showResumeReadingOverlay(pageNumber, totalPages) {
    const overlay = document.getElementById('resumeReadingOverlay');
    const info = document.getElementById('resumeReadingInfo');

    if (!overlay || !info) return;

    info.textContent = `Continue from page ${pageNumber} of ${totalPages}?`;
    overlay.style.display = 'flex';
}

/**
 * Hide the resume reading overlay
 */
function hideResumeReadingOverlay() {
    const overlay = document.getElementById('resumeReadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

/**
 * Dismiss the resume prompt without answering it (backdrop click / Escape).
 *
 * This is a deferral, not a decision, so the stored bookmark must survive. The
 * user is left on page 1; without the flag, closing from there would persist
 * page 1, which the server reads as "clear my bookmark" -- destroying a
 * bookmark the user never chose to discard.
 */
function dismissResumeOverlay() {
    hideResumeReadingOverlay();
    if (savedReadingPosition) {
        preserveBookmarkOnClose = true;
    }
}

/**
 * Update the bookmark button state
 * @param {boolean} hasSavedPosition - Whether there's a saved position
 */
function updateBookmarkButtonState(hasSavedPosition) {
    const bookmarkBtn = document.getElementById('comicReaderBookmark');
    if (!bookmarkBtn) return;

    const icon = bookmarkBtn.querySelector('i');
    if (icon) {
        if (hasSavedPosition) {
            icon.classList.remove('bi-bookmark');
            icon.classList.add('bi-bookmark-fill');
            bookmarkBtn.title = 'Position Saved';
        } else {
            icon.classList.remove('bi-bookmark-fill');
            icon.classList.add('bi-bookmark');
            bookmarkBtn.title = 'Save Position';
        }
    }
}

/**
 * Save current reading position
 */
function saveReadingPosition() {
    if (!currentComicPath || !readerHasView()) return;

    const currentPage = getReaderCurrentIndex() + 1; // 1-indexed for display
    const payload = _readerPositionPayload();

    fetch('/api/reading-position', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(response => response.json())
        .then(data => {
            if (!data.success) return;
            lastPersistedPage = currentPage;
            // page_number <= 1 clears the bookmark server-side.
            const bookmarked = !data.cleared;
            savedReadingPosition = bookmarked ? currentPage : null;
            updateBookmarkButtonState(bookmarked);
            // Brief visual feedback
            const bookmarkBtn = document.getElementById('comicReaderBookmark');
            if (bookmarkBtn) {
                bookmarkBtn.classList.add('btn-success');
                bookmarkBtn.classList.remove('btn-outline-light');
                setTimeout(() => {
                    bookmarkBtn.classList.remove('btn-success');
                    bookmarkBtn.classList.add('btn-outline-light');
                }, 1000);
            }
        }).catch(err => console.error('Failed to save reading position:', err));
}

/**
 * Continue to the next issue
 */
function continueToNextIssue() {
    if (currentComicIndex < 0 || currentComicIndex + 1 >= currentComicSiblings.length) {
        return;
    }

    const nextComic = currentComicSiblings[currentComicIndex + 1];

    // The user chose to move on, so this issue counts as finished regardless
    // of the page-based heuristic.
    markCurrentComicFinished();

    // Close current comic without triggering the normal close logic
    const modal = document.getElementById('comicReaderModal');
    modal.style.display = 'none';

    destroyReaderView();

    // Reset state
    currentComicPath = null;
    currentComicPageCount = 0;
    highestPageViewed = 0;
    hideNextIssueOverlay();

    // Open the next comic (keeping the siblings list intact)
    openComicReader(nextComic.path);
}

// Setup reader event handlers
document.addEventListener('DOMContentLoaded', () => {
    const closeBtn = document.getElementById('comicReaderClose');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeComicReader);
    }

    const readerModal = document.getElementById('comicReaderModal');
    if (readerModal) attachReaderSwipes(readerModal);

    // Rotating an iPad switches between one page and a spread: rebuild on the
    // page the user is on (navigation, not reading).
    window.matchMedia(SPREAD_QUERY).addEventListener('change', () => {
        if (!comicReaderSwiper || readerSpread === wantsSpread()) return;
        rebuildingReaderView = true;
        try {
            initializeComicReader(currentComicPageCount, comicReaderSwiper.activeIndex);
        } finally {
            rebuildingReaderView = false;
        }
    });

    // Close on overlay click
    const overlay = document.querySelector('.comic-reader-overlay');
    if (overlay) {
        overlay.addEventListener('click', closeComicReader);
    }

    // Close on Escape key. If a decision overlay is up, Escape dismisses that
    // first rather than tearing down the whole reader underneath it.
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !currentComicPath) return;
        const resumeOverlayEl = document.getElementById('resumeReadingOverlay');
        if (resumeOverlayEl && resumeOverlayEl.style.display !== 'none') {
            dismissResumeOverlay();
            return;
        }
        if (nextIssueOverlayShown) {
            hideNextIssueOverlay();
            return;
        }
        closeComicReader();
    });

    // Durability: the reader used to persist ONLY on an explicit modal close,
    // so closing the tab, refreshing, navigating back, or a mobile browser
    // discarding the page lost the position outright. visibilitychange is the
    // only signal mobile Safari reliably fires before discarding a tab, and
    // pagehide covers bfcache navigation and the Back button. beforeunload is
    // deliberately NOT used: it disables bfcache and adds nothing here.
    //
    // These handlers SAVE ONLY. They must never mark-read or delete: a hidden
    // tab is ambiguous (mobile fires it for the OS keyboard and share sheets),
    // and destroying state on an ambiguous signal is the whole bug class this
    // change exists to fix.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            persistReadingPosition({ useBeacon: true });
        }
    });
    window.addEventListener('pagehide', () => {
        persistReadingPosition({ useBeacon: true });
    });

    // A resized window changes what "fits the width" means. Re-fit unless the
    // user has zoomed in on purpose.
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (comicReaderSwiper && !readerZoomedBeyondFit()) {
                resetPagedZoomToFit('top');
            }
        }, 150);
    });

    // Next issue overlay handlers
    const nextIssueContinue = document.getElementById('nextIssueContinue');
    if (nextIssueContinue) {
        nextIssueContinue.addEventListener('click', continueToNextIssue);
    }

    const nextIssueClose = document.getElementById('nextIssueClose');
    if (nextIssueClose) {
        nextIssueClose.addEventListener('click', () => {
            // Reaching this overlay means the comic was finished. The guard
            // inside markCurrentComicFinished() stops closeComicReader() from
            // firing a second mark-read + delete for the same comic.
            markCurrentComicFinished();
            closeComicReader();
        });
    }

    // Close overlay when clicking outside the panel (just dismiss, don't mark as read)
    const nextIssueOverlay = document.getElementById('nextIssueOverlay');
    if (nextIssueOverlay) {
        nextIssueOverlay.addEventListener('click', (e) => {
            if (e.target === nextIssueOverlay) {
                hideNextIssueOverlay();
            }
        });
    }

    // Bookmark button handler
    const bookmarkBtn = document.getElementById('comicReaderBookmark');
    if (bookmarkBtn) {
        bookmarkBtn.addEventListener('click', saveReadingPosition);
    }

    // Resume reading overlay handlers
    const resumeReadingYes = document.getElementById('resumeReadingYes');
    if (resumeReadingYes) {
        resumeReadingYes.addEventListener('click', () => {
            hideResumeReadingOverlay();
            // Jump to the saved page WITHOUT counting it as pages read --
            // otherwise resuming a bookmark near the end instantly looks
            // "finished" and the next close deletes the bookmark.
            if (readerHasView() && savedReadingPosition) {
                readerSlideTo(savedReadingPosition - 1); // 1-indexed -> 0-indexed
            }
        });
    }

    const resumeReadingNo = document.getElementById('resumeReadingNo');
    if (resumeReadingNo) {
        resumeReadingNo.addEventListener('click', () => {
            hideResumeReadingOverlay();
            // Start from the beginning
            readerSlideTo(0);
            savedReadingPosition = null;
            updateBookmarkButtonState(false);
            // Clear the stored bookmark now, at the moment of the decision.
            // Leaving it would make the rejected prompt reappear next time.
            persistReadingPosition();
        });
    }

    // Close resume overlay when clicking outside the panel
    const resumeOverlay = document.getElementById('resumeReadingOverlay');
    if (resumeOverlay) {
        resumeOverlay.addEventListener('click', (e) => {
            if (e.target === resumeOverlay) {
                dismissResumeOverlay();
            }
        });
    }
});
