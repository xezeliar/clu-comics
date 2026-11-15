# Floating Reader Toolbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the reader's header and footer bars with floating dark pills, add a View panel and a page scrubber, and remove the "Continue Reading?" popup.

**Architecture:** Each of the four page templates currently pastes its own copy of the reader markup. They all collapse onto `templates/partials/reader_modal.html`, then the partial, `static/css/reader.css` and `static/js/reader.js` are rewritten in place. The ids that JS reaches for stay where they still mean something. Removed controls take their ids, CSS and JS with them.

**Tech Stack:** Flask/Jinja, Bootstrap 5.3 + Bootstrap Icons, Swiper, vanilla JS. Tests are pytest that assert on assets as text, because there is no JS runner (see the docstring in `tests/unit/test_reader_pan_controls.py`).

**Spec:** `docs/superpowers/specs/2026-11-15-reader-floating-toolbar-design.md`

**Mock:** CLU Design Board, entry `#reader-toolbar`, direction B (https://claude.ai/artifact/1Sf9kRe1CHPyLVXghiZuji). Copy pill, capsule and panel measurements from it.

## Global Constraints

- Pills: background `rgba(18,18,18,.86)` with `box-shadow: 0 0 0 1px rgba(255,255,255,.08)`; ink is always white. No `backdrop-filter`, no gradients.
- Round buttons: 40px, or 44px under `@media (pointer: coarse)`. Icons are 20px Bootstrap Icons: `bi-x-lg`, `bi-bookmark` / `bi-bookmark-fill`, `bi-sliders`, `bi-zoom-in`, `bi-zoom-out`.
- The bottom capsule is centred and at most 34rem wide. Zoom buttons render only under `@media (pointer: fine)`.
- The only theme colour is `--clu-select`, used on the scrubber fill and on the 2px hidden-state line.
- Motion: pills fade and slide over 0.25s, and the View panel scales in over 0.16s. Under `prefers-reduced-motion: reduce`, keep the opacity fade only.
- Never `alert()`/`confirm()`. Write control characters as escapes (CLAUDE.md, Frontend).
- Tests: run only the files you touched, with `.venv/bin/python -m pytest <files>` from the repo root, not the full suite (owner's instruction).

## Review Focus

1. **Last page with no next issue** (a single file, or the end of a reading list): →, Space and a right-edge tap must do nothing, with no error and no flicker. *Pinned in Task 2.*
2. **Two-page spread on an iPad in landscape:** the scrubber must jump to the first page of the spread, not land on the right-hand page. *Pinned in Task 4.*
3. **Scroll layout:** the View panel must hide Page turn, and the scrubber must scroll the strip rather than call Swiper. *Pinned in Tasks 3 and 4.*
4. **Light-edged pages** (white scans): the pills stay dark with white ink, and the backdrop still takes the page colour. *Pinned in Task 5.*
5. **Keyboard on the toolbar:** Space or Enter on a focused pill button must press it, not turn the page. Esc with the panel open closes only the panel, not the reader. *Pinned in Tasks 3 and 5.*

---

### Task 1: One reader markup

**Files:**
- Modify: `templates/collection.html`, `templates/source_wall.html`, `templates/reading_list_view.html`, `templates/metadata_browser.html`. In each, replace the whole `<div id="comicReaderModal">…</div>` block with `{% include 'partials/reader_modal.html' %}`.
- Modify: `tests/unit/test_reader_pan_controls.py`, `tests/unit/test_reader_scroll_and_fit.py`. Their `READER_TEMPLATES` loops now read the partial.
- Test: `tests/unit/test_reader_single_markup.py` (new)

**Interfaces:**
- Produces: `partials/reader_modal.html` is the only reader markup. Later tasks edit only that file.

- [ ] **Step 1: Write the failing test.** `test_reader_markup_lives_only_in_partial`, parametrized over the four templates:
  - each template contains `{% include 'partials/reader_modal.html' %}`;
  - `'id="comicReaderModal"' not in html`.
  It also asserts the partial contains `id="comicReaderModal"` exactly once.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/unit/test_reader_single_markup.py -v`. Expected: FAIL in four cases.
- [ ] **Step 3:** Swap each copy for the include. Diff each copy against the partial first. `source_wall` and `metadata_browser` lack the footer progress line, and `reading_list_view` labels its bookmark button "Save Reading Position". Fold nothing back in; the partial's version wins. Point the two existing test files' template loops at `partials/reader_modal.html`, and keep their assertions.
- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/unit/test_reader_single_markup.py tests/unit/test_reader_pan_controls.py tests/unit/test_reader_scroll_and_fit.py tests/unit/test_ux_polish_wiring.py tests/routes/test_reading_lists_routes.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `Reader: one markup, every page includes partials/reader_modal.html`.

### Task 2: Last page goes straight to the next issue

**Files:**
- Modify: `static/js/reader.js`:
  - `readerAdvance` (around line 1186);
  - the paged `ArrowRight` in `handleZoomKeyboard` (around line 1630);
  - the scroll-mode `ArrowRight` (around line 2507) and the scroll-mode Space path (`scrollReaderBy` at the bottom edge).
- Delete from `static/js/reader.js`: `checkAndShowNextIssueOverlay`, `showNextIssueOverlay`, `hideNextIssueOverlay`, `nextIssueOverlayShown`, every call site, and the `nextIssueContinue`/`nextIssueClose` listeners.
- Delete: the `#nextIssueOverlay` block in `templates/partials/reader_modal.html` and the `.next-issue-*` rules in `static/css/reader.css`.
- Test: `tests/unit/test_reader_next_issue.py` (new)

**Interfaces:**
- Consumes: the existing `goToIssue(offset) -> boolean` (reader.js ~1246). It returns false when there is no sibling.

- [ ] **Step 1: Write the failing tests**, using `function_body(js, name)` from `test_reader_scroll_and_fit.py`. Copy the helper or import it.
  - `test_no_continue_reading_overlay`: `nextIssueOverlay` and `next-issue` appear in none of reader.js, reader.css or the partial.
  - `test_advance_on_last_page_opens_next_issue`: the body of `readerAdvance` contains `isEnd` and `goToIssue(1)`.
  - `test_arrow_right_on_last_page_opens_next_issue`: in `handleZoomKeyboard`, the `ArrowRight` case contains `goToIssue(1)`.
  - `test_scroll_mode_forward_at_end_opens_next_issue`: the scroll-mode key handler's `ArrowRight` case references `goToIssue(1)` when `s.index` is the last page.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/unit/test_reader_next_issue.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - On the last page, with nothing left to pan through, each forward path calls `goToIssue(1)` instead of `slideNext()`. That is `comicReaderSwiper.isEnd`, or `s.index === s.pageCount - 1` in scroll mode.
  - A right-edge tap already routes through `readerAdvance`.
  - `goToIssue` already does nothing when there is no next issue, so no extra guard is needed.
- [ ] **Step 4:** Run the new file, plus `tests/unit/test_reader_gestures.py tests/unit/test_reader_gestures_and_polish.py`. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `Reader: last page opens the next issue; drop the Continue Reading popup`.

### Task 3: View panel replaces the three cycling buttons

**Files:**
- Modify: `templates/partials/reader_modal.html`. After the bookmark button, add `<button id="readerViewBtn" aria-expanded="false" aria-controls="readerViewPanel" aria-label="View options">`, and right after it `<div id="readerViewPanel" role="group" aria-label="View options" hidden>`. The panel holds three rows (`data-row="mode|fit|turn"`) of `<button type="button" data-set="mode|fit|turn" data-v="…" aria-pressed>`:
  - Layout: Pages `paged`, Scroll `scroll`;
  - Fit: Width `width`, Height `height`;
  - Page turn: Slide `slide`, Turn `turn`, None `none`.
- Modify: `static/js/reader.js`:
  - delete `ensureReaderViewControls`'s three injected buttons;
  - rewrite `updateReaderViewControls()` to set `aria-pressed` on `[data-set]` buttons from `readerMode`/`readerFit`/`readerTurn`, and `hidden` on `[data-row="turn"]` when `readerMode === 'scroll'`;
  - add `setReaderViewPanel(open: boolean)`;
  - add one delegated click on the panel that calls the existing `setReaderMode`/`setReaderFit`/`setReaderTurn`.
- Modify: `static/css/reader.css`, panel styles from the mock (`.rt-pop`, `.rt-seg`).
- Modify: `tests/unit/test_reader_scroll_and_fit.py`. Its `readerModeBtn`/`readerFitBtn` assertions (lines 79–83) become the panel's `data-set` assertions.
- Test: `tests/unit/test_reader_view_panel.py` (new)

**Interfaces:**
- Produces: `setReaderViewPanel(open: boolean): void`. Opening it focuses the panel's first `[aria-pressed="true"]` button. Esc closes it and focuses `#readerViewBtn`, and the Esc that closes the panel must not also close the reader.

- [ ] **Step 1: Write the failing tests.**
  - `test_panel_markup`: the partial has `id="readerViewPanel"`, and the `data-set` buttons cover exactly `{paged, scroll}`, `{width, height}` and `{slide, turn, none}`.
  - `test_no_cycling_buttons`: `readerModeBtn`, `readerFitBtn` and `readerTurnBtn` are absent from reader.js.
  - `test_turn_row_hidden_in_scroll`: `updateReaderViewControls` references `data-row="turn"` and `readerMode === 'scroll'`.
  - `test_escape_closes_panel_first`: the reader's Escape handling calls `setReaderViewPanel(false)` and returns before the close path.
- [ ] **Step 2:** Run the new file. Expected: FAIL.
- [ ] **Step 3:** Implement as listed under Files.
- [ ] **Step 4:** Run the new file plus `tests/unit/test_reader_scroll_and_fit.py tests/routes/test_reader_prefs_routes.py`. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `Reader: View panel with labelled Layout, Fit and Page turn choices`.

### Task 4: Scrubber replaces the page dropdown

**Files:**
- Modify: `templates/partials/reader_modal.html`. Replace `<select id="pageSelector">` with `<input type="range" id="pageScrubber" min="1" step="1" aria-label="Page">` and a sibling `<div class="reader-scrub-tip" hidden>`.
- Modify: `static/js/reader.js`:
  - replace `initializePageSelector(pageCount, startPage)` with `initializePageScrubber(pageCount: number, startPage: number): void`;
  - replace every `pageSelector.value = …` sync (lines ~836, ~2260) with `syncPageScrubber(index: number): void`, which sets `value`, the `--p` fill percent and `aria-valuetext` "Page N of M".
- Modify: `static/css/reader.css`, the range track and thumb from the mock (`.rt-range`). The empty track is `rgba(255,255,255,.45)`.
- Modify: `tests/unit/test_reader_scroll_and_fit.py:92` and `tests/routes/test_reading_lists_routes.py:857`, from `pageSelector` to `pageScrubber`.
- Test: `tests/unit/test_reader_scrubber.py` (new)

**Interfaces:**
- Produces: `initializePageScrubber`, `syncPageScrubber`. On `input`, the tip shows `readerPageUrl(n)` as an `<img>`, throttled to one update per 120ms, plus the page number. On `change`, navigate:
  - paged: `comicReaderSwiper.slideTo(wantsSpread() ? spreadStart(i) : i)`;
  - scroll: `scrollToReaderPage(i)`;
  - then hide the tip.

- [ ] **Step 1: Write the failing tests.**
  - `test_select_gone`: `pageSelector` is absent from reader.js and the partial.
  - `test_scrubber_has_valuetext`: `syncPageScrubber` sets `aria-valuetext`.
  - `test_scrubber_snaps_to_spread`: `initializePageScrubber` references `spreadStart`.
  - `test_scrubber_handles_scroll_mode`: `initializePageScrubber` references `scrollToReaderPage`.
  - `test_navigates_on_change_not_input`: the navigation call sits in the `change` listener; the `input` listener only updates the tip.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement as listed under Files.
- [ ] **Step 4:** Run the new file plus the two modified test files. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `Reader: page scrubber with preview replaces the page dropdown`.

### Task 5: Floating pills

**Files:**
- Modify: `templates/partials/reader_modal.html`:
  - The header becomes `.reader-top`: a title pill `#comicReaderTitle` with a `#comicReaderSubtitle` line under it, then the bookmark, view and close round buttons. Delete `.comic-reader-progress` and `#comicReaderPageInfo`.
  - The footer becomes a `.reader-capsule` holding the zoom buttons, the scrubber and `#readerProgressLine`, followed by `<div class="reader-hidden-line"><i></i></div>`.
- Modify: `static/css/reader.css`:
  - pill and capsule styles per Global Constraints;
  - `.reader-chrome-hidden` hides the pills (slide plus fade) and shows `.reader-hidden-line`;
  - delete the `reader-light-bg` rules for the header, footer, page info, progress text, outline buttons and page selector;
  - delete `.comic-reader-progress*`. `.reader-pan-hint` sits 1rem above the capsule.
- Modify: `static/js/reader.js`:
  - `applyReaderBackgroundColor` / `resetReaderBackgroundColor` stop touching the header and footer;
  - `updateReadingProgress` drops the % bar;
  - `updateReaderPaceLine` writes `"12 / 32 · about 6 min left"`, in a `.pace` span that CSS hides under `@container`/`(max-width: 480px)`;
  - `toggleReaderChrome` sets `inert` on `.reader-top` and `.reader-capsule` while hidden;
  - every reference to `comicReaderPageInfo` goes, its text now living in the capsule;
  - `#comicReaderSubtitle` is filled from `data.title` (empty means the line is hidden).
- Modify: `app.py` `read_comic_info` (~line 6019). Add `"title": (get_file_index_entry_by_path(comic_path) or {}).get("ci_title") or None` to the JSON.
- Modify: `tests/unit/test_ux_polish_wiring.py:46` if the progress-line id moves. Keep `readerProgressLine` as the id.
- Test: `tests/unit/test_reader_floating_chrome.py` (new)

**Interfaces:**
- Consumes: `syncPageScrubber` from Task 4 and `#readerViewBtn` from Task 3, both already in the markup.

- [ ] **Step 1: Write the failing tests.**
  - `test_bars_not_painted`: the body of `applyReaderBackgroundColor` does not contain `header.style` or `footer.style`.
  - `test_no_percent_bar`: `comic-reader-progress` is absent from the partial, reader.css and reader.js, and `#4CAF50` is absent from reader.css.
  - `test_pills_have_no_glass`: reader.css has no `backdrop-filter` in the `.reader-top` and `.reader-capsule` rules.
  - `test_hidden_chrome_is_inert`: `toggleReaderChrome` sets `inert`.
  - `test_zoom_only_with_mouse`: reader.css contains `pointer: fine` for the zoom buttons.
  - `test_reduced_motion`: reader.css has a `prefers-reduced-motion` block covering `.reader-top`.
  - `test_info_returns_title`: `read_comic_info` in app.py, read as text, contains `ci_title`.
  - `test_keys_ignore_toolbar_buttons`: `handleComicReaderKeydown` returns early when `e.target.closest('button')`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement as listed under Files.
- [ ] **Step 4:** Run the new file plus `tests/unit/test_reader_chrome_toggle.py tests/unit/test_ux_polish_wiring.py tests/unit/test_reader_mobile_smoothness.py tests/unit/test_static_assets_are_text.py`. Expected: PASS.
- [ ] **Step 5: Check in the browser.**
  - Run the app (`python app.py`) and open a comic from the Library.
  - On desktop and at 400px wide, check against the board mock: the pills, the View panel, scrubbing, a light-edged page, the last page with and without a next issue, and hiding and showing the chrome.
- [ ] **Step 6: Commit.** Message: `Reader: floating pill toolbar`.

### Task 6: Docs

- [ ] Update DESIGN.md's `### Reader` paragraph. It currently says "translucent black header and footer bars". It should describe the floating pills, and that the backdrop takes the page's edge colour while the pills stay dark.
- [ ] Commit. Message: `DESIGN.md: reader chrome is floating pills`.
