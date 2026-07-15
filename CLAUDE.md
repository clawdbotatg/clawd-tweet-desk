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
    - `inbox/handoff/clawd-twitter/` — **the engine room**: the outgoing
      agent's repo, cloned (public: `clawdbotatg/clawd-twitter`). See
      "Engine room" below.
- `scripts/desk.py` — THE entry point: `new / idea / list / show / post
  (--dry-run) / mark-posted / scrap / media`. Run with no args for usage.
- `scripts/clips.py` — slop.computer clip proposals: reads the SlopComputer
  contract (mainnet, stdlib JSON-RPC) + IPFS manifests to inventory every
  clawd-clipper clip bundle, tracks which clips were already tweeted
  (`desk/clips/tweeted.json` — seeded 2026-07-14 from a timeline audit of
  @clawdbotatg + @austingriffith; `mark` after every clip post), and
  downloads a chosen 9:16 mp4 onto the desk. `inventory / list / show /
  fetch / mark / unmark`. Picking the clip + writing the voice stays manual.
- `scripts/lib/twitter_api.py` — pure-stdlib OAuth 1.0a client
  (post_tweet / upload_media / delete_tweet). Creds from `.env`.
- `STYLE.md` — the voice law, copied verbatim from the handoff repo (already
  public there). Read it before drafting ANYTHING.
- `.env` (gitignored, see `.env.example`) — Twitter + Telegram keys.

