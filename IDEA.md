# CLU idea backlog

Brainstorm of features, UX/UI improvements and cosmetic ideas. Nothing here is
committed to or started unless marked. ⚡ = small or quick win.

Already built and removed from this list: reader tap zones, iPad two-page
spreads, swipe down to close, next-issue overlay, Netflix-style home shelves
(Continue Reading, New This Week, On The Stack, Recently Added, Favorites),
cover progress marks, creator and character pages, follow-a-creator, smart
collections, gap report, Activity feed, download queue page, bulk Unsubscribe,
Search all failed again, Undo toast, skeleton loaders, pull-to-refresh, larger
touch targets, phone tab bar, onboarding checklist, clearer empty states,
ghost-publisher fix, back-to-top button, Gruvbox and Catppuccin themes,
series page header (banner, owned run, credits), "new issue arrived" badge,
Pull List, Wanted, Reading Lists, Insights and CBZ Information redesigns, one
Downloads tab, reading-list highlight covers, series page links from Library
and creator pages, long-press cover menu, swipe rows, phone bottom sheets, focus
rings, search suggestions, breadcrumb collapse, reader pace line, double-tap
zoom and loupe, settings search, "What's new" card, and the motion set (one
reduce-motion setting, shared cover and reader open, grid stagger, cover
fade-in, tab pill, press feedback, spring toasts, count-up, favourite burst,
queue motion, collapse timing).

The reader still has no right-to-left mode, no brightness control and no
keep-awake.

## Top picks

1. OLED black theme

## Reader

- ⚡ **Right-to-left (manga) mode**: flip swipe and arrow direction, saved per series.
- ⚡ **Brightness and warm-light slider** in the reader toolbar, for reading in bed.
- **Page strip**: a scrubber of small page thumbnails at the bottom for jumping around.
- **Panel-by-panel view** (like Comixology's Guided View), using automatic panel detection.
- ⚡ **Keep the screen awake while reading** (Wake Lock API).
- **Preload the next issue** in the background so it opens instantly.
- **Offline reading**: download an issue to the device through the PWA.

## UX polish

- **Inline rename**: double-click or long-press a series title to edit it in place.

## Motion and animation

Keep every item here behind the reduce-motion setting.

- **Blur-up covers**: a tiny blurred thumbnail sharpens into the full image,
  so grids never show empty boxes while they load.
- **Progress ring fill** on a series card animates when a new issue is read.
- ⚡ **Smooth scroll to a letter** when tapping the A-Z bar, instead of an instant jump.

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
- **Animated page transitions** in the reader (slide or curl).
- **Wrapped upgrades**: more card styles, matching the active theme.

## Small fixes worth doing

- ⚡ `tests/unit/test_series_json_wiring.py::test_series_routes_writers_use_the_fallback`
  fails on `develop` (expects 3 `write_series_json(` calls, finds 2). May be a real
  bug: a series.json writer losing its description fallback.
- ⚡ `tests/unit/test_thumbnail_cache_permissions.py::test_saving_directly_would_have_failed`
  fails when tests run as root; make it skip under root so the suite reads green.
