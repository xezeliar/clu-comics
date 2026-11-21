# Browse hub (Characters, Creators, Teams)

Status: index pages built; Gaps 1 and 3 done (Teams, Editor, Translator indexed;
team counts from `<Teams>`; every credit links); stored profiles done
(`entity_profiles`, `core/entity_profiles.py`, Refresh at
`POST /api/<characters|teams|creators>/<name>/refresh`); the character, team
and creator pages (`templates/character.html`, `templates/team.html` and
`templates/creator.html`, all extending `templates/entity_page.html`;
`entity_details`, `character_info`, `team_info`, `team_members` and
`creator_info` in `core/creators.py`). `person.html` is gone. Change match /
Unmatch done (see "Matching"); portraits fall back to the ComicVine image.
Design: the "Character page", "Team page", "Creator page" and "Change match"
entries on the CLU Design Board.

## Origin and data policy

The layout is inspired by League of Comic Geeks' character page. **No data is
taken from League of Comic Geeks**: it has no public API and blocks automated
fetches behind Cloudflare. All data comes from the user's own library
(ComicInfo.xml, already indexed), CLU's own tables (read status, reading
lists), and cached Metron and ComicVine records.

## What already exists

- Index and detail pages: `/characters`, `/creators`, `/teams` and their
  `/<name>` pages (`routes/creators.py`, `core/creators.py`), rendered by
  `templates/people_index.html` and the detail templates above, respecting
  per-user folder grants.
- Photos: `core/person_art.py` resolves a name on Metron (exact, casefolded
  name match) on a daemon thread when a detail page opens, and caches the image.
  When Metron has none, the stored ComicVine image is downloaded and cached the
  same way (never ComicVine's `*blank.png` placeholder). The browser never loads
  either provider: images are fetched only from Metron and ComicVine hosts,
  through one paced shared client per host.
- Teams: where a team appears comes from ComicInfo `<Teams>` (`ci_teams`, tag
  kind `teams`); who is on it from `character_teams`, filled from Metron
  `Character.teams` during that resolve.
- `/browse/<category>/<name>` (`browse_metadata.html`) for writer, penciller,
  characters and publisher, linked from Insights.

## Gaps

1. **ComicInfo `<Teams>` is not indexed, so team counts are guessed.** Today a
   team's issues are "owned issues with any member" (`_TEAM_TAGS` in
   `core/creators.py`): a Batman solo issue counts as Justice League, and a
   member nobody has opened adds nothing. CLU's own taggers already write
   `<Teams>` (`models/comicvine.py`, `models/metron.py`). Fix:
   - Add a `ci_teams` column and a `teams` kind in `file_metadata_tags`;
     backfill on re-index.
   - **Trust ComicInfo only.** A team's Comics tab, issue counts, the Teams
     index (built from `<Teams>` values, like Characters from `<Characters>`)
     and `read_team_counts` all come from `ci_teams`, matched case-insensitively.
     No member-based fallback: a guess is worse than no number.
   - `character_teams` and ComicVine `members` stay only for the Members tab
     (who belongs to the team, not where it appears).
   - A team with no tagged issues shows an empty state: "No issues tagged with
     this team. Re-tag with ComicVine or Metron to fill in `<Teams>`."
2. **The character page shows only photo and issues.** No bio, aliases,
   creators or ComicVine details.
3. **Only Writer and Penciller credits link to a creator.** The Credits block
   in the CBZ info panel (`static/js/clu-cbz-info.js`, `_fieldGroups`) sets
   `browse` only on Writer and Penciller. Inker, Colorist, Letterer and Cover
   artist are already indexed (`_TAG_KINDS`, `CREDIT_KINDS`) and already count
   on `/creators/<name>`; they are just plain text. Editor and Translator are
   written by CLU's taggers (`models/comicvine.py`, `models/metron.py`) but not
   indexed at all. Fix:
   - Link every credit field to `/creators/<name>?role=<kind>` (the page's
     existing role filter), so a name opens on the role it was clicked from.
   - Index `<Editor>` and `<Translator>` as `ci_editor` / `ci_translator` plus
     `editor` / `translator` tag kinds; add both to `CREDIT_KINDS`,
     `ROLE_LABELS`, `_METADATA_FACET_COLUMNS` and `_TAG_KINDS`; backfill on
     re-index (same pass as `ci_teams`).
   - Link Teams in the Story block to `/teams/<name>` once `ci_teams` exists.