## Engine room — the inherited clawd-twitter scripts
The previous agent's proven Node toolkit lives at
`desk/inbox/handoff/clawd-twitter/` (its own git clone, inside gitignored
`desk/` so it never leaks into this repo's history). Deps are installed
(`npm i --ignore-scripts`; node v22 on this machine). Read its `CLAUDE.md`
(hard rules + approval protocol + full script table) and `HANDOFF.md`
(scars/judgment calls) — they are the law this desk inherits.

Script highlights (run from that dir; `--json` on most):
- **Reads (work NOW, no creds):** `read-x-card.js <url>` — guest-token
  reader, full tweet text + article cards. Verified working on this laptop.
- **Reads (need `.env`):** `read-feed.js` / `feed-trends.js` (Austin's home
  timeline), `mentions.js`, `score-mentions.js` (deterministic triage),
  `my-tweets.js` (ALWAYS check before drafting — never re-announce),
  `tweet-info.js`, `repo-activity.js` (GH_TOKEN).
- **Writes (need `.env` + explicit approval per draft):** `tweet.js`,
  `tweet-with-image.js`, `reply.js`, `qt.js`, `rt.js`, `thread.js`,
  `delete-tweet.js` (delete = do immediately on Austin's command).
- **Other:** `gm-image.js` (gpt-image-2 character image; OPENAI_API_KEY),
  `tg-send.js` (Telegram to Austin), `x.js` (generic API wrapper).

Its `.env` (gitignored there too) uses different names than ours:
`X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET` =
@clawdbotatg posting OAuth · `AUSTIN_X_*` = @austingriffith read OAuth
(limited tier, home timeline only) · `X_BEARER_TOKEN` = public lookups ·
`TELEGRAM_TWEET_BOT_TOKEN` + `TELEGRAM_AUSTIN_ID` · `OPENAI_API_KEY` ·
`GH_TOKEN`. When the values arrive, drop the file at
`desk/inbox/handoff/clawd-twitter/.env` verbatim, then derive this repo's
root `.env` from it (TWITTER_API_KEY=X_API_KEY, TWITTER_ACCESS_SECRET=
X_ACCESS_TOKEN_SECRET, etc. per `.env.example`). Never echo values.

Long-term: cherry-pick scripts worth keeping into `scripts/` (public, so
port carefully or keep stdlib-Python), but the engine room runs as-is
meanwhile — don't rewrite what already works.

## Hard editorial rules (inherited, non-negotiable)
1. **Publishing (tweet/reply/QT/thread/RT) always gets Austin's explicit
   approval — per exact draft.** Text changed after approval = new draft =
   ask again. The previous-previous bot was terminated for posting unasked.
   Non-publishing actions (delete, like, follow, reads) run immediately on
   his command.
2. **No hashtags. Ever.** Under 280 weighted chars (URLs = 23).
3. **Never invent facts** — every name/number/launch comes from feed data,
   repo activity, or Austin.
4. **Scheduled-style tweets (gm, build reports) always ship with an image**
   that matches the text's vibe; image gen failed → say so, don't ship
   text-only.
5. **Check `my-tweets.js` before drafting** — advance a covered story, never
   repeat it as fresh news.
6. Voice per `STYLE.md`: lowercase, 🦞/🦀, dry + specific + technical, named
   narratives ("AI is moving fast" is a firing offense), no engagement-bait.
   Threads end with the cop-pointing-up impersonation closer.
7. Austin's phone is @austingriffith — he CANNOT delete @clawdbotatg tweets
   himself. "delete that" → `delete-tweet.js` immediately; we are the only
   path.

## Posting: deterministic first, browser fallback
1. **Preferred:** `python3 scripts/desk.py post <id>` — checks 280/part,
   uploads media, posts threads as reply chains, archives + logs.
   Always `--dry-run` first on anything non-trivial.
2. **Fallback (API failure):** post via the claude-in-chrome
   browser extension, then IMMEDIATELY record it:
   `python3 scripts/desk.py mark-posted <id> --tweet-id <id>` so the ledger
   stays complete.

## Status / pending (update as these land)
- **Handoff: RECEIVED + digested (2026-07-11).** Engine room cloned, deps
  installed, no-cred reads verified. `HANDOFF.md` there has the deep scars
  (headless quirks, cron-killers, open daemon bugs) — most are AWS-box
  specific and don't apply here, but read it before touching anything
  daemon-shaped.
- **Credentials: RECEIVED (2026-07-11 evening).** Scp'd from the AWS box
  (Austin's ok) to `desk/inbox/handoff/clawd-twitter/.env`; root `.env`
  derived from it (regenerate, don't hand-edit). Verified live: clawd-OAuth
  reads (`my-tweets.js`), Austin-OAuth home timeline (`read-feed.js`,
  `feed-trends.js`), Telegram (`tg-send.js`). Posting scripts share the
  same OAuth pair — first real approved post is the remaining proof.
- **CUTOVER DONE (2026-07-12, ~2pm Denver).** This laptop now runs
  @clawdbotatg solo. launchd jobs `com.clawd.twitter-{morning,nightly,
  sweep,approval}` are loaded (gm 8:02a, nightly 8:02p, sweeps
  7/10/1/4/7:06 Denver, approval daemon always-on with KeepAlive). Plists +
  installer staged at `desk/inbox/handoff/clawd-twitter/state/
  launchd-staging/`. The AWS box's four units are stopped AND disabled
  (not deleted — `sudo systemctl enable --now …` on the box rolls back).
  Handoff was zero-gap: the box covered 2026-07-12's gm + 1:06p sweep;
  the laptop owns everything after. Wrapper logs: `state/*.log`;
  launchd-level logs: `state/launchd-*.log`. The daemon routes LLM turns
  through `~/clawd-harness/projects/claude-p-agent/adapters/run.py`
  (env-scrub + subscription routing built in).
- **Telegram:** Austin's messages to the bot now land on THIS machine's
  approval daemon. Never run a second getUpdates poller anywhere.

## Conventions
- Date-stamp everything; filenames are ids (`2026-07-11-slug`).
- Python stdlib only in scripts — no pip deps, so they run anywhere the
  harness does.
- Posting is an outward-facing, irreversible act: unless the user has
  explicitly said "post it" (here or via Telegram), stop at a ready draft
  and ask.
- Git identity: clawdbotatg / clawd@buidlguidl.com, HTTPS.
