# CLU idea backlog

Brainstorm of features, UX/UI improvements and cosmetic ideas. Nothing here is
committed to or started unless marked. ⚡ = small or quick win.

Checked against what already exists: CLU has a PWA, a continuous scroll
(webtoon) mode, OPDS, and Gruvbox and Catppuccin themes. The reader has no
right-to-left mode, no two-page spreads and no brightness control yet.

## Top picks (daily reading on iPhone and iPad)

1. Tap zones in the reader
2. Next-issue auto-advance
3. Swipe down to close the reader
4. OLED black theme
5. Two-page spreads on iPad landscape

## Reader

- ⚡ **Right-to-left (manga) mode**: flip swipe and arrow direction, saved per series.
- **Two-page spreads on iPad landscape**: pages side by side; the cover stays on
  its own and wide double-page art is joined.
- ⚡ **Brightness and warm-light slider** in the reader toolbar, for reading in bed.
- ⚡ **Tap zones**: left/right third turns pages, middle shows the toolbar, with a
  setting to choose the layout.
- **Page strip**: a scrubber of small page thumbnails at the bottom for jumping around.
- ⚡ **Auto-advance**: at the last page, "Next issue →" opens the next issue in the
  series or reading list.
- **Panel-by-panel view** (like Comixology's Guided View), using automatic panel detection.
- ⚡ **Keep the screen awake while reading** (Wake Lock API).
- **Preload the next issue** in the background so it opens instantly.
- ⚡ **Swipe down to close** the reader, like closing a photo on iOS.
- **Offline reading**: download an issue to the device through the PWA.

## Library and browsing

- **Fix ghost publishers** and add a **publisher alias** setting ("DC" → "DC Comics").
  See `docs/todo-ghost-publisher-index.md`.
- ⚡ **"Recently added" shelf** on the home page.
- **Netflix-style home page**: rows for Continue Reading, New This Week, On the
  Stack, Recently Added and Favorites.
- ⚡ **Progress bar on each cover** showing how much has been read.
- **Series page header**: large banner art, description, creators, and an
  "12 of 18 owned" ring.
- ⚡ **Sticky A-Z bar** and a "back to top" button on long grids.
- **Global search shortcut**: `/` or `Ctrl+K` from any page, searching series,
  issues, creators and settings.
- **Smart collections**: saved filters such as "unread Image Comics from 2024".
- **Creator pages**: everything owned by one writer or artist, with a "follow" option.
- **Character pages** built from the ComicInfo character tags.

## Pull List, Wanted and downloads

- ✅ **Bulk Unsubscribe**: done on branch `feat/pulllist-unsubscribe-mobile-reader` (not merged).
- ⚡ **Weekly release calendar view** of what comes out each Wednesday for the pull list.
- **"New issue arrived" badge** on the series card, cleared once opened.
- ⚡ **Search review: "Search all failed again"** bulk button.
- **Download queue page**: progress bars, retry, cancel and drag-to-reorder.
- **Follow a creator**: auto-add new series by followed writers or artists (opt-in).
- **Gap report**: "missing issues 4, 7 and 12" on each series, with one-click search.

## UX polish

- ⚡ **Skeleton loaders** instead of spinners while grids load, so the page doesn't jump.
- ⚡ **Undo toast** after destructive actions ("Unsubscribed 5 series · Undo").
- **Bottom tab bar on phones**: Home, Library, Pull List, Reading, Settings.
- ⚡ **Pull-to-refresh** on mobile list pages.
- ⚡ **Larger touch targets** on mobile; some toolbar buttons are hard to hit.
- **Onboarding checklist**: "Add a library ✓, connect Metron ✓, subscribe to a series…".
- ⚡ **Clearer empty states** with a next step ("No series yet → Search Metron").
- **Keyboard shortcut help** with `?` on every page.
- **Activity feed**: one timeline of downloads, moves, tags and errors, instead of
  digging through logs.

## Themes and cosmetics

New local themes follow the existing pattern in `core/themes.py` (`LOCAL_THEMES`,
a stylesheet under `static/css/themes/`, a 1000×600 preview image).

- **New dark themes**: Nord, Dracula, Tokyo Night, Rosé Pine, Everforest,
  One Dark, Solarized Dark/Light, Kanagawa.
- **Comic-flavoured themes**:
  - **Newsprint / Golden Age**: off-white paper, faint halftone dots, slightly faded ink colours.
  - **Noir**: black and white with one red accent, in the style of Sin City.
  - **Pop Art**: Ben-Day dots, thick black outlines, bold yellow, red and blue;
    cards look like comic panels.
  - **Manga**: white, black and screentone grey with speed-line accents.
- ⚡ **OLED black**: true `#000` for iPhone battery life and the reader.
- ⚡ **Follow the system**: switch light and dark with the device's setting.
- ⚡ **Accent colour picker** on top of any theme.
- **Publisher-coloured badges**: DC blue, Marvel red, Image black.
- ⚡ **Cover hover effects**: a slight lift and shadow, and a 3D tilt on desktop.
- **Animated page transitions** in the reader (slide or curl), with a
  "reduce motion" option.
- **Seasonal touches**: Halloween, Christmas, or a "Free Comic Book Day" banner each May.
- **Wrapped upgrades**: more card styles, matching the active theme.

## Small fixes worth doing

- ⚡ `tests/unit/test_series_json_wiring.py::test_series_routes_writers_use_the_fallback`
  fails on `develop` (expects 3 `write_series_json(` calls, finds 2). May be a real
  bug: a series.json writer losing its description fallback.
- ⚡ `tests/unit/test_thumbnail_cache_permissions.py::test_saving_directly_would_have_failed`
  fails when tests run as root; make it skip under root so the suite reads green.
