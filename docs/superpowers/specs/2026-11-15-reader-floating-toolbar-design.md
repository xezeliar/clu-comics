# Reader toolbar: Floating (direction B)

Mock: CLU Design Board, entry `#reader-toolbar`, direction B.

## Why

The reader is where CLU gets used most, and its toolbar feels dull and
unpolished. It has stock outline buttons, a green percentage that repeats the
page count, a page dropdown, and three icons that change a setting on every
click. The owner wants it to look good without adding much, and without the
generic AI-generated look. The "Continue Reading?" popup on the last page is
redundant, because scrolling past the end already opens the next issue.

## Goals

- Floating dark pills instead of bars, so the page runs edge to edge.
- The same controls, made clearer: one View panel with labelled choices
  replaces the three cycling buttons, and a scrubber replaces the page dropdown.
- Remove the "Continue Reading?" popup. On the last page, → , Space and a tap
  on the right edge open the next issue, as scrolling past the end already
  does. With no next issue they do nothing.

## Non-goals

- New reader features.
- Changes to tap zones, swiping or scrolling past either end, the Resume
  Reading prompt, two-page spreads, keyboard zoom and pan, or how
  `/api/reader-prefs` saves layout.

## Anti-goals

- Glassy panels (`backdrop-filter`) or gradients on the pills, and anything
  else that reads as generic SaaS.
- A toolbar that loses a control or a keyboard path that works today.

## Approaches considered

- **A · Quiet bars:** keeps today's bars, drawn as a gradient in the page's
  edge colour. The smallest change.
- **B · Floating (picked):** pills with no bars. The most immersive. While the
  pills show, they cover the page's corners and the middle of its bottom edge.
- **C · Filmstrip:** page thumbnails along the bottom. The most work, because
  every page image loads when the strip opens.

The owner picked B.

## Design

**Top row:** a title pill on the left with the series and issue number, and
the issue's ComicInfo `Title` under it (that line is left out when there is no
title). On the right are round buttons for Bookmark, View and Close.

**Bottom capsule:** centred, up to 34rem wide. It holds Zoom out and Zoom in
(only with a mouse, `pointer: fine`), a range scrubber, and a count.

**View panel:** opens under the View button. It holds Layout (Pages | Scroll),
Fit (Width | Height) and Page turn (Slide | Turn | None). Page turn is hidden
in Scroll layout. Esc closes the panel and focus returns to View.

**Hidden state:** a middle tap hides the pills, as today. While they are
hidden they are `inert`, and a 2px progress line in `--clu-select` sits along
the bottom edge.

**Colour:** the pills are always dark (`rgba(18,18,18,.86)` with a 1px
white-8% ring) and their ink is always white. The backdrop and slides keep
taking the page's edge colour. `applyReaderBackgroundColor` stops painting
the header and footer, and the `reader-light-bg` rules for the bars are
removed, because pills don't need them. The only theme colour is
`--clu-select`, on the scrubber fill and the hidden-state line.

**Scrubber:** a native `<input type=range>` with `aria-valuetext`
"Page 12 of 32". A small page preview follows the thumb while you drag. The
reader jumps on release. In a two-page spread it snaps to the spread's first
page.

**Removed:**
- the header progress bar and its percentage (hard-coded `#4CAF50`)
- the `<select>` page dropdown
- the three injected cycling buttons
- the `nextIssueOverlay` markup, CSS and JS

**One markup:** `collection.html`, `source_wall.html`,
`reading_list_view.html` and `metadata_browser.html` each carry their own copy
of the reader. All four switch to
`{% include 'partials/reader_modal.html' %}`.

**Motion:** the pills fade and slide 0.25s, and the View panel scales in over
0.16s. With reduced motion, only the fade is kept.

## Decided by me (please check)

- **Pace estimate:** today's footer line reads "Page 12 of 24 · about 6 min
  left". The count in the capsule keeps it on wide screens ("12 / 32 · 6 min
  left") and shows only "12 / 32" on a phone. Dropping the estimate would
  remove a feature.
- **Pill size:** buttons are 40px, or 44px on touch.
- **The pan hint** (shown on the first zoom) keeps working as today, sitting
  above the capsule.

## Left to the builder

- How the scrubber preview loads its image. It uses the existing page URL and
  should be throttled.
- The test updates for the removed ids (`pageSelector`, the cycling buttons,
  `comic-reader-progress`, `nextIssue*`) in `tests/unit/test_reader_*.py` and
  `tests/routes/test_reading_lists_routes.py`.
