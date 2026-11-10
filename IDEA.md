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
ghost-publisher fix, back-to-top button, Gruvbox and Catppuccin themes.

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

## Library and browsing

- **Publisher alias setting** ("DC" → "DC Comics").
- **Series page header**: large banner art, description, creators, and an
  "12 of 18 owned" ring.
- ⚡ **Sticky A-Z bar** on long grids.
- **Global search shortcut**: `/` or `Ctrl+K` from any page, searching series,
  issues, creators and settings.

## Pull List, Wanted and downloads

- **"New issue arrived" badge** on the series card, cleared once opened.

## UX polish

- ⚡ **Long-press a cover** on touch for a context menu: mark read, subscribe,
  open folder, search metadata.
- ⚡ **Swipe actions on list rows** on phones: swipe left to unsubscribe or mark read.
- **Bottom sheets on phones** instead of centred modals for pickers and filters,
  with a drag handle and swipe-to-dismiss.
- ⚡ **Visible focus rings** on every control for keyboard and switch users.
- ⚡ **Empty search results** suggest the nearest matches and offer a "clear
  filters" button.
- **Breadcrumbs** on folder browsing, so a deep path can be climbed in one tap.
- **Reader progress line**: "Page 12 of 24 · about 6 min left" in the footer.
- **Double-tap to zoom** on a page in paged mode, and a press-and-hold loupe.
- **Inline rename**: double-click or long-press a series title to edit it in place.
- ⚡ **Settings search box** that filters the settings page by label.
- **"What's new" card** after an upgrade, dismissible, linking to the changelog.

## Motion and animation

Keep every item here behind `prefers-reduced-motion`, with a single
reduce-motion setting that also covers the reader transitions above.

- **Shared-element open**: the tapped cover grows into the series page header
  instead of the page cutting over.
- **Reader open and close from the cover**: the page scales up from the tapped
  cover and shrinks back to it on close.
- ⚡ **Staggered grid entrance**: cards fade and rise in with a small delay per
  row on first load, once per visit only.
- **Blur-up covers**: a tiny blurred thumbnail sharpens into the full image,
  so grids never show empty boxes while they load.
- ⚡ **Fade-in per cover** as each image finishes loading, rather than popping in.
- **Sliding pill on the phone tab bar**: the active indicator slides and stretches
  between tabs instead of jumping.
- ⚡ **Press feedback**: buttons and cover cards scale to about 97% on touch-down
  and spring back on release.
- **Spring-eased toasts and sheets**: toasts slide in with a slight overshoot and
  can be swiped away.
- **Animated count-up** for the numbers on the Insights page.
- **Progress ring fill** on a series card animates when a new issue is read.
- ⚡ **Smooth scroll to a letter** when tapping the A-Z bar, instead of an instant jump.
- **Collapsible panels** (filters, advanced settings) animate their height
  rather than snapping open.
- **Favourite burst**: a small particle pop when a series is favourited or subscribed.
- **Queue item motion**: items in the download queue slide when reordered, and a
  finished item fades out with a check.

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
