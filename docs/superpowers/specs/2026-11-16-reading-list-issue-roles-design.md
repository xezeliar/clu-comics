# Reading-list issue roles

## Why
An event reads differently when you know which issues are the main story. The
owner wants each issue in a reading list marked Prologue, Core, Tie-In or
Epilogue, visible only on that list's page.

## Goals
- A role per reading-list entry, shown as a pill under the cover (Core tinted
  with `--clu-select`, the rest outlined).
- A Role filter row (All · Prologue · Core · Tie-In · Epilogue, counts, only
  the roles the list uses) that combines with Show. Up next and the reader's
  next issue follow it.
- Metron imports and syncs fill the role from the item's `issue_type`.
- A role set by hand is the user's: a sync never overwrites it. None counts.

## Non-goals
- Nothing written to the comic file or ComicInfo.xml.
- CBL export leaves roles out (the format has no field).
- ComicVine arcs and CBL files have no role; their issues start unmarked.

## Approaches
Three mocked on the Design Board (`#issue-roles`): 1 badges only, 2 badges +
filter, 3 badges + per-role progress. **Option 2 picked.**

## Design
- `reading_list_entries.role` (`prologue|core|tie_in|epilogue`|NULL) and
  `role_manual` (0/1), added by migration. `normalize_entry_role` drops any
  other value.
- `metron_role()` maps "Prologue", "Core Issue", "Tie-In", "Epilogue".
  `metron_issue_to_entry(issue, loader, issue_type=None)`; the list import and
  the list sync pass the item's `issue_type`, arcs pass nothing.
- `sync_reading_list_entries` writes role on inserts, and on kept entries
  replaces it only when `role_manual = 0`.
- `POST /api/reading-lists/<id>/roles` `{entry_ids: [int], role: str|null}`
  sets `role_manual = 1`. Clerk-gated by the mutation default in `core/auth.py`.
- Clerk: the pill is a Bootstrap dropdown (Prologue, Core, Tie-In, Epilogue,
  None; header "Set by Metron" when the role came from a sync); an unmarked
  issue shows a dashed "Set role". Reader: the pill as text, or nothing.

## Builder's calls
- Select mode for many issues at once is not built: the list page has no
  per-issue select mode yet. The endpoint already takes many ids.
- The sync's sort-order step for added entries used `UPDATE ... ORDER BY ...
  LIMIT`, which needs a SQLite compile option most builds lack, so a sync that
  added an issue failed there. It now updates by the inserted row id.
