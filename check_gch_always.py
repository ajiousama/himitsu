#!/usr/bin/env python3
"""Reject FreeWiFi updates that drop an always-on Green Channel route."""
from pathlib import Path
import re

PLAYLIST = Path("freewifi")
GROUP = "今日の開催場"
REQUIRED = {
    "グリーンチャンネル MAIN HQ": (
        "jra.gch.hq",
        "https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/gchmain.m3u8",
    ),
    "グリーンチャンネル MAIN LQ": (
        "jra.gch.lq",
        "https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/gchmain_LQ.m3u8",
    ),
    "グリーンチャンネル (5002直)": (
        "jra.gch.hq",
        "http://67.215.237.218:5002/bs14.m3u8?gid=bs14&token=guoziyun&channel=zhongying&uin=159413&ts=0&sign=&playseek=0",
    ),
    "グリーンチャンネル (HARUKA)": (
        "jra.gch.hq",
        "http://118.69.27.222:9394/stream/60.m3u8",
    ),
}


def main() -> None:
    text = PLAYLIST.read_text(encoding="utf-8-sig")
    start = text.find("# === TODAY_JRA_START ===")
    end = text.find("# === TODAY_JRA_END ===", start)
    if start < 0 or end < start:
        raise SystemExit("GCH always-on guard: TODAY_JRA block is missing")
    lines = text.splitlines()
    found = {}
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        name = line.rsplit(",", 1)[-1].strip()
        if name not in REQUIRED:
            continue
        if name in found:
            raise SystemExit(f"GCH always-on guard: duplicate entry: {name}")
        tvg_id = re.search(r'tvg-id="([^"]+)"', line)
        group = re.search(r'group-title="([^"]+)"', line)
        url = lines[index + 1].strip() if index + 1 < len(lines) else ""
        found[name] = (tvg_id.group(1) if tvg_id else "", url, group.group(1) if group else "")
        if not (start < text.find(line) < end):
            raise SystemExit(f"GCH always-on guard: source escaped TODAY_JRA block: {name}")

    for name, (expected_id, expected_url) in REQUIRED.items():
        expected = (expected_id, expected_url, GROUP)
        actual = found.get(name)
        if actual != expected:
            raise SystemExit(f"GCH always-on guard: {name} missing or changed: {actual!r}")
    print("GCH always-on guard OK: MAIN HQ/LQ, 5002 direct, HARUKA; all in today's venues")


if __name__ == "__main__":
    main()