## Character page (redesign of `person.html` for characters)

Header: portrait, name, publisher · universe, stat line (issues · series ·
read · owned year range), bio, Read next (primary), More. Tabs: Overview,
Titles, Timeline (by `ci_year`; no month). Information column on the right.

### Sources, one winner per field

| Field | Source |
|---|---|
| Issues, series, years, writers, artists, publisher, first in your library | Library (`file_index`) |
| Read count, Read next, reading lists | CLU tables |
| Bio | Metron `desc`, else ComicVine `summary` (never CV's long `description`) |
| Aliases, created by | Metron, else ComicVine |
| Universe, GCD link | Metron |
| Portrait | Metron `image`, else ComicVine `image`, else first owned cover (labelled "Cover") |
| Teams | Metron ∪ ComicVine, merged by name; counts from `ci_teams` |
| Real name, first appearance, origin, powers, allies (`friends`), enemies | ComicVine |

**Creators** (Overview, replaces "Writers and artists"): the eight people
credited most on this character's issues, any role (writer, penciller, inker,
colorist, letterer, cover artist, editor, translator), each with their main
role on those issues and the issue count, linking to
`/creators/<name>?role=<kind>`. From `file_metadata_tags`; the Team page shows
the same block over its `ci_teams` issues.

Not shown: CV gender, date of birth, deaths, friendly/enemy teams. No source
has family, occupation or pronouns.

### Rules

- **ComicVine is reached only through Metron's `cv_id`.** Never search
  ComicVine by name. No `cv_id`, no ComicVine rows.
- **Stored, never live.** See "Storage and refresh" below. A page view only
  reads the stored row.
- **Quota.** One CV call per character per refresh; respect
  `.claude/rules/provider-clients.md` (pacing, auth lockout, quota latch). Metron
  or CV down leaves the page on whatever is cached.
- **Matching.** Keep the exact-name Metron match as the default. Add Change
  match / Unmatch (Clerk and Store Owner) to pick the Metron character when two
  share a name.
- Allies, enemies, creators and teams link to their CLU page when the library
  has them, with an issue count; otherwise plain text. First appearance says
  "Not in your library" when it is not owned.
- Sanitize bios like `_sanitize_html` in `core/reading_list_sync.py`.

## Team page (redesign of `person.html` for teams)

Header: team image, name, publisher · universe, stat line (members · issues ·
series), bio, More. Tabs: Overview, Members, Comics. No upcoming
appearances: CLU has no release calendar.

### Sources

