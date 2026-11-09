# TODO: Ghost "DC" publisher on the Library page (stale file_index rows)

Status: **investigated, not fixed.** Logged for review.

## Symptom

The Library page (`/library`, Publisher view) shows two tiles: **DC Comics**
(correct) and **DC** (wrong, 8 issues). There is no `/DC` folder on disk, and
every issue under the "DC" tile fails to open because the `.cbz` does not exist.
Index & Sync Management, "Rebuild File Index Now", does not remove it.

## Why it happens

- The Library page does not read folders. `metadata_browse`
  (`core/database.py`) groups the `file_index` table by `ci_publisher`, the
  `<Publisher>` tag from each comic's ComicInfo.xml. "DC" is just a publisher
  string on 8 rows.
- That query never checks the file exists and never limits rows to the current
  library roots (`allowed_prefixes` is `None` for the owner).
- Cleanup only acts inside current library roots:
  - `POST /api/rebuild-file-index` runs `prune_vanished_index_dirs` (only folders
    under a mounted root) then `sync_file_index_incremental(walked_roots=...)`
    (only deletes rows under the roots it walked). Both are scoped on purpose, so
    a sleeping NAS is not read as "everything deleted".
- So rows whose path is **outside every current library root** are never removed.
- Likely source: `delete_library` / `update_library` (`core/database.py`) only
  change the `libraries` table. They never touch that library's `file_index`
  rows. Also possible: folders moved/renamed outside CLU, or a changed Docker
  volume mapping.

## Confirm first (one command, assumes container `comic-utils`)

```
docker exec comic-utils sqlite3 /config/comic_utils.db "SELECT path FROM file_index WHERE ci_publisher='DC';"
```

If the paths start with a folder that is no longer a library root, the
explanation above is confirmed.

## Proposed fix (new branch from `develop`)

1. **Library page only counts rows under current library roots** (publisher,
   series, year, issue views and the A-Z letters). Reuse the `helpers.library`
   helpers. Hides the ghost tile immediately, deletes nothing.
2. **Remove rows whose file no longer exists, even outside the roots.** Run it in
   small background batches. Skip any root that is unmounted or empty, so a
   sleeping NAS is safe. Also clear `file_metadata_tags` and path references,
   like `prune_vanished_index_dirs` does.
3. **Clean up on library delete / path change.** `delete_library` and the path
   change in `update_library` should drop that root's `file_index`,
   `file_metadata_tags` and path references. Confirm in a Bootstrap modal (never
   a native dialog), since re-adding the library needs a rescan.
4. **Tests:** a ghost row outside any root is hidden; a real file still shows;
   the missing-file cleanup removes rows; it skips an unmounted or empty root;
   deleting a library clears its rows.

## Open question

- **"DC" vs "DC Comics" split (optional, separate):** different tagging sources
  spell the publisher differently, so even real files make two tiles. Option: a
  publisher-alias setting (map "DC" to "DC Comics") applied when the Library page
  groups. Not started; needs a decision.

## Related, same session (on branch `feat/pulllist-unsubscribe-mobile-reader`, not pushed)

- Pull List bulk **Unsubscribe** (done, tested).
- Mobile reader: native iOS page zoom blocked, scroll-mode pinch-zoom, modal sized
  with `inset`/100% instead of 100vw (done, tested). Not verified on a real
  iPhone; worth a try before merging.
