# Series shelf and issue carousel sheet

Approved in the CLU Design Board entry "Series carousel" (artifact `1Sf9kRe1CHPyLVXghiZuji`, `#series-carousel`). That entry is the visual source of truth; this file records the build decisions.

## Intent
Let a phone user swipe through the issues of a series like a mobile comic app: big centre cover, neighbours peeking, details and actions below. Entry point is a new dashboard section, "Series", listing every series in the library.

## Behaviour
- **Section `series`** is a normal dashboard section (`DASHBOARD_SECTION_DEFS`, last in `DEFAULT_DASHBOARD_ORDER`), so it is hideable and reorderable. It renders a Swiper shelf on every screen size.
- **Shelf** loads 30 series by last activity (newest `first_indexed_at` of a file in the series folder), 30 more on `reachEnd`. Last tile "View all N" opens the Collection root. Card: cover, name, "owned of total", "N new" sticker (`get_new_arrival_counts`, never call `mark_series_visited`).
- **Tap a series cover:** viewport < 768px opens the sheet; otherwise `loadDirectory(series folder)` (the folder holding issues, `series.json`, `cvinfo`).
- **Continue Reading** is unchanged: tap goes straight to the reader.
- **Sheet:** full-screen dialog, immersive (cover edge colour, white fixed text), opens on in-progress issue, else first unread owned, else first. Native scroll-snap carousel (64% centre, 18% peeks, `scroll-snap-stop: always`), arrows, keyboard left/right, top-bar "3 of 18" and thin progress line. Below: "Issue #N: Title", date, read chip, summary (3-line clamp, More), credits grid (Writer, Penciller, Inker, Colorist, Letterer, Cover artist, Editor; blank roles omitted; "From ComicInfo.xml").
- **Actions:** Start Reading / Continue · p.N / Read again (reader), Mark Unread (disabled unless read), Download, Save (Want to Read toggle). Missing issue: dashed cover, single action Add to Wanted / On Wanted (monitored series are already wanted).
- Esc / back closes, focus returns to the opening cover. Reduced motion: fade, no scaling.

## API (new blueprint file `routes/series_shelf.py`, login required, user path filtering)
- `GET /api/dashboard/series?offset=0&limit=30` -> `{success, total, series:[{id, name, volume, folder, folder_url, cover_url, owned, total, new_count}]}`.
- `GET /api/dashboard/series/<id>/issues` -> `{success, series:{id,name,monitored}, issues:[{number, owned, path?, title?, date?, thumb_url?, read(bool), page?, total_pages?}]}` ordered by issue number; owned from `file_index` (ci_number, ci_title), missing from `wanted_issues`.
- `GET /api/dashboard/issue-info?path=` -> `{success, title, summary, date, credits:{writer,penciller,inker,colorist,letterer,cover_artist,editor}}` read from the CBZ's ComicInfo.xml via `core.comicinfo` (only Editor and Summary are not cached, and one source keeps the sheet consistent). Requires a library path + grant check like `/cbz-metadata`.
- Reuse for actions: `DELETE /api/reading-position`, `GET /api/download`, `/api/favorites/to-read`, `POST /api/series/<id>/wanted-marks`, JS `openReaderForFile`.
- Not under `/api/v1`, so no `ENDPOINTS` entry needed (dashboard-internal routes like `/list-recent-files`).

## Frontend files
`templates/partials/series_sheet.html`, `static/css/series-sheet.css`, `static/js/series-sheet.js` (all via `asset()`), loader `loadSeriesSwiper` + `data-dash-action="open-series"` in `static/js/collection.js`. No `alert/confirm/prompt`; feedback via `CLU.toast`.

## Non-goals
Tablet/desktop sheet, per-page reader changes, a new issue detail page, provider calls, any new setting.

## Open items for the builder
How an `issues_read` row is removed on Mark Unread (grep; add a helper only if none exists). Page-edge colour: sample the cover thumbnail on the client (as `applyReaderBackgroundColor` does) with the series' own cover as fallback.

## Tests
`tests/routes/test_series_shelf.py` (all three routes: ordering, paging, path filtering, new_count, missing issues, issue-info credits, 403/404); update `tests/unit/test_themes.py` and `tests/routes/test_home_progress_tabbar.py` section-list assertions; a static test that the sheet JS/CSS have no native dialogs or raw control chars (existing ratchets cover this).
