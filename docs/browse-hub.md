# Browse hub (Characters, Creators, Teams, Locations)

Status: planned. Tracked as task #1 in the session task list.

## Origin and data policy

The layout is inspired by League of Comic Geeks' search tabs and character
page. **No data is taken from League of Comic Geeks**: it has no public API,
and scraping is not an acceptable source (its terms were not readable from the
planning session, so that is unverified). All data comes from the user's own
library (ComicInfo.xml, already indexed) and from Metron via `mokkari`.

## What already exists

- `/browse/<category>/<name>` (`routes/collection.py`, `browse_by_metadata`)
  for writer, penciller, characters and publisher, rendered by
  `templates/browse_metadata.html`.
- `file_index.ci_characters` and the `file_metadata_tags` table
  (`core/database.py`, `_TAG_KINDS`), with provider ids stripped by
  `normalize_credit_list`.
- Insights page links into the detail pages from its "top" lists.

What is missing is an **index** (list every name) and any Teams/Locations
indexing.

## Phase 1: index pages (library data only)

- New `/browse` hub with tabs: Characters, Creators, Teams, Locations.
- Each tab lists every name with an issue count, a filter box, sort
  (most issues / A-Z) and paging; a name links to the existing detail page.
- Creators merges writer, penciller, inker, colorist, letterer and cover artist,
  with a role filter so one person is not listed six times.
- Teams and Locations: add `ci_teams` / `ci_locations` columns and
  `file_metadata_tags` kinds, plus a backfill from ComicInfo `Teams` /
  `Locations`. Empty until a re-index runs.
- Cards: text first; lazy-loaded cover of the most recent issue per name later.
- Respect per-user folder grants (`accessible_folder_prefixes`).
- Add an `ENDPOINTS` entry in `routes/api_v1_docs.py` only if an API route is
  added.

## Phase 2: character detail page

Header, Titles tab (existing grouped query) and Timeline tab (library issues in
cover-date order), enriched from the Metron character record
(`mokkari.schemas.character.Character`):

| Field | Used for |
|---|---|
| `alias[]` | Aliases |
| `desc` | Bio (sanitize like `_sanitize_html` in `core/reading_list_sync.py`) |
| `image` | Portrait |
| `creators[]`, `teams[]`, `universes[]` | Creators, teams, universe line |
| `cv_id`, `gcd_id` | Cross-links |

Rules:

- Store a name -> Metron character id mapping; do not search by name at view
  time (two "Spider-Man" characters exist on different Earths).
- Cache one record per character in a new table and refresh rarely. A page view
  never makes a live provider call (daily quota, see
  `.claude/rules/provider-clients.md`).
- Without Metron credentials or a match, the page still shows Titles, Timeline
  and the creators/teams found in the library; only bio and aliases are absent.

## Dropped (no source in Metron or ComicInfo)

First appearance, relationships, abilities, proficiencies, species,
occupations, pronouns, living status, places of origin/residence/work.

## Out of scope

Entity/mantle grouping, universe and franchise hubs.

## Definition of done

Routes have tests in `tests/routes/`, query and indexing changes have tests in
`tests/unit/`, any new table follows `.claude/rules/database-health.md`, and
`pytest` passes in full.
