# Push notification covers and icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apprise pushes get an emoji icon per event, a bold comic name, a link to the source page, and the issue cover attached when one comic is the subject.

**Architecture:** `core/notifications.py` owns icons, the cover attachment and the body format. Bodies are built as small HTML (`<b>`, `<a>`, `<br/>`): Apprise 2.2 converts HTML to Markdown for Discord/ntfy and to plain text for text-only services, while it has no Markdown→text converter (verified). Callers pass an optional `cover_path`; the cover is resolved on the notification thread.

**Tech Stack:** Python, Apprise 2.2.0, `core.thumbnail_cache`.

**Spec:** `docs/superpowers/specs/2026-11-16-notification-covers-design.md`

## Global Constraints

- Icons: ✅ download_complete, ❌ download_failed, 📚 wanted_added, ⚠️ db_corrupt, 🔔 test.
- A notification never raises into its caller and never blocks the download worker or pollers.
- Cover only for a finished download and for a wanted sweep that moved exactly one issue.
- Source link uses the task's `page_url`, never the direct file URL.
- Every interpolated value (filename, error, issue name, URL) is `html.escape`d.
- Run only targeted tests: `.venv/bin/python -m pytest tests/unit/test_notifications.py tests/unit/test_download_notify_hooks.py` (venv at the main checkout: `../../../.venv/bin/python`).

## Review Focus

- A filename with `&`, `<` or `*` renders literally, not as markup.
- `cover_path` pointing at a file the monitor already moved: message sent without attach.
- A PDF or unreadable archive as `cover_path`: no attach, no raise.
- `page_url` None: plain `Source: <provider>` text, no empty link.
- Apprise `notify()` raising with an `attach` kwarg: swallowed like any other send error.

---

### Task 1: Icons, HTML body format and cover attachment in `core/notifications.py`

**Files:**
- Modify: `core/notifications.py`
- Test: `tests/unit/test_notifications.py`

**Interfaces:**
- Produces: `notify(event, title, body, cover_path=None) -> bool`, `notify_async(event, title, body, cover_path=None) -> None`, `_cover_image(cover_path) -> str | None`, `_send(urls, title, body, notify_type, attach=None)`. `EVENT_DEFS[e]["icon"]`.

- [ ] **Step 1: Update/add tests**
  - `test_sends_when_enabled`: notify called with `title="✅ Title", body="Body", notify_type="success", body_format="html"` (no `attach` kwarg when no cover).
  - `test_every_event_has_an_icon`: each `EVENT_DEFS` value has a non-empty `icon`; failed is "❌", wanted "📚", db "⚠️".
  - `test_cover_is_attached`: patch `core.notifications._cover_image` to return `"/c/x.jpg"`; `notify(..., cover_path="/lib/a.cbz")` → notify kwargs include `attach="/c/x.jpg"`.
  - `test_unresolvable_cover_sends_without_attach`: `_cover_image` returns None → no `attach` kwarg, still returns True.
  - `test_cover_image_missing_file_is_none`: `_cover_image("/nope.cbz") is None`.
  - `test_cover_image_never_raises`: patch `core.thumbnail_cache.regenerate_thumbnail` to raise; existing temp `.cbz` path → None.
  - `test_cover_image_uses_fresh_cache`: temp file plus patched `thumbnail_cache_path` to an existing jpg and `is_thumbnail_stale` False → returns that jpg, `regenerate_thumbnail` not called.
  - `send_test` sends title `"🔔 Comic Library Utilities"`.
  - `notify_async` passes `cover_path` through to the thread target args.
- [ ] **Step 2: Run, expect failures**
- [ ] **Step 3: Implement**: add `icon` to each `EVENT_DEFS` entry; `notify` prefixes `f"{icon} {title}"`; `_cover_image` returns None unless `os.path.isfile` and `can_thumbnail`; uses the cached jpg when present and not stale, else `regenerate_thumbnail(path, record_job=False)` and returns the cache path if it now exists; everything in try/except → None. `_send` passes `body_format=apprise.NotifyFormat.HTML` (fall back to the string `"html"` if the attribute is missing, as in the test fake) and `attach=attach` only when set. Body of `send_test` stays text-safe.
- [ ] **Step 4: Run tests, expect pass**
- [ ] **Step 5: Commit** `Notifications: icon per event, HTML body, cover attachment`

### Task 2: HTML bodies and source link

**Files:**
- Modify: `core/download_utils.py` (`download_notification_body`), `core/notifications.py` (`format_digest`, `notify_download_terminal`), `core/db_health.py` (`_notify_corruption`)
- Test: `tests/unit/test_download_notify_hooks.py`, `tests/unit/test_notifications.py`

**Interfaces:**
- Produces: `download_notification_body(dest_filename, file_path=None, provider=None, error=None, attempts=0, page_url=None) -> str` (lines joined with `"<br/>"`, name in `<b>`).

- [ ] **Step 1: Update/add tests** (existing ones change from `"\n"` to `"<br/>"` and a bold name):
  - `download_notification_body("Batman 001.cbz") == "<b>Batman 001.cbz</b>"`.
  - with `provider="GetComics", page_url="https://getcomics.org/a?b=1&c=2"` contains `'Source: <a href="https://getcomics.org/a?b=1&amp;c=2">GetComics</a>'`.
  - `page_url` without provider → link text is the page host.
  - `provider` without `page_url` → `"Source: GetComics"` with no `<a`.
  - `download_notification_body("a & <b>.cbz")` contains `"a &amp; &lt;b&gt;.cbz"`.
  - `format_digest("Added:", ["X & Y #1"])` escapes the item; header and `...and N more` unchanged in meaning, lines joined with `<br/>`.
  - `notify_download_terminal("complete", "a&b.cbz", source="SABnzbd")` sends a body with `<b>a&amp;b.cbz</b>` (patch `notify_async`).
- [ ] **Step 2: Run, expect failures**
- [ ] **Step 3: Implement** with `html.escape`; link text is `provider` or `urlparse(page_url).hostname`; db_health message escaped and `\n\n` → `<br/><br/>`.
- [ ] **Step 4: Run tests, expect pass**
- [ ] **Step 5: Commit** `Notifications: bold comic name and source link`

### Task 3: Wire covers and page_url at the hook sites

**Files:**
- Modify: `api.py` (success `notify_async` in `process_download`), `app.py` (wanted digest)
- Test: `tests/unit/test_download_notify_hooks.py` (structural, AST — api.py/app.py cannot be imported)

- [ ] **Step 1: Tests**
  - In `process_download`, the `EVENT_DOWNLOAD_COMPLETE` `notify_async` call has keyword `cover_path` and its `download_notification_body` call has keyword `page_url`.
  - The failure `notify_async` has no `cover_path` keyword.
  - In app.py, the `EVENT_WANTED_ADDED` `notify_async` call has keyword `cover_path`.
- [ ] **Step 2: Run, expect failures**
- [ ] **Step 3: Implement**: api.py success passes `page_url=source_page_url` and `cover_path=file_path`. app.py records the final library path of each moved file (`moved_paths`, next to `moved_issues`) and passes `cover_path=moved_paths[0] if moved_count == 1 else None`. Usenet/DC++ unchanged.
- [ ] **Step 4: Run both test files, expect pass; also `tests/unit/test_no_shadowed_local_imports.py`**
- [ ] **Step 5: Commit** `Notifications: attach the cover and link the source page`
