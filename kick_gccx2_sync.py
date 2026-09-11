#!/usr/bin/env python3
import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

SLUG = "joshua-hkd"
API = f"https://kick.com/api/v2/channels/{SLUG}"
FREEWIFI = Path("freewifi")
LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/kick_gccx2.svg"
MIN_VALID_SECONDS = 240


def get_json(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://kick.com/{SLUG}",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"KICK lookup attempt {attempt + 1} failed: {exc}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    return None


def find_playback(value):
    if isinstance(value, str):
        if value.startswith(("http://", "https://")) and ".m3u8" in value:
            return value
        return None
    if isinstance(value, list):
        for item in value:
            hit = find_playback(item)
            if hit:
                return hit
        return None
    if isinstance(value, dict):
        for key in ("playback_url", "playbackUrl", "hls_url", "hlsUrl", "stream_url", "streamUrl"):
            candidate = value.get(key)
            if isinstance(candidate, str) and ".m3u8" in candidate:
                return candidate
        for item in value.values():
            hit = find_playback(item)
            if hit:
                return hit
    return None


def current_cx2_url(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if 'tvg-id="kick.gccx2"' in line and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if candidate.startswith(("http://", "https://")):
                return candidate
    return None


def token_exp(url):
    if not url:
        return None
    try:
        token = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("token", [None])[0]
        if not token:
            return None
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def still_fresh(url):
    exp = token_exp(url)
    return bool(exp and exp - int(time.time()) > MIN_VALID_SECONDS)


def remove_cx2(text):
    lines = text.splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        if 'tvg-id="kick.gccx2"' in lines[i]:
            i += 1
            if i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith("#"):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def add_cx2(text, playback_url):
    block = (
        f'#EXTINF:-1 group-title="その他" tvg-id="kick.gccx2" tvg-logo="{LOGO}",ゲームセンターＣＸ2(KICK)\n'
        f"{playback_url}\n"
    )
    nogi = '#EXTINF:-1 group-title="その他" tvg-id="kick.nogizaka"'
    pos = text.find(nogi)
    if pos >= 0:
        return text[:pos] + block + text[pos:]
    end = "# === KICK_MANAGED_END ==="
    pos = text.find(end)
    if pos >= 0:
        return text[:pos] + block + text[pos:]
    return text.rstrip() + "\n" + block


def main():
    text = FREEWIFI.read_text(encoding="utf-8")
    old_url = current_cx2_url(text)

    data = get_json(API)
    if data is None:
        print("KICK lookup failed; keeping current Free Wi-Fi state unchanged")
        return 0

    playback = find_playback(data)
    live = bool(playback)
    final_url = None
    new_text = remove_cx2(text)

    if live:
        if still_fresh(old_url):
            final_url = old_url
        else:
            final_url = playback
        new_text = add_cx2(new_text, final_url)

    if new_text != text:
        FREEWIFI.write_text(new_text, encoding="utf-8")
        if live:
            print("CX2 Free Wi-Fi state changed: LIVE -> refreshed direct KICK HLS")
        else:
            print("CX2 Free Wi-Fi state changed: OFFLINE -> removed")
    else:
        print("CX2 Free Wi-Fi state unchanged:", "LIVE (token still fresh)" if live else "OFFLINE")

    exp = token_exp(final_url)
    Path("gccx2_live_state.json").write_text(
        json.dumps(
            {
                "slug": SLUG,
                "live": live,
                "playback_detected": bool(playback),
                "mode": "direct-kick-playback",
                "token_expires_at": exp,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
