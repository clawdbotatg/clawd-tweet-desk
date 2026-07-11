"""Minimal Twitter API client — pure stdlib, OAuth 1.0a user context.

Covers what the desk needs deterministically:
  - post_tweet(text, reply_to=, media_ids=)   POST /2/tweets
  - upload_media(path)                        v1.1 media/upload (simple, images)
  - delete_tweet(tweet_id)                    DELETE /2/tweets/:id

Anything beyond this (search, timelines, DMs) → add here or fall back to the
browser. Credentials come from the repo-root .env via load_env().
"""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(ROOT, ".env")

CRED_KEYS = {
    "api_key": "TWITTER_API_KEY",
    "api_secret": "TWITTER_API_SECRET",
    "access_token": "TWITTER_ACCESS_TOKEN",
    "access_secret": "TWITTER_ACCESS_SECRET",
}


class NotConfigured(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status, body):
        self.status, self.body = status, body
        super().__init__(f"HTTP {status}: {body}")


def load_env(path=ENV_PATH):
    """Parse KEY=VALUE lines; also honors real env vars (they win)."""
    env = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith(("TWITTER_", "TELEGRAM_"))})
    return env


def load_creds():
    env = load_env()
    creds = {short: env.get(var, "") for short, var in CRED_KEYS.items()}
    missing = [CRED_KEYS[k] for k, v in creds.items() if not v]
    if missing:
        raise NotConfigured(
            "Twitter API keys not configured — missing: " + ", ".join(missing)
            + f"\nFill them into {ENV_PATH} (see .env.example)."
            + "\nFallback: post via the browser (claude-in-chrome) and log it with 'desk.py mark-posted'."
        )
    return creds


def _pct(s):
    return urllib.parse.quote(str(s), safe="~-._")


def _oauth1_header(method, url, query, creds):
    oauth = {
        "oauth_consumer_key": creds["api_key"],
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["access_token"],
        "oauth_version": "1.0",
    }
    params = {**query, **oauth}
    param_str = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(params.items()))
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    key = f"{_pct(creds['api_secret'])}&{_pct(creds['access_secret'])}".encode()
    sig = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def _request(method, url, creds, query=None, json_body=None, raw_body=None, content_type=None):
    query = query or {}
    full = url + ("?" + urllib.parse.urlencode(query) if query else "")
    headers = {"Authorization": _oauth1_header(method, url, query, creds)}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        data = raw_body
        headers["Content-Type"] = content_type
    req = urllib.request.Request(full, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode()) from None


def post_tweet(text, creds=None, reply_to=None, media_ids=None, quote=None):
    """Post one tweet; returns {'id': ..., 'text': ...}."""
    creds = creds or load_creds()
    body = {"text": text}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": str(reply_to)}
    if media_ids:
        body["media"] = {"media_ids": [str(m) for m in media_ids]}
    if quote:
        body["quote_tweet_id"] = str(quote)
    out = _request("POST", "https://api.twitter.com/2/tweets", creds, json_body=body)
    return out.get("data", out)


def delete_tweet(tweet_id, creds=None):
    creds = creds or load_creds()
    return _request("DELETE", f"https://api.twitter.com/2/tweets/{tweet_id}", creds)


def upload_media(path, creds=None):
    """Simple (non-chunked) media upload — fine for images. Returns media_id string."""
    creds = creds or load_creds()
    with open(path, "rb") as f:
        payload = f.read()
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="{os.path.basename(path)}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    out = _request(
        "POST",
        "https://upload.twitter.com/1.1/media/upload.json",
        creds,
        raw_body=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    return str(out["media_id"])
