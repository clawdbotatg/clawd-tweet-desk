# clawd-tweet-desk — orientation for Claude

The **tweet desk**: a local-first workspace for coordinating our Twitter game.
Drafts, ideas, generated images, and a posted ledger all live as date-stamped
files under `desk/` so any session (harness UI or Telegram) can look at the
desk and reason about what's on it.

## The one rule
**Everything generated lands on the desk first.** Never compose a tweet and
post it in one motion. Draft → file in `desk/drafts/` → review → post via
script. Images the same: generate → `desk/media/YYYY-MM-DD/` → attach →
review → post. The desk is the ledger; if it didn't hit the desk, it didn't
happen.

## Second rule — this repo is PUBLIC
Remote is `clawdbotatg/clawd-tweet-desk` on GitHub, public. `desk/` and
`.env` are gitignored and must stay that way. Scripts and skills with nothing
sensitive in them are fine to commit. **Before any commit, scan the diff for
keys, handles-in-progress, or unposted draft text.** When in doubt, it stays
local.

## Layout
- `desk/` (gitignored) — the desk itself. Created on demand by the scripts.
  - `drafts/` — tweets in progress, `YYYY-MM-DD-slug.md` (frontmatter + body;
    a body line of exactly `---` splits a thread)
  - `ideas/` — raw seeds, same format, lower bar
  - `media/YYYY-MM-DD/` — generated/collected images
  - `posted/` — archived drafts after posting + `log.jsonl` (the ledger)
  - `scrapped/` — rejected drafts (kept, not deleted — they inform tone)
  - `inbox/` — handoff notes, telegram dumps, anything incoming
- `scripts/desk.py` — THE entry point: `new / idea / list / show / post
  (--dry-run) / mark-posted / scrap / media`. Run with no args for usage.
- `scripts/lib/twitter_api.py` — pure-stdlib OAuth 1.0a client
  (post_tweet / upload_media / delete_tweet). Creds from `.env`.
- `.env` (gitignored, see `.env.example`) — Twitter + Telegram keys.

## Posting: deterministic first, browser fallback
1. **Preferred:** `python3 scripts/desk.py post <id>` — checks 280/part,
   uploads media, posts threads as reply chains, archives + logs.
   Always `--dry-run` first on anything non-trivial.
2. **Fallback (no keys yet / API failure):** post via the claude-in-chrome
   browser extension, then IMMEDIATELY record it:
   `python3 scripts/desk.py mark-posted <id> --tweet-id <id>` so the ledger
   stays complete.

## Status / pending (update as these land)
- **Twitter API keys:** NOT yet provided — `.env` doesn't exist yet. Until
  then `post` fails fast with a clear message; use the browser fallback.
- **Telegram bot:** planned coordination channel; token/details not yet
  provided.
- **claude-p-agent handoff:** the Twitter game currently runs on a
  claude-p-agent; its handoff notes are coming and should be filed into
  `desk/inbox/handoff/` and digested into this file.

## Conventions
- Date-stamp everything; filenames are ids (`2026-07-11-slug`).
- Python stdlib only in scripts — no pip deps, so they run anywhere the
  harness does.
- Posting is an outward-facing, irreversible act: unless the user has
  explicitly said "post it" (here or via Telegram), stop at a ready draft
  and ask.
- Git identity: clawdbotatg / clawd@buidlguidl.com, HTTPS.
