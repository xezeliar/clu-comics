# Reading list folders, bulk tagging, full series creators, Home "Go to series"

Four independent changes, one branch each (cut from `develop`), built in this order. Targeted tests only.

## Intent
The owner has a very large reading-list collection that tags alone cannot organise; wants fuller series credits; and wants the Reading List "Go to series page" action on Home.

## Goals
1. **Home:** "Go to series page" in the 3-dot menu of dashboard issue cards.
2. **Bulk tagging:** "Tag" button in the Reading Lists select-mode bulk bar; add/remove tags across selected lists.
3. **Nested folders** for reading lists.
4. **Series page** shows all creators, including those from issues not owned.

## Non-goals / anti-goals
- No change to existing tag semantics or the tag filter.
- Folder deletion never deletes lists.
- No new provider-call path that bypasses `GuardedClient` pacing.

## Approaches (picked)
- Folders: **table** (`reading_list_folders(id, parent_id, name)` + nullable `reading_lists.folder_id`) over a path string on each list (no empty folders, costly rename).
- Creators: **fetch from mapped provider on demand, cached** over storing credits at metadata-fetch time (schema change + backfill).

## Design
1. **Home:** add item to the dashboard issue menu in `static/js/collection.js`, calling the existing `/api/series/for-folder?path=<parent folder>` as `openIssueSeriesPage` in `static/js/reading_list.js` does. Reuse, do not duplicate (share one helper if it fits).
2. **Bulk tagging:** new `POST /api/reading-lists/bulk-tags` `{ids, add[], remove[]}` in `routes/reading_lists.py`, reusing the tag normalisation behind `update_reading_list_tags`; modal in `reading_lists.html`/JS; entry in `routes/api_v1_docs.py` if token-protected; route test in `tests/routes/`.
3. **Folders:** migration in `core/database.py` (new table, `folder_id` column, migration guarded like the existing `tags` one). Endpoints: create/rename/move/delete folder, move lists into a folder (also bulk "Move to folder" in select mode). Page shows breadcrumbs, sub-folders, then lists of the current folder; search and tag filters span all folders. Deleting a folder re-parents its children and lists to its parent. Reject moves that create a cycle. Route tests.
4. **Creators:** resolve the series' mapped provider id, fetch credits via the existing provider client (rate-limited), cache them, merge with `core.creators.series_credits` output, marking owned-issue credits. Fail soft: owned-only list plus a note when no mapping or the provider fails. Test with a stubbed provider.

## Left to the builder
Exact UI layout, modal copy, cache location/TTL for provider credits (to be decided after checking what the provider cache already holds and Metron series-level credit cost), bulk-tag UX for tags present on only some selected lists.
