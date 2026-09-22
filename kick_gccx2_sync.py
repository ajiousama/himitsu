#!/usr/bin/env python3
import json
import time
import urllib.request
from pathlib import Path

CONFIG = Path("vod5/kick_channels.json")
FREEWIFI = Path("freewifi")
LIVE_OUT = Path("vod5/freewifi_live.m3u")
STATE_OUT = Path("vod5/kick_live_state.json")

PROXIES = {
    "kick.gccx2": "https://kick-resolver.onrender.com/kick?ch=gccx2",
    "kick.nogizaka": "https://himitsu-six.vercel.app/api/kick?ch=nogizaka",
    "kick.seiz": "https://kick-resolver.onrender.com/kick?ch=seiz",
}
ORDER = ["kick.gccx2", "kick.nogizaka", "kick.seiz"]


def get_json(slug):
    url = f"https://kick.com/api/v2/channels/{slug}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://kick.com/{slug}",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"KICK lookup {slug} attempt {attempt + 1} failed: {exc}")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return None


def find_playback(value):
    if isinstance(value, str):
        return value if value.startswith(("http://", "https://")) and ".m3u8" in value else None
    if isinstance(value, list):
        for item in value:
            hit = find_playback(item)
            if hit:
                return hit
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


def parse_entries(text):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:"):
            ext = lines[i]
            url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            out.append((ext, url))
            i += 2
            continue
        i += 1
    return out


def id_from_ext(ext):
    marker = 'tvg-id="'
    if marker not in ext:
        return ""
    return ext.split(marker, 1)[1].split('"', 1)[0]


def managed_block(text):
    start = text.find("# === KICK_MANAGED_START ===")
    end_marker = "# === KICK_MANAGED_END ==="
    end = text.find(end_marker, start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        raise RuntimeError("KICK managed block missing")
    end += len(end_marker)
    return start, end, text[start:end]


def build_entry(item, url):
    return (
        f'#EXTINF:-1 group-title="その他" tvg-id="{item["tvg_id"]}" '
        f'tvg-logo="{item.get("logo", "")}",{item.get("name", item["tvg_id"])}\n'
        f"{url}\n"
    )


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    by_id = {str(x.get("tvg_id")): x for x in config if isinstance(x, dict)}
    text = FREEWIFI.read_text(encoding="utf-8")
    start, end, old_block = managed_block(text)
    old_entries = {id_from_ext(ext): (ext, url) for ext, url in parse_entries(old_block)}

    states = {}
    active = {}
    for tvg_id in ORDER:
        item = by_id.get(tvg_id)
        if not item:
            continue
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        data = get_json(slug)
        if data is None:
            if tvg_id in old_entries:
                active[tvg_id] = PROXIES[tvg_id]
            states[tvg_id] = {"slug": slug, "lookup_ok": False, "live": None, "preserved": tvg_id in old_entries}
            continue
        playback = find_playback(data)
        live = bool(playback)
        if live:
            active[tvg_id] = PROXIES[tvg_id]
        states[tvg_id] = {"slug": slug, "lookup_ok": True, "live": live, "playback_detected": bool(playback)}

    lines = ["# === KICK_MANAGED_START ===", "## KICK"]
    for tvg_id in ORDER:
        if tvg_id in active and tvg_id in by_id:
            lines.append(build_entry(by_id[tvg_id], active[tvg_id]).rstrip())
    lines.append("# === KICK_MANAGED_END ===")
    new_block = "\n".join(lines)

    new_text = text[:start] + new_block + text[end:]
    FREEWIFI.write_text(new_text.rstrip() + "\n", encoding="utf-8")
    LIVE_OUT.parent.mkdir(parents=True, exist_ok=True)
    LIVE_OUT.write_text("#EXTM3U\n\n" + new_block + "\n", encoding="utf-8")
    STATE_OUT.write_text(json.dumps(states, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("KICK live channels:", list(active))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
