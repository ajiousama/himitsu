#!/usr/bin/env python3
import json
import time
import urllib.request
from pathlib import Path

SLUG = "joshua-hkd"
API = f"https://kick.com/api/v2/channels/{SLUG}"
FREEWIFI = Path("freewifi")
LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/kick_gccx2.svg"
PLAY_URL = "https://himitsu-six.vercel.app/api/kick2"


def get_json(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://kick.com/",
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


def add_cx2(text):
    block = (
        f'#EXTINF:-1 group-title="その他" tvg-id="kick.gccx2" tvg-logo="{LOGO}",ゲームセンターＣＸ2(KICK)\n'
        f"{PLAY_URL}\n"
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
    data = get_json(API)
    if data is None:
        raise SystemExit("KICK lookup failed; keeping current Free Wi-Fi state unchanged")

    playback = find_playback(data)
    live = bool(playback)
    text = FREEWIFI.read_text(encoding="utf-8")
    new_text = remove_cx2(text)
    if live:
        new_text = add_cx2(new_text)

    if new_text != text:
        FREEWIFI.write_text(new_text, encoding="utf-8")
        print("CX2 Free Wi-Fi state changed:", "LIVE -> added" if live else "OFFLINE -> removed")
    else:
        print("CX2 Free Wi-Fi state unchanged:", "LIVE" if live else "OFFLINE")

    Path("gccx2_live_state.json").write_text(
        json.dumps({"slug": SLUG, "live": live, "playback_detected": bool(playback)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
