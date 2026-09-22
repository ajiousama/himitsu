#!/usr/bin/env python3
import json
import time
import urllib.request
from pathlib import Path

SLUG = "joshua-hkd"
API = f"https://kick.com/api/v2/channels/{SLUG}"
FREEWIFI = Path("freewifi")\nLIVE_OUT = Path("vod5/freewifi_live.m3u")
LOGO = "https://pbs.twimg.com/profile_images/826592912389451777/PnXfhxJD_400x400.jpg"
PROXY = "https://kick-resolver.onrender.com/kick?ch=gccx2"


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


def write_state(*, live, playback_detected, lookup_ok):
    Path("gccx2_live_state.json").write_text(
        json.dumps(
            {
                "slug": SLUG,
                "live": live,
                "playback_detected": playback_detected,
                "lookup_ok": lookup_ok,
                "mode": "stable-render-kick-proxy",
                "playback": PROXY if live is not False else None,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def write_live_projection(text):\n    start = text.find("# === KICK_MANAGED_START ===")\n    end_marker = "# === KICK_MANAGED_END ==="\n    end = text.find(end_marker, start + 1) if start >= 0 else -1\n    if start >= 0 and end >= 0:\n        LIVE_OUT.parent.mkdir(parents=True, exist_ok=True)\n        LIVE_OUT.write_text("#EXTM3U\\n\\n" + text[start:end + len(end_marker)].strip() + "\\n", encoding="utf-8")\n\n\ndef main():
    text = FREEWIFI.read_text(encoding="utf-8")
    old_url = current_cx2_url(text)

    data = get_json(API)
    if data is None:
        # If CX2 was already visible, keep that visibility but replace any old
        # short-lived KICK token with the stable resolver URL. A transient KICK
        # API failure must not leave an expiring direct HLS in FreeWiFi.
        if old_url:
            new_text = add_cx2(remove_cx2(text), PROXY)
            if new_text != text:
                FREEWIFI.write_text(new_text, encoding="utf-8")\n        write_live_projection(new_text)\n                write_live_projection(new_text)
                print("KICK lookup failed; preserved CX2 via stable Render resolver")
            else:
                print("KICK lookup failed; existing CX2 proxy kept unchanged")
            write_state(live=None, playback_detected=False, lookup_ok=False)
        else:
            print("KICK lookup failed; no current CX2 entry to preserve")
            write_state(live=None, playback_detected=False, lookup_ok=False)
        return 0

    playback = find_playback(data)
    live = bool(playback)
    new_text = remove_cx2(text)

    if live:
        new_text = add_cx2(new_text, PROXY)

    if new_text != text:
        FREEWIFI.write_text(new_text, encoding="utf-8")
        if live:
            print("CX2 Free Wi-Fi state changed: LIVE -> stable Render KICK resolver")
        else:
            print("CX2 Free Wi-Fi state changed: OFFLINE -> removed")
    else:
        print("CX2 Free Wi-Fi state unchanged:", "LIVE (proxy)" if live else "OFFLINE")

    write_state(live=live, playback_detected=bool(playback), lookup_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
