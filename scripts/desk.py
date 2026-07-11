#!/usr/bin/env python3
"""The tweet desk CLI — deterministic entry point for everything on the desk.

Everything generated (text, images) lands on the desk (desk/, gitignored,
date-stamped) BEFORE it goes anywhere near Twitter. Posting moves a draft to
desk/posted/ and records the tweet id, so the desk is a full local ledger.

  desk.py new "text"  [--slug s]      create a draft (or pipe text on stdin)
  desk.py idea "text"                 quick idea capture
  desk.py list [drafts|ideas|posted|scrapped|all]
  desk.py show <id-prefix>
  desk.py edit <id-prefix>            print the file path (open/edit it yourself)
  desk.py post <id-prefix> [--dry-run]
  desk.py mark-posted <id-prefix> --tweet-id <id>   log a browser-posted draft
  desk.py scrap <id-prefix>
  desk.py media <file> [name]         stamp a file into desk/media/YYYY-MM-DD/

Draft format: frontmatter (--- delimited) + body. In the body, a line that is
exactly `---` splits the draft into a thread; parts post as a reply chain.
Attach media with a frontmatter line: `media: relative/path.png, other.jpg`
(paths relative to desk/).
"""

import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import twitter_api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = os.path.join(ROOT, "desk")
SUBDIRS = ["drafts", "ideas", "media", "posted", "scrapped", "inbox"]
POST_LOG = os.path.join(DESK, "posted", "log.jsonl")
TWEET_LIMIT = 280


def ensure_dirs():
    for d in SUBDIRS:
        os.makedirs(os.path.join(DESK, d), exist_ok=True)


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def today():
    return datetime.date.today().isoformat()


def slugify(text, maxwords=5):
    words = re.findall(r"[a-z0-9]+", text.lower())[:maxwords]
    return "-".join(words) or "untitled"


# ── draft file format ────────────────────────────────────────────────


def parse_draft(path):
    lines = open(path).read().split("\n")
    meta, body_start = {}, 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body_start = i + 1
                break
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    body = "\n".join(lines[body_start:]).strip()
    parts = [p.strip() for p in re.split(r"\n---\n", body) if p.strip()]
    return meta, parts


def write_draft(path, meta, body):
    with open(path, "w") as f:
        f.write("---\n")
        for k, v in meta.items():
            f.write(f"{k}: {v}\n")
        f.write("---\n")
        f.write(body.rstrip() + "\n")


def find(id_prefix, dirs=("drafts", "ideas")):
    hits = []
    for d in dirs:
        folder = os.path.join(DESK, d)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.endswith(".md") and name.removesuffix(".md").startswith(id_prefix):
                hits.append(os.path.join(folder, name))
    if not hits:
        sys.exit(f"no draft matching '{id_prefix}' in {'/'.join(dirs)}")
    if len(hits) > 1:
        sys.exit("ambiguous, matches:\n  " + "\n  ".join(os.path.basename(h) for h in hits))
    return hits[0]


def char_report(parts):
    out = []
    for i, p in enumerate(parts, 1):
        n = len(p)
        flag = "  ⚠ OVER 280" if n > TWEET_LIMIT else ""
        label = f"[{i}/{len(parts)}] " if len(parts) > 1 else ""
        out.append(f"  {label}{n} chars{flag}")
    return "\n".join(out)


# ── commands ─────────────────────────────────────────────────────────


def cmd_new(args, folder="drafts"):
    slug = None
    if "--slug" in args:
        i = args.index("--slug")
        slug = args[i + 1]
        args = args[:i] + args[i + 2:]
    text = " ".join(args).strip() or sys.stdin.read().strip()
    if not text:
        sys.exit("no text given (arg or stdin)")
    slug = slug or slugify(text)
    base = f"{today()}-{slug}"
    path = os.path.join(DESK, folder, base + ".md")
    n = 2
    while os.path.exists(path):
        path = os.path.join(DESK, folder, f"{base}-{n}.md")
        n += 1
    meta = {"created": now_iso(), "status": folder.rstrip("s"), "media": "", "tweet_ids": ""}
    write_draft(path, meta, text)
    _, parts = parse_draft(path)
    print(f"created {os.path.relpath(path, ROOT)}")
    print(char_report(parts))


def cmd_idea(args):
    cmd_new(args, folder="ideas")


def cmd_list(args):
    which = args[0] if args else "all"
    dirs = SUBDIRS[:4] if which == "all" else [which]
    for d in dirs:
        folder = os.path.join(DESK, d)
        if not os.path.isdir(folder):
            continue
        entries = sorted(f for f in os.listdir(folder) if not f.startswith("."))
        if not entries:
            continue
        print(f"{d}/  ({len(entries)})")
        for name in entries:
            path = os.path.join(folder, name)
            if name.endswith(".md"):
                _, parts = parse_draft(path)
                first = (parts[0] if parts else "").split("\n")[0]
                thread = f" [thread×{len(parts)}]" if len(parts) > 1 else ""
                print(f"  {name.removesuffix('.md')}{thread}  — {first[:70]}")
            else:
                print(f"  {name}")
        print()


