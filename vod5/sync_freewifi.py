#!/usr/bin/env python3
from pathlib import Path
import re

FREEWIFI = Path("freewifi")
LIVE = Path("vod5/freewifi_live.m3u")
SPECIALS = Path("vod5/freewifi_specials.m3u")
PLAYLIST = Path("vod5/playlist.m3u")
LIVE_START = "# === KICK_MANAGED_START ==="
LIVE_END = "# === KICK_MANAGED_END ==="
SP_START = "# === GMCX_LONG_VOD_START ==="
SP_END = "# === GMCX_LONG_VOD_END ==="
VOD5_START = "# === VOD5_CATALOG_START ==="
VOD5_END = "# === VOD5_CATALOG_END ==="

def managed(path: Path, start: str, end: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(re.escape(start) + r".*?" + re.escape(end), text, re.S)
    return (m.group(0).strip() + "\n") if m else ""

def playlist_block(path: Path, start: str, end: str) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return (start + "\n" + body + "\n" + end + "\n") if body else ""

def replace(text: str, start: str, end: str, payload: str) -> str:
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if pat.search(text):
        return pat.sub(payload.strip(), text, count=1)
    if payload:
        return text.rstrip() + "\n\n" + payload.strip() + "\n"
    return text

def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    text = replace(text, LIVE_START, LIVE_END, managed(LIVE, LIVE_START, LIVE_END))
    text = replace(text, VOD5_START, VOD5_END, playlist_block(PLAYLIST, VOD5_START, VOD5_END))
    text = replace(text, SP_START, SP_END, managed(SPECIALS, SP_START, SP_END))
    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")
    print("vod5 KICK live/full catalog projections synced")

if __name__ == "__main__":
    main()
