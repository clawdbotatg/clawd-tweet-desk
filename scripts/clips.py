#!/usr/bin/env python3
"""Clip proposals from slop.computer episodes — inventory, tweeted-tracking, fetch.

The clawd-clipper pipeline pins AI-cut 9:16 clips (with suggested tweet copy)
to IPFS and references them from each episode's manifest on the SlopComputer
contract (mainnet). This script reads that public trail end-to-end so the desk
can answer "what clips exist and which haven't been tweeted yet" in one
command, then pull the chosen mp4 onto the desk.

  clips.py inventory            refresh desk/clips/inventory.json from chain+IPFS
  clips.py list [--all]         clips by episode, untweeted only by default
  clips.py show <slug> <rank>   full record: copy variants, CIDs, timing
  clips.py fetch <slug> <rank>  download the 9:16 mp4 to desk/media/YYYY-MM-DD/
  clips.py mark <slug> <rank>   record a clip as tweeted (desk/clips/tweeted.json)
  clips.py unmark <slug> <rank>

Tweeted state is desk-local (desk/ is gitignored). `mark` is the manual path;
posted desk drafts created via `fetch` carry a `source:` line, but the ledger
here is the source of truth for clip dedup. The picking itself stays manual —
this script only makes the mechanical parts one-liners.

Stdlib only, like everything in scripts/. The two 4-byte selectors below are
keccak256 signatures precomputed with viem (stdlib sha3 is NIST-SHA3, not
keccak, so they can't be derived at runtime).
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from twitter_api import load_env

ROOT = Path(__file__).resolve().parent.parent
DESK = ROOT / "desk"
CLIPS_DIR = DESK / "clips"
INVENTORY = CLIPS_DIR / "inventory.json"
TWEETED = CLIPS_DIR / "tweeted.json"

CONTRACT = "0xf3ce3614fe8cd4294a0bf05d10cfda9d9cbc4886"
SEL_EPISODE_COUNT = "0x6be153ae"  # episodeCount()
SEL_GET_EPISODES = "0xa75cd791"  # getEpisodes(uint256,uint256)
GATEWAY = "https://media.slop.computer/ipfs"
# ETH_RPC in .env (e.g. a local node) is tried first; public RPCs are fallback.
RPCS = [
    "https://eth.llamarpc.com",
    "https://ethereum-rpc.publicnode.com",
    "https://cloudflare-eth.com",
]
_local_rpc = load_env().get("ETH_RPC")
if _local_rpc:
    RPCS.insert(0, _local_rpc)


# Some public RPCs (and CDNs in front of gateways) 403 urllib's default UA.
UA = {"user-agent": "clawd-tweet-desk/clips.py"}


def http_json(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = dict(UA, **({"content-type": "application/json"} if data else {}))
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def eth_call(data):
    last = None
    for rpc in RPCS:
        try:
            res = http_json(
                rpc,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [{"to": CONTRACT, "data": data}, "latest"],
                },
            )
            if "result" in res:
                return bytes.fromhex(res["result"][2:])
            last = RuntimeError(res.get("error"))
        except Exception as e:  # noqa: BLE001 — try the next RPC
            last = e
    raise last


# ── minimal ABI decoding (just what getEpisodes returns) ─────────────────────

def word(buf, i):
    return buf[i : i + 32]


def uint_at(buf, i):
    return int.from_bytes(word(buf, i), "big")


def string_at(buf, base, head_off):
    """Decode a dynamic string whose offset-word sits at base+head_off."""
    data = base + uint_at(buf, base + head_off)
    ln = uint_at(buf, data)
    return buf[data + 32 : data + 32 + ln].decode("utf-8", "replace")


def decode_episodes(buf):
    """getEpisodes returns Episode[] — tuples with dynamic strings, so the
    layout is offset → array length → per-tuple offsets → tuple data."""
    arr = uint_at(buf, 0)  # offset of the array
    n = uint_at(buf, arr)
    base = arr + 32  # start of the per-element offset table
    eps = []
    for k in range(n):
        t = base + uint_at(buf, base + 32 * k)  # this tuple's data start
        eps.append(
            {
                "slug": string_at(buf, t, 32 * 2),
                "name": string_at(buf, t, 32 * 1),
                "liveSlug": string_at(buf, t, 32 * 3),
                "manifest": string_at(buf, t, 32 * 4),
                "datetime": uint_at(buf, t + 32 * 6),
            }
        )
    return eps


# ── IPFS ─────────────────────────────────────────────────────────────────────

def cid_of(s):
    return s[7:] if s.startswith("ipfs://") else s


def ipfs_json(cid):
    return http_json(f"{GATEWAY}/{cid_of(cid)}")


# ── state files ──────────────────────────────────────────────────────────────

def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def tweeted_key(slug, rank):
    return f"{slug}#{rank}"


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_inventory():
    count = uint_at(eth_call(SEL_EPISODE_COUNT), 0)
    call = SEL_GET_EPISODES + hex(0)[2:].zfill(64) + hex(count)[2:].zfill(64)
    episodes = decode_episodes(eth_call(call))
    out = []
    for ep in episodes:
        row = {
            "slug": ep["slug"],
            "name": ep["name"],
            "date": datetime.fromtimestamp(ep["datetime"], tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )
            if ep["datetime"]
            else None,
        }
        if ep["manifest"]:
            try:
                man = ipfs_json(ep["manifest"])
                clips_ref = (man.get("clips") or {}).get("cid")
                if clips_ref:
                    bundle = ipfs_json(clips_ref)
                    row["clips"] = bundle.get("clips") or []
            except Exception as e:  # noqa: BLE001 — keep the row, note the failure
                row["error"] = str(e)
        out.append(row)
        n = len(row.get("clips") or [])
        print(f"  {row['date'] or '----------'} {ep['slug']:<20} "
              f"{n or '-'} clips{'  ERR ' + row['error'] if row.get('error') else ''}")
    save(INVENTORY, {"fetchedAt": datetime.now(timezone.utc).isoformat(), "episodes": out})
    total = sum(len(r.get("clips") or []) for r in out)
    print(f"wrote {INVENTORY.relative_to(ROOT)} — {len(out)} episodes, {total} clips")


def need_inventory():
    inv = load(INVENTORY, None)
    if not inv:
        sys.exit("no inventory yet — run: clips.py inventory")
    return inv


def find_clip(inv, slug, rank):
    for ep in inv["episodes"]:
        if ep["slug"] == slug:
            for c in ep.get("clips") or []:
                if c.get("rank") == rank:
                    return c
            sys.exit(f"episode '{slug}' has no clip rank {rank}")
    sys.exit(f"no episode with slug '{slug}'")


def cmd_list(show_all=False):
    inv = need_inventory()
    marks = load(TWEETED, {})
    print(f"inventory from {inv['fetchedAt'][:16]}  "
          f"(refresh: clips.py inventory · {len(marks)} marked tweeted)")
    for ep in sorted(
        [e for e in inv["episodes"] if e.get("clips")],
        key=lambda e: e["date"] or "",
        reverse=True,
    ):
        clips = ep["clips"]
        fresh = [c for c in clips if tweeted_key(ep["slug"], c["rank"]) not in marks]
        shown = clips if show_all else fresh
        if not shown:
            continue
        print(f"\n{ep['date']} {ep['slug']} — {len(fresh)}/{len(clips)} untweeted")
        for c in sorted(shown, key=lambda c: c["rank"]):
            mark = " [TWEETED]" if tweeted_key(ep["slug"], c["rank"]) in marks else ""
            print(f"  #{c['rank']:>2} [{round(c.get('durationSec', 0)):>3}s]"
                  f" {c.get('title', '?')}{mark}")


def cmd_show(slug, rank):
    c = find_clip(need_inventory(), slug, rank)
    marks = load(TWEETED, {})
    print(f"{slug} #{rank} — {c.get('title')}"
          f"{'  [TWEETED]' if tweeted_key(slug, rank) in marks else ''}")
    print(f"  {round(c.get('durationSec', 0))}s · {', '.join(c.get('speakers') or [])}"
          f" · {round(c.get('startSec', 0))}s–{round(c.get('endSec', 0))}s in episode")
    for kind in ("tweetShort", "tweetMedium", "tweetLong"):
        if c.get(kind):
            print(f"\n  {kind[5:].lower()}: {c[kind]}")
    print()
    for fmt, key in (("9:16", "mobile"), ("alt 9:16", "altMobile"), ("16:9", "landscape")):
        cid = (c.get(key) or {}).get("cid")
        if cid:
            print(f"  {fmt}: {GATEWAY}/{cid_of(cid)}")


def cmd_fetch(slug, rank):
    c = find_clip(need_inventory(), slug, rank)
    cid = (c.get("mobile") or {}).get("cid")
    if not cid:
        sys.exit("clip has no 9:16 mobile rendition")
    title_slug = re.sub(r"[^a-z0-9]+", "-", (c.get("title") or "clip").lower()).strip("-")[:40]
    day = datetime.now().strftime("%Y-%m-%d")
    dest = DESK / "media" / day / f"{slug}-{rank}-{title_slug}-9x16.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{GATEWAY}/{cid_of(cid)}?filename={dest.name}"
    print(f"fetching {url}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f"saved {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes)")
    print(f"draft it:  python3 scripts/desk.py new '<text>' --slug {slug}-clip{rank}")
    print(f"           then set frontmatter media: {dest.relative_to(DESK)}")
    print(f"and after posting:  python3 scripts/clips.py mark {slug} {rank}")


def cmd_mark(slug, rank, on=True):
    find_clip(need_inventory(), slug, rank)  # validate it exists
    marks = load(TWEETED, {})
    key = tweeted_key(slug, rank)
    if on:
        marks[key] = {"markedAt": datetime.now(timezone.utc).isoformat()}
    else:
        marks.pop(key, None)
    save(TWEETED, marks)
    print(f"{'marked' if on else 'unmarked'} {key} ({len(marks)} total)")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__.strip())
    cmd, rest = args[0], args[1:]
    if cmd == "inventory":
        cmd_inventory()
    elif cmd == "list":
        cmd_list(show_all="--all" in rest)
    elif cmd in ("show", "fetch", "mark", "unmark"):
        if len(rest) < 2:
            sys.exit(f"usage: clips.py {cmd} <slug> <rank>")
        slug, rank = rest[0], int(rest[1])
        {"show": cmd_show, "fetch": cmd_fetch,
         "mark": lambda s, r: cmd_mark(s, r, True),
         "unmark": lambda s, r: cmd_mark(s, r, False)}[cmd](slug, rank)
    else:
        sys.exit(f"unknown command '{cmd}'\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
