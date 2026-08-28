#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.parse
import urllib.request

UA = "Mozilla/5.0"


def get(url: str, timeout: int = 60) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type") or ""
    return data, ctype


def first_payload(url: str, depth: int = 0) -> tuple[str, bytes]:
    if depth > 5:
        raise RuntimeError("playlist nesting too deep")
    data, ctype = get(url)
    textish = "mpegurl" in ctype.lower() or data.lstrip().startswith(b"#EXTM3U")
    if not textish:
        if len(data) < 256:
            raise RuntimeError(f"media payload too small: {len(data)} bytes")
        return url, data

    text = data.decode("utf-8", "replace")
    if "#EXTM3U" not in text:
        raise RuntimeError("response is not an HLS playlist")
    candidates = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not candidates:
        raise RuntimeError("playlist has no media URI")
    return first_payload(urllib.parse.urljoin(url, candidates[0]), depth + 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: radiko_public_selftest.py https://host/live/RNB", file=sys.stderr)
        return 2
    start = sys.argv[1]
    media_url, payload = first_payload(start)
    print(f"PUBLIC AUDIO OK bytes={len(payload)} url={media_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