def cmd_show(args):
    path = find(args[0], dirs=("drafts", "ideas", "posted", "scrapped"))
    print(f"# {os.path.relpath(path, ROOT)}\n")
    print(open(path).read())
    _, parts = parse_draft(path)
    print(char_report(parts))


def cmd_edit(args):
    print(find(args[0], dirs=("drafts", "ideas")))


def _media_ids_for(meta, dry):
    rels = [m.strip() for m in meta.get("media", "").split(",") if m.strip()]
    ids = []
    for rel in rels:
        p = os.path.join(DESK, rel)
        if not os.path.exists(p):
            sys.exit(f"media file missing: {p}")
        if dry:
            print(f"  would upload media: {rel}")
        else:
            mid = twitter_api.upload_media(p)
            print(f"  uploaded {rel} → media_id {mid}")
            ids.append(mid)
    return ids


def cmd_post(args):
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    path = find(args[0])
    meta, parts = parse_draft(path)
    if not parts:
        sys.exit("draft is empty")
    over = [i for i, p in enumerate(parts, 1) if len(p) > TWEET_LIMIT]
    if over:
        sys.exit(f"refusing to post — part(s) {over} over {TWEET_LIMIT} chars:\n{char_report(parts)}")
    print(("DRY RUN — " if dry else "") + f"posting {os.path.basename(path)} ({len(parts)} tweet(s))")
    print(char_report(parts))
    if not dry:
        twitter_api.load_creds()  # fail fast before any upload
    media_ids = _media_ids_for(meta, dry)
    if dry:
        for i, p in enumerate(parts, 1):
            print(f"\n── tweet {i} ──\n{p}")
        return
    tweet_ids, reply_to = [], None
    for i, p in enumerate(parts, 1):
        out = twitter_api.post_tweet(p, reply_to=reply_to, media_ids=media_ids if i == 1 else None)
        tid = out["id"]
        tweet_ids.append(tid)
        reply_to = tid
        print(f"  posted {i}/{len(parts)} → https://x.com/i/status/{tid}")
    _finish_posted(path, meta, parts, tweet_ids, via="api")


def cmd_mark_posted(args):
    if "--tweet-id" not in args:
        sys.exit("usage: desk.py mark-posted <id-prefix> --tweet-id <id>[,<id>…]")
    i = args.index("--tweet-id")
    tweet_ids = [t.strip() for t in args[i + 1].split(",")]
    path = find(args[0])
    meta, parts = parse_draft(path)
    _finish_posted(path, meta, parts, tweet_ids, via="browser")


def _finish_posted(path, meta, parts, tweet_ids, via):
    meta.update(status="posted", posted_at=now_iso(), tweet_ids=",".join(tweet_ids), via=via)
    write_draft(path, meta, "\n\n---\n\n".join(parts))
    dest = os.path.join(DESK, "posted", os.path.basename(path))
    shutil.move(path, dest)
    with open(POST_LOG, "a") as f:
        f.write(json.dumps({
            "id": os.path.basename(dest).removesuffix(".md"),
            "posted_at": meta["posted_at"], "via": via,
            "tweet_ids": tweet_ids, "text": parts,
        }) + "\n")
    print(f"archived → {os.path.relpath(dest, ROOT)}  (log: desk/posted/log.jsonl)")


def cmd_scrap(args):
    path = find(args[0])
    dest = os.path.join(DESK, "scrapped", os.path.basename(path))
    shutil.move(path, dest)
    print(f"scrapped → {os.path.relpath(dest, ROOT)}")


def cmd_media(args):
    src = args[0]
    if not os.path.exists(src):
        sys.exit(f"no such file: {src}")
    name = args[1] if len(args) > 1 else os.path.basename(src)
    folder = os.path.join(DESK, "media", today())
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, name)
    shutil.copy2(src, dest)
    rel = os.path.relpath(dest, DESK)
    print(f"stamped → desk/{rel}")
    print(f"attach with frontmatter:  media: {rel}")


COMMANDS = {
    "new": cmd_new, "idea": cmd_idea, "list": cmd_list, "show": cmd_show,
    "edit": cmd_edit, "post": cmd_post, "mark-posted": cmd_mark_posted,
    "scrap": cmd_scrap, "media": cmd_media,
}


def main():
    ensure_dirs()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__.strip())
        sys.exit(0 if len(sys.argv) < 2 else 1)
    try:
        COMMANDS[sys.argv[1]](sys.argv[2:])
    except (twitter_api.NotConfigured, twitter_api.ApiError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
