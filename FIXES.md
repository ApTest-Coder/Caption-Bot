# Bug Fix Report

This document records the issues found during a full code audit and the
fixes applied. Seven files changed; nothing else in the project was
	touched. Every fix below was verified either by an automated test in
`tests/`, or by an offline smoke-test harness that exercised the real
handler functions in `main.py` with a stand-in Telegram layer.

## 1. Season number failed to parse for the most common naming pattern
**File:** `utils/parser.py`

`SEASON_RE` required a regex word-boundary (`\\b`) immediately after the
captured season digits. That boundary never matches when the digits are
followed directly by the episode marker with no separator — e.g.
`Show.S02E07.mkv`, which is the single most common release-naming
convention. As a result, `{season}` silently fell back to the
`"S01 - S0?"` placeholder for the vast majority of real files, while
`{episode}` parsed correctly, producing inconsistent captions.

The existing test happened to pass anyway, because its assertion
(`assert '2' in result`) was satisfied by the digit "2" appearing
elsewhere in the rendered filename — not by the `{season}` placeholder
actually resolving correctly. That masked the bug.

**Fix:** changed the trailing `\\b` to a negative lookahead for another
digit (`(?!\\d)`), which correctly stops at the season digits whether they're
followed by a separator, a letter (`E`), or end of string.
Added `tests/test_formatter.py` coverage with a direct assertion.

## 2. `/broadcast` command was documented but did not exist
**Files:** `main.py`, `database/settings.py`

`README.md` lists `/broadcast` as an admin command, `plugins/admin.py`
lists it, and `plugins/broadcast.py` claimed it was "implemented in main.py"
— but no such handler existed. The database layer already had a
`user_ids()` method and a `blocked` column specifically for this purpose,
but nothing ever called `user_ids()`, and nothing ever set `blocked`.

**Fix:** implemented `/broadcast` (admin-only). Reply to a message with
`/broadcast` to copy that message to every tracked user, or send
`/broadcast <text>` for a plain announcement. Handles Telegram flood
control (`TelegramRetryAfter`, one retry using the server-given delay)
and users who blocked the bot (`TelegramForbiddenError`, now recorded
via the new `Database.mark_blocked()` so future broadcasts skip them
automatically). Reports a delivery summary back to the admin.

## 3. Flood-wait recovery retried the wrong Telegram API call
**File:** `main.py` (`channel_post`)

When Telegram returned a flood-wait (`TelegramRetryAfter`), the handler
always retried `edit_message_caption`, regardless of which call had
actually triggered it. Two failure modes followed: if the **forward**
step (`copy_message`) was the one flood-waited, the retry re-ran the
already-successful caption edit instead — so the forward silently never
happened (and the pointless re-edit could itself error with "message is
not modified", which then got mis-reported to the owner as a real failure).
If the **edit** step was flood-waited, the retry never went on to attempt
the forward at all.

**Fix:** added `retry_after_floodwait()`, a small helper that wraps a single
API call and retries *that exact call* once with the server-requested delay.
Both the caption edit and the forward now use it independently, so a
flood-wait on either one no longer skips or misdirects the other.

## 4. Logging was never configured
**Files:** `main.py`

`utils/logger.py` already defined a `setup()` helper with a readable,
timestamped format, but nothing called it, and `main()` never called
`logging.basicConfig()` either. Python's root logger has no handler by
default, so `LOGGER.info(...)` (including the startup message) was silently
dropped, and warnings/errors printed with no timestamp or module context.

**Fix:** `main()` now calls `setup_logging()` as its first line.

## 5. Unrelated `TgCrypto` dependency
**File:** `requirements.txt`

`TgCrypto` accelerates MTProto encryption for Pyrogram/Telethon clients.
This project is built entirely on `aiogram` (plain HTTP Bot API) and
never imports `TgCrypto` anywhere.

**Fix:** removed.

## 6. Inline-menu buttons didn't re-check private-mode / force-subscribe
**File:** `main.py`

Command handlers enforce private mode and force-subscribe, but old inline
menus also need to re-check access when clicked later.

**Fix:** added `public_access_cb()` and applied it to inline navigation and
channel-management callbacks.

## 7. Hardening: unsafe dict lookup in the settings callback
**File:** `main.py` (`setting_callback`)

`prompts[kind]` could raise a `KeyError` if unexpected callback data arrived.

**Fix:** changed the lookup to `prompts.get(kind, "⚠️ Unknown option.")`.

## Minor cleanup
- `plugins/status.py` and `plugins/users.py` now reference `database.settings`.

## Not changed
- Colored inline buttons are intentionally retained.
- The small plugin/database reference files are intentionally retained as
  project documentation/stubs; live logic remains in the entry point and
  storage facade.