| Field | Source |
|---|---|
| Comics tab, issue and series counts | Library (`ci_teams` only, see Gap 1) |
| Bio | Metron `desc`, else ComicVine `summary` |
| Image | Metron `image`, else ComicVine `image` |
| Universe, created by, GCD link | Metron |
| Members | Metron, reversed (`character_teams`, from each character's `teams`) ∪ ComicVine `members`, merged by name |
| First appearance, disbanded in, allies (`friends`), enemies | ComicVine |

The Metron team id is already stored (`character_teams.team_metron_id`), so a
team page fetches `team(id)` directly; ComicVine again only through its `cv_id`.

### Members tab

- **One Members grid, no Active / Former.** No source records membership
  status: Metron has no member list on a team, ComicVine's `members` is flat,
  ComicInfo only says who appears in an issue.
- Sorted by owned issue count. Each card in the library links to its
  character page, `/characters/<name>`, using the library's own spelling of the
  name (the page 404s on a name with no owned issues).
- Members only ComicVine knows of go last under "Not in your library", muted,
  not links.

## Creator page (redesign of `person.html` for creators)

Header: photo (initials when unmatched), name, role summary (Writer · Artist,
from the credits you own), stat line (issues · series · read · owned year
range), bio, Read next, Follow (outline; "Following" when on), More (Refresh).
Tabs: Overview and Comics. Comics has View (Series/Issues) and a Role filter
listing only the roles the creator has, each with its issue count; `?role=`
alone opens Comics, and an unowned or unknown role is ignored. Overview:
Credited most in, Newest in your library, Credited characters, Works most with
(other creators on the same issues), then "More on <name>". No upcoming comics
and no news: CLU has neither.

### Sources

| Field | Source |
|---|---|
| Comics, series, roles, read count | Library (`ci_writer`, `ci_penciller`... as today) |
| Credited characters | Library: `ci_characters` of the creator's owned issues, ranked by issue count, each linking to its character page |
| Bio | Metron `desc`, else ComicVine `summary`; the long CV `description` only in a collapsed "More on <name>", sanitized |
| Photo | Metron `image`, else ComicVine `image` (already cached by `person_art`) |
| Aliases, born, died, GCD link | Metron (`alias`, `birth`, `death`) |
| Hometown, country, website | ComicVine |

Not shown: CV email, gender. Credited characters come from your files, not
from ComicVine's `characters`, so every one links.

## Storage and refresh

Characters, teams and creators share one table and one flow.

**First open fetches; the row is kept forever.** Extend `person_art.resolve`
for characters, teams and creators: it already fetches the Metron detail, so store the
profile fields there, then fetch the CV record by `cv_id` through the guarded
ComicVine client. Write both into one `entity_profiles` row per (kind, key)
(new table, follows `.claude/rules/database-health.md`):

| Column | Holds |
|---|---|
| `kind`, `key` | `character`, `team` or `creator`, and the casefolded name (same key as `person_art`) |
| `metron_id`, `cv_id` | the matched records (`cv_id` from Metron) |
| `metron_json`, `cv_json` | only the fields the page shows (the source tables), not the whole response |
| `metron_fetched_at`, `cv_fetched_at` | UTC, set on each successful fetch |
| `status`, `error` | `ok` / `error` / `missing` / `unmatched`, last error text |

- **No expiry.** A stored profile is never deleted or hidden because it is old.
  Only Unmatch clears it (and Change match replaces it).
- **A failed refetch keeps the old data.** It updates `status`/`error` only;
  the page keeps showing the last good profile.
- **Refresh** in More refetches that one character, team or creator (Clerk and Store Owner). It
  is the only way a stored profile is updated. It uses the same paced, guarded
  clients and shows a toast if a provider is rate-limited or locked out.

**No scheduled refetch.** Refreshing is manual only, from the detail page.
A sweep would burn the shared Metron and ComicVine limits (`person_art` already
removed one because it "hammered Metron into timeouts"), so no job, setting or
Schedules row is added.

## Matching

The default match is still the exact, casefolded name on Metron. A Clerk or
Store Owner fixes a wrong one from More on the detail page
(`templates/partials/match_modal.html`, `static/js/entity-match.js`):

- **Change match** (or **Match <noun>** when nothing is matched) searches
  Metron by name (`GET /api/<grid>/<name>/match/search?q=`) and shows the one
  record picked (`GET /api/<grid>/metron-record/<id>`). Search results are only
  names and ids, so the record tells them apart. Its image comes back as a small
  data URI made on the server: the browser never loads Metron.
- **Use this match** (`POST /api/<grid>/<name>/match {metron_id}`) is enabled
  only once a record other than Current has loaded. `person_art.set_match` pins
  the id and clears the photo, the stored profile and (characters) the teams
  before the refetch, so the old record's ComicVine facts never show under the
  new one if ComicVine fails.
- **Unmatch** (`DELETE /api/<grid>/<name>/match`, after a confirm) clears the
  same things and sets status `unmatched` in `person_art` and
  `entity_profiles`. An unmatched name is never looked up by name again; a
  Change match is the only way back.
- Errors carry `reason`: `quota` (Metron paused, no Retry), `token` (link to
  Settings) or `failed` (Retry). The stored match is kept in every case.

## Out of scope

Locations tab and `ci_locations` (deferred; same shape as Teams). Entity/mantle
grouping (personas), universe and franchise hubs, News.

## Definition of done

Route changes have tests in `tests/routes/`, query, indexing and provider
changes have tests in `tests/unit/`, any new table follows
`.claude/rules/database-health.md`, and the targeted tests pass.
