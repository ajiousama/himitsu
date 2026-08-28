#!/usr/bin/env python3
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def first_media_url(text, base):
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return urllib.parse.urljoin(base, s)
    return None


def check(start_url):
    url = start_url
    for depth in range(5):
        data, ctype = fetch(url)
        if data.startswith(b"#EXTM3U") or "mpegurl" in ctype.lower():
            text = data.decode("utf-8", "replace")
            nxt = first_media_url(text, url)
            if not nxt:
                raise RuntimeError(f"empty HLS playlist at depth {depth}: {url}")
            url = nxt
            continue
        if len(data) < 256:
            raise RuntimeError(f"media payload too small: {len(data)} bytes from {url}")
        print(f"OK media={len(data)} bytes depth={depth} url={url}")
        return 0
    raise RuntimeError("HLS nesting too deep")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: radiko_selftest.py URL")
    try:
        raise SystemExit(check(sys.argv[1]))
    except Exception as e:
        print(f"NG {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(1)
