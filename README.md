# clawd-tweet-desk

A local-first "tweet desk" for drafting, reviewing, and posting tweets with an
AI agent in the loop. Everything generated — draft text, thread outlines,
images — lands as date-stamped files in a local `desk/` folder first, gets
reviewed there, and only then goes out through deterministic scripts.

- `scripts/desk.py` — the CLI: capture ideas, draft tweets/threads, dry-run,
  post, and keep a ledger of everything published.
- `scripts/lib/twitter_api.py` — dependency-free (pure Python stdlib)
  Twitter API client: OAuth 1.0a, tweets, threads, media upload.

The desk contents themselves (`desk/`, credentials) are local-only and
gitignored — this repo holds just the tooling.
