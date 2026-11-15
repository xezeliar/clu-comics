# Push notifications: cover image and icons

## Why
Apprise pushes (Discord, Telegram, ntfy...) are bare text today. The owner wants
them to look like a comics app sent them: the issue cover and an icon per event.

## Goals
- Download complete pushes, and Wanted-added pushes for a single issue, carry
  the issue cover as an attachment.
- Every event title starts with an emoji icon: ✅ complete, ❌ failed,
  📚 wanted added, ⚠️ database corruption, 🔔 test message.
- The body is light markdown (comic name in bold); Apprise sends plain text to
  services that cannot render markdown.

## Non-goals
- No image URLs (B): Discord fetches them itself, so they fail unless CLU is
  public on the internet.
- No custom bot avatar, no per-service formatting, no new settings.

## Anti-goals
- A notification must never break or slow the download it reports on. A missing,
  moved or unreadable file sends the message without an image.

## Approaches
- **A (picked): attach the cover file.** CLU uploads the JPEG with the message
  (outbound), so it works on a home network. Cost is one thumbnail render
  (~50-200 ms) on the existing notification thread, or none when cached.
- **B: link an image URL.** Free for CLU, but only works when CLU is reachable
  from the internet. Dropped.

## Design
- `core/notifications.py`
  - `EVENT_DEFS` gains an `icon` per event; `notify()` prefixes the title with it.
  - `notify` / `notify_async` take an optional `cover_path` (path to a comic).
    On the notification thread, resolve it to a JPEG via `core.thumbnail_cache`
    (cached thumbnail if fresh, else `regenerate_thumbnail`); on any failure or
    missing file, send without it.
  - `_send` passes `attach=` when there is an image and
    `body_format=markdown`.
  - `send_test` uses the 🔔 icon.
- Callers:
  - `api.py` download complete passes the final `file_path`.
  - `app.py` wanted digest passes a cover only when the sweep moved exactly one
    issue. A multi-issue digest sends no image: one cover would misrepresent
    the list, and a collage costs N renders for a phone-sized thumbnail.
  - Failed downloads, the Usenet/DC++ pollers' failures and `db_health` pass
    nothing. The pollers' complete path passes the file only if they already
    hold a local path (builder's call; otherwise no image).
- Download complete links its source: `Source: [GetComics](page_url)` using the
  task's `page_url` (the post page, never the direct file link, which expires
  or re-downloads). No `page_url` (extension grabs, Usenet, DC++) keeps the
  plain `Source: <name>` line. Bodies are built as HTML: Apprise 2.2 converts
  HTML to Markdown and to text, but has no Markdown→text converter. So
  text-only services (SMS) get `Source: GetComics` without the URL.
- Bodies: comic name in bold (`download_notification_body`, `format_digest`
  items), everything else unchanged.

## Left to the builder
- Exact markdown escaping of filenames (`*`, `_` in names must not break bold).
- Tests in `tests/unit/test_notifications.py` and
  `tests/unit/test_download_notify_hooks.py`: icon prefix, attach passed when a
  cover resolves, sent without attach when it does not, nothing raised.
