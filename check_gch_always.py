#!/usr/bin/env python3
"""Reject FreeWiFi updates that drop an always-on Green Channel route."""
from pathlib import Path
import re
import json

PLAYLIST = Path("freewifi")
GROUP = "今日の開催場"
LOCAL_RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
REGIONAL = {
    "JRA EAST WEB3 HQ": ("jra.east.hq", "jra.east", "gch_east_master.m3u8"),
    "JRA EAST WEB3 LQ": ("jra.east.lq", "jra.east", "gch_east_LQ.m3u8"),
    "JRA WEST WEB4 HQ": ("jra.west.hq", "jra.west", "gch_west_master.m3u8"),
    "JRA WEST WEB4 LQ": ("jra.west.lq", "jra.west", "gch_west_LQ.m3u8"),
    "JRA LOCAL WEB5 HQ": ("jra.local.hq", "jra.hokkaido", "gch_hokkaido_master.m3u8"),
    "JRA LOCAL WEB5 LQ": ("jra.local.lq", "jra.hokkaido", "gch_hokkaido_LQ.m3u8"),
}
REQUIRED = {
    "グリーンチャンネル MAIN HQ": (
        "jra.gch.hq",
        "https://raw.githubusercontent.com/ajiousama/himitsu/main/gchmain_master.m3u8",
    ),
    "グリーンチャンネル MAIN LQ": (
        "jra.gch.lq",
        "https://raw.githubusercontent.com/ajiousama/himitsu/main/gchmain_LQ.m3u8",
    ),
    "グリーンチャンネル (5002直)": (
        "jra.gch.hq",
        "http://67.215.237.218:5002/bs14.m3u8?gid=bs14&token=guoziyun&channel=zhongying&uin=159413&ts=0&sign=&playseek=0",
    ),
}


def main() -> None:
    text = PLAYLIST.read_text(encoding="utf-8-sig")
    start = text.find("# === TODAY_JRA_START ===")
    end = text.find("# === TODAY_JRA_END ===", start)
    if start < 0 or end < start:
        raise SystemExit("GCH always-on guard: TODAY_JRA block is missing")
    block = text[start:end]
    if ('earphone' + '1981') in block:
        raise SystemExit('GCH/JRA guard: retired external source returned')
    lines = text.splitlines()
    found = {}
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        name = line.rsplit(",", 1)[-1].strip()
        if name not in REQUIRED and name not in REGIONAL:
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
    status_path = Path("today_jra_status.json")
    if status_path.is_file():
        active = set(json.loads(status_path.read_text(encoding="utf-8-sig")).get("active_ids") or [])
        for name, (cid, family, filename) in REGIONAL.items():
            actual = found.get(name)
            if family in active and actual != (cid, f"{LOCAL_RAW}/{filename}", GROUP):
                raise SystemExit(f"Weekend JRA guard: {name} missing or changed: {actual!r}")
            if family not in active and actual is not None:
                raise SystemExit(f"Weekend JRA guard: inactive source unexpectedly present: {name}")
            if not Path(filename).is_file():
                raise SystemExit(f"Weekend JRA guard: local source missing: {filename}")
    for filename in ("gchmain_master.m3u8", "gchmain_LQ.m3u8"):
        if not Path(filename).is_file():
            raise SystemExit(f"GCH guard: local source missing: {filename}")
    if "haruka" in text.lower():
        raise SystemExit("GCH guard: retired HARUKA route returned")
    print("GCH/JRA local-source guard OK: MAIN HQ/LQ, 5002 and weekend regional routes")


if __name__ == "__main__":
    main()
